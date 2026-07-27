# Hook 系统设计哲学：为什么不用 If-Else

---

## 一、Hook vs If-Else 的本质区别

### If-Else 的做法

```python
def execute_tool(tool_call):
    if tool_call.name == "Bash" and "rm -rf" in tool_call.command:
        raise Denied("危险命令")
    if tool_call.name == "Write" and tool_call.file_path.endswith(".env"):
        raise Denied("敏感文件")
    if tool_call.name == "WebFetch" and tool_call.url not in allowed_domains:
        raise Denied("不允许的域名")
    # ... 无穷无尽的条件
    result = tool_call.execute()
```

问题：
- 每加一个新规则，就要改源码
- 所有规则耦合在一个函数里，越滚越大
- 不同来源的规则（用户、项目、插件）混在一起
- 改规则要重启程序

### Hook 的解法

```json
// settings.json — 不改源码
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash(rm -rf:*)",   "command": "deny.sh" },
      { "matcher": "Write(*.env)",     "command": "warn.sh" },
      { "matcher": "WebFetch(*)",      "webhook": "https://audit.example.com" }
    ]
  }
}
```

本质上是把**策略（Policy）从机制（Mechanism）中分离出来**。

### 配置结构

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash|Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "/path/to/script.sh",
            "timeout": 10
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          { "type": "command", "command": "check_prompt.sh" }
        ]
      }
    ]
  }
}
```

- **matcher**：正则表达式，匹配工具名（仅 `PreToolUse` / `PostToolUse` 支持）
- **type**：目前仅支持 `"command"`
- **timeout**：可选，超时秒数

### matcher 语法

matcher 使用**正则表达式**：

| 表达式 | 含义 |
|--------|------|
| `"Bash"` | 仅匹配 Bash 工具 |
| `"Edit\|Write\|MultiEdit"` | 匹配多种编辑工具 |
| `".*"` | 匹配所有工具 |
| `"Bash(npm:.*)"` | 匹配特定参数的 Bash 命令 |

---

## 二、五个关键差异

### 1. 配置 vs 代码

| If-Else | Hook |
|---------|------|
| 改规则 = 改源码 + 重新编译 | 改规则 = 编辑 JSON 文件 |
| 只有开发者能改 | 任何用户都能改 |
| 规则隐藏在代码里 | 规则透明可见 |

### 2. 多源组合

```
PreToolUse 被触发:
  ├── 用户级配置（~/.claude/settings.json）
  ├── 项目级配置（项目/.claude/settings.json）
  ├── 插件注入的 Hook
  └── CLAUDE.md 中声明的 Hook
         ↓
    全部注册到同一个事件上，按优先级执行
```

If-Else 做不到——不能让用户、项目、插件三方的规则在同一个函数里独立注册、互不干扰。

### 3. 热加载

```
改了 if-else:
  重新编译 → 重启 → 重新建立会话 → 丢失上下文

改了 hook 配置:
  保存 JSON → 立即生效，无需重启
```

### 4. 可中断决策链

Hook 的执行结果有三个级别（通过 JSON stdout 的 `permissionDecision` 字段返回，仅 PreToolUse 适用）：

| 返回值 | 行为 |
|--------|------|
| `allow` | 允许工具执行 |
| `deny` | 拒绝工具执行 |
| `ask` | 提示用户决定 |

此外，任何 hook 都可通过**退出码**控制流程：

| 退出码 | 行为 |
|--------|------|
| `0` | 成功，继续执行 |
| `2` | 阻止操作（stderr 内容反馈给 Claude） |
| 其他非零 | 非阻塞错误，显示警告但不阻止 |

If-Else 只能 true/false。Hook 可以把决策延迟到用户，或通过退出码阻止操作并把错误信息回灌给模型。

### 5. 独立失败域

```
if-else 中的一个检查抛异常:
  → 整个 execute_tool 崩溃

Hook A 执行失败:
  → 记录日志
  → 不影响 Hook B 的执行
  → 不影响工具本身的执行（如果 Hook 没有 deny）
```

---

## 三、执行类型

| 类型 | 机制 | 适用场景 |
|------|------|---------|
| **command** | 执行 Shell 脚本，通过 stdin 传入 JSON、通过退出码/stdout 返回决策 | 本地检查、发送通知、自定义审批流程 |

> 注：目前官方仅支持 `command` 类型。LLM 评估、webhook 回调等并非官方内置的 hook type，需要用户在 command 脚本中自行调用外部服务来实现。

---

## 四、设计哲学：外部化策略

来自 Claude Code 的 13 条设计原则之一：

> 策略应该写成配置文件，不是代码。机制是通用的，策略是具体的。

核心循环（`queryLoop`）是**机制**——它只负责"调用前触发 PreToolUse 事件"。
权限规则是**策略**——它定义"什么情况下拒绝"。

两者通过事件总线解耦，互不感知。这也是"98.4% 是基础设施"的体现——基础设施提供 hook 点，策略通过配置注入。

### 完整事件列表（官方 27 种）

> 以下清单通过直接核实本地安装的 Claude Code 源码 `cli.js` 第 6594-6670 行的事件定义对象 `MQ8` 得出，是最权威的一手来源。官方公开文档（docs.anthropic.com）目前只覆盖其中一部分，以源码为准。

#### 会话与生命周期

| 事件 | 触发时机 | Matcher | 阻止能力 |
|------|---------|---------|---------|
| `SessionStart` | 新会话启动时 | `source`（startup/resume/clear/compact） | 阻止错误被忽略 |
| `SessionEnd` | 会话结束时 | `reason`（clear/logout/prompt_input_exit/other） | 否 |
| `Setup` | 仓库初始化/维护时 | `trigger` | 阻止错误被忽略 |
| `ConfigChange` | 配置文件在会话中变更时 | `source` | 退出码 2 阻止应用 |
| `InstructionsLoaded` | 指令文件（CLAUDE.md 等）加载时 | `load_reason` | 仅观测，不支持阻止 |

#### 用户输入与对话

| 事件 | 触发时机 | Matcher | 阻止能力 |
|------|---------|---------|---------|
| `UserPromptSubmit` | 用户提交 prompt 时 | 无 | 退出码 2 阻止处理 |
| `Notification` | 发送通知时 | `notification_type`（permission_prompt/idle_prompt/auth_success/elicitation_*） | 否 |

#### 工具调用

| 事件 | 触发时机 | Matcher | 阻止能力 |
|------|---------|---------|---------|
| `PreToolUse` | 工具执行之前 | `tool_name` | 退出码 2 阻止工具调用 |
| `PostToolUse` | 工具成功执行之后 | `tool_name` | 退出码 2 向模型显示 stderr |
| `PostToolUseFailure` | 工具执行失败之后 | `tool_name` | 退出码 2 向模型显示 stderr |
| `PermissionRequest` | 权限对话框显示时 | `tool_name` | 可返回 allow/deny 决定 |
| `PermissionDenied` | auto 模式分类器拒绝工具调用之后 | `tool_name` | 可返回 `retry:true` 让模型重试 |

#### 响应结束

| 事件 | 触发时机 | Matcher | 阻止能力 |
|------|---------|---------|---------|
| `Stop` | Claude 即将结束响应时 | 无 | 退出码 2 继续对话 |
| `StopFailure` | 回合因 API 错误结束时（替代 Stop） | `error`（rate_limit/authentication_failed/billing_error/...） | fire-and-forget，输出被忽略 |
| `SubagentStart` | 子代理启动时 | `agent_type` | 阻止错误被忽略 |
| `SubagentStop` | 子代理即将结束响应时 | `agent_type` | 退出码 2 继续子代理运行 |

#### 上下文压缩

| 事件 | 触发时机 | Matcher | 阻止能力 |
|------|---------|---------|---------|
| `PreCompact` | 对话压缩之前 | `trigger`（manual/auto） | 退出码 2 阻止压缩；stdout 可作为自定义压缩指令 |
| `PostCompact` | 对话压缩之后 | `trigger`（manual/auto） | 否 |

#### 任务与协作

| 事件 | 触发时机 | Matcher | 阻止能力 |
|------|---------|---------|---------|
| `TaskCreated` | 任务创建时 | 无 | 退出码 2 阻止创建 |
| `TaskCompleted` | 任务标记完成时 | 无 | 退出码 2 阻止完成 |
| `TeammateIdle` | 队友即将空闲时 | 无 | 退出码 2 阻止空闲 |

#### MCP 与外部交互

| 事件 | 触发时机 | Matcher | 阻止能力 |
|------|---------|---------|---------|
| `Elicitation` | MCP 服务器请求用户输入时 | `mcp_server_name` | 退出码 2 拒绝 |
| `ElicitationResult` | 用户响应 MCP elicitation 之后 | `mcp_server_name` | 退出码 2 阻止响应 |

#### 工作区与文件

| 事件 | 触发时机 | Matcher | 阻止能力 |
|------|---------|---------|---------|
| `WorktreeCreate` | 创建隔离工作树时 | 无 | 非零退出码表示创建失败 |
| `WorktreeRemove` | 移除工作树时 | 无 | 否 |
| `CwdChanged` | 工作目录变更后 | 无 | 否 |
| `FileChanged` | 被监视文件变更时 | 无 | 否 |

#### 关于"Checkpoint"的澄清

原文档曾列出 `Checkpoint` 事件，**实际不存在**。Claude Code 代码中的 "Checkpoint" 指的是 git 快照机制（用于 /rewind 等功能），与 hooks 系统无关。

Hook 覆盖了 Agent 的完整生命周期：从会话启动、指令加载、用户输入、工具调用、权限决策、上下文压缩、子代理、任务协作、MCP 交互到工作区文件变更。

---

> 基于对话记录整理，更新时间：2026-07-13（已对齐本地 Claude Code 源码核实：27 种事件、command 类型、三级决策）

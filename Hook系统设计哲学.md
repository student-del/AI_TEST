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

Hook 的执行结果有四个级别：

| 返回值 | 行为 |
|--------|------|
| `allow` | 跳过后续 Hook，直接允许执行 |
| `deny` | 阻止执行，返回错误信息 |
| `ask` | 弹窗询问用户决定 |
| `continue` | 不决策，交给下一个 Hook 判断 |

If-Else 只能 true/false。Hook 可以把决策延迟到用户，或委托给 LLM（`type: "llm"`），或转发到外部服务（`type: "webhook"`）。

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

## 三、四种执行类型

| 类型 | 机制 | 适用场景 |
|------|------|---------|
| **command** | 执行 Shell 脚本 | 本地检查、发送通知 |
| **LLM** | 由模型评估决策 | 需要语义理解的安全判断 |
| **webhook** | HTTP 回调外部服务 | 企业审计、外部系统集成 |
| **subagent verifier** | 子代理验证 | 自动检查工作结果 |

---

## 四、设计哲学：外部化策略

来自 Claude Code 的 13 条设计原则之一：

> 策略应该写成配置文件，不是代码。机制是通用的，策略是具体的。

核心循环（`queryLoop`）是**机制**——它只负责"调用前触发 PreToolUse 事件"。
权限规则是**策略**——它定义"什么情况下拒绝"。

两者通过事件总线解耦，互不感知。这也是"98.4% 是基础设施"的体现——基础设施提供 hook 点，策略通过配置注入。

### 完整事件列表（13 种）

```
会话生命周期: SessionStart → SessionEnd → Checkpoint
      ↓
工具调用:     PreToolUse → PostToolUse / PostToolUseFailure
      ↓
上下文压缩:   PreCompact → PostCompact
      ↓
安全与权限:   PermissionDenied
      ↓
任务与停止:   TaskCreated → Stop / StopFailure
      ↓
通用通知:     Notification (permission_prompt, idle_prompt, auth_success...)
```

Hook 覆盖了 Agent 的完整生命周期，不仅是工具前后。

---

> 基于对话记录整理，更新时间：2026-06-14

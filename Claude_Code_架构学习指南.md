# Claude Code 架构学习指南

> 本文档基于源码分析、学术论文（arXiv 2604.14228）、社区拆解和官方文档整理，旨在帮助系统性地学习 Claude Code 的设计与实现。

---

## 目录

1. [概述与核心理念](#1-概述与核心理念)
2. [整体架构：5 层子系统](#2-整体架构5-层子系统)
3. [Agent 循环：9 步对话管道](#3-agent-循环9-步对话管道)
4. [表层：四种入口与终端 UI](#4-表层四种入口与终端-ui)
5. [核心层：上下文组装与压缩](#5-核心层上下文组装与压缩)
6. [安全/执行层：权限与工具](#6-安全执行层权限与工具)
7. [状态层：持久化与记忆](#7-状态层持久化与记忆)
8. [后端层：Shell、工具与 MCP](#8-后端层shell工具与-mcp)
9. [扩展性系统：Hook、Skill、Plugin、MCP](#9-扩展性系统hookskillpluginmcp)
10. [子代理系统](#10-子代理系统)
11. [权限系统深度解析](#11-权限系统深度解析)
12. [会话持久化机制](#12-会话持久化机制)
13. [CLAUDE.md 层级体系](#13-claudemd-层级体系)
14. [自动记忆系统](#14-自动记忆系统)
15. [环境与配置](#15-环境与配置)
16. [设计理念与原则](#16-设计理念与原则)
17. [学习资源](#17-学习资源)

---

## 1. 概述与核心理念

### 一句话概括

Claude Code 本质上是一个 **ReAct 循环**：

```python
while claude_response.has_tool_call:
    result = execute_tool(tool_call)
    claude_response = send_to_claude(result)
return claude_response.text
```

约 **98.4%** 的代码是围绕这个简单循环的决定性基础设施，只有约 1.6% 是 AI 决策逻辑。循环本身很简单，工程工作在于围绕它的各个子系统。

### 五大核心价值

| 价值 | 说明 |
|------|------|
| **人类决策权威** | 人类保持控制；当 93% 批准率显示疲劳时，重构边界而非增加警告 |
| **安全、安保、隐私** | 7 个独立安全层，即使在人类警惕松懈时仍能保护系统 |
| **可靠执行** | 收集-执行-验证循环，优雅恢复，追加型状态 |
| **能力放大** | "一个 Unix 工具，而非一个产品" |
| **上下文自适应** | CLAUDE.md 层级、渐进式扩展性、随时间推移的信任轨道 |

### 十三条设计原则

1. **拒绝优先** — deny 永远覆盖 allow
2. **渐进信任** — 权限每会话重新建立，不复用
3. **纵深防御** — 7 个独立安全层
4. **外部化策略** — 配置写成文件，不是代码
5. **上下文作为稀缺资源** — 5 级压缩管线
6. **追加型状态** — JSONL 追加写入，可审计、可回溯
7. **最小脚手架** — 不过度抽象
8. **价值观重于规则** — 原则指导而非机械执行
9. **可组合扩展** — Hook、Skill、Plugin 三级扩展
10. **可逆性加权风险** — 考虑操作的可逆性
11. **透明文件式配置** — 一切配置可见、可编辑
12. **隔离子代理边界** — 子代理上下文不污染父代理
13. **优雅恢复** — API 失败时自动降级、重试

---

## 2. 整体架构：5 层子系统

```
┌──────────────────────────────────────────────┐
│  表层 (Surface)                              │
│  CLI | Headless | SDK | IDE | React+Ink UI   │
├──────────────────────────────────────────────┤
│  核心层 (Core)                               │
│  queryLoop | 上下文组装 | 5级压缩 | 子代理    │
├──────────────────────────────────────────────┤
│  安全/执行层 (Safety/Action)                 │
│  7种权限模式 | 27个Hook事件 | 42+工具 | 沙箱  │
├──────────────────────────────────────────────┤
│  状态层 (State)                              │
│  JSONL转录 | CLAUDE.md | 自动记忆 | Sidechain│
├──────────────────────────────────────────────┤
│  后端层 (Backend)                            │
│  Bash/PowerShell | MCP(7种传输) | 内置工具   │
└──────────────────────────────────────────────┘
```

### 技术栈

| 组件 | 技术 |
|------|------|
| 运行时 | Bun |
| 语言 | TypeScript |
| Schema 校验 | Zod v4 |
| 终端 UI | React + Ink |
| 文件搜索 | 内置 ripgrep |
| 外部扩展 | MCP 协议 |
| 包管理 | npm 全局安装 |

---

## 3. Agent 循环：9 步对话管道

每个对话回合按固定管线执行：

```
1. 设置解析 (Settings Resolution)
      ↓
2. 状态初始化 (State Initialization)
      ↓
3. 上下文组装 (Context Assembly) ← 9 个来源注入
      ↓
4. 5 个预模型整形器 (Pre-Model Shapers) ← 按成本递增
   ├── Budget Reduction: 单条消息大小上限（始终活跃）
   ├── Snip: 裁剪较早历史（功能门控）
   ├── Microcompact: 缓存感知细粒度压缩（始终活跃）
   ├── Context Collapse: 读取时虚拟投影（非破坏性）
   └── Auto-Compact: 模型生成摘要（最后手段）
      ↓
5. 模型调用 (Model Call)
      ↓
6. 工具派发 (Tool Dispatch)
      ↓
7. 权限门控 (Permission Gate)
      ↓
8. 工具执行 (Tool Execution)
      ↓
9. 停止条件检查 (Stop Condition Check)
      ↓
   循环回到步骤 3，直到无工具调用
```

### 恢复机制

| 机制 | 说明 |
|------|------|
| 最大输出 Token 升级 | 最多 3 次重试，每次扩大上限 |
| 响应式压缩 | 每回合最多一次 |
| Prompt-too-long 处理 | 裁剪上下文 |
| 流式回退 | 流式失败时回退到非流式 |
| 模型切换 | 主模型失败时切换到备用模型 |

---

## 4. 表层：四种入口与终端 UI

### 四种入口

| 入口 | 说明 | 使用场景 |
|------|------|---------|
| **CLI** | 交互式终端界面 | 日常开发 |
| **Headless** | 非交互式 `-p` 模式 | CI/CD 管道 |
| **SDK** | 编程式调用 | 应用集成 |
| **IDE** | VS Code / JetBrains 扩展 | IDE 内使用 |

所有入口最终汇聚到同一个 `queryLoop` — **不允许多个执行引擎**。

### 终端 UI

- 使用 **React + Ink** 渲染终端界面
- 支持流式渲染、diff 展示、动画效果
- 组件化架构，与 Web React 开发体验类似

---

## 5. 核心层：上下文组装与压缩

### 9 个有序上下文来源

按优先级从高到低：

| 优先级 | 来源 | 说明 |
|--------|------|------|
| 1 | 系统提示 | 角色定义、行为约束 |
| 2 | 环境信息 | OS、Shell、工作目录、日期 |
| 3 | CLAUDE.md 层级 | 项目指导文件 |
| 4 | 路径作用域规则 | 文件访问范围 |
| 5 | 自动记忆 | 基于文件的内存系统 |
| 6 | 工具元数据 | 可用工具的描述和参数 |
| 7 | 对话历史 | 当前会话的完整历史 |
| 8 | 工具结果 | 最近工具执行返回值 |
| 9 | 压缩摘要 | 早期对话的压缩版本 |

### 5 阶段压缩管线

上下文窗口有限，需要分层压缩：

| 阶段 | 说明 | 触发条件 |
|------|------|---------|
| **Budget Reduction** | 限制单条消息大小 | 始终活跃 |
| **Snip** | 裁剪较早的对话历史 | 功能门控触发 |
| **Microcompact** | 缓存感知的细粒度压缩 | 始终活跃 |
| **Context Collapse** | 读取时的虚拟投影（非破坏性） | 按需 |
| **Auto-Compact** | 使用模型生成摘要替换历史 | 最后手段 |

**关键设计**：Microcompact 利用了 LLM 的缓存机制（如 Anthropic 的 prompt caching），在压缩的同时保持缓存命中率。

---

## 6. 安全/执行层：权限与工具

### 7 种权限模式

| 模式 | 行为 | 信任级别 |
|------|------|---------|
| `plan` | 用户先批准计划再执行 | 最低 |
| `default` | 标准交互式审批 | 低 |
| `acceptEdits` | 文件编辑 + 文件系统 shell 自动批准 | 中 |
| `auto` | ML 分类器评估工具安全性 | 高 |
| `dontAsk` | 不提示，deny 规则仍然执行 | 更高 |
| `bypassPermissions` | 跳过大多数提示，安全检查保留 | 最高 |
| `bubble` | 内部：子代理上报给父代理 | 特殊 |

### 4 级授权管线

```
1. 预过滤 → 从模型视图中剥离 denied 工具
        ↓
2. PreToolUse hooks → 可返回 permissionDecision
        ↓
3. 规则评估 → deny-first（deny 永远覆盖 allow）
        ↓
4. 权限处理 → 4 分支：
   ├── coordinator（协调器）
   ├── swarm worker（集群工作器）
   ├── speculative classifier（推测分类器）
   └── interactive（交互式）
```

### 7 个独立安全层

1. 工具预过滤
2. Deny-first 规则评估
3. 权限模式约束
4. Auto-mode ML 分类器（`yoloClassifier.ts`）
5. Shell 沙箱（文件系统 + 网络隔离）
6. 恢复时不恢复权限（每会话重新建立）
7. 基于 Hook 的拦截

---

## 7. 状态层：持久化与记忆

### 三种持久化通道

| 通道 | 格式 | 用途 |
|------|------|------|
| **Session transcripts** | 追加型 JSONL | 完整对话记录，链式修补压缩边界 |
| **Global prompt history** | JSONL | 跨会话提示召回 |
| **Subagent sidechains** | 独立 JSONL | 隔离子代理历史 |

**设计权衡**：追加型 JSONL 优先考虑可审计性和简单性，而非查询性能。每个事件人类可读、可版本控制。

### 用户目录结构 (`~/.claude/`)

```
~/.claude/
├── settings.json              # 项目环境变量 (API key, 模型配置)
├── settings.local.json        # 本地权限规则 (allow/deny list)
├── .claude.json               # 全局配置 (projects, MCP, 遥测)
├── history.jsonl              # 跨会话提示历史
├── changelog.md               # 版本发布说明缓存
├── sessions/                  # 会话转录 (每个会话一个文件夹)
├── projects/                  # 项目级配置 (按路径哈希分目录)
├── plans/                     # 计划模式文档
├── tasks/                     # 后台任务状态
├── backups/                   # .claude.json 自动备份
├── shell-snapshots/           # Shell 快照脚本
├── file-history/              # 文件编辑历史
├── telemetry/                 # 遥测事件日志
├── plugins/                   # 插件系统
│   └── marketplaces/
│       └── claude-plugins-official/
│           ├── plugins/       # 第一方插件
│           └── external_plugins/  # 第三方 MCP 集成
├── downloads/                 # 下载文件
└── cache/                     # 缓存
```

---

## 8. 后端层：Shell、工具与 MCP

### 完整工具列表（20 种）

| 工具 | 功能 | 关键参数 |
|------|------|---------|
| **Agent** | 启动子代理 | description, prompt, subagent_type, model, isolation |
| **Bash** | 执行 Shell 命令 | command, timeout, description, run_in_background |
| **TaskOutput** | 获取后台任务结果 | task_id, block, timeout |
| **ExitPlanMode** | 退出计划模式 | allowedPrompts |
| **FileEdit** | 精确字符串替换 | file_path, old_string, new_string, replace_all |
| **FileRead** | 读取文件 | file_path, offset, limit, pages |
| **FileWrite** | 写入文件 | file_path, content |
| **Glob** | 文件模式匹配 | pattern, path |
| **Grep** | 内容搜索（ripgrep） | pattern, path, glob, output_mode |
| **TaskStop** | 停止后台任务 | task_id |
| **ListMcpResources** | 列出 MCP 资源 | server |
| **Mcp** | 执行 MCP 工具 | 任意参数 |
| **NotebookEdit** | 编辑 Jupyter Notebook | notebook_path, cell_id, cell_type, edit_mode |
| **ReadMcpResource** | 读取 MCP 资源 | server, uri |
| **TodoWrite** | 任务列表管理 | todos[] |
| **WebFetch** | 获取网页内容 | url, prompt |
| **WebSearch** | 网络搜索 | query, allowed_domains, blocked_domains |
| **AskUserQuestion** | 向用户提问 | questions[] (最多 4 题) |
| **Config** | 配置管理 | — |
| **Enter/ExitWorktree** | Git worktree 管理 | action, discard_changes |

### MCP 协议

支持 7 种传输类型：
- stdio
- SSE (Server-Sent Events)
- HTTP
- WebSocket
- SDK
- IDE 扩展
- 自定义传输

---

## 9. 扩展性系统：Hook、Skill、Plugin、MCP

### 四种扩展机制对比

| 机制 | 上下文成本 | 关键能力 |
|------|-----------|---------|
| **Hooks** | 零 | 27 个事件，4 种执行类型 |
| **Skills** | 低 | SKILL.md 含 YAML frontmatter |
| **Plugins** | 中 | 10 种组件类型 |
| **MCP Servers** | 高 | 7 种传输类型的外部工具 |

### Agent 循环中的 3 个注入点

```
assemble() → 模型看到什么
  ├── CLAUDE.md 层级
  ├── Skill 描述
  ├── MCP 资源
  └── Hook 注入上下文

model() → 模型能调用什么
  ├── 内置工具（20 种）
  ├── MCP 工具
  ├── SkillTool
  └── AgentTool

execute() → 动作是否/如何执行
  ├── 权限规则
  ├── PreToolUse / PostToolUse hooks
  └── Stop hooks
```

### SkillTool vs AgentTool

| 特性 | SkillTool | AgentTool |
|------|-----------|-----------|
| 机制 | 向当前上下文注入指令 | 生成新的隔离上下文窗口 |
| 成本 | 低 | 高（约 7 倍 tokens） |
| 上下文 | 共享父代理上下文 | 独立上下文窗口 |
| 适用场景 | 轻量级行为定制 | 复杂独立任务 |

### Hook 系统

#### 事件类型

| 事件 | 触发时机 |
|------|---------|
| **SessionStart** | 会话开始时 |
| **PreToolUse** | 工具执行前（可拦截/修改） |
| **PostToolUse** | 工具执行后 |
| **Notification** | 通知事件（permission_prompt, idle_prompt, auth_success 等） |
| **PermissionDenied** | Auto 模式拒绝后 |
| **TaskCreated** | 任务创建时（阻塞式） |
| **Stop** | 停止时 |

#### 四种执行类型

| 类型 | 说明 |
|------|------|
| **command** | 执行 Shell 脚本 |
| **LLM** | 由模型评估 |
| **webhook** | HTTP 回调 |
| **subagent verifier** | 子代理验证 |

#### 配置示例

```json
{
  "hooks": {
    "SessionStart": [{
      "hooks": [{ "type": "command", "command": "echo '会话开始'" }]
    }],
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{ "type": "command", "command": "validate-command.sh" }]
    }],
    "PostToolUse": [{
      "hooks": [{ "type": "command", "command": "notify.sh" }]
    }]
  }
}
```

---

## 10. 子代理系统

### 6 种内置子代理类型

| 类型 | 用途 |
|------|------|
| **Explore** | 探索代码库 |
| **Plan** | 设计实现方案 |
| **General-purpose** | 通用任务 |
| **Claude Code Guide** | 回答 Claude Code 相关问题 |
| **Verification** | 验证结果 |
| **Statusline-setup** | 配置状态行 |

### 自定义代理

通过 `.claude/agents/*.md` 文件定义，支持 YAML frontmatter：

```yaml
---
tools: [Read, Grep, Glob]
model: sonnet
permissions: acceptEdits
hooks: []
skills: []
---
```

### 三种隔离模式

| 模式 | 机制 | 默认 |
|------|------|------|
| **Worktree** | Git worktree（文件系统隔离） | 否 |
| **Remote** | 远程执行（内部功能） | 否 |
| **In-process** | 共享文件系统，隔离对话 | 是 |

### Sidechain 转录

- 每个子代理写入独立的 `.jsonl` 文件
- **只有摘要返回给父代理**，完整历史不进入父代理上下文
- 多实例协调通过 POSIX `flock()` 实现（零外部依赖）

---

## 11. 权限系统深度解析

### 权限配置结构

`settings.local.json` 中的权限规则：

```json
{
  "permissions": {
    "allow": [
      "Bash(git:*)",
      "Bash(npm:*)",
      "Bash(node:*)",
      "Read(*)",
      "Glob(*)"
    ],
    "deny": [
      "Bash(rm -rf:*)",
      "Bash(curl:*)"
    ]
  }
}
```

### 权限评估逻辑

1. **Deny 永远覆盖 allow** — 即使有匹配的 allow 规则，deny 也优先
2. 规则按顺序匹配，第一个匹配的 deny 立即阻止
3. 支持通配符：`Bash(python:*)` 匹配所有以 `python` 开头的命令
4. 权限模式决定未匹配规则的默认行为

### 安全不变量

> 权限**从不**在恢复时保留 — 信任每会话重新建立。

这是最核心的安全设计决策之一，在保持安全不变量的代价下接受用户摩擦。

---

## 12. 会话持久化机制

### 转录格式（JSONL）

每行一个 JSON 对象，追加写入：

```jsonl
{"type":"user","content":"修复登录页面的 bug"}
{"type":"assistant","content":"我来帮你修复..."}
{"type":"tool_use","tool":"Read","input":{"file_path":"..."}}
{"type":"tool_result","output":"..."}
```

### 设计特点

- **追加型**：只追加不修改，保证完整性
- **人类可读**：JSON 格式，无需专门工具解读
- **链式修补**：压缩边界通过 JSONL 中的应用层标记追踪
- **版本控制友好**：纯文本，可纳入 git 管理

### 三种存储位置

| 位置 | 内容 | 生命周期 |
|------|------|---------|
| `sessions/` | 当前会话完整转录 | 会话期间 |
| `history.jsonl` | 跨会话提示历史 | 持久 |
| `projects/` 下的子代理 sidechain | 子代理独立转录 | 子代理生命周期 |

---

## 13. CLAUDE.md 层级体系

### 四级配置

| 级别 | 路径 | 作用域 | 提交到 Git |
|------|------|--------|-----------|
| **Managed** | `/etc/claude-code/CLAUDE.md` | 系统级（企业） | 否 |
| **User** | `~/.claude/CLAUDE.md` | 用户级 | 否 |
| **Project** | `CLAUDE.md`、`.claude/CLAUDE.md`、`.claude/rules/*.md` | 项目级 | 是 |
| **Local** | `CLAUDE.local.md` | 个人（gitignored） | 否 |

### 关键设计

- CLAUDE.md 是**用户上下文**（概率性遵守），不是系统提示（确定性执行）
- 权限规则提供**确定性**执行层
- 多个文件按层级合并，级别越高优先级越高

---

## 14. 自动记忆系统

### 设计特点

- **无向量数据库**：不依赖 embedding 或向量检索
- **基于 LLM 扫描**：LLM 扫描记忆文件头部的 YAML frontmatter
- **按需选择**：每次最多选择 5 个相关记忆文件
- **完全可审计**：Markdown 文件，可手动编辑、版本控制
- **项目隔离**：每个项目的记忆独立存储在 `~/.claude/projects/<项目名>/memory/` 下

### 记忆类型

| 类型 | 用途 | 示例 |
|------|------|------|
| **user** | 用户角色、偏好、知识背景 | 用户是资深后端开发 |
| **feedback** | 用户给出的行为指导 | 测试必须用真实数据库 |
| **project** | 项目背景、目标、约束 | 下周四起冻结合入 |
| **reference** | 外部系统资源指针 | 在 Linear "INGEST" 项目中跟踪 bug |

### 文件结构

```
~/.claude/projects/<project>/
├── MEMORY.md              # 索引文件，列出所有记忆条目
├── user_role.md           # 具体记忆内容
├── feedback_testing.md
└── ...
```

每个记忆文件格式：

```markdown
---
name: 记忆名称
description: 简短描述，用于判断相关性
type: user | feedback | project | reference
---

记忆内容...
```

---

## 15. 环境与配置

### 安装位置

| 项目 | 路径 |
|------|------|
| NPM 全局包 | `C:\Users\juwei\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\` |
| CLI 入口 | `C:\Users\juwei\AppData\Roaming\npm\cli.js`（约 13MB） |
| 用户配置 | `C:\Users\juwei\.claude\` |

### 包结构

```
@anthropic-ai/claude-code/
├── cli.js              # 主入口 (编译后的 Bun 二进制)
├── package.json        # npm 包定义
├── sdk-tools.d.ts      # 完整工具类型定义 (约 4297 行)
└── vendor/
    ├── audio-capture/  # 音频捕获原生插件
    └── ripgrep/        # 内置 ripgrep 二进制（各平台）
```

---

## 16. 设计理念与原则

### 核心洞察："98.4% 是基础设施"

Claude Code 的核心极其简单 — 一个 ReAct while 循环。工程工作的重点在于：
- 上下文管理（组装、压缩、缓存）
- 安全模型（权限、沙箱、Hook）
- 可靠性（恢复、重试、降级）
- 扩展性（工具、MCP、插件）

### 值得学习的工程决策

1. **统一入口**：所有接口共享同一个 `queryLoop`，杜绝多引擎
2. **追加型持久化**：JSONL 追加写入，零查询开销，完美审计
3. **文件记忆替代向量数据库**：简单、可审计、可版本控制
4. **子代理隔离**：上下文污染是真实问题，sidechain 是优雅解法
5. **Deny-first 安全模型**：从零信任开始，逐步授权
6. **CLAUDE.md 不是系统提示**：是概率性指导，权限规则才是确定性约束
7. **不保留会话间信任**：每次新会话重新建立权限，减少持久化风险

---

## 17. 学习资源

### 必读

| 资源 | 链接 | 说明 |
|------|------|------|
| **学术论文** | [arXiv 2604.14228](https://arxiv.org/html/2604.14228v1) | VILA-Lab 的系统性架构分析，最权威 |
| **官方文档** | [code.claude.com/docs](https://code.claude.com/docs/en/overview) | 官方使用和配置文档 |
| **官方 GitHub** | [anthropics/claude-code](https://github.com/anthropics/claude-code) | 反馈、Issue、更新日志 |

### 社区深度拆解

| 资源 | 说明 |
|------|------|
| [VILA-Lab/Dive-into-Claude-Code](https://github.com/VILA-Lab/Dive-into-Claude-Code) | 学术级架构分析 |
| [HZ0108/Inside-Claude-Code](https://github.com/HZ0108/Inside-Claude-Code-Architecture-and-Design-Philosophy) | 架构与设计哲学详解 |
| [FlorianBruniaux/claude-code-ultimate-guide](https://github.com/FlorianBruniaux/claude-code-ultimate-guide) | 实用指南含架构文档 |

### 本地源码

```
C:\Users\juwei\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\
├── cli.js           # 编译后主文件（约 13MB）
└── sdk-tools.d.ts   # 工具类型定义（约 4297 行）
```

### 推荐学习路径

1. **先读论文** — arXiv 2604.14228，从学术视角理解设计空间
2. **看类型定义** — `sdk-tools.d.ts`，理解所有工具的输入输出
3. **看社区拆解** — 三个 GitHub 仓库从不同角度解读
4. **动手实践** — 自己写一个简化的 ReAct Agent，理解循环本身
5. **读源码** — 从 CLI 入口开始追踪 `queryLoop` 的执行路径
6. **深入子系统** — 按兴趣选择：权限系统、压缩管线、Hook 机制等

---

> 文档更新时间：2026-05-29

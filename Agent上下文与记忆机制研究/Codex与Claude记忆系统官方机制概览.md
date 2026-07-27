# Codex 与 Claude 有记忆系统吗？官方机制概览

> 更新时间：2026-07-26  
> 证据范围：仅以 OpenAI、Anthropic 官方文档、官方博客及 OpenAI 官方源码仓库为事实依据。官方未公开的选择算法、提示词、服务端存储结构等，不作推断。

## 结论

有，但“记忆”不是模型权重里永久记住了用户，而是 Agent 产品在模型外部保存信息，并在之后把相关信息重新放入模型上下文。

应至少区分三层：

1. **会话工作记忆**：当前消息、工具结果、打开的文件等，受上下文窗口限制。
2. **长会话连续性**：历史过长时压缩/摘要，然后继续运行。
3. **跨会话持久记忆**：把规则、偏好、项目事实存入线程历史或可持久化文件，在新会话中重新加载。

Claude Code 与 Codex 都覆盖这三类需求，但公开程度不同：Claude Code 已公开自动记忆的本地文件布局和加载阈值；Codex 官方公开了线程、压缩、`AGENTS.md` 和可审阅 memory/vault 的产品机制，但未完整公开其自动挑选、召回和服务端实现。

## 一、Claude Code

### 1. 人写的持久指令：`CLAUDE.md`

`CLAUDE.md` 是人维护的 Markdown 指令文件，可处于组织、用户、项目或本地范围。Claude Code 在会话开始时把适用内容加载进上下文；子目录规则可在访问对应目录时按需加载。

它适合保存构建命令、编码规范、项目架构和工作流。它是上下文指导，不是客户端强制策略；必须强制的限制应使用权限设置或 Hook。

### 2. Claude 自写的跨会话自动记忆

Anthropic 官方文档明确称 Claude Code 有“自动记忆”，默认开启：

- 每个项目存于 `~/.claude/projects/<project>/memory/`；
- 入口为 `MEMORY.md`，还可包含 `debugging.md` 等主题文件；
- 每次会话启动加载 `MEMORY.md` 的前 200 行或前 25KB，以先达到者为准；
- 主题文件不在启动时全部加载，Claude 需要时用文件工具读取；
- Claude 会在工作中判断哪些构建命令、调试经验、架构信息、偏好或习惯值得保存；
- 文件是本地纯 Markdown，可审计、编辑和删除；同一仓库的 worktree 共享，但不自动跨机器或云环境同步。

因此其公开实现模式是：

```text
对话/工具执行
  → Claude 判断某信息以后是否有用
  → 写入 MEMORY.md 或主题文件
  → 新会话预载 MEMORY.md 的有限索引
  → 需要细节时按需读取主题文件
  → 内容重新进入上下文，影响本次推理
```

官方没有公开“值得记住”的完整评分算法或内部提示词。

### 3. 长会话压缩

Anthropic 官方工程文章说明：Claude Code 会把消息历史交给模型做摘要压缩，尽量保留架构决策、未解决问题和实现细节，丢弃冗余工具输出或消息，再用压缩后的上下文继续。官方文章还举例称会配合最近访问的五个文件。

压缩只是单个长会话的续航机制，不等于跨会话自动记忆；摘要可能损失细节。

## 二、OpenAI Codex

### 1. 会话/线程连续性

Codex 使用线程保存任务对话与工作状态。OpenAI 官方介绍称，Codex App 的 Agent 运行在按项目组织的独立线程中，可在任务之间切换而不丢失上下文；CLI、IDE 与 App 也可延续既有会话历史与配置。

### 2. 仓库级持久指令：`AGENTS.md`

`AGENTS.md` 是 Codex 的持久项目指导层。它不是 Agent 自发形成的“经验记忆”，而是人写、可版本控制、可团队审阅的外部记忆。官方开源仓库和文档表明，其内容会作为模型可见的用户指令上下文提供给模型，并具有目录范围。

它和 Claude Code 的 `CLAUDE.md` 属于同一类机制：把稳定规则保存在模型外，每次任务再注入上下文。

### 3. 长会话压缩

OpenAI 官方产品介绍确认 Codex 支持压缩会话状态，使长会话更易管理；当前产品还存在自动压缩，CLI 保留了手动 `/compact`。可安全确认其作用是以更短的表示替代部分旧历史，从而释放上下文窗口。

但官方面向用户的资料没有完整公开当前各端的触发阈值、摘要提示词、保留字段和服务端数据结构，不能把某版本源码常量当作所有 Codex 产品的稳定机制。

### 4. 跨线程 memory / vault

OpenAI 2026 年官方长任务指南把 Memory 描述为“可打开、编辑、diff 和复用”的笔记，并建议把人物偏好、项目状态、决定和未闭环事项记录到 memory vault；持久线程的历史也可保存在其中。官方同时强调仓库保存代码，vault 保存围绕工作的滚动上下文，并可借助 GitHub diff 审阅记忆变化。

据此可以确认：Codex 当前已有面向长任务的可持久、可审阅记忆工作流。不能仅凭该指南进一步断言所有 Codex 表面都采用同一个自动抽取管线、固定目录、固定召回算法或固定遗忘周期；这些细节官方没有在本次可核查资料中完整披露。

## 三、对照

| 机制 | Claude Code | Codex |
|---|---|---|
| 当前会话上下文 | 对话、工具结果、文件 | 对话、工具结果、项目/IDE上下文 |
| 人写持久规则 | `CLAUDE.md`、`.claude/rules/` | `AGENTS.md` |
| Agent 自动跨会话笔记 | 已公开本地 `memory/`、`MEMORY.md` 和加载限制 | 官方确认 memory/vault 工作流，但统一内部管线未完整公开 |
| 长会话续航 | 模型摘要压缩历史 | 会话状态压缩、自动压缩，CLI 有 `/compact` |
| 可审计性 | 纯 Markdown，可编辑删除 | `AGENTS.md` 可版本控制；vault 指南强调可打开、编辑、diff、复用 |

## 四、核心认识

这类系统的本质通常不是“LLM 自己永久学习”，而是：

```text
持久化存储（文件/线程/vault）
        ↓ 选择与加载
提示词/上下文窗口
        ↓
模型本次推理
        ↓
必要时更新外部记忆
```

所以它会遗忘或记错：没有被写入、没有被召回、压缩摘要遗漏、记忆过期或与当前事实冲突，都会造成看似“失忆”。稳定且必须遵守的规则应放入 `AGENTS.md` / `CLAUDE.md` 或强制策略；动态经验才适合自动记忆。

## 官方来源

- [Anthropic：Claude 如何记住你的项目](https://code.claude.com/docs/zh-CN/memory)
- [Anthropic：Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [OpenAI：Introducing upgrades to Codex](https://openai.com/index/introducing-upgrades-to-codex/)
- [OpenAI：Introducing the Codex app](https://openai.com/index/introducing-the-codex-app/)
- [OpenAI：Codex-maxxing for long-running work（PDF）](https://cdn.openai.com/pdf/8a9f00cf-d379-4e20-b06f-dd7ba5196a11/OAI_WhitePaper_Codex-maxxing26.pdf)
- [OpenAI 官方 Codex 仓库：AGENTS.md 文档入口](https://github.com/openai/codex/blob/main/docs/agents_md.md)


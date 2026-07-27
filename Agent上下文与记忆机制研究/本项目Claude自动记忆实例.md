# 本项目 Claude Code 自动记忆实例

> 检查日期：2026-07-15  
> 检查对象：`C:\Users\juwei\.claude\projects\E--AI-TEST\memory\`

## 检查结果

项目仓库 `E:\AI_TEST` 内没有 `MEMORY.md` 或 memory 目录；`C:\Users\juwei\.codex\memories` 也不存在。因此当前没有发现 Codex 本地 memory。

Claude Code 为该项目建立了机器本地 auto-memory：

```text
memory/
├── MEMORY.md
├── conversation_local_save.md
├── feedback_verify_before_overwrite.md
├── reference_hook_fires_on_slash_commands.md
└── user_language.md
```

## 文件结构

`MEMORY.md` 是简短索引，每行包含主题文件链接和一句摘要。主题文件使用 Markdown frontmatter：

```yaml
---
name: 记忆名称
description: 用于判断未来相关性的一句话摘要
type: feedback
---
```

frontmatter 之后是具体内容，部分文件还包含 `Why` 和 `How to apply`，用于保存原因和使用方式。

本项目现有类型包括：

- `feedback`：用户反馈、行为偏好或需要避免的错误；
- `reference`：经过调查得到的外部机制或实现参考。

## 发现的陈旧冲突

`conversation_local_save.md` 仍记录“所有技术讨论都必须保存”，但当前仓库 `AGENTS.md` 已明确改为“仅 AI Agent 学习相关内容需要保存”。

这说明：

1. Auto-memory 不会因为项目规则修改而自动保持一致；
2. Memory 只能作为历史线索，使用前需要与当前 `AGENTS.md` 核对；
3. 冲突时应遵守当前项目指导，并更新或删除陈旧 memory；
4. 将 memory 当作绝对约束会导致旧要求继续污染后续会话。

本次只读取并分析了 memory，没有修改 `C:\Users\juwei\.claude\projects\E--AI-TEST\memory\` 下的原始文件。

## 证据性质

以上内容是本机 Claude Code memory 文件的直接观察，不代表 Anthropic 对所有版本、环境或用户的通用实现保证。产品通用机制仍应以 Anthropic 官方文档为准。

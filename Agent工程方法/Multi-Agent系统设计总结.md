# Claude Code Multi-Agent 系统设计总结

---

## 一、核心架构

Claude Code 的多代理系统基于一个简单原则：**AgentTool 创建独立 Agent 循环，Sidechain 保证上下文隔离**。

```
父代理 (主 queryLoop)
  │
  ├─ 调用 Agent({description, prompt, subagent_type, ...})
  │
  ├──→ 子代理 A (独立 queryLoop)
  │      ├─ 独立上下文窗口
  │      ├─ 独立 Sidechain JSONL 转录
  │      └─ 完成 → 只返回摘要
  │
  ├──→ 子代理 B (后台运行)
  │      ├─ run_in_background: true
  │      └─ 完成 → 通知父代理
  │
  └──→ 子代理 C (Worktree 隔离)
         ├─ isolation: "worktree"
         └─ Git worktree 中隔离执行
```

---

## 二、AgentTool vs SkillTool：本质区别

| | AgentTool | SkillTool |
|---|---|---|
| **本质** | 开一个新的独立对话 | 在当前对话中注入一页指令 |
| **上下文** | 完全独立窗口 | 共享父代理上下文 |
| **成本** | 高（~7x tokens） | 低（仅注入文本） |
| **隔离** | Sidechain + 可选 Worktree | 无隔离 |
| **返回** | 只返回摘要 | 结果直接进入上下文 |

**选择逻辑**：需要独立 ReAct 循环 → AgentTool，只需注入指令 → SkillTool

---

## 三、Sidechain 隔离机制（最核心设计）

子代理的完整对话历史**从不进入父代理上下文**：

```
子代理执行过程:
  [系统提示] [环境] [CLAUDE.md] [prompt] → [工具调用] → [工具结果] → ...
        ↓ 全部记录在独立的 sidechain JSONL 中
        ↓
子代理完成:
  ┌─────────────────────────────────────┐
  │ 返回给父代理的只有:                   │
  │  · 最终文本输出（content[].text）     │
  │  · 元数据（token数、耗时、工具调用次数）│
  │  · AgentOutput (约几百 token)         │
  └─────────────────────────────────────┘
  
  父代理永远看不到子代理 5000 行的完整对话历史
```

**三层隔离**：
- **转录隔离**：独立的 sidechain JSONL 文件
- **上下文隔离**：不共享窗口，子代理看不到父代理的历史
- **文件系统隔离**（可选）：Worktree 模式下使用独立代码副本

---

## 四、6 种内置子代理

| 类型 | 用途 | 典型场景 |
|------|------|---------|
| **Explore** | 只读探索代码库 | 搜索文件、理解结构 |
| **Plan** | 设计实现方案 | 架构决策、步骤规划 |
| **General-purpose** | 通用任务 | 大多数编程任务 |
| **Claude Code Guide** | 回答工具问题 | 配置、用法咨询 |
| **Verification** | 验证结果 | Hook 中的自动检查 |
| **Statusline-setup** | 配置状态行 | IDE 状态行定制 |

---

## 五、并发与协调

**执行模式**：
- **同步**（默认）：父代理等待子代理完成
- **异步**（`run_in_background: true`）：后台执行，完成后通知

**协调机制**：
- **flock() 文件锁**：多实例共享资源互斥（零外部依赖）
- **SendMessage**：通过 `name` 参数命名子代理，可寻址收发消息
- **team_name**：多代理协作时指定团队上下文

**权限 Bubble 模式**：子代理权限审批"气泡"到父代理，由父代理统一处理。

---

## 六、自定义代理

通过 `.claude/agents/*.md` 定义：

```yaml
---
tools: [Read, Grep, Glob]
model: sonnet
permissions: acceptEdits
---

代理的角色描述和行为约束...
```

---

## 七、关键设计原则

1. **只返回摘要** — 完整 sidechain 历史不污染父代理上下文
2. **渐进隔离** — in-process → worktree → remote（按需升级）
3. **零外部依赖** — flock() 文件锁，不依赖 Redis/DB
4. **文件即配置** — 自定义代理通过 .md 文件定义

---

> 基于源码分析和调研整理，更新时间：2026-06-14

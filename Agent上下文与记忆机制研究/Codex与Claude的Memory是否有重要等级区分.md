# Codex 与 Claude 的 Memory 是否有重要等级区分

> 更新时间：2026-07-28  
> 证据范围：仅采用 OpenAI、Anthropic 官方文档、官方博客或官方仓库。官方未披露的内部评分、提示词和检索算法不作推断。

> **范围修正**：本文原版误将 `CLAUDE.md`、`AGENTS.md` 的指令优先级纳入了主要回答。用户实际询问的是自动记忆目录中的 `MEMORY.md`。以下“补充更正”才是该问题的直接答案；后文关于指令文件的内容仅作为反例保留，不应混同于 `MEMORY.md` 的重要性机制。

## 补充更正：只看 `MEMORY.md`

### 直接答案

**Claude 与 Codex 的官方 `MEMORY.md` 都没有公开的逐条 `high / medium / low` 重要等级字段。**

但两者都会在生成、整理或读取记忆时做筛选，形成事实上的重要性差异：

| 系统 | 显式重要度字段 | 实际区分方式 |
|---|---|---|
| Claude Code auto memory | 官方未公开 | 是否值得未来会话使用；是否进入启动时加载的 `MEMORY.md` 索引；详细内容是否移入按需读取的主题文件；是否陈旧 |
| OpenAI Codex memories | 官方开源实现未显示统一的高/中/低字段 | 近期线程资格、线程年龄、memory 最近使用时间、项目/cwd 适用范围、摘要与详细记忆分层、模型合并与去重 |

### Claude 的 `MEMORY.md`

Claude 会自行判断信息“对未来对话是否有用”，决定要不要保存。这是一个**写入筛选**，但 Anthropic 没有公开评分公式或等级标签。

写入后又有两层：

```text
MEMORY.md
  = 简洁索引
  = 每次会话只预载前 200 行或 25KB

其他 topic files
  = 详细记忆
  = 不在启动时预载，需要时再读取
```

因此，进入 `MEMORY.md` 有更高的启动可见性；进入主题文件则是冷记忆。Claude Code 接近容量上限时会提示 Claude：

- 每项尽量保持一行；
- 把细节移到主题文件；
- 合并或丢弃陈旧条目。

从 v2.1.214 起，带 YAML frontmatter 的 memory 文件在被 Claude 写入时会记录 `modified` 时间。这提供新旧程度线索，**仍不是 importance 分数**。

### Codex 的 `MEMORY.md`

OpenAI 官方 Codex 仓库已经公开启动时运行的两阶段 memory 管线：

```text
Phase 1：从符合条件的近期线程提取结构化 raw memory
Phase 2：把 raw memories 合并、去重并整理为全局 memory 产物
```

公开配置中可以看到这些筛选量：

- `max_rollout_age_days`：参与记忆生成的线程最大年龄；
- `max_rollouts_per_startup`：每轮最多处理多少线程；
- `max_raw_memories_for_consolidation`：合并时最多保留多少近期 raw memories；
- `max_unused_days`：一条 memory 距离上次使用多久后，不再具有 Phase 2 选择资格；
- memory block 的项目/cwd 适用范围。

这说明 Codex 确实区分记忆的保留/选择价值，主要依据**时间、是否使用、适用项目和模型合并判断**。但官方实现没有据此公开一个通用的：

```yaml
importance: high
```

也没有公开固定的综合评分公式。

Codex 中还要区别：

- `memory_summary.md`：面向新会话注入的压缩摘要；
- `MEMORY.md`：更详细、可进一步查阅的整合记忆；
- `raw_memories.md` / rollout summaries：更靠近提取来源的中间材料。

这是**摘要层级和读取层级**，不是每条记录的显式重要等级。

### 一个容易造成误解的证据

OpenAI Codex 官方 issue 中有人提议给主题 memory 添加：

```yaml
priority: high
```

并介绍某个社区维护 fork 已经这样实现。但该内容是用户提案和社区 fork 行为，OpenAI 维护者没有把它声明为官方 Codex 机制。因此不能用它证明官方 Codex 的 `MEMORY.md` 具有 `priority` 等级。

### 最准确的结论

```text
Claude：
模型判断是否值得记
  + MEMORY.md 热索引 / topic files 冷详情
  + modified 新旧线索
  ≠ 官方高/中/低评分

Codex：
线程年龄与资格
  + 最近是否使用
  + cwd/project 适用范围
  + 两阶段提取、合并、摘要
  ≠ 官方高/中/低评分
```

官方证据：

- [Anthropic：Claude Code auto memory](https://code.claude.com/docs/en/memory#auto-memory)
- [OpenAI Codex 官方仓库：Memories Pipeline](https://github.com/openai/codex/blob/main/codex-rs/core/src/memories/README.md)
- [OpenAI Codex 官方仓库：memory 配置 schema](https://github.com/openai/codex/blob/main/codex-rs/core/config.schema.json)

## 结论

有“重要性差异”，但要区分两种含义：

1. **没有公开的统一重要度标签**：截至本次核查，OpenAI 和 Anthropic 都没有公开说明 Codex/Claude Code 会给每条记忆保存一个通用的 `high / medium / low` 或数值 `importance score`，再据此统一排序。
2. **存在结构性的优先层级**：信息来源的权威性、适用范围的具体程度、是否在启动时常驻、是否按路径/主题按需加载，以及容量限制，会使不同信息事实上具有不同的保留与生效强度。

因此，准确说法是：

> 两者存在“指令优先级、作用域和加载层级”，Claude auto memory 还存在未公开算法的价值筛选；但不能把这些统称为官方公开的逐条记忆重要度评分系统。

## 一、需要分开的四种“等级”

| 维度 | 回答的问题 | 是否等于记忆重要度 |
|---|---|---|
| 指令权威 | 冲突时听谁的 | 否，但决定行为优先级 |
| 作用域具体性 | 哪条规则更贴近当前目录/任务 | 否，但影响适用优先级 |
| 加载层级 | 启动常驻还是按需读取 | 否，但影响被模型看到的概率 |
| 保存筛选 | 哪些经验值得跨会话保存 | 最接近“重要性判断”，但算法未公开 |

## 二、Codex 怎么区分

### 2.1 `AGENTS.md` 是持久指令，不是逐条打分的经验库

OpenAI 官方资料说明：

- `AGENTS.md` 对其所在目录树生效；
- 更深目录中的 `AGENTS.md` 在冲突时优先；
- prompt 中直接给出的 system/developer/user 指令优先于 `AGENTS.md`；
- Codex 汇集用户级和项目目录链上的指令时，通常把更具体的指令放在后面。

这是一套**来源与作用域优先级**，不是“这条记忆 90 分、那条 30 分”。

可概括为：

```text
平台更高权威指令
  > 当前 prompt 中适用的直接指令
  > AGENTS.md 持久指令

同类 AGENTS.md 内：
更接近目标文件的目录规则 > 更上层、更宽泛的目录规则
```

注意：上图是对官方规则的概括，不代表 OpenAI 公布了统一内部数值权重。

### 2.2 Codex 的“重要差异”主要由结构表达

工程上可观察到的区分信号包括：

- **来源**：直接指令与仓库指导文件不是同一权威层；
- **范围**：嵌套得更深的 `AGENTS.md` 更具体；
- **位置/加载顺序**：OpenAI 官方对 Agent loop 的说明称，汇总的用户指令通常按“更具体的内容靠后”组织；
- **当前任务相关性**：只有作用域覆盖目标文件的规则才应生效。

官方资料没有完整公开：Codex 是否对一般跨会话 memory 的每个事实保存数值重要度、具体召回公式、时间衰减公式或固定高/中/低分类。因此不能把这些说成 Codex 官方机制。

## 三、Claude Code 怎么区分

### 3.1 `CLAUDE.md` 的层级是“范围与顺序”，不是硬覆盖表

Anthropic 官方列出的持久指令范围包括：

```text
Managed policy（组织）
→ User instructions（个人跨项目）
→ Project instructions（项目共享）
→ Local instructions（个人且项目专属）
```

目录树中，从文件系统上层到当前工作目录的文件会被拼接进上下文；更接近启动目录的内容更晚出现。`CLAUDE.local.md` 在同一目录中追加于 `CLAUDE.md` 之后。用户级 rules 先于项目 rules 加载，因此项目规则获得更具体的作用范围。

但官方同时明确：

- 这些文件被当作**上下文**，不是强制配置；
- 冲突规则可能导致 Claude 任意选择；
- 真正必须强制执行的限制应使用 managed settings、permissions 或 hooks。

所以不能简单声称“后加载的 CLAUDE.md 一定覆盖前面的所有内容”。“更具体、后出现”有利于优先遵循，但普通 `CLAUDE.md` 本身不是确定性的策略执行器。

### 3.2 Auto memory 有“值不值得记”的筛选，但算法未公开

Anthropic 明确说明，Claude 不会每个会话都保存内容，而是自行判断信息对未来会话是否有用。官方示例包括：

- 构建命令；
- 调试经验；
- 架构笔记；
- 代码风格偏好；
- 工作流习惯。

这确实是语义上的重要性筛选。不过官方没有公开：

- 高/中/低等级；
- 数值评分字段；
- 完整评分提示词；
- recency、frequency、relevance 各自的权重；
- 固定淘汰或晋级公式。

因此只能说 Claude 会做“是否值得保存”的模型判断，不能声称它采用某个已知重要度公式。

### 3.3 加载预算形成事实上的冷热分层

Claude auto memory 的公开结构是：

```text
MEMORY.md
  ├─ 启动时加载前 200 行或前 25KB（先达到者为准）
  └─ 作为简洁索引

topic files
  ├─ debugging.md
  ├─ api-conventions.md
  └─ 需要时再读取
```

这形成：

- **热层**：`MEMORY.md` 的有限前部，每个会话预载；
- **冷层**：主题文件，不在启动时全部加载，按需读取。

它很像重要等级，但官方定义它的是加载策略与容量预算，而不是名为 `importance` 的等级字段。放进 `MEMORY.md` 前部的信息更容易每次都影响模型，主题文件则依赖后续召回。

## 四、完整冲突案例

### 用户诉求

用户希望 Agent 在仓库中始终使用 `pnpm`，但某个旧 auto memory 仍记录“使用 npm”。

### 信息拆分

| 信息 | 来源 | 范围 | 性质 |
|---|---|---|---|
| “本仓库使用 pnpm” | 项目 `AGENTS.md` / `CLAUDE.md` | 当前仓库 | 人写的持久规则 |
| “以前成功使用 npm” | auto memory | 当前仓库的跨会话经验 | Agent 自写经验 |
| “本次只运行 npm 做兼容验证” | 当前用户消息 | 当前任务 | 显式临时要求 |

### 依赖关系与处理

```text
先确定当前任务的直接要求
  → 再应用覆盖当前目录的项目规则
  → auto memory 只作为辅助事实
  → 若 memory 与当前仓库事实冲突，核验 package.json / lockfile
  → 修正或删除过期 memory
```

### 状态变化

1. 初始：auto memory 中存在旧的 `npm` 经验。
2. 加载：项目规则说明默认使用 `pnpm`。
3. 当前任务：用户明确要求仅做一次 npm 兼容验证。
4. 执行：本次按用户明确范围运行 npm；不把它泛化成仓库默认。
5. 校验：检查 `pnpm-lock.yaml`、脚本和项目文档，确认默认仍为 pnpm。
6. 更新：将旧 memory 改成“默认 pnpm；npm 仅用于指定的兼容验证”。

### 验收结果

- 本次直接要求被满足；
- 项目长期规则没有被一次性例外覆盖；
- 过期经验被纠正；
- 没有假设系统内部存在一个可见的数值重要度。

### 证据边界

这个决策流程是依据官方公开的指令范围、上下文加载和可编辑 memory 机制整理出的**工程解释**。官方没有公开 Codex 或 Claude Code 在模型内部对这三条信息使用的精确数值权重。

## 五、实用判断法

需要某条信息更“重要”时，不要依赖一句“请重点记住”，应按性质放置：

| 信息性质 | Codex | Claude Code |
|---|---|---|
| 必须长期遵守的仓库规则 | `AGENTS.md` | `CLAUDE.md` / `.claude/rules/` |
| 仅某目录或文件类型适用 | 更深层 `AGENTS.md` | 嵌套 `CLAUDE.md` 或 path-scoped rule |
| Agent 偶然学到的动态经验 | 使用当前产品公开支持的可审计 memory/文件工作流；具体自动评分未公开 | auto memory |
| 必须机械强制的安全限制 | 不应只靠 memory，应使用产品支持的策略/沙箱/权限机制 | managed settings、permissions、hooks |
| 一次性例外 | 当前 prompt | 当前 prompt |

## 官方来源

- [OpenAI：Unrolling the Codex agent loop](https://openai.com/index/unrolling-the-codex-agent-loop/)
- [OpenAI：Introducing Codex（AGENTS.md 作用域与冲突优先级）](https://openai.com/index/introducing-codex/)
- [OpenAI Codex 官方仓库：AGENTS.md 文档入口](https://github.com/openai/codex/blob/main/docs/agents_md.md)
- [Anthropic：How Claude remembers your project](https://code.claude.com/docs/en/memory)
- [Anthropic：How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works)

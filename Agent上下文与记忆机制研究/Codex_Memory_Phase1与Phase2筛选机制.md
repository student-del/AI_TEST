# Codex Memory Phase 1 与 Phase 2 筛选机制

> 更新时间：2026-07-28  
> 证据范围：OpenAI 官方 `openai/codex` 仓库的 memory module README、配置 schema 及仓库公开的运行时结构。模型提示词可能随版本调整；未公开或当前无法由官方页面核实的精确措辞不作补写。

## 一句话结论

Codex 没有把每条 memory 直接算成一个统一 importance 分数。它使用的是一条混合管线：

```text
Phase 1
线程级硬筛选
  → 模型从单个线程中提取可复用经验

Phase 2
memory 级硬筛选与排序
  → 合并 Agent 去重、更新、组织和遗忘
```

其中：

- Phase 1 主要回答：“这个线程现在是否有资格被处理？其中有什么值得保存？”
- Phase 2 主要回答：“已有的 raw memories 中，哪些还能进入本轮全局整合？顺序如何？怎样更新最终 MEMORY.md？”

## 一、管线何时启动

memory pipeline 在 root session 启动时异步运行，但需要同时满足：

- 当前 session 不是 ephemeral；
- memory feature 已启用；
- 当前 session 不是 sub-agent；
- state DB 可用。

之后严格按 Phase 1 → Phase 2 执行。

这意味着并不是每个模型回合结束都立即改写 `MEMORY.md`。

## 二、Phase 1：从线程提取 raw memory

### 2.1 第一层：线程资格的确定性筛选

Phase 1 从 state DB 中 claim 一批 rollout。候选线程必须满足：

| 条件 | 判断性质 | 目的 |
|---|---|---|
| 来源属于允许的交互式 session source | 硬规则 | 排除不适合作为个人工作记忆的内部或非交互来源 |
| 在线程年龄窗口内 | 硬规则 | 只处理 `max_rollout_age_days` 范围内的近期线程 |
| 已空闲足够久 | 硬规则 | 使用 `min_rollout_idle_hours`，避免总结仍在活跃或刚结束的线程 |
| 没被其他 Phase 1 worker 占用 | lease/claim | 防止多个启动任务重复提取同一线程 |
| 没超过本轮处理上限 | 数量预算 | 使用 `max_rollouts_per_startup` 限制启动时工作量 |
| thread 的 memory mode 允许生成 | 状态规则 | `generate_memories=false` 时，新线程会以 disabled 状态记录 |

这一步不判断“登录 bug 比目录列表更重要”，只是决定哪条完整线程有资格进入模型提取。

抽象伪代码：

```text
candidates = state_db.rollouts
  .where(source in allowed_interactive_sources)
  .where(age <= max_rollout_age_days)
  .where(idle_time >= min_rollout_idle_hours)
  .where(memory_mode permits generation)
  .where(not leased_by_another_worker)
  .limit(max_rollouts_per_startup)
```

### 2.2 第二层：过滤线程中的输入内容

线程被选中后，Codex 不一定把 rollout 的所有原始记录原封不动交给提取模型。官方 README 说明，它会把内容过滤为 memory-relevant response items。

这一步属于结构性降噪，例如排除不需要参与记忆总结的内部记录。官方 README 没有在同一页面完整枚举每种 ResponseItem 的取舍表，因此不能声称某个具体 item 类型永远保留或永远删除。

### 2.3 第三层：提取模型的语义判断

过滤后的单线程内容被交给 extraction model。模型输出结构为：

```text
raw_memory       # 详细的、可供之后合并的记忆
rollout_summary  # 本线程的紧凑摘要
rollout_slug     # 可选的简短标识
```

这里才发生 Phase 1 的语义重要性判断：

- 是否存在对未来任务可复用的信息；
- 哪些过程、结论、工作流或教训值得写进 `raw_memory`；
- 如何把线程压缩为 `rollout_summary`；
- 如果没有有用产物，可以返回无输出。

官方定义了三种结果：

| 结果 | 含义 |
|---|---|
| `succeeded` | 成功产生 memory |
| `succeeded_no_output` | 模型调用有效，但没有值得保存的内容 |
| `failed` | 提取失败，进入带 backoff 的后续重试 |

`succeeded_no_output` 很关键：它证明 Phase 1 不是“每个线程必写一条记忆”，而是允许模型判定整条线程无持久价值。

### 2.4 第四层：安全清洗与持久化

模型产出的 memory 字段会经过 secret redaction，再作为 stage-1 output 写回 state DB。

所以 Phase 1 的完整漏斗是：

```text
所有 rollout
  ↓ 来源、年龄、空闲时间、状态、lease、数量上限
合格 rollout
  ↓ 过滤为 memory-relevant items
提取模型
  ↓ 有用性与内容选择
raw_memory + rollout_summary + optional slug
  ↓ secret redaction
stage-1 DB records
```

## 三、Phase 2：选择并整合全局 memory

### 3.1 第一层：只允许一个全局合并任务

Phase 2 会 claim 单个 global job，保证同一时刻只有一个 consolidation 修改共享 memory artifacts。

这不是重要性判断，而是一致性机制。

### 3.2 第二层：对 Stage 1 outputs 做资格筛选

Phase 2 从 DB 加载有数量上限的 Stage 1 outputs。

每条候选 memory 使用一个“有效时间”：

```text
effective_last_use =
  last_usage 存在 ? last_usage : generated_at
```

然后应用：

```text
effective_last_use 必须位于 max_unused_days 窗口内
```

含义：

- 使用过的 memory，看最近一次使用时间；
- 从未使用过的新 memory，用生成时间兜底，使其有机会第一次进入整合；
- 长期没有被使用的 memory 会失去 Phase 2 选择资格。

这不是连续的指数衰减，而是官方公开的**资格窗口**。

### 3.3 第三层：明确的排序规则

对仍合格的 memories，Phase 2 排序依据是：

```text
第一关键字：usage_count，越高越靠前
第二关键字：last_usage / generated_at，越新越靠前
```

然后受 `max_raw_memories_for_consolidation` 限制，只取 bounded top-N。

可表示为：

```text
eligible = memories where effective_last_use >= cutoff

selected = eligible
  .sort_desc(usage_count)
  .then_sort_desc(effective_last_use)
  .take(max_raw_memories_for_consolidation)
```

这就是 Codex 当前最接近“重要性等级”的公开机制：

- 被反复使用的 memory 优先；
- 使用次数相同时，最近使用或最近生成的优先；
- 超过未使用期限的 memory 直接失去资格。

注意它并未公开加入：

- embedding relevance 分数；
- 用户手写 priority；
- LLM importance 1–10 分；
- `high / medium / low` 等级。

### 3.4 第四层：计算 added / retained / removed

Phase 2 不只看本轮 top-N，还与上一次成功整合时选择的精确快照比较：

| 状态 | 含义 |
|---|---|
| `added` | 本轮新进入，或者同一线程的 Stage 1 快照已更新但尚未被成功整合 |
| `retained` | 上轮选择过，本轮仍在选择集合，且快照相同 |
| `removed` | 上轮选择过，但本轮已跌出选择集合或失去资格 |

这里的 `removed` 不代表立即物理删除所有证据。合并 Agent 启动前，`raw_memories.md` 和 `rollout_summaries/` 暂时保留“本轮集合 ∪ 上轮成功集合”，让 Agent 看见被移除项目的旧证据并执行有依据的遗忘。

这是一个很重要的设计：

```text
先把某项标记为 removed
  → 仍给 consolidation agent 看旧内容
  → Agent 决定最终 MEMORY.md 中哪些内容应删除、改写或保留
```

避免了 top-N 变化导致无上下文的硬删除。

### 3.5 第五层：同步中间文件

Phase 2 会整理：

- `raw_memories.md`：合并后的 raw memories，较新的在前；
- `rollout_summaries/`：每个保留 rollout 对应一个摘要文件；
- 不再保留的 stale rollout summaries 会被清理。

如果没有 Phase 1 输入，也没有需要处理的旧 extension resources，Phase 2 会直接成功退出，不启动 consolidation agent。

### 3.6 第六层：Consolidation Agent 的语义合并

如果存在变化，Codex 启动一个内部 consolidation sub-agent。它得到：

- 当前 memory workspace；
- `added / retained / removed` 差异；
- extension 资源变化；
-现有整合结果。

它负责高层语义处理：

- 合并重复经验；
- 更新被新证据替代的旧事实；
- 保持不同 cwd/project 的适用边界；
- 把细节组织到 `MEMORY.md`；
- 生成或刷新更短的 `memory_summary.md`；
- 对 removed 输入执行相应的遗忘或改写。

该 Agent：

- 无网络；
- 无审批；
- 只拥有本地写权限；
- 禁用 collaboration，避免递归再派生 Agent。

这里没有公开固定的数值评分公式。去重、矛盾消解和最终措辞属于模型语义判断。

## 四、一个完整案例

### 输入线程

假设 state DB 中存在四条线程：

| 线程 | 内容 | 年龄 | 空闲时间 | 状态 |
|---|---|---:|---:|---|
| A | 修复项目 X 的 Windows 路径 bug，最终验证成功 | 2 天 | 10 小时 | 可生成 memory |
| B | 用户说“你好”后结束 | 1 天 | 12 小时 | 可生成 memory |
| C | 正在调试数据库迁移 | 1 小时 | 5 分钟 | 仍活跃 |
| D | 两个月前的旧任务 | 60 天 | 很久 | 可生成 memory |

### Phase 1

1. C 因未达到 `min_rollout_idle_hours` 被硬筛掉。
2. 如果 D 超过 `max_rollout_age_days`，被硬筛掉。
3. A、B 进入 extraction model。
4. A 产出：

```text
raw_memory:
- cwd: project X
- Windows 下路径比较必须先规范化分隔符
- 失败方案：直接字符串前缀比较
- 成功方案：解析为规范绝对路径后比较
- 验证：Windows 专项测试通过
```

5. B 没有未来复用价值，返回 `succeeded_no_output`。
6. A 的结果经过 secret redaction 后进入 Stage 1 DB。

### Phase 2 初次选择

假设 A 尚未被使用：

```text
last_usage = null
effective_last_use = generated_at
```

它因为刚生成而在 `max_unused_days` 内，有资格进入选择集合。

### 后续变化

假设还有 memories E、F：

| Memory | usage_count | last_usage |
|---|---:|---|
| E | 8 | 10 天前 |
| A | 3 | 今天 |
| F | 0 | 昨天生成 |

排序首先看 `usage_count`：

```text
E → A → F
```

即使 A 比 E 更新，E 仍因使用次数更高排在前面。只有 usage_count 相同时，才比较最近使用/生成时间。

若之后 E 长期未再使用，超过 `max_unused_days`：

1. E 不再具备本轮选择资格；
2. 相比上一轮，它被标记为 `removed`；
3. consolidation agent 仍能看到其旧证据；
4. Agent 据此从最终 `MEMORY.md` 删除、压缩或调整由 E 支撑的内容。

### 验收结果

- 活跃线程不会被过早总结；
- 无价值闲聊可以产生 `succeeded_no_output`；
- 新 memory 即使还没用过，也可凭 `generated_at` 获得首次机会；
- 高频使用 memory 排在低频 memory 前；
- 长期未使用 memory 失去资格；
- 遗忘通过 diff 和 consolidation 完成，而不是无证据瞬时删除。

## 五、硬规则与模型判断的边界

| 环节 | 决策者 | 可核查依据 |
|---|---|---|
| 线程来源、年龄、空闲时间 | Rust/DB 查询规则 | 配置与官方 module README |
| claim、lease、并发、backoff | Rust/DB 状态机 | 官方 module README |
| 线程中什么值得成为 raw memory | Extraction model | 官方确认使用模型；精确语义标准取决于运行时模板 |
| 是否 `succeeded_no_output` | Extraction model + 输出处理 | 官方 module README |
| 未使用期限 | 硬规则 | `max_unused_days` |
| Phase 2 排序 | 硬规则 | `usage_count`，再看 `last_usage/generated_at` |
| top-N 截断 | 硬规则 | `max_raw_memories_for_consolidation` |
| 去重、冲突更新、最终组织 | Consolidation agent | 官方 module README 与 consolidation 管线 |

## 六、证据边界

可以确认的是管线、资格条件、排序字段、diff 状态和 Agent 分工。

不能据此断言：

- Phase 1 使用了某个未公开的 importance 数值；
- Codex 使用 embedding 相似度给 memories 排名；
- `usage_count` 是唯一语义重要性；
- 某条 memory 一旦成为 `removed` 就立即从所有磁盘证据物理删除；
- 当前所有 Codex 产品表面、账户和实验组都采用完全相同参数默认值。

## 官方来源

- [OpenAI Codex：Memories Pipeline (Core)](https://github.com/openai/codex/blob/main/codex-rs/core/src/memories/README.md)
- [OpenAI Codex：配置 Schema 中的 MemoriesToml](https://github.com/openai/codex/blob/main/codex-rs/core/config.schema.json)
- [OpenAI Codex：App Server 的实验性 memory/reset](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md)


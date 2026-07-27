# 无后训练的 Skill 自演进：学术方案综述

> 核查日期：2026-07-20  
> 严格边界：模型参数保持冻结，不进行 SFT、LoRA、RL、蒸馏或任何后训练；只通过普通推理调用修改外部 Skill 文档、Skill 目录、可执行脚本或 Skill 库。论文指标均为作者报告结果，多数工作发表于 2026 年且仍属前沿预印本，不能等同于独立复现或生产验证。

## 一、结论

按“不做后训练，只优化 Skill 本身”的口径，当前学术界最值得关注的方案是：

1. **SkillOpt**：最适合单个 Skill 的稳定优化。通过受限文本编辑、留出验证门禁和拒绝修改记忆，解决越改越坏的问题。
2. **Ratchet**：最轻量的持续 Skill 库演进。冻结的单一 LLM 负责写入、检索、淘汰自然语言 Skill；核心是生命周期卫生而非复杂搜索。
3. **Trace2Skill**：最适合从 Agent Trace 中沉淀经验。并行提炼大量成功/失败轨迹，再合并成统一、无冲突的 Skill/SOP。
4. **SkillForge**：最接近企业反馈闭环。批量分析真实支持任务失败，定位 Skill 缺陷，再针对性重写。
5. **EvoSkill**：适合不知道缺什么 Skill 的探索阶段。可提出新 Skill，并联合演化提示和 Skill set。
6. **SkillFoundry / SkillOps**：分别解决 Skill 库的自动构建和长期维护。
7. **MetaSkill-Evolve**：进一步让“如何改 Skill 的方法”本身也成为可演进 meta-skill，但复杂度更高，属于较新的研究前沿。

如果只想做一个轻量、可靠的原型，推荐：

```text
Ratchet 的写入/检索/淘汰
          +
SkillOpt 的小步修改和验证门禁
          +
Trace2Skill 的多轨迹归纳
```

## 二、为什么不能只让 LLM 自我反思后重写

SkillsBench 在 86 个任务、11 个领域、7,308 条轨迹上比较 no-skill、curated skill 和 self-generated skill。论文报告人工精选 Skill 平均提升 16.2 个百分点，但一次性自生成 Skill 平均没有收益，而且部分任务会被 Skill 损害。[SkillsBench 原始论文](https://arxiv.org/abs/2602.12670)

SWE-Skills-Bench 在真实软件工程任务上也报告：49 个公开 Skill 中有 39 个没有提高通过率，平均收益仅约 1.2%；部分 Skill 因版本不匹配反而降低性能，token 开销最高可显著增加。[SWE-Skills-Bench 原始论文](https://arxiv.org/abs/2603.15401)

这两个结果表明：

- LLM 能写 Skill，不等于写出的 Skill 有增益；
- Skill 内容越全面不一定越好，聚焦的程序性指导可能更有效；
- Skill 会产生负迁移、上下文干扰和版本冲突；
- 自演进必须包含回归测试、淘汰和能力保持，而不能只增加规则。

## 三、方案一：SkillOpt——受控的单 Skill 文本优化

### 核心思想

SkillOpt 把一个外部 Skill 文档当作冻结 Agent 的可训练外部状态，但“训练”完全发生在文本空间，不修改模型权重。一个独立优化模型根据 scored rollouts 提出结构化编辑，候选只有在留出验证集上严格改善才被接受。[SkillOpt 原始论文](https://arxiv.org/abs/2605.23904)

### 闭环

```text
Skill vN
  ↓ 冻结目标模型批量执行
scored trajectories
  ↓ 优化器分析成功/失败
add / delete / replace 候选
  ↓ 限制文本修改预算
Skill candidate
  ↓ held-out validation
严格改善 → vN+1
未改善 → 拒绝，并保存 rejected edit
```

### 稳定性机制

- **目标模型与优化模型分离**：执行者不是唯一裁判；
- **Bounded edit**：每轮只允许有限的增删改，避免整体漂移；
- **Textual learning rate**：限制单次版本变化幅度；
- **Held-out gate**：修改证据和接受评测使用不同样本；
- **Rejected-edit buffer**：让后续优化器知道哪些方向已失败；
- **Slow/meta update**：长期保留跨轮次稳定的改进规律。

### 作者报告结果

论文报告在 6 个 benchmark、7 个目标模型和 direct chat/Codex/Claude Code 三种执行环境的 52 个比较单元中达到最好或并列最好。最终 Skill 通常约 300–2,000 tokens，并且目标模型和 Agent harness 保持冻结。

### 适用与局限

适合有明确自动评分器的单 Skill，例如电子表格、文档、搜索、数学和工具使用流程。局限是每轮需要多次 rollout；如果 grader 不可靠，验证门禁也会优化错误目标。

### 轻量化建议

不必实现论文全部机制，保留三个组件已经很有价值：

```text
每轮一个最小 diff
+ 独立验证集
+ 严格改善才接受
```

## 四、方案二：Ratchet——Skill 库的最小卫生机制

### 核心思想

Ratchet 使用一个冻结 LLM 写入、检索、整理和淘汰自己的自然语言 Skill。它认为自演进瓶颈不是“不会生成 Skill”，而是 Skill 库缺少生命周期管理。[Ratchet 原始论文](https://arxiv.org/abs/2605.22148)

### 四类机制

- **Outcome-driven retirement**：长期无效或产生负面结果的 Skill 被淘汰；
- **Bounded active cap**：限制活跃 Skill 数量，防止库无限膨胀；
- **Meta-skill authoring guidance**：用一个写 Skill 的方法约束新 Skill 质量；
- **Pattern canonicalisation**：将相似经验归一化，减少重复和表述漂移。

论文消融实验认为，真正关键的是退休机制和 meta-skill authoring prior；显式去重的部分作用可能被良好 meta-skill 吸收。

### 作者报告结果

论文报告在 MBPP+ hard-100 上，held-out pass@1 从约 0.258 提升到后期滚动均值 0.584；并在 SWE-bench Verified 的实验中报告峰值提升。但该方案很新，且从公开检索结果看未发现明确的官方复现仓库，应将其视为值得复现的研究方案，而非现成生产框架。

### 为什么适合轻量落地

它不要求独立强优化模型、复杂 Pareto 搜索或大规模多 Agent。一个模型、一个 Skill 列表、一个结果评分和几条维护规则即可工作。

### 最小实现

```text
任务结束
  ↓
成功且出现可复用新方法？→ 生成候选 Skill
失败且关联已有 Skill？  → 降低该 Skill utility
  ↓
合并语义重复 Skill
  ↓
超过 active cap 时淘汰低 utility Skill
  ↓
保留少量活跃 Skill 参与下一轮
```

## 五、方案三：Trace2Skill——从执行轨迹归纳程序性经验

### 核心思想

Trace2Skill 反对逐条轨迹顺序修改 Skill。它先让多个分析器对大量成功和失败轨迹抽取局部经验，再通过层级归纳合并成统一、无冲突的 Skill 目录。[Trace2Skill 原始论文](https://arxiv.org/abs/2603.25158)；[官方代码](https://github.com/Qwen-Applications/Trace2Skill)

### 闭环

```text
多条成功/失败 Agent Trace
          ↓
并行 trajectory-local lesson extraction
          ↓
按失败模式和方法聚类
          ↓
去重、处理冲突、层级归纳
          ↓
统一 Skill/SOP
          ↓
独立 benchmark 回归
```

### 优势

- 不会因最近一次失败过度修改全局 Skill；
- 可同时使用成功经验和失败经验；
- 输出是可审阅、可迁移的声明式 Skill；
- 官方仓库提供 SpreadsheetBench 执行、评价、错误分析和并行 Skill evolution 入口。

### 风险

如果轨迹分析阶段使用现实部署中不可获得的 ground truth 或 oracle，线上效果可能低于论文；多 Agent 合并也可能把偶然规律写成通用规则。

## 六、方案四：SkillForge——企业失败反馈驱动的 Skill 修复

### 核心思想

SkillForge 面向云技术支持，把历史工单和知识库用于构建初始 Skill，再通过三阶段管线迭代：[SkillForge 原始论文](https://arxiv.org/abs/2604.08618)

```text
Failure Analyzer
      ↓ 批量找失败模式
Skill Diagnostician
      ↓ 定位是 Skill 的哪类缺陷
Skill Optimizer
      ↓ 针对性重写 Skill
新一轮部署反馈
```

论文在 5 类云支持场景、1,883 个 ticket 和 3,737 个任务上评价，作者报告多轮演进能改善不同来源的初始 Skill，包括人工 Skill、领域创建 Skill 和通用 Skill。

### 价值与边界

它最值得借鉴的是“先做失败归因，再改 Skill”，而不是把所有失败都当作指令缺陷。论文摘要没有证明这是已部署的公开生产系统，也未在本轮检索中发现明确官方代码，因此可复现性弱于 Trace2Skill。

## 七、方案五：EvoSkill——自动发现和联合演化 Skill set

### 核心思想

EvoSkill 从失败轨迹中提出新 Skill 或修改已有 Skill，并把 `system prompt + Skill set` 视为一个 Agent program；在留出数据上评价候选，用 Pareto frontier 进行选择。[EvoSkill 原始论文](https://arxiv.org/abs/2603.02766)；[官方代码](https://github.com/sentient-agi/EvoSkill)

### 与 SkillOpt 的差别

| SkillOpt | EvoSkill |
|---|---|
| 优化单一紧凑 Skill 文档 | 搜索提示和多个 Skill 的组合 |
| 强调小步稳定更新 | 强调发现新能力与候选多样性 |
| 搜索空间相对小 | 搜索空间和成本更大 |

适合系统不知道缺少什么能力的探索阶段。轻量系统若已有明确 Skill，优先使用 SkillOpt 而不是 EvoSkill。

## 八、方案六：SkillFoundry——从异构资料构建和维护 Skill 库

SkillFoundry 面向科学领域，从代码仓库、API、脚本、notebook、文档、数据库和论文中提取可操作知识，并编译为包含任务范围、输入输出、步骤、环境假设、来源和测试的 Skill package。[SkillFoundry 原始论文](https://arxiv.org/abs/2604.03964)

其流程是：

```text
构建领域知识树
 → 在高价值分支挖掘资源
 → 提取 operational contract
 → 编译成带测试的 Skill
 → 验证
 → 扩展 / 修复 / 合并 / 剪枝 Skill 库
```

该方案更像“知识到程序性 Skill 的编译器”，适合科研、医疗和企业知识库，不是针对单个 Skill 的最轻方案。

## 九、方案七：SkillOps——把 Skill 库当成需维护的软件生态

SkillOps 关注 Skill technical debt：单个 Skill 局部可用，但整个库可能出现兼容性、风险、检索和组合缺陷。[SkillOps 原始论文](https://arxiv.org/abs/2605.13716)

它将 Skill 表示为 typed Skill Contract，并建立层级 Skill Ecosystem Graph，从 utility、compatibility、risk 和 validation 四个维度诊断和维护 Skill 库。作者强调当前规则式维护实现几乎不需要 library-time LLM 调用。

它不是主要的“自动写 Skill”算法，却非常适合成为自演进之后的治理层：检测重复 Skill、依赖失效、组合冲突和未验证能力。

## 十、方案八：MetaSkill-Evolve——任务 Skill 与演进方法共同演化

MetaSkill-Evolve 在 2026 年 7 月提出两时间尺度机制：任务 Skill 在快循环中演进，定义 Analyzer、Retriever、Allocator、Proposer、Evolver 行为的 meta-skill 在慢循环中演进。所有管线角色共享同一个冻结 backbone，不引入额外训练目标。[MetaSkill-Evolve 原始论文](https://arxiv.org/abs/2607.05297)

```text
快循环：task skill 改善任务方法
慢循环：meta-skill 改善“如何分析和修改 task skill”
```

作者报告相对 raw backbone，在 OfficeQA、SealQA、ALFWorld held-out test 上分别提升 23.54、16.09 和 1.92 个百分点。

它满足无参数更新要求，但不属于最轻量方案：需要维护分支、本地 meta-skill 和五角色优化管线；而且论文发布很新，尚需更多复现和长期稳定性研究。

## 十一、学术方案横向比较

| 方案 | 演进对象 | 反馈 | 防退化机制 | 是否有公开代码 | 轻量度 |
|---|---|---|---|---|---|
| SkillOpt | 单 Skill 文档 | scored trace | bounded edit、held-out gate、rejected buffer | 本轮检索以论文/项目页为主 | 中 |
| Ratchet | 自然语言 Skill 库 | 任务结果 | retirement、active cap | 未确认官方代码 | 高 |
| Trace2Skill | Skill 目录/SOP | 多条成功失败 trace | 批量归纳、独立评价 | 有 | 中 |
| SkillForge | 领域 Skill | 批量企业失败 | 分析→诊断→优化 | 未确认官方代码 | 中 |
| EvoSkill | prompt + Skill set | 失败轨迹 | held-out Pareto | 有 | 低 |
| SkillFoundry | 领域 Skill 库 | 资源验证和任务结果 | tests、修复/合并/剪枝 | 未确认官方代码 | 低 |
| SkillOps | Skill 生态图 | 库健康指标 | contract、兼容和风险诊断 | 未确认官方代码 | 高（规则维护） |
| MetaSkill-Evolve | task skill + meta-skill | 执行 trace | 双时间尺度分支选择 | 未确认官方代码 | 低 |

“轻量度高”表示系统组件和推理调用较少，不代表论文效果更强。

## 十二、持续演进必须解决的遗忘问题

无参数更新不代表没有灾难性遗忘。Skill 文件或 Skill 库被覆盖、剪枝或错误路由，也会导致旧能力退化。相关研究 *Do Self-Evolving Agents Forget?* 将其称为 capability erosion，并提出 Capability-Preserving Evolution：更新时不仅评价新分布，还显式检查保留能力。[论文页面](https://arxiv.org/abs/2605.09315)

对轻量 Skill 系统，可采用更简单的做法：

- 永久保留一组历史关键回归用例；
- 候选 Skill 必须同时通过新任务集和旧能力集；
- 不原地覆盖，保留所有版本；
- 删除 Skill 前验证其他 Skill 是否覆盖其能力；
- 按任务类型分别统计表现，不能只看总体平均分。

## 十三、推荐的轻量学术组合

### 状态

```text
ACTIVE Skill vN
      ↓ 累积一批 Trace
EVIDENCE_READY
      ↓ 归纳重复模式
ONE_BOUNDED_EDIT
      ↓ 新旧能力回归
VALIDATION
  ├─ 严格改善且无关键回归 → ACTIVE vN+1
  └─ 否则 → REJECTED_EDIT
```

### 组件映射

- 从 **Trace2Skill** 借鉴：不要逐条修补，先汇总多条轨迹；
- 从 **SkillOpt** 借鉴：每轮只做小范围增删改，使用独立验证门禁；
- 从 **Ratchet** 借鉴：限制 Skill 数量，淘汰长期无效或有害 Skill；
- 从 **Capability-Preserving Evolution** 借鉴：保留旧能力回归集；
- 从 **SkillsBench** 借鉴：必须做 with-skill/no-skill 对照，不默认 Skill 有益。

### 接受规则

```text
accept(candidate) iff
  candidate.new_task_score > baseline.new_task_score
  AND candidate.old_capability_score >= required_floor
  AND candidate.trigger_false_positive <= threshold
  AND candidate.token_cost <= budget
  AND no new security violation
```

### 不建议的方案

- 每次失败立即把一条规则追加到 Skill；
- 让同一个 Agent 生成、执行、评分并直接发布；
- 只比较候选版得分，不与 no-skill 和旧版对照；
- 使用训练案例答案作为 Skill 内容；
- Skill 库只增不减；
- 用总平均分掩盖某类旧任务能力退化；
- 自动改写脚本后不做代码安全和执行验证。

## 十四、最终判断

无后训练的 Skill 自演进已经形成清晰的学术路线，但仍是快速发展的前沿领域。当前最稳健的共识不是“LLM 可以自己写 Skill”，而是：

```text
冻结模型
+ 从多条可验证轨迹获取证据
+ 只对外部 Skill 做受限修改
+ 在独立验证集上严格比较
+ 保持旧能力
+ 淘汰无效 Skill
+ 版本化、可审计、可回滚
```

对现实系统而言，**SkillOpt 提供优化纪律，Ratchet 提供库卫生，Trace2Skill 提供经验归纳**。三者组合是目前最符合“轻量、无参数更新、只优化 Skill”的技术路线。

# Skill 自演进：业界优秀案例与工程启示

> 核查日期：2026-07-20  
> 来源边界：Anthropic、OpenAI 机制只采用官方资料；其他案例采用项目官方仓库与原始论文，并明确标注其学术或第三方性质。论文中的指标是作者报告结果，不等同于独立复现或大规模生产验证。

## 一、结论与推荐顺序

如果目标是研究或落地 Skill 自演进，当前最值得看的案例可以分为四档：

1. **最适合直接工程落地：Microsoft Waza**——围绕标准 Agent Skills 做触发测试、行为评分、token 管理和 CI 门禁；重点是“可测、可审、可发布”。
2. **最完整的 Skill 优化算法：SkillOpt**——把 Skill 文档当成冻结模型之外的可训练状态，用受限编辑、验证集门禁和拒绝修改记忆保证稳定演进。
3. **最好的经验蒸馏案例：Trace2Skill**——并行分析大量成功/失败轨迹，把局部经验合并成统一、可迁移的 Skill/SOP。
4. **最好的自动发现案例：EvoSkill**——不只修改一个 Skill，还能从失败中提出新 Skill，并联合演化系统提示和 Skill 集合。

作为算法底座，还应研究 **GEPA/DSPy**；作为历史先驱，应研究 **Voyager**。Anthropic 官方 `skill-creator` 是当前厂商原生 Skill 迭代闭环中最清晰的参照，但仍是显式触发、带评测与人工审阅的迭代工具，不是默认运行时自修改。

## 二、如何判断一个案例是否真正优秀

不能只看“Agent 会反思并重写提示”。一个成熟的 Skill 自演进案例至少应回答：

| 问题 | 合格机制 |
|---|---|
| 从哪里学习 | 代表性成功/失败轨迹，而非单次印象 |
| 修改什么 | Skill 指令、脚本、描述或 Skill 集合，边界明确 |
| 谁提出修改 | 与执行 Agent 分离的优化器或独立分析角色 |
| 如何防退化 | held-out validation、回归集、严格改善门禁 |
| 如何防过拟合 | 训练/验证/测试分离，跨任务或跨模型迁移验证 |
| 如何发布 | 候选版本、diff、审批、CI、灰度与回滚 |
| 如何控制成本 | rollout 预算、token/延迟指标、缓存 |
| 是否可审计 | Skill 是紧凑文本/代码制品，保留轨迹与版本 |

## 三、案例一：Microsoft Waza——最接近 Skill 工程基础设施

### 定位

Waza 是 Microsoft 开源的 Agent Skills CLI/Framework，用于创建、测试、度量和改进 Skill。它不是一个声称能完全自治学习的研究 Agent，而是把 Skill 演进所需的测试与治理能力做成工程工具。[Microsoft Waza 官方仓库](https://github.com/microsoft/waza)

### 公开机制

- 创建和运行 Skill eval；
- 支持不同 grader；
- 建立 `trigger_tests.yaml` 测试 Skill 是否应触发；
- `waza dev` 迭代评分和改进 `SKILL.md` frontmatter；
- 报告 Skill token 使用；
- 可请求 Copilot 提出改善 Skill selection 的建议；
- 非交互模式只输出建议报告，不直接应用修改；
- 提供 GitHub Actions CI 集成。

### 为什么优秀

Waza 把“自演进”放在软件工程生命周期中处理：修改不是结束，测试、评分、CI 门禁和审阅才是发布依据。尤其是默认可以只建议、不自动写回，适合企业控制风险。

### 局限

它主要是评测和开发框架，不是 SkillOpt 那样有完整优化理论的自动搜索器。最终效果仍依赖测试集、grader 和候选修改质量。

### 最值得借鉴

把每个 Skill 当成带测试的版本化软件包：

```text
SKILL.md + trigger_tests + behavior evals + grader + CI report
```

## 四、案例二：SkillOpt——把 Skill 文档变成可控的训练状态

### 定位与来源

SkillOpt 是 2026 年论文提出的研究系统，作者来自 Microsoft、上海交通大学、同济大学和复旦大学。它不是 OpenAI、Anthropic 或 Microsoft 产品功能，应视为学术原型。[SkillOpt 原始论文](https://arxiv.org/abs/2605.23904)

### 核心闭环

```text
当前 Skill
   ↓
冻结的目标 Agent 批量执行任务，生成 scored rollouts
   ↓
独立优化模型分析成功/失败轨迹
   ↓
提出受限的 add / delete / replace 修改
   ↓
应用“文本学习率”限制单次修改幅度
   ↓
在 held-out selection split 上评估候选版
   ↓
只有严格改善才接受；拒绝修改进入负反馈缓冲区
   ↓
周期性 slow/meta update 沉淀长期稳定规律
```

### 关键创新

- **目标模型与优化器分离**：执行者不直接裁定自己的修改；
- **受限文本编辑**：不允许每次完全重写，减少漂移；
- **严格验证门禁**：候选版必须在留出集上严格变好；
- **Rejected-edit buffer**：失败修改也成为下一轮的负反馈；
- **Slow/meta update**：类似动量，保留跨 epoch 的稳定改进方向；
- **零部署额外调用**：训练后只部署约 300–2,000 token 的 Skill 文档。

### 作者报告结果

论文报告在 6 个 benchmark、7 个目标模型和 direct chat/Codex/Claude Code 三种 harness 上，SkillOpt 在 52/52 个比较单元达到最好或并列最好；对论文使用的 GPT-5.5，作者报告相对 no-skill 平均提升分别为 direct chat +23.5、Codex +24.8、Claude Code +19.1 个百分点。

这些是论文作者在其设置中的结果。论文发布日期较新，不能直接推导为现实生产流量上的普遍收益，也不应把论文所称 Codex/Claude Code harness 误认为厂商官方集成。

### 为什么优秀

它第一次比较完整地回答了“如何让 Skill 连续更新却不越改越坏”：控制步长、保留验证集、记录拒绝步骤，并始终冻结目标 Agent。对于本知识库研究的“外部文本状态演进”，它是当前最贴题的设计。

## 五、案例三：Trace2Skill——从大量轨迹蒸馏可迁移 SOP

### 定位与来源

Trace2Skill 是 Qwen-Applications 发布官方代码的研究项目。它针对“一条轨迹一个补丁”容易过拟合的问题，先并行提炼大量轨迹的局部教训，再分层合并成统一 Skill 目录。[Trace2Skill 官方仓库](https://github.com/Qwen-Applications/Trace2Skill)；[原始论文](https://arxiv.org/abs/2603.25158)

### 执行步骤

1. 在 SpreadsheetBench 等任务上运行 Agent，并保存输出和 trajectory log；
2. 用官方兼容 evaluator 评分；
3. 匹配结果与日志，生成 failure triage；
4. 分别分析失败轨迹和成功轨迹；
5. 多个子 Agent 并行抽取 trajectory-local lessons；
6. 用层级归纳把冲突、重复的经验合并为统一 Skill；
7. 重新运行 benchmark，验证 Skill 是否改善；
8. 可从零创建 Skill，也可深化已有人工 Skill。

### 为什么优秀

它解决了 Skill 演进的一个核心数据问题：不能因为最近一次失败就在全局 Skill 中加入一条特例。先对多条轨迹聚类、归纳和去冲突，更接近从经验生成稳定 SOP。

论文还测试了跨模型规模和分布外迁移；作者报告某些由 Qwen3.5-35B 自身轨迹演进的 Skill 能明显改善更大模型。这支持“经验可通过声明式 Skill 转移”的方向，但具体大幅数字具有 benchmark 和诊断条件依赖。

### 风险边界

- 如果错误分析使用了现实部署中不可获得的 ground truth，离在线生产还有距离；
- 多 Agent 归纳可能把偶然相关性写成规则；
- 必须用独立留出集防止 SOP 记忆题目。

## 六、案例四：EvoSkill——自动发现与组合 Skill

### 定位与来源

EvoSkill 是第三方开源研究框架，不是 Anthropic/OpenAI 官方功能。它分析失败轨迹，提出新 Skill 或修改已有 Skill，并把结果物化为结构化 Skill 文件夹。[EvoSkill 官方仓库](https://github.com/sentient-agi/EvoSkill)；[原始论文](https://arxiv.org/abs/2603.02766)

### 机制

- 一个候选 Agent program 由 system prompt 与 Skill set 构成；
- 从失败执行中提出多个 Skill/提示 mutation；
- 每轮产生新的候选 Agent program；
- 在 held-out 数据上评价；
- 用 Pareto frontier 保留有效候选；
- 底层模型保持冻结。

### 作者报告结果

论文报告 OfficeQA exact match 从 60.6% 提升到 67.9%，SealQA 从 26.6% 提升到 38.7%；SealQA 演进出的 Skill 零样本迁移到 BrowseComp 后提升 5.3 个百分点。

### 为什么优秀

SkillOpt 优化“一个稳定 Skill 文档”，EvoSkill 则搜索“系统提示 + 多 Skill 组合”。当系统不知道缺少哪种能力时，自动发现比只修改现有 Skill 更合适。

### 局限

搜索空间和评测成本更大；多个 Skill 还会产生触发冲突、重复规则与上下文膨胀。生产使用需要额外的 Skill 去重、依赖管理和安全审查。

## 七、案例五：GEPA/DSPy——反思式文本进化的算法底座

### 定位

GEPA 本质是通用文本组件优化器，并非专门的 `SKILL.md` 生命周期系统。它对执行轨迹和反馈做自然语言反思，诊断问题，生成候选提示/代码/指令，再通过 Genetic-Pareto 搜索保留互补候选。[GEPA 原始论文](https://arxiv.org/abs/2507.19457)；[GEPA 官方实现](https://github.com/gepa-ai/gepa)；[DSPy 官方仓库](https://github.com/stanfordnlp/dspy)

### 作者报告结果

GEPA 论文报告：在 6 个任务上平均超过 GRPO 6%，最高 20%，rollout 最多减少 35 倍；官方示例中，AIME 2025 提示优化将 GPT-4.1-mini 从 46.6% 提高到 56.6%。

### 与 Skill 自演进的关系

只要把 `SKILL.md` 的正文、description 或工具说明暴露为待优化文本组件，GEPA 就能成为 Skill 候选生成器。但它默认优化的是任意文本组件，不自动解决 Skill 的目录结构、脚本安全、版本治理和发布审批。

### 最值得借鉴

- 从完整 trace 而不只是一个分数中学习；
- 保留多个 Pareto 候选，而不是贪心覆盖当前最佳；
- 强优化模型可以为较小执行模型预计算程序性经验。

## 八、案例六：Voyager——可执行 Skill 库的历史先驱

### 定位

2023 年的 Voyager 早于当前 Agent Skills 文件标准，但已经体现了“冻结模型 + 自动课程 + 持续增长的 Skill 库 + 环境反馈修复”的核心模式。[Voyager 官方仓库](https://github.com/MineDojo/Voyager)；[项目主页](https://voyager.minedojo.org/)

### 机制

- 自动课程选择下一项探索任务；
- GPT-4 生成可执行 Minecraft 行为代码；
- 环境反馈、执行错误和自验证驱动代码迭代；
- 成功代码进入可检索、可组合的 Skill library；
- 后续复杂任务复用已有 Skill。

### 为什么重要

它展示了“能力增长”不一定要改模型权重：将成功行为固化为可执行、可组合、可检索的外部 Skill，也能形成终身学习效果。

### 为什么不能直接等同于今天的 Skill 自演进

Voyager 的 Skill 主要是环境中的可执行代码，任务反馈相对明确；企业知识工作中的 `SKILL.md` 更开放、更难验证，还涉及权限、数据泄露和错误规则污染。

## 九、厂商原生参照：Anthropic skill-creator

Anthropic 官方 `skill-creator` 已包含测试提示、with-skill/without-skill 运行、定量断言、人工审阅、可选盲测、失败归因、改写和 description 触发优化。[Anthropic 官方 skill-creator](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/skill-creator/skills/skill-creator/SKILL.md)

它的优势不是算法指标最强，而是与原生 Agent Skills 格式和 Claude 使用方式一致，适合作为创建与人工协同迭代基线。其核心仍然是显式开发工作流；不应表述为 Claude 在每次使用后自动覆盖生产 Skill。

OpenAI 官方 `skill-creator` 更侧重初始化、渐进披露、结构验证与真实使用反馈迭代，可作为另一种更保守的厂商基线。[OpenAI 官方 skill-creator](https://github.com/openai/skills/blob/main/skills/.system/skill-creator/SKILL.md)

## 十、横向比较

| 案例 | 演进对象 | 反馈来源 | 选择/门禁 | 主要优势 | 成熟度判断 |
|---|---|---|---|---|---|
| Microsoft Waza | frontmatter、Skill 行为 | trigger/behavior eval | grader、CI、人审 | 工程治理完整 | 可直接试用的工具 |
| SkillOpt | 单一 Skill 文档 | scored rollouts | 严格 held-out 改善 | 稳定、可控、紧凑 | 前沿研究原型 |
| Trace2Skill | Skill 目录/SOP | 大量成功失败轨迹 | benchmark 回归 | 多轨迹归纳、迁移 | 有代码的研究系统 |
| EvoSkill | system prompt + Skill set | 失败轨迹 | held-out Pareto | 自动发现新 Skill | 有代码的研究系统 |
| GEPA/DSPy | 任意文本组件 | trace + metric feedback | Pareto 搜索 | 通用优化器、样本效率 | 成熟开源研究框架 |
| Voyager | 可执行代码 Skill 库 | 环境与执行错误 | 自验证、任务成功 | 终身能力积累先驱 | 特定环境经典案例 |
| Anthropic skill-creator | Agent Skill | eval、人工反馈 | 断言、盲审、人审 | 原生、完整迭代流程 | 厂商官方开发工具 |

## 十一、不同需求应选择哪个案例

### 企业要给现有 Skills 建质量体系

优先参考 Waza：先建立 trigger tests、行为 eval、grader、CI 和审批。不要一开始就允许自动写回。

### 想研究“Skill 如何像参数一样稳定训练”

优先复现 SkillOpt：重点验证 bounded edits、held-out gate、rejected buffer 三个组件，而不是只复刻提示词。

### 已经积累大量 Agent 运行日志

优先参考 Trace2Skill：对轨迹做并行局部分析，再层级合并；不要按时间顺序逐条把失败补丁追加进 Skill。

### 不知道系统究竟缺哪些能力

参考 EvoSkill：允许提出新 Skill 和重新组合 Skill set，但必须增加去重、依赖和安全治理。

### 优化对象不只是 Skill

参考 GEPA/DSPy：联合优化 system prompt、tool description、routing instruction 等文本组件，再把稳定部分固化为 Skill。

### 环境有确定性反馈

参考 Voyager：代码 Skill + 环境验证最适合游戏、浏览器测试、代码构建、数据处理等可执行任务。

## 十二、一个可落地的组合方案（自拟工程建议）

不建议照搬单一案例。更稳健的组合是：

```text
Waza 风格的测试与 CI 外壳
             +
Trace2Skill 风格的多轨迹经验归纳
             +
SkillOpt 风格的受限修改与验证门禁
             +
GEPA 风格的多候选反思搜索
```

### 状态机

```text
ACTIVE vN
   ↓ 收集达到阈值的代表性轨迹
DATASET_FROZEN
   ↓ 归纳失败模式与候选修改
CANDIDATES_READY
   ↓ 训练集筛选
VALIDATION
   ├─ 未严格改善 → REJECTED（写入拒绝修改库）
   └─ 严格改善 → SECURITY_REVIEW
                         ↓
                    CANARY vN+1
                    ├─ 回归 → ROLLBACK
                    └─ 达标 → ACTIVE vN+1
```

### 最低验收字段

```json
{
  "skill_name": "spreadsheet-analysis",
  "base_version": "1.4.0",
  "candidate_version": "1.5.0-rc1",
  "evidence_dataset": "traces-2026-07-01.freeze.jsonl",
  "edit_budget_tokens": 180,
  "changes": ["add", "replace"],
  "train_score": 0.86,
  "validation_score": 0.82,
  "baseline_validation_score": 0.76,
  "heldout_test_score": 0.80,
  "trigger_false_positive_rate": 0.03,
  "token_delta": 0.08,
  "security_review": "approved",
  "rollback_artifact": "skill-v1.4.0.zip"
}
```

### 必须保留的证据边界

- 自动评分只能证明 grader 定义的质量，不能替代业务正确性；
- benchmark 改善不保证真实流量改善；
- 轨迹可能包含敏感信息，进入优化集前必须清洗和授权；
- LLM judge 会有偏差，应与确定性 verifier 和人工抽检结合；
- Skill 中的脚本属于可执行供应链制品，修改必须走代码安全审查；
- 任何“自演进”都应先生成候选版本，不能直接覆盖生产版本。

## 十三、最终判断

当前业界已经从“让 Agent 自我反思一下”进入了更严谨的阶段：

- **Waza** 代表可测试、可治理的 SkillOps；
- **SkillOpt** 代表受控文本空间训练；
- **Trace2Skill** 代表跨轨迹经验蒸馏；
- **EvoSkill** 代表 Skill 自动发现与组合搜索；
- **GEPA** 代表反思式文本优化算法；
- **Voyager** 证明外部可执行 Skill 库能够产生持续能力积累。

其中最有工程价值的共同原则不是“自动改写”，而是：**冻结执行模型、保存可验证轨迹、分离执行者与优化器、限制单次修改、使用独立验证门禁、保留拒绝经验，并将新 Skill 作为可审计候选制品发布。**

## 十四、轻量级口径：只优化 Skill，不修改模型参数

本节进一步收窄问题边界。这里的“Skill 自演进”只允许修改以下外部制品：

- `SKILL.md` 的 description、步骤、约束和示例；
- `references/` 中的领域知识或操作说明；
- `scripts/` 中与 Skill 工作流直接相关的确定性辅助脚本；
- Skill 自带的模板、校验器和路由测试。

明确排除：模型微调、LoRA、RL/RLHF、梯度更新、权重合并、蒸馏、训练服务以及任何形式的模型后训练。执行模型在所有版本对比中保持冻结。

### 最小闭环

```text
Skill vN + 代表性任务集
          ↓
冻结模型执行，保存输入、结果和必要 trace
          ↓
确定性校验器/人工反馈识别失败
          ↓
另一次普通 LLM 调用提出小范围 Skill diff
          ↓
用同一个冻结模型运行回归集
          ↓
候选版严格达标 → 保存为 vN+1
否则 → 丢弃候选，继续使用 vN
```

这里的“优化器”仍然只是一次或数次普通推理调用，不涉及训练。最小系统甚至不需要多 Agent、向量库或长期在线服务。

### 最贴合这一口径的公开案例

#### Anthropic skill-creator

完全符合冻结模型、修改 Skill 文件、重新运行 eval 的口径。它能根据测试输出和人工意见修改 Skill，还能优化 description 的触发效果。完整流程较重，但可以只采用“3–5 个任务 + 人工审阅 + 一次改写”的轻量模式。

#### Microsoft Waza

适合给轻量闭环补上 trigger tests、grader 和 CI。其只输出建议、不自动应用修改的模式尤其安全。它本身不要求模型训练。

#### SkillOpt 的简化版

SkillOpt 论文使用“训练”类比，但其被优化对象仍然只是自然语言 Skill 文档，目标模型权重保持冻结。轻量落地不必复刻 epoch、meta update 或大批 rollouts，只借鉴三个原则：

1. 每次只允许小范围 add/delete/replace；
2. 在与修改依据分离的验证任务上比较；
3. 只有候选版严格优于旧版才接受。

#### Trace2Skill 的简化版

若已有若干真实运行记录，可抽取重复失败，而不是逐条追加经验。轻量版不需要并行 Agent 群，只需让一个分析调用对 10–30 条去敏轨迹做聚类，然后生成少量可泛化规则。

### 三个轻量等级

| 等级 | 组件 | 适合场景 |
|---|---|---|
| L1 人工辅助 | 失败样例、LLM 修改建议、人工 diff、手动回归 | 个人或低频 Skill |
| L2 半自动 | 固定 eval、自动评分、生成候选 diff、人工批准 | 团队共享 Skill |
| L3 自动候选 | 定期汇总轨迹、自动小步编辑、验证门禁、自动建 PR | 高频且可确定性验证的 Skill |

三个等级都不需要模型后训练。差别只在数据收集、评分和候选发布的自动化程度。

### 推荐的最小文件结构

```text
my-skill/
├── SKILL.md
├── references/
├── scripts/
├── evals/
│   ├── cases.yaml
│   └── trigger-tests.yaml
└── evolution/
    ├── rejected-edits.jsonl
    └── latest-report.md
```

其中 `evals/` 和 `evolution/` 是自拟工程目录，不是 Agent Skills 标准的必需部分。若希望 Skill 包保持纯净，也可以把它们放在仓库的独立测试目录中。

### 一个最小候选编辑格式

```json
{
  "base_version": "1.2.0",
  "evidence": ["case-03", "case-07", "case-11"],
  "failure_pattern": "完成修改后未运行格式校验",
  "operation": "add",
  "target": "SKILL.md#Validation",
  "proposed_text": "完成写入后运行 bundled validator；失败时修复并重新验证。",
  "expected_effect": "减少无效或格式错误的输出",
  "edit_budget_tokens": 35
}
```

### 接受规则

可以使用非常简单的门禁，不必做复杂优化：

```text
accept(candidate) 当且仅当：
1. 验证集通过率 > 基线通过率；
2. 原有高优先级用例无回归；
3. trigger false-positive 不上升到阈值之外；
4. Skill token 增量没有超过预算；
5. 脚本和权限没有引入新的安全风险。
```

对于样本很少的 Skill，不宜要求统计显著性，可以采用“所有关键案例通过 + 人工审阅 diff”的保守规则。

### 最小提示模板（自拟）

```text
你是 Skill 编辑器，不得修改模型、工具权限或评测数据。

输入：
- 当前 SKILL.md
- 失败案例及校验结果
- 成功案例

任务：
1. 找出跨案例重复出现、可泛化的失败原因；
2. 只提出一个最小修改；
3. 修改必须是 add、delete 或 replace；
4. 不得加入具体测试答案、文件名或样例特例；
5. 输出 failure_pattern、operation、target、proposed_text、expected_effect；
6. 如果证据不足，输出 NO_CHANGE。
```

### 最重要的轻量化原则

- 不要每次任务后都改 Skill，应按批次积累重复证据；
- 不要让优化器看到隐藏测试答案；
- 不要把完整 trace 全部追加到 Skill，只沉淀可泛化程序；
- 优先修改指令和校验步骤，谨慎自动修改可执行脚本；
- 每次只做一个或极少数修改，便于归因和回滚；
- 自动化的终点最好是候选 diff 或 PR，而不是直接覆盖生产 Skill。

在这个严格口径下，最推荐的落地组合是：**Anthropic skill-creator 的反思改写思想 + Waza 的测试门禁 + SkillOpt 的小步严格改善原则**。这已经能形成有效的 Skill 自演进，同时完全不触碰模型参数和后训练。

# Skill 自演进机制：Anthropic 与 OpenAI 的当前实现对比

> 核查日期：2026-07-20  
> 证据范围：仅使用 Anthropic、OpenAI 官方文档、官方博客和官方 GitHub 仓库。文中“工程建议”部分为自拟方案，不代表厂商内部实现。

## 一、先给结论

当前公开实现中的 Skill 并不是一个会自行训练、自动更新权重或在每次任务后悄悄改写自己的模块。“Skill 自演进”更准确地说，是围绕可编辑的 `SKILL.md`、脚本、参考资料和资产建立的一条外部优化闭环：

1. Agent 根据名称和描述判断是否触发 Skill；
2. 按需加载指令和资源并执行任务；
3. 用人工反馈、断言、评分或对照实验评价结果；
4. 找出失败模式，修改 Skill 的描述、指令、示例或工具；
5. 重新测试、比较并发布新版本。

因此，它属于“上下文层/工作流层的演进”，而不是“模型参数层的在线学习”。截至核查日期，两家公司均未在所查官方资料中披露一种默认开启、无人工授权、能根据每次运行结果持续修改已安装 Skill 的生产机制。

Anthropic 当前公开的闭环更完整：官方 `skill-creator` 明确包含测试提示、with-skill/without-skill 基准、定量断言、人工审阅、盲测比较、失败归因、Skill 重写和触发描述优化。OpenAI 当前公开的 `skill-creator` 则以脚手架、渐进披露、结构校验和“真实使用后迭代”为主；公开文件没有展示与 Anthropic 同等完整的自动基准和描述搜索循环。

## 二、“自演进”应拆成四个层次

| 层次 | 含义 | 当前官方公开支持情况 |
|---|---|---|
| 运行时适应 | 按任务选择 Skill、按需读取资源、组合工具 | 两家均支持 |
| 会话内反思 | 执行、检查结果、修复本次产物 | 两家 Agent 都可实现，但不必然修改 Skill |
| Skill 迭代 | 根据测试与反馈修改 `SKILL.md`、脚本、示例、描述 | 两家均支持；Anthropic 的公开闭环更系统 |
| 完全自治的持续自修改 | 无需用户批准，长期收集运行数据并自动覆盖生产 Skill | 所查官方资料未证明两家默认提供该机制 |

这里最容易混淆的是“Agent 自己完成了一轮修改”和“系统自治演进”。前者仍可能由用户发起、由评测约束、由人审阅并通过文件或版本控制落盘；只有后者才接近严格意义上的自主在线学习。

## 三、共同底座：Skill 是可动态加载的外部能力包

Anthropic 将 Skill 定义为包含 `SKILL.md`、指令、脚本和资源的目录。启动时只把各 Skill 的 `name` 和 `description` 预载入提示；Claude 判断相关后读取完整 `SKILL.md`，再按需读取其引用文件。这是三层渐进披露机制。[Anthropic 工程博客](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)

OpenAI 的官方 `skill-creator` 采用相近结构：`SKILL.md` 的 frontmatter 负责触发，正文只在触发后载入，`scripts/`、`references/`、`assets/` 按需使用；官方仓库也把 Skill 定义为可被 Agent 发现和使用的指令、脚本与资源目录。[OpenAI skill-creator](https://github.com/openai/skills/blob/main/skills/.system/skill-creator/SKILL.md)；[OpenAI Skills 仓库](https://github.com/openai/skills)

这套底座让“演进”成本很低：改的是版本化文本和资源，而不是重新训练基础模型。但动态发现与渐进加载只是运行机制，本身不构成学习闭环。

## 四、Anthropic：评测驱动的 Skill 迭代闭环

Anthropic 官方 `skill-creator` 给出的高层流程是：明确目标、写初稿、建立测试提示、运行带 Skill 的任务、进行定性与定量评价、根据结果重写，然后扩大测试集继续迭代。[Anthropic 官方 skill-creator](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/skill-creator/skills/skill-creator/SKILL.md)

其公开机制可还原为：

```text
用户目标/现有 Skill
        ↓
生成或整理测试提示 + 客观断言
        ↓
多次运行：with-skill 与 without-skill
        ↓
收集产物、通过率、耗时、token、工具调用
        ↓
人工审阅；必要时进行匿名 A/B 比较
        ↓
分析胜负原因和跨测试失败模式
        ↓
修改指令 / 工具 / 示例 / 错误处理 / 结构 / 引用
        ↓
重新运行，直至满意
```

### 1. 能演进什么

- `SKILL.md` 的工作步骤和约束；
- 配套脚本、模板、参考资料；
- 错误处理和校验程序；
- frontmatter 中用于触发的 `description`。

### 2. 如何判断“变好了”

- 客观断言：例如文件是否生成、字段是否齐全、格式是否符合要求；
- 资源指标：耗时、token、工具调用次数及其方差；
- 定性审阅：适合写作、设计等不宜硬编码评分的任务；
- 盲测：独立 Agent 不知道哪份结果来自哪个版本，比较两个输出；
- 消融对照：比较 with-skill 和 without-skill，判断 Skill 是否真正贡献增益。

官方仓库中的分析器还要求基于 transcript 和指标提出具体、可操作的改进，并区分 `instructions`、`tools`、`examples`、`error_handling`、`structure`、`references` 等修改类别。[Anthropic analyzer](https://github.com/anthropics/skills/blob/main/skills/skill-creator/agents/analyzer.md)

### 3. 触发机制也可被优化

Anthropic 的 `skill-creator` 会建立 should-trigger / should-not-trigger 查询集，评估不同 description 的触发准确率，并将最佳描述写回 `SKILL.md`。官方文件同时说明，Claude 主要依据 available skills 中的名称和描述判断是否查阅 Skill；简单任务即使描述匹配，也可能因为无需额外帮助而不触发。[Anthropic 官方 skill-creator](https://github.com/anthropics/claude-plugins-official/blob/main/plugins/skill-creator/skills/skill-creator/SKILL.md)

这属于对“路由策略的文字接口”做黑盒优化，并非修改 Claude 模型内部的路由权重。

### 4. 人仍在闭环中

该流程强调向用户展示结果、让用户定性评价、解释断言，并在反馈后重写。因此更准确的名字是“Agent 辅助、评测驱动、人机协同的 Skill 演进”。盲测 Agent 和自动指标能减少主观偏差，但没有消除发布审批、权限控制和回滚需求。

## 五、OpenAI：创建、验证、真实使用反馈驱动的迭代

OpenAI 官方资料确认：Skill 可包含指令、资源和脚本；Codex 可以根据任务自动选择 Skill，用户也可显式指定；在 ChatGPT 中，当用户要求创建或修改 Skill 时，系统会自动使用 `skill-creator` 协助生成、更新或排错。[OpenAI Codex 发布文章](https://openai.com/index/introducing-the-codex-app/)；[Skills in ChatGPT](https://help.openai.com/en/articles/20001066)

当前开源 `skill-creator` 的流程是：

```text
收集具体使用案例
      ↓
规划 scripts / references / assets
      ↓
用 init_skill.py 初始化
      ↓
编写 SKILL.md 与资源
      ↓
用 quick_validate.py 做结构校验
      ↓
在真实任务中使用
      ↓
观察困难或低效点，修改并再次测试
```

[OpenAI 官方 skill-creator](https://github.com/openai/skills/blob/main/skills/.system/skill-creator/SKILL.md)

### 1. 当前公开实现的重点

- 用明确的 `description` 作为主要触发接口；
- 用渐进披露控制上下文成本；
- 将重复且要求确定性的动作固化成脚本；
- 用 `init_skill.py` 生成标准目录与 UI 元数据；
- 用 `quick_validate.py` 校验 frontmatter、必填字段和命名；
- 在真实使用中发现问题，再更新 Skill。

### 2. 与 Anthropic 公开实现的差异

OpenAI 当前官方 `skill-creator` 确实允许使用子 Agent 对修改后的行为、输出或失败模式做独立验证，并强调避免把预期答案或待验证结论泄漏给评测 Agent。但它公开的主流程没有像 Anthropic 那样内建完整的 with/without 多次运行、指标聚合、盲测比较、失败归因以及 description 搜索优化工具链。

因此，OpenAI 的公开能力应描述为“Agent 可辅助创建和迭代 Skill，且可接入独立验证”，而不应描述为“Codex 已默认自动自我进化 Skill”。OpenAI 发布文章展示了 Codex 在长时间运行中反复游玩、找缺陷、实现和验证游戏，也提到 Automations 可以定期创建新 Skill；这说明其通用 Agent、Skill 与定时自动化可以被组合成演进流水线，但文章没有披露一个自动收集所有 Skill 运行反馈并安全覆盖生产版本的内建优化器。[OpenAI Codex 发布文章](https://openai.com/index/introducing-the-codex-app/)

### 3. 管理与安全边界

OpenAI 文档显示，上传的 Skill 会经过扫描，可能被标为 `Needs Review` 或 `Blocked`；企业管理员可控制创建、上传、分享、发布和安装权限，并查看使用元数据。这反映的是受治理的制品生命周期，而不是无约束的自修改。[Skills in ChatGPT](https://help.openai.com/en/articles/20001066)

## 六、横向对比

| 维度 | Anthropic | OpenAI |
|---|---|---|
| Skill 载体 | `SKILL.md` + scripts/resources | `SKILL.md` + scripts/references/assets |
| 触发 | name/description 进入可用 Skill 信息，由 Claude 判断 | name/description 是主要触发机制，由 Codex 判断或用户显式指定 |
| 上下文加载 | 明确公开三层渐进披露 | 明确公开 metadata → body → bundled resources |
| 创建辅助 | 官方 `skill-creator` | 官方 `skill-creator`，ChatGPT 可自动调用它 |
| 结构校验 | 可打包、测试，官方创建器含配套工具 | `init_skill.py`、`quick_validate.py`、UI metadata 生成 |
| 行为评测 | 公开流程较完整：多次运行、with/without、断言、指标、人工审阅 | 公开主流程以真实使用反馈和独立验证为主 |
| 盲测/失败归因 | 官方创建器明确提供可选盲测和 analyzer | 当前公开主流程未展示同等级内建闭环 |
| 触发描述优化 | 有 should/should-not-trigger 测试与优化循环 | 强调 description 质量，但公开创建器未展示等价搜索循环 |
| 默认持续自改 | 未被官方资料证明 | 未被官方资料证明 |
| 发布治理 | 用户参与评价与打包 | 扫描、审核状态、角色权限、分享/发布控制 |

## 七、一个完整案例：文档 Skill 如何演进

以下是根据两家公开构件整理的“分析框架”，用于说明机制，不代表任一厂商未公开的内部流水线。

### 用户诉求

“让财务报告 Skill 稳定生成包含封面、利润表、风险摘要和来源说明的 PDF，并减少格式错误。”

### 任务拆分与依赖

| 任务 | 输入 | 输出 | 依赖 |
|---|---|---|---|
| 定义测试集 | 真实报告需求 | 10 个代表性提示 | 无 |
| 定义断言 | 验收标准 | 每个提示的结构/内容断言 | 测试集 |
| 运行基线 | 提示、旧 Skill | 旧版产物与 trace | Skill v1 |
| 运行候选版 | 提示、新 Skill | 新版产物与 trace | Skill v2 |
| 评分与盲审 | 产物、断言 | 通过率、偏好、成本 | 两组运行完成 |
| 失败归因 | trace、评分 | 可操作修改项 | 评分完成 |
| 发布 | 候选 Skill | v2 发布或回滚 | 达到门槛并经审批 |

### 结构化字段

```json
{
  "eval_id": "finance-pdf-007",
  "prompt": "根据输入数据生成季度财务报告 PDF",
  "skill_version": "v2",
  "run_seed": 3,
  "assertions": [
    "生成单个可打开的 PDF",
    "包含利润表和风险摘要",
    "每个外部数字带来源",
    "没有文本溢出或截断"
  ],
  "metrics": {
    "assertion_pass_rate": 1.0,
    "duration_seconds": 46,
    "tokens": 18200,
    "tool_calls": 14
  },
  "human_preference": "v2",
  "evidence": ["output.pdf", "trace.json", "rendered-pages/"]
}
```

### 状态变化

```text
DRAFT
  → BASELINE_RUNNING
  → CANDIDATE_RUNNING
  → REVIEW_REQUIRED
  → APPROVED
  → PUBLISHED

任一阶段失败：→ REVISION_REQUIRED → DRAFT
发布后回归失败：→ ROLLED_BACK
```

### 执行与校验

1. 固定输入数据和评测提示，避免两个版本收到不同任务。
2. 每个版本至少运行多次，避免把单次随机波动当成改进。
3. 对文件存在、章节结构、字段完整性采用确定性断言。
4. 对版式与可读性渲染为图片后人工或盲审评价。
5. 对失败 trace 做因果归因：是指令遗漏、脚本缺陷、触发失败，还是模型随机性。
6. 只修改有证据支持的部分。例如发现 4/10 次漏掉来源，就在模板和验证脚本中同时加入来源字段与失败检查。
7. 候选版必须同时满足质量门槛和成本上限，才允许替换旧版。

### 验收结果示例

| 指标 | v1 | v2 | 结论 |
|---|---:|---:|---|
| 客观断言通过率 | 72% | 96% | 改善 |
| 盲审偏好率 | 35% | 65% | v2 更优 |
| 平均 token | 16k | 18.2k | 增加 13.8% |
| 平均耗时 | 41s | 46s | 增加 12.2% |
| 严重格式错误 | 3/30 | 0/30 | 达标 |

验收可写为：“v2 在质量上达到发布门槛，成本增加仍低于预设 15% 上限，经人工批准发布；保留 v1 以便回滚。”

### 证据边界

- 上述 JSON 字段、状态机和数字是示范性的自拟设计；
- Anthropic 官方创建器支持相似的测试、指标、比较和迭代思想，但不代表其生产后台使用相同字段；
- OpenAI 官方公开材料允许组合 Skill、验证、Automation 和版本化文件，但未公开完全相同的自动发布流水线。

## 八、工程建议：如何安全实现真正的 Skill 自演进

以下为自拟方案。

建议把系统拆成五个角色，避免执行 Agent 既当运动员又当裁判：

1. **Runner**：使用固定版本 Skill 执行任务；
2. **Collector**：保存输入、产物、trace、成本和用户反馈；
3. **Evaluator**：运行确定性断言和独立盲审；
4. **Optimizer**：根据失败聚类提出最小修改；
5. **Governor**：负责权限、审批、灰度发布、回滚和审计。

最重要的控制规则是：

- 生产 Skill 不允许原地覆盖，只能生成候选版本；
- 训练/优化集与保留测试集分离，防止过拟合；
- 评价器看不到版本身份和修改意图，减少偏见；
- 同时看质量、成本、延迟、安全和触发准确率；
- 脚本变更按代码变更处理，进行沙箱、依赖和供应链审查；
- 自动发布仅限低风险 Skill，高风险领域必须人工批准；
- 每次演进保留 diff、数据集版本、评测报告和可回滚制品。

## 九、最终判断

如果把“自演进”定义为“Agent 能帮助 Skill 从使用反馈中迭代”，Anthropic 和 OpenAI 都已实现；Anthropic 的公开工具链目前更接近完整的 eval-driven optimization loop。

如果把“自演进”定义为“Skill 在生产运行中自主积累经验、自动修改自身并无审批发布”，则截至 2026-07-20，所查官方资料不足以证明 Anthropic 或 OpenAI 已默认提供这种机制。比较准确的表述是：**两家已经提供了可演进的 Skill 制品与 Agent 化迭代工具，但安全、持续、全自动的自演进仍需要用户或平台工程方自行搭建评测、版本、审批和回滚层。**

## 十、2026 年 7 月 Reflect 功能与 Agent Skill 的关系

Anthropic 于 2026 年 7 月 9 日发布测试版 Reflect（官方标题为 *Introducing a way to reflect on how you use Claude*）。它是 Claude Web 和桌面端设置中的个人使用复盘仪表板，面向开启 Memory 的 Free、Pro 和 Max 用户。[Anthropic：Reflect 发布说明](https://www.anthropic.com/news/reflect-with-claude)

### Reflect 实际做什么

- 汇总过去 1、3、6 或 12 个月的 Claude 对话活动；
- 展示常见主题、使用时段、任务类型和协作模式；
- 引导用户反思哪些事情适合委托 AI、哪些仍希望自己完成；
- 按 4D AI Fluency Framework 给出反馈：Delegation、Description、Discernment、Diligence；
- 提供改进建议，例如对长期工作使用 Project，减少反复解释上下文；
- 支持 quiet hours 和使用一段时间后的休息提醒。

### 为什么容易和 Agent Skills 混淆

发布文章有一个标题是 “Build AI skills that support your original thinking”，正文也写到利用 reflection “build new skills”。但紧接着给出的四项是 AI Fluency Framework 中的人类能力：委托、描述、判断和勤勉。因此这里的 `skills` 是普通意义上的“人的 AI 使用技能”，不是以 `SKILL.md`、脚本和资源目录表示的产品功能 **Agent Skills**。

官方文章没有说明 Reflect 会：

- 创建或编辑 `SKILL.md`；
- 把历史失败自动写回某个 Agent Skill；
- 运行 Skill 的 with/without 对照评测；
- 调用 `skill-creator` 优化 Skill；
- 自动发布新的 Skill 版本。

相反，Anthropic 明确表示 Reflect 生成的信息和洞察保留在该功能中，不用于其他目的。这进一步说明，不能把它描述成 Agent Skill 的自动经验采集器或自演进后台。

### 与 Skill 自演进的真正联系

两者存在的是**概念关系和潜在人工桥接**，不是官方披露的直接技术连接：

```text
Reflect：分析人的长期 Claude 使用模式
                    ↓ 用户主动判断
发现某类任务反复出现或协作方式不佳
                    ↓ 用户主动发起
用 skill-creator 创建/修改 Agent Skill
                    ↓
用代表性任务、断言和人工审阅评测 Skill
```

换言之，Reflect 可以帮助用户发现“什么工作值得固化成 Skill”，却没有证据表明它会自行完成固化和优化。

Anthropic 关于 Agent Skills 的官方工程文章确实建议另一种更直接的演进方法：在真实任务中观察 Claude 使用 Skill 的轨迹，让 Claude 把成功做法和常见错误沉淀为 Skill 中的上下文与代码；跑偏时要求它 self-reflect，找出问题并迭代 Skill。该文章还把“Agent 自己创建、编辑和评估 Skills”描述为更长远的方向。[Anthropic：Equipping agents for the real world with Agent Skills](https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills)

这里需要区分三个同名或近义概念：

| 概念 | 反思对象 | 输出 | 是否直接修改 Agent Skill |
|---|---|---|---|
| 2026-07 Reflect 产品功能 | 用户长期如何使用 Claude | 仪表板、AI Fluency 建议、提醒 | 官方未说明会修改 |
| 任务中的 self-reflect | Claude 某次任务为何成功或失败 | 失败归因、改进建议 | 用户可据此要求修改 |
| Skill eval/iteration | Skill 在代表性任务中的表现 | 指标、比较结果、候选 Skill 版本 | 可以，但属于显式迭代流程 |

因此，对 7 月 Reflect 最准确的判断是：**它不是 Skill 自演进机制，而是面向人的使用复盘功能；它可以成为用户发现 Skill 需求的上游信号，但官方没有把两者自动串联。**

# Hermes Skill 自演进方案详解

> 核查日期：2026-07-26  
> 研究对象：Nous Research 的开源项目 Hermes Agent，以及独立仓库 `NousResearch/hermes-agent-self-evolution`。  
> 证据边界：方案描述以 Nous Research 官方仓库和文档、DSPy/GEPA 官方资料及当前公开源码为准。README/PLAN 中的目标不等于已经实现；本文专门区分“运行时代码”“离线优化原型”和“未来规划”。

## 一、先给结论

Hermes 所谓的 Skill“自演进”，实际包含两个闭环：

1. **在线经验沉淀闭环**：Hermes 在日常任务中通过 `skill_manage` 创建、局部修补、重写或删除 Skill，把一次任务中学到的程序性知识保存到 `~/.hermes/skills/`，供未来会话按需加载。
2. **离线评测优化闭环**：独立项目 `hermes-agent-self-evolution` 把 `SKILL.md` 正文包装成 DSPy 模块，构造训练/验证/留出评测集，用 GEPA 根据执行结果搜索更好的文本版本，再经过约束与留出集比较后输出候选文件。

二者的定位不同：

```text
任务内学习：
一次成功/纠错 → Agent 总结步骤 → skill_manage 写入 Skill

系统化优化：
Skill vN + 多个评测任务 → GEPA 搜索候选 → 留出集比较 → 人工审阅 → Skill vN+1
```

前者更像“把经验写进程序性记忆”，后者才是严格意义上的“以评测为反馈的 Skill 优化”。它们都不修改模型参数，不是微调或强化学习。

截至核查日，官方 README 将 **Phase 1：Skill 文件优化**标为已实现；工具描述、系统提示、Python 工具代码和持续自动优化仍标为 planned。并且当前 Phase 1 源码仍有明显的原型性缺口，不能把 README 描述的全部 guardrails 当作已经接通的生产能力。

## 二、Hermes 的 Skill 基础设施

### 2.1 Skill 是什么

Hermes 将 Skill 定义为按需加载的知识文档，遵循渐进披露：

```text
skill-name/
├── SKILL.md
├── references/
├── templates/
└── scripts/
```

`SKILL.md` frontmatter 提供名称、描述、版本等元数据，正文保存操作流程；大篇幅 API 文档、示例和模板可以放到配套文件中。Skill 与 Memory 的官方区分是：

- Skill：程序性知识，即“怎样做”，仅在相关时加载；
- Memory：事实性知识，即“是什么”，通常注入每次会话。

所有本地 Skill 以 `~/.hermes/skills/` 为主要事实源。Agent 创建的 Skill、Hub 安装的 Skill 和随 Hermes 附带的 Skill最终都在这里可用。

### 2.2 为什么 Skill 能成为“可演进状态”

模型权重是冻结的，但 Skill 是外部、可读写、可版本化的文本状态，因此有四个优势：

1. 修改成本远低于模型训练；
2. 新知识跨会话保留；
3. 修改结果可用 Git diff 审阅；
4. 出现退化时可以回滚。

所以 Hermes 的“学习”更准确地说是：

> 将执行经验编译成外部程序性说明，并让未来的同一 Agent 在相关任务中重新加载这些说明。

这会改变后续行为，但不代表底层模型形成了新的参数记忆。

## 三、第一层：运行时的 Agent-managed Skills

### 3.1 何时触发经验沉淀

Hermes 官方 Skills 文档列出的典型场景包括：

- 成功完成复杂任务，尤其是经历了多次工具调用；
- 遇到错误或死路后找到正确路径；
- 用户纠正了 Agent 的方法；
- 发现一个非平凡、以后可能复用的工作流。

这不是每次任务后无条件自改。更合理的语义是：Agent 判断经验具有复用价值时，提出或执行 Skill 管理操作。

### 3.2 `skill_manage` 的修改粒度

公开文档列出的动作包括：

| 动作 | 作用 |
|---|---|
| `create` | 创建新的 `SKILL.md` |
| `patch` | 用 `old_string/new_string` 做局部修改，官方偏好此方式 |
| `edit` | 完整替换 `SKILL.md`，用于较大重构 |
| `delete` | 删除整个 Skill |
| `write_file` | 写入 references、scripts、templates 等配套文件 |
| `remove_file` | 删除配套文件 |

这里最重要的工程选择是优先 `patch`：小步修改更容易归因、审阅和回滚，避免 Agent 因一个局部教训重写整份 Skill。

### 3.3 在线闭环的实际过程

```text
用户任务
  ↓
Agent 加载已有 Skill
  ↓
调用工具并观察成功、错误、用户纠正
  ↓
识别“可泛化的程序性经验”
  ↓
create / patch / edit
  ↓
写入 ~/.hermes/skills/
  ↓
未来会话通过 Skill 描述发现并按需加载
```

这一层的优点是快、贴近真实环境；缺点是单次经验可能具有偶然性，且 Agent 既是执行者又是经验总结者，容易把特例写成通则。因此，它更适合保存明确的操作路径、环境约束和已验证恢复步骤，不适合自动发布高风险脚本或安全策略。

## 四、第二层：基于 DSPy + GEPA 的离线进化

### 4.1 独立仓库与总体架构

`hermes-agent-self-evolution` 是运行在 Hermes Agent 之外的优化器。官方 PLAN 明确说它 “operates ON hermes-agent, not inside it”。目标架构是：

```text
读取当前 Skill
      ↓
构造评测集
      ↓
将 Skill 包装为 DSPy Module
      ↓
GEPA 读取执行轨迹/反馈并生成候选文本
      ↓
候选在验证集上评分
      ↓
约束检查与留出集比较
      ↓
输出最佳候选、指标和 diff
      ↓
目标设计：创建分支/PR，人工审阅后合并
```

它通过普通模型 API 调用变异和评测字符串，不训练权重，也不需要 GPU。

### 4.2 Skill 如何被包装成可优化对象

当前 `skill_module.py` 将 Skill 拆为：

```text
frontmatter：保留，不参与优化
body：作为 skill_text，参与优化
```

`SkillModule.forward(task_input)` 调用一个 DSPy `ChainOfThought`：

```text
输入：
  skill_instructions = 当前 Skill 正文
  task_input = 评测任务

输出：
  output = 按 Skill 完成任务后的回答
```

因此优化变量不是模型，而是 `skill_text`。候选确定后，程序用原 frontmatter 与新 body 重新组装 `SKILL.md`。

这也意味着当前实现主要优化“文字回答是否更符合程序”，并不等价于把完整 Hermes 工具循环、文件修改、终端执行都纳入真实评测。对于代码审查、部署、调试等依赖工具的 Skill，这一简化会影响外部有效性。

### 4.3 评测数据从哪里来

当前代码支持三类来源：

1. `synthetic`：强模型阅读 Skill，生成 `(task_input, expected_behavior)`；
2. `golden`：人工维护的 JSONL 评测集；
3. `sessiondb`：从 Claude Code、Copilot、Hermes 会话历史导入相关案例。

数据随后切成：

```text
train：供优化器观察与变异
validation：选择候选
holdout：优化完成后比较 baseline 与 evolved
```

合成数据适合冷启动，但存在“从当前 Skill 生成问题和标准”的闭环偏差：如果原 Skill 本身漏掉关键步骤，合成 rubric 也可能继承遗漏。生产使用应以人工 golden cases、真实失败样例和确定性验证器为主，合成数据只用于补充覆盖面。

### 4.4 GEPA 到底怎样“进化”

GEPA 是 Genetic-Pareto 反思式文本优化器。根据 DSPy 官方说明，它的核心有三步：

1. **反思式变异**：读取输入、输出、失败、约束和文字反馈，诊断问题并提出新的指令文本；
2. **富反馈优化**：不仅使用一个标量分数，也可利用测试错误、执行日志、解析失败、分项评分等文字反馈；
3. **Pareto 候选选择**：不只保留全局平均分最高者，还保留在某些评测样本上表现最好的候选，维持互补策略和探索能力。

直观示例：

```text
Skill v1：
“审查 PR，指出潜在问题。”

失败轨迹：
- 能发现命名问题；
- 三次漏掉资源未关闭；
- rubric 指出没有检查异常路径。

反思：
检查顺序太宽泛，缺少资源生命周期与异常路径门禁。

候选 v2：
“先建立资源获取/释放表，再逐条检查正常、异常、提前返回路径；
只有所有资源都有成对清理时才通过该项。”
```

候选 v2 不是因为“写得更长”就被接受，而应在验证任务上实际提高发现率，并在留出任务上不退化。

### 4.5 当前命令

官方 README 给出的入口是：

```bash
python -m evolution.skills.evolve_skill \
  --skill github-code-review \
  --iterations 10 \
  --eval-source synthetic
```

也可选择 `sessiondb` 或提供 golden dataset。程序当前会保存：

```text
output/<skill>/<timestamp>/
├── baseline_skill.md
├── evolved_skill.md
└── metrics.json
```

## 五、完整案例：`github-code-review` Skill 的一次进化

以下案例用于解释官方管线如何工作。字段和验收设计是基于公开架构整理的工程化示例，不表示官方仓库已经附带完全相同的数据集或产出。

### 5.1 用户诉求

团队发现 `github-code-review` Skill 能检查代码风格，但经常漏报：

- 异常路径上的资源泄漏；
- 未处理的权限边界；
- 测试只覆盖 happy path。

目标是提高实质性缺陷召回率，同时避免让审查报告变得过长。

### 5.2 任务拆分

```text
T1 冻结 Skill v1 和执行模型
T2 建立带已知缺陷的 PR 评测集
T3 运行 baseline 并保存输出/评分
T4 GEPA 根据失败样例提出候选
T5 在 validation 上筛选
T6 在不可见 holdout 上比较
T7 检查大小、结构、安全与通用回归
T8 人工审阅 diff，决定是否发布
```

依赖关系为 `T1 → T2 → T3 → T4 → T5 → T6 → T7 → T8`；其中训练、验证和留出数据必须在 T2 时冻结，不能在看到 holdout 结果后反复改 Skill。

### 5.3 结构化评测样例

```json
{
  "case_id": "review-017",
  "task_input": "Review this Python PR that opens a file before a parsing operation.",
  "expected_behavior": {
    "must_find": [
      "file handle leaks when parsing raises",
      "missing test for exception path"
    ],
    "must_not_claim": [
      "SQL injection"
    ],
    "max_findings": 6
  },
  "split": "holdout",
  "artifact_hash": "sha256:...",
  "deterministic_checks": {
    "planted_issue_recall": true,
    "false_positive_count": true
  }
}
```

### 5.4 状态变化

```text
BASELINE_FROZEN
  ↓ baseline 执行
FAILURE_EVIDENCE_READY
  ↓ GEPA 反思与变异
CANDIDATE_POOL
  ↓ validation 选择
HOLDOUT_EVALUATED
  ├─ 未严格改善 → REJECTED
  └─ 严格改善 → HUMAN_REVIEW
                         ├─ 拒绝 → REJECTED
                         └─ 批准 → RELEASE_CANDIDATE
```

假设 GEPA 发现旧 Skill 的清单只关注“代码表面问题”，便加入：

```markdown
Before writing findings:
1. Trace acquired resources through success, exception, and early-return paths.
2. Check authorization at each externally reachable boundary.
3. Match every high-severity finding to an existing or missing regression test.
```

### 5.5 校验方法

至少同时使用：

- 确定性 planted-issue recall；
- 无缺陷样例上的 false-positive rate；
- LLM judge 对可操作性、程序遵循和简洁性的分项评分；
- 报告长度和 Skill 大小限制；
- 通用任务回归；
- 人工检查是否泄漏 holdout 答案或硬编码样例。

### 5.6 验收结果示例

```json
{
  "baseline_holdout_recall": 0.61,
  "candidate_holdout_recall": 0.78,
  "baseline_false_positive_rate": 0.09,
  "candidate_false_positive_rate": 0.08,
  "report_token_delta": 0.12,
  "skill_size_bytes": 11840,
  "structure_check": "passed",
  "general_regression": "passed",
  "human_review": "approved"
}
```

只有在指标定义、数据冻结、模型版本和运行环境都一致时，这组前后结果才可比较。LLM judge 分数本身只能证明与 rubric 的一致性，不能替代真实缺陷校验。

## 六、官方愿景与当前源码之间的差距

这是理解 Hermes 方案最关键的部分。

### 6.1 README/PLAN 描述的目标 guardrails

官方仓库宣称候选需要经过：

- 完整 pytest；
- Skill 大小限制；
- prompt caching 兼容；
- 语义保持；
- benchmark 回归；
- PR 人工审阅，不直接提交。

PLAN 还提出 TBLite、YC-Bench、统计显著性检查、Git 分支和自动 PR。

### 6.2 当前 Phase 1 源码实际接通的内容

从当前公开源码可确认：

- 能发现并读取 Skill；
- 能生成/加载并切分数据集；
- 能建立 DSPy SkillModule；
- 能调用 GEPA，失败时显式回退 MIPROv2；
- 能做大小、增长、非空和结构检查；
- 能在 holdout 上比较 baseline/evolved；
- 能保存候选文件和 `metrics.json`。

### 6.3 当前实现的关键缺口

#### 评分目标仍是关键词重合

`fitness.py` 虽然定义了多维 `LLMJudge`，但 `evolve_skill.py` 实际传给 GEPA 的是 `skill_fitness_metric`。该函数主要计算 `expected_behavior` 与输出之间的词集合重合度。

后果是优化器可能学会重复 rubric 关键词，而不是更正确地完成任务。源码中“完整 LLM judge”类存在，不代表当前主优化路径已使用它。

#### `--run-tests` 目前没有接到主流程

`ConstraintValidator` 定义了 `run_test_suite()`，配置也保存 `run_pytest`，但当前 `evolve()` 主流程没有调用测试方法。因此不能把命令行的 `--run-tests` 当作已经生效的硬门禁。

#### benchmark gate 和自动 PR 尚未落实在 Phase 1 主路径

README 图中有 benchmark 和 PR；当前主脚本只保存本地输出，没有执行 TBLite/YC-Bench，也没有创建 Git 分支或 PR。

#### Skill 结构校验存在接口错位风险

当前调用 `validate_all(skill["body"], "skill")`，但结构校验要求文本以 YAML frontmatter 开头并包含 `name`、`description`。`body` 已经被解析器剥离 frontmatter，因此按公开代码推断，这项检查会失败。这里是直接源码推断，需以实际运行测试进一步确认。

#### 语义保持与缓存兼容没有形成强验证

当前约束器可见的主要检查是字符数、相对增长、非空和结构；没有看到独立的语义等价判定或缓存兼容检测。

因此，更准确的成熟度判断是：

> Hermes 已公开一个能跑通核心概念的 Skill 文本优化原型和一份较完整的目标设计，但当前仓库还不是 README 全部治理能力均已落实的生产级持续自演进系统。

## 七、这套方案为什么有价值

### 7.1 把能力改进从权重空间搬到文本空间

Skill 是显式文本，修改可读、可审计、可回滚。对于部署流程、代码审查规范、故障处置等程序性知识，这通常比重新训练模型更经济。

### 7.2 从单次反思升级到多样本评测

普通“self-reflection”只根据一次失败改提示；GEPA 管线让候选在多个样本上竞争，并通过 validation/holdout 降低单例过拟合。

### 7.3 反思信号可以比单一 reward 更丰富

GEPA 可以利用执行轨迹、错误消息和分项反馈。比如“测试失败”只给 0 分，而“第 3 步没有关闭文件句柄，异常路径断言失败”可以指导具体文本变异。

### 7.4 与 Hermes 原生 Skill 生命周期衔接自然

离线优化器输出的仍是普通 `SKILL.md`，无需改运行时协议；通过人工审阅后即可进入原有 Skill 加载体系。

## 八、主要风险

1. **评测集污染**：从原 Skill 合成 rubric，可能只会强化原 Skill 已有偏见。
2. **奖励黑客**：关键词重合、单一 LLM judge 都可能被表面文本欺骗。
3. **轨迹隐私**：SessionDB 可能包含源码、用户数据、密钥或第三方内容。
4. **同模型自评偏差**：执行、生成数据、评判若使用同一模型家族，错误会相关。
5. **Skill 膨胀**：每次追加规则会增加上下文、冲突和过拟合。
6. **工具型任务失真**：只评回答文本，不能证明真实工具操作更可靠。
7. **自动写回风险**：未经审批修改脚本、权限规则或共享 Skill 会扩大事故范围。
8. **版本归因错误**：评测必须绑定 Skill hash、模型版本、工具版本和数据集快照。

## 九、若要落地，建议怎样补强（工程建议）

以下不是 Hermes 官方已实现机制，而是基于其架构的补强方案：

```text
真实 Trace / Golden cases / 合成边界案例
              ↓
PII 与秘密清洗，冻结 dataset hash
              ↓
Baseline 执行（绑定 model/tool/skill hash）
              ↓
GEPA 生成有限数量的候选 diff
              ↓
确定性 verifier + LLM judge + 成本/延迟评分
              ↓
validation 严格改善门禁
              ↓
holdout 一次性验收 + 通用 benchmark
              ↓
安全扫描 + 人工 diff
              ↓
PR / Canary / Rollback
```

最低限度应做：

- 用真实 Agent tool loop 代替纯文本 `SkillModule`；
- 将多维 judge 真正接入 GEPA，并返回文字反馈；
- 对可验证任务优先使用测试、schema、静态分析等确定性评分；
- 修复并强制执行 pytest/benchmark gates；
- 候选只能生成 PR，不直接覆盖活动 Skill；
- 保存 rejected candidates，防止以后重复引入已知坏修改；
- 设置 Skill token budget 与每次 diff 大小上限；
- 在 canary 流量上观察后再晋升。

## 十、最终判断

Hermes 的独特之处不在于提出了全新的“自学习模型”，而在于把三种已有能力组合起来：

```text
原生可写 Skill
+ 跨会话程序性记忆
+ DSPy/GEPA 的反思式文本搜索
= 无需训练权重的 Agent 能力演进路径
```

其中运行时 `skill_manage` 解决“怎样及时保存经验”，离线 GEPA 管线解决“怎样用多个评测样本系统地改进经验”。理想闭环是在线收集证据、离线生成候选、严格评测、人工发布。

但按当前公开源码，最严谨的表述应是：**Hermes 已具备 Agent-managed Skills，并发布了 Phase 1 Skill 优化原型；完整的自动测试门禁、benchmark、PR 发布和持续闭环仍未全部实现。**研究它时应把官方愿景、README 状态和可验证源码三层分开。

## 十一、主要来源

- [Nous Research：Hermes Agent Self-Evolution 官方仓库](https://github.com/NousResearch/hermes-agent-self-evolution)
- [Nous Research：Self-Evolution 完整 PLAN](https://github.com/NousResearch/hermes-agent-self-evolution/blob/main/PLAN.md)
- [Nous Research：Hermes Skills System](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/skills.md)
- [Nous Research：Work with Skills](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/guides/work-with-skills.md)
- [当前 `evolve_skill.py` 源码](https://github.com/NousResearch/hermes-agent-self-evolution/blob/main/evolution/skills/evolve_skill.py)
- [当前 `skill_module.py` 源码](https://github.com/NousResearch/hermes-agent-self-evolution/blob/main/evolution/skills/skill_module.py)
- [当前 `fitness.py` 源码](https://github.com/NousResearch/hermes-agent-self-evolution/blob/main/evolution/core/fitness.py)
- [当前 `constraints.py` 源码](https://github.com/NousResearch/hermes-agent-self-evolution/blob/main/evolution/core/constraints.py)
- [当前 `dataset_builder.py` 源码](https://github.com/NousResearch/hermes-agent-self-evolution/blob/main/evolution/core/dataset_builder.py)
- [DSPy 官方：GEPA Reflective Prompt Optimizer](https://github.com/stanfordnlp/dspy/blob/main/docs/docs/api/optimizers/GEPA/overview.md)
- [GEPA 原始论文](https://arxiv.org/abs/2507.19457)
- [GEPA 官方实现](https://github.com/gepa-ai/gepa)

## 十二、补充：DSPy 模块与 GEPA 的关系

### 12.1 DSPy 模块是什么

DSPy Module 可以理解为一个“包含 LLM 调用的可组合程序单元”。它与普通 Python 函数相似：有输入、有输出、可以嵌套；不同之处是内部某些步骤由语言模型完成。

一个最小 DSPy 程序通常包含三层：

```text
Signature：声明输入字段、输出字段和任务语义
    ↓
Module：组织一个或多个推理步骤
    ↓
LM：真正执行这些步骤的语言模型
```

例如：

```python
class ReviewSignature(dspy.Signature):
    """按照审查规则检查代码。"""

    rules: str = dspy.InputField()
    code: str = dspy.InputField()
    findings: str = dspy.OutputField()


class ReviewModule(dspy.Module):
    def __init__(self, rules: str):
        super().__init__()
        self.rules = rules
        self.review = dspy.ChainOfThought(ReviewSignature)

    def forward(self, code: str):
        return self.review(rules=self.rules, code=code)
```

这里：

- `ReviewSignature` 是接口契约，不负责实现具体算法；
- `ReviewModule` 是工作流；
- `dspy.ChainOfThought` 是一个内置推理模块；
- 配置给 DSPy 的模型在运行时生成 `findings`；
- `rules` 或 Signature 中的自然语言指令可以成为优化对象。

“模块”不代表模型参数模块，也不是神经网络层。它主要是把 Prompt、输入输出字段、推理步骤和子调用包装成一个可运行、可评测、可替换的程序组件。

在 Hermes 当前实现中，Skill 被包装为：

```python
class SkillModule(dspy.Module):
    def __init__(self, skill_text):
        self.skill_text = skill_text
        self.predictor = dspy.ChainOfThought(TaskWithSkill)

    def forward(self, task_input):
        result = self.predictor(
            skill_instructions=self.skill_text,
            task_input=task_input,
        )
        return dspy.Prediction(output=result.output)
```

所以 Hermes 所说的“把 Skill 包装为 DSPy Module”，实际含义是：

```text
原来的 SKILL.md 正文
      ↓
成为 SkillModule 的文本参数 skill_text
      ↓
每个评测任务都执行 SkillModule(task_input)
      ↓
产生可被评分的 output
```

DSPy Module 本身不负责寻找更好的 Skill，它只使 Skill 变成一个具有稳定输入、输出和执行路径的可评测程序。

### 12.2 GEPA 是什么

GEPA 全称 Genetic-Pareto，是 DSPy 可使用的一种反思式文本优化器。它负责回答：

> 在底层模型和 Python 工作流基本不变的情况下，怎样改写 Module 中的指令文本，才能在给定评测集上获得更高质量？

最小优化接口可以抽象为：

```python
optimizer = dspy.GEPA(metric=score_function)

optimized_module = optimizer.compile(
    student=baseline_module,
    trainset=train_cases,
    valset=validation_cases,
)
```

这里：

- `student`：等待优化的 DSPy Module；
- `trainset`：用来发现失败和生成修改的案例；
- `valset`：用来比较候选的案例；
- `metric`：判定输出质量的评分函数；
- `compile()`：执行离线优化，返回一个文本参数经过改进的 Module；
- `optimized_module`：优化后的程序制品，不是新训练出来的模型。

GEPA 的核心循环是：

```text
执行当前 Module
      ↓
收集输入、输出、执行轨迹、分数和文字反馈
      ↓
反思失败原因
      ↓
生成针对性的指令变异
      ↓
运行候选并评分
      ↓
更新 Pareto 候选集合
      ↓
继续选择候选进行变异
```

#### Genetic 的含义

它把文本版本视为候选个体，不断执行“选择—变异—评测”。这里的遗传不是更新神经网络权重，而是产生新的 Prompt、规则或代码文本。

#### Pareto 的含义

GEPA 不只保留平均分最高的单一候选。假设：

| 候选 | 案例 A | 案例 B | 案例 C |
|---|---:|---:|---:|
| v1 | 0.9 | 0.4 | 0.6 |
| v2 | 0.6 | 0.9 | 0.6 |
| v3 | 0.7 | 0.7 | 0.8 |

v1 擅长 A，v2 擅长 B，v3 擅长 C。GEPA 可以把这些在不同实例上具有优势的候选保留在 Pareto frontier，而不是过早只留下某个平均最好版本。随后再从这些互补候选中抽样和变异，减少陷入局部最优的风险。

#### Reflective 的含义

普通遗传搜索可能只知道候选得了 `0.4` 分。GEPA还能接收：

```text
“输出发现了文件未关闭，但没有分析异常路径；
第 2 项结论没有引用相关代码；
报告超过长度限制。”
```

反思模型据此提出更有方向的修改，例如增加“分别跟踪正常、异常和提前返回路径”，而不是进行无目标的随机改写。

### 12.3 两者怎样配合

```text
DSPy Module = 待执行、待评测的 LLM 程序
Metric      = 质量标准
Dataset     = 考题
GEPA        = 根据做题轨迹修改程序文本的优化算法
LM          = 实际执行任务和提出修改的模型
```

用传统机器学习作类比，但不要把它们完全等同：

| 传统训练概念 | DSPy/GEPA 中的近似对应 |
|---|---|
| 模型结构 | DSPy Module/工作流 |
| 可训练参数 | Prompt、Skill、指令和示例文本 |
| 训练样本 | trainset |
| 验证样本 | valset |
| 损失/指标 | metric 与文字反馈 |
| 优化器 | GEPA |
| 训练结果 | 优化后的 DSPy Module |

关键区别是：GEPA 修改的是可读文本，不通过梯度更新底层 LLM 权重。

### 12.4 在 Hermes 中的一次具体执行

假设当前 Skill 正文是：

```text
检查代码中的重要问题，并简洁汇报。
```

评测任务：

```text
审查一个在异常路径上没有关闭文件的 Python 函数。
```

执行过程：

1. `SkillModule` 把 Skill 正文与任务输入交给模型；
2. 模型只发现命名问题，没有发现资源泄漏；
3. verifier 或 judge 给低分，并反馈“没有检查异常路径”；
4. GEPA 阅读该轨迹，生成候选 Skill：

   ```text
   先列出资源的获取点，再分别检查正常、异常和提前返回路径上的释放操作。
   ```

5. 新候选重新执行训练和验证任务；
6. 如果它提高相关案例得分，同时没有让其他案例退化，就进入较优候选集合；
7. 优化结束后返回带有新 `skill_text` 的 `SkillModule`；
8. Hermes 的辅助代码把新正文与原 frontmatter 重新拼成候选 `SKILL.md`。

### 12.5 三个容易误解的地方

1. `compile()` 不是把 Python 编译成机器码，而是执行 Prompt/程序优化。
2. DSPy Module 不一定是 Agent。它可以只是一次分类调用，也可以组合成 RAG、ReAct 或完整 Agent 工作流。
3. GEPA 不天然保证结果正确。效果取决于评测集、metric、反馈质量、候选执行环境和最终门禁；错误指标会把 Skill 优化到错误方向。

## 十三、补充：经验沉淀何时触发、由谁判断

### 13.1 结论：规则触发审查，LLM 判断是否值得写入

Hermes 当前采用的是两级混合判断：

```text
第一层：代码规则
工具迭代累计达到阈值
        ↓
触发一次后台 Skill Review

第二层：LLM 语义判断
阅读会话，判断是否存在可复用经验
        ↓
create / patch / write_file / Nothing to save
```

因此，“触发经验审查”和“确认沉淀经验”不是同一个决策：

- 是否启动后台审查：主要由确定性计数器决定；
- 是否真的写 Skill、写什么：由后台 Review Agent 根据提示规则进行语义判断；
- 写入是否需要人批准：由 `skills.write_approval` 配置决定；
- 写入内容是否触发危险扫描：由 `skills.guard_agent_created` 配置决定。

### 13.2 代码层的硬触发条件

官方 Codex runtime 文档明确说明，Hermes 为 Skill 使用 `_iters_since_skill` 计数器：

```text
每发生一次工具执行迭代
    → _iters_since_skill += 1

当：
    _iters_since_skill >= _skill_nudge_interval
    且 skill_manage 工具可用
    且任务正常产出 final response
    且任务没有被中断

则：
    _should_review_skills = True
    计数器归零
    用户响应完成后启动后台 review
```

默认 `_skill_nudge_interval` 为 10，可通过以下配置修改：

```yaml
skills:
  creation_nudge_interval: 10
```

设置为 `0` 可以关闭这条定期 Skill review 触发路径。这里统计的是工具迭代，不是用户消息数量。一个用户请求可能触发多次“模型判断—工具调用—读取结果—继续判断”，因而一次复杂任务就可能达到阈值。

官方概念文档写“复杂任务（5+ tool calls）”是提供给模型的经验判断指导；当前运行时代码的后台 nudge 默认阈值是 10。二者用途不同，不应把“5+”误读为当前后台线程唯一的硬编码触发阈值。

当主 Agent 已主动调用 `skill_manage` 保存或更新 Skill 时，相应计数器会重置，避免任务结束后马上再触发一次重复审查。

### 13.3 另一条路径：主 Agent 可主动沉淀

后台计数器不是唯一入口。Hermes 的 system prompt 本身也给主 Agent提供行为指导：

```text
完成复杂任务、修复棘手错误或发现非平凡工作流后，
用 skill_manage 保存方法。

如果使用中的 Skill 已过时、遗漏步骤或内容错误，
立即 patch，而不必等待用户要求。
```

所以主 Agent 在尚未达到后台计数阈值时，也可能直接调用 `skill_manage`。这一步同样主要是 LLM 根据会话语义作出的判断，而不是代码解析出“错误已经解决”后自动写文件。

最终共有两条入口：

```text
路径 A：主 Agent 在正常任务循环中主动判断并调用 skill_manage

路径 B：累计工具迭代达到阈值
      → 后台 Review Agent 被规则唤醒
      → Review Agent 再判断是否调用 skill_manage
```

### 13.4 后台 LLM 判断哪些信号值得沉淀

当前 `_SKILL_REVIEW_PROMPT` 列出的正向信号包括，任意一个都可支持采取行动：

1. 用户纠正了风格、语气、格式、可读性、篇幅或工作方式；
2. 用户纠正了流程、方法或步骤顺序；
3. 任务中出现了可复用的非平凡技术、修复、绕过方案、调试路径或工具使用模式；
4. 本次加载的 Skill 被证明有错误、缺步骤或已经过时；
5. 用户明确要求“记住这种做法”。

Review Agent 的更新优先级是：

```text
1. Patch 本次已经加载的 Skill
2. Patch 现有的同类 umbrella Skill
3. 在现有 Skill 下添加 reference/template/script
4. 实在没有合适归属时，创建新的 class-level Skill
```

这表明判断标准不只是“是否出现新知识”，还包括“这条知识应该落在哪个既有能力类别中”。Hermes 希望形成少量较丰富的类别级 Skill，而不是每个会话生成一个狭窄 Skill。

### 13.5 哪些情况不应沉淀

后台提示明确要求排除：

- 缺少二进制、未安装包、凭据未配置等临时环境状态；
- “某工具坏了”“某功能不能用”等可能很快过时的负面结论；
- 重试后已经消失的一次性错误；
- 只适用于当天任务的叙事或答案；
- 单个 PR 编号、错误字符串或 feature codename；
- 没有形成新方法、没有纠正、顺利完成的普通任务。

例如：

```text
不应保存：
“今天 curl 命令不存在，所以以后不要使用 curl。”

可以保存：
“在最小容器中先检测 curl；缺失时使用 Python urllib，
并在安装被允许时提供安装命令。”
```

前者把临时状态固化成永久禁令；后者沉淀了可复用的检测与恢复流程。

### 13.6 后台 Review Agent 如何运行

当规则阈值命中后，Hermes 在主响应完成后启动后台 fork：

```text
主 Agent 完成用户任务并返回结果
        ↓
复制会话快照
        ↓
启动后台 Review Agent
        ↓
输入 _SKILL_REVIEW_PROMPT
        ↓
只允许 memory / skill-management 等白名单工具
        ↓
写入 Skill，或回答 Nothing to save
```

当前 `background_review.py` 说明该 fork：

- 默认继承主 Agent 的 provider、model、认证和缓存上下文；
- 可配置为使用单独、较便宜的辅助模型；
- 使用与主会话隔离的持久化上下文；
- 工具被限制在 memory 与 Skill 管理白名单；
- 写入直接进入对应的 Memory/Skill store；
- 不阻塞用户正在等待的主响应。

所以最终“值得不值得”的判断仍是概率性的 LLM 判断。代码规则只保证在足够复杂的执行之后安排一次复盘，并不能证明复盘结论正确。

### 13.7 写入还有哪些确定性门禁

LLM 决定调用 `skill_manage` 后，不一定立即生效。用户可配置：

```yaml
skills:
  write_approval: true
  guard_agent_created: true
```

- `write_approval: true`：每次 create/edit/patch/delete/supporting-file 修改先进入 pending，等待用户查看 diff 后批准；
- `guard_agent_created: true`：对凭据收集、明显 prompt injection、外泄指令等危险模式进行扫描并要求批准。

这两项默认均不是“自动保证正确性”的完整评测：

- approval 是人工发布控制；
- guard 是关键词式安全启发；
- 它们都不验证新 Skill 是否能提高任务成功率。

效果验证仍需要离线 eval/GEPA 管线或人工回归。

### 13.8 一个完整触发示例

用户要求修复一个部署失败：

```text
迭代 1：读取部署配置
迭代 2：运行部署命令，证书错误
迭代 3：检查证书链
迭代 4：尝试错误修复，失败
迭代 5：读取代理设置
迭代 6：发现内部代理替换证书
迭代 7：导入组织 CA
迭代 8：重新部署
迭代 9：运行健康检查
迭代 10：验证回滚
```

状态变化：

```text
_iters_since_skill: 9 → 10
_should_review_skills: false → true
主响应：先返回给用户
后台 Review：启动
```

Review Agent 随后进行语义判断：

```text
是否只是一次临时证书错误？
是否发现了以后可复用的企业代理诊断流程？
是否已有 deployment/troubleshooting Skill？
本次路径是否得到部署和健康检查的验证？
```

如果认为具有复用价值，它可能 patch 现有 Skill：

```markdown
When TLS verification suddenly fails only inside the corporate network:
1. Inspect the served certificate chain before disabling verification.
2. Check whether a TLS-intercepting proxy issued the leaf certificate.
3. Import the organization CA into the workload trust store.
4. Re-run deployment and health checks.
5. Never persist `verify=false` as the workaround.
```

如果最终只是服务偶发抖动，重试即恢复，没有形成新方法，则输出 `Nothing to save`。

### 13.9 机制评价

Hermes 采用的是：

```text
规则负责“别忘了复盘”
LLM负责“复盘出什么”
权限/扫描负责“能不能落盘”
离线评测负责“落盘后是否真的更好”
```

优势是实现简单、不会在每一步都额外调用反思模型；不足是“10 次工具迭代”只代表任务可能复杂，不代表一定产生了新知识，而 LLM 的价值判断也可能过度沉淀或遗漏经验。它是一种启发式触发器加语义审查器，不是确定性的知识学习算法。

## 十四、补充：自演进训练代码是否开源

截至 2026-07-30，答案是：**Skill 文本自演进的 Phase 1 原型已经公开，但完整路线图并未全部实现。**

官方公开仓库：

```text
https://github.com/NousResearch/hermes-agent-self-evolution
```

仓库的 `pyproject.toml` 声明：

```toml
[project]
name = "hermes-agent-self-evolution"
version = "0.1.0"
license = {text = "MIT"}
```

已公开的主要代码包括：

```text
evolution/
├── core/
│   ├── config.py
│   ├── dataset_builder.py
│   ├── external_importers.py
│   ├── fitness.py
│   └── constraints.py
└── skills/
    ├── evolve_skill.py
    └── skill_module.py
```

其中可以直接核查：

- 如何读取和拆分 `SKILL.md`；
- 如何把 Skill body 包装成 DSPy `SkillModule`；
- 如何生成 synthetic eval，或导入 golden/session history；
- 如何切分 train/validation/holdout；
- 如何调用 `dspy.GEPA.compile()`；
- GEPA 不可用时如何回退到 `MIPROv2`；
- 如何比较 baseline/evolved；
- 如何输出候选 Skill 和 `metrics.json`；
- 基础大小、增长、非空和结构约束。

官方 README 当前的状态表是：

| 阶段 | 对象 | 状态 |
|---|---|---|
| Phase 1 | `SKILL.md` | Implemented |
| Phase 2 | 工具描述 | Planned |
| Phase 3 | System prompt | Planned |
| Phase 4 | 工具实现代码 | Planned |
| Phase 5 | 持续自动改进循环 | Planned |

这里的“训练”不是模型训练。公开代码通过模型 API 生成、评测和选择文本候选，不包含梯度更新、LoRA、RL 或权重训练。更准确的名称是“离线 Prompt/Skill 优化”。

开源范围也需要谨慎理解：

1. Phase 1 是可阅读、可运行的研究原型；
2. README/PLAN 描述的完整 pytest、benchmark、语义保持和自动 PR 门禁，并未全部接入当前主脚本；
3. 当前实际传给 GEPA 的 fitness 仍主要是关键词重合启发式，而不是文件中定义的完整 LLM judge；
4. `--run-tests` 参数虽然存在，当前主流程没有调用 `run_test_suite()`；
5. 因此不能把仓库等同于已经生产验证的完整自治训练平台。

此外，Hermes 主仓库也公开了在线经验沉淀代码，包括后台 Review Agent、Skill 触发计数器和 `skill_manage` 写入路径。这部分属于运行时自我改进，不是 DSPy+GEPA 离线搜索。

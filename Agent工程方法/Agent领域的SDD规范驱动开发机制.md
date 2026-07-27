# Agent 领域的 SDD：规范驱动开发机制

> 核查日期：2026-07-22  
> 术语说明：本文的 SDD 指当前 Coding Agent 领域最常见的 **Specification-Driven Development（规范驱动开发）**。Schema-Driven Development 和 Skill-Driven Development 也偶尔缩写为 SDD，但不是本文主线。事实依据优先采用 GitHub Spec Kit 和 Kiro 官方资料；“工程建议”部分为自拟分析。

## 一、SDD 是什么

传统 AI 编程常采用：

```text
一句需求 → Agent 直接改代码 → 人不断补充提示 → 测试和返工
```

SDD 将过程改成：

```text
用户意图
  ↓
可审阅的需求规范
  ↓
技术设计
  ↓
有依赖和验收标准的任务
  ↓
Agent 分步实现
  ↓
根据规范验证代码
```

其核心不是文档数量，而是把规范提升为开发的权威输入：代码不再仅由临时对话驱动，而是规范及其派生计划的实现结果。GitHub Spec Kit 将其概括为以 specification 为 AI 辅助软件开发中心，核心流程为 `Spec → Plan → Tasks → Implement`，每个阶段产生 Markdown artifact，作为下一阶段的结构化上下文。[GitHub Spec Kit 官方文档](https://github.github.io/spec-kit/)；[SDD 原理说明](https://github.com/github/spec-kit/blob/main/spec-driven.md)

## 二、SDD 为什么在 Agent 时代变得重要

人类开发者面对模糊需求，通常会主动询问、理解现有系统、权衡架构并补齐边界。Coding Agent 如果直接收到一句自然语言任务，很容易：

- 对模糊点自行作出未经确认的假设；
- 只满足表面 happy path；
- 修改超出用户期望的范围；
- 忘记非功能要求和兼容性约束；
- 长任务中因上下文变化偏离最初目标；
- 代码写完后才发现双方对“完成”的定义不同。

SDD 的作用是把不稳定的聊天上下文转换成稳定的仓库制品，并在实现前暴露歧义。它同时解决三类 Agent 问题：

| Agent 问题 | SDD 对策 |
|---|---|
| 意图不明确 | requirements + acceptance criteria |
| 长任务漂移 | 持久化 spec/design/tasks，阶段间重新加载 |
| 无法证明完成 | 每项任务和测试追踪到需求 |

## 三、核心制品

不同框架命名略有区别，但通常包含四层。

### 1. Constitution / Steering

项目级长期规则，例如：

- 架构原则；
- 安全和隐私约束；
- 技术栈；
- 测试政策；
- 代码风格；
- 禁止事项；
- 决策优先级。

它约束所有 feature spec，不应混进单次功能需求。GitHub Spec Kit 提供 constitution 阶段；Kiro 使用 steering files 表达长期项目规则。

### 2. Requirements

描述“系统必须做什么”，不急于规定“如何实现”。应包含：

- actor / user story；
- 功能行为；
- 输入输出；
- 前置条件；
- 异常与边缘情况；
- 非功能要求；
- 明确排除范围；
- 可验证 acceptance criteria。

Kiro 的 requirements-first 流程可用 EARS 风格表达行为，例如 `WHEN ... THE SYSTEM SHALL ...`。[Kiro Requirements-First 官方文档](https://kiro.dev/docs/specs/feature-specs/requirements-first/)

### 3. Design

把需求转化为技术方案：

- 现有代码和约束分析；
- 组件边界；
- 数据模型；
- API/接口契约；
- 数据流和状态变化；
- 错误处理；
- 安全模型；
- 迁移与兼容策略；
- 测试策略；
- 关键技术决策及理由。

设计必须能追踪到需求，不能凭空加入用户没有要求的产品功能。

### 4. Tasks

把设计拆成 Agent 可独立执行和验证的任务：

- 每项任务范围有限；
- 明确输入、输出和依赖；
- 指向相关 requirement/design；
- 包含验证方法；
- 有合理执行顺序；
- 可区分 required 与 optional。

## 四、完整 Agentic SDD 流程

GitHub Spec Kit 当前完整命令链为：[Agentic SDD 官方参考](https://github.github.io/spec-kit/reference/agentic-sdd.html)

```text
constitution
  ↓
specify
  ↓
clarify
  ↓
plan
  ↓
checklist
  ↓
tasks
  ↓
analyze
  ↓
implement
  ↓
converge
```

### Constitution

建立项目不可轻易违反的原则，为后续决策提供最高级约束。

### Specify

从用户意图生成 feature specification，回答“做什么、为什么、什么算完成”。

### Clarify

定位会实质影响方案的模糊点，让用户或领域负责人决策，而不是让 Agent 静默猜测。

### Plan

读取代码库、技术约束和规范，产生可落地技术设计。

### Checklist

检查需求是否完整、明确、一致、可验证。它检查的是规范质量，而不是代码质量。

### Tasks

生成按依赖排序的执行单元，并建立 requirement → design → task 的追踪关系。

### Analyze

在写代码前做跨制品一致性分析，例如：

- 某项需求是否没有对应任务；
- 某项任务是否没有需求来源；
- design 是否违反 constitution；
- 两项需求是否冲突；
- 验收标准是否无法测试。

### Implement

Agent 按任务执行，每完成一项就运行对应验证，并更新任务状态。

### Converge

检查实现、测试、规范和剩余任务是否真正收敛，避免“代码已写完”被误判为“需求已完成”。

## 五、SDD 的关键机制不是瀑布，而是受控反馈环

SDD 容易被误解为先写完所有文档再一次性编码。更准确的结构是：

```text
需求 ←──────────────┐
 ↓                  │
设计 ←──── 技术不可行│
 ↓                  │
任务 ←──── 拆分不合理│
 ↓                  │
实现 ──── 发现新事实│
 ↓                  │
验证 ──── 行为不符合┘
```

但反馈不能只留在聊天记录里。若实现发现规范有误，应先更新对应规范和下游制品，再继续编码，保持权威状态一致。

Kiro 官方也允许 requirements-first、design-first、bugfix 和 quick plan 等不同入口；修改需求后可重新派生设计和任务。这说明 SDD 是带阶段约束的迭代流程，而非固定单向瀑布。[Kiro Specs](https://kiro.dev/docs/web/specs/)；[Kiro Design-first/Bugfix](https://kiro.dev/blog/specs-bugfix-and-design-first/)

## 六、规范如何变成“可执行规范”

仅有自然语言文档仍可能含糊。成熟 SDD 会逐步把需求编译成机器可验证制品：

```text
自然语言意图
 → 结构化需求
 → acceptance criteria
 → API/schema/invariant
 → example tests / property tests
 → CI gate
```

例如需求：

```text
任何时刻，同一用户最多只能有一个有效的密码重置令牌。
```

可以派生为：

- 数据库唯一性约束；
- 创建新令牌时撤销旧令牌的设计；
- 并发请求测试；
- property：对任意操作序列，有效令牌数始终 `<= 1`。

Kiro 将从需求提取可测试 property、生成随机化测试来验证实现称为 executable specification。[Kiro Property-Based Testing](https://kiro.dev/blog/property-based-testing/)

## 七、一个完整案例：密码重置功能

以下为基于 SDD 机制整理的自拟案例，不代表 GitHub 或 Kiro 的内部模板。

### 用户原始诉求

> 给现有账户系统增加“忘记密码”。用户输入邮箱后收到重置链接，安全地修改密码。

直接编码会留下大量未知项：是否暴露邮箱存在、链接多久失效、能否重复使用、旧会话是否失效、邮件失败怎么办。

### 第一阶段：Specification

```markdown
# Password Reset Specification

## Goal
允许忘记密码的用户通过已验证邮箱安全重置密码，同时不泄露账户是否存在。

## Functional Requirements

R1. 用户提交任意格式合法的邮箱后，接口返回相同的通用响应。
R2. 若账户存在，系统生成一次性重置令牌并发送链接。
R3. 令牌在 30 分钟后失效。
R4. 创建新令牌时，同一用户以前的未使用令牌全部失效。
R5. 成功使用后，令牌不可再次使用。
R6. 新密码必须满足现有密码策略。
R7. 成功重置后，撤销该用户已有登录会话。

## Non-functional Requirements

R8. 请求接口按 IP 和账户维度限流。
R9. 日志不得记录原始令牌、新密码或完整邮箱。

## Out of Scope

- 修改用户邮箱；
- 短信重置；
- 管理员代重置。

## Acceptance Criteria

AC1. 存在和不存在的邮箱获得相同 HTTP 状态和响应结构。
AC2. 过期、已使用、被替换的令牌均不能修改密码。
AC3. 并发创建多个令牌后，最多一个令牌有效。
AC4. 成功重置后，旧会话无法继续访问受保护资源。
```

### 第二阶段：Clarification

Agent 提出会改变设计的短问题：

1. 所有设备会话都撤销，还是保留当前设备？
2. 邮件发送失败时是否重试？
3. 令牌采用数据库保存的随机值，还是自包含签名 token？

用户决定：撤销全部会话；邮件最多异步重试三次；数据库只保存随机令牌的 hash。

### 第三阶段：Design

```markdown
## Components

- POST /password-reset/request
- POST /password-reset/confirm
- password_reset_tokens table
- PasswordResetService
- MailQueue
- SessionRevocationService

## Data Model

password_reset_tokens:
- id
- user_id
- token_hash
- created_at
- expires_at
- used_at
- invalidated_at

## State Transition

ISSUED → USED
ISSUED → EXPIRED
ISSUED → INVALIDATED

终态不可返回 ISSUED。

## Security

- 使用密码学安全随机 token；
- 数据库只保存 hash；
- 通用响应防账户枚举；
- 限流；
- 日志脱敏；
- 成功后撤销全部 session。
```

### 第四阶段：Tasks

| 任务 | 依赖 | 对应需求 | 验证 |
|---|---|---|---|
| T1 新增 token 表和约束 | 无 | R3–R5 | migration test |
| T2 实现 token 生命周期服务 | T1 | R2–R5 | unit + property tests |
| T3 实现 request API | T2 | R1、R2、R8 | API tests |
| T4 接入异步邮件 | T2 | R2 | queue integration test |
| T5 实现 confirm API | T2 | R3、R5、R6 | API tests |
| T6 撤销用户会话 | T5 | R7 | integration test |
| T7 日志和限流审查 | T3、T5 | R8、R9 | security tests |
| T8 端到端回归 | T1–T7 | AC1–AC4 | E2E suite |

### 第五阶段：跨制品 Analyze

分析发现：设计中尚未说明“邮件任务重试时是否重复生成令牌”。修正规范和设计：重试复用同一个未过期 token 对应的邮件 payload，不创建新 token。

这一步体现 SDD 的价值：问题在写代码之前暴露。

### 第六阶段：Implementation

Agent 每次只执行一个任务：

```text
读取 T2 + R2~R5 + token design
 → 实现生命周期服务
 → 运行单元测试和 property tests
 → 保存结果
 → 标记 T2 完成
```

### 第七阶段：验证和验收

| 验收项 | 证据 | 结果 |
|---|---|---|
| 账户不可枚举 | 存在/不存在邮箱响应快照 | 通过 |
| 令牌一次性 | 重复 confirm 测试 | 通过 |
| 令牌过期 | 时钟模拟测试 | 通过 |
| 并发唯一有效 | property/concurrency test | 通过 |
| 会话撤销 | E2E 登录会话测试 | 通过 |
| 日志无敏感字段 | 日志捕获测试 | 通过 |

验收结论必须是“所有 acceptance criteria 有对应证据”，而不是“Agent 表示已经完成”。

## 八、SDD 与 TDD、BDD、Plan Mode 的关系

| 方法 | 主要回答 | 制品 |
|---|---|---|
| SDD | 要构建什么、如何设计、如何追踪完成 | spec/design/tasks/tests |
| TDD | 单元行为如何通过测试驱动实现 | failing/passing tests |
| BDD | 业务行为在场景中如何表现 | Given/When/Then scenarios |
| Plan Mode | 当前 Agent 准备按什么步骤执行 | 会话级计划 |
| ADR | 为什么选择某项架构决策 | architecture decision record |

它们并不冲突：SDD 可以生成 BDD 场景和 TDD 测试；ADR 可以成为 design 的依据；Plan Mode 可以执行某一份 tasks，但会话计划通常没有 SDD 制品那样完整的需求追踪和长期权威性。

## 九、SDD 与 Skill、AGENTS.md、Agent Trace 的关系

### SDD 与 Skill

Skill 定义“Agent 应如何执行一类工作”，Specification 定义“这个具体功能必须满足什么”。例如：

```text
SDD Skill：规定 specify/clarify/plan/tasks/implement 流程
具体 Spec：记录 password-reset 功能的需求和设计
```

Skill 是可复用方法，Spec 是某个任务的权威状态。

### SDD 与 AGENTS.md

`AGENTS.md` 适合保存仓库级长期约定；Spec 适合保存单项变更的需求和设计。不要把具体 feature requirement 永久塞进全局 Agent 指令。

### SDD 与 Agent Trace

Spec 描述应当发生什么，Trace 记录实际发生了什么：

```text
Spec → expected behavior
Trace → observed behavior
Diff  → 失败归因和改进依据
```

二者结合后，可以判断是规范错误、计划遗漏、Agent 未遵循任务，还是实现/工具失败。

## 十、主流实现

### GitHub Spec Kit

- 开源、Agent 无关；
- 支持 Codex、Claude、Copilot、Gemini、Kiro 等多种集成；
- 通过命令、模板和 Markdown 制品组织流程；
- 提供 clarify、checklist、analyze、converge 等质量门；
- 适合把 SDD 引入现有仓库。[GitHub Spec Kit](https://github.github.io/spec-kit/)

### Kiro Specs

- IDE、CLI、Web 原生支持；
- 主要产物为 `requirements.md`、`design.md`、`tasks.md`；
- 支持 feature、bugfix、quick plan；
- 支持 requirements-first 和 design-first；
- 任务执行之间进行验证；
- 强调从需求生成 property-based tests。[Kiro Specs](https://kiro.dev/docs/web/specs/)；[Kiro CLI Specs](https://kiro.dev/docs/cli/v3/specs/)

### 学术扩展：Spec Kit Agents

2026 年论文 *Spec Kit Agents* 指出，大型、持续变化的代码库中，即使有 SDD，Agent 仍可能因缺少实时仓库上下文而虚构 API 或违反架构；其方案在不同阶段加入 context-grounding hooks，并区分 PM/Developer 角色。[Spec Kit Agents 论文](https://arxiv.org/abs/2604.05278)

这说明 Spec 不是代码库事实的替代物。Agent 在 plan 和 implementation 阶段仍必须重新检查当前代码、依赖、API 和测试。

## 十一、优点

- 在成本最低的阶段发现需求歧义；
- 减少长任务中的目标漂移；
- 让多人和多个 Agent 共享同一组显式约束；
- 需求、设计、任务、测试之间可追踪；
- 便于审计为什么产生某项代码；
- 支持任务级审批和并行实施；
- 对跨会话、跨 Agent 的工作更稳定；
- 能将自然语言意图逐步编译成自动验收。

## 十二、局限和常见失败

### 1. Spec 自身可能错误

Agent 生成的规范不天然正确。若人类未经审阅就批准，SDD 只会让错误需求被更系统地实现。

### 2. 文档与代码仍会漂移

如果紧急修改只改代码不更新 Spec，source of truth 会失真。必须在 PR/CI 中检查需求、实现和测试的一致性。

### 3. 仪式和 token 开销

小修复使用完整九阶段流程可能得不偿失。应根据风险选择精度：

- 小而明确：quick spec；
- 普通功能：spec → plan → tasks；
- 高风险/跨系统：完整 clarify/checklist/analyze/converge。

### 4. 伪精确

文档结构完整不代表需求真实完整。大量模板化字段可能掩盖关键业务未知项。

### 5. 上下文失真

若设计只读 Spec 不检查真实代码，可能基于不存在的接口规划。Brownfield 项目必须在各阶段进行代码库 grounding。

### 6. 过度再生成

把每次规范调整都视为“重新生成所有代码”风险很大。现实项目更适合 spec-anchored：规范控制变化，代码以增量 diff 演进。

## 十三、三种严格程度

学术分析常把 SDD 分成类似三个等级：[Spec-Driven Development: From Code to Contract](https://arxiv.org/abs/2602.00180)

| 等级 | 规范角色 | 适用场景 |
|---|---|---|
| Spec-first | 实现前先建立规范 | 普通新功能 |
| Spec-anchored | 规范持续约束和校验代码演进 | 现有长期项目 |
| Spec-as-source | 规范可生成或再生成实现 | DSL、API client、基础设施等高度声明式系统 |

大多数团队适合 spec-anchored，而不是把所有手写代码都降为可丢弃的生成物。

## 十四、工程建议：最小可用 SDD

以下为自拟方案。

对普通 Coding Agent，不需要一开始引入完整平台。仓库中建立：

```text
specs/
└── 001-password-reset/
    ├── requirements.md
    ├── design.md
    ├── tasks.md
    └── acceptance.md
```

最低规则：

1. 写代码前必须存在可测试 acceptance criteria；
2. design 中每个关键组件指向 requirement；
3. task 同时指向 requirement 和验证命令；
4. Agent 每次只完成一个或一组低耦合任务；
5. 发现需求变化时先更新 Spec，再更新代码；
6. 完成声明必须附测试、diff 或运行证据；
7. PR 同时审查 Spec 和实现；
8. 规范中不要保存密钥、个人数据或未经核实的事实。

## 十五、与另外两个 SDD 的区别

### Schema-Driven Development

以 JSON Schema、OpenAPI、Protobuf 或数据库 schema 为中心生成代码、校验器和接口。它可作为 Specification-Driven Development 的一个形式化组成部分，但范围更窄。

### Skill-Driven Development

以 Agent Skill 作为开发方法或能力模块，让 Agent 按 Skill 工作流执行。这一名称尚未像 Specification-Driven Development 那样形成统一主流定义。Skill 可以承载 SDD 流程，但不能替代具体功能规范。

## 十六、最终判断

Agent 领域的 SDD 本质上是一种**面向 Agent 的意图编译和控制机制**：

```text
人类意图
 → 可审阅需求
 → 可追踪设计
 → 可执行任务
 → 可验证实现
```

它最重要的价值不是让 Agent 写更多文档，而是把容易丢失、模糊和漂移的自然语言意图，转化为跨会话、跨 Agent、可检查的持久约束。对大型或高风险任务，SDD 是连接 Agent 规划、执行、测试、Trace 和审计的控制平面；对小任务，则应采用精简版本，避免流程成本超过收益。

## 十七、SDD 如何保证 Agent 执行完整流程

### 先明确证据边界

SDD 方法本身不能仅凭 Markdown 或 Prompt 保证 Agent 一定遵循完整流程。实际可靠性来自多层机制叠加：

```text
Agent 指令与模板（软约束）
        ↓
制品前置条件（结构门禁）
        ↓
工作流状态机和审批（阶段门禁）
        ↓
任务依赖调度（执行顺序）
        ↓
测试、Hook、CI（确定性门禁）
        ↓
人工审批与发布策略（治理门禁）
```

只有最后几层能提供较强的确定性。模型仍可能误解规范或产出错误内容，所以“走完流程”和“结果正确”是两个不同问题。

### 第一层：专用命令、Skill 和模板引导 Agent

Spec Kit 初始化后，为具体 Coding Agent 安装 `/speckit.*` 命令或对应 Skill。每个命令定义：

- 当前阶段的角色和目标；
- 必须读取哪些上游文件；
- 允许创建或修改哪些文件；
- 输出模板；
- 下一步是什么；
- 该阶段不应该做什么。

例如 `specify` 只处理 what/why，`plan` 处理技术方案，`tasks` 生成执行拆分，`implement` 消费任务。这能显著降低 Agent 跳步概率，但本质仍是模型遵循指令的概率性约束。

### 第二层：文件制品形成前置条件

每个阶段必须产生可检查的持久文件：

```text
spec.md / requirements.md
        ↓
plan.md / design.md
        ↓
tasks.md
        ↓
implementation
```

下游命令运行前检查上游文件是否存在。例如 Kiro CLI 官方说明，`/spec run <name>` 会验证 `tasks.md` 已存在，才启动自主执行。[Kiro CLI Specs](https://kiro.dev/docs/cli/v3/specs/)

Spec Kit 安装 Bash 或 PowerShell 脚本，并在相关命令中调用 prerequisite check。文件存在性、目录、Git feature 分支和必要制品可由普通程序检查，不依赖模型自行记忆。[Spec Kit 安装说明](https://github.com/github/spec-kit/blob/main/docs/installation.md)

但“文件存在”只证明阶段留下了产物，不证明内容合格。空洞的 `design.md` 仍可能通过存在性检查，因此还需要内容质量门禁。

### 第三层：工作流状态和人工审批

产品可以把阶段做成状态机：

```text
DRAFT_REQUIREMENTS
  → REQUIREMENTS_APPROVED
  → DESIGN_APPROVED
  → TASKS_APPROVED
  → IMPLEMENTING
  → VERIFYING
  → COMPLETE
```

界面只有满足前一状态后才开放下一操作。Kiro 的标准 Feature Spec 适合在 requirements、design、tasks 之间加入显式审阅点；官方将 Quick Plan 描述为不经过这些阶段审批门的快速模式，反过来也说明是否“硬等人确认”取决于所选模式。[Kiro Specs](https://kiro.dev/docs/web/specs/)；[Kiro Best Practices](https://kiro.dev/docs/specs/best-practices/)

因此：

- 标准模式：适合高歧义或合规任务，使用人工审批；
- Quick Plan：一次生成三个制品，流程更快，但保障较弱；
- 完全自动模式：必须由机器 grader/CI 替代人工阶段批准。

### 第四层：依赖图控制任务执行顺序

`tasks.md` 不应只是自由文本列表，而要包含：

- task ID；
- 依赖任务；
- 并行标记；
- 对应需求；
- 完成条件；
- 验证命令。

执行器根据依赖构建 DAG：

```text
Wave 1：无依赖任务，并行执行
Wave 2：依赖 Wave 1 且前置已通过的任务
Wave N：所有依赖满足后才执行
```

Kiro 官方说明，Run all Tasks 会分析依赖，将独立任务分 wave 并行；wave 之间顺序执行。[Kiro Specs](https://kiro.dev/docs/specs/)

Spec Kit 的 `implement` 则按 `tasks.md` 的依赖阶段和 parallel marker 执行。[Spec Kit Agentic SDD](https://github.github.io/spec-kit/reference/agentic-sdd.html)

这可以防止“API 尚未建立就运行依赖它的集成任务”，但前提是任务依赖本身定义正确。

### 第五层：Checklist 和跨制品一致性检查

完整 SDD 在编码前检查：

```text
Requirement 是否明确、无冲突、可测试？
每个 Requirement 是否有 Design 覆盖？
每个 Design 是否有 Task 落地？
每个 Task 是否有需求来源？
每个 Acceptance Criterion 是否有 Validator？
```

Spec Kit 的 `checklist` 用于检查规范质量；`analyze` 跨 spec、plan、tasks 查找遗漏和矛盾。官方明确说明 `analyze` 不修改文件，只产生报告和可选修复建议，问题仍需返回负责的上游阶段修复后重新运行。[Spec Kit Agentic SDD](https://github.github.io/spec-kit/reference/agentic-sdd.html)

所以默认的 `analyze` 是质量检测器，不是硬阻断器。若要保证其执行，必须在外层脚本或 CI 中规定：

```text
analyze 发现 HIGH/CRITICAL 问题 → 禁止 implement
```

### 第六层：每项任务后的确定性验证

执行任务时，不能让模型自行宣布完成。任务完成状态应由验证结果驱动：

```text
Agent 修改代码
  ↓
运行 task.validator
  ├─ exit 0 / assertions pass → task VERIFIED
  └─ failure → task FAILED，不解锁下游任务
```

验证器包括：

- 编译和类型检查；
- unit/integration/E2E tests；
- schema validator；
- property-based tests；
- lint/security scan；
- 文件、API、数据库状态断言；
- UI screenshot 或浏览器流程验收。

Kiro CLI 将执行描述为 tasks 顺序执行并在任务之间验证；Kiro 也从规范提取 property-based test 来检查实现是否满足需求。[Kiro CLI Specs](https://kiro.dev/docs/cli/v3/specs/)；[Kiro Property-Based Testing](https://kiro.dev/blog/property-based-testing/)

### 第七层：Converge 和完成证明

所有任务被勾选仍不能证明功能完成。最终需要聚合检查：

```text
所有 required tasks 已 VERIFIED
所有 acceptance criteria 有对应证据
没有未解决的高优先级 analyze 问题
完整回归集通过
实现 diff 没有越出 spec scope
```

Spec Kit 的 `converge` 用于检查实现是否满足 spec、plan 和 tasks；无缺口时报告 converged。[Spec Kit Agentic SDD](https://github.github.io/spec-kit/reference/agentic-sdd.html)

但若组织不要求发布前运行 converge，它仍可能被跳过。真正的强制方式是将收敛报告或等价 CI job 设为合并必需检查。

### 第八层：Hook、权限和 CI 防止绕过

如果 Agent 可以绕过 `/speckit.implement` 直接编辑代码，那么仅靠 SDD 命令无法保证完整流程。需要在执行层增加策略，例如：

```text
PreEdit Hook：没有 APPROVED spec 时拒绝修改 src/
PreCommand Hook：未到 IMPLEMENTING 状态时拒绝部署
PostEdit Hook：自动运行对应 validator
CI：缺少 requirement-task-test traceability 时失败
Branch Protection：SDD 验证 job 未通过禁止合并
```

这些属于自拟工程强化方案，不是所有 Spec Kit/Kiro 项目的默认行为。它们把流程从“推荐路径”提升为“无法轻易绕过的策略”。

## 十八、不同机制的保证强度

| 机制 | 能保证什么 | 不能保证什么 | 强度 |
|---|---|---|---|
| Prompt/Skill | 告诉 Agent 应怎样做 | Agent 一定遵循、内容一定正确 | 软 |
| 模板 | 输出字段相对完整 | 字段内容真实充分 | 软—中 |
| 文件前置检查 | 上游制品存在 | 制品质量 | 中 |
| UI/状态机审批 | 阶段不能随意前进 | 审批者判断正确 | 中—强 |
| Task DAG | 依赖顺序正确执行 | 依赖定义正确 | 强 |
| Validator/Test | 可自动验证的性质成立 | 未编码进测试的需求 | 强 |
| Hook/Permission | 禁止某类越权行为 | 所有语义错误 | 强 |
| CI/Branch protection | 未达门槛不能合并 | 部署后所有行为正确 | 强 |
| 人工审查 | 处理语义和业务判断 | 绝对无遗漏 | 中—强 |

## 十九、一个可真正强制的最小 SDD 状态机（自拟方案）

```json
{
  "feature_id": "001-password-reset",
  "state": "TASKS_APPROVED",
  "artifacts": {
    "requirements": {"status": "approved", "hash": "sha256:..."},
    "design": {"status": "approved", "hash": "sha256:..."},
    "tasks": {"status": "approved", "hash": "sha256:..."}
  },
  "quality_gates": {
    "cross_artifact_analysis": "passed",
    "critical_findings": 0
  }
}
```

允许的转换：

```text
requirements approved → 才能生成 design
design approved       → 才能生成 tasks
tasks approved        → 才允许修改实现目录
task validator passed → 才能标记 task complete
all AC passed         → 才能进入 COMPLETE
```

伪代码：

```python
def authorize(action, state):
    if action == "edit_source":
        return state.phase == "IMPLEMENTING" and state.tasks_approved
    if action == "complete_task":
        return state.current_task.validator_passed
    if action == "merge":
        return (
            state.all_required_tasks_verified
            and state.all_acceptance_criteria_passed
            and state.critical_findings == 0
        )
    return False
```

状态由编排器、Hook 或 CI 更新，而不是让 LLM 通过自然语言自行声明。

## 二十、最终回答：SDD 的保证来自哪里

SDD 对完整流程的保证可以概括为：

```text
规范负责定义正确路径
制品依赖负责保存阶段状态
状态机负责限制阶段转换
任务 DAG 负责执行顺序
Validator 负责判定每步完成
Hook/CI 负责防止绕过
人工审批负责语义和风险决策
```

GitHub Spec Kit 默认更接近“结构化 Agent harness”：它提供命令、模板、前置检查和质量分析，但一些质量步骤仍可被用户跳过。Kiro 将其中更多部分产品化为 Spec agent、审批界面、任务依赖调度和任务间验证。若需要合规级“必须完整执行”，还应在外层加入确定性状态机、Hook、CI required checks 和分支保护，不能只依赖模型遵循 Prompt。

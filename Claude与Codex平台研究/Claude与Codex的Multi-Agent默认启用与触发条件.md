# Claude 与 Codex 的 Multi-Agent 默认启用与触发条件

> 核对日期：2026-07-16  
> 范围：Claude Code、Codex 当前官方产品机制。这里的“默认启用”区分为：**multi-agent 能力是否默认可用**，以及**一次普通任务是否默认实际创建多个 agent**。

## 结论

不能笼统地说 Claude 和 Codex 都“默认以 multi-agent 运行”。更准确的说法是：

- **Codex：multi-agent/subagent 能力默认开启，但普通任务不会因此必然创建 subagent。** 当前官方配置参考把 `features.multi_agent` 标为 stable、on by default；官方 Subagents 文档同时说明，本地 Codex 通常在用户直接要求，或适用的 `AGENTS.md` / skill 指令要求委派时，才创建 subagent。
- **Claude Code subagents：能力内置，Claude 会在匹配任务时按需自动委派，也可以由用户显式调用。** 这不代表每个任务都会使用多个 agent。
- **Claude Code Agent Teams：默认关闭。** 这是比 subagents 更完整的多 Agent 团队机制，具有独立 Claude Code 实例、共享任务表和 teammate 直接通信；当前仍属 experimental，必须显式设置 `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`，启用后再通过自然语言要求 Claude 创建 teammates。

## 触发条件

### Codex

本地 Codex 当前会在以下条件下创建 subagent：

1. 用户直接要求，例如“spawn two agents”“并行委派”“每一点使用一个 agent”。
2. 当前任务范围内适用的 `AGENTS.md` 明确要求 delegation / parallel agent work。
3. 当前使用的 skill 指令明确要求 delegation。

适合触发的任务通常可以独立拆分并行，尤其是代码库探索、测试、分类审查、日志分析和总结。并行写入同一代码区域会增加冲突和协调成本，不宜仅因 multi-agent 工具可用就自动拆分。

需区分 ChatGPT Work：官方文档称，大多数 intelligence level 需要用户显式要求 delegation；Ultra 可在并行 agent 能显著提升速度或质量时主动委派。这一条不能直接外推成所有 Codex 客户端都会主动委派。

### Claude Code subagents

Claude Code 包含 Explore、Plan、general-purpose 等内置 subagent，也支持自定义 subagent。触发方式包括：

1. Claude 遇到与 subagent 描述匹配的任务时自动委派。
2. 用户在自然语言中指定某个 subagent；Claude决定是否委派。
3. 用户用 `@` mention 指定 subagent，可保证该 subagent 对该任务运行。
4. 用 `--agent` 或 `agent` 设置让整个 session 采用指定 agent 配置；这属于主会话角色切换，不等同于同时创建多个 agent。

典型场景是把会污染主上下文的搜索结果、日志、测试输出或文件内容放进隔离上下文；也适合专门化工具权限、模型与系统提示。

### Claude Code Agent Teams

必须先设置：

```json
{
  "env": {
    "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"
  }
}
```

然后在提示中描述任务以及希望创建的 teammates。官方建议把它用于并行探索确有价值、成员能够相对独立工作的任务，例如：多路研究与审查、互相竞争的调试假设、彼此分离的新模块，以及前端/后端/测试分层协作。

对于顺序依赖明显、多人要修改同一文件、或需要频繁同步的任务，单 session 或普通 subagents 更合适。Agent Teams 的 token 和协调成本显著更高。

## 概念边界

| 机制 | 默认状态 | 是否每次任务自动创建多个 Agent | 协作结构 |
|---|---|---|---|
| Codex subagents | 能力默认开启 | 否；本地 Codex当前依赖显式请求或项目/skill 指令 | 主 agent 分派，收集子线程结果 |
| Claude Code subagents | 内置可用 | 否；只在任务匹配或显式调用时使用 | subagent 独立上下文，结果返回调用者 |
| Claude Code Agent Teams | 默认关闭、实验性 | 否；需先开启，再要求创建 teammates | lead + 独立 teammates + 共享任务表 + 直接通信 |
| Codex App 多线程并行 | 产品界面支持 | 用户通常创建/委派多个任务 | 独立 threads/worktrees；不等同于单任务内部必然自动分叉 |

## 官方来源

- OpenAI, [Codex Configuration Reference](https://learn.chatgpt.com/docs/config-file/config-reference)：`features.multi_agent` 为 stable、on by default，并列出 multi-agent collaboration tools。
- OpenAI, [Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)：本地 Codex 的默认可用性、显式请求/`AGENTS.md`/skill 触发条件、适用任务与 token 成本。
- OpenAI, [Introducing the Codex app](https://openai.com/index/introducing-the-codex-app/)：Codex App 用独立线程和 worktree 管理多个 agent 并行工作。
- Anthropic, [Create custom subagents](https://code.claude.com/docs/en/sub-agents)：内置 subagents、自动委派、显式调用、隔离上下文和适用场景。
- Anthropic, [Orchestrate teams of Claude Code sessions](https://code.claude.com/docs/en/agent-teams)：Agent Teams 默认关闭、实验状态、启用变量、触发方式、推荐场景及与 subagents 的区别。

## 证据边界

以上只描述官方公开的产品行为。官方文档说明了可见的触发规则和配置，但没有公开模型内部如何计算“是否值得委派”的具体阈值或决策算法；不能把任务规模、token 数或文件数量臆测成固定的内部触发阈值。

## 补充：Claude Code 内置 subagent 的路由条件

### 总体决策输入

Anthropic 官方公开的自动委派依据只有三个层面：用户请求中的任务描述、subagent 配置的 `description`、当前上下文。官方没有公布固定评分、文件数、token 数或复杂度阈值，因此只能描述功能性路由边界，不能声称存在确定的 if/else 算法。

### Explore

Claude 在“需要搜索或理解代码库，但不需要修改”时委派给 Explore。Explore 是只读 agent，目标是文件发现、代码搜索与代码库探索。Claude 调用时还会给出 `quick`、`medium` 或 `very thorough` 的检索深度。

“检索文档”并不必然等于 Explore：

- 搜索仓库内的 Markdown、源码注释或本地文档，本质上是代码库/文件探索，符合 Explore 的职责。
- 从网站、MCP 或外部资料源抓取文档，官方只把它列为适合隔离的高输出操作；并未规定必须由内置 Explore 执行。实际是否用 Explore 还受可用工具与当前上下文影响。

### Plan

只有在 Plan Mode 中，且 Claude 为形成计划需要理解代码库时，才委派给 Plan subagent。它同样只读，但语义目标是“为计划收集代码库上下文”，不是通用文件搜索。Plan subagent 的结果供主线程形成计划。

### general-purpose

任务需要探索加修改、需要解释探索结果的复杂推理，或包含多个相互依赖步骤时，Claude 会委派给 general-purpose。它有全部工具，更适合可以采取行动的复杂子任务。

### 是否并行调用多个 Explore

机制上可以并行创建多个 subagent。官方给出的 parallel research 模式是：把互不依赖的研究方向交给多个 subagent 同时执行，完成后由 Claude 汇总。因此，多个独立的代码库区域或研究问题可以分别由多个 Explore 实例并行处理。

但官方没有说“一次文档检索会默认自动创建多个 Explore”，也没有公开自动决定数量的规则。是否多开取决于任务能否自然拆成独立调查路径、用户是否要求并行，以及 Claude 基于任务描述与上下文作出的工具调用选择。若要确定性地并行，应在提示中明确写出拆分维度和 agent 数量。

另外，Claude Code v2.1.198 起 subagent 默认在后台运行；若主线程必须先拿到结果才能继续，Claude 会改为前台运行。后台运行意味着可并发，不等于 Claude 一定会为同一个检索自动创建多个实例。

## 补充：Plan 结果与 TODO / Task List 的关系

Plan Mode 完成后，Claude 会通过 `ExitPlanMode` 向用户呈现一份计划并请求批准。计划通常会采用步骤、清单或分阶段结构，但官方没有规定它必须输出某种固定的 TODO schema。

需要区分两个对象：

1. **Proposed plan**：面向用户审阅的实施方案。用户可以批准并切换到执行模式、继续反馈修改，或用 `Ctrl+G` 在编辑器中直接编辑计划。
2. **Task list**：Claude Code 用于执行期进度跟踪的结构化任务表，状态包括 pending、in progress 和 complete。在当前交互式 Claude Code 中由 `TaskCreate`、`TaskGet`、`TaskList`、`TaskUpdate` 管理；旧的 `TodoWrite` 主要保留在非交互模式和 Agent SDK 兼容路径。

因此，批准 plan 不等于由一个固定转换器必然把计划逐条转成 task list。对于复杂、多步骤工作，Claude 通常会创建结构化任务列表跟踪执行；对于简单计划，可能直接实施而不建立明显的任务列表。Anthropic 对 Agent SDK 公开的 todo 使用启发条件包括：至少三个不同动作的复杂任务、用户提供多个任务项、值得跟踪的非平凡操作，或用户显式要求 TODO 组织。该描述是公开的行为指导，不应被理解为所有 Claude Code 表面的绝对硬编码保证。

## 补充：TODO / Task 的完成判定与验证

默认情况下，没有一个独立的、必然运行的验证器逐项证明 TODO 已完成。执行 agent 读取 task 的 subject/description，在 agentic loop 中观察文件、命令、测试、构建、截图或其他工具结果，然后由同一个模型判断成功条件是否满足，并调用 `TaskUpdate(status="completed")`。因此，task 状态本身是模型写入的工作流状态，不是正确性的证明。

验证强度取决于任务是否含有可观测验收标准，以及 Claude 是否实际执行了相应检查。官方将 Claude Code 的循环概括为 gather context、take action、verify results，并建议提供测试用例、期望输出或截图，让 Claude 运行测试、比较视觉结果或执行检查命令。若缺少明确成功标准，模型可能仅根据代码 diff、文件存在、命令未报错或语义判断宣布完成。

可增加两类独立约束：

1. **`TaskCompleted` hook**：当 agent 试图把 task 标记为 completed 时触发。确定性脚本可运行测试、lint、构建或自定义验收；若 hook 以退出码 2 结束，Claude Code 不会把 task 标为完成，并把 stderr 反馈给模型继续修复。这是逐 task 完成门禁。
2. **`/goal`**：每个 turn 结束后，由一个独立的小模型根据会话中已呈现的证据判断目标是否满足；若未满足则启动下一 turn。该 evaluator 自己不读文件、不运行命令，只能审查主 agent 已放进 transcript 的测试结果、退出码等证据。因此它是独立判断者，但不是独立执行测试的 verifier。

最可靠的工程方式是：在 task description 中写清 acceptance criteria 和验证命令，再用 `TaskCompleted` hook 对关键命令实行硬门禁；如需跨 turn 持续工作，再用 `/goal` 要求一个可测量的最终状态。用户最终仍应审查重要改动，因为模型判断、模型 evaluator 和测试覆盖本身都可能不完整。

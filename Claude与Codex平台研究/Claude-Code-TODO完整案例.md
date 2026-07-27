# Claude Code TODO 完整案例

> 自拟工程案例。机制依据 Anthropic 官方公开的 Plan Mode、Task tools、agentic loop、`TaskCompleted` hook 和 `/goal`；具体需求与执行轨迹不是 Anthropic 固定内部流程。

## 用户诉求

```text
给登录接口增加失败锁定：连续密码错误 5 次后锁定 15 分钟；
锁定期间正确密码也拒绝；成功登录清零失败次数；JWT 格式不能改变。
添加单元测试和接口测试。先 Plan，批准后建立 task list 实施；
每个 task 完成前必须运行其验证命令。
```

## Plan Mode 调研与计划

Claude 只读调研登录入口、数据模型、JWT 和测试框架，得到：

```text
POST /api/login -> AuthService.login()
User 尚无失败次数和锁定时间字段
JWT 由 token.ts 生成
使用 Prisma、Vitest、Supertest
```

随后向用户展示 proposed plan：

```text
1. User 增加 failedLoginAttempts 和 lockedUntil，生成迁移。
2. 实现锁定检查、失败原子计数、第 5 次设置 15 分钟锁定、成功清零。
3. 不修改 JWT payload 和 token.ts。
4. 添加服务单元测试和登录接口测试。
5. 运行 schema、typecheck、lint、目标测试和全量测试。
```

用户回复“批准，并把 JWT 未改变作为独立验收项”，Claude 退出 Plan Mode。

## 创建 Task List

模型通过 `TaskCreate` 建立结构化任务，而非仅显示 Markdown 复选框：

| ID | Task | 依赖 | 完成标准 |
|---|---|---|---|
| T1 | 数据模型和迁移 | 无 | `prisma validate` 成功，迁移只含预期字段 |
| T2 | 锁定业务逻辑 | T1 | 单元测试通过，并发计数不丢失 |
| T3 | 登录接口测试 | T2 | 失败、锁定、过期、成功场景通过 |
| T4 | JWT 不变性验证 | T2 | 契约测试通过，token.ts 无 diff |
| T5 | 全量质量检查 | T2-T4 | typecheck、lint、全量测试通过 |
| T6 | 文档和需求对照 | T5 | 每项原始要求都有实现位置和验证证据 |

所有任务初始为 `pending`。这只是工作状态，不是正确性证明。

## 执行 T1

```json
{"tool":"TaskUpdate","taskId":"T1","status":"in_progress"}
```

Claude 修改 schema、生成迁移并运行 `npx prisma validate`。返回 exit 0 后检查迁移 diff，再请求：

```json
{"tool":"TaskUpdate","taskId":"T1","status":"completed"}
```

此时触发 `TaskCompleted` hook。Hook 复验成功则允许完成；失败并退出 2，则 T1 保持 `in_progress`，错误反馈给模型。

## 执行 T2：先失败再修复

Claude 实现逻辑并运行目标单元测试。第一次结果：

```text
8 tests, 7 passed, 1 failed
concurrent failed logins: expected 5, received 3
exit 1
```

模型不能完成 T2。它识别到 read-modify-write 竞争，改用数据库原子增量或事务；重跑得到 8/8 passed、exit 0。随后 `TaskCompleted` hook 再运行目标测试，只有复验成功才允许 T2 变成 `completed`。

## 执行 T3 与 T4

T3 的接口测试证据：

```text
第 1～4 次错误密码 -> 401
第 5 次 -> 423 ACCOUNT_LOCKED
锁定期正确密码 -> 423
时钟推进 15 分钟后正确密码 -> 200
全部通过，exit 0
```

T4 同时检查：

```text
JWT contract tests -> passed, exit 0
token.ts diff -> empty
```

“无文件 diff”证明实现文件未改，“契约测试通过”证明被测试的可观察 JWT 行为未变；两者结合后 T4 完成。

## 执行 T5 与 T6

T5 运行：

```text
npm run typecheck -> exit 0
npm run lint      -> exit 0
npm test          -> 126 passed, exit 0
```

若任一失败，模型修复并重跑，Hook 也可以统一执行 `npm run verify` 作为硬门禁。

T6 最终对照：

| 原始要求 | 实现位置 | 证据 |
|---|---|---|
| 失败 5 次锁定 | auth-service.ts | 单元 + 接口测试 |
| 锁定 15 分钟 | auth-service.ts | fake-clock 测试 |
| 锁定期正确密码拒绝 | auth-service.ts | 接口返回 423 |
| 成功清零 | auth-service.ts | 单元测试 |
| JWT 不变 | token.ts 未修改 | 契约测试 |
| 测试要求 | 两个测试文件 | 全量 126 passed |

## 可选 `/goal` 复核

```text
/goal T1-T6 全部 completed，npm run verify 退出 0，JWT 契约测试通过，最终回复逐项给出原始需求的证据
```

每个 turn 后，独立小模型只依据 transcript 判断。例如缺少 JWT 结果时返回：

```text
NO: transcript 中没有 JWT contract test 的结果。
```

主 agent 继续工作并展示证据。条件齐全后 evaluator 返回 YES。它不自己读文件或运行命令，所以是独立判断者，不是独立测试执行器。

## 最终回复示例

```text
登录失败锁定已实现：连续 5 次失败后锁定 15 分钟；锁定期正确密码仍返回 423；成功登录清零计数。JWT 生成文件无变化，契约测试通过。

验证：Prisma schema、typecheck、lint 和 126 项测试全部通过。
上线前需要先执行数据库迁移，并确认多实例使用一致的数据库时钟策略。
```

## 完整状态轨迹

```text
用户需求 -> Plan 调研 -> Proposed Plan -> 用户批准
-> TaskCreate(T1..T6)
-> pending -> in_progress -> 执行 -> 验证
-> TaskUpdate(completed) -> TaskCompleted Hook
-> 失败：阻止完成并反馈模型 / 成功：completed
-> 全量验证 -> 需求逐项对照 -> 可选 /goal 复核 -> 最终证据摘要
```

## 关键边界

- Plan 是用户审阅的方案；Task List 是执行状态，两者不保证机械一一映射。
- `TaskUpdate(completed)` 是完成声明；测试、退出码、截图和契约检查才是证据。
- `TaskCompleted` hook 可把完成标准变成确定性门禁。
- `/goal` 是独立模型审查，但只看 transcript。
- 测试覆盖可能不完整，重要变更仍需人工审查。

## Task List 为什么是结构化的

是的，当前交互式 Claude Code 的 Task List 由一组内置工具管理：

- `TaskCreate`：创建一项任务。
- `TaskGet`：按 ID 读取任务详情。
- `TaskList`：读取当前任务列表及状态。
- `TaskUpdate`：修改状态、描述、依赖、负责人或删除任务。

模型并不是先输出一段 Markdown，再由 Claude Code 猜测其中哪些行是任务。模型产生的是 `tool_use` 内容块，其中包含工具名和结构化 `input`。例如：

```json
{
  "name": "TaskCreate",
  "input": {
    "subject": "实现登录失败锁定",
    "description": "连续失败 5 次后锁定 15 分钟，并添加单元测试",
    "activeForm": "正在实现登录失败锁定",
    "metadata": {"requirement": "AUTH-LOCK-01"}
  }
}
```

Claude Code runtime 执行该工具，为任务分配 ID，并通过 `tool_result` 返回类似 `{ "task": { "id": "1", "subject": "实现登录失败锁定" } }` 的结果。之后模型使用该 ID：

```json
{
  "name": "TaskUpdate",
  "input": {
    "taskId": "1",
    "status": "in_progress"
  }
}
```

官方公开的 canonical input 形状为：

```text
TaskCreate: { subject, description, activeForm?, metadata? }
TaskUpdate: { taskId, status?, subject?, description?, activeForm?,
              addBlocks?, addBlockedBy?, owner?, metadata? }
status: pending | in_progress | completed | deleted
```

因此结构化来自工具调用协议和工具输入字段约束，而不是依赖自然语言格式稳定性。官方文档还说明，stream 中能观察到模型原始产生的 `tool_use input`；Claude Code 对少数接近但不规范的字段名会在执行前修复，例如把 `task_id` 或 `id` 映射成 `taskId`，但修复后的形状不会回写到原始 stream。

Runtime 维护任务状态，终端 UI 再读取和渲染它：`Ctrl+T` 显示最多五项任务，任务可跨 context compaction 保留。设置 `CLAUDE_CODE_TASK_LIST_ID` 后，可以使用 `~/.claude/tasks/` 下的命名目录在 session 之间共享列表。官方只公开了这一用户可见存储位置约定，没有在上述文档中承诺内部文件格式；不应依赖未公开格式直接修改文件。

旧机制 `TodoWrite` 用一次工具调用整体重写 `{ content, status, activeForm }[]`。从 Claude Code v2.1.142 起它默认关闭，改由 `TaskCreate`/`TaskUpdate` 增量维护；`TaskList`/`TaskGet`负责读取。这也解释了为什么当前任务可以有稳定 ID、依赖关系和逐项更新。

## 执行 Agent 能获得哪些 Task 信息

需要区分“Task 记录字段”与“Agent 的完整执行上下文”。

### Task 记录字段

根据官方公开的 Task tool 输入，任务记录可包含：

- `id`：runtime 在创建后分配的任务标识。
- `subject`：简短标题，例如“数据模型和迁移”。
- `description`：详细任务说明；验收标准、范围、禁止事项和验证命令通常应写在这里。
- `activeForm`：任务进行中用于 UI 展示的文字。
- `status`：`pending`、`in_progress`、`completed`；`deleted` 用于删除。
- 依赖关系：通过 `addBlockedBy` 表示本任务依赖哪些任务，通过 `addBlocks` 表示本任务阻塞哪些任务。
- `owner`：Agent Teams 中可用于记录负责人/teammate。
- `metadata`：附加的结构化元数据。

“完成标准”不是官方 schema 中单独命名的 first-class 字段。它通常被编码在 `description`，也可把机器可读部分放进 `metadata`。同理，文件范围、验证命令、禁止改动、交付物和风险都不会凭空成为任务字段，必须由 lead/模型写进 description、metadata 或另发消息。

### Agent 的执行上下文

执行者除了通过 `TaskGet`/`TaskList`读取 task 记录，还可能拥有：

- 自己的 system prompt、模型、工具权限和 permission mode。
- 当前工作目录及可访问文件。
- 项目上下文，如 `CLAUDE.md`；Agent Teams teammate 还会像普通 session 一样加载项目 skills 与 MCP servers。
- lead 创建 teammate 时给出的 spawn prompt。
- lead 或其他 teammate 后续通过消息发送的补充信息。
- 共享列表中其他任务的状态与依赖，用于判断当前任务是否可 claim。

这些信息不属于 T1 记录本身，而是围绕任务的运行上下文。

### 三种执行方式的差异

1. **主 Agent 自己执行**：主会话拥有用户需求、Plan、此前调研和 Task List，因此上下文最完整。
2. **普通 subagent 执行**：subagent 有独立的新上下文，官方明确它接收的是父 Agent 编写的 delegation/task message，而不是父对话历史。Task List 和 subagent delegation 是两个机制，不能假设创建 T1 后 subagent 自动获得全部原始需求；父 Agent 应把 subject、description、验收标准、相关路径、验证命令和约束写进 spawn prompt。
3. **Agent Teams teammate 执行**：teammate 是独立 Claude Code session，加载项目上下文、接收 lead 的 spawn prompt，并能访问共享 Task List、claim/被分配任务、读取状态和依赖，还能接收 agent 间消息。它不会继承 lead 的完整对话历史。

官方没有公开保证“任务被 assign 时，TaskGet 的所有字段会以某个固定 prompt 模板完整注入 teammate 上下文”。可核实的是 teammate 能看到共享 Task List、task management tools 始终可用、并接收 spawn prompt。因而可靠做法是让 task description 自包含，并要求执行者在开工前调用 `TaskGet`，不要依赖隐式上下文。

### 自包含 T1 示例

```json
{
  "subject": "扩展登录锁定数据模型并生成迁移",
  "description": "在 prisma/schema.prisma 的 User 增加 failedLoginAttempts Int @default(0) 与 lockedUntil DateTime?，生成迁移。只允许修改 schema 和新迁移文件，不修改既有迁移。完成前运行 npx prisma validate，并检查迁移 SQL 只增加预期字段。返回修改文件、命令、退出码和风险。",
  "activeForm": "正在扩展登录锁定数据模型",
  "metadata": {
    "requirementIds": ["AUTH-LOCK-01"],
    "validationCommand": "npx prisma validate",
    "allowedPaths": ["prisma/schema.prisma", "prisma/migrations/<new>/**"]
  }
}
```

依赖和负责人随后通过 `TaskUpdate` 添加，例如 `addBlockedBy` 与 `owner`。这样即使执行者没有 lead 的对话历史，单独读取 T1 也能理解交付物、边界和验证要求。

## 官方机制来源

- [Plan Mode](https://code.claude.com/docs/en/permission-modes#analyze-before-you-edit-with-plan-mode)
- [Tools reference](https://code.claude.com/docs/en/tools-reference)
- [How Claude Code works](https://code.claude.com/docs/en/how-claude-code-works)
- [TaskCompleted hook](https://code.claude.com/docs/en/hooks#taskcompleted)
- [`/goal`](https://code.claude.com/docs/en/goal)

## TaskCompleted Hook 是否调用 LLM

`TaskCompleted` 是生命周期事件，不等同于一个 LLM verifier。只有配置了匹配 handler 时才会执行检查；handler 可以是 `command`、`http`、`mcp_tool`、`prompt` 或 `agent`。因此是否调用 LLM 取决于配置。

- `command`：运行确定性脚本，例如 test、lint、build。退出码 2 阻止任务变成 completed，并把 stderr 反馈给模型；不调用 LLM。
- `http`：请求外部验证服务。
- `mcp_tool`：调用已连接 MCP server 的工具。
- `prompt`：把事件输入和自定义 prompt 发给 Claude，默认使用 Haiku，单轮返回结构化决定；会调用 LLM。
- `agent`：实验性 agent hook，启动一个具有 Read、Grep、Glob 等工具能力的 verifier subagent，多轮检查后返回决定。

多个匹配 handler 会并行运行。官方建议生产工作流优先采用 command hook；常见组合是用 command 硬性检查测试退出码，再用 prompt 或 agent hook 处理难以脚本化的语义标准。

## 没有专属 Hook 时如何判断 Task 完成

用户的判断成立：Task List 是模型根据当前需求动态生成的，而 settings 中的 Hook 通常是预先配置的通用策略；默认并不存在“每个动态 Task 自动生成一个对应 verifier”。如果没有匹配的 `TaskCompleted` hook，也没有 `/goal` 或额外 reviewer，完成判定走默认 agentic loop：

1. 执行模型读取 task 的 subject、description、依赖，以及当前会话/项目上下文。
2. 模型采取行动：读写文件、运行命令、调用工具。
3. 工具结果回到同一个模型上下文，例如 edit 成功、test exit 0、文件内容、截图或 API 响应。
4. 模型把观察到的结果与自己理解的任务目标进行语义比较。
5. 模型认为满足后调用 `TaskUpdate(status="completed")`；Claude Code runtime 记录并显示状态。

这里没有必然独立于执行模型的校验层。`TaskUpdate(completed)` 是模型基于现有证据作出的完成声明；runtime 只执行状态变更与依赖解锁，不会自动理解业务验收标准并证明它正确。Anthropic 把整体工作描述为 gather context、take action、verify results，但没有公开一个固定的 task completion 打分算法、隐式 verifier prompt 或强制测试规则。

所谓“模型校验”通常是模型主动选择可用反馈回路：运行测试、typecheck、lint、build、读取修改后的文件、比较 diff/截图/期望输出，再根据工具结果决定是否继续。这些检查是否发生、运行哪些命令及覆盖范围，受用户要求、task description、`CLAUDE.md`、当前上下文和模型判断影响。若没有明确验收标准或验证工具，模型可能仅凭 diff 与语义判断完成，因此存在误报风险。

Hook 的作用不是为动态任务自动创造专属标准，而是把通用组织规则变成门禁。例如一个通用 `TaskCompleted` command hook 可以读取事件里的 task ID/subject/description，再调用项目统一的 `npm run verify`；也可以由脚本依据 metadata/subject 路由不同检查。但这种映射必须由用户或项目工程化配置，Claude Code不会从每个动态 task 自动生成并持久化对应 Hook。

可靠性由弱到强可分为：同一模型主观判断；同一模型运行客观检查；通用 `TaskCompleted` 硬门禁；按 task metadata 路由的专属检查；独立 reviewer/agent hook；最后人工审查。Task List 本身主要解决分解、进度、依赖和上下文持久化，不是 correctness verification framework。

## Hook 的配置作用域

官方公开的持久化/组件作用域包括：用户级 `~/.claude/settings.json`（本机所有项目）、项目共享级 `.claude/settings.json`、项目本地级 `.claude/settings.local.json`、组织 managed policy、插件 `hooks/hooks.json`，以及 skill/subagent frontmatter（仅组件激活期间）。`/hooks` 还会显示内存中的 Session hook 和 Claude Code 内置 Hook；session hook 随会话结束而消失。

`TaskCompleted` 没有原生 matcher 支持：一旦配置，它会在每次任务尝试完成时触发；为它填写 matcher 会被忽略。因此 Claude Code 没有一个声明式的“此 Hook 只绑定 task ID T1”配置层级。

可以在 handler 内部实现任务级过滤。事件输入含 `task_id`、`task_subject`、可选 `task_description`、`teammate_name` 和已弃用的 `team_name`。脚本读取这些字段，不相关任务直接 exit 0，匹配的任务再运行检查。例如按 `task_id` 精确绑定只适合当前动态列表；按 subject、description 中的标签或 metadata 约定路由更容易复用。需要注意官方 TaskCompleted hook 输入未列出完整 metadata 字段，因此若验证器依赖 metadata，通常需自行通过 task ID 读取外部映射，或把关键标签写进 subject/description。

Skill 或 subagent frontmatter Hook 可以把检查限定在某个工作流/Agent 的生命周期，适合“这个 skill 执行期间的任务”或“这个 verifier agent 工作期间”的范围，但仍不等价于原生 per-task Hook。若需要真正的一次性任务门禁，可由应用/SDK在 session 内注册临时 Hook，或用通用 Hook 脚本读取当前任务 ID 后路由；这属于工程编排，不是 TaskCreate 自动完成的行为。

## Task 依赖如何阻止后续任务提前执行

依赖由 `TaskUpdate` 写入任务图：对 T2 设置 `addBlockedBy: [T1]` 表示 T2 必须等待 T1；反方向也可用 `addBlocks` 表示 T1 阻塞 T2。Task List 将 T2 保持为 pending/blocked，直到 T1 变成 completed。

Anthropic 对 Agent Teams 明确公开了运行时调度保证：带未解决依赖的 pending task 不能被 teammate claim；T1 完成后系统自动解除依赖并使 T2 可 claim。多个 teammate 同时抢同一可用 task 时，claim 使用文件锁防止竞态。因此强制发生在“任务认领与调度状态”这一层。

这不是通用的文件或工具执行沙箱。依赖不会天然阻止某个 Agent直接编辑 T2 相关文件、运行命令或在对话里提前做后续工作；尤其在主 Agent 单会话的普通 checklist 中，官方资料只明确 Task tools 能记录/更新依赖，没有公开与 Agent Teams 相同的 claim 门禁保证。主模型通常通过 `TaskList` 选择未阻塞任务并遵守依赖，但不能把它表述为所有工具调用都会被 runtime 硬性拦截。

若需要更强约束，应把调度与执行权限结合：由 lead 只给 teammate 分配 unblocked task；每个 worker 开工前 `TaskGet`/`TaskList` 检查 `blockedBy`；按 task 划分文件所有权或 worktree；必要时用 PreToolUse hook/外部 orchestrator 阻止未满足前置状态时的写入；并用 TaskCompleted hook 确保 T1 只有通过验证后才变成 completed。这样 T2 的自动解锁才建立在可信的 T1 完成状态上。

### Teammate claim 的含义

Claim 是 Agent Teams 中 teammate 对一个共享、未分配且未阻塞任务进行“认领”：把自己登记为该 task 的 owner，并通常把 task 从 pending 推进到 in_progress，从而告诉整个团队“该任务已由我负责”。Lead 也可以直接 assign，此时不需要 teammate 自行选择。

Claim 是协调状态变更，不是创建 Agent，也不是文件锁定、权限授权或代码修改本身。认领成功后 teammate 才开始读取任务详情和执行工作；其他 teammate 看到 owner/in_progress 后不应再做同一任务。多个 teammate 同时 self-claim 时，Claude Code 使用文件锁保证只有一个认领成功。带未完成 `blockedBy` 的任务不可 claim；依赖完成后才进入可认领集合。

### Teammate claim 完整案例

共享 Task List：

```text
T1 创建数据库迁移       pending，未分配
T2 实现登录锁定逻辑     pending，blocked by T1
T3 添加接口测试         pending，blocked by T2
```

团队成员：

```text
database-agent
backend-agent
test-agent
```

`database-agent` 检查 T1，发现它是 pending、没有未完成依赖且没有 owner，于是 self-claim：

```text
Claim 前：
T1.status = pending
T1.owner = null

Claim 后：
T1.status = in_progress
T1.owner = database-agent
```

概念上相当于：

```json
{
  "taskId": "T1",
  "owner": "database-agent",
  "status": "in_progress"
}
```

此时其他 teammate 看到 T1 已有 owner，不应重复执行。Claim 只登记逻辑所有权；它不会自动创建 Agent、修改代码、锁住相关文件、创建 Git 分支或增加权限。

Lead 也可以直接 assign：

```text
Lead：把 T1 分配给 database-agent。
```

结果同样是 owner/status 更新。区别是 assign 由 lead 决定，self-claim 是 teammate 从未分配且未阻塞的任务中自主选择。

如果 `database-agent` 与 `backend-agent` 同时 claim T1：

```text
database-agent ─┐
                ├─ 同时请求 claim T1
backend-agent ──┘
```

Claude Code 使用文件锁保护认领记录：先获得锁的 agent 检查 T1 仍未分配，写入 owner/status 后释放锁；后获得锁的 agent 会看到 T1 已有 owner，因此 claim 失败。这里锁住的是任务认领状态，不是代码文件。

`backend-agent` 此时也不能 claim T2：

```text
T2.blockedBy = [T1]
T1.status = in_progress
```

运行时检查到前置依赖未完成，T2 不属于可认领集合。当 database-agent 完成并成功标记 T1：

```text
T1.status = completed
```

系统自动解除 T2 的阻塞：

```text
T1 completed
T2 pending，unblocked，未分配
T3 pending，blocked by T2
```

现在 backend-agent 可以 claim T2；T2 完成后，T3 同理自动解锁并可由 test-agent claim。

完整状态流：

```text
T1 pending/unassigned
  -> database-agent claim
  -> T1 in_progress/owner=database-agent
  -> 实施和验证
  -> T1 completed
  -> Runtime 自动解锁 T2
  -> backend-agent claim T2
  -> T2 completed
  -> Runtime 自动解锁 T3
  -> test-agent claim T3
```

需要再次区分：任务依赖和 claim 强制的是共享 Task List 的调度顺序，不会天然阻止某个具有 Edit/Bash 权限的 agent 绕过列表提前修改 T2 文件。严格隔离还需要 lead 调度、文件所有权/worktree 或额外的 PreToolUse 门禁。

### 普通 subagent 与 Agent Teams teammate 的时序差异

前述 claim 案例专指 Agent Teams teammate，不适用于普通 subagent。二者都可以并发，但协调模型不同。

普通 subagent 由主 Agent 通过 Agent tool 派生，使用独立上下文并把结果返回调用者；没有 Agent Teams 那种 teammate 共享认领协议。对于 `T1 -> T2` 的强依赖链，典型流程确实是：主 Agent 派发 T1 给 database subagent，等待结果；确认/标记 T1 完成；再把 T1 的必要结果写入 T2 delegation prompt，派发 backend subagent。此时依赖链在逻辑上串行，即使 Claude Code v2.1.198 起 subagent 默认后台运行。

```text
Main
  -> spawn database subagent(T1)
  -> wait T1 result
  <- migration path/schema summary/verification
  -> mark T1 completed
  -> spawn backend subagent(T2 + T1 relevant result)
  -> wait T2 result
```

“后台默认”表示主线程在 subagent 工作时可以继续处理不依赖它的事情，不代表有依赖的 T2 会自动同时启动。若任务独立，主 Agent 可以一次启动多个 subagent 并行；若有硬依赖，应等待前置结果后再委派后续任务。

Agent Teams 中多个 teammate 是同时存活的独立 Claude Code session，可以并行处理不同的 unblocked task，并共享任务状态。T1 未完成时 backend teammate 可以处于 idle，或处理另一个独立任务，但不能 claim 被 T1 阻塞的 T2。T1 完成后 runtime 解锁 T2；backend teammate 或任一合适的空闲 teammate 再 claim T2。结果交接不必由 main 手工复制全部文本，因为共享 Task List负责状态/依赖，teammate 还可通过消息通信；但 T2 所需的具体产物路径、接口变化和注意事项仍应写入 task description 或由 T1 owner/lead 发消息。

```text
Agent Team：

lead
├── database teammate: claim T1 -> work -> complete
├── backend teammate: idle/做其他独立任务
└── test teammate: idle/做其他独立任务

T1 completed -> runtime unlock T2
backend teammate -> claim T2 -> work
```

因此：“其他 teammate 看到 T1 已有 owner”是在解释 Agent Teams 中多个并行存在的 session；若讨论普通 subagent，更准确的说法是主 Agent控制 spawn/wait 顺序，不需要 claim 来防止重复派发。

### 串行任务如何依序推进

对普通 subagent，串行主要由主 Agent充当 orchestrator 来实现，而不是由一个隐藏的全局事务调度器保证。主 Agent读取任务图，选择当前没有未完成 `blockedBy` 的 task，将其设为 in_progress，委派给 subagent；需要结果才能继续时以前台方式调用，或后台调用后显式等待完成；收到 tool result/最终摘要后进行必要验证，把前置 task 标为 completed，然后才创建下一次 Agent 调用并把前置产物摘要写进 delegation prompt。

```text
TaskList -> 选择T1 -> TaskUpdate(T1,in_progress)
-> Agent(T1) -> wait/result -> verify
-> TaskUpdate(T1,completed)
-> 再选择T2 -> Agent(T2 + T1 handoff)
```

Claude Code 对控制流能提供的硬边界是：一次前台 Agent tool call 未返回时，主模型没有下一次推理回合，因此不能在该回合继续派发依赖任务；后台 subagent 虽可并发，若后续依赖其结果，主 Agent必须使用任务状态/等待机制等到结果到达。模型通常根据工具返回结果和 Task List 继续，但若它错误地提前派发、错误标记 completed，普通 checklist 本身不保证阻止。

Agent Teams 的依赖更强：被未完成依赖阻塞的 task 不能 claim，前置 completed 后 runtime 自动解锁。不过这仍只保证调度顺序，不保证前置业务实现正确，也不阻止绕过 Task List 的直接文件操作。

因此“保证”分三层：模型层遵循任务图和一次只推进一个依赖链节点；工具控制流层通过 foreground/wait 阻止在结果返回前进入下一模型步骤；Agent Teams runtime 在 claim 层拒绝 blocked task。要提高工程可靠性，应再规定依赖链最多一个 in_progress、每次开工前 TaskGet/TaskList、把前置产物写入 handoff、用 TaskCompleted hook验证前置任务、并对关键链路由外部 orchestrator/CI 门禁。没有这些增强时，普通 subagent 串行是模型驱动的流程纪律，而不是形式化证明或数据库事务。

### Subagent 完成后的验收者

默认验收者是调用 subagent 的主 Agent。普通 subagent 在独立上下文中工作并返回结果/摘要到主会话；官方没有规定每次 subagent 完成后自动生成专门 verifier。主 Agent读取返回摘要，结合原始需求和 Task description，必要时读取 diff、文件或运行测试，然后决定继续修复、重新委派或把 task 标为 completed。

执行 subagent 自己也可能在返回前运行测试和自检，但这是第一方自验证；主 Agent若只相信其“已完成”摘要而不复核证据，仍可能误验收。返回内容应包括修改文件、验证命令、退出码、未解决问题和风险，使主 Agent可核查。

专门验证 subagent 是可选的显式工作流：用户或主 Agent可以在实现者返回后再 spawn 一个只读 code-reviewer/test-runner，让它依据验收标准独立检查，然后把验证结果返回主 Agent。Anthropic 官方最佳实践明确建议实现后可使用 subagent review edge cases；官方也支持 chain subagents，即一个 subagent 返回后由 Claude把相关上下文传给下一个。

```text
Main -> implementer(T1) -> implementation result
Main -> verifier(T1 criteria + result/diff) -> pass/fail findings
Main -> pass: completed / fail: send fixes to implementer or new worker
```

这种 verifier 不会默认出现。它可由用户明确要求、`CLAUDE.md`/skill工作流规定、custom subagent description 触发，或通过 experimental agent-based `SubagentStop`/`TaskCompleted` hook实现。确定性测试 Hook 和独立 reviewer解决不同问题：前者检查机器可执行条件，后者检查语义、遗漏和边界；最终状态仍由主 Agent/orchestrator综合决定。

#### 默认的两层检查：完整案例

第一层是执行 subagent 自检。以 database subagent 执行 T1 为例：

```text
1. 修改 Prisma schema
2. 创建迁移
3. 运行 prisma validate
4. 检查迁移 SQL
5. 返回结果
```

它应返回可核查的执行摘要：

```text
T1执行结果：

修改文件：
- prisma/schema.prisma
- prisma/migrations/20260716_login_lock/migration.sql

验证：
- npx prisma validate
- exit code 0

迁移内容：
- 添加 failedLoginAttempts
- 添加 lockedUntil

未解决问题：
- 无
```

这是执行者的第一方自检，不能视为独立验收，因为同一个 subagent 同时编写代码、运行测试、解释结果并声称完成。

第二层是主 Agent验收。结果返回主会话后，主 Agent拥有用户原始需求、批准的 Plan、T1 description、subagent 摘要和后续任务依赖。主 Agent应检查：

```text
1. 是否完成全部交付物？
2. 是否运行规定的验证命令？
3. 退出码是否成功？
4. 是否违反禁止修改项？
5. 是否仍有未解决问题？
6. 返回结果是否足以启动 T2？
```

必要时主 Agent自行复验：

```text
Read prisma/schema.prisma
Read migration.sql
Run npx prisma validate
Run git diff
```

通过则把 T1 标记 completed、生成 handoff 并启动 T2；不通过则保持 in_progress，要求原 subagent继续修复或创建新的修复 subagent。

#### 默认不会自动产生 Verifier

Claude Code没有公开保证实现 subagent 完成后系统自动再创建 verifier。专门 verifier 需要由用户明确要求、主 Agent主动选择、`CLAUDE.md`/skill规定、自定义 agent description 触发、Hook配置或外部 orchestrator 编排。

可显式要求：

```text
每个实现 subagent 完成后，必须创建一个独立的只读 verifier subagent。
verifier 不得相信实现者的完成声明，必须重新读取 diff、运行目标测试并逐项检查验收标准。
只有 verifier 通过后，主 Agent才能把 Task 标记 completed。
```

流程：

```text
Main -> implementer(T1) -> 实现结果
Main -> verifier(T1标准 + diff/结果) -> PASS/FAIL证据
Main -> PASS: completed
     -> FAIL: 返回implementer修复并重新验收
```

Verifier 委派示例：

```text
你是 T1 的独立验收者，只读检查，不修改文件。

目标：增加 failedLoginAttempts 和 lockedUntil，创建迁移。
禁止：不修改既有迁移，不修改 JWT 逻辑。
验收：读取 schema 和新迁移；检查字段类型与默认值；运行 npx prisma validate；检查 git diff；确认迁移只含预期字段。
返回：PASS 或 FAIL、每项标准的证据、失败项和修复建议。
```

失败示例：

```text
Verdict: FAIL

通过：
- Prisma schema 有效
- 两个字段类型正确

失败：
- migration.sql 同时删除了 legacyToken 字段
- 违反“只包含预期字段”标准

Evidence:
- migration.sql line 8: DROP COLUMN legacyToken
```

主 Agent据此拒绝完成 T1，进入 implementer 修复、verifier 重验循环。

#### 按任务风险选择验收方式

```text
低风险：拼写、注释、简单配置
-> 实现者自检 + 主Agent看diff

中风险：普通业务功能、局部重构、新接口
-> 实现subagent + 主Agent复验 + TaskCompleted command hook

高风险：数据库迁移、认证、权限、支付、并发、部署
-> 实现subagent + 独立verifier + 确定性Hook + CI + 人工审查
```

各机制职责：

| 机制 | 主要职责 |
|---|---|
| 主 Agent | 综合原始需求、Task和返回结果，决定下一步 |
| 实现 subagent | 实现并进行第一方自检 |
| Verifier subagent | 独立检查语义、边界、遗漏和风险 |
| Command Hook | 强制 test、lint、build 等确定性条件 |
| CI | 在标准环境执行完整自动检查 |
| 人工审查 | 判断业务语义、测试覆盖和最终可接受性 |

即使 verifier 返回 PASS，最终完成状态通常仍由主 Agent或共享任务 owner更新；verifier 提供验收证据，不天然拥有最终决定权。

## 前序讨论案例补全

### Explore、Plan 与 general-purpose 路由案例

用户请求：

```text
找到登录锁定逻辑位于哪些文件，不要修改代码。
```

Claude可能选择 Explore，因为任务是只读的文件发现、代码搜索和代码库理解。调用时会指定 quick、medium 或 very thorough 深度。Explore 返回文件、调用链和摘要，搜索噪音留在独立上下文。

```text
Main -> Explore(quick)
     <- auth-service.ts、auth.ts、login.test.ts及调用关系
```

如果用户处于 Plan Mode 并要求设计迁移：

```text
/plan 为登录失败锁定设计实施方案，先理解现有认证和数据库结构。
```

Claude需要为计划收集代码库上下文时使用 Plan subagent：

```text
Main(Plan Mode) -> Plan subagent(read-only research)
                <- schema、认证流程、测试框架、风险
Main            -> Proposed Plan -> 用户批准
```

如果任务要求“调查并直接修改”：

```text
调查登录失败计数丢失的原因，修复并运行测试。
```

这同时需要探索、复杂推理、编辑和多步骤操作，更符合 general-purpose：

```text
Main -> general-purpose
     -> 搜索 -> 定位竞态 -> 修改 -> 测试 -> 返回摘要
```

官方没有公开固定路由分数。自动委派依据用户任务描述、agent description 和当前上下文；上述是功能性边界，不是保证每次必然调用同一 agent。

### 单个 Explore 与多个 Explore 并行案例

定点搜索通常只需要一个 Explore：

```text
找到 AuthService.login 的定义和直接调用者。
```

可拆分的独立研究可以显式并行：

```text
使用三个 Explore subagent 并行调查：
1. 认证模块
2. 数据库模型和迁移
3. 登录测试
等待全部完成后汇总文件、接口和风险。
```

```text
Main
├── Explore A：认证模块
├── Explore B：数据库模型
└── Explore C：登录测试
          ↓
       Main 汇总
```

后台运行提供并发条件，但不会让一次普通搜索必然自动生成多个 Explore。若三条研究路径互相依赖，应串行；若需要确定数量和拆分方式，应在提示中明确写出。

### Plan 与结构化 Task List 的转换案例

Plan 是给用户审批的方案：

```text
1. 扩展User模型
2. 实现锁定逻辑
3. 添加测试
4. 全量验证
```

用户批准后，复杂任务可能被转换成 Task tools 管理的列表：

```text
T1 扩展User模型       pending
T2 实现锁定逻辑       pending, blockedBy T1
T3 添加接口测试       pending, blockedBy T2
T4 全量验证           pending, blockedBy T3
```

两者没有官方承诺的一对一机械转换。模型可能把一个 Plan 步骤拆成多个 Task，也可能把多个步骤合并；简单计划可能不创建 Task List。若需要确定映射，应明确要求“批准后把每个实施阶段转换成结构化任务并标注依赖”。

### Task 工具调用与 UI 渲染完整案例

模型产生结构化 `tool_use`：

```json
{
  "type": "tool_use",
  "name": "TaskCreate",
  "input": {
    "subject": "扩展User模型",
    "description": "增加failedLoginAttempts与lockedUntil；运行prisma validate",
    "activeForm": "正在扩展User模型"
  }
}
```

Runtime 创建记录并返回 ID：

```json
{"task":{"id":"T1","subject":"扩展User模型"}}
```

模型随后增量更新：

```json
{"name":"TaskUpdate","input":{"taskId":"T1","status":"in_progress"}}
```

Claude Code保存任务状态，`Ctrl+T` 读取并渲染 checklist。它不是从 Markdown 复选框反向解析出来的。旧 `TodoWrite` 是一次重写整个 todos 数组；当前 Task tools 用稳定 ID 逐项创建、读取和更新。

### 无 Hook 时的完成判断案例

```text
T1.description：增加两个字段并运行prisma validate。
```

默认执行者：

```text
读取Task -> 修改schema -> 运行命令 -> 观察exit 0
-> 对照description -> TaskUpdate(completed)
```

如果 description 只有“优化认证模块”，模型可能仅凭 diff 和语义判断完成。Task状态是模型声明，不是 correctness proof；Runtime保存状态和解锁依赖，不自动理解业务标准。

### TaskCompleted 五种 Handler 案例

```text
command  -> npm test；exit 2时阻止完成
http     -> POST事件JSON到外部验证服务
mcp_tool -> 调用已连接MCP检查器
prompt   -> 默认Haiku做单轮yes/no语义判断
agent    -> 实验性verifier subagent读取/搜索代码后判断
```

常见组合：

```text
TaskCompleted
├── command：test + lint + typecheck
└── prompt/agent：检查需求遗漏、架构约束和完成证据
```

没有配置 handler 时，事件本身不会凭空执行验证。

### Hook 各作用域配置案例

用户级 `~/.claude/settings.json`：所有项目阻止危险命令；适合个人通用安全策略。

项目共享级 `.claude/settings.json`：提交到仓库，所有成员在 TaskCompleted 时运行 `npm run verify`。

项目本地级 `.claude/settings.local.json`：当前机器的数据库、路径或私有检查，不提交 Git。

组织 managed settings：管理员分发不可由低层设置关闭的治理 Hook。

Plugin `hooks/hooks.json`：插件启用期间合并生效，适合可分发工具链。

Skill frontmatter：仅 skill 激活期间，例如 migration skill 执行期间对每次任务完成运行迁移检查。

Subagent frontmatter：仅该 agent 生命周期，例如安全 reviewer 使用期间限制 Bash 或在停止前执行检查。

Session Hook：只在当前会话内存中存在；`/goal` 是 session-scoped prompt-based Stop hook 的官方快捷方式。

TaskCompleted 不支持 matcher，所以不能直接声明 `matcher: T1`。若只验证 T1，handler 必须读取事件里的 `task_id`/`task_subject`/`task_description`：

```text
if task_id != T1 -> exit 0
if task_id == T1 -> run prisma validate；失败exit 2
```

更可复用的方式是在 subject/description 放置 `[db-migration]` 等标签，让通用 Hook按任务类型路由。

### 依赖、认领与串行交接总案例

普通 subagent：

```text
Main -> database subagent(T1) -> wait -> T1结果/验证
Main -> TaskUpdate(T1,completed)
Main -> backend subagent(T2 + T1 handoff) -> wait
```

Agent Teams：

```text
T1 pending/unassigned
T2 pending/blockedBy T1

database teammate claim T1
-> owner=database, in_progress
-> complete T1
-> runtime unlock T2
-> backend teammate claim T2
```

Claim 的文件锁只保护任务认领记录；Task依赖只强制 claim/调度，不锁代码文件。若要防止绕过列表提前编辑，需要文件所有权、worktree、PreToolUse门禁或外部 orchestrator。

# SKILL.md 与 AGENTS.md 的约束力和区别

## 结论

`SKILL.md` 和 `AGENTS.md` 被 Codex 加载后，其中的指令都需要执行，但二者并不是同一种、同作用域的约束，也不能简单理解为“约束力完全一样”。

- `AGENTS.md` 是持久的项目指导：Codex 开始工作前加载，规定仓库或目录中普遍适用的约定。
- `SKILL.md` 是按任务激活的工作流：只有 Skill 被显式调用或因任务匹配而选中后，Codex 才加载其完整内容。
- 官方将两者描述为互补层，而不是竞争关系：`AGENTS.md` 塑造项目内行为，Skill 封装可复用流程和领域能力。

## 核心区别

| 维度 | AGENTS.md | SKILL.md |
|---|---|---|
| 主要用途 | 仓库惯例、构建测试命令、审查要求、目录规则 | 可复用任务流程、领域知识、脚本、参考资料和资产 |
| 生效条件 | Codex 在开始工作前按路径发现并加载 | Skill 被显式调用，或任务与其 `description` 匹配后才完整加载 |
| 典型作用域 | 全局、仓库、目录子树；越靠近当前目录的指导越优先 | 用户级或仓库级；以“是否选择该 Skill”限定任务作用域 |
| 加载方式 | 从全局到项目根，再到当前目录组成指令链 | 渐进披露：先提供名称、描述和路径；选中后读取完整 `SKILL.md`，按需读取引用或运行脚本 |
| 内容形态 | 通常是持续适用的简短文字规则 | 必需的元数据和流程说明，可带 `scripts/`、`references/`、`assets/` |
| 合适示例 | “本仓库只引用官方资料”“修改后运行指定测试” | “生成并视觉检查 DOCX”“按固定步骤发布版本” |

## 如何理解“约束力”

应分成两个问题：

1. **是否必须遵循**：如果文件内容已经进入当前任务的有效指令上下文，而且不与更高优先级指令冲突，就应遵循。因此，在这一层面二者都不是可随意忽略的建议。
2. **何时、对什么任务生效**：二者明显不同。`AGENTS.md` 默认对其路径作用域内的工作持续生效；`SKILL.md` 则以 Skill 已被选中为前提，通常只约束对应工作流。

所以，更准确的表述是：**加载后都有约束性，但加载条件、职责和作用域不同。**

## 冲突时怎样处理

OpenAI 的公开页面明确说明了 `AGENTS.md` 自身的合并顺序：从项目根向当前目录拼接，离当前目录更近的指导因出现在后面而覆盖较早指导。公开的 Skills 页面则说明 Skill 的触发和加载机制，但没有在这两个页面中公布一条“`SKILL.md` 与 `AGENTS.md` 二选一时谁固定优先”的专门排序规则。

因此不应声称“Skill 天生高于 AGENTS”或“AGENTS 天生高于 Skill”。工程上应让它们职责分离：

- 把无论执行什么任务都必须遵守的仓库底线放进 `AGENTS.md`。
- 把某类任务的具体步骤、模板、引用材料放进 `SKILL.md`。
- 避免在 Skill 中改写仓库底线；若确有例外，应在 `AGENTS.md` 中明确授权该例外及其范围。
- 更高层级的系统、开发者和用户指令仍可能限制或覆盖本地文件；本地文件不能提升权限，也不能绕过沙箱或审批。

最后一点是通用的指令层级说明；上述两篇公开页面主要解释 `AGENTS.md` 与 Skills 各自的产品机制，并未完整公开 Codex 内部提示词组装的所有优先级细节。

### 同一目录中的 SKILL.md 与 AGENTS.md 冲突

“越靠近当前工作目录的规则优先”只适用于 Codex 构建 `AGENTS.md` 指令链时的覆盖关系。例如，`repo/AGENTS.md` 与 `repo/module/AGENTS.md` 冲突，而当前目录位于 `repo/module/` 时，后者覆盖前者。这个目录规则不能外推为“当前目录下的 `SKILL.md` 与 `AGENTS.md` 同级”或“路径相同所以二者平级”。

Skill 所在目录决定它是否会被发现以及属于用户级还是仓库级；它不会因此自动获得覆盖同目录 `AGENTS.md` 的优先权。Skill 还必须先被选中，完整 `SKILL.md` 才会加载。

OpenAI 当前公开的 `AGENTS.md` 与 Skills 页面没有规定二者发生直接矛盾时的固定文件级胜负关系。因此，不能依据官方资料宣称任一方总是优先。安全的处理方式是：

1. 先遵守系统、开发者和当前用户的更高层指令；本地文件不能突破权限、安全或审批边界。
2. 若两条本地指令可以按作用域协调，采用更具体且不违反仓库底线的解释。例如 `AGENTS.md` 规定“所有文档必须引用官方来源”，Skill 可以进一步规定某类报告的引用格式，但不能改成“不需要来源”。
3. 若是不可同时满足的硬冲突，不应默默任选一条。应停止冲突动作，向用户说明两条规则及影响，请用户决定；随后修改文件以消除长期歧义。
4. 工程设计上，`AGENTS.md` 应写不随任务变化的仓库不变量，`SKILL.md` 应写在这些不变量内执行的任务流程。如需让 Skill 构成例外，应由 `AGENTS.md` 明确写出授权，例如“执行 `$release` Skill 时允许修改版本文件”。

示例：同目录 `AGENTS.md` 写“禁止联网”，`SKILL.md` 写“第一步联网搜索”。不能因为 Skill 与它同目录或已被触发，就断定 Skill 覆盖前者。若没有更高层明确授权联网例外，应把它视为不可协调冲突并请求澄清；同时，实际联网仍受沙箱与审批控制。

## 官方来源

- OpenAI, [Customization](https://developers.openai.com/codex/concepts/customization)：将 `AGENTS.md` 定义为持久项目指导，将 Skills 定义为可复用工作流，并明确二者“互补而非竞争”。
- OpenAI, [Custom instructions with AGENTS.md](https://developers.openai.com/codex/guides/agents-md)：说明加载时机、路径发现、合并顺序，以及更靠近当前目录的文件覆盖较早指导。
- OpenAI, [Build skills](https://developers.openai.com/codex/skills)：说明 Skill 的渐进披露、显式/隐式触发、目录结构及用户级/仓库级位置。

记录日期：2026-07-15。

## Anthropic Claude Code 的官方说明

Claude Code 的对应项目指令文件是 `CLAUDE.md`。Anthropic 官方文档明确说明，Claude Code 原生读取 `CLAUDE.md`，而不是 `AGENTS.md`；已有 `AGENTS.md` 的跨 Agent 仓库，可以在 `CLAUDE.md` 中用 `@AGENTS.md` 导入。Windows 上官方也更建议使用导入，而不是依赖需要额外权限的符号链接。

对于 `CLAUDE.md` 与 Skill 的关系，Anthropic 官方给出了以下规则：

- `CLAUDE.md` 用于每次会话都需要知道的规则，包括编码惯例、构建命令和“永远不要做 X”。
- Skill 按需加载，用于参考资料和可调用的工作流。
- 多个 `CLAUDE.md` 是累加进入上下文的，不是简单文件覆盖；冲突时 Claude 使用判断来协调，通常更具体的指令优先。
- 官方同时警告：如果两条规则互相矛盾，Claude 可能任意选择其中一条。因此应定期移除过时或冲突的规则。
- `CLAUDE.md` 和 Skill 都是模型解释执行的提示指令，不是确定性强制层。必须每次成立的约束，应使用 Hook；权限、安全和沙箱则应使用 settings/policy 等客户端强制机制。

Anthropic 公开页面没有给出一条“`CLAUDE.md` 与已加载 `SKILL.md` 冲突时，某文件类型固定胜出”的规则。“更具体通常优先”是模型协调原则，不是可验证的硬优先级保证。

### 自拟方案：不变量—流程—执行三层模型

以下是工程建议，不是 Anthropic 或 OpenAI 已公布的内部算法。

1. **不变量层**：在 `AGENTS.md` / `CLAUDE.md` 中只放跨任务始终成立的约束，例如资料来源、安全边界、禁止修改的目录和最低验证要求。规则应使用 `MUST`、`MUST NOT`、`MAY` 等明确措辞，并给每条重要规则一个稳定 ID。
2. **流程层**：在 `SKILL.md` 中定义任务步骤，但声明它服从哪些不变量，并明确列出前置条件、允许的副作用和遇到冲突时的停止条件。Skill 不得自行创建对不变量的隐式例外。
3. **执行层**：把不能依赖模型判断的规则放进 Hook、权限设置、CI、lint 或策略系统。Prompt 文件负责指导，确定性机制负责阻断。

建议采用显式冲突协议：

```md
## Instruction contract

- Repository invariants: R-001, R-002 always apply.
- This skill does not override repository invariants.
- Authorized exceptions: none.
- On an irreconcilable conflict: do not perform the conflicting action;
  report both instruction IDs and request user resolution.
```

若需要例外，由不变量文件授权，而不是 Skill 单方面宣布：

```md
R-010: 禁止发布到生产环境。
Exception: 用户显式调用 `/deploy-production` 且审批通过时，
该 Skill 可以发布；仍须满足 R-001 安全检查和 R-002 审计记录。
```

这个设计把冲突处理从模糊的“谁更靠近、谁更具体”改成可审查的授权关系：默认无覆盖，例外必须显式授权，硬约束由确定性机制执行。

### Anthropic 官方来源

- Anthropic, [How Claude remembers your project](https://code.claude.com/docs/en/memory)：说明 Claude Code 读取 `CLAUDE.md` 而非 `AGENTS.md`、导入方式、冲突规则可能被任意选择，以及提示指令不是硬强制层。
- Anthropic, [Extend Claude Code](https://code.claude.com/docs/en/features-overview)：说明 `CLAUDE.md` 与 Skills 的职责、冲突时更具体指令通常优先，以及 Hooks 适合确定性约束。
- Anthropic, [Extend Claude with skills](https://code.claude.com/docs/en/slash-commands)：说明 Skill 的加载、作用域、同名 Skill 覆盖规则和显式调用机制。

# 结构化任务对象与 Prompt 的代码边界

## 用户问题

在 CodeAgent 三阶段流水线中，如果输入是包含任务 ID、代码仓版本、材料引用、阶段依赖、工具权限、预算和验收条件的结构化任务对象，代码上应如何实现？如何体现系统不是“一个 Prompt”？

## 核心结论

“不是一个 Prompt”不等于模型完全不接收 Prompt。任何 LLM 调用最终仍会收到消息或序列化上下文。真正的区别是：

- Prompt 只是 Runtime 在某个阶段根据当前状态生成的一次性视图。
- 任务事实、状态、权限、预算、阶段产物和工具执行记录保存在模型上下文之外。
- 阶段选择、依赖判断、预算检查、工具执行、结果校验和状态持久化由确定性代码负责。
- 模型只能生成受 Schema 约束的“决策或候选动作”，不能靠自然语言自行宣布任务已经成功。

可以把关系概括为：

```text
TaskSpec + 持久化状态 + 阶段产物 + 工具结果
                    |
                    v
         Runtime 选择当前阶段和上下文
                    |
                    v
            生成本轮 Prompt / Messages
                    |
                    v
       LLM 输出结构化决策或工具调用请求
                    |
                    v
    权限校验 -> 工具执行 -> 验收 -> 持久化
                    |
                    +------ 下一轮重新装配上下文
```

Anthropic 官方将预定义代码路径中的 LLM 与工具编排称为 workflow，而由 LLM 动态决定过程和工具使用的系统称为 agent。三阶段 CodeAgent 通常是二者的组合：外层阶段和门禁由 workflow 控制，阶段内部允许 Agent 动态检索、修改和修复。官方同时建议从简单、可组合的模式开始，并通过环境反馈和明确的停止条件控制 Agent。[Anthropic：Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)

## 一、领域对象

以下是最小化示例。它们是应用程序中的 Python 对象，可以保存到数据库或 JSON 文件中；它们不是 Prompt 文本。

```python
from enum import StrEnum
from pydantic import BaseModel, Field


class Stage(StrEnum):
    DESIGN = "design"
    PLAN = "plan"
    APPLY = "apply"


class Status(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    RETRYABLE_FAILED = "retryable_failed"
    TERMINAL_FAILED = "terminal_failed"


class AcceptanceRule(BaseModel):
    kind: str
    command: str | None = None
    expected: str | int | bool


class TaskSpec(BaseModel):
    task_id: str
    repo_url: str
    base_commit: str
    requirement_refs: list[str]
    allowed_tools: set[str]
    max_llm_tokens: int
    max_tool_calls: int
    acceptance_rules: list[AcceptanceRule]


class TaskItem(BaseModel):
    item_id: str
    title: str
    target_files: list[str]
    depends_on: list[str] = Field(default_factory=list)
    status: Status = Status.PENDING
    attempts: int = 0


class RunState(BaseModel):
    run_id: str
    task_id: str
    stage: Stage = Stage.DESIGN
    status: Status = Status.PENDING
    design_artifact_id: str | None = None
    plan_artifact_id: str | None = None
    patch_artifact_id: str | None = None
    task_items: list[TaskItem] = Field(default_factory=list)
    used_llm_tokens: int = 0
    used_tool_calls: int = 0
    version: int = 0
```

这里有几个关键点：

1. `base_commit` 是代码操作的事实基线，不允许模型用自然语言改写。
2. `allowed_tools` 是执行器的授权清单，而不是 Prompt 中一句“请不要调用危险工具”。
3. `max_llm_tokens` 和 `max_tool_calls` 由 Runtime 计数并强制停止。
4. `status` 和 `stage` 由状态机改变；不能仅凭模型输出“完成了”就标记成功。
5. `acceptance_rules` 最终由编译器、测试工具或确定性校验器执行。

## 二、持久化接口

Runtime 应通过存储层读取和更新状态。生产系统可以使用 PostgreSQL、事件日志或工作流引擎；示例只展示接口边界。

```python
from typing import Protocol


class RunRepository(Protocol):
    def load_spec(self, task_id: str) -> TaskSpec: ...
    def load_run(self, run_id: str) -> RunState: ...
    def save_run(self, state: RunState, expected_version: int) -> None: ...
    def append_event(self, run_id: str, event: dict) -> None: ...
    def save_artifact(self, run_id: str, kind: str, content: str) -> str: ...
    def load_artifact(self, artifact_id: str) -> str: ...
```

`expected_version` 用于乐观并发控制：只有数据库中的版本仍等于读取时的版本，更新才成功，避免两个 Worker 同时推进同一个任务。

## 三、外层状态机

外层控制流不交给模型自由决定：

```python
class Runtime:
    def __init__(self, repo, llm, tools, validators):
        self.repo = repo
        self.llm = llm
        self.tools = tools
        self.validators = validators

    def step(self, run_id: str) -> RunState:
        state = self.repo.load_run(run_id)
        spec = self.repo.load_spec(state.task_id)
        old_version = state.version

        self._check_budget(spec, state)

        if state.stage == Stage.DESIGN:
            self._run_design(spec, state)
        elif state.stage == Stage.PLAN:
            self._run_plan(spec, state)
        elif state.stage == Stage.APPLY:
            self._run_apply(spec, state)
        else:
            raise ValueError(f"unknown stage: {state.stage}")

        state.version += 1
        self.repo.save_run(state, expected_version=old_version)
        return state
```

`step()` 才是 Harness/Runtime 的主体。它负责读取状态、选择阶段、检查预算、执行阶段逻辑和提交新状态。Prompt 只是 `_run_design()` 等函数内部的一项输入。

## 四、Prompt 是结构化状态的阶段视图

以设计阶段为例：

```python
class DesignDecision(BaseModel):
    summary: str
    affected_domains: list[str]
    missing_information: list[str]
    design_markdown: str


def _run_design(self, spec: TaskSpec, state: RunState) -> None:
    materials = [
        self.tools.execute_readonly("read_requirement", {"ref": ref})
        for ref in spec.requirement_refs
    ]

    messages = build_design_messages(
        task_id=spec.task_id,
        base_commit=spec.base_commit,
        materials=materials,
        acceptance_rules=spec.acceptance_rules,
    )

    decision = self.llm.generate(
        messages=messages,
        output_model=DesignDecision,
        tools=self.tools.schemas(spec.allowed_tools),
    )

    if decision.missing_information:
        state.status = Status.WAITING_APPROVAL
        return

    self.validators.validate_design(decision.design_markdown)
    artifact_id = self.repo.save_artifact(
        state.run_id, "DESIGN.md", decision.design_markdown
    )
    state.design_artifact_id = artifact_id
    state.stage = Stage.PLAN
    state.status = Status.PENDING
```

这里确实生成了 `messages`，但它只是以下内容的投影：

- 当前阶段需要的任务字段；
- 通过工具读取到的需求材料；
- 当前阶段相关的验收规则；
- 本阶段允许使用的工具 Schema。

模型看不到数据库更新权限，也不能直接将 `state.stage` 改成 `PLAN`。只有在结构化输出解析成功、`validate_design()` 通过、产物保存成功后，Runtime 才推进状态。

OpenAI 官方 Agents SDK 将 Agent、工具、handoff、guardrail 和 tracing 作为不同的工程原语；这也说明生产 Agent 的执行边界不等同于一段提示词。[OpenAI：New tools for building agents](https://openai.com/index/new-tools-for-building-agents/)

## 五、工具调用不是让模型直接执行函数

模型返回的是“工具调用请求”，Runtime 才是实际执行者：

```python
class ToolExecutor:
    def __init__(self, registry, call_store):
        self.registry = registry
        self.call_store = call_store

    def execute(
        self,
        *,
        spec: TaskSpec,
        run_id: str,
        step_id: str,
        tool_name: str,
        arguments: dict,
    ) -> dict:
        if tool_name not in spec.allowed_tools:
            raise PermissionError(f"tool not allowed: {tool_name}")

        idempotency_key = f"{run_id}:{step_id}:{tool_name}"
        previous = self.call_store.get_success(idempotency_key)
        if previous is not None:
            return previous.result

        tool = self.registry[tool_name]
        validated_args = tool.input_model.model_validate(arguments)
        result = tool.handler(**validated_args.model_dump())

        self.call_store.record_success(
            idempotency_key=idempotency_key,
            arguments=validated_args.model_dump(),
            result=result,
        )
        return result
```

代码体现了四个 Prompt 无法可靠替代的约束：

- 授权检查；
- 参数 Schema 校验；
- 幂等键；
- 执行结果持久化。

OpenAI Responses API 的工具调用对象具有工具名、JSON 参数和唯一调用 ID，工具输出通过对应调用 ID 返回；这是“模型提出调用，应用执行工具并反馈结果”的接口边界。[OpenAI：Responses API streaming reference](https://platform.openai.com/docs/api-reference/responses-streaming/response/web_search_call)

## 六、Apply 阶段的受控写入

对代码库的写操作可以采用“先生成 Patch，再受控应用”的方式：

```python
def apply_patch_safely(spec, patch, workspace, git):
    current_commit = git.head(workspace)
    if current_commit != spec.base_commit:
        raise RuntimeError("repository baseline changed")

    changed_files = parse_changed_files(patch)
    if any(not is_path_allowed(path) for path in changed_files):
        raise PermissionError("patch touches forbidden path")

    check_patch_syntax(patch)
    git.apply_check(workspace, patch)
    git.apply(workspace, patch)
```

模型只负责生成候选 Patch；基线校验、路径权限和实际写入由代码负责。随后还要执行编译、测试和验收规则。只有这些外部证据通过，任务才能进入 `SUCCEEDED`。

## 七、怎样在面试中证明“不是一个 Prompt”

不建议回答“因为我的 Prompt 很复杂、里面有很多 JSON”。JSON 被拼进 Prompt 仍然可能只是一个 Prompt。

更有说服力的回答是展示四类代码：

1. **领域模型**：`TaskSpec`、`RunState`、`TaskItem`。
2. **状态机**：合法阶段转换、失败分类、重试和人工审批。
3. **执行边界**：工具注册表、权限校验、Schema 校验和幂等控制。
4. **持久化与验证**：阶段产物、事件日志、编译测试结果和状态恢复。

可以这样概括：

> 模型每一轮仍然会接收 Prompt，但 Prompt 不是系统的事实来源。任务状态、权限、预算、阶段产物和工具执行记录都保存在 Runtime 中。Runtime 根据阶段选择最小上下文，模型只返回结构化决策或工具调用请求；真正的执行、校验和状态迁移由确定性代码完成。因此它是“代码控制的工作流加阶段内 Agent 循环”，而不是靠一段 Prompt 从头跑到尾。

## 八、证据边界

- 上述 Python 是解释 Runtime 边界的自拟工程示例，不代表 OpenAI、Anthropic 或候选人的实际内部实现。
- OpenAI 与 Anthropic 官方资料支持工具、状态、编排、guardrail、trace、环境反馈等工程原语，但没有公开候选人 CodeAgent 项目的具体代码。
- 候选人面试时只能采用其项目真实实现过的字段和机制。如果现有系统只是将 JSON 拼入 Prompt，没有独立持久化、权限执行器或状态机，应如实说明当前版本边界和计划演进方向。

## 官方来源

- [Anthropic：Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)
- [Anthropic：Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [OpenAI：New tools for building agents](https://openai.com/index/new-tools-for-building-agents/)
- [OpenAI：Responses API streaming reference](https://platform.openai.com/docs/api-reference/responses-streaming/response/web_search_call)

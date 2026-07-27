# Agent Trace 轻量实现与 Skill 演进数据闭环

> 核查日期：2026-07-20  
> 目标边界：冻结模型参数，不做后训练；Trace 只服务于调试、评测和 Skill 文件优化。OpenAI、Anthropic 机制依据官方文档；通用架构与示例代码为自拟工程方案。

## 一、Agent Trace 到底记录什么

Agent Trace 是一次 Agent 任务从输入到结束的结构化事件记录。它不是思维链日志，也不应试图收集模型未公开的内部推理。应记录的是系统可以直接观察和验证的事件：

- 用户任务及经过脱敏的输入；
- 使用的模型、Agent 配置、Skill 名称和版本；
- Skill 是否被发现、触发、加载了哪些文件；
- 每一次模型请求和响应的可保存部分；
- 工具名称、参数摘要、结果摘要、耗时和错误；
- Agent handoff 或 subagent 调用；
- 文件 diff、命令退出码和测试结果；
- guardrail、权限审批和人工反馈；
- token、成本、延迟；
- 最终输出、grader 分数和任务状态。

最小数据关系是：

```text
Trace：一次完整业务任务
└── Span：任务中的一个有起止时间的操作
    ├── model span
    ├── tool span
    ├── skill span
    ├── validation span
    └── human-feedback span
```

每个 Span 用 `trace_id` 关联同一任务，用 `parent_span_id` 表达嵌套关系。

## 二、与普通日志的区别

| 普通日志 | Agent Trace |
|---|---|
| 主要按时间输出文本 | 结构化事件，可建立父子关系 |
| 通常关注异常 | 同时记录正常决策路径和结果 |
| 难以还原一次完整任务 | `trace_id` 贯穿模型、工具、验证和反馈 |
| 不一定带版本 | 必须绑定模型、Prompt、Skill、工具版本 |
| 不一定可直接评测 | 每次运行可附 grader 和验收结果 |

对 Skill 自演进而言，最重要的不是“日志更多”，而是能回答：**哪一版 Skill 在什么任务上，导致了哪条行为路径，最终为什么成功或失败。**

## 三、最小事件模型

推荐采用 append-only JSONL，每行一个事件。它简单、可流式写入、崩溃后容易恢复，也便于以后导入数据库或 OpenTelemetry。

```json
{
  "schema_version": "1.0",
  "event_id": "evt_01J...",
  "trace_id": "tr_01J...",
  "span_id": "sp_01J...",
  "parent_span_id": "sp_root",
  "sequence": 7,
  "event_type": "tool.end",
  "timestamp": "2026-07-20T13:21:44.182Z",
  "agent": {
    "name": "spreadsheet-agent",
    "version": "0.4.1"
  },
  "model": {
    "provider": "example",
    "name": "frozen-model-id"
  },
  "skill": {
    "name": "spreadsheet-analysis",
    "version": "1.3.0",
    "content_hash": "sha256:..."
  },
  "operation": {
    "name": "validate_workbook",
    "status": "error",
    "duration_ms": 4187
  },
  "input": {
    "summary": "Validate generated workbook",
    "artifact_refs": ["artifact://workbook/sha256:..."]
  },
  "output": {
    "summary": "Formula reference error on sheet Summary",
    "exit_code": 1
  },
  "error": {
    "type": "ValidationError",
    "message_redacted": "Invalid formula reference"
  },
  "privacy": {
    "content_logged": false,
    "redaction_policy": "default-v2"
  }
}
```

### 必需字段

| 字段 | 作用 |
|---|---|
| `trace_id` | 关联一次端到端任务 |
| `span_id` | 标识一个操作 |
| `parent_span_id` | 重建调用树 |
| `sequence` | 并发或时间相同时保持顺序 |
| `event_type` | 区分模型、工具、Skill、验证等事件 |
| `timestamp` | 排序与延迟分析 |
| `status` | `ok/error/cancelled/denied` |
| Skill 版本与 hash | 将行为准确归因到具体 Skill 内容 |
| 输入/输出摘要或引用 | 支撑诊断，不必保存所有原文 |
| privacy policy | 说明是否保存敏感内容及如何脱敏 |

## 四、建议的事件类型

```text
trace.start
trace.end
user.input
skill.available
skill.triggered
skill.loaded
model.start
model.end
tool.start
tool.end
tool.error
permission.requested
permission.decided
agent.handoff
subagent.start
subagent.end
artifact.created
file.diff
validation.result
human.feedback
trace.score
```

Skill 相关事件建议独立记录，而不是只把 Skill 名称写在模型输入中：

```json
{
  "event_type": "skill.loaded",
  "skill": {
    "name": "pdf",
    "version": "2.1.0",
    "content_hash": "sha256:...",
    "loaded_resources": ["SKILL.md", "references/forms.md"]
  },
  "trigger": {
    "mode": "automatic",
    "matched_description": true
  }
}
```

这样可以分别识别：Skill 没有触发、触发但没读关键资源、正确加载但执行失败。

## 五、采集架构

```text
User / Scheduler
       ↓
Agent Runtime
 ├─ model wrapper ──────┐
 ├─ tool wrapper ───────┤
 ├─ skill loader ───────┤ emit(event)
 ├─ validation wrapper ─┤
 └─ feedback endpoint ──┘
                        ↓
                 Non-blocking queue
                        ↓
              Redactor / Normalizer
                        ↓
          JSONL / SQLite / OTLP Collector
                        ↓
        Trace Viewer / Eval / Skill Optimizer
```

核心原则：采集回调不做复杂分析，只快速写入队列；脱敏、上传、评分和 Skill 归纳放在异步处理器中，避免 Trace 系统改变 Agent 的执行行为。

## 六、一个无依赖的 Python 最小实现

以下为自拟示例。它只展示本地 JSONL 事件记录，不依赖任何厂商 SDK。

```python
from __future__ import annotations

import contextvars
import hashlib
import json
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


current_trace_id = contextvars.ContextVar("trace_id", default=None)
current_span_id = contextvars.ContextVar("span_id", default=None)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


class JsonlTraceWriter:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.sequence = 0

    def emit(self, event_type: str, **data: Any) -> None:
        self.sequence += 1
        event = {
            "schema_version": "1.0",
            "event_id": new_id("evt"),
            "trace_id": current_trace_id.get(),
            "span_id": current_span_id.get(),
            "sequence": self.sequence,
            "event_type": event_type,
            "timestamp": utc_now(),
            **data,
        }
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    @contextmanager
    def trace(self, workflow: str, metadata: dict[str, Any]) -> Iterator[str]:
        trace_id = new_id("tr")
        token = current_trace_id.set(trace_id)
        try:
            self.emit("trace.start", workflow=workflow, metadata=metadata)
            yield trace_id
            self.emit("trace.end", workflow=workflow, status="ok")
        except Exception as exc:
            self.emit(
                "trace.end",
                workflow=workflow,
                status="error",
                error={"type": type(exc).__name__},
            )
            raise
        finally:
            current_trace_id.reset(token)

    @contextmanager
    def span(self, operation: str, kind: str, **attributes: Any) -> Iterator[str]:
        span_id = new_id("sp")
        parent_span_id = current_span_id.get()
        token = current_span_id.set(span_id)
        started = time.perf_counter()
        try:
            self.emit(
                f"{kind}.start",
                parent_span_id=parent_span_id,
                operation=operation,
                attributes=attributes,
            )
            yield span_id
            self.emit(
                f"{kind}.end",
                parent_span_id=parent_span_id,
                operation=operation,
                status="ok",
                duration_ms=round((time.perf_counter() - started) * 1000),
            )
        except Exception as exc:
            self.emit(
                f"{kind}.end",
                parent_span_id=parent_span_id,
                operation=operation,
                status="error",
                duration_ms=round((time.perf_counter() - started) * 1000),
                error={"type": type(exc).__name__},
            )
            raise
        finally:
            current_span_id.reset(token)
```

使用方式：

```python
writer = JsonlTraceWriter("traces/run.jsonl")
skill_text = Path("skills/pdf/SKILL.md").read_text(encoding="utf-8")

with writer.trace(
    "pdf-form-workflow",
    metadata={
        "skill.name": "pdf",
        "skill.version": "2.1.0",
        "skill.hash": content_hash(skill_text),
    },
):
    with writer.span("load-pdf-skill", "skill"):
        writer.emit(
            "skill.loaded",
            skill={
                "name": "pdf",
                "version": "2.1.0",
                "content_hash": content_hash(skill_text),
            },
        )

    with writer.span("extract-form-fields", "tool", tool_name="extract_fields"):
        result = extract_fields("input.pdf")
        writer.emit(
            "validation.result",
            validator="required-fields",
            passed=result.required_fields_present,
        )
```

生产环境应将逐行文件写入改成内存队列加后台批量写入，避免并发竞争和 I/O 阻塞。

## 七、包装模型和工具调用

### 模型 Wrapper

```python
async def traced_model_call(client, request, writer):
    with writer.span("generate", "model", model=request.model):
        safe_input = summarize_and_redact(request.messages)
        writer.emit("model.input", input=safe_input)

        response = await client.generate(request)

        writer.emit(
            "model.output",
            response_id=response.id,
            finish_reason=response.finish_reason,
            usage=response.usage,
            output=summarize_and_redact(response.output),
        )
        return response
```

### Tool Wrapper

```python
async def traced_tool_call(tool, arguments, writer):
    with writer.span(tool.name, "tool", tool_name=tool.name):
        writer.emit("tool.input", input=redact_tool_args(tool.name, arguments))
        try:
            result = await tool(arguments)
        except Exception as exc:
            writer.emit(
                "tool.error",
                tool_name=tool.name,
                error_type=type(exc).__name__,
            )
            raise

        writer.emit("tool.output", output=summarize_tool_result(result))
        return result
```

不要默认保存完整 prompt、文件内容、密钥、cookie、数据库结果或工具输出。多数 Skill 演进只需要错误类型、操作摘要、artifact hash 和 validator 结果。

## 八、OpenAI 官方实现

OpenAI Agents SDK 默认记录完整 Agent workflow，并把以下内容表示成 span：Runner、task、turn、agent、generation、function tool、guardrail、handoff 和音频操作；也支持 custom span。Trace 含 `workflow_name`、`trace_id`、可选 `group_id` 和 metadata；Span 含起止时间、`trace_id`、`parent_id` 与不同类型的 `span_data`。[OpenAI Agents SDK Tracing](https://openai.github.io/openai-agents-python/tracing/)

多个并发操作通过 Python `contextvar` 维护当前 Trace/Span 和父子关系。默认 `BatchTraceProcessor` 后台批量导出，也可用 `add_trace_processor()` 增加自己的处理器，或用 `set_trace_processors()` 完全替换默认处理器。[OpenAI Tracing API](https://openai.github.io/openai-agents-python/ref/tracing/)

### 用自定义 Processor 落本地数据

官方处理器接口提供：

```text
on_trace_start
on_trace_end
on_span_start
on_span_end
shutdown
force_flush
```

`on_span_end` 适合把已完成 Span 放进本地队列，但官方要求回调快速返回、不要阻塞、不要抛异常。[OpenAI Processor interface](https://openai.github.io/openai-agents-python/ref/tracing/processor_interface/)

需要特别注意，OpenAI SDK 的 generation/function span 可能包含模型和工具输入输出；可通过 `RunConfig.trace_include_sensitive_data` 禁止捕获敏感数据。官方文档说明其默认值为 `True`，生产部署应显式检查并配置。[OpenAI Agents SDK Tracing](https://openai.github.io/openai-agents-python/tracing/)

## 九、Anthropic 官方实现

### Claude Code Hooks

Claude Code Hooks 可以在 Session、用户提交、工具调用前后、工具失败、权限请求、停止、压缩等生命周期事件触发命令或 HTTP handler。Hook 通过 stdin 或 HTTP POST 接收结构化 JSON，常见字段包括 `session_id`、`cwd`、`hook_event_name`、`tool_name`、`tool_input` 和 `tool_use_id`。[Claude Code Hooks reference](https://code.claude.com/docs/en/hooks)；[Hooks guide](https://code.claude.com/docs/en/hooks-guide)

用于 Trace 时，最有用的是：

- `SessionStart/SessionEnd`：Trace 边界；
- `UserPromptSubmit`：输入事件；
- `PreToolUse`：工具意图和参数；
- `PostToolUse`：工具成功结果；
- `PostToolUseFailure`：错误、是否中断、耗时；
- `PermissionRequest`：权限决策；
- `SubagentStop/Stop`：子任务和任务终止；
- `PreCompact`：上下文压缩边界。

Hooks 输入中还可能包含 `transcript_path`，可作为完整会话记录的位置引用；但不建议无差别复制 transcript 到演进数据集。

### OpenTelemetry

Claude Code 官方支持通过 OpenTelemetry 导出使用、成本、工具活动以及增强的 span tracing。启用 trace 需要显式配置 telemetry、enhanced telemetry beta 和 `OTEL_TRACES_EXPORTER`。官方说明 trace 默认会脱敏用户提示、工具输入细节和工具内容；只有显式开启相关配置才包含原文。[Claude Code Monitoring](https://code.claude.com/docs/en/monitoring-usage)

Agent SDK 也能使用 CLI 内置的 OpenTelemetry instrumentation，记录模型请求和工具执行 Span、token/cost metrics 及结构化事件。[Anthropic Agent SDK observability](https://code.claude.com/docs/en/agent-sdk/observability)

## 十、Trace 如何服务 Skill 自演进

不要直接把全部 Trace 交给优化器。先转成可控的 `SkillEvidence`：

```json
{
  "trace_id": "tr_01J...",
  "skill": {
    "name": "spreadsheet-analysis",
    "version": "1.3.0",
    "hash": "sha256:..."
  },
  "task_category": "formula-repair",
  "outcome": "failed",
  "failure_stage": "validation",
  "failure_code": "FORMULA_REF_ERROR",
  "trajectory_summary": [
    "loaded SKILL.md",
    "edited workbook",
    "did not run bundled validator",
    "final artifact failed formula check"
  ],
  "validator": {
    "name": "workbook-integrity",
    "score": 0,
    "evidence_ref": "artifact://validation/sha256:..."
  },
  "privacy_review": "passed"
}
```

然后按批次寻找重复模式：

```text
原始 Trace
   ↓ 脱敏、标准化、去重
SkillEvidence
   ↓ 按 skill_hash + task_category + failure_code 聚类
重复失败模式
   ↓ LLM 生成最小 Skill diff
候选 Skill
   ↓ 使用独立 eval set 回归
接受或拒绝
```

### 必须绑定 Skill hash

只记录 `skill.name` 不够。同名 Skill 会发生变化，归因时必须记录内容 hash。否则 v1.2 的失败可能被错误归到 v1.4。

### 只沉淀可泛化行为

适合写入 Skill：

- 多次失败都缺少同一个验证步骤；
- Agent 经常使用错误的工具顺序；
- 某类错误需要明确恢复流程；
- description 导致稳定的漏触发或误触发。

不适合写入 Skill：

- 单个用户的具体数据；
- 某个 benchmark 的答案；
- 一次网络抖动或偶发服务错误；
- 已在模型或工具更新中修复的问题；
- 无法从可观察证据确认的“模型想法”。

## 十一、隐私和安全

### 默认不记录

- API key、OAuth token、cookie、密码；
- 完整用户隐私数据和企业机密；
- 未脱敏文件内容；
- 隐藏思维链；
- 工具返回的整份数据库或邮箱内容；
- 超出评测需要的会话历史。

### 推荐保存引用而非内容

大型产物存到受控 artifact store，Trace 只保存：

```text
artifact URI + SHA-256 + MIME type + size + access policy
```

### 保留策略

为不同数据分层设置 TTL：

- 原始敏感 Trace：短期或不落盘；
- 脱敏事件：中期调试；
- 聚合指标：长期；
- 被选为 Skill 改进证据的样本：单独审批和版本化。

## 十二、推荐的最小落地方案

对于只想实现轻量 Skill 演进的团队，不需要先上完整 OpenTelemetry 平台：

1. 为每次任务生成 `trace_id`；
2. 包装 Skill loader、model client、tool executor 和 validator；
3. 用 JSONL append-only 记录结构化事件；
4. 默认只保存摘要、错误码、耗时、token 和 artifact hash；
5. 每次 Trace 记录 `skill.name/version/hash`；
6. 任务结束生成一条确定性 `validation.result`；
7. 定期把失败 Trace 转成脱敏 `SkillEvidence`；
8. 相同失败至少重复出现若干次才允许生成候选 Skill diff；
9. 候选版在独立 eval set 上严格改善才保存；
10. 自动化终点为 diff/PR，不直接覆盖生产 Skill。

起步时用 JSONL；当需要跨服务关联、实时图形界面和大规模查询时，再将相同事件模型映射到 OpenTelemetry：

```text
trace_id      → OTel TraceId
span_id       → OTel SpanId
parent_span_id→ Parent SpanId
event_type    → Span name / Span event
attributes    → OTel attributes
duration      → Span start/end
```

## 十三、验收标准

一个 Agent Trace 实现至少应通过：

- 能重建一次任务的模型—工具—验证调用树；
- 并发工具调用不会串到其他 Trace；
- 每个结果能定位到准确 Skill hash；
- Agent 崩溃时已写事件仍可读取；
- Trace writer 故障不会导致 Agent 主任务失败；
- 默认数据中不存在密钥和原始敏感内容；
- 能从 Trace 自动生成失败阶段和错误码；
- 同一 eval 在 Skill vN/vN+1 间可以进行可比回归；
- 可删除特定用户或特定 Trace 的数据；
- 事件 schema 有版本，未来可以迁移。

## 十四、最终结论

Agent Trace 的本质不是录下 Agent 的所有文字，而是建立一份**可关联、可验证、可脱敏、可比较的执行事件账本**。对于轻量 Skill 自演进，最小充分数据是：

```text
任务类别
+ Skill version/hash
+ 可观察行为路径
+ 工具成功/失败
+ 最终 validator 结果
+ 成本与延迟
+ 人工反馈（如有）
```

有了这些数据，普通 LLM 推理就能从重复失败中提出 Skill 小步修改；不需要访问隐藏思维链，也不需要任何模型参数更新或后训练。

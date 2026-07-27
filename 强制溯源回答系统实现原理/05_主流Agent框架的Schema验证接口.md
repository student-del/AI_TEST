# 主流 Agent 框架的 Schema 验证接口

> 调研时间：2026-07-14。框架接口会随版本变化，使用时应核对对应版本的官方文档。

## 核心结论

目前主流 Agent 框架普遍提供现成的结构化输出接口，但它们通常不是暴露一个名为 `SchemaValidator` 的统一组件，而是让开发者声明 Pydantic、Zod、dataclass、TypedDict 或 JSON Schema，然后在 Agent 输出或工具调用边界自动完成：

```text
类型定义
  -> 生成 JSON Schema
  -> 交给模型的 Structured Output / Tool Calling
  -> 解析模型返回的 JSON
  -> 本地类型验证
  -> 返回类型化对象，失败则异常或重试
```

如果已经持有一份原生 JSON Schema，并需要独立校验任意 JSON，通常仍直接使用 Python `jsonschema`、Pydantic `TypeAdapter` 或 JavaScript AJV/Zod，而不是启动一个 Agent。

## 框架对照

| 框架 | 主要接口 | Schema 表达 | 本地验证/失败处理 |
|---|---|---|---|
| OpenAI Agents SDK | `Agent(output_type=...)` | Pydantic、dataclass、TypedDict 等 | `AgentOutputSchema.validate_json()`；Pydantic TypeAdapter 解析验证 |
| LangChain Python | `create_agent(response_format=...)` | Pydantic、dataclass、TypedDict、JSON Schema | 捕获并验证为 `structured_response`；工具策略支持错误反馈与重试 |
| LangChain JS/TS | `createAgent({responseFormat})`、`withStructuredOutput()` | Zod、Standard Schema、JSON Schema | Zod/Standard Schema 自动验证；原生 JSON Schema 某些模型级接口需自行验证 |
| Pydantic AI | `Agent(output_type=...)` | Pydantic 模型及 Python 类型 | 用 Pydantic 生成 Schema 并验证返回数据；支持 output validator 和 `ModelRetry` |
| LlamaIndex | `output_cls=...`、`structured_output_fn=...` | Pydantic 模型 | 输出可转 Pydantic；自定义函数可验证或重写最终结果 |

## 一、OpenAI Agents SDK

最直接的接口是 `output_type`：

```python
from pydantic import BaseModel, Field
from agents import Agent, Runner

class Claim(BaseModel):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)

agent = Agent(
    name="citation_agent",
    instructions="回答必须绑定证据 ID",
    output_type=Claim,
)

result = Runner.run_sync(agent, "回答问题")
claim: Claim = result.final_output
```

官方文档说明 `output_type` 可以使用能被 Pydantic `TypeAdapter` 包装的类型。SDK 的 `AgentOutputSchemaBase` 同时暴露 `json_schema()` 和 `validate_json()`，后者负责把模型产生的 JSON 验证并解析为目标类型；严格 Schema 默认开启，也可以自定义 Schema 实现。

适合：使用 OpenAI Agents SDK，并希望 Agent 最终输出直接成为类型化对象。

官方资料：

- <https://openai.github.io/openai-agents-python/agents/#output-types>
- <https://openai.github.io/openai-agents-python/ref/agent_output/>

## 二、LangChain Python

LangChain 的 Agent 接口通过 `response_format` 声明结构：

```python
from pydantic import BaseModel, Field
from langchain.agents import create_agent

class Claim(BaseModel):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)

agent = create_agent(
    model="...",
    tools=[...],
    response_format=Claim,
)

state = agent.invoke({
    "messages": [{"role": "user", "content": "回答问题"}]
})

claim = state["structured_response"]
```

LangChain 根据模型能力选择两条路径：

- `ProviderStrategy`：使用提供商原生 Structured Output，通常可靠性更高。
- `ToolStrategy`：把目标结构包装成工具参数；校验失败后可以把错误反馈给模型并重试。

这意味着 LangChain 同时封装了 Schema 传递、模型输出捕获、本地验证和部分重试逻辑。

官方资料：<https://docs.langchain.com/oss/python/langchain/structured-output>

## 三、LangChain JavaScript / TypeScript

JS 版本通常使用 Zod：

```typescript
import * as z from "zod";
import { createAgent, providerStrategy } from "langchain";

const Claim = z.object({
  text: z.string().min(1),
  evidence_ids: z.array(z.string()).min(1),
});

const agent = createAgent({
  model: "...",
  tools: [],
  responseFormat: providerStrategy(Claim),
});

const result = await agent.invoke({
  messages: [{ role: "user", content: "回答问题" }],
});

console.log(result.structuredResponse);
```

`responseFormat` 支持 Zod、Standard Schema 和 JSON Schema。官方文档特别指出：Zod 和 Standard Schema 对象可以在运行时自动验证；在某些模型级 `withStructuredOutput` 用法中，若只传原生 JSON Schema，则仍需要开发者自行做本地验证。需要按具体入口区分，不能笼统认为“传了 JSON Schema 就一定做了本地校验”。

官方资料：

- <https://docs.langchain.com/oss/javascript/langchain/structured-output>
- <https://docs.langchain.com/oss/javascript/langchain/models#structured-output>

## 四、Pydantic AI

Pydantic AI 将 Pydantic 验证作为核心能力：

```python
from pydantic import BaseModel, Field
from pydantic_ai import Agent

class Claim(BaseModel):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)

agent = Agent("provider:model", output_type=Claim)
result = agent.run_sync("回答问题")

claim: Claim = result.output
```

官方文档说明，结构化输出使用 Pydantic 生成工具所需的 JSON Schema，并用 Pydantic 验证模型返回的数据。它支持 Tool Output、模型原生 Native Output 和 Prompted Output 三种模式，还可以用 output validator 增加跨字段或业务规则；验证失败时可通过 `ModelRetry` 让模型重新生成。

适合：Python 项目希望把类型验证、自定义 validator 和 Agent 重试紧密组合。

官方资料：<https://pydantic.dev/docs/ai/core-concepts/output/>

## 五、LlamaIndex

LlamaIndex 的 Agent/Workflow 支持：

- `output_cls`：指定 Pydantic 输出模型；
- `structured_output_fn`：提供自定义函数，把对话结果验证或重写成目标结构。

```python
from pydantic import BaseModel, Field
from llama_index.core.agent.workflow import FunctionAgent

class Claim(BaseModel):
    text: str = Field(min_length=1)
    evidence_ids: list[str] = Field(min_length=1)

agent = FunctionAgent(
    llm=llm,
    tools=tools,
    output_cls=Claim,
)
```

适合：系统主体是 LlamaIndex 的 RAG、AgentWorkflow，并希望最终输出直接映射为 Pydantic 模型。

官方资料：<https://developers.llamaindex.ai/python/framework/understanding/agent/structured_output/>

## 六、框架接口不能替代哪些验证

框架自带接口主要保证结构和类型，例如：

```text
evidence_ids 存在
evidence_ids 是数组
数组至少有一个字符串
枚举值属于允许集合
```

它通常不能独立保证：

```text
证据 ID 在数据库中仍存在
证据版本适用于当前时间和地区
当前用户有权引用该文档
证据内容真的支持 claim
多个 claim 是否遗漏引用
```

因此强制溯源系统仍应分层：

```text
Agent Structured Output
  -> Pydantic / Zod / JSON Schema 本地校验
  -> evidence ID 数据库校验
  -> claim-evidence 语义验证
  -> 发布闸门
```

## 七、选型建议

- Python + OpenAI Agents SDK：优先 `output_type=PydanticModel`。
- Python + 多模型编排：LangChain `response_format`，明确选择 Provider 或 Tool Strategy。
- Python + 强业务校验：Pydantic AI 的 `output_type` 加 output validator 较自然。
- TypeScript：优先 Zod；它同时承担类型推导和运行时验证。
- LlamaIndex RAG：使用 `output_cls`，复杂校验放入 `structured_output_fn` 或后置业务节点。
- 已有原生 JSON Schema：在 Agent 框架之外再运行标准 validator；Python 可用 `jsonschema`，Node.js 可用 AJV。


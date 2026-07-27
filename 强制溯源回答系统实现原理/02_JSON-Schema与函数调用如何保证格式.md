# JSON Schema 与函数调用如何保证格式

## 关键区别

> JSON Schema 负责定义“什么格式合法”；函数调用负责把结构化数据放进专用通道；真正的强制保证来自约束解码或应用程序校验。

## 一、JSON Schema 怎么保证格式

JSON Schema 本身不能主动保证格式。它只是一份声明式规则，例如：

```json
{
  "type": "object",
  "properties": {
    "text": { "type": "string" },
    "evidence_ids": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 1
    }
  },
  "required": ["text", "evidence_ids"],
  "additionalProperties": false
}
```

它规定输出必须是对象，必须包含 `text` 和非空的 `evidence_ids` 数组，并禁止额外字段。Schema 必须由以下机制执行才会形成保证。

### 1. 生成后校验

```text
模型自由生成
  -> 解析 JSON
  -> Schema validator 校验
  -> 合法则接受；非法则丢弃、重试或拒答
```

```python
result = model.generate(prompt)

try:
    data = json.loads(result)
    validate(instance=data, schema=claim_schema)
except (JSONDecodeError, ValidationError):
    retry_or_reject()
```

这种方式保证的是“非法结果不会进入后续业务”，而不是“模型第一次一定生成合法结果”。如果重试次数耗尽，系统必须拒答，不能继续使用非法数据。

### 2. 生成时约束解码

LLM 每一步会为整个词表输出 logits。推理引擎把 JSON Schema 编译成 grammar、FSM 或 PDA，根据当前状态屏蔽所有不合法 token：

```text
模型输出 logits
  -> 约束引擎计算当前合法 token
  -> 非法 token 的 logit 设为负无穷
  -> 只从合法 token 中采样
```

例如当前已经生成：

```json
{
  "text": "法规自 1 月 1 日生效"
```

由于 `evidence_ids` 是必填字段，在它出现前，状态机不允许模型用 `}` 结束对象。进入 `evidence_ids` 后，因为其类型是数组，只允许先生成 `[`，不能生成对象、字符串或 `null`。

在推理引擎正确实现、生成正常完成且使用受支持 Schema 子集的前提下，这可以保证输出结构合法。但它仍不能保证内容语义正确。

## 二、怎么限制 evidence ID 不能编造

下面的 Schema 只能要求数组元素是字符串：

```json
"items": { "type": "string" }
```

因此模型仍可以输出格式正确但虚构的 ID。若本次检索只返回三个证据，可以动态生成枚举：

```json
{
  "type": "array",
  "items": {
    "type": "string",
    "enum": [
      "doc-17#p42",
      "doc-21#p8",
      "doc-36#p15"
    ]
  },
  "minItems": 1
}
```

约束解码后，模型只能从这三个 ID 中选择。它可以保证 ID 来自本次检索结果且引用非空，但不能保证所选文档真的支持 `claim.text`，后者仍需要语义验证。

## 三、函数调用怎么保证

函数调用通常不是模型直接执行函数，而是生成“工具名 + 参数”：

```json
{
  "name": "submit_claim",
  "arguments": {
    "text": "某法规已经生效",
    "evidence_ids": ["doc-17#p42"]
  }
}
```

实际流程是：

```text
模型生成工具名和参数
  -> API 封装为 tool_call
  -> 应用程序解析 arguments
  -> 校验参数
  -> 通过后才调用真实函数
```

函数定义中的 `parameters` 本质上仍是 JSON Schema。函数调用包含三个互相独立的保证维度。

### 1. 是否保证调用函数

`tool_choice="required"` 表示必须选择某个工具；指定具体函数则表示必须选择该函数。它只保证走工具通道，不保证参数正确。`auto` 模式下模型还可能完全不调用工具。

### 2. 是否保证参数符合 Schema

只有服务明确提供 strict structured outputs，并在生成过程中执行约束时，才能承诺受支持 Schema 范围内的参数结构。普通 tool calling 仍可能漏字段或产生类型错误，必须进行应用侧校验。

### 3. 是否保证真实函数安全

即使参数格式正确，也不代表业务操作合理。宿主程序仍须检查：

- 参数值和资源是否真实存在；
- evidence ID 是否属于当前检索结果；
- 证据是否支持对应 claim；
- 当前用户是否有权限；
- 操作是否需要人工批准；
- 是否存在提示注入或越权风险。

```python
call = model_response.tool_call

if call.name != "submit_claim":
    reject()

args = parse_json(call.arguments)
validate(args, claim_schema)

if not evidence_exists(args["evidence_ids"]):
    reject()

if not evidence_supports_claim(args["text"], args["evidence_ids"]):
    reject()

submit_claim(args)
```

## 四、各机制的保证边界

| 机制 | 能保证 | 不能保证 |
|---|---|---|
| JSON Schema | 定义合法数据集合 | 自己不会执行约束 |
| 事后校验 | 非法结果不进入业务 | 首次生成一定合法 |
| 约束解码 | 生成结果结构合法 | 内容事实正确 |
| 函数调用通道 | 区分工具参数与普通文本 | 参数一定正确 |
| `tool_choice=required` | 必须选择工具 | 参数符合 Schema |
| strict function calling | 参数满足受支持的 Schema | 参数业务上合理 |
| 语义验证器 | 检查证据是否支持事实 | 来源本身绝对正确 |

最可靠的组合是：

```text
强制选择函数
+ strict JSON Schema
+ 应用侧再次校验
+ evidence ID 存在性检查
+ claim 与 evidence 的语义验证
+ 失败时不执行、不发布
```


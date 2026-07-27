# JSON Schema Validator 校验实现

## 核心结论

Schema validator 是一个确定性程序。它接收两个输入：Schema 和待校验的数据实例，然后递归遍历 Schema 中的关键字，对实例执行类型、字段、数量、取值和组合规则检查。

```text
validate(schema, instance)
  -> 解析 Schema 方言和引用
  -> 按类型执行对应关键字
  -> 递归校验对象属性和数组元素
  -> 汇总带路径的错误
  -> 返回 valid / invalid
```

它只能判断结构和值是否满足 Schema，不能判断 `claim.text` 是否真实，也不能判断证据是否支持 claim。

## 一、校验器的输入与输出

Schema：

```json
{
  "type": "object",
  "properties": {
    "text": { "type": "string", "minLength": 1 },
    "evidence_ids": {
      "type": "array",
      "items": {
        "type": "string",
        "enum": ["doc-17#p42", "doc-21#p8"]
      },
      "minItems": 1,
      "uniqueItems": true
    }
  },
  "required": ["text", "evidence_ids"],
  "additionalProperties": false
}
```

实例：

```json
{
  "text": "该法规已经生效",
  "evidence_ids": ["doc-99#p1"]
}
```

校验结果可以表示为：

```json
{
  "valid": false,
  "errors": [
    {
      "instancePath": "/evidence_ids/0",
      "schemaPath": "/properties/evidence_ids/items/enum",
      "keyword": "enum",
      "message": "value is not one of the allowed values"
    }
  ]
}
```

`instancePath` 指向数据中出错的位置；`schemaPath` 指向被违反的规则。

## 二、核心递归算法

一个简化校验器可以写成：

```python
def validate(schema, value, path="$", root_schema=None):
    errors = []

    if "$ref" in schema:
        target = resolve_ref(root_schema, schema["$ref"])
        return validate(target, value, path, root_schema)

    if "type" in schema and not matches_type(value, schema["type"]):
        return [error(path, "type", schema["type"], value)]

    if "enum" in schema and value not in schema["enum"]:
        errors.append(error(path, "enum", schema["enum"], value))

    if isinstance(value, dict):
        errors += validate_object(schema, value, path, root_schema)

    if isinstance(value, list):
        errors += validate_array(schema, value, path, root_schema)

    if isinstance(value, str):
        errors += validate_string(schema, value, path)

    if is_json_number(value):
        errors += validate_number(schema, value, path)

    errors += validate_combinators(schema, value, path, root_schema)
    return errors
```

真实实现还要处理 Schema 方言、布尔 Schema、动态引用、正则规范、Unicode 长度、数值精度和循环引用等问题。

## 三、对象如何校验

以对象为例，校验器通常执行：

1. `type: object`：实例必须是 JSON object。
2. `required`：逐个检查必填键是否存在。
3. `properties`：对已出现的已知字段递归调用 `validate`。
4. `additionalProperties`：处理未在 `properties` 中声明的字段。
5. `minProperties` / `maxProperties`：检查字段数量。
6. `dependentRequired` 等：检查字段之间的依赖。

简化实现：

```python
def validate_object(schema, obj, path, root):
    errors = []
    properties = schema.get("properties", {})

    for name in schema.get("required", []):
        if name not in obj:
            errors.append(error(path, "required", name, None))

    for name, value in obj.items():
        child_path = f"{path}.{name}"

        if name in properties:
            errors += validate(properties[name], value, child_path, root)
        elif schema.get("additionalProperties") is False:
            errors.append(error(child_path, "additionalProperties", False, value))
        elif isinstance(schema.get("additionalProperties"), dict):
            errors += validate(
                schema["additionalProperties"], value, child_path, root
            )

    return errors
```

注意：`required` 只检查键是否存在，不检查字符串是否为空。若 `text` 不能是空字符串，还需要 `minLength: 1`。

## 四、数组如何校验

对于 `evidence_ids`，校验器会执行：

```python
def validate_array(schema, array, path, root):
    errors = []

    if len(array) < schema.get("minItems", 0):
        errors.append(error(path, "minItems", schema["minItems"], len(array)))

    if "maxItems" in schema and len(array) > schema["maxItems"]:
        errors.append(error(path, "maxItems", schema["maxItems"], len(array)))

    if schema.get("uniqueItems") and contains_duplicates(array):
        errors.append(error(path, "uniqueItems", True, array))

    if "items" in schema:
        for index, item in enumerate(array):
            errors += validate(schema["items"], item, f"{path}[{index}]", root)

    return errors
```

因此，对于：

```json
"evidence_ids": ["doc-17#p42", "doc-99#p1"]
```

第一个元素通过 `type` 和 `enum`；第二个元素在路径 `/evidence_ids/1` 违反 `enum`。

## 五、组合规则如何校验

组合关键字本质上是对子 Schema 的多次递归调用：

- `allOf`：所有子 Schema 都必须通过。
- `anyOf`：至少一个通过。
- `oneOf`：必须恰好一个通过。
- `not`：子 Schema 必须不通过。
- `if` / `then` / `else`：先校验条件，再选择对应分支。

```python
def validate_combinators(schema, value, path, root):
    errors = []

    if "allOf" in schema:
        for child in schema["allOf"]:
            errors += validate(child, value, path, root)

    if "anyOf" in schema:
        results = [validate(child, value, path, root)
                   for child in schema["anyOf"]]
        if all(result for result in results):
            errors.append(error(path, "anyOf", "at least one match", value))

    if "oneOf" in schema:
        match_count = sum(
            not validate(child, value, path, root)
            for child in schema["oneOf"]
        )
        if match_count != 1:
            errors.append(error(path, "oneOf", "exactly one match", value))

    return errors
```

`oneOf` 不是“至少一个”，而是“恰好一个”。若两个分支同时匹配，仍然失败。

## 六、`$ref` 如何实现

`$ref` 用来复用 Schema：

```json
{
  "$defs": {
    "evidenceId": {
      "type": "string",
      "pattern": "^doc-[0-9]+#p[0-9]+$"
    }
  },
  "properties": {
    "evidence_ids": {
      "type": "array",
      "items": { "$ref": "#/$defs/evidenceId" }
    }
  }
}
```

校验器把 `#/$defs/evidenceId` 当作 JSON Pointer，从根 Schema 找到目标节点，然后用该节点继续递归校验。真实校验器通常会缓存已经解析的引用，并检测不终止的循环引用。

远程 `$ref` 还涉及网络访问和供应链风险。高安全系统通常预加载并固定允许的 Schema，禁止校验过程中任意访问外部 URL。

## 七、为什么要先验证 Schema 自己

待校验的数据叫 instance，而描述 Schema 合法性的 Schema 叫 meta-schema。正规校验器通常先根据 `$schema` 判断方言，例如 Draft 2020-12，再用对应 meta-schema 检查规则文件本身。

如果把关键字拼成 `require` 而不是 `required`，某些实现会把它当作未知注解忽略，而不是自动猜测。因此应在部署时执行 Schema 自检，并固定使用的方言和 validator 版本。

## 八、生产系统的实际执行顺序

```text
1. 接收模型输出字符串
2. JSON parser：检查是不是合法 JSON
3. Schema validator：检查结构和值约束
4. 业务 validator：检查 ID 是否存在、权限和状态
5. 语义 validator：检查证据是否支持 claim
6. 全部通过才发布或执行
```

这四类问题必须区分：

| 输入 | JSON 解析 | Schema 校验 | 业务/语义校验 |
|---|---:|---:|---:|
| 缺少右花括号 | 失败 | 不执行 | 不执行 |
| 缺少 `evidence_ids` | 通过 | 失败 | 不执行 |
| ID 格式正确但数据库不存在 | 通过 | 可能通过 | 业务校验失败 |
| ID 存在但证据不支持 claim | 通过 | 通过 | 语义校验失败 |

所以 Schema validator 的准确定位是：**确定性地判断数据是否属于 Schema 所描述的合法结构集合，它是发布闸门的一层，但不是事实核验器。**


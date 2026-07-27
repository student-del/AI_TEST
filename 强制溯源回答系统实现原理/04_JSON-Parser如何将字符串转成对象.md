# JSON Parser 如何将字符串转成对象

## 核心结论

JSON parser 是一个确定性的语法解析程序。它读取字符串中的字符，按照 JSON grammar 识别值、对象、数组、字符串、数字、布尔值和 `null`，并构造宿主语言中的内存对象。

```text
JSON 字符串
  -> 字符读取 / 词法识别
  -> 递归下降语法解析
  -> 构造内存对象
  -> 返回结果或语法错误
```

它只回答“这是不是合法 JSON，以及对应什么数据结构”，不检查 `required`、`enum` 等 Schema 规则，也不判断内容是否真实。

## 一、JSON 的核心语法

JSON 可以简化为以下 grammar：

```text
value  := object | array | string | number | true | false | null
object := '{' members? '}'
members := pair (',' pair)*
pair   := string ':' value
array  := '[' elements? ']'
elements := value (',' value)*
```

这套语法具有递归性：对象的字段值可以是另一个对象或数组，数组元素也可以继续包含对象或数组。

## 二、字符如何变成语言对象

常见映射为：

| JSON | Python | JavaScript |
|---|---|---|
| object | `dict` | 普通 object |
| array | `list` | `Array` |
| string | `str` | `string` |
| number | `int` / `float` | `number` |
| `true` / `false` | `True` / `False` | `true` / `false` |
| `null` | `None` | `null` |

例如：

```json
{"text":"已生效","evidence_ids":["doc-17#p42"]}
```

在 Python 中会构造成：

```python
{
    "text": "已生效",
    "evidence_ids": ["doc-17#p42"]
}
```

## 三、典型实现：游标 + 递归下降

解析器维护两个核心状态：输入字符串 `text` 和当前字符位置 `pos`。

```python
class JsonParser:
    def __init__(self, text):
        self.text = text
        self.pos = 0

    def peek(self):
        if self.pos >= len(self.text):
            return None
        return self.text[self.pos]

    def consume(self, expected=None):
        ch = self.peek()
        if expected is not None and ch != expected:
            self.fail(f"expected {expected}, got {ch}")
        self.pos += 1
        return ch
```

顶层 `parse` 先解析一个 JSON value，然后确认后面除了空白没有多余字符：

```python
def parse(self):
    self.skip_whitespace()
    result = self.parse_value()
    self.skip_whitespace()

    if self.pos != len(self.text):
        self.fail("unexpected trailing characters")

    return result
```

如果不做末尾检查，`{"a":1} malicious text` 可能被错误地接受为合法输入。

## 四、`parse_value` 如何分派

解析器查看当前字符就可以决定进入哪个子解析函数：

```python
def parse_value(self):
    self.skip_whitespace()
    ch = self.peek()

    if ch == '{':
        return self.parse_object()
    if ch == '[':
        return self.parse_array()
    if ch == '"':
        return self.parse_string()
    if ch == '-' or (ch is not None and ch.isdigit()):
        return self.parse_number()
    if self.starts_with("true"):
        self.pos += 4
        return True
    if self.starts_with("false"):
        self.pos += 5
        return False
    if self.starts_with("null"):
        self.pos += 4
        return None

    self.fail("expected a JSON value")
```

这叫递归下降解析：grammar 中每个主要规则对应一个解析函数。

## 五、对象如何解析

对象语法是：

```text
'{' (string ':' value) (',' string ':' value)* '}'
```

简化实现：

```python
def parse_object(self):
    result = {}
    self.consume('{')
    self.skip_whitespace()

    if self.peek() == '}':
        self.consume('}')
        return result

    while True:
        self.skip_whitespace()
        if self.peek() != '"':
            self.fail("object key must be a string")

        key = self.parse_string()
        self.skip_whitespace()
        self.consume(':')
        value = self.parse_value()
        result[key] = value

        self.skip_whitespace()
        ch = self.consume()
        if ch == '}':
            return result
        if ch != ',':
            self.fail("expected ',' or '}'")
```

当 value 是 `{` 或 `[` 时，`parse_value` 会再次调用 `parse_object` 或 `parse_array`，因此可以处理任意层嵌套；实际实现一般设置最大深度，避免栈溢出或拒绝服务攻击。

## 六、数组如何解析

数组语法是：

```text
'[' value (',' value)* ']'
```

```python
def parse_array(self):
    result = []
    self.consume('[')
    self.skip_whitespace()

    if self.peek() == ']':
        self.consume(']')
        return result

    while True:
        result.append(self.parse_value())
        self.skip_whitespace()
        ch = self.consume()

        if ch == ']':
            return result
        if ch != ',':
            self.fail("expected ',' or ']'")
```

标准 JSON 不允许尾随逗号，所以 `[1, 2,]` 应报错。某些宽松 parser 会接受它，但这属于扩展行为。

## 七、字符串与转义如何解析

解析字符串不能简单查找下一个 `"`，因为其中可能包含转义引号：

```json
{"text":"他说：\"已生效\""}
```

解析器逐字符读取：

```python
def parse_string(self):
    self.consume('"')
    chars = []

    while True:
        ch = self.consume()

        if ch == '"':
            return ''.join(chars)

        if ch == '\\':
            escape = self.consume()
            chars.append(self.decode_escape(escape))
        else:
            if ord(ch) < 0x20:
                self.fail("unescaped control character")
            chars.append(ch)
```

标准转义包括 `\"`、`\\`、`\/`、`\b`、`\f`、`\n`、`\r`、`\t` 和 `\uXXXX`。实现 `\uXXXX` 时还需要正确组合 UTF-16 surrogate pair，例如两个转义共同表示一个非 BMP Unicode 字符。

## 八、数字如何解析

JSON number 的形式可简化为：

```text
-? (0 | [1-9][0-9]*) ('.' [0-9]+)? ([eE] [+-]? [0-9]+)?
```

因此以下是合法数字：

```text
0
-12
3.14
6.02e23
-1E-9
```

以下不是标准 JSON number：

```text
01
+1
.5
NaN
Infinity
```

parser 先扫描符合数字 grammar 的字符片段，再转换成宿主语言的数字类型：

```python
literal = scan_number_characters()

if '.' in literal or 'e' in literal.lower():
    return float(literal)
return int(literal)
```

金融等精度敏感场景不应默认使用二进制浮点数，可将小数解析为 `Decimal`，或者暂时保留原始数字字符串。

## 九、词法分析是否一定独立

编译器教材通常把处理分成：

```text
字符流 -> Lexer 产生 token -> Parser 识别语法树
```

例如：

```text
{ "a": 1 }
```

可以先转换成：

```text
LBRACE STRING("a") COLON NUMBER(1) RBRACE
```

但 JSON grammar 很简单，许多高性能实现不会先创建完整 token 列表，而是在递归下降过程中直接扫描字符，以减少内存分配。逻辑上仍然包含词法识别和语法解析两个职责。

## 十、错误如何定位

parser 一般记录：

- 绝对字符偏移；
- 行号和列号；
- 当前期待的字符或 value；
- 实际遇到的字符或文件结尾。

例如：

```json
{"text":"ok" "evidence_ids":[]}
```

在完成第一个字段后，grammar 只允许 `,` 或 `}`，但遇到了第二个字符串，因此可以报告：

```text
line 1, column 14: expected ',' or '}', got '"'
```

## 十一、安全与工程边界

生产 parser 通常还需要限制：

- 最大输入字节数；
- 最大嵌套深度；
- 最大字符串和数组长度；
- 数字位数及指数范围；
- 重复对象键的处理策略；
- 非法 Unicode 的处理；
- 解析超时和内存使用。

重复键尤其需要注意：

```json
{"role":"user","role":"admin"}
```

不同 parser 可能采用第一个值、最后一个值或直接报错。安全系统应明确策略，通常应拒绝重复键，避免校验组件和业务组件对同一输入产生不同解释。

## 十二、与后续校验的关系

```text
原始字符串
  -> JSON parser：语法是否合法，转换成对象
  -> Schema validator：对象结构和值是否符合规则
  -> 业务 validator：ID、权限、状态是否有效
  -> 语义 validator：证据是否支持事实
```

例如：

| 输入问题 | JSON parser | Schema validator |
|---|---:|---:|
| 缺少 `}` | 失败 | 不执行 |
| 缺少 `evidence_ids` | 通过 | 失败 |
| `evidence_ids` 类型为数字 | 通过 | 失败 |
| ID 存在但证据不支持 claim | 通过 | 通过，交给语义验证 |

## 十三、一个完整的输入与输出案例

### 1. 输入是字符串，不是对象

假设程序实际收到的原始字符序列是：

```text
{"claim":{"text":"该法规已生效","evidence_ids":["doc-17#p42","doc-21#p8"]},"verified":false,"note":null}
```

在 Python 源代码中，为了表达这段字符串，可以写成：

```python
json_text = '''{
  "claim": {
    "text": "该法规已生效",
    "evidence_ids": ["doc-17#p42", "doc-21#p8"]
  },
  "verified": false,
  "note": null
}'''
```

此时 `json_text` 的类型是 `str`。程序还不能使用 `json_text["claim"]`，因为它只是一串字符。

### 2. 调用 parser

```python
import json

result = json.loads(json_text)
```

`json.loads` 中的 `s` 可以理解为 string：它把包含 JSON 文本的字符串解析成 Python 对象。

### 3. parser 内部识别过程

```text
{                          -> 创建根 dict
  "claim"                 -> 读取键 claim
  : {                      -> claim 的值是新 dict
      "text"              -> 读取键 text
      : "该法规已生效"      -> 产生 Python str
      "evidence_ids"      -> 读取键 evidence_ids
      : [                  -> 创建 Python list
          "doc-17#p42"    -> 加入第 1 个 str
          "doc-21#p8"     -> 加入第 2 个 str
        ]                  -> list 完成
    }                      -> claim dict 完成
  "verified": false       -> 产生 Python False
  "note": null            -> 产生 Python None
}                          -> 根 dict 完成
```

### 4. 输出对象

`result` 是下面这个 Python 内存对象：

```python
{
    "claim": {
        "text": "该法规已生效",
        "evidence_ids": ["doc-17#p42", "doc-21#p8"]
    },
    "verified": False,
    "note": None
}
```

注意，输出不是一段新的 JSON 文本，而是 Python 中相互嵌套的 `dict`、`list`、`str`、`bool` 和 `None` 对象。

### 5. 可以按对象方式访问

```python
print(type(json_text))                         # <class 'str'>
print(type(result))                            # <class 'dict'>
print(result["claim"]["text"])                # 该法规已生效
print(result["claim"]["evidence_ids"][0])     # doc-17#p42
print(type(result["claim"]["evidence_ids"]))  # <class 'list'>
print(result["verified"])                     # False
print(result["note"] is None)                  # True
```

### 6. 输入错误时没有输出对象

如果输入缺少逗号：

```python
bad_json = '{"text":"已生效" "evidence_ids":[]}'
json.loads(bad_json)
```

parser 在读完 `"已生效"` 后只允许遇到 `,` 或 `}`，实际却遇到下一个字段名，因此抛出 `JSONDecodeError`，不会返回一个部分解析的业务对象。

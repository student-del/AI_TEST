# FSM 约束解码详解 — Outlines

> 覆盖 Outlines 完整的 FSM 约束解码管线：JSON Schema → Regex → DFA → Index → 逐 Token 掩码。

---

## 一、核心思路：反转模式匹配

**传统做法**：每一步遍历全部 5 万个 token，逐个用正则检查 → O(N)/步。

**Outlines**：初始化阶段一次性遍历全部 token，构建"FSM 状态 → 合法 Token 集合"映射表，推理时 O(1) 查表。

```
初始化（一次性）: JSON Schema → Regex → DFA → state→{token} 索引表
推理（每步）:     查表获取合法 token → 非法 token 设为 -∞ → 采样 → 推进状态
```

---

## 二、Step 1：JSON Schema → 正则表达式

这是整个管线的第一步，也是最关键的基础。

### 算法：递归类型驱动

```
build_regex(schema) =
  string  → "[^"\\\n]*"          （JSON 字符串的正则）
  integer → \d+                   （数字的正则）
  boolean → (true|false)
  null    → null
  object  → \{ key:regex, ... \}  （递归每个属性）
  array   → \[ regex, ... \]      （递归元素类型）
  enum    → "v1"|"v2"|...
  anyOf   → (regex1|regex2|...)   （递归每个选项）
  $ref    → 查 definitions 递归
```

### 基本类型

```python
def build_string_regex(schema):
    if schema.get("pattern"):
        return f'"{schema["pattern"]}"'
    return '"[^"\\\\\\n]*"'

def build_integer_regex(schema):
    if schema.get("minimum", 0) >= 0:
        return r'\d+'
    return r'-?\d+'
```

### 对象：最复杂的部分

```python
def build_object_regex(schema, definitions):
    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    parts = []
    for key, val_schema in properties.items():
        key_pattern = f'"{key}"'
        value_pattern = build_regex(val_schema, definitions)  # 递归！
        pair = f'\\s*{key_pattern}\\s*:\\s*{value_pattern}'

        if key in required:
            parts.append(("required", pair))
        else:
            parts.append(("optional", pair))

    # required 字段固定顺序在前，optional 字段用 (a|b)* 匹配任意组合
    req = ',\\s*'.join(p for t, p in parts if t == "required")
    opt = '|'.join(p for t, p in parts if t == "optional")
    combined = req + (f'(,\\s*({opt}))*' if opt else '')

    return r'\{\s*' + combined + r'\\s*\\}'
```

### 完整转换示例

输入 Schema：
```json
{
  "type": "object",
  "properties": {
    "name": { "type": "string" },
    "age":  { "type": "integer", "minimum": 0 }
  },
  "required": ["name"]
}
```

递归展开：
```
object → \{ required_fields (optional_fields)* \}
  ├─ "name" → string_regex  → "[^"\\\n]*"
  └─ "age"  → integer_regex → \d+
```

最终正则：
```
\{\s*"name"\s*:\s*"[^"\\\n]*"(\s*,\s*("age"\s*:\s*\d+))*\s*\}
```

匹配：`{"name":"张三"}`, `{"name":"张三","age":25}`
不匹配：`{"age":25}`（缺少 required "name"）

### 关键难点

1. **可选字段任意顺序**：用 `(,(a|b|c))*` 匹配 0 个或多个可选字段的任意组合
2. **字符串转义**：JSON `"` 和 `\` 在正则中需要特殊处理
3. **递归深度限制**：防止 `$ref` 无限递归，depth > 100 时抛出异常
4. **`$ref` 解析**：需要 definitions 上下文在递归中传递

---

## 三、Step 2：Regex → NFA（Thompson 构造）

正则表达式先编译为**非确定有限自动机（NFA）**。Thompson 构造法的核心思想：**每个子表达式对应一个带 ε 转移的小自动机，递归拼接**。

### 基本构造规则

```
ε (空串):     ──ε──▶ Ⓐ         Ⓐ = 接受状态

字符 'a':     ──a──▶ Ⓐ         Ⓐ = 接受状态

连接 AB:      NFA_A ──ε──▶ NFA_B     首尾用 ε 连接

选择 A|B:     ┌─ NFA_A ─┐
              ┤         ├─▶            两条分支，ε 进入
              └─ NFA_B ─┘

重复 A*:      ◀──ε── NFA_A ──ε──▶
              │                 │      ε 环实现循环
              └────── ε ────────┘
```

### 具体示例：`a|b`

```
1. 构建 'a':  s0 ─a─▶ s1 Ⓐ
2. 构建 'b':  s2 ─b─▶ s3 Ⓐ
3. 选择运算:
   新建起始 s4 ─ε─▶ s0, s4 ─ε─▶ s2
   s1 ─ε─▶ s5 Ⓐ,   s3 ─ε─▶ s5 Ⓐ

结果 NFA:  s4 ─ε─▶ s0 ─a─▶ s1 ─ε─▶ s5
           s4 ─ε─▶ s2 ─b─▶ s3 ─ε─▶ s5
```

从 s4 出发，可以选两条路之一。ε 转移是"自由移动"——不需要消耗字符就能走。

### 另一种经典示例：`a*`

```
构建 'a':   s0 ─a─▶ s1 Ⓐ
添加 *:
  新建 s2 ─ε─▶ s0, s1 ─ε─▶ s2   ← 形成环路
  s2 ─ε─▶ s3 Ⓐ                    ← 直接跳过
  s3 ─ε─▶ s2                       ← 可再次循环

结果: s2 可跳到 s0 走 a, 回到 s1, 再经 ε 回 s2 → 无限次重复
     或者直接 ε 到 s3 接受 → 匹配空串
```

### Thompson 构造的特点

- 每个子自动机恰好**一个起始状态、一个接受状态**
- 状态数不超过 2n（n 是正则长度），线性空间
- ε 转移大量存在，NFA 状态数小而转换模糊

### 完整代码实现

#### 1. NFA 的数据结构

```python
from dataclasses import dataclass
from typing import List, Dict, Set, Optional

# ε 转移用特殊标记
EPSILON = 'ε'

@dataclass
class NFAState:
    id: int
    is_accept: bool = False

@dataclass  
class NFA:
    start: NFAState
    accept: NFAState
    states: List[NFAState]
    # 转移表: { from_state_id: { character: [to_state_ids] } }
    transitions: Dict[int, Dict[str, List[int]]]

    def add_transition(self, from_id: int, char: str, to_id: int):
        if from_id not in self.transitions:
            self.transitions[from_id] = {}
        if char not in self.transitions[from_id]:
            self.transitions[from_id][char] = []
        self.transitions[from_id][char].append(to_id)
```

每个 NFA 严格只有一个 `start` 入口和一个 `accept` 出口，这是 Thompson 构造递归拼接的基础。

#### 2. 基本单元：单字符 NFA

```python
def build_char_nfa(char: str, state_counter: 'StateCounter') -> NFA:
    """
    字符 'a' → NFA: s_start ─a─▶ s_accept
    """
    s0 = NFAState(id=state_counter.next(), is_accept=False)
    s1 = NFAState(id=state_counter.next(), is_accept=True)

    nfa = NFA(start=s0, accept=s1, states=[s0, s1], transitions={})
    nfa.add_transition(s0.id, char, s1.id)

    return nfa
```

这是原子单位——每个正则中的字母/数字最终都变成一个两态的 NFA。

#### 3. 连接运算（AB）

```python
def build_concat_nfa(left: NFA, right: NFA) -> NFA:
    """
    连接 A·B：
      left 的接受状态 ─ε─▶ right 的起始状态
      合并两个自动机的 states
      left.start 成为新入口，right.accept 成为新出口
    """
    # 取消 left 原接受标记，用 ε 连接到 right 入口
    left.accept.is_accept = False
    left.add_transition(left.accept.id, EPSILON, right.start.id)

    # 合并状态列表
    merged_states = left.states + right.states

    # 合并转移表
    merged_trans = left.transitions.copy()
    for from_id, char_map in right.transitions.items():
        if from_id not in merged_trans:
            merged_trans[from_id] = {}
        for char, to_ids in char_map.items():
            merged_trans[from_id][char] = merged_trans[from_id].get(char, []) + to_ids

    return NFA(start=left.start, accept=right.accept,
               states=merged_states, transitions=merged_trans)
```

#### 4. 选择运算（A|B）

```python
def build_union_nfa(nfa_a: NFA, nfa_b: NFA, state_counter: 'StateCounter') -> NFA:
    """
    选择 A|B：
      新建 start ─ε─▶ nfa_a.start  ─ε─▶ new_accept
                ─ε─▶ nfa_b.start  ─ε─▶ new_accept
    """
    new_start = NFAState(id=state_counter.next(), is_accept=False)
    new_accept = NFAState(id=state_counter.next(), is_accept=True)
    new_states = [new_start, new_accept]

    # 取消原有接受标记
    nfa_a.accept.is_accept = False
    nfa_b.accept.is_accept = False

    trans = {}
    # 新起始 → 两条分支
    trans[new_start.id] = {EPSILON: [nfa_a.start.id, nfa_b.start.id]}
    # 两个接受 → 新接受
    for old_accept in [nfa_a.accept, nfa_b.accept]:
        if old_accept.id not in trans:
            trans[old_accept.id] = {}
        trans[old_accept.id][EPSILON] = [new_accept.id]

    # 合并转移
    for nfa in [nfa_a, nfa_b]:
        for from_id, char_map in nfa.transitions.items():
            trans.setdefault(from_id, {})
            for char, to_ids in char_map.items():
                trans[from_id][char] = trans[from_id].get(char, []) + to_ids

    return NFA(start=new_start, accept=new_accept,
               states=new_states + nfa_a.states + nfa_b.states, transitions=trans)
```

#### 5. 闭包运算（A*）

```python
def build_star_nfa(inner: NFA, state_counter: 'StateCounter') -> NFA:
    """
    A*（零次或多次重复）：
      new_start ─ε─▶ inner.start ─ε─▶ new_accept
                ─ε── directly to ──▶ new_accept   ← 跳过（匹配 0 次）
      new_accept ─ε─▶ new_start                    ← 再次循环
    """
    new_start = NFAState(id=state_counter.next(), is_accept=False)
    new_accept = NFAState(id=state_counter.next(), is_accept=True)

    inner.accept.is_accept = False

    trans = {}
    # 三条 ε 转移
    trans[new_start.id] = {EPSILON: [inner.start.id, new_accept.id]}  # 进入 or 跳过
    trans.setdefault(inner.accept.id, {})
    trans[inner.accept.id][EPSILON] = [new_accept.id]   # 完成一圈
    trans.setdefault(new_accept.id, {})
    trans[new_accept.id][EPSILON] = [new_start.id]      # 再循环

    # 合并 inner 的转移
    for from_id, char_map in inner.transitions.items():
        trans.setdefault(from_id, {})
        for char, to_ids in char_map.items():
            trans[from_id][char] = trans[from_id].get(char, []) + to_ids

    return NFA(start=new_start, accept=new_accept,
               states=[new_start, new_accept] + inner.states, transitions=trans)
```

#### 6. 正则解析器 + 主构造器

```python
class StateCounter:
    """全局状态 ID 计数器"""
    def __init__(self):
        self._id = 0
    def next(self):
        self._id += 1
        return self._id


def build_nfa(regex: str) -> NFA:
    """
    正则 → NFA 入口

    简化实现：用递归下降解析，处理 | 和连接，不支持括号嵌套。
    完整实现需要先做 Lexer/Parser 生成 AST，这里展示核心思路。
    """
    counter = StateCounter()

    # Step 1: 分词 → tokens
    tokens = tokenize(regex)  # 将 "(a|b)*c" → ['(', 'a', '|', 'b', ')', '*', 'c']

    # Step 2: 解析 → AST
    ast = parse_regex(tokens)

    # Step 3: 递归构造 NFA
    return _build_nfa_from_ast(ast, counter)


def _build_nfa_from_ast(node, counter: StateCounter) -> NFA:
    """递归：AST 节点 → NFA"""

    if node.type == 'CHAR':
        return build_char_nfa(node.char, counter)

    elif node.type == 'CONCAT':
        left_nfa  = _build_nfa_from_ast(node.left, counter)
        right_nfa = _build_nfa_from_ast(node.right, counter)
        return build_concat_nfa(left_nfa, right_nfa)

    elif node.type == 'UNION':
        left_nfa  = _build_nfa_from_ast(node.left, counter)
        right_nfa = _build_nfa_from_ast(node.right, counter)
        return build_union_nfa(left_nfa, right_nfa, counter)

    elif node.type == 'STAR':
        inner_nfa = _build_nfa_from_ast(node.child, counter)
        return build_star_nfa(inner_nfa, counter)

    elif node.type == 'EPSILON':
        return build_char_nfa(EPSILON, counter)

    raise ValueError(f"Unknown AST node: {node.type}")
```

#### 7. 完整示例：`(a|b)*c`

```
1. 解析 AST:
       CONCAT
      /       \
    STAR      CHAR('c')
     |
   UNION
   /    \
 CHAR('a')  CHAR('b')

2. 递归构造:

   CHAR('a'):     s0 ─a─▶ s1
   CHAR('b'):     s2 ─b─▶ s3
   UNION('a','b'): s4 ─ε─▶ s0 ─a─▶ s1 ─ε─▶ s5
                  s4 ─ε─▶ s2 ─b─▶ s3 ─ε─▶ s5
   STAR(union):   s6 ─ε─▶ s4, s5 ─ε─▶ s5_accept
                  s5_accept ─ε─▶ s6

   CHAR('c'):     s7 ─c─▶ s8

   CONCAT(star, c):
     s5_accept ─ε─▶ s7 ─c─▶ s8

最终 NFA（入口 s6，出口 s8）:
   s6 ─ε→ s4 ─ε→ s0 ─a→ s1 ─ε→ s5 ─ε→ s7 ─c→ s8
        ↘(跳过) s5_accept ─ε→ s6 (循环)  ……
```

Thompson 构造的核心优美之处：**每种运算都生成一个单入口-单出口的模块，拼接时只通过 ε 转移连接**，从不修改子模块的内部结构。

---

## 四、Step 2-续：NFA → DFA（子集构造法）

NFA 可同时处于多个状态（不确定性），DFA 必须每步只处于一个确定状态。子集构造的核心：**把 NFA 的状态集合当作 DFA 的一个状态**。

### 关键操作：ε-闭包

```
ε-closure(S) = 从 S 中的任意状态出发，只经过 ε 转移能到达的所有状态集合
```

因为 ε 转移不消耗字符，从状态 q 出发，闭包告诉你"实际上我可能在哪些状态"。

### 算法

```
输入: NFA (Q, Σ, δ, q₀, F)
输出: DFA (Q', Σ, δ', q₀', F')

q₀' = ε-closure({q₀})
Q' = {q₀'}
未处理队列 = [q₀']

while 未处理队列非空:
    取出一个 DFA 状态 S = 未处理队列.pop()

    for 每个输入字符 c:
        # 1. 从 S 中的每个 NFA 状态出发，走 c 转移
        T = { δ(q, c) | q ∈ S 且 δ(q, c) 存在 }

        # 2. 再走 ε 转移（不确定性的来源）
        S_new = ε-closure(T)

        if S_new 不在 Q' 中:
            加入 Q' 和队列

        δ'(S, c) = S_new   # DFA 转移

F' = { S ∈ Q' | S 中包含任意 NFA 的接受状态 }
```

### 具体示例：`a|b` 的 NFA → DFA

```
起始 NFA:
  q₀ ─ε─▶ q₁ ─a─▶ q₂ ─ε─▶ q₅ Ⓐ
  q₀ ─ε─▶ q₃ ─b─▶ q₄ ─ε─▶ q₅ Ⓐ

1. 起始状态: S₀ = ε-closure({q₀}) = {q₀, q₁, q₃}   ← ε 扩散到两个分支起点

2. 处理 S₀ = {q₀, q₁, q₃}:
   输入 'a': q₀ 无 a ✗, q₁ ─a─▶ q₂, q₃ 无 a ✗
   → T = {q₂}, ε-closure({q₂}) = {q₂, q₅}
   → 新状态 S₁ = {q₂, q₅} ← 包含接受状态 q₅，所以是接受状态

   输入 'b': q₀ 无 b ✗, q₁ 无 b ✗, q₃ ─b─▶ q₄
   → T = {q₄}, ε-closure({q₄}) = {q₄, q₅}
   → 新状态 S₂ = {q₄, q₅}

3. 处理 S₁ = {q₂, q₅}:
   输入 'a' 和 'b': 都无转移 → DEAD（死状态 ∅）

4. 处理 S₂ = {q₄, q₅}: 同 S₁

最终 DFA:
        a        b
  S₀ ──▶ S₁    S₀ ──▶ S₂
  S₁ ──▶ ∅     S₂ ──▶ ∅

状态: S₀(起始), S₁(接受), S₂(接受)
```

和 NFA 不同——DFA 每次只处于一个状态，没有"选哪条路"的歧义。

### 最坏情况

子集构造理论上生成 2^|Q| 个状态。但实际中绝大多数正则的 DFA 状态数远小于上限。真正爆炸的是 `maxLength=100` 这类约束 — 它让 NFA 被迫为每种长度维护独立状态，再被子集构造进一步放大。

---

## 五、Step 2-续：DFA 最小化（Hopcroft 算法）

子集构造后的 DFA 可能有冗余——**行为等价的状态可以合并**。

### 核心思想

> 如果两个状态对任意输入字符都转移到"等价"的状态，那它们就是等价的。

### 算法

```
1. 初始划分: P = { F 接受状态组,  Q\F 非接受状态组 }
2. repeat:
     检查每个组，如果组内状态对于某字符 c 转移到不同的组
     → 按转移目标拆分组
   until 没有组可以拆分
3. 每个最终组 → 最小 DFA 的一个状态
```

### 示例：`a*`

```
子集构造后的 DFA:
  S₀ ─a─▶ S₁ Ⓐ (接受)
  S₁ ─a─▶ S₁ Ⓐ

1. 初始: G₁={S₁}(接受), G₂={S₀}(非接受)
2. 检查 G₂: S₀ ─a→ S₁ ∈ G₁，组内一致，不拆分
3. 检查 G₁: S₁ ─a→ S₁ ∈ G₁，组内一致，不拆分
4. 无变化 → 结束

结论: S₀ 和 S₁ 行为不同（一个接受一个不接受），无法合并
      DFA 已是最小状态
```

### 另一个示例：`a|a`

```
原始 NFA: a|a  →  子集构造后有两个相同行为的接受状态
  S₁ Ⓐ ─a─▶ DEAD
  S₂ Ⓐ ─a─▶ DEAD

Hopcroft:
  S₁ 和 S₂ 同组(接受), 对任何字符都到同一组(DEAD)
  → 行为等价 → 合并为 S₁₂

最小 DFA: S₀ ─a─▶ S₁₂ Ⓐ （只 2 个状态，S₂ 消失了）
```

---

## 六、Step 2 总结：三阶段编译

```python
from interegular import parse_pattern

nfa = parse_pattern(regex).to_fsm()    # ① Thompson 构造: Regex → NFA
dfa = nfa.reduce()                     # ② 子集构造: NFA → DFA
                                       # ③ Hopcroft:  DFA → 最小 DFA
```

最终得到 DFA 五元组 `(Q, Σ, δ, q₀, F)`：

| 符号 | 含义 |
|------|------|
| `Q` | 有限状态集合（最小化后无冗余） |
| `Σ` | 字符表（所有 ASCII/Unicode 字符） |
| `δ: Q × Σ → Q` | 状态转移函数（每步只有一个确定目标） |
| `q₀` | 初始状态 |
| `F` | 接受状态集合（到达这些状态 = JSON 完整合法） |

示例 DFA（`\d+(\.\d+)?`）：

```
          digit           .            digit
  q₀ ──▶ q₁ ◀──digit──  q₁ ──▶ q₂ ──▶ q₃
           接受状态                 接受状态
```

这三步都是纯 CPU 操作，是 Outlines 初始化阶段的主要性能瓶颈——尤其含 `maxLength` 等约束时，子集构造会放大 NFA 的状态，导致内存爆炸。

---

## 七、Step 3：构建 FSM 索引表（Index）— 核心创新

初始化时一次性遍历整个词汇表，为每个 DFA 状态预计算合法 token 集合：

```python
sigma = {}  # state → 合法 token ID 集合

for state in dfa.states:
    sigma[state] = set()
    for token_id, token_str in vocab:
        end_state = dfa.walk(token_str, start=state)
        if end_state is not None and end_state != DEAD:
            sigma[state].add(token_id)
```

示例（词汇表 = `['A', '.', '42', '.2', '1']`，Schema = `(\d*)\.?\d*`）：

```
从 state_0:
  'A'  → dfa.walk('A', state_0)  → DEAD  ✗
  '.'  → dfa.walk('.', state_0)  → state_1 ✓
  '42' → dfa.walk('42', state_0) → state_1 ✓
  '.2' → dfa.walk('.2', state_0) → state_2 ✓
  '1'  → dfa.walk('1', state_0)  → state_1 ✓

结果:
  sigma[state_0] = {'.', '42', '.2', '1'}
  sigma[state_1] = {'.', '42', '.2', '1'}
  sigma[state_2] = {'42', '1'}
```

**分词器字符鸿沟**：LLM 操作 token，FSM 操作字符。通过 walk_fsm 逐字符步进解决：

```python
def walk_fsm(dfa, start_state, token_str):
    current = start_state
    for char in token_str:
        current = dfa.transition(current, char)
        if current == DEAD:
            return None
    return current
```

---

## 八、Step 4：逐 Token 掩码推理

初始化后每一步都是 O(1)：

```python
guide = Guide(index)

for _ in range(max_tokens):
    # 1. 模型前向
    logits = model(input_ids)[:, -1, :]

    # 2. 查表获取合法 token（O(1)）
    allowed = guide.get_tokens()

    # 3. 掩码
    logits[~allowed] = -float('inf')

    # 4. 采样
    next_token = sample(softmax(logits))

    # 5. 推进状态
    guide.advance(next_token)

    if guide.is_finished():
        break
```

完整逐 Token 示例：

```
步骤 1: model logits=[0.5, 0.2, 0.8, 0.3, 0.6]
        state_0 合法: ['.', '42', '.2', '1'] → 采样 '42'
        state_0 ─'4'→ s1 ─'2'→ s1

步骤 2: model logits=[0.1, 0.7, 0.4, 0.9, 0.3]
        state_1 合法: ['.', '42', '.2', '1'] → 采样 '.2'
        state_1 ─'.'→ s2 ─'2'→ s3

步骤 3: model logits=[0.2, 0.1, 0.8, 0.5, 0.4]
        state_3 合法: ['42', '1'] → 采样 '1'
        state_3 ─'1'→ s1 → is_finished → 结束

输出: "42.21" → 100% 符合 schema
```

---

## 九、架构与性能

### Outlines-Core 架构（2025）

| 层 | 语言 | 职责 |
|---|---|---|
| outlines-core | Rust | DFA 构建、Index、state 转移 |
| outlines | Python | 循环编排、模型集成、高层 API |

### DFA 状态爆炸问题

```
不含 maxLength:      DFA ≈ 10 个状态
maxLength=20:        DFA ≈ 200+ 个状态（每个长度一个独立状态）
maxLength=100+嵌套:  数万状态，内存可达 77GB，100% CPU
```

**缓解**：移除不必要的 `maxLength`（吞吐 37x），或改用 PDA 方案。

### FSM vs PDA

两者的核心区别在于**如何跟踪嵌套深度**——这是"有限状态"和"下推栈"的理论能力差异。

| | FSM (Outlines) | PDA (XGrammar) |
|---|---|---|
| 数学模型 | `(Q, Σ, δ, q₀, F)` | `(Q, Σ, Γ, δ, q₀, Z, F)` |
| 记忆 | 只有当前状态 | 状态 + **无限栈** |
| 识别能力 | 正则语言 | 上下文无关语言 |
| 嵌套处理 | 展开为独立状态（爆炸） | 栈天然处理，压栈/弹栈 |
| 初始化 | 慢（DFA 编译 + 词汇遍历） | 快（无状态爆炸） |
| 每步 | O(1) | O(1) |

**具体示例**：Schema 允许嵌套对象 `{ "a": { "b": "c" } }`

FSM 的做法——状态本身编码嵌套深度：
```
state_0 ─{─▶ state_1 ─"a"─▶ state_2 ─:─▶ state_3 ─{─▶ state_4
               ↑ 第一层              ↑ 在 "a" 后面      ↑ 第二层，新状态！

state_4 ─"b"─▶ state_5 ─:─▶ state_6 ─"c"─▶ state_7 ─}─▶ state_8
state_8 ─}─▶ state_9

嵌套 5 层就需要 5 套独立状态 → 状态数 = 结构位置数 × 嵌套深度 → 膨胀
```

PDA 的做法——同一套状态复用，栈跟踪深度：
```
state_0 ─{─▶ state_1    栈: [obj_1]           ← 压栈
state_1 ─"a"─▶ state_2  栈: [obj_1]
state_2 ─:─▶ state_3    栈: [obj_1]
state_3 ─{─▶ state_1    栈: [obj_1, obj_2]    ← 再次压栈，但回到 state_1！
state_1 ─"b"─▶ state_2  栈: [obj_1, obj_2]    ← 同一个 state_1
state_2 ─:─▶ state_3    栈: [obj_1, obj_2]
state_3 ─"c"─▶ state_4  栈: [obj_1, obj_2]
state_4 ─}─▶ state_5    栈: [obj_1]           ← 弹栈，回到上一层
state_5 ─}─▶ state_6    栈: []                ← 再弹栈

关键：state_1 既处理第一层的键又处理第二层的键
      通过栈高度区分当前在哪一层——状态复用，栈来记忆
```

```
公式总结：
  FSM:  状态本身 = 结构位置 × 嵌套深度 → 每深一层，状态翻倍
  PDA:  状态 = 结构位置（~10 个），深度 = 栈高度（无限） → 状态数恒定
```

这就是为什么 FSM 有 DFA 状态爆炸而 PDA 没有——PDA 用栈把"层数"这个维度从状态中分离了出去。

---

## 十、总结

```
不是: 每步对全词表做正则匹配 — O(N)/步
而是: 初始化一次性构建 state→token 索引表 — O(|Q|×N) 一次性
      → 推理时 O(1) 查表
```

核心创新：**把正则匹配反转为状态到 Token 集合的映射**。初始化付出一次代价，推理零开销。

---

> 基于源码分析和技术调研整理，更新时间：2026-06-20

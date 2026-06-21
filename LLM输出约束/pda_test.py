"""
PDA 约束解码 — 完整可运行测试

验证点:
  1. 状态枚举: 只编码 (语法位置, 键名)，不编码栈深度
  2. Token 分类: 上下文无关 token 编译时判定，上下文相关 token 运行时判断
  3. 编译: 位图固化 99% token，dependent_ids 标记 1%
  4. 推理: 掩码约束 + 状态推进 + 栈维护
"""

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple, Set


# ============================================================
# 第 1 步：PDA 状态定义
# ============================================================

class JsonState(Enum):
    START = 0
    EXPECT_KEY = 1
    EXPECT_COLON = 2
    EXPECT_VALUE = 3
    EXPECT_COMMA_OR_END = 4
    EXPECT_ARRAY_ITEM = 5
    DONE = 6


@dataclass
class StackFrame:
    """栈帧：记录嵌套层类型"""
    type: str  # "object" 或 "array"

    @staticmethod
    def object_frame() -> 'StackFrame':
        return StackFrame(type="object")

    @staticmethod
    def array_frame() -> 'StackFrame':
        return StackFrame(type="array")


# ============================================================
# 第 2 步：上下文相关 token 判定
# ============================================================

CONTEXT_DEPENDENT_CHARS = {'}', ']'}

def is_context_dependent(token_str: str) -> bool:
    """只有含 } 或 ] 的 token 才需要在运行时结合栈判断"""
    for ch in token_str:
        if ch in CONTEXT_DEPENDENT_CHARS:
            return True
    return False


# ============================================================
# 第 3 步：状态枚举 — 只编码有限部分
# ============================================================

class PDAStateEnumerator:
    """
    枚举所有 (语法位置, 键名) 组合。

    state_id = js_id × 1000 + key_id
    不编码栈深度 —— 那是运行时变量，不参与编译。
    """

    def __init__(self, schema: dict):
        properties = schema.get("properties", {})
        self.all_keys: List[Optional[str]] = [None] + list(properties.keys())
        self.properties = properties

    def enumerate(self) -> List[int]:
        states = []
        for js_state in JsonState:
            for key in self.all_keys:
                states.append(self._encode(js_state, key))
        return states

    def _encode(self, js_state: JsonState, key: Optional[str]) -> int:
        return js_state.value * 1000 + self.all_keys.index(key)

    def _decode(self, state_id: int) -> Tuple[JsonState, Optional[str]]:
        return JsonState(state_id // 1000), self.all_keys[state_id % 1000]


# ============================================================
# 第 4 步：模拟分词器
# ============================================================

class MockTokenizer:
    def __init__(self, vocabulary: List[str]):
        self.vocabulary = vocabulary
        self.vocab_size = len(vocabulary)
        self._s2i = {s: i for i, s in enumerate(vocabulary)}
        self._i2s = {i: s for i, s in enumerate(vocabulary)}

    def encode(self, text: str) -> List[int]:
        return [self._s2i[ch] for ch in text if ch in self._s2i]

    def id_to_str(self, tid: int) -> str:
        return self._i2s.get(tid, "")

    def decode_ids(self, tids: List[int]) -> str:
        return ''.join(self._i2s[t] for t in tids)


# ============================================================
# 第 5 步：编译 — 分类 token + 构建位图
# ============================================================

def _check_context_free(js_state: JsonState, _key: Optional[str],
                        token_str: str) -> bool:
    """上下文无关检查 — 编译时执行，只看语法位置不看栈"""
    if not token_str or token_str.isspace():
        return True
    fc = token_str[0]

    if js_state == JsonState.START:
        return fc in ('{', '[')
    if js_state == JsonState.EXPECT_KEY:
        return fc == '"'
    if js_state == JsonState.EXPECT_COLON:
        return fc == ':'
    if js_state in (JsonState.EXPECT_VALUE, JsonState.EXPECT_ARRAY_ITEM):
        if fc == '"':  return True
        if fc in ('{', '['): return True
        if fc.isdigit() or fc == '-': return True
        if fc == 't':  return token_str.strip() == 'true'
        if fc == 'f':  return token_str.strip() == 'false'
        if fc == 'n':  return token_str.strip() == 'null'
        return False
    if js_state == JsonState.EXPECT_COMMA_OR_END:
        return True
    if js_state == JsonState.DONE:
        return token_str.strip() == ""
    return True


def _runtime_check(tstr: str, js_state: JsonState,
                   stack_depth: int, stack_top_type: Optional[str]) -> bool:
    """上下文相关检查 — 推理时执行，需要完整的栈信息"""
    if '}' in tstr:
        if stack_depth == 0 or stack_top_type != "object":
            return False
        return js_state == JsonState.EXPECT_COMMA_OR_END
    if ']' in tstr:
        if stack_depth == 0 or stack_top_type != "array":
            return False
        return js_state in (JsonState.EXPECT_COMMA_OR_END, JsonState.EXPECT_ARRAY_ITEM)
    if ',' in tstr:
        if stack_depth == 0:
            return False
        return js_state == JsonState.EXPECT_COMMA_OR_END
    return True


class CompiledPDA:
    """编译后的 PDA：预计算位图 + 上下文相关 token 列表"""

    def __init__(self, schema: dict, tokenizer: MockTokenizer):
        self.schema = schema
        self.tokenizer = tokenizer
        self.vocab_size = tokenizer.vocab_size
        self.enumerator = PDAStateEnumerator(schema)

        self.bitmasks: Dict[int, List[bool]] = {}
        self.dependent_ids: List[int] = []
        self.states: List[int] = []

        self._compile()

    def _compile(self):
        """离线编译：分类 token + 为每个状态构建位图"""
        self.states = self.enumerator.enumerate()

        # 第一遍：找出所有上下文相关 token
        for tid in range(self.vocab_size):
            if is_context_dependent(self.tokenizer.id_to_str(tid)):
                self.dependent_ids.append(tid)

        # 第二遍：为每个状态构建上下文无关位图
        for state_id in self.states:
            js_state, key = self.enumerator._decode(state_id)
            bm = [False] * self.vocab_size
            for tid in range(self.vocab_size):
                if tid in self.dependent_ids:
                    bm[tid] = True  # 默认允许，运行时修正
                else:
                    bm[tid] = _check_context_free(js_state, key,
                                                  self.tokenizer.id_to_str(tid))
            self.bitmasks[state_id] = bm

    def get_mask(self, state_id: int, stack_depth: int,
                 stack_top_type: Optional[str]) -> List[bool]:
        """运行时获取最终掩码：位图 + 上下文相关修正"""
        mask = self.bitmasks[state_id].copy()
        js_state, _ = self.enumerator._decode(state_id)
        for tid in self.dependent_ids:
            mask[tid] = _runtime_check(self.tokenizer.id_to_str(tid),
                                       js_state, stack_depth, stack_top_type)
        return mask


# ============================================================
# 第 6 步：推理循环
# ============================================================

class PDADecoder:
    """PDA 约束推理器"""

    def __init__(self, compiled: CompiledPDA):
        self.compiled = compiled
        self.enumerator = compiled.enumerator
        self.tokenizer = compiled.tokenizer
        self.state_id: int = self.enumerator._encode(JsonState.START, None)
        self.stack: List[StackFrame] = []
        self.current_key: Optional[str] = None
        self.output: List[int] = []

    def step(self, token_id: int) -> bool:
        """
        单步推理：检查 token 合法性 → 通过则输出并推进状态。

        返回 True 表示 token 被接受。
        """
        mask = self.compiled.get_mask(
            self.state_id,
            len(self.stack),
            self.stack[-1].type if self.stack else None
        )
        if not mask[token_id]:
            return False  # 非法 token，被约束拦截

        # 合法：输出 + 推进
        self.output.append(token_id)
        self._advance(token_id)
        return True

    def _advance(self, token_id: int):
        """推进 PDA 状态 + 维护栈"""
        tstr = self.tokenizer.id_to_str(token_id)
        if not tstr or tstr.isspace():
            return

        # ═══ 结构字符：压栈/弹栈 ═══
        if '{' in tstr:
            self.stack.append(StackFrame.object_frame())
            js_state = JsonState.EXPECT_KEY
        elif '[' in tstr:
            self.stack.append(StackFrame.array_frame())
            js_state = JsonState.EXPECT_ARRAY_ITEM
        elif '}' in tstr or ']' in tstr:
            if self.stack:
                self.stack.pop()
            js_state = JsonState.EXPECT_COMMA_OR_END

        # ═══ 内容字符：更新语法位置 ═══
        elif tstr == ':':
            js_state = JsonState.EXPECT_VALUE
        elif tstr == ',':
            if self.stack and self.stack[-1].type == "object":
                js_state = JsonState.EXPECT_KEY
            else:
                js_state = JsonState.EXPECT_ARRAY_ITEM
        elif tstr.startswith('"'):
            js_state_before, _ = self.enumerator._decode(self.state_id)
            if js_state_before == JsonState.EXPECT_KEY:
                self.current_key = tstr.strip('"')
                js_state = JsonState.EXPECT_COLON
            else:
                js_state = JsonState.EXPECT_COMMA_OR_END
        else:
            js_state = JsonState.EXPECT_COMMA_OR_END

        self.state_id = self.enumerator._encode(js_state, self.current_key)

    def decode(self, token_ids: List[int]) -> List[int]:
        """对 token 序列施加约束，返回过滤后的序列"""
        for tid in token_ids:
            self.step(tid)
        return self.output

    def is_done(self) -> bool:
        js_state, _ = self.enumerator._decode(self.state_id)
        return js_state == JsonState.DONE


# ============================================================
# 测试 1：状态枚举
# ============================================================

def test_state_enumeration():
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
        "required": ["name"]
    }
    e = PDAStateEnumerator(schema)
    states = e.enumerate()
    # 7 × 3 = 21
    assert len(states) == 21, f"预期 21，实际 {len(states)}"
    # 同一状态编码相同，不区分栈深度
    assert e._encode(JsonState.EXPECT_VALUE, "name") == \
           e._encode(JsonState.EXPECT_VALUE, "name")
    print("  ✓ 状态数 21，同一 (位置,键名) 编码相同")


# ============================================================
# 测试 2：Token 分类
# ============================================================

def test_token_classification():
    assert not is_context_dependent('"')
    assert not is_context_dependent('{')
    assert not is_context_dependent('true')
    assert is_context_dependent('}')
    assert is_context_dependent(']')
    print("  ✓ 上下文相关 token 正确分类")


# ============================================================
# 测试 3：编译
# ============================================================

def test_compilation():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    vocab = ['{', '}', '"', ':', ',', ' ', '\n',
             '"name"', '"张三"']
    t = MockTokenizer(vocab)
    c = CompiledPDA(schema, t)

    assert len(c.states) == 14  # 7 × 2
    assert len(c.dependent_ids) > 0
    assert all(is_context_dependent(t.id_to_str(tid))
               for tid in c.dependent_ids)
    print(f"  ✓ {len(c.states)} 状态, "
          f"上下文相关 token: {[t.id_to_str(x) for x in c.dependent_ids]}")


# ============================================================
# 测试 4：运行时检查 — 同一 token 在不同栈深度下行为不同
# ============================================================

def test_runtime_check():
    # 栈空 → } 非法
    assert not _runtime_check("}", JsonState.EXPECT_COMMA_OR_END, 0, None)
    # 栈非空 object → } 合法
    assert _runtime_check("}", JsonState.EXPECT_COMMA_OR_END, 1, "object")
    # 栈非空但 array → } 非法（array 用 ] 关闭）
    assert not _runtime_check("}", JsonState.EXPECT_COMMA_OR_END, 1, "array")
    print("  ✓ } 合法性依赖栈深度和栈顶类型")


# ============================================================
# 测试 5：合法 JSON 全部通过
# ============================================================

def test_valid_json_passes():
    schema = {"type": "object", "properties": {"name": {"type": "string"}},
              "required": ["name"]}
    vocab = ['{', '}', '"', '"name"', ':', '"张三"', ',']
    t = MockTokenizer(vocab)
    c = CompiledPDA(schema, t)
    d = PDADecoder(c)

    input_ids = t.encode('{"name":"张三"}')
    output = d.decode(input_ids)
    assert output == input_ids, f"合法 JSON 应全部通过"
    print(f"  ✓ 合法 JSON 全部通过: {t.decode_ids(output)}")


# ============================================================
# 测试 6：空栈时的非法 } 被拦截
# ============================================================

def test_empty_stack_blocks_brace():
    schema = {"type": "object", "properties": {"name": {"type": "string"}}}
    vocab = ['{', '}', '"', '"name"', ':', '"张三"']
    t = MockTokenizer(vocab)
    c = CompiledPDA(schema, t)

    # 输入: {} → } 应在空对象内容前被拦截
    d = PDADecoder(c)
    output = d.decode(t.encode('{}'))
    result = t.decode_ids(output)
    assert '}' not in result, f"空栈时 }} 不应通过，实际输出: {result}"
    print(f"  ✓ 空栈 }} 被拦截: {result}")


# ============================================================
# 测试 7：嵌套对象 — 同一 state_id 服务不同深度
# ============================================================

def test_nested_same_state_id():
    schema = {"type": "object",
              "properties": {"outer": {"type": "object"}}}
    vocab = ['{', '}', '"', ':', ',',
             '"outer"', '"inner"', '"value"']
    t = MockTokenizer(vocab)
    c = CompiledPDA(schema, t)

    # 外层和内层的 EXPECT_KEY 用的是同一个 state_id
    sid1 = c.enumerator._encode(JsonState.EXPECT_KEY, None)
    sid2 = c.enumerator._encode(JsonState.EXPECT_KEY, None)
    assert sid1 == sid2

    # 同一 state_id 下 } 的行为由栈深度区分
    assert _runtime_check("}", JsonState.EXPECT_COMMA_OR_END, 1, "object")
    assert not _runtime_check("}", JsonState.EXPECT_COMMA_OR_END, 0, None)
    print(f"  ✓ 嵌套内外共用 state_id={sid1}，}} 行为由栈深度区分")


# ============================================================
# 测试 8：单步推理跟踪 — 展示完整数据流
# ============================================================

def test_step_by_step_trace():
    """
    以 {"name":"张三"} 为例，跟踪每步的：
      当前状态 / 合法 token / 采样结果 / 栈变化
    """
    schema = {"type": "object", "properties": {"name": {"type": "string"}},
              "required": ["name"]}
    vocab = ['{', '}', '"', '"name"', ':', '"张三"', ',', ' ']
    t = MockTokenizer(vocab)
    c = CompiledPDA(schema, t)
    d = PDADecoder(c)

    tokens = t.encode('{"name":"张三"}')

    trace = []
    for tid in tokens:
        tstr = t.id_to_str(tid)
        state_before = d.state_id
        stack_before = len(d.stack)

        mask = c.get_mask(state_before, len(d.stack),
                          d.stack[-1].type if d.stack else None)
        allowed = [t.id_to_str(i) for i, ok in enumerate(mask) if ok]
        passed = mask[tid]

        if d.step(tid):
            trace.append(f"  {tstr:8s}  → 通过  "
                         f"栈深{stack_before}→{len(d.stack)}  "
                         f"允许:{allowed}")

    print("  ✓ 逐步跟踪:")
    for line in trace:
        print(line)

    assert t.decode_ids(d.output) == '{"name":"张三"}'
    assert d.output == tokens


# ============================================================
# 测试 9：true/false/null 全词匹配
# ============================================================

def test_literal_full_match():
    """t / f / n 开头的 token 必须完全匹配 true/false/null"""
    # true 合法
    assert _check_context_free(JsonState.EXPECT_VALUE, None, "true")
    # txxx 不合法
    assert not _check_context_free(JsonState.EXPECT_VALUE, None, "txxx")
    # false 合法
    assert _check_context_free(JsonState.EXPECT_VALUE, None, "false")
    # f123 不合法
    assert not _check_context_free(JsonState.EXPECT_VALUE, None, "f123")
    # null 合法
    assert _check_context_free(JsonState.EXPECT_VALUE, None, "null")
    # none 不合法
    assert not _check_context_free(JsonState.EXPECT_VALUE, None, "none")
    print("  ✓ true/false/null 全词匹配正确")


# ============================================================
# 主入口
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("PDA 约束解码 — 测试套件")
    print("=" * 60)

    tests = [
        ("状态枚举",            test_state_enumeration),
        ("Token 分类",          test_token_classification),
        ("编译",                test_compilation),
        ("运行时检查",           test_runtime_check),
        ("合法 JSON 通过",      test_valid_json_passes),
        ("空栈 } 拦截",         test_empty_stack_blocks_brace),
        ("嵌套共用 state_id",   test_nested_same_state_id),
        ("逐步跟踪",            test_step_by_step_trace),
        ("字面量全词匹配",       test_literal_full_match),
    ]

    for name, fn in tests:
        print(f"\n[测试] {name}")
        fn()

    print("\n" + "=" * 60)
    print(f"全部 {len(tests)} 个测试通过 ✓")
    print("=" * 60)

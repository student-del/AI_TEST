# 工具结果的 fresh / frozen 是字段还是派生状态?

> 讨论问题:Tool Result Budget(Stage 0)里,工具结果的 `fresh`(可自由处置)/ `frozen`(已被模型看到、不可改)状态,是某个数据结构里的字段指定的吗?
>
> 结论:**不是字段,是派生状态。** 结果对象上没有 `state: "frozen"` 这类属性;状态由该结果的 `toolUseId` 是否出现在两个外部集合里,每轮运行时重新推导得出。
>
> 依据:社区对 cli.js 的反编译(《上下文压缩机制详解.md》Stage 0)。
> 更新时间:2026-07-12

---

## 一、证据:分类函数 KHz

```javascript
function KHz(q, K) {
  return q.reduce((_, z) => {
    let Y = K.replacements.get(z.toolUseId);   // 查 Map
    if (Y !== void 0)
      _.mustReapply.push({ ...z, replacement: Y });  // 命中替换表 → mustReapply
    else if (K.seenIds.has(z.toolUseId))             // 查 Set
      _.frozen.push(z);                               // 已发给模型 → frozen
    else
      _.fresh.push(z);                                // 都不在 → fresh
    return _;
  }, { mustReapply: [], frozen: [], fresh: [] });
}
```

## 二、要点

- `fresh` / `frozen` / `mustReapply` 是**累加器对象里的三个数组桶**,不是结果对象的属性。一条结果每轮被 `KHz` 重新分类进某个桶,状态是**瞬时派生、不持久**的。
- **真正承载状态的持久结构有两个,均以 `toolUseId` 为键**:
  | 结构 | 类型 | 含义 | 命中即为 |
  |------|------|------|---------|
  | `seenIds` | `Set<toolUseId>` | 是否已发给模型 | frozen |
  | `replacements` | `Map<toolUseId, 占位符字符串>` | 是否已被替换过 | mustReapply |
- **判定优先级**:先查 `replacements`(mustReapply)→ 再查 `seenIds`(frozen)→ 都不在才是 fresh。

## 三、状态转移 fresh → frozen

不是翻转字段,而是发送给模型后执行:

```javascript
fresh.forEach((item) => seenIds.add(item.toolUseId));
```

把 `toolUseId` 加进 `seenIds` 后,**下一轮** `KHz` 分类时该结果即落入 `frozen` 桶。"变 frozen" = "id 进了 seenIds",无任何 `.state` 字段被改写。

## 四、来源与可信度

- 来自社区对 cli.js 的**反编译**;`KHz`、`WS4`、`rjz` 等为混淆变量名。
- **无官方文档**记载这些内部状态(Claude Code 闭源)。`fresh/frozen/mustReapply` 是逆向重构出的桶名,非 Anthropic 公开 API。
- 工程上真正的状态信号是两个集合成员关系:`toolUseId ∈ seenIds?` 与 `toolUseId ∈ replacements?`。

## 五、一句话

状态是**派生**的(靠两个以 toolUseId 为键的集合做成员检查),不是**存储**的(结果对象上没有 fresh/frozen 字段)。

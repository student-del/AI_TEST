# 用 UserPromptSubmit Hook 实现本地执行的 /models 命令

## 目标

让自定义 slash 命令 `/models` 像 Claude Code 内置 `/model` 一样在客户端本地执行，不经过 LLM，同时保留自动补全。

## 核心结论（源码核实）

**UserPromptSubmit hook 会对自定义 slash 命令触发，且能阻断 LLM 调用。**

之前曾错误推断「slash 命令走独立代码路径，hook 不触发」。经 CLI 源码核实，此结论错误。

### 源码证据（cli.js）

- `Tl8` 函数（第 8247 行）：用户输入处理主逻辑。先调用 `hcY` 展开 slash 命令，若返回 `shouldQuery=true`，**继续执行** `Kz7`（UserPromptSubmit hook 执行器）
- `hcY` 函数（第 8249 行）：检测 `/` 前缀 → 调用 `processSlashCommand` 展开 `.md` 模板。prompt 类自定义命令返回 `shouldQuery: true`（第 2237 行）
- `Kz7` 函数（第 7838 行）：构造 hook 输入 `{hook_event_name:"UserPromptSubmit", prompt: q}`，其中 `q` 是**原始用户输入**（不是展开后的内容）
- exit 2 处理（`Tl8` 内）：`shouldQuery: false` → prompt 不发送给 LLM，stderr 显示给用户

### 关键点

1. hook 收到的 `prompt` 字段是**原始输入** `/models glm5.2`，不是 `models.md` 展开后的文本
2. exit 2 → `shouldQuery=false` → 阻断 LLM
3. **`models.md` 必须存在**：否则 `/models` 没有精确匹配，会被 Claude Code 模糊匹配到内置 `/model` 命令，hook 无法拦截

## 实现方案

### 文件清单

| 文件 | 作用 |
|------|------|
| `~/.claude/commands/models.md` | 让 `/models` 注册为命令，出现在自动补全菜单。内容作为 fallback（hook 拦截后不会到达 LLM） |
| `~/.claude/scripts/models-hook.js` | UserPromptSubmit hook 脚本，匹配 `/models` 输入，本地执行切换，exit 2 阻断 |
| `~/.claude/scripts/switch-model.js` | 实际的模型切换逻辑（读写 settings.json） |
| `~/.claude/settings.json` | 注册 `hooks.UserPromptSubmit` 指向 models-hook.js |

### 工作流程

```
用户输入 /models [name]
  ↓
Claude Code 识别为自定义命令（models.md 精确匹配）→ 补全菜单可用
  ↓
命令展开，shouldQuery=true → 进入 UserPromptSubmit hook 管道
  ↓
models-hook.js 收到 prompt="/models [name]"
  ↓
正则匹配 /^\/models(?:\s+(\S+))?\s*$/ → 调用 switch-model.js
  ↓
输出写 stderr → exit 2
  ↓
框架阻断 LLM，显示 stderr 内容 + "blocked by hook" 提示
```

### 拦截提示文字（不可移除）

exit 2 时 Claude Code 框架会自动添加：
```
● UserPromptSubmit operation blocked by hook:
  [hook 命令]: <stderr 内容>
  Original prompt: /models
```
这部分是框架固定标注，无法从脚本侧移除。

## 关键教训

1. **未核实不推翻原文档**：子代理首次推断「hook 不触发」时基于文档措辞过度解读。最终需查 CLI 源码（`Tl8`/`hcY`/`Kz7` 函数）才确认 hook 确实触发。
2. **删 `models.md` 导致 `/models` 被路由到内置 `/model`**：Claude Code 对 `/` 开头输入会做精确匹配 → 模糊匹配。没有精确匹配时，`/models` 会落到最近的内置命令 `/model` 上。
3. **hook 看到的是原始输入**：不是 `models.md` 展开后的内容。所以 hook 用正则匹配 `/models` 即可，无需解析展开模板。

## 测试结果

```
'/models'          → 列出模型，exit 2 ✓
'/models glm5.2'   → 切换成功，exit 2 ✓
'/models deepseek' → 切换成功，exit 2 ✓
'普通文本'         → 放行，exit 0 ✓
```

## 涉及的文件路径

- `C:\Users\juwei\.claude\commands\models.md`
- `C:\Users\juwei\.claude\scripts\models-hook.js`（已删除）
- `C:\Users\juwei\.claude\scripts\switch-model.js`
- `C:\Users\juwei\.claude\settings.json`（hooks.UserPromptSubmit 配置，已移除）
- CLI 源码：`C:\Users\juwei\AppData\Roaming\npm\node_modules\@anthropic-ai\claude-code\cli.js`

## 最终决策：回退到 LLM 版本

hook 方案技术上可行（本地执行 + 自动补全），但**无法实现 `/model` 那种箭头键交互选择菜单**。`/model` 的交互选择器是 Claude Code 客户端硬编码的 UI 组件，不读自定义配置，也不对 hook/脚本开放。hook 是一次性 shell 子进程，没有终端输入循环，无法承接键盘选择。

用户期望「`/models` 和 `/model` 效果相同，只是支持不同服务商」，这需要交互选择 UI，而该 UI 不可扩展。因此回退：

- 删除 `models-hook.js`
- 移除 `settings.json` 中的 `hooks.UserPromptSubmit` 配置
- `models.md` 恢复为纯 LLM 版本（`$ARGUMENTS` 模板，走 LLM）

**结论：`/model` 风格的交互选择对自定义模型列表不可复现。** 除非 Claude Code 未来开放交互选择器扩展接口。

# AGENTS.md 加载时机与修改生效范围

> 记录日期：2026-07-14

## 结论

Codex 修改 `AGENTS.md` 后，**当前已建立的会话通常不会自动重新发现并重新注入整条 AGENTS.md 指令链**。

OpenAI 官方文档说明：Codex 在一次 run 启动时构建指令链一次；在 TUI 中，这通常对应一次启动的 session。因此，文件修改要作为启动级项目指令稳定生效，最可靠的方法是新建或重启会话。

## 两种容易混淆的情况

### 1. 运行时重新加载

指 Codex 客户端重新执行 AGENTS.md 的发现、合并和注入流程。修改文件本身通常不会触发这一流程。

### 2. Agent 主动重读文件

当前会话中的 Agent 可以通过文件工具读取修改后的 `AGENTS.md`，并根据当前用户要求在后续工作中遵守新内容。但这是一次新的文件读取及当前会话指令，不等于客户端重建了启动时的系统/开发者上下文。

因此：

- 修改后仅需当前任务继续：可以明确要求 Agent 重新读取并遵守。
- 希望验证 Codex 启动时发现、目录覆盖和合并行为：应启动新会话。
- 新旧规则发生冲突时：不要假定磁盘上的新文件已经自动替换当前上下文中的旧副本，最好新建会话。

## 官方依据

[OpenAI：Custom instructions with AGENTS.md](https://developers.openai.com/codex/guides/agents-md) 说明 Codex 在启动时构建 instruction chain，且每次 run 构建一次；TUI 中通常是每次启动的 session 一次。

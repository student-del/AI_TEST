# Codex CLI 启动指南

记录日期：2026-07-14

## 最简启动方式

在 PowerShell 中进入项目目录，然后运行：

```powershell
cd E:\AI_TEST
codex
```

首次运行时，按界面提示选择“使用 ChatGPT 登录”或其他可用的登录方式。登录完成后，直接输入任务即可。

## 尚未安装时

如果已安装 Node.js 和 npm，可以运行：

```powershell
npm install -g @openai/codex
```

安装后检查并启动：

```powershell
codex --version
cd E:\AI_TEST
codex
```

如果 PowerShell 提示找不到 `codex`，关闭并重新打开终端，再次运行；仍无效时检查 npm 的全局安装目录是否已加入 `PATH`。

## 常用方式

```powershell
# 启动交互界面
codex

# 带着首个任务启动
codex "解释这个项目的结构"

# 恢复之前的会话
codex resume

# 非交互执行，适合脚本或 CI
codex exec "运行测试并总结失败原因"
```

## 说明

Codex CLI 与当前桌面任务不是同一个界面实例，但可使用同一 ChatGPT 账号。CLI 会从启动时所在的目录读取项目文件和 `AGENTS.md`，因此应先进入目标项目目录再启动。

官方文档：https://developers.openai.com/codex/cli

## 确认登录状态

运行：

```powershell
codex login status
```

如果已经通过 ChatGPT 账号登录，会显示：

```text
Logged in using ChatGPT
```

2026-07-14 在本机检查得到的结果正是上述内容，因此当前 Codex CLI 已登录 ChatGPT 账号。

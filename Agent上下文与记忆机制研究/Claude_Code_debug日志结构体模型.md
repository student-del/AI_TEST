# Claude Code Debug 日志结构体模型

> 来源：`claude --debug-file` 实际输出分析
> 时间：2026-07-12
> 版本：Claude Code v2.1.89.728（从 attribution header 提取）

---

## 行格式

```
YYYY-MM-DDTHH:mm:ss.sssZ [LEVEL] <MESSAGE>
```

- `YYYY-MM-DDTHH:mm:ss.sssZ` — ISO 8601 UTC 时间戳
- `[LEVEL]` — 日志级别，仅出现 `[DEBUG]` 和 `[WARN]` 两种
- `<MESSAGE>` — 消息体，按业务模块分为 13 类（见下文）

---

## 13 类消息体结构

```
DebugLog
├── time: string            // ISO 8601 UTC 时间戳
├── level: "DEBUG" | "WARN" // 日志级别
└── Entry                   // 13 类之一
    │
    ├── 1. Startup — 启动流程
    │   ├── [pattern] "[STARTUP] <phase>"                    // 启动阶段，phase = Loading commands and agents / setup / MCP configs / showSetupScreens 等
    │   ├── [pattern] "[init] <phase>"                       // 初始化步骤，phase = configureGlobalMTLS / configureGlobalAgents 等
    │   └── [pattern] "MDM settings load completed in <N>ms" // 托管设备管理（Managed Device Management）配置加载耗时
    │
    ├── 2. Plugin — 插件系统
    │   ├── [pattern] "Loading skills from: managed=<path>, user=<path>, project=<paths>"
    │   ├── [pattern] "Loading hooks from <source> for plugin <name>: <path>"
    │   ├── [pattern] "Loaded <N> <type> from plugin <name> <source>: <path>"
    │   │   // type = skills | commands | agents | LSP servers
    │   ├── [pattern] "Total plugin <type> loaded: <N>"      // type = skills | commands | agents 等
    │   ├── [pattern] "Plugin <name> has no entry.skills defined"
    │   ├── [pattern] "getSkills returning: <N> skill dir commands, <N> plugin skills, <N> bundled skills, <N> builtin plugin skills"
    │   └── [pattern] "Loaded <N> unique skills (<N> unconditional, <N> conditional, managed: <N>, user: <N>, project: <N>, additional: <N>, legacy commands: <N>)"
    │
    ├── 3. FileSystem — 文件操作
    │   ├── [pattern] "[FileIndex] <operation>"              // 文件索引操作
    │   │   ├── operation = "getProjectFiles called"         // 获取项目文件列表
    │   │   ├── operation = "getFilesUsingGit called"        // 通过 git 获取
    │   │   ├── operation = "git ls-files (tracked) took <N>ms"
    │   │   ├── operation = "git ls-files: <N> tracked files in <N>ms"
    │   │   ├── operation = "using git ls-files result (<N> files)"
    │   │   ├── operation = "cache refresh completed in <N>ms"
    │   │   └── operation = "skipped index rebuild — <reason>"
    │   ├── [pattern] "Broken symlink or missing file encountered for settings.json at path: <path>"
    │   ├── [pattern] "Preserving file permissions: <mode>"  // 保留原文件权限位
    │   ├── [pattern] "Writing to temp file: <path>"         // 写临时文件
    │   ├── [pattern] "Temp file written successfully, size: <N> bytes"
    │   ├── [pattern] "Renaming <tmp> to <target>"           // 原子重命名
    │   ├── [pattern] "File <path> written atomically"       // 原子写完成
    │   └── [pattern] "rg error (signal=<sig>, code=<N>, stderr: <msg>), <N> results"
    │       // ripgrep 执行错误，通常为目录不存在（os error 2 / os error 3）
    │
    ├── 4. API — API 调用完整链路
    │   ├── [pattern] "[API:request] Creating client, ANTHROPIC_CUSTOM_HEADERS present: <bool>, has Authorization header: <bool>"
    │   ├── [pattern] "[API:auth] OAuth token check starting" // OAuth 认证开始
    │   ├── [pattern] "[API:auth] OAuth token check complete"  // OAuth 认证完成
    │   ├── [pattern] "[API REQUEST] <endpoint> source=<source>"
    │   │   // endpoint = "/anthropic/v1/messages", source = repl_main_thread
    │   ├── [pattern] "Stream started - received first chunk"  // 收到第一个响应 chunk
    │   ├── [pattern] "attribution header x-anthropic-billing-header: <info>"
    │   │   // 计费/版本头，格式：cc_version=<ver>; cc_entrypoint=<entry>; cch=<hash>
    │   ├── [pattern] "autocompact: tokens=<used> threshold=<limit> effectiveWindow=<window>"
    │   │   // 上下文窗口监控，tokens = 当前占用，threshold = 压缩触发阈值
    │   └── [pattern] "Tool search disabled: <reason>"         // 工具搜索功能被禁用（非 Anthropic 原生 API）
    │
    ├── 5. LSP — 语言服务器协议
    │   ├── [pattern] "[LSP MANAGER] <action>"               // LSP 管理器生命周期
    │   │   ├── action = "initializeLspServerManager() called"
    │   │   ├── action = "Created manager instance, state=<state>"  // state = pending 等
    │   │   └── action = "reinitializeLspServerManager() called"
    │   ├── [pattern] "[LSP SERVER MANAGER] getAllLspServers returned <N> server(s)"
    │   ├── [pattern] "Loaded <N> LSP server(s) from plugin: <name>"
    │   ├── [pattern] "Total LSP servers loaded: <N>"
    │   ├── [pattern] "LSP manager initialized with <N> servers"
    │   ├── [pattern] "LSP server manager initialized successfully"
    │   ├── [pattern] "Queued request handler for <plugin:server>.<method> (connection not ready)"
    │   ├── [pattern] "Queued notification handler for <plugin:server>.<method> (connection not ready)"
    │   ├── [pattern] "Registered diagnostics handler for <plugin:server>"
    │   └── [pattern] "LSP Diagnostics: <action>"            // action = getLSPDiagnosticAttachments called / Checking registry - <N> pending
    │
    ├── 6. Hooks — 钩子系统
    │   ├── [pattern] "Loaded hooks from <source> for plugin <name>: <path>"
    │   ├── [pattern] "Registered <N> hooks from <N> plugins"
    │   ├── [pattern] "Hook <event> (<hookName>) <status>: <output>"
    │   │   // event = SessionStart:startup | SessionStart:resume 等
    │   │   // status = success | failure
    │   │   // 若 output 不以 "{" 开头 → "Hook output does not start with {, treating as plain text"
    │   ├── [pattern] "Hooks: Found <N> total hooks in registry"
    │   └── [pattern] "Hooks: checkForNewResponses returning <N> responses"
    │
    ├── 7. Rendering — 终端渲染
    │   ├── [pattern] "High write ratio: blit=<N>, write=<N> (<PCT>% writes), screen=<W>x<H>"
    │   │   // blit = 增量渲染字节数，write = 全量重写字节数，screen = 终端尺寸
    │   ├── [pattern] "[useDeferredValue] Messages deferred by <N> (<from>→<to>)"
    │   │   // 消息队列延迟渲染计数
    │   ├── [pattern] "Full reset (shrink->below): prevHeight=<H>, nextHeight=<H>, viewport=<H>"
    │   │   // 窗口缩小时的全量重置
    │   ├── [pattern] "[keybindings] KeyBindingSetup initialized with <N> bindings, <N> warnings"
    │   └── [pattern] "[keybindings] Skipping file watcher - user customization disabled"
    │
    ├── 8. Session — 会话管理
    │   ├── [pattern] "/resume: loading sessions for cwd=<path>, worktrees=[<paths>]"
    │   ├── [pattern] "/resume: found <N> session files on disk"
    │   ├── [pattern] "Cleared all session hooks for session <uuid>"
    │   ├── [pattern] "FileHistory: Copied backup <id>@<version> from session <src> to <dst>"
    │   ├── [pattern] "FileHistory: Making snapshot for message <uuid>"
    │   ├── [pattern] "FileHistory: Added snapshot for <uuid>, tracking <N> files"
    │   ├── [pattern] "[Reconnection] computeInitialTeamContext: No teammate context set (not a teammate)"
    │   └── [pattern] "[repl:mount] REPL mounted, disabled=<bool>"
    │
    ├── 9. Shell — Shell 执行
    │   ├── [pattern] "Creating shell snapshot for bash (<path>)"
    │   ├── [pattern] "Looking for shell config file: <path>"     // 查找 .bashrc 等
    │   ├── [pattern] "Shell config file not found: <path>, creating snapshot with Claude Code defaults only"
    │   ├── [pattern] "Snapshots directory: <path>"
    │   ├── [pattern] "Creating snapshot at: <path>"
    │   ├── [pattern] "Execution timeout: <N>ms"
    │   ├── [pattern] "Shell snapshot created successfully (<N> bytes)"
    │   ├── [pattern] "Session environment not yet supported on Windows"
    │   ├── [pattern] "Spawning shell without login (-l flag skipped)"
    │   └── [pattern] "Bash tool error (<N>ms): <reason>"        // 命令执行失败
    │
    ├── 10. Permission — 权限系统
    │   ├── [pattern] "Applying permission update: <operation> <N> <type> rule(s) to destination '<name>': [<rules>]"
    │   │   // operation = Adding | Removing, type = allow | deny, name = localSettings 等
    │   ├── [pattern] "Persisting permission update: <operation> to source '<name>'"
    │   ├── [pattern] "Persisting <N> <type> rule(s) to <destination>"
    │   ├── [pattern] "Permission suggestions for <ToolName>: [<JSON.rules>]"
    │   └── [pattern] "executePermissionRequestHooks called for tool: <ToolName>"
    │
    ├── 11. Settings — 配置管理
    │   ├── [pattern] "Watching for changes in setting files <paths>..."
    │   ├── [pattern] "CA certs: Config fallback - globalEnv keys: <keys>, settingsEnv keys: <keys>"
    │   └── [pattern] "CA certs: useSystemCA=<bool>, extraCertsPath=<path>"
    │
    ├── 12. FeatureGates — 功能开关与状态检查
    │   ├── [pattern] "[auto-mode] verifyAutoModeGateAccess: <key=value, ...>"
    │   │   // 自动模式准入检查，字段：enabledState / disabledBySettings / model / modelSupported / disableFastModeBreakerFires / carouselAvailable / canEnterAuto
    │   ├── [WARN pattern] "auto mode disabled: <reason>"
    │   ├── [pattern] "[3P telemetry] isTelemetryEnabled=<bool> (CLAUDE_CODE_ENABLE_TELEMETRY=<value>)"
    │   ├── [WARN pattern] "[3P telemetry] Event dropped (no event logger initialized): <eventName>"
    │   ├── [pattern] "[Bootstrap] Skipped: <reason>"           // 启动时被跳过的步骤
    │   ├── [pattern] "[ScheduledTasks] scheduler start() — enabled=<bool>, hasTasks=<bool>"
    │   ├── [pattern] "[Perfetto] initializePerfettoTracing called, env value: <value>"
    │   ├── [pattern] "AutoUpdaterWrapper: Installation type: <type>"  // type = npm-global 等
    │   └── [pattern] "Plugin autoupdate: <result>"             // 插件自动更新结果
    │
    └── 13. Browser — 浏览器集成
        ├── [pattern] "[Claude in Chrome] Found <browser> profiles: <names>"
        │   // browser = chrome | edge
        └── [pattern] "[Claude in Chrome] Extension not found in any browser"
```

---

## 日志级别分布

| 级别 | 含义 | 典型场景 |
|------|------|---------|
| `[DEBUG]` | 正常运行时信息 | 绝大多数日志行 |
| `[WARN]` | 非致命异常 | 自动模式禁用、telemetry 事件丢失、statusline 脚本退出码 127、commands 目录不存在 |

---

## 关键链路：一次 API 调用的完整日志序列

```
autocompact: tokens=<N> threshold=<N>               // 压缩阈值检查
attribution header: <version info>                   // 构建计费头
[API:request] Creating client                        // 创建 HTTP 客户端
[API:auth] OAuth token check starting                // 认证开始
[API:auth] OAuth token check complete                // 认证完成
[API REQUEST] /anthropic/v1/messages source=repl_main_thread  // 发起请求
Stream started - received first chunk                // 收到首个响应块
```

两轮 API 调用之间的间隔 = 模型推理耗时（不含首字节时间）。

---

## 重要说明

- **不记录请求体和响应体**：所有 `[DEBUG]` 行仅包含 harness 层的元数据，不包含用户消息内容、模型推理内容、工具调用参数
- **不记录 API Key**：`Authorization` header 的值不出现在日志中
- **日志文件位置**：由 `--debug-file <path>` 指定，未指定时输出到终端 stderr
- **分类过滤**：可用 `--debug "api,hooks"` 只记录指定分类，或 `--debug "!1p,!file"` 排除指定分类

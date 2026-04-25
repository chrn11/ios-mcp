# iOS MCP 功能增强方案 — 测试友好

> **项目**: ios-mcp  
> **场景**: 没有 Xcode，用 TrollStore + Dopamine 开发 IPA/Deb 插件，通过 MCP 测试  
> **原则**: 只加"方便测试"的功能，不要大而全

---

## 一、开发者的痛点

没有 Xcode 意味着：
- **没有控制台日志** — 插件写错了，看不到 NSLog 输出
- **没有崩溃调试** — 崩了只能去设备翻崩溃报告
- **没有快速重载** — 改一行代码要 respring 整个系统
- **没有文件推送** — 编译好的 deb/ipa 要手动 scp/mcp 上传再装
- **没有断点** — 只能靠日志和截图猜问题

当前 MCP 已有的 33 个工具解决的是"操控设备"，但在"测试插件"场景下，缺的是：

| 缺什么 | 现状 | 影响 |
|--------|------|------|
| 看日志 | 只能 `run_command("log stream ...")` 但一次就返回了，没法持续看 | 每改一行要看效果就要重新跑命令 |
| 看崩溃报告 | 要手动去 `/var/mobile/Library/Logs/CrashReporter/` 找 | 效率极低 |
| 重载 dylib | 只能 respring 整个系统，10 秒起步 | 迭代飞不起来 |
| 检查注入 | 不知道 tweak 有没有成功注入目标进程 | 排问题的第一步都做不了 |
| 偏好测试 | 改插件配置要手动改 plist 再 respring | 慢 |

---

## 二、增强方案（6 个新工具）

### 工具 1: `stream_logs` — 实时日志流

**最刚需。没有 Xcode console 的情况下，这是最核心的功能。**

```json
{
  "name": "stream_logs",
  "description": "Stream device logs in real-time. Returns log entries as they arrive. "
    "Filters by process name or subsystem. Essential for debugging tweaks and apps without Xcode.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "filter":      { "type": "string",  "description": "Grep pattern to filter logs (e.g. 'witchan', 'mytweak')" },
      "process":     { "type": "string",  "description": "Only show logs from this process name (e.g. 'SpringBoard')" },
      "level":       { "type": "string",  "description": "Minimum log level: debug/info/default/error/fault" },
      "duration":    { "type": "number",  "description": "How many seconds to capture (default 5, max 30)" },
      "max_lines":   { "type": "integer", "description": "Maximum lines to return (default 100, max 500)" }
    }
  }
}
```

**返回示例**:
```json
{
  "lines": 3,
  "logs": [
    {"time": "15:42:03", "process": "SpringBoard", "level": "default", "message": "[witchan][ios-mcp] MCP server started on port 8090"},
    {"time": "15:42:05", "process": "SpringBoard", "level": "error",   "message": "[mytweak] Failed to hook -viewDidLoad"},
    {"time": "15:42:08", "process": "MyApp",       "level": "debug",   "message": "[mytweak] Hooked -viewDidAppear"}
  ]
}
```

**实现**: 用 `run_command` 执行 `log stream --process X --timeout Y --style compact`，解析输出返回。或者用 `NSPipe` + `NSTask` 包装 OS-log API。

---

### 工具 2: `get_crash_reports` — 崩溃报告查看

**插件崩了，秒看原因。**

```json
{
  "name": "get_crash_reports",
  "description": "List and read device crash reports. Shows recent crashes for debugging tweaks and apps.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "action":     { "type": "string", "description": "'list' to see recent crashes, 'read' to get details", "enum": ["list", "read"] },
      "process":    { "type": "string", "description": "Filter by process name (e.g. 'SpringBoard')" },
      "report_id":  { "type": "string", "description": "Specific report ID to read (from list)" },
      "count":      { "type": "integer", "description": "Number of recent reports to list (default 10)" }
    },
    "required": ["action"]
  }
}
```

**实现**: 用 `run_command` 读 `/var/mobile/Library/Logs/CrashReporter/` 目录 + 解析 `.ips` 文件头部（异常类型、线程回溯）。

---

### 工具 3: `respring` / `reload_tweak` — 快速重载

**改完代码不用等 10 秒 respring，非 SpringBoard 的进程可以直接杀重启。**

```json
{
  "name": "respring",
  "description": "Restart SpringBoard. Equivalent to running 'killall SpringBoard'. "
    "Use after installing or updating a tweak that affects SpringBoard.",
  "inputSchema": { "type": "object", "properties": {} }
}
```

```json
{
  "name": "reload_tweak",
  "description": "Reload a tweak in a target process by killing and restarting it. "
    "Much faster than respring for iterative tweak development. "
    "For non-SpringBoard processes only.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "dylib":     { "type": "string", "description": "Dylib name to verify after reload (e.g. 'mytweak.dylib')" },
      "process":   { "type": "string", "description": "Target process bundle ID (e.g. 'com.apple.mobilesafari')" }
    },
    "required": ["process"]
  }
}
```

**实现**: `respring` = `killall SpringBoard`。`reload_tweak` = 杀死目标进程（kill_app 已有），系统自动重启并重新加载 dylib。

---

### 工具 4: `check_injection` — 检查 dylib 注入状态

**改完 tweak 不知道有没有注入进去？一眼看清。**

```json
{
  "name": "check_injection",
  "description": "Check if a tweak dylib is loaded in a running process. "
    "Essential for verifying your tweak is actually injected and running.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "dylib":    { "type": "string",  "description": "Dylib name to check (e.g. 'mytweak.dylib')" },
      "process":  { "type": "string",  "description": "Process name or bundle ID (e.g. 'SpringBoard', 'com.apple.mobilesafari')" }
    },
    "required": ["dylib"]
  }
}
```

**返回示例**:
```json
{
  "dylib": "mytweak.dylib",
  "process": "SpringBoard (PID 1234)",
  "injected": true,
  "path": "/Library/MobileSubstrate/DynamicLibraries/mytweak.dylib"
}
```

**实现**: 通过 `run_command` 读 `/proc/<pid>/maps` 或用 `launchctl procinfo` 查找 dylib。

---

### 工具 5: `read_plist` / `write_plist` — 快速偏好操作

**改插件配置不用 ssh 打 plist 文件。**

```json
{
  "name": "read_plist",
  "description": "Read a plist file or preferences domain from the device. "
    "Useful for checking app preferences, tweak settings, and Info.plist values.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path":   { "type": "string", "description": "Path to plist file, or a domain like 'com.witchan.ios-mcp'" },
      "key":    { "type": "string", "description": "Specific key to read (omit for all keys)" }
    },
    "required": ["path"]
  }
}
```

```json
{
  "name": "write_plist",
  "description": "Write a value to a plist file or preferences domain on the device. "
    "Useful for changing tweak settings during testing without respring.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "path":     { "type": "string", "description": "Path to plist file or domain" },
      "key":      { "type": "string", "description": "Key to set" },
      "value":    { "type": "string", "description": "Value to set (auto-detected as bool/int/string)" },
      "type":     { "type": "string", "description": "Force type: bool/int/string", "enum": ["bool","int","string"] }
    },
    "required": ["path", "key", "value"]
  }
}
```

**实现**: 通过 `run_command` 调用 `plutil -p` / `defaults read` / `defaults write`，或用 CFPrefs API。

---

### 工具 6: `tap_element` / `wait_for_element` — 智能交互

**AI 不应该靠猜坐标来点击。** 测试 UI 时极其方便。

```json
{
  "name": "tap_element",
  "description": "Tap a UI element by its accessibility label, identifier, or visible text. "
    "Much more reliable than coordinate-based tap_screen for testing app flows.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "label":       { "type": "string", "description": "Accessibility label to match" },
      "identifier":  { "type": "string", "description": "Accessibility identifier to match" },
      "text":        { "type": "string", "description": "Visible text to match" },
      "index":       { "type": "integer", "description": "When multiple matches, click the Nth one (0-based, default 0)" }
    }
  }
}
```

```json
{
  "name": "wait_for_element",
  "description": "Wait for a UI element to appear or disappear. "
    "Blocks until element is found or timeout. Essential for testing async UI like loading screens, alerts, navigation.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "label":       { "type": "string", "description": "Accessibility label to wait for" },
      "identifier":  { "type": "string", "description": "Accessibility identifier to wait for" },
      "text":        { "type": "string", "description": "Visible text to wait for" },
      "timeout":     { "type": "number", "description": "Seconds to wait (default 10, max 30)" },
      "disappear":   { "type": "boolean", "description": "Wait for element to disappear instead (default false)" }
    }
  }
}
```

**实现**: 遍历 AccessibilityManager 的 UI 树，匹配 label/id/text，提取中心坐标调用 `HIDManager.tapAtPoint`。wait 用 500ms 间隔轮询。

---

## 三、必要安全（2 项，极简）

### 3.1 命令黑名单

`run_command` 直接跑 `rm -rf /` 太危险。加正则过滤：

```
禁止: rm -rf /, dd if=, mkfs, fork bomb
其他照旧
```

在 `MCPServer.m:executeRunCommand:` 开头加检查。

### 3.2 UI 树安全字段

`get_ui_elements` 遇到 `isSecureTextEntry=YES` 的字段不返回 value，标记 `secureTextField:YES`。

---

## 四、不需要的

| 被砍的 | 原因 |
|--------|------|
| HTTP 认证 / TLS | 局域网不需要 |
| Token 配对 | 同上 |
| 速率限制 | 自己测试用 |
| 文件浏览器 | 有 run_command 够了 |
| 录屏 | 截图够用 |
| 联系人/照片 | 和测试插件无关 |
| 位置模拟 | 用 run_command 即可 |
| 剪贴板图片 | 优先级太低 |
| 通知读取 | stream_logs 更通用 |
| 双指缩放 | 测试用例少 |

---

## 五、实施计划

| 顺序 | 工具 | 预估 | 理由 |
|------|------|------|------|
| **1** | `stream_logs` | 1-2 天 | 没有日志就是在瞎试，第一刚需 |
| **2** | `get_crash_reports` | 1 天 | 崩了要能秒看原因 |
| **3** | `tap_element` + `wait_for_element` | 2-3 天 | 不用截图猜坐标 |
| **4** | `respring` + `reload_tweak` | 1 天 | 快速迭代 |
| **5** | `check_injection` | 0.5 天 | 排问题第一步 |
| **6** | `read_plist` / `write_plist` | 1 天 | 改配置不用 ssh |
| S1 | 命令黑名单 | 0.5 天 | 防误操作 |
| S2 | UI 安全字段过滤 | 0.5 天 | 防密码泄露 |

**总计约 8-10 天**。

---

## 六、优先级只有一个标准

> **能不能让我在没有 Xcode 的情况下更快地测我的 tweak？**

这个标准下排序：
1. **`stream_logs`** — 没有日志完全是在盲测
2. **`get_crash_reports`** — 崩了要能秒查
3. **`tap_element` + `wait_for_element`** — 不用截图猜坐标
4. **`respring` / `reload_tweak`** — 快速迭代
5. **`check_injection`** — 排问题第一步
6. **`read_plist` / `write_plist`** — 改配置方便

---

*文档版本: 3.0 | 日期: 2026-04-25 | 聚焦：没有 Xcode 的插件开发测试体验*
# claude-lark

[![CI](https://github.com/ysyecust/claude-lark/actions/workflows/ci.yml/badge.svg)](https://github.com/ysyecust/claude-lark/actions/workflows/ci.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Claude Code → 飞书通知**

[English](README.md)

Claude Code 完成任务或需要你确认时，自动发送飞书消息提醒——让你可以放心离开终端，回来时不会错过任何事。

---

## 特性

- **零依赖** — 纯 Python 标准库，不需要 `pip install`
- **无需服务** — 本地 hook 脚本直接调飞书 API，不用跑任何后台服务
- **轻量快速** — token 自动缓存（2 小时有效），每次通知仅 ~100ms
- **静默失败** — 任何异常都不会阻塞 Claude Code
- **丰富卡片** — 项目、设备、统计（tokens / 工具 / 耗时）、git 信息、Claude 回复
- **多事件支持** — 任务完成、权限确认、等待输入等不同场景使用不同卡片样式
- **手机号/邮箱安装** — 无需手动查 Open ID，安装器自动通过手机号或邮箱获取
- **子 Agent 感知** — 追踪并展示 Claude Code 派生的子 Agent

## 工作原理

```
Claude Code 事件 (Stop / Notification)
  → 触发本地 hook 脚本
    → 获取飞书 tenant_access_token（有缓存）
      → 调飞书消息 API 发送卡片
        → 你在飞书收到通知
```

只有 2 个 HTTP 请求，全部在本地完成，不依赖任何中间服务。

---

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/ysyecust/claude-lark.git
cd claude-lark
```

### 2. 运行安装器

**macOS / Linux:**
```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

**Windows (PowerShell):**
```powershell
.\scripts\install.ps1
```

安装器会引导你完成：

1. 输入飞书机器人凭证（App ID + App Secret，团队管理员提供）
2. 选择身份验证方式（**手机号** / 邮箱 / 直接输入 Open ID）
3. 自动验证 API 连接
4. 发送测试通知到你的飞书
5. 自动配置 Claude Code hooks

### 3. 完成

之后 Claude Code 每次完成回复，你都会在飞书收到通知卡片。

---

## 配置

配置文件位于 `~/.config/claude-lark/config.json`（权限 600，仅用户可读）：

```json
{
    "app_id": "cli_xxx",
    "app_secret": "xxx",
    "open_id": "ou_xxx",
    "events": ["Stop", "Notification"]
}
```

| 字段 | 说明 | 来源 |
|------|------|------|
| `app_id` | 飞书机器人 App ID | 团队管理员提供 |
| `app_secret` | 飞书机器人 App Secret | 团队管理员提供 |
| `open_id` | 你的飞书 Open ID | 安装器自动获取 |
| `events` | 通知哪些事件（可选） | 默认 `["Stop", "Notification"]` |

### 事件过滤

通过 `events` 字段控制通知哪些事件：

```json
{
    "events": ["Stop"]
}
```

| 值 | 含义 |
|----|------|
| `Stop` | Claude Code 完成回复时通知 |
| `Notification` | Claude Code 需要确认/输入时通知 |

如果只想在任务完成时收到通知，去掉 `"Notification"` 即可。

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CLAUDE_LARK_TZ_OFFSET` | 时区偏移（相对 UTC 的小时数） | `8`（Asia/Shanghai） |

---

## 通知卡片

### ✅ 任务完成 (Stop)

Claude Code 完成回复时发送，turquoise 绿色卡片：

| 信息 | 说明 |
|------|------|
| 项目 | 当前工作目录的项目名 |
| 设备 | 运行 Claude Code 的主机名 |
| 统计 | 耗时、tokens（本轮/总计）、工具调用（本轮/总计）、对话轮次、git 分支 |
| 子 Agent | 本轮新派生的 Agent，显示类型和描述 |
| Git | 最近提交、分支、是否有未提交更改 |
| 回复 | Claude 最后一条回复（markdown 转换后，最长 4000 字） |

### ⚠️ 需要确认 (Notification)

Claude Code 需要你的输入时发送，根据类型使用不同颜色：

| 类型 | 颜色 | 含义 |
|------|------|------|
| `permission_prompt` | 🟠 橙色 | Claude 需要执行权限 |
| `idle_prompt` | 🟡 黄色 | Claude 等待你的输入 |
| `auth_success` | 🟢 绿色 | 认证完成 |
| `elicitation_dialog` | 🔵 蓝色 | Claude 需要额外信息 |

### 🔧 子 Agent 完成

蓝色卡片，标明来自 worktree/swarm 子 Agent，与主 Agent 通知明确区分。

---

## 飞书机器人配置（团队管理员操作）

> 完整指南含常见问题排查：[docs/admin-setup.md](docs/admin-setup.md)

### 创建机器人

1. 打开 [飞书开放平台](https://open.feishu.cn/app)
2. 创建 **自建应用**
3. **添加应用能力** → 开启 **机器人**

### 配置权限

在 **权限管理** 中开通以下权限：

| 权限 | 权限标识 | 用途 |
|------|---------|------|
| 发送消息 | `im:message:send_as_bot` | 发送通知卡片（必需） |
| 获取用户 ID | `contact:user.id:readonly` | 安装时通过手机号/邮箱查找用户（推荐） |

### 发布应用

1. **版本管理** → 创建版本 → 发布
2. 在管理后台审批通过

### 分发给团队

将以下信息发给团队成员：

```
App ID:     cli_xxxxxxxx
App Secret: xxxxxxxx
```

团队成员运行 `./install.sh`，输入手机号即可完成配置。

---

## 手动安装

如果不想使用安装器，手动配置：

### 1. 创建配置文件

```bash
mkdir -p ~/.config/claude-lark
cat > ~/.config/claude-lark/config.json << 'EOF'
{
    "app_id": "cli_xxx",
    "app_secret": "xxx",
    "open_id": "ou_xxx",
    "events": ["Stop", "Notification"]
}
EOF
chmod 600 ~/.config/claude-lark/config.json
```

### 2. 编辑 Claude Code 设置

在 `~/.claude/settings.json` 的 `hooks` 中添加：

```json
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/claude_lark_notify.py",
            "timeout": 30
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/claude_lark_notify.py",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

### 3. 测试

```bash
echo '{"hook_event_name":"Stop","cwd":"/tmp/test","session_id":"test","last_assistant_message":"Hello!"}' \
  | python3 /path/to/claude_lark_notify.py
```

---

## 卸载

**macOS / Linux:**
```bash
./scripts/uninstall.sh
```

**Windows:**
```powershell
.\scripts\uninstall.ps1
```

自动移除 Claude Code hooks，可选删除配置文件。

---

## 项目结构

```
claude-lark/
├── claude_lark_notify.py   # Hook 脚本（单文件，纯 stdlib）
├── install.sh              # 交互式安装器
├── uninstall.sh            # 卸载脚本
├── config.example.json     # 配置示例
├── tests/                  # 测试套件（57 个测试）
├── CONTRIBUTING.md         # 贡献指南
├── CHANGELOG.md            # 版本历史
├── LICENSE                 # MIT
└── README.md
```

## 系统要求

- Python 3.8+（macOS / Linux 自带；Windows 需 [安装](https://www.python.org/downloads/)）
- [Claude Code](https://claude.ai/claude-code) CLI
- 飞书自建应用（需 `im:message:send_as_bot` 权限）
- **Windows**: PowerShell 5.1+（系统自带）

## FAQ

**Q: 会不会拖慢 Claude Code？**

不会。hook 脚本超时设为 30 秒，实际执行约 100ms。即使网络异常也会静默退出，不影响 Claude Code。

**Q: token 是怎么缓存的？**

`tenant_access_token` 缓存在 `~/.config/claude-lark/.token_cache`，有效期 2 小时。过期后自动刷新。

**Q: 通知太频繁怎么办？**

在配置中设置 `"events": ["Notification"]`，只在需要确认时通知，不在每次回复完成时通知。

**Q: 多台电脑怎么办？**

每台电脑独立运行 `install.sh`，使用同一套 App ID/Secret 和你的手机号即可。卡片会显示设备名，方便区分。

**Q: Open ID 是什么？怎么获取？**

Open ID 是飞书为每个用户在每个应用下生成的唯一标识。安装器支持通过手机号或邮箱自动查询，无需手动获取。

## License

MIT

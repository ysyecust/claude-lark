# claude-lark

[![CI](https://github.com/ysyecust/claude-lark/actions/workflows/ci.yml/badge.svg)](https://github.com/ysyecust/claude-lark/actions/workflows/ci.yml)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Claude Code → Lark (Feishu) Notifications**

[中文文档](README_zh.md)

Get instant Lark messages when Claude Code finishes a task or needs your attention — step away from the terminal without missing anything.

---

## Features

- **Zero dependencies** — Python 3.8+ stdlib only, no `pip install`
- **No server needed** — local hook script calls Lark API directly
- **Fast** — token caching (2h TTL), ~100ms per notification
- **Silent failures** — never blocks Claude Code
- **Rich cards** — project, device, stats (tokens, tools, duration), git info, Claude's response
- **Multiple event types** — task completion, permission prompts, idle prompts with distinct card styles
- **Phone/email install** — auto-lookup Open ID during setup, no manual steps
- **Sub-agent aware** — tracks and displays spawned sub-agents

## How it Works

```
Claude Code event (Stop / Notification)
  → triggers local hook script
    → fetches Lark tenant_access_token (cached)
      → calls Lark message API to send card
        → you receive a notification in Lark
```

Just 2 HTTP requests, all local. No intermediate server.

---

## Quick Start

### 1. Clone

```bash
git clone https://github.com/ysyecust/claude-lark.git
cd claude-lark
```

### 2. Install

**macOS / Linux:**
```bash
chmod +x scripts/install.sh
./scripts/install.sh
```

**Windows (PowerShell):**
```powershell
.\scripts\install.ps1
```

The installer will:

1. Ask for Lark Bot credentials (App ID + App Secret, provided by team admin)
2. Choose identity lookup method (**phone number** / email / direct Open ID)
3. Verify API connection
4. Send a test notification
5. Configure Claude Code hooks automatically

### 3. Done

From now on, every time Claude Code finishes a response, you'll receive a Lark card notification.

---

## Configuration

Config file: `~/.config/claude-lark/config.json` (permissions 600):

```json
{
    "app_id": "cli_xxx",
    "app_secret": "xxx",
    "open_id": "ou_xxx",
    "events": ["Stop", "Notification"]
}
```

| Field | Description | Source |
|-------|-------------|--------|
| `app_id` | Lark Bot App ID | Team admin |
| `app_secret` | Lark Bot App Secret | Team admin |
| `open_id` | Your Lark Open ID | Auto-detected by installer |
| `events` | Which events to notify (optional) | Default: `["Stop", "Notification"]` |

### Event Filtering

Control which events trigger notifications:

```json
{
    "events": ["Stop"]
}
```

| Value | Meaning |
|-------|---------|
| `Stop` | Notify when Claude Code finishes a response |
| `Notification` | Notify when Claude Code needs confirmation/input |

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CLAUDE_LARK_TZ_OFFSET` | Timezone offset from UTC (hours) | `8` (Asia/Shanghai) |

---

## Notification Cards

### ✅ Task Complete (Stop)

Turquoise card sent when Claude Code finishes a response:

| Info | Description |
|------|-------------|
| Project | Current working directory name |
| Device | Hostname of the machine running Claude Code |
| Stats | Duration, tokens (turn/total), tools (turn/total), conversation turns, git branch |
| Sub-agents | Newly spawned agents with type and description |
| Git | Latest commit, branch, dirty status |
| Response | Claude's last message (markdown-cleaned, up to 4000 chars) |

### ⚠️ Attention Needed (Notification)

Sent when Claude Code needs your input, with color-coded headers:

| Type | Color | Meaning |
|------|-------|---------|
| `permission_prompt` | Orange | Claude needs execution permission |
| `idle_prompt` | Yellow | Claude is waiting for your input |
| `auth_success` | Green | Authentication completed |
| `elicitation_dialog` | Blue | Claude needs additional information |

### 🔧 Sub-Agent Complete

Blue card for worktree/swarm sub-agent completions, clearly distinguished from main agent notifications.

---

## Lark Bot Setup (Team Admins)

> Full guide with troubleshooting: [docs/admin-setup.md](docs/admin-setup.md)

### Create Bot

1. Go to [Lark Open Platform](https://open.feishu.cn/app)
2. Create a **Custom App**
3. **Add capabilities** → enable **Bot**

### Permissions

Enable these in **Permission Management**:

| Permission | Identifier | Purpose |
|-----------|------------|---------|
| Send messages | `im:message:send_as_bot` | Send notification cards (required) |
| Get user ID | `contact:user.id:readonly` | Lookup users by phone/email during install (recommended) |

### Publish & Distribute

1. **Version Management** → Create version → Publish
2. Approve in admin console
3. Share App ID and App Secret with your team

---

## Manual Installation

If you prefer not to use the installer:

### 1. Create config

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

### 2. Add Claude Code hooks

Add to `~/.claude/settings.json`:

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

### 3. Test

```bash
echo '{"hook_event_name":"Stop","cwd":"/tmp/test","session_id":"test","last_assistant_message":"Hello!"}' \
  | python3 /path/to/claude_lark_notify.py
```

---

## Uninstall

**macOS / Linux:**
```bash
./scripts/uninstall.sh
```

**Windows:**
```powershell
.\scripts\uninstall.ps1
```

Removes Claude Code hooks and optionally deletes config files.

---

## Project Structure

```
claude-lark/
├── claude_lark_notify.py       # Hook script (single file, stdlib only)
├── scripts/
│   ├── install.sh              # Installer (macOS/Linux)
│   ├── install.ps1             # Installer (Windows)
│   ├── uninstall.sh            # Uninstaller (macOS/Linux)
│   └── uninstall.ps1           # Uninstaller (Windows)
├── tests/                      # Test suite (58 tests)
├── docs/
│   └── admin-setup.md          # Lark Bot admin guide
├── config.example.json
├── CONTRIBUTING.md / CHANGELOG.md / LICENSE
└── README.md / README_zh.md
```

## Requirements

- Python 3.8+ (pre-installed on macOS / Linux; [download](https://www.python.org/downloads/) for Windows)
- [Claude Code](https://claude.ai/claude-code) CLI
- Lark Custom App with `im:message:send_as_bot` permission
- **Windows**: PowerShell 5.1+ (built-in)

## FAQ

**Q: Will it slow down Claude Code?**

No. The hook timeout is 30s, but actual execution is ~100ms. Any errors exit silently without affecting Claude Code.

**Q: How is the token cached?**

`tenant_access_token` is cached at `~/.config/claude-lark/.token_cache` with a 2-hour TTL. Auto-refreshes when expired.

**Q: Too many notifications?**

Set `"events": ["Notification"]` in config to only get notified when Claude needs your input, not on every response.

**Q: Multiple machines?**

Run `install.sh` on each machine with the same App ID/Secret and your phone number. Cards show the device name so you can tell them apart.

**Q: What is Open ID?**

A unique identifier Lark generates for each user per app. The installer auto-detects it via phone number or email — no manual lookup needed.

## License

MIT

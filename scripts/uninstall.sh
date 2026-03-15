#!/usr/bin/env bash
#
# claude-lark uninstaller
# Removes hooks from Claude Code settings and cleans up config.
#
set -euo pipefail

CONFIG_DIR="$HOME/.config/claude-lark"
SETTINGS_FILE="$HOME/.claude/settings.json"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

info()  { echo -e "${CYAN}[info]${NC}  $*"; }
ok()    { echo -e "${GREEN}[ok]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC}  $*"; }

echo ""
echo -e "${BOLD}claude-lark${NC} — Uninstaller"
echo -e "────────────────────────────"
echo ""

# ── Remove hooks from settings.json ──────────────────────────────────
if [[ -f "$SETTINGS_FILE" ]]; then
    info "从 Claude Code settings 中移除 hooks..."
    python3 << 'PYEOF'
import json, os

settings_path = os.path.expanduser("~/.claude/settings.json")
with open(settings_path, "r") as f:
    settings = json.load(f)

hooks = settings.get("hooks", {})
modified = False

for event_type in ("Stop", "Notification"):
    entries = hooks.get(event_type, [])
    filtered = []
    for entry in entries:
        hook_list = entry.get("hooks", [])
        cleaned = [h for h in hook_list if "claude_lark_notify" not in h.get("command", "")]
        if cleaned:
            entry["hooks"] = cleaned
            filtered.append(entry)
        elif hook_list != cleaned:
            modified = True
            continue
        else:
            filtered.append(entry)
    if len(filtered) != len(entries):
        modified = True
    hooks[event_type] = filtered
    # Remove empty event arrays
    if not hooks[event_type]:
        del hooks[event_type]
        modified = True

if modified:
    settings["hooks"] = hooks
    with open(settings_path, "w") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    print("REMOVED")
else:
    print("NOT_FOUND")
PYEOF
    ok "Claude Code hooks 已移除"
else
    info "未找到 Claude Code settings.json，跳过"
fi

# ── Remove config ────────────────────────────────────────────────────
if [[ -d "$CONFIG_DIR" ]]; then
    echo ""
    read -rp "是否删除配置文件 ($CONFIG_DIR)？[y/N] " DELETE_CONFIG
    if [[ "$DELETE_CONFIG" =~ ^[Yy] ]]; then
        rm -rf "$CONFIG_DIR"
        ok "配置目录已删除"
    else
        info "保留配置目录"
    fi
else
    info "未找到配置目录，跳过"
fi

echo ""
echo -e "${GREEN}${BOLD}卸载完成。${NC}"
echo ""

#!/usr/bin/env bash
#
# claude-lark installer
# Configures Claude Code hooks to send Lark (飞书) notifications.
#
# Usage:
#   ./install.sh                        # Interactive
#   ./install.sh --phone 138xxxx        # Auto-lookup open_id by phone
#   ./install.sh --email foo@bar.com    # Auto-lookup open_id by email
#   ./install.sh --open-id ou_xxx       # Direct open_id
#   ./install.sh --hooks-only           # Skip credentials, only install hooks
#
set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────
CONFIG_DIR="$HOME/.config/claude-lark"
CONFIG_FILE="$CONFIG_DIR/config.json"
SETTINGS_FILE="$HOME/.claude/settings.json"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NOTIFY_SCRIPT="$PROJECT_DIR/claude_lark_notify.py"

# ── Colors ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

info()  { echo -e "${CYAN}[info]${NC}  $*"; }
ok()    { echo -e "${GREEN}  ✓${NC}   $*"; }
warn()  { echo -e "${YELLOW}  ⚠${NC}   $*"; }
error() { echo -e "${RED}  ✗${NC}   $*"; exit 1; }
step()  { echo -e "\n${BOLD}$1${NC}"; }

# ── Parse args ────────────────────────────────────────────────────────
OPEN_ID="" ; APP_ID="" ; APP_SECRET="" ; PHONE="" ; EMAIL=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --open-id)    OPEN_ID="$2";    shift 2 ;;
        --app-id)     APP_ID="$2";     shift 2 ;;
        --app-secret) APP_SECRET="$2"; shift 2 ;;
        --phone)      PHONE="$2";      shift 2 ;;
        --email)      EMAIL="$2";      shift 2 ;;
        --hooks-only) HOOKS_ONLY=true; shift ;;
        -h|--help)
            echo "Usage: $0 [--phone 138xxx | --email x@y.com | --open-id ou_xxx]"
            echo "       [--app-id cli_xxx] [--app-secret xxx]"
            echo "       [--hooks-only]  # Skip credentials, only install hooks"
            exit 0 ;;
        *) error "Unknown argument: $1" ;;
    esac
done

# ── Banner ────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}  claude-lark${NC}  ${DIM}v1.0${NC}"
echo -e "  Claude Code → 飞书通知"
echo -e "  ─────────────────────────────────"
echo ""

# ── Check Python 3 ───────────────────────────────────────────────────
command -v python3 &>/dev/null || error "需要 python3 (3.8+)，请先安装。"
ok "python3 $(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"

[[ -f "$NOTIFY_SCRIPT" ]] || error "未找到 claude_lark_notify.py: $NOTIFY_SCRIPT"

# ── Helper: read existing config value ────────────────────────────────
_cfg_val() {
    [[ -f "$CONFIG_FILE" ]] || return 1
    python3 -c "import json; print(json.load(open('$CONFIG_FILE')).get('$1',''))" 2>/dev/null
}

# ── Auto-detect non-interactive mode ─────────────────────────────────
# If --hooks-only is set, or config already has complete credentials and
# no credential arguments were passed, skip Steps 1-3.
if [[ "${HOOKS_ONLY:-false}" != "true" && -z "$APP_ID" && -z "$APP_SECRET" && \
      -z "$PHONE" && -z "$EMAIL" && -z "$OPEN_ID" ]]; then
    # Check if config already has all required fields
    _existing_app_id=$(_cfg_val app_id) || _existing_app_id=""
    _existing_secret=$(_cfg_val app_secret) || _existing_secret=""
    _existing_oid=$(_cfg_val open_id) || _existing_oid=""
    if [[ -n "$_existing_app_id" && -n "$_existing_secret" && -n "$_existing_oid" ]]; then
        HOOKS_ONLY=true
        info "检测到完整配置文件，跳过凭证设置"
    fi
fi

if [[ "${HOOKS_ONLY:-false}" == "true" ]]; then
    # Verify config exists
    [[ -f "$CONFIG_FILE" ]] || error "配置文件不存在: $CONFIG_FILE，请先放置配置文件"
    APP_ID=$(_cfg_val app_id) || error "配置文件缺少 app_id"
    APP_SECRET=$(_cfg_val app_secret) || error "配置文件缺少 app_secret"
    OPEN_ID=$(_cfg_val open_id) || error "配置文件缺少 open_id"

    step "Step 1/2  验证 API 连接"
    TOKEN=$(LARK_APP_ID="$APP_ID" LARK_APP_SECRET="$APP_SECRET" python3 -c "
import json, urllib.request, sys, os
req = urllib.request.Request(
    'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/',
    data=json.dumps({'app_id': os.environ['LARK_APP_ID'], 'app_secret': os.environ['LARK_APP_SECRET']}).encode(),
    headers={'Content-Type': 'application/json'}, method='POST')
try:
    data = json.loads(urllib.request.urlopen(req, timeout=10).read())
    if data.get('code') == 0: print(data['tenant_access_token'])
    else: print('FAIL:' + data.get('msg',''), file=sys.stderr); sys.exit(1)
except Exception as e: print('FAIL:' + str(e), file=sys.stderr); sys.exit(1)
" 2>&1) || error "API 连接失败，请检查配置文件中的凭证"
    ok "飞书 API 连接成功"

    step "Step 2/2  安装 hooks"
else
# ══════════════════════════════════════════════════════════════════════
#  Step 1: Collect Bot Credentials
# ══════════════════════════════════════════════════════════════════════
step "Step 1/4  飞书机器人凭证"

# App ID
if [[ -z "$APP_ID" ]]; then
    EXISTING=$(_cfg_val app_id) || EXISTING=""
    if [[ -n "$EXISTING" ]]; then
        read -rp "  App ID [$EXISTING]: " APP_ID
        APP_ID="${APP_ID:-$EXISTING}"
    else
        read -rp "  App ID: " APP_ID
    fi
fi
[[ -z "$APP_ID" ]] && error "App ID 不能为空"

# App Secret
if [[ -z "$APP_SECRET" ]]; then
    EXISTING=$(_cfg_val app_secret) || EXISTING=""
    if [[ -n "$EXISTING" ]]; then
        read -rsp "  App Secret [已保存，回车跳过]: " APP_SECRET; echo ""
        APP_SECRET="${APP_SECRET:-$EXISTING}"
    else
        read -rsp "  App Secret: " APP_SECRET; echo ""
    fi
fi
[[ -z "$APP_SECRET" ]] && error "App Secret 不能为空"

# Verify credentials
step "Step 2/4  验证 API 连接"
TOKEN=$(LARK_APP_ID="$APP_ID" LARK_APP_SECRET="$APP_SECRET" python3 -c "
import json, urllib.request, sys, os
req = urllib.request.Request(
    'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/',
    data=json.dumps({'app_id': os.environ['LARK_APP_ID'], 'app_secret': os.environ['LARK_APP_SECRET']}).encode(),
    headers={'Content-Type': 'application/json'}, method='POST')
try:
    data = json.loads(urllib.request.urlopen(req, timeout=10).read())
    if data.get('code') == 0: print(data['tenant_access_token'])
    else: print('FAIL:' + data.get('msg',''), file=sys.stderr); sys.exit(1)
except Exception as e: print('FAIL:' + str(e), file=sys.stderr); sys.exit(1)
" 2>&1) || error "API 连接失败，请检查 App ID 和 App Secret"
ok "飞书 API 连接成功"

# ══════════════════════════════════════════════════════════════════════
#  Step 3: Get Open ID
# ══════════════════════════════════════════════════════════════════════
step "Step 3/4  确定你的飞书身份"

# If no open_id, phone, or email provided, ask user to choose
if [[ -z "$OPEN_ID" && -z "$PHONE" && -z "$EMAIL" ]]; then
    EXISTING=$(_cfg_val open_id) || EXISTING=""
    echo ""
    echo -e "  ${DIM}选择查找方式:${NC}"
    echo "  1) 手机号（推荐）"
    echo "  2) 邮箱"
    echo "  3) 直接输入 Open ID"
    if [[ -n "$EXISTING" ]]; then
        echo -e "  4) 使用已保存的 Open ID ${DIM}($EXISTING)${NC}"
    fi
    echo ""
    read -rp "  请选择 [1]: " CHOICE
    CHOICE="${CHOICE:-1}"

    case "$CHOICE" in
        1) read -rp "  飞书手机号: " PHONE ;;
        2) read -rp "  飞书邮箱: " EMAIL ;;
        3) read -rp "  Open ID: " OPEN_ID ;;
        4) OPEN_ID="$EXISTING" ;;
        *) error "无效选择" ;;
    esac
fi

# Lookup by phone or email
if [[ -n "$PHONE" || -n "$EMAIL" ]]; then
    info "通过 ${PHONE:+手机号}${EMAIL:+邮箱} 查询 Open ID..."

    OPEN_ID=$(LARK_TOKEN="$TOKEN" LARK_PHONE="$PHONE" LARK_EMAIL="$EMAIL" python3 -c "
import json, urllib.request, sys, os
token = os.environ['LARK_TOKEN']
phone = os.environ.get('LARK_PHONE', '')
email = os.environ.get('LARK_EMAIL', '')
payload = {}
if phone: payload['mobiles'] = [phone]
if email: payload['emails'] = [email]
req = urllib.request.Request(
    'https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id',
    data=json.dumps(payload).encode(),
    headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'},
    method='POST')
try:
    resp = urllib.request.urlopen(req, timeout=10)
    data = json.loads(resp.read())
    if data.get('code') != 0:
        print('FAIL:' + data.get('msg',''), file=sys.stderr); sys.exit(1)
    users = data.get('data',{}).get('user_list',[])
    if not users or not users[0].get('user_id'):
        print('FAIL:未找到用户', file=sys.stderr); sys.exit(1)
    print(users[0]['user_id'])
except Exception as e:
    print('FAIL:' + str(e), file=sys.stderr); sys.exit(1)
" 2>&1) || error "查询失败: $OPEN_ID"

    ok "查询成功: $OPEN_ID"
fi

[[ -z "$OPEN_ID" ]] && error "Open ID 不能为空"

# ══════════════════════════════════════════════════════════════════════
#  Write config + install hooks
# ══════════════════════════════════════════════════════════════════════
step "Step 4/4  安装"

# Write config
mkdir -p "$CONFIG_DIR"
LARK_APP_ID="$APP_ID" LARK_APP_SECRET="$APP_SECRET" LARK_OPEN_ID="$OPEN_ID" \
LARK_CONFIG_FILE="$CONFIG_FILE" python3 -c "
import json, os
cfg = {'app_id': os.environ['LARK_APP_ID'], 'app_secret': os.environ['LARK_APP_SECRET'],
       'open_id': os.environ['LARK_OPEN_ID'], 'events': ['Stop', 'Notification']}
with open(os.environ['LARK_CONFIG_FILE'], 'w') as f: json.dump(cfg, f, indent=4)
"
chmod 600 "$CONFIG_FILE"
ok "配置已保存  $CONFIG_FILE"

fi  # end of interactive vs hooks-only

# Install Claude Code hooks
HOOK_CMD="python3 $NOTIFY_SCRIPT"
mkdir -p "$HOME/.claude"

if [[ -f "$SETTINGS_FILE" ]]; then
    python3 << PYEOF
import json

with open("$SETTINGS_FILE", "r") as f:
    settings = json.load(f)

hooks = settings.setdefault("hooks", {})
hook_cmd = "$HOOK_CMD"
entry = {"matcher": "", "hooks": [{"type": "command", "command": hook_cmd, "timeout": 30}]}

for ev in ("Stop", "Notification"):
    entries = hooks.setdefault(ev, [])
    already = any("claude_lark_notify" in h.get("command", "") for e in entries for h in e.get("hooks", []))
    if not already:
        entries.append(entry)

with open("$SETTINGS_FILE", "w") as f:
    json.dump(settings, f, indent=2, ensure_ascii=False)
PYEOF
else
    python3 -c "
import json
hook_cmd = '$HOOK_CMD'
entry = {'matcher': '', 'hooks': [{'type': 'command', 'command': hook_cmd, 'timeout': 30}]}
settings = {'hooks': {'Stop': [entry], 'Notification': [entry]}}
with open('$SETTINGS_FILE', 'w') as f: json.dump(settings, f, indent=2)
"
fi
ok "Claude Code hooks 已配置"

# ── Test notification ─────────────────────────────────────────────────
echo ""
read -rp "  发送测试通知？[Y/n] " SEND_TEST
if [[ "${SEND_TEST:-Y}" =~ ^[Yy] ]]; then
    echo '{"hook_event_name":"Stop","cwd":"'"$SCRIPT_DIR"'","session_id":"install-test","last_assistant_message":"🎉 claude-lark 安装成功！\n\n你现在可以收到 Claude Code 的飞书通知了。去终端试试吧。"}' \
        | python3 "$NOTIFY_SCRIPT"
    ok "测试通知已发送，请查看飞书"
fi

# ── Done ──────────────────────────────────────────────────────────────
echo ""
echo -e "  ${GREEN}${BOLD}安装完成 ✓${NC}"
echo ""
echo -e "  ${DIM}配置${NC}   $CONFIG_FILE"
echo -e "  ${DIM}脚本${NC}   $NOTIFY_SCRIPT"
echo -e "  ${DIM}卸载${NC}   ./uninstall.sh"
echo ""
echo "  Claude Code 每次完成任务，你都会在飞书收到通知。"
echo ""

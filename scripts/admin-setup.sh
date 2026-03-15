#!/usr/bin/env bash
#
# claude-lark admin batch setup
# Generate config files for team members without exposing app credentials.
#
# Usage:
#   ./scripts/admin-setup.sh
#   ./scripts/admin-setup.sh --app-id cli_xxx --app-secret xxx
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUTPUT_DIR="$PROJECT_DIR/team-configs"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'
BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

info()  { echo -e "${CYAN}[info]${NC}  $*"; }
ok()    { echo -e "${GREEN}  ✓${NC}   $*"; }
error() { echo -e "${RED}  ✗${NC}   $*"; exit 1; }

# ── Parse args ────────────────────────────────────────────────────────
APP_ID="" ; APP_SECRET=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --app-id)     APP_ID="$2";     shift 2 ;;
        --app-secret) APP_SECRET="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--app-id cli_xxx] [--app-secret xxx]"
            echo ""
            echo "Batch-generate config.json files for team members."
            echo "Prompts for phone numbers, looks up Open IDs, outputs"
            echo "ready-to-distribute config files."
            exit 0 ;;
        *) error "Unknown: $1" ;;
    esac
done

echo ""
echo -e "${BOLD}claude-lark${NC} — 团队批量配置 / Team Batch Setup"
echo -e "───────────────────────────────────────────────"
echo ""

# ── Collect credentials ──────────────────────────────────────────────
if [[ -z "$APP_ID" ]]; then
    read -rp "  App ID: " APP_ID
fi
[[ -z "$APP_ID" ]] && error "App ID is required"

if [[ -z "$APP_SECRET" ]]; then
    read -rsp "  App Secret: " APP_SECRET; echo ""
fi
[[ -z "$APP_SECRET" ]] && error "App Secret is required"

# ── Get token ────────────────────────────────────────────────────────
info "验证 API 连接..."
TOKEN=$(LARK_APP_ID="$APP_ID" LARK_APP_SECRET="$APP_SECRET" python3 -c "
import json, urllib.request, sys, os
req = urllib.request.Request(
    'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/',
    data=json.dumps({'app_id': os.environ['LARK_APP_ID'], 'app_secret': os.environ['LARK_APP_SECRET']}).encode(),
    headers={'Content-Type': 'application/json'}, method='POST')
try:
    data = json.loads(urllib.request.urlopen(req, timeout=10).read())
    if data.get('code') == 0: print(data['tenant_access_token'])
    else: print('FAIL', file=sys.stderr); sys.exit(1)
except Exception as e: print('FAIL', file=sys.stderr); sys.exit(1)
" 2>&1) || error "API 连接失败"
ok "API 连接成功"

# ── Collect team members ─────────────────────────────────────────────
echo ""
info "输入团队成员手机号（每行一个，空行结束）:"
info "Enter phone numbers (one per line, empty line to finish):"
echo ""

PHONES=()
while true; do
    read -rp "  手机号: " phone
    [[ -z "$phone" ]] && break
    PHONES+=("$phone")
done

if [[ ${#PHONES[@]} -eq 0 ]]; then
    error "至少需要一个手机号"
fi

echo ""
info "查询 ${#PHONES[@]} 个成员的 Open ID..."

# ── Lookup and generate configs ──────────────────────────────────────
mkdir -p "$OUTPUT_DIR"

SUCCESS=0
FAIL=0

for phone in "${PHONES[@]}"; do
    OPEN_ID=$(LARK_TOKEN="$TOKEN" LARK_PHONE="$phone" python3 -c "
import json, urllib.request, sys, os
token = os.environ['LARK_TOKEN']
phone = os.environ['LARK_PHONE']
req = urllib.request.Request(
    'https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id',
    data=json.dumps({'mobiles': [phone]}).encode(),
    headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {token}'},
    method='POST')
try:
    data = json.loads(urllib.request.urlopen(req, timeout=10).read())
    users = data.get('data',{}).get('user_list',[])
    if users and users[0].get('user_id'):
        print(users[0]['user_id'])
    else:
        sys.exit(1)
except: sys.exit(1)
" 2>/dev/null) || true

    if [[ -n "$OPEN_ID" ]]; then
        # Generate config file
        config_file="$OUTPUT_DIR/config-${phone}.json"
        LARK_APP_ID="$APP_ID" LARK_APP_SECRET="$APP_SECRET" LARK_OPEN_ID="$OPEN_ID" \
        LARK_CONFIG_FILE="$config_file" python3 -c "
import json, os
cfg = {'app_id': os.environ['LARK_APP_ID'], 'app_secret': os.environ['LARK_APP_SECRET'],
       'open_id': os.environ['LARK_OPEN_ID'], 'events': ['Stop', 'Notification']}
with open(os.environ['LARK_CONFIG_FILE'], 'w') as f: json.dump(cfg, f, indent=4)
"
        ok "$phone → $OPEN_ID → $config_file"
        ((SUCCESS++))
    else
        echo -e "  ${RED}✗${NC}   $phone → 未找到 / not found"
        ((FAIL++))
    fi
done

# ── Summary ──────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}完成 / Done${NC}"
echo "  成功 / Success: $SUCCESS"
[[ $FAIL -gt 0 ]] && echo "  失败 / Failed:  $FAIL"
echo ""
echo "  配置文件在 / Config files at: $OUTPUT_DIR/"
echo ""
echo "  分发给成员 / Distribute to members:"
echo "    1. 发送对应的 config-手机号.json 给每个人"
echo "       Send each person their config-phone.json"
echo ""
echo "    2. 成员执行 / Members run:"
echo "       mkdir -p ~/.config/claude-lark"
echo "       cp config-xxx.json ~/.config/claude-lark/config.json"
echo "       chmod 600 ~/.config/claude-lark/config.json"
echo ""
echo "    3. 安装 hook / Install hook:"
echo "       ./scripts/install.sh    (会跳过凭证步骤 / skips credential prompts)"
echo ""

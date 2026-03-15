#!/usr/bin/env python3
"""Non-interactive config setup for claude-lark.

Usage:
    python3 setup.py --app-id cli_xxx --app-secret xxx --phone 138xxx
    python3 setup.py --app-id cli_xxx --app-secret xxx --email foo@bar.com
    python3 setup.py --app-id cli_xxx --app-secret xxx --open-id ou_xxx
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "claude-lark"
CONFIG_PATH = CONFIG_DIR / "config.json"
TOKEN_URL = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/"
LOOKUP_URL = "https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id"


def _api_post(url: str, data: dict, headers: dict | None = None) -> dict:
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(
        url, data=json.dumps(data).encode(),
        headers=h, method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def main() -> int:
    parser = argparse.ArgumentParser(description="claude-lark config setup")
    parser.add_argument("--app-id", required=True, help="Lark Bot App ID")
    parser.add_argument("--app-secret", required=True, help="Lark Bot App Secret")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--phone", help="Feishu phone number")
    group.add_argument("--email", help="Feishu email")
    group.add_argument("--open-id", help="Direct Open ID")
    parser.add_argument("--events", default="Stop,Notification", help="Comma-separated events")
    args = parser.parse_args()

    # 1. Get token
    try:
        token_resp = _api_post(TOKEN_URL, {
            "app_id": args.app_id, "app_secret": args.app_secret,
        })
        if token_resp.get("code") != 0:
            print(f"ERROR: API auth failed: {token_resp.get('msg', 'unknown')}", file=sys.stderr)
            return 1
        token = token_resp["tenant_access_token"]
        print(f"OK: API connection verified")
    except Exception as e:
        print(f"ERROR: Cannot connect to Lark API: {e}", file=sys.stderr)
        return 1

    # 2. Resolve open_id
    open_id = args.open_id
    if not open_id:
        try:
            payload = {}
            if args.phone:
                payload["mobiles"] = [args.phone]
            elif args.email:
                payload["emails"] = [args.email]

            lookup = _api_post(LOOKUP_URL, payload, {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            })
            if lookup.get("code") != 0:
                print(f"ERROR: Lookup failed: {lookup.get('msg', '')}", file=sys.stderr)
                return 1
            users = lookup.get("data", {}).get("user_list", [])
            if not users or not users[0].get("user_id"):
                identifier = args.phone or args.email
                print(f"ERROR: User not found: {identifier}", file=sys.stderr)
                return 1
            open_id = users[0]["user_id"]
            print(f"OK: Open ID resolved: {open_id}")
        except Exception as e:
            print(f"ERROR: Lookup failed: {e}", file=sys.stderr)
            return 1

    # 3. Write config
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    cfg = {
        "app_id": args.app_id,
        "app_secret": args.app_secret,
        "open_id": open_id,
        "events": [e.strip() for e in args.events.split(",")],
    }
    with open(CONFIG_PATH, "w") as f:
        json.dump(cfg, f, indent=4)

    # Set file permissions (Unix only)
    try:
        CONFIG_PATH.chmod(0o600)
    except (OSError, AttributeError):
        pass

    print(f"OK: Config saved to {CONFIG_PATH}")

    # 4. Send test notification
    try:
        card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "✅ claude-lark 配置成功"},
                "template": "green",
            },
            "elements": [
                {"tag": "markdown", "content": "你已成功配置 claude-lark 通知！\n\n从现在起，Claude Code 完成任务时你都会收到飞书通知。"},
            ],
        }
        msg_resp = _api_post(
            f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
            {"receive_id": open_id, "msg_type": "interactive",
             "content": json.dumps(card, ensure_ascii=False)},
            {"Content-Type": "application/json; charset=utf-8",
             "Authorization": f"Bearer {token}"},
        )
        if msg_resp.get("code") == 0:
            print("OK: Test notification sent")
        else:
            print(f"WARN: Test notification failed: {msg_resp.get('msg', '')}")
    except Exception:
        print("WARN: Test notification failed (non-critical)")

    return 0


if __name__ == "__main__":
    sys.exit(main())

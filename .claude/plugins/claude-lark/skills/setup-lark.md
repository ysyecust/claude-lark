---
name: setup-lark
description: Configure claude-lark notifications. Use when user wants to set up or reconfigure Lark/Feishu notifications for Claude Code.
user-invocable: true
---

# Setup claude-lark Notifications

Help the user configure claude-lark to receive Lark (Feishu) notifications.

## Steps

1. **Ask the user for these three pieces of information** (one message, not one-by-one):
   - Lark Bot **App ID** (format: `cli_xxxx`, from team admin)
   - Lark Bot **App Secret** (from team admin)
   - Their **phone number** or **email** registered in Feishu (for Open ID lookup)

   If the user already has a config file or Open ID, they can provide that directly instead.

2. **Run the setup script** with the provided values:

   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/setup.py \
     --app-id <APP_ID> \
     --app-secret <APP_SECRET> \
     --phone <PHONE>
   ```

   Or with email: `--email <EMAIL>`
   Or with direct Open ID: `--open-id <OPEN_ID>`

3. **Report the result** to the user:
   - If all lines show `OK:` → setup is complete, ask the user to check Feishu for a test notification
   - If any line shows `ERROR:` → explain the error and suggest fixes:
     - "API auth failed" → wrong App ID or App Secret
     - "User not found" → wrong phone/email, or the bot's contact scope doesn't include this user
     - "Lookup failed: contact:user.id:readonly" → bot needs this permission enabled

## Important Notes

- **Never echo the App Secret** back to the user in your response
- The config file is saved at `~/.config/claude-lark/config.json` with permissions 600
- If the user already has hooks configured manually, this setup is still safe — the plugin hooks take priority

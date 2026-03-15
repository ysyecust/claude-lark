# Lark Bot Admin Setup Guide / 飞书机器人管理员配置指南

This guide is for **team admins** who need to create and configure the Lark bot before team members can use claude-lark.

本指南面向**团队管理员**，用于创建和配置飞书机器人。

---

## 1. Create App / 创建应用

1. Go to [Lark Open Platform](https://open.feishu.cn/app) / 打开 [飞书开放平台](https://open.feishu.cn/app)
2. Click **Create Custom App** / 点击 **创建自建应用**
3. Fill in app name (e.g. "Claude Notifier") and description / 填写应用名称和描述

## 2. Enable Bot / 开启机器人能力

1. In the app settings, go to **Add Capabilities** / 进入 **添加应用能力**
2. Enable **Bot** / 开启 **机器人**

## 3. Configure Permissions / 配置权限

Go to **Permission Management** and enable: / 进入 **权限管理**，开通以下权限：

### Required / 必需

| Permission | Identifier | Purpose |
|-----------|------------|---------|
| Send messages as bot | `im:message:send_as_bot` | Send notification cards to users |
| 以应用身份发消息 | `im:message:send_as_bot` | 向用户发送通知卡片 |

### Recommended / 推荐

| Permission | Identifier | Purpose |
|-----------|------------|---------|
| Get user ID by phone/email | `contact:user.id:readonly` | Auto-lookup Open ID during install |
| 通过手机号/邮箱获取用户 ID | `contact:user.id:readonly` | 安装时自动查询用户 Open ID |

## 4. Publish / 发布应用

1. Go to **Version Management** → Create version → Publish / 进入 **版本管理** → 创建版本 → 发布
2. Approve in admin console / 在管理后台审批通过

## 5. Distribute to Team / 分发给团队

Copy the credentials and share with your team: / 复制凭证并发给团队：

```
App ID:     cli_xxxxxxxxxxxxxxxx
App Secret: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

Team members then run: / 团队成员运行：

```bash
# macOS / Linux
./scripts/install.sh

# Windows
.\scripts\install.ps1
```

They'll be prompted to enter the credentials and their phone number.

他们会被提示输入凭证和手机号。

## 6. Verify / 验证

The installer sends a test notification. If the user receives a Lark card, setup is complete.

安装器会发送测试通知。如果用户收到飞书卡片，配置就完成了。

---

## Security Notes / 安全注意

- The App Secret grants message-sending access. Share it only with trusted team members.
- Each user's config file is stored with `chmod 600` (owner-read only) on macOS/Linux.
- The App Secret is stored locally on each user's machine, not transmitted anywhere except to Lark API.

- App Secret 拥有发送消息的权限，只分享给可信的团队成员。
- 配置文件在 macOS/Linux 上权限为 600（仅所有者可读）。
- App Secret 仅存储在用户本地，只传输给飞书 API。

## Troubleshooting / 常见问题

**"Bot ability is not activated" (code 230006)**
→ Enable Bot capability in app settings / 在应用设置中开启机器人能力

**"open_id cross app" (code 99992361)**
→ The Open ID was obtained from a different app. Each app has its own Open IDs. Re-run the installer with phone number lookup.
→ Open ID 来自其他应用。每个应用有独立的 Open ID。重新运行安装器用手机号查询。

**"Access denied... contact:user.id:readonly" (code 99991672)**
→ Enable the `contact:user.id:readonly` permission and re-publish the app.
→ 开通 `contact:user.id:readonly` 权限并重新发布应用。

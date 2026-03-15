#Requires -Version 5.1
<#
.SYNOPSIS
    claude-lark installer for Windows
.DESCRIPTION
    Configures Claude Code hooks to send Lark (Feishu) notifications.
    Supports non-interactive mode when config already exists.
.PARAMETER AppId
    Lark Bot App ID
.PARAMETER AppSecret
    Lark Bot App Secret
.PARAMETER Phone
    Feishu phone number for Open ID lookup
.PARAMETER Email
    Feishu email for Open ID lookup
.PARAMETER OpenId
    Direct Open ID (skip lookup)
.EXAMPLE
    .\install.ps1
    .\install.ps1 -Phone 138xxxx
    .\install.ps1 -OpenId ou_xxx
#>
param(
    [string]$AppId,
    [string]$AppSecret,
    [string]$Phone,
    [string]$Email,
    [string]$OpenId
)

$ErrorActionPreference = "Stop"

# ── Paths ────────────────────────────────────────────────────────────
$ConfigDir = Join-Path $HOME ".config" "claude-lark"
$ConfigFile = Join-Path $ConfigDir "config.json"
$SettingsFile = Join-Path $HOME ".claude" "settings.json"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$ProjectDir = Split-Path -Parent $ScriptDir
$NotifyScript = Join-Path $ProjectDir "claude_lark_notify.py"

# ── Helpers ──────────────────────────────────────────────────────────
function Write-Info  { Write-Host "  [info]  $args" -ForegroundColor Cyan }
function Write-Ok    { Write-Host "    ✓     $args" -ForegroundColor Green }
function Write-Warn  { Write-Host "    ⚠     $args" -ForegroundColor Yellow }
function Write-Err   { Write-Host "    ✗     $args" -ForegroundColor Red; exit 1 }
function Write-Step  { Write-Host "`n  $args" -ForegroundColor White -NoNewline; Write-Host "" }

function Get-ConfigValue([string]$Key) {
    if (Test-Path $ConfigFile) {
        try {
            $cfg = Get-Content $ConfigFile -Raw | ConvertFrom-Json
            return $cfg.$Key
        } catch { return "" }
    }
    return ""
}

# ── Banner ───────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  claude-lark v1.0" -ForegroundColor White
Write-Host "  Claude Code → Lark Notifications"
Write-Host "  ─────────────────────────────────"
Write-Host ""

# ── Check Python ─────────────────────────────────────────────────────
# Detect the actual working Python 3 command.
# On Windows, "python3" is often a Microsoft Store stub (exit code 49),
# so we test each candidate and use the first one that actually works.
$PythonCmd = $null
foreach ($candidate in @("python3", "python")) {
    try {
        $pyOut = & $candidate --version 2>&1
        if ($LASTEXITCODE -eq 0 -and "$pyOut" -match "Python 3") {
            $PythonCmd = $candidate
            Write-Ok "$candidate $pyOut"
            break
        }
    } catch { }
}
if (-not $PythonCmd) { Write-Err "未找到 Python 3.8+，请先安装 Python" }

if (-not (Test-Path $NotifyScript)) {
    Write-Err "未找到 claude_lark_notify.py: $NotifyScript"
}

# ── Check for existing complete config (non-interactive mode) ────────
$HasCompleteConfig = $false
if (Test-Path $ConfigFile) {
    $existingAppId = Get-ConfigValue "app_id"
    $existingAppSecret = Get-ConfigValue "app_secret"
    $existingOpenId = Get-ConfigValue "open_id"
    if ($existingAppId -and $existingAppSecret -and $existingOpenId) {
        $HasCompleteConfig = $true
    }
}

# If config is complete AND no credentials were passed as arguments,
# skip Steps 1-3 and go straight to hook installation.
$SkipCredentials = $HasCompleteConfig -and (-not $AppId) -and (-not $AppSecret) -and `
                   (-not $Phone) -and (-not $Email) -and (-not $OpenId)

if ($SkipCredentials) {
    Write-Info "检测到完整配置文件，跳过凭证设置"
    $AppId = $existingAppId
    $AppSecret = $existingAppSecret
    $OpenId = $existingOpenId

    # Quick API verification
    Write-Step "Step 1/2  验证 API 连接"
    $tokenBody = @{ app_id = $AppId; app_secret = $AppSecret } | ConvertTo-Json
    try {
        $tokenResp = Invoke-RestMethod -Uri "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/" `
            -Method Post -ContentType "application/json" -Body $tokenBody
        if ($tokenResp.code -ne 0) { Write-Err "API 连接失败: $($tokenResp.msg)" }
        Write-Ok "飞书 API 连接成功"
    } catch {
        Write-Err "API 连接失败，请检查配置文件中的 App ID 和 App Secret"
    }

    Write-Step "Step 2/2  安装 hooks"
} else {
    # ══════════════════════════════════════════════════════════════════
    #  Step 1: Bot Credentials
    # ══════════════════════════════════════════════════════════════════
    Write-Step "Step 1/4  飞书机器人凭证"

    if (-not $AppId) {
        $existing = Get-ConfigValue "app_id"
        if ($existing) {
            $input = Read-Host "  App ID [$existing]"
            $AppId = if ($input) { $input } else { $existing }
        } else {
            $AppId = Read-Host "  App ID"
        }
    }
    if (-not $AppId) { Write-Err "App ID 不能为空" }

    if (-not $AppSecret) {
        $existing = Get-ConfigValue "app_secret"
        if ($existing) {
            $secureInput = Read-Host "  App Secret [已保存，回车跳过]" -AsSecureString
            $plainInput = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
                [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureInput))
            $AppSecret = if ($plainInput) { $plainInput } else { $existing }
        } else {
            $secureInput = Read-Host "  App Secret" -AsSecureString
            $AppSecret = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
                [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureInput))
        }
    }
    if (-not $AppSecret) { Write-Err "App Secret 不能为空" }

    # ══════════════════════════════════════════════════════════════════
    #  Step 2: Verify API
    # ══════════════════════════════════════════════════════════════════
    Write-Step "Step 2/4  验证 API 连接"

    $tokenBody = @{ app_id = $AppId; app_secret = $AppSecret } | ConvertTo-Json
    try {
        $tokenResp = Invoke-RestMethod -Uri "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal/" `
            -Method Post -ContentType "application/json" -Body $tokenBody
        if ($tokenResp.code -ne 0) { Write-Err "API 连接失败: $($tokenResp.msg)" }
        $Token = $tokenResp.tenant_access_token
        Write-Ok "飞书 API 连接成功"
    } catch {
        Write-Err "API 连接失败，请检查 App ID 和 App Secret"
    }

    # ══════════════════════════════════════════════════════════════════
    #  Step 3: Get Open ID
    # ══════════════════════════════════════════════════════════════════
    Write-Step "Step 3/4  确定你的飞书身份"

    if (-not $OpenId -and -not $Phone -and -not $Email) {
        $existing = Get-ConfigValue "open_id"
        Write-Host ""
        Write-Host "  选择查找方式:" -ForegroundColor DarkGray
        Write-Host "  1) 手机号（推荐）"
        Write-Host "  2) 邮箱"
        Write-Host "  3) 直接输入 Open ID"
        if ($existing) { Write-Host "  4) 使用已保存的 Open ID ($existing)" -ForegroundColor DarkGray }
        Write-Host ""
        $choice = Read-Host "  请选择 [1]"
        if (-not $choice) { $choice = "1" }

        switch ($choice) {
            "1" { $Phone = Read-Host "  飞书手机号" }
            "2" { $Email = Read-Host "  飞书邮箱" }
            "3" { $OpenId = Read-Host "  Open ID" }
            "4" { $OpenId = $existing }
            default { Write-Err "无效选择" }
        }
    }

    # Lookup by phone or email
    if ($Phone -or $Email) {
        Write-Info "查询 Open ID..."
        $lookupBody = @{}
        if ($Phone) { $lookupBody["mobiles"] = @($Phone) }
        if ($Email) { $lookupBody["emails"] = @($Email) }

        try {
            $lookupResp = Invoke-RestMethod `
                -Uri "https://open.feishu.cn/open-apis/contact/v3/users/batch_get_id?user_id_type=open_id" `
                -Method Post -ContentType "application/json" `
                -Headers @{ Authorization = "Bearer $Token" } `
                -Body ($lookupBody | ConvertTo-Json)

            if ($lookupResp.code -ne 0) { Write-Err "查询失败: $($lookupResp.msg)" }
            $users = $lookupResp.data.user_list
            if (-not $users -or -not $users[0].user_id) { Write-Err "未找到用户" }
            $OpenId = $users[0].user_id
            Write-Ok "查询成功: $OpenId"
        } catch {
            Write-Err "查询失败: $_"
        }
    }

    if (-not $OpenId) { Write-Err "Open ID 不能为空" }

    Write-Step "Step 4/4  安装"

    # Write config
    New-Item -ItemType Directory -Path $ConfigDir -Force | Out-Null
    $config = @{
        app_id     = $AppId
        app_secret = $AppSecret
        open_id    = $OpenId
        events     = @("Stop", "Notification")
    } | ConvertTo-Json -Depth 3
    Set-Content -Path $ConfigFile -Value $config -Encoding UTF8
    Write-Ok "配置已保存  $ConfigFile"
    Write-Warn "Windows 上 config.json 无法通过 chmod 保护，请确保文件不被其他用户读取"
}

# ── Install Claude Code hooks (shared by both paths) ─────────────────
$claudeDir = Join-Path $HOME ".claude"
New-Item -ItemType Directory -Path $claudeDir -Force | Out-Null

# Use the detected Python command (python or python3) in hook command
$hookCmd = "$PythonCmd $($NotifyScript -replace '\\','/')"
$hookEntry = @{
    matcher = ""
    hooks   = @(@{ type = "command"; command = $hookCmd; timeout = 30 })
}

if (Test-Path $SettingsFile) {
    $settings = Get-Content $SettingsFile -Raw | ConvertFrom-Json
    if (-not $settings.hooks) {
        $settings | Add-Member -NotePropertyName "hooks" -NotePropertyValue @{} -Force
    }
} else {
    $settings = @{ hooks = @{} }
}

# Convert to hashtable for easier manipulation, then back to JSON
$settingsJson = $settings | ConvertTo-Json -Depth 10 | ConvertFrom-Json
$raw = Get-Content $SettingsFile -Raw -ErrorAction SilentlyContinue
if (-not $raw) { $raw = "{}" }

# Use Python for safe JSON merge (PowerShell JSON handling is fragile)
$env:SETTINGS_FILE = $SettingsFile
$env:HOOK_CMD = $hookCmd
& $PythonCmd -c @"
import json, os
path = os.environ['SETTINGS_FILE']
hook_cmd = os.environ['HOOK_CMD']
try:
    with open(path, 'r') as f: settings = json.load(f)
except: settings = {}
hooks = settings.setdefault('hooks', {})
entry = {'matcher': '', 'hooks': [{'type': 'command', 'command': hook_cmd, 'timeout': 30}]}
for ev in ('Stop', 'Notification'):
    entries = hooks.setdefault(ev, [])
    already = any('claude_lark_notify' in h.get('command', '') for e in entries for h in e.get('hooks', []))
    if not already: entries.append(entry)
with open(path, 'w') as f: json.dump(settings, f, indent=2, ensure_ascii=False)
"@
Remove-Item Env:\SETTINGS_FILE, Env:\HOOK_CMD -ErrorAction SilentlyContinue
Write-Ok "Claude Code hooks 已配置"

# ── Test notification ─────────────────────────────────────────────────
Write-Host ""
$sendTest = Read-Host "  发送测试通知？[Y/n]"
if (-not $sendTest -or $sendTest -match "^[Yy]") {
    $testPayload = @{
        hook_event_name = "Stop"
        cwd = $ScriptDir
        session_id = "install-test"
        last_assistant_message = "claude-lark 安装成功！你现在可以收到 Claude Code 的飞书通知了。"
    } | ConvertTo-Json -Compress
    $testPayload | & $PythonCmd $NotifyScript
    Write-Ok "测试通知已发送，请查看飞书"
}

# ── Done ──────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "  安装完成 ✓" -ForegroundColor Green
Write-Host ""
Write-Host "  配置   $ConfigFile" -ForegroundColor DarkGray
Write-Host "  脚本   $NotifyScript" -ForegroundColor DarkGray
Write-Host "  卸载   .\uninstall.ps1" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Claude Code 每次完成任务，你都会在飞书收到通知。"
Write-Host ""

#Requires -Version 5.1
<#
.SYNOPSIS
    claude-lark uninstaller for Windows
#>

$ErrorActionPreference = "Stop"

$ConfigDir = Join-Path $HOME ".config" "claude-lark"
$SettingsFile = Join-Path $HOME ".claude" "settings.json"

Write-Host ""
Write-Host "  claude-lark — Uninstaller" -ForegroundColor White
Write-Host "  ────────────────────────────"
Write-Host ""

# Remove hooks from settings.json
if (Test-Path $SettingsFile) {
    Write-Host "  [info]  从 Claude Code settings 中移除 hooks..." -ForegroundColor Cyan

    python3 -c @"
import json, os
path = r'$SettingsFile'
with open(path, 'r') as f: settings = json.load(f)
hooks = settings.get('hooks', {})
modified = False
for ev in ('Stop', 'Notification'):
    entries = hooks.get(ev, [])
    filtered = []
    for entry in entries:
        hl = entry.get('hooks', [])
        cleaned = [h for h in hl if 'claude_lark_notify' not in h.get('command', '')]
        if cleaned:
            entry['hooks'] = cleaned
            filtered.append(entry)
        elif hl != cleaned:
            modified = True
        else:
            filtered.append(entry)
    if len(filtered) != len(entries): modified = True
    hooks[ev] = filtered
    if not hooks[ev]: del hooks[ev]
settings['hooks'] = hooks
with open(path, 'w') as f: json.dump(settings, f, indent=2, ensure_ascii=False)
"@
    Write-Host "    ✓     Claude Code hooks 已移除" -ForegroundColor Green
} else {
    Write-Host "  [info]  未找到 settings.json，跳过" -ForegroundColor Cyan
}

# Remove config
if (Test-Path $ConfigDir) {
    Write-Host ""
    $delete = Read-Host "  是否删除配置文件 ($ConfigDir)？[y/N]"
    if ($delete -match "^[Yy]") {
        Remove-Item -Path $ConfigDir -Recurse -Force
        Write-Host "    ✓     配置目录已删除" -ForegroundColor Green
    } else {
        Write-Host "  [info]  保留配置目录" -ForegroundColor Cyan
    }
}

Write-Host ""
Write-Host "  卸载完成。" -ForegroundColor Green
Write-Host ""

# 安装 multi-model-orchestration 技能到 DSH
# 用法：.\install.ps1
$ErrorActionPreference = "Stop"

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$src  = Join-Path $here "multi-model-orchestration"
$dst  = Join-Path $env:USERPROFILE ".agents\skills\multi-model-orchestration"

if (-not (Test-Path $src)) { throw "找不到源目录：$src" }
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $dst) | Out-Null
if (Test-Path $dst) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $bak = "$dst.backup-$stamp"
    Copy-Item $dst $bak -Recurse -Force
    Write-Host "已备份旧版本 → $bak"
}
Copy-Item $src $dst -Recurse -Force
Write-Host "安装完成：$dst"
Write-Host ""
Write-Host "自检："
python (Join-Path $dst "tools\modelops.py") check

<#
.SYNOPSIS
    Install the hermes-bili-whale adapter into a Hermes Agent installation (Windows).

.DESCRIPTION
    Copies three pieces and tells you what to do next:
      1. plugin/         -> $HermesHome\plugins\bili_whale          (9 tools + panel server)
      2. desktop-plugin/ -> $HermesHome\desktop-plugins\bili-whale  (sidebar row + page)
      3. scripts\        -> $WhaleHome\scripts + $HermesHome\scripts (login / monitor / ollama)

    It does NOT install upstream `tools/` for you unless -CloneUpstream is given,
    because that code belongs to its authors (see NOTICE).

.PARAMETER HermesHome
    Hermes home directory. Default: $env:LOCALAPPDATA\hermes

.PARAMETER WhaleHome
    Where upstream `tools/` lives. Default: $HOME\bili-whale

.PARAMETER CloneUpstream
    git clone the upstream repo and copy its tools/ into $WhaleHome.

.EXAMPLE
    .\install.ps1 -CloneUpstream
#>
[CmdletBinding()]
param(
    [string]$HermesHome = (Join-Path $env:LOCALAPPDATA 'hermes'),
    [string]$WhaleHome  = (Join-Path $HOME 'bili-whale'),
    [switch]$CloneUpstream
)

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
function Step($m) { Write-Host "[*] $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "[+] $m" -ForegroundColor Green }
function Warn($m) { Write-Host "[!] $m" -ForegroundColor Yellow }

Write-Host "hermes-bili-whale installer" -ForegroundColor White
Write-Host "  Hermes home : $HermesHome"
Write-Host "  Whale home  : $WhaleHome"
Write-Host ""

# --- prerequisites -----------------------------------------------------------
Step 'Checking prerequisites'
foreach ($exe in @('node','python','ffmpeg','ffprobe')) {
    $p = Get-Command $exe -ErrorAction SilentlyContinue
    if ($p) { Ok "$exe -> $($p.Source)" } else { Warn "$exe NOT found on PATH" }
}
if (-not (Test-Path $HermesHome)) { throw "Hermes home not found: $HermesHome" }

# --- upstream tools ----------------------------------------------------------
$toolsDir = Join-Path $WhaleHome 'tools'
if (Test-Path (Join-Path $toolsDir 'bili.mjs')) {
    Ok "upstream tools already present: $toolsDir"
} elseif ($CloneUpstream) {
    Step 'Cloning upstream dsh-bili-whale (MIT, by Alterssss)'
    $tmp = Join-Path $env:TEMP ('dsh-bili-whale-' + [guid]::NewGuid().ToString('N').Substring(0,8))
    git clone --depth 1 https://github.com/Alterssss/dsh-bili-whale.git $tmp
    New-Item -ItemType Directory -Force -Path $WhaleHome | Out-Null
    Copy-Item -Recurse -Force (Join-Path $tmp 'tools') $WhaleHome
    Copy-Item -Force (Join-Path $tmp 'lib') $WhaleHome -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force $tmp
    Ok "tools copied to $toolsDir"
} else {
    Warn "upstream tools missing: $toolsDir\tools\bili.mjs"
    Warn "run with -CloneUpstream, or clone https://github.com/Alterssss/dsh-bili-whale yourself"
}

# --- 1) python plugin --------------------------------------------------------
Step 'Installing Python plugin'
$pluginDst = Join-Path $HermesHome 'plugins\bili_whale'
New-Item -ItemType Directory -Force -Path $pluginDst | Out-Null
Copy-Item -Force (Join-Path $here 'plugin\*') $pluginDst
Ok "plugin -> $pluginDst"

# --- 2) desktop runtime plugin ----------------------------------------------
Step 'Installing desktop runtime plugin (sidebar entry)'
$deskDst = Join-Path $HermesHome 'desktop-plugins\bili-whale'
New-Item -ItemType Directory -Force -Path $deskDst | Out-Null
Copy-Item -Force (Join-Path $here 'desktop-plugin\*') $deskDst
Ok "desktop plugin -> $deskDst"

# --- 3) scripts --------------------------------------------------------------
Step 'Installing scripts'
$scriptsDst = Join-Path $WhaleHome 'scripts'
New-Item -ItemType Directory -Force -Path $scriptsDst | Out-Null
Copy-Item -Force (Join-Path $here 'scripts\*') $scriptsDst
Ok "scripts -> $scriptsDst"

$monitorSrc = Join-Path $scriptsDst 'night-watch.sh'
$monitorDst = Join-Path $HermesHome 'scripts'
if (Test-Path $monitorSrc) {
    New-Item -ItemType Directory -Force -Path $monitorDst | Out-Null
    $wrapper = Join-Path $monitorDst 'bili-whale-night.sh'
    "@echo off`nexec bash `"$($monitorSrc -replace '\\','/')`"" | Out-Null
    # bash wrapper (cron monitor only accepts a filename in $HermesHome\scripts)
    "#!/usr/bin/env bash`nexec bash `"$($monitorSrc -replace '\\','/')`"" |
        Set-Content -Path $wrapper -Encoding utf8
    Ok "cron monitor wrapper -> $wrapper"
}

# --- next steps --------------------------------------------------------------
Write-Host ""
Write-Host "Done. Next steps:" -ForegroundColor White
Write-Host "  1) enable the plugin :  hermes plugins enable bili_whale"
Write-Host "  2) restart Hermes    :  tools + sidebar row load on next boot"
Write-Host "  3) log in a THROWAWAY bilibili account:"
Write-Host "       node `"$scriptsDst\login.mjs`" --qr     # scan the PNG it writes"
Write-Host "       node `"$scriptsDst\login.mjs`" --poll"
Write-Host "  4) optional cron (zero-token idle): schedule=every 10m, monitor=bili-whale-night.sh"
Write-Host "     prompt template: docs\cron-prompt.md"
Write-Host ""
Write-Host "Panel: http://127.0.0.1:8791/  (starts with Hermes)" -ForegroundColor DarkGray

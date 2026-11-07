$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location (Join-Path $projectRoot 'frontend')
if (-not (Test-Path -LiteralPath 'node_modules\vite\bin\vite.js')) { throw 'Install frontend dependencies first. See README.md.' }
& node node_modules/vite/bin/vite.js --host 127.0.0.1

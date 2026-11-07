$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create .venv and install backend/requirements.txt first. See README.md.' }
Set-Location (Join-Path $projectRoot 'backend')
& $pythonPath -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $pythonPath -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log

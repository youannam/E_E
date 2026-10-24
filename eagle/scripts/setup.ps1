# Non-destructive one-time setup for Windows. Run from the project root.
$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
$PythonCommand = (Get-Command python -ErrorAction SilentlyContinue).Source
$PythonLauncher = (Get-Command py -ErrorAction SilentlyContinue).Source
if (-not $PythonCommand -and -not $PythonLauncher) { throw 'Install Python 3.11+ and enable Add to PATH.' }
if (-not (Test-Path '.venv\Scripts\python.exe')) { if ($PythonCommand) { & $PythonCommand -m venv .venv } else { & $PythonLauncher -3.11 -m venv .venv } }
& '.venv\Scripts\python.exe' -m pip install --upgrade pip
& '.venv\Scripts\python.exe' -m pip install -r requirements.txt
if (-not (Test-Path '.env')) { & '.venv\Scripts\python.exe' scripts\create_env.py }
if (-not (Test-Path 'eagle_eye.db')) {
  if (-not (Test-Path 'ai\models\active_model.json')) { & '.venv\Scripts\python.exe' -m ai.train }
  $envText = Get-Content '.env' -Raw
  $envText = [regex]::Replace($envText, '(?m)^DEMO_ADMIN_PASSWORD=.*$', 'DEMO_ADMIN_PASSWORD=EagleAdmin@2026!')
  $envText = [regex]::Replace($envText, '(?m)^DEMO_ANALYST_PASSWORD=.*$', 'DEMO_ANALYST_PASSWORD=EagleAnalyst@2026!')
  Set-Content -Path '.env' -Value $envText -NoNewline
  & '.venv\Scripts\python.exe' -m backend.cli init-db
  & '.venv\Scripts\python.exe' -m backend.cli seed-demo --days 14
}
Write-Host 'Setup complete. Use RUN_WEB.bat or RUN_MOBILE.bat.' -ForegroundColor Green

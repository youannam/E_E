# Validate the virtual environment without importing application packages or
# treating Python's stderr as a terminating PowerShell error.
param([string]$Requirements = "requirements.txt")
$ErrorActionPreference = 'Stop'
$VenvPython = Join-Path (Get-Location) '.venv\Scripts\python.exe'
if (-not (Test-Path $VenvPython)) {
  $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
  $PythonLauncher = Get-Command py -ErrorAction SilentlyContinue
  if (-not $PythonCommand -and -not $PythonLauncher) { throw 'Python 3.11+ is required. Install Python and enable Add to PATH.' }
  Write-Host 'Creating Python environment (first run only)...' -ForegroundColor Cyan
  if ($PythonCommand) { & $PythonCommand.Source -m venv .venv 2>&1 | ForEach-Object { Write-Host $_ } }
  else { & $PythonLauncher.Source -3.11 -m venv .venv 2>&1 | ForEach-Object { Write-Host $_ } }
  if ($LASTEXITCODE -ne 0) { throw 'Could not create Python virtual environment.' }
}
if (-not (Test-Path $VenvPython)) { throw 'The virtual environment was not created. Check your Python installation.' }

# pip check is quick and offline. Check for required module names without importing
# them, so missing packages trigger installation instead of a Python traceback.
$NeedsInstall = $false
$oldErrorActionPreference = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
& $VenvPython -m pip check *> $null
if ($LASTEXITCODE -ne 0) { $NeedsInstall = $true }
if (-not $NeedsInstall) {
  & $VenvPython -c "import importlib.util,sys; mods=['fastapi','starlette','uvicorn','pydantic','sqlalchemy','alembic','jwt','dotenv','numpy','pandas','sklearn','joblib']; missing=[m for m in mods if importlib.util.find_spec(m) is None]; print('Missing Python modules: '+', '.join(missing) if missing else 'Python modules are present'); sys.exit(bool(missing))" 2>&1 | ForEach-Object { Write-Host $_ }
  if ($LASTEXITCODE -ne 0) { $NeedsInstall = $true }
}
$ErrorActionPreference = $oldErrorActionPreference
if ($NeedsInstall) {
  Write-Host 'Installing or repairing Python dependencies...' -ForegroundColor Cyan
  & $VenvPython -m pip install -r $Requirements
  if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed. Check the pip error above and your internet connection.' }
} else {
  Write-Host 'Python dependencies already installed; skipping download.' -ForegroundColor Green
}

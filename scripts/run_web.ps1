$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root

& (Join-Path $PSScriptRoot 'ensure_python_deps.ps1') -Requirements 'requirements.txt'
if (-not (Test-Path '.env')) { & '.venv\Scripts\python.exe' scripts\create_env.py }
if (-not (Test-Path 'eagle_eye.db')) {
  Write-Host 'Preparing the database, AI model, and demo accounts...' -ForegroundColor Cyan
  if (-not (Test-Path 'ai\models\active_model.json')) { & '.venv\Scripts\python.exe' -m ai.train }
  # Development-only demo accounts, kept predictable for the local graduation demo.
  $envText = Get-Content '.env' -Raw
  $envText = [regex]::Replace($envText, '(?m)^DEMO_ADMIN_PASSWORD=.*$', 'DEMO_ADMIN_PASSWORD=EagleAdmin@2026!')
  $envText = [regex]::Replace($envText, '(?m)^DEMO_ANALYST_PASSWORD=.*$', 'DEMO_ANALYST_PASSWORD=EagleAnalyst@2026!')
  Set-Content -Path '.env' -Value $envText -NoNewline
  & '.venv\Scripts\python.exe' -m backend.cli init-db
  if ($LASTEXITCODE -ne 0) { throw 'Database initialization failed.' }
  & '.venv\Scripts\python.exe' -m backend.cli seed-demo --days 14
  if ($LASTEXITCODE -ne 0) { throw 'Demo data initialization failed.' }
}

# Prefer the full React/TypeScript SOC console when Node.js is installed. The legacy
# dashboard remains available as an offline fallback, and is served by the same API.
$NpmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $NpmCommand) { $NpmCommand = Get-Command npm -ErrorAction SilentlyContinue }
$UseReact = $false
if ($NpmCommand) {
  Push-Location frontend
  try {
    if ((-not (Test-Path 'node_modules\.bin\vite.cmd') -and -not (Test-Path 'node_modules\.bin\vite')) -or -not (Test-Path 'node_modules\react\package.json')) {
      Write-Host 'Preparing the React web console dependencies (first launch only)...' -ForegroundColor Cyan
      & $NpmCommand.Source install --no-audit --no-fund
    }
    if (((Test-Path 'node_modules\.bin\vite.cmd') -or (Test-Path 'node_modules\.bin\vite')) -and (Test-Path 'node_modules\react\package.json')) { $UseReact = $true }
  } finally { Pop-Location }
}

# Start the backend in its own window so the launcher can open the browser only after
# the health endpoint responds. If it is already running, reuse it.
$BackendRunning = $false
try { $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 2; $BackendRunning = $true } catch {}
if (-not $BackendRunning) {
  $quotedRoot = $Root.Replace("'", "''")
  $backendCommand = "Set-Location '$quotedRoot'; & '.venv\Scripts\python.exe' -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 *> backend-startup.log"
  Start-Process powershell.exe -ArgumentList @('-NoExit','-ExecutionPolicy','Bypass','-Command',$backendCommand) | Out-Null
  $ready = $false
  for ($i=0; $i -lt 40; $i++) {
    Start-Sleep -Milliseconds 750
    try { $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 2; $ready = $true; break } catch {}
  }
  if (-not $ready) { throw 'The backend did not become ready. Check the separate API PowerShell window for errors.' }
}

if ($UseReact) {
  $FrontendRoot = (Resolve-Path 'frontend').Path.Replace("'", "''")
  $frontendCommand = "Set-Location '$FrontendRoot'; `$env:VITE_API_BASE_URL='http://127.0.0.1:8000'; npm run dev -- --host 127.0.0.1 --port 5173 *> ..\frontend-startup.log"
  Start-Process powershell.exe -ArgumentList @('-NoExit','-ExecutionPolicy','Bypass','-Command',$frontendCommand) | Out-Null
  Start-Sleep -Seconds 4
  Write-Host ''
  Write-Host 'Eagle Eye SOC console is ready.' -ForegroundColor Green
  Write-Host 'Opening the console in a clean app window (no address bar).' -ForegroundColor Cyan
  Write-Host 'Demo Admin:  admin / EagleAdmin@2026!'
  Write-Host 'Demo Analyst: analyst / EagleAnalyst@2026!'
  Write-Host 'Keep the API and React windows open while using the project.' -ForegroundColor Yellow
  $WebUrl = 'http://127.0.0.1:5173/'
} else {
  Write-Host ''
  Write-Host 'Node.js/npm was not found or the React dependencies could not be installed.' -ForegroundColor Yellow
  Write-Host 'Opening the built-in dashboard in a clean app window (no address bar).' -ForegroundColor Cyan
  Write-Host 'Install Node.js to use the full React SOC console with Accounts and Detection Rules.' -ForegroundColor Yellow
  Write-Host 'Demo Admin:  admin / EagleAdmin@2026!'
  Write-Host 'Demo Analyst: analyst / EagleAnalyst@2026!'
  $WebUrl = 'http://127.0.0.1:8000/dashboard/'
}

# App mode removes the normal address/omnibox from the visible window. It hides the URL
# for presentation, but it is not a security boundary: a local user can still inspect processes/network settings.
$EdgePaths = @(
  (Join-Path $env:ProgramFiles 'Microsoft\Edge\Application\msedge.exe'),
  (Join-Path ${env:ProgramFiles(x86)} 'Microsoft\Edge\Application\msedge.exe'),
  (Join-Path $env:LOCALAPPDATA 'Microsoft\Edge\Application\msedge.exe')
) | Where-Object { $_ -and (Test-Path $_) }
$ChromePaths = @(
  (Join-Path $env:ProgramFiles 'Google\Chrome\Application\chrome.exe'),
  (Join-Path ${env:ProgramFiles(x86)} 'Google\Chrome\Application\chrome.exe'),
  (Join-Path $env:LOCALAPPDATA 'Google\Chrome\Application\chrome.exe')
) | Where-Object { $_ -and (Test-Path $_) }
$BrowserPath = $EdgePaths | Select-Object -First 1
if (-not $BrowserPath) { $BrowserPath = $ChromePaths | Select-Object -First 1 }
if ($BrowserPath) {
  Start-Process -FilePath $BrowserPath -ArgumentList @("--app=$WebUrl", '--no-first-run') | Out-Null
} else {
  Write-Host 'Edge/Chrome app mode is unavailable; opening the default browser.' -ForegroundColor Yellow
  Start-Process $WebUrl
}
Write-Host 'The API may listen on the local network so the Flutter phone app can connect. Use trusted Wi-Fi only.' -ForegroundColor Yellow
Write-Host 'Address-bar hiding and copy deterrents reduce casual sharing only; they cannot block screenshots, DevTools, or OS-level inspection.' -ForegroundColor Yellow
Write-Host 'Close the API PowerShell window and the React window when you finish.'

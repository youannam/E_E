$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root

& (Join-Path $PSScriptRoot 'ensure_python_deps.ps1') -Requirements 'requirements.txt'
if (-not (Test-Path '.env')) { & '.venv\Scripts\python.exe' scripts\create_env.py }
if (-not (Test-Path 'eagle_eye.db')) {
  Write-Host 'Preparing the database, AI model, and demo accounts...' -ForegroundColor Cyan
  if (-not (Test-Path 'ai\models\active_model.json')) { & '.venv\Scripts\python.exe' -m ai.train }
  # These are local DEVELOPMENT demo credentials only; .env is git-ignored.
  $envText = Get-Content '.env' -Raw
  $envText = [regex]::Replace($envText, '(?m)^DEMO_ADMIN_PASSWORD=.*$', 'DEMO_ADMIN_PASSWORD=EagleAdmin@2026!')
  $envText = [regex]::Replace($envText, '(?m)^DEMO_ANALYST_PASSWORD=.*$', 'DEMO_ANALYST_PASSWORD=EagleAnalyst@2026!')
  Set-Content -Path '.env' -Value $envText -NoNewline
  & '.venv\Scripts\python.exe' -m backend.cli init-db
  & '.venv\Scripts\python.exe' -m backend.cli seed-demo --days 14
}

$Flutter = (Get-Command flutter -ErrorAction SilentlyContinue).Source
if (-not $Flutter) {
  $Candidate = Join-Path $env:USERPROFILE 'Downloads\flutter_windows_3.47.6-stable\flutter\bin\flutter.bat'
  if (Test-Path $Candidate) { $Flutter = $Candidate }
}
if (-not $Flutter) { throw 'Flutter was not found. Add Flutter\bin to PATH, then reopen the terminal.' }

Write-Host ''
Write-Host 'Choose where to run Eagle Eye Mobile:' -ForegroundColor Cyan
Write-Host '  1. Android Emulator'
Write-Host '  2. Windows Desktop'
Write-Host '  3. Physical Android phone (USB cable - recommended)'
Write-Host '  4. Physical Android phone (same Wi-Fi as this PC)'
$Choice = Read-Host 'Enter 1, 2, 3, or 4'
$HostAddress = '127.0.0.1'
$ApiBase = 'http://10.0.2.2:8000'
$BackendHost = '127.0.0.1'
if ($Choice -eq '2') { $ApiBase = 'http://127.0.0.1:8000' }
elseif ($Choice -eq '4') {
  $ip = Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -match '^192\.168\.|^10\.|^172\.(1[6-9]|2[0-9]|3[01])\.' -and $_.InterfaceAlias -notmatch 'Loopback|vEthernet|WSL' } | Select-Object -First 1 -ExpandProperty IPAddress
  if (-not $ip) { throw 'Could not detect your Wi-Fi/LAN IP. Connect the PC and phone to the same Wi-Fi.' }
  $ApiBase = "http://${ip}:8000"
  $BackendHost = '0.0.0.0'
} elseif ($Choice -eq '3') {
  # ADB reverse lets the phone reach the API through USB even when the API is bound to localhost.
  $ApiBase = 'http://127.0.0.1:8000'
  $Adb = (Get-Command adb -ErrorAction SilentlyContinue).Source
  if (-not $Adb) {
    $Sdk = if ($env:ANDROID_SDK_ROOT) { $env:ANDROID_SDK_ROOT } elseif ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { Join-Path $env:LOCALAPPDATA 'Android\Sdk' }
    $CandidateAdb = Join-Path $Sdk 'platform-tools\adb.exe'
    if (Test-Path $CandidateAdb) { $Adb = $CandidateAdb }
  }
  if (-not $Adb) { throw 'ADB was not found. Install Android SDK Platform-Tools in Android Studio, enable USB debugging, and reconnect the phone.' }
  & $Adb start-server | Out-Null
  & $Adb reverse tcp:8000 tcp:8000
  if ($LASTEXITCODE -ne 0) { throw 'USB reverse failed. Unlock the phone and accept the USB debugging prompt, then try again.' }
} elseif ($Choice -ne '1') { throw 'Invalid choice.' }

$health = $false
try { $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 2; $health = $true } catch {}
if (-not $health) {
  Write-Host 'Starting the API in a separate PowerShell window...' -ForegroundColor Cyan
  $quotedRoot = $Root.Replace("'", "''")
  $quotedHost = $BackendHost
  $cmd = "Set-Location '$quotedRoot'; & '.venv\Scripts\python.exe' -m uvicorn backend.main:app --host $quotedHost --port 8000"
  Start-Process powershell.exe -ArgumentList @('-NoExit','-ExecutionPolicy','Bypass','-Command',$cmd) | Out-Null
  $ready = $false
  for ($i=0; $i -lt 40; $i++) { Start-Sleep -Milliseconds 750; try { $null = Invoke-RestMethod -Uri 'http://127.0.0.1:8000/api/v1/health' -TimeoutSec 2; $ready = $true; break } catch {} }
  if (-not $ready) { throw 'Backend did not start. Check the separate PowerShell window for an error.' }
}

Push-Location mobile
try {
  if (-not (Test-Path 'android\app\build.gradle.kts') -or -not (Test-Path 'windows\runner\CMakeLists.txt')) {
    Write-Host 'Generating missing Flutter platform folders (Android + Windows)...' -ForegroundColor Cyan
    & $Flutter create --platforms=android,windows --project-name eagle_eye_mobile .
    if ($LASTEXITCODE -ne 0) { throw 'Could not generate Flutter platform folders.' }
  }
  # This local development app uses an HTTP API; allow cleartext traffic in Android debug builds.
  $Manifest = 'android\app\src\main\AndroidManifest.xml'
  if (Test-Path $Manifest) {
    $ManifestText = Get-Content $Manifest -Raw
    if ($ManifestText -notmatch 'usesCleartextTraffic') {
      $ManifestText = $ManifestText -replace '<application\b', '<application android:usesCleartextTraffic="true"'
      Set-Content -Path $Manifest -Value $ManifestText -NoNewline -Encoding UTF8
    }
  }
  # Reuse the existing Flutter package cache; resolve dependencies only on first run
  # or when the lockfile/package config is missing.
  if (-not (Test-Path '.dart_tool\package_config.json') -or -not (Test-Path 'pubspec.lock')) {
    Write-Host 'Resolving Flutter packages (first run or dependency changes)...' -ForegroundColor Cyan
    & $Flutter pub get
    if ($LASTEXITCODE -ne 0) { throw 'flutter pub get failed.' }
  } else {
    Write-Host 'Flutter packages already resolved; skipping pub get.' -ForegroundColor Green
  }
  $deviceId = $null
  if ($Choice -eq '2') {
    $deviceId = 'windows'
  } else {
    $deviceJson = & $Flutter devices --machine
    if ($LASTEXITCODE -ne 0) { throw 'Could not list Flutter devices. Check Android Studio/SDK setup.' }
    $devices = $deviceJson | ConvertFrom-Json
    if ($Choice -eq '1') {
      $target = $devices | Where-Object { $_.targetPlatform -like 'android-*' -and $_.emulator -eq $true } | Select-Object -First 1
      if (-not $target) { throw 'No Android emulator found. Open Android Studio > Device Manager, create/start an emulator, then run RUN_MOBILE.bat again.' }
    } else {
      $target = $devices | Where-Object { $_.targetPlatform -like 'android-*' -and $_.emulator -ne $true } | Select-Object -First 1
      if (-not $target) { throw 'No physical Android phone found. Enable Developer options > USB debugging, reconnect the phone, accept the trust prompt, and check that it appears in flutter devices.' }
    }
    $deviceId = $target.id
  }
  Write-Host "Launching mobile app on device '$deviceId' with API: $ApiBase" -ForegroundColor Green
  & $Flutter run -d $deviceId "--dart-define=API_BASE=$ApiBase"
} finally { Pop-Location }

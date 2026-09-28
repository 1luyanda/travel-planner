# Start Team 4 Travel Planner (backend + frontend)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path .env)) {
  Copy-Item .env.example .env
  $py = $null
  foreach ($c in @("python3.13.exe", "py -3.13", "py -3", "python")) {
    try {
      if ($c -like "py *") {
        $parts = $c.Split(" ")
        & $parts[0] $parts[1] -c "pass" 2>$null
        if ($LASTEXITCODE -eq 0) { $py = $c; break }
      } else {
        & $c -c "pass" 2>$null
        if ($LASTEXITCODE -eq 0) { $py = $c; break }
      }
    } catch {}
  }
  if (-not $py) { throw "Python not found. Install Python 3.13 or ensure it is on PATH." }

  function Invoke-Py([string]$code) {
    if ($py -like "py *") {
      $parts = $py.Split(" ")
      & $parts[0] $parts[1] -c $code
    } else {
      & $py -c $code
    }
  }

  $apiKey = (Invoke-Py "import secrets; print(secrets.token_urlsafe(32))").Trim()
  $sessionSecret = (Invoke-Py "import secrets; print(secrets.token_urlsafe(32))").Trim()
  $envText = Get-Content .env -Raw
  $envText = $envText -replace "(?m)^API_AUTH_KEY=.*$", "API_AUTH_KEY=$apiKey"
  $envText = $envText -replace "(?m)^AUTH_SESSION_SECRET=.*$", "AUTH_SESSION_SECRET=$sessionSecret"
  Set-Content -Path .env -Value $envText -NoNewline
  Write-Host "Created .env with generated API_AUTH_KEY and AUTH_SESSION_SECRET."
  Write-Host "Fill COSMOS_CONNECTION_STRING and COSMOS_DATABASE in .env for live data."
}

$pythonCmd = $null
foreach ($c in @("python3.13.exe", "py -3.13", "py -3", "python")) {
  try {
    if ($c -like "py *") {
      $parts = $c.Split(" ")
      & $parts[0] $parts[1] -c "pass" 2>$null
      if ($LASTEXITCODE -eq 0) { $pythonCmd = $c; break }
    } else {
      & $c -c "pass" 2>$null
      if ($LASTEXITCODE -eq 0) { $pythonCmd = $c; break }
    }
  } catch {}
}
if (-not $pythonCmd) { throw "Python not found." }

Write-Host "Installing Python dependencies..."
if ($pythonCmd -like "py *") {
  $parts = $pythonCmd.Split(" ")
  & $parts[0] $parts[1] -m pip install -r requirements.txt
} else {
  & $pythonCmd -m pip install -r requirements.txt
}

Write-Host "Starting backend on http://127.0.0.1:8000 ..."
if ($pythonCmd -like "py *") {
  $parts = $pythonCmd.Split(" ")
  Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$PSScriptRoot'; & '$($parts[0])' $($parts[1]) -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000"
  )
} else {
  Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "Set-Location '$PSScriptRoot'; & '$pythonCmd' -m uvicorn backend.main:app --reload --host 127.0.0.1 --port 8000"
  )
}

Write-Host "Installing frontend dependencies..."
Set-Location (Join-Path $PSScriptRoot "frontend")
npm install

Write-Host "Starting frontend (Vite)..."
Start-Process powershell -ArgumentList @(
  "-NoExit", "-Command",
  "Set-Location '$(Join-Path $PSScriptRoot 'frontend')'; npm run dev"
)

Write-Host ""
Write-Host "Backend docs:  http://127.0.0.1:8000/docs"
Write-Host "Frontend UI:   http://localhost:5173"
Write-Host "Health check:  http://127.0.0.1:8000/api/health"

# Quick start for Windows: installs uv (which brings Python) and Bun if missing, installs the backend and
# frontend packages from their lockfiles, then runs both. Ctrl+C stops both.
#   powershell -ExecutionPolicy Bypass -File start.ps1
# PORT (frontend, default 3000) and BACKEND_PORT (default 8000) change the ports.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Windows PowerShell started from PowerShell 7 can inherit 7's module paths and then fails to load its own
# built-in modules (the uv installer stops at Get-ExecutionPolicy). Keep only the paths it can use.
if ($PSVersionTable.PSEdition -eq "Desktop") {
    $env:PSModulePath = ($env:PSModulePath -split ";" | Where-Object { $_ -notmatch "\\PowerShell\\|microsoft\.powershell_" }) -join ";"
}

# native commands do not stop the script on failure by themselves
function Check { if ($LASTEXITCODE) { exit $LASTEXITCODE } }

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "Installing uv..."
    powershell -NoProfile -ExecutionPolicy Bypass -c "irm https://astral.sh/uv/0.13.7/install.ps1 | iex"; Check
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
}
if (-not (Get-Command bun -ErrorAction SilentlyContinue)) {
    Write-Host "Installing Bun..."
    powershell -NoProfile -ExecutionPolicy Bypass -c "& ([scriptblock]::Create((irm https://bun.sh/install.ps1))) -Version 1.4.4"; Check
    $env:Path = "$env:USERPROFILE\.bun\bin;$env:Path"
}

uv sync --locked --directory backend; Check # also downloads Python 3.14 if it is not there
Push-Location frontend; bun install --frozen-lockfile; Check; Pop-Location

$port = if ($env:BACKEND_PORT) { $env:BACKEND_PORT } else { "8000" }
$env:API_URL = "http://127.0.0.1:$port"
$backend = Start-Process uv -ArgumentList "run", "--directory", "backend", "uvicorn", "app.main:create_app", "--factory", "--port", $port -NoNewWindow -PassThru
try {
    Set-Location frontend
    bun run dev
} finally {
    # /T: stopping uv alone leaves its uvicorn processes running; after Ctrl+C there is nothing left to stop
    $ErrorActionPreference = "Continue"
    taskkill /PID $backend.Id /T /F 2>&1 | Out-Null
}

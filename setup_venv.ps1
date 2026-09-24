# setup_venv.ps1 — create the Portfolio_Manager venv and install requirements (Windows)
#
# Usage (from the repo root):
#   pwsh -File setup_venv.ps1
#
# Notes:
#  - Anaconda's python breaks `ensurepip`, so the script falls back to
#    `venv --without-pip` and installs with the host pip using `--target`.
#  - If .venv is half-broken, delete it first:  Remove-Item .venv -Recurse -Force
param([string]$RepoRoot = $PSScriptRoot)

$ErrorActionPreference = "Stop"
$Venv = Join-Path $RepoRoot ".venv"
$HostPython = (Get-Command python).Source   # capture BEFORE activation

# 1) Create the venv
if (-not (Test-Path (Join-Path $Venv "Scripts\python.exe"))) {
    python -m venv $Venv
    if ($LASTEXITCODE -ne 0) {
        Remove-Item $Venv -Recurse -Force -ErrorAction SilentlyContinue
        python -m venv --without-pip $Venv
    }
}

# 2) Activate
. (Join-Path $Venv "Scripts\Activate.ps1")

# 3) Install requirements into the venv's site-packages
#    (host pip with --target: sidesteps ensurepip / `pip --python` bootstrap problems)
& $HostPython -m pip install -r (Join-Path $RepoRoot "requirements.txt") --target (Join-Path $Venv "Lib\site-packages")

# 4) Verify
python -c "import pandas, pyarrow, fastapi, feedparser, dotenv; print('venv imports OK')"
Write-Host "venv ready: $Venv"
Write-Host "Use it with:  . .venv\Scripts\Activate.ps1"

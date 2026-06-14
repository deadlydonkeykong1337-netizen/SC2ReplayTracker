# Updates SC2 Replay Tracker to the latest version from GitHub.
# Works whether the app was installed via "git clone" or by downloading the ZIP.
# Your stats database (data\) and virtual environment (.venv\) are preserved.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$repo = "deadlydonkeykong1337-netizen/SC2ReplayTracker"
$branch = "main"

Write-Host "============================================"
Write-Host "  SC2 Replay Tracker - Update"
Write-Host "============================================"
Write-Host ""

# Make sure the app isn't running (it locks pythonw.exe / the database)
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -like "*run.py*" -and $_.CommandLine -like "*sc2-replay-tracker*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$gitOk = $false
if (Test-Path ".git") {
    $git = Get-Command git -ErrorAction SilentlyContinue
    if ($git) {
        Write-Host "Updating via git..."
        git pull
        if ($LASTEXITCODE -eq 0) { $gitOk = $true }
        else { Write-Host "git pull failed (local changes?). Falling back to ZIP download." }
    }
}

if (-not $gitOk) {
    $zipUrl = "https://github.com/$repo/archive/refs/heads/$branch.zip"
    $tmp = Join-Path $env:TEMP ("sc2tracker_update_" + [System.Guid]::NewGuid().ToString("N"))
    New-Item -ItemType Directory -Path $tmp | Out-Null
    $zip = Join-Path $tmp "src.zip"
    Write-Host "Downloading latest version..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $zipUrl -OutFile $zip
    Write-Host "Extracting..."
    Expand-Archive -Path $zip -DestinationPath $tmp -Force
    $src = (Get-ChildItem -Path $tmp -Directory | Select-Object -First 1).FullName
    Write-Host "Installing new files (keeping your data)..."
    # /E all subdirs; no /PURGE so local-only folders (data, .venv) are kept.
    robocopy $src $root /E /XD ".git" /NFL /NDL /NJH /NJS /NP | Out-Null
    Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
}

Write-Host "Updating dependencies..."
if (Test-Path ".venv\Scripts\pip.exe") {
    & ".venv\Scripts\pip.exe" install -r requirements.txt --quiet --disable-pip-version-check
} else {
    Write-Host "No virtual environment found - run setup.bat first."
}

Write-Host ""
Write-Host "Update complete. You can close this window and start the app."

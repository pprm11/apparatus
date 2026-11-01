# Thin wrapper: find a real Python 3.10+ (installing it with winget when missing), then hand over to
# tools\bootstrap.py. Everything else lives in Python. Usage: .\bootstrap.ps1 --psique OWNER/REPO [--dry-run]
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Find-Python {
  foreach ($cand in @("python", "python3", "py")) {
    $cmd = Get-Command $cand -ErrorAction SilentlyContinue
    # The Microsoft Store alias under WindowsApps is a stub that opens the Store, not a Python.
    if (-not $cmd -or $cmd.Source -like "*\WindowsApps\*") { continue }
    & $cmd.Source -c "import sys; sys.exit(sys.version_info < (3, 10))" 2>$null
    if ($LASTEXITCODE -eq 0) { return $cmd.Source }
  }
  return $null
}

$py = Find-Python
if (-not $py) {
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { throw "winget is missing; install Python 3.10+ by hand, then run this again." }
  winget install --id Python.Python.3.12 -e --silent --accept-source-agreements --accept-package-agreements
  # winget does not update this session's PATH.
  $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
  $py = Find-Python
  if (-not $py) { throw "Python 3.10+ is still not on PATH; open a new terminal and run this again." }
}
& $py -I (Join-Path $here "tools\bootstrap.py") @args
exit $LASTEXITCODE

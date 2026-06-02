param(
    [string]$Wheelhouse = (Join-Path $PSScriptRoot "..\pyvisa_pkgs")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Wheelhouse)) {
    throw "Wheelhouse not found: $Wheelhouse"
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
}

if (-not $python) {
    throw "Python が見つかりません。先に Miniconda をインストールしてください。"
}

& $python.Source -m pip install --no-index --find-links $Wheelhouse -r (Join-Path $PSScriptRoot "..\requirements-offline.txt")
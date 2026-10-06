param([string]$Python = '', [switch]$Cuda)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $Python) {
    $bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    $Python = if (Test-Path -LiteralPath $bundledPython) { $bundledPython } else { 'python' }
}
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
    & $Python -c "import sys; assert (3,11) <= sys.version_info[:2] <= (3,13), 'Use Python 3.11-3.13; Python 3.12 is recommended'"
    if ($LASTEXITCODE) { throw 'Select Python 3.12 with -Python C:\path\python.exe' }
    & $Python -m venv .venv
    if ($LASTEXITCODE) { throw 'Cannot create virtual environment' }
}
if ($Cuda) {
    & .\.venv\Scripts\python.exe -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
} else {
    & .\.venv\Scripts\python.exe -m pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cpu
}
if ($LASTEXITCODE) { throw 'Cannot install PyTorch' }
& .\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
if ($LASTEXITCODE) { throw 'Cannot install application dependencies' }
& .\.venv\Scripts\python.exe scripts\download_ocr.py
if ($LASTEXITCODE) { throw 'Cannot download OCR model' }
Write-Host 'Setup complete. Run .\run.cmd and open http://127.0.0.1:8000'

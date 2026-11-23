param([string]$BindAddress = '127.0.0.1', [int]$Port = 8787)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (!(Test-Path '.venv/Scripts/python.exe')) { throw 'Ambiente Python ausente. Consulte README.md.' }
if (!(Test-Path 'dist/index.html')) { npm run build; if ($LASTEXITCODE -ne 0) { throw 'Build falhou.' } }
& '.\.venv\Scripts\python.exe' 'server/runtime.py'
if ($LASTEXITCODE -ne 0) { Write-Warning 'O motor local precisa de atenção. Consulte Conta e fontes.' }
& '.\.venv\Scripts\python.exe' 'server/app.py' '--host' $BindAddress '--port' $Port

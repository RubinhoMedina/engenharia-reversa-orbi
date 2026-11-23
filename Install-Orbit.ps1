$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (!(Test-Path '.venv/Scripts/python.exe')) {
    python -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar ambiente Python.' }
}
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências Python.' }
npm ci
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências da interface.' }
npm run build
if ($LASTEXITCODE -ne 0) { throw 'Falha no build.' }
Write-Output 'Dependências preparadas. Use Configure-Orbit.ps1 para conectar serviços e Start-Orbit.ps1 para iniciar.'

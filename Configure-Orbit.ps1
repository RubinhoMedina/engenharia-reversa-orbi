$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (!(Test-Path '.venv/Scripts/python.exe')) { throw 'Execute Install-Orbit.ps1 para preparar as dependências.' }
& '.\.venv\Scripts\python.exe' 'server/configure.py'

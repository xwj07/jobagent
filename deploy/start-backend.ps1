$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot '..')
python -m uvicorn jobagent.api:app --host 127.0.0.1 --port 8000
exit $LASTEXITCODE

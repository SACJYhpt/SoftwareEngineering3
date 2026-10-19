param([switch]$SeedDemo)
$ErrorActionPreference = 'Stop'
Push-Location $PSScriptRoot
try {
    $pythonPath = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        python -m venv venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.10+ is required.' }
    }
    & $pythonPath -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    if (-not (Test-Path -LiteralPath '.env')) {
        $randomBytes = New-Object byte[] 48
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        try { $rng.GetBytes($randomBytes) } finally { $rng.Dispose() }
        $secret = [Convert]::ToBase64String($randomBytes)
        $envText = (Get-Content -LiteralPath '.env.example' -Raw).Replace('replace-with-a-random-secret-at-least-32-characters', $secret)
        [System.IO.File]::WriteAllText((Join-Path $PSScriptRoot '.env'), $envText, (New-Object System.Text.UTF8Encoding($false)))
    }
    if ($SeedDemo) {
        & $pythonPath seed_demo.py
        if ($LASTEXITCODE -ne 0) { throw 'Demo seed failed.' }
    }
    Write-Host 'Open http://127.0.0.1:8000/docs to test the backend. Ctrl+C stops it.'
    & $pythonPath -m uvicorn main:app --host 127.0.0.1 --port 8000
    if ($LASTEXITCODE -ne 0) { throw 'Backend startup failed.' }
} finally {
    Pop-Location
}

# Starts only the disposable, loopback CashPilot practice environment.
[CmdletBinding()]
param([switch]$OpenBrowser)

$ErrorActionPreference = 'Stop'
$project = $PSScriptRoot
$backend = Join-Path $project 'backend'
$frontend = Join-Path $project 'frontend'
$practice = 'http://127.0.0.1:5179/practice.html'
$status = 'http://127.0.0.1:18081/practice/status'
$headers = @{Authorization='Bearer cashpilot-disposable-demo'}
$started = @()

function Test-CashPilotEndpoint([bool]$Api) {
    try {
        if ($Api) {
            $data = Invoke-RestMethod -Uri $status -Headers $headers -TimeoutSec 1
            return $null -ne $data.imported
        }
        $response = Invoke-WebRequest -Uri $practice -TimeoutSec 1
        return $response.StatusCode -eq 200 -and $response.Content.Contains('CashPilot Local Practice')
    } catch { return $false }
}

function Assert-FreePort([int]$Port) {
    $listeners = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
    if ($listeners) { throw "Port $Port is already taken. Close the conflicting local app and retry." }
}

function Wait-ForCashPilot([bool]$Api, $Process, [string]$Log) {
    for ($attempt=0; $attempt -lt 20; $attempt++) {
        if (Test-CashPilotEndpoint $Api) { return }
        if ($Process.HasExited) { break }
        Start-Sleep -Milliseconds 500
    }
    throw "CashPilot did not start. See $Log"
}

try {
    $needApi = -not (Test-CashPilotEndpoint $true)
    $needUi = -not (Test-CashPilotEndpoint $false)
    if ($needApi) {
        Assert-FreePort 18081
        $python = @((Join-Path $project '.venv/Scripts/python.exe'), (Join-Path $backend '.venv/Scripts/python.exe')) |
            Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
        if (-not $python) { throw 'Create a Python virtual environment and install backend/requirements.txt first (see README).' }
    }
    if ($needUi) {
        Assert-FreePort 5179
        $node = (Get-Command node.exe -ErrorAction Stop).Source
        $vite = Join-Path $frontend 'node_modules/vite/bin/vite.js'
        if (-not (Test-Path -LiteralPath $vite)) { throw 'Run npm ci in the frontend folder first (see README).' }
    }
    if ($needApi -or $needUi) {
        $logs = Join-Path ([IO.Path]::GetTempPath()) ("cashpilot-practice-" + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $logs | Out-Null
    }
    if ($needApi) {
        $stderr = Join-Path $logs 'api-error.log'
        $process = Start-Process -FilePath $python -ArgumentList 'pilot_demo.py' -WorkingDirectory $backend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'api.log') -RedirectStandardError $stderr -PassThru
        $started += $process
        Wait-ForCashPilot $true $process $stderr
    }
    if ($needUi) {
        $stderr = Join-Path $logs 'ui-error.log'
        $process = Start-Process -FilePath $node -ArgumentList @('node_modules/vite/bin/vite.js','--host','127.0.0.1','--port','5179','--strictPort') -WorkingDirectory $frontend -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logs 'ui.log') -RedirectStandardError $stderr -PassThru
        $started += $process
        Wait-ForCashPilot $false $process $stderr
    }
} catch {
    foreach ($process in $started) {
        if (-not $process.HasExited) { Stop-Process -InputObject $process -ErrorAction SilentlyContinue }
    }
    throw
}

Write-Output "CashPilot practice is ready: $practice"
if ($OpenBrowser) { Start-Process $practice }

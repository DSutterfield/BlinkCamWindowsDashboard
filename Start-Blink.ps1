<#
Start-Blink.ps1

Starts the Blink clip poller and web dashboard, waits for the web server,
and opens the dashboard in the default browser only when the dashboard
process is newly started.

Developer note - 2026-08-02, Dan and Sage:
The script uses $PSScriptRoot so it works from the repository directory
without hard-coded project paths.

Developer note - 2026-08-03, Dan and Sage:
Start-PythonScript now returns whether it started a new process.
The browser is opened only when the web dashboard is newly started,
preventing duplicate browser windows during repeated startup requests.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv\Scripts\python.exe'
$pollerScript = Join-Path $projectRoot 'blink_dvr.py'
$webScript = Join-Path $projectRoot 'web_app.py'
$dashboardUrl = 'http://127.0.0.1:5000'

function Test-PythonScriptRunning {
    param(
        [Parameter(Mandatory)]
        [string]$ScriptPath
    )

    $escapedPath = [regex]::Escape($ScriptPath)

    $process = Get-CimInstance Win32_Process |
        Where-Object {
            $_.Name -match '^python(w)?\.exe$' -and
            $_.CommandLine -match $escapedPath
        } |
        Select-Object -First 1

    return $null -ne $process
}

function Start-PythonScript {
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$ScriptPath
    )

    if (Test-PythonScriptRunning -ScriptPath $ScriptPath) {
        Write-Host "$Name is already running."
        return $false
    }

    Write-Host "Starting $Name..."

    Start-Process `
        -FilePath $pythonExe `
        -ArgumentList "`"$ScriptPath`"" `
        -WorkingDirectory $projectRoot `
        -WindowStyle Minimized

    Start-Sleep -Seconds 1

    return $true
}

if (-not (Test-Path $pythonExe)) {
    throw "Python environment not found: $pythonExe"
}

if (-not (Test-Path $pollerScript)) {
    throw "Clip poller not found: $pollerScript"
}

if (-not (Test-Path $webScript)) {
    throw "Web server not found: $webScript"
}

Write-Host
Write-Host 'Blink DVR startup'
Write-Host '-----------------'

$pollerStarted = Start-PythonScript `
    -Name 'Clip poller' `
    -ScriptPath $pollerScript

$webStarted = Start-PythonScript `
    -Name 'Web dashboard' `
    -ScriptPath $webScript

Write-Host
Write-Host 'Checking the dashboard...'

$serverReady = $false

for ($attempt = 1; $attempt -le 20; $attempt++) {
    try {
        $response = Invoke-WebRequest `
            -Uri $dashboardUrl `
            -UseBasicParsing `
            -TimeoutSec 2

        if ($response.StatusCode -eq 200) {
            $serverReady = $true
            break
        }
    }
    catch {
        Start-Sleep -Seconds 1
    }
}

if (-not $serverReady) {
    throw "The web server did not respond at $dashboardUrl."
}

Write-Host 'Dashboard is ready.'

if ($webStarted) {
    Write-Host "Opening $dashboardUrl"
    Start-Process $dashboardUrl
}
else {
    Write-Host 'Dashboard was already running; browser not opened.'
}
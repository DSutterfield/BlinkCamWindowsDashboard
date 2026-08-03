<#
Get-BlinkStatus.ps1

Reports the state of the Blink clip poller, web dashboard process,
TCP listener, and dashboard HTTP response.

Developer note - 2026-08-02, Dan and Sage:
A process alone does not prove that the dashboard is usable. Therefore,
the script reports the Python process, TCP port, and HTTP response
separately.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = $PSScriptRoot
$pollerScript = Join-Path $projectRoot 'blink_dvr.py'
$webScript = Join-Path $projectRoot 'web_app.py'
$dashboardUrl = 'http://127.0.0.1:5000'

function Get-PythonScriptProcesses {
    param(
        [Parameter(Mandatory)]
        [string]$ScriptPath
    )

    $escapedPath = [regex]::Escape($ScriptPath)

    return @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -match '^python(w)?\.exe$' -and
                $_.CommandLine -and
                $_.CommandLine -match $escapedPath
            }
    )
}

function Show-ProcessStatus {
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [AllowEmptyCollection()]
        [object[]]$Processes
    )

    if ($Processes.Count -eq 0) {
        Write-Host ("{0,-20} STOPPED" -f $Name)
        return
    }

    $processIds = ($Processes.ProcessId -join ', ')
    Write-Host (
        "{0,-20} RUNNING  Process ID: {1}" -f
        $Name,
        $processIds
    )
}

$pollerProcesses = @(
    Get-PythonScriptProcesses -ScriptPath $pollerScript
)

$webProcesses = @(
    Get-PythonScriptProcesses -ScriptPath $webScript
)

$listeners = @(
    Get-NetTCPConnection `
        -LocalPort 5000 `
        -State Listen `
        -ErrorAction SilentlyContinue
)

$dashboardResponding = $false
$dashboardStatusCode = $null

try {
    $response = Invoke-WebRequest `
        -Uri $dashboardUrl `
        -UseBasicParsing `
        -TimeoutSec 5

    $dashboardStatusCode = $response.StatusCode
    $dashboardResponding = $response.StatusCode -eq 200
}
catch {
    $dashboardResponding = $false
}

Write-Host
Write-Host 'Blink DVR status'
Write-Host '----------------'

Show-ProcessStatus `
    -Name 'Clip poller' `
    -Processes $pollerProcesses

Show-ProcessStatus `
    -Name 'Web dashboard' `
    -Processes $webProcesses

if ($listeners.Count -gt 0) {
    $listenerIds = ($listeners.OwningProcess -join ', ')
    Write-Host (
        "{0,-20} LISTENING  Process ID: {1}" -f
        'TCP port 5000',
        $listenerIds
    )
}
else {
    Write-Host ("{0,-20} CLOSED" -f 'TCP port 5000')
}

if ($dashboardResponding) {
    Write-Host (
        "{0,-20} AVAILABLE  HTTP {1}" -f
        'Dashboard',
        $dashboardStatusCode
    )
}
else {
    Write-Host ("{0,-20} NOT AVAILABLE" -f 'Dashboard')
}

Write-Host
Write-Host "Dashboard address: $dashboardUrl"
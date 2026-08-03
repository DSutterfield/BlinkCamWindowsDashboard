<#
Stop-Blink.ps1

Stops the Blink clip poller and web dashboard processes started from this
project. Other Python programs are not affected.

Developer note - 2026-08-02, Dan and Sage:
Process command lines are matched against the full paths of blink_dvr.py
and web_app.py so unrelated Python applications are left running.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = $PSScriptRoot
$pollerScript = Join-Path $projectRoot 'blink_dvr.py'
$webScript = Join-Path $projectRoot 'web_app.py'

function Stop-PythonScript {
    param(
        [Parameter(Mandatory)]
        [string]$Name,

        [Parameter(Mandatory)]
        [string]$ScriptPath
    )

    $escapedPath = [regex]::Escape($ScriptPath)

    $processes = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.Name -match '^python(w)?\.exe$' -and
                $_.CommandLine -match $escapedPath
            }
    )

    if ($processes.Count -eq 0) {
        Write-Host "$Name is not running."
        return
    }

    foreach ($process in $processes) {
        Write-Host (
            "Stopping {0} - process {1}..." -f
            $Name,
            $process.ProcessId
        )

        Stop-Process `
            -Id $process.ProcessId `
            -Force `
            -ErrorAction Stop
    }

    Write-Host "$Name stopped."
}

Write-Host
Write-Host 'Blink DVR shutdown'
Write-Host '------------------'

Stop-PythonScript `
    -Name 'Clip poller' `
    -ScriptPath $pollerScript

Stop-PythonScript `
    -Name 'Web dashboard' `
    -ScriptPath $webScript

Write-Host
Write-Host 'Blink DVR processes have been stopped.'
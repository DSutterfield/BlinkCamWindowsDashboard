<#
Create-BlinkShortcuts.ps1

Creates Windows desktop shortcuts for starting, stopping, and checking
the status of the Blink DVR application.

Developer note - 2026-08-03, Dan and Sage:
The Start and Stop shortcuts now close their PowerShell windows after
completion. The Status shortcut remains open so its report can be read.

Developer note - 2026-08-02, Dan and Sage:
The shortcuts point to scripts in this repository. Re-run this script if
the repository is moved to another directory.
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$projectRoot = $PSScriptRoot
$desktopPath = [Environment]::GetFolderPath('Desktop')
$powershellExe = Join-Path $PSHOME 'powershell.exe'

if (-not (Test-Path $powershellExe)) {
    $powershellExe = 'powershell.exe'
}

function New-BlinkShortcut {
    param(
        [Parameter(Mandatory)]
        [string]$ShortcutName,

        [Parameter(Mandatory)]
        [string]$ScriptName,

        [Parameter(Mandatory)]
        [string]$Description,

        [switch]$KeepWindowOpen
    )

    $scriptPath = Join-Path $projectRoot $ScriptName

    if (-not (Test-Path $scriptPath)) {
        throw "Required script not found: $scriptPath"
    }

    $shortcutPath = Join-Path $desktopPath "$ShortcutName.lnk"

    $arguments = '-NoProfile '

    if ($KeepWindowOpen) {
        $arguments += '-NoExit '
    }

    $arguments += "-File `"$scriptPath`""

    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)

    $shortcut.TargetPath = $powershellExe
    $shortcut.Arguments = $arguments
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.Description = $Description
    $shortcut.IconLocation = "$powershellExe,0"
    $shortcut.Save()

    Write-Host "Created: $shortcutPath"
}

Write-Host
Write-Host 'Creating Blink desktop shortcuts'
Write-Host '--------------------------------'

New-BlinkShortcut `
    -ShortcutName 'Start Blink' `
    -ScriptName 'Start-Blink.ps1' `
    -Description 'Start the Blink services and open the dashboard'

New-BlinkShortcut `
    -ShortcutName 'Stop Blink' `
    -ScriptName 'Stop-Blink.ps1' `
    -Description 'Stop the Blink services'

New-BlinkShortcut `
    -ShortcutName 'Blink Status' `
    -ScriptName 'Get-BlinkStatus.ps1' `
    -Description 'Display the current Blink service status' `
    -KeepWindowOpen

Write-Host
Write-Host 'Desktop shortcuts created successfully.'
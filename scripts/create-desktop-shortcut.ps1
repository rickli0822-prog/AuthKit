# 在桌面创建「AuthKit」快捷方式
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Launcher = Join-Path $PSScriptRoot "authkit-gui.cmd"
$IconPath = Join-Path $ProjectRoot "assets\authkit.ico"
$Icon = if (Test-Path $IconPath) { $IconPath } else { "$env:SystemRoot\System32\imageres.dll,109" }
$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "AuthKit.lnk"
$StartMenuDir = Join-Path ([Environment]::GetFolderPath("StartMenu")) "Programs"
$StartMenuShortcut = Join-Path $StartMenuDir "AuthKit.lnk"

if (-not (Test-Path $Launcher)) {
    throw "找不到启动器: $Launcher"
}

function New-AppShortcut {
    param(
        [string]$LinkPath,
        [string]$Description
    )
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($LinkPath)
    $shortcut.TargetPath = $Launcher
    $shortcut.WorkingDirectory = $ProjectRoot
    $shortcut.WindowStyle = 1
    $shortcut.Description = $Description
    $shortcut.IconLocation = $Icon
    $shortcut.Save()
}

$description = "AuthKit — AI client login diagnostics"

New-AppShortcut -LinkPath $ShortcutPath -Description $description
Write-Host "已创建桌面快捷方式:"
Write-Host "  $ShortcutPath"

if (Test-Path $StartMenuDir) {
    New-AppShortcut -LinkPath $StartMenuShortcut -Description $description
    Write-Host "已创建开始菜单快捷方式:"
    Write-Host "  $StartMenuShortcut"
}

Write-Host ""
Write-Host "双击「AuthKit」即可打开图形界面。"

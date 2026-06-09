<#
.SYNOPSIS
Installation script for QGIS Plugin GeoVCS

.DESCRIPTION
Installs or removes the GeoVCS QGIS plugin.

.EXAMPLE
.\install.ps1
Installs the plugin.

.EXAMPLE
.\install.ps1 -Remove
Removes the plugin.

.EXAMPLE
.\install.ps1 -Name custom_name
Installs the plugin with a custom folder name.
#>

param (
    [switch]$Remove,
    [string]$Name = "geovcs"
)

# Equivalente ao "set -e" do Bash. O script vai parar se encontrar erros não tratados.
$ErrorActionPreference = "Stop"

# Detecta o sistema operacional e define o diretório de plugins do QGIS
if ($IsLinux) {
    $OS = "Linux"
    $PluginDir = Join-Path $HOME ".local/share/QGIS/QGIS4/profiles/default/python/plugins"
}
elseif ($IsMacOS) {
    $OS = "macOS"
    $PluginDir = Join-Path $HOME "Library/Application Support/QGIS/QGIS4/profiles/default/python/plugins"
}
elseif ($IsWindows -or ($PSVersionTable.PSVersion.Major -lt 6)) {
    # No Windows PowerShell 5.1 as variáveis $Is* não existem, então assumimos Windows como padrão aqui.
    $OS = "Windows"
    $PluginDir = Join-Path $env:APPDATA "QGIS\QGIS4\profiles\default\python\plugins"
}
else {
    Write-Host "Unknown OS type." -ForegroundColor Red
    Write-Host "Please manually copy the geovcs folder to your QGIS plugins directory."
    exit 1
}

# Obtém o diretório onde este script está localizado
$SourceDir = Join-Path $PSScriptRoot "geovcs"
$TargetDir = Join-Path $PluginDir $Name

Write-Host "Platform: $OS"
Write-Host "Plugin directory: $PluginDir"
Write-Host "Plugin name: GeoVCS"
Write-Host ""

if ($Remove) {
    # Remove o plugin
    if (Test-Path -Path $TargetDir) {
        Write-Host "Removing plugin: $TargetDir"
        Remove-Item -Path $TargetDir -Recurse -Force
        Write-Host "Plugin removed successfully." -ForegroundColor Green
    }
    else {
        Write-Host "Plugin not found. Nothing to remove." -ForegroundColor Yellow
    }
}
else {
    # Instala o plugin

    # Verifica se a pasta de origem existe
    if (-not (Test-Path -Path $SourceDir)) {
        Write-Host "Error: Source directory not found: $SourceDir" -ForegroundColor Red
        exit 1
    }

    # Cria o diretório de plugins se ele não existir
    if (-not (Test-Path -Path $PluginDir)) {
        New-Item -Path $PluginDir -ItemType Directory -Force | Out-Null
    }

    # Remove a instalação existente
    if (Test-Path -Path $TargetDir) {
        Write-Host "Removing existing installation..."
        Remove-Item -Path $TargetDir -Recurse -Force
    }

    # Copia o plugin
    Write-Host "Installing plugin to: $PluginDir"
    Copy-Item -Path $SourceDir -Destination $TargetDir -Recurse -Force

    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "Installation complete!" -ForegroundColor Green
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To use the plugin:"
    Write-Host "  1. Restart QGIS"
    Write-Host "  2. Go to Plugins -> Manage and Install Plugins..."
    Write-Host "  3. Enable 'GeoVCS'"
    Write-Host ""
}
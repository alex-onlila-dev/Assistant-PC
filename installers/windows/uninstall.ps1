# Désinstallation de Jarvis (Windows) quand il a été installé avec install.ps1 seul.
# Avec JarvisSetup.exe, passe plutôt par Paramètres > Applications > Jarvis > Désinstaller.
param([string]$AppDir = "$env:LOCALAPPDATA\Jarvis\app", [switch]$KeepData, [switch]$Quiet)
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

if ((Test-Path $AppDir) -and -not ((Test-Path "$AppDir\main.py") -and (Test-Path "$AppDir\jarvis"))) {
    throw "$AppDir ne ressemble pas à une installation de Jarvis : rien n'est supprimé."
}

# Arrête Jarvis s'il tourne (seulement les processus lancés depuis ce dossier)
Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -like "*$AppDir\main.py*" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$programs = [Environment]::GetFolderPath("Programs")
Remove-Item "$programs\Jarvis.lnk", "$programs\Jarvis (mode texte).lnk",
            "$([Environment]::GetFolderPath('Startup'))\Jarvis.lnk" -ErrorAction SilentlyContinue
Remove-Item $AppDir -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "Jarvis est désinstallé."

$DataDir = if ($env:JARVIS_HOME) { $env:JARVIS_HOME } else { "$env:USERPROFILE\.jarvis" }
if (-not $KeepData -and -not $Quiet) {
    $r = Read-Host "Supprimer aussi ta configuration, ton historique et tes alarmes ($DataDir) ? [o/N]"
    if ($r -match '^(o|oui|y)$') { Remove-Item $DataDir -Recurse -Force; Write-Host "Données supprimées." }
}
Write-Host "Ollama et ses modèles ne sont pas touchés. Pour libérer leur place : ollama rm qwen2.5:3b"

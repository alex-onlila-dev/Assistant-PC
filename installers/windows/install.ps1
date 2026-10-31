# ============================================================
#  Installation de Jarvis — Windows 10 / 11
#
#  Appelé par JarvisSetup.exe, ou à la main depuis le dossier du projet :
#    powershell -ExecutionPolicy Bypass -File installers\windows\install.ps1
#
#  Options : -Yes          sans questions (réponses par défaut)
#            -NoAutostart  ne pas lancer Jarvis à l'ouverture de session
#            -SkipOllama   ne pas installer Ollama ni télécharger le cerveau
#            -SkipModels   ne pas précharger Whisper / la voix / le mot d'activation
#            -Model NOM    modèle Ollama (défaut : choisi selon la mémoire vive)
#            -WithVision   télécharger aussi le modèle vision (~6 Go)
#
#  Jarvis s'installe pour ton compte, sans droits administrateur.
# ============================================================
param(
    [string]$AppDir = "$env:LOCALAPPDATA\Jarvis\app",
    [switch]$Yes, [switch]$NoAutostart, [switch]$SkipOllama, [switch]$SkipModels,
    [string]$Model = "", [switch]$WithVision,
    [switch]$NoShortcuts   # JarvisSetup.exe crée lui-même les raccourcis
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest est 10x plus lent avec la barre de progression
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$Src = (Resolve-Path "$PSScriptRoot\..\..").Path
$DataDir = if ($env:JARVIS_HOME) { $env:JARVIS_HOME } else { "$env:USERPROFILE\.jarvis" }
$PiperUrl = "https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium"

function Step($t) { Write-Host "`n> $t" -ForegroundColor Cyan }
function Ok($t)   { Write-Host "  [ok] $t" -ForegroundColor Green }
function Warn($t) { Write-Host "  [!] $t" -ForegroundColor Yellow }
function Ask($q)  {
    if ($Yes) { return $true }
    $r = Read-Host "  $q [O/n]"
    return -not ($r -match '^(n|non)$')
}
function Have($c) { return [bool](Get-Command $c -ErrorAction SilentlyContinue) }

# --- Mémoire vive -> taille du cerveau ---
$RamGb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
if (-not $Model) { $Model = if ($RamGb -lt 12) { "qwen2.5:3b" } else { "qwen2.5:7b" } }

Write-Host "Installation de Jarvis" -ForegroundColor White
Write-Host "  Mémoire vive   : $RamGb Go"
Write-Host "  Programme      : $AppDir"
Write-Host "  Configuration  : $DataDir\config.yaml (conservée lors des mises à jour)"
Write-Host "  Cerveau        : $Model"
if (-not (Ask "Continuer ?")) { Write-Host "Installation annulée."; exit 0 }

# ------------------------------------------------------------ 1. uv (fournit Python, sans toucher au système)
Step "Python"
$env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
if (-not (Have "uv")) {
    Write-Host "  Installation de uv (gestionnaire Python autonome)…"
    $env:UV_NO_MODIFY_PATH = "1"
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression | Out-Null
}
if (-not (Have "uv")) { throw "uv introuvable après installation." }
Ok "uv $((uv --version).Split(' ')[1])"

# ------------------------------------------------------------ 2. programme
Step "Programme"
New-Item -ItemType Directory -Force -Path $AppDir, $DataDir | Out-Null
if ((Resolve-Path $AppDir).Path -ne $Src) {
    robocopy $Src $AppDir /E /XD .git .venv models __pycache__ .pytest_cache dist /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Copie du programme impossible (robocopy $LASTEXITCODE)." }
    if (Test-Path "$Src\models") { robocopy "$Src\models" "$AppDir\models" /XC /XN /XO /NFL /NDL /NJH /NJS /NP | Out-Null }
}
Ok "code copié dans $AppDir"

$Py = "$AppDir\.venv\Scripts\python.exe"
$PyW = "$AppDir\.venv\Scripts\pythonw.exe"
uv venv --quiet --allow-existing --python 3.12 "$AppDir\.venv"
if ($LASTEXITCODE) { throw "Création de l'environnement Python impossible." }
Write-Host "  Installation des modules Python (quelques minutes la première fois)…"
uv pip install --quiet --python $Py -r "$AppDir\requirements.txt"
if ($LASTEXITCODE) { throw "Installation des modules Python impossible." }
Ok "Python $(& $Py -c 'import sys; print(sys.version.split()[0])') et modules installés"

# ------------------------------------------------------------ 3. configuration
Step "Configuration"
if (Test-Path "$DataDir\config.yaml") {
    Ok "configuration existante conservée ($DataDir\config.yaml)"
} else {
    $cfg = Get-Content "$AppDir\config.yaml" -Raw -Encoding UTF8
    $cfg = $cfg -replace '(?m)^  model: "[^"]*"', "  model: `"$Model`""
    [IO.File]::WriteAllText("$DataDir\config.yaml", $cfg, (New-Object Text.UTF8Encoding $false))
    Ok "configuration créée (cerveau : $Model)"
}

# ------------------------------------------------------------ 4. voix et écoute
if (-not $SkipModels) {
    Step "Voix et écoute"
    New-Item -ItemType Directory -Force -Path "$AppDir\models" | Out-Null
    foreach ($f in "fr_FR-siwis-medium.onnx", "fr_FR-siwis-medium.onnx.json") {
        if (-not (Test-Path "$AppDir\models\$f")) {
            Write-Host "  Téléchargement de $f…"
            Invoke-WebRequest "$PiperUrl/$f" -OutFile "$AppDir\models\$f"
        }
    }
    Ok "voix française (Piper)"
    Write-Host "  Préchargement de la reconnaissance vocale et du mot d'activation…"
    $preload = @"
from jarvis.config import load_config
cfg = load_config()
from jarvis.voice.stt import get_transcriber
get_transcriber(cfg)
import openwakeword
openwakeword.utils.download_models(model_names=[cfg['voice']['wake_word']])
"@
    Push-Location $AppDir
    $ErrorActionPreference = "Continue"   # PowerShell 5.1 : sinon le moindre message sur stderr arrête tout
    $preload | & $Py - 2>$null
    $failed = $LASTEXITCODE
    $ErrorActionPreference = "Stop"
    if ($failed) { Warn "préchargement impossible : ils se téléchargeront au premier lancement" } else { Ok "Whisper et « Hey Jarvis » prêts" }
    Pop-Location
}

# ------------------------------------------------------------ 5. cerveau (Ollama)
if (-not $SkipOllama) {
    Step "Cerveau (Ollama)"
    $ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
    if (-not $ollama) { $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" }
    if (-not (Test-Path $ollama)) {
        if ((Have "winget") -and (Ask "Installer Ollama ?")) {
            winget install --id Ollama.Ollama -e --silent --accept-source-agreements --accept-package-agreements | Out-Null
        } else {
            Warn "Installe Ollama depuis https://ollama.com/download puis relance l'installation."
            Start-Process "https://ollama.com/download"
        }
    }
    if (Test-Path $ollama) {
        try { Invoke-RestMethod http://localhost:11434/api/tags -TimeoutSec 2 | Out-Null }
        catch { Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden; Start-Sleep 4 }
        Write-Host "  Téléchargement du cerveau $Model (plusieurs Go la première fois)…"
        & $ollama pull $Model
        if (-not $LASTEXITCODE) { Ok "cerveau $Model prêt" } else { Warn "téléchargement du cerveau impossible : relance « ollama pull $Model »" }
        if ($WithVision) { & $ollama pull qwen2.5vl:7b }
    } else {
        Warn "Ollama absent : Jarvis ne pourra pas réfléchir tant qu'il n'est pas installé."
    }
}

# ------------------------------------------------------------ 6. raccourcis
if (-not $NoShortcuts) {
    Step "Raccourcis"
    $shell = New-Object -ComObject WScript.Shell
    function Shortcut($path, $exe, $arguments) {
        $s = $shell.CreateShortcut($path)
        $s.TargetPath = $exe; $s.Arguments = $arguments; $s.WorkingDirectory = $AppDir
        $s.Description = "Jarvis — assistant personnel local"; $s.Save()
    }
    $programs = [Environment]::GetFolderPath("Programs")
    Shortcut "$programs\Jarvis.lnk" $PyW "`"$AppDir\main.py`" --voice --background"
    Shortcut "$programs\Jarvis (mode texte).lnk" $Py "`"$AppDir\main.py`" --cli"
    Ok "menu Démarrer"
    $startup = "$([Environment]::GetFolderPath('Startup'))\Jarvis.lnk"
    if ($NoAutostart) { Remove-Item $startup -ErrorAction SilentlyContinue }
    else { Shortcut $startup $PyW "`"$AppDir\main.py`" --voice --background"; Ok "lancement automatique à l'ouverture de session" }
}

# ------------------------------------------------------------ 7. autorisations
Step "Autorisations"
Write-Host "  Vérifie que les applications de bureau peuvent utiliser le micro :"
Write-Host "    Paramètres > Confidentialité et sécurité > Microphone > « Autoriser les applications de bureau »"
if (-not $Yes -and (Ask "Ouvrir ce réglage maintenant ?")) { Start-Process "ms-settings:privacy-microphone" }

Write-Host "`nJarvis est installé." -ForegroundColor Green
Write-Host "  Lance « Jarvis » depuis le menu Démarrer, puis dis « Hey Jarvis » ou claque deux fois des mains."
Write-Host "  Messages et erreurs : $DataDir\jarvis.log"

# ============================================================
#  Installation de Jarvis — Windows 10 / 11
#
#  Appelé par JarvisSetup.exe, ou à la main depuis le dossier du projet :
#    powershell -ExecutionPolicy Bypass -File installers\windows\install.ps1
#
#  Options : -Yes          sans questions (réponses par défaut ; le cerveau se choisit alors plus tard)
#            -Brain X      cerveau : ollama | claude | openai | later (défaut : demandé)
#            -BaseUrl URL  avec -Brain openai : adresse du service (ex. https://api.mistral.ai/v1)
#            -ApiModel NOM avec -Brain claude ou openai : nom du modèle
#            -KeyFile F    fichier contenant la clé API (effacé une fois lu) ; sinon variable JARVIS_API_KEY
#            -NoAutostart  ne pas lancer Jarvis à l'ouverture de session
#            -SkipOllama   ne jamais installer Ollama
#            -SkipModels   ne pas précharger Whisper / la voix / le mot d'activation
#            -Model NOM    modèle Ollama (défaut : choisi selon la mémoire vive ; implique -Brain ollama)
#            -WithVision   avec Ollama : télécharger aussi le modèle vision (~6 Go)
#
#  Jarvis s'installe pour ton compte, sans droits administrateur.
# ============================================================
param(
    [string]$AppDir = "$env:LOCALAPPDATA\Jarvis\app",
    [switch]$Yes, [switch]$NoAutostart, [switch]$SkipOllama, [switch]$SkipModels,
    [string]$Model = "", [switch]$WithVision,
    [ValidateSet("", "ollama", "claude", "openai", "later")][string]$Brain = "",
    [string]$BaseUrl = "", [string]$ApiModel = "", [string]$KeyFile = "",
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

function ReadSecret($q) {
    $s = Read-Host "  $q" -AsSecureString
    return [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
}

# --- Mémoire vive -> taille du cerveau local ---
$RamGb = [math]::Round((Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory / 1GB)
if ($PSBoundParameters.ContainsKey("Model") -and -not $Brain) { $Brain = "ollama" }
if (-not $Model) { $Model = if ($RamGb -lt 12) { "qwen2.5:3b" } else { "qwen2.5:7b" } }

# --- Le cerveau : c'est l'utilisateur qui choisit ---
$ApiKey = if ($KeyFile -and (Test-Path $KeyFile)) { (Get-Content $KeyFile -Raw).Trim() } else { "$env:JARVIS_API_KEY" }
if ($KeyFile) { Remove-Item $KeyFile -ErrorAction SilentlyContinue }
if (-not $Brain -and $Yes) { $Brain = "later" }
if (-not $Brain) {
    $advice = if ($RamGb -ge 12) { "1" } else { "2" }
    Write-Host "Quel cerveau pour Jarvis ? (modifiable ensuite dans Paramètres > Cerveau)" -ForegroundColor White
    Write-Host "  1. Ollama : sur cet ordinateur, sans Internet (télécharge ~5 Go, pour 12 Go de mémoire vive ou plus)"
    Write-Host "  2. Claude : avec une clé API Anthropic, rien à télécharger"
    Write-Host "  3. Autre service compatible OpenAI (OpenAI, Mistral, Groq, OpenRouter, Gemini, LM Studio…)"
    Write-Host "  4. Plus tard"
    $r = Read-Host "  Choix [1-4] (conseillé ici : $advice)"
    if (-not $r) { $r = $advice }
    $Brain = @{ "1" = "ollama"; "2" = "claude"; "3" = "openai" }[$r]
    if (-not $Brain) { $Brain = "later" }
    if ($Brain -eq "claude" -and -not $ApiKey) {
        Write-Host "  Clé à créer sur https://console.anthropic.com (payée à l'usage ; un abonnement Claude Pro/Max ne sert pas ici)."
        $ApiKey = ReadSecret "Clé API Claude (Entrée = plus tard)"
    }
    if ($Brain -eq "openai") {
        $presets = @("https://api.openai.com/v1", "https://api.mistral.ai/v1", "https://api.groq.com/openai/v1",
                     "https://openrouter.ai/api/v1", "https://api.deepseek.com/v1",
                     "https://generativelanguage.googleapis.com/v1beta/openai", "http://localhost:1234/v1")
        if (-not $BaseUrl) {
            for ($i = 0; $i -lt $presets.Count; $i++) { Write-Host "    $($i + 1). $($presets[$i])" }
            $u = Read-Host "  Service [1-$($presets.Count)] ou adresse complète"
            $BaseUrl = if ($u -match '^\d+$' -and [int]$u -ge 1 -and [int]$u -le $presets.Count) { $presets[[int]$u - 1] } else { $u }
        }
        if (-not $ApiKey) { $ApiKey = ReadSecret "Clé API du service (Entrée = aucune)" }
        if (-not $ApiModel) { $ApiModel = Read-Host "  Nom du modèle (celui donné par le service)" }
    }
}
if ($SkipOllama -and $Brain -eq "ollama") { Warn "-SkipOllama : Ollama ne sera pas installé" }
$BrainText = @{ "ollama" = "Ollama, $Model (sur cet ordinateur)"; "claude" = "Claude"
                "openai" = "service compatible OpenAI ($BaseUrl)"; "later" = "à choisir plus tard dans Paramètres > Cerveau" }[$Brain]

Write-Host "Installation de Jarvis" -ForegroundColor White
Write-Host "  Mémoire vive   : $RamGb Go"
Write-Host "  Programme      : $AppDir"
Write-Host "  Configuration  : $DataDir\config.yaml (conservée lors des mises à jour)"
Write-Host "  Cerveau        : $BrainText"
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
# Python 3.11, comme sur macOS et Linux (openwakeword n'a pas toutes ses dépendances en 3.12)
# Un environnement d'une autre version (ancienne installation) est recréé, pas mélangé
if ((Test-Path "$AppDir\.venv\pyvenv.cfg") -and -not (Select-String -Path "$AppDir\.venv\pyvenv.cfg" -Pattern '^version_info = 3\.11' -Quiet)) {
    Remove-Item "$AppDir\.venv" -Recurse -Force
}
uv venv --quiet --allow-existing --python 3.11 "$AppDir\.venv"
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
    Ok "configuration créée"
}
if ($Brain -ne "later") {
    # La clé passe par l'environnement, pas par la ligne de commande (visible dans la liste des processus)
    $env:JARVIS_BRAIN = $Brain; $env:JARVIS_API_KEY = $ApiKey; $env:JARVIS_BASE_URL = $BaseUrl
    $env:JARVIS_MODEL = if ($Brain -eq "ollama") { $Model } else { $ApiModel }
    Push-Location $AppDir
    $out = & $Py -m jarvis.setup_brain
    $failed = $LASTEXITCODE
    Pop-Location
    Remove-Item Env:JARVIS_BRAIN, Env:JARVIS_API_KEY, Env:JARVIS_BASE_URL, Env:JARVIS_MODEL -ErrorAction SilentlyContinue
    if ($failed) { Warn "cerveau non enregistré : choisis-le dans Paramètres > Cerveau" } else { Ok $out }
}
$ApiKey = ""

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

# ------------------------------------------------------------ 5. cerveau local (Ollama), seulement s'il est choisi
if ($Brain -eq "ollama" -and -not $SkipOllama) {
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
    Shortcut "$programs\Jarvis (discussion).lnk" $PyW "`"$AppDir\main.py`" --background"   # fenêtre + Paramètres
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
if ($Brain -eq "later") { Write-Host "  Choisis son cerveau dans la fenêtre Jarvis : Paramètres > Cerveau (Ollama, Claude ou un autre service)." }
Write-Host "  Lance « Jarvis » depuis le menu Démarrer, puis dis « Hey Jarvis » ou claque deux fois des mains."
Write-Host "  Messages et erreurs : $DataDir\jarvis.log"

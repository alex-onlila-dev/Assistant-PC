; ============================================================
;  JarvisSetup.exe — installateur Windows (Inno Setup 6)
;  Construit automatiquement par GitHub Actions (.github/workflows/installers.yml).
;  À la main, sous Windows :  iscc /DAppVersion=1.0.0 installers\windows\jarvis.iss
;
;  L'installateur copie le programme puis lance install.ps1, qui installe Python (via uv),
;  les modules, la voix et le cerveau. Aucun droit administrateur : tout va dans le compte.
; ============================================================
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6B2F1E4A-3C7D-4E8A-9F15-7A0C2D9B4E61}
AppName=Jarvis
AppVersion={#AppVersion}
AppVerName=Jarvis {#AppVersion}
AppPublisher=alex-onlila-dev
AppPublisherURL=https://github.com/alex-onlila-dev/Assistant-PC
DefaultDirName={localappdata}\Jarvis\app
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=JarvisSetup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName=Jarvis — assistant personnel
CloseApplications=no

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "autostart"; Description: "Lancer Jarvis à l'ouverture de session (il attend « Hey Jarvis » en arrière-plan)"
Name: "vision"; Description: "Télécharger aussi le modèle vision pour analyser images et vidéos (~6 Go)"; Flags: unchecked

[Files]
Source: "..\..\*"; DestDir: "{app}"; \
  Excludes: ".git,.github,.venv,models,dist,__pycache__,.pytest_cache,*.pyc,.DS_Store"; \
  Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{userprograms}\Jarvis"; Filename: "{app}\.venv\Scripts\pythonw.exe"; \
  Parameters: """{app}\main.py"" --voice --background"; WorkingDir: "{app}"; Comment: "Assistant personnel local"
Name: "{userprograms}\Jarvis (mode texte)"; Filename: "{app}\.venv\Scripts\python.exe"; \
  Parameters: """{app}\main.py"" --cli"; WorkingDir: "{app}"
Name: "{userstartup}\Jarvis"; Filename: "{app}\.venv\Scripts\pythonw.exe"; \
  Parameters: """{app}\main.py"" --voice --background"; WorkingDir: "{app}"; Tasks: autostart

[Run]
; Python, modules, voix et cerveau : la fenêtre montre la progression (plusieurs minutes la première fois)
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installers\windows\install.ps1"" -AppDir ""{app}"" -Yes -NoShortcuts {code:VisionFlag}"; \
  StatusMsg: "Installation de Python, des modules, de la voix et du cerveau…"; Flags: waituntilterminated
Filename: "{app}\.venv\Scripts\pythonw.exe"; Parameters: """{app}\main.py"" --voice --background"; \
  WorkingDir: "{app}"; Description: "Lancer Jarvis maintenant"; Flags: postinstall nowait skipifsilent

[UninstallRun]
; Arrête Jarvis s'il tourne et retire les raccourcis ; la configuration (~/.jarvis) est conservée
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installers\windows\uninstall.ps1"" -AppDir ""{app}"" -KeepData -Quiet"; \
  Flags: runhidden; RunOnceId: "StopJarvis"

[UninstallDelete]
; Ce que install.ps1 a créé après la copie (environnement Python, voix téléchargée)
Type: filesandordirs; Name: "{app}\.venv"
Type: filesandordirs; Name: "{app}\models"
Type: filesandordirs; Name: "{app}"

[Code]
function VisionFlag(Param: String): String;
begin
  if WizardIsTaskSelected('vision') then Result := '-WithVision' else Result := '';
end;

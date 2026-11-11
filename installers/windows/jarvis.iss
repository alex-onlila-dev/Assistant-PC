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
Name: "vision"; Description: "Avec Ollama : télécharger aussi le modèle vision pour analyser images et vidéos (~6 Go)"; Flags: unchecked

[Files]
Source: "..\..\*"; DestDir: "{app}"; \
  Excludes: ".git,.github,.venv,models,dist,__pycache__,.pytest_cache,*.pyc,.DS_Store"; \
  Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{userprograms}\Jarvis"; Filename: "{app}\.venv\Scripts\pythonw.exe"; \
  Parameters: """{app}\main.py"" --voice --background"; WorkingDir: "{app}"; Comment: "Assistant personnel local"
Name: "{userprograms}\Jarvis (discussion)"; Filename: "{app}\.venv\Scripts\pythonw.exe"; \
  Parameters: """{app}\main.py"" --background"; WorkingDir: "{app}"; Comment: "Fenêtre de discussion et Paramètres"
Name: "{userprograms}\Jarvis (mode texte)"; Filename: "{app}\.venv\Scripts\python.exe"; \
  Parameters: """{app}\main.py"" --cli"; WorkingDir: "{app}"
Name: "{userstartup}\Jarvis"; Filename: "{app}\.venv\Scripts\pythonw.exe"; \
  Parameters: """{app}\main.py"" --voice --background"; WorkingDir: "{app}"; Tasks: autostart

[Run]
; Python, modules, voix et cerveau : la fenêtre montre la progression (plusieurs minutes la première fois)
Filename: "powershell.exe"; \
  Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\installers\windows\install.ps1"" -AppDir ""{app}"" -Yes -NoShortcuts {code:BrainArgs} {code:VisionFlag}"; \
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
// Le cerveau de Jarvis : c'est l'utilisateur qui choisit (0 Claude, 1 autre service, 2 Ollama, 3 plus tard)
var
  BrainPage: TInputOptionWizardPage;
  ClaudePage, OtherPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  BrainPage := CreateInputOptionPage(wpWelcome, 'Cerveau de Jarvis',
    'Qui va comprendre tes demandes et y répondre ?',
    'Tu pourras changer ce choix plus tard dans Jarvis : Paramètres > Cerveau.', True, False);
  BrainPage.Add('Claude (Anthropic) : avec une clé API, rien à télécharger');
  BrainPage.Add('Autre service compatible OpenAI : OpenAI, Mistral, Groq, OpenRouter, Gemini, LM Studio…');
  BrainPage.Add('Ollama : sur cet ordinateur, sans Internet (télécharge environ 5 Go, 12 Go de mémoire vive conseillés)');
  BrainPage.Add('Plus tard : je choisirai dans les Paramètres de Jarvis');
  BrainPage.SelectedValueIndex := 3;

  ClaudePage := CreateInputQueryPage(BrainPage.ID, 'Clé API Claude',
    'À créer sur console.anthropic.com, rubrique API Keys.',
    'La clé est payée à l''usage, à part : un abonnement Claude Pro ou Max ne fonctionne que dans les ' +
    'applications Claude. Laisse vide pour l''ajouter plus tard dans les Paramètres.');
  ClaudePage.Add('Clé API :', True);

  OtherPage := CreateInputQueryPage(ClaudePage.ID, 'Service compatible OpenAI',
    'Adresse du service, clé API et nom du modèle.',
    'Exemples d''adresses : https://api.openai.com/v1 — https://api.mistral.ai/v1 — ' +
    'https://api.groq.com/openai/v1 — https://openrouter.ai/api/v1 — ' +
    'https://generativelanguage.googleapis.com/v1beta/openai — http://localhost:1234/v1 (LM Studio).');
  OtherPage.Add('Adresse du service :', False);
  OtherPage.Add('Clé API (vide pour un serveur local) :', True);
  OtherPage.Add('Nom du modèle (celui donné par le service) :', False);
  OtherPage.Values[0] := 'https://api.openai.com/v1';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := ((PageID = ClaudePage.ID) and (BrainPage.SelectedValueIndex <> 0)) or
            ((PageID = OtherPage.ID) and (BrainPage.SelectedValueIndex <> 1));
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if (CurPageID = OtherPage.ID) and ((Trim(OtherPage.Values[0]) = '') or (Trim(OtherPage.Values[2]) = '')) then
  begin
    MsgBox('Indique l''adresse du service et le nom du modèle.', mbError, MB_OK);
    Result := False;
  end;
end;

// Arguments pour install.ps1. La clé passe par un fichier temporaire (effacé par install.ps1 dès qu'il l'a lu) :
// sur la ligne de commande, elle serait visible dans la liste des processus.
function BrainArgs(Param: String): String;
var
  Key, KeyFile: String;
begin
  Key := '';
  case BrainPage.SelectedValueIndex of
    0: begin
         Result := '-Brain claude';
         Key := Trim(ClaudePage.Values[0]);
       end;
    1: begin
         Result := '-Brain openai -BaseUrl "' + Trim(OtherPage.Values[0]) + '" -ApiModel "' + Trim(OtherPage.Values[2]) + '"';
         Key := Trim(OtherPage.Values[1]);
       end;
    2: Result := '-Brain ollama';
  else
    Result := '-Brain later';
  end;
  if Key <> '' then
  begin
    KeyFile := ExpandConstant('{tmp}\jarvis-key.txt');
    SaveStringToFile(KeyFile, Key, False);
    Result := Result + ' -KeyFile "' + KeyFile + '"';
  end;
end;

function VisionFlag(Param: String): String;
begin
  if (BrainPage.SelectedValueIndex = 2) and WizardIsTaskSelected('vision') then Result := '-WithVision' else Result := '';
end;

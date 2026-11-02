#ifndef ProjectRoot
  #define ProjectRoot SourcePath + "\.."
#endif
#define Version "1.2.0"
#include ProjectRoot + "\build\model-download.iss"

[Setup]
AppId={{ACF9BE92-EF19-492B-962D-C3F0BEAF9473}
AppName=Paçoca
AppVersion={#Version}
AppPublisher=Paçoca
AppPublisherURL=https://github.com/AthirsonLamonato/Pacoca
AppSupportURL=https://github.com/AthirsonLamonato/Pacoca/issues
DefaultDirName={localappdata}\Programs\Pacoca
DefaultGroupName=Paçoca
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
SetupArchitecture=x64
MinVersion=10.0.17763
OutputDir={#ProjectRoot}\release
OutputBaseFilename=Pacoca-Setup
SetupIconFile={#ProjectRoot}\packaging\icon.ico
UninstallDisplayIcon={app}\Pacoca.exe
Compression=lzma2/fast
SolidCompression=no
DiskSpanning=no
WizardStyle=modern
WizardSizePercent=115
DisableProgramGroupPage=yes
DisableWelcomePage=no
CloseApplications=yes
RestartApplications=no
UninstallDisplayName=Paçoca
VersionInfoDescription=Paçoca · Instalador único
LicenseFile={#ProjectRoot}\packaging\DISTRIBUTION.txt
InfoBeforeFile={#ProjectRoot}\packaging\WELCOME.txt

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar um atalho na área de trabalho"; GroupDescription: "Deixar a Paçoca por perto:"
Name: "advancedmodel"; Description: "Baixar também a inteligência avançada 8B (5 GB, opcional)"; GroupDescription: "Recursos adicionais:"; Flags: unchecked

[Files]
Source: "{#ProjectRoot}\dist\Pacoca\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ProjectRoot}\build\offline-assets\*"; DestDir: "{app}\assets"; Excludes: "*.gguf"; Flags: ignoreversion recursesubdirs createallsubdirs
; Windows limits a runnable Setup.exe to roughly 4 GB. Keep the more capable
; model and provision it inside this same installer, never with a second app.
Source: "{#ModelURL}"; DestDir: "{app}\assets\models"; DestName: "{#ModelFile}"; ExternalSize: {#ModelSize}; Hash: "{#ModelHash}"; Flags: external download ignoreversion; Check: NeedsChatModel
Source: "{#AdvancedURL}"; DestDir: "{app}\assets\models"; DestName: "{#AdvancedFile}"; ExternalSize: {#AdvancedSize}; Hash: "{#AdvancedHash}"; Flags: external download ignoreversion; Tasks: advancedmodel; Check: NeedsAdvancedModel
Source: "{#ProjectRoot}\docs\USAR-PACOCA.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\docs\ALEXA.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "{#ProjectRoot}\packaging\alexa\pt-BR.json"; DestDir: "{app}\alexa"; Flags: ignoreversion
Source: "{#ProjectRoot}\build\source\*"; DestDir: "{app}\source"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#ProjectRoot}\build\licenses\*"; DestDir: "{app}\licenses"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Paçoca"; Filename: "{app}\Pacoca.exe"
Name: "{group}\Como usar a Paçoca"; Filename: "{app}\USAR-PACOCA.md"
Name: "{autodesktop}\Paçoca"; Filename: "{app}\Pacoca.exe"; Tasks: desktopicon

[InstallDelete]
; Remove the incompatible vendor ICU accidentally shipped in 1.0.0 on upgrade.
Type: files; Name: "{app}\_internal\icuuc.dll"
Type: files; Name: "{app}\_internal\icudt78.dll"

[Run]
Filename: "{app}\Pacoca.exe"; Description: "Conhecer minha Paçoca"; Flags: nowait postinstall skipifsilent

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "Pacoca"; Flags: uninsdeletevalue

[Code]
var
  ChatModelCheckedPath: String;
  ChatModelNeeded: Boolean;

function NeedsChatModel: Boolean;
var
  Filename: String;
begin
  Filename := ExpandConstant('{app}\assets\models\{#ModelFile}');
  if ChatModelCheckedPath <> Filename then begin
    ChatModelCheckedPath := Filename;
    ChatModelNeeded := True;
    if FileExists(Filename) then begin
      try
        ChatModelNeeded := CompareText(GetSHA256OfFile(Filename), '{#ModelHash}') <> 0;
      except
        Log('The existing model could not be verified; it will be downloaded again.');
      end;
    end;
  end;
  Result := ChatModelNeeded;
end;

function NeedsAdvancedModel: Boolean;
var Filename: String;
begin
  Filename := ExpandConstant('{app}\assets\models\{#AdvancedFile}');
  Result := True;
  if FileExists(Filename) then
    try
      Result := CompareText(GetSHA256OfFile(Filename), '{#AdvancedHash}') <> 0;
    except
      Log('The optional advanced model needs downloading.');
    end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    if not UninstallSilent then
      if MsgBox('Quer apagar também suas conversas, lembranças e preferências? Se escolher Não, elas serão preservadas para uma próxima instalação.', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(ExpandConstant('{localappdata}\Pacoca'), True, True, True);
end;

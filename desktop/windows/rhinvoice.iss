; Rhinvoice for Windows: installs the runtime and app package of desktop/build.py
; (ADR 0021, 0022). Later app packages come as updates inside the program.
; Built in CI: iscc /DAppVersion=x.y.z desktop\windows\rhinvoice.iss
;
; Installs for the current user only (no administrator rights). The data folder
; (%LOCALAPPDATA%\Rhinvoice) is not part of the installation: an uninstall or an
; update never touches invoices, which must be kept for ten years.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F0C7E59-3B7B-4E43-9A57-2C2F7D0B8B1E}
AppName=Rhinvoice
AppVersion={#AppVersion}
AppVerName=Rhinvoice {#AppVersion}
AppPublisher=Webberz
AppPublisherURL=https://rhinvoice.com
AppSupportURL=https://rhinvoice.com/docs
DefaultDirName={localappdata}\Programs\Rhinvoice
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\build\windows
OutputBaseFilename=Rhinvoice-Setup-{#AppVersion}
SetupIconFile=..\icons\Rhinvoice.ico
UninstallDisplayIcon={app}\Rhinvoice.ico
UninstallDisplayName=Rhinvoice
LicenseFile=..\..\LICENSE
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; Closes a running Rhinvoice before files are replaced.
CloseApplications=yes

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\build\windows\install\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; An update replaces the program completely; old files must not mix with new ones.
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\postgresql"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\static"
Type: filesandordirs; Name: "{app}\restic"

[UninstallDelete]
; Files the program wrote beside the installed ones (e.g. the boot's compiled Python files).
; The data lives elsewhere (%LOCALAPPDATA%\Rhinvoice) and stays.
Type: filesandordirs; Name: "{app}"

[Icons]
Name: "{autoprograms}\Rhinvoice"; Filename: "{app}\python\Rhinvoice.exe"; Parameters: "-m rhinvoice_boot"; WorkingDir: "{app}"; IconFilename: "{app}\Rhinvoice.ico"
Name: "{autodesktop}\Rhinvoice"; Filename: "{app}\python\Rhinvoice.exe"; Parameters: "-m rhinvoice_boot"; WorkingDir: "{app}"; IconFilename: "{app}\Rhinvoice.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\python\Rhinvoice.exe"; Parameters: "-m rhinvoice_boot"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,Rhinvoice}"; Flags: nowait postinstall skipifsilent

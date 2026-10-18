; Rhinvoice for Windows: installs the runtime and app package of desktop/build.py
; (ADR 0021, 0022). Later app packages come as updates inside the program.
; Built in CI: iscc /DAppVersion=x.y.z desktop\windows\rhinvoice.iss
;
; Installs for the current user only (no administrator rights). The data folder
; (%LOCALAPPDATA%\Rhinvoice) is not part of the installation: an uninstall or an
; update never touches invoices, which must be kept for ten years.
;
; With /DEdition=beta it installs Rhinvoice Beta from build\windows\install-beta
; (build.py windows-beta), for release candidates (ADR 0030): a program of its own beside
; Rhinvoice, with its own AppId, folder, shortcuts and uninstall entry; its data lives in
; %LOCALAPPDATA%\Rhinvoice Beta. Never change an AppId: Windows knows the program by it.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef Edition
  #define Edition "stable"
#endif

#if Edition == "beta"
  #define AppIdentity "{{33C691D7-C73A-4302-83F7-0BCA80193E27}"
  #define AppTitle "Rhinvoice Beta"
  #define SetupName "Rhinvoice-Beta-Setup"
  #define InstallFolder "install-beta"
#elif Edition == "stable"
  #define AppIdentity "{{6F0C7E59-3B7B-4E43-9A57-2C2F7D0B8B1E}"
  #define AppTitle "Rhinvoice"
  #define SetupName "Rhinvoice-Setup"
  #define InstallFolder "install"
#else
  #error Edition is "stable" or "beta"
#endif

[Setup]
AppId={#AppIdentity}
AppName={#AppTitle}
AppVersion={#AppVersion}
AppVerName={#AppTitle} {#AppVersion}
AppPublisher=Webberz
AppPublisherURL=https://rhinvoice.com
AppSupportURL=https://rhinvoice.com/docs
DefaultDirName={localappdata}\Programs\{#AppTitle}
; Always there: not into the data folder or a folder holding other things. An update keeps
; the folder an earlier version was installed to.
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\build\windows
OutputBaseFilename={#SetupName}-{#AppVersion}
SetupIconFile=..\icons\Rhinvoice.ico
UninstallDisplayIcon={app}\Rhinvoice.ico
UninstallDisplayName={#AppTitle}
LicenseFile=..\..\LICENSE
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; Closes a running Rhinvoice of this installation before files are replaced.
CloseApplications=yes

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\..\build\windows\{#InstallFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; An update replaces the program completely; old files must not mix with new ones.
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\postgresql"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\static"
Type: filesandordirs; Name: "{app}\restic"

[UninstallDelete]
; Files the program wrote into its own parts (e.g. the boot's compiled Python files).
; Exactly the parts the setup installs, never {app} as a whole: a folder chosen by hand
; may hold other things. The data lives elsewhere (%LOCALAPPDATA%\{#AppTitle}) and stays.
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\postgresql"
Type: filesandordirs; Name: "{app}\app"
Type: filesandordirs; Name: "{app}\static"
Type: filesandordirs; Name: "{app}\restic"
Type: dirifempty; Name: "{app}"

[Icons]
Name: "{autoprograms}\{#AppTitle}"; Filename: "{app}\python\Rhinvoice.exe"; Parameters: "-m rhinvoice_boot"; WorkingDir: "{app}"; IconFilename: "{app}\Rhinvoice.ico"
Name: "{autodesktop}\{#AppTitle}"; Filename: "{app}\python\Rhinvoice.exe"; Parameters: "-m rhinvoice_boot"; WorkingDir: "{app}"; IconFilename: "{app}\Rhinvoice.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\python\Rhinvoice.exe"; Parameters: "-m rhinvoice_boot"; WorkingDir: "{app}"; Description: "{cm:LaunchProgram,{#AppTitle}}"; Flags: nowait postinstall skipifsilent

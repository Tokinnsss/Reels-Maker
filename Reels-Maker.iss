; Build with Inno Setup 6.7+; override PayloadDir with /DPayloadDir=...
#ifndef PayloadDir
  #define PayloadDir "..\..\work\installer-payload"
#endif

[Setup]
AppId={{B16F9531-BCF7-4DB8-99A4-5713B55FB8C2}
AppName=Reels Maker
AppVersion=1.1.2
AppVerName=Reels Maker 1.1.2
AppPublisher=Tokinns Soft
AppPublisherURL=https://t.me/tokinnssoft
AppSupportURL=https://t.me/tokinnssoft
AppUpdatesURL=https://t.me/tokinnssoft
DefaultDirName={localappdata}\Programs\Reels Maker
DefaultGroupName=Reels Maker
DisableProgramGroupPage=yes
DisableWelcomePage=no
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=.
OutputBaseFilename=Reels-Maker-Setup-1.1.2
Compression=lzma2
SolidCompression=yes
DiskSpanning=no
WizardStyle=modern
SetupIconFile={#PayloadDir}\_internal\resources\icon.ico
UninstallDisplayIcon={app}\Reels Maker.exe
UninstallDisplayName=Reels Maker
VersionInfoVersion=1.1.2.0
VersionInfoDescription=Reels Maker Setup
VersionInfoProductName=Reels Maker
VersionInfoProductVersion=1.1.2
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
CreateUninstallRegKey=RegisterUninstall
UsePreviousAppDir=RegisterUninstall
UsePreviousGroup=RegisterUninstall
UsePreviousTasks=RegisterUninstall
InfoBeforeFile={#PayloadDir}\INSTALL-NOTES.txt

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Reels Maker"; Filename: "{app}\Reels Maker.exe"; WorkingDir: "{app}"
Name: "{autodesktop}\Reels Maker"; Filename: "{app}\Reels Maker.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Reels Maker.exe"; Description: "{cm:LaunchProgram,Reels Maker}"; Flags: nowait postinstall skipifsilent

[Code]
function RegisterUninstall: Boolean;
begin
  { The verification environment does not allow registry access. Normal installs
    still register their uninstaller; isolated smoke tests only write files. }
  Result := ExpandConstant('{param:ISOLATEDTEST|0}') <> '1';
end;

#ifndef AppVersion
  #define AppVersion "0.1.3"
#endif

#define AppName "Mixput"
#define AppPublisher "K3NYEL"
#define AppExeName "mixput.exe"

[Setup]
AppId={{A6A3C9D8-12E7-4F3A-9D2D-7B0A4C2E61F5}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\Mixput
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist\packages
OutputBaseFilename=Mixput-Setup-v{#AppVersion}-windows-x64
SetupIconFile=..\..\public\assets\mixput.ico
UninstallDisplayIcon={app}\{#AppExeName}
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
PrivilegesRequired=admin
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
#ifdef SignTool
SignTool=SignTool
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\..\dist\mixput.exe"; DestDir: "{app}"; DestName: "{#AppExeName}"; Flags: ignoreversion
Source: "..\..\public\assets\mixput-ico.png"; DestDir: "{app}\assets"; Flags: ignoreversion

[Icons]
Name: "{group}\Mixput"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"
Name: "{autodesktop}\Mixput"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch Mixput"; Flags: postinstall nowait skipifsilent

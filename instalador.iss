; Instalador do Tradutor Runeteria (Inno Setup 6). Gerado pelo build.bat:
;   ISCC /DAppVersion=1.0.0 instalador.iss   ->   dist\TradutorRuneteria-Instalar.exe
; Instala so para o usuario atual (nao pede administrador) e abre o programa no final.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "Tradutor Runeteria"
#define AppExe "TradutorRuneteria.exe"

[Setup]
AppId={{B6E1D2A4-6F0B-4C55-9A0E-7A3D5C1F2E90}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Toshi
AppPublisherURL=https://github.com/Toshiharo/tradutor-runeteria
DefaultDirName={localappdata}\Programs\TradutorRuneteria
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; o minimo de telas: sem escolher pasta, sem grupo de menu, sem tela de "pronto para instalar"
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
DisableWelcomePage=yes
WizardStyle=modern
SetupIconFile=app\icone.ico
WizardSmallImageFile=tools\instalador_logo.bmp
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
OutputDir=dist
OutputBaseFilename=TradutorRuneteria-Instalar
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"
Name: "autostart"; Description: "Abrir junto com o jogo (fica esperando, sem janela, e aparece quando o Hytale abrir)"; Flags: unchecked

[Files]
Source: "dist\TradutorRuneteria\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; mesmo valor que a opcao "Abrir junto com o jogo" do programa grava (winutil.set_autostart)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "TradutorRuneteria"; ValueData: """{app}\{#AppExe}"" --com-o-jogo"; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir o {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c taskkill /im {#AppExe} /f"; Flags: runhidden; RunOnceId: "FecharApp"

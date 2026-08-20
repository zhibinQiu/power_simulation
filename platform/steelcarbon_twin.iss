; ============================================================
; 行业能碳仿真平台 - Windows 安装程序脚本 (Inno Setup 6)
; 输入：..\dist\SteelCarbonTwin\  (PyInstaller onedir 产物)
; 输出：SteelCarbonTwin-windows-x64-setup.exe（位于项目根）
; 用法（由 GitHub Actions 调用）：
;   ISCC.exe /DAppVersion=1.0.0 steelcarbon_twin.iss
; ============================================================
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6B3F0E2A-9C41-4D7E-B8A5-7D2F1C0A9E64}
AppName=SteelCarbonTwin
AppVersion={#AppVersion}
AppPublisher=SteelCarbon
AppVerName=SteelCarbonTwin {#AppVersion}
DefaultDirName={autopf}\SteelCarbonTwin
DefaultGroupName=SteelCarbonTwin
DisableProgramGroupPage=yes
OutputDir=..
OutputBaseFilename=SteelCarbonTwin-windows-x64-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\SteelCarbonTwin.exe
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "..\dist\SteelCarbonTwin\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\SteelCarbonTwin"; Filename: "{app}\SteelCarbonTwin.exe"
Name: "{autodesktop}\SteelCarbonTwin"; Filename: "{app}\SteelCarbonTwin.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\SteelCarbonTwin.exe"; Description: "Launch SteelCarbonTwin"; Flags: nowait postinstall skipifsilent

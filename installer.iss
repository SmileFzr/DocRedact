; DocRedact 安装包脚本（Inno Setup 6）
;
; 构建：ISCC.exe installer.iss
; 产物：release\DocRedact_v3.3_setup.exe
;
; 设计要点：
;   · PrivilegesRequired=lowest —— 免管理员，装到当前用户的 LocalAppData，
;     不需要 UAC 弹窗，也不需要管理员密码，适合分发给普通用户
;   · LZMA2 最大压缩 + 固实压缩 —— 比 zip 再小一截
;   · 卸载时保留用户处理结果（uploads/outputs），只删程序本体

#define MyAppName "DocRedact"
#define MyAppVersion "3.3"
#define MyAppPublisher "SmileFzr"
#define MyAppURL "https://github.com/SmileFzr/DocRedact"
#define MyAppExeName "DocRedact.exe"

[Setup]
AppId={{8F3A6C21-4D57-4E9B-9C1A-77B2E5D3A940}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
VersionInfoVersion={#MyAppVersion}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=release
OutputBaseFilename=DocRedact_v{#MyAppVersion}_setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} 文档隐私遮罩工具
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
DisableWelcomePage=no
AllowNoIcons=yes

[Languages]
; 官方安装包不带简中语言文件，这里用社区维护版（放在 installer\ 下，随仓库一起走）
Name: "chinese"; MessagesFile: "installer\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"; Flags: checkedonce
Name: "quicklaunchicon"; Description: "创建快速启动栏图标"; GroupDescription: "附加任务:"; Flags: unchecked
Name: "autostart"; Description: "开机自动启动（不建议，会常驻后台）"; GroupDescription: "附加任务:"; Flags: unchecked

[Files]
Source: "dist\DocRedact\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName} 文档隐私遮罩工具"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{group}\使用说明"; Filename: "{app}\使用说明.txt"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName} 文档隐私遮罩工具"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "DocRedact"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 只清理程序自己的缓存目录，用户的处理结果（uploads/outputs）保留
Type: filesandordirs; Name: "{app}\ui_data"
Type: filesandordirs; Name: "{app}\__pycache__"
Type: files; Name: "{app}\DocRedact_错误日志.txt"

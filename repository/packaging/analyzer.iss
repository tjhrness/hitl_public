[Setup]
AppId={{656AE238-F590-471B-B9EA-0CC4C7C479F3}
AppName=Inter-Rater Variability Analyzer
AppVersion=0.1.0
DefaultDirName={localappdata}\Programs\InterRaterAnalyzer
DefaultGroupName=Inter-Rater Variability Analyzer
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.22000
OutputDir=..\dist\installer
OutputBaseFilename=InterRaterAnalyzer-0.1.0-Setup
Compression=lzma2
SolidCompression=yes
UninstallDisplayIcon={app}\InterRaterAnalyzer.exe
CloseApplications=yes

[Files]
Source: "..\dist\InterRaterAnalyzer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Inter-Rater Variability Analyzer"; Filename: "{app}\InterRaterAnalyzer.exe"

; Runtime state is in {localappdata}\InterRaterAnalyzer, outside the install directory.
; Deliberately no UninstallDelete, InstallDelete, or state-directory entries.

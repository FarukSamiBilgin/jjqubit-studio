; ============================================================================
; JJQubit Studio -- Inno Setup installer script (Faz 4, Windows installer)
; ============================================================================
;
; This script wraps the PyInstaller ONE-FOLDER build produced by
; ``scripts\build_exe.py`` into a single Windows setup .exe.
;
; PREREQUISITE (IMPORTANT):
;   You MUST build the app first. From the repo root, run:
;
;       python scripts\build_exe.py --clean
;
;   That produces ``dist\JJQubitStudio\`` (the folder this installer packages).
;   If that folder does not exist, compilation of this script will FAIL with a
;   "no files found matching ...\dist\JJQubitStudio\*" error -- that is the
;   guard telling you to run the build step first.
;
; COMPILING THIS SCRIPT:
;   Install Inno Setup 6+ (https://jrsoftware.org/isdl.php), then either:
;     - Command line:  iscc scripts\installer\JJQubitStudio.iss
;     - GUI:           open this file in the Inno Setup Compiler and press F9.
;   The resulting setup .exe is written to ``Output\`` next to this script
;   (see [Setup] OutputDir below).
;
; VERSION SYNC:
;   ``MyAppVersion`` below must be kept in sync with ``APP_VERSION`` in
;   ``gui\app.py`` (currently "0.1.0"). There is no build-time coupling between
;   the two -- update both together when you cut a release.
; ============================================================================

; --- Defines --------------------------------------------------------------
; APP_NAME    from gui/app.py:  APP_NAME    = "JJQubit Studio"
; APP_VERSION from gui/app.py:  APP_VERSION = "0.1.0"
; Exe name    from scripts/build_exe.py / JJQubitStudio.spec: JJQubitStudio.exe
#define MyAppName "JJQubit Studio"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "JJQubit Studio"
#define MyAppExeName "JJQubitStudio.exe"

; Source folder that build_exe.py produces (relative to this .iss file).
; scripts\installer\  ->  ..\..  ->  repo root  ->  dist\JJQubitStudio
#define MyAppSourceDir "..\..\dist\JJQubitStudio"

[Setup]
; AppId uniquely identifies this application for install/upgrade/uninstall.
; Keep this GUID STABLE across releases -- changing it makes Windows treat a
; new version as a separate product instead of an upgrade.
AppId={{C9058143-64FB-4EDD-9DE9-29271EC0E8CD}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Default install location: Program Files (64-bit on x64 Windows).
DefaultDirName={autopf}\JJQubit Studio
DefaultGroupName={#MyAppName}
; Allow the user to change the Start Menu group; default is the app name.
AllowNoIcons=yes
; Modern setup wizard style.
WizardStyle=modern
; The app is 64-bit; install in 64-bit mode and target x64 machines only.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Compress the payload.
Compression=lzma2
SolidCompression=yes
; Where the compiled setup .exe is written, and its file name.
OutputDir=Output
OutputBaseFilename=JJQubitStudioSetup-{#MyAppVersion}
; Installing into Program Files requires elevation; request it up front.
PrivilegesRequired=admin
; Show the app version on the wizard.
VersionInfoVersion={#MyAppVersion}
; NOTE: No LicenseFile is set because the repository has no LICENSE file.
; If a LICENSE file is added at the repo root, add (adjusting the path):
;   LicenseFile=..\..\LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Optional desktop shortcut, unchecked by default (Inno's usual convention).
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Package the ENTIRE one-folder PyInstaller build: the exe plus its _internal
; directory (Qt plugins, scientific-package data, bundled examples, etc.).
; recursesubdirs + createallsubdirs preserves the whole tree under _internal.
Source: "{#MyAppSourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
; Start Menu shortcut to the app.
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
; Start Menu uninstaller entry.
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
; Optional desktop shortcut (created only if the "desktopicon" task is chosen).
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Offer to launch the app when setup finishes (skipped in silent installs).
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

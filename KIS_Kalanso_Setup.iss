; ============================================================================
; KIS Kalanso — script Inno Setup (installateur Windows)
; ----------------------------------------------------------------------------
; Compile le dossier déjà généré par PyInstaller (dist\KIS_Kalanso_Alpha\,
; voir KIS_Kalanso_Alpha_FIX12.spec) en un programme d'installation classique
; (raccourcis Bureau/Menu Démarrer, désinstalleur listé dans "Programmes").
;
; Prérequis avant de compiler ce script :
;   1) Avoir déjà généré le dossier dist\KIS_Kalanso_Alpha\ avec PyInstaller.
;   2) Avoir Inno Setup installé (https://jrsoftware.org/isinfo.php).
;
; Compilation : ouvrir ce fichier avec Inno Setup (clic droit > "Compile"),
; ou en ligne de commande :
;   "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" KIS_Kalanso_Setup.iss
;
; Le programme d'installation généré est déposé dans .\installer\.
; ============================================================================

#define MyAppName "KIS Kalanso"
#define MyAppVersion "MVP Alpha V1"
#define MyAppPublisher "KIS Solutions"
#define MyAppExeName "KIS_Kalanso_Alpha.exe"
#define MyAppIcon "static\images\app_icon.ico"

[Setup]
; Identifiant unique et stable de l'application : NE JAMAIS le changer d'une
; version à l'autre (sinon Windows considère qu'il s'agit d'un autre logiciel
; et ne propose plus de mise à jour propre par-dessus une version déjà installée).
AppId={{5C9E9C9A-6E7B-4C7E-9C36-8E6C4E7C4C1B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#MyAppExeName}
; Le programme écrit ses données (base SQLite, médias) dans %PROGRAMDATA%,
; qui est déjà accessible sans droits administrateur particuliers ; seule
; l'installation dans Program Files nécessite les droits administrateur.
PrivilegesRequired=admin
OutputDir=installer
OutputBaseFilename=KIS_Kalanso_Setup_MVP_Alpha_V1
SetupIconFile={#MyAppIcon}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer une icône sur le Bureau"; GroupDescription: "Icônes supplémentaires :"

[Files]
; Tout le dossier produit par PyInstaller en mode onedir (exe + _internal).
; Le mode onedir évite la décompression de ~90 Mo dans %TEMP% à chaque
; lancement : c'était la principale cause de lenteur au démarrage.
Source: "dist\KIS_Kalanso_Alpha\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Désinstaller {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
; Réseau local (mode serveur) : autorise les autres postes de l'école à joindre
; KIS Kalanso sur ce poste (réseaux privés et de domaine uniquement, jamais
; les réseaux publics). Sans effet tant que le mode serveur n'est pas activé.
; Les règles déjà présentes pour l'exécutable sont d'abord supprimées, y compris un
; éventuel blocage créé par Windows si quelqu'un a refusé l'alerte du pare-feu.
; La règle vaut pour tous les profils (un Wi-Fi d'école est souvent classé « Public »)
; mais uniquement pour les appareils du même réseau local (remoteip=localsubnet).
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=all program=""{app}\{#MyAppExeName}"""; Flags: runhidden; StatusMsg: "Configuration du pare-feu..."
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""KIS Kalanso"""; Flags: runhidden
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall add rule name=""KIS Kalanso"" dir=in action=allow program=""{app}\{#MyAppExeName}"" enable=yes profile=any remoteip=localsubnet protocol=tcp"; Flags: runhidden
Filename: "{app}\{#MyAppExeName}"; Description: "Lancer {#MyAppName} maintenant"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\netsh.exe"; Parameters: "advfirewall firewall delete rule name=""KIS Kalanso"""; Flags: runhidden; RunOnceId: "KISFirewall"

[UninstallDelete]
; Nettoie uniquement le dossier d'installation (l'exécutable). Les données de
; l'établissement (%PROGRAMDATA%\KIS Kalanso\data — base SQLite, médias,
; licence) ne sont PAS supprimées automatiquement : un utilisateur qui
; désinstalle puis réinstalle ne doit pas perdre ses données par accident.
; Pour un nettoyage complet manuel (ex. réinitialiser une machine de test),
; supprimer à la main : %PROGRAMDATA%\KIS Kalanso et %APPDATA%\KIS Kalanso.
Type: filesandordirs; Name: "{app}"

; Installatore di Pressmark per Windows (Inno Setup 6). Lo compila confezione/costruisci.py, che prima prepara la
; cartella confezione/uscita/Pressmark e passa Versione e VersioneNumerica:
;   ISCC /DVersione=2026.11.01+e21b46b /DVersioneNumerica=2026.11.01 /DCartella=<cartella> /O<uscita> pressmark.iss
;
; Installa per il solo utente, senza amministratore, in %LOCALAPPDATA%\Programs\Pressmark. Le scelte e i progetti
; dell'utente stanno altrove (%APPDATA%\Pressmark, Documenti\Pressmark): un aggiornamento o una disinstallazione
; non li toccano.

#ifndef Versione
  #define Versione "0.0.0"
#endif
#ifndef Cartella
  #define Cartella "uscita\Pressmark"
#endif
#ifndef VersioneNumerica
  #define VersioneNumerica "0.0.0"
#endif

[Setup]
AppId={{6C1F3A52-8E0B-4C55-9B57-0A1D2E7C4F11}
AppName=Pressmark
AppVersion={#Versione}
AppVerName=Pressmark {#Versione}
AppPublisher=Ivan Masci
VersionInfoVersion={#VersioneNumerica}
DefaultDirName={localappdata}\Programs\Pressmark
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile={#Cartella}\docs\LICENSE
OutputBaseFilename=Pressmark-{#VersioneNumerica}-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName=Pressmark
SetupIconFile={#Cartella}\assets\pressmark.ico
UninstallDisplayIcon={app}\assets\pressmark.ico

[Languages]
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
it.Collegamento=Un collegamento sul desktop
en.Collegamento=A desktop shortcut
it.Apri=Apri Pressmark
en.Apri=Open Pressmark

[Tasks]
Name: "desktop"; Description: "{cm:Collegamento}"; Flags: unchecked

[InstallDelete]
; il codice e il Python di una versione precedente si sostituiscono per intero (niente moduli rimasti da prima);
; le lingue OCR scaricate in tesseract\tessdata restano
Type: filesandordirs; Name: "{app}\scripts"
Type: filesandordirs; Name: "{app}\python"
; i collegamenti col nome di prima (AIrchivist). Lo stesso AppId fa aggiornare una versione precedente nella sua
; cartella (%LOCALAPPDATA%\Programs\AIrchivist), quindi l'installazione resta una sola
Type: files; Name: "{userprograms}\AIrchivist.lnk"
Type: files; Name: "{userdesktop}\AIrchivist.lnk"

[Files]
Source: "{#Cartella}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{userprograms}\Pressmark"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\scripts\app.py"""; WorkingDir: "{app}\scripts"; IconFilename: "{app}\assets\pressmark.ico"; Comment: "Ricerca nelle fonti primarie"
Name: "{userdesktop}\Pressmark"; Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\scripts\app.py"""; WorkingDir: "{app}\scripts"; IconFilename: "{app}\assets\pressmark.ico"; Tasks: desktop

[Run]
Filename: "{app}\python\pythonw.exe"; Parameters: """{app}\scripts\app.py"""; WorkingDir: "{app}\scripts"; Description: "{cm:Apri}"; Flags: postinstall nowait skipifsilent

[UninstallDelete]
; file creati dopo l'installazione: cache dei moduli e lingue OCR scaricate
Type: filesandordirs; Name: "{app}\scripts"
Type: filesandordirs; Name: "{app}\python"
Type: filesandordirs; Name: "{app}\tesseract"

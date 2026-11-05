; Installatore di Pressmark per Windows (Inno Setup 6). Lo compila confezione/costruisci.py, che prima prepara la
; cartella confezione/uscita/Pressmark e passa Versione e VersioneNumerica:
;   ISCC /DVersione=2026.11.01+e21b46b /DVersioneNumerica=2026.11.01 /DCartella=<cartella> /O<uscita> pressmark.iss
;
; Installa per il solo utente, senza amministratore, in %LOCALAPPDATA%\Programs\Pressmark. Le scelte e i progetti
; dell'utente stanno altrove (%APPDATA%\Pressmark, Documenti\Pressmark): un aggiornamento non li tocca; la
; disinstallazione chiede se togliere le impostazioni e le chiavi salvate da Pressmark (i progetti restano sempre).

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
it.TogliDati=Rimuovere anche le impostazioni di Pressmark (configurazione e profili dei modelli) e le chiavi dei servizi che Pressmark ha salvato tra le variabili del tuo utente?%n%nI progetti in Documenti\Pressmark restano in ogni caso.
en.TogliDati=Also remove Pressmark's settings (configuration and model profiles) and the service keys Pressmark saved in your user environment variables?%n%nProjects in Documents\Pressmark are kept either way.

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

[Code]
// Su richiesta, la disinstallazione toglie anche i dati dell'utente in %APPDATA%\Pressmark e le variabili
// d'ambiente elencate in variabili_salvate.txt (installa.ricorda_variabile): solo quelle salvate da Pressmark, non
// chiavi con lo stesso nome impostate da altri programmi prima. I progetti (Documenti\Pressmark) non si toccano.
// Senza domanda (disinstallazione silenziosa) i dati restano.
const
  WM_SETTINGCHANGE = $001A;
  SMTO_ABORTIFHUNG = $0002;

function SendMessageTimeout(hWnd: HWND; Msg: UINT; wParam: Longint; lParam: String; fuFlags, uTimeout: UINT;
  var lpdwResult: DWORD): Longint;
  external 'SendMessageTimeoutW@user32.dll stdcall';

procedure TogliDatiUtente();
var
  Cartella: String;
  Nomi: TArrayOfString;
  I: Integer;
  Nome: String;
  Esito: DWORD;
begin
  Cartella := ExpandConstant('{userappdata}\Pressmark');
  if LoadStringsFromFile(Cartella + '\variabili_salvate.txt', Nomi) then
  begin
    for I := 0 to GetArrayLength(Nomi) - 1 do
    begin
      Nome := Trim(Nomi[I]);
      if Nome <> '' then
        RegDeleteValue(HKEY_CURRENT_USER, 'Environment', Nome);
    end;
    // i programmi aperti da adesso (Esplora risorse compreso) vedono le variabili senza le chiavi tolte
    SendMessageTimeout(HWND_BROADCAST, WM_SETTINGCHANGE, 0, 'Environment', SMTO_ABORTIFHUNG, 5000, Esito);
  end;
  DelTree(Cartella, True, True, True);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent then
    if MsgBox(CustomMessage('TogliDati'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      TogliDatiUtente();
end;

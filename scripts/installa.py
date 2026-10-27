#!/usr/bin/env python3
"""
Installazione e controllo dell'ambiente (lavoro 15, fase 4).

Il motore è la cartella scripts: si scarica (git clone o archivio .zip) e si usa dove sta, con config.ini accanto
al codice. I requisiti si installano nel sistema, mai dentro la cartella del progetto.

Uso (nella cartella scripts):
  python installa.py                    controlla l'ambiente (come «controlla»)
  python installa.py controlla          Python, SQLite FTS5, librerie, Tesseract e lingue, modelli, progetto
  python installa.py librerie           installa nel Python di sistema le librerie facoltative (requirements.txt)
  python installa.py client [nome]      configurazione del server MCP per un client: jan, claude, lmstudio, json
      client <nome> --scrivi [--si]       aggiunge la voce al file di configurazione del client (claude, lmstudio,
                                          jan): copia di sicurezza prima, modifiche mostrate e conferma; senza
                                          --scrivi mostra solo che cosa cambierebbe
      client --verifica                  avvia il server come lo avvierebbe il client e controlla handshake MCP
                                         ed elenco degli strumenti
  python installa.py modello [azione]   profili dei modelli che leggono i passaggi (lavoro 26):
      nuovo                         procedura guidata per un profilo nuovo (azione predefinita)
      elenca                        profili, quelli in uso, chiavi presenti
      usa <profilo> [--ruolo R] [--progetto]
                                    sceglie il profilo, solo se la prova di collegamento riesce; il cambio si
                                    annota in system/model_changes.csv del progetto
      prova <profilo>               prova di collegamento con una richiesta minima
      togli <profilo> [--si]        toglie un profilo non in uso
      converti [--si]               trasforma in profili la configurazione precedente di config.ini
  python installa.py inizia [--passi N,...] [--saltati N,...] [--si] [--rapido]
                                    avvio guidato per chi installa per la prima volta (lavoro 28):
                                    1 ambiente, 2 modello, 3 primo progetto, 4 chat, 5 riepilogo.
                                    Si interrompe e riprende senza rifare i passi già completati; ogni passo
                                    si può saltare (--saltati 2,4). Con --si i passi automatici non chiedono
                                    conferma (la scelta del modello resta comunque interattiva)

Esito di «controlla»: 0 se i requisiti necessari ci sono, 1 se ne manca almeno uno. I facoltativi (PyMuPDF,
Tesseract, PaddleOCR) servono solo a importare nuove fonti.
"""
import argparse
import codecs
import configparser
import csv
import datetime as dt
import getpass
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
REQUISITI = CARTELLA.parent / "requirements.txt"
PYTHON_MINIMO = (3, 10)
NOME_SERVER = "airchivist"


class Esito:
    """Righe del controllo: ok, manca (necessario), facoltativo (manca ma non blocca), info."""
    SEGNI = {"ok": "  ok ", "manca": "MANCA", "facoltativo": "  -- ", "info": "     "}

    def __init__(self, stampa=print):
        self.stampa, self.mancanti = stampa, []

    def __call__(self, stato, voce, dettaglio=""):
        if stato == "manca":
            self.mancanti.append(voce)
        self.stampa(f"[{self.SEGNI[stato]}] {voce}" + (f": {dettaglio}" if dettaglio else ""))


# ---------------------------------------------------------------- controlli
def controlla_python(esito):
    v = sys.version_info
    testo = f"{v.major}.{v.minor}.{v.micro} ({sys.executable})"
    if (v.major, v.minor) >= PYTHON_MINIMO:
        esito("ok", "Python", testo)
    else:
        esito("manca", "Python", f"{testo}; serve {'.'.join(map(str, PYTHON_MINIMO))} o successivo")
    if not (os.environ.get("PYTHONUTF8") == "1" or sys.flags.utf8_mode):
        esito("info", "PYTHONUTF8", "non impostata: nei client MCP aggiungi la variabile PYTHONUTF8=1 "
                                    "(la configurazione di «installa.py client» la contiene già)")


def controlla_sqlite(esito):
    try:
        con = sqlite3.connect(":memory:")
        con.execute("CREATE VIRTUAL TABLE t USING fts5(x)")
        con.close()
        esito("ok", "SQLite con FTS5", sqlite3.sqlite_version)
    except sqlite3.Error as e:
        esito("manca", "SQLite con FTS5", f"{sqlite3.sqlite_version}, FTS5 non disponibile ({e}); "
                                          "usa il Python di python.org, che lo include")


def controlla_pymupdf(esito):
    try:
        from importa import carica_pymupdf
        m = carica_pymupdf()
        esito("ok", "PyMuPDF", f"{getattr(m, 'VersionBind', '?')} (importazione dei PDF)")
    except ImportError:
        esito("facoltativo", "PyMuPDF", "non installato; serve solo a importare PDF: python installa.py librerie")


def lingue_progetto():
    """Codici Tesseract delle lingue delle serie del progetto in uso (series.ini)."""
    import profili
    from importa import LINGUE_OCR
    lingue = {p.get("lingua", "").strip() for p in profili.tutti(ricarica=True).values()}
    return {l: LINGUE_OCR[l] for l in sorted(lingue) if l in LINGUE_OCR}


def controlla_tesseract(esito, cfg):
    from importa import cartella_modelli, cerca_tesseract, come_installare_tesseract, lingue_installate
    exe = cerca_tesseract(cfg)
    if not exe:
        esito("facoltativo", "Tesseract", "non trovato; serve solo a importare scansioni: "
                                          + come_installare_tesseract())
        return
    try:
        r = subprocess.run([exe, "--version"], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        versione = (r.stdout + r.stderr).decode("utf-8", "replace").splitlines()[0].strip()
        installate = lingue_installate(exe, cartella_modelli(cfg))
    except OSError as e:
        esito("facoltativo", "Tesseract", f"{exe} non avviabile ({e})")
        return
    esito("ok", "Tesseract", f"{versione} ({exe})")
    esito("info", "lingue installate", ", ".join(sorted(installate)) or "nessuna")
    try:
        servono = lingue_progetto()
    except Exception as e:                      # series.ini illeggibile: lo segnala progetto.py
        esito("info", "lingue delle serie", f"non lette ({e})")
        return
    assenti = {l: c for l, c in servono.items() if c not in installate}
    if assenti:
        esito("facoltativo", "lingue OCR delle serie",
              "mancano " + ", ".join(f"{c} ({l})" for l, c in assenti.items()) +
              ": riesegui l'installazione di Tesseract e spunta le lingue, oppure copia <lingua>.traineddata "
              "da https://github.com/tesseract-ocr/tessdata_best nella cartella tessdata")
    elif servono:
        esito("ok", "lingue OCR delle serie", ", ".join(sorted(set(servono.values()))))


def controlla_paddle(esito, cfg):
    from motori_ocr import Paddle
    p = Paddle(cfg, "zh")
    if p.disponibile():
        esito("ok", "PaddleOCR", f"{p.versione} ({' '.join(p.python)})")
    else:
        esito("facoltativo", "PaddleOCR", f"{p.motivo}; serve solo come motore OCR alternativo (prova_ocr.py)")


def controlla_servizio(esito, voce, p):
    """Un profilo di modello: chiave presente e servizio raggiungibile (senza richieste al modello)."""
    servizio = p.get("servizio", "").strip().lower()
    nome_env = p.get("chiave_env", "").strip() or ("ANTHROPIC_API_KEY" if servizio == "anthropic" else "")
    chiave = os.environ.get(nome_env, "") if nome_env else ""
    if nome_env and not chiave:
        esito("manca", voce, f"variabile {nome_env} assente ({come_salvare_variabile(nome_env)})")
        return
    if servizio == "anthropic":
        esito("ok", voce, f"chiave {nome_env} presente")
        return
    if servizio == "ollama":
        url = (p.get("url", "") or "http://localhost:11434").rstrip("/") + "/api/tags"
        intestazioni = {}
    else:
        url = p.get("url", "").rstrip("/") + "/models"
        intestazioni = {"Authorization": f"Bearer {chiave}"} if chiave else {}
    intestazioni["User-Agent"] = "ricerca-fonti/1.0"
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers=intestazioni), timeout=10).close()
        esito("ok", voce, f"{url} risponde")
    except urllib.error.HTTPError as e:
        motivo = "chiave rifiutata" if e.code in (401, 403) else f"errore HTTP {e.code}"
        e.close()
        esito("manca", voce, f"{url}: {motivo}")
    except Exception:
        avvio = {"router": "avvia FreeLLMAPI", "ollama": "avvia Ollama"}.get(servizio, "controlla l'indirizzo")
        esito("manca", voce, f"{url} non risponde: {avvio} e riprova")


def controlla_modelli(esito, cfg):
    """Profili di modello scelti per i tre ruoli (o servizio della configurazione precedente)."""
    from llm import RUOLI, ErroreModello, profilo, usa_profili
    usati = {}
    try:
        for r in RUOLI:
            nome, p = profilo(cfg, r)
            usati.setdefault(nome, (p, []))[1].append(r)
    except ErroreModello as e:
        esito("manca", "modelli", str(e))
        return
    if not usa_profili(cfg):
        p = next(iter(usati.values()))[0]
        controlla_servizio(esito, f"modelli: {p['servizio']}", p)
        esito("info", "profili di modello", "nessuno scelto, vale la configurazione precedente di config.ini; "
                                            "per convertirla: python installa.py modello converti")
        return
    for nome, (p, ruoli) in usati.items():
        controlla_servizio(esito, f"modelli: {nome}", p)
        esito("info", f"  {nome}", f"{p.get('modello', '')} ({p.get('servizio', '')}) per " + ", ".join(ruoli))


def controlla_progetto(esito, cfg):
    from progetto import VARIABILE, cartella_scelta, nome, percorso
    radice = cartella_scelta(cfg)
    if radice is None:
        esito("manca", "progetto", f"nessun progetto scelto: crea un progetto con python progetto.py nuovo "
                                   f"<cartella> e sceglilo in config.ini ([progetto] cartella) o con {VARIABILE}")
        return
    esito("ok", "progetto", f"{nome(cfg)} ({radice})")
    for chiave, necessario in (("entita", True), ("serie", True), ("dati", False), ("indice", False)):
        p = percorso(cfg, chiave)
        if p.exists():
            esito("ok", f"  {chiave}", str(p))
        elif necessario:
            esito("manca", f"  {chiave}", f"{p} non esiste: crea un progetto vuoto con python progetto.py nuovo "
                                          f"<cartella> e sceglilo in config.ini ([progetto] cartella) o con "
                                          f"{VARIABILE}")
        else:
            esito("facoltativo", f"  {chiave}", f"{p} non esiste ancora")


def cmd_controlla(args, stampa=print):
    sys.path.insert(0, str(CARTELLA))
    esito = Esito(stampa)
    stampa("Requisiti necessari")
    controlla_python(esito)
    controlla_sqlite(esito)
    cfg = leggi_cfg()
    controlla_modelli(esito, cfg)
    controlla_progetto(esito, cfg)
    stampa("\nPer importare nuove fonti (facoltativi)")
    controlla_pymupdf(esito)
    controlla_tesseract(esito, cfg)
    if not args.rapido:
        controlla_paddle(esito, cfg)
    stampa("")
    if esito.mancanti:
        stampa("Manca: " + ", ".join(v.strip() for v in esito.mancanti) + ".")
        return 1
    stampa("Requisiti necessari presenti. Collega un client con: python installa.py client")
    return 0


# ---------------------------------------------------------------- librerie
def cmd_librerie(args, stampa=print):
    if not REQUISITI.exists():
        stampa(f"Manca {REQUISITI}.")
        return 1
    cmd = [sys.executable, "-m", "pip", "install", "-r", str(REQUISITI)]
    stampa("Installo nel Python di sistema: " + " ".join(cmd))
    esito = subprocess.run(cmd).returncode
    if esito and sys.platform.startswith("linux"):
        stampa("Se pip ha rifiutato con «externally-managed-environment», installa PyMuPDF dai pacchetti della "
               "distribuzione (Debian e Ubuntu: sudo apt install python3-fitz).")
    return esito


# ---------------------------------------------------------------- client MCP (lavoro 27)
def voce_server():
    return {"command": sys.executable, "args": [str(CARTELLA / "mcp_server.py")], "env": {"PYTHONUTF8": "1"}}


def cartella_dati():
    """Cartella dei dati dell'applicazione per l'utente, sui tre sistemi (Windows APPDATA, macOS Application
    Support, Linux ~/.config o XDG_CONFIG_HOME)."""
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    return Path(xdg) if xdg else Path.home() / ".config"


# nomi con cui i client indicano il nostro server nelle loro configurazioni esistenti
ALIAS_CLIENT = {"claude": ("airchivist", "AIrchivist", "Pipeline"),
                "lmstudio": ("airchivist", "AIrchivist", "Pipeline"),
                "jan": ("airchivist", "AIrchivist", "Pipeline")}


def file_client(nome, dati=None):
    """Percorso del file di configurazione del client sul sistema in uso. Per Jan è il file dove il programma
    tiene i server MCP e le loro impostazioni (mcp_config.json: «mcpServers» e «mcpSettings»), che «--scrivi»
    aggiorna quando Jan è chiuso; per «json» non c'è un file: serve solo a stampare il blocco."""
    dati = cartella_dati() if dati is None else Path(dati)
    if nome == "claude":
        return dati / "Claude" / "claude_desktop_config.json"
    if nome == "lmstudio":
        return Path(os.environ.get("LMSTUDIO_DIR", Path.home() / ".lmstudio")) / "mcp.json"
    if nome == "jan":
        return dati / "Jan" / "data" / "mcp_config.json"
    return None


# Jan (verificato il 26/10/2026 su un'installazione reale): i server stanno in mcp_config.json, «mcpServers»,
# ciascuno con «active» (spento se manca) e «type»; le impostazioni MCP in «mcpSettings» dello stesso file; la
# ricerca web in settings.json, voce «setting-web-search» (testo JSON: state.webSearchEnabled). Jan riscrive i
# file quando si chiude: vanno modificati a Jan chiuso.
IMPOSTAZIONI_JAN = (
    ("toolCallTimeoutSeconds", lambda v: isinstance(v, (int, float)) and v >= 90, 90,
     "timeout degli strumenti almeno 90 secondi (la ricerca attende fino a 75 secondi per chiamata)"),
    ("enableSmartToolRouting", lambda v: v is False, False,
     "smart routing disattivato (sceglierebbe da sé quali strumenti mostrare al modello)"),
    ("maxToolOutputChars", lambda v: isinstance(v, (int, float)) and v >= 8000, 8000,
     "risultati degli strumenti fino a 8000 caratteri (il server resta sotto [mcp] max_caratteri)"),
)


def passaggi_manuali_jan(stampa):
    """Stampa che cosa serve in Jan oltre alla voce del server, e dove sta (senza --scrivi lo si fa a mano)."""
    stampa("In Jan servono anche (con --scrivi li sistemo io nei file, a Jan chiuso):")
    for _, _, valore, spiegazione in IMPOSTAZIONI_JAN:
        stampa(f"  - {spiegazione}")
    stampa("  - Web Search disattivato, così le risposte vengono solo dalle fonti")
    stampa("  (interfaccia: Settings > MCP Servers e Settings > Web Search; file: mcp_config.json, «mcpSettings», "
           "e settings.json)")


def impostazioni_jan(doc):
    """Porta «mcpSettings» di mcp_config.json ai valori che servono; restituisce le descrizioni delle modifiche."""
    imp = doc.get("mcpSettings")
    if imp is not None and not isinstance(imp, dict):
        return ["«mcpSettings» non è un oggetto: le impostazioni di Jan restano da cambiare a mano"]
    if imp is None:
        imp = doc["mcpSettings"] = {}
    modifiche = []
    for chiave, va_bene, valore, spiegazione in IMPOSTAZIONI_JAN:
        if not va_bene(imp.get(chiave)):
            modifiche.append(f"~ mcpSettings.{chiave}: {imp.get(chiave, '(assente)')} -> {valore} ({spiegazione})")
            imp[chiave] = valore
    return modifiche


def ricerca_web_jan(f):
    """(documento di settings.json con la ricerca web spenta, descrizione) se in Jan è accesa; (None, None)
    se è già spenta o il file non c'è o non ha la forma attesa (allora lo si fa a mano)."""
    if not f.exists():
        return None, None
    try:
        doc = json.loads(_leggi_testo(f)[0])
        stato = json.loads(doc["setting-web-search"])
        attiva = stato["state"]["webSearchEnabled"]
    except (ValueError, KeyError, TypeError):
        return None, None
    if attiva is not True:
        return None, None
    stato["state"]["webSearchEnabled"] = False
    doc["setting-web-search"] = json.dumps(stato, ensure_ascii=False, separators=(",", ":"))
    return doc, "~ settings.json, Web Search: attiva -> disattivata (le risposte vengono solo dalle fonti)"


def in_esecuzione(nome):
    """Vero se il programma del client è aperto (solo Jan: alla chiusura riscrive i suoi file)."""
    if nome != "jan":
        return False
    try:
        if os.name == "nt":
            r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Jan.exe", "/NH"], capture_output=True, text=True,
                               errors="replace", creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return "jan.exe" in r.stdout.lower()
        return subprocess.run(["pgrep", "-xi", "jan"], capture_output=True).returncode == 0
    except OSError:
        return False


def conferma_domanda(testo, chiedi):
    """Domanda di conferma: «testo [S/n] » risponde sì anche a vuoto, «testo [s/N] » no a vuoto.
    Se non c'è nessuno da interrogare (tastiera assente o pipe chiusa: EOFError) la risposta è «no»,
    così --scrivi senza --si in modalità non interattiva non scrive nulla invece di interrompersi."""
    m = re.search(r"\[(s[Nn])\]\s*$", testo)
    default = m and m.group(1) == "sN"
    try:
        r = chiedi(testo).strip().lower()
    except EOFError:
        return False
    if not r:
        return not default
    return r in ("s", "si", "sì", "y", "yes")


def unisci_voci(client, esistente, nome_server, voce):
    """Restituisce (documento aggiornato, descrizioni delle modifiche, già_presente). Tocca solo la voce del
    nostro server — individuata anche col nome usato in precedenza («Pipeline») — e lascia invariate tutte le
    altre. «esistente» deve essere un oggetto JSON (dict) o None per un file nuovo; se la forma non è valida
    restituisce documento None, così il comando rifiuta di scrivere."""
    if esistente is None:
        esistente = {}
    if not isinstance(esistente, dict):
        return None, ["il file non è un oggetto JSON valido: non scrivo nulla"], False
    doc = json.loads(json.dumps(esistente))               # copia: non tocchiamo l'oggetto ricevuto
    chiavi = ("mcpServers", "servers")                    # Jan, Claude Desktop e LM Studio usano «mcpServers»
    sezione = next((k for k in chiavi if isinstance(doc.get(k), dict)), None)
    if sezione is None:
        for k in chiavi:                                  # una chiave presente ma malformata blocca la scrittura
            if k in doc:
                return None, [f"«{k}» nel file non è un elenco di server: non scrivo nulla"], False
        sezione = chiavi[0]
        doc[sezione] = {}
    servers = doc[sezione]
    vecchio_nome = next((n for n in ALIAS_CLIENT.get(client, (nome_server,)) if n in servers), None)
    vecchio = servers.get(vecchio_nome) if vecchio_nome else None
    # le voci proprie del client restano (Jan: «type», «active»); per Jan il server va acceso
    nuova = {**{k: v for k, v in (vecchio or {}).items() if k not in ("command", "args", "env")}, **voce}
    if client == "jan":
        nuova.update(active=True, type=nuova.get("type", "stdio"))
    if vecchio is not None and vecchio == nuova:
        return doc, [f"la voce «{vecchio_nome}» è già esattamente questa"], True
    if vecchio is None:
        servers[nome_server] = nuova
        return doc, [f"+ «{nome_server}» ({sezione}): avvierà il server MCP",
                     "- nessuna altra voce viene toccata"], False
    # il nome che l'utente ha dato alla voce resta: cambia solo il contenuto
    servers[vecchio_nome] = nuova
    altri = ", ".join(str(a) for a in (vecchio.get("args") or [])) or "(nessun argomento)"
    mod = [f"~ «{vecchio_nome}» aggiornata: prima command {vecchio.get('command')} | args {altri}"
           + (" | spenta" if client == "jan" and not vecchio.get("active") else ""),
           "- nessuna altra voce viene toccata"]
    return doc, mod, False


def scrivi_file_client(f, doc):
    """Scrive il file JSON con copia di sicurezza «<file>.airchivist-<data>.bak» accanto all'originale."""
    _, bom, fine_riga = _leggi_testo(f)
    testo = json.dumps(doc, ensure_ascii=False, indent=2) + fine_riga
    if f.exists():
        copia = f.with_name(f"{f.name}.airchivist-{dt.date.today().isoformat()}.bak")
        shutil.copyfile(f, copia)
        yield f"copia di sicurezza: {copia}"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(((chr(0xFEFF) if bom else "") + testo).encode("utf-8"))
    yield f"scritto: {f}"


def cmd_client_scrivi(args, stampa, chiedi=input, nome_server=None):
    """`installa.py client <claude|lmstudio|jan> --scrivi`: trova il file, prepara la modifica, la mostra e
    scrive solo dopo conferma. Con `--verifica` in più fa anche la prova del collegamento."""
    nome = args.nome
    if nome == "json":
        stampa("«json» serve a stampare il blocco per client non riconosciuti: niente file da scrivere.")
        return 1
    f = Path(args.file) if getattr(args, "file", None) else file_client(nome)
    voce = getattr(args, "voce", None) or voce_server()
    nome_server = nome_server or NOME_SERVER
    esistente = None
    if f.exists():
        try:
            esistente = json.loads(_leggi_testo(f)[0])
        except ValueError:
            stampa(f"Il file {f} non è JSON valido: non lo tocco. Sistema a mano o sposta il file.")
            return 3
    doc, modifiche, gia = unisci_voci(nome, esistente, nome_server, voce)
    stampa(f"File di configurazione: {f} ({'esiste' if f.exists() else 'non esiste ancora'})")
    for m in modifiche:
        stampa("  " + m)
    if doc is None:
        return 3
    altri_file = []                         # (file, documento) da scrivere insieme a quello del client
    if nome == "jan":
        imp = impostazioni_jan(doc)
        f_web = Path(args.file_impostazioni) if getattr(args, "file_impostazioni", None) else f.with_name("settings.json")
        doc_web, mod_web = ricerca_web_jan(f_web)
        if doc_web is not None:
            altri_file.append((f_web, doc_web))
            imp.append(mod_web)
        for m in imp:
            stampa("  " + m)
        gia = gia and not any(m.startswith("~") for m in imp)
    if gia:
        stampa("Nessuna scrittura necessaria.")
        return client_verifica(args, stampa) if getattr(args, "verifica", False) else 0
    if not args.scrivi:
        stampa("Con --scrivi faccio io queste modifiche (copia di sicurezza prima). Ora non ho scritto nulla.")
        return 0
    if in_esecuzione(nome):
        stampa("Jan è aperto: quando si chiude riscrive i suoi file e queste modifiche andrebbero perse. Chiudi Jan "
               "(anche dall'icona accanto all'orologio) e rilancia il comando.")
        return 1
    if not args.si and not conferma_domanda("Scrivere queste modifiche? [S/n] ", chiedi):
        stampa("Annullato: il file non è cambiato.")
        return 0
    for file_, documento in [(f, doc)] + altri_file:
        for riga in scrivi_file_client(file_, documento):
            stampa("  " + riga)
    if nome == "jan":
        stampa("Apri Jan: il server AIrchivist è acceso. Le altre impostazioni dell'assistente sono nella guida "
               "(docs/user_guide.it.md, «Jan»).")
    else:
        stampa("Riavvia il client perché legga la nuova configurazione.")
    return client_verifica(args, stampa) if getattr(args, "verifica", False) else 0


def scambia_jsonrpc(proc, msg):
    """Una chiamata JSON-RPC su STDIO/STDOUT: scrive una riga, legge la risposta.
    Le notifiche (senza «id») non producono risposta: si scrive e basta, altrimenti la lettura
    della risposta blocca per sempre il controllo."""
    proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
    proc.stdin.flush()
    if "id" not in msg:
        return None
    riga = proc.stdout.readline()
    if not riga:
        raise ValueError("risposta assente (il server ha chiuso la conversazione)")
    return json.loads(riga)


STRUMENTI_ATTESI = ["guida", "schede", "esplora_nome", "cerca_testo", "ricerca", "modello", "risposte",
                   "passaggi_archivio", "copertura_fonti", "apri_fonte", "varianti", "correggi_passaggio",
                   "importa", "serie"]


def client_verifica(args, stampa, avvia=None):
    """`installa.py client --verifica`: avvia il server MCP come lo avvierebbe il client (stesso eseguibile,
    stessi argomenti, stesse variabili d'ambiente) e controlla l'handshake MCP e l'elenco degli strumenti."""
    def avvia_di_default(voce):
        env = {**os.environ, **(voce.get("env") or {})}
        return subprocess.Popen([voce["command"], *voce.get("args", [])], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                encoding="utf-8", env=env)

    voce = getattr(args, "voce", None) or voce_server()
    proc = (avvia or avvia_di_default)(voce)
    try:
        r = scambia_jsonrpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                   "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                                              "clientInfo": {"name": "installa.py", "version": "1"}}})
        if "error" in r:
            stampa(f"Handshake MCP non riuscito: {r['error'].get('message')}")
            return 1
        info = r.get("result", {}).get("serverInfo", {})
        stampa(f"Handshake MCP riuscito: server «{info.get('name')}» versione {info.get('version')}, "
               f"protocollo {r['result'].get('protocolVersion')}")
        scambia_jsonrpc(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})  # notifica: senza id
        r = scambia_jsonrpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        if "error" in r:
            stampa(f"Elenco degli strumenti non riuscito: {r['error'].get('message')}")
            return 1
        trovati = [t["name"] for t in r["result"]["tools"]]
        mancanti = [n for n in STRUMENTI_ATTESI if n not in trovati]
        stampa(f"Strumenti annunciati: {len(trovati)}"
               + (" (mancano: " + ", ".join(mancanti) + ")" if mancanti else ": tutti quelli attesi"))
        return 1 if mancanti else 0
    except (OSError, ValueError) as e:
        stampa(f"Verifica non riuscita: {e}")
        return 1
    finally:
        try:
            proc.kill()
            proc.wait(timeout=5)
        except OSError:
            pass
        for canale in (getattr(proc, "stdin", None), getattr(proc, "stdout", None)):
            try:
                canale.close()
            except (AttributeError, OSError):
                pass


def cmd_client(args, stampa=print, chiedi=input):
    if getattr(args, "verifica", False) and not getattr(args, "scrivi", False) \
            and getattr(args, "nome", "json") == "json":
        return client_verifica(args, stampa)
    if getattr(args, "scrivi", False):
        return cmd_client_scrivi(args, stampa, chiedi=chiedi)
    voce = voce_server()
    if args.nome == "jan":
        stampa("Jan: Settings > MCP Servers > + Add MCP Server (oppure: python installa.py client jan --scrivi)")
        stampa(f"  Nome:      {NOME_SERVER}")
        stampa("  Tipo:      STDIO")
        stampa(f"  Command:   {voce['command']}")
        stampa(f"  Arguments: {voce['args'][0]}")
        stampa("  Variabile d'ambiente: PYTHONUTF8 = 1")
        passaggi_manuali_jan(stampa)
        return 0
    blocco = json.dumps({"mcpServers": {NOME_SERVER: voce}}, ensure_ascii=False, indent=2)
    f = file_client(args.nome)
    if f:
        stato = "esiste: aggiungi la voce dentro «mcpServers»" if f.exists() else "non esiste ancora: crealo"
        stampa(f"File di configurazione: {f} ({stato})")
        stampa("Oppure, per scrivere io la voce (con copia di sicurezza e conferma): aggiungi --scrivi")
    stampa(blocco)
    if args.nome == "json":
        stampa("Per un client che usa HTTP invece di STDIO: python mcp_server.py --http 8765")
        stampa("Per controllare che il server risponda come lo vedrebbe il client: "
               "python installa.py client --verifica")
    stampa("Riavvia il client dopo aver salvato il file.")
    return 0


# ---------------------------------------------------------------- profili di modello (lavoro 26)
FILE_CONFIG = CARTELLA / "config.ini"
NOME_PROFILO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# servizi con una sola chiave: nome, indirizzo, variabile della chiave, modello proposto, pausa, dove si prende la chiave
SERVIZI_CHIAVE = [
    ("Groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "qwen/qwen3.8-27b", "6",
     "https://console.groq.com/keys"),
    ("Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY",
     "gemini-3.8-flash", "5", "https://aistudio.google.com/apikey"),
    ("OpenRouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "", "3.5", "https://openrouter.ai/keys"),
]


def leggi_cfg():
    from progetto import leggi_config
    return leggi_config(FILE_CONFIG)


def oggi():
    return dt.date.today().isoformat()


def copia_di_sicurezza(f):
    """Copia accanto al file (<file>.airchivist-<data>.bak, esclusa da git); None se il file non c'è."""
    if not f.exists():
        return None
    dest = f.with_name(f"{f.name}.airchivist-{oggi()}.bak")
    n = 2
    while dest.exists():
        dest = f.with_name(f"{f.name}.airchivist-{oggi()}-{n}.bak")
        n += 1
    shutil.copy2(f, dest)
    return dest


def _leggi_testo(f):
    dati = f.read_bytes() if f.exists() else b""
    testo = dati.decode("utf-8-sig")
    return testo, dati.startswith(codecs.BOM_UTF8), "\r\n" if "\r\n" in testo else "\n"


def _scrivi_testo(f, righe, bom, nl):
    f.write_bytes((("﻿" if bom else "") + nl.join(righe).rstrip() + nl).encode("utf-8"))


def _limiti_sezione(righe, sezione):
    inizio = next((i for i, r in enumerate(righe) if r.strip() == f"[{sezione}]"), None)
    if inizio is None:
        return None, None
    fine = next((i for i in range(inizio + 1, len(righe)) if righe[i].lstrip().startswith("[")), len(righe))
    return inizio, fine


VOCE_INI = re.compile(r"^\s*([^#;\s=\[][^=]*?)\s*[=:]")


def imposta_voci(f, sezione, voci):
    """Cambia o aggiunge (valore) e toglie (None) voci di una sezione di un file .ini lasciando il resto com'è:
    commenti, ordine, codifica e fine riga. Se la sezione manca si aggiunge in fondo."""
    testo, bom, nl = _leggi_testo(f)
    righe = testo.splitlines()
    inizio, fine = _limiti_sezione(righe, sezione)
    if inizio is None:
        if righe and righe[-1].strip():
            righe.append("")
        righe.append(f"[{sezione}]")
        inizio, fine = len(righe) - 1, len(righe)
    resto = {k.lower(): (k, v) for k, v in voci.items()}
    ultima = inizio
    for i in range(inizio + 1, fine):
        m = VOCE_INI.match(righe[i])
        if not m:
            continue
        ultima = i
        chiave = m.group(1).strip().lower()
        if chiave in resto:
            k, v = resto.pop(chiave)
            righe[i] = None if v is None else f"{k} = {v}"
    righe[ultima + 1:ultima + 1] = [f"{k} = {v}" for k, v in resto.values() if v is not None]
    _scrivi_testo(f, [r for r in righe if r is not None], bom, nl)


def aggiungi_profilo(f, nome, voci):
    testo, bom, nl = _leggi_testo(f)
    righe = testo.splitlines() or ["# Profili dei modelli (installa.py modello). Spiegazione delle voci: "
                                   "models_template.ini"]
    righe += ["", f"[{nome}]"] + [f"{k} = {v}" for k, v in voci.items() if v not in (None, "")]
    _scrivi_testo(f, righe, bom, nl)


def togli_profilo(f, nome):
    """Toglie la sezione con i commenti che la precedono subito; restano i commenti del profilo seguente."""
    testo, bom, nl = _leggi_testo(f)
    righe = testo.splitlines()
    inizio, fine = _limiti_sezione(righe, nome)
    if inizio is None:
        return False
    while fine > inizio + 1 and (not righe[fine - 1].strip() or righe[fine - 1].lstrip().startswith(("#", ";"))):
        fine -= 1
    while inizio > 0 and righe[inizio - 1].lstrip().startswith(("#", ";")):
        inizio -= 1
    del righe[inizio:fine]
    _scrivi_testo(f, righe, bom, nl)
    return True


def nome_proposto(p):
    """Nome breve per un profilo: servizio e ultima parte del nome del modello (groq-qwen3.8-27b)."""
    servizio, modello = p.get("servizio", ""), p.get("modello", "")
    if servizio == "router":
        etichetta = "freellmapi"
    elif servizio == "ollama":
        etichetta = "ollama"
    elif servizio == "openai":
        host = (urllib.parse.urlparse(p.get("url", "")).hostname or "").lower()
        parti = [x for x in host.split(".") if x not in ("api", "www", "com", "ai", "org", "net", "io")]
        etichetta = "gemini" if "googleapis" in host else (parti[0] if parti else "openai")
        etichetta = "locale" if etichetta in ("localhost", "127") else etichetta
    else:
        etichetta = ""
    pezzo = re.sub(r"[^a-z0-9.]+", "-", modello.split("/")[-1].lower()).strip("-.") or "modello"
    return f"{etichetta}-{pezzo}" if etichetta and not pezzo.startswith(etichetta) else pezzo


def nome_libero(nome, profili, voci=None):
    """nome, o nome-2, nome-3...: il primo che non c'è (o che c'è già con le stesse voci)."""
    candidato, n = nome, 2
    while candidato in profili and profili[candidato] != voci:
        candidato, n = f"{nome}-{n}", n + 1
    return candidato


def descrivi(p):
    return f"{p.get('modello', '?')} ({p.get('servizio', '?')}" + (f", {p['url']}" if p.get("url") else "") + ")"


def registra_cambio(cfg, cambi, dove, stampa):
    """Una riga per ruolo in system/model_changes.csv del progetto (UTF-8 con BOM, CRLF come gli altri registri)."""
    from progetto import NessunProgetto, cartella_scelta, percorso
    if not progetto_esiste(cartella_scelta(cfg)):
        return                              # nessun progetto ancora (avvio guidato): niente cartelle fantasma
    try:
        f = percorso(cfg, "cambi_modello")
    except NessunProgetto:
        return
    nuovo = not f.exists()
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a", encoding="utf-8-sig" if nuovo else "utf-8", newline="") as h:
        w = csv.writer(h, lineterminator="\r\n")
        if nuovo:
            w.writerow(["data", "ruolo", "profilo_precedente", "profilo_nuovo", "file"])
        for ruolo, prima, dopo in cambi:
            w.writerow([dt.datetime.now().strftime("%Y-%m-%d %H:%M"), ruolo, prima, dopo, dove])
    stampa(f"Cambio annotato in {f}.")


def prova_profilo(cfg, nome, stampa):
    from llm import ErroreModello, LLM
    try:
        risposto = LLM(cfg, "analisi", nome).prova()
    except ErroreModello as e:
        stampa(f"Collegamento con «{nome}» non riuscito: {str(e).rstrip('.')}.")
        return False
    stampa(f"Collegamento con «{nome}» riuscito (ha risposto {risposto}).")
    return True


def sn(chiedi, domanda, predefinito):
    """Sì/no con default; se non c'è nessuno da interrogare (tastiera assente: EOFError) vale il default."""
    try:
        r = chiedi(f"{domanda} [{'S/n' if predefinito else 's/N'}] ").strip().lower()
    except EOFError:
        return predefinito
    return predefinito if not r else r in ("s", "si", "sì", "y", "yes")


def stato_misura(p, misurati, coppie):
    """«questo profilo» se una prova misurata è stata fatta con lo stesso servizio e modello; «stesso modello,
    altro servizio» se il modello ha risposto in una prova fatta attraverso un altro servizio (un router sceglie
    il modello a ogni richiesta: per lui conta solo la prova del profilo); altrimenti «no»."""
    from sintesi import misurato
    if (p.get("servizio", ""), p.get("modello", "")) in coppie:
        return "questo profilo"
    if p.get("servizio") != "router" and misurato(p.get("modello", ""), misurati):
        return "stesso modello, altro servizio"
    return "no"


def stato_profili(cfg):
    """Profili, scelta per ruolo, chiavi e misure, come dati (per lo strumento MCP «modello»)."""
    from llm import RUOLI, ErroreModello, file_profili, leggi_profili, nome_scelto, profilo, usa_profili
    from progetto import NessunProgetto, percorso
    from sintesi import modelli_misurati, profili_misurati
    try:
        misurati = modelli_misurati(percorso(cfg, "risultati"))
        coppie = profili_misurati(percorso(cfg, "risultati"))
    except NessunProgetto:
        misurati, coppie = set(), set()
    scelti = {r: nome_scelto(cfg, r) for r in RUOLI}
    out = {"file_profili": str(file_profili(cfg)), "profili": []}
    for nome, p in leggi_profili(cfg).items():
        env = p.get("chiave_env", "") or ("ANTHROPIC_API_KEY" if p.get("servizio") == "anthropic" else "")
        voce = {"nome": nome, "servizio": p.get("servizio", ""), "modello": p.get("modello", ""),
                "chiave": ("presente" if os.environ.get(env) else "assente") if env else "non serve",
                "in_uso_per": [r for r in RUOLI if scelti[r] == nome]}
        voce["misurato"] = stato_misura(p, misurati, coppie)
        out["profili"].append(voce)
    try:
        out["in_uso"] = {r: profilo(cfg, r)[0] for r in RUOLI}
    except ErroreModello as e:
        out["errore"] = str(e)
    if not usa_profili(cfg):
        out["nota"] = ("Nessun profilo scelto: vale la configurazione precedente di config.ini "
                       "(per convertirla: python installa.py modello converti).")
    return out


def modello_elenca(args, stampa, **_):
    from llm import RUOLI, ErroreModello, file_profili, leggi_profili, nome_scelto, profilo, usa_profili
    cfg = leggi_cfg()
    profili = leggi_profili(cfg)
    misure = {v["nome"]: v["misurato"] for v in stato_profili(cfg)["profili"]}
    f = file_profili(cfg)
    if profili:
        stampa(f"Profili di modello in {f} (* = in uso):")
    else:
        stampa(f"Nessun profilo di modello ({f} non c'è o è vuoto). Crea il primo: python installa.py modello nuovo")
    scelti = {r: nome_scelto(cfg, r) for r in RUOLI}
    for nome, p in profili.items():
        ruoli = [r for r in RUOLI if scelti[r] == nome]
        env = p.get("chiave_env", "") or ("ANTHROPIC_API_KEY" if p.get("servizio") == "anthropic" else "")
        chiave = f"; chiave {env} " + ("presente" if os.environ.get(env) else "ASSENTE") if env else ""
        stampa(f"{'*' if ruoli else ' '} {nome}: {descrivi(p)}{chiave}; misurato: {misure.get(nome, 'no')}"
               + (f"  [in uso per {', '.join(ruoli)}]" if ruoli else ""))
    if not usa_profili(cfg):
        try:
            p = profilo(cfg, "analisi")[1]
            stampa(f"In uso: configurazione precedente ai profili (config.ini, backend = {p['servizio']}). "
                   "Per convertirla in profili: python installa.py modello converti")
        except ErroreModello as e:
            stampa(str(e))
    else:
        mancanti = {n for n in scelti.values() if n and n not in profili}
        for n in sorted(mancanti):
            stampa(f"ATTENZIONE: il profilo «{n}», scelto nella configurazione, non esiste in {f}.")
    stampa("Il modello della chat (Jan, Claude Desktop, LM Studio) è un'altra cosa: si sceglie nel client.")
    return 0


def modello_prova(args, stampa, **_):
    from llm import leggi_profili
    cfg = leggi_cfg()
    if not args.nome or args.nome not in leggi_profili(cfg):
        stampa(f"Indica un profilo esistente: python installa.py modello prova <profilo> "
               f"(profili: {', '.join(leggi_profili(cfg)) or 'nessuno'}).")
        return 1
    return 0 if prova_profilo(cfg, args.nome, stampa) else 1


def modello_usa(args, stampa, gia_provato=False, default=None, **_):
    """Sceglie un profilo per tutti i ruoli o per quelli indicati, solo dopo una prova di collegamento riuscita.
    «default» (callable): procedura guidata che chiede il nome quando args.nome manca (avvio guidato, lavoro 28)."""
    from llm import RUOLI, ErroreModello, leggi_profili, profili_attivi
    from progetto import cartella_scelta
    cfg = leggi_cfg()
    nome = (args.nome or "").strip() if args.nome else ""
    if not nome and default:
        nome = (default() or "").strip()
    if not nome or nome not in leggi_profili(cfg):
        stampa(f"Indica un profilo esistente: python installa.py modello usa <profilo> "
               f"(profili: {', '.join(leggi_profili(cfg)) or 'nessuno'}).")
        return 1
    ruoli = list(dict.fromkeys(args.ruolo or RUOLI))
    try:
        prima = profili_attivi(cfg)
    except ErroreModello:
        prima = {r: "(profilo non valido)" for r in RUOLI}
    if not gia_provato and not prova_profilo(cfg, nome, stampa):
        stampa("Scelta non cambiata. Restano in uso: " + ", ".join(f"{r} {prima[r]}" for r in RUOLI) + ".")
        return 1
    if args.progetto:
        radice = cartella_scelta(cfg)
        if radice is None:
            stampa("Nessun progetto in uso: senza --progetto la scelta vale per tutti i progetti.")
            return 1
        dest = radice / "project.ini"
    else:
        dest = FILE_CONFIG
    if set(ruoli) == set(RUOLI):
        voci = {"profilo": nome, **{r: None for r in RUOLI}}
    else:
        voci = {r: nome for r in ruoli}
    imposta_voci(dest, "modello", voci)
    dopo = profili_attivi(leggi_cfg())
    stampa(f"In uso ({dest.name}): " + ", ".join(f"{r} {dopo[r]}" for r in RUOLI) + ".")
    for r in ruoli:
        if dopo[r] != nome:
            stampa(f"ATTENZIONE: per {r} vale ancora «{dopo[r]}», scelto nel project.ini del progetto, che prevale "
                   f"su config.ini. Per cambiarlo: python installa.py modello usa {nome} --progetto")
    cambi = [(r, prima[r], dopo[r]) for r in RUOLI if prima[r] != dopo[r]]
    if cambi:
        registra_cambio(cfg, cambi, str(dest), stampa)
    stampa("Il cambio vale per le ricerche avviate da adesso; le letture già fatte restano nell'archivio con il "
           "nome del modello che le ha fatte.")
    return 0


def modello_togli(args, stampa, chiedi=input, **_):
    from llm import RUOLI, file_profili, leggi_profili, nome_scelto
    cfg = leggi_cfg()
    f = file_profili(cfg)
    if not args.nome or args.nome not in leggi_profili(cfg):
        stampa(f"Il profilo «{args.nome or ''}» non esiste in {f}.")
        return 1
    usato = [r for r in RUOLI if nome_scelto(cfg, r) == args.nome]
    if usato:
        stampa(f"«{args.nome}» è in uso per {', '.join(usato)}: scegli prima un altro profilo "
               "(python installa.py modello usa <profilo>).")
        return 1
    if not args.si and not sn(chiedi, f"Tolgo il profilo «{args.nome}» da {f}?", False):
        stampa("Nessuna modifica.")
        return 0
    copia = copia_di_sicurezza(f)
    togli_profilo(f, args.nome)
    stampa(f"Profilo «{args.nome}» tolto (copia del file prima della modifica: {copia}).")
    return 0


def modello_converti(args, stampa, chiedi=input, **_):
    """Configurazione precedente (backend e sezioni dei servizi in config.ini) trasformata in profili."""
    from llm import RUOLI, SERVIZI, file_profili, leggi_profili, profilo_precedente, usa_profili
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#",))
    cp.read(FILE_CONFIG, encoding="utf-8")
    if usa_profili(cp):
        stampa("config.ini sceglie già i profili di modello: niente da convertire (python installa.py modello elenca).")
        return 0
    backend = cp.get("modello", "backend", fallback="anthropic").strip().lower()
    esistenti = leggi_profili(cp)
    nuovi, scelte = {}, {}
    for servizio in SERVIZI:
        if not cp.has_section(servizio):
            continue
        for r in RUOLI:
            p = profilo_precedente(cp, r, servizio)
            if not p["modello"]:
                continue
            nome = nome_libero(nome_proposto(p), {**esistenti, **nuovi}, p)
            if nome not in esistenti:
                nuovi[nome] = p
            if servizio == backend:
                scelte[r] = nome
    if not nuovi and not scelte:
        stampa("In config.ini non ci sono modelli da convertire. Crea un profilo: python installa.py modello nuovo")
        return 1
    f = file_profili(cp)
    stampa(f"Profili da aggiungere a {f}:")
    for nome, p in nuovi.items():
        stampa(f"  {nome}: {descrivi(p)}")
    if not nuovi:
        stampa("  nessuno (ci sono già)")
    if len(set(scelte.values())) == 1 and len(scelte) == len(RUOLI):
        voci = {"profilo": next(iter(scelte.values())), **{r: None for r in RUOLI}}
    else:
        voci = scelte
    if scelte:
        stampa("Scelta in config.ini, [modello]: " + ", ".join(f"{k} = {v}" for k, v in voci.items() if v))
    if not args.si and not sn(chiedi, "Procedo? (prima salvo una copia di config.ini e di models.ini)", True):
        stampa("Nessuna modifica.")
        return 0
    copie = [c for c in (copia_di_sicurezza(FILE_CONFIG), copia_di_sicurezza(f)) if c]
    for nome, p in nuovi.items():
        aggiungi_profilo(f, nome, p)
    if scelte:
        imposta_voci(FILE_CONFIG, "modello", voci)
    stampa("Conversione fatta. Copie di sicurezza: " + ", ".join(map(str, copie)) + ".")
    stampa("Le sezioni [anthropic], [openai], [router], [ollama] di config.ini non contano più: puoi toglierle.")
    return 0


def _scegli(chiedi, stampa, domanda, opzioni, predefinita=1):
    """Scelta numerata; se non c'è nessuno da interrogare (tastiera assente: EOFError) vale la scelta di default."""
    for i, o in enumerate(opzioni, 1):
        stampa(f"  {i}. {o}")
    while True:
        try:
            r = chiedi(f"{domanda} [{predefinita}] ").strip() or str(predefinita)
        except EOFError:
            return predefinita
        if r.isdigit() and 1 <= int(r) <= len(opzioni):
            return int(r)
        stampa(f"Scrivi un numero da 1 a {len(opzioni)}.")


def _chiedi_valore(chiedi, domanda, predefinito=""):
    try:
        r = chiedi(f"{domanda}" + (f" [{predefinito}]" if predefinito else "") + ": ").strip()
    except EOFError:                     # tastiera assente: il valore di default, se c'è
        return predefinito
    return r or predefinito


def modelli_ollama(url):
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=5) as r:
            return [m.get("name", "") for m in json.load(r).get("models", []) if m.get("name")]
    except Exception:
        return None


def come_salvare_variabile(nome, piattaforma=None):
    """Come salvare una variabile d'ambiente dell'utente sul sistema in uso."""
    piattaforma = piattaforma or sys.platform
    if piattaforma.startswith("win"):
        return f"setx {nome} \"...\", poi riapri il terminale"
    profilo_shell = "~/.zprofile" if piattaforma == "darwin" else "~/.profile"
    return f"aggiungi export {nome}=\"...\" a {profilo_shell}, poi riapri il terminale"


def salva_variabile(nome, valore, stampa):
    """Variabile d'ambiente dell'utente (solo dopo conferma). Su Windows con setx; altrove si spiega dove scriverla."""
    if os.name == "nt":
        r = subprocess.run(["setx", nome, valore], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode == 0:
            stampa(f"Variabile {nome} salvata per il tuo utente: vale nei terminali e nei programmi aperti da adesso.")
            return True
        stampa(f"Non riesco a salvare la variabile {nome}: impostala a mano (vedi docs/user_guide.it.md).")
        return False
    profilo_shell = "~/.zprofile" if sys.platform == "darwin" else "~/.profile"
    stampa(f"Per conservarla, aggiungi questa riga a {profilo_shell} (con la tua chiave al posto di ...):\n"
           f"  export {nome}=\"...\"")
    return False


def _chiedi_chiave(env, dove_chiave, stampa, chiedi, segreto, salva):
    """Chiede la chiave (nascosta), la mette nell'ambiente per la prova e, se l'utente vuole, la conserva.
    Vero se una chiave è stata data."""
    if dove_chiave:
        stampa(f"La chiave si crea qui: {dove_chiave}")
    chiave = segreto(f"Incolla la chiave per {env} (non si vede mentre scrivi; Invio per saltare): ").strip()
    if not chiave:
        return False
    os.environ[env] = chiave            # vale subito, per la prova
    if sn(chiedi, f"Salvo la chiave nella variabile d'ambiente {env} del tuo utente, perché resti per le "
                  "prossime volte?", True):
        salva(env, chiave, stampa)
    return True


# modelli che un servizio elenca ma che non servono a leggere testi (audio, filtri di sicurezza, immagini, vettori)
NON_TESTUALI = re.compile(r"whisper|tts|guard|embed|playai|orpheus|distil|vision|image|audio|safeguard|moderation",
                          re.I)


def modelli_servizio(url, chiave, timeout=10):
    """Modelli che un servizio compatibile OpenAI elenca (GET <url>/models); None se non risponde."""
    richiesta = urllib.request.Request(url.rstrip("/") + "/models", headers={
        "User-Agent": "ricerca-fonti/1.0", **({"Authorization": f"Bearer {chiave}"} if chiave else {})})
    try:
        with urllib.request.urlopen(richiesta, timeout=timeout) as r:
            dati = json.load(r).get("data", [])
    except Exception:
        return None
    nomi = (m.get("id", "") for m in dati if isinstance(m, dict))
    return sorted(n.removeprefix("models/") for n in nomi if n and not NON_TESTUALI.search(n))


def scegli_modello_servizio(url, chiave, proposto, stampa, chiedi, massimo=30):
    """Il modello di un servizio noto: dall'elenco del servizio quando si può avere, altrimenti scritto a mano
    (con la proposta solo se il servizio non l'ha smentita). Restituisce il nome, o "" se resta da scrivere."""
    elenco = modelli_servizio(url, chiave) if chiave else None
    if elenco and proposto not in elenco:
        proposto = ""                   # la proposta del codice non c'è più: non la suggeriamo
    if elenco and len(elenco) <= massimo:
        elenco = ([proposto] if proposto else []) + [m for m in elenco if m != proposto]
        stampa("Modelli del servizio" + (" (il primo è quello consigliato)" if proposto else "") + ":")
        n = _scegli(chiedi, stampa, "Quale", elenco + ["un altro (da scrivere)"])
        if n <= len(elenco):
            return elenco[n - 1]
    elif elenco:
        stampa(f"Il servizio offre {len(elenco)} modelli: scegli il nome nella sua console.")
    return _chiedi_valore(chiedi, "Nome esatto del modello (dalla console del servizio)", proposto)


def modello_nuovo(args, stampa, chiedi=input, segreto=getpass.getpass, salva=salva_variabile, **_):
    """Procedura guidata: servizio, modello, nome del profilo, chiave; poi prova e, se riesce, scelta."""
    from llm import leggi_profili, file_profili
    cfg = leggi_cfg()
    profili = leggi_profili(cfg)
    stampa("Nuovo profilo di modello. Quale servizio legge i passaggi?")
    tipo = _scegli(chiedi, stampa, "Scelta", [
        "Ollama, sul tuo computer: gratuito, nessuna chiave; serve un computer abbastanza potente",
        "Un servizio con una sola chiave (Groq, Google Gemini, OpenRouter o altro compatibile OpenAI)",
        "API di Anthropic (Claude): a consumo",
        "FreeLLMAPI (avanzato): più servizi gratuiti in catena, sul tuo computer"])
    dove_chiave = ""
    if tipo == 1:
        url = _chiedi_valore(chiedi, "Indirizzo di Ollama", "http://localhost:11434")
        installati = modelli_ollama(url)
        if installati is None:
            stampa("Ollama non risponde: avvialo (https://ollama.com) e riprova la prova con "
                   "python installa.py modello prova <profilo>.")
            installati = []
        if installati:
            stampa("Modelli installati:")
            n = _scegli(chiedi, stampa, "Quale", installati + ["un altro (da scrivere)"])
            modello = installati[n - 1] if n <= len(installati) else ""
        else:
            modello = ""
        modello = modello or _chiedi_valore(chiedi, "Nome del modello (si scarica con: ollama pull <nome>)",
                                            "qwen3.5:9b")
        p = {"servizio": "ollama", "url": url, "modello": modello, "num_ctx": "4096"}
    elif tipo == 2:
        stampa("Quale servizio?")
        n = _scegli(chiedi, stampa, "Scelta", [s[0] for s in SERVIZI_CHIAVE] + ["altro servizio compatibile OpenAI"])
        if n <= len(SERVIZI_CHIAVE):
            _, url, env, modello, pausa, dove_chiave = SERVIZI_CHIAVE[n - 1]
            # la chiave prima del modello: con la chiave il servizio dice quali modelli ha davvero
            if not os.environ.get(env):
                _chiedi_chiave(env, dove_chiave, stampa, chiedi, segreto, salva)
            dove_chiave = ""
            modello = scegli_modello_servizio(url, os.environ.get(env, ""), modello, stampa, chiedi)
        else:
            url = _chiedi_valore(chiedi, "Indirizzo del servizio (finisce di solito in /v1)")
            env = _chiedi_valore(chiedi, "Nome della variabile d'ambiente per la chiave (vuoto se non serve)")
            modello, pausa = "", "0"
        modello = modello or _chiedi_valore(chiedi, "Nome esatto del modello (dalla console del servizio)")
        p = {"servizio": "openai", "url": url, "modello": modello, "chiave_env": env, "pausa_secondi": pausa}
    elif tipo == 3:
        modello = _chiedi_valore(chiedi, "Modello", "claude-sonnet-5-5")
        p = {"servizio": "anthropic", "modello": modello, "chiave_env": "ANTHROPIC_API_KEY"}
        dove_chiave = "https://console.anthropic.com/settings/keys"
    else:
        url = _chiedi_valore(chiedi, "Indirizzo di FreeLLMAPI (pannello: Chiavi > URL di base)",
                             "http://127.0.0.1:31415/v1")
        modello = _chiedi_valore(chiedi, "Modello o catena (auto:<nome della catena>)", "auto:ricerca")
        ammessi = _chiedi_valore(chiedi, "Modelli ammessi, parti di nome separate da \";\" (vuoto = tutti)")
        p = {"servizio": "router", "url": url, "modello": modello, "chiave_env": "FREELLMAPI_KEY",
             "pausa_secondi": "2", "modelli_ammessi": ammessi}
    if not p.get("modello") or (p["servizio"] in ("openai", "router") and not p.get("url")):
        stampa("Mancano il modello o l'indirizzo: nessun profilo creato.")
        return 1
    proposto = nome_libero(nome_proposto(p), profili)
    while True:
        nome = _chiedi_valore(chiedi, "Nome del profilo", proposto)
        if not NOME_PROFILO.match(nome):
            stampa("Usa solo lettere, cifre, punto, trattino e trattino basso, senza spazi.")
        elif nome in profili:
            stampa(f"Esiste già un profilo «{nome}»: scegli un altro nome.")
        else:
            break
    env = p.get("chiave_env", "")
    if env and not os.environ.get(env) and not _chiedi_chiave(env, dove_chiave, stampa, chiedi, segreto, salva):
        stampa(f"Senza chiave la prova non riuscirà: imposta la variabile {env} e poi "
               f"python installa.py modello prova {nome}.")
    f = file_profili(cfg)
    aggiungi_profilo(f, nome, p)
    stampa(f"Profilo «{nome}» salvato in {f}.")
    if not prova_profilo(leggi_cfg(), nome, stampa):
        stampa(f"Il profilo resta salvato: correggilo in {f} o riprova con python installa.py modello prova {nome}. "
               "La scelta del modello in uso non è cambiata.")
        return 1
    if sn(chiedi, f"Uso «{nome}» da adesso per tutti i ruoli?", True):
        return modello_usa(argparse.Namespace(nome=nome, ruolo=None, progetto=False), stampa, gia_provato=True)
    stampa(f"Per sceglierlo più tardi: python installa.py modello usa {nome}")
    return 0


AZIONI_MODELLO = {"nuovo": modello_nuovo, "elenca": modello_elenca, "usa": modello_usa, "prova": modello_prova,
                  "togli": modello_togli, "converti": modello_converti}


def cmd_modello(args, stampa=print, **kw):
    sys.path.insert(0, str(CARTELLA))
    return AZIONI_MODELLO[args.azione](args, stampa=stampa, **kw)


# ---------------------------------------------------------------- avvio guidato (lavoro 28)
PASSI = {1: "ambiente", 2: "modello", 3: "progetto", 4: "chat", 5: "riepilogo"}


def scegli_passi(args, stampa):
    """Quali passi eseguire, in ordine, dai numeri dati (--passi e --saltati); None se i numeri non valgono."""
    def numeri(testo, nome):
        try:
            v = {int(x) for x in testo.replace(" ", ",").split(",") if x.strip()}
        except ValueError:
            stampa(f"--{nome}: scrivi numeri da 1 a 5 separati da virgola (es. 2,4).")
            return False
        if not v <= set(PASSI):
            stampa(f"--{nome}: i passi sono solo 1-5 ({', '.join(f'{n} {t}' for n, t in PASSI.items())}).")
            return False
        return v
    scelti = numeri(args.passi, "passi") if args.passi else set(PASSI)
    if scelti is False:
        return None
    saltati = numeri(args.saltati, "saltati") if args.saltati else set()
    if saltati is True:
        saltati = set()
    if saltati is False:
        return None
    scelti -= saltati
    if 5 not in scelti:
        scelti.add(5)                     # il riepilogo finale si fa sempre: costa niente e riassume lo stato
    return sorted(scelti)


def stato_ambiente(args, stampa):
    """Passo 1: controllo dell'ambiente di base (Python, SQLite con FTS5, librerie e OCR facoltativi); 0 tutto a
    posto, 1 manca qualcosa di necessario (istruzioni già stampate). Modello e progetto no: li preparano i passi 2
    e 3, e il riepilogo controlla tutto."""
    esito = Esito(stampa)
    controlla_python(esito)
    controlla_sqlite(esito)
    stampa("Per importare nuove fonti (facoltativi):")
    controlla_pymupdf(esito)
    controlla_tesseract(esito, leggi_cfg())
    if not args.rapido:
        controlla_paddle(esito, leggi_cfg())
    return 1 if esito.mancanti else 0


def guida_modello(stampa, chiedi=input):
    """Passo 2: scelta del modello che legge i passaggi (lavoro 26). 0 fatto o non necessario, 1 fallito o saltato."""
    from llm import ErroreModello, leggi_profili, profilo, usa_profili
    cfg = leggi_cfg()
    profili = leggi_profili(cfg)
    if usa_profili(cfg):
        try:
            attivi = {r: profilo(cfg, r)[0] for r in ("smistamento", "analisi", "sintesi")}
        except ErroreModello as e:
            if profili:                         # senza profili (copia nuova) la procedura qui sotto basta
                stampa(str(e))
            attivi = {}
        if attivi:
            stampa("Modello che legge i passaggi, già scelto: "
                   + ", ".join(sorted(set(attivi.values()))) + ". Per cambiarlo: python installa.py modello usa "
                   "<profilo> (la scelta resta valida anche se salti questo passo).")
            return 0
    if not profili:
        stampa("Nessun profilo di modello: ne creo uno adesso con la procedura guidata (servizio, modello, chiave).")
        return modello_nuovo(argparse.Namespace(), stampa, chiedi=chiedi)
    nomi = list(profili)
    stampa("Ci sono già dei profili di modello:")
    n = _scegli(chiedi, stampa, "Quale uso per leggere i passaggi?",
                nomi + ["ne creo uno nuovo"], predefinita=1)
    if n > len(nomi):
        return modello_nuovo(argparse.Namespace(), stampa, chiedi=chiedi)
    return modello_usa(argparse.Namespace(nome=nomi[n - 1], ruolo=None, progetto=False), stampa)


def progetto_esiste(radice):
    """Vero se la cartella è un progetto (c'è project.ini): una cartella indicata ma assente non conta."""
    return radice is not None and (Path(radice) / "project.ini").is_file()


def cartella_progetti():
    return CARTELLA.parent / "projects"


def guida_progetto(stampa, chiedi=input, config=None, crea=None, base=None, si=False):
    """Passo 3: creazione del primo progetto e sua scelta in config.ini, senza modifiche manuali ai file.
    0 fatto o non necessario, 1 fallito o saltato dall'utente. Parametri solo per i test: «config» file .ini da
    scrivere, «crea» la funzione che crea il progetto, «base» cartella dove proporre di metterlo."""
    from progetto import VARIABILE, cartella_scelta, cmd_nuovo, nome
    cfg = leggi_cfg()
    radice = cartella_scelta(cfg)
    if progetto_esiste(radice):
        stampa(f"Progetto in uso: «{nome(cfg)}» ({radice}). Per un progetto nuovo: python progetto.py nuovo "
               f'<cartella> --nome "..." (la scelta resta valida anche se salti questo passo).')
        return 0
    if radice is not None:
        stampa(f"La configurazione indica come progetto {radice}, che non esiste (o non è un progetto): ne creo uno.")
    base = Path(base) if base else cartella_progetti()
    proposto = _chiedi_valore(chiedi, "Nome del progetto nuovo (la ricerca sui tuoi documenti)", "La mia ricerca")
    cartella = _chiedi_valore(chiedi, "Cartella dove mettere i suoi file", str(base / re.sub(r"\s+", "_", proposto)))
    if not Path(cartella).expanduser().is_absolute():     # un nome solo: dentro la cartella dei progetti
        cartella = str(base / cartella)
    cartella = str(Path(cartella).expanduser())
    if not si and not conferma_domanda(f"Creo il progetto «{proposto}» in {cartella}? [S/n] ", chiedi):
        stampa("Passo saltato: nessun progetto creato. Quando vuoi: python progetto.py nuovo <cartella> --nome \"...\"")
        return 1
    esito = (crea or cmd_nuovo)(argparse.Namespace(cartella=cartella, nome=proposto, descrizione=""), stampa)
    if esito:
        return 1
    f = Path(cartella).resolve()
    dest = Path(config) if config else FILE_CONFIG
    copia = copia_di_sicurezza(dest)
    imposta_voci(dest, "progetto", {"cartella": str(f)})
    stampa(f"Progetto scelto in {dest.name}, sezione [progetto]: vale per tutti i comandi."
           + (f" Copia di sicurezza: {copia}" if copia else ""))
    stampa(f"(Solo per una finestra del terminale, senza toccare i file: {VARIABILE}={f})")
    return 0


CLIENT_GUIDA = [("jan", "Jan"), ("claude", "Claude Desktop"), ("lmstudio", "LM Studio")]


def voce_presente(codice, file=None):
    """Vero se il file di configurazione del client contiene la voce di AIrchivist (anche col nome «Pipeline»)."""
    f = Path(file) if file else file_client(codice)
    if f is None or not f.exists():
        return False
    try:
        doc = json.loads(_leggi_testo(f)[0])
    except ValueError:
        return False
    servers = next((doc[k] for k in ("mcpServers", "servers") if isinstance(doc.get(k), dict)), {})
    return any(n in servers for n in ALIAS_CLIENT.get(codice, (NOME_SERVER,)))


def guida_chat(stampa, chiedi=input, si=False, file=None, scrivi_voce=None):
    """Passo 4: configurazione della chat (lavoro 27). Mostra le modifiche al file del client scelto, le scrive
    dopo la conferma (senza domanda solo con --si), poi prova l'handshake MCP come lo farebbe il client. 0 fatto,
    1 saltato o non riuscito. «file» e «scrivi_voce» servono solo ai test: percorso del file da usare al posto di
    quello reale e voce del server finta."""
    gia = next((c for c, _ in CLIENT_GUIDA if voce_presente(c, file)), None)
    stampa("Quale programma di chat colleghi a AIrchivist? (la chat è diversa dal modello che legge i passaggi)")
    predefinita = next((i for i, (c, _) in enumerate(CLIENT_GUIDA, 1) if c == gia), 1)
    n = _scegli(chiedi, stampa, "Scelta", [etichetta for _, etichetta in CLIENT_GUIDA] + ["nessuno, per ora"],
                predefinita=predefinita)
    if n > len(CLIENT_GUIDA):
        stampa("Passo saltato. Quando vuoi: python installa.py client <jan|claude|lmstudio> --scrivi")
        return 1
    nome = CLIENT_GUIDA[n - 1][0]
    args = argparse.Namespace(nome=nome, scrivi=True, verifica=True, si=si,
                              file=str(file) if file else None,
                              voce=scrivi_voce or voce_server())
    esito = cmd_client_scrivi(args, stampa, chiedi=chiedi)
    return esito if esito or voce_presente(nome, file) else 1        # annullato: passo non completato


def riepilogo(stampa, file_client_fn=None):
    """Passo 5: che cosa è installato, dove sta il progetto, prossimo passo. Rifà tutti i controlli necessari
    (come «controlla»): 0 se non manca nulla, 1 altrimenti. «file_client_fn» nei test."""
    from llm import RUOLI, ErroreModello, profilo, usa_profili
    from progetto import cartella_scelta, nome
    cfg = leggi_cfg()
    fc = file_client_fn or file_client
    controlli = Esito(lambda riga: None)
    controlla_python(controlli)
    controlla_sqlite(controlli)
    controlla_modelli(controlli, cfg)
    controlla_progetto(controlli, cfg)
    stampa("\n=== Riepilogo ===")
    stampa(f"- Motore: {CARTELLA} (Python {sys.version_info.major}.{sys.version_info.minor})")
    if usa_profili(cfg):
        try:
            stampa("- Modello che legge i passaggi: " + ", ".join(f"{r}: {profilo(cfg, r)[0]}" for r in RUOLI))
        except ErroreModello as e:
            stampa(f"- Modello che legge i passaggi: attenzione, {e}")
    else:
        stampa("- Modello che legge i passaggi: nessuna scelta ancora (python installa.py modello nuovo)")
    radice = cartella_scelta(cfg)
    stampa(f"- Progetto: «{nome(cfg)}» in {radice}" if progetto_esiste(radice) else
           "- Progetto: nessuno ancora (python installa.py inizia --passi 3)")
    configurati = [etichetta for codice, etichetta in CLIENT_GUIDA if voce_presente(codice, fc(codice))]
    if configurati:
        stampa("- Chat: AIrchivist è nella configurazione di " + ", ".join(configurati) +
               "; se il programma era aperto, riavvialo perché legga la voce")
    else:
        stampa("- Chat: non configurata ancora (python installa.py client <jan|claude|lmstudio> --scrivi)")
    if controlli.mancanti:
        stampa("- Manca ancora: " + ", ".join(v.strip() for v in controlli.mancanti) +
               " (dettagli: python installa.py controlla)")
        return 1
    stampa("- Prossimo passo: importa le fonti con la tabella di revisione: python importa.py proponi <cartella dei "
           "documenti>, controlla la tabella in Excel o LibreOffice, poi python importa.py applica <tabella> (o dalla "
           "chat: strumento importa, azioni proponi e applica); vedi docs/quickstart.it.md (in inglese docs/quickstart.md) e «Importare "
           "nuove fonti» in docs/user_guide.it.md")
    return 0


def cmd_inizia(args, stampa=print, chiedi=input, funzioni=None, riepilogo_fn=None):
    """Avvio guidato: i cinque passi della roadmap (lavoro 28). Si interrompe e riprende senza rifare i passi
    già completati (ognuno riconosce il proprio stato); ogni passo si può saltare (--saltati, o rispondendo
    «no» alle domande). «funzioni» e «riepilogo_fn» servono solo ai test."""
    sys.path.insert(0, str(CARTELLA))
    passi = scegli_passi(args, stampa)
    if passi is None:
        return 2
    stampa("AIrchivist — avvio guidato (puoi interrompere con Ctrl+C e riprendere: i passi già fatti non si "
           "rifanno)\n")
    esiti = {}
    si = getattr(args, "si", False)
    default = {1: lambda: stato_ambiente(args, stampa),
               2: lambda: guida_modello(stampa, chiedi),
               3: lambda: guida_progetto(stampa, chiedi, si=si),
               4: lambda: guida_chat(stampa, chiedi, si=si)}
    funzioni = funzioni or default
    for n in passi:
        if n == 5:
            continue
        titolo = {1: "Controllo dell'ambiente", 2: "Modello che legge i passaggi",
                  3: "Il tuo primo progetto", 4: "Collegamento con la chat"}[n]
        stampa(f"\n--- Passo {n} di 5: {titolo} ---")
        esiti[n] = funzioni[n]()
        if esiti[n] != 0 and n == 1:
            stampa("\nManca qualcosa di necessario: sistema seguendo le indicazioni qui sopra e rilancia "
                   "«python installa.py inizia»: i passi già completati non verranno rifatti.")
            return 1
    completo = (riepilogo_fn or riepilogo)(stampa) == 0
    blocco = [n for n in (1, 2, 3, 4) if n in esiti and esiti[n] != 0]
    if blocco:
        stampa("Passi non completati: " + ", ".join(f"{n} {PASSI[n]}" for n in blocco) +
               ". Riprendi quando vuoi: python installa.py inizia (o --passi " + ",".join(map(str, blocco)) + ").")
    if blocco or not completo:
        return 1
    stampa("Tutto pronto.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="comando")
    c = sub.add_parser("controlla")
    c.add_argument("--rapido", action="store_true", help="salta il controllo di PaddleOCR (lento)")
    sub.add_parser("librerie")
    k = sub.add_parser("client")
    k.add_argument("nome", nargs="?", default="json", choices=["jan", "claude", "lmstudio", "json"])
    k.add_argument("--scrivi", action="store_true",
                   help="aggiungi la voce al file di configurazione del client (prima le modifiche, poi conferma)")
    k.add_argument("--verifica", action="store_true", dest="verifica",
                   help="avvia il server come lo avvierebbe il client: handshake MCP ed elenco degli strumenti")
    k.add_argument("--si", action="store_true", help="--scrivi: niente domanda di conferma")
    k.add_argument("--file", default=None, help="--scrivi: file di configurazione da usare (di norma lo trovo io)")
    k.add_argument("--file-impostazioni", default=None, dest="file_impostazioni",
                   help="jan --scrivi: settings.json di Jan da usare (di norma accanto a mcp_config.json)")
    m = sub.add_parser("modello", help="profili dei modelli: nuovo, elenca, usa, prova, togli, converti")
    m.add_argument("azione", nargs="?", default="nuovo", choices=list(AZIONI_MODELLO))
    m.add_argument("nome", nargs="?", help="nome del profilo (usa, prova, togli)")
    m.add_argument("--ruolo", action="append", choices=["smistamento", "analisi", "sintesi"],
                   help="usa: solo per questo ruolo (ripetibile); senza, per tutti")
    m.add_argument("--progetto", action="store_true", help="usa: scelta nel project.ini del progetto in uso")
    m.add_argument("--si", action="store_true", help="togli, converti: niente domanda di conferma")
    i = sub.add_parser("inizia", help="avvio guidato: ambiente, modello, primo progetto, chat, riepilogo "
                                      "(lavoro 28)")
    i.add_argument("--passi", default="", help="solo questi passi, numeri da 1 a 5 separati da virgola (es. 3,4)")
    i.add_argument("--saltati", default="", help="tutti tranne questi (es. --saltati 2 per non toccare il modello)")
    i.add_argument("--si", action="store_true", help="nei passi automatici nessuna domanda di conferma")
    i.add_argument("--rapido", action="store_true", help="passo 1: salta il controllo di PaddleOCR (lento)")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    if args.comando is None:
        args.comando, args.rapido = "controlla", False
    return {"controlla": cmd_controlla, "librerie": cmd_librerie, "client": cmd_client,
            "modello": cmd_modello, "inizia": cmd_inizia}[args.comando](args)


if __name__ == "__main__":
    sys.exit(main())

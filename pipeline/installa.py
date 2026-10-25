#!/usr/bin/env python3
"""
Installazione e controllo dell'ambiente (lavoro 15, fase 4).

Il motore è la cartella pipeline: si scarica (git clone o archivio .zip) e si usa dove sta, con config.ini accanto
al codice. I requisiti si installano nel sistema, mai dentro la cartella del progetto.

Uso (nella cartella pipeline):
  python installa.py                    controlla l'ambiente (come «controlla»)
  python installa.py controlla          Python, SQLite FTS5, librerie, Tesseract e lingue, modelli, progetto
  python installa.py librerie           installa nel Python di sistema le librerie facoltative (requirements.txt)
  python installa.py client [nome]      configurazione del server MCP per un client: jan, claude, lmstudio, json

Esito di «controlla»: 0 se i requisiti necessari ci sono, 1 se ne manca almeno uno. I facoltativi (PyMuPDF,
Tesseract, PaddleOCR) servono solo a importare nuove fonti.
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
import urllib.error
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
    """Codici Tesseract delle lingue delle serie del progetto in uso (serie.ini)."""
    import profili
    from importa import LINGUE_OCR
    lingue = {p.get("lingua", "").strip() for p in profili.tutti(ricarica=True).values()}
    return {l: LINGUE_OCR[l] for l in sorted(lingue) if l in LINGUE_OCR}


def controlla_tesseract(esito, cfg):
    from importa import cartella_modelli, cerca_tesseract, lingue_installate
    exe = cerca_tesseract(cfg)
    if not exe:
        esito("facoltativo", "Tesseract", "non trovato; serve solo a importare scansioni. Windows: "
                                          "https://github.com/UB-Mannheim/tesseract/wiki")
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
    except Exception as e:                      # serie.ini illeggibile: lo segnala progetto.py
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


def controlla_modelli(esito, cfg):
    """Servizio dei modelli scelto in config.ini: chiave presente e servizio raggiungibile."""
    backend = cfg.get("modello", "backend", fallback="anthropic").strip().lower()
    sez = cfg[backend] if cfg.has_section(backend) else {}
    if backend == "anthropic":
        esito("ok" if os.environ.get("ANTHROPIC_API_KEY") else "manca", "modelli: Anthropic",
              "chiave ANTHROPIC_API_KEY " + ("presente" if os.environ.get("ANTHROPIC_API_KEY") else "assente"))
        return
    if backend == "ollama":
        url = sez.get("url", "http://localhost:11434").rstrip("/") + "/api/tags"
        intestazioni = {}
    else:
        nome_env = sez.get("chiave_env", "").strip()
        chiave = os.environ.get(nome_env, "") if nome_env else ""
        if nome_env and not chiave:
            esito("manca", f"modelli: {backend}", f"variabile {nome_env} assente (setx {nome_env} \"...\", poi "
                                                  "riapri il terminale)")
            return
        url = sez.get("url", "").rstrip("/") + "/models"
        intestazioni = {"Authorization": f"Bearer {chiave}"} if chiave else {}
    intestazioni["User-Agent"] = "ricerca-fonti/1.0"
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers=intestazioni), timeout=10).close()
        esito("ok", f"modelli: {backend}", f"{url} risponde")
    except urllib.error.HTTPError as e:
        motivo = "chiave rifiutata" if e.code in (401, 403) else f"errore HTTP {e.code}"
        esito("manca", f"modelli: {backend}", f"{url}: {motivo}")
    except Exception:
        avvio = {"router": "avvia FreeLLMAPI", "ollama": "avvia Ollama"}.get(backend, "controlla l'indirizzo")
        esito("manca", f"modelli: {backend}", f"{url} non risponde: {avvio} e riprova")


def controlla_progetto(esito, cfg):
    from progetto import VARIABILE, cartella_scelta, nome, percorso
    radice = cartella_scelta(cfg) or CARTELLA.parent
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
    from progetto import leggi_config
    cfg = leggi_config()
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
    return subprocess.run(cmd).returncode


# ---------------------------------------------------------------- client MCP
def voce_server():
    return {"command": sys.executable, "args": [str(CARTELLA / "mcp_server.py")], "env": {"PYTHONUTF8": "1"}}


def file_client(nome):
    if nome == "claude":
        base = Path(os.environ.get("APPDATA", "")) if os.name == "nt" else (
            Path.home() / "Library" / "Application Support" if sys.platform == "darwin" else Path.home() / ".config")
        return base / "Claude" / "claude_desktop_config.json"
    if nome == "lmstudio":
        return Path.home() / ".lmstudio" / "mcp.json"
    return None


def cmd_client(args, stampa=print):
    voce = voce_server()
    if args.nome == "jan":
        stampa("Jan: Settings > MCP Servers > + Add MCP Server")
        stampa(f"  Nome:      {NOME_SERVER}")
        stampa("  Tipo:      STDIO")
        stampa(f"  Command:   {voce['command']}")
        stampa(f"  Arguments: {voce['args'][0]}")
        stampa("  Variabile d'ambiente: PYTHONUTF8 = 1")
        stampa("Poi, nelle impostazioni MCP: timeout degli strumenti 90 secondi (vedi ISTRUZIONI.md, «Jan»).")
        return 0
    blocco = json.dumps({"mcpServers": {NOME_SERVER: voce}}, ensure_ascii=False, indent=2)
    f = file_client(args.nome)
    if f:
        stato = "esiste: aggiungi la voce dentro «mcpServers»" if f.exists() else "non esiste ancora: crealo"
        stampa(f"File di configurazione: {f} ({stato})")
    stampa(blocco)
    if args.nome == "json":
        stampa("Per un client che usa HTTP invece di STDIO: python mcp_server.py --http 8765")
    stampa("Riavvia il client dopo aver salvato il file.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="comando")
    c = sub.add_parser("controlla")
    c.add_argument("--rapido", action="store_true", help="salta il controllo di PaddleOCR (lento)")
    sub.add_parser("librerie")
    k = sub.add_parser("client")
    k.add_argument("nome", nargs="?", default="json", choices=["jan", "claude", "lmstudio", "json"])
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    if args.comando is None:
        args.comando, args.rapido = "controlla", False
    return {"controlla": cmd_controlla, "librerie": cmd_librerie, "client": cmd_client}[args.comando](args)


if __name__ == "__main__":
    sys.exit(main())

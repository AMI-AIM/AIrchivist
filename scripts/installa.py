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
  python installa.py modello [azione]   profili dei modelli che leggono i passaggi (lavoro 26):
      nuovo                         procedura guidata per un profilo nuovo (azione predefinita)
      elenca                        profili, quelli in uso, chiavi presenti
      usa <profilo> [--ruolo R] [--progetto]
                                    sceglie il profilo, solo se la prova di collegamento riesce; il cambio si
                                    annota in system/model_changes.csv del progetto
      prova <profilo>               prova di collegamento con una richiesta minima
      togli <profilo> [--si]        toglie un profilo non in uso
      converti [--si]               trasforma in profili la configurazione precedente di config.ini

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
        esito("manca", voce, f"variabile {nome_env} assente (setx {nome_env} \"...\", poi riapri il terminale)")
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
        stampa("Poi, nelle impostazioni MCP: timeout degli strumenti 90 secondi (vedi docs/user_guide.it.md, «Jan»).")
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


# ---------------------------------------------------------------- profili di modello (lavoro 26)
FILE_CONFIG = CARTELLA / "config.ini"
NOME_PROFILO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# servizi con una sola chiave: nome, indirizzo, variabile della chiave, modello proposto, pausa, dove si prende la chiave
SERVIZI_CHIAVE = [
    ("Groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "llama-3.3-70b-versatile", "6",
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
    from progetto import NessunProgetto, percorso
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
        stampa(f"Collegamento con «{nome}» non riuscito: {e}.")
        return False
    stampa(f"Collegamento con «{nome}» riuscito (ha risposto {risposto}).")
    return True


def sn(chiedi, domanda, predefinito):
    r = chiedi(f"{domanda} [{'S/n' if predefinito else 's/N'}] ").strip().lower()
    return predefinito if not r else r in ("s", "si", "sì", "y", "yes")


def modello_elenca(args, stampa, **_):
    from llm import RUOLI, ErroreModello, file_profili, leggi_profili, nome_scelto, profilo, usa_profili
    cfg = leggi_cfg()
    profili = leggi_profili(cfg)
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
        stampa(f"{'*' if ruoli else ' '} {nome}: {descrivi(p)}{chiave}"
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


def modello_usa(args, stampa, gia_provato=False, **_):
    """Sceglie un profilo per tutti i ruoli o per quelli indicati, solo dopo una prova di collegamento riuscita."""
    from llm import RUOLI, ErroreModello, leggi_profili, profili_attivi
    from progetto import cartella_scelta
    cfg = leggi_cfg()
    nome = args.nome
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
    for i, o in enumerate(opzioni, 1):
        stampa(f"  {i}. {o}")
    while True:
        r = chiedi(f"{domanda} [{predefinita}] ").strip() or str(predefinita)
        if r.isdigit() and 1 <= int(r) <= len(opzioni):
            return int(r)
        stampa(f"Scrivi un numero da 1 a {len(opzioni)}.")


def _chiedi_valore(chiedi, domanda, predefinito=""):
    r = chiedi(f"{domanda}" + (f" [{predefinito}]" if predefinito else "") + ": ").strip()
    return r or predefinito


def modelli_ollama(url):
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/tags", timeout=5) as r:
            return [m.get("name", "") for m in json.load(r).get("models", []) if m.get("name")]
    except Exception:
        return None


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
        else:
            url = _chiedi_valore(chiedi, "Indirizzo del servizio (finisce di solito in /v1)")
            env = _chiedi_valore(chiedi, "Nome della variabile d'ambiente per la chiave (vuoto se non serve)")
            modello, pausa = "", "0"
        modello = _chiedi_valore(chiedi, "Nome esatto del modello (dalla console del servizio)", modello)
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
    if env and not os.environ.get(env):
        if dove_chiave:
            stampa(f"La chiave si crea qui: {dove_chiave}")
        chiave = segreto(f"Incolla la chiave per {env} (non si vede mentre scrivi; Invio per saltare): ").strip()
        if chiave:
            os.environ[env] = chiave            # vale subito, per la prova
            if sn(chiedi, f"Salvo la chiave nella variabile d'ambiente {env} del tuo utente, perché resti per le "
                          "prossime volte?", True):
                salva(env, chiave, stampa)
        else:
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="comando")
    c = sub.add_parser("controlla")
    c.add_argument("--rapido", action="store_true", help="salta il controllo di PaddleOCR (lento)")
    sub.add_parser("librerie")
    k = sub.add_parser("client")
    k.add_argument("nome", nargs="?", default="json", choices=["jan", "claude", "lmstudio", "json"])
    m = sub.add_parser("modello", help="profili dei modelli: nuovo, elenca, usa, prova, togli, converti")
    m.add_argument("azione", nargs="?", default="nuovo", choices=list(AZIONI_MODELLO))
    m.add_argument("nome", nargs="?", help="nome del profilo (usa, prova, togli)")
    m.add_argument("--ruolo", action="append", choices=["smistamento", "analisi", "sintesi"],
                   help="usa: solo per questo ruolo (ripetibile); senza, per tutti")
    m.add_argument("--progetto", action="store_true", help="usa: scelta nel project.ini del progetto in uso")
    m.add_argument("--si", action="store_true", help="togli, converti: niente domanda di conferma")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    if args.comando is None:
        args.comando, args.rapido = "controlla", False
    return {"controlla": cmd_controlla, "librerie": cmd_librerie, "client": cmd_client,
            "modello": cmd_modello}[args.comando](args)


if __name__ == "__main__":
    sys.exit(main())

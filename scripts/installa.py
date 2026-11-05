#!/usr/bin/env python3
"""
Installazione e controllo dell'ambiente.

Il motore è la cartella scripts: si scarica (git clone o archivio .zip) e si usa dove sta, con config.ini accanto
al codice. I requisiti si installano nel sistema, mai dentro la cartella del progetto.

Uso (nella cartella scripts):
  python installa.py                    controlla l'ambiente (come «controlla»)
  python installa.py controlla          Python, SQLite FTS5, librerie, Tesseract e lingue, modelli, progetto
  python installa.py librerie           installa nel Python di sistema le librerie facoltative (requirements.txt)
  python installa.py modello [azione]   profili dei modelli che leggono i passaggi:
      nuovo                         procedura guidata per un profilo nuovo (azione predefinita)
      elenca                        profili, quelli in uso, chiavi presenti
      usa <profilo> [--ruolo R] [--progetto]
                                    sceglie il profilo, solo se la prova di collegamento riesce; il cambio si
                                    annota in system/model_changes.csv del progetto
      prova <profilo>               prova di collegamento con una richiesta minima
      togli <profilo> [--si]        toglie un profilo non in uso
      converti [--si]               trasforma in profili la configurazione precedente di config.ini
  python installa.py lingue [codici]    lingue OCR: installate, richieste dalle serie, mancanti; con i codici
                                    (es. sqi chi_sim) le scarica da tessdata_best nella cartella dei modelli
                                    di Tesseract, se si può scrivere (Tesseract incluso nel programma)
  python installa.py inizia [--passi N,...] [--saltati N,...] [--si]
                                    avvio guidato per chi installa per la prima volta:
                                    1 ambiente, 2 modello, 3 primo progetto, 4 riepilogo.
                                    Si interrompe e riprende senza rifare i passi già completati; ogni passo
                                    si può saltare (--saltati 2,3). Con --si i passi automatici non chiedono
                                    conferma (la scelta del modello resta comunque interattiva)

Esito di «controlla»: 0 se i requisiti necessari ci sono, 1 se ne manca almeno uno. I facoltativi (PyMuPDF,
Tesseract) servono solo a importare nuove fonti.
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

import posizioni

CARTELLA = Path(__file__).resolve().parent
REQUISITI = CARTELLA.parent / "requirements.txt"
PYTHON_MINIMO = (3, 10)


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


def controlla_pywebview(esito):
    try:
        import webview  # noqa: F401
        from importlib.metadata import PackageNotFoundError, version
        try:
            v = version("pywebview")
        except PackageNotFoundError:
            v = "?"
        esito("ok", "pywebview", f"{v} (finestra propria dell'interfaccia)")
    except ImportError:
        esito("facoltativo", "pywebview", "non installato: l'interfaccia si apre nel browser invece che in una "
                                          "finestra propria (python installa.py librerie)")


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


def stato_lingue(cfg):
    """Le lingue OCR per la riga di comando e per l'interfaccia: Tesseract in uso, cartella dei modelli e se ci si
    può scrivere, lingue installate, richieste dalle serie del progetto (più osd, l'orientamento della pagina),
    mancanti, e i codici da proporre per lo scaricamento."""
    import importa
    from progetto import NessunProgetto
    exe = importa.cerca_tesseract(cfg)
    out = {"tesseract": exe, "cartella": None, "scrivibile": False, "installate": [], "richieste": [],
           "mancanti": [], "proposte": [], "nomi": importa.NOMI_LINGUE}
    if not exe:
        return out
    cartella = importa.cartella_lingue(cfg, exe)
    installate = importa.lingue_installate(exe, importa.cartella_modelli(cfg))
    try:
        richieste = importa.lingue_delle_serie() | {"osd"}
    except (NessunProgetto, configparser.Error):
        richieste = {"osd"}
    # da installare: tutti i modelli di tessdata_best che non ci sono ancora
    proposte = sorted((set(importa.NOMI_LINGUE) | set(importa.LINGUE_OCR.values()) | set(importa.ALTRE_LINGUE))
                      - installate)
    propria = importa.cartella_modelli(cfg) is not None
    out.update(cartella=str(cartella) if cartella else None, scrivibile=importa.scrivibile(cartella),
               installate=sorted(installate), richieste=sorted(richieste),
               mancanti=sorted(richieste - installate), proposte=proposte,
               # una cartella delle lingue propria si può creare se quella di Tesseract non si può scrivere
               propria=propria, cartella_utente=str(cartella_lingue_utente()),
               dimensione_mb=round(_dimensione(cartella) / 1e6) if cartella else 0)
    return out


def cartella_lingue_utente():
    """Dove vanno le lingue OCR dell'utente quando quella di Tesseract chiede l'amministratore: nella cartella dei
    dati dell'applicazione dell'utente (anche in modo sviluppo: 100 MB e più non vanno nel repository)."""
    return posizioni.cartella_sistema() / "tessdata"


def _dimensione(cartella):
    try:
        return sum(f.stat().st_size for f in Path(cartella).rglob("*") if f.is_file() and f.suffix != ".jar")
    except OSError:
        return 0


def usa_cartella_lingue_propria(cfg, file_config, stampa=print):
    """Copia i modelli della cartella di Tesseract (lingue, configs, tessconfigs; non i .jar di ScrollView) nella
    cartella dell'utente e la indica in config.ini ([ocr] modelli): da lì si scaricano le lingue nuove senza i
    diritti di amministratore. Tesseract resta com'è. Restituisce la cartella."""
    import importa
    exe = importa.cerca_tesseract(cfg)
    if not exe:
        raise ValueError("Tesseract non trovato: senza, le lingue non servono.")
    sorgente = importa.cartella_lingue(cfg, exe)
    dest = cartella_lingue_utente()
    if sorgente is not None and Path(sorgente).resolve() == dest.resolve():
        raise ValueError(f"Le lingue stanno già in {dest}.")
    prima = importa.lingue_installate(exe, importa.cartella_modelli(cfg))
    dest.mkdir(parents=True, exist_ok=True)
    if sorgente is not None and Path(sorgente).is_dir():
        stampa(f"Copio i modelli da {sorgente} in {dest}…")
        shutil.copytree(sorgente, dest, dirs_exist_ok=True, ignore=shutil.ignore_patterns("*.jar", "*.parziale"))
    dopo = importa.lingue_installate(exe, dest)
    perse = prima - dopo
    if perse:
        raise ValueError(f"Nella cartella nuova Tesseract non vede: {', '.join(sorted(perse))}. La configurazione "
                         f"non è cambiata; la copia resta in {dest}.")
    copia_di_sicurezza(file_config)
    imposta_voci(file_config, "ocr", {"modelli": str(dest)})
    stampa(f"Le lingue OCR ora stanno in {dest} ({len(dopo)} modelli).")
    return dest


def cmd_lingue(args, stampa=print):
    import importa
    s = stato_lingue(leggi_cfg())
    if not s["tesseract"]:
        stampa(f"Tesseract non trovato: {importa.come_installare_tesseract()}")
        return 1
    stampa(f"Tesseract: {s['tesseract']}\nModelli delle lingue: {s['cartella']}"
           + ("" if s["scrivibile"] else " (non scrivibile: serve l'amministratore)"))
    stampa("Installate: " + (", ".join(s["installate"]) or "nessuna"))
    stampa("Richieste dalle serie del progetto: " + ", ".join(s["richieste"]))
    codici = list(dict.fromkeys(getattr(args, "codici", None) or []))
    if not codici:
        stampa("Mancano: " + ", ".join(s["mancanti"]) if s["mancanti"] else "Non manca nessuna lingua richiesta.")
        if s["mancanti"] and s["scrivibile"]:
            stampa(f"Per scaricarle: python installa.py lingue {' '.join(s['mancanti'])}")
        return 1 if s["mancanti"] else 0
    if not s["scrivibile"]:
        stampa(importa.AIUTO_LINGUE.format(", ".join(codici)))
        return 1
    esito = 0
    for c in codici:
        try:
            importa.scarica_lingua(c, s["cartella"], stampa=stampa)
        except (ValueError, OSError) as e:
            stampa(f"{c}: non scaricata ({e})")
            esito = 1
    return esito


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
    intestazioni["User-Agent"] = "Pressmark/1.0"
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
    controlla_pywebview(esito)
    controlla_tesseract(esito, cfg)
    stampa("")
    if esito.mancanti:
        stampa("Manca: " + ", ".join(v.strip() for v in esito.mancanti) + ".")
        return 1
    stampa("Requisiti necessari presenti. Per aprire l'interfaccia: python app.py")
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


# ---------------------------------------------------------------- profili di modello
FILE_CONFIG = posizioni.file_config()
NOME_PROFILO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# servizi con una sola chiave: nome, indirizzo, variabile della chiave, modello proposto, pausa, dove si prende la chiave
SERVIZI_CHIAVE = [
    ("Groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", "qwen/qwen3.8-27b", "6",
     "https://console.groq.com/keys"),
    ("Google Gemini", "https://generativelanguage.googleapis.com/v1beta/openai", "GEMINI_API_KEY",
     "gemini-3.8-flash", "5", "https://aistudio.google.com/apikey"),
    ("OpenRouter", "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "", "3.5", "https://openrouter.ai/keys"),
    # a consumo o con piano gratuito: il modello si sceglie dall'elenco del servizio, non lo proponiamo noi
    ("OpenAI", "https://api.openai.com/v1", "OPENAI_API_KEY", "", "0", "https://platform.openai.com/api-keys"),
    ("Mistral", "https://api.mistral.ai/v1", "MISTRAL_API_KEY", "", "1", "https://console.mistral.ai/api-keys"),
    ("xAI", "https://api.x.ai/v1", "XAI_API_KEY", "", "0", "https://console.x.ai"),
    ("MiniMax", "https://api.minimax.io/v1", "MINIMAX_API_KEY", "", "0", "https://platform.minimax.io"),
    ("Hugging Face", "https://router.huggingface.co/v1", "HF_TOKEN", "", "1", "https://huggingface.co/settings/tokens"),
    ("NVIDIA NIM", "https://integrate.api.nvidia.com/v1", "NVIDIA_API_KEY", "", "1.5", "https://build.nvidia.com"),
]
# servizi che elencano i modelli anche con una chiave sbagliata: l'elenco non prova la chiave
ELENCO_SENZA_CHIAVE = {"Hugging Face", "NVIDIA NIM"}


def leggi_cfg():
    from progetto import leggi_config
    return leggi_config(FILE_CONFIG)


def oggi():
    return dt.date.today().isoformat()


def copia_di_sicurezza(f):
    """Copia accanto al file (<file>.pressmark-<data>.bak, esclusa da git); None se il file non c'è."""
    if not f.exists():
        return None
    dest = f.with_name(f"{f.name}.pressmark-{oggi()}.bak")
    n = 2
    while dest.exists():
        dest = f.with_name(f"{f.name}.pressmark-{oggi()}-{n}.bak")
        n += 1
    shutil.copy2(f, dest)
    return dest


def _leggi_testo(f):
    dati = f.read_bytes() if f.exists() else b""
    testo = dati.decode("utf-8-sig")
    return testo, dati.startswith(codecs.BOM_UTF8), "\r\n" if "\r\n" in testo else "\n"


def _scrivi_testo(f, righe, bom, nl):
    f.parent.mkdir(parents=True, exist_ok=True)      # la cartella dei dati dell'utente, al primo salvataggio
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


def rinomina_profilo(f, vecchio, nuovo):
    """Cambia solo l'intestazione della sezione: voci e commenti restano dove sono."""
    testo, bom, nl = _leggi_testo(f)
    righe = testo.splitlines()
    inizio, _fine = _limiti_sezione(righe, vecchio)
    if inizio is None:
        return False
    righe[inizio] = f"[{nuovo}]"
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


def fornitore(p):
    """Chi fornisce il modello di un profilo, per raggrupparli nell'interfaccia. «servizio» dice il protocollo, non il
    fornitore (Groq, Gemini e OpenRouter sono tutti «openai»): per quelli conta l'indirizzo. «servizio_id» è la voce
    della procedura «Aggiungi modello» che crea un profilo dello stesso fornitore."""
    import urllib.parse
    servizio = p.get("servizio", "")
    if servizio == "ollama":
        return {"id": "ollama", "nome": "Ollama", "servizio_id": "ollama", "dove_chiave": ""}
    if servizio == "anthropic":
        return {"id": "anthropic", "nome": "Anthropic", "servizio_id": "anthropic",
                "dove_chiave": "https://console.anthropic.com/settings/keys"}
    if servizio == "router":
        return {"id": "freellmapi", "nome": "FreeLLMAPI", "servizio_id": "router", "dove_chiave": ""}
    host = urllib.parse.urlsplit(p.get("url", "")).hostname or ""
    for n, url, _env, _modello, _pausa, dove in SERVIZI_CHIAVE:
        if host and host == urllib.parse.urlsplit(url).hostname:
            return {"id": n.lower().replace(" ", "-"), "nome": n, "servizio_id": f"chiave:{n}", "dove_chiave": dove}
    return {"id": "openai:" + host, "nome": host or "Servizio compatibile OpenAI", "servizio_id": "openai",
            "dove_chiave": ""}


# Interruttori (config.ini, sezione [disattivati]): fornitori, chiavi (per nome della variabile) e profili spenti.
# Spento non vuol dire tolto: il profilo resta in models.ini e la chiave nella sua variabile, ma non si sceglie.
SEZIONE_SPENTI = "disattivati"
TIPI_SPENTI = {"fornitore": "fornitori", "chiave": "chiavi", "profilo": "profili"}


def spenti(cfg):
    """{"fornitori": set, "chiavi": set, "profili": set} dalla sezione [disattivati] (voci separate da virgole)."""
    out = {}
    for voce in TIPI_SPENTI.values():
        testo = cfg.get(SEZIONE_SPENTI, voce, fallback="") if cfg.has_section(SEZIONE_SPENTI) else ""
        out[voce] = {x.strip() for x in testo.split(",") if x.strip()}
    return out


def env_chiave(p):
    return p.get("chiave_env", "") or ("ANTHROPIC_API_KEY" if p.get("servizio") == "anthropic" else "")


def motivo_spento(nome, p, s):
    """Perché un profilo non si può scegliere: "" se si può, altrimenti la spiegazione."""
    if nome in s["profili"]:
        return f"il modello «{nome}» è spento"
    f = fornitore(p)
    if f["id"] in s["fornitori"]:
        return f"il fornitore {f['nome']} è spento"
    env = env_chiave(p)
    if env and env in s["chiavi"]:
        return f"la chiave {env} è spenta"
    return ""


def stato_profili(cfg):
    """Profili, scelta per ruolo, chiavi e misure, come dati (per lo strumento «modello» della conversazione)."""
    from llm import RUOLI, ErroreModello, file_profili, leggi_profili, nome_scelto, profilo, usa_profili
    from progetto import NessunProgetto, percorso
    from sintesi import modelli_misurati, profili_misurati
    try:
        misurati = modelli_misurati(percorso(cfg, "risultati"))
        coppie = profili_misurati(percorso(cfg, "risultati"))
    except NessunProgetto:
        misurati, coppie = set(), set()
    scelti = {r: nome_scelto(cfg, r) for r in RUOLI}
    s = spenti(cfg)
    out = {"file_profili": str(file_profili(cfg)), "profili": []}
    for nome, p in leggi_profili(cfg).items():
        env = env_chiave(p)
        voce = {"nome": nome, "servizio": p.get("servizio", ""), "modello": p.get("modello", ""),
                "chiave": ("presente" if os.environ.get(env) else "assente") if env else "non serve",
                "chiave_env": env, "fornitore": fornitore(p), "url": p.get("url", ""),
                "in_uso_per": [r for r in RUOLI if scelti[r] == nome],
                "spento": nome in s["profili"], "bloccato": motivo_spento(nome, p, s)}
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
    «default» (callable): procedura guidata che chiede il nome quando args.nome manca (avvio guidato)."""
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
    motivo = motivo_spento(nome, leggi_profili(cfg)[nome], spenti(cfg))
    if motivo:
        stampa(f"Non si può scegliere «{nome}»: {motivo} (sezione [{SEZIONE_SPENTI}] di config.ini, o le "
               "Impostazioni dell'interfaccia).")
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
    cp.read(posizioni.file_letti(FILE_CONFIG), encoding="utf-8")
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
        "User-Agent": "Pressmark/1.0", **({"Authorization": f"Bearer {chiave}"} if chiave else {})})
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
        "Un servizio con una sola chiave (Groq, Gemini, OpenAI, Mistral, OpenRouter e altri compatibili OpenAI)",
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


# ---------------------------------------------------------------- avvio guidato
PASSI = {1: "ambiente", 2: "modello", 3: "progetto", 4: "riepilogo"}


def scegli_passi(args, stampa):
    """Quali passi eseguire, in ordine, dai numeri dati (--passi e --saltati); None se i numeri non valgono."""
    def numeri(testo, nome):
        try:
            v = {int(x) for x in testo.replace(" ", ",").split(",") if x.strip()}
        except ValueError:
            stampa(f"--{nome}: scrivi numeri da 1 a 4 separati da virgola (es. 2,3).")
            return False
        if not v <= set(PASSI):
            stampa(f"--{nome}: i passi sono solo 1-4 ({', '.join(f'{n} {t}' for n, t in PASSI.items())}).")
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
    if 4 not in scelti:
        scelti.add(4)                     # il riepilogo finale si fa sempre: costa niente e riassume lo stato
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
    return 1 if esito.mancanti else 0


def guida_modello(stampa, chiedi=input):
    """Passo 2: scelta del modello che legge i passaggi. 0 fatto o non necessario, 1 fallito o saltato."""
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


def progetto_esiste(radice):
    """Vero se la cartella è un progetto (c'è project.ini): una cartella indicata ma assente non conta."""
    return radice is not None and (Path(radice) / "project.ini").is_file()


def cartella_progetti():
    return posizioni.cartella_progetti()


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


def riepilogo(stampa):
    """Passo 4: che cosa è installato, dove sta il progetto, prossimo passo. Rifà tutti i controlli necessari
    (come «controlla»): 0 se non manca nulla, 1 altrimenti."""
    from llm import RUOLI, ErroreModello, profilo, usa_profili
    from progetto import cartella_scelta, nome
    cfg = leggi_cfg()
    controlli = Esito(lambda riga: None)
    controlla_python(controlli)
    controlla_sqlite(controlli)
    controlla_modelli(controlli, cfg)
    controlla_progetto(controlli, cfg)
    stampa("\n=== Riepilogo ===")
    stampa(f"- Motore: {CARTELLA} (Python {sys.version_info.major}.{sys.version_info.minor})")
    stampa(f"- Configurazione: {FILE_CONFIG}" + (" (sopra i valori predefiniti del programma)"
                                                   if posizioni.installato() else ""))
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
    if controlli.mancanti:
        stampa("- Manca ancora: " + ", ".join(v.strip() for v in controlli.mancanti) +
               " (dettagli: python installa.py controlla)")
        return 1
    stampa("- Interfaccia nel browser (menu Progetto e Modello, ricerca guidata, importazione): python app.py")
    stampa("- Prossimo passo: importa le fonti con la tabella di revisione: python importa.py proponi <cartella dei "
           "documenti>, controlla la tabella in Excel o LibreOffice, poi python importa.py applica <tabella> (o "
           "dall'interfaccia); vedi docs/quickstart.it.md (in inglese docs/quickstart.md) e «Importare "
           "nuove fonti» in docs/user_guide.it.md")
    return 0


def cmd_inizia(args, stampa=print, chiedi=input, funzioni=None, riepilogo_fn=None):
    """Avvio guidato: i quattro passi. Si interrompe e riprende senza rifare i passi
    già completati (ognuno riconosce il proprio stato); ogni passo si può saltare (--saltati, o rispondendo
    «no» alle domande). «funzioni» e «riepilogo_fn» servono solo ai test."""
    sys.path.insert(0, str(CARTELLA))
    passi = scegli_passi(args, stampa)
    if passi is None:
        return 2
    stampa("Pressmark — avvio guidato (puoi interrompere con Ctrl+C e riprendere: i passi già fatti non si "
           "rifanno)\n")
    esiti = {}
    si = getattr(args, "si", False)
    default = {1: lambda: stato_ambiente(args, stampa),
               2: lambda: guida_modello(stampa, chiedi),
               3: lambda: guida_progetto(stampa, chiedi, si=si)}
    funzioni = funzioni or default
    for n in passi:
        if n == 4:
            continue
        titolo = {1: "Controllo dell'ambiente", 2: "Modello che legge i passaggi",
                  3: "Il tuo primo progetto"}[n]
        stampa(f"\n--- Passo {n} di 4: {titolo} ---")
        esiti[n] = funzioni[n]()
        if esiti[n] != 0 and n == 1:
            stampa("\nManca qualcosa di necessario: sistema seguendo le indicazioni qui sopra e rilancia "
                   "«python installa.py inizia»: i passi già completati non verranno rifatti.")
            return 1
    completo = (riepilogo_fn or riepilogo)(stampa) == 0
    blocco = [n for n in (1, 2, 3) if n in esiti and esiti[n] != 0]
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
    sub.add_parser("controlla")
    sub.add_parser("librerie")
    m = sub.add_parser("modello", help="profili dei modelli: nuovo, elenca, usa, prova, togli, converti")
    m.add_argument("azione", nargs="?", default="nuovo", choices=list(AZIONI_MODELLO))
    m.add_argument("nome", nargs="?", help="nome del profilo (usa, prova, togli)")
    m.add_argument("--ruolo", action="append", choices=["smistamento", "analisi", "sintesi"],
                   help="usa: solo per questo ruolo (ripetibile); senza, per tutti")
    m.add_argument("--progetto", action="store_true", help="usa: scelta nel project.ini del progetto in uso")
    m.add_argument("--si", action="store_true", help="togli, converti: niente domanda di conferma")
    g = sub.add_parser("lingue", help="lingue OCR: stato; con i codici, le scarica (Tesseract incluso nel programma)")
    g.add_argument("codici", nargs="*", help="codici Tesseract da scaricare, es. sqi chi_sim")
    i = sub.add_parser("inizia", help="avvio guidato: ambiente, modello, primo progetto, riepilogo")
    i.add_argument("--passi", default="", help="solo questi passi, numeri da 1 a 4 separati da virgola (es. 2,3)")
    i.add_argument("--saltati", default="", help="tutti tranne questi (es. --saltati 2 per non toccare il modello)")
    i.add_argument("--si", action="store_true", help="nei passi automatici nessuna domanda di conferma")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    if args.comando is None:
        args.comando = "controlla"
    return {"controlla": cmd_controlla, "librerie": cmd_librerie,
            "modello": cmd_modello, "inizia": cmd_inizia, "lingue": cmd_lingue}[args.comando](args)


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Importazione di nuovo materiale nelle fonti: PDF (con o senza testo), scansioni (jpg, png, tif) e testi (.txt).

Per ogni documento:
  1. prende il testo del PDF quando c'è; altrimenti fa l'OCR della pagina con Tesseract (gratuito, sul tuo PC);
  2. scrive in data\\<cartella della serie> un file .txt con l'intestazione dei metadati
     ([SERIES], [DATE], [FULL_CITATION], [LANG]...), come le fonti già presenti;
  3. registra in importazioni\\registro.csv metodo, pagine, qualità dell'OCR e avvisi;
  4. aggiorna l'indice delle fonti (solo i file nuovi).
Le serie (testate, raccolte) sono descritte in serie.ini.

Uso:
  python importa.py prepara                          controlla Tesseract, PyMuPDF e le lingue dell'OCR
  python importa.py serie                            elenca le serie di serie.ini
  python importa.py importa <file o cartella> --serie "Zëri i Popullit" [opzioni]
  python importa.py controlla [cartella dentro data]  controlla le intestazioni delle fonti

Opzioni di importa:
  --prova N          solo le prime N pagine del primo documento: mostra testo e qualità, non scrive nulla
  --data AAAA-MM-GG  data del documento (per un solo file; altrimenti dal nome del file o dalla prima pagina)
  --numero, --titolo, --autore, --anno, --volume, --luogo, --editore   metadati del documento
  --metadati file.csv   metadati file per file: colonne file, data, numero, titolo, autore, anno, volume...
  --ocr auto|sempre  auto (predefinito) = usa il testo del PDF quando c'è; sempre = rifà l'OCR di ogni pagina
  --unisci           tutti i file indicati diventano un solo documento (es. le foto delle pagine di un numero)
  --sovrascrivi      sostituisce i documenti già importati con lo stesso nome
  --processi N       pagine lette in parallelo (predefinito: metà dei processori)
  --senza-indice     non aggiorna l'indice alla fine
"""
import argparse
import configparser
import csv
import datetime as dt
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARTELLA))
from estrai_occorrenze import (HDR, STATI_CAMPO, leggi_intestazione, stato_attivo,
                           stato_del_valore, nota_del_campo)   # noqa: E402

PDF = {".pdf"}
IMMAGINI = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".jp2"}
TESTI = {".txt"}
LINGUE_OCR = {"sq": "sqi", "it": "ita", "fr": "fra", "en": "eng", "de": "deu", "es": "spa", "ru": "rus",
              "zh": "chi_sim", "pt": "por", "nl": "nld", "el": "ell", "tr": "tur", "mk": "mkd", "sr": "srp_latn",
              "bg": "bul", "ro": "ron", "pl": "pol", "cs": "ces", "hu": "hun", "sv": "swe", "da": "dan"}
MESI_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
           "ottobre", "novembre", "dicembre"]
# nomi dei mesi nelle lingue più probabili delle fonti (per riconoscere la data stampata in testata)
MESI = {}
for _n, _nomi in enumerate([
        "janar january janvier gennaio januar enero", "shkurt february février fevrier febbraio februar febrero",
        "mars march mars marzo märz marz", "prill april avril aprile abril",
        "maj may mai maggio mayo", "qershor june juin giugno juni junio",
        "korrik july juillet luglio juli julio", "gusht august août aout agosto",
        "shtator september septembre settembre septiembre", "tetor october octobre ottobre oktober octubre",
        "nëntor nentor november novembre noviembre", "dhjetor december décembre decembre dicembre dezember diciembre"],
        1):
    for _m in _nomi.split():
        MESI[_m] = _n
SOGLIA_TESTO_PDF = 200       # caratteri alfanumerici per pagina sotto i quali il testo del PDF non basta
SOGLIA_DEBOLE = 60           # confidenza media dell'OCR sotto la quale una pagina va controllata


# ---------------------------------------------------------------- configurazione
def leggi_config():
    from llm import leggi_config as lc
    return lc()


def radice(cfg):
    from llm import percorso
    return percorso(cfg, "dati").resolve().parent


def leggi_serie():
    cp = configparser.ConfigParser(interpolation=None, delimiters=("=",), inline_comment_prefixes=None)
    cp.optionxform = str
    cp.read(CARTELLA / "serie.ini", encoding="utf-8")
    return cp


def aggiungi_serie(nome, tipo, lingua, cartella, citazione, sigla="", nota_limiti="", **fissi):
    """Aggiunge una serie a serie.ini (senza toccare le altre). Restituisce un messaggio."""
    cp = leggi_serie()
    if cp.has_section(nome):
        return f"La serie «{nome}» c'è già in serie.ini."
    if tipo not in ("periodico", "volume"):
        return "tipo deve essere «periodico» o «volume»."
    if not re.fullmatch(r"[a-z]{2,3}", lingua or ""):
        return "lingua: codice di due lettere (sq, it, fr, en...)."
    cartella = cartella.replace("\\", "/").strip("/")
    if ".." in cartella or not cartella:
        return "cartella: percorso dentro data, ad es. riviste/nome_testata."
    righe = [f"\n[{nome}]", f"tipo = {tipo}", f"lingua = {lingua}", f"cartella = {cartella}"]
    if sigla:
        righe.append(f"sigla = {sigla}")
    righe.append(f"citazione = {citazione}")
    for k, v in fissi.items():
        if v:
            righe.append(f"{k} = {v}")
    if nota_limiti:
        righe.append(f"nota_limiti = {nota_limiti}")
    with open(CARTELLA / "serie.ini", "a", encoding="utf-8") as f:
        f.write("\n".join(righe) + "\n")
    return f"Serie «{nome}» aggiunta a serie.ini."


def cerca_tesseract(cfg):
    if cfg.has_option("ocr", "tesseract") and cfg.get("ocr", "tesseract").strip():
        p = Path(cfg.get("ocr", "tesseract").strip())
        return str(p) if p.exists() else None
    trovato = shutil.which("tesseract")
    if trovato:
        return trovato
    for p in [Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Tesseract-OCR" / "tesseract.exe",
              Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Tesseract-OCR" / "tesseract.exe",
              Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Tesseract-OCR" / "tesseract.exe"]:
        if p.exists():
            return str(p)
    return None


def cartella_modelli(cfg):
    """Cartella dei modelli delle lingue indicata in config.ini ([ocr] modelli); None = quella di Tesseract
    (installazione di sistema, o la variabile TESSDATA_PREFIX)."""
    if cfg.has_option("ocr", "modelli") and cfg.get("ocr", "modelli").strip():
        p = Path(cfg.get("ocr", "modelli").strip())
        return p if p.is_absolute() else (CARTELLA / p).resolve()
    return None


def lingue_installate(exe, modelli=None):
    cmd = [exe, "--list-langs"] + (["--tessdata-dir", str(modelli)] if modelli else [])
    r = subprocess.run(cmd, capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    righe = (r.stdout + r.stderr).decode("utf-8", "replace").splitlines()
    return {l.strip() for l in righe if l.strip() and " " not in l.strip() and not l.strip().endswith(":")}


AIUTO_LINGUE = ("Mancano i modelli OCR di: {}. Installali nel sistema: riesegui l'installazione di Tesseract "
                "(UB Mannheim) e in «Additional language data» spunta le lingue (Albanian per sqi); oppure copia "
                "<lingua>.traineddata da https://github.com/tesseract-ocr/tessdata_best nella cartella tessdata "
                "di Tesseract (es. C:\\Program Files\\Tesseract-OCR\\tessdata, serve l'amministratore).")


def lingue_ocr(scheda, override=None):
    if override:
        return override
    if scheda.get("ocr_lingue"):
        return scheda["ocr_lingue"]
    l = scheda.get("lingua", "en")
    return LINGUE_OCR.get(l, l)


# ---------------------------------------------------------------- OCR
class Ocr:
    def __init__(self, cfg, lingue, dpi=300):
        self.exe = cerca_tesseract(cfg)
        if not self.exe:
            raise SystemExit("Tesseract non trovato. Installalo (gratuito): winget install -e --id "
                             "UB-Mannheim.TesseractOCR  — poi riapri il Prompt dei comandi. "
                             "Oppure indica il percorso in config.ini, sezione [ocr], voce tesseract.")
        self.lingue, self.dpi = lingue, dpi
        self.modelli = cartella_modelli(cfg)
        presenti = lingue_installate(self.exe, self.modelli)
        mancanti = [l for l in lingue.split("+") if l and l not in presenti]
        if mancanti:
            raise SystemExit(AIUTO_LINGUE.format(", ".join(mancanti)))
        # 1 = segmentazione automatica con orientamento della pagina (serve il modello osd), altrimenti 3
        self.psm = "1" if "osd" in presenti else "3"
        self.env = dict(os.environ, OMP_THREAD_LIMIT="1")

    def leggi_immagine(self, img):
        """(testo, confidenza media 0-100, parole) di un'immagine."""
        cmd = [self.exe, str(img), "stdout"] + (["--tessdata-dir", str(self.modelli)] if self.modelli else []) + \
              ["-l", self.lingue, "--psm", self.psm, "-c", "tessedit_create_tsv=1"]
        r = subprocess.run(cmd, capture_output=True, env=self.env, timeout=900,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            raise RuntimeError(r.stderr.decode("utf-8", "replace").strip()[-400:])
        return da_tsv(r.stdout.decode("utf-8", "replace"))


def da_tsv(tsv):
    """Ricompone il testo dall'uscita TSV di Tesseract: una riga per riga stampata, una riga vuota tra i
    paragrafi; calcola la confidenza media pesata sulla lunghezza delle parole."""
    righe, chiave_prec, par_prec, riga = [], None, None, []
    somma = peso = 0
    for l in tsv.splitlines()[1:]:
        c = l.split("\t")
        if len(c) < 12 or c[0] != "5":
            continue
        parola = c[11].strip()
        if not parola:
            continue
        par = (c[1], c[2], c[3])
        chiave = par + (c[4],)
        if chiave != chiave_prec and riga:
            righe.append(" ".join(riga))
            riga = []
            if par != par_prec:
                righe.append("")
        chiave_prec, par_prec = chiave, par
        riga.append(parola)
        try:
            conf = float(c[10])
        except ValueError:
            conf = -1
        if conf >= 0:
            somma += conf * len(parola)
            peso += len(parola)
    if riga:
        righe.append(" ".join(riga))
    testo = "\n".join(righe).strip()
    testo = re.sub(r"\n{3,}", "\n\n", testo)
    return testo, (round(somma / peso, 1) if peso else 0.0), len(testo.split())


def carica_pymupdf():
    try:
        import pymupdf
        return pymupdf
    except ImportError:
        import fitz
        return fitz


def testo_utile(t):
    return sum(1 for ch in t if ch.isalnum())


def leggi_documento(percorsi, ocr_fn, modo="auto", processi=2, cache=None, stampa=print, max_pagine=None):
    """Legge uno o più file (unendoli nell'ordine dato). Restituisce (testo, rapporto).
    Le pagine senza testo si rendono come immagini e si passano a Tesseract poche alla volta (in parallelo),
    così anche un volume di centinaia di pagine non riempie il disco; le pagine già lette restano nella cache
    e, se l'importazione si interrompe, alla ripresa non si rileggono."""
    from collections import deque
    pagine = []          # [chiave, testo, metodo, confidenza]
    tmp = Path(tempfile.mkdtemp(prefix="importa_"))
    attesa = deque()
    stato = {"fatti": 0, "t0": time.time(), "annunciato": False}

    def uno(i, img, k, temporanea):
        try:
            testo, conf, _ = ocr_fn.leggi_immagine(img)
        finally:
            if temporanea:
                Path(img).unlink(missing_ok=True)
        if cache and k:
            (cache / f"{k:05d}.txt").write_text(testo, encoding="utf-8")
            (cache / f"{k:05d}.conf").write_text(str(conf))
        return i, testo, conf

    def raccogli(fut):
        i, testo, conf = fut.result()
        pagine[i][1], pagine[i][3] = testo, conf
        stato["fatti"] += 1
        if stato["fatti"] % 10 == 0:
            stampa(f"    {stato['fatti']} pagine lette con l'OCR ({time.time() - stato['t0']:.0f} s)")

    def invia(ex, img, k, temporanea):
        if not stato["annunciato"]:
            stampa(f"  OCR ({ocr_fn.lingue}, {processi} pagine alla volta) ...")
            stato["annunciato"] = True
        pagine.append([f"{img.name}" if not k else None, None, "ocr", None])
        attesa.append(ex.submit(uno, len(pagine) - 1, img, k, temporanea))
        while len(attesa) >= 3 * processi:
            raccogli(attesa.popleft())

    try:
        with ThreadPoolExecutor(max_workers=max(1, processi)) as ex:
            for p in percorsi:
                if max_pagine and len(pagine) >= max_pagine:
                    break
                ext = p.suffix.lower()
                if ext in TESTI:
                    t = p.read_text(encoding="utf-8", errors="replace")
                    meta, pos = leggi_intestazione(t)
                    pagine.append([p.name, t[pos:].strip(), "testo", None])
                elif ext in IMMAGINI:
                    invia(ex, p, None, False)
                    pagine[-1][0] = p.name
                elif ext in PDF:
                    fitz = carica_pymupdf()
                    with fitz.open(p) as doc:
                        for k, pag in enumerate(doc, 1):
                            if max_pagine and len(pagine) >= max_pagine:
                                break
                            chiave = f"{p.name} p.{k}"
                            t = pag.get_text("text") if modo != "sempre" else ""
                            if testo_utile(t) >= SOGLIA_TESTO_PDF:
                                pagine.append([chiave, t.strip(), "testo del PDF", None])
                                continue
                            if cache and (cache / f"{k:05d}.conf").exists():
                                pagine.append([chiave, (cache / f"{k:05d}.txt").read_text(encoding="utf-8"), "ocr",
                                               float((cache / f"{k:05d}.conf").read_text() or 0)])
                                continue
                            img = tmp / f"{k:05d}.png"
                            pag.get_pixmap(dpi=ocr_fn.dpi, colorspace=fitz.csGRAY).save(img)
                            invia(ex, img, k, True)
                            pagine[-1][0] = chiave
            while attesa:
                raccogli(attesa.popleft())
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if stato["fatti"]:
        stampa(f"    {stato['fatti']} pagine lette con l'OCR in {time.time() - stato['t0']:.0f} s")
    testo = "\n\n".join(t for _, t, _, _ in pagine if t)
    confs = [c for *_, c in pagine if c is not None]
    metodi = sorted({m for _, _, m, _ in pagine})
    rapporto = {"pagine": len(pagine), "pagine_ocr": len(confs), "metodo": " + ".join(metodi) or "nessuno",
                "confidenza": round(sum(confs) / len(confs), 1) if confs else None,
                "pagine_deboli": [k for k, _, _, c in pagine if c is not None and c < SOGLIA_DEBOLE],
                "pagine_vuote": [k for k, t, _, _ in pagine if not (t or "").strip()]}
    return testo, rapporto


# ---------------------------------------------------------------- metadati
def data_da_testo(s):
    """Data ISO (AAAA-MM-GG, AAAA-MM o AAAA) in un nome di file o in una stringa; "" se manca."""
    s = s.replace("_", "-")
    m = re.search(r"(?<!\d)(1[89]\d\d|20\d\d)[-. ]?([01]\d)[-. ]?([0-3]\d)(?!\d)", s)
    if m and valida(m.group(1), m.group(2), m.group(3)):
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(?<!\d)([0-3]?\d)[-. /]([01]?\d)[-. /](1[89]\d\d|20\d\d)(?!\d)", s)
    if m and valida(m.group(3), m.group(2), m.group(1)):
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    m = re.search(r"(?<!\d)([0-3]?\d)\s*\.?\s*([A-Za-zëçéèûô]{3,10})\.?\s*(1[89]\d\d|20\d\d)(?!\d)", s, re.I)
    if m and m.group(2).lower() in MESI and valida(m.group(3), MESI[m.group(2).lower()], m.group(1)):
        return f"{m.group(3)}-{MESI[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    m = re.search(r"(?<!\d)(1[89]\d\d|20\d\d)[-. ]([01]\d)(?!\d)", s)
    if m and 1 <= int(m.group(2)) <= 12:
        return f"{m.group(1)}-{m.group(2)}"
    return ""


def valida(a, m, g):
    try:
        dt.date(int(a), int(m), int(g))
        return True
    except ValueError:
        return False


def data_it(iso):
    p = iso.split("-")
    try:
        if len(p) == 3:
            return f"{int(p[2])} {MESI_IT[int(p[1]) - 1]} {p[0]}"
        if len(p) == 2:
            return f"{MESI_IT[int(p[1]) - 1]} {p[0]}"
    except (ValueError, IndexError):
        pass
    return iso


def numero_da_nome(nome):
    m = re.search(r"(?:^|[-_ ])(?:n|nr|no|numri)[-_. ]?(\d{1,4})(?!\d)", nome, re.I)
    return m.group(1) if m else ""


def componi(modello, valori):
    """Riempie il modello di citazione; un tratto tra [ ] sparisce se uno dei suoi segnaposto è vuoto."""
    def opzionale(m):
        pezzo = m.group(1)
        chiavi = re.findall(r"\{(\w+)\}", pezzo)
        return pezzo.format_map(valori) if all(valori.get(k) for k in chiavi) else ""
    s = re.sub(r"\[([^\]]*)\]", opzionale, modello)
    s = re.sub(r"\{(\w+)\}", lambda m: str(valori.get(m.group(1)) or ""), s)
    s = re.sub(r"\s+,", ",", s)
    s = re.sub(r",\s*,", ",", s)
    s = re.sub(r":\s*,", ",", s)
    return re.sub(r"\s{2,}", " ", s).strip(" ,:")


def nome_file(scheda, serie, valori, origine):
    if scheda.get("tipo", "periodico") == "periodico":
        sigla = scheda.get("sigla") or re.sub(r"[^A-Z]", "", serie.upper())[:4] or "DOC"
        base = sigla + (valori.get("data_iso") or "s.d.")
        if valori.get("numero") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", valori.get("data_iso") or ""):
            base += f"-n{valori['numero']}"
        if not valori.get("data_iso") and not valori.get("numero"):
            base += "-" + re.sub(r"[^\w\-]+", "_", origine)[:60]
        return base + ".txt"
    titolo = valori.get("titolo") or origine
    if valori.get("volume"):
        titolo += f" vol. {valori['volume']}"
    return re.sub(r'[\\/:*?"<>|]+', "_", titolo).strip()[:150] + ".txt"


def intestazione(serie, scheda, valori, rapporto, origine, nome):
    data = valori.get("data_iso", "")
    righe = [
        ("DOC_ID", Path(nome).stem),
        ("SERIES", serie),
        ("YEAR", valori.get("anno") or data[:4]),
        ("ISSUE", valori.get("numero", "")),
        ("VOLUME", valori.get("volume", "")),
        ("DATE", data if re.fullmatch(r"\d{4}-\d{2}-\d{2}", data) else ""),
        ("DATE_STATUS", valori.get("stato_data", "")),
        ("DATE_NOTE", valori.get("nota_data", "") if valori.get("stato_data") else ""),
        ("AUTHOR", valori.get("autore", "")),
        ("TITLE", valori.get("titolo", "") if scheda.get("tipo") == "volume" else ""),
        ("PUBLISHER", valori.get("editore", "")),
        ("PUBLICATION_PLACE", valori.get("luogo", "")),
        ("LANG", scheda.get("lingua", "")),
        ("SOURCE_FILE", origine),
        ("METADATA_SOURCE", f"importa.py {dt.date.today().isoformat()} ({rapporto['metodo']})"),
        ("OCR_CONFIDENCE", "" if rapporto["confidenza"] is None else str(rapporto["confidenza"])),
        ("FULL_CITATION", valori["citazione"]),
    ]
    # ISSUE_STATUS/ISSUE_NOTE solo se il numero è stato dedotto dal nome del file (lavoro 8, punto 4);
    # un campo senza _STATUS vale «verificato», quindi i campi dell'operatore non ricevono stati espliciti
    if valori.get("stato_numero"):
        righe += [("ISSUE_STATUS", valori["stato_numero"]), ("ISSUE_NOTE", valori.get("nota_numero", ""))]
    return "".join(f"[{k}: {v}]\n" for k, v in righe if v != "" or k in ("FULL_CITATION", "SERIES")) + "\n"


def valori_documento(serie, scheda, args, riga_csv, origine, testo):
    v = {"serie": serie}
    for k in ("autore", "titolo", "luogo", "editore", "anno", "volume"):
        v[k] = scheda.get(k, "")
    for k in ("autore", "titolo", "luogo", "editore", "anno", "volume", "numero"):
        if getattr(args, k, None):
            v[k] = getattr(args, k)
        if riga_csv.get(k):
            v[k] = riga_csv[k].strip()
    data, provenienza = "", ""
    if riga_csv.get("data"):
        data, provenienza = data_da_testo(riga_csv["data"]) or riga_csv["data"].strip(), "dal file dei metadati"
    elif args.data:
        data, provenienza = data_da_testo(args.data) or args.data, "indicata all'importazione"
    elif scheda.get("tipo", "periodico") == "periodico":
        data = data_da_testo(Path(origine).stem)
        if data:
            provenienza = "dal nome del file"
        else:
            data = data_da_testo(testo[:1500])
            if data:
                provenienza = "letta nella prima pagina (OCR): da controllare"
    # stato ricavato dal metodo di rilevamento (lavoro 8, punto 4): --data e il file dei metadati sono scelte
    # dell'operatore -> campo verificato (senza _STATUS); gli altri metodi no
    if provenienza == "dal nome del file":
        stato = "dedotto"
    elif "controllare" in provenienza:
        stato = "da verificare"
    else:
        stato = ""
    if scheda.get("tipo", "periodico") == "periodico" and not v.get("numero"):
        v["numero"] = numero_da_nome(Path(origine).stem)
        if v["numero"]:
            v["stato_numero"], v["nota_numero"] = "dedotto", "ricavato dal nome del file"
    v["data_iso"], v["stato_data"], v["nota_data"] = data, stato, provenienza
    if not v.get("anno") and data[:4].isdigit():
        v["anno"] = data[:4]
    v["data"] = data_it(data) if data else ("" if scheda.get("tipo") == "volume" else "s.d.")
    # FULL_CITATION in stile Chicago, se la serie ha il modello "chicago" (senza pagina: vale per il file)
    if scheda.get("chicago"):
        from citazioni import valori_da_intestazione, componi as componi_chicago
        meta = {"SERIES": serie, "TITLE": v.get("titolo", ""), "AUTHOR": v.get("autore", ""),
                "VOLUME": v.get("volume", ""), "ISSUE": v.get("numero", ""), "YEAR": v.get("anno", ""),
                "DATE": data if re.fullmatch(r"\d{4}-\d{2}-\d{2}", data) else "",
                "PUBLICATION_PLACE": v.get("luogo", ""), "PUBLISHER": v.get("editore", "")}
        v["citazione"] = componi_chicago(scheda["chicago"], dict(valori_da_intestazione(meta, scheda), pagina=""))
    else:
        v["citazione"] = componi(scheda.get("citazione") or "{serie}, {data}", v)
    return v


def registra(cfg, riga):
    f = radice(cfg) / "importazioni" / "registro.csv"
    f.parent.mkdir(parents=True, exist_ok=True)
    nuovo = not f.exists()
    campi = ["quando", "origine", "destinazione", "serie", "metodo", "pagine", "pagine_ocr", "confidenza",
             "pagine_deboli", "data", "stato_data", "citazione", "avvisi"]
    with open(f, "a", encoding="utf-8-sig" if nuovo else "utf-8", newline="") as out:
        w = csv.DictWriter(out, campi, extrasaction="ignore")
        if nuovo:
            w.writeheader()
        w.writerow(riga)


# ---------------------------------------------------------------- comandi
def raccogli(percorsi):
    out = []
    for p in percorsi:
        p = Path(p)
        if p.is_dir():
            out += sorted(f for f in p.rglob("*") if f.suffix.lower() in PDF | IMMAGINI | TESTI)
        elif p.exists():
            out.append(p)
        else:
            raise SystemExit(f"Non trovo {p}")
    return out


def cmd_importa(args, stampa=print):
    cfg = leggi_config()
    serie_ini = leggi_serie()
    if not serie_ini.has_section(args.serie):
        raise SystemExit(f"La serie «{args.serie}» non è in serie.ini. Serie presenti: "
                         + "; ".join(serie_ini.sections()))
    scheda = dict(serie_ini[args.serie])
    from llm import percorso
    dati = percorso(cfg, "dati").resolve()
    dest = (dati / scheda.get("cartella", "altre_fonti")).resolve()
    if dati not in dest.parents:
        raise SystemExit("La cartella della serie deve stare dentro data.")
    file = raccogli(args.percorsi)
    if not file:
        raise SystemExit("Nessun file da importare (PDF, immagini o .txt).")
    metadati = {}
    if args.metadati:
        with open(args.metadati, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                metadati[Path(r.get("file", "")).name] = {k.strip().lower(): (v or "") for k, v in r.items()}
    gruppi = [file] if args.unisci else [[f] for f in file]
    lingue = lingue_ocr(scheda, args.lingue)
    ocr = None
    if any(f.suffix.lower() in PDF | IMMAGINI for f in file):
        ocr = Ocr(cfg, lingue, args.dpi)
    processi = args.processi or max(1, (os.cpu_count() or 2) // 2)
    cache_radice = radice(cfg) / "importazioni" / "_cache"
    if args.prova:
        g = gruppi[0]
        stampa(f"Prova su {g[0].name}: prime {args.prova} pagine")
        testo, rap = leggi_documento(g, ocr, args.ocr, processi, None, stampa, args.prova)
        v = valori_documento(args.serie, scheda, args, metadati.get(g[0].name, {}), g[0].name, testo)
        stampa(f"\nMetodo: {rap['metodo']}; confidenza media OCR: {rap['confidenza']}; "
               f"pagine deboli: {rap['pagine_deboli'] or 'nessuna'}")
        stampa(f"Data: {v['data_iso'] or 'non trovata'} ({v['stato_data'] or '-'}); citazione: {v['citazione']}")
        stampa(f"File che verrebbe scritto: {dest / nome_file(scheda, args.serie, v, g[0].stem)}")
        stampa("\n--- inizio del testo ---\n" + testo[:3000] + "\n--- fine dell'estratto ---")
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    scritti, saltati, problemi = [], [], []
    for k, g in enumerate(gruppi, 1):
        origine = g[0].name if len(g) == 1 else f"{g[0].name} … {g[-1].name} ({len(g)} file)"
        stampa(f"[{k}/{len(gruppi)}] {origine}")
        firma = hashlib.sha1("|".join(f"{f.resolve()}|{f.stat().st_size}|{int(f.stat().st_mtime)}" for f in g)
                             .encode("utf-8")).hexdigest()[:16]
        cache = cache_radice / firma
        cache.mkdir(parents=True, exist_ok=True)
        try:
            testo, rap = leggi_documento(g, ocr, args.ocr, processi, cache, stampa)
        except Exception as e:
            problemi.append(f"{origine}: {type(e).__name__}: {e}")
            stampa(f"  ERRORE: {type(e).__name__}: {e}")
            continue
        v = valori_documento(args.serie, scheda, args, metadati.get(g[0].name, {}), g[0].name, testo)
        nome = nome_file(scheda, args.serie, v, g[0].stem)
        out = dest / nome
        avvisi = []
        if out.exists() and not args.sovrascrivi:
            saltati.append(nome)
            stampa(f"  già presente: {out.relative_to(dati)} (usa --sovrascrivi per sostituirlo)")
            continue
        if testo_utile(testo) < 100:
            avvisi.append("testo quasi vuoto")
        if rap["confidenza"] is not None and rap["confidenza"] < 70:
            avvisi.append(f"OCR di qualità bassa (confidenza {rap['confidenza']})")
        if rap["pagine_deboli"]:
            avvisi.append(f"{len(rap['pagine_deboli'])} pagine con OCR debole")
        if not v["data_iso"] and scheda.get("tipo", "periodico") == "periodico":
            avvisi.append("data non trovata: aggiungila con --data o --metadati")
        elif v["stato_data"]:
            avvisi.append(f"data con stato «{v['stato_data']}» ({v['nota_data']})")
        tmp = out.with_suffix(".parziale")
        tmp.write_text(intestazione(args.serie, scheda, v, rap, origine, nome) + testo + "\n", encoding="utf-8")
        tmp.replace(out)
        shutil.rmtree(cache, ignore_errors=True)
        scritti.append(nome)
        stampa(f"  -> {out.relative_to(dati)} ({rap['pagine']} pagine, {rap['metodo']}"
               + (f", confidenza {rap['confidenza']}" if rap["confidenza"] is not None else "") + ")"
               + ("; " + "; ".join(avvisi) if avvisi else ""))
        registra(cfg, {"quando": dt.datetime.now().isoformat(timespec="minutes"), "origine": origine,
                       "destinazione": out.relative_to(dati).as_posix(), "serie": args.serie,
                       "metodo": rap["metodo"], "pagine": rap["pagine"], "pagine_ocr": rap["pagine_ocr"],
                       "confidenza": rap["confidenza"], "pagine_deboli": " ".join(rap["pagine_deboli"][:50]),
                       "data": v["data_iso"], "stato_data": v["stato_data"], "citazione": v["citazione"],
                       "avvisi": "; ".join(avvisi)})
    stampa(f"\nImportati {len(scritti)} documenti in {dest.relative_to(dati)}"
           + (f"; {len(saltati)} già presenti" if saltati else "") + (f"; {len(problemi)} errori" if problemi else "")
           + ". Registro: importazioni\\registro.csv")
    for p in problemi:
        stampa(f"  {p}")
    if scritti and not args.senza_indice:
        from indice import Indice, percorso_indice
        ind = Indice(percorso_indice(cfg), dati)
        if ind.pronto():
            ind.aggiorna(stampa=stampa)
        else:
            stampa("Indice assente: python indice.py costruisci")
    return 4 if problemi and not scritti else 0


def cmd_controlla(args, stampa=print, cfg=None):
    """Controlla le intestazioni: errori (da correggere) e avvisi (da guardare).
    'cfg' è facoltativo (config.ini di default); la radice per il CSV di controllo è il genitore di 'dati'."""
    cfg = cfg or leggi_config()
    from llm import percorso
    from citazioni import MARCATORE_PAGINA, marcatori_pagina   # validazione dei marcatori (lavoro 8)
    dati = percorso(cfg, "dati").resolve()
    base = (dati / args.cartella).resolve() if args.cartella else dati
    righe, doc_id, migrazioni = [], {}, []
    file = sorted(base.rglob("*.txt"))
    for f in file:
        rel = f.relative_to(dati).as_posix()
        try:
            t = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            righe.append((rel, "errore", "il file non è in UTF-8"))
            continue
        meta, pos = leggi_intestazione(t)
        if not meta:
            righe.append((rel, "errore", "manca l'intestazione dei metadati"))
            continue
        if not meta.get("FULL_CITATION"):
            righe.append((rel, "errore", "manca [FULL_CITATION]"))
        d = meta.get("DATE", "")
        if d and not (re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) and valida(*d.split("-"))):
            righe.append((rel, "errore", f"[DATE] non valida: {d}"))
        if meta.get("YEAR") and not re.fullmatch(r"\d{4}", meta["YEAR"]):
            righe.append((rel, "avviso", f"[YEAR] non è un anno: {meta['YEAR']}"))
        if d and meta.get("YEAR", d[:4]) != d[:4]:
            righe.append((rel, "avviso", f"[YEAR] {meta.get('YEAR')} diverso dall'anno di [DATE] {d}"))
        if testo_utile(t[pos:]) < 100:
            righe.append((rel, "errore", "testo quasi vuoto"))
        if meta.get("DOC_ID"):
            if meta["DOC_ID"] in doc_id:
                righe.append((rel, "avviso", f"[DOC_ID] uguale a {doc_id[meta['DOC_ID']]}"))
            doc_id.setdefault(meta["DOC_ID"], rel)
        # stati dei campi <CAMPO>_STATUS (lavoro 8): vocabolario chiuso; i valori storici sono tollerati come provenienza
        for campo, valore in meta.items():
            if campo.endswith("_STATUS"):
                s, noto = stato_del_valore(valore)
                if not noto:
                    righe.append((rel, "avviso", f"[{campo}] fuori dal vocabolario ({valore}): stato normalizzato «{s}»"))
        # la migrazione riguarda i valori storici: lo stato è riconosciuto ma il valore non è «noto»
        # (stato_del_valore restituisce noto=False); i valori fuori vocabolario restano un avviso e non si toccano
        prefs = [pref for pref in ("DATE", "ISSUE")
                 if meta.get(pref + "_STATUS")
                 and not stato_del_valore(meta[pref + "_STATUS"])[1]
                 and stato_del_valore(meta[pref + "_STATUS"])[0] in STATI_CAMPO]
        if args.migra_stati and prefs:
            migrazioni.append((f, meta, t, pos, prefs))
        if stato_attivo(meta, "DATE") or meta.get("METADATA_SOURCE") == "filename+local_header":
            righe.append((rel, "avviso", f"data da controllare ({nota_del_campo(meta, 'DATE') or meta.get('DATE_STATUS', '')})"))
        # marcatori di pagina (lavoro 8): ogni riga che inizia con [[ deve essere un marcatore riconosciuto;
        # le pagine numerate devono seguire l'ordine del documento
        for riga in t[pos:].splitlines():
            r = riga.strip()
            if r.startswith("[[") and not MARCATORE_PAGINA.match(r):
                righe.append((rel, "errore", f"marcatore di pagina non riconosciuto: {r[:60]}"))
        numeri = [int(p) for _, p in marcatori_pagina(t, pos) if p.isdigit()]
        inversioni = [(a, b) for a, b in zip(numeri, numeri[1:]) if b <= a]
        if inversioni:
            a, b = inversioni[0]
            righe.append((rel, "avviso", f"pagine dei marcatori non in ordine crescente: {a} -> {b}"))
        try:
            if meta.get("OCR_CONFIDENCE") and float(meta["OCR_CONFIDENCE"]) < 70:
                righe.append((rel, "avviso", f"OCR di qualità bassa ({meta['OCR_CONFIDENCE']})"))
        except ValueError:
            pass
        if args.lingua and not meta.get("LANG"):
            righe.append((rel, "avviso", "manca [LANG]"))
    # --migra-stati (lavoro 8, punto 5): i valori storici di <CAMPO>_STATUS diventano lo stato del vocabolario
    # chiuso e la provenienza passa in <CAMPO>_NOTE; gli altri campi non vengono toccati
    if migrazioni:
        for f, meta, testo, pos, prefs in migrazioni:
            # la migrazione riguarda solo le righe dell'intestazione (fino a pos), non il testo del documento
            intestazione_t, corpo = testo[:pos], testo[pos:]
            stati = {p: stato_del_valore(meta[f"{p}_STATUS"])[0] for p in prefs}
            note = {p: meta[f"{p}_STATUS"].strip() for p in prefs}   # la provenienza storica è dentro il valore

            def sostituisci(m, stati=stati, note=note):
                riga = m.group(0)
                for p in prefs:
                    if re.match(rf"^\[{p}_STATUS:", riga):
                        return f"[{p}_STATUS: {stati[p]}]"
                    if re.match(rf"^\[{p}_NOTE:", riga):
                        return f"[{p}_NOTE: {note[p]}]"
                return riga

            modello = r"^\[(?:%s)_(?:STATUS|NOTE):[^\]]*\]" % "|".join(prefs)
            nuovo_int = re.sub(modello, sostituisci, intestazione_t, flags=re.MULTILINE)
            for p in prefs:
                if f"[{p}_NOTE:" not in nuovo_int:
                    nuovo_int = re.sub(rf"^\[{p}_STATUS:[^\]]*\]",
                                       lambda m, n=note[p]: m.group(0) + f"\n[{p}_NOTE: {n}]",
                                       nuovo_int, count=1, flags=re.MULTILINE)
            tmp = f.with_suffix(".txt.tmp")
            tmp.write_text(nuovo_int + corpo, encoding="utf-8")
            tmp.replace(f)
        stampa(f"Migrati {len(migrazioni)} file: stati normalizzati sul vocabolario chiuso, "
               f"provenienza spostata in <CAMPO>_NOTE")
    out = (dati.parent / "importazioni" / f"controllo_{dt.date.today().isoformat()}.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8-sig", newline="") as fo:
        w = csv.writer(fo)
        w.writerow(["file", "gravità", "problema"])
        w.writerows(righe)
    err = sum(1 for r in righe if r[1] == "errore")
    stampa(f"Controllati {len(file)} file: {err} errori, {len(righe) - err} avvisi. Elenco: {out}")
    for r in [r for r in righe if r[1] == "errore"][:20]:
        stampa(f"  {r[0]}: {r[2]}")
    return 1 if err else 0


def cmd_prepara(args, stampa=print):
    cfg = leggi_config()
    ok = True
    try:
        fitz = carica_pymupdf()
        stampa(f"PyMuPDF {fitz.VersionBind}: ok")
    except ImportError:
        ok = False
        stampa("PyMuPDF manca: python -m pip install pymupdf")
    exe = cerca_tesseract(cfg)
    if exe:
        v = subprocess.run([exe, "--version"], capture_output=True).stdout.decode("utf-8", "replace").split("\n")[0]
        stampa(f"Tesseract: {exe} ({v})")
    else:
        ok = False
        stampa("Tesseract manca: winget install -e --id UB-Mannheim.TesseractOCR (poi riapri il Prompt dei comandi)")
    lingue = set()
    for s in leggi_serie().sections():
        if leggi_serie()[s].get("ocr", "").strip().lower() == "no":      # serie già nel corpus, senza OCR
            continue
        lingue.update(lingue_ocr(dict(leggi_serie()[s])).split("+"))
    lingue.update((args.lingue or "").split("+"))
    lingue.discard("")
    if exe:
        presenti = lingue_installate(exe, cartella_modelli(cfg))
        stampa("Lingue OCR installate: " + ", ".join(sorted(presenti)))
        mancanti = sorted(l for l in lingue | {"osd"} if l not in presenti)
        if mancanti:
            ok = False
            stampa(AIUTO_LINGUE.format(", ".join(mancanti)))
        else:
            stampa(f"Ci sono tutte le lingue richieste dalle serie: {', '.join(sorted(lingue))}.")
    return 0 if ok else 1


def cmd_serie(args, stampa=print):
    cp = leggi_serie()
    for s in cp.sections():
        x = cp[s]
        stampa(f"{s}: {x.get('tipo', '?')}, lingua {x.get('lingua', '?')}, in data\\{x.get('cartella', '?')}; "
               f"citazione «{x.get('citazione', '')}»")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="comando", required=True)
    a = sub.add_parser("importa")
    a.add_argument("percorsi", nargs="+")
    a.add_argument("--serie", required=True)
    for k in ("data", "numero", "titolo", "autore", "anno", "volume", "luogo", "editore", "metadati", "lingue"):
        a.add_argument(f"--{k}")
    a.add_argument("--ocr", choices=["auto", "sempre"], default="auto")
    a.add_argument("--unisci", action="store_true")
    a.add_argument("--sovrascrivi", action="store_true")
    a.add_argument("--processi", type=int)
    a.add_argument("--dpi", type=int, default=300)
    a.add_argument("--prova", type=int)
    a.add_argument("--senza-indice", action="store_true")
    c = sub.add_parser("controlla")
    c.add_argument("cartella", nargs="?")
    c.add_argument("--lingua", action="store_true", help="segnala anche i file senza [LANG]")
    c.add_argument("--migra-stati", action="store_true", dest="migra_stati",
                   help="porta i DATE_STATUS storici sul vocabolario chiuso (la provenienza va in DATE_NOTE)")
    p = sub.add_parser("prepara")
    p.add_argument("--lingue")
    sub.add_parser("serie")
    ap.add_argument("--lavoro", help=argparse.SUPPRESS)      # cartella del lavoro avviato dalla chat
    args = ap.parse_args(argv)
    if args.lavoro:
        d = Path(args.lavoro)
        d.mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(d / "registro.txt", "a", encoding="utf-8", buffering=1)
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass
    codice, errore = 4, ""
    try:
        codice = {"importa": cmd_importa, "controlla": cmd_controlla, "prepara": cmd_prepara,
                  "serie": cmd_serie}[args.comando](args) or 0
    except SystemExit as e:
        if isinstance(e.code, str):
            print(e.code)
            errore = e.code
        codice = e.code if isinstance(e.code, int) else 4
    except Exception as e:
        errore = f"{type(e).__name__}: {e}"
        print("ERRORE: " + errore)
    if args.lavoro:
        import json
        (Path(args.lavoro) / "esito.json").write_text(json.dumps(
            {"codice": codice, "errore": errore, "fine": dt.datetime.now().isoformat(timespec="seconds")},
            ensure_ascii=False), encoding="utf-8")
    return codice


if __name__ == "__main__":
    sys.exit(main())

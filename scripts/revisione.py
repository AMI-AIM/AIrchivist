#!/usr/bin/env python3
"""
Importazione guidata con tabella di revisione (lavoro 29, fase 7): serie e metadati diventano una tabella da
controllare in Excel o LibreOffice, invece di concetti tecnici da scrivere a mano.

  python importa.py proponi <cartella o file> [--serie "..."]
      Legge tutti i file senza importarli (niente OCR: testo dei PDF, etichette e metadati del PDF, nome del
      file) e propone serie e metadati. Scrive audit/review_<data>.csv (punto e virgola, si apre in Excel con un
      doppio clic) con una riga per documento e una colonna «da_controllare» che spiega i dubbi; accanto,
      review_<data>.json con le proposte, per sapere poi che cosa è stato corretto.
  python importa.py applica audit/review_<data>.csv [--prova] [--sovrascrivi]
      Crea le serie che mancano in series.ini, importa i documenti con i metadati della tabella (anche salvata
      come .xlsx), registra in audit/imports.csv le importazioni e in audit/changes.csv i valori che il
      ricercatore ha cambiato rispetto alla proposta. --prova controlla la tabella e dice che cosa farebbe.
  python importa.py rivedi [--serie "..."] [--cartella <dentro data>] [--solo-dubbi]
      La stessa tabella per documenti già importati (audit/review_rivedi_<data>.csv): si correggono le
      intestazioni nel foglio di calcolo e «applica» le riscrive, con copia di sicurezza in system/backups e una
      riga in audit/changes.csv per ogni campo cambiato.

Stati dei valori (colonne stato_data, stato_numero): «dedotto» (dal nome del file, dalle etichette del PDF),
«da verificare» (letto nella prima pagina), «verificato». Un valore cambiato a mano vale «verificato». La colonna
fonte_data dice da dove viene la data proposta e diventa DATE_NOTE dell'intestazione.
"""
import argparse
import csv
import datetime as dt
import io
import json
import re
import shutil
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARTELLA))

# colonne della tabella: prima quelle da controllare, in fondo quelle informative
COLONNE = ["importa", "file", "serie", "tipo_serie", "lingua", "cartella_serie", "sigla", "tipo_documento",
           "data", "stato_data", "fonte_data", "numero", "stato_numero", "titolo", "autore", "anno", "volume", "luogo", "editore",
           "prima_pagina", "da_pagina", "pagine", "formato", "testo", "qualita_ocr", "da_controllare", "percorso"]
COLONNE_RIVEDI = ["file_dati", "serie", "data", "stato_data", "numero", "stato_numero", "titolo", "autore", "anno",
                  "volume", "luogo", "editore", "lingua", "pagine", "da_controllare"]
# colonna della tabella -> campo dell'intestazione dei file in data
CAMPI = {"data": "DATE", "stato_data": "DATE_STATUS", "numero": "ISSUE", "stato_numero": "ISSUE_STATUS",
         "titolo": "TITLE", "autore": "AUTHOR", "anno": "YEAR", "volume": "VOLUME", "luogo": "PUBLICATION_PLACE",
         "editore": "PUBLISHER", "lingua": "LANG", "serie": "SERIES"}
TIPI_SERIE = ("periodico", "articolo", "volume", "archivio")
TIPI_DOCUMENTO = ("fascicolo", "articolo", "volume")
STATI = ("dedotto", "da verificare", "verificato")
SI = ("sì", "si", "s", "x", "yes", "y", "1", "vero", "true")
PAGINE_VOLUME = 80             # da qui un documento è un volume
PAGINE_ARTICOLO = 60           # fin qui un PDF nativo con autore e titolo è un articolo
# parole frequenti per riconoscere la lingua dei testi in caratteri latini
PAROLE = {"sq": "dhe të në për që një nga me është u së ka do ishte janë",
          "it": "il della che di per non con una sono del le nel dei alla",
          "fr": "le la les des et est que une dans pour du pas sur au",
          "en": "the and of to in is that for with was on by as are",
          "de": "der die und das ist nicht mit den von zu des sich auf",
          "es": "el la de que y los las en por una del con para",
          "pt": "o a de que e os do da em não um uma para com"}
SCRITTURE_LINGUA = {"CJK": "zh", "CYRILLIC": "ru", "GREEK": "el", "ARABIC": "ar", "HEBREW": "he"}
# righe con la data di scaricamento o di consultazione, non di pubblicazione
SCARICAMENTO = re.compile(r"download|accessed|retrieved|this content|scaricat|consultat|t[ée]l[ée]charg|\bUTC\b|"
                          r"jstor\.org/terms", re.IGNORECASE)
# frontespizio di JSTOR: «Source: The American Historical Review, APRIL 2016, Vol. 121, No. 2 (APRIL 2016), pp. 377-402»
FONTE_JSTOR = re.compile(r"Source:\s*(?P<serie>[^,\n]+),\s*(?P<data>[^,\n]*?\d{4})(?:\s*,\s*Vol\.\s*(?P<volume>[\w.]+))?"
                         r"(?:\s*,\s*No\.\s*(?P<numero>[\w./-]+))?", re.IGNORECASE)


def fonte_jstor(testo):
    """Rivista, data, volume e numero dal frontespizio di JSTOR; {} se non c'è."""
    import importa
    m = FONTE_JSTOR.search((testo or "").replace("\x00", "\n")[:3000])
    if not m:
        return {}
    data = importa.data_da_testo(m.group("data"))
    if not data:
        mese = re.search(r"([A-Za-zé]+)\s+(\d{4})", m.group("data"))
        if mese and mese.group(1).lower() in importa.MESI:
            data = f"{mese.group(2)}-{importa.MESI[mese.group(1).lower()]:02d}"
        else:
            data = (re.search(r"\d{4}", m.group("data")) or [""])[0]
    autore = re.search(r"Author\(s\):\s*([^\n]+)", (testo or "").replace("\x00", "\n")[:3000])
    return {"serie": m.group("serie").strip(), "data": data, "volume": m.group("volume") or "",
            "numero": m.group("numero") or "", "autore": autore.group(1).strip() if autore else ""}
TITOLI_INUTILI = re.compile(r"^(untitled|senza titolo|microsoft word|document\d*|scan\d*|\S+\.(docx?|pdf|tiff?))",
                            re.IGNORECASE)


# ---------------------------------------------------------------- lettura dei documenti (senza OCR)
def lingua_del_testo(testo):
    """Codice della lingua (zh, ru, sq, it, fr, en...) da scrittura e parole frequenti; "" se non si capisce."""
    lettere = [unicodedata.name(ch, "?").split()[0] for ch in testo[:20000] if ch.isalpha()]
    if len(lettere) < 40:
        return ""
    scritture = Counter(lettere)
    for scrittura, codice in SCRITTURE_LINGUA.items():
        if scritture.get(scrittura, 0) > 0.3 * len(lettere):
            return codice
    parole = Counter(re.findall(r"[^\W\d_]+", testo[:20000].lower()))
    punti = {l: sum(parole[p] for p in elenco.split()) for l, elenco in PAROLE.items()}
    migliore = max(punti, key=punti.get)
    return migliore if punti[migliore] >= 5 else ""


def prime_righe(testo, n=8):
    return [r.strip() for r in (testo or "").splitlines() if len(r.strip()) >= 3][:n]


def titolo_plausibile(t):
    t = (t or "").strip()
    return t if 3 <= len(t) <= 200 and not TITOLI_INUTILI.match(t) else ""


def dpi_stimati(pag):
    """Risoluzione dell'immagine più grande della pagina (scansione), in punti per pollice; None se non c'è."""
    try:
        info = max(pag.get_image_info(), key=lambda i: (i["bbox"][2] - i["bbox"][0]) * (i["bbox"][3] - i["bbox"][1]))
        larghezza_pt = info["bbox"][2] - info["bbox"][0]
        return round(info["width"] / (larghezza_pt / 72)) if larghezza_pt > 0 and info.get("width") else None
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def leggi_pdf(f):
    """Pagine, testo per pagina, etichette, metadati, pagine scansionate e risoluzione: solo lettura."""
    import importa
    fitz = importa.carica_pymupdf()
    testi, etichette, scansioni, dpi = [], [], 0, []
    with fitz.open(str(f)) as doc:
        meta = dict(getattr(doc, "metadata", None) or {})
        for pag in doc:
            try:
                t = pag.get_text("text")
            except Exception:
                t = ""
            testi.append(t)
            etichette.append(importa.etichetta_pagina(pag))
            try:
                scansione = importa.e_scansione(pag)
            except Exception:
                scansione = False
            if scansione:
                scansioni += 1
                if len(dpi) < 3:
                    d = dpi_stimati(pag)
                    if d:
                        dpi.append(d)
    return {"testi": testi, "etichette": etichette, "meta": meta, "scansioni": scansioni,
            "dpi": sorted(dpi)[len(dpi) // 2] if dpi else None}


def leggi_immagine(f):
    """Risoluzione di un'immagine (se PyMuPDF la legge)."""
    try:
        import importa
        fitz = importa.carica_pymupdf()
        pix = fitz.Pixmap(str(f))
        return pix.xres if getattr(pix, "xres", 0) and pix.xres > 1 else None
    except Exception:
        return None


def qualita(dpi):
    if not dpi:
        return "non stimata"
    if dpi >= 280:
        return f"buona (circa {dpi} dpi)"
    if dpi >= 200:
        return f"media (circa {dpi} dpi)"
    return f"bassa (circa {dpi} dpi: meglio rifare la scansione a 300 dpi)"


def analizza(doc, ocr_disponibile):
    """Che cosa si sa di un documento senza importarlo: formato, testo, pagine, prima pagina, metadati."""
    import importa
    import numerazione
    file = doc["file"]
    est = file[0].suffix.lower()
    a = {"formato": "", "testo": "", "qualita_ocr": "", "pagine_pdf": 0, "inizio": "", "meta": {}, "pagine": "",
         "nota_pagine": "", "stato_pagine": "", "dubbi": [], "etichette": False}
    if est in importa.PDF:
        a["formato"] = "PDF"
        try:
            p = leggi_pdf(file[0])
        except Exception as e:
            a["dubbi"].append(f"il PDF non si legge ({type(e).__name__}: {e})")
            return a
        n = len(p["testi"])
        nativo = sum(1 for t in p["testi"] if importa.testo_utile(t) >= importa.SOGLIA_TESTO_PDF)
        a["pagine_pdf"], a["meta"] = n, p["meta"]
        a["inizio"] = "\n".join(p["testi"][:2])[:3000]
        if p["scansioni"] and nativo:
            a["testo"] = "scansione con strato di testo"
            a["qualita_ocr"] = qualita(p["dpi"]) + "; lo strato si confronta con un OCR nuovo all'importazione"
        elif p["scansioni"] or not nativo:
            a["testo"] = "scansione senza testo" if not nativo else "scansione"
            a["qualita_ocr"] = qualita(p["dpi"])
            a["inizio"] = ""                     # niente testo da cui dedurre: lo darà l'OCR
        else:
            a["testo"] = "testo nativo"
            a["qualita_ocr"] = "non serve"
        pagine, info = numerazione.numera(p["testi"], p["etichette"])
        a["etichette"] = info.get("metodo") == "etichette di pagina del PDF"
        if pagine:
            numeri = [pagine[k][0] for k in sorted(pagine)]
            a["pagine"] = f"{numeri[0]}-{numeri[-1]}" if len(numeri) > 1 else numeri[0]
            a["nota_pagine"], a["stato_pagine"] = f"{info['metodo']}: {info['nota']}", info["stato"]
    elif est in importa.IMMAGINI:
        a["formato"] = "immagine" if len(file) == 1 else f"{len(file)} immagini"
        a["testo"] = "scansione senza testo"
        a["pagine_pdf"] = len(file)
        a["qualita_ocr"] = qualita(leggi_immagine(file[0]))
    elif est in importa.TESTI:
        a["formato"], a["testo"], a["qualita_ocr"] = "testo", "testo nativo", "non serve"
        try:
            a["inizio"] = file[0].read_text(encoding="utf-8-sig", errors="replace")[:3000]
        except OSError:
            pass
    else:
        a["formato"] = "PAGE/ALTO XML" if est in importa.XML else "archivio PAGE/ALTO"
        a["testo"], a["qualita_ocr"] = "trascrizione esportata", "non serve"
        a["pagine_pdf"] = len(file)
    if "scansione" in a["testo"] and "strato" not in a["testo"] and not ocr_disponibile:
        a["dubbi"].append("serve l'OCR, ma Tesseract non c'è: installalo prima di applicare la tabella")
    if a["qualita_ocr"].startswith("bassa"):
        a["dubbi"].append("scansione a bassa risoluzione: OCR probabilmente scadente")
    return a


def raggruppa_immagini(gruppi):
    """Le immagini della stessa cartella con lo stesso nome a meno dei numeri (pagina_001.jpg, pagina_002.jpg)
    sono le pagine di un solo documento."""
    import importa
    out, per_chiave = [], {}
    for g in gruppi:
        f = g["file"][0]
        if len(g["file"]) == 1 and f.suffix.lower() in importa.IMMAGINI:
            chiave = (f.parent, re.sub(r"\d+", "#", f.stem))
            if chiave in per_chiave:
                per_chiave[chiave]["file"].append(f)
                continue
            g = per_chiave[chiave] = dict(g, file=[f])
        out.append(g)
    for g in per_chiave.values():
        if len(g["file"]) > 1:
            g["unisci"] = True
            g["origine"] = f"{g['file'][0].name} … {g['file'][-1].name} ({len(g['file'])} immagini)"
    return out


# ---------------------------------------------------------------- proposta
def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "serie"


def schema_nome(stem):
    """Nome del file senza cifre (ZP1967-01-12 -> ZP#-#-#): i file di una stessa serie lo condividono."""
    return re.sub(r"#+", "#", re.sub(r"\d", "#", stem))


def data_e_numero(stem):
    """(data, stato, nota, numero, dubbio) dal nome del file. «PR1967-11» è ambiguo: anno e mese o anno e numero."""
    import importa
    data = importa.data_da_testo(stem)
    numero = importa.numero_da_nome(stem)
    dubbio = ""
    m = re.search(r"(?<!\d)(1[89]\d\d|20\d\d)[-_. ]([01]?\d)(?![\d-])", stem)
    if data and len(data) == 7 and m and not numero:
        dubbio = f"nel nome «{stem}» {m.group(2)} può essere il mese o il numero del fascicolo"
    return data, numero, dubbio


def serie_esistente(nome_cartella, schema, profili):
    """Serie di series.ini a cui appartiene probabilmente il gruppo: per sigla in testa ai nomi dei file o per nome."""
    for nome, p in profili.items():
        sigla = (p.get("sigla") or "").strip()
        if sigla and schema.upper().startswith(sigla.upper() + "#"):
            return nome
        if slug(nome) == slug(nome_cartella):
            return nome
    return ""


def titolo_ricorrente(inizi):
    """Riga che compare in testa alla prima pagina di almeno metà dei documenti (testata del periodico)."""
    conta = Counter()
    for t in inizi:
        conta.update({re.sub(r"\s+", " ", r) for r in prime_righe(t, 5) if 3 <= len(r) <= 60 and
                      not re.search(r"\d{3,}", r)})
    if not conta or len(inizi) < 2:
        return ""
    riga, n = conta.most_common(1)[0]
    return riga if n >= max(2, len(inizi) / 2) else ""


def proponi(percorsi, serie_forzata="", stampa=print):
    """Righe della tabella di revisione per i file indicati (nessuna scrittura in data)."""
    import importa
    import profili
    cfg = importa.leggi_config()
    radice = Path(percorsi[0]).resolve()
    radice = radice if radice.is_dir() else radice.parent
    file = importa.raccogli(percorsi)
    if not file:
        raise SystemExit("Nessun file da proporre (PDF, immagini, .txt, esportazioni PAGE/ALTO .xml o .zip).")
    gruppi = raggruppa_immagini(importa.raggruppa_file(file))
    ocr = bool(importa.cerca_tesseract(cfg))
    esistenti = profili.tutti(ricarica=True)
    stampa(f"Documenti da esaminare: {len(gruppi)} (da {len(file)} file)")
    documenti = []
    for k, g in enumerate(gruppi, 1):
        a = analizza(g, ocr)
        primo = g["file"][0]
        cartella_rel = primo.parent.resolve().relative_to(radice).as_posix() if primo.parent.resolve() != radice else ""
        if primo.suffix.lower() in importa.XML:            # una cartella di pagine XML è il documento
            cartella_rel = Path(cartella_rel).parent.as_posix() if cartella_rel else ""
            cartella_rel = "" if cartella_rel == "." else cartella_rel
        stem = g["base"]
        data, numero, dubbio_nome = data_e_numero(stem)
        documenti.append({"g": g, "a": a, "cartella": cartella_rel, "schema": schema_nome(stem), "stem": stem,
                          "data_nome": data, "numero_nome": numero, "dubbio_nome": dubbio_nome})
        if k % 25 == 0:
            stampa(f"  esaminati {k}/{len(gruppi)}")
    # gruppi di serie: la sottocartella; nella cartella principale, lo schema dei nomi dei file
    per_serie = defaultdict(list)
    for d in documenti:
        per_serie[d["cartella"]].append(d)
    # una cartella è una serie se i suoi file si somigliano: nome con le stesse cifre (ZP1967-01-12) o la
    # stessa testata in prima pagina. Altrimenti (articoli di riviste diverse, libri) ogni file fa serie a sé,
    # salvo i gruppi di nomi uguali a meno delle cifre
    gruppi_serie = defaultdict(list)
    for cartella, docs in per_serie.items():
        schemi = Counter(d["schema"] for d in docs if "#" in d["schema"])
        simili = schemi and schemi.most_common(1)[0][1] >= max(2, len(docs) / 2)
        if cartella and len(docs) > 1 and (simili or titolo_ricorrente([d["a"]["inizio"] for d in docs])):
            gruppi_serie[cartella] += docs
            continue
        for d in docs:
            stessi = schemi.get(d["schema"], 0) > 1
            gruppi_serie[f"{cartella}#{d['schema']}" if stessi else f"#solo#{cartella}/{d['stem']}"].append(d)
    per_serie = gruppi_serie
    righe = []
    for chiave, docs in per_serie.items():
        proposta = proponi_serie(chiave, docs, esistenti, serie_forzata)
        for d in docs:
            righe.append(riga_documento(d, proposta, radice))
    righe.sort(key=lambda r: (r["serie"], r["file"]))
    return righe, radice


def proponi_serie(chiave, docs, esistenti, serie_forzata=""):
    """Nome, tipo, lingua, cartella e sigla proposti per un gruppo di documenti, con i dubbi."""
    dubbi = []
    con_data = sum(1 for d in docs if d["data_nome"] or d["numero_nome"])
    lingue = Counter(l for l in (lingua_del_testo(d["a"]["inizio"]) for d in docs) if l)
    lingua = lingue.most_common(1)[0][0] if lingue else ""
    schema = docs[0]["schema"]
    sotto = "" if chiave.startswith("#solo#") or "#" in chiave else chiave
    nome = serie_forzata or serie_esistente(Path(sotto).name if sotto else "", schema, esistenti)
    if nome and nome in esistenti:
        p = esistenti[nome]
        return {"serie": nome, "tipo_serie": p.get("tipo", "periodico"), "lingua": p.get("lingua", lingua),
                "cartella_serie": p.get("cartella", ""), "sigla": p.get("sigla", ""), "esiste": True,
                "dubbi": [f"serie già in series.ini: «{nome}»"] + (
                    [f"la lingua dei testi sembra «{lingua}», la serie ha «{p.get('lingua')}»"]
                    if lingua and p.get("lingua") and lingua != p.get("lingua") else [])}
    periodico = con_data >= max(1, len(docs) / 2) or (len(docs) > 1 and all(d["a"]["pagine_pdf"] < PAGINE_VOLUME
                                                                             for d in docs))
    titolo = titolo_ricorrente([d["a"]["inizio"] for d in docs])
    riviste = {fonte_jstor(d["a"]["inizio"]).get("serie") for d in docs}
    if not nome and len(riviste) == 1 and None not in riviste and "" not in riviste:
        nome = riviste.pop()
        periodico = True
        dubbi.append("rivista dal frontespizio di JSTOR")
    if not nome:
        if titolo:
            nome = titolo.title() if titolo.isupper() else titolo
            dubbi.append(f"nome della serie dalla testata ricorrente «{titolo}»")
        elif sotto:
            nome = Path(sotto).name.replace("_", " ").strip()
            nome = nome.title() if nome.islower() else nome
            dubbi.append("nome della serie dal nome della cartella")
        elif len(docs) == 1 and docs[0]["a"]["pagine_pdf"] >= PAGINE_VOLUME:
            # un libro da solo: la serie è il libro stesso (o la sua collana)
            a = docs[0]["a"]
            righe = prime_righe(a["inizio"], 1)
            nome = titolo_plausibile(a["meta"].get("title")) or (re.sub(r"[\s\d]+$", "", righe[0])[:80] if righe else "")
            nome = nome.title() if nome.isupper() else nome
            dubbi.append("serie = titolo del libro (o la sua collana): controlla")
        elif len(docs) == 1:
            dubbi.append("serie da indicare (per un articolo: la rivista che lo pubblica)")
        else:
            prefisso = re.match(r"[A-Za-z]+", schema)
            nome = prefisso.group(0) if prefisso else ""
            dubbi.append("nome della serie dal nome dei file: scrivi quello vero")
    if not lingua:
        dubbi.append("lingua non riconosciuta (scansioni senza testo): indicala")
    tipo = "periodico" if periodico else "volume"
    sigla = ""
    if tipo == "periodico":
        prefissi = Counter((re.match(r"[A-Za-z]{1,6}(?=\d)", d["stem"]) or [""])[0].upper() for d in docs)
        sigla = prefissi.most_common(1)[0][0] if prefissi and prefissi.most_common(1)[0][0] else ""
        sigla = sigla or re.sub(r"[^A-Z]", "", (nome or "").title())[:4]
    cartella = ("riviste/" if tipo == "periodico" else "volumi/") + slug(nome or sotto or "serie")
    return {"serie": nome, "tipo_serie": tipo, "lingua": lingua, "cartella_serie": cartella, "sigla": sigla,
            "esiste": False, "dubbi": dubbi}


def riga_documento(d, s, radice):
    """Una riga della tabella: valori proposti e dubbi del documento."""
    import importa
    a, g = d["a"], d["g"]
    dubbi = list(s["dubbi"]) + list(a["dubbi"])
    meta = a["meta"] or {}
    pagine = a["pagine_pdf"]
    nativo = a["testo"] == "testo nativo"
    if pagine >= PAGINE_VOLUME or (s["tipo_serie"] == "volume" and pagine > PAGINE_ARTICOLO):
        tipo_doc = "volume"
    elif (nativo or "strato" in a["testo"]) and pagine and pagine <= PAGINE_ARTICOLO and (
            (titolo_plausibile(meta.get("title")) and meta.get("author")) or a["etichette"] or
            (a["pagine"] and not a["pagine"].split("-")[0] in ("1", "i"))):
        tipo_doc = "articolo"
    else:
        tipo_doc = "fascicolo" if s["tipo_serie"] == "periodico" else "volume"
    data, stato_data, numero, stato_numero = d["data_nome"], "", d["numero_nome"], ""
    jstor = fonte_jstor(a["inizio"])
    if tipo_doc == "articolo" and not s["esiste"]:
        # articoli: serie di tipo articolo (la rivista, un file per articolo con autore e titolo)
        s = dict(s, tipo_serie="articolo", cartella_serie="riviste/" + slug(s["serie"]) if s["serie"] else "")
    fonte_data = ""
    if jstor and not data:
        data, stato_data, numero = jstor["data"], "dedotto", jstor["numero"] or numero
        stato_numero = "dedotto" if jstor["numero"] else ""
        fonte_data = "dal frontespizio di JSTOR"
        dubbi.append("data, volume e numero dal frontespizio di JSTOR")
    elif data:
        stato_data, fonte_data = "dedotto", "dal nome del file"
        dubbi += [d["dubbio_nome"]] if d["dubbio_nome"] else []
    elif a["inizio"]:
        data = importa.data_da_testo("\n".join(r for r in a["inizio"][:1500].splitlines()
                                               if not SCARICAMENTO.search(r)))
        if data:
            stato_data, fonte_data = "da verificare", "letta nella prima pagina"
            dubbi.append("data letta nella prima pagina")
    if not data and tipo_doc != "volume":
        dubbi.append("data non trovata: indicala")
    if numero and not stato_numero:
        stato_numero = "dedotto"
    titolo = autore = anno = ""
    if tipo_doc in ("articolo", "volume"):
        titolo = titolo_plausibile(meta.get("title"))
        autore = (meta.get("author") or jstor.get("autore") or "").strip()
        autore = autore.title() if autore.isupper() else autore
        if not titolo:
            righe = prime_righe(a["inizio"], 3)
            titolo = re.sub(r"\s+\d{1,4}$", "", righe[0])[:150] if righe else ""
            titolo = titolo.title() if titolo.isupper() else titolo
            dubbi.append("titolo dalla prima riga della prima pagina" if titolo else "titolo da indicare")
        if autore and (";" in autore or " and " in autore or
                       ("," in autore and len(autore.split(",")[0].split()) >= 2)):
            dubbi.append("più autori nei metadati del PDF: scrivili come vanno citati (Cognome, Nome, Nome Cognome…)")
        elif autore and "," not in autore and len(autore.split()) >= 2:
            parti = autore.split()
            autore = f"{parti[-1]}, {' '.join(parti[:-1])}"            # Cognome, Nome
            dubbi.append("autore dai metadati del PDF, messo nella forma Cognome, Nome")
        if tipo_doc == "volume":
            anni = Counter(re.findall(r"(?<!\d)(1[89]\d\d|20\d\d)(?!\d)", a["inizio"]))
            anno = anni.most_common(1)[0][0] if anni and not data else ""
            if anno:
                dubbi.append("anno letto nelle prime pagine")
    if a["stato_pagine"] == "dedotto":
        dubbi.append(f"pagine dedotte dai numeri stampati ({a['nota_pagine']})")
    if tipo_doc == "articolo" and not a["pagine"]:
        dubbi.append("pagine non ricavate: indica prima_pagina")
    xml = g["file"][0].suffix.lower() in importa.XML
    if g.get("unisci"):
        percorso = ";".join(str(f.resolve()) for f in g["file"])
    else:
        percorso = str((g["file"][0].parent if xml else g["file"][0]).resolve())
    file_rel = g["file"][0].parent if xml else g["file"][0]
    try:
        file_rel = file_rel.resolve().relative_to(radice).as_posix()
    except ValueError:
        file_rel = file_rel.name
    if g.get("unisci"):
        file_rel += f" (+ {len(g['file']) - 1} pagine)"
    return {"importa": "sì", "file": file_rel, "serie": s["serie"], "tipo_serie": s["tipo_serie"],
            "lingua": s["lingua"], "cartella_serie": s["cartella_serie"], "sigla": s["sigla"],
            "tipo_documento": tipo_doc, "data": data, "stato_data": stato_data, "fonte_data": fonte_data,
            "numero": numero,
            "stato_numero": stato_numero, "titolo": titolo, "autore": autore, "anno": anno or data[:4],
            "volume": jstor.get("volume", ""), "luogo": "", "editore": "", "prima_pagina": "", "da_pagina": "",
            "pagine": a["pagine"],
            "formato": a["formato"] + (f", {pagine} pagine" if pagine and a["formato"] == "PDF" else ""),
            "testo": a["testo"], "qualita_ocr": a["qualita_ocr"],
            "da_controllare": "; ".join(dict.fromkeys(x for x in dubbi if x)), "percorso": percorso}


# ---------------------------------------------------------------- tabelle
def scrivi_tabella(f, colonne, righe):
    """CSV con punto e virgola e BOM: Excel e LibreOffice lo aprono già diviso in colonne."""
    with open(f, "w", encoding="utf-8-sig", newline="") as h:
        w = csv.DictWriter(h, colonne, extrasaction="ignore", delimiter=";")
        w.writeheader()
        w.writerows(righe)


def leggi_tabella(f):
    """Righe della tabella compilata: CSV (; , o tabulazione) o cartella di lavoro Excel (.xlsx), anche salvata
    con il nome .csv."""
    f = Path(f)
    with open(f, "rb") as h:
        inizio = h.read(4)
    if inizio.startswith(b"PK"):
        from tabelle import leggi_xlsx
        tabella = [r for r in leggi_xlsx(f) if any((x or "").strip() for x in r)]
        if not tabella:
            return []
        titoli = [(x or "").strip() for x in tabella[0]]
        return [dict(zip(titoli, [(x or "") for x in r] + [""] * (len(titoli) - len(r)))) for r in tabella[1:]]
    testo = f.read_text(encoding="utf-8-sig")
    sep = max(";,\t", key=testo.split("\n", 1)[0].count)
    return [{(k or "").strip(): (v or "") for k, v in r.items()} for r in
            csv.DictReader(io.StringIO(testo, newline=""), delimiter=sep)]


def file_proposte(f):
    """review_<data>.json accanto alla tabella (anche se la tabella è stata salvata come .xlsx)."""
    return Path(f).with_suffix(".json")


def cmd_proponi(args, stampa=print):
    import importa
    from llm import percorso
    cfg = importa.leggi_config()
    righe, radice = proponi(args.percorsi, args.serie or "", stampa)
    audit = percorso(cfg, "registro_modifiche").parent
    audit.mkdir(parents=True, exist_ok=True)
    f = Path(args.out) if args.out else audit / f"review_{dt.datetime.now():%Y%m%d_%H%M}.csv"
    scrivi_tabella(f, COLONNE, righe)
    file_proposte(f).write_text(json.dumps({"tipo": "proposta", "radice": str(radice), "creata": dt.datetime.now()
                                            .isoformat(timespec="seconds"), "righe": righe}, ensure_ascii=False,
                                           indent=1), encoding="utf-8")
    serie = Counter(r["serie"] or "(da indicare)" for r in righe)
    dubbi = sum(1 for r in righe if r["da_controllare"])
    stampa(f"\nTabella: {f}")
    stampa(f"{len(righe)} documenti; serie proposte: " + "; ".join(f"{s} ({n})" for s, n in serie.items()))
    stampa(f"Righe con qualcosa da controllare: {dubbi} (colonna da_controllare).")
    stampa("Aprila con Excel o LibreOffice, correggi i valori (importa = no per saltare un documento), salvala "
           f"(anche come .xlsx) e poi: python importa.py applica \"{f}\" --prova, e senza --prova per importare.")
    return 0


# ---------------------------------------------------------------- applicazione
def registra_modifiche(cfg, modifiche):
    """Righe in audit/changes.csv (file, campo, valore precedente, valore nuovo, motivo), nella forma del file:
    virgola, BOM UTF-8 e CRLF."""
    if not modifiche:
        return
    from llm import percorso
    f = percorso(cfg, "registro_modifiche")
    nuovo = not f.exists()
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a", encoding="utf-8-sig" if nuovo else "utf-8", newline="") as h:
        w = csv.writer(h, lineterminator="\r\n")
        if nuovo:
            w.writerow(["file", "campo", "valore_precedente", "valore_nuovo", "motivo"])
        w.writerows(modifiche)


def controlla_righe(righe, esistenti):
    """(righe da importare, serie da creare {nome: campi}, errori, avvisi)."""
    errori, avvisi, da_creare = [], [], {}
    attive = []
    for n, r in enumerate(righe, 2):                      # 2: la riga 1 sono i titoli
        if (r.get("importa") or "").strip().lower() not in SI:
            continue
        attive.append((n, r))
        serie = (r.get("serie") or "").strip()
        for campo in ("stato_data", "stato_numero"):
            v = (r.get(campo) or "").strip().lower()
            if v and v not in STATI:
                errori.append(f"riga {n}: {campo} «{v}» non ammesso (solo: {', '.join(STATI)}, o vuoto)")
        if (r.get("tipo_documento") or "").strip() and r["tipo_documento"].strip() not in TIPI_DOCUMENTO:
            errori.append(f"riga {n}: tipo_documento «{r['tipo_documento']}» (solo: {', '.join(TIPI_DOCUMENTO)})")
        for campo in ("prima_pagina", "da_pagina"):
            if (r.get(campo) or "").strip() and not r[campo].strip().isdigit():
                errori.append(f"riga {n}: {campo} deve essere un numero")
        percorsi = [p for p in (r.get("percorso") or "").split(";") if p.strip()]
        if not percorsi or not all(Path(p).exists() for p in percorsi):
            errori.append(f"riga {n}: il file «{r.get('percorso')}» non c'è più")
        if not serie:
            errori.append(f"riga {n} ({r.get('file')}): manca la serie")
            continue
        if serie in esistenti:
            p = esistenti[serie]
            for campo, chiave in (("tipo_serie", "tipo"), ("lingua", "lingua"), ("cartella_serie", "cartella")):
                v = (r.get(campo) or "").strip()
                if v and v != (p.get(chiave) or "").strip():
                    avvisi.append(f"riga {n}: {campo} «{v}» diverso da quello di series.ini («{p.get(chiave)}»): "
                                  "vale series.ini")
            continue
        voce = {k: (r.get(k) or "").strip() for k in ("tipo_serie", "lingua", "cartella_serie", "sigla")}
        if not voce["cartella_serie"] and voce["tipo_serie"] in TIPI_SERIE:
            import profili
            voce["cartella_serie"] = profili.completa(serie, {"tipo": voce["tipo_serie"]})["cartella"]
        if serie in da_creare:
            for k, v in voce.items():
                if v and da_creare[serie][k] and v != da_creare[serie][k]:
                    errori.append(f"riga {n}: {k} «{v}» diverso da «{da_creare[serie][k]}» delle altre righe della "
                                  f"serie «{serie}»")
                elif v:
                    da_creare[serie][k] = da_creare[serie][k] or v
        else:
            da_creare[serie] = voce
    for nome, v in da_creare.items():
        if v["tipo_serie"] not in TIPI_SERIE:
            errori.append(f"serie «{nome}»: tipo_serie «{v['tipo_serie']}» (solo: {', '.join(TIPI_SERIE)})")
        if not re.fullmatch(r"[a-z]{2,3}", v["lingua"]):
            errori.append(f"serie «{nome}»: lingua «{v['lingua']}» (codice di due lettere: sq, it, en, zh...)")
        cartella = v["cartella_serie"].replace("\\", "/").strip("/")
        if ".." in cartella:
            errori.append(f"serie «{nome}»: cartella_serie dentro data (es. riviste/nome)")
    return attive, da_creare, errori, avvisi


def cmd_applica(args, stampa=print):
    import importa
    import profili
    righe = leggi_tabella(args.tabella)
    if not righe:
        raise SystemExit("La tabella è vuota.")
    if "file_dati" in righe[0]:
        return applica_revisione(args, righe, stampa)
    if "percorso" not in righe[0]:
        raise SystemExit("La tabella non ha la colonna «percorso»: è una tabella di importa.py proponi?")
    cfg = importa.leggi_config()
    esistenti = profili.tutti(ricarica=True)
    attive, da_creare, errori, avvisi = controlla_righe(righe, esistenti)
    for a in avvisi:
        stampa("Avviso: " + a)
    if errori:
        stampa("La tabella ha errori da correggere prima di importare:")
        for e in errori:
            stampa("  - " + e)
        return 2
    stampa(f"Da importare: {len(attive)} documenti; serie da creare: "
           + ("; ".join(f"{n} ({v['tipo_serie']}, {v['lingua']}, data/{v['cartella_serie']})"
                        for n, v in da_creare.items()) or "nessuna"))
    if args.prova:
        stampa("Prova: nessuna scrittura. Per importare: lo stesso comando senza --prova.")
        return 0
    for nome, v in da_creare.items():
        stampa(importa.aggiungi_serie(nome, v["tipo_serie"], v["lingua"], v["cartella_serie"], sigla=v["sigla"]))
    proposte = {}
    if file_proposte(args.tabella).exists():
        dati = json.loads(file_proposte(args.tabella).read_text(encoding="utf-8"))
        proposte = {r["percorso"]: r for r in dati.get("righe", [])}
    importati, falliti, modifiche = 0, [], []
    for n, r in attive:
        proposta = proposte.get(r["percorso"], {})
        valori = {k: (r.get(k) or "").strip() for k in COLONNE}
        # un valore cambiato rispetto alla proposta è stato controllato: verificato, salvo stato indicato a mano
        for campo, stato in (("data", "stato_data"), ("numero", "stato_numero")):
            if proposta and valori[campo] != (proposta.get(campo) or "").strip() and \
                    valori[stato] == (proposta.get(stato) or "").strip():
                valori[stato] = "verificato"
        esiti = []
        a = argparse.Namespace(
            percorsi=[p for p in r["percorso"].split(";") if p.strip()], serie=valori["serie"],
            data=valori["data"] or None, numero=valori["numero"] or None, titolo=valori["titolo"] or None,
            autore=valori["autore"] or None, anno=valori["anno"] or None, volume=valori["volume"] or None,
            luogo=valori["luogo"] or None, editore=valori["editore"] or None, metadati=None, lingue=None,
            ocr="auto", campione=importa.PAGINE_CAMPIONE,
            prima_pagina=int(valori["prima_pagina"]) if valori["prima_pagina"] else None,
            da_pagina=int(valori["da_pagina"] or 1), senza_pagine=False, unisci=";" in r["percorso"],
            sovrascrivi=args.sovrascrivi, processi=None, dpi=300, prova=None, senza_indice=True,
            stato_data=None if valori["stato_data"] == "verificato" else valori["stato_data"],
            nota_data=(valori["fonte_data"] or "dalla tabella di revisione")
            if valori["stato_data"] in ("dedotto", "da verificare") else "",
            stato_numero=None if valori["stato_numero"] == "verificato" else valori["stato_numero"],
            esiti=esiti)
        stampa(f"\n=== riga {n}: {r.get('file')} -> {valori['serie']}")
        try:
            importa.cmd_importa(a, stampa)
        except SystemExit as e:
            falliti.append(f"riga {n}: {e}")
            continue
        if not esiti:
            falliti.append(f"riga {n} ({r.get('file')}): non importato (vedi i messaggi sopra)")
            continue
        importati += 1
        for campo, chiave in CAMPI.items():
            prima, dopo = (proposta.get(campo) or "").strip(), valori.get(campo, "")
            if proposta and prima != dopo and campo not in ("stato_data", "stato_numero"):
                modifiche.append([esiti[0]["destinazione"], chiave, prima or "(assente)", dopo or "(assente)",
                                  "corretto nella tabella di revisione dell'importazione (importa.py applica)"])
    registra_modifiche(cfg, modifiche)
    if importati:
        from indice import Indice, percorso_indice
        from llm import percorso
        ind = Indice(percorso_indice(cfg), percorso(cfg, "dati").resolve())
        if ind.pronto():
            ind.aggiorna(stampa=stampa)
        else:
            stampa("Indice assente: python indice.py costruisci")
    stampa(f"\nImportati {importati} documenti su {len(attive)}"
           + (f"; valori corretti rispetto alla proposta: {len(modifiche)} (audit/changes.csv)" if modifiche else "")
           + ". Registro: audit/imports.csv")
    for f in falliti:
        stampa("  " + f)
    return 4 if falliti and not importati else (1 if falliti else 0)


# ---------------------------------------------------------------- revisione dei documenti già importati
def cmd_rivedi(args, stampa=print):
    import importa
    import profili
    from estrai_occorrenze import leggi_intestazione, stato_attivo
    from llm import percorso
    cfg = importa.leggi_config()
    dati = percorso(cfg, "dati").resolve()
    base = (dati / args.cartella).resolve() if args.cartella else dati
    righe = []
    for f in sorted(base.rglob("*.txt")):
        rel = f.relative_to(dati).as_posix()
        meta, _ = leggi_intestazione(f.read_text(encoding="utf-8-sig", errors="replace")[:6000])
        if args.serie and meta.get("SERIES") != args.serie and profili.nome_di("", rel) != args.serie:
            continue
        dubbi = []
        for campo, prefisso in (("data", "DATE"), ("numero", "ISSUE"), ("pagine", "PAGES")):
            s = stato_attivo(meta, prefisso)
            if s:
                dubbi.append(f"{campo} {s}")
        tipo = profili.di(meta.get("SERIES", ""), rel).get("tipo", "periodico")
        if tipo == "periodico" and not meta.get("DATE"):
            dubbi.append("data mancante")
        if args.solo_dubbi and not dubbi:
            continue
        righe.append({"file_dati": rel, "serie": meta.get("SERIES", ""), "data": meta.get("DATE", ""),
                      "stato_data": stato_attivo(meta, "DATE"), "numero": meta.get("ISSUE", ""),
                      "stato_numero": stato_attivo(meta, "ISSUE"), "titolo": meta.get("TITLE", ""),
                      "autore": meta.get("AUTHOR", ""), "anno": meta.get("YEAR", ""),
                      "volume": meta.get("VOLUME", ""), "luogo": meta.get("PUBLICATION_PLACE", ""),
                      "editore": meta.get("PUBLISHER", ""), "lingua": meta.get("LANG", ""),
                      "pagine": meta.get("PAGES", ""), "da_controllare": "; ".join(dubbi)})
    if not righe:
        stampa("Nessun documento corrisponde.")
        return 1
    audit = percorso(cfg, "registro_modifiche").parent
    f = Path(args.out) if args.out else audit / f"review_rivedi_{dt.datetime.now():%Y%m%d_%H%M}.csv"
    scrivi_tabella(f, COLONNE_RIVEDI, righe)
    file_proposte(f).write_text(json.dumps({"tipo": "rivedi", "creata": dt.datetime.now().isoformat(timespec="seconds"),
                                            "righe": righe}, ensure_ascii=False, indent=1), encoding="utf-8")
    stampa(f"Tabella: {f} ({len(righe)} documenti, {sum(1 for r in righe if r['da_controllare'])} con qualcosa da "
           f"controllare). Correggi le celle, salva e poi: python importa.py applica \"{f}\" --prova")
    return 0


def riscrivi_intestazione(f, nuovi):
    """Cambia, aggiunge ("" o None toglie) campi dell'intestazione [CAMPO: valore] di un file, lasciando com'è il
    resto: testo, codifica (BOM), fine riga."""
    dati = f.read_bytes()
    bom = dati.startswith(b"\xef\xbb\xbf")
    testo = dati.decode("utf-8-sig")
    nl = "\r\n" if "\r\n" in testo else "\n"
    righe = testo.split(nl)
    from estrai_occorrenze import HDR
    fine = 0
    while fine < len(righe) and HDR.match(righe[fine].strip()):
        fine += 1
    resto = dict(nuovi)
    testata = []
    for r in righe[:fine]:
        chiave = HDR.match(r.strip()).group(1).upper()
        if chiave in resto:
            v = resto.pop(chiave)
            if v:
                testata.append(f"[{chiave}: {v}]")
        else:
            testata.append(r)
    # i campi nuovi prima di FULL_CITATION, che resta l'ultima riga dell'intestazione
    pos = next((i for i, r in enumerate(testata) if r.strip().upper().startswith("[FULL_CITATION:")), len(testata))
    testata[pos:pos] = [f"[{k}: {v}]" for k, v in resto.items() if v]
    f.write_bytes((("﻿" if bom else "") + nl.join(testata + righe[fine:])).encode("utf-8"))


def applica_revisione(args, righe, stampa):
    import importa
    from estrai_occorrenze import leggi_intestazione
    from llm import percorso
    cfg = importa.leggi_config()
    dati = percorso(cfg, "dati").resolve()
    f_prop = file_proposte(args.tabella)
    if not f_prop.exists():
        raise SystemExit(f"Manca {f_prop.name} accanto alla tabella: senza i valori di partenza non so che cosa è "
                         "cambiato. Rifai «importa.py rivedi».")
    prima = {r["file_dati"]: r for r in json.loads(f_prop.read_text(encoding="utf-8"))["righe"]}
    piano, errori = [], []
    for n, r in enumerate(righe, 2):
        rel = (r.get("file_dati") or "").strip()
        if rel not in prima:
            errori.append(f"riga {n}: «{rel}» non era nella tabella esportata")
            continue
        cambi = {}
        for campo in CAMPI:
            vecchio, nuovo = (prima[rel].get(campo) or "").strip(), (r.get(campo) or "").strip()
            if vecchio != nuovo:
                cambi[campo] = (vecchio, nuovo)
        if not cambi:
            continue
        if "serie" in cambi:
            errori.append(f"riga {n}: la serie non si cambia da qui (sposterebbe il file in un'altra serie)")
            continue
        for campo in ("stato_data", "stato_numero"):
            if campo in cambi and cambi[campo][1] and cambi[campo][1] not in STATI:
                errori.append(f"riga {n}: {campo} «{cambi[campo][1]}» non ammesso")
        if "data" in cambi and cambi["data"][1] and not re.fullmatch(r"\d{4}(-\d{2}(-\d{2})?)?", cambi["data"][1]):
            errori.append(f"riga {n}: data «{cambi['data'][1]}» (scrivi AAAA-MM-GG, AAAA-MM o AAAA)")
        if not (dati / rel).is_file():
            errori.append(f"riga {n}: {rel} non esiste più in data")
        piano.append((rel, cambi))
    if errori:
        stampa("La tabella ha errori da correggere:")
        for e in errori:
            stampa("  - " + e)
        return 2
    stampa(f"Documenti da correggere: {len(piano)}; campi cambiati: {sum(len(c) for _, c in piano)}")
    for rel, cambi in piano[:30]:
        stampa(f"  {rel}: " + "; ".join(f"{CAMPI[k]} {v or '(vuoto)'} -> {w or '(vuoto)'}" for k, (v, w) in cambi.items()))
    if args.prova or not piano:
        stampa("Prova: nessuna scrittura." if args.prova else "Niente da cambiare.")
        return 0
    copie = percorso(cfg, "backup") / f"{dt.date.today().isoformat()}_revisione_metadati"
    modifiche = []
    for rel, cambi in piano:
        f = dati / rel
        dest = copie / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            shutil.copy2(f, dest)
        nuovi = {CAMPI[k]: w for k, (v, w) in cambi.items()}
        # un valore corretto a mano è verificato: via lo stato e la provenienza, salvo stato scritto nella tabella
        for campo, stato, prefisso in (("data", "stato_data", "DATE"), ("numero", "stato_numero", "ISSUE")):
            if campo in cambi and stato not in cambi:
                nuovi[f"{prefisso}_STATUS"], nuovi[f"{prefisso}_NOTE"] = "", ""
            if stato in cambi and cambi[stato][1] in ("", "verificato"):
                nuovi[f"{prefisso}_STATUS"], nuovi[f"{prefisso}_NOTE"] = "", ""
        meta, _ = leggi_intestazione(f.read_text(encoding="utf-8-sig", errors="replace")[:6000])
        if "data" in cambi and not cambi.get("anno") and cambi["data"][1][:4] != meta.get("YEAR", "") \
                and cambi["data"][1][:4].isdigit():
            nuovi["YEAR"] = cambi["data"][1][:4]
        riscrivi_intestazione(f, nuovi)
        for chiave, valore in nuovi.items():
            if (meta.get(chiave) or "") != (valore or ""):
                modifiche.append([rel, chiave, meta.get(chiave) or "(assente)", valore or "(assente)",
                                  "revisione in tabella (importa.py rivedi / applica)"])
    registra_modifiche(cfg, modifiche)
    stampa(f"Corretti {len(piano)} documenti; {len(modifiche)} righe in audit/changes.csv; copie di prima in {copie}. "
           "FULL_CITATION non è stata ricalcolata: le risposte compongono le citazioni dall'intestazione "
           "(citazioni.py). Se le correzioni chiudono problemi di audit/open_issues.csv, aggiornalo.")
    return 0

#!/usr/bin/env python3
"""
Citazioni delle fonti del corpus in stile Chicago standard (nota), fino alla pagina quando c'è.

La citazione si compone dall'intestazione del file ([SERIES: ...], [ISSUE: ...], [DATE: ...] ...) e dal profilo
della serie in series.ini (campo "chicago", modello con segnaposto; un tratto tra [ ] sparisce se manca uno dei
suoi segnaposto). Le serie senza profilo usano il modello predefinito del loro tipo (periodico, volume). Nome del file e numero di riga non entrano mai nella citazione.

La pagina è quella dell'ultimo marcatore [[p. N]] che precede il passaggio nel file; per le serie che segnano le
pagine in altro modo il profilo indica un'espressione regolare ("pagina_regex", es. 第N版 del Renmin Ribao).
Il campo "pagina" già calcolato per il passaggio vale solo se il file non ne dà una.

Uso da riga di comando (prova):
  python citazioni.py <file del corpus, relativo a data> [offset]
"""
import datetime as dt
import re
import sys
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
HDR = re.compile(r"^\[([A-Za-z_]+):\s*(.*?)\]\s*$")
# Marcatore di pagina (sintassi fissata nel lavoro 8, fase 2): su una riga propria, prima del testo della pagina.
#   [[p. 12]]             pagina numerata (N: cifre arabe o romane, maiuscolo e spaziatura liberi)
#   [[pagina 12]]         forma estesa tollerata
#   [[p. 12b]] / [[p. II]] prefissi/suffissi: es. «23b», pagine romane iniziali, intervallo «I-IV»
#   [[p. s.n.]]           pagina non numerata -> vale come assenza di pagina
#   [[p. 12 | pdf 17]]    forma estesa, con la pagina del file originale (dopo | è annotazione)
# Il doppio [[ iniziale distingue il marcatore dall'intestazione [CAMPO: valore] e lo rende improbabile nel testo.
PAGINA_NON_NUMERATA = {"s.n.", "sn", "s. n.", "senza pagina", "n.p.", "np"}
MARCATORE_PAGINA = re.compile(
    r"^\[\[\s*(?:p(?:age|agina)?\.?|pag\.)\s*[:]?\s*([A-Za-z0-9][A-Za-z0-9 .+\-/]*?)\s*(?:\|\s*[^\]]*)?\]\]\s*$",
    re.IGNORECASE | re.MULTILINE)
MESI_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
           "settembre", "ottobre", "novembre", "dicembre"]
ROMANI = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}

# Modelli predefiniti per tipo di serie (Chicago, nota). Segnaposto in valori_da_intestazione().
PREDEFINITI = {
    "periodico": "*{serie}*[ {volume}][, {numero_lbl}][, {contenitore}] ({data_o_anno})[: {pagina}]",
    "volume": "[{autore}, ]*{titolo}*[, {volume_lbl}] ([{luogo}: ][{editore}, ]{anno})[, {pagina}]",
}
DATE_INATTENDIBILI = {"filename+local_header"}      # METADATA_SOURCE con date ricavate dal testo (Peking Review)


# ---------------------------------------------------------------- profili
def profili():
    """Sezioni di series.ini (nome della serie -> campi): profili.py."""
    import profili as P
    return P.tutti()


def profilo_di(meta, file=""):
    """Profilo della serie del file: per nome della serie, altrimenti per cartella (profili.py)."""
    import profili as P
    return P.di(meta.get("SERIES", ""), file)


# ---------------------------------------------------------------- intestazione
def leggi_intestazione(testo):
    """(metadati con chiavi maiuscole, posizione in cui inizia il testo)."""
    meta, pos = {}, 0
    for riga in testo.splitlines(keepends=True):
        m = HDR.match(riga.strip())
        if m:
            meta[m.group(1).upper()] = m.group(2).strip()
        elif not (riga.strip() == "" and meta):
            break
        pos += len(riga)
    return meta, pos


def data_it(iso):
    """«4 maggio 1966»; per le date note solo al mese (AAAA-MM) «maggio 1966»."""
    try:
        d = dt.date.fromisoformat(iso)
        return f"{d.day} {MESI_IT[d.month - 1]} {d.year}"
    except (TypeError, ValueError):
        m = re.fullmatch(r"(\d{4})-(\d{2})", iso or "")
        if m and 1 <= int(m.group(2)) <= 12:
            return f"{MESI_IT[int(m.group(2)) - 1]} {m.group(1)}"
        return iso or ""


def arabo(v):
    """Volume in numeri romani -> arabi (Chicago usa i numeri arabi per i volumi)."""
    v = (v or "").strip()
    if v and re.fullmatch(r"[IVXLC]+", v):
        tot, prec = 0, 0
        for ch in reversed(v):
            n = ROMANI[ch]
            tot, prec = (tot - n, prec) if n < prec else (tot + n, n)
        return str(tot)
    return v


def contenitore(meta):
    """Supplemento, indice e simili: dal campo CONTAINER_TYPE; nelle intestazioni che non l'hanno ancora,
    dalla FULL_CITATION registrata (es. «supplement: subject index, nos. 1-26»)."""
    if meta.get("CONTAINER_TYPE"):
        tipo = meta["CONTAINER_TYPE"].strip()
        return "" if tipo.lower() in ("fascicolo", "issue", "numero") else tipo
    fc = meta.get("FULL_CITATION", "")
    for rx in (r"\bsupplement:\s*.+$", r"\bsubject index.*$", r"\bsupplement\b"):
        m = re.search(rx, fc, re.IGNORECASE)
        if m:
            return m.group(0).strip(" ,").lower()
    return ""


def data_affidabile(meta):
    """False se la data è dichiarata inattendibile (METADATA_SOURCE) o non verificata (<CAMPO>_STATUS, lavoro 8)."""
    from estrai_occorrenze import stato_attivo          # vocabolario degli stati: modulo unico (estrai_occorrenze)
    return not (meta.get("METADATA_SOURCE") in DATE_INATTENDIBILI or stato_attivo(meta, "DATE"))


def valori_da_intestazione(meta, profilo=None):
    """Segnaposto per i modelli di citazione. I valori fissi del profilo (autore, titolo...) prevalgono sui
    campi mancanti dell'intestazione, non su quelli presenti."""
    profilo = profilo or {}
    v = {
        "serie": meta.get("SERIES", ""),
        "titolo": meta.get("TITLE", ""),
        "autore": meta.get("AUTHOR") or meta.get("AUTHOR_NORMALIZED", ""),
        "volume": arabo(meta.get("VOLUME", "")),
        "numero": (meta.get("ISSUE", "") or "").lstrip("0") or meta.get("ISSUE", ""),
        "luogo": meta.get("PUBLICATION_PLACE", ""),
        "editore": meta.get("PUBLISHER", ""),
        "anno": meta.get("YEAR") or meta.get("ENGLISH_EDITION_YEAR", ""),
        "data": "",
        "data_rapporto": data_it(meta.get("REPORT_DATE", "")),
        "rapporto": "",
        "serie_originale": meta.get("ORIGINAL_SERIES", ""),
        "traduttore": meta.get("TRANSLATOR", ""),
    }
    for k in ("titolo", "autore", "luogo", "editore", "anno", "serie"):
        if not v[k] and profilo.get(k):
            v[k] = profilo[k].strip()
    if profilo.get("titolo_fisso"):
        v["titolo"] = profilo["titolo_fisso"].strip()
    if not v["titolo"]:
        v["titolo"] = v["serie"] or meta.get("DOC_ID", "")
    data = meta.get("DATE", "")
    if re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", data) and data_affidabile(meta):     # anche al mese
        v["data"] = data_it(data)
    if not v["anno"] and data[:4].isdigit():
        v["anno"] = data[:4]
    v["data_o_anno"] = v["data"] or v["anno"]
    vol = v["volume"]
    vol = re.sub(r",\s*\(", " (", vol)
    v["volume_lbl"] = f"vol. {vol}" if re.match(r"\d", vol) and "vol" not in vol.lower() else vol
    num = v["numero"]
    if re.fullmatch(r"\d+", num):
        v["numero_lbl"] = f"no. {num}"
    elif re.fullmatch(r"\d+\s*[-–]\s*\d+", num):                     # numero doppio
        a_, b_ = re.split(r"\s*[-–]\s*", num)
        v["numero_lbl"] = f"nos. {a_.lstrip('0') or a_}–{b_.lstrip('0') or b_}"
    else:
        v["numero_lbl"] = num                                          # es. «special issue»
    v["contenitore"] = contenitore(meta)
    rid = (meta.get("JPRS_ID") or meta.get("REPORT_ID") or "").strip()
    if rid:
        v["rapporto"] = rid if rid.upper().startswith("JPRS") else f"JPRS {rid}"
    return v


def componi(modello, valori):
    """Riempie il modello; un tratto tra [ ] sparisce se uno dei suoi segnaposto è vuoto."""
    def opzionale(m):
        pezzo = m.group(1)
        chiavi = re.findall(r"\{(\w+)\}", pezzo)
        return pezzo.format_map(valori) if all(valori.get(k) for k in chiavi) else ""
    s = re.sub(r"\[([^\]]*)\]", opzionale, modello)
    s = re.sub(r"\{(\w+)\}", lambda m: str(valori.get(m.group(1)) or ""), s)
    s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"\s+([,:;)])", r"\1", s)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r",\s*,", ",", s)
    s = re.sub(r":\s*,", ",", s)
    s = dopo_punto_interrogativo(s)
    return re.sub(r"\s{2,}", " ", s).strip(" ,:")


def dopo_punto_interrogativo(s):
    """Chicago: dopo un titolo che finisce con «?» o «!» non si aggiunge punto né virgola, anche oltre le virgolette
    o il corsivo («"Whither Albania?."» -> «"Whither Albania?"»)."""
    return re.sub(r"([?!])([\"”’'*»]*)[.,]", r"\1\2", s)


def modello_di(profilo, meta):
    if profilo.get("chicago"):
        return profilo["chicago"]
    tipo = (profilo.get("tipo") or "").strip()
    if tipo not in PREDEFINITI:
        tipo = "periodico" if meta.get("ISSUE") else "volume"
    return PREDEFINITI[tipo]


def citazione(meta, file="", pagina=""):
    """Nota in stile Chicago per il file (e la pagina, se data)."""
    pr = profilo_di(meta, file)
    v = valori_da_intestazione(meta, pr)
    v["pagina"] = pagina or ""
    return componi(modello_di(pr, meta), v)


# ---------------------------------------------------------------- pagina
def normalizza_pagina(m):
    """Pagina leggibile dal marcatore: '' se non numerata ('s.n.' e simili), altrimenti il valore ripulito."""
    p = (m.group(1) if isinstance(m, re.Match) else m or "").strip()
    return "" if p.lower().replace(" ", "") in {x.replace(" ", "") for x in PAGINA_NON_NUMERATA} else p


def pagina_nel_testo(testo, offset, profilo=None, inizio=0):
    """Pagina dell'ultimo marcatore che precede 'offset' ("" se non c'è o se la pagina non è numerata)."""
    prima = testo[inizio:offset] if offset else ""
    m = None
    for m in MARCATORE_PAGINA.finditer(prima):
        pass
    if m:
        return normalizza_pagina(m)
    rx = (profilo or {}).get("pagina_regex", "").strip()
    if rx:
        trovate = list(re.finditer(rx, prima))
        if trovate:
            return trovate[-1].group(1)
    return ""


def marcatori_pagina(testo, inizio=0):
    """Elenco di (offset del marcatore, pagina) per tutti i marcatori del testo dalla posizione 'inizio'.
    Pagina '' per i marcatori di pagina non numerata. Usato anche da importa.py per validare i marcatori."""
    return [(m.start() + inizio, normalizza_pagina(m)) for m in MARCATORE_PAGINA.finditer(testo, inizio)]


_CACHE = {}


def _leggi(path):
    if path not in _CACHE:
        if len(_CACHE) > 100:
            _CACHE.clear()
        try:
            testo = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            testo = ""
        _CACHE[path] = (testo, *leggi_intestazione(testo))
    return _CACHE[path]


def _dati_predefiniti():
    sys.path.insert(0, str(CARTELLA))
    from llm import leggi_config, percorso
    return percorso(leggi_config(), "dati")


def per_passaggio(c, dati=None):
    """(citazione, pagina) per un passaggio di passaggi.jsonl / classificati.jsonl."""
    dati = Path(dati) if dati else _dati_predefiniti()
    testo, meta, inizio = _leggi(dati / c["file"])
    a = c.get("analisi") or {}
    if not meta:                                  # file non leggibile: si usa la citazione registrata
        pag = a.get("pagina", "")
        base = c.get("citazione") or c.get("fonte", "")
        return (f"{base}, {pag}" if pag else base), pag
    pr = profilo_di(meta, c["file"])
    pag = pagina_nel_testo(testo, c.get("offset", 0), pr, inizio) or a.get("pagina", "")
    return citazione(meta, c["file"], pag), pag


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    c = {"file": sys.argv[1], "offset": int(sys.argv[2]) if len(sys.argv) > 2 else 0}
    print(per_passaggio(c)[0])


if __name__ == "__main__":
    main()

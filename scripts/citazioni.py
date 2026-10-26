#!/usr/bin/env python3
"""
Citazioni delle fonti del corpus in stile Chicago, 17ª edizione, sistema autore-data: la voce della bibliografia
(reference list entry), con la pagina citata in coda quando c'è («…, p. 3.»).

La voce si compone dall'intestazione del file ([SERIES: ...], [AUTHOR: ...], [DATE: ...] ...) e dal profilo della
serie in series.ini: tipo (periodico, articolo, volume, archivio, voce_autore_data), nome della testata come va
scritto (campo «nome_citazione», es. *Renmin ribao* 人民日报), valori fissi. Il campo «chicago» del profilo, se
c'è, è un modello con segnaposto che sostituisce la voce del tipo (un tratto tra [ ] sparisce se manca uno dei
suoi segnaposto). Nome del file e numero di riga non entrano mai nella citazione.

Forme (Chicago 17, 15.9 e seguenti):
  articolo di rivista  Putnam, Lara. 2016. “Titolo.” *The American Historical Review* 121, no. 2 (aprile): 377–402.
  quotidiano           Autore. 1967. “Titolo.” *Zëri i Popullit*, 12 gennaio 1967.  /  senza autore la testata
                       al posto dell'autore: *Zëri i Popullit*. 1967. 12 gennaio 1967.
  libro                Hoxha, Enver. 1969. *Vepra*. Vol. 2. Tirana: Naim Frashëri.
  archivio             Central Intelligence Agency. 1971. “Titolo.” 3 marzo 1971. Segnatura, fondo, archivio.

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

TIPI_VOCE = ("periodico", "articolo", "volume", "archivio")
SENZA_DATA = "s.d."                                   # Chicago «n.d.»: anno sconosciuto
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
        "segnatura": meta.get("CALL_NUMBER", ""),
        "fondo": meta.get("COLLECTION", ""),
        "archivio": meta.get("ARCHIVE", ""),
    }
    for k in ("fondo", "archivio", "segnatura"):
        if not v[k] and profilo.get(k):
            v[k] = profilo[k].strip()
    if not v["archivio"]:
        v["archivio"] = v["serie"]
    titolo_proprio = v["titolo"]
    for k in ("titolo", "autore", "luogo", "editore", "anno", "serie"):
        if not v[k] and profilo.get(k):
            v[k] = profilo[k].strip()
    if profilo.get("titolo_fisso"):
        v["titolo"] = profilo["titolo_fisso"].strip()
    if not v["titolo"]:
        v["titolo"] = v["serie"] or meta.get("DOC_ID", "")
    # titolo del singolo documento (articolo, documento d'archivio), non quello fisso della serie
    v["titolo_articolo"] = titolo_proprio if titolo_proprio and titolo_proprio != v["serie"] else ""
    v["autore_nota"] = nome_in_nota(v["autore"])
    v["autore_bib"] = autore_bibliografia(v["autore"])
    v["testata"] = (profilo.get("nome_citazione") or "").strip() or (f"*{v['serie']}*" if v["serie"] else "")
    v["pagine"] = re.sub(r"\s*[-–]\s*", "–", meta.get("PAGES", "") or "")
    data = meta.get("DATE", "")
    if re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", data) and data_affidabile(meta):     # anche al mese
        v["data"] = data_it(data)
    v["mese"] = v["data"].split()[0] if re.fullmatch(r"\d{4}-\d{2}", data) and v["data"] else ""   # (aprile)
    if not v["anno"] and data[:4].isdigit():
        v["anno"] = data[:4]
    v["data_o_anno"] = v["data"] or v["anno"]
    v["anno_o_sd"] = v["anno"] or SENZA_DATA
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


def nome_in_nota(autore):
    """Autore nella forma della nota Chicago: «Larrabee, F. Stephen» -> «F. Stephen Larrabee»; più autori separati
    da «;» uniti con «and» (due o tre), «et al.» da quattro; enti e nomi senza virgola restano come sono."""
    a = (autore or "").strip()
    if not a:
        return ""
    m = re.search(r",?\s*(et al\.?|e altri)$", a, re.IGNORECASE)
    et_al = " et al." if m else ""
    a = a[:m.start()].strip() if m else a
    if ";" in a:
        nomi = [nome_in_nota(x) for x in a.split(";") if x.strip()]
        if len(nomi) >= 4:
            return nomi[0] + " et al."
        return (" and ".join(nomi) if len(nomi) == 2 else ", ".join(nomi[:-1]) + ", and " + nomi[-1]) + et_al
    if a.count(",") == 1:
        cognome, nome = (x.strip() for x in a.split(","))
        return f"{nome} {cognome}".strip() + et_al
    return a + et_al


def autore_bibliografia(autore):
    """Autore nella forma della bibliografia: il primo «Cognome, Nome», gli altri «Nome Cognome», «and» prima
    dell'ultimo; oltre dieci autori i primi sette e «et al.» (Chicago 17, 15.9); enti e nomi senza virgola
    restano come sono."""
    a = (autore or "").strip()
    if ";" not in a:
        return a
    nomi = [x.strip() for x in a.split(";") if x.strip()]
    et_al = len(nomi) > 10
    nomi = nomi[:7] if et_al else nomi
    altri = [nome_in_nota(x) for x in nomi[1:]]
    if not altri:
        return nomi[0]
    if et_al:
        return nomi[0] + ", " + ", ".join(altri) + ", et al."
    return nomi[0] + ", " + (", ".join(altri[:-1]) + ", " if len(altri) > 1 else "") + "and " + altri[-1]


def maiuscola(s):
    return s[:1].upper() + s[1:] if s else s


def voce_del_tipo(tipo, v):
    """Voce di bibliografia autore-data (senza punto finale e senza pagina citata) per il tipo della serie."""
    autore, anno, titolo = v["autore_bib"], v["anno"] or SENZA_DATA, v["titolo_articolo"]
    testata = v["testata"]
    if tipo == "volume":
        libro = f"*{v['titolo']}*" if v["titolo"] else testata
        s = f"{autore}. {anno}. {libro}." if autore else f"{libro}. {anno}."
        editoriale = (f"{v['luogo']}: {v['editore']}" if v["luogo"] and v["editore"] else
                      v["luogo"] or v["editore"])
        for parte in (f"Vol. {v['volume']}" if v["volume"] else "", editoriale):
            if parte:
                s += f" {parte}."
        return s.rstrip(".")
    if tipo == "archivio":
        capo = autore or testata
        s = f"{capo}. {anno}." + (f" “{titolo}.”" if titolo else "")
        if v["data"] and v["data"] != anno:
            s += f" {v['data']}."
        archivio = "" if not autore and f"*{v['archivio']}*" == testata else v["archivio"]
        coda = ", ".join(x for x in (v["segnatura"], v["fondo"], archivio, v["luogo"]) if x)
        return (s + (f" {maiuscola(coda)}" if coda else "")).rstrip(".")
    # periodico e articolo: rivista (con mese) o quotidiano (con giorno); la data completa è parte della voce
    giorno = v["data"] if v["data"] and not v["mese"] else ""
    numerazione = [f"{v['volume']}" if v["volume"] else "", v["numero_lbl"], v["contenitore"]]
    if autore:
        s = f"{autore}. {anno}." + (f" “{titolo}.”" if titolo else "") + f" {testata}"
        if v["volume"]:
            s += f" {v['volume']}"
        s += "".join(f", {x}" for x in numerazione[1:] if x)
        if giorno:
            s += f", {giorno}"
        elif v["mese"]:
            s += f" ({v['mese']})"
        if v["pagine"]:
            s += (", " if giorno else ": ") + v["pagine"]
        return s
    # senza autore la testata ne prende il posto (Chicago 17, 15.49)
    s = f"{testata}. {anno}." + (f" “{titolo}.”" if titolo else "")
    elementi = [f"vol. {v['volume']}" if v["volume"] else "", v["numero_lbl"], v["contenitore"],
                giorno or (v["data"] if v["mese"] else "")]
    corpo = ", ".join(x for x in elementi if x)
    if corpo:
        s += " " + maiuscola(corpo)
    if v["pagine"] and titolo:
        s += f": {v['pagine']}"
    return s


def tipo_della_voce(profilo, meta):
    tipo = (profilo.get("tipo") or "").strip()
    if tipo in TIPI_VOCE:
        return tipo
    return "periodico" if meta.get("ISSUE") or meta.get("DATE") else "volume"


def voce(meta, profilo=None, pagina=""):
    """Voce di bibliografia autore-data del documento, con la pagina citata in coda («…, p. 3.»). Il campo chicago
    del profilo, se c'è, è il modello da usare al posto della voce del tipo (la pagina va nel modello)."""
    profilo = profilo or {}
    v = valori_da_intestazione(meta, profilo)
    v["pagina"] = pagina or ""
    if profilo.get("chicago"):
        return componi(profilo["chicago"], v)
    s = voce_del_tipo(tipo_della_voce(profilo, meta), v)
    if pagina:
        s += f", p. {pagina}"
    s = dopo_punto_interrogativo(re.sub(r"\s{2,}", " ", s).strip(" ,:"))
    return s if s.endswith((".", "?", "!", "”")) else s + "."


def componi(modello, valori):
    """Riempie il modello; un tratto tra [ ] sparisce se uno dei suoi segnaposto è vuoto."""
    def opzionale(m):
        pezzo = m.group(1)
        chiavi = re.findall(r"\{(\w+)\}", pezzo)
        return pezzo.format_map(valori) if all(valori.get(k) for k in chiavi) else ""
    s = re.sub(r"\[([^\]]*)\]", opzionale, modello)
    s = re.sub(r"\{(\w+)\}", lambda m: str(valori.get(m.group(1)) or ""), s)
    s = re.sub(r"\(\s*\)", "", s)
    s = re.sub(r"\.(\s*\.)+", ".", s)                  # tratti spariti tra due punti: «2016. . Trad.»
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


def citazione(meta, file="", pagina=""):
    """Voce Chicago autore-data per il file, con la pagina citata se data."""
    return voce(meta, profilo_di(meta, file), pagina)


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

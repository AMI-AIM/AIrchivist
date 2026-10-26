#!/usr/bin/env python3
"""
Lettura delle esportazioni PAGE XML e ALTO XML (Transkribus, eScriptorium e altri strumenti) nel formato
interno dell'importazione: pagine nell'ordine del file, righe, confidenza se disponibile (lavoro 10, fase 3).

Il formato si riconosce dalla radice del file (PcGts = PAGE, alto = ALTO), per qualsiasi versione dello schema:
i nomi degli elementi si leggono senza lo spazio dei nomi.

PAGE
  - ordine delle regioni: ReadingOrder (RegionRefIndexed/RegionRef), altrimenti l'attributo custom
    «readingOrder {index:N;}» di Transkribus, altrimenti l'ordine nel file; le regioni annidate (tabelle) si
    leggono al loro posto;
  - testo di una riga: TextEquiv/Unicode della riga (quello con l'index più basso), altrimenti le sue Word;
    una regione senza righe vale con il suo TextEquiv;
  - confidenza: attributo conf (0-1) di TextEquiv, pesato sulla lunghezza;
  - pagina stampata: il testo della regione di tipo «page-number», se è un numero (arabo o romano); quella
    regione non entra nel testo.
ALTO
  - un file può contenere più Page; testo da String/@CONTENT, SP = spazio, HYP = trattino di fine riga;
  - confidenza: @WC (0-1) delle String, altrimenti della TextLine;
  - pagina stampata: Page/@PRINTED_IMG_NR.
Tra due regioni (PAGE TextRegion, ALTO TextBlock) c'è una riga vuota, come nel testo dell'OCR proprio.

Le confidenze sono riportate in scala 0-100 come quelle di Tesseract, ma calcolate da motori diversi: non sono
confrontabili tra motori e restano indicative.

Un archivio .zip (esportazione di Transkribus o eScriptorium) si legge senza estrarlo: si usano solo i suoi
file .xml PAGE o ALTO, in ordine naturale dei nomi (2 prima di 10).
"""
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NUMERO_PAGINA = re.compile(r"^[\[(]?\s*(\d{1,4}[a-z]?|[ivxlcdm]{1,8})\s*[\])]?$", re.IGNORECASE)


def _locale(tag):
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _figli(el, nome):
    return [c for c in el if _locale(c.tag) == nome]


def _primo(el, nome):
    return next((c for c in el if _locale(c.tag) == nome), None)


def _tutti(el, nome):
    return [c for c in el.iter() if _locale(c.tag) == nome]


def chiave_naturale(nome):
    """Ordine naturale dei nomi di file: «p2.xml» prima di «p10.xml»."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(nome))]


def formato(radice):
    """'page', 'alto' o '' dalla radice del documento XML."""
    nome = _locale(radice.tag).lower()
    return {"pcgts": "page", "alto": "alto"}.get(nome, "")


def _conf(valore):
    try:
        c = float(valore)
    except (TypeError, ValueError):
        return None
    return c * 100 if c <= 1 else c            # 0-1 negli standard; qualche strumento scrive già 0-100


def _media(pesate):
    peso = sum(n for _, n in pesate)
    return round(sum(c * n for c, n in pesate) / peso, 1) if peso else None


def pagina_stampata(testo):
    """Numero di pagina stampato da un testo breve («12», «[12]», «xiv»), '' se non è un numero di pagina."""
    m = NUMERO_PAGINA.match((testo or "").strip())
    return m.group(1) if m else ""


# ---------------------------------------------------------------- PAGE
def _indice_custom(el):
    m = re.search(r"readingOrder\s*\{[^}]*index\s*:\s*(\d+)", el.get("custom", ""))
    return int(m.group(1)) if m else None


def _textequiv(el):
    """(testo, confidenza) del TextEquiv diretto di un elemento, scegliendo quello con l'index più basso."""
    eq = _figli(el, "TextEquiv")
    if not eq:
        return None, None
    eq.sort(key=lambda e: int(e.get("index", 0)) if (e.get("index") or "0").lstrip("-").isdigit() else 0)
    u = _primo(eq[0], "Unicode")
    return (u.text or "") if u is not None else "", _conf(eq[0].get("conf"))


def _riga_page(riga):
    """(testo, [(confidenza, lunghezza)]) di una TextLine."""
    testo, conf = _textequiv(riga)
    if testo is not None and testo.strip():
        return testo, ([(conf, len(testo))] if conf is not None else [])
    parole, pesate = [], []
    for w in _figli(riga, "Word"):
        t, c = _textequiv(w)
        if t:
            parole.append(t)
            if c is not None:
                pesate.append((c, len(t)))
    return " ".join(parole), pesate


def _riferimenti(gruppo):
    """regionRef di un gruppo del ReadingOrder nell'ordine di lettura: gli elementi indicizzati per index,
    i gruppi annidati al loro posto (gli indici valgono dentro il loro gruppo)."""
    voci = [e for e in gruppo if _locale(e.tag).startswith(("RegionRef", "OrderedGroup", "UnorderedGroup"))]
    voci.sort(key=lambda e: int(e.get("index")) if (e.get("index") or "").isdigit() else 0)
    out = []
    for e in voci:
        if _locale(e.tag).startswith("RegionRef"):
            out.append(e.get("regionRef"))
        else:
            out += ([e.get("regionRef")] if e.get("regionRef") else []) + _riferimenti(e)
    return out


def _regioni_in_ordine(page):
    """TextRegion della pagina nell'ordine di lettura."""
    regioni = _tutti(page, "TextRegion")
    per_id = {r.get("id"): r for r in regioni}
    ordine = []
    ro = _primo(page, "ReadingOrder")
    if ro is not None:
        ordine = list({id(per_id[r]): per_id[r] for r in _riferimenti(ro) if r in per_id}.values())
    if not ordine and any(_indice_custom(r) is not None for r in regioni):
        ordine = sorted(regioni, key=lambda r: (_indice_custom(r) is None, _indice_custom(r) or 0))
    visti = {id(r) for r in ordine}
    return ordine + [r for r in regioni if id(r) not in visti]     # regioni fuori dall'ordine: in coda


def leggi_page(radice, nome=""):
    page = _primo(radice, "Page")
    if page is None:
        return []
    blocchi, pesate, stampata = [], [], ""
    for reg in _regioni_in_ordine(page):
        righe_reg = []
        linee = _figli(reg, "TextLine")
        if any(_indice_custom(l) is not None for l in linee):
            linee.sort(key=lambda l: (_indice_custom(l) is None, _indice_custom(l) or 0))
        for l in linee:
            t, p = _riga_page(l)
            if t.strip():
                righe_reg.append(t.rstrip())
                pesate += p
        if not linee:
            t, c = _textequiv(reg)
            if t and t.strip():
                righe_reg = [x.rstrip() for x in t.splitlines() if x.strip()]
                if c is not None:
                    pesate.append((c, len(t)))
        tipo = (reg.get("type") or "").lower()
        if tipo == "page-number" or "type:page-number" in reg.get("custom", "").replace(" ", "").lower():
            stampata = stampata or pagina_stampata(" ".join(righe_reg))
            if stampata:
                continue                              # il numero diventa il marcatore di pagina
        if righe_reg:
            blocchi.append("\n".join(righe_reg))
    meta = _primo(radice, "Metadata")
    creatore = _primo(meta, "Creator") if meta is not None else None
    creatore = (creatore.text or "").strip() if creatore is not None else ""
    return [{"origine": nome, "immagine": page.get("imageFilename", ""), "testo": "\n\n".join(blocchi),
             "confidenza": _media(pesate), "pagina_stampata": stampata, "formato": "PAGE XML", "motore": creatore}]


# ---------------------------------------------------------------- ALTO
def _riga_alto(riga):
    """(testo, [(confidenza, lunghezza)]) di una TextLine. Due String consecutive senza SP sono comunque due
    parole (eScriptorium e altri omettono SP)."""
    pezzi, pesate, prec = [], [], ""
    for el in riga:
        n = _locale(el.tag)
        if n == "String":
            t = el.get("CONTENT", "")
            if prec == "String":
                pezzi.append(" ")
            pezzi.append(t)
            c = _conf(el.get("WC"))
            if c is not None and t:
                pesate.append((c, len(t)))
        elif n == "SP":
            pezzi.append(" ")
        elif n == "HYP":
            pezzi.append(el.get("CONTENT") or "-")
        prec = n
    testo = "".join(pezzi)
    if not pesate and riga.get("WC") and testo:
        c = _conf(riga.get("WC"))
        if c is not None:
            pesate.append((c, len(testo)))
    return re.sub(r"[ \t]+", " ", testo).strip(), pesate


def _motore_alto(radice):
    desc = _primo(radice, "Description")
    if desc is None:
        return ""
    nomi = [el.text.strip() for el in desc.iter()
            if _locale(el.tag) in ("softwareName", "softwareVersion") and el.text and el.text.strip()]
    return " ".join(dict.fromkeys(nomi))


def leggi_alto(radice, nome=""):
    layout = _primo(radice, "Layout")
    if layout is None:
        return []
    motore = _motore_alto(radice)
    out = []
    for page in _figli(layout, "Page"):
        blocchi, pesate = [], []
        for blocco in _tutti(page, "TextBlock"):
            righe = []
            for l in _figli(blocco, "TextLine"):
                t, p = _riga_alto(l)
                if t:
                    righe.append(t)
                    pesate += p
            if righe:
                blocchi.append("\n".join(righe))
        out.append({"origine": nome, "immagine": "", "testo": "\n\n".join(blocchi), "confidenza": _media(pesate),
                    "pagina_stampata": pagina_stampata(page.get("PRINTED_IMG_NR", "")), "formato": "ALTO XML",
                    "motore": motore})
    return out


# ---------------------------------------------------------------- file e archivi
def leggi_xml(dati, nome=""):
    """Pagine di un documento XML (contenuto in bytes). [] se non è PAGE né ALTO (METS, metadati...)."""
    try:
        radice = ET.fromstring(dati)
    except ET.ParseError as e:
        raise ValueError(f"{nome}: XML non valido ({e})") from e
    f = formato(radice)
    if f == "page":
        return leggi_page(radice, nome)
    if f == "alto":
        return leggi_alto(radice, nome)
    return []


def leggi(percorso):
    """(pagine, ignorati) di un file .xml o di un archivio .zip di esportazione. 'ignorati' elenca i file XML
    che non sono PAGE né ALTO."""
    p = Path(percorso)
    pagine, ignorati = [], []
    if p.suffix.lower() == ".zip":
        with zipfile.ZipFile(p) as z:
            nomi = sorted((n for n in z.namelist() if n.lower().endswith(".xml") and not n.endswith("/")),
                          key=chiave_naturale)
            for n in nomi:
                lette = leggi_xml(z.read(n), f"{p.name}:{n}")
                (pagine.extend(lette) if lette else ignorati.append(n))
        return pagine, ignorati
    lette = leggi_xml(p.read_bytes(), p.name)
    return (lette, []) if lette else ([], [p.name])


def marcatore(pagina, n_immagine):
    """Marcatore di pagina [[p. N | img K]] quando la pagina stampata è dichiarata nel file; '' altrimenti
    (una pagina non dichiarata non è una pagina «non numerata»: il numero va ricavato dopo)."""
    return f"[[p. {pagina['pagina_stampata']} | img {n_immagine}]]" if pagina.get("pagina_stampata") else ""


def main():
    import sys
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    for arg in sys.argv[1:]:
        pagine, ignorati = leggi(arg)
        for k, pg in enumerate(pagine, 1):
            print(f"--- {pg['origine']} ({pg['formato']}, motore: {pg['motore'] or '?'}, pagina stampata: "
                  f"{pg['pagina_stampata'] or '-'}, confidenza: {pg['confidenza']})")
            print(pg["testo"][:800])
        if ignorati:
            print(f"Ignorati (non PAGE né ALTO): {', '.join(ignorati)}")


if __name__ == "__main__":
    main()

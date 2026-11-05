#!/usr/bin/env python3
"""
Esportazioni di una risposta o di una ricerca, nei formati che i ricercatori usano fuori da Pressmark:

  csl     CSL-JSON (Zotero, Mendeley, Pandoc): un elemento per documento citato o pertinente
  bibtex  BibTeX (LaTeX, JabRef, Zotero): gli stessi documenti
  csv     i passaggi letti, uno per riga (Excel, LibreOffice: punto e virgola, UTF-8 con BOM)
  docx    la risposta in Word, con i rimandi [n] diventati note a piè di pagina in stile Chicago

I metadati dei documenti vengono dall'intestazione dei file in data/ ([TITLE: …], [AUTHOR: …], [DATE: …]);
la citazione completa (FULL_CITATION) resta nella nota di ogni elemento, perché è quella che il progetto ha
verificato. Solo libreria standard di Python: il file Word è scritto a mano (Office Open XML in uno zip).
"""
import csv
import io
import json
import re
import zipfile
from xml.sax.saxutils import escape

FORMATI = {"csl": ("application/vnd.citationstyles.csl+json; charset=utf-8", ".json"),
           "bibtex": ("application/x-bibtex; charset=utf-8", ".bib"),
           "csv": ("text/csv; charset=utf-8", ".csv"),
           "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".docx")}


# ------------------------------------------------------------------ metadati dei documenti
def _data_parti(meta):
    """[anno, mese, giorno] (quelli noti) da DATE (AAAA-MM-GG, AAAA-MM o AAAA) o da YEAR."""
    d = (meta.get("DATE") or "").strip()
    m = re.match(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", d)
    if m:
        return [int(x) for x in m.groups() if x]
    a = re.match(r"\d{4}", (meta.get("YEAR") or "").strip())
    return [int(a.group(0))] if a else []


def _autori(testo):
    """«Cognome, Nome; Cognome2, Nome2» o «Nome Cognome» -> autori CSL; un ente resta un nome letterale."""
    out = []
    for a in re.split(r"\s*;\s*|\s+and\s+|\s+e\s+", (testo or "").strip()):
        if not a:
            continue
        if "," in a:
            cognome, nome = [x.strip() for x in a.split(",", 1)]
            out.append({"family": cognome, "given": nome})
        else:
            out.append({"literal": a})
    return out


def _tipo(meta):
    """Tipo CSL dal contenuto dell'intestazione: archivio (segnatura), periodico (numero o data piena), volume."""
    if meta.get("CALL_NUMBER"):
        return "manuscript"
    if meta.get("ISSUE") or len(_data_parti(meta)) == 3:
        return "article-newspaper"
    if meta.get("PUBLISHER") and not meta.get("SERIES"):
        return "book"
    return "article-journal" if meta.get("VOLUME") else "document"


def _chiave(meta, file, viste):
    """Chiave BibTeX/CSL leggibile e unica: cognome (o serie) + anno + prima parola del titolo."""
    autore = _autori(meta.get("AUTHOR"))
    base = (autore[0].get("family") or autore[0].get("literal", "")) if autore else (meta.get("SERIES") or file)
    anno = (_data_parti(meta) or [""])[0]
    titolo = re.findall(r"[A-Za-zÀ-ÿ]{4,}", meta.get("TITLE") or "")
    k = re.sub(r"[^A-Za-z0-9]", "", _ascii(f"{base}{anno}{titolo[0] if titolo else ''}"))[:40] or "doc"
    finale, n = k, 1
    while finale in viste:
        n += 1
        finale = f"{k}{chr(96 + n) if n < 27 else n}"
    viste.add(finale)
    return finale


def _ascii(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


_IN_VOLUME = re.compile(r"\bIn \*?(?P<libro>[^*]+?)\*?,\s*(?:edited by|a cura di)\s+(?P<curatori>.+?)"
                        r"(?:,\s*(?:pp?\.\s*)?[\d–-]+)?\.?\s*$")


def in_volume(meta):
    """(volume, curatori) se la citazione completa dice «In *Volume*, edited by A and B, 45–50.»: un documento
    pubblicato in una raccolta curata (le serie di tipo raccolta o archivio edito)."""
    m = _IN_VOLUME.search(re.sub(r"\s+", " ", meta.get("FULL_CITATION") or ""))
    return (m.group("libro").strip(), m.group("curatori").strip()) if m else (None, None)


def elemento_csl(meta, file, chiave, pagine=()):
    e = {"id": chiave, "type": _tipo(meta), "title": meta.get("TITLE") or meta.get("SERIES") or file}
    volume, curatori = in_volume(meta)
    if volume:
        e["type"] = "chapter"
        e["container-title"] = volume
        e["editor"] = [{"literal": c} for c in re.split(r"\s*;\s*|\s+and\s+|\s+e\s+", curatori) if c]
    if meta.get("AUTHOR"):
        e["author"] = _autori(meta["AUTHOR"])
    parti = _data_parti(meta)
    if parti:
        e["issued"] = {"date-parts": [parti]}
    for k, campo in (("SERIES", "container-title"), ("PUBLISHER", "publisher"),
                     ("PUBLICATION_PLACE", "publisher-place"), ("VOLUME", "volume"), ("ISSUE", "issue"),
                     ("CALL_NUMBER", "archive_location"), ("LANG", "language")):
        if meta.get(k) and not (k == "SERIES" and e["title"] == meta[k]) and campo not in e:
            e[campo] = meta[k]
    if pagine:
        e["page"] = ", ".join(sorted(set(p for p in pagine if p), key=lambda x: (len(x), x)))
    elif meta.get("PAGES"):
        e["page"] = meta["PAGES"]
    if meta.get("FULL_CITATION"):
        e["note"] = re.sub(r"[*_]", "", meta["FULL_CITATION"])
    e["source"] = f"Pressmark: {file}"
    return e


def csl(documenti):
    """documenti: [(meta, file, pagine)] -> testo CSL-JSON."""
    viste = set()
    return json.dumps([elemento_csl(m, f, _chiave(m, f, viste), p) for m, f, p in documenti],
                      ensure_ascii=False, indent=2)


def _bib(v):
    return (v or "").replace("\\", "\\textbackslash{}").replace("{", "\\{").replace("}", "\\}") \
        .replace("&", "\\&").replace("%", "\\%").replace("#", "\\#").replace("_", "\\_")


def bibtex(documenti):
    viste, out = set(), []
    for meta, file, pagine in documenti:
        e = elemento_csl(meta, file, _chiave(meta, file, viste), pagine)
        tipo = {"article-newspaper": "article", "article-journal": "article", "book": "book",
                "manuscript": "unpublished", "chapter": "incollection"}.get(e["type"], "misc")
        campi = [("title", e["title"])]
        if e.get("author"):
            campi.append(("author", " and ".join(
                f"{a['family']}, {a['given']}" if "family" in a else "{" + a["literal"] + "}" for a in e["author"])))
        parti = (e.get("issued") or {}).get("date-parts", [[]])[0]
        if parti:
            campi.append(("year", str(parti[0])))
            if len(parti) > 1:
                campi.append(("month", str(parti[1])))
            if len(parti) > 2:
                campi.append(("day", str(parti[2])))
            campi.append(("date", "-".join(f"{x:02d}" if i else str(x) for i, x in enumerate(parti))))
        if e.get("editor"):
            campi.append(("editor", " and ".join(x["literal"] for x in e["editor"])))
        for k, b in (("container-title", {"article": "journal", "incollection": "booktitle"}.get(tipo, "howpublished")),
                     ("publisher", "publisher"), ("publisher-place", "address"), ("volume", "volume"),
                     ("issue", "number"), ("page", "pages"), ("archive_location", "note"), ("language", "langid")):
            if e.get(k):
                campi.append((b, e[k]))
        if e.get("note"):
            campi.append(("annote", e["note"]))
        campi.append(("file", file))
        out.append(f"@{tipo}{{{e['id']},\n" + ",\n".join(f"  {k} = {{{_bib(v) if k != 'author' else v}}}"
                                                         for k, v in campi) + "\n}\n")
    return "\n".join(out)


COLONNE_CSV = ["data", "fonte", "pagina", "pertinente", "corretto_a_mano", "letto_da", "traduzione", "file", "riga",
               "collegamento"]


def tabella_csv(passaggi, base=""):
    """I passaggi in CSV: punto e virgola e BOM, come le tabelle di revisione, così Excel lo apre con un doppio
    clic. «collegamento» apre il passaggio in Pressmark finché l'interfaccia è aperta a quell'indirizzo."""
    from urllib.parse import urlencode
    buf = io.StringIO()
    buf.write("﻿")
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(COLONNE_CSV)
    for p in passaggi:
        link = f"{base}/?{urlencode({'fonte': p.get('file', ''), 'riga': p.get('riga', '')})}" if base else ""
        w.writerow([p.get("data", ""), re.sub(r"[*_]", "", p.get("fonte", "")), p.get("pagina", ""),
                    p.get("pertinente", ""), "sì" if p.get("corretto") else "", p.get("letto_da", ""),
                    p.get("traduzione", ""), p.get("file", ""), p.get("riga", ""), link])
    return buf.getvalue()


# ------------------------------------------------------------------ Word con note a piè di pagina
W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'

_STILI = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles {W}>
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Georgia" w:hAnsi="Georgia" w:eastAsia="SimSun" w:cs="Georgia"/>
<w:sz w:val="22"/><w:lang w:val="it-IT"/></w:rPr></w:rPrDefault>
<w:pPrDefault><w:pPr><w:spacing w:after="160" w:line="300" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:after="240"/></w:pPr><w:rPr><w:sz w:val="40"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>
<w:pPr><w:keepNext/><w:spacing w:before="360" w:after="120"/><w:outlineLvl w:val="0"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>
<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="80"/><w:outlineLvl w:val="1"/></w:pPr>
<w:rPr><w:b/><w:sz w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Quote"><w:name w:val="Quote"/><w:basedOn w:val="Normal"/>
<w:pPr><w:ind w:left="567" w:right="567"/></w:pPr><w:rPr><w:sz w:val="21"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/>
<w:pPr><w:ind w:left="567" w:hanging="283"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="FootnoteText"><w:name w:val="footnote text"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:after="60" w:line="240" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="18"/></w:rPr></w:style>
<w:style w:type="character" w:styleId="FootnoteReference"><w:name w:val="footnote reference"/>
<w:rPr><w:vertAlign w:val="superscript"/></w:rPr></w:style>
</w:styles>"""


def _run(testo, b=False, i=False, mono=False):
    if not testo:
        return ""
    pr = ("<w:b/>" if b else "") + ("<w:i/>" if i else "") + \
         ('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>' if mono else "")
    return f'<w:r>{"<w:rPr>" + pr + "</w:rPr>" if pr else ""}<w:t xml:space="preserve">{escape(testo)}</w:t></w:r>'


_INLINE = re.compile(r"\*\*(.+?)\*\*|\*([^*\s][^*]*?)\*|`([^`]+)`|((?:\s*\[\s*\d+(?:\s*[,;]\s*\d+)*\s*\])+)")


class _Note:
    """Le note a piè di pagina: ogni rimando [n] diventa una nota con il riferimento completo la prima volta e
    in forma breve le volte successive (Chicago, 14.29)."""
    def __init__(self, riferimenti):
        self.riferimenti, self.xml, self.usati = riferimenti, [], set()

    def nota(self, numeri):
        parti = []
        for n in numeri:
            rif = self.riferimenti.get(n, f"Documento {n}")
            if n in self.usati:
                breve = re.split(r"(?<=[.”])\s", rif, maxsplit=2)
                rif = " ".join(breve[:2]) if len(breve) > 2 else rif
            self.usati.add(n)
            parti.append(rif.rstrip(". ") + ".")
        k = len(self.xml) + 1
        self.xml.append(f'<w:footnote w:id="{k}"><w:p><w:pPr><w:pStyle w:val="FootnoteText"/></w:pPr>'
                        f'<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteRef/></w:r>'
                        f'{_run(" ")}{_inline(" ".join(parti), None)}</w:p></w:footnote>')
        return f'<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteReference w:id="{k}"/></w:r>'


def _inline(testo, note):
    out, pos = [], 0
    for m in _INLINE.finditer(testo):
        out.append(_run(testo[pos:m.start()]))
        if m.group(1) is not None:
            out.append(_run(m.group(1), b=True))
        elif m.group(2) is not None:
            out.append(_run(m.group(2), i=True))
        elif m.group(3) is not None:
            out.append(_run(m.group(3), mono=True))
        elif note is not None:
            numeri = []
            for n in re.findall(r"\d+", m.group(4)):
                if int(n) not in numeri:
                    numeri.append(int(n))
            out.append(note.nota(numeri))
        else:
            out.append(_run(m.group(4)))
        pos = m.end()
    out.append(_run(testo[pos:]))
    return "".join(out)


def _paragrafo(testo, note, stile=None):
    pr = f'<w:pPr><w:pStyle w:val="{stile}"/></w:pPr>' if stile else ""
    return f"<w:p>{pr}{_inline(testo, note)}</w:p>"


def docx(md, riferimenti):
    """La risposta (Markdown di documento.py) in Word. riferimenti: {n: riferimento Chicago}. La sezione dei dati
    tecnici (file e righe) resta fuori: serve a verificare in Pressmark, non a chi legge."""
    md = re.sub(r"<!--.*?-->\s*", "", md, flags=re.DOTALL)
    md = re.split(r"^## \d+\.\s*Dati tecnici.*$", md, flags=re.MULTILINE)[0]
    note, corpo = _Note(riferimenti), []
    for blocco in re.split(r"\n\s*\n", md.strip()):
        righe = [r.rstrip() for r in blocco.splitlines() if r.strip()]
        if not righe:
            continue
        primo = righe[0]
        if primo.startswith("# "):
            corpo.append(_paragrafo(primo[2:].strip(), None, "Title"))
            righe = righe[1:]
        elif primo.startswith("## "):
            corpo.append(_paragrafo(primo[3:].strip(), None, "Heading1"))
            righe = righe[1:]
        elif primo.startswith("### "):
            corpo.append(_paragrafo(re.sub(r"^\[\d+\]\s*", "", primo[4:].strip()), None, "Heading2"))
            righe = righe[1:]
        if not righe:
            continue
        if all(r.lstrip().startswith(">") for r in righe):
            corpo.append(_paragrafo(" ".join(r.lstrip()[1:].strip() for r in righe), note, "Quote"))
        elif all(re.match(r"\s*([-*]|\d+\.)\s", r) for r in righe):
            for r in righe:
                corpo.append(_paragrafo("• " + re.sub(r"^\s*([-*]|\d+\.)\s+", "", r), note, "ListParagraph"))
        elif all(re.match(r"\[\d+\]\s", r) for r in righe):        # elenco dei documenti: già nelle note
            for r in righe:
                corpo.append(_paragrafo(re.sub(r"\s*\(`[^`]*`[^)]*\)", "", r), None, "ListParagraph"))
        else:
            corpo.append(_paragrafo(" ".join(r.strip() for r in righe), note))
    documento = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document {W}><w:body>'
                 + "".join(corpo) +
                 '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1418" w:right="1418" w:bottom="1418" '
                 'w:left="1418" w:header="709" w:footer="709" w:gutter="0"/></w:sectPr></w:body></w:document>')
    separatori = ('<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
                  '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/>'
                  '</w:r></w:p></w:footnote>')
    footnotes = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:footnotes {W}>{separatori}'
                 + "".join(note.xml) + "</w:footnotes>")
    tipi = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.styles+xml"/>'
            '<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.footnotes+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'officeDocument" Target="word/document.xml"/></Relationships>')
    rels_doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
                'styles" Target="styles.xml"/>'
                '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
                'footnotes" Target="footnotes.xml"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", tipi)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/_rels/document.xml.rels", rels_doc)
        z.writestr("word/document.xml", documento)
        z.writestr("word/styles.xml", _STILI)
        z.writestr("word/footnotes.xml", footnotes)
    return buf.getvalue()

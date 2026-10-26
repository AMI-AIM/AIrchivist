"""
Tabelle compilate dal ricercatore in Excel o LibreOffice: lettura dei file .xlsx con la sola libreria standard
(valutazione.py, revisione.py).
"""
import re


def leggi_xlsx(path):
    """Righe del primo foglio di un file .xlsx, come liste di testi (solo libreria standard)."""
    import xml.etree.ElementTree as ET
    import zipfile
    m = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    with zipfile.ZipFile(path) as z:
        condivise = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{m}si"):
                condivise.append("".join(t.text or "" for t in si.findall(f"{m}t") + si.findall(f"{m}r/{m}t")))
        primo = ET.fromstring(z.read("xl/workbook.xml")).find(f"{m}sheets/{m}sheet")
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        dest = next(r.get("Target") for r in rels if r.get("Id") == primo.get(rel))
        foglio = ET.fromstring(z.read(dest.lstrip("/") if dest.startswith("/") else "xl/" + dest))
    tabella = []
    for riga in foglio.iter(f"{m}row"):
        valori = {}
        for i, c in enumerate(riga.findall(f"{m}c")):
            ref = re.match(r"[A-Z]+", c.get("r") or "")
            col = i
            if ref:
                col = 0
                for ch in ref.group(0):
                    col = col * 26 + ord(ch) - 64
                col -= 1
            tipo, v = c.get("t"), c.find(f"{m}v")
            if tipo == "s":
                x = condivise[int(v.text)]
            elif tipo == "inlineStr":
                x = "".join(t.text or "" for t in c.iter(f"{m}t"))
            else:
                x = v.text if v is not None and v.text else ""
                if tipo in (None, "n") and re.fullmatch(r"-?\d+\.0+", x):
                    x = x.split(".")[0]                  # 129801.0 -> 129801 (scostamenti, numeri)
            valori[col] = x
        tabella.append([valori.get(i, "") for i in range(max(valori) + 1)] if valori else [])
    return tabella

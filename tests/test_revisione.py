"""
Test dell'importazione guidata con tabella di revisione (lavoro 29: revisione.py, importa.py proponi | applica |
rivedi) su un corpus di prova misto generato al momento: fascicoli di un periodico con la data nel nome (testo
nativo), un fascicolo in scansione senza testo, un articolo nativo con etichette di pagina e metadati, un volume
con i numeri di pagina stampati, un file di testo. Progetto temporaneo (AIRCHIVIST_PROGETTO), nessun OCR.
"""
import argparse
import csv
import io
import json
import os
import sys
import tempfile
import unittest
from collections import Counter
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOTORE))
import importa as I  # noqa: E402
import profili  # noqa: E402
import revisione as R  # noqa: E402
from estrai_occorrenze import leggi_intestazione  # noqa: E402
from progetto import VARIABILE, cmd_nuovo  # noqa: E402

try:
    FITZ = I.carica_pymupdf()
    FITZ.open                                       # pypdf non basta: servono PDF da creare
    import fitz as FITZ  # noqa: F811
except ImportError:
    FITZ = None

ALBANESE = ("Partia e Punës e Shqipërisë dhe populli shqiptar janë të bashkuar për ndërtimin e socializmit në "
            "vendin tonë. Shokët e komitetit qendror ishin në mbledhjen që u mbajt në Tiranë. ") * 6
INGLESE = ("The Albanian leadership has insisted that the country will follow its own road, and the break with "
           "China was presented as a defence of principle. It is not clear that this is the whole story. ") * 5
FRANCESE = ("Le parti a publié une déclaration dans laquelle il est dit que la ligne du comité est juste et que "
            "les militants doivent étudier les textes. ") * 6


def pdf(f, testi, etichette=None, meta=None, scansione=False):
    f.parent.mkdir(parents=True, exist_ok=True)
    doc = FITZ.open()
    for t in testi:
        pag = doc.new_page(width=420, height=595)
        if scansione:                               # immagine a tutta pagina, niente strato di testo
            img = FITZ.open()
            img.new_page(width=420, height=595).insert_textbox(FITZ.Rect(30, 30, 390, 565), t, fontsize=9)
            pix = img[0].get_pixmap(dpi=150)
            pag.insert_image(pag.rect, stream=pix.tobytes("png"))
        else:
            pag.insert_textbox(FITZ.Rect(30, 30, 390, 565), t, fontsize=8)
    if etichette:
        doc.set_page_labels(etichette)
    if meta:
        doc.set_metadata(meta)
    doc.save(f)
    return f


@unittest.skipIf(FITZ is None, "PyMuPDF assente: servirebbe a creare i PDF di prova")
class Revisione(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.progetto = self.tmp / "progetto"
        with redirect_stdout(io.StringIO()):
            cmd_nuovo(argparse.Namespace(cartella=str(self.progetto), nome="Prova", descrizione=""))
        env = mock.patch.dict(os.environ, {VARIABILE: str(self.progetto)})
        env.start()
        self.addCleanup(env.stop)
        profili.tutti(ricarica=True)
        self.addCleanup(lambda: profili.tutti(ricarica=True))
        c = self.corpus = self.tmp / "da_importare"
        for data in ("1967-01-12", "1967-01-13"):
            pdf(c / "zeri_i_popullit" / f"ZP{data}.pdf", ["ZËRI I POPULLIT\n" + ALBANESE, ALBANESE])
        pdf(c / "zeri_i_popullit" / "ZP1967-01-14.pdf", ["ZËRI I POPULLIT\n" + ALBANESE], scansione=True)
        pdf(c / "Larrabee_Whither_Albania.pdf", [INGLESE] * 9,
            etichette=[{"startpage": 0, "prefix": "", "style": "D", "firstpagenum": 61}],
            meta={"title": "Whither Albania?", "author": "F. Stephen Larrabee"})
        pdf(c / "storia_del_partito.pdf", [f"STORIA DEL PARTITO {k + 10}\n" + FRANCESE for k in range(90)])
        (c / "note.txt").write_text("Le 12 janvier 1967. " + FRANCESE, encoding="utf-8")

    def comando(self, *argomenti):
        with redirect_stdout(io.StringIO()) as uscita:
            codice = I.main(list(map(str, argomenti)))
        return codice, uscita.getvalue()

    def tabella(self):
        f = next((self.progetto / "audit").glob("review_2*.csv"))
        return f, R.leggi_tabella(f)

    def scrivi(self, f, righe, colonne=R.COLONNE):
        R.scrivi_tabella(f, colonne, righe)

    def test_proposta(self):
        codice, uscita = self.comando("proponi", self.corpus)
        self.assertEqual(codice, 0, uscita)
        f, righe = self.tabella()
        self.assertTrue(f.read_bytes().startswith(b"\xef\xbb\xbf"))            # Excel: BOM e punto e virgola
        self.assertIn(";", f.read_text(encoding="utf-8-sig").splitlines()[0])
        per_file = {r["file"]: r for r in righe}
        zp = per_file["zeri_i_popullit/ZP1967-01-12.pdf"]
        self.assertEqual((zp["serie"], zp["tipo_serie"], zp["lingua"], zp["sigla"], zp["cartella_serie"]),
                         ("Zëri I Popullit", "periodico", "sq", "ZP", "riviste/zeri_i_popullit"))
        self.assertEqual((zp["data"], zp["stato_data"], zp["tipo_documento"], zp["testo"]),
                         ("1967-01-12", "dedotto", "fascicolo", "testo nativo"))
        scan = per_file["zeri_i_popullit/ZP1967-01-14.pdf"]
        self.assertEqual(scan["serie"], zp["serie"])
        self.assertEqual(scan["testo"], "scansione senza testo")
        self.assertTrue(scan["qualita_ocr"].startswith("bassa"), scan["qualita_ocr"])    # 150 dpi
        art = per_file["Larrabee_Whither_Albania.pdf"]
        self.assertEqual((art["tipo_documento"], art["titolo"], art["autore"], art["pagine"], art["lingua"]),
                         ("articolo", "Whither Albania?", "Larrabee, F. Stephen", "61-69", "en"))
        self.assertIn("serie da indicare", art["da_controllare"])
        vol = per_file["storia_del_partito.pdf"]
        self.assertEqual((vol["tipo_documento"], vol["tipo_serie"], vol["lingua"]), ("volume", "volume", "fr"))
        self.assertEqual(vol["pagine"], "10-99")
        self.assertEqual(vol["serie"], "Storia Del Partito")                  # un libro da solo: il suo titolo
        self.assertIn("pagine dedotte", vol["da_controllare"])
        self.assertEqual(per_file["note.txt"]["testo"], "testo nativo")
        self.assertTrue(f.with_suffix(".json").exists())
        self.assertFalse(list((self.progetto / "data").rglob("*.txt")))       # proporre non importa nulla

    def test_applica(self):
        self.comando("proponi", self.corpus)
        f, righe = self.tabella()
        per_file = {r["file"]: r for r in righe}
        per_file["Larrabee_Whither_Albania.pdf"].update(serie="The World Today", tipo_serie="periodico",
                                                        cartella_serie="riviste/world_today", data="1978-02",
                                                        sigla="WT")
        per_file["zeri_i_popullit/ZP1967-01-13.pdf"]["data"] = "1967-01-15"       # correzione a mano
        for k in ("zeri_i_popullit/ZP1967-01-14.pdf", "storia_del_partito.pdf", "note.txt"):
            per_file[k]["importa"] = "no"
        self.scrivi(f, righe)
        codice, uscita = self.comando("applica", f, "--prova")
        self.assertEqual(codice, 0, uscita)
        self.assertIn("serie da creare", uscita)
        self.assertFalse(list((self.progetto / "data").rglob("*.txt")))
        codice, uscita = self.comando("applica", f)
        self.assertEqual(codice, 0, uscita)
        serie = profili.tutti(ricarica=True)
        self.assertEqual(serie["Zëri I Popullit"]["sigla"], "ZP")
        self.assertEqual(serie["The World Today"]["tipo"], "periodico")
        dati = self.progetto / "data"
        m12 = leggi_intestazione((dati / "riviste/zeri_i_popullit/ZP1967-01-12.txt").read_text(encoding="utf-8"))[0]
        self.assertEqual((m12["DATE"], m12["DATE_STATUS"], m12["DATE_NOTE"]), ("1967-01-12", "dedotto", "dal nome del file"))
        m15 = leggi_intestazione((dati / "riviste/zeri_i_popullit/ZP1967-01-15.txt").read_text(encoding="utf-8"))[0]
        self.assertEqual(m15["DATE"], "1967-01-15")
        self.assertNotIn("DATE_STATUS", m15)                                   # corretta a mano: verificata
        art = next((dati / "riviste/world_today").glob("*.txt")).read_text(encoding="utf-8")
        ma = leggi_intestazione(art)[0]
        self.assertEqual((ma["TITLE"], ma["AUTHOR"], ma["PAGES"]), ("Whither Albania?", "Larrabee, F. Stephen", "61-69"))
        self.assertIn("[[p. 61 | pdf 1]]", art)
        modifiche = list(csv.reader(io.StringIO((self.progetto / "audit/changes.csv").read_text(encoding="utf-8-sig"))))
        self.assertIn(["riviste/zeri_i_popullit/ZP1967-01-15.txt", "DATE", "1967-01-13", "1967-01-15",
                       "corretto nella tabella di revisione dell'importazione (importa.py applica)"], modifiche)
        self.assertTrue(any(r[1] == "SERIES" and r[3] == "The World Today" for r in modifiche))
        codice, uscita = self.comando("controlla")                     # intestazioni valide
        self.assertEqual(codice, 0, uscita)
        self.assertIn(": 0 errori", uscita)
        importazioni = csv.DictReader(io.StringIO((self.progetto / "audit/imports.csv").read_text(encoding="utf-8-sig")))
        self.assertEqual(Counter(r["serie"] for r in importazioni), {"Zëri I Popullit": 2, "The World Today": 1})

    def test_errori_della_tabella(self):
        self.comando("proponi", self.corpus)
        f, righe = self.tabella()
        per_file = {r["file"]: r for r in righe}
        per_file["zeri_i_popullit/ZP1967-01-12.pdf"]["stato_data"] = "forse"
        per_file["zeri_i_popullit/ZP1967-01-13.pdf"]["serie"] = ""
        per_file["storia_del_partito.pdf"]["prima_pagina"] = "dieci"
        self.scrivi(f, righe)
        codice, uscita = self.comando("applica", f)
        self.assertEqual(codice, 2)
        for testo in ("stato_data «forse»", "manca la serie", "prima_pagina deve essere un numero"):
            self.assertIn(testo, uscita)
        self.assertFalse(list((self.progetto / "data").rglob("*.txt")))

    def test_rivedi(self):
        self.comando("proponi", self.corpus / "zeri_i_popullit")
        f, righe = self.tabella()
        for r in righe:
            r["importa"] = "no" if "01-14" in r["file"] else "sì"
        self.scrivi(f, righe)
        self.assertEqual(self.comando("applica", f)[0], 0)
        file_dati = self.progetto / "data/riviste/zeri_i_popullit/ZP1967-01-12.txt"
        prima = file_dati.read_bytes()
        nl = b"\r\n" if b"\r\n" in prima else b"\n"
        codice, uscita = self.comando("rivedi", "--serie", "Zëri I Popullit", "--solo-dubbi")
        self.assertEqual(codice, 0, uscita)
        fr = next((self.progetto / "audit").glob("review_rivedi_*.csv"))
        righe = R.leggi_tabella(fr)
        self.assertEqual(len(righe), 2)
        r = next(x for x in righe if x["file_dati"].endswith("ZP1967-01-12.txt"))
        self.assertEqual((r["data"], r["stato_data"]), ("1967-01-12", "dedotto"))
        r["numero"], r["stato_data"] = "12", "verificato"
        self.scrivi(fr, righe, R.COLONNE_RIVEDI)
        codice, uscita = self.comando("applica", fr)
        self.assertEqual(codice, 0, uscita)
        dopo = file_dati.read_bytes()
        self.assertEqual(b"\r\n" in dopo, nl == b"\r\n")                      # fine riga conservati
        meta = leggi_intestazione(dopo.decode("utf-8"))[0]
        self.assertEqual(meta["ISSUE"], "12")
        self.assertNotIn("DATE_STATUS", meta)
        self.assertEqual(dopo.split(nl + nl, 1)[1], prima.split(nl + nl, 1)[1])     # testo intatto
        copia = next((self.progetto / "system/backups").rglob("ZP1967-01-12.txt"))
        self.assertEqual(copia.read_bytes(), prima)
        modifiche = (self.progetto / "audit/changes.csv").read_text(encoding="utf-8-sig")
        self.assertIn("ZP1967-01-12.txt,ISSUE,(assente),12,revisione in tabella", modifiche)
        self.assertIn("ZP1967-01-12.txt,DATE_STATUS,dedotto,(assente)", modifiche)


def xlsx(f, righe):
    """Cartella di lavoro Excel minima (celle in linea), come la salverebbe chi apre la tabella in Excel."""
    import zipfile
    from xml.sax.saxutils import escape

    def cella(c, v):
        lettera = chr(65 + c) if c < 26 else "A" + chr(65 + c - 26)
        return f'<c r="{lettera}{{r}}" t="inlineStr"><is><t>{escape(v)}</t></is></c>'
    righe_xml = "".join(f'<row r="{n}">' + "".join(cella(c, v).format(r=n) for c, v in enumerate(r)) + "</row>"
                        for n, r in enumerate(righe, 1))
    ns = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"'
    rel = 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'
    with zipfile.ZipFile(f, "w") as z:
        z.writestr("xl/workbook.xml", f'<workbook {ns} {rel}><sheets><sheet name="a" sheetId="1" r:id="rId1"/>'
                                      "</sheets></workbook>")
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                   '<Relationship Id="rId1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", f"<worksheet {ns}><sheetData>{righe_xml}</sheetData></worksheet>")


class Tabelle(unittest.TestCase):
    def test_xlsx(self):
        f = Path(tempfile.mkdtemp()) / "review.xlsx"
        xlsx(f, [["importa", "file", "serie", "data"], ["sì", "a.pdf", "Zëri i Popullit", "1967-01-12"],
                 ["no", "b.pdf", "", ""]])
        self.assertEqual(R.leggi_tabella(f), [{"importa": "sì", "file": "a.pdf", "serie": "Zëri i Popullit",
                                               "data": "1967-01-12"},
                                              {"importa": "no", "file": "b.pdf", "serie": "", "data": ""}])
        self.assertEqual(R.file_proposte(f).name, "review.json")          # le proposte valgono anche per l'xlsx


class Lingua(unittest.TestCase):
    def test_lingue(self):
        self.assertEqual(R.lingua_del_testo(ALBANESE), "sq")
        self.assertEqual(R.lingua_del_testo(INGLESE), "en")
        self.assertEqual(R.lingua_del_testo("中国共产党中央委员会发表声明，支持阿尔巴尼亚劳动党的立场。" * 5), "zh")
        self.assertEqual(R.lingua_del_testo("1967 12 3"), "")

    def test_frontespizio_jstor(self):
        testo = ("The Transnational and the Text-Searchable\nAuthor(s): Lara Putnam\nSource: The American Historical "
                 "Review, APRIL 2016, Vol. 121, No. 2 (APRIL 2016), pp. 377-402\x005.91.141.123 on Sat, 24 Oct 2026 "
                 "08:53:48 UTC")
        self.assertEqual(R.fonte_jstor(testo), {"serie": "The American Historical Review", "data": "2016-04",
                                                "volume": "121", "numero": "2", "autore": "Lara Putnam"})
        self.assertEqual(R.fonte_jstor("Senza frontespizio, 1967."), {})

    def test_nome_ambiguo(self):
        self.assertIn("mese o il numero", R.data_e_numero("PR1967-11")[2])
        self.assertEqual(R.data_e_numero("ZP1967-01-12")[:2], ("1967-01-12", ""))


if __name__ == "__main__":
    unittest.main()

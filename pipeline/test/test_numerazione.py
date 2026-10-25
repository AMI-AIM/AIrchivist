"""
Test delle pagine stampate dei PDF importati (numerazione.py, importa.py): etichette di pagina, numeri stampati in
testa e in piede con scarto costante, indicazione dell'operatore, marcatori [[p. N | pdf K]] e citazioni. Casi
modellati sui PDF della prova del 25/10/2026: Larrabee, «Whither Albania?» (JSTOR, etichette «p. 61»...) e
*History of the PLA* (numero stampato in prima riga). L'importazione si prova su PDF generati con PyMuPDF.
"""
import argparse
import configparser
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))
import citazioni as C  # noqa: E402
import importa as I  # noqa: E402
import numerazione as N  # noqa: E402

try:
    FITZ = I.carica_pymupdf()
except ImportError:          # PyMuPDF è facoltativo: senza, si saltano i test sui PDF
    FITZ = None

PAROLE = "The Party continued the struggle against revisionism and for the construction of socialism. " * 6


class Etichette(unittest.TestCase):
    def test_jstor(self):
        etichette = ["", "p. 61", "p. 62", "p. 63"]                      # copertina di JSTOR senza etichetta
        self.assertEqual(N.da_etichette(etichette), {2: "61", 3: "62", 4: "63"})

    def test_predefinite_non_valgono(self):
        self.assertEqual(N.da_etichette(["1", "2", "3"]), {})
        self.assertEqual(N.da_etichette([]), {})

    def test_romane(self):
        self.assertEqual(N.da_etichette(["i", "ii", "1", "2"]), {1: "i", 2: "ii", 3: "1", 4: "2"})


class NumeriStampati(unittest.TestCase):
    def libro(self, scarto=0, senza=(), da=1, n=12):
        """Pagine con il numero stampato in prima riga (come la History of the PLA) dalla pagina `da`."""
        testi = []
        for k in range(1, n + 1):
            testa = "" if k < da or k in senza else f"{k + scarto}\n"
            testi.append(testa + "Chapter One\n" + PAROLE)
        return testi

    def test_scarto_zero(self):
        pagine, scarto = N.da_testo(self.libro(da=3))
        self.assertEqual(scarto, 0)
        self.assertEqual(min(pagine), 3)                                  # niente prima del primo numero letto
        self.assertEqual(pagine[3], ("3", True))

    def test_scarto_e_pagine_senza_numero(self):
        pagine, info = N.numera(self.libro(scarto=40, senza=(6,)))
        self.assertEqual(pagine[1], ("41", ""))
        self.assertEqual(pagine[6], ("46", "dedotta"))                   # per continuità
        self.assertEqual(info["stato"], "dedotto")
        self.assertIn("scarto costante +40", info["nota"])

    def test_numero_in_piede_e_testatina(self):
        testi = [f"THE WORLD TODAY February 1978\n{PAROLE}\n{60 + k}" for k in range(1, 6)]
        self.assertEqual(N.da_testo(testi)[1], 60)
        testi = [f"{100 + k} HISTORY OF THE PLA\n{PAROLE}" for k in range(1, 6)]
        self.assertEqual(N.da_testo(testi)[1], 100)

    def test_scarto_non_costante(self):
        testi = [f"{n}\n{PAROLE}" for n in (5, 9, 2, 40, 13, 7)]
        self.assertEqual(N.da_testo(testi), ({}, None))
        self.assertEqual(N.numera([PAROLE] * 5), ({}, {"metodo": "", "stato": "", "nota": ""}))

    def test_indice_iniziale_non_confonde(self):
        indice = "Contents\nIntroduction ........ 13\nChapter I ........ 18\nThe Founding ........ 69"
        pagine, scarto = N.da_testo([indice, indice] + self.libro(scarto=0, n=12)[2:])
        self.assertEqual(scarto, 0)
        self.assertEqual(min(pagine), 3)


class Indicazione(unittest.TestCase):
    def test_prima_pagina(self):
        pagine, info = N.numera([PAROLE] * 4, ["p. 1", "p. 2", "p. 3", "p. 4"], prima_pagina=61, da_pagina=2)
        self.assertEqual(pagine, {2: ("61", ""), 3: ("62", ""), 4: ("63", "")})   # prevale sulle etichette
        self.assertEqual(info["stato"], "")

    def test_marcatore_riconosciuto(self):
        for m in (N.marcatore("61", 2), N.marcatore("46", 6, "dedotta")):
            self.assertTrue(C.MARCATORE_PAGINA.match(m), m)
        testo = N.marcatore("61", 2) + "\nprima pagina\n" + N.marcatore("62", 3) + "\nseconda pagina Shehu"
        self.assertEqual(C.pagina_nel_testo(testo, testo.index("Shehu")), "62")

    def test_opzioni_da_metadati(self):
        args = argparse.Namespace(prima_pagina=None, da_pagina=1, senza_pagine=False)
        self.assertEqual(I.opzioni_pagine(args, {"prima_pagina": "61", "da_pagina": "2"}),
                         {"prima_pagina": 61, "da_pagina": 2, "pagine_pdf": True})
        args = argparse.Namespace(prima_pagina=5, da_pagina=1, senza_pagine=True)
        self.assertEqual(I.opzioni_pagine(args, {}), {"prima_pagina": 5, "da_pagina": 1, "pagine_pdf": False})


SERIE = """[Studi]
tipo = volume
lingua = en
cartella = opere/studi
citazione = {titolo}
titolo = Prova
chicago = *{titolo}*[, {pagina}]
"""


@unittest.skipIf(FITZ is None, "PyMuPDF non installato")
class ImportazionePdf(unittest.TestCase):
    def pdf(self, cartella, testi, etichette=None):
        f = cartella / "prova.pdf"
        doc = FITZ.open()
        for t in testi:
            doc.new_page(width=420, height=595).insert_textbox(FITZ.Rect(30, 30, 390, 565), t, fontsize=8)
        if etichette:
            doc.set_page_labels(etichette)
        doc.save(f)
        return f

    def importa(self, crea, *opzioni):
        with tempfile.TemporaryDirectory() as tmp:
            radice = Path(tmp)
            (radice / "serie.ini").write_text(SERIE, encoding="utf-8")
            cfg = configparser.ConfigParser(interpolation=None)
            cfg["percorsi"] = {"dati": str(radice / "data"), "risultati": str(radice / "risultati"),
                               "entita": str(radice / "entita.ini"), "serie": str(radice / "serie.ini"),
                               "problemi": str(radice / "p.csv")}
            originale, I.leggi_config = I.leggi_config, lambda: cfg
            try:
                with redirect_stdout(io.StringIO()):
                    codice = I.main(["importa", str(crea(radice)), "--serie", "Studi", "--senza-indice", *opzioni])
            finally:
                I.leggi_config = originale
            testo = next((radice / "data").rglob("*.txt")).read_text(encoding="utf-8")
        self.assertEqual(codice, 0)
        return testo

    def test_etichette_jstor(self):
        # come Larrabee su JSTOR: copertina senza etichetta, poi «p. 61», «p. 62»... (startpage parte da 0)
        testi = ["Cover page of the download service " + PAROLE] + [PAROLE] * 3
        etichette = [{"startpage": 1, "prefix": "p. ", "style": "D", "firstpagenum": 61}]
        testo = self.importa(lambda r: self.pdf(r, testi, etichette))
        self.assertIn("[PAGES: 61-63]", testo)
        self.assertIn("[[p. 61 | pdf 2]]", testo)
        self.assertNotIn("PAGES_STATUS", testo)                  # dichiarate dal PDF: non dedotte

    def test_caratteri_di_controllo(self):
        def testo_con_nulli(radice):
            f = radice / "nulli.txt"
            f.write_text("This content downloaded from\x00\x00\x00 5.91.58.224\n" + PAROLE, encoding="utf-8")
            return f
        testo = self.importa(testo_con_nulli)
        self.assertNotIn("\x00", testo)
        self.assertIn("downloaded from 5.91.58.224", testo)

    def test_numeri_stampati(self):
        testi = [f"{20 + k}\nChapter\n{PAROLE}" for k in range(1, 6)]
        testo = self.importa(lambda r: self.pdf(r, testi))
        self.assertIn("[PAGES: 21-25]", testo)
        self.assertIn("[PAGES_STATUS: dedotto]", testo)
        self.assertIn("[[p. 21 | pdf 1]]", testo)
        self.assertIn("[[p. 25 | pdf 5]]", testo)

    def test_indicazione_e_senza_pagine(self):
        testi = [PAROLE] * 3
        testo = self.importa(lambda r: self.pdf(r, testi), "--prima-pagina", "101", "--da-pagina", "2")
        self.assertIn("[[p. 101 | pdf 2]]", testo)
        self.assertNotIn("PAGES_STATUS", testo)
        testo = self.importa(lambda r: self.pdf(r, [f"{k}\n{PAROLE}" for k in range(1, 5)]), "--senza-pagine")
        self.assertNotIn("[[p.", testo)


if __name__ == "__main__":
    unittest.main()

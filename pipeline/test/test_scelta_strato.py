"""
Test della scelta tra lo strato di testo di un PDF scansionato e un OCR rifatto (importa.py): regola, pagine
del campione, riconoscimento delle scansioni, documento completo. PDF costruiti con PyMuPDF e un OCR finto:
non servono Tesseract né scansioni vere.
"""
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))
import importa as I  # noqa: E402

FITZ = I.carica_pymupdf()
TESTO = ("Shoku Jacques Grippa foli ne mbledhjen e Komitetit Qendror per ceshtjet e levizjes "
         "marksiste-leniniste ne Evrope dhe per lidhjet me partite motra. ") * 4


class OcrFinto:
    """Restituisce per ogni pagina il testo «vero»; conta le letture."""
    lingue, dpi = "sqi", 72

    def __init__(self, conf=95):
        self.conf, self.letture = conf, 0

    def leggi_immagine(self, img):
        self.letture += 1
        return TESTO, self.conf, len(TESTO.split())


def pdf(cartella, strato, scansione=True, pagine=4):
    """PDF di prova: ogni pagina con un'immagine che la copre (scansione) e uno strato di testo."""
    f = Path(cartella) / f"prova_{'scan' if scansione else 'nativo'}_{abs(hash(strato)) % 1000}.pdf"
    doc = FITZ.open()
    for _ in range(pagine):
        pag = doc.new_page(width=300, height=400)
        if scansione:
            pix = FITZ.Pixmap(FITZ.csGRAY, FITZ.IRect(0, 0, 30, 40), False)
            pix.clear_with(200)
            pag.insert_image(pag.rect, pixmap=pix)
        pag.insert_textbox(FITZ.Rect(10, 10, 290, 390), strato, fontsize=6)
    doc.save(f)
    return f


class Regola(unittest.TestCase):
    def test_decidi(self):
        self.assertEqual(I.decidi_strato(1.5, 95), "strato")          # concordano: lo strato costa zero
        self.assertEqual(I.decidi_strato(8.0, 92), "ocr")             # discordano, OCR sicuro
        self.assertEqual(I.decidi_strato(8.0, 70), "strato (incerto)")
        self.assertEqual(I.decidi_strato(8.0, None), "strato (incerto)")

    def test_pagine_campione(self):
        self.assertEqual(I.pagine_campione(list(range(1, 101)), 3), [26, 51, 76])
        self.assertEqual(I.pagine_campione([4, 7], 3), [4, 7])
        self.assertEqual(I.pagine_campione([1, 2, 3], 1), [2])
        self.assertEqual(I.pagine_campione([1, 2, 3], 0), [])


class Pdf(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_scansione_e_testo_nativo(self):
        with FITZ.open(pdf(self.tmp, TESTO)) as d:
            self.assertTrue(I.e_scansione(d[0]))
        with FITZ.open(pdf(self.tmp, TESTO, scansione=False)) as d:
            self.assertFalse(I.e_scansione(d[0]))

    def test_testo_nativo_senza_confronto(self):
        ocr = OcrFinto()
        with FITZ.open(pdf(self.tmp, TESTO, scansione=False)) as d:
            self.assertEqual(I.scegli_strato(d, ocr, self.tmp, 3, lambda *a: None), ("strato", {}, {}))
        self.assertEqual(ocr.letture, 0)

    def test_strato_buono_tenuto(self):
        ocr = OcrFinto()
        with FITZ.open(pdf(self.tmp, TESTO)) as d:
            scelta, dettagli, letti = I.scegli_strato(d, ocr, self.tmp, 3, lambda *a: None)
        self.assertEqual((scelta, dettagli["pagine_campione"], ocr.letture), ("strato", [2, 3, 4], 3))
        self.assertLessEqual(dettagli["discordanza"], 2.0)

    def test_strato_scadente_documento_rifatto_con_l_ocr(self):
        rovinato = TESTO.replace("e", "c").replace("i", "l")             # vecchio OCR scadente
        ocr = OcrFinto(conf=93)
        testo, rap = I.leggi_documento([pdf(self.tmp, rovinato)], ocr, "auto", 1, None, lambda *a: None)
        self.assertEqual(rap["scelte_strato"][0]["scelta"], "ocr")
        self.assertEqual(rap["metodo"], "ocr")
        self.assertEqual(ocr.letture, 4)                   # 3 nel campione (riusate) + 1 pagina rimasta
        self.assertNotIn("Komltctl", testo)
        self.assertIn("strato di testo del PDF scartato", rap["metodo_testo"])

    def test_strato_scadente_ma_ocr_poco_sicuro(self):
        rovinato = TESTO.replace("e", "c")
        testo, rap = I.leggi_documento([pdf(self.tmp, rovinato)], OcrFinto(conf=60), "auto", 1, None,
                                       lambda *a: None)
        self.assertEqual(rap["scelte_strato"][0]["scelta"], "strato (incerto)")
        self.assertEqual(rap["metodo"], "testo del PDF")
        self.assertIn("da controllare", I.nota_scelta(rap["scelte_strato"][0]))

    def test_modo_strato_come_prima(self):
        ocr = OcrFinto()
        testo, rap = I.leggi_documento([pdf(self.tmp, TESTO.replace("e", "c"))], ocr, "strato", 1, None,
                                       lambda *a: None)
        self.assertEqual((rap["metodo"], rap["scelte_strato"], ocr.letture), ("testo del PDF", [], 0))


if __name__ == "__main__":
    unittest.main()

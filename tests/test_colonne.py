"""
Test dell'ordine di lettura per colonne dei PDF di giornale (colonne.py, importa.testo_pagina). Il caso è quello
del Renmin Ribao del 1° gennaio 1961: un articolo su tre colonne e, sotto le colonne 2 e 3, un altro articolo
scritto nel file prima della colonna 3 del primo; nell'ordine del file i passaggi mescolavano i due articoli.
"""
import sys
import tempfile
import unittest
from pathlib import Path

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOTORE))
import colonne as COL  # noqa: E402
import importa as I  # noqa: E402

try:
    FITZ = I.carica_pymupdf()
    FITZ.Rect
except (ImportError, AttributeError):          # senza PyMuPDF (o solo pypdf) si saltano i test sui PDF
    FITZ = None


class Ordine(unittest.TestCase):
    def test_articolo_a_l(self):
        # 0 titolo su tre colonne; 1, 2, 4 le tre colonne del primo articolo; 3 l'articolo sotto le colonne 2-3
        # (nel file viene prima della colonna 3); 5 il piede della colonna 1, staccato di 2 punti
        riquadri = [(24, 286, 373, 328), (24, 335, 137, 520), (142, 335, 256, 446), (142, 486, 373, 577),
                    (261, 335, 373, 446), (24, 522, 137, 577)]
        self.assertEqual(COL.ordina(riquadri), [0, 1, 5, 2, 4, 3])

    def test_una_colonna_resta_come_e(self):
        riquadri = [(50, 50, 500, 100), (50, 104, 500, 300), (50, 310, 500, 700)]
        self.assertEqual(COL.ordina(riquadri), [0, 1, 2])

    def test_sovrapposti_ordine_del_file(self):
        # un titolo verticale dentro il riquadro del testo: la parte non si taglia, vale l'ordine del file
        riquadri = [(411, 288, 426, 304), (379, 280, 571, 571), (411, 305, 426, 321)]
        self.assertEqual(COL.ordina(riquadri), [0, 1, 2])

    def test_da_destra(self):
        riquadri = [(10, 10, 90, 500), (100, 10, 190, 500)]
        self.assertEqual(COL.ordina(riquadri, da_destra=True), [1, 0])


@unittest.skipUnless(FITZ, "serve PyMuPDF")
class Importazione(unittest.TestCase):
    def pdf(self, f):
        d = FITZ.open()
        p = d.new_page(width=400, height=600)
        scrivi = lambda r, t: p.insert_textbox(FITZ.Rect(*r), t, fontsize=8)     # noqa: E731
        scrivi((20, 20, 380, 40), "TITOLO DEL PRIMO ARTICOLO")
        scrivi((20, 50, 130, 400), "Primo articolo, colonna uno. " * 6)
        scrivi((140, 50, 250, 200), "Primo articolo, colonna due. " * 4)
        scrivi((140, 230, 380, 400), "Secondo articolo, sotto. " * 6)          # nel file prima della colonna tre
        scrivi((260, 50, 380, 200), "Primo articolo, colonna tre. " * 4)
        d.save(f)

    def test_testo_pagina(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "giornale.pdf"
            self.pdf(f)
            with FITZ.open(f) as doc:
                nel_file = I.testo_pagina(doc[0], colonne=False)
                in_ordine = I.testo_pagina(doc[0], colonne=True)
        self.assertLess(nel_file.index("Secondo"), nel_file.index("colonna tre"))
        posizioni = [in_ordine.index(s) for s in ("TITOLO", "colonna uno", "colonna due", "colonna tre", "Secondo")]
        self.assertEqual(posizioni, sorted(posizioni))

    def test_profilo(self):
        self.assertTrue(I.ordine_per_colonne({"tipo": "periodico"}))
        self.assertFalse(I.ordine_per_colonne({"tipo": "volume"}))
        self.assertFalse(I.ordine_per_colonne({"tipo": "periodico", "ordine_lettura": "pdf"}))
        self.assertTrue(I.ordine_per_colonne({"tipo": "volume", "ordine_lettura": "colonne"}))


if __name__ == "__main__":
    unittest.main()

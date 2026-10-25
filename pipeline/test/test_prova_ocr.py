"""
Test dello strumento di prova dei motori OCR (prova_ocr.py): misura del CER, riferimenti verificati e no,
riepilogo per motore. Senza motori OCR né scansioni.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))
import prova_ocr as P  # noqa: E402


class Cer(unittest.TestCase):
    def test_distanza(self):
        self.assertEqual(P.distanza("kitten", "sitting"), 3)
        self.assertEqual(P.distanza("", "abc"), 3)
        self.assertEqual(P.distanza("格里巴", "格里巴"), 0)

    def test_cinese_senza_spazi_e_larghezza_piena(self):
        # spazi e a capo spuri dell'OCR non contano; （ e ( sono lo stesso carattere dopo NFKC
        self.assertEqual(P.cer("格 里\n巴(同志)", "格里巴（同志）", "zh"), (0, 7))
        self.assertEqual(P.cer("格里吧同志", "格里巴同志", "zh"), (1, 5))

    def test_latino_spazi_ridotti(self):
        self.assertEqual(P.cer("Shoku  Grippa\nfoli", "Shoku Grippa foli", "sq"), (0, 17))
        self.assertEqual(P.cer("Shoku Gripa foli", "Shoku Grippa foli", "sq"), (1, 17))

    def test_senza_punteggiatura(self):
        self.assertEqual(P.cer("格里巴同志", "格里巴同志。", "zh", punteggiatura=False), (0, 5))


class Riferimento(unittest.TestCase):
    def scrivi(self, d, testo, chi=""):
        f = d / "p001.riferimento.txt"
        f.write_text(P.ISTRUZIONI_RIF.format(img="p001.png", verifica=P.VERIFICA, motore="tesseract")
                     .replace(P.VERIFICA + " ", P.VERIFICA + " " + chi) + testo, encoding="utf-8")
        return f

    def test_non_verificato_e_verificato(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            self.assertEqual(P.leggi_riferimento(self.scrivi(d, "格里巴同志\n")), ("格里巴同志", ""))
            self.assertEqual(P.leggi_riferimento(self.scrivi(d, "格里巴同志\n", "Ivan Masci")),
                             ("格里巴同志", "Ivan Masci"))

    def test_misura_solo_pagine_verificate(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "campione.json").write_text(json.dumps({
                "sorgente": "x.pdf", "lingua": "zh", "dpi": 300, "pagine": [1, 2],
                "motori": {"tesseract": {"disponibile": True, "secondi_per_pagina": 2.0},
                           "paddleocr": {"disponibile": True, "secondi_per_pagina": 5.0},
                           "kraken": {"disponibile": False, "motivo": "serve Linux"}}}), encoding="utf-8")
            self.scrivi(d, "格里巴同志访问北京", "Ivan Masci")
            (d / "p002.riferimento.txt").write_text(P.ISTRUZIONI_RIF.format(
                img="p002.png", verifica=P.VERIFICA, motore="x") + "未检查", encoding="utf-8")
            for n in (1, 2):
                (d / f"p{n:03d}.tesseract.txt").write_text("格里吧同志访问北京", encoding="utf-8")
                (d / f"p{n:03d}.paddleocr.txt").write_text("格里巴同志\n访问北京", encoding="utf-8")
            camp, out, da_verificare = P.misura_campione(d)
            self.assertEqual(da_verificare, [2])
            self.assertEqual((out["tesseract"]["errori"], out["tesseract"]["caratteri"]), (1, 9))
            self.assertEqual(out["paddleocr"]["errori"], 0)
            self.assertNotIn("kraken", out)


if __name__ == "__main__":
    unittest.main()

"""
Test della costruzione del programma per Windows (confezione/costruisci.py, lavoro 39, fase 3) e di ciò che il
motore fa diversamente quando è confezionato:
- config.ini distribuito senza le scelte di chi costruisce (progetto, profili, percorsi di Tesseract), con il resto
  identico;
- solo i file del motore sotto git (niente models.ini, copie .bak, cache);
- il motore preferisce il Tesseract incluso accanto a scripts, ma una scelta in config.ini prevale.
La costruzione vera (download, Inno Setup) si prova a mano: stato_del_sistema.md.
"""
import configparser
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "scripts"))
sys.path.insert(0, str(RADICE / "confezione"))
import costruisci as C  # noqa: E402
import importa  # noqa: E402

CONFIG = """# Configurazione
[progetto]
# commento
cartella = C:\\Users\\qualcuno\\projects\\ricerca

[modello]
backend = router
timeout = 300
profilo = groq-personale
analisi = altro
file_profili = D:\\miei\\models.ini

[ocr]
tesseract = C:\\Tesseract\\tesseract.exe
modelli = D:\\tessdata

[estrazione]
finestra = 400
"""


class Confezione(unittest.TestCase):
    def test_config_pulito(self):
        testo = C.config_pulito(CONFIG)
        cp = configparser.ConfigParser(interpolation=None)
        cp.read_string(testo)
        self.assertEqual(cp.get("progetto", "cartella"), "")
        for voce in ("profilo", "analisi", "file_profili"):
            self.assertFalse(cp.has_option("modello", voce), voce)
        self.assertEqual(cp.get("modello", "timeout"), "300")
        self.assertEqual(cp.get("ocr", "tesseract"), "")
        self.assertEqual(cp.get("ocr", "modelli"), "")
        self.assertEqual(cp.get("estrazione", "finestra"), "400")
        self.assertIn("# commento", testo)
        self.assertNotIn("qualcuno", testo)

    def test_config_del_repository(self):
        """Il config.ini vero, ripulito, non sceglie né progetto né profilo."""
        cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#",))
        cp.read_string(C.config_pulito((RADICE / "scripts" / "config.ini").read_text(encoding="utf-8")))
        self.assertEqual(cp.get("progetto", "cartella", fallback=""), "")
        self.assertFalse(cp.has_option("modello", "profilo"))

    def test_file_del_motore(self):
        nomi = {f.relative_to(RADICE / "scripts").as_posix() for f in C.file_del_motore()}
        self.assertIn("app.py", nomi)
        self.assertIn("posizioni.py", nomi)
        self.assertIn("interfaccia/index.html", nomi)
        self.assertFalse({"models.ini", "installazione.ini"} & nomi)
        self.assertFalse(any(n.endswith((".bak", ".pyc")) or "__pycache__" in n for n in nomi))

    def test_tesseract_incluso(self):
        with tempfile.TemporaryDirectory() as d:
            prog = Path(d)
            (prog / "scripts").mkdir()
            vuota = configparser.ConfigParser()
            with mock.patch.object(importa, "CARTELLA", prog / "scripts"):
                self.assertIsNone(importa.tesseract_incluso())
                (prog / "tesseract").mkdir()
                (prog / "tesseract" / "tesseract.exe").write_bytes(b"")
                self.assertEqual(importa.cerca_tesseract(vuota), str(prog / "tesseract" / "tesseract.exe"))
                altro = prog / "altro.exe"
                altro.write_bytes(b"")
                scelto = configparser.ConfigParser()
                scelto.read_dict({"ocr": {"tesseract": str(altro)}})
                self.assertEqual(importa.cerca_tesseract(scelto), str(altro))      # la configurazione prevale


if __name__ == "__main__":
    unittest.main()

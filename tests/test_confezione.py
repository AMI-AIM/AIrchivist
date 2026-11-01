"""
Test della costruzione del programma per Windows (confezione/costruisci.py, lavoro 39, fase 3) e di ciò che il
motore fa diversamente quando è confezionato:
- config.ini distribuito senza le scelte di chi costruisce (progetto, profili, percorsi di Tesseract), con il resto
  identico;
- solo i file del motore sotto git (niente models.ini, copie .bak, cache);
- il motore preferisce il Tesseract incluso accanto a scripts, ma una scelta in config.ini prevale;
- le lingue OCR si scaricano da tessdata_best solo con un codice valido, senza lasciare file rotti, e il messaggio
  delle lingue mancanti rimanda all'interfaccia solo se la cartella dei modelli è scrivibile.
La costruzione vera (download, Inno Setup) si prova a mano: stato_del_sistema.md.
"""
import configparser
import io
import os
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


class Risposta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class LingueOcr(unittest.TestCase):
    """Scaricamento dei modelli delle lingue di Tesseract (importa.scarica_lingua), senza rete."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cartella = Path(self._tmp.name)
        self.chiesti = []

    def tearDown(self):
        self._tmp.cleanup()

    def apri(self, contenuto=b"x" * 50000, errore=None):
        def apri(url, timeout=None):
            self.chiesti.append(url)
            if errore:
                raise errore
            return Risposta(contenuto)
        return apri

    def test_scarica(self):
        f = importa.scarica_lingua("sqi", self.cartella, apri=self.apri(), stampa=lambda t: None)
        self.assertEqual(f, self.cartella / "sqi.traineddata")
        self.assertEqual(f.stat().st_size, 50000)
        self.assertEqual(self.chiesti, ["https://github.com/tesseract-ocr/tessdata_best/raw/main/sqi.traineddata"])
        self.assertEqual(list(self.cartella.glob("*.parziale")), [])
        importa.scarica_lingua("chi_sim_vert", self.cartella, apri=self.apri(), stampa=lambda t: None)
        importa.scarica_lingua("srp_latn", self.cartella, apri=self.apri(), stampa=lambda t: None)

    def test_codici_rifiutati_senza_rete(self):
        for codice in ("", "../eng", "eng.traineddata", "ENG", "e", "eng/../x", "https://x"):
            with self.assertRaises(ValueError, msg=codice):
                importa.scarica_lingua(codice, self.cartella, apri=self.apri(), stampa=lambda t: None)
        self.assertEqual(self.chiesti, [])

    def test_errori_non_lasciano_file(self):
        import urllib.error
        assente = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        with self.assertRaisesRegex(ValueError, "non ha un modello"):
            importa.scarica_lingua("xyz", self.cartella, apri=self.apri(errore=assente), stampa=lambda t: None)
        with self.assertRaisesRegex(ValueError, "troppo piccolo"):
            importa.scarica_lingua("abc", self.cartella, apri=self.apri(b"<html>"), stampa=lambda t: None)
        with self.assertRaises(OSError):
            importa.scarica_lingua("ita", self.cartella, apri=self.apri(errore=OSError("rete assente")),
                                   stampa=lambda t: None)
        self.assertEqual(list(self.cartella.iterdir()), [])

    def test_cartella_e_messaggio(self):
        vuota = configparser.ConfigParser()
        exe = self.cartella / "tesseract.exe"
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("TESSDATA_PREFIX", None)
            self.assertEqual(importa.cartella_lingue(vuota, str(exe)), self.cartella / "tessdata")
            os.environ["TESSDATA_PREFIX"] = str(self.cartella)
            self.assertEqual(importa.cartella_lingue(vuota, str(exe)), self.cartella)
        scelta = configparser.ConfigParser()
        scelta.read_dict({"ocr": {"modelli": str(self.cartella / "modelli")}})
        self.assertEqual(importa.cartella_lingue(scelta, str(exe)), self.cartella / "modelli")
        self.assertTrue(importa.scrivibile(self.cartella))
        self.assertFalse(importa.scrivibile(self.cartella / "assente"))
        self.assertFalse(importa.scrivibile(None))
        with mock.patch.object(importa, "cartella_lingue", return_value=self.cartella):
            self.assertIn("interfaccia", importa.aiuto_lingue(["sqi"], vuota))
        with mock.patch.object(importa, "cartella_lingue", return_value=self.cartella / "assente"):
            self.assertIn("Tesseract", importa.aiuto_lingue(["sqi"], vuota))
            self.assertNotIn("interfaccia", importa.aiuto_lingue(["sqi"], vuota))

    def test_tabella_avvisa_delle_lingue_mancanti(self):
        """La prova della tabella di revisione dice quali scansioni non si potranno leggere, prima di importare.
        Le serie esistenti valgono con la loro lingua; quelle da creare con la lingua della tabella; i PDF con testo
        e quelli con lingua installata non contano."""
        import revisione
        righe = [(2, {"serie": "Zëri i Popullit", "testo": "scansione senza testo"}),
                 (3, {"serie": "Zëri i Popullit", "testo": "scansione senza testo"}),
                 (4, {"serie": "Nuova", "testo": "scansione senza testo"}),
                 (5, {"serie": "Zëri i Popullit", "testo": "testo nativo"}),
                 (6, {"serie": "Italiana", "testo": "scansione senza testo"}),
                 (7, {"serie": "Zëri i Popullit", "testo": "scansione con strato di testo"})]
        esistenti = {"Zëri i Popullit": {"lingua": "sq"}, "Italiana": {"lingua": "it"}}
        da_creare = {"Nuova": {"lingua": "ru"}}
        cfg = configparser.ConfigParser()
        with mock.patch.object(importa, "cerca_tesseract", return_value="tesseract.exe"), \
                mock.patch.object(importa, "lingue_installate", return_value={"eng", "ita", "osd"}), \
                mock.patch.object(importa, "cartella_lingue", return_value=self.cartella):
            avvisi = revisione.lingue_mancanti(righe, esistenti, da_creare, cfg)
        self.assertEqual(len(avvisi), 2, avvisi)
        self.assertTrue(avvisi[0].startswith("righe 2, 3 (serie «Zëri i Popullit»)"), avvisi[0])
        self.assertIn("sqi", avvisi[0])
        self.assertIn("interfaccia", avvisi[0])
        self.assertTrue(avvisi[1].startswith("riga 4 (serie «Nuova»)"), avvisi[1])
        self.assertIn("rus", avvisi[1])
        with mock.patch.object(importa, "cerca_tesseract", return_value=None):
            self.assertEqual(revisione.lingue_mancanti(righe, esistenti, da_creare, cfg), [])


if __name__ == "__main__":
    unittest.main()

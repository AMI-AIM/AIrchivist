"""
Test della skill ricerca-fonti per la chat di Claude: chat.py su un corpus caricato in .zip (progetto
temporaneo, serie e scheda create dalla chat, nessun archivio delle letture), importazione di un PDF con testo
senza Tesseract, lettura dei PDF con pypdf quando manca PyMuPDF, costruzione dello zip della skill.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))
import crea_skill_chat  # noqa: E402

INTESTAZIONE = """[DOC_ID: RMB-{data}]
[SERIES: Renmin Ribao]
[LANG: zh]
[YEAR: {anno}]
[DATE: {data}]
[FULL_CITATION: Renmin Ribao, {data}]

"""
TESTO = ("第1版() 专栏： 贝林格同志率意共中央代表团抵京 新华社北京四月十四日电 应中国共产党中央委员会邀请，"
         "由总书记贝林格率领的意大利共产党中央代表团今天晚间乘飞机到达北京。")
RIEMPITIVO = (" La discussione nel movimento comunista internazionale prosegue nelle sezioni e nelle federazioni,"
              " dove i compagni esaminano i documenti approvati.") * 3
PAGINE = ["Rinascita. Settimanale del Partito comunista italiano." + RIEMPITIVO,
          "Il compagno Enrico Berlinguer, capo della delegazione del PCI alla riunione di Mosca, ha dichiarato "
          "che le condizioni per una nuova conferenza non sono mature." + RIEMPITIVO,
          "Cronache delle federazioni." + RIEMPITIVO]


def pdf_di_prova(f):
    """PDF di tre pagine con testo e numero stampato in piede (41-43); None senza PyMuPDF."""
    try:
        import fitz
    except ImportError:
        return None
    d = fitz.open()
    for i, t in enumerate(PAGINE, 1):
        p = d.new_page()
        p.insert_textbox(fitz.Rect(60, 60, 540, 760), t, fontsize=11)
        p.insert_text((300, 800), str(40 + i))
    d.save(f)
    return f


class CorpusCaricato(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        t = Path(cls.tmp.name)
        cls.caricati = t / "caricati"
        cls.caricati.mkdir()
        with zipfile.ZipFile(cls.caricati / "corpus.zip", "w") as z:
            z.writestr("data/riviste/renmin_ribao/1980-04-15.txt",
                       INTESTAZIONE.format(data="1980-04-15", anno="1980") + TESTO + "\n")
            z.writestr("data/riviste/renmin_ribao/../../fuori.txt", "[SERIES: X]\n")   # percorso rifiutato
        cls.pdf = pdf_di_prova(cls.caricati / "rinascita_1965_11.pdf")

    def setUp(self):
        # un progetto per test, come una chat nuova
        self.radice = Path(self.tmp.name) / self._testMethodName
        self.env = dict(os.environ, AIRCHIVIST_PROGETTO=str(self.radice), PYTHONIOENCODING="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def chat(self, *argomenti, codice=0):
        r = subprocess.run([sys.executable, str(PIPELINE / "chat.py"), *map(str, argomenti)], cwd=PIPELINE,
                           env=self.env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, codice, r.stdout + r.stderr)
        return r.stdout

    def test_percorso_completo(self):
        esito = json.loads(self.chat("apri", self.caricati))
        self.assertEqual(esito["fonti"], 1)
        self.assertEqual(esito["serie"], {"Renmin Ribao": 1})
        self.assertEqual(esito["serie_senza_profilo"], {"Renmin Ribao": "riviste/renmin_ribao"})
        self.assertEqual(esito["indice"], "pronto")
        self.assertFalse((self.radice / "fuori.txt").exists())
        self.assertFalse((self.radice / "data" / "fuori.txt").exists())
        if self.pdf:
            self.assertIn(str(self.pdf), esito["da_importare"])

        self.assertIn("aggiunta", self.chat("serie-crea", "Renmin Ribao", "--tipo", "periodico", "--lingua", "zh",
                                            "--cartella", "riviste/renmin_ribao", "--citazione", "Renmin Ribao, {data}",
                                            "--campo", "chicago=*Renmin ribao* 人民日报, {data_o_anno}[, {pagina}]",
                                            "--campo", r"pagina_regex=第\s*(\d+)\s*版"))
        self.chat("serie-crea", "Errata", "--tipo", "rivista", "--lingua", "it", "--cartella", "riviste/x",
                  "--citazione", "x", codice=1)
        self.assertEqual(json.loads(self.chat("stato"))["serie_senza_profilo"], {})

        esplorato = json.loads(self.chat("esplora", "Enrico Berlinguer", "--candidate", "贝林格"))
        self.assertIn("贝林格", json.dumps(esplorato, ensure_ascii=False))
        self.assertEqual(json.loads(self.chat("scheda-crea", "Enrico Berlinguer", "--varianti",
                                              "贝林格; Enrico Berlinguer", "--tipo", "persona"))["scheda"],
                         "Enrico Berlinguer")
        self.chat("scheda-crea", "Enrico Berlinguer", "--varianti", "x", codice=1)

        uscita = self.chat("prepara", "Enrico Berlinguer")
        self.assertIn("da leggere: 1 in 1 lotti", uscita)
        cart = self.radice / "risultati" / "enrico_berlinguer"
        self.assertTrue((cart / ".senza_archivio").exists())
        pid = json.loads((cart / "passaggi.jsonl").read_text(encoding="utf-8").splitlines()[0])["id"]
        (cart / "l.json").write_text(json.dumps([{"id": pid, "pertinente": "sì", "motivazione": "arrivo",
                                                  "traduzione_it": "Berlinguer arriva a Pechino.",
                                                  "sintesi_it": "Il 14 aprile 1980 Berlinguer arriva a Pechino."}],
                                                ensure_ascii=False), encoding="utf-8")
        self.assertIn("ancora da leggere: 0", self.chat("registra", "enrico_berlinguer", cart / "l.json"))
        self.assertFalse((self.radice / "risultati" / "_archivio" / "letture.jsonl").exists())
        self.assertIn("[1] *Renmin ribao*", self.chat("documenti", "enrico_berlinguer"))
        (cart / "s.json").write_text(json.dumps({"dati_espliciti": [{"testo": "Arriva a Pechino.", "rif": [1]}],
                                                 "inferenze": [], "problemi_interpretativi": [],
                                                 "risposta_finale": "Arriva a Pechino [1]."}), encoding="utf-8")
        self.chat("sintesi", "enrico_berlinguer", "--domanda", "Chi era?", "--sintesi-da", cart / "s.json")
        risposta = (cart / "risposta.md").read_text(encoding="utf-8")
        self.assertIn("— *Renmin ribao* 人民日报, 15 aprile 1980, 1", risposta)
        self.assertIn("- Arriva a Pechino. [1]", risposta)

        uscite = Path(self.tmp.name) / "uscite"
        consegnati = json.loads(self.chat("consegna", "enrico_berlinguer", "--dest", uscite))["consegnati"]
        self.assertEqual(sorted(Path(f).name for f in consegnati),
                         ["entita.ini", "risposta_enrico_berlinguer.md", "serie.ini"])

    @unittest.skipUnless(pdf_di_prova(Path(tempfile.gettempdir()) / "_prova_chat.pdf"), "serve PyMuPDF")
    def test_pdf_senza_tesseract_e_in_italiano(self):
        self.chat("apri", self.caricati)
        (self.radice / "progetto.ini").write_text(
            "[progetto]\nnome = prova\n[ocr]\ntesseract = " + str(Path(self.tmp.name) / "nessuno.exe") + "\n",
            encoding="utf-8")
        self.chat("serie-crea", "Rinascita", "--tipo", "periodico", "--lingua", "it", "--cartella",
                  "riviste/rinascita", "--sigla", "RIN", "--citazione", "Rinascita, {data}",
                  "--campo", "chicago=*Rinascita*[, {numero_lbl}] ({data_o_anno})[: {pagina}]")
        uscita = self.chat("importa", self.pdf, "--serie", "Rinascita", "--data", "1965-03-13", "--numero", "11")
        self.assertIn("OCR non disponibile", uscita)
        testo = next((self.radice / "data" / "riviste" / "rinascita").glob("*.txt")).read_text(encoding="utf-8")
        self.assertIn("[[p. 42 | pdf 2]]", testo)
        self.chat("scheda-crea", "Berlinguer (Rinascita)", "--varianti", "Enrico Berlinguer")
        self.chat("prepara", "Berlinguer (Rinascita)", "--fonti", "Rinascita")
        cart = self.radice / "risultati" / "berlinguer_rinascita"
        lotto = (cart / "lotti" / "lotto_01.md").read_text(encoding="utf-8")
        self.assertIn("testo in italiano: non serve tradurre", lotto)
        pid = json.loads((cart / "passaggi.jsonl").read_text(encoding="utf-8").splitlines()[0])["id"]
        (cart / "l.json").write_text(json.dumps([{"id": pid, "pertinente": "sì", "motivazione": "Mosca",
                                                  "sintesi_it": "Condizioni non mature."}]), encoding="utf-8")
        self.assertIn("ancora da leggere: 0", self.chat("registra", cart, cart / "l.json"))


class PdfConPypdf(unittest.TestCase):
    def test_testo_ed_etichette(self):
        try:
            import pypdf  # noqa: F401
        except ImportError:
            self.skipTest("serve pypdf")
        import importa
        with tempfile.TemporaryDirectory() as tmp:
            f = pdf_di_prova(Path(tmp) / "p.pdf")
            if not f:
                self.skipTest("serve PyMuPDF per creare il PDF")
            with importa.PdfSemplice(f) as doc:
                self.assertEqual(len(doc), 3)
                self.assertIn("Enrico Berlinguer", doc[1].get_text("text"))
                self.assertEqual(doc[0].get_label(), "")            # nessuna etichetta dichiarata
                self.assertEqual(doc[0].get_image_info(), [])
                with self.assertRaises(RuntimeError):
                    doc[0].get_pixmap(dpi=300)


class ZipDellaSkill(unittest.TestCase):
    def test_contenuto(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "skill.zip"
            from contextlib import redirect_stdout
            import io
            with redirect_stdout(io.StringIO()):
                crea_skill_chat.main(["--out", str(out)])
            nomi = set(zipfile.ZipFile(out).namelist())
        self.assertIn("ricerca-fonti/SKILL.md", nomi)
        self.assertIn("ricerca-fonti/motore/config.ini", nomi)
        self.assertIn("ricerca-fonti/motore/serie_modello.ini", nomi)
        for m in ("chat", "sessione", "sintesi", "importa", "estrai_occorrenze", "indice", "citazioni"):
            self.assertIn(f"ricerca-fonti/motore/{m}.py", nomi)
        for m in ("mcp_server", "lavori", "valutazione", "installa"):          # non servono nella chat
            self.assertNotIn(f"ricerca-fonti/motore/{m}.py", nomi)


if __name__ == "__main__":
    unittest.main()

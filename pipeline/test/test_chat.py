"""
Test della skill ricerca-fonti per la chat di Claude: chat.py su un corpus caricato in .zip (progetto
temporaneo, serie e scheda create dalla chat, nessun archivio delle letture), importazione di un PDF con testo
senza Tesseract, lettura dei PDF con pypdf quando manca PyMuPDF, confezioni della skill.
"""
import json
import re
import os
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))
import confeziona  # noqa: E402

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


def pdf_a_mano(f, pagine):
    """PDF minimo scritto senza librerie: una pagina per elemento di `pagine` (righe di testo, dall'alto),
    font Helvetica. Serve a provare la lettura con pypdf dove PyMuPDF non c'è."""
    oggetti = ["<< /Type /Catalog /Pages 2 0 R >>", None,
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    figli = []
    for righe in pagine:
        flusso = "BT /F1 11 Tf 60 780 Td 14 TL " + " ".join(
            "(" + r.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") + ") Tj T*" for r in righe) + " ET"
        oggetti.append(f"<< /Length {len(flusso.encode('latin-1'))} >>\nstream\n{flusso}\nendstream")
        oggetti.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                       f"/Resources << /Font << /F1 3 0 R >> >> /Contents {len(oggetti)} 0 R >>")
        figli.append(f"{len(oggetti)} 0 R")
    oggetti[1] = f"<< /Type /Pages /Kids [{' '.join(figli)}] /Count {len(figli)} >>"
    corpo, posizioni = b"%PDF-1.4\n", []
    for i, o in enumerate(oggetti, 1):
        posizioni.append(len(corpo))
        corpo += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(corpo)
    corpo += f"xref\n0 {len(oggetti) + 1}\n0000000000 65535 f \n".encode("latin-1")
    corpo += "".join(f"{p:010d} 00000 n \n" for p in posizioni).encode("latin-1")
    corpo += f"trailer\n<< /Size {len(oggetti) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("latin-1")
    Path(f).write_bytes(corpo)
    return Path(f)


class PdfSenzaPyMuPDF(unittest.TestCase):
    """Ambiente senza PyMuPDF (come la chat): chat.py ambiente lo dice e i PDF con testo si importano con
    pypdf, con i numeri di pagina stampati. PyMuPDF è nascosto con moduli finti che non si importano."""
    def test_ripiego_su_pypdf(self):
        try:
            import pypdf  # noqa: F401
        except ImportError:
            self.skipTest("serve pypdf")
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            finti = t / "senza_pymupdf"
            finti.mkdir()
            for m in ("fitz", "pymupdf"):
                (finti / f"{m}.py").write_text("raise ImportError('PyMuPDF assente (prova)')\n", encoding="utf-8")
            (t / "fonti").mkdir()
            corpo = [r for r in RIEMPITIVO.split(". ") if r.strip()]
            pdf_a_mano(t / "fonti" / "rinascita.pdf",
                       [["Rinascita. Settimanale del Partito comunista italiano.", *corpo, "", "41"],
                        ["Il compagno Enrico Berlinguer, capo della delegazione del PCI,",
                         "ha dichiarato che le condizioni non sono mature.", *corpo, "", "42"],
                        ["Cronache delle federazioni.", *corpo, "", "43"]])
            env = dict(os.environ, AIRCHIVIST_PROGETTO=str(t / "progetto"), PYTHONIOENCODING="utf-8",
                       PYTHONPATH=str(finti))

            def chat(*argomenti):
                r = subprocess.run([sys.executable, str(PIPELINE / "chat.py"), *map(str, argomenti)], cwd=PIPELINE,
                                   env=env, capture_output=True, text=True, encoding="utf-8")
                self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                return r.stdout

            self.assertEqual(json.loads(chat("ambiente"))["pdf"], "pypdf")
            chat("apri", t / "fonti")
            chat("serie-crea", "Rinascita", "--tipo", "periodico", "--lingua", "it", "--cartella",
                 "riviste/rinascita", "--citazione", "Rinascita, {data}")
            chat("importa", t / "fonti" / "rinascita.pdf", "--serie", "Rinascita", "--data", "1965-03-13")
            testo = next((t / "progetto" / "data" / "riviste" / "rinascita").glob("*.txt")).read_text(
                encoding="utf-8")
            self.assertIn("Enrico Berlinguer", testo)
            self.assertIn("[[p. 42 | pdf 2]]", testo)


def confeziona_in(dist):
    from contextlib import redirect_stdout
    import io
    with redirect_stdout(io.StringIO()):
        confeziona.main(["--dist", str(dist)])
    return Path(dist)


class Confezioni(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dist = confeziona_in(Path(cls.tmp.name) / "dist")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_zip_claude(self):
        nomi = set(zipfile.ZipFile(self.dist / "ricerca-fonti-claude.zip").namelist())
        self.assertEqual({n.split("/")[0] for n in nomi}, {"ricerca-fonti"})       # la cartella alla radice
        for f in ("SKILL.md", "LEGGIMI.md", "LICENSE", "motore/config.ini", "motore/serie_modello.ini"):
            self.assertIn(f"ricerca-fonti/{f}", nomi)
        for m in ("chat", "sessione", "sintesi", "importa", "estrai_occorrenze", "indice", "citazioni"):
            self.assertIn(f"ricerca-fonti/motore/{m}.py", nomi)
        for m in ("mcp_server", "lavori", "valutazione", "installa", "confeziona"):  # non servono nella chat
            self.assertNotIn(f"ricerca-fonti/motore/{m}.py", nomi)

    def test_plugin_claude_code_e_chatgpt(self):
        mercato = json.loads((self.dist / "claude-code" / ".claude-plugin" / "marketplace.json")
                             .read_text(encoding="utf-8"))
        voce = mercato["plugins"][0]
        self.assertTrue(mercato["name"] and mercato["owner"]["name"])
        cart = self.dist / "claude-code" / voce["source"]
        self.assertTrue((cart / "skills" / "ricerca-fonti" / "motore" / "chat.py").is_file())
        claude = json.loads((cart / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        portabile = json.loads((cart / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(claude["name"], voce["name"])
        self.assertEqual(portabile["name"], claude["name"])
        self.assertIn("agent-plugins.org", portabile["$schema"])
        self.assertTrue(claude["description"])                # OpenAI la vuole non vuota
        # ChatGPT: alla radice dello zip il manifesto e almeno skills/<nome>/SKILL.md
        z = zipfile.ZipFile(self.dist / "ricerca-fonti-chatgpt.zip")
        nomi = set(z.namelist())
        for f in (".claude-plugin/plugin.json", "plugin.json", "LEGGIMI.md", "LICENSE",
                  "skills/ricerca-fonti/SKILL.md", "skills/ricerca-fonti/motore/chat.py"):
            self.assertIn(f, nomi)
        self.assertEqual(nomi, {f.relative_to(cart).as_posix() for f in cart.rglob("*") if f.is_file()})

    def test_fonte_unica(self):
        """Le confezioni prendono SKILL.md dalla fonte unica; ogni comando di chat.py che SKILL.md richiama
        esiste e la skill non nomina un provider."""
        fonte = PIPELINE.parent / "skills" / "ricerca-fonti" / "SKILL.md"
        self.assertEqual(zipfile.ZipFile(self.dist / "ricerca-fonti-claude.zip").read("ricerca-fonti/SKILL.md"),
                         fonte.read_bytes())
        self.assertEqual(zipfile.ZipFile(self.dist / "ricerca-fonti-chatgpt.zip")
                         .read("skills/ricerca-fonti/SKILL.md"), fonte.read_bytes())
        testo = fonte.read_text(encoding="utf-8")
        richiamati = set(re.findall(r"chat\.py ([a-z-]+)", testo))
        aiuto = subprocess.run([sys.executable, str(PIPELINE / "chat.py"), "--help"], capture_output=True,
                               text=True, encoding="utf-8").stdout
        comandi = set(re.search(r"\{([a-z,-]+)\}", aiuto).group(1).split(","))
        self.assertTrue(richiamati, "SKILL.md non richiama chat.py")
        self.assertEqual(richiamati - comandi, set())
        for nome in ("Claude", "ChatGPT", "OpenAI", "Anthropic"):
            self.assertNotIn(nome, testo)
        descrizione = re.search(r"^description: (.*)$", testo, re.M).group(1)
        self.assertLessEqual(len(descrizione), 1024)


class Ambiente(unittest.TestCase):
    def esegui(self, chat_py, *argomenti, env=None, cwd=None, codice=0):
        r = subprocess.run([sys.executable, str(chat_py), *map(str, argomenti)], cwd=cwd, env=env,
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, codice, r.stdout + r.stderr)
        return r.stdout + r.stderr

    def test_sistema_completo(self):
        import chat
        with tempfile.TemporaryDirectory() as tmp:
            motore = Path(tmp) / "AIrchivist" / "pipeline"
            (motore.parent / "docs").mkdir(parents=True)
            motore.mkdir()
            vecchio = os.environ.pop("AIRCHIVIST_MOTORE", None)
            try:
                self.assertIsNone(chat.sistema_completo(motore.parent / "docs"))
                for f in ("mcp_server.py", "sessione.py", "config.ini"):
                    (motore / f).write_text("", encoding="utf-8")
                self.assertEqual(chat.sistema_completo(motore.parent / "docs"), motore.resolve())
                self.assertEqual(chat.sistema_completo(motore), motore.resolve())
            finally:
                if vecchio is not None:
                    os.environ["AIRCHIVIST_MOTORE"] = vecchio

    def test_skill_fuori_dal_sistema(self):
        """Il motore copiato nella skill, lanciato fuori da un'installazione completa: nessuna fonte, progetto
        temporaneo."""
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            zipfile.ZipFile(confeziona_in(t / "dist") / "ricerca-fonti-claude.zip").extractall(t / "skill")
            env = {k: v for k, v in os.environ.items() if k != "AIRCHIVIST_MOTORE"}
            env.update(AIRCHIVIST_PROGETTO=str(t / "progetto"), PYTHONIOENCODING="utf-8")
            esito = json.loads(self.esegui(t / "skill" / "ricerca-fonti" / "motore" / "chat.py", "ambiente",
                                           env=env, cwd=t))
            self.assertEqual(esito["modo"], "nessuna_fonte")
            self.assertTrue(esito["temporaneo"])
            self.assertIn(esito["pdf"], ("PyMuPDF", "pypdf", "nessuno"))
            self.assertEqual(Path(esito["consegna"]), t / "progetto" / "consegna")

    def test_progetto_del_sistema_protetto(self):
        """Nel motore completo, su un progetto vero (progetto.ini senza il segno dei progetti della chat), apri,
        importa, serie-crea e consegna si rifiutano."""
        with tempfile.TemporaryDirectory() as tmp:
            radice = Path(tmp) / "vero"
            radice.mkdir()
            (radice / "progetto.ini").write_text("[progetto]\nnome = vero\n", encoding="utf-8")
            env = dict(os.environ, AIRCHIVIST_PROGETTO=str(radice), PYTHONIOENCODING="utf-8")
            for argomenti in (["apri", tmp], ["importa", tmp, "--serie", "X"],
                              ["serie-crea", "X", "--tipo", "volume", "--lingua", "it", "--cartella", "volumi/x",
                               "--citazione", "x"], ["consegna", "x"]):
                self.assertIn("non si usa sul progetto del sistema completo",
                              self.esegui(PIPELINE / "chat.py", *argomenti, env=env, codice=1))
            self.assertFalse((radice / "data").exists())
            self.assertFalse((radice / "serie.ini").exists())


if __name__ == "__main__":
    unittest.main()

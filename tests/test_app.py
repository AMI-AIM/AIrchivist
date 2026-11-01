"""
Test dell'interfaccia (app.py, lavoro 35), con il server HTTP vero in locale, due progetti temporanei e un servizio
dei modelli finto:
- sicurezza: senza il token di sessione ogni richiesta è rifiutata; Host estraneo e POST senza intestazione no;
- menu «Progetto»: elenco, cambio (scritto in config.ini), nuovo progetto, cambio bloccato da una ricerca in corso;
- menu «Modello»: un profilo il cui collegamento fallisce non diventa quello in uso; uno che funziona sì;
- percorso guidato: scheda trovata, ricerca avviata dall'interfaccia su un'entità già in archivio con lo stesso
  risultato della riga di comando; documento della risposta servito solo dalle cartelle del progetto;
- importazione (lavoro 37): tabella di revisione letta e corretta dalla pagina solo nelle cartelle del progetto,
  righe che non coincidono rifiutate, file Excel mai riscritto (le correzioni vanno nel CSV accanto), stato del
  lavoro con avanzamento e tabella pronta;
- conversazione (lavoro 38): disattivata, con la spiegazione, se il modello non sa usare gli strumenti.
"""
import http.client
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import quote

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
PROVA = Path(__file__).resolve().parent / "test_project"
sys.path.insert(0, str(MOTORE))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import app as A  # noqa: E402
import revisione as R  # noqa: E402
from llm import VARIABILE_FISSATI  # noqa: E402
from progetto import VARIABILE  # noqa: E402
from test_revisione import xlsx  # noqa: E402

CHIAVE = "chiave-di-prova"
INTESTAZIONE = ("[DOC_ID: RMB-{data}]\n[SERIES: Renmin Ribao]\n[DOC_TYPE: newspaper]\n[LANG: zh]\n[YEAR: {anno}]\n"
                "[DATE: {data}]\n[FULL_CITATION: Renmin Ribao, {data}]\n\n")
TESTI = {"1980-04-15": "第1版() 专栏： 贝林格同志率意共中央代表团抵京 新华社北京四月十四日电 由总书记贝林格率领的"
                       "意大利共产党中央代表团今天晚间乘飞机到达北京。",
         "1980-04-16": "第1版() 专栏： 华国锋会见贝林格 新华社北京四月十五日电 华国锋今天会见了意大利共产党总书记贝林格。"}
SCHEDA = "[Enrico Berlinguer]\ntipo = persona\nvarianti = 贝林格\nnote = Segretario del Partito comunista italiano.\n"


class Servizio(BaseHTTPRequestHandler):
    """Servizio compatibile OpenAI che risponde a smistamento, analisi e sintesi."""
    def log_message(self, *a):
        pass

    def _rispondi(self, codice, dati):
        corpo = json.dumps(dati, ensure_ascii=False).encode("utf-8")
        self.send_response(codice)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        self._rispondi(200, {"data": [{"id": "modello-a"}]})

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        testo = corpo["messages"][-1]["content"]
        if '"risultati"' in testo:
            r = {"risultati": [{"n": k, "pertinente": "sì", "motivazione": "è lui"} for k in range(1, 7)]}
        elif "dati_espliciti" in testo:
            r = {"dati_espliciti": [{"testo": "Berlinguer arriva a Pechino.", "rif": [1]}]}
        elif "risposta_finale" in testo:
            r = {"inferenze": [], "problemi_interpretativi": [], "risposta_finale": "Visita in Cina [1]."}
        elif "ok" in testo.lower() and len(testo) < 200:          # prova di collegamento
            r = {"ok": True}
        else:
            r = {"pertinente": "sì", "motivazione": "è lui", "tipo_menzione": "delegazione/visita",
                 "traduzione_it": "Berlinguer a Pechino.", "sintesi_it": "Visita.", "tono": "neutro",
                 "nuove_varianti": [], "altri_nominati": [], "ruolo_entita": "", "evento": ""}
        self._rispondi(200, {"model": corpo["model"],
                             "choices": [{"message": {"content": json.dumps(r, ensure_ascii=False)}}]})


class Interfaccia(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servizio = ThreadingHTTPServer(("127.0.0.1", 0), Servizio)
        url = f"http://127.0.0.1:{cls.servizio.server_address[1]}/v1"
        threading.Thread(target=cls.servizio.serve_forever, daemon=True).start()
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.progetti = base / "projects"
        cls.p1 = cls.progetti / "uno"
        shutil.copytree(PROVA, cls.p1)
        rr = cls.p1 / "data" / "riviste" / "renmin_ribao"
        rr.mkdir(parents=True)
        for data, testo in TESTI.items():
            (rr / f"{data}.txt").write_text(INTESTAZIONE.format(data=data, anno=data[:4]) + testo + "\n",
                                            encoding="utf-8")
        (cls.p1 / "glossary" / "entities.ini").write_text(SCHEDA, encoding="utf-8")
        cls.p2 = cls.progetti / "due"
        shutil.copytree(PROVA, cls.p2)
        (cls.p2 / "project.ini").write_text("[progetto]\nnome = Secondo progetto\n", encoding="utf-8")
        cls.profili = base / "models.ini"
        cls.testo_profili = (
            f"[a]\nservizio = openai\nurl = {url}\nmodello = modello-a\nchiave_env = AIRCHIVIST_PROVA\n\n"
            "[rotto]\nservizio = openai\nurl = http://127.0.0.1:9/v1\nmodello = assente\n"
            "chiave_env = AIRCHIVIST_PROVA\n")
        cls.config = base / "config.ini"
        cls.env = mock.patch.dict(os.environ, {"AIRCHIVIST_PROVA": CHIAVE, VARIABILE: str(cls.p1)})
        cls.env.start()
        os.environ.pop(VARIABILE_FISSATI, None)

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.servizio.shutdown()
        cls.servizio.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        os.environ[VARIABILE] = str(self.p1)
        self.profili.write_text(self.testo_profili, encoding="utf-8")
        self.config.write_text(f"[progetto]\ncartella = {self.p1.as_posix()}\n\n[modello]\n"
                               f"file_profili = {self.profili.as_posix()}\nprofilo = a\n\n"
                               "[estrazione]\nforme_sicure = no\n", encoding="utf-8")
        self.app = A.App(self.config, self.progetti)
        self.server = A.avvia_server(self.app)
        self.porta = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.cookie = self.accedi()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    # ------------------------------------------------------------ richieste
    def richiesta(self, metodo, percorso, dati=None, cookie=True, intestazioni=None):
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=30)
        h = {"Host": f"127.0.0.1:{self.porta}", **(intestazioni or {})}
        if cookie and getattr(self, "cookie", None):
            h["Cookie"] = self.cookie
        corpo = None
        if dati is not None:
            corpo = json.dumps(dati).encode("utf-8")
            h.update({"Content-Type": "application/json", "X-AIrchivist": "1"})
            h.update(intestazioni or {})
        c.request(metodo, percorso, body=corpo, headers=h)
        r = c.getresponse()
        testo = r.read()
        c.close()
        return r, testo

    def accedi(self):
        r, _ = self.richiesta("GET", f"/?t={self.app.token}", cookie=False)
        self.assertEqual(r.status, 303)
        return r.getheader("Set-Cookie").split(";")[0]

    def get(self, percorso):
        r, testo = self.richiesta("GET", percorso)
        return r.status, json.loads(testo)

    def post(self, percorso, dati):
        r, testo = self.richiesta("POST", percorso, dati)
        return r.status, json.loads(testo)

    # ------------------------------------------------------------ sicurezza
    def test_senza_token_rifiutato(self):
        self.assertEqual(self.richiesta("GET", "/api/stato", cookie=False)[0].status, 403)
        self.assertEqual(self.richiesta("GET", "/", cookie=False)[0].status, 403)
        self.assertEqual(self.richiesta("GET", "/?t=sbagliato", cookie=False)[0].status, 403)
        r, testo = self.richiesta("GET", "/")
        self.assertEqual(r.status, 200)
        self.assertIn(b"AIrchivist", testo)

    def test_host_e_post_controllati(self):
        r, _ = self.richiesta("GET", "/api/stato", intestazioni={"Host": "esempio.invalid"})
        self.assertEqual(r.status, 400)
        r, _ = self.richiesta("POST", "/api/ricerca/ferma", {}, intestazioni={"X-AIrchivist": "0"})
        self.assertEqual(r.status, 403)
        r, _ = self.richiesta("GET", "/../config.ini")
        self.assertEqual(r.status, 404)

    # ------------------------------------------------------------ progetto
    def test_cambio_di_progetto(self):
        codice, s = self.get("/api/stato")
        self.assertEqual(codice, 200)
        nomi = {p["nome"]: p["in_uso"] for p in s["progetti"]}
        self.assertEqual(nomi.get("Secondo progetto"), False)
        self.assertEqual(s["progetto"]["cartella"], str(self.p1.resolve()))
        codice, r = self.post("/api/progetto", {"cartella": str(self.p2)})
        self.assertEqual(codice, 200, r)
        self.assertEqual(r["progetto"]["nome"], "Secondo progetto")
        self.assertIn(f"cartella = {self.p2.resolve()}", self.config.read_text(encoding="utf-8"))
        self.assertEqual(os.environ[VARIABILE], str(self.p2.resolve()))
        codice, r = self.post("/api/progetto", {"cartella": str(self.progetti / "inesistente")})
        self.assertEqual(codice, 400)
        self.assertEqual(self.get("/api/stato")[1]["progetto"]["nome"], "Secondo progetto")

    def test_cambio_bloccato_da_una_ricerca_in_corso(self):
        lavoro = self.p1 / "system" / "jobs" / "20990101-000000-prova"
        lavoro.mkdir(parents=True)
        (lavoro / "stato.json").write_text(json.dumps({"id": lavoro.name, "stato": "in corso", "domanda": "X",
                                                       "inizio": time.time(), "battito": time.time()}),
                                           encoding="utf-8")
        try:
            codice, r = self.post("/api/progetto", {"cartella": str(self.p2)})
            self.assertEqual(codice, 400)
            self.assertIn("ricerca in corso", r["errore"])
            self.assertIn(f"cartella = {self.p1.as_posix()}", self.config.read_text(encoding="utf-8"))
        finally:
            shutil.rmtree(lavoro)

    def test_nuovo_progetto(self):
        codice, r = self.post("/api/progetto/nuovo", {"nome": "Stampa albanese"})
        self.assertEqual(codice, 200, r)
        nuovo = self.progetti / "Stampa_albanese"
        self.assertTrue((nuovo / "project.ini").is_file())
        self.assertEqual(r["progetto"]["nome"], "Stampa albanese")
        self.assertEqual(self.post("/api/progetto/nuovo", {"nome": "Stampa albanese"})[0], 400)
        shutil.rmtree(nuovo)

    # ------------------------------------------------------------ modello
    def test_cambio_di_modello(self):
        codice, m = self.get("/api/modelli")
        self.assertEqual({p["nome"] for p in m["profili"]}, {"a", "rotto"})
        self.assertEqual(set(m["in_uso"].values()), {"a"})
        codice, r = self.post("/api/modello/usa", {"nome": "rotto"})
        self.assertEqual(codice, 200, r)
        self.assertFalse(r["cambiato"])
        self.assertEqual(set(self.get("/api/modelli")[1]["in_uso"].values()), {"a"})     # resta il precedente
        self.assertFalse(self.get("/api/collegamento?nome=rotto")[1]["ok"])
        self.assertTrue(self.get("/api/collegamento?nome=a")[1]["ok"])
        codice, r = self.post("/api/modello/usa", {"nome": "a"})
        self.assertTrue(r["cambiato"], r)

    def test_aggiungi_modello(self):
        url = f"http://127.0.0.1:{self.servizio.server_address[1]}/v1"
        codice, r = self.post("/api/modello/elenco", {"servizio": "openai", "url": url, "chiave": CHIAVE})
        self.assertEqual(r["modelli"], ["modello-a"])
        codice, r = self.post("/api/modello/nuovo", {"servizio": "openai", "url": url, "modello": "modello-a",
                                                     "chiave_env": "AIRCHIVIST_PROVA", "nome": "nuovo-a",
                                                     "usa": False})
        self.assertEqual(codice, 200, r)
        self.assertTrue(r["riuscita"], r)
        self.assertNotIn(CHIAVE, self.profili.read_text(encoding="utf-8"))
        self.assertEqual(set(self.get("/api/modelli")[1]["in_uso"].values()), {"a"})
        self.assertEqual(self.post("/api/modello/nuovo", {"servizio": "openai", "url": url,
                                                          "modello": "modello-a", "nome": "nuovo-a"})[0], 400)

    # ------------------------------------------------------------ percorso guidato
    def test_scheda_trovata(self):
        codice, r = self.post("/api/entita", {"nome": "Enrico Berlinguer"})
        self.assertEqual(r["schede"][0]["varianti"], ["贝林格"])
        codice, r = self.post("/api/entita", {"nome": "Nessuno Qui"})
        self.assertEqual(r["schede"], [])
        self.assertEqual(self.post("/api/entita", {"nome": " "})[0], 400)

    def test_documento_solo_dal_progetto(self):
        r, _ = self.richiesta("GET", "/documento?risposta=..%2F..%2Fconfig.ini")
        self.assertEqual(r.status, 404)
        r, _ = self.richiesta("GET", "/documento?ricerca=..")
        self.assertEqual(r.status, 404)

    def test_ricerca_come_da_riga_di_comando(self):
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        cli = subprocess.run([sys.executable, "ricerca.py", "Enrico Berlinguer", "--config", str(self.config)],
                             cwd=MOTORE, env=env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(cli.returncode, 0, cli.stdout + cli.stderr)
        cartella = self.p1 / "results" / "searches" / "enrico_berlinguer"
        da_riga = (cartella / "risposta.md").read_text(encoding="utf-8")
        (cartella / "risposta.md").unlink()

        codice, r = self.post("/api/ricerca/avvia", {"entita": "Enrico Berlinguer", "domanda": "Prova"})
        self.assertEqual(codice, 200, r)
        fine = time.time() + 120
        while time.time() < fine:
            codice, s = self.get("/api/ricerca")
            if s.get("finito"):
                break
            time.sleep(1)
        self.assertTrue(s.get("finito"), s)
        self.assertIn("risposta_pronta", s, s)
        self.assertEqual(s["risposta_pronta"]["documenti_pertinenti"], 2)
        dall_interfaccia = (cartella / "risposta.md").read_text(encoding="utf-8")
        for titolo in ("## 1.", "## 2.", "## 3."):
            self.assertEqual(sezione(dall_interfaccia, titolo), sezione(da_riga, titolo), titolo)
        r, html_ = self.richiesta("GET", s["documento"])
        self.assertEqual(r.status, 200)
        self.assertIn("贝林格".encode("utf-8"), html_)
        storico = self.get("/api/storico")[1]
        self.assertTrue(storico["risposte"])
        self.assertIn("enrico_berlinguer", [x["cartella"] for x in storico["ricerche"]])

    # ------------------------------------------------------------ conversazione (lavoro 38)
    def test_conversazione_disattivata_se_il_modello_non_usa_strumenti(self):
        codice, r = self.get("/api/conversazione")
        self.assertEqual(codice, 200, r)
        self.assertFalse(r["attiva"])
        self.assertIn("percorso guidato", r["motivo"])
        self.assertTrue(r["riprova"])
        codice, r = self.post("/api/conversazione", {"testo": "Chi è Berlinguer?"})
        self.assertEqual(codice, 400)
        self.assertIn("disattivata", r["errore"])
        self.assertEqual(self.post("/api/conversazione", {"testo": " "})[0], 400)
        self.assertFalse(self.post("/api/conversazione/nuova", {})[1]["attiva"])

    # ------------------------------------------------------------ importazione (lavoro 37)
    def audit(self):
        d = A.percorso(self.app.cfg(), "registro_modifiche").parent
        d.mkdir(parents=True, exist_ok=True)
        return d

    def tabella_di_prova(self, f):
        righe = [{"importa": "sì", "file": "a.pdf", "serie": "", "data": "1967-01-12", "da_controllare": "serie",
                  "percorso": "C:/fonti/a.pdf"},
                 {"importa": "sì", "file": "b.pdf", "serie": "Renmin Ribao", "data": "", "da_controllare": "",
                  "percorso": "C:/fonti/b.pdf"}]
        R.scrivi_tabella(f, list(righe[0]), righe)
        return righe

    def test_tabella_di_revisione(self):
        f = self.audit() / "review_prova.csv"
        righe = self.tabella_di_prova(f)
        try:
            codice, t = self.get("/api/tabella?percorso=" + quote(str(f)))
            self.assertEqual(codice, 200, t)
            self.assertEqual(t["tipo"], "proposta")
            self.assertEqual(t["colonne"][:3], ["importa", "file", "serie"])
            self.assertEqual(t["colonne"][-1], "percorso")                   # le avanzate dopo le essenziali
            self.assertEqual([r["file"] for r in t["righe"]], ["a.pdf", "b.pdf"])
            self.assertIn("serie", t)

            corrette = [dict(righe[0], serie="Renmin Ribao"), {"percorso": "C:/fonti/b.pdf", "importa": "no"}]
            codice, s = self.post("/api/tabella", {"percorso": str(f), "righe": corrette})
            self.assertEqual(codice, 200, s)
            self.assertEqual((s["righe"], s["tabella"]), (2, str(f.resolve())))
            grezzo = f.read_bytes()
            self.assertTrue(grezzo.startswith(b"\xef\xbb\xbf"))                  # BOM e CRLF come proponi
            self.assertTrue(grezzo[3:].startswith(b"importa;file;serie;data;da_controllare;percorso\r\n"))
            nuove = R.leggi_tabella(f)
            self.assertEqual(nuove[0]["serie"], "Renmin Ribao")
            self.assertEqual(nuove[1]["importa"], "no")
            self.assertEqual(nuove[1]["serie"], "Renmin Ribao")              # colonna non mandata: resta com'è

            codice, r = self.post("/api/tabella", {"percorso": str(f), "righe": corrette[:1]})
            self.assertEqual(codice, 400)
            self.assertIn("ricaricala", r["errore"])
            scambiate = [corrette[1], corrette[0]]
            self.assertEqual(self.post("/api/tabella", {"percorso": str(f), "righe": scambiate})[0], 400)
            self.assertEqual(R.leggi_tabella(f), nuove)                      # nessuna scrittura dopo un rifiuto
        finally:
            f.unlink()

    def test_tabella_solo_dal_progetto(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "review_fuori.csv"
            self.tabella_di_prova(f)
            prima = f.read_bytes()
            codice, r = self.get("/api/tabella?percorso=" + quote(str(f)))
            self.assertEqual(codice, 400)
            self.assertIn("cartelle del progetto", r["errore"])
            self.assertEqual(self.post("/api/tabella", {"percorso": str(f), "righe": []})[0], 400)
            self.assertEqual(f.read_bytes(), prima)
            self.assertEqual(self.post("/api/importa", {"azione": "applica", "percorso": str(f)})[0], 400)
        self.assertEqual(self.get("/api/tabella?percorso=" + quote(str(self.audit() / "assente.csv")))[0], 400)

    def test_tabella_excel_non_riscritta(self):
        f = self.audit() / "review_excel.xlsx"
        xlsx(f, [["importa", "file", "serie", "percorso"], ["sì", "a.pdf", "", "C:/fonti/a.pdf"]])
        prima = f.read_bytes()
        csv_ = f.with_suffix(".csv")
        try:
            codice, t = self.get("/api/tabella?percorso=" + quote(str(f)))
            self.assertEqual(codice, 200, t)
            self.assertEqual(t["righe"][0]["file"], "a.pdf")
            codice, s = self.post("/api/tabella", {"percorso": str(f),
                                                   "righe": [dict(t["righe"][0], serie="Renmin Ribao")]})
            self.assertEqual(codice, 200, s)
            self.assertEqual(f.read_bytes(), prima)                           # il file Excel resta intatto
            self.assertEqual(s["tabella"], str(csv_.resolve()))
            self.assertEqual(R.leggi_tabella(csv_)[0]["serie"], "Renmin Ribao")
            self.assertEqual(self.get("/api/tabella?percorso=" + quote(s["tabella"]))[0], 200)
        finally:
            f.unlink()
            csv_.unlink(missing_ok=True)

    def test_stato_importazione(self):
        f = self.audit() / "review_stato.csv"
        self.tabella_di_prova(f)
        lavoro = A.percorso(self.app.cfg(), "lavori_importazioni") / "20990101-000000-prova"
        lavoro.mkdir(parents=True)
        try:
            (lavoro / "registro.txt").write_text("Lettura dei file\npagina 3/12 a.pdf\n", encoding="utf-8")
            codice, r = self.get("/api/importa?id=" + lavoro.name)
            self.assertEqual(codice, 200, r)
            self.assertFalse(r["finita"])
            self.assertEqual(r["avanzamento"]["fatto"], 3)
            self.assertEqual(r["avanzamento"]["totale"], 12)
            self.assertNotIn("tabella", r)
            self.assertNotIn("registro", r)                                   # alla pagina solo le ultime righe

            (lavoro / "registro.txt").write_text(f"pagina 12/12 b.pdf\n\nTabella: {f}\n", encoding="utf-8")
            (lavoro / "esito.json").write_text(json.dumps({"codice": 0}), encoding="utf-8")
            codice, r = self.get("/api/importa?id=" + lavoro.name)
            self.assertTrue(r["finita"])
            self.assertTrue(r["pronta"])
            self.assertEqual(r["tabella"], str(f))
            self.assertEqual(r["ultime"][-1], f"Tabella: {f}")
            self.assertEqual(self.get("/api/importa?id=assente")[0], 400)
        finally:
            shutil.rmtree(lavoro)
            f.unlink()

    def test_importa_azioni_controllate(self):
        codice, r = self.post("/api/importa", {"azione": "stato"})
        self.assertEqual(codice, 400)
        self.assertEqual(self.post("/api/importa", {"azione": "proponi", "percorso": " "})[0], 400)
    # ------------------------------------------------------------ fonte, passaggi, glossario (lavoro 36)
    def test_visore_della_fonte(self):
        rel = "volumi/prova_visore/documento.txt"
        f = self.p1 / "data" / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("[DOC_ID: documento]\n[SERIES: Prova visore]\n[TITLE: Documento di prova]\n"
                     "[SOURCE_FILE: volumi/prova_visore/documento.pdf]\n\n[[p. 5 | pdf 1]]\nprima pagina\n"
                     "[[p. 6 | pdf 2]]\nseconda pagina, riga cercata\nultima riga\n", encoding="utf-8")
        cercata = 9                                       # «seconda pagina, riga cercata»
        codice, r = self.get("/api/fonte?file=" + quote(rel) + f"&riga={cercata}")
        self.assertEqual(codice, 200, r)
        self.assertEqual([p["etichetta"] for p in r["pagine"]], ["p. 5", "p. 6"])
        self.assertEqual((r["pagina"], r["evidenzia"], r["titolo"]), (2, cercata, "Documento di prova"))
        self.assertEqual([x["n"] for x in r["righe"]], [8, 9, 10])
        self.assertEqual(r["immagine"], "")               # l'originale non c'è ancora
        codice, r = self.get("/api/fonte?file=" + quote(rel) + "&pagina=1")
        self.assertEqual((r["pagina"], r["evidenzia"], r["righe"][0]["n"]), (1, None, 1))   # con l'intestazione
        codice, r = self.get("/api/fonte?file=" + quote("riviste/renmin_ribao/1980-04-15.txt"))
        self.assertTrue(r["pagine"][0]["etichetta"].startswith("righe 1-"))        # senza marcatori: blocchi
        for fuori in ("../project.ini", "../../config.ini", "riviste/renmin_ribao/assente.txt"):
            self.assertEqual(self.get("/api/fonte?file=" + quote(fuori))[0], 400, fuori)
        fitz = A._fitz()
        if fitz is None:
            return
        pdf = self.p1 / "sources" / "volumi" / "prova_visore" / "documento.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        doc = fitz.open()
        for k in (5, 6):
            doc.new_page(width=300, height=400).insert_text((40, 60), f"pagina {k}")
        doc.save(pdf)
        doc.close()
        r = self.get("/api/fonte?file=" + quote(rel) + f"&riga={cercata}")[1]
        self.assertIn("pdf=2", r["immagine"])
        risposta, png = self.richiesta("GET", r["immagine"])
        self.assertEqual((risposta.status, risposta.getheader("Content-Type")), (200, "image/png"))
        self.assertTrue(png.startswith(b"\x89PNG"))
        self.assertEqual(self.richiesta("GET", "/fonte/pagina?file=" + quote(rel) + "&pdf=9")[0].status, 404)
        self.assertEqual(self.richiesta("GET", "/fonte/pagina?file=" + quote("../project.ini") + "&pdf=1")[0].status,
                         404)
        self.assertEqual(self.richiesta("GET", "/fonte/pagina?file=" + quote(rel) + "&pdf=1",
                                        cookie=False)[0].status, 403)

    def test_passaggi_e_rimandi(self):
        risposte = self.p1 / "results" / "answers"
        risposte.mkdir(parents=True, exist_ok=True)
        (risposte / "prova_rimandi.md").write_text(
            "# Prova\n\n## 2. Passaggi rilevanti\n\n### [1] *Renmin Ribao*. 1980. 15 aprile 1980.\n\n> testo\n\n"
            "— *Renmin Ribao*. 1980. 15 aprile 1980, p. 1.\n\n"
            "### [2] *Renmin Ribao*. 1980. 16 aprile 1980.\n\n## 8. Dati tecnici per la verifica\n\n"
            "- [1] `riviste/renmin_ribao/1980-04-15.txt`, riga 9\n"
            "- [2] `riviste/renmin_ribao/1980-04-16.txt`, righe 9, 12\n", encoding="utf-8")
        codice, r = self.get("/api/passaggi?risposta=prova_rimandi.md")
        self.assertEqual(codice, 200, r)
        self.assertEqual(r["rimandi"]["1"], {"file": "riviste/renmin_ribao/1980-04-15.txt", "riga": 9,
                                             "riferimento": "*Renmin Ribao*. 1980. 15 aprile 1980.", "pagina": "1"})
        self.assertEqual((r["rimandi"]["2"]["riga"], r["rimandi"]["2"]["pagina"]), (9, ""))
        self.assertEqual([(p["n"], p["riga"]) for p in r["passaggi"]], [("1", "9"), ("2", "9")])
        cartella = self.p1 / "results" / "searches" / "prova_visore"
        cartella.mkdir(parents=True, exist_ok=True)
        (cartella / "passaggi.jsonl").write_text(json.dumps({"id": "a1"}) + "\n", encoding="utf-8")
        analisi = {"pertinente": "sì", "traduzione_it": "Berlinguer a Pechino.", "pagina": "1",
                   "provenienza": {"lettura": {"livello": "modello", "da": "modello-a"}}}
        righe = [{"id": "a1", "data": "1980-04-15", "citazione": "Renmin Ribao, 1980-04-15", "riga": 9,
                  "file": "riviste/renmin_ribao/1980-04-15.txt", "analisi": analisi},
                 {"id": "vecchio", "data": "1979-01-01", "file": "x.txt", "riga": 1, "analisi": analisi}]
        (cartella / "classificati.jsonl").write_text("".join(json.dumps(x, ensure_ascii=False) + "\n" for x in righe),
                                                     encoding="utf-8")
        codice, r = self.get("/api/passaggi?ricerca=prova_visore")       # senza risposta.html: va bene lo stesso
        self.assertEqual(codice, 200, r)
        self.assertEqual(r["passaggi"], [{"data": "1980-04-15", "fonte": "Renmin Ribao, 1980-04-15", "pagina": "1",
                                          "pertinente": "sì", "letto_da": "modello-a",
                                          "traduzione": "Berlinguer a Pechino.",
                                          "file": "riviste/renmin_ribao/1980-04-15.txt", "riga": "9"}])
        for q in ("ricerca=..", "ricerca=assente", "risposta=..%2F..%2Fconfig.ini", ""):
            self.assertEqual(self.get("/api/passaggi?" + q)[0], 400, q)

    def test_glossario(self):
        codice, r = self.get("/api/glossario")
        self.assertEqual(codice, 200, r)
        scheda = next(s for s in r["schede"] if s["nome"] == "Enrico Berlinguer")
        self.assertEqual(scheda["campi"]["varianti"], "贝林格")
        self.assertTrue(r["serie"])
        self.assertTrue(all({"nome", "campi"} <= set(s) for s in r["serie"]))

    # ------------------------------------------------------------ preparazione (lavoro 39)
    def client_finti(self):
        """I file dei client di chat in una cartella temporanea, mai quelli veri di questo computer."""
        base = self.p1.parent.parent / f"client_{self._testMethodName}"      # una cartella per test
        return mock.patch.object(A.installa, "file_client",
                                 lambda nome, dati=None: base / nome / "data" / "mcp_config.json")

    def test_preparazione(self):
        with self.client_finti():
            codice, r = self.get("/api/avvio")
        self.assertEqual(codice, 200, r)
        self.assertTrue(r["completo"])
        passi = {p["id"]: p for p in r["passi"]}
        self.assertEqual(list(passi), ["progetto", "modello", "fonti", "chat"])
        self.assertTrue(passi["progetto"]["fatto"] and passi["modello"]["fatto"] and passi["fonti"]["fatto"])
        self.assertIn("a", passi["modello"]["dettaglio"])
        self.assertFalse(passi["chat"]["fatto"])
        self.assertEqual([c["id"] for c in r["chat"]], ["jan", "claude", "lmstudio"])
        # senza progetto né modello: la preparazione non è completa e comincia dal progetto
        vuoto = self.config.with_name("vuoto.ini")
        vuoto.write_text("[estrazione]\nforme_sicure = no\n", encoding="utf-8")
        os.environ.pop(VARIABILE, None)
        with self.client_finti():
            r = A.App(vuoto, self.progetti).avvio()
        passi = {p["id"]: p for p in r["passi"]}
        self.assertFalse(r["completo"])
        self.assertFalse(passi["progetto"]["fatto"] or passi["modello"]["fatto"] or passi["fonti"]["fatto"])
        self.assertIn("progetto", passi["modello"]["dettaglio"])
        # primo avvio: senza progetto le serie sono vuote invece di un errore (prima l'interfaccia non partiva)
        import progetto
        vera = progetto.leggi_config
        with mock.patch.object(progetto, "leggi_config", lambda path=None: vera(vuoto)):
            self.assertEqual(A.profili.tutti(ricarica=True), {})
        A.profili.tutti(ricarica=True)
        # profilo scelto ma inesistente: il modello resta da fare
        self.config.write_text(self.config.read_text(encoding="utf-8").replace("profilo = a", "profilo = nessuno"),
                               encoding="utf-8")
        os.environ[VARIABILE] = str(self.p1)
        with self.client_finti():
            r = self.get("/api/avvio")[1]
        self.assertFalse(r["completo"])
        self.assertFalse(next(p for p in r["passi"] if p["id"] == "modello")["fatto"])

    def test_ambiente(self):
        codice, r = self.get("/api/ambiente")
        self.assertEqual(codice, 200, r)
        self.assertEqual([g["titolo"] for g in r["gruppi"]],
                         ["Programma", "Progetto e modello", "Importazione delle fonti"])
        voci = {v["voce"]: v for g in r["gruppi"] for v in g["voci"]}
        self.assertEqual(r["mancano"], [], r)
        self.assertEqual(voci["modelli: a"]["stato"], "ok")       # il servizio finto risponde
        self.assertNotIn("PYTHONUTF8", voci)
        self.assertTrue(any(x.startswith("Configurazione: ") for x in r["posizioni"]))
        # senza progetto: manca, con l'azione che lo crea; il modello non si controlla
        vuoto = self.config.with_name("vuoto.ini")
        vuoto.write_text("[estrazione]\nforme_sicure = no\n", encoding="utf-8")
        os.environ.pop(VARIABILE, None)
        r = A.App(vuoto, self.progetti).ambiente()
        voci = {v["voce"]: v for g in r["gruppi"] for v in g["voci"]}
        self.assertEqual(r["mancano"], ["progetto"])
        self.assertEqual(voci["progetto"]["azione"], "progetto")
        self.assertFalse(any(v.startswith("modelli") for v in voci))

    def test_collega_la_chat(self):
        f = self.p1.parent.parent / f"client_{self._testMethodName}" / "jan" / "data" / "mcp_config.json"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps({"mcpServers": {"altro": {"command": "x", "args": []}}}), encoding="utf-8")
        prove = []

        def verifica(args, stampa, avvia=None):
            prove.append(1)
            stampa("Handshake MCP riuscito")
            return 0
        with self.client_finti(), mock.patch.object(A.installa, "in_esecuzione", lambda nome: False), \
                mock.patch.object(A.installa, "client_verifica", verifica):
            codice, c = self.get("/api/client?nome=jan")
            self.assertEqual(codice, 200, c)
            self.assertFalse(c["gia"])
            self.assertTrue(any("airchivist" in m for m in c["modifiche"]), c)
            self.assertIn("mcp_server.py", c["avvia"])
            self.assertEqual(json.loads(f.read_text(encoding="utf-8")),     # l'anteprima non scrive
                             {"mcpServers": {"altro": {"command": "x", "args": []}}})
            codice, r = self.post("/api/client", {"nome": "jan"})
            self.assertEqual(codice, 200, r)
            self.assertTrue(r["scritto"] and r["prova"])
            doc = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(doc["mcpServers"]["altro"], {"command": "x", "args": []})
            self.assertTrue(doc["mcpServers"]["airchivist"]["active"])
            self.assertTrue(list(f.parent.glob("mcp_config.json.airchivist-*.bak")))
            self.assertTrue(self.get("/api/client?nome=jan")[1]["gia"])
            avvio = self.get("/api/avvio")[1]
            self.assertTrue(next(p for p in avvio["passi"] if p["id"] == "chat")["fatto"])
            # di nuovo: niente da scrivere, solo la prova
            r = self.post("/api/client", {"nome": "jan"})[1]
            self.assertFalse(r["scritto"])
            self.assertEqual(len(prove), 2)
            self.assertEqual(self.get("/api/client?nome=sconosciuto")[0], 400)
        # Jan aperto: nessuna scrittura
        g = f.with_name("altro.json")
        with mock.patch.object(A.installa, "file_client", lambda nome, dati=None: g), \
                mock.patch.object(A.installa, "in_esecuzione", lambda nome: True):
            self.assertTrue(self.get("/api/client?nome=jan")[1]["aperto"])
            codice, r = self.post("/api/client", {"nome": "jan"})
        self.assertEqual(codice, 400)
        self.assertIn("aperto", r["errore"])
        self.assertFalse(g.exists())


def sezione(testo, titolo):
    """Il testo di una sezione della risposta, dal suo titolo al successivo."""
    inizio = testo.index(titolo)
    fine = testo.find("\n## ", inizio + 1)
    return testo[inizio:fine if fine > 0 else None]


if __name__ == "__main__":
    unittest.main()

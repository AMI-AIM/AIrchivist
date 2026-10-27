"""
Test dell'interfaccia (app.py, lavoro 35), con il server HTTP vero in locale, due progetti temporanei e un servizio
dei modelli finto:
- sicurezza: senza il token di sessione ogni richiesta è rifiutata; Host estraneo e POST senza intestazione no;
- menu «Progetto»: elenco, cambio (scritto in config.ini), nuovo progetto, cambio bloccato da una ricerca in corso;
- menu «Modello»: un profilo il cui collegamento fallisce non diventa quello in uso; uno che funziona sì;
- percorso guidato: scheda trovata, ricerca avviata dall'interfaccia su un'entità già in archivio con lo stesso
  risultato della riga di comando; documento della risposta servito solo dalle cartelle del progetto.
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

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
PROVA = Path(__file__).resolve().parent / "test_project"
sys.path.insert(0, str(MOTORE))
import app as A  # noqa: E402
from llm import VARIABILE_FISSATI  # noqa: E402
from progetto import VARIABILE  # noqa: E402

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


def sezione(testo, titolo):
    """Il testo di una sezione della risposta, dal suo titolo al successivo."""
    inizio = testo.index(titolo)
    fine = testo.find("\n## ", inizio + 1)
    return testo[inizio:fine if fine > 0 else None]


if __name__ == "__main__":
    unittest.main()

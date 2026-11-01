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


def sezione(testo, titolo):
    """Il testo di una sezione della risposta, dal suo titolo al successivo."""
    inizio = testo.index(titolo)
    fine = testo.find("\n## ", inizio + 1)
    return testo[inizio:fine if fine > 0 else None]


if __name__ == "__main__":
    unittest.main()

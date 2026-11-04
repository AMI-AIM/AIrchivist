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
            f"[a]\nservizio = openai\nurl = {url}\nmodello = modello-a\nchiave_env = PRESSMARK_PROVA\n\n"
            "[rotto]\nservizio = openai\nurl = http://127.0.0.1:9/v1\nmodello = assente\n"
            "chiave_env = PRESSMARK_PROVA\n")
        cls.config = base / "config.ini"
        cls.env = mock.patch.dict(os.environ, {"PRESSMARK_PROVA": CHIAVE, VARIABILE: str(cls.p1)})
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
            h.update({"Content-Type": "application/json", "X-Pressmark": "1"})
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
        self.assertIn(b"Pressmark", testo)

    def test_host_e_post_controllati(self):
        r, _ = self.richiesta("GET", "/api/stato", intestazioni={"Host": "esempio.invalid"})
        self.assertEqual(r.status, 400)
        r, _ = self.richiesta("POST", "/api/ricerca/ferma", {}, intestazioni={"X-Pressmark": "0"})
        self.assertEqual(r.status, 403)
        r, _ = self.richiesta("GET", "/../config.ini")
        self.assertEqual(r.status, 404)

    def test_marchio(self):
        # logotipo e favicon vengono da assets/marchio; fuori da quella cartella non si legge nulla
        for nome in ("pressmark-favicon-chiaro.svg", "pressmark-logotipo-scuro.svg"):
            r, testo = self.richiesta("GET", f"/marchio/{nome}")
            self.assertEqual((r.status, r.getheader("Content-Type")), (200, "image/svg+xml"))
            self.assertIn(b"<svg", testo)
        self.assertEqual(self.richiesta("GET", "/marchio/../../scripts/config.ini")[0].status, 404)
        self.assertEqual(self.richiesta("GET", "/marchio/assente.svg")[0].status, 404)

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

    def test_modello_per_ruolo_e_fornitore(self):
        url = f"http://127.0.0.1:{self.servizio.server_address[1]}/v1"
        self.profili.write_text(self.testo_profili + f"\n[b]\nservizio = openai\nurl = {url}\nmodello = modello-a\n"
                                "chiave_env = PRESSMARK_PROVA\n", encoding="utf-8")
        m = self.get("/api/modelli")[1]
        # i profili si raggruppano per fornitore: un indirizzo sconosciuto fa gruppo da sé, con il suo host
        self.assertEqual({p["fornitore"]["id"] for p in m["profili"]}, {"openai:127.0.0.1"})
        self.assertEqual(next(p for p in m["profili"] if p["nome"] == "a")["chiave_env"], "PRESSMARK_PROVA")
        # un ruolo solo: gli altri restano sul profilo di prima
        codice, r = self.post("/api/modello/usa", {"nome": "b", "ruoli": ["sintesi"]})
        self.assertTrue(r["cambiato"], r)
        self.assertEqual(self.get("/api/modelli")[1]["in_uso"],
                         {"smistamento": "a", "analisi": "a", "sintesi": "b"})
        # senza ruoli vale per tutti, e toglie la scelta per ruolo
        codice, r = self.post("/api/modello/usa", {"nome": "b"})
        self.assertTrue(r["cambiato"], r)
        self.assertEqual(set(self.get("/api/modelli")[1]["in_uso"].values()), {"b"})
        self.assertEqual(self.post("/api/modello/usa", {"nome": "a", "ruoli": "sintesi"})[0], 400)

    def test_interruttori(self):
        spegni = lambda tipo, nome: self.post("/api/interruttore", {"tipo": tipo, "nome": nome, "acceso": False})
        accendi = lambda tipo, nome: self.post("/api/interruttore", {"tipo": tipo, "nome": nome, "acceso": True})
        # ciò che è in uso non si spegne: il profilo, il suo fornitore, la sua chiave
        self.assertEqual(spegni("profilo", "a")[0], 400)
        self.assertEqual(spegni("fornitore", "openai:127.0.0.1")[0], 400)
        self.assertEqual(spegni("chiave", "PRESSMARK_PROVA")[0], 400)
        self.assertEqual(spegni("altro", "x")[0], 400)
        self.assertEqual(spegni("profilo", "nessuno")[0], 400)
        # un profilo spento resta nel file ma non si sceglie
        codice, r = spegni("profilo", "rotto")
        self.assertTrue(r["cambiato"], r)
        p = {x["nome"]: x for x in self.get("/api/modelli")[1]["profili"]}
        self.assertTrue(p["rotto"]["spento"] and p["rotto"]["bloccato"])
        self.assertFalse(p["a"]["spento"] or p["a"]["bloccato"])
        codice, r = self.post("/api/modello/usa", {"nome": "rotto"})
        self.assertFalse(r["cambiato"])
        self.assertIn("spento", " ".join(r["messaggi"]))
        self.assertIn("profili = rotto", self.config.read_text(encoding="utf-8"))
        # un fornitore spento non è attivo, anche con la chiave
        with mock.patch.dict(os.environ, {"GROQ_API_KEY": "k"}):
            self.assertTrue(spegni("fornitore", "groq")[1]["cambiato"])
            g = next(x for x in self.get("/api/fornitori")[1]["fornitori"] if x["id"] == "groq")
            self.assertTrue(g["spento"])
            self.assertFalse(g["attivo"] or g["pronto"])
            self.assertFalse(spegni("fornitore", "groq")[1]["cambiato"])      # già spento: nessuna scrittura
            accendi("fornitore", "groq")
            self.assertTrue(next(x for x in self.get("/api/fornitori")[1]["fornitori"] if x["id"] == "groq")["attivo"])
        accendi("profilo", "rotto")
        testo = self.config.read_text(encoding="utf-8")
        self.assertNotIn("\nprofili =", testo)                                # niente più spento: la voce sparisce
        self.assertNotIn("\nfornitori =", testo)

    def test_prova_rinomina_e_togli_un_profilo(self):
        self.assertTrue(self.post("/api/modello/prova", {"nome": "a"})[1]["riuscita"])
        self.assertFalse(self.post("/api/modello/prova", {"nome": "rotto"})[1]["riuscita"])
        self.assertEqual(set(self.get("/api/modelli")[1]["in_uso"].values()), {"a"})     # la prova non sceglie
        # il profilo in uso non si rinomina e non si toglie
        self.assertEqual(self.post("/api/modello/rinomina", {"nome": "a", "nuovo": "b"})[0], 400)
        self.assertEqual(self.post("/api/modello/togli", {"nome": "a"})[0], 400)
        self.assertEqual(self.post("/api/modello/rinomina", {"nome": "rotto", "nuovo": "a"})[0], 400)   # esiste già
        self.assertEqual(self.post("/api/modello/rinomina", {"nome": "rotto", "nuovo": "con spazi"})[0], 400)
        codice, r = self.post("/api/modello/rinomina", {"nome": "rotto", "nuovo": "rotto-2"})
        self.assertEqual(codice, 200, r)
        testo = self.profili.read_text(encoding="utf-8")
        self.assertIn("[rotto-2]\nservizio = openai\nurl = http://127.0.0.1:9/v1", testo)
        self.assertNotIn("[rotto]", testo)
        codice, r = self.post("/api/modello/togli", {"nome": "rotto-2"})
        self.assertEqual(codice, 200, r)
        self.assertEqual({p["nome"] for p in self.get("/api/modelli")[1]["profili"]}, {"a"})
        self.assertTrue(list(self.profili.parent.glob("models.ini.pressmark-*.bak")))    # la copia prima
        self.assertEqual(self.post("/api/modello/togli", {"nome": "rotto-2"})[0], 400)

    def test_fornitori_e_chiave(self):
        with mock.patch.dict(os.environ, {}):
            for env in ("ANTHROPIC_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY", "FREELLMAPI_KEY",
                        "OPENAI_API_KEY", "MISTRAL_API_KEY", "XAI_API_KEY", "MINIMAX_API_KEY", "HF_TOKEN",
                        "NVIDIA_API_KEY"):
                os.environ.pop(env, None)
            r = self.get("/api/fornitori?locali=1")[1]
            f = {x["id"]: x for x in r["fornitori"]}
            # senza ?locali=1 non si chiede nulla ai servizi sul computer: lo stato resta da sapere
            senza = {x["id"]: x for x in self.get("/api/fornitori")[1]["fornitori"]}
            self.assertIsNone(senza["openai:127.0.0.1"]["pronto"])
            self.assertTrue(senza["groq"]["pronto"] is False and senza["anthropic"]["pronto"] is False)
            # i fornitori noti ci sono anche senza profili; quello dei profili di prova fa gruppo da sé
            self.assertLessEqual({"ollama", "anthropic", "groq", "google-gemini", "openrouter", "freellmapi", "openai",
                                  "mistral", "xai", "minimax", "hugging-face", "nvidia-nim"}, set(f))
            self.assertFalse(any(x["attivo"] for x in f.values() if x["chiave_env"].endswith(("_KEY", "_TOKEN"))
                                 and x["id"] != "openai:127.0.0.1"))
            locale = f["openai:127.0.0.1"]
            self.assertEqual({p["nome"] for p in locale["profili"]}, {"a", "rotto"})
            self.assertTrue(locale["attivo"] and locale["locale"])
            # un servizio sul computer è «pronto» solo se risponde: quello di prova sì, e dice i suoi modelli
            self.assertTrue(locale["raggiungibile"] and locale["pronto"])
            self.assertEqual(locale["installati"], ["modello-a"])
            self.assertTrue(locale["url"].startswith("http://127.0.0.1:"))
            self.assertIsNone(f["groq"]["raggiungibile"])                  # online: non si chiede
            self.assertTrue(f["ollama"]["attivo"])                        # non serve una chiave
            self.assertFalse(f["groq"]["attivo"] or f["groq"]["locale"])
            self.assertEqual(f["groq"]["chiave_env"], "GROQ_API_KEY")
            self.assertEqual(set(r["in_uso"].values()), {"a"})
            # una chiave rifiutata dal servizio non si salva
            with mock.patch.object(A.installa, "modelli_servizio", return_value=None) as prova:
                codice, s = self.post("/api/chiave", {"fornitore": "groq", "chiave": "sbagliata"})
            self.assertEqual(codice, 200, s)
            self.assertFalse(s["salvata"])
            self.assertEqual(prova.call_args[0], ("https://api.groq.com/openai/v1", "sbagliata"))
            self.assertNotIn("GROQ_API_KEY", os.environ)
            with mock.patch.object(A.installa, "modelli_servizio", return_value=["qwen"]):
                codice, s = self.post("/api/chiave", {"fornitore": "groq", "chiave": " buona "})
            self.assertTrue(s["salvata"] and s["provata"], s)
            self.assertEqual(os.environ["GROQ_API_KEY"], "buona")
            self.assertTrue(next(x for x in self.get("/api/fornitori")[1]["fornitori"] if x["id"] == "groq")["attivo"])
            # Anthropic non elenca i modelli, Hugging Face li elenca anche con una chiave sbagliata: vale senza prova
            codice, s = self.post("/api/chiave", {"fornitore": "anthropic", "chiave": "k"})
            self.assertTrue(s["salvata"] and not s["provata"], s)
            with mock.patch.object(A.installa, "modelli_servizio") as prova:
                codice, s = self.post("/api/chiave", {"fornitore": "hugging-face", "chiave": "hf_x"})
            self.assertTrue(s["salvata"] and not s["provata"], s)
            prova.assert_not_called()
            self.assertEqual(os.environ["HF_TOKEN"], "hf_x")
            self.assertEqual(self.post("/api/chiave", {"fornitore": "ollama", "chiave": "k"})[0], 400)
            self.assertEqual(self.post("/api/chiave", {"fornitore": "groq", "chiave": "  "})[0], 400)
            self.assertEqual(self.post("/api/chiave", {"fornitore": "nessuno", "chiave": "k"})[0], 400)

    def test_aggiungi_modello(self):
        url = f"http://127.0.0.1:{self.servizio.server_address[1]}/v1"
        codice, r = self.post("/api/modello/elenco", {"servizio": "openai", "url": url, "chiave": CHIAVE})
        self.assertEqual(r["modelli"], ["modello-a"])
        codice, r = self.post("/api/modello/nuovo", {"servizio": "openai", "url": url, "modello": "modello-a",
                                                     "chiave_env": "PRESSMARK_PROVA", "nome": "nuovo-a",
                                                     "usa": False})
        self.assertEqual(codice, 200, r)
        self.assertTrue(r["riuscita"], r)
        self.assertNotIn(CHIAVE, self.profili.read_text(encoding="utf-8"))
        self.assertEqual(set(self.get("/api/modelli")[1]["in_uso"].values()), {"a"})
        self.assertEqual(self.post("/api/modello/nuovo", {"servizio": "openai", "url": url,
                                                          "modello": "modello-a", "nome": "nuovo-a"})[0], 400)
        # aggiunto e scelto: una sola prova di collegamento (prima una per «aggiungi» e una per «usa»)
        with mock.patch.object(A.installa, "prova_profilo", wraps=A.installa.prova_profilo) as prova:
            codice, r = self.post("/api/modello/nuovo", {"servizio": "openai", "url": url, "modello": "modello-a",
                                                         "chiave_env": "PRESSMARK_PROVA", "nome": "nuovo-b"})
        self.assertTrue(r["cambiato"], r)
        self.assertEqual(prova.call_count, 1)
        self.assertEqual(set(self.get("/api/modelli")[1]["in_uso"].values()), {"nuovo-b"})

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
            # importazione: «[k/N]» annuncia il documento in corso, la barra non si riempie prima della fine
            (lavoro / "registro.txt").write_text("[1/1] a.pdf\n  OCR (sqi, 2 pagine alla volta) ...\n",
                                                 encoding="utf-8")
            a = self.get("/api/importa?id=" + lavoro.name)[1]["avanzamento"]
            self.assertEqual((a["fatto"], a["totale"]), (0, 1))
            self.assertIn("OCR", a["testo"])

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

    def test_fili_e_corpo_del_documento(self):
        filo = {"titolo": "Chi era Berlinguer?", "entita": "Enrico Berlinguer",
                "messaggi": [{"tipo": "utente", "testo": "Chi era Berlinguer?"}]}
        codice, r = self.post("/api/filo", {"filo": filo})
        self.assertEqual(codice, 200, r)
        ident = r["id"]
        filo.update(id=ident, messaggi=filo["messaggi"] + [{"tipo": "conversazione", "voce": {"testo": "Un segretario."}}])
        self.assertEqual(self.post("/api/filo", {"filo": filo})[1]["id"], ident)       # stesso filo, riscritto
        codice, letto = self.get("/api/filo?id=" + ident)
        self.assertEqual((codice, len(letto["messaggi"]), letto["entita"]), (200, 2, "Enrico Berlinguer"))
        self.assertEqual([x["id"] for x in self.get("/api/fili")[1]["fili"]], [ident])
        for male in ("../config", "x" * 16, ""):                                       # niente percorsi
            self.assertEqual(self.get("/api/filo?id=" + quote(male))[0], 400, male)
        self.assertEqual(self.post("/api/filo", {"filo": {"id": "../../x", "messaggi": []}})[0], 400)
        risposte = self.p1 / "results" / "answers"
        risposte.mkdir(parents=True, exist_ok=True)
        (risposte / "prova_corpo.md").write_text("# Prova\n\n## 7. Risposta finale\n\nTesto <b>sicuro</b>.\n",
                                                 encoding="utf-8")
        codice, r = self.get("/api/documento?risposta=prova_corpo.md")
        self.assertEqual(codice, 200, r)
        self.assertIn("<h2>Risposta finale</h2>", r["corpo"])
        self.assertIn("&lt;b&gt;sicuro&lt;/b&gt;", r["corpo"])
        self.assertNotIn("<body", r["corpo"])

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
        self.assertEqual(r["rimandi"]["1"], {"file": "riviste/renmin_ribao/1980-04-15.txt", "riga": 9, "righe": [9],
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
            self.assertTrue(any("pressmark" in m for m in c["modifiche"]), c)
            self.assertIn("mcp_server.py", c["avvia"])
            self.assertEqual(json.loads(f.read_text(encoding="utf-8")),     # l'anteprima non scrive
                             {"mcpServers": {"altro": {"command": "x", "args": []}}})
            codice, r = self.post("/api/client", {"nome": "jan"})
            self.assertEqual(codice, 200, r)
            self.assertTrue(r["scritto"] and r["prova"])
            doc = json.loads(f.read_text(encoding="utf-8"))
            self.assertEqual(doc["mcpServers"]["altro"], {"command": "x", "args": []})
            self.assertTrue(doc["mcpServers"]["pressmark"]["active"])
            self.assertTrue(list(f.parent.glob("mcp_config.json.pressmark-*.bak")))
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

    def test_cartella_delle_lingue_propria(self):
        # Tesseract in una cartella che chiede l'amministratore: le lingue si copiano in una cartella dell'utente
        import importa
        base = Path(self.tmp.name)
        sistema = base / "tessdata_sistema"
        (sistema / "configs").mkdir(parents=True, exist_ok=True)
        for c in ("eng", "osd"):
            (sistema / f"{c}.traineddata").write_bytes(b"x" * 20000)
        (sistema / "configs" / "tsv").write_text("tessedit_create_tsv 1", encoding="utf-8")
        (sistema / "ScrollView.jar").write_bytes(b"jar")
        utente = base / "utente"

        def installate(exe, modelli=None):
            return {f.stem for f in Path(modelli or sistema).glob("*.traineddata")}

        def cartella(cfg, exe=None):
            return importa.cartella_modelli(cfg) or sistema
        with mock.patch.object(importa, "cerca_tesseract", return_value="tesseract.exe"), \
                mock.patch.object(importa, "lingue_installate", installate), \
                mock.patch.object(importa, "cartella_lingue", cartella), \
                mock.patch.object(importa, "scrivibile", lambda c: Path(c) != sistema), \
                mock.patch.object(importa, "lingue_delle_serie", return_value=set()), \
                mock.patch.object(A.installa.posizioni, "cartella_sistema", return_value=utente):
            s = self.get("/api/lingue")[1]
            self.assertFalse(s["scrivibile"] or s["propria"])
            self.assertEqual(s["cartella_utente"], str(utente / "tessdata"))
            self.assertIn("por", s["proposte"])                          # tutte le lingue di tessdata_best
            self.assertNotIn("eng", s["proposte"])
            codice, r = self.post("/api/lingue/cartella", {})
            self.assertEqual(codice, 200, r)
            dest = utente / "tessdata"
            self.assertEqual(sorted(f.name for f in dest.glob("*.traineddata")), ["eng.traineddata", "osd.traineddata"])
            self.assertTrue((dest / "configs" / "tsv").is_file())
            self.assertFalse((dest / "ScrollView.jar").exists())
            self.assertIn(f"modelli = {dest}", self.config.read_text(encoding="utf-8"))
            self.assertTrue(r["scrivibile"] and r["propria"])
            self.assertEqual(r["cartella"], str(dest))
            self.assertEqual(self.post("/api/lingue/cartella", {})[0], 400)     # già scrivibile: niente da fare

    def test_nomi_delle_lingue(self):
        # ogni codice che l'interfaccia propone o che le serie possono chiedere ha il nome per esteso
        import importa
        codici = set(importa.LINGUE_OCR.values()) | set(importa.ALTRE_LINGUE) | {"osd"}
        self.assertEqual(codici - set(importa.NOMI_LINGUE), set())
        self.assertEqual(importa.NOMI_LINGUE["sqi"], "Albanese")
        self.assertTrue(all(importa.CODICE_LINGUA.match(c) for c in importa.NOMI_LINGUE))
        with mock.patch.object(importa, "cerca_tesseract", return_value=None):
            self.assertEqual(self.get("/api/lingue")[1]["nomi"]["ita"], "Italiano")

    def test_lingue_ocr(self):
        """Lo stato delle lingue; lo scaricamento solo se la cartella dei modelli è scrivibile, e la lingua deve
        poi risultare installata. Né Tesseract né la rete veri: funzioni finte."""
        import importa
        cartella = self.p1.parent.parent / f"tessdata_{self._testMethodName}"
        cartella.mkdir()
        installate = {"eng", "osd"}

        def stato(cfg):
            return {"tesseract": "tesseract.exe", "cartella": str(cartella), "scrivibile": scrivibile[0],
                    "installate": sorted(installate), "richieste": ["osd", "sqi"],
                    "mancanti": sorted({"osd", "sqi"} - installate), "proposte": ["sqi"]}

        def scarica(codice, dove, apri=None, stampa=print):
            if codice == "xyz":
                raise ValueError("tessdata_best non ha un modello «xyz»")
            f = Path(dove) / f"{codice}.traineddata"
            f.write_bytes(b"x" * 20000)
            installate.add(codice)
            return f
        scrivibile = [False]
        with mock.patch.object(A.installa, "stato_lingue", stato), mock.patch.object(importa, "scarica_lingua", scarica):
            codice, s = self.get("/api/lingue")
            self.assertEqual(codice, 200, s)
            self.assertEqual(s["mancanti"], ["sqi"])
            codice, r = self.post("/api/lingue", {"codice": "sqi"})
            self.assertEqual(codice, 400)
            self.assertIn("amministratore", r["errore"])
            self.assertFalse((cartella / "sqi.traineddata").exists())
            scrivibile[0] = True
            codice, r = self.post("/api/lingue", {"codice": "sqi"})
            self.assertEqual(codice, 200, r)
            self.assertEqual((r["scaricata"], r["mancanti"]), ("sqi", []))
            codice, r = self.post("/api/lingue", {"codice": "xyz"})
            self.assertEqual(codice, 400)
            self.assertIn("xyz", r["errore"])


def sezione(testo, titolo):
    """Il testo di una sezione della risposta, dal suo titolo al successivo."""
    inizio = testo.index(titolo)
    fine = testo.find("\n## ", inizio + 1)
    return testo[inizio:fine if fine > 0 else None]


if __name__ == "__main__":
    unittest.main()

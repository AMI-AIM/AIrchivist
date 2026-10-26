"""
Test del cambio di modello a metà progetto (lavoro 26) sulla ricerca completa (ricerca.py -> classifica.py ->
sintesi.py), con un servizio finto in locale e un progetto temporaneo con due numeri finti del Renmin Ribao:
- una ricerca interrotta riprende con il profilo con cui era partita, anche dopo un cambio di scelta;
- finita la ricerca, la successiva usa il profilo scelto adesso, e i passaggi già letti vengono dall'archivio;
- --rileggi-modello rimanda al modello attuale i passaggi letti da un altro (l'archivio conserva le due letture);
- la sezione «Limiti» dice quali modelli hanno letto, quanti passaggi ciascuno e se sono misurati.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
PROVA = Path(__file__).resolve().parent / "test_project"
sys.path.insert(0, str(MOTORE))
import ricerca as R  # noqa: E402
import sintesi as S  # noqa: E402
from llm import VARIABILE_FISSATI  # noqa: E402
from progetto import VARIABILE, leggi_config  # noqa: E402

CHIAVE = "chiave-di-prova"
INTESTAZIONE = """[DOC_ID: RMB-{data}]
[SERIES: Renmin Ribao]
[DOC_TYPE: newspaper]
[LANG: zh]
[YEAR: {anno}]
[DATE: {data}]
[FULL_CITATION: Renmin Ribao, {data}]

"""
TESTI = {"1980-04-15": "第1版() 专栏： 贝林格同志率意共中央代表团抵京 新华社北京四月十四日电 由总书记贝林格率领的"
                       "意大利共产党中央代表团今天晚间乘飞机到达北京。",
         "1980-04-16": "第1版() 专栏： 华国锋会见贝林格 新华社北京四月十五日电 华国锋今天会见了意大利共产党总书记贝林格。"}
SCHEDA = "[Enrico Berlinguer]\ntipo = persona\nvarianti = 贝林格\nnote = Segretario del Partito comunista italiano.\n"


class Servizio(BaseHTTPRequestHandler):
    """Servizio compatibile OpenAI che risponde a smistamento, analisi e sintesi; con «rifiuta» rifiuta la chiave."""
    rifiuta = False
    modelli = []

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
        self._rispondi(200, {"data": []})

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if Servizio.rifiuta:
            return self._rispondi(401, {"error": "chiave rifiutata"})
        Servizio.modelli.append(corpo["model"])
        testo = corpo["messages"][-1]["content"]
        if '"risultati"' in testo:
            r = {"risultati": [{"n": k, "pertinente": "sì", "motivazione": "è lui"} for k in range(1, 7)]}
        elif "dati_espliciti" in testo:
            r = {"dati_espliciti": [{"testo": "Berlinguer arriva a Pechino.", "rif": [1]}]}
        elif "risposta_finale" in testo:
            r = {"inferenze": [], "problemi_interpretativi": [], "risposta_finale": "Visita in Cina [1]."}
        else:
            r = {"pertinente": "sì", "motivazione": "è lui", "tipo_menzione": "delegazione/visita",
                 "traduzione_it": "Berlinguer a Pechino.", "sintesi_it": "Visita.", "tono": "neutro",
                 "nuove_varianti": [], "altri_nominati": [], "ruolo_entita": "", "evento": ""}
        self._rispondi(200, {"model": corpo["model"],
                             "choices": [{"message": {"content": json.dumps(r, ensure_ascii=False)}}]})


class CambioDiModello(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Servizio)
        url = f"http://127.0.0.1:{cls.server.server_address[1]}/v1"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.radice = base / "progetto"
        shutil.copytree(PROVA, cls.radice)
        rr = cls.radice / "data" / "riviste" / "renmin_ribao"
        rr.mkdir(parents=True)
        for data, testo in TESTI.items():
            (rr / f"{data}.txt").write_text(INTESTAZIONE.format(data=data, anno=data[:4]) + testo + "\n",
                                            encoding="utf-8")
        (cls.radice / "glossary" / "entities.ini").write_text(SCHEDA, encoding="utf-8")
        cls.profili = base / "models.ini"
        cls.profili.write_text("".join(f"[{n}]\nservizio = openai\nurl = {url}\nmodello = modello-{n}\n"
                                       f"chiave_env = AIRCHIVIST_PROVA\n\n" for n in ("a", "b")), encoding="utf-8")
        cls.config = base / "config.ini"
        cls.env = {k: v for k, v in os.environ.items() if k != VARIABILE_FISSATI}
        cls.env.update({VARIABILE: str(cls.radice), "PYTHONIOENCODING": "utf-8", "AIRCHIVIST_PROVA": CHIAVE})
        cls.cart = cls.radice / "results" / "searches" / "enrico_berlinguer"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def scegli(self, profilo):
        self.config.write_text(f"[modello]\nfile_profili = {self.profili.as_posix()}\nprofilo = {profilo}\n"
                               "[estrazione]\nforme_sicure = no\n", encoding="utf-8")

    def ricerca(self, *opzioni):
        r = subprocess.run([sys.executable, "ricerca.py", "Enrico Berlinguer", "--config", str(self.config),
                            *opzioni], cwd=MOTORE, env=self.env, capture_output=True, text=True, encoding="utf-8")
        return r.returncode, r.stdout + r.stderr

    def letture(self):
        """Ultima lettura di ogni passaggio (classificati.jsonl: vale l'ultima riga)."""
        righe = (self.cart / "classificati.jsonl").read_text(encoding="utf-8").splitlines()
        return {c["id"]: c["analisi"] for c in map(json.loads, righe)}

    def modelli_json(self):
        return json.loads((self.cart / "modelli.json").read_text(encoding="utf-8"))

    def test_cambio_a_meta_progetto(self):
        # 1. la ricerca parte con «a» e si interrompe (chiave rifiutata): resta «in corso» con il profilo «a»
        self.scegli("a")
        Servizio.rifiuta = True
        codice, uscita = self.ricerca()
        self.assertNotEqual(codice, 0, uscita)
        self.assertEqual(self.modelli_json()["stato"], "in corso")
        self.assertEqual(self.modelli_json()["ruoli"]["analisi"]["nome"], "a")
        self.assertNotIn(CHIAVE, (self.cart / "modelli.json").read_text(encoding="utf-8"))

        # 2. nel frattempo si sceglie «b»; rilanciata, la ricerca riprende con «a», con cui era partita
        Servizio.rifiuta = False
        self.scegli("b")
        Servizio.modelli.clear()
        codice, uscita = self.ricerca()
        self.assertEqual(codice, 0, uscita)
        self.assertIn("Ricerca ripresa con i profili con cui era partita", uscita)
        self.assertIn("--usa-modello-attuale", uscita)
        self.assertEqual(set(Servizio.modelli), {"modello-a"})
        letture = self.letture()
        self.assertEqual(len(letture), 2)
        self.assertEqual({a["modello_analisi"] for a in letture.values()}, {"modello-a"})
        self.assertEqual(self.modelli_json()["stato"], "completata")
        risposta = (self.cart / "risposta.md").read_text(encoding="utf-8")
        limiti = risposta[risposta.index("## 5."):risposta.index("## 6.")]
        self.assertIn("letti dal modello modello-a: non misurato su queste fonti", limiti)

        # 3. ricerca nuova: usa «b»; i passaggi già letti non si rileggono, il modello scrive solo la sintesi
        Servizio.modelli.clear()
        codice, uscita = self.ricerca()
        self.assertEqual(codice, 0, uscita)
        self.assertNotIn("ripresa", uscita)
        self.assertEqual(self.modelli_json()["ruoli"]["sintesi"]["nome"], "b")
        self.assertIn("Nessun passaggio nuovo da leggere", uscita)
        self.assertEqual(set(Servizio.modelli), {"modello-b"})
        self.assertEqual({a["modello_analisi"] for a in self.letture().values()}, {"modello-a"})

        # 4. --rileggi-modello: i passaggi di «modello-a» tornano al modello attuale («b»)
        codice, uscita = self.ricerca("--rileggi-modello", "modello-a")
        self.assertEqual(codice, 0, uscita)
        self.assertIn("Da rileggere perché letti da «modello-a»: 2 passaggi (modello-a)", uscita)
        self.assertEqual({a["modello_analisi"] for a in self.letture().values()}, {"modello-b"})
        archivio = [json.loads(r) for r in (self.radice / "results" / "archive" / "readings.jsonl")
                    .read_text(encoding="utf-8").splitlines()]
        self.assertEqual(sorted(v["analisi"]["modello_analisi"] for v in archivio),
                         ["modello-a", "modello-a", "modello-b", "modello-b"])      # la vecchia resta nella storia
        risposta = (self.cart / "risposta.md").read_text(encoding="utf-8")
        self.assertIn("letti dal modello modello-b", risposta)
        self.assertNotIn("modello-a", risposta[risposta.index("## 5."):risposta.index("## 6.")])

        # 5. nessun passaggio di «modello-a» rimasto: niente da rileggere
        codice, uscita = self.ricerca("--rileggi-modello", "modello-a")
        self.assertEqual(codice, 0, uscita)
        self.assertIn("Da rileggere perché letti da «modello-a»: 0 passaggi", uscita)


class ProfiliFissati(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        (self.tmp / "models.ini").write_text("[a]\nservizio = ollama\nmodello = m-a\n\n[b]\nservizio = ollama\n"
                                             "modello = m-b\n", encoding="utf-8")
        self.config = self.tmp / "config.ini"
        self.cart = self.tmp / "ricerca"
        self.cart.mkdir()
        self.env = mock.patch.dict(os.environ, {})
        self.env.start()
        os.environ.pop(VARIABILE, None)
        os.environ.pop(VARIABILE_FISSATI, None)

    def tearDown(self):
        self.env.stop()

    def scegli(self, profilo):
        self.config.write_text(f"[modello]\nfile_profili = {(self.tmp / 'models.ini').as_posix()}\n"
                               f"profilo = {profilo}\n", encoding="utf-8")
        return leggi_config(self.config)

    def test_ripresa_e_modello_attuale(self):
        from llm import LLM
        self.assertEqual(R.fissa_profili(self.cart, self.scegli("a"))["analisi"], "a")
        cfg = self.scegli("b")
        self.assertEqual(R.fissa_profili(self.cart, cfg)["analisi"], "a")              # ripresa
        self.assertEqual(LLM(cfg, "analisi").modello, "m-a")
        self.assertEqual(R.fissa_profili(self.cart, cfg, usa_attuale=True)["analisi"], "b")
        self.assertEqual(LLM(cfg, "analisi").modello, "m-b")

    def test_profilo_tolto_dopo_l_avvio(self):
        from llm import LLM
        R.fissa_profili(self.cart, self.scegli("a"))
        (self.tmp / "models.ini").write_text("[b]\nservizio = ollama\nmodello = m-b\n", encoding="utf-8")
        cfg = self.scegli("b")
        R.fissa_profili(self.cart, cfg)
        self.assertEqual(LLM(cfg, "analisi").modello, "m-a")           # le voci sono conservate nella ricerca


class Limiti(unittest.TestCase):
    def lettura(self, modello):
        return {"analisi": {"pertinente": "sì", "traduzione_it": "t", "modello_smistamento": modello,
                            "modello_analisi": modello}}

    def test_piu_modelli_e_misure(self):
        voci = [self.lettura("groq/qwen/qwen3.8-27b")] * 3 + [self.lettura("qwen3.5:9b")]
        righe = S.righe_modelli_limiti(voci, {"qwen/qwen3.8-27b"})
        self.assertEqual(len(righe), 1)
        self.assertIn("modelli diversi", righe[0])
        self.assertIn("groq/qwen/qwen3.8-27b, 3 passaggi, misurato su passaggi verificati", righe[0])
        self.assertIn("qwen3.5:9b, 1 passaggi, non misurato", righe[0])

    def test_solo_sessione_niente_riga(self):
        self.assertEqual(S.righe_modelli_limiti([{"analisi": {"pertinente": "sì", "classificato_da": "lettura manuale"}}],
                                                set()), [])

    def test_misure_dalle_prove(self):
        ris = Path(tempfile.mkdtemp())
        d = ris / "evaluation" / "riferimento_1"
        d.mkdir(parents=True)
        (d / "modelli_20261026_1200.jsonl").write_text(
            json.dumps({"modello": "x", "risposto": "groq/a, groq/b", "letti": 5, "misure": {"n": 5}}) + "\n" +
            json.dumps({"modello": "y", "risposto": "groq/c", "letti": 0, "misure": None}) + "\n", encoding="utf-8")
        self.assertEqual(S.modelli_misurati(ris), {"groq/a", "groq/b"})


if __name__ == "__main__":
    unittest.main()

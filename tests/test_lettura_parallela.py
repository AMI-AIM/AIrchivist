"""
Test della lettura che non si blocca e va più veloce (lavoro 40, obiettivi C e G della roadmap della prova del flusso):
- C1: un'attesa lunga si annuncia; dopo «ferma_dopo» secondi senza risposte utili la chiamata si ferma (ServizioFermo);
- C3: il registro della ricerca (registro.txt) riceve ogni riga con l'ora, anche quella dei passi;
- G2: l'analisi va a lotti (più passaggi per richiesta), con ritorno alla lettura uno per uno per le voci mancanti;
  gli esiti dello smistamento restano in smistamento.jsonl e un'interruzione dell'analisi non lo fa ripetere;
- G3: più richieste alla volta, con la pausa tra le richieste rispettata da tutti i thread.
Senza modelli: un servizio finto in locale.
"""
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import closing, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
PROVA = Path(__file__).resolve().parent / "test_project"
sys.path.insert(0, str(MOTORE))
import classifica as K  # noqa: E402
import llm as L  # noqa: E402
import ricerca as R  # noqa: E402
from llm import VARIABILE_FISSATI  # noqa: E402
from progetto import VARIABILE  # noqa: E402

CHIAVE = "chiave-di-prova"
INTESTAZIONE = ("[DOC_ID: RMB-{data}]\n[SERIES: Renmin Ribao]\n[DOC_TYPE: newspaper]\n[LANG: zh]\n[YEAR: 1980]\n"
                "[DATE: {data}]\n[FULL_CITATION: Renmin Ribao, {data}]\n\n")
DATE = ["1980-04-1%d" % k for k in range(1, 6)]
SCHEDA = "[Enrico Berlinguer]\ntipo = persona\nvarianti = 贝林格\nnote = Segretario del Partito comunista italiano.\n"
ANALISI = {"tipo_menzione": "delegazione/visita", "traduzione_it": "Berlinguer a Pechino.", "sintesi_it": "Visita.",
           "tono": "neutro", "nuove_varianti": [], "altri_nominati": [], "ruolo_entita": "", "evento": "visita"}


class Servizio(BaseHTTPRequestHandler):
    """Servizio compatibile OpenAI: prova del collegamento, smistamento e analisi a lotti o uno per uno, sintesi.
    Con «rifiuta_analisi» rifiuta la chiave alle sole richieste di analisi."""
    rifiuta_analisi = False
    richieste = []

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
        testo = corpo["messages"][-1]["content"]
        n = int((re.search(r"Seguono (\d+) passaggi", testo) or [0, 1])[1])
        if "Prova di collegamento" in testo:
            tipo, r = "prova", "ok"
        elif "Compiti, per OGNI passaggio" in testo:
            tipo, r = "analisi_lotto", {"risultati": [dict(ANALISI, n=k) for k in range(1, n + 1)]}
        elif "Compiti:" in testo:
            tipo, r = "analisi", ANALISI
        elif '"risultati"' in testo:
            tipo, r = "smistamento_lotto", {"risultati": [{"n": k, "pertinente": "sì", "motivazione": "è lui"}
                                                          for k in range(1, n + 1)]}
        elif "dati_espliciti" in testo:
            tipo, r = "sintesi", {"dati_espliciti": [{"testo": "Berlinguer arriva a Pechino.", "rif": [1]}]}
        elif "risposta_finale" in testo:
            tipo, r = "sintesi", {"inferenze": [], "problemi_interpretativi": [], "risposta_finale": "Visita [1]."}
        else:
            tipo, r = "smistamento", {"pertinente": "sì", "motivazione": "è lui"}
        Servizio.richieste.append(tipo)
        if tipo.startswith("analisi") and Servizio.rifiuta_analisi:
            return self._rispondi(401, {"error": "chiave rifiutata"})
        contenuto = r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)
        self._rispondi(200, {"model": corpo["model"], "choices": [{"message": {"content": contenuto}}]})


class RicercaALotti(unittest.TestCase):
    """Cinque passaggi: una richiesta di smistamento, due di analisi (lotti di 3), in parallelo; registro della
    ricerca; ripresa dopo un'interruzione dell'analisi senza ripetere lo smistamento."""
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
        for data in DATE:
            (rr / f"{data}.txt").write_text(INTESTAZIONE.format(data=data) + "第1版() 华国锋今天会见了意大利共产党"
                                            "总书记贝林格。\n", encoding="utf-8")
        (cls.radice / "glossary" / "entities.ini").write_text(SCHEDA, encoding="utf-8")
        (base / "models.ini").write_text(f"[finto]\nservizio = openai\nurl = {url}\nmodello = finto\n"
                                         "chiave_env = PRESSMARK_PROVA\nparalleli = 2\n", encoding="utf-8")
        cls.config = base / "config.ini"
        cls.config.write_text(f"[modello]\nfile_profili = {(base / 'models.ini').as_posix()}\nprofilo = finto\n"
                              "[estrazione]\nforme_sicure = no\nlotto_smistamento = 6\nlotto_analisi = 3\n",
                              encoding="utf-8")
        cls.env = {k: v for k, v in os.environ.items() if k != VARIABILE_FISSATI}
        cls.env.update({VARIABILE: str(cls.radice), "PYTHONIOENCODING": "utf-8", "PRESSMARK_PROVA": CHIAVE})
        cls.cart = cls.radice / "results" / "searches" / "enrico_berlinguer"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def ricerca(self):
        Servizio.richieste.clear()
        r = subprocess.run([sys.executable, "ricerca.py", "Enrico Berlinguer", "--config", str(self.config)],
                           cwd=MOTORE, env=self.env, capture_output=True, text=True, encoding="utf-8")
        return r.returncode, r.stdout + r.stderr

    def test_interruzione_e_ripresa(self):
        # 1. l'analisi non riesce (chiave rifiutata): lo smistamento, una richiesta per cinque passaggi, resta salvato
        Servizio.rifiuta_analisi = True
        codice, uscita = self.ricerca()
        self.assertEqual(codice, 4, uscita)
        self.assertEqual(Servizio.richieste.count("prova"), 1)
        self.assertEqual(Servizio.richieste.count("smistamento_lotto"), 1)
        self.assertEqual(len((self.cart / "smistamento.jsonl").read_text(encoding="utf-8").splitlines()), 5)
        registro = (self.cart / "registro.txt").read_text(encoding="utf-8")
        self.assertIn("== 2/3 Smistamento e analisi dei passaggi", registro)
        self.assertIn("durata:", registro)
        self.assertRegex(registro, r"\d\d/\d\d \d\d:\d\d:\d\d   smistamento 1/1: 5 pertinenti")

        # 2. rilanciata: niente smistamento, l'analisi va a lotti (due richieste per cinque passaggi)
        Servizio.rifiuta_analisi = False
        codice, uscita = self.ricerca()
        self.assertEqual(codice, 0, uscita)
        self.assertIn("già smistati in un lancio precedente: 5", uscita)
        self.assertNotIn("smistamento_lotto", Servizio.richieste)
        self.assertNotIn("smistamento", Servizio.richieste)
        self.assertEqual(Servizio.richieste.count("analisi_lotto"), 2, Servizio.richieste)
        self.assertNotIn("analisi", Servizio.richieste)
        righe = (self.cart / "classificati.jsonl").read_text(encoding="utf-8").splitlines()
        letture = {c["id"]: c["analisi"] for c in map(json.loads, righe)}
        self.assertEqual(len(letture), 5)
        self.assertEqual({a["traduzione_it"] for a in letture.values()}, {"Berlinguer a Pechino."})
        self.assertEqual(sorted(a.get("lotto") for a in letture.values()), [2, 2, 3, 3, 3])
        self.assertIn("analisi: 2 richieste", uscita)


class LottiDiAnalisi(unittest.TestCase):
    def rec(self, k, entita="E", lungo=100):
        t = "x" * lungo + f"⟦nome{k}⟧. Fine."
        return {"id": f"p{k}", "entita": entita, "fonte": "F", "data": "1964-07-04", "file": "f.txt", "riga": k,
                "passaggio": t.replace("⟦", "").replace("⟧", ""), "passaggio_evidenziato": t}

    def test_gruppi(self):
        recs = [self.rec(k) for k in range(5)] + [self.rec(9, "Altra")]
        self.assertEqual([len(g) for g in K.lotti_analisi(recs, 3, 100000)], [3, 2, 1])   # l'entità non si mescola
        self.assertEqual([len(g) for g in K.lotti_analisi(recs, 3, 250)], [1, 1, 1, 1, 1, 1])  # limite di caratteri

    def test_voci_mancanti_lette_uno_per_uno(self):
        class Finto:
            max_token, ultimo_modello, chiamate = 4000, "finto", []

            def json(self, sistema, utente, schema, tentativi_forma=3, max_token=None):
                self.chiamate.append((schema is K.SCHEMA_ANALISI_LOTTO, tentativi_forma, max_token))
                if schema is K.SCHEMA_ANALISI_LOTTO:       # la terza voce manca della sintesi
                    return {"risultati": [dict(ANALISI, n=1), dict(ANALISI, n=2), dict(ANALISI, n=3, sintesi_it="")]}
                return dict(ANALISI, sintesi_it="letto da solo")
        recs = [self.rec(k) for k in range(3)]
        esiti = {r["id"]: ("sì", "è lui", "finto") for r in recs}
        schede = {"E": {"varianti": [], "note": ""}}
        with mock.patch.object(K, "pagina", return_value=""):
            letture, errori = K.analizza_lotto(recs, schede, esiti, Finto(), 0, [])
        self.assertEqual(errori, [])
        self.assertEqual([letture[f"p{k}"]["sintesi_it"] for k in range(3)], ["Visita.", "Visita.", "letto da solo"])
        self.assertEqual(letture["p0"]["lotto"], 3)
        self.assertNotIn("lotto", letture["p2"])
        self.assertEqual(Finto.chiamate[0], (True, 1, 8000))        # lotto: un tentativo, risposta più lunga
        self.assertTrue(all(c[0] is False for c in Finto.chiamate[1:]))
        self.assertTrue(all(letture[f"p{k}"]["citazione_verificata"] for k in range(3)))

    def test_prompt_del_lotto(self):
        recs = [self.rec(k) for k in range(2)]
        p = K.prompt_analisi_lotto(recs, {"note": ""}, [K.frase_chiave(r) for r in recs])
        self.assertIn("Seguono 2 passaggi", p)
        self.assertIn("[2] Fonte: F (data: 1964-07-04)", p)
        self.assertIn(K.REGOLA_DISCORSO, p)                 # stesse regole dell'analisi di un passaggio
        self.assertIn(K.REGOLA_DISCORSO, K.prompt_analisi(recs[0], {"note": ""}, "frase"))


class Parallelo(unittest.TestCase):
    def test_richieste_contemporanee(self):
        inizio = time.time()
        risultati = list(K.in_parallelo([0.3, 0.3, 0.3], lambda s: time.sleep(s) or s, 3))
        self.assertLess(time.time() - inizio, 0.8)
        self.assertEqual([r[1] for r in risultati], [0.3] * 3)

    def test_errori_e_interruzione(self):
        partiti = []

        def lavoro(k):
            partiti.append(k)
            time.sleep(0.1)
            if k == 0:
                raise L.ErroreModello("errore")
            return k
        with closing(K.in_parallelo(range(6), lavoro, 1)) as risultati:
            primo = next(risultati)
        self.assertEqual((primo[0], primo[1], str(primo[2])), (0, None, "errore"))
        self.assertLessEqual(len(partiti), 2)              # i lavori non partiti si annullano

    def test_pausa_condivisa(self):
        m = L.LLM.__new__(L.LLM)
        m._blocco, m.pausa, m._ultima = threading.Lock(), 0.2, 0.0
        attese = []
        fili = [threading.Thread(target=lambda: attese.append(m._turno())) for _ in range(3)]
        for f in fili:
            f.start()
        for f in fili:
            f.join()
        attese.sort()
        self.assertLess(attese[0], 0.05)
        self.assertGreaterEqual(attese[1], 0.15)
        self.assertGreaterEqual(attese[2], 0.35)


class Attese(unittest.TestCase):
    def llm(self, risposta, **voci):
        m = L.LLM.__new__(L.LLM)
        m._blocco, m._locale = threading.Lock(), threading.local()
        m.backend, m.pausa, m._ultima, m.max_token, m.timeout, m.modello = "openai", 0, 0.0, 100, 60, "finto"
        m.richieste = m.secondi_modello = m.secondi_attesa = 0
        m._openai = risposta
        for k, v in voci.items():
            setattr(m, k, v)
        return m

    def test_attesa_annunciata(self):
        m = self.llm(lambda s, u, sc, mt: time.sleep(1.5) or "ok", avviso_dopo=1, ferma_dopo=600)
        uscita = io.StringIO()
        with redirect_stdout(uscita):
            self.assertEqual(m._chiama("s", "u", None), "ok")
        self.assertIn("nessuna risposta da 0 min (attendo la risposta del modello)", uscita.getvalue())

    def test_servizio_fermo(self):
        def guasto(s, u, sc, mt):
            raise OSError("collegamento chiuso")
        m = self.llm(guasto, avviso_dopo=0, ferma_dopo=0)
        with mock.patch.object(L.time, "sleep"), redirect_stdout(io.StringIO()):
            with self.assertRaises(L.ServizioFermo) as e:
                m._chiama("s", "u", None)
        self.assertIn("rilancia lo stesso comando", str(e.exception))
        self.assertEqual(m.richieste, 1)                    # nessun nuovo tentativo dopo il limite
        self.assertFalse(K.PERMANENTE.search(str(e.exception)))     # si riprova più tardi (codice 3)

    def test_valori_del_profilo(self):
        from configparser import ConfigParser
        cfg = ConfigParser()
        cfg.read_string("[modello]\ntimeout = 300\n")
        with mock.patch.object(L, "profilo", return_value=("r", {"servizio": "router", "url": "http://x/v1",
                                                                  "modello": "auto"})):
            r = L.LLM(cfg, "smistamento")
            a = L.LLM(cfg, "sintesi")
        self.assertEqual((r.timeout, r.paralleli, r.avviso_dopo, r.ferma_dopo), (120, 3, 120, 600))
        self.assertEqual(a.timeout, 300)            # risposte lunghe: il timeout breve del router no
        with mock.patch.object(L, "profilo", return_value=("o", {"servizio": "openai", "url": "http://x/v1",
                                                                  "modello": "m", "paralleli": "2"})):
            o = L.LLM(cfg, "analisi")
        self.assertEqual((o.timeout, o.paralleli), (300, 2))


class RegistroDellaRicerca(unittest.TestCase):
    def test_ora_a_ogni_riga(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "registro.txt"
            schermo = io.StringIO()
            r = R.Registro(f, schermo)
            r.write("prima ")
            r.write("riga\nseconda riga\n")
            r.write("terza\n")
            r.f.close()
            righe = f.read_text(encoding="utf-8").splitlines()
        self.assertEqual(schermo.getvalue(), "prima riga\nseconda riga\nterza\n")
        self.assertEqual(len(righe), 3)
        self.assertTrue(all(re.match(r"\d\d/\d\d \d\d:\d\d:\d\d ", x) for x in righe))
        self.assertTrue(righe[0].endswith(" prima riga"))


if __name__ == "__main__":
    unittest.main()

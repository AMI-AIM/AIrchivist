"""
Test dei profili di modello (lavoro 26: llm.py, installa.py modello) con un servizio finto in locale: profilo
scelto per tutti i ruoli o per uno, configurazione precedente ancora valida, cambio riuscito e annotato, cambio
rifiutato per collegamento fallito (resta il precedente), scelta nel project.ini, procedura guidata, togli,
conversione della configurazione precedente, copia per le prove dei modelli (valuta.py). Nessun servizio vero.
"""
import argparse
import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOTORE))
import installa as I  # noqa: E402
import llm as L  # noqa: E402
from progetto import VARIABILE, leggi_config  # noqa: E402

CHIAVE = "chiave-di-prova"


class Servizio(BaseHTTPRequestHandler):
    """Servizio compatibile OpenAI: /v1 risponde, /rotto/v1 dice che il modello non c'è; chiave controllata."""
    richieste = []

    def log_message(self, *a):
        pass

    def _rispondi(self, codice, dati):
        corpo = json.dumps(dati).encode("utf-8")
        self.send_response(codice)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def _autorizzato(self):
        return self.headers.get("Authorization") == f"Bearer {CHIAVE}"

    def do_GET(self):
        if not self._autorizzato():
            return self._rispondi(401, {"error": "chiave"})
        self._rispondi(200, {"data": [{"id": "finto-1"}]})

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Servizio.richieste.append(corpo)
        if not self._autorizzato():
            return self._rispondi(401, {"error": "chiave"})
        if self.path.startswith("/rotto"):
            return self._rispondi(404, {"error": "modello inesistente"})
        self._rispondi(200, {"model": corpo["model"], "choices": [{"message": {"content": "ok"}}]})


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Servizio)
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.progetto = self.tmp / "progetto"
        (self.progetto / "system").mkdir(parents=True)
        (self.progetto / "project.ini").write_text("[progetto]\nnome = prova\n", encoding="utf-8")
        self.config = self.tmp / "config.ini"
        self.profili = self.tmp / "models.ini"
        self.scrivi_config("profilo = buono\n")
        self.profili.write_text(
            "# profili di prova\n"
            f"[buono]\nservizio = openai\nurl = {self.url}/v1\nmodello = finto-1\nchiave_env = AIRCHIVIST_PROVA\n"
            "max_token = 1000\n\n"
            "# commento del profilo seguente\n"
            f"[secondo]\nservizio = openai\nurl = {self.url}/v1\nmodello = finto-2\nchiave_env = AIRCHIVIST_PROVA\n"
            "max_token_sintesi = 9000\n\n"
            f"[rotto]\nservizio = openai\nurl = {self.url}/rotto/v1\nmodello = assente\nchiave_env = AIRCHIVIST_PROVA\n\n"
            "[spento]\nservizio = ollama\nurl = http://127.0.0.1:9\nmodello = qwen3.5:9b\n", encoding="utf-8")
        self.env = mock.patch.dict(os.environ, {"AIRCHIVIST_PROVA": CHIAVE})
        self.env.start()
        os.environ.pop(VARIABILE, None)
        self.patch_config = mock.patch.object(I, "FILE_CONFIG", self.config)
        self.patch_config.start()
        self.righe = []

    def tearDown(self):
        self.patch_config.stop()
        self.env.stop()

    def scrivi_config(self, voci_modello):
        self.config.write_text(
            "# configurazione di prova\n"
            f"[progetto]\ncartella = {self.progetto.as_posix()}\n\n"
            "[modello]\n# commento da conservare\n"
            f"file_profili = {self.profili.as_posix()}\nmax_token = 4000\nmax_token_sintesi = 8000\n"
            f"{voci_modello}\n", encoding="utf-8")

    def cfg(self):
        return leggi_config(self.config)

    def esegui(self, azione, nome=None, chiedi=None, **kw):
        args = argparse.Namespace(azione=azione, nome=nome, ruolo=kw.pop("ruolo", None),
                                  progetto=kw.pop("progetto", False), si=kw.pop("si", False))
        if chiedi is not None:
            risposte = iter(chiedi)
            kw["chiedi"] = lambda domanda: next(risposte)
        return I.cmd_modello(args, stampa=self.righe.append, **kw)

    def uscita(self):
        return "\n".join(self.righe)


class Lettura(Base):
    def test_profilo_per_tutti_i_ruoli(self):
        llm = L.LLM(self.cfg(), "sintesi")
        self.assertEqual((llm.profilo, llm.modello, llm.chiave), ("buono", "finto-1", CHIAVE))
        self.assertEqual(llm.max_token, 1000)          # il profilo prevale su [modello]

    def test_profilo_per_un_ruolo(self):
        self.scrivi_config("profilo = buono\nsintesi = secondo\n")
        self.assertEqual(L.profili_attivi(self.cfg()),
                         {"smistamento": "buono", "analisi": "buono", "sintesi": "secondo"})
        self.assertEqual(L.LLM(self.cfg(), "sintesi").max_token, 9000)
        self.assertEqual(L.LLM(self.cfg(), "analisi", "secondo").max_token, 4000)   # da [modello]

    def test_profilo_inesistente(self):
        self.scrivi_config("profilo = nessuno\n")
        with self.assertRaises(L.ErroreModello) as e:
            L.LLM(self.cfg(), "analisi")
        self.assertIn("installa.py modello", str(e.exception))

    def test_configurazione_precedente(self):
        self.scrivi_config(f"backend = router\n[router]\nurl = {self.url}/v1\nchiave_env = AIRCHIVIST_PROVA\n"
                           "modello_smistamento = a\nmodello_analisi = b\nmodello_sintesi = b\n"
                           "modelli_ammessi = finto\n")
        llm = L.LLM(self.cfg(), "smistamento")
        self.assertEqual((llm.profilo, llm.sezione, llm.modello, llm.ammessi),
                         ("config.ini [router]", "router", "a", ["finto"]))
        self.assertEqual(llm.max_token, 4000)

    def test_chiamata(self):
        self.assertEqual(L.LLM(self.cfg(), "analisi").testo("s", "u"), "ok")


class Usa(Base):
    def test_cambio_riuscito(self):
        self.assertEqual(self.esegui("usa", "secondo"), 0)
        self.assertEqual(L.profili_attivi(self.cfg())["analisi"], "secondo")
        testo = self.config.read_text(encoding="utf-8")
        self.assertIn("# commento da conservare", testo)
        self.assertEqual(testo.count("profilo ="), 1)
        registro = (self.progetto / "system" / "model_changes.csv").read_bytes()
        self.assertTrue(registro.startswith(b"\xef\xbb\xbf"))
        self.assertIn(b"\r\n", registro)
        self.assertEqual(registro.decode("utf-8-sig").count("buono,secondo"), 3)

    def test_cambio_rifiutato_resta_il_precedente(self):
        prima = self.config.read_bytes()
        for nome in ("rotto", "spento"):
            self.assertEqual(self.esegui("usa", nome), 1)
        self.assertEqual(self.config.read_bytes(), prima)
        self.assertIn("non trova il modello", self.uscita())
        self.assertIn("Ollama non risponde", self.uscita())
        self.assertIn("Restano in uso", self.uscita())
        self.assertFalse((self.progetto / "system" / "model_changes.csv").exists())

    def test_chiave_rifiutata(self):
        os.environ["AIRCHIVIST_PROVA"] = "sbagliata"
        self.assertEqual(self.esegui("usa", "secondo"), 1)
        self.assertIn("rifiuta la chiave", self.uscita())

    def test_solo_un_ruolo(self):
        self.assertEqual(self.esegui("usa", "secondo", ruolo=["sintesi"]), 0)
        self.assertEqual(L.profili_attivi(self.cfg()),
                         {"smistamento": "buono", "analisi": "buono", "sintesi": "secondo"})
        # poi di nuovo uno per tutti: la voce del ruolo sparisce
        self.assertEqual(self.esegui("usa", "buono"), 0)
        self.assertNotIn("\nsintesi =", self.config.read_text(encoding="utf-8"))

    def test_progetto_prevale(self):
        self.assertEqual(self.esegui("usa", "secondo", progetto=True), 0)
        self.assertIn("profilo = secondo", (self.progetto / "project.ini").read_text(encoding="utf-8"))
        self.assertIn("profilo = buono", self.config.read_text(encoding="utf-8"))
        self.righe.clear()
        self.assertEqual(self.esegui("usa", "buono"), 0)       # in config.ini, ma il progetto prevale
        self.assertIn("ATTENZIONE", self.uscita())
        self.assertEqual(L.profili_attivi(self.cfg())["analisi"], "secondo")

    def test_prova_ed_elenca(self):
        self.assertEqual(self.esegui("prova", "buono"), 0)
        self.assertEqual(self.esegui("prova", "inesistente"), 1)
        self.righe.clear()
        self.esegui("elenca")
        self.assertIn("* buono", self.uscita())
        self.assertIn("  rotto", self.uscita())


class Nuovo(Base):
    def test_procedura_guidata(self):
        salvate = {}
        os.environ.pop("AIRCHIVIST_NUOVA", None)
        risposte = ["2", "4", f"{self.url}/v1", "AIRCHIVIST_NUOVA", "finto-3", "", "s", "s"]
        codice = self.esegui("nuovo", chiedi=risposte, segreto=lambda d: CHIAVE,
                             salva=lambda n, v, s: salvate.update({n: v}))
        self.assertEqual(codice, 0, self.uscita())
        self.assertEqual(salvate, {"AIRCHIVIST_NUOVA": CHIAVE})
        profili = L.leggi_profili(self.cfg())
        self.assertEqual(profili["locale-finto-3"]["chiave_env"], "AIRCHIVIST_NUOVA")
        self.assertNotIn(CHIAVE, self.profili.read_text(encoding="utf-8"))
        self.assertEqual(L.profili_attivi(self.cfg())["analisi"], "locale-finto-3")

    def test_servizio_noto_chiave_prima_e_modelli_dal_servizio(self):
        # il modello proposto dal codice non c'è più nel servizio: si sceglie da quelli che il servizio elenca
        noto = [("Finto", f"{self.url}/v1", "AIRCHIVIST_NOTO", "sparito", "0", "https://esempio/chiavi")]
        os.environ.pop("AIRCHIVIST_NOTO", None)
        salvate = {}
        with mock.patch.object(I, "SERVIZI_CHIAVE", noto):
            codice = self.esegui("nuovo", chiedi=["2", "1", "s", "1", "", "s"], segreto=lambda d: CHIAVE,
                                 salva=lambda n, v, s: salvate.update({n: v}))
        self.assertEqual(codice, 0, self.uscita())
        self.assertEqual(salvate, {"AIRCHIVIST_NOTO": CHIAVE})
        self.assertNotIn("sparito", self.uscita())
        self.assertIn("finto-1", self.uscita())
        nome = L.profili_attivi(self.cfg())["analisi"]
        self.assertEqual(L.leggi_profili(self.cfg())[nome]["modello"], "finto-1")

    def test_modello_senza_chiave_si_scrive(self):
        risposte = iter([""])
        self.assertEqual(I.scegli_modello_servizio(f"{self.url}/v1", "", "proposto", self.righe.append,
                                                   lambda d: next(risposte)), "proposto")

    def test_modelli_non_testuali_esclusi(self):
        self.assertTrue(I.NON_TESTUALI.search("whisper-large-v3"))
        self.assertTrue(I.NON_TESTUALI.search("meta-llama/llama-guard-4-12b"))
        self.assertFalse(I.NON_TESTUALI.search("qwen/qwen3.8-27b"))

    def test_procedura_con_collegamento_fallito(self):
        risposte = ["2", "4", f"{self.url}/rotto/v1", "AIRCHIVIST_PROVA", "assente", "prova-rotta"]
        self.assertEqual(self.esegui("nuovo", chiedi=risposte), 1)
        self.assertIn("prova-rotta", L.leggi_profili(self.cfg()))       # resta salvato, da correggere
        self.assertEqual(L.profili_attivi(self.cfg())["analisi"], "buono")


class Togli(Base):
    def test_togli(self):
        self.assertEqual(self.esegui("togli", "buono", si=True), 1)      # in uso
        self.assertEqual(self.esegui("togli", "buono2", si=True), 1)     # non esiste
        self.assertEqual(self.esegui("togli", "secondo", chiedi=["n"]), 0)
        self.assertIn("secondo", L.leggi_profili(self.cfg()))
        self.assertEqual(self.esegui("togli", "secondo", si=True), 0)
        testo = self.profili.read_text(encoding="utf-8")
        self.assertNotIn("[secondo]", testo)
        self.assertNotIn("commento del profilo seguente", testo)
        self.assertIn("[rotto]", testo)
        self.assertTrue(list(self.tmp.glob("models.ini.airchivist-*.bak")))


class Converti(Base):
    def test_conversione(self):
        self.profili.unlink()
        self.scrivi_config(f"backend = router\ntimeout = 300\n\n[router]\n# FreeLLMAPI\nurl = {self.url}/v1\n"
                           "chiave_env = AIRCHIVIST_PROVA\nmodello_smistamento = auto:ricerca\n"
                           "modello_analisi = auto:ricerca\nmodello_sintesi = auto:ricerca\n"
                           "modelli_ammessi = finto\npausa_secondi = 2\n\n"
                           "[ollama]\nurl = http://localhost:11434\nmodello_smistamento = qwen3.5:4b\n"
                           "modello_analisi = qwen3.5:9b\nmodello_sintesi = qwen3.5:9b\nnum_ctx = 4096\n")
        prima = L.LLM(self.cfg(), "analisi")
        self.assertEqual(self.esegui("converti", si=True), 0, self.uscita())
        profili = L.leggi_profili(self.cfg())
        self.assertEqual(set(profili), {"freellmapi-auto-ricerca", "ollama-qwen3.5-4b", "ollama-qwen3.5-9b"})
        dopo = L.LLM(self.cfg(), "analisi")
        self.assertEqual(dopo.profilo, "freellmapi-auto-ricerca")
        for voce in ("url", "modello", "chiave", "ammessi", "pausa", "max_token", "timeout", "sezione"):
            self.assertEqual(getattr(prima, voce), getattr(dopo, voce), voce)
        self.assertIn("# FreeLLMAPI", self.config.read_text(encoding="utf-8"))
        self.assertTrue(list(self.tmp.glob("config.ini.airchivist-*.bak")))
        self.righe.clear()
        self.assertEqual(self.esegui("converti", si=True), 0)            # già fatta: niente da fare
        self.assertIn("niente da convertire", self.uscita())

    def test_controlla_con_profili(self):
        esito = I.Esito(self.righe.append)
        I.controlla_modelli(esito, self.cfg())
        self.assertEqual(esito.mancanti, [])
        self.scrivi_config("profilo = buono\nsintesi = spento\n")
        esito = I.Esito(self.righe.append)
        I.controlla_modelli(esito, self.cfg())
        self.assertEqual(esito.mancanti, ["modelli: spento"])


class StrumentoMcp(Base):
    """Strumento «modello» del server MCP e opzioni dello strumento «ricerca»."""
    def setUp(self):
        super().setUp()
        import mcp_server
        self.M = mcp_server
        self.patch_mcp = mock.patch.object(mcp_server, "CONFIG", str(self.config))
        self.patch_mcp.start()

    def tearDown(self):
        self.patch_mcp.stop()
        super().tearDown()

    def test_elenca(self):
        out = self.M.t_modello("elenca")
        self.assertEqual(out["in_uso"], {"smistamento": "buono", "analisi": "buono", "sintesi": "buono"})
        voci = {p["nome"]: p for p in out["profili"]}
        self.assertEqual(voci["buono"]["in_uso_per"], ["smistamento", "analisi", "sintesi"])
        self.assertEqual((voci["buono"]["chiave"], voci["spento"]["chiave"]), ("presente", "non serve"))
        self.assertEqual(voci["buono"]["misurato"], "no")
        self.assertIn("non qui", out["nota_chat"])

    def test_prova_e_usa(self):
        self.assertTrue(self.M.t_modello("prova", "buono")["riuscita"])
        self.assertIn("errore", self.M.t_modello("usa", "inesistente"))
        rifiutato = self.M.t_modello("usa", "rotto")
        self.assertFalse(rifiutato["cambiato"])
        self.assertIn("Restano in uso", " ".join(rifiutato["messaggi"]))
        self.assertEqual(L.profili_attivi(self.cfg())["analisi"], "buono")
        self.assertTrue(self.M.t_modello("usa", "secondo", ruoli=["sintesi"])["cambiato"])
        self.assertEqual(L.profili_attivi(self.cfg()),
                         {"smistamento": "buono", "analisi": "buono", "sintesi": "secondo"})
        self.assertTrue(self.M.t_modello("usa", "secondo", solo_progetto=True)["cambiato"])
        self.assertIn("profilo = secondo", (self.progetto / "project.ini").read_text(encoding="utf-8"))

    def test_opzioni_della_ricerca(self):
        import lavori
        i = {"principale": "X", "collegate": [], "modalita": "occorrenze", "dal": None, "al": None, "fonti": []}
        self.assertNotIn("--usa-modello-attuale", lavori.comando_ricerca(i, "d"))
        comando = lavori.comando_ricerca(dict(i, usa_modello_attuale=True, rileggi_modello="gpt-oss"), "d")
        self.assertIn("--usa-modello-attuale", comando)
        self.assertEqual(comando[comando.index("--rileggi-modello") + 1], "gpt-oss")
        schema = {n: p for n, (_, _, p, _) in self.M.STRUMENTI.items()}
        self.assertIn("rileggi_modello", schema["ricerca"])
        self.assertEqual(schema["modello"]["azione"]["enum"], ["elenca", "prova", "usa"])


class MisurePerProfilo(Base):
    """Misure legate al profilo (servizio + modello): prove di valutazione.py con --profili."""
    def test_prova_di_un_profilo(self):
        import valutazione as V
        # il progetto sceglie un altro profilo: la prova misura comunque quello chiesto
        (self.progetto / "project.ini").write_text("[progetto]\nnome = prova\n[modello]\nprofilo = rotto\n",
                                                   encoding="utf-8")
        args = argparse.Namespace(config=str(self.config))
        passaggio = {"id": "p1", "entita": "X", "passaggio": "testo", "riferimento": {"giudizio": "sì"}}
        with mock.patch.dict(os.environ, {VARIABILE: str(self.progetto)}):
            cfg = leggi_config(self.config)
            prova = V.prepara_prova(args, cfg, [passaggio], V.PROFILO + "secondo")
            self.assertEqual(V.info_profilo(prova / "config_prova.ini"),
                             {"profilo": "secondo", "servizio": "openai", "modello_profilo": "finto-2"})
            with mock.patch.dict(os.environ, {L.VARIABILE_FISSATI: str(prova / "modelli.json")}):
                self.assertEqual(L.LLM(leggi_config(prova / "config_prova.ini"), "smistamento").modello, "finto-2")
        self.assertTrue((prova / ".senza_archivio").exists())
        self.assertNotIn("riferimento", (prova / "passaggi.jsonl").read_text(encoding="utf-8"))

    def test_elenco_con_profili(self):
        import valutazione as V
        args = argparse.Namespace(modelli="", profili="buono; secondo", escludi="", config_attuale=False,
                                  solo_elenco=False)
        self.assertEqual(V.elenco_modelli(args, self.cfg()), ["profilo:buono", "profilo:secondo"])
        with self.assertRaises(SystemExit):
            V.elenco_modelli(dict_ns(args, profili="inesistente"), self.cfg())

    def test_stato_della_misura(self):
        from sintesi import profili_misurati
        d = self.progetto / "results" / "evaluation" / "rif"
        d.mkdir(parents=True)
        righe = [{"modello": "profilo:buono", "risposto": "finto-1", "letti": 4, "misure": {"n": 4},
                  "profilo": "buono", "servizio": "openai", "modello_profilo": "finto-1"},
                 {"modello": "x", "risposto": "groq/finto-2", "letti": 4, "misure": {"n": 4},
                  "profilo": "prova", "servizio": "router", "modello_profilo": "x"}]
        (d / "modelli_20261026_1500.jsonl").write_text("".join(json.dumps(r) + "\n" for r in righe), encoding="utf-8")
        self.assertEqual(profili_misurati(self.progetto / "results"), {("openai", "finto-1"), ("router", "x")})
        voci = {p["nome"]: p["misurato"] for p in I.stato_profili(self.cfg())["profili"]}
        self.assertEqual((voci["buono"], voci["secondo"], voci["rotto"]),
                         ("questo profilo", "stesso modello, altro servizio", "no"))
        self.esegui("elenca")
        self.assertIn("misurato: questo profilo", self.uscita())


def dict_ns(ns, **k):
    return argparse.Namespace(**{**vars(ns), **k})


class Voci(unittest.TestCase):
    def test_bom_e_crlf_conservati(self):
        f = Path(tempfile.mkdtemp()) / "a.ini"
        f.write_bytes(b"\xef\xbb\xbf# c\r\n[modello]\r\n# nota\r\nbackend = router\r\n\r\n[altro]\r\nx = 1\r\n")
        I.imposta_voci(f, "modello", {"profilo": "p", "backend": None})
        I.imposta_voci(f, "nuova", {"y": "2"})
        self.assertEqual(f.read_bytes(), b"\xef\xbb\xbf# c\r\n[modello]\r\n# nota\r\nprofilo = p\r\n\r\n"
                                         b"[altro]\r\nx = 1\r\n\r\n[nuova]\r\ny = 2\r\n")


class ProvaDeiModelli(Base):
    def test_config_per_modello(self):
        from valuta import config_per_modello
        self.profili.write_text(self.profili.read_text(encoding="utf-8") +
                                f"\n[router]\nservizio = router\nurl = {self.url}/v1\nmodello = auto:x\n"
                                "chiave_env = AIRCHIVIST_PROVA\nmodelli_ammessi = altro\n", encoding="utf-8")
        dest = self.tmp / "prova" / "config_prova.ini"
        dest.parent.mkdir()
        config_per_modello(self.config, "finto-9", dest)
        llm = L.LLM(leggi_config(dest), "smistamento")
        self.assertEqual((llm.sezione, llm.modello, llm.ammessi, llm.url), ("router", "finto-9", [], f"{self.url}/v1/chat/completions"))


if __name__ == "__main__":
    unittest.main()

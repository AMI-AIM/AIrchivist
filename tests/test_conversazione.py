"""
Test della conversazione sulle fonti (conversazione.py, lavoro 38), con servizi finti in locale e un server degli
strumenti finto:
- verifica delle citazioni: esatta, corrispondente (stesso titolo e numeri), non trovata, rimando di pagina isolato,
  due citazioni vicine non fuse in una;
- prova degli strumenti: un modello che chiama lo strumento sa usarli, uno che risponde con un testo no;
- una domanda: il modello chiama uno strumento, riceve il risultato e risponde; la citazione che gli strumenti hanno
  dato è trovata, quella inventata no; il ragionamento <think> non resta nella risposta;
- sola lettura: gli strumenti che scrivono non arrivano al server; ricerca (attendi) aspetta pochi secondi;
- conversione della storia per Anthropic e Ollama;
- richiesta troppo grande per il servizio (413): si riprova con i risultati accorciati;
- un errore del servizio non lascia la domanda a metà nella storia.
"""
import json
import os
import shutil
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
import conversazione as C  # noqa: E402
from llm import leggi_config  # noqa: E402
from progetto import VARIABILE  # noqa: E402

RIF = "*Renmin Ribao*. 1980. 15 aprile 1980, p. 1."
RISULTATO = {"entita": "Enrico Berlinguer", "totale": 1, "passaggi": [
    {"id": "rmb-1", "riferimento": RIF, "originale": "贝林格同志率意共中央代表团抵京",
     "traduzione": "Il compagno Berlinguer guida a Pechino la delegazione del PCI.",
     "solo_per_apri_fonte": {"file": "riviste/renmin_ribao/1980-04-15.txt", "riga": 9}}]}
INVENTATA = "*Renmin Ribao*. 1975. 1 gennaio 1975, p. 9."


class Servizio(BaseHTTPRequestHandler):
    """Servizio compatibile OpenAI con gli strumenti: «modello-strumenti» chiama passaggi_archivio e poi risponde
    citando il riferimento ricevuto e uno inventato; «modello-testo» risponde sempre con un testo; «modello-rotto»
    risponde con un errore."""
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

    def do_POST(self):
        corpo = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Servizio.richieste.append(corpo)
        ultimo = corpo["messages"][-1]
        if corpo["model"] == "modello-rotto":
            return self._rispondi(400, {"error": "richiesta non valida"})
        risultati = sum(len(m["content"]) for m in corpo["messages"] if m["role"] == "tool")
        if corpo["model"] == "modello-grande" and risultati > 2000:     # come Groq oltre i token al minuto
            return self._rispondi(413, {"error": {"message": "Request too large", "code": "rate_limit_exceeded"}})
        if corpo["model"] == "modello-testo":
            msg = {"content": "Non so usare gli strumenti, ma la serie ha 12 documenti."}
        elif ultimo["role"] == "user" and "conta_documenti" in ultimo["content"]:
            msg = {"tool_calls": [{"id": "c1", "type": "function",
                                   "function": {"name": "conta_documenti", "arguments": '{"serie": "Prova"}'}}]}
        elif ultimo["role"] == "user" and "scrivi" in ultimo["content"]:
            msg = {"tool_calls": [
                {"id": "c3", "function": {"name": "schede", "arguments": json.dumps(
                    {"azione": "crea", "nome": "X", "varianti": ["x"]})}},
                {"id": "c4", "function": {"name": "ricerca", "arguments": json.dumps(
                    {"azione": "attendi", "secondi": 600})}},
                {"id": "c5", "function": {"name": "importa", "arguments": json.dumps({"azione": "stato"})}}]}
        elif ultimo["role"] == "user":
            msg = {"content": None, "tool_calls": [{"id": "c2", "type": "function", "function": {
                "name": "passaggi_archivio", "arguments": json.dumps({"entita": "Enrico Berlinguer"})}}]}
        else:
            if ultimo["role"] == "tool" and ultimo.get("name") in ("schede", "ricerca", "importa"):
                msg = {"content": "Fatto."}
            else:
                if corpo["model"] == "modello-grande":
                    return self._rispondi(200, {"model": "modello-grande", "choices": [{"message": {
                        "content": f"Ho letto {risultati} caratteri."}}]})
                rif = json.loads(ultimo["content"])["passaggi"][0]["riferimento"]
                msg = {"content": f"<think>cerco i riferimenti</think>Berlinguer arriva a Pechino ({rif}). Lo dice "
                                  f"anche {INVENTATA} Si veda inoltre p. 44."}
        self._rispondi(200, {"model": corpo["model"], "choices": [{"message": msg}]})


class ServerFinto:
    """Il minimo del server MCP che la conversazione usa."""
    STRUMENTI = {n: None for n in ("guida", "schede", "passaggi_archivio", "ricerca", "importa", "modello", "serie")}

    def __init__(self):
        self.chiamate = []

    def elenco_strumenti(self):
        return [{"name": n, "description": f"strumento {n}", "inputSchema": {"type": "object", "properties": {}}}
                for n in self.STRUMENTI]

    def istruzioni(self):
        return "Regole del server."

    def gestisci(self, msg):
        p = msg["params"]
        self.chiamate.append((p["name"], p["arguments"]))
        out = RISULTATO if p["name"] == "passaggi_archivio" else {"stato": "in corso", "finito": False}
        return {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": json.dumps(
            out, ensure_ascii=False)}]}}


class Verifica(unittest.TestCase):
    def test_esatta_corrispondente_non_trovata(self):
        risultati = [json.dumps(RISULTATO, ensure_ascii=False)]
        testo = (f"Arrivo a Pechino ({RIF}) e ancora Renmin Ribao, 15 aprile 1980, p. 1. Poi *Renmin Ribao*. "
                 "1975. 2 maggio 1975, p. 4. E un rimando isolato, p. 1, e un altro, p. 77.")
        v = C.verifica_citazioni(testo, risultati)
        self.assertEqual([x["stato"] for x in v],
                         ["esatta", "corrispondente", "non trovata", "corrispondente", "non trovata"], v)
        self.assertEqual(testo[v[0]["inizio"]:v[0]["fine"]], "*Renmin Ribao*. 1980. 15 aprile 1980, p. 1")
        self.assertEqual(v[0]["passaggio"]["traduzione"], RISULTATO["passaggi"][0]["traduzione"])
        self.assertEqual(v[0]["riferimento"], RIF)
        self.assertEqual(C.conta(v), {"esatte": 1, "corrispondenti": 2, "non_trovate": 2})

    def test_citazioni_vicine_separate(self):
        testo = f"Fonti: {RIF} {INVENTATA}"
        v = C.verifica_citazioni(testo, [json.dumps(RISULTATO, ensure_ascii=False)])
        self.assertEqual([x["stato"] for x in v], ["esatta", "non trovata"], v)
        self.assertTrue(v[1]["testo"].startswith("*Renmin Ribao*. 1975"))

    def test_citazione_in_tabella(self):
        testo = "| Fonte | Data |\n|---|---|\n| *Renmin Ribao*, 15 aprile 1980, p. 1 | 1980-04-15 |\n"
        v = C.verifica_citazioni(testo, [json.dumps(RISULTATO, ensure_ascii=False)])
        self.assertEqual([(x["stato"], x["testo"]) for x in v],
                         [("corrispondente", "*Renmin Ribao*, 15 aprile 1980, p. 1")])

    def test_nome_senza_data_non_e_citazione(self):
        v = C.verifica_citazioni("Il Renmin Ribao ne parla spesso.", [json.dumps(RISULTATO, ensure_ascii=False)])
        self.assertEqual(v, [])

    def test_titolo_della_serie_senza_riferimenti(self):
        v = C.verifica_citazioni("Peking Review 7, no. 12 (1964): 5.", ["{}"], ["Peking Review"])
        self.assertEqual([x["stato"] for x in v], ["non trovata"])

    def test_voce_di_rivista_e_conteggi_fra_virgolette(self):
        """Prova nel browser (1/11/2026): la voce Chicago di una rivista («*Titolo* 121, no. 2: 377–402», anno prima
        del titolo) non si controllava; il riassunto «*Titolo* 2016 (forme: «X» 17, …)» risultava inventato."""
        rif = ("Putnam, Lara. 2016. \"The Transnational and the Text-Searchable.\" *The American Historical Review* "
               "121, no. 2 (aprile): 377-402, p. 377.")
        risultati = [json.dumps({"esempi": [{"riferimento": rif, "originale": "Author(s): LARA PUTNAM"}]})]
        testo = ("Tutte in *The American Historical Review* 2016 (forme: «Lara Putnam» 17, «LARA PUTNAM» 2).\n"
                 "- Putnam, Lara. 2016. \"The Transnational.\" *The American Historical Review* 121, no. 2: 377–402.\n"
                 "- Putnam, Lara. 2016. \"The Transnational.\" *The American Historical Review* 121, no. 2: 410–420.\n")
        v = C.verifica_citazioni(testo, risultati, ["The American Historical Review"])
        self.assertEqual([(x["stato"], x["testo"]) for x in v],
                         [("corrispondente", "*The American Historical Review* 2016"),
                          ("corrispondente", "*The American Historical Review* 121, no. 2: 377–402"),
                          ("non trovata", "*The American Historical Review* 121, no. 2: 410–420")])

    def test_citazione_nel_testo_della_risposta_pronta(self):
        pronta = json.dumps({"risposta_pronta": {"risposta": f"Berlinguer arriva a Pechino.\n- {RIF}"}},
                            ensure_ascii=False)
        v = C.verifica_citazioni(f"Secondo {RIF}", [pronta])
        self.assertEqual(v[0]["stato"], "esatta")


class Conversazione(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servizio = ThreadingHTTPServer(("127.0.0.1", 0), Servizio)
        threading.Thread(target=cls.servizio.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{cls.servizio.server_address[1]}/v1"
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        progetto = base / "progetto"
        shutil.copytree(PROVA, progetto)
        profili = base / "models.ini"
        profili.write_text("".join(f"[{m}]\nservizio = openai\nurl = {url}\nmodello = modello-{m}\n"
                                   "chiave_env = AIRCHIVIST_PROVA\n\n" for m in ("strumenti", "testo", "rotto", "grande")),
                           encoding="utf-8")
        cls.config = base / "config.ini"
        cls.config.write_text(f"[progetto]\ncartella = {progetto.as_posix()}\n\n[modello]\n"
                              f"file_profili = {profili.as_posix()}\nprofilo = strumenti\n", encoding="utf-8")
        cls.env = mock.patch.dict(os.environ, {"AIRCHIVIST_PROVA": "chiave", VARIABILE: str(progetto)})
        cls.env.start()

    @classmethod
    def tearDownClass(cls):
        cls.env.stop()
        cls.servizio.shutdown()
        cls.servizio.server_close()
        cls.tmp.cleanup()

    def setUp(self):
        Servizio.richieste.clear()
        self.server = ServerFinto()

    def conv(self, profilo="strumenti", **k):
        return C.Conversazione(leggi_config(self.config), self.server, profilo, **k)

    def test_prova_degli_strumenti(self):
        self.assertTrue(self.conv().prova_strumenti()["sa_usare_strumenti"])
        p = self.conv("testo").prova_strumenti()
        self.assertFalse(p["sa_usare_strumenti"])
        self.assertIn("testo invece di chiamare lo strumento", p["motivo"])
        with self.assertRaises(C.ErroreConversazione):
            self.conv("rotto").prova_strumenti()

    def test_domanda_con_strumenti_e_verifica(self):
        c = self.conv()
        voce = c.invia("Che cosa dicono le fonti di Berlinguer?")
        self.assertNotIn("<think>", voce["testo"])
        self.assertEqual([s["nome"] for s in voce["strumenti"]], ["passaggi_archivio"])
        self.assertEqual(self.server.chiamate, [("passaggi_archivio", {"entita": "Enrico Berlinguer"})])
        self.assertEqual([x["stato"] for x in voce["citazioni"]], ["esatta", "non trovata", "non trovata"])
        self.assertEqual(voce["verifica"], {"esatte": 1, "corrispondenti": 0, "non_trovate": 2})
        self.assertEqual([m["ruolo"] for m in c.storia], ["utente", "modello"])
        # strumenti offerti al modello: non guida, modello, importa, serie; istruzioni del server come sistema
        richiesta = Servizio.richieste[0]
        self.assertEqual({t["function"]["name"] for t in richiesta["tools"]},
                         {"schede", "passaggi_archivio", "ricerca"})
        self.assertTrue(richiesta["messages"][0]["content"].startswith("Regole del server."))
        # seconda domanda: il risultato del turno precedente torna accorciato, se lungo
        c.messaggi[2]["content"] = "x" * 5000
        c.invia("E poi?")
        rimandato = [m for m in Servizio.richieste[-2]["messages"] if m["role"] == "tool"][0]["content"]
        self.assertLess(len(rimandato), 2000)

    def test_sola_lettura_e_attesa_breve(self):
        c = self.conv(sola_lettura=True)
        voce = c.invia("scrivi una scheda")
        self.assertEqual([s["nome"] for s in voce["strumenti"]], ["schede", "ricerca", "importa"])
        self.assertEqual(self.server.chiamate, [("ricerca", {"azione": "attendi", "secondi": C.ATTESA_RICERCA})])
        risultati = [m["content"] for m in c.messaggi if m["role"] == "tool"]
        self.assertIn("simulato", risultati[0])
        self.assertIn("non disponibile", risultati[2])

    def test_richiesta_troppo_grande_risultati_accorciati(self):
        lungo = dict(RISULTATO, nota="x" * 9000)
        with mock.patch.object(ServerFinto, "gestisci", lambda s, m: {"result": {"content": [
                {"text": json.dumps(lungo, ensure_ascii=False)}]}}):
            voce = self.conv("grande").invia("Domanda")
        self.assertTrue(voce["testo"].startswith("Ho letto"))
        self.assertLessEqual(int(voce["testo"].split()[2]), 2000)
        self.assertEqual([r["model"] for r in Servizio.richieste].count("modello-grande"), 5)
        # la chiamata dello strumento, poi il risultato di 9000 caratteri, accorciato a 6000, 3000 e 1500

    def test_errore_del_servizio_non_lascia_la_domanda(self):
        c = self.conv("rotto")
        with self.assertRaises(C.ErroreConversazione):
            c.invia("Domanda")
        self.assertEqual((c.messaggi, c.storia), ([], []))


class Conversioni(unittest.TestCase):
    STORIA = [{"role": "user", "content": "Domanda"},
              {"role": "assistant", "content": "", "tool_calls": [
                  {"id": "a", "function": {"name": "schede", "arguments": '{"azione": "elenca"}'}},
                  {"id": "b", "function": {"name": "ricerca", "arguments": '{"azione": "attendi"}'}}]},
              {"role": "tool", "tool_call_id": "a", "name": "schede", "content": "uno"},
              {"role": "tool", "tool_call_id": "b", "name": "ricerca", "content": "due"},
              {"role": "assistant", "content": "Risposta"}]

    def test_anthropic(self):
        m = C.per_anthropic(self.STORIA)
        self.assertEqual([x["role"] for x in m], ["user", "assistant", "user", "assistant"])
        self.assertEqual([b["type"] for b in m[1]["content"]], ["tool_use", "tool_use"])
        self.assertEqual(m[1]["content"][0]["input"], {"azione": "elenca"})
        self.assertEqual([b["tool_use_id"] for b in m[2]["content"]], ["a", "b"])
        self.assertEqual(m[3]["content"], [{"type": "text", "text": "Risposta"}])

    def test_ollama(self):
        m = C.per_ollama(self.STORIA)
        self.assertEqual(m[1]["tool_calls"][1]["function"]["arguments"], {"azione": "attendi"})
        self.assertEqual(m[2], {"role": "tool", "content": "uno", "tool_name": "schede"})


if __name__ == "__main__":
    unittest.main()

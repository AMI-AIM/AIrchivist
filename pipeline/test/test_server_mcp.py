"""
Test del server MCP generico (mcp_server.py, istruzioni.py): il server avviato davvero in stdio su un progetto
nuovo (variabile AIRCHIVIST_PROGETTO), con le istruzioni composte dai profili e da istruzioni.md, il prompt
«istruzioni», i 13 strumenti e i nomi di prima accettati come alias.
"""
import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))
import progetto as P  # noqa: E402


class ServerMcp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        radice = Path(cls._tmp.name) / "stampa"
        with redirect_stdout(io.StringIO()):
            P.cmd_nuovo(argparse.Namespace(cartella=str(radice), nome="Stampa di prova", descrizione="Solo un test."))
        with open(radice / "serie.ini", "a", encoding="utf-8") as f:
            f.write("\n[Gazzetta di prova]\ntipo = periodico\nlingua = it\ncartella = riviste/gazzetta\n"
                    "periodo = 1950-01-01 / 1960-12-31\n")
        (radice / "istruzioni.md").write_text("# commento da non inviare\nCita sempre la Gazzetta per prima.\n",
                                              encoding="utf-8")
        (radice / "progetto.ini").write_text("[progetto]\nnome = Stampa di prova\ndescrizione = Solo un test.\n"
                                             "[mcp]\nlingua = inglese\nattesa_massima = 20\n", encoding="utf-8")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1", AIRCHIVIST_PROGETTO=str(radice))
        messaggi = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "prompts/list"},
            {"jsonrpc": "2.0", "id": 4, "method": "prompts/get", "params": {"name": "istruzioni"}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "elenca_serie", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 6, "method": "tools/call", "params": {"name": "schede",
                                                                             "arguments": {"azione": "crea"}}},
            {"jsonrpc": "2.0", "id": 7, "method": "tools/call", "params": {"name": "inesistente", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 8, "method": "tools/call", "params": {"name": "guida", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 9, "method": "tools/call",
             "params": {"name": "passaggi_archivio", "arguments": {"entita": "Persona senza scheda"}}},
            {"jsonrpc": "2.0", "id": 10, "method": "tools/call",
             "params": {"name": "ricerca", "arguments": {"azione": "avvia", "entita": "Persona senza scheda"}}},
            {"jsonrpc": "2.0", "id": 11, "method": "tools/call",
             "params": {"name": "apri_fonte", "arguments": {"file": "riviste/gazzetta/G1955-01-01.txt", "riga": 2}}},
        ]
        (radice / "data" / "riviste" / "gazzetta").mkdir(parents=True)
        (radice / "data" / "riviste" / "gazzetta" / "G1955-01-01.txt").write_text(
            "[SERIES: Gazzetta di prova]\n\nPrima riga del testo.\nSeconda riga.\n", encoding="utf-8")
        r = subprocess.run([sys.executable, str(PIPELINE / "mcp_server.py")], env=env, capture_output=True,
                           input="\n".join(json.dumps(m) for m in messaggi) + "\n", text=True, encoding="utf-8",
                           timeout=120)
        cls.risposte = {x["id"]: x for x in map(json.loads, r.stdout.splitlines()) if x.get("id") is not None}
        cls.stderr = r.stderr

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _testo(self, i):
        return self.risposte[i]["result"]["content"][0]["text"]

    def test_istruzioni_del_progetto(self):
        ist = self.risposte[1]["result"]["instructions"]
        self.assertIn("Rispondi in inglese", ist)
        self.assertIn("al massimo 20 secondi", ist)
        self.assertIn("Progetto: Stampa di prova. Solo un test.", ist)
        self.assertIn("- Gazzetta di prova (periodico, it, 1950-01-01 / 1960-12-31)", ist)
        self.assertIn("Cita sempre la Gazzetta per prima.", ist)
        self.assertNotIn("commento da non inviare", ist)
        for estraneo in ("Renmin", "Peking Review", "Pechino", "Jan", "corpus"):  # nulla del corpus attuale o di un client
            self.assertNotIn(estraneo, ist)

    def test_strumenti_e_prompt(self):
        nomi = [t["name"] for t in self.risposte[2]["result"]["tools"]]
        self.assertEqual(len(nomi), 13)
        self.assertIn("guida", nomi)
        self.assertNotIn("elenca_serie", nomi)                     # alias: accettato, non elencato
        self.assertEqual(self.risposte[3]["result"]["prompts"][0]["name"], "istruzioni")
        self.assertEqual(self.risposte[4]["result"]["messages"][0]["content"]["text"],
                         self.risposte[1]["result"]["instructions"])

    def test_alias_errori_e_guida(self):
        self.assertIn("Gazzetta di prova", json.loads(self._testo(5))["serie"])
        self.assertTrue(self.risposte[6]["result"]["isError"])     # crea senza nome e varianti
        self.assertEqual(self.risposte[7]["error"]["code"], -32602)
        guida = json.loads(self._testo(8))
        self.assertEqual((guida["progetto"], guida["fonti_selezionabili"]), ("Stampa di prova", ["Gazzetta di prova"]))


    def test_regole_nelle_descrizioni(self):
        # le descrizioni sono il solo testo che ogni client mostra sempre al modello
        d = {t["name"]: t["description"] for t in self.risposte[2]["result"]["tools"]}
        self.assertIn("PRIMA di qualsiasi altro strumento", d["guida"])
        self.assertIn("SOLO per verificare", d["cerca_testo"])
        self.assertIn("Non costruire risposte", d["apri_fonte"])
        self.assertIn("non citare file né righe", d["apri_fonte"])
        self.assertIn("Il modo di rispondere", d["ricerca"])

    def test_scheda_mancante_e_avvertenze(self):
        for i in (9, 10):
            out = json.loads(self._testo(i))
            self.assertTrue(self.risposte[i]["result"]["isError"])
            self.assertIn("esplora_nome", out["prossimo_passo"])
            self.assertIn("schede (azione crea)", out["prossimo_passo"])
        fonte = json.loads(self._testo(11))
        self.assertEqual(list(fonte)[0], "avvertenza")                # prima cosa che il modello legge
        self.assertIn("non è una risposta", fonte["avvertenza"])
        self.assertIn("Seconda riga", fonte["testo"])


if __name__ == "__main__":
    unittest.main()

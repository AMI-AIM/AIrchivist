"""
Test dell'installazione e del controllo dell'ambiente (installa.py): esito dei controlli, servizio dei modelli
senza chiave o non raggiungibile, configurazione dei client MCP. Nessuna rete né installazione vera.
"""
import argparse
import configparser
import json
import os
import sys
import unittest
from pathlib import Path

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOTORE))
import installa as I  # noqa: E402


def config(testo):
    cp = configparser.ConfigParser(interpolation=None)
    cp.read_string(testo)
    return cp


class Controlli(unittest.TestCase):
    def setUp(self):
        self.righe = []
        self.esito = I.Esito(self.righe.append)

    def test_esito_conta_solo_i_necessari(self):
        self.esito("ok", "Python", "3.12")
        self.esito("facoltativo", "PyMuPDF", "assente")
        self.esito("manca", "modelli", "assente")
        self.assertEqual(self.esito.mancanti, ["modelli"])
        self.assertTrue(self.righe[2].startswith("[MANCA] modelli"))

    def test_python_e_sqlite(self):
        I.controlla_python(self.esito)
        I.controlla_sqlite(self.esito)
        self.assertEqual(self.esito.mancanti, [])

    def test_chiave_assente(self):
        cfg = config("[modello]\nbackend = router\n[router]\nurl = http://127.0.0.1:9/v1\n"
                     "chiave_env = AIRCHIVIST_CHIAVE_DI_PROVA\n")
        os.environ.pop("AIRCHIVIST_CHIAVE_DI_PROVA", None)
        I.controlla_modelli(self.esito, cfg)
        self.assertEqual(self.esito.mancanti, ["modelli: router"])
        self.assertIn("AIRCHIVIST_CHIAVE_DI_PROVA", self.righe[0])

    def test_servizio_spento(self):
        cfg = config("[modello]\nbackend = ollama\n[ollama]\nurl = http://127.0.0.1:9\n")
        I.controlla_modelli(self.esito, cfg)
        self.assertEqual(self.esito.mancanti, ["modelli: ollama"])
        self.assertIn("avvia Ollama", self.righe[0])


class Client(unittest.TestCase):
    def esegui(self, nome):
        righe = []
        codice = I.cmd_client(argparse.Namespace(nome=nome), righe.append)
        self.assertEqual(codice, 0)
        return righe

    def test_json(self):
        righe = self.esegui("json")
        blocco = json.loads(next(r for r in righe if r.startswith("{")))
        voce = blocco["mcpServers"][I.NOME_SERVER]
        self.assertEqual(voce["command"], sys.executable)
        self.assertEqual(Path(voce["args"][0]), MOTORE / "mcp_server.py")
        self.assertEqual(voce["env"], {"PYTHONUTF8": "1"})

    def test_claude_indica_il_file(self):
        righe = self.esegui("claude")
        self.assertIn("claude_desktop_config.json", righe[0])

    def test_jan(self):
        testo = "\n".join(self.esegui("jan"))
        self.assertIn("STDIO", testo)
        self.assertIn(str(MOTORE / "mcp_server.py"), testo)


if __name__ == "__main__":
    unittest.main()

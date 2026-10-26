"""
Test dell'installazione e del controllo dell'ambiente (installa.py): esito dei controlli, servizio dei modelli
senza chiave o non raggiungibile, configurazione dei client MCP. Nessuna rete né installazione vera.
"""
import argparse
import configparser
import json
import os
import sys
import tempfile
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
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cartella = Path(self.tmp.name)

    def esegui(self, nome):
        righe = []
        codice = I.cmd_client(argparse.Namespace(nome=nome, scrivi=False, verifica=False, si=True, file=None),
                              righe.append)
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
        self.assertIn("timeout degli strumenti", testo)          # i campi non modificabili restano manuali
        self.assertIn("smart routing", testo)

    # ------------------------------------------------- --scrivi (lavoro 27)
    def scrivi(self, nome="claude", esistente=None, risposta="", voce=None):
        f = self.cartella / f"{nome}.json"
        if esistente is not None:
            f.write_text(json.dumps(esistente), encoding="utf-8")
        args = argparse.Namespace(nome=nome, scrivi=True, verifica=False, si=False, file=str(f),
                                  voce=voce or {"command": "py", "args": ["server.py"], "env": {"PYTHONUTF8": "1"}})
        righe = []
        codice = I.cmd_client_scrivi(args, righe.append, chiedi=lambda _t: risposta)
        return codice, righe, f

    def test_scrive_su_configurazione_vuota(self):
        codice, _, f = self.scrivi()
        self.assertEqual(codice, 0)
        doc = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual(doc["mcpServers"][I.NOME_SERVER]["args"], ["server.py"])

    def test_preserva_le_altre_voci(self):
        base = {"mcpServers": {"altro": {"command": "x", "args": ["y"]}}, "theme": "dark"}
        codice, _, f = self.scrivi(esistente=base)
        self.assertEqual(codice, 0)
        doc = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual(doc["mcpServers"]["altro"], base["mcpServers"]["altro"])
        self.assertEqual(doc["theme"], "dark")
        self.assertIn(I.NOME_SERVER, doc["mcpServers"])

    def test_aggiorna_la_voce_esistente_senza_duplicati(self):
        vecchia = {k: v for k, v in I.voce_server().items()}
        base = {"mcpServers": {I.NOME_SERVER: {"command": "vecchio", "args": ["a"]}, "altro": {"command": "x"}}}
        args = argparse.Namespace(nome="claude", scrivi=True, verifica=False, si=True, file=None, voce=vecchia)
        doc, modifiche, gia = I.unisci_voci("claude", base, I.NOME_SERVER, vecchia)
        self.assertFalse(gia)
        self.assertEqual(len(doc["mcpServers"]), 2)
        self.assertEqual(doc["mcpServers"][I.NOME_SERVER], vecchia)
        self.assertTrue(any(m.startswith("~") for m in modifiche))

    def test_riconosce_il_nome_vecchio_pipeline(self):
        base = {"servers": {"Pipeline": {"command": "python", "args": ["mcp_server.py"]}}}
        voce = {"command": "py", "args": ["s.py"], "env": {}}
        doc, modifiche, gia = I.unisci_voci("jan", base, I.NOME_SERVER, voce)
        self.assertNotIn("Pipeline", doc["servers"])
        self.assertIn(I.NOME_SERVER, doc["servers"])
        self.assertTrue(any("Pipeline" in m for m in modifiche))

    def test_gia_presente_non_scrive(self):
        voce = {"command": "py", "args": ["server.py"], "env": {"PYTHONUTF8": "1"}}
        codice, righe, f = self.scrivi(esistente={"mcpServers": {I.NOME_SERVER: voce}})
        self.assertEqual(codice, 0)
        self.assertIn("già esattamente questa", "\n".join(righe))
        self.assertEqual(list(f.parent.glob("*.bak")), [])      # nessuna copia: non ha scritto

    def test_domanda_di_conferma_e_copia_di_sicurezza(self):
        base = {"mcpServers": {"altro": {"command": "x"}}}
        codice, righe, f = self.scrivi(esistente=base, risposta="n")
        self.assertEqual(codice, 0)
        self.assertIn("Annullato", "\n".join(righe))
        self.assertEqual(json.loads(f.read_text(encoding="utf-8")), base)   # file intatto
        codice, righe, f = self.scrivi(esistente=base, risposta="")         # a vuoto: vale S/n -> sì
        self.assertEqual(codice, 0)
        copie = list(f.parent.glob("*.airchivist-*.bak"))
        self.assertEqual(len(copie), 1)
        self.assertEqual(json.loads(copie[0].read_text(encoding="utf-8")), base)

    def test_senza_scrivi_mostra_solo(self):
        f = self.cartella / "c.json"
        args = argparse.Namespace(nome="claude", scrivi=False, verifica=False, si=False, file=str(f), voce=None)
        righe = []
        self.assertEqual(I.cmd_client(args, righe.append), 0)
        self.assertFalse(f.exists())

    def test_file_malformato_blocca(self):
        f = self.cartella / "rotto.json"
        f.write_text("non è JSON", encoding="utf-8")
        args = argparse.Namespace(nome="claude", scrivi=True, verifica=False, si=True, file=str(f), voce=None)
        righe = []
        self.assertEqual(I.cmd_client_scrivi(args, righe.append, chiedi=lambda t: ""), 3)
        self.assertEqual(f.read_text(encoding="utf-8"), "non è JSON")

    def test_sezione_malformata_blocca(self):
        doc, modifiche, _ = I.unisci_voci("claude", {"mcpServers": [1, 2]}, I.NOME_SERVER, {"command": "a"})
        self.assertIsNone(doc)
        self.assertEqual(modifiche, ["«mcpServers» nel file non è un elenco di server: non scrivo nulla"])

    def test_jan_usa_sezione_servers(self):
        base = {"servers": {"Altro": {"command": "x", "args": ["y"], "enabled": True}}}
        voce = {"command": "py", "args": ["s.py"], "env": {}}
        doc, _, _ = I.unisci_voci("jan", base, I.NOME_SERVER, voce)
        self.assertIn(I.NOME_SERVER, doc["servers"])
        self.assertEqual(doc["servers"]["Altro"], base["servers"]["Altro"])

    # ------------------------------------------------- --verifica
    class FintoProc:
        def __init__(self, risposte):
            self.risposte = list(risposte)
            self.inviati = []
            class _W(list):
                pass
            self.stdin = type("_Stdin", (), {"write": lambda s, t: self.inviati.append(t),
                                             "flush": lambda s: None})()
            self.stdout = type("_Stdout", (), {"readline": lambda s: (self.risposte.pop(0) + "\n"
                                                                      if self.risposte else "")})()

        def kill(self):
            pass

        def wait(self, timeout=None):
            return 0

    @staticmethod
    def risposte_valide():
        ini = json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2024-11-05",
                                                                "serverInfo": {"name": "ricerca-fonti",
                                                                               "version": "1.0"}}})
        tools = json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": n} for n in I.STRUMENTI_ATTESI]}})
        return [ini, tools]

    def test_verifica_handshake_ed_elenco(self):
        proc = self.FintoProc(self.risposte_valide())
        righe = []
        args = argparse.Namespace(nome="json", scrivi=False, verifica=True, si=True, file=None, voce=None)
        codice = I.client_verifica(args, righe.append, avvia=lambda v: proc)
        self.assertEqual(codice, 0)
        testo = "\n".join(righe)
        self.assertIn("Handshake MCP riuscito", testo)
        self.assertIn("tutti quelli attesi", testo)
        self.assertIn('"initialize"', proc.inviati[0])
        self.assertIn('"tools/list"', proc.inviati[-1])

    def test_verifica_strumenti_mancanti(self):
        ini, _ = self.risposte_valide()
        corto = json.dumps({"jsonrpc": "2.0", "id": 2, "result": {"tools": [{"name": "guida"}]}})
        proc = self.FintoProc([ini, corto])
        righe = []
        args = argparse.Namespace(nome="json", scrivi=False, verifica=True, si=True, file=None, voce=None)
        self.assertEqual(I.client_verifica(args, righe.append, avvia=lambda v: proc), 1)
        self.assertIn("mancano", "\n".join(righe))

    def test_verifica_serve_reale(self):
        """Prova vera: avvia mcp_server.py come lo avvierebbe il client e controlla l'handshake."""
        righe = []
        args = argparse.Namespace(nome="json", scrivi=False, verifica=True, si=True, file=None, voce=None)
        codice = I.client_verifica(args, righe.append)
        self.assertEqual(codice, 0, "\n".join(righe))
        self.assertIn("ricerca-fonti", "\n".join(righe))


if __name__ == "__main__":
    unittest.main()

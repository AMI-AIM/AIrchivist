"""
Test dell'installazione e del controllo dell'ambiente (installa.py): esito dei controlli, servizio dei modelli
senza chiave o non raggiungibile, configurazione dei client MCP (anche Jan nella forma reale dei suoi file), avvio
guidato su una configurazione come quella di una copia pulita. Nessuna rete né installazione vera.
"""
import argparse
import configparser
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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
        # forma reale di mcp_config.json di Jan (26/10/2026): «mcpServers», voci con «active» e «type»
        base = {"mcpServers": {"Pipeline": {"command": "python", "args": ["mcp_server.py"], "env": {},
                                            "active": False, "type": "stdio"}}}
        voce = {"command": "py", "args": ["s.py"], "env": {}}
        doc, modifiche, gia = I.unisci_voci("jan", base, I.NOME_SERVER, voce)
        self.assertNotIn("servers", doc)
        self.assertEqual(list(doc["mcpServers"]), ["Pipeline"])            # il nome scelto dall'utente resta
        self.assertEqual(doc["mcpServers"]["Pipeline"],
                         {"command": "py", "args": ["s.py"], "env": {}, "active": True, "type": "stdio"})
        self.assertTrue(any("Pipeline" in m and "spenta" in m for m in modifiche))

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

    def test_non_interattiva_eof_non_scrive(self):
        """--scrivi senza --si con tastiera assente (EOFError): deve annullare con codice 0, non esplodere."""
        base = {"mcpServers": {"altro": {"command": "x"}}}
        f = self.cartella / "eof.json"
        f.write_text(json.dumps(base), encoding="utf-8")
        args = argparse.Namespace(nome="claude", scrivi=True, verifica=False, si=False, file=str(f),
                                  voce={"command": "py", "args": ["server.py"], "env": {}})
        righe = []

        def chiedi_che_esplode(_t):
            raise EOFError

        codice = I.cmd_client_scrivi(args, righe.append, chiedi=chiedi_che_esplode)
        self.assertEqual(codice, 0)
        self.assertIn("Annullato", "\n".join(righe))
        self.assertEqual(json.loads(f.read_text(encoding="utf-8")), base)   # file intatto

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

    def test_jan_voce_nuova_accesa(self):
        base = {"mcpServers": {"fetch": {"command": "x", "args": ["y"], "env": {}, "active": False}}}
        voce = {"command": "py", "args": ["s.py"], "env": {}}
        doc, _, _ = I.unisci_voci("jan", base, I.NOME_SERVER, voce)
        self.assertEqual(doc["mcpServers"][I.NOME_SERVER]["active"], True)
        self.assertEqual(doc["mcpServers"]["fetch"], base["mcpServers"]["fetch"])

    def jan(self, mcp, impostazioni=None, risposta="", si=False):
        """--scrivi per Jan su due file finti: mcp_config.json e settings.json."""
        f = self.cartella / "mcp_config.json"
        f.write_text(json.dumps(mcp, indent=2), encoding="utf-8")
        f_imp = self.cartella / "settings.json"
        if impostazioni is not None:
            f_imp.write_text(json.dumps(impostazioni, indent=2), encoding="utf-8")
        args = argparse.Namespace(nome="jan", scrivi=True, verifica=False, si=si, file=str(f),
                                  file_impostazioni=str(f_imp),
                                  voce={"command": "py", "args": ["server.py"], "env": {"PYTHONUTF8": "1"}})
        righe = []
        with mock.patch.object(I, "in_esecuzione", lambda nome: False):
            codice = I.cmd_client_scrivi(args, righe.append, chiedi=lambda _t: risposta)
        return codice, "\n".join(righe), f, f_imp

    def test_jan_impostazioni_e_ricerca_web(self):
        mcp = {"mcpServers": {"Pipeline": {"command": "python", "args": ["vecchio.py"], "env": {}, "active": True,
                                           "type": "stdio"}},
               "mcpSettings": {"toolCallTimeoutSeconds": 30, "enableSmartToolRouting": True,
                               "maxToolOutputChars": 4000, "baseRestartDelayMs": 1000}}
        imp = {"theme": "dark", "setting-web-search": json.dumps(
            {"state": {"webSearchEnabled": True, "searchProvider": "x", "endpoints": {}}, "version": 0},
            separators=(",", ":"))}
        codice, testo, f, f_imp = self.jan(mcp, imp)
        self.assertEqual(codice, 0, testo)
        doc = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual(doc["mcpServers"]["Pipeline"]["args"], ["server.py"])
        self.assertEqual(doc["mcpSettings"], {"toolCallTimeoutSeconds": 90, "enableSmartToolRouting": False,
                                              "maxToolOutputChars": 8000, "baseRestartDelayMs": 1000})
        doc_imp = json.loads(f_imp.read_text(encoding="utf-8"))
        self.assertEqual(doc_imp["theme"], "dark")
        self.assertFalse(json.loads(doc_imp["setting-web-search"])["state"]["webSearchEnabled"])
        self.assertEqual(len(list(self.cartella.glob("*.airchivist-*.bak"))), 2)       # una copia per file
        # di nuovo: tutto già a posto, nessuna scrittura
        codice, testo, _, _ = self.jan(doc, doc_imp)
        self.assertIn("Nessuna scrittura necessaria", testo)

    def test_jan_valori_gia_buoni_restano(self):
        mcp = {"mcpServers": {}, "mcpSettings": {"toolCallTimeoutSeconds": 120, "enableSmartToolRouting": False,
                                                 "maxToolOutputChars": 20000}}
        codice, testo, f, _ = self.jan(mcp)
        self.assertEqual(json.loads(f.read_text(encoding="utf-8"))["mcpSettings"], mcp["mcpSettings"])

    def test_jan_aperto_non_scrive(self):
        f = self.cartella / "mcp_config.json"
        f.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")
        args = argparse.Namespace(nome="jan", scrivi=True, verifica=False, si=True, file=str(f),
                                  file_impostazioni=None, voce={"command": "py", "args": ["s.py"], "env": {}})
        righe = []
        with mock.patch.object(I, "in_esecuzione", lambda nome: True):
            self.assertEqual(I.cmd_client_scrivi(args, righe.append), 1)
        self.assertIn("Jan è aperto", "\n".join(righe))
        self.assertEqual(json.loads(f.read_text(encoding="utf-8")), {"mcpServers": {}})

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


class AvvioGuidato(unittest.TestCase):
    """installa.py inizia con la configurazione di una copia pulita del repository: il progetto indicato in
    config.ini non esiste e il profilo scelto non è in models.ini. Servizio dei modelli e client finti."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.config = self.tmp / "config.ini"
        self.config.write_text(f"[progetto]\ncartella = {(self.tmp / 'inesistente').as_posix()}\n\n[modello]\n"
                               f"file_profili = {(self.tmp / 'models.ini').as_posix()}\nprofilo = assente\n",
                               encoding="utf-8")
        (self.tmp / "models.ini").write_text("[locale]\nservizio = ollama\nmodello = m\n", encoding="utf-8")
        self.client = self.tmp / "client"
        finti = {"FILE_CONFIG": self.config, "prova_profilo": lambda cfg, nome, stampa: True,
                 "file_client": lambda nome, dati=None: self.client / f"{nome}.json",
                 "in_esecuzione": lambda nome: False, "client_verifica": lambda a, s, avvia=None: 0,
                 "cartella_progetti": lambda: self.tmp / "projects",
                 "controlla_modelli": lambda esito, cfg: esito("ok", "modelli", "finto")}
        for nome, valore in finti.items():
            p = mock.patch.object(I, nome, valore)
            p.start()
            self.addCleanup(p.stop)
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("AIRCHIVIST_PROGETTO", None)

    def inizia(self, risposte, **opzioni):
        r = iter(risposte)
        righe = []
        args = argparse.Namespace(**{"passi": "", "saltati": "", "si": False, "rapido": True, **opzioni})
        codice = I.cmd_inizia(args, righe.append, chiedi=lambda _d: next(r))
        return codice, "\n".join(righe)

    def test_copia_pulita_fino_al_riepilogo(self):
        # passo 2: profilo «locale»; passo 3: nome, cartella proposta, conferma; passo 4: Claude Desktop, conferma
        codice, testo = self.inizia(["1", "Ricerca di prova", "", "", "2", ""])
        self.assertEqual(codice, 0, testo)
        self.assertIn("non esiste (o non è un progetto): ne creo uno", testo)
        progetto = self.tmp / "projects" / "Ricerca_di_prova"
        self.assertTrue((progetto / "project.ini").is_file())
        cfg = self.config.read_text(encoding="utf-8")
        self.assertIn(f"cartella = {progetto.resolve()}", cfg)
        self.assertIn("profilo = locale", cfg)
        self.assertFalse((self.tmp / "inesistente").exists())            # nessuna cartella fantasma
        doc = json.loads((self.client / "claude.json").read_text(encoding="utf-8"))
        self.assertIn(I.NOME_SERVER, doc["mcpServers"])
        self.assertIn("AIrchivist è nella configurazione di Claude Desktop", testo)
        self.assertIn("python importa.py proponi", testo)                  # comando che esiste (lavoro 29)
        self.assertTrue(testo.rstrip().endswith("Tutto pronto."))

    def test_conferma_della_chat(self):
        domande = []
        risposte = iter(["1", "Ricerca", "", "", "1", "n"])

        def chiedi(d):
            domande.append(d)
            return next(risposte)
        args = argparse.Namespace(passi="", saltati="", si=False, rapido=True)
        righe = []
        codice = I.cmd_inizia(args, righe.append, chiedi=chiedi)
        testo = "\n".join(righe)
        self.assertEqual(codice, 1)
        self.assertIn("Scrivere queste modifiche?", domande[-1])
        self.assertFalse((self.client / "jan.json").exists())
        self.assertIn("Passi non completati: 4 chat", testo)
        self.assertIn("Chat: non configurata ancora", testo)

    def test_passo_1_non_si_ferma_per_modello_e_progetto(self):
        righe = []
        self.assertEqual(I.stato_ambiente(argparse.Namespace(rapido=True), righe.append), 0, "\n".join(righe))

    def test_riepilogo_non_dice_pronto_se_manca_il_progetto(self):
        codice, testo = self.inizia([], passi="5")
        self.assertEqual(codice, 1)
        self.assertIn("Progetto: nessuno ancora", testo)
        self.assertIn("Manca ancora:", testo)
        self.assertNotIn("Tutto pronto", testo)


if __name__ == "__main__":
    unittest.main()

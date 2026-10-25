"""
Test dei progetti di ricerca separati dal motore (progetto.py): disposizione storica, progetto scelto da
config.ini o dalla variabile d'ambiente, impostazioni di progetto.ini, creazione di un progetto nuovo.
Configurazioni temporanee: il config.ini vero non conta.
"""
import argparse
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))
import progetto as P  # noqa: E402


class Progetto(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._env = os.environ.pop(P.VARIABILE, None)

    def tearDown(self):
        os.environ.pop(P.VARIABILE, None)
        if self._env is not None:
            os.environ[P.VARIABILE] = self._env
        self._tmp.cleanup()

    def config(self, testo):
        f = self.tmp / "config.ini"
        f.write_text(testo, encoding="utf-8")
        return P.leggi_config(f)

    def test_disposizione_storica(self):
        cfg = self.config("[percorsi]\ndati = ../data\nrisultati = /altrove/risultati\n")
        self.assertEqual(P.percorso(cfg, "dati"), (PIPELINE / "../data").resolve())
        self.assertEqual(P.percorso(cfg, "entita"), PIPELINE / "entita.ini")
        self.assertEqual(P.percorso(cfg, "serie"), PIPELINE / "serie.ini")
        # indice, lavori, risposte accanto a risultati; importazioni accanto a data
        self.assertEqual(P.percorso(cfg, "lavori"), Path("/altrove/lavori").resolve())
        self.assertEqual(P.percorso(cfg, "indice"), Path("/altrove/indice/fonti.sqlite").resolve())
        self.assertEqual(P.percorso(cfg, "importazioni"), (PIPELINE.parent / "importazioni").resolve())

    def test_progetto_da_config_con_progetto_ini(self):
        radice = self.tmp / "ricerca"
        radice.mkdir()
        (radice / "progetto.ini").write_text("[progetto]\nnome = Stampa albanese\n[percorsi]\nentita = schede/e.ini\n"
                                             "[estrazione]\nfinestra = 300\n", encoding="utf-8")
        cfg = self.config(f"[progetto]\ncartella = {radice}\n[percorsi]\ndati = ../data\n[estrazione]\nfinestra = 400\n")
        self.assertEqual(P.percorso(cfg, "dati"), (radice / "data").resolve())           # [percorsi] di config.ini ignorati
        self.assertEqual(P.percorso(cfg, "entita"), (radice / "schede" / "e.ini").resolve())
        self.assertEqual(P.percorso(cfg, "lavori"), (radice / "lavori").resolve())
        self.assertEqual(cfg.get("estrazione", "finestra"), "300")                         # progetto.ini prevale
        self.assertEqual(P.nome(cfg), "Stampa albanese")

    def test_variabile_d_ambiente_prevale(self):
        a, b = self.tmp / "a", self.tmp / "b"
        os.environ[P.VARIABILE] = str(b)
        cfg = self.config(f"[progetto]\ncartella = {a}\n")
        self.assertEqual(P.percorso(cfg, "risultati"), (b / "risultati").resolve())

    def test_percorsi_assoluti_per_le_prove(self):
        cfg = self.config(f"[progetto]\ncartella = {self.tmp / 'r'}\n")
        tutti = P.percorsi_assoluti(cfg)
        self.assertEqual(set(tutti), set(P.PERCORSI))
        self.assertTrue(all(Path(v).is_absolute() for v in tutti.values()))

    def test_nuovo_progetto(self):
        radice = self.tmp / "nuovo"
        with redirect_stdout(io.StringIO()):
            P.cmd_nuovo(argparse.Namespace(cartella=str(radice), nome="Prova", descrizione=""))
        for p in ("data", "risultati/_archivio", "risposte", "lavori", "importazioni", "entita.ini", "serie.ini",
                  "progetto.ini", "audit_fonti/problemi_residui.csv", "audit_fonti/registro_modifiche.csv"):
            self.assertTrue((radice / p).exists(), p)
        self.assertTrue((radice / "audit_fonti/registro_modifiche.csv").read_bytes().startswith(b"\xef\xbb\xbffile,"))
        self.assertTrue((radice / "audit_fonti/registro_modifiche.csv").read_bytes().endswith(b"\r\n"))
        serie = (radice / "serie.ini").read_text(encoding="utf-8")
        self.assertIn("periodicita", serie)
        self.assertNotIn("[Renmin Ribao]", serie)                  # solo la descrizione dei campi, nessuna serie
        with self.assertRaises(SystemExit):                        # cartella non vuota: non si tocca
            P.cmd_nuovo(argparse.Namespace(cartella=str(radice), nome="", descrizione=""))


if __name__ == "__main__":
    unittest.main()

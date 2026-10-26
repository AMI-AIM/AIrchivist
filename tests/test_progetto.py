"""
Test dei progetti di ricerca separati dal motore (progetto.py): senza progetto valgono solo i percorsi scritti,
progetto scelto da config.ini o dalla variabile d'ambiente, impostazioni di project.ini, creazione di un progetto
nuovo. Configurazioni temporanee: il config.ini vero non conta.
"""
import argparse
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOTORE))
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

    def test_senza_progetto(self):
        """Senza progetto scelto valgono solo i percorsi scritti in [percorsi]; per gli altri il motore chiede
        di scegliere o di creare un progetto (la disposizione storica accanto al motore non c'è più)."""
        cfg = self.config("[percorsi]\ndati = ../data\nrisultati = /altrove/results\n")
        self.assertEqual(P.percorso(cfg, "dati"), (MOTORE / "../data").resolve())
        self.assertEqual(P.cartella_ricerche(cfg), Path("/altrove/results/searches").resolve())
        for chiave in ("entita", "lavori", "indice"):
            with self.assertRaises(P.NessunProgetto):
                P.percorso(cfg, chiave)
        self.assertEqual(P.nome(cfg), "nessun progetto")

    def test_progetto_da_config_con_project_ini(self):
        radice = self.tmp / "ricerca"
        radice.mkdir()
        (radice / "project.ini").write_text("[progetto]\nnome = Stampa albanese\n[percorsi]\nentita = schede/e.ini\n"
                                            "[estrazione]\nfinestra = 300\n", encoding="utf-8")
        cfg = self.config(f"[progetto]\ncartella = {radice}\n[percorsi]\ndati = ../data\n[estrazione]\nfinestra = 400\n")
        self.assertEqual(P.percorso(cfg, "dati"), (radice / "data").resolve())           # [percorsi] di config.ini ignorati
        self.assertEqual(P.percorso(cfg, "entita"), (radice / "schede" / "e.ini").resolve())
        self.assertEqual(P.percorso(cfg, "serie"), (radice / "glossary" / "series.ini").resolve())
        self.assertEqual(P.percorso(cfg, "lavori"), (radice / "system" / "jobs").resolve())
        self.assertEqual(P.percorso(cfg, "indice"), (radice / "system" / "index" / "sources.sqlite").resolve())
        self.assertEqual(P.percorso(cfg, "risposte"), (radice / "results" / "answers").resolve())
        self.assertEqual(P.cartella_ricerche(cfg), (radice / "results" / "searches").resolve())
        self.assertEqual(cfg.get("estrazione", "finestra"), "300")                         # project.ini prevale
        self.assertEqual(P.nome(cfg), "Stampa albanese")

    def test_variabile_d_ambiente_prevale(self):
        a, b = self.tmp / "a", self.tmp / "b"
        os.environ[P.VARIABILE] = str(b)
        cfg = self.config(f"[progetto]\ncartella = {a}\n")
        self.assertEqual(P.percorso(cfg, "risultati"), (b / "results").resolve())

    def test_percorsi_assoluti_per_le_prove(self):
        cfg = self.config(f"[progetto]\ncartella = {self.tmp / 'r'}\n")
        tutti = P.percorsi_assoluti(cfg)
        self.assertEqual(set(tutti), set(P.PERCORSI))
        self.assertTrue(all(Path(v).is_absolute() for v in tutti.values()))

    def test_nuovo_progetto(self):
        radice = self.tmp / "nuovo"
        with redirect_stdout(io.StringIO()):
            P.cmd_nuovo(argparse.Namespace(cartella=str(radice), nome="Prova", descrizione=""))
        for p in ("project.ini", "glossary/entities.ini", "glossary/series.ini", "glossary/instructions.md",
                  "sources", "data", "audit/changes.csv", "audit/open_issues.csv", "audit/checks",
                  "results/archive", "results/searches", "results/answers", "system/index", "system/jobs",
                  "system/backups"):
            self.assertTrue((radice / p).exists(), p)
        self.assertTrue((radice / "audit/changes.csv").read_bytes().startswith(b"\xef\xbb\xbffile,"))
        self.assertTrue((radice / "audit/changes.csv").read_bytes().endswith(b"\r\n"))
        serie = (radice / "glossary/series.ini").read_text(encoding="utf-8")
        self.assertIn("periodicita", serie)
        self.assertNotIn("[Renmin Ribao]", serie)                  # solo la descrizione dei campi, nessuna serie
        with self.assertRaises(SystemExit):                        # cartella non vuota: non si tocca
            P.cmd_nuovo(argparse.Namespace(cartella=str(radice), nome="", descrizione=""))


if __name__ == "__main__":
    unittest.main()

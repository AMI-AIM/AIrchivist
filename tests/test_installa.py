"""
Test dell'installazione e del controllo dell'ambiente (installa.py): esito dei controlli, servizio dei modelli
senza chiave o non raggiungibile, avvio guidato su una configurazione come quella di una copia pulita. Nessuna rete né installazione vera.
"""
import argparse
import configparser
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
                     "chiave_env = PRESSMARK_CHIAVE_DI_PROVA\n")
        os.environ.pop("PRESSMARK_CHIAVE_DI_PROVA", None)
        I.controlla_modelli(self.esito, cfg)
        self.assertEqual(self.esito.mancanti, ["modelli: router"])
        self.assertIn("PRESSMARK_CHIAVE_DI_PROVA", self.righe[0])

    def test_servizio_spento(self):
        cfg = config("[modello]\nbackend = ollama\n[ollama]\nurl = http://127.0.0.1:9\n")
        I.controlla_modelli(self.esito, cfg)
        self.assertEqual(self.esito.mancanti, ["modelli: ollama"])
        self.assertIn("avvia Ollama", self.righe[0])

    def test_istruzioni_per_sistema(self):
        from importa import come_installare_tesseract
        self.assertIn("winget", come_installare_tesseract("win32"))
        self.assertIn("brew", come_installare_tesseract("darwin"))
        self.assertIn("apt", come_installare_tesseract("linux"))
        self.assertIn("setx X", I.come_salvare_variabile("X", "win32"))
        self.assertIn("export X=", I.come_salvare_variabile("X", "darwin"))
        self.assertIn("~/.zprofile", I.come_salvare_variabile("X", "darwin"))
        self.assertIn("~/.profile", I.come_salvare_variabile("X", "linux"))


class AvvioGuidato(unittest.TestCase):
    """installa.py inizia con la configurazione di una copia pulita del repository: il progetto indicato in
    config.ini non esiste e il profilo scelto non è in models.ini. Servizio dei modelli finto."""
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.config = self.tmp / "config.ini"
        self.config.write_text(f"[progetto]\ncartella = {(self.tmp / 'inesistente').as_posix()}\n\n[modello]\n"
                               f"file_profili = {(self.tmp / 'models.ini').as_posix()}\nprofilo = assente\n",
                               encoding="utf-8")
        (self.tmp / "models.ini").write_text("[locale]\nservizio = ollama\nmodello = m\n", encoding="utf-8")
        finti = {"FILE_CONFIG": self.config, "prova_profilo": lambda cfg, nome, stampa: True,
                 "cartella_progetti": lambda: self.tmp / "projects",
                 "controlla_modelli": lambda esito, cfg: esito("ok", "modelli", "finto")}
        for nome, valore in finti.items():
            p = mock.patch.object(I, nome, valore)
            p.start()
            self.addCleanup(p.stop)
        env = mock.patch.dict(os.environ, {})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop("PRESSMARK_PROGETTO", None)

    def inizia(self, risposte, **opzioni):
        r = iter(risposte)
        righe = []
        args = argparse.Namespace(**{"passi": "", "saltati": "", "si": False, **opzioni})
        codice = I.cmd_inizia(args, righe.append, chiedi=lambda _d: next(r))
        return codice, "\n".join(righe)

    def test_copia_pulita_fino_al_riepilogo(self):
        # passo 2: profilo «locale»; passo 3: nome, cartella proposta, conferma; passo 4: riepilogo
        codice, testo = self.inizia(["1", "Ricerca di prova", "", ""])
        self.assertEqual(codice, 0, testo)
        self.assertIn("non esiste (o non è un progetto): ne creo uno", testo)
        progetto = self.tmp / "projects" / "Ricerca_di_prova"
        self.assertTrue((progetto / "project.ini").is_file())
        cfg = self.config.read_text(encoding="utf-8")
        self.assertIn(f"cartella = {progetto.resolve()}", cfg)
        self.assertIn("profilo = locale", cfg)
        self.assertFalse((self.tmp / "inesistente").exists())            # nessuna cartella fantasma
        self.assertIn("python importa.py proponi", testo)                  # comando che esiste
        self.assertTrue(testo.rstrip().endswith("Tutto pronto."))

    def test_cartella_del_progetto_come_nome(self):
        # un nome solo al posto del percorso: il progetto va nella cartella dei progetti, non in quella corrente
        codice, testo = self.inizia(["La mia tesi", "tesi", ""], passi="3")
        self.assertEqual(codice, 0, testo)
        self.assertTrue((self.tmp / "projects" / "tesi" / "project.ini").is_file())

    def test_passo_1_non_si_ferma_per_modello_e_progetto(self):
        righe = []
        self.assertEqual(I.stato_ambiente(argparse.Namespace(), righe.append), 0, "\n".join(righe))

    def test_riepilogo_non_dice_pronto_se_manca_il_progetto(self):
        codice, testo = self.inizia([], passi="4")
        self.assertEqual(codice, 1)
        self.assertIn("Progetto: nessuno ancora", testo)
        self.assertIn("Manca ancora:", testo)
        self.assertNotIn("Tutto pronto", testo)


if __name__ == "__main__":
    unittest.main()

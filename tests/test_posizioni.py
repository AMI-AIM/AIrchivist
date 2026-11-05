"""
Test delle posizioni dei file dell'utente (posizioni.py, applicazione installabile, fase 1):
- modo sviluppo: profili in scripts, progetti in projects/; le scelte dell'utente in config.utente.ini (fuori da
  git), letto sopra il config.ini pubblico, che non si modifica;
- modo installato (PRESSMARK_DATI o installazione.ini): le scelte dell'utente nel suo config.ini, letto sopra i
  valori predefiniti del programma, che non si modificano mai; models.ini e progetti nuovi fuori dal programma;
- un file indicato a mano (prove, --config) si legge da solo anche da installato;
- l'interfaccia, da installato, scrive il progetto scelto nella cartella dell'utente.
I valori predefiniti del programma sono un config.ini temporaneo: quello vero non conta.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOTORE))
import installa as I  # noqa: E402
import llm  # noqa: E402
import posizioni as Q  # noqa: E402
import progetto as P  # noqa: E402

BASE = "[modello]\nprofilo = predefinito\nmax_token = 4000\n\n[progetto]\ncartella =\n\n[estrazione]\nfinestra = 200\n"


class Posizioni(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self._env = {k: os.environ.pop(k, None) for k in (Q.VARIABILE_DATI, P.VARIABILE)}
        self.base = self.tmp / "programma" / "config.ini"
        self.base.parent.mkdir()
        self.base.write_text(BASE, encoding="utf-8")
        self.base_prima = self.base.read_bytes()
        self.marcatore = self.tmp / "programma" / "installazione.ini"      # assente: modo sviluppo
        self.utente = self.tmp / "programma" / "config.utente.ini"
        self._patch = [mock.patch.object(Q, "CONFIG_BASE", self.base),
                       mock.patch.object(Q, "CONFIG_SVILUPPO", self.utente),
                       mock.patch.object(Q, "FILE_INSTALLAZIONE", self.marcatore)]
        for p in self._patch:
            p.start()

    def tearDown(self):
        for p in self._patch:
            p.stop()
        for k, v in self._env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v
        self._tmp.cleanup()

    def installa_in(self, nome="dati"):
        dati = self.tmp / nome
        os.environ[Q.VARIABILE_DATI] = str(dati)
        return dati

    def test_sviluppo(self):
        """Senza marcatore né variabile: tutto accanto al codice, come prima."""
        self.assertFalse(Q.installato())
        self.assertEqual(Q.cartella_dati(), Q.CARTELLA)
        # le scelte dell'utente in un file fuori da git, sopra il config.ini pubblico
        self.assertEqual(Q.file_config(), self.utente)
        self.assertEqual(Q.file_profili(), Q.CARTELLA / "models.ini")
        self.assertEqual(Q.cartella_progetti(), Q.CARTELLA.parent / "projects")
        self.assertEqual(Q.file_letti(), [self.base, self.utente])
        self.assertEqual(llm.file_profili(P.leggi_config(self.base)), Q.CARTELLA / "models.ini")

    def test_sviluppo_non_scrive_nel_config_pubblico(self):
        """Nel repository le scelte vanno in config.utente.ini: config.ini (sotto git) resta identico."""
        I.imposta_voci(Q.file_config(), "modello", {"profilo": "mio"})
        self.assertTrue(self.utente.is_file())
        self.assertEqual(self.base.read_bytes(), self.base_prima)
        cfg = P.leggi_config()
        self.assertEqual(cfg.get("modello", "profilo"), "mio")
        self.assertEqual(cfg.get("modello", "max_token"), "4000")

    def test_installato_legge_sopra_i_predefiniti(self):
        dati = self.installa_in()
        self.assertTrue(Q.installato())
        self.assertEqual(Q.file_config(), dati / "config.ini")
        # senza file dell'utente valgono i predefiniti
        cfg = P.leggi_config()
        self.assertEqual(cfg.get("modello", "profilo"), "predefinito")
        self.assertIsNone(P.cartella_scelta(cfg))
        dati.mkdir()
        (dati / "config.ini").write_text("[modello]\nprofilo = mio\n", encoding="utf-8")
        cfg = P.leggi_config()
        self.assertEqual(cfg.get("modello", "profilo"), "mio")            # la scelta dell'utente prevale
        self.assertEqual(cfg.get("modello", "max_token"), "4000")         # il resto dai predefiniti
        self.assertEqual(cfg.get("estrazione", "finestra"), "200")
        # lo stesso file indicato per nome (come fanno installa.FILE_CONFIG e l'interfaccia)
        self.assertEqual(P.leggi_config(dati / "config.ini").get("modello", "max_token"), "4000")

    def test_file_indicato_a_mano_da_solo(self):
        """Le prove e --config indicano un file completo: niente predefiniti sotto, anche da installato."""
        self.installa_in()
        f = self.tmp / "prova.ini"
        f.write_text("[modello]\nprofilo = prova\n", encoding="utf-8")
        self.assertEqual(Q.file_letti(f), [f])
        cfg = P.leggi_config(f)
        self.assertEqual(cfg.get("modello", "profilo"), "prova")
        self.assertFalse(cfg.has_option("modello", "max_token"))

    def test_scrittura_solo_nella_cartella_dell_utente(self):
        """Il primo salvataggio crea la cartella dei dati; il config.ini del programma resta identico."""
        dati = self.installa_in("nuova/annidata")
        progetto = self.tmp / "ricerca"
        P.cmd_nuovo(mock.Mock(cartella=str(progetto), nome="Ricerca", descrizione=""), stampa=lambda t: None)
        I.imposta_voci(Q.file_config(), "progetto", {"cartella": str(progetto)})
        I.imposta_voci(Q.file_config(), "modello", {"profilo": "mio"})
        self.assertTrue((dati / "config.ini").is_file())
        self.assertEqual(self.base.read_bytes(), self.base_prima)
        cfg = P.leggi_config()
        self.assertEqual(P.cartella_scelta(cfg), progetto.resolve())
        self.assertEqual(P.nome(cfg), "Ricerca")
        self.assertEqual(cfg.get("modello", "profilo"), "mio")
        self.assertEqual(cfg.get("estrazione", "finestra"), "200")

    def test_profili_dei_modelli(self):
        dati = self.installa_in()
        self.assertEqual(llm.file_profili(P.leggi_config()), dati / "models.ini")
        dati.mkdir()
        (dati / "config.ini").write_text("[modello]\nfile_profili = altri.ini\n", encoding="utf-8")
        self.assertEqual(llm.file_profili(P.leggi_config()), dati / "altri.ini")
        I.aggiungi_profilo(dati / "models.ini", "mio", {"servizio": "openai", "modello": "m"})
        (dati / "config.ini").write_text("[modello]\nprofilo = mio\n", encoding="utf-8")
        self.assertIn("mio", llm.leggi_profili(P.leggi_config()))

    def test_marcatore_dell_installatore(self):
        """installazione.ini senza voci: cartella del sistema e Documenti/Pressmark; con le voci: dove indicate
        (relative alla cartella del programma, per la copia portatile)."""
        self.marcatore.write_text("[installazione]\n", encoding="utf-8")
        with mock.patch.object(Q, "documenti", return_value=self.tmp / "Documenti"):
            self.assertTrue(Q.installato())
            self.assertEqual(Q.cartella_dati(), Q.cartella_sistema())
            self.assertEqual(Q.cartella_progetti(), self.tmp / "Documenti" / "Pressmark")
        self.marcatore.write_text("[installazione]\ndati = dati\nprogetti = %s\n" % (self.tmp / "Ricerche"),
                                  encoding="utf-8")
        self.assertEqual(Q.cartella_dati(), (Q.CARTELLA.parent / "dati").resolve())
        self.assertEqual(Q.cartella_progetti(), self.tmp / "Ricerche")
        os.environ[Q.VARIABILE_DATI] = str(self.tmp / "altrove")            # la variabile prevale
        self.assertEqual(Q.cartella_dati(), self.tmp / "altrove")

    def test_cartella_del_sistema(self):
        casa = Path.home()
        with mock.patch.dict(os.environ, {"APPDATA": str(self.tmp / "Roaming")}):
            self.assertEqual(Q.cartella_sistema("win32"), self.tmp / "Roaming" / "Pressmark")
        self.assertEqual(Q.cartella_sistema("darwin"), casa / "Library" / "Application Support" / "Pressmark")
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.tmp / "cfg")}):
            self.assertEqual(Q.cartella_sistema("linux"), self.tmp / "cfg" / "pressmark")
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("XDG_CONFIG_HOME", None)
            self.assertEqual(Q.cartella_sistema("linux"), casa / ".config" / "pressmark")
        self.assertTrue(Q.documenti().is_absolute())

    def test_cartella_col_nome_di_prima(self):
        roaming = self.tmp / "Roaming"
        (roaming / "AIrchivist").mkdir(parents=True)
        with mock.patch.dict(os.environ, {"APPDATA": str(roaming)}):
            self.assertEqual(Q.cartella_sistema("win32"), roaming / "AIrchivist")   # c'è solo quella di prima
            (roaming / "Pressmark").mkdir()
            self.assertEqual(Q.cartella_sistema("win32"), roaming / "Pressmark")    # la nuova prevale
        cfg = self.tmp / "cfg"
        (cfg / "airchivist").mkdir(parents=True)
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(cfg)}):
            self.assertEqual(Q.cartella_sistema("linux"), cfg / "airchivist")

    def test_interfaccia_da_installato(self):
        """L'interfaccia apre la configurazione dell'utente, propone i progetti nella sua cartella e vi scrive la
        scelta del progetto, lasciando intatto il config.ini del programma."""
        import app as A
        dati = self.installa_in()
        progetti = self.tmp / "Documenti" / "Pressmark"
        progetto = progetti / "Prima"
        P.cmd_nuovo(mock.Mock(cartella=str(progetto), nome="Prima", descrizione=""), stampa=lambda t: None)
        vecchio = I.FILE_CONFIG
        try:
            with mock.patch.object(Q, "documenti", return_value=self.tmp / "Documenti"):
                app = A.App()
            self.assertEqual(app.config, dati / "config.ini")
            self.assertEqual(app.cartella_progetti, progetti)
            self.assertEqual([Path(p["cartella"]) for p in app.progetti()], [progetto.resolve()])
            app._scrivi_progetto(progetto.resolve())
            self.assertEqual(P.cartella_scelta(P.leggi_config()), progetto.resolve())
            os.environ.pop(P.VARIABILE, None)                              # lo legge dal file, non dalla variabile
            self.assertEqual(P.cartella_scelta(P.leggi_config()), progetto.resolve())
            self.assertEqual(self.base.read_bytes(), self.base_prima)
        finally:
            I.FILE_CONFIG = vecchio


if __name__ == "__main__":
    unittest.main()

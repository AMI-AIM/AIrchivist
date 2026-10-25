"""
Test del controllo delle schede (schede.py) sulle forme ambigue che non sono tra le varianti, e dell'avviso del
server MCP quando la chat crea una scheda così. Schede in una cartella temporanea.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))
import schede as S  # noqa: E402

SCHEDA = """[Enrico Berlinguer]
tipo = persona
varianti = Enrico Berlinguer; 恩里科·贝林格; 贝林格
forme_ambigue = Berlinguer; 贝林格
note = Dirigente del PCI.
"""


class FormeAmbigue(unittest.TestCase):
    def test_non_cercate(self):
        self.assertEqual(S.ambigue_non_cercate(["Enrico Berlinguer", "贝林格"], ["Berlinguer", "贝林格"]),
                         ["Berlinguer"])
        self.assertEqual(S.ambigue_non_cercate(["Ber-linguer"], ["Berlinguer"]), [])     # stessa forma normalizzata
        self.assertEqual(S.ambigue_non_cercate(["Berlinguer"], []), [])

    def test_controlla(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "entita.ini"
            f.write_text(SCHEDA, encoding="utf-8")
            avvisi = [p for g, s, p in S.controlla(f) if s == "Enrico Berlinguer" and "forma ambigua" in p]
        self.assertEqual(len(avvisi), 1)
        self.assertIn("«Berlinguer»", avvisi[0])
        self.assertIn("non la cerca", avvisi[0])


class CreazioneDallaChat(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        radice = Path(self._tmp.name)
        (radice / "entita.ini").write_text("", encoding="utf-8")
        (radice / "serie.ini").write_text("", encoding="utf-8")
        self._env = os.environ.get("AIRCHIVIST_PROGETTO")
        os.environ["AIRCHIVIST_PROGETTO"] = str(radice)
        import mcp_server
        self.M = mcp_server

    def tearDown(self):
        if self._env is None:
            os.environ.pop("AIRCHIVIST_PROGETTO", None)
        else:
            os.environ["AIRCHIVIST_PROGETTO"] = self._env
        self._tmp.cleanup()

    def test_avviso_alla_creazione(self):
        out = self.M.t_crea_scheda("Enrico Berlinguer", ["Enrico Berlinguer", "贝林格"],
                                   forme_ambigue=["Berlinguer", "贝林格"], tipo="persona")
        self.assertEqual(out["scheda"], "Enrico Berlinguer")
        self.assertIn("Berlinguer", out["avviso"])
        self.assertNotIn("贝林格", out["avviso"])

    def test_nessun_avviso(self):
        out = self.M.t_crea_scheda("Fosco Dinucci", ["Fosco Dinucci", "Dinucci"], forme_ambigue=["Dinucci"])
        self.assertNotIn("avviso", out)


if __name__ == "__main__":
    unittest.main()

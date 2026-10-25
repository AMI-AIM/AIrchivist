"""
Test dell'anno delle date nelle sintesi (25/10/2026): regola del prompt di analisi (classifica.py), date sospette
nell'archivio e loro rilettura (archivio.py date_sospette, classifica.da_completare). Caso reale: Renmin ribao
del 2 agosto 1979, «贝林格十月访问莫斯科以后», letto come «ottobre 1979». Senza modelli.
"""
import configparser
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import archivio as A  # noqa: E402
import classifica as K  # noqa: E402

ORIGINALE = "而且在贝林格十月访问莫斯科以后同意大利共产党的关系有了改善"
LETTURA = {"pertinente": "sì", "citazione_testuale": ORIGINALE, "traduzione_it": "dopo la visita di Berlinguer a Mosca "
           "in ottobre", "sintesi_it": "Enrico Berlinguer visitò Mosca nell'ottobre 1979.",
           "provenienza": {"decisione": {"livello": "modello", "da": "m"}, "lettura": {"livello": "modello", "da": "m"}}}


class Regola(unittest.TestCase):
    def test_prompt(self):
        rec = {"entita": "Enrico Berlinguer", "fonte": "Renmin ribao", "data": "1979-08-02",
               "passaggio_evidenziato": ORIGINALE, "passaggio": ORIGINALE}
        p = K.prompt_analisi(rec, {"note": ""}, ORIGINALE)
        self.assertIn("data: 1979-08-02", p)
        self.assertIn("anno precedente", p)
        self.assertIn("(anno non indicato)", p)
        self.assertNotIn("ricavandolo se necessario dalla data della fonte", p)


class DateSospette(unittest.TestCase):
    def test_caso_berlinguer(self):
        self.assertEqual([d for d, _ in A.date_sospette(LETTURA, "1979-08-02")], ["ottobre 1979"])

    def test_non_sospette(self):
        a = dict(LETTURA, sintesi_it="Visitò Mosca nell'ottobre 1978; il 3 aprile 1979 fu rieletto.")
        self.assertEqual(A.date_sospette(a, "1979-08-02"), [])                 # anno precedente, o prima della fonte
        a = dict(LETTURA, sintesi_it="Visiterà la Cina in ottobre 1979.", citazione_testuale="一九七九年十月访华")
        self.assertEqual(A.date_sospette(a, "1979-08-02"), [])                 # anno scritto nell'originale
        a = dict(LETTURA, sintesi_it="Il 20 agosto 1979 parlò a Roma.")
        self.assertEqual(A.date_sospette(a, "1979-08-02"), [])                 # stesso mese: non si decide
        self.assertEqual(A.date_sospette(LETTURA, ""), [])                     # fonte senza data

    def test_anno_nel_testo(self):
        self.assertTrue(A.anno_nel_testo(1979, "一九七九年"))
        self.assertTrue(A.anno_nel_testo(1960, "一九六○年"))
        self.assertTrue(A.anno_nel_testo(1979, "in 1979"))
        self.assertFalse(A.anno_nel_testo(1979, "十月"))


class Rilettura(unittest.TestCase):
    def test_da_completare(self):
        self.assertIsNone(K.da_completare(LETTURA))
        self.assertEqual(K.da_completare(dict(LETTURA, da_rileggere="analisi")), "analisi")
        incerto = dict(LETTURA, pertinente="incerto", da_rileggere="analisi")
        self.assertIsNone(K.da_completare(incerto))                            # solo i pertinenti
        a_mano = dict(LETTURA, da_rileggere="analisi", corretto_a_mano=True)
        self.assertIsNone(K.da_completare(a_mano))

    def test_piano_e_applica(self):
        with tempfile.TemporaryDirectory() as tmp:
            radice = Path(tmp)
            (radice / "data").mkdir()
            (radice / "data" / "rr.txt").write_text("[DATE: 1979-08-02]\n\n" + ORIGINALE + "\n", encoding="utf-8")
            sessione = dict(LETTURA, provenienza={"decisione": {"livello": "sessione"}, "lettura": {"livello": "sessione"}})
            voci = [{"id": "a1", "entita": "Enrico Berlinguer", "file": "rr.txt", "impronta": "x1", "analisi": LETTURA},
                    {"id": "a2", "entita": "Enrico Berlinguer", "file": "rr.txt", "impronta": "x2", "analisi": sessione}]
            arch_dir = radice / "risultati" / "_archivio"
            arch_dir.mkdir(parents=True)
            (arch_dir / "letture.jsonl").write_text("".join(json.dumps(v, ensure_ascii=False) + "\n" for v in voci),
                                                    encoding="utf-8")
            cfg = configparser.ConfigParser(interpolation=None)
            cfg["percorsi"] = {"dati": str(radice / "data"), "risultati": str(radice / "risultati"),
                               "backup": str(radice / "backup")}
            righe, nuove = A.piano_date_sospette(cfg)
            self.assertEqual(sorted(r["esito"] for r in righe), ["da controllare a mano", "da rileggere"])
            self.assertEqual([v["id"] for v in nuove], ["a1"])                 # le letture in sessione non si toccano
            import io
            from contextlib import redirect_stdout
            with redirect_stdout(io.StringIO()):
                A.segna_date_sospette(cfg, applica=True)
            a, _ = A.Archivio(radice / "risultati").cerca({"id": "a1", "entita": "Enrico Berlinguer"})
            self.assertEqual(K.da_completare(a), "analisi")
            righe, nuove = A.piano_date_sospette(cfg)                          # già segnata: non si ripete
            self.assertEqual(nuove, [])


if __name__ == "__main__":
    unittest.main()

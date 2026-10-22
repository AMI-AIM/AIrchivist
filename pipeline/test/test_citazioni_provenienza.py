"""
Test delle citazioni in stile Chicago (citazioni.py), della provenienza delle letture (archivio.py) e delle
funzioni di calcolo dello strumento di valutazione (valutazione.py). Senza corpus né modelli.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import citazioni as C  # noqa: E402
from archivio import descrivi_provenienza, livello, provenienza  # noqa: E402
import valutazione as V  # noqa: E402


class Citazioni(unittest.TestCase):
    def test_periodico_con_volume_numero_data_pagina(self):
        meta = {"SERIES": "Peking Review", "VOLUME": "X", "ISSUE": "11", "DATE": "1967-03-10"}
        self.assertEqual(C.citazione(meta, "riviste/peking_review/PR1967-11.txt", "5"),
                         "*Peking Review* 10, no. 11 (10 marzo 1967): 5")

    def test_data_inattendibile_diventa_anno(self):
        meta = {"SERIES": "Peking Review", "VOLUME": "X", "ISSUE": "11", "DATE": "1967-03-10", "YEAR": "1967",
                "METADATA_SOURCE": "filename+local_header"}
        self.assertEqual(C.citazione(meta, "riviste/peking_review/PR1967-11.txt"), "*Peking Review* 10, no. 11 (1967)")

    def test_numero_doppio_e_supplemento(self):
        self.assertEqual(C.citazione({"SERIES": "Hongqi", "ISSUE": "10-11", "YEAR": "1963"}),
                         "*Hongqi* 红旗, nos. 10–11 (1963)")
        meta = {"SERIES": "Peking Review", "VOLUME": "XVI", "ISSUE": "41", "DATE": "1973-10-12",
                "FULL_CITATION": "Peking Review (1973), no. 41, supplement"}
        self.assertEqual(C.citazione(meta), "*Peking Review* 16, no. 41, supplement (12 ottobre 1973)")

    def test_volume_senza_profilo(self):
        meta = {"SERIES": "关于国际共产主义运动总路线的论战", "PUBLISHER": "人民出版社", "PUBLICATION_PLACE": "北京",
                "YEAR": "1965"}
        self.assertEqual(C.citazione(meta, "fonti_primarie/x.txt", "12"), "*关于国际共产主义运动总路线的论战* (北京: 人民出版社, 1965), 12")

    def test_traduzione_jprs(self):
        meta = {"SERIES": "Red Flag", "ISSUE": "10", "DATE": "1977-10-08", "REPORT_DATE": "1977-12-01",
                "JPRS_ID": "70256"}
        self.assertEqual(C.citazione(meta), "Joint Publications Research Service, JPRS 70256 (1 dicembre 1977), "
                                            "trad. ingl. di *Hongqi* 红旗, no. 10 (8 ottobre 1977)")

    def test_pagina_dal_marcatore_e_dal_profilo(self):
        testo = "[SERIES: X]\n\n[[p. 11]]\ntesto\n[[p. 12 | pdf 17]]\nqui il nome\n[[p. 13]]\n"
        self.assertEqual(C.pagina_nel_testo(testo, testo.index("qui")), "12")
        self.assertEqual(C.pagina_nel_testo("[[p. s.n.]]\nnome", 14), "")
        rmrb = "第1版()\n专栏：\n...\n第4版()\n专栏：\n弗朗茨"
        self.assertEqual(C.pagina_nel_testo(rmrb, rmrb.index("弗"), {"pagina_regex": r"第\s*(\d+)\s*版"}), "4")

    def test_mai_file_ne_riga(self):
        meta = {"SERIES": "Renmin Ribao", "DATE": "1971-07-09"}
        cit = C.citazione(meta, "riviste/renmin_ribao/1971-07-09.txt", "5")
        self.assertEqual(cit, "*Renmin ribao* 人民日报, 9 luglio 1971, 5")
        self.assertNotIn(".txt", cit)


class Provenienza(unittest.TestCase):
    def test_letture_di_un_modello(self):
        p = provenienza({"pertinente": "sì", "modello_smistamento": "m1", "modello_analisi": "m2",
                         "traduzione_it": "testo"})
        self.assertEqual(p, {"decisione": livello("modello", "m1"), "lettura": livello("modello", "m2")})

    def test_regola_e_non_tradotto(self):
        p = provenienza({"pertinente": "sì", "classificato_da": "lettura manuale",
                         "tipo_menzione": "menzione (classificazione per regola)"})
        self.assertEqual(p["decisione"]["livello"], "regola")
        self.assertIsNone(p["lettura"])
        self.assertIn("non tradotto", descrivi_provenienza(p))

    def test_forma_inequivocabile(self):
        p = provenienza({"pertinente": "sì", "modello_smistamento": "regola (forma inequivocabile)",
                         "modello_analisi": "m2", "traduzione_it": "x"})
        self.assertEqual(p["decisione"], livello("regola", "forma inequivocabile"))

    def test_sessione_e_correzione(self):
        self.assertEqual(provenienza({"pertinente": "sì", "classificato_da": "lettura manuale",
                                      "traduzione_it": "x"})["lettura"]["livello"], "sessione")
        self.assertEqual(provenienza({"pertinente": "no", "corretto_a_mano": True,
                                      "classificato_da": "correzione manuale"})["decisione"]["da"],
                         "correzione dalla chat")

    def test_provenienza_registrata_prevale(self):
        reg = {"decisione": livello("regola", "x"), "lettura": None}
        self.assertIs(provenienza({"provenienza": reg, "modello_smistamento": "m"}), reg)


class Valutazione(unittest.TestCase):
    def test_wilson(self):
        a, b = V.wilson(12, 12)
        self.assertGreater(a, 0.7)
        self.assertEqual(b, 1.0)
        self.assertIsNone(V.wilson(0, 0))

    def test_forme_larghe(self):
        rx = V.forme_larghe(["弗朗茨·施特罗伯尔", "Franz Strobl"])
        for t in ("第一书记施特罗伯尔的唁函", "Strobi", "Ströbl", "Franz"):
            self.assertTrue(rx.search(V.senza_accenti(t)), t)
        self.assertFalse(rx.search("Strobllandia"))

    def test_misure(self):
        m = V.misure([("sì", "sì"), ("sì", "incerto"), ("sì", "no"), ("no", "sì"), ("no", "no")])
        self.assertEqual(m["richiamo"], (2, 3))
        self.assertEqual(m["richiamo_stretto"], (1, 3))
        self.assertEqual(m["precisione"], (1, 2))


if __name__ == "__main__":
    unittest.main()

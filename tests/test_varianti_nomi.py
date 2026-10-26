"""
Test del generatore di varianti dei nomi (varianti_nomi.py): indizi tradotti, trascrizioni cinesi sul modello
Xinhua, nomi di partito. I casi sono forme reali del progetto (schede confermate e fonti), senza corpus.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import varianti_nomi as V  # noqa: E402


class Indizi(unittest.TestCase):
    def test_paesi_in_tutte_le_lingue(self):
        self.assertEqual(V.indizi_tradotti(["Italian", "Italy"]), ["意大利", "意共"])
        self.assertEqual(V.indizi_tradotti(["partito belga"]), ["比利时", "比共"])
        self.assertEqual(V.indizi_tradotti(["Shqipëria"]), ["阿尔巴尼亚", "阿劳动党"])
        self.assertEqual(V.indizi_tradotti(["Communist Party of Austria (Marxist-Leninist)"]), ["奥地利", "奥共"])
        self.assertEqual(V.indizi_tradotti(["comunismo dissidente"]), [])


class Trascrizioni(unittest.TestCase):
    CASI = {          # nome -> forma attestata nelle fonti o confermata in una scheda
        "Berlinguer": "贝林格", "Enrico Berlinguer": "恩里科·贝林格", "Grippa": "格里巴",
        "Jacques Grippa": "雅克·格里巴", "Dinucci": "迪努齐", "Fosco Dinucci": "福斯科·迪努齐", "Gracci": "格拉齐",
        "Pesce": "贝契", "Osvaldo Pesce": "奥斯瓦尔多·贝契", "Strobl": "施特罗伯尔", "Duse": "杜塞",
        "Désiré Trifaux": "德西雷·特里福", "Regis": "雷吉斯", "Dini": "迪尼", "Misefari": "米塞法里",
    }

    def test_forme_reali_tra_le_varianti(self):
        for nome, attesa in self.CASI.items():
            with self.subTest(nome=nome):
                cognome = attesa.split("·")[-1]
                # esplora_nome combina il nome proprio con i cognomi trovati nelle fonti
                self.assertIn(attesa, V.trascrizioni_cinesi(nome, cognomi=[cognome] if "·" in attesa else None))
                self.assertIn(cognome, V.trascrizioni_cinesi(nome.split()[-1]))

    def test_varianti_limitate(self):
        for nome in self.CASI:
            self.assertLessEqual(len(V.trascrivi(nome.split()[-1])), V.MASSIMO_VARIANTI)

    def test_grafia_fonetica(self):
        self.assertIn("berlinger", V.fonetica("Berlinguer"))            # gu davanti a e: g dura
        self.assertNotIn("berlinjer", V.fonetica("Berlinguer"))
        self.assertIn("dinuchi", V.fonetica("Dinucci"))                  # cci italiano
        self.assertIn("jak", V.fonetica("Jacques"))                      # finale francese muta
        self.assertIn("shtrobl", V.fonetica("Strobl"))                   # st tedesco iniziale


class Partiti(unittest.TestCase):
    def test_partiti_marxisti_leninisti(self):
        forme = V.partiti_cinesi("Communist Party of Italy (Marxist-Leninist)")
        for attesa in ("意大利共产党（马克思列宁主义）", "意大利共产党（马列）", "意大利（马列）共产党", "意共（马列）"):
            self.assertIn(attesa, forme)
        self.assertEqual(V.partiti_cinesi("Marxist-Leninist Party of Austria")[:2],
                         ["奥地利马克思列宁主义党", "奥地利马列主义党"])
        self.assertEqual(V.partiti_cinesi("Partito comunista del Belgio"), ["比利时共产党"])
        self.assertEqual(V.partiti_cinesi("Nuova Unità"), [])


if __name__ == "__main__":
    unittest.main()

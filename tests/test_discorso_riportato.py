"""
Test delle regole su chi dice che cosa e sulle note dei curatori nei prompt della lettura
(classifica.py) e della sintesi (sintesi.py). Caso reale della prova del 3/11/2026: in un rapporto della Legazione
albanese a Roma Dinucci racconta la biografia di un comunista di Udine («Deri më 1952 ka qenë social demokrat»),
e la risposta l'ha attribuita a Dinucci. Senza modelli: si controlla che cosa riceve il modello.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import classifica as K  # noqa: E402
import sintesi as S  # noqa: E402

PASSAGGIO = ("atëherë unë tha ⟦Dinuçi⟧ i thash se jam komunist i vjetër, ish drejtues në parti, partizan e komandant, "
             "por ju kur jini bërë komunist. Atëherë tregoj ⟦Dinuçi⟧ ai më kallzoj. Deri më 1952 ka qenë social "
             "demokrat.")
REC = {"entita": "Fosco Dinucci", "fonte": "Raccolta", "data": "1964-04-12", "passaggio_evidenziato": PASSAGGIO,
       "passaggio": PASSAGGIO.replace("⟦", "").replace("⟧", "")}


class Lettura(unittest.TestCase):
    def test_regola_nel_prompt_di_analisi(self):
        p = K.prompt_analisi(REC, {"note": ""}, "Atëherë tregoj Dinuçi ai më kallzoj.")
        self.assertIn("Chi dice che cosa", p)
        self.assertIn("riferisce che [altra persona]", p)
        self.assertNotIn("NOTA DEI CURATORI", p)

    def test_nota_dei_curatori_nei_prompt(self):
        nota = dict(REC, apparato="nota")
        for p in (K.prompt_analisi(nota, {"note": ""}, "x"),
                  K.prompt_smistamento(nota, {"note": "", "varianti": ["Dinuçi"]}),
                  K.prompt_lotto([nota], {"note": "", "varianti": ["Dinuçi"]})):
            self.assertIn("NOTA DEI CURATORI", p)


class Sintesi(unittest.TestCase):
    def test_regole_nel_prompt_dei_dati_espliciti(self):
        visti = []

        class Finto:
            def json(self, sistema, utente, schema):
                visti.append(utente)
                return {}

        voce = dict(REC, analisi={"citazione_verificata": True, "sintesi_it": "Dinucci riferisce che il comunista "
                                  "di Udine era socialdemocratico fino al 1952.", "traduzione_it": "…"})
        nota = dict(REC, apparato="nota", analisi={"citazione_verificata": True, "sintesi_it": "Secondo la nota "
                                                   "dei curatori, Dinucci visse dal 1921 al 1993.", "traduzione_it": ""})
        docs = [{"n": 1, "rif": "Pani, Jordan. “Informacion.”", "voci": [voce, nota]}]
        S.scrivi_con_modello(Finto(), "Fosco Dinucci", "", docs)
        self.assertIn("il dato è il racconto dell'entità", visti[0])
        self.assertIn("Secondo la nota dei curatori,", visti[0])
        righe = [r for r in visti[0].splitlines() if r.startswith("[1]")]
        self.assertEqual(len(righe), 2)
        self.assertNotIn("NOTA DEI CURATORI DELL'EDIZIONE, non testo", righe[0])
        self.assertIn("NOTA DEI CURATORI DELL'EDIZIONE, non testo", righe[1])


if __name__ == "__main__":
    unittest.main()

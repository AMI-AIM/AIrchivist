"""
Test della forma delle risposte JSON dei modelli (llm.py): oggetto, elenco con un oggetto, elenco da mettere
sotto l'unica proprietà elenco dello schema, forme non utilizzabili. Senza modelli.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from classifica import SCHEMA_ANALISI, SCHEMA_LOTTO  # noqa: E402
from llm import ErroreModello, come_oggetto, estrai_json  # noqa: E402


class FormaJson(unittest.TestCase):
    def test_oggetto(self):
        self.assertEqual(come_oggetto({"tono": "neutro"}, SCHEMA_ANALISI), {"tono": "neutro"})

    def test_elenco_con_un_oggetto(self):
        # 25/10/2026: un modello ha risposto [{...}] all'analisi e la ricerca si è fermata
        dati = estrai_json('[{"tipo_menzione": "citazione", "traduzione_it": "..."}]')
        self.assertEqual(come_oggetto(dati, SCHEMA_ANALISI)["tipo_menzione"], "citazione")

    def test_elenco_del_lotto(self):
        dati = [{"n": 1, "pertinente": "sì"}, {"n": 2, "pertinente": "no"}]
        self.assertEqual(come_oggetto(dati, SCHEMA_LOTTO), {"risultati": dati})

    def test_forme_inutilizzabili(self):
        for dati in ([{"a": 1}, {"b": 2}], ["sì"], [], "sì", 3, None):
            with self.assertRaises(ErroreModello):
                come_oggetto(dati, SCHEMA_ANALISI)


if __name__ == "__main__":
    unittest.main()

"""
Test del nome del file dei documenti datati senza data. Nella prova del
3/11/2026 il documento senza data, con anno 1962 indicato nella tabella, diventava «MPs.d.-relacion….txt»:
con l'anno il nome comincia con l'anno (MP1962-…). I documenti delle raccolte si distinguono per titolo, come
quelli d'archivio: due documenti con la stessa data non finiscono nello stesso file.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import importa as I  # noqa: E402


class NomeFile(unittest.TestCase):
    def test_anno_al_posto_di_sd(self):
        scheda = {"tipo": "archivio", "sigla": "MP"}
        valori = {"anno": "1962", "data_iso": "", "titolo": "Relacion i Legates"}
        self.assertEqual(I.nome_file(scheda, "Serie", valori, "x"), "MP1962-relacion_i_legates.txt")
        scheda = {"tipo": "periodico", "sigla": "MP"}
        self.assertEqual(I.nome_file(scheda, "Serie", {"anno": "1962", "data_iso": ""}, "relacion"),
                         "MP1962-relacion.txt")

    def test_la_data_prevale_sull_anno(self):
        scheda = {"tipo": "periodico", "sigla": "MP"}
        self.assertEqual(I.nome_file(scheda, "Serie", {"anno": "1962", "data_iso": "1962-07-04"}, "x"),
                         "MP1962-07-04.txt")
        self.assertEqual(I.nome_file(scheda, "Serie", {"anno": "1962", "data_iso": "1962-07", "numero": "5"}, "x"),
                         "MP1962-07-n5.txt")

    def test_senza_anno_ne_data(self):
        scheda = {"tipo": "periodico", "sigla": "MP"}
        self.assertEqual(I.nome_file(scheda, "Serie", {"anno": "", "data_iso": ""}, "relacion pa date"),
                         "MPs.d.-relacion_pa_date.txt")
        self.assertEqual(I.nome_file(scheda, "Serie", {"anno": "s.d.", "data_iso": ""}, "x"), "MPs.d.-x.txt")

    def test_raccolta_stessa_data_titoli_diversi(self):
        scheda = {"tipo": "raccolta", "sigla": "MP"}
        a = I.nome_file(scheda, "Serie", {"data_iso": "1964-07-04", "titolo": "Relacion mbi takimin"}, "x")
        b = I.nome_file(scheda, "Serie", {"data_iso": "1964-07-04", "titolo": "Informacion mbi takimin"}, "y")
        self.assertNotEqual(a, b)
        self.assertTrue(a.startswith("MP1964-07-04-"))


if __name__ == "__main__":
    unittest.main()

"""
Test specifici per il punto B4 della roadmap: segnatura d'archivio e tipo 'raccolta'.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import revisione as R
import profili as P


class TestSegnatura(unittest.TestCase):
    """B4: estrazione della segnatura d'archivio dalle ultime pagine."""

    def test_segnatura_con_AQSH(self):
        """Test estrazione segnatura AQSH (esempio dal roadmap)."""
        testo = "Pagine di testo... [AQSH, F. 14/APMP ML Itali, V. 1964, D. 1, fl. 9-12]"
        m = R.SEGNATURA.search(testo)
        self.assertTrue(m, "La regex deve trovare la segnatura AQSH")
        self.assertIn("AQSH", m.group(0))
        self.assertIn("F. 14/APMP", m.group(0))

    def test_nessuna_segnatura(self):
        """Test quando non c'è segnatura."""
        testo = "Testo senza segnatura"
        m = R.SEGNATURA.search(testo)
        self.assertFalse(m, "La regex non deve trovare nulla")


class TestRaccolta(unittest.TestCase):
    """B4: tipo serie 'raccolta' per documenti con segnature d'archivio pubblicate in un volume curato."""

    def test_proposta_raccolta_con_segnature(self):
        """Proposta automatica del tipo 'raccolta' quando i documenti hanno segnature."""
        # Documenti fittizi con testatina, data e segnatura (formato dal roadmap B4)
        # Importante: segnatura deve essere non vuota per essere conteggiata
        doc1 = {
            "file": [Path("doc1.pdf")],
            "a": {
                "formato": "PDF", "testo": "scansione", "qualita_ocr": "media",
                "pagine_pdf": 5, "inizio": "Chiave testo di inizio\n", "fine": "[AQSH, F. 1/1, D. 1, fl. 1-3]",
                "meta": {}, "pagine": "1-3", "nota_pagine": "", "stato_pagine": "dedotto",
                "dubbi": [], "etichette": False, "segnatura": "AQSH, F. 1/1, D. 1, fl. 1-3"
            },
            "data_nome": "1964-01-01", "numero_nome": "", "dubbio_nome": "",
            "g": {"file": [Path("doc1.pdf")]},
            "stem": "doc1", "schema": "DOC#"
        }
        doc2 = {
            "file": [Path("doc2.pdf")],
            "a": {
                "formato": "PDF", "testo": "scansione", "qualita_ocr": "media",
                "pagine_pdf": 4, "inizio": "Altro testo\n", "fine": "[AQSH, F. 1/1, D. 1, fl. 4-6]",
                "meta": {}, "pagine": "4-6", "nota_pagine": "", "stato_pagine": "dedotto",
                "dubbi": [], "etichette": False, "segnatura": "AQSH, F. 1/1, D. 1, fl. 4-6"
            },
            "data_nome": "1964-02-01", "numero_nome": "", "dubbio_nome": "",
            "g": {"file": [Path("doc2.pdf")]},
            "stem": "doc2", "schema": "DOC#"
        }

        proposta = R.proponi_serie("raccolta_test", [doc1, doc2], {})
        # Con segnature entrambi i doc, il tipo deve essere raccolta
        self.assertEqual(proposta["tipo_serie"], "raccolta",
                         f"Atteso 'raccolta', ma c'è '{proposta['tipo_serie']}'. Dubbi: {proposta['dubbi']}")
        self.assertTrue(proposta["cartella_serie"].startswith("raccolte/"))

    def test_proposta_non_raccolta_senza_segnature(self):
        """Se i documenti non hanno segnature, non viene proposto il tipo 'raccolta'."""
        doc1 = {
            "file": [Path("doc1.pdf")],
            "a": {
                "formato": "PDF", "testo": "scansione", "qualita_ocr": "media",
                "pagine_pdf": 5, "inizio": "Some text\n", "fine": "",
                "meta": {}, "pagine": "1-3", "nota_pagine": "", "stato_pagine": "dedotto",
                "dubbi": [], "etichette": False, "segnatura": ""
            },
            "data_nome": "1964-01-01", "numero_nome": "", "dubbio_nome": "",
            "g": {"file": [Path("doc1.pdf")]},
            "stem": "doc1", "schema": "DOC#"
        }
        doc2 = {
            "file": [Path("doc2.pdf")],
            "a": {
                "formato": "PDF", "testo": "scansione", "qualita_ocr": "media",
                "pagine_pdf": 4, "inizio": "Other text\n", "fine": "",
                "meta": {}, "pagine": "4-6", "nota_pagine": "", "stato_pagine": "dedotto",
                "dubbi": [], "etichette": False, "segnatura": ""
            },
            "data_nome": "1964-02-01", "numero_nome": "", "dubbio_nome": "",
            "g": {"file": [Path("doc2.pdf")]},
            "stem": "doc2", "schema": "DOC#"
        }

        proposta = R.proponi_serie("normale_test", [doc1, doc2], {})
        # Senza segnature, non deve essere raccolta
        self.assertNotEqual(proposta["tipo_serie"], "raccolta",
                            f"Senza segnature, atteso diverso da 'raccolta', ma è '{proposta['tipo_serie']}'")


if __name__ == "__main__":
    unittest.main()
"""
Test per il punto C2 della roadmap: gestione errori di formato JSON inatteso.

C2 Osservato: Un modello ha risposto con un elenco JSON invece di un oggetto: il passaggio è saltato,
la ricerca è uscita con codice 3 e andava rilanciata a mano per un solo passaggio.

C2 Obiettivo: Il passaggio si riprova nello stesso lancio (anche con un altro modello della catena)
prima di lasciarlo; la ricerca si ferma solo se restano passaggi dopo i nuovi tentativi.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from llm import ErroreModello, come_oggetto


class TestJsonFormato(unittest.TestCase):
    """C2: test per la gestione del formato JSON inatteso."""

    def test_come_oggetto_con_dizionario(self):
        """Un dizionario passato in viene restituito così com'è."""
        dati = {"chiave": "valore"}
        risultato = come_oggetto(dati, {})
        self.assertEqual(risultato, dati)

    def test_come_oggetto_con_elenco_unico(self):
        """Un elenco con un singolo oggetto viene restituito come oggetto."""
        dati = [{"chiave": "valore"}]
        schema = {"properties": {"risultati": {"type": "array"}}}
        risultato = come_oggetto(dati, schema)
        self.assertEqual(risultato, {"risultati": [{"chiave": "valore"}]})

    def test_come_oggetto_errore_forma_inattesa(self):
        """Un elenco con molti oggetti solleva ErroreModello."""
        dati = [{"id": 1}, {"id": 2}, {"id": 3}]
        try:
            come_oggetto(dati, None)
            self.fail("Dovrebbe sollevare ErroreModello")
        except ErroreModello as e:
            self.assertIn("forma inattesa", str(e))

    def test_come_oggetto_stringa_non_json(self):
        """Una stringa non JSON solleva ErroreModello."""
        try:
            come_oggetto("questo non è JSON", None)
            self.fail("Dovrebbe sollevare ErroreModello")
        except ErroreModello as e:
            self.assertIn("forma inattesa", str(e))

    def test_estrai_json_da_testo_con_json_incollato(self):
        """Estragge JSON da testo con parole prima e dopo."""
        from llm import estrai_json
        testo = "Ecco la risposta:\n{\"chiave\": \"valore\"}\nFine."
        risultato = estrai_json(testo)
        self.assertEqual(risultato, {"chiave": "valore"})

    def test_estrai_json_manca_json(self):
        """Se manca JSON, solleva ErroreModello."""
        from llm import estrai_json
        try:
            estrai_json("nessun JSON qui")
            self.fail("Dovrebbe sollevare ErroreModello")
        except ErroreModello as e:
            self.assertIn("non contiene JSON", str(e))


if __name__ == "__main__":
    unittest.main()
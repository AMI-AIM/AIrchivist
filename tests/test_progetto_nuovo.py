"""
Test dei difetti emersi nella prova di un progetto nuovo con PDF (25/10/2026, Larrabee, «Whither Albania?», The
World Today 1978): modello di istruzioni.md, titolo degli articoli dei periodici, punteggiatura dopo «?» nelle
citazioni, articoli con note a piè di pagina presi per sommari. Senza modelli né PDF.
"""
import argparse
import configparser
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOTORE))
import citazioni as C  # noqa: E402
import classifica as K  # noqa: E402
import importa as I  # noqa: E402
import istruzioni  # noqa: E402
import progetto as P  # noqa: E402


class IstruzioniDelProgetto(unittest.TestCase):
    def test_modello_tutto_commentato(self):
        self.assertEqual(istruzioni._righe_progetto(P.ISTRUZIONI_VUOTO), "")      # nulla arriva alla chat

    def test_progetto_nuovo_senza_regole(self):
        with tempfile.TemporaryDirectory() as tmp:
            radice = Path(tmp) / "nuovo"
            with redirect_stdout(io.StringIO()):
                P.cmd_nuovo(argparse.Namespace(cartella=str(radice), nome="Prova", descrizione=""))
            testo = (radice / "glossary" / "instructions.md").read_text(encoding="utf-8")
        self.assertEqual(istruzioni._righe_progetto(testo), "")


SERIE = """[The World Today]
tipo = periodico
lingua = en
cartella = riviste/the_world_today
sigla = WT
citazione = The World Today[, vol. {volume}][, n. {numero}], {data}
chicago = {autore}. "{titolo}." *The World Today*[ {volume}][, {numero_lbl}] ({data_o_anno})[: {pagina}]
"""


class ArticoloDiPeriodico(unittest.TestCase):
    def test_titolo_e_citazione(self):
        with tempfile.TemporaryDirectory() as tmp:
            radice = Path(tmp)
            (radice / "serie.ini").write_text(SERIE, encoding="utf-8")
            (radice / "articolo.txt").write_text("Whither Albania?\nOf all the countries in Eastern Europe Albania "
                                                 "has been the least affected by the winds of change.\n" * 3,
                                                 encoding="utf-8")
            cfg = configparser.ConfigParser(interpolation=None)
            cfg["percorsi"] = {"dati": str(radice / "data"), "risultati": str(radice / "risultati"),
                               "entita": str(radice / "entita.ini"), "serie": str(radice / "serie.ini"),
                               "problemi": str(radice / "p.csv"),
                               "importazioni": str(radice / "audit" / "checks"),
                               "registro_importazioni": str(radice / "audit" / "imports.csv"),
                               "cache": str(radice / "system" / "cache"),
                               "originali": str(radice / "sources")}
            originale, I.leggi_config = I.leggi_config, lambda: cfg
            try:
                with redirect_stdout(io.StringIO()):
                    codice = I.main(["importa", str(radice / "articolo.txt"), "--serie", "The World Today",
                                     "--data", "1978-02-15", "--autore", "Larrabee, F. Stephen",
                                     "--titolo", "Whither Albania?", "--volume", "34", "--numero", "2",
                                     "--senza-indice"])
            finally:
                I.leggi_config = originale
            testo = next((radice / "data").rglob("*.txt")).read_text(encoding="utf-8")
        self.assertEqual(codice, 0)
        self.assertIn("[TITLE: Whither Albania?]", testo)
        self.assertIn('[FULL_CITATION: Larrabee, F. Stephen. "Whither Albania?" *The World Today* 34, no. 2', testo)
        meta = {"SERIES": "The World Today", "TITLE": "Whither Albania?", "AUTHOR": "Larrabee, F. Stephen",
                "VOLUME": "34", "ISSUE": "2", "YEAR": "1978"}
        cit = C.componi(SERIE.split("chicago = ")[1].strip(), dict(C.valori_da_intestazione(meta, {}), pagina="63"))
        self.assertEqual(cit, 'Larrabee, F. Stephen. "Whither Albania?" *The World Today* 34, no. 2 (1978): 63')

    def test_punteggiatura(self):
        self.assertEqual(C.dopo_punto_interrogativo('"Whither Albania?."'), '"Whither Albania?"')
        self.assertEqual(C.dopo_punto_interrogativo("*Who Rules?*, 1980"), "*Who Rules?* 1980")
        self.assertEqual(C.dopo_punto_interrogativo("Tirana: 8 Nëntori, 1982."), "Tirana: 8 Nëntori, 1982.")


def passaggio(testo):
    return {"passaggio_evidenziato": testo}


class Sommari(unittest.TestCase):
    def test_articolo_con_note_non_e_sommario(self):
        # Larrabee, The World Today 1978: numeri di nota attaccati al testo, date, piè di pagina di JSTOR
        t = ("Albania's aid if it were attacked. 11SeePravda, 26 October 1076. 18In an apparent reference to "
             "our ship.' (Radio Tirana, 8 November 1976.) 66 This content downloaded on Sun, 30 Aug 2026 "
             "Premier ⟦Mehmet Shehu⟧ was even more categorical in rejecting any improvement in relations")
        self.assertFalse(K.e_sommario(passaggio(t)))

    def test_note_dopo_una_data(self):
        # Peking Review 1964, no. 6: elenco di note con rimandi dopo le date
        t = ("Le Drapeau Rouge, July 26, 1960.14“The Belgian Communist Party and the Congress,” Le Drapeau Rouge, "
             "Apr. 22, 1958.15 Speech by Jean Blume on Dec. 3, 1961, cited by ⟦Jacques Grippa⟧ in “For the Unity”")
        self.assertFalse(K.e_sommario(passaggio(t)))

    def test_sommari_veri(self):
        # Peking Review 1980, no. 17 e 1969, no. 45; 1975, no. 23 («Hsiang Jung 23» non è una data)
        for t in ("ARTICLES AND DOCUMENTSVisit of Italian C. P. Delegation: Comrade Hua Guofeng's Toast 14 Comrade "
                  "⟦Enrico Berlinguer⟧'s Toast 4 Deng Xiaoping Meets Italian Journalists 15 General Secretary",
                  "Greetings From Central Committee of ⟦Communist Party of Belgium⟧ (Marxist-Leninist)The Hell With "
                  "Nixon's \"Reasonable Step\". 27ROUND THE WORLD 28Italy: Three 5 Struggles",
                  "Leadership — Hsiao Lou 22“Big Drama — Hsiang Jung 23 NATO: Summit Meeting ⟦Communist Party of "
                  "Germany⟧ (M-L): Kremlin Rulers ON THE HOME FRONT 30 Working Class"):
            self.assertTrue(K.e_sommario(passaggio(t)), t[:40])


if __name__ == "__main__":
    unittest.main()

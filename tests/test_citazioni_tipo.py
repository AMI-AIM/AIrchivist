"""
Test delle serie con meno campi e della citazione Chicago generata dal tipo (lavoro 30): un profilo di tre campi
(nome, tipo, lingua) ha cartella e sigla predefinite e produce una nota Chicago corretta per ogni tipo (periodico,
quotidiano, articolo, volume, archivio); autori nella forma della nota; una serie minima creata e usata per
importare un documento.
"""
import argparse
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOTORE))
import citazioni as C  # noqa: E402
import importa as I  # noqa: E402
import profili as P  # noqa: E402
from estrai_occorrenze import leggi_intestazione  # noqa: E402
from progetto import VARIABILE, cmd_nuovo  # noqa: E402


def nota(profilo, meta, pagina="3", nome=None):
    p = P.completa(nome or meta.get("SERIES", "Serie"), profilo)
    v = C.valori_da_intestazione(meta, p)
    v["pagina"] = pagina
    return C.componi(C.modello_di(p, meta), v)


class CitazioneDalTipo(unittest.TestCase):
    def test_quotidiano(self):
        self.assertEqual(nota({"tipo": "periodico", "lingua": "sq"},
                              {"SERIES": "Zëri i Popullit", "DATE": "1967-01-12"}),
                         "*Zëri i Popullit*, 12 gennaio 1967, 3")

    def test_articolo_di_rivista(self):
        meta = {"SERIES": "The American Historical Review", "VOLUME": "121", "ISSUE": "2", "DATE": "2016-04",
                "TITLE": "The Transnational and the Text-Searchable", "AUTHOR": "Putnam, Lara"}
        attesa = ("Lara Putnam, “The Transnational and the Text-Searchable,” *The American Historical Review* 121, "
                  "no. 2 (aprile 2016): 377")
        self.assertEqual(nota({"tipo": "periodico", "lingua": "en"}, meta, "377"), attesa)
        self.assertEqual(nota({"tipo": "articolo", "lingua": "en"}, meta, "377"), attesa)

    def test_titolo_con_punto_interrogativo(self):
        meta = {"SERIES": "The World Today", "VOLUME": "34", "ISSUE": "2", "DATE": "1978-02",
                "TITLE": "Whither Albania?", "AUTHOR": "Larrabee, F. Stephen"}
        self.assertEqual(nota({"tipo": "articolo", "lingua": "en"}, meta, "63"),
                         "F. Stephen Larrabee, “Whither Albania?” *The World Today* 34, no. 2 (febbraio 1978): 63")

    def test_fascicolo_con_numero(self):
        self.assertEqual(nota({"tipo": "periodico", "lingua": "en"},
                              {"SERIES": "Peking Review", "ISSUE": "11", "YEAR": "1967"}, ""),
                         "*Peking Review*, no. 11 (1967)")

    def test_volume(self):
        meta = {"SERIES": "Vepra", "TITLE": "Vepra", "AUTHOR": "Hoxha, Enver", "VOLUME": "II",
                "PUBLICATION_PLACE": "Tirana", "PUBLISHER": "Naim Frashëri", "YEAR": "1969"}
        self.assertEqual(nota({"tipo": "volume", "lingua": "sq"}, meta, "45"),
                         "Enver Hoxha, *Vepra*, vol. 2 (Tirana: Naim Frashëri, 1969), 45")

    def test_archivio(self):
        meta = {"SERIES": "Central Intelligence Agency", "AUTHOR": "Central Intelligence Agency",
                "TITLE": "Chinese Support for Foreign Communist Parties", "DATE": "1971-03-03",
                "CALL_NUMBER": "CIA-RDP85T00875R001100010023-9"}
        profilo = {"tipo": "archivio", "lingua": "en", "archivio": "CIA FOIA Electronic Reading Room"}
        self.assertEqual(nota(profilo, meta, "12"),
                         "Central Intelligence Agency, “Chinese Support for Foreign Communist Parties,” 3 marzo 1971, "
                         "CIA-RDP85T00875R001100010023-9, CIA FOIA Electronic Reading Room, 12")
        # senza archivio nel profilo: il nome della serie
        self.assertTrue(nota({"tipo": "archivio", "lingua": "en"}, meta, "").endswith(", Central Intelligence Agency"))

    def test_il_campo_chicago_prevale(self):
        profilo = {"tipo": "periodico", "lingua": "zh", "chicago": "*Renmin ribao* 人民日报, {data_o_anno}[, {pagina}]"}
        self.assertEqual(nota(profilo, {"SERIES": "Renmin Ribao", "DATE": "1967-01-12", "TITLE": "x"}),
                         "*Renmin ribao* 人民日报, 12 gennaio 1967, 3")


class Autori(unittest.TestCase):
    def test_forma_della_nota(self):
        casi = {"Larrabee, F. Stephen": "F. Stephen Larrabee", "Central Intelligence Agency": "Central Intelligence Agency",
                "Mao Tse-tung": "Mao Tse-tung", "Hufe, Lorenz, et al.": "Lorenz Hufe et al.",
                "Hufe, Lorenz; Griesshaber, Niclas": "Lorenz Hufe and Niclas Griesshaber",
                "A, B; C, D; E, F": "B A, D C, and F E", "A, B; C, D; E, F; G, H": "B A et al.", "": ""}
        for autore, attesa in casi.items():
            self.assertEqual(C.nome_in_nota(autore), attesa, autore)


class ProfiloMinimo(unittest.TestCase):
    def test_valori_predefiniti(self):
        self.assertEqual(P.completa("Zëri i Popullit", {"tipo": "periodico", "lingua": "sq"}),
                         {"tipo": "periodico", "lingua": "sq", "cartella": "riviste/zeri_i_popullit", "sigla": "ZP"})
        self.assertEqual(P.completa("Vepra", {"tipo": "volume", "lingua": "sq"})["cartella"], "volumi/vepra")
        self.assertNotIn("sigla", P.completa("Vepra", {"tipo": "volume", "lingua": "sq"}))
        self.assertEqual(P.completa("Central Intelligence Agency", {"tipo": "archivio"})["cartella"],
                         "archivi/central_intelligence_agency")
        scritto = P.completa("X", {"tipo": "periodico", "cartella": "riviste/altro", "sigla": "AB"})
        self.assertEqual((scritto["cartella"], scritto["sigla"]), ("riviste/altro", "AB"))

    def test_serie_minima_creata_e_usata(self):
        tmp = Path(tempfile.mkdtemp())
        with redirect_stdout(io.StringIO()):
            cmd_nuovo(argparse.Namespace(cartella=str(tmp / "progetto"), nome="Prova", descrizione=""))
        with mock.patch.dict(os.environ, {VARIABILE: str(tmp / "progetto")}):
            P.tutti(ricarica=True)
            self.addCleanup(lambda: P.tutti(ricarica=True))
            self.assertIn("aggiunta", I.aggiungi_serie("The World Today", "articolo", "en"))
            testo = (tmp / "progetto" / "glossary" / "series.ini").read_text(encoding="utf-8")
            self.assertTrue(testo.rstrip().endswith("[The World Today]\ntipo = articolo\nlingua = en"))
            self.assertIn("tipo deve essere", I.aggiungi_serie("Altra", "rivista", "en"))
            f = tmp / "Larrabee.txt"
            f.write_text("The Albanian leadership has insisted on its own road. " * 20, encoding="utf-8")
            with redirect_stdout(io.StringIO()) as uscita:
                codice = I.main(["importa", str(f), "--serie", "The World Today", "--data", "1978-02",
                                 "--titolo", "Whither Albania?", "--autore", "Larrabee, F. Stephen", "--volume", "34",
                                 "--numero", "2", "--senza-indice"])
            self.assertEqual(codice, 0, uscita.getvalue())
            scritto = next((tmp / "progetto" / "data" / "riviste" / "the_world_today").glob("*.txt"))
            self.assertEqual(scritto.name, "TWT1978-02-n2-whither_albania.txt")
            meta = leggi_intestazione(scritto.read_text(encoding="utf-8"))[0]
            self.assertEqual(meta["FULL_CITATION"],
                             "F. Stephen Larrabee, “Whither Albania?” *The World Today* 34, no. 2 (febbraio 1978)")


if __name__ == "__main__":
    unittest.main()

"""
Test dei profili di serie (profili.py) e delle regole che ne dipendono (cronologia, sintesi, ricerca): una serie
nuova, descritta solo nel suo profilo, deve funzionare come quelle già presenti. Profili finti, senza corpus.
"""
import csv
import datetime as dt
import sys
import tempfile
import unittest
from pathlib import Path

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOTORE))
import cronologia as CR  # noqa: E402
import profili as P  # noqa: E402
import ricerca as R  # noqa: E402
import sintesi as S  # noqa: E402

FINTI = {
    "Zëri i Popullit": {"tipo": "periodico", "cartella": "riviste/zeri_i_popullit", "sigla": "ZP",
                        "periodo": "1960-01-01 / 1990-12-31", "periodicita": "quotidiano", "righe_intere": "sì",
                        "nota_limiti": "La stampa albanese registra ciò che Tirana sceglieva di pubblicare."},
    "Rruga e Partisë": {"tipo": "periodico", "cartella": "riviste/rruga_e_partise", "sigla": "RP",
                        "periodo": "1960-01-01 / 1975-12-31", "periodicita": "mensile; 1970: quindicinale",
                        "gruppo": "Stampa del PPSH"},
    "Bashkimi": {"tipo": "periodico", "cartella": "riviste/bashkimi", "gruppo": "Stampa del PPSH",
                 "pagina_regex": r"Faqe\s+(\d+)", "allinea_con": "Zëri i Popullit", "allinea_giorni": "7"},
    "Dokumente": {"tipo": "volume", "cartella": "dokumente", "gruppo": "documenti"},
    "Dokumente PPSH": {"tipo": "volume", "cartella": "dokumente/ppsh"},
}


class ConProfiliFinti(unittest.TestCase):
    def setUp(self):
        self._originali = P._PROFILI
        P._PROFILI = FINTI

    def tearDown(self):
        P._PROFILI = self._originali


class Profili(ConProfiliFinti):
    def test_profilo_per_serie_o_per_cartella(self):
        self.assertEqual(P.nome_di("Zëri i Popullit", "altrove/x.txt"), "Zëri i Popullit")
        self.assertEqual(P.nome_di("", "riviste/zeri_i_popullit/ZP1967-01-12.txt"), "Zëri i Popullit")
        self.assertEqual(P.nome_di("", "dokumente/ppsh/v1.txt"), "Dokumente PPSH")      # la cartella più specifica
        self.assertEqual(P.nome_di("", "dokumente/altro/v1.txt"), "Dokumente")
        self.assertEqual(P.nome_di("Ignota", "riviste/ignota/x.txt"), "")

    def test_gruppi(self):
        self.assertEqual(P.serie_del_gruppo("stampa del ppsh"), {"Rruga e Partisë", "Bashkimi"})
        self.assertEqual(P.serie_del_gruppo("Bashkimi"), {"Rruga e Partisë", "Bashkimi"})
        self.assertEqual(P.serie_del_gruppo("Ignota"), {"Ignota"})
        self.assertEqual((P.serie_breve("Bashkimi"), P.serie_breve("中共中央文件选集")),
                         ("Stampa del PPSH", "中共中央文件选集"))

    def test_periodo_e_periodicita(self):
        self.assertEqual(P.periodo("Rruga e Partisë"), (dt.date(1960, 1, 1), dt.date(1975, 12, 31)))
        self.assertEqual(P.fine_fonti(), dt.date(1990, 12, 31))
        self.assertEqual(P.fine_fonti({"Rruga e Partisë"}), dt.date(1975, 12, 31))
        self.assertEqual((P.periodicita("Rruga e Partisë", 1965), P.periodicita("Rruga e Partisë", 1972)),
                         ("mensile", "quindicinale"))
        self.assertEqual((P.mese_del_numero("Rruga e Partisë", 1965, 5), P.mese_del_numero("Rruga e Partisë", 1972, 5)),
                         (5, 3))
        self.assertIsNone(P.mese_del_numero("Zëri i Popullit", 1965, 5))          # quotidiano: c'è la data

    def test_pagine_righe_intere_allineamenti(self):
        self.assertEqual(P.ultima_pagina("Faqe 2 ... Faqe 3 testo", "Bashkimi"), "3")
        self.assertEqual(P.ultima_pagina("第3版", "Zëri i Popullit"), "")
        self.assertEqual(P.righe_intere(), {"Zëri i Popullit"})
        self.assertEqual(P.allineamenti(), [("Bashkimi", "Zëri i Popullit", 7)])


def passaggio(fonte, file, data, entita="X", data_interna=False):
    c = {"id": file + data, "entita": entita, "fonte": fonte, "file": file, "data": data, "offset": 1,
         "riga": 1, "analisi": {"pertinente": "sì"}}
    if data_interna is not False:
        c["data_interna"] = data_interna
    return c


class Regole(ConProfiliFinti):
    def test_serie_nuova_nella_cronologia(self):
        p = [passaggio("Zëri i Popullit", "riviste/zeri_i_popullit/ZP1966-03-01.txt", "1966-03-01"),
             passaggio("Zëri i Popullit", "riviste/zeri_i_popullit/ZP1967-01-12.txt", "1967-01-12"),
             passaggio("Rruga e Partisë", "riviste/rruga_e_partise/RP1965-5.txt", "1965")]
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "problemi.csv"
            with open(f, "w", encoding="utf-8-sig", newline="") as out:
                w = csv.writer(out)
                w.writerow(["serie", "file", "problema", "dettaglio"])
                w.writerow(["Zëri i Popullit", "riviste/zeri_i_popullit/ZP1966-07-01.txt", "giorno mancante", ""])
                w.writerow(["Zëri i Popullit", "riviste/zeri_i_popullit/ZP1980-01-01.txt", "giorno mancante", ""])
            cr = CR.calcola(p, "X", problemi=f)
            fatti = CR.fatti(cr)
        self.assertEqual(cr["estremi"]["X"][:3], (dt.date(1966, 3, 1), dt.date(1967, 1, 12), 2))
        self.assertEqual(cr["per_anno"][1965]["X"], 1)                  # fascicolo datato all'anno
        self.assertIn("mancano dalle fonti 1 numero di Zëri i Popullit", fatti[1])
        self.assertIn("fino alla fine delle fonti periodiche disponibili (31 dicembre 1990)", fatti[2])

    def test_mese_della_lacuna_dalla_sigla(self):
        self.assertEqual(S._mese_problema("Rruga e Partisë", "riviste/rruga_e_partise/RP1972-05.txt"), (1972, 3))
        self.assertEqual(S._mese_problema("Zëri i Popullit", "ZP1966-07-01.txt"), (1966, 7))
        self.assertEqual(S._mese_problema("Ignota", "X1966.txt"), (1966, None))

    def test_lacuna_attribuita_al_gruppo(self):
        self.assertEqual(CR.serie_della_lacuna("Stampa del PPSH (supplementi)"), "Rruga e Partisë")
        self.assertEqual(CR.serie_della_lacuna("Zëri i Popullit"), "Zëri i Popullit")

    def test_filtro_per_fonte(self):
        rp = passaggio("Rruga e Partisë", "riviste/rruga_e_partise/RP1972-05.txt", "1972")
        doc = passaggio("Dokumente PPSH 1966", "dokumente/ppsh/v1.txt", "2005")
        self.assertTrue(R.fonte_ammessa(rp, ["Stampa del PPSH"]))
        self.assertTrue(R.fonte_ammessa(rp, ["Bashkimi"]))              # stesso gruppo
        self.assertFalse(R.fonte_ammessa(rp, ["Zëri i Popullit"]))
        self.assertFalse(R.fonte_ammessa(doc, ["documenti"]))           # cartella più specifica, senza gruppo
        self.assertTrue(R.fonte_ammessa(passaggio("x", "dokumente/altro/v.txt", "2005"), ["documenti"]))

    def test_filtro_del_periodo_sulla_data_del_documento(self):
        import io
        import json
        from contextlib import redirect_stdout
        interna = {"data": "1962-01-04", "precisione": "giorno", "stato": "dedotto", "posizione": 5, "distanza": 9}
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "passaggi.jsonl"
            righe = [passaggio("Dokumente", "dokumente/v.txt", "2013", data_interna=interna),       # 1962: resta
                     passaggio("Dokumente", "dokumente/w.txt", "2013", data_interna=None),          # anno ignoto: resta
                     passaggio("Zëri i Popullit", "riviste/zeri_i_popullit/ZP1975-01-01.txt", "1975-01-01")]
            f.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in righe), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                R.filtra_passaggi(Path(tmp), al=1970)
            tenuti = [json.loads(r)["file"] for r in f.read_text(encoding="utf-8").splitlines()]
        self.assertEqual(tenuti, ["dokumente/v.txt", "dokumente/w.txt"])

    def test_note_dei_limiti_dal_profilo(self):
        self.assertEqual(S.note_limiti("", "riviste/zeri_i_popullit/ZP1967-01-12.txt"),
                         ["La stampa albanese registra ciò che Tirana sceglieva di pubblicare."])
        self.assertEqual(S.note_limiti("Ignota", "x.txt"), [])


if __name__ == "__main__":
    unittest.main()

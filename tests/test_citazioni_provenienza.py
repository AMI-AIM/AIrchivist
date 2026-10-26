"""
Test delle citazioni in stile Chicago autore-data (citazioni.py), della provenienza delle letture (archivio.py) e delle
funzioni di calcolo dello strumento di valutazione (valutazione.py). Senza corpus né modelli.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import citazioni as C  # noqa: E402
from archivio import descrivi_provenienza, livello, provenienza, riallinea  # noqa: E402
import valutazione as V  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prova import setUpModule, tearDownModule  # noqa: E402,F401  profili delle serie di prova


class Citazioni(unittest.TestCase):
    def test_periodico_con_volume_numero_data_pagina(self):
        meta = {"SERIES": "Peking Review", "VOLUME": "X", "ISSUE": "11", "DATE": "1967-03-10"}
        self.assertEqual(C.citazione(meta, "riviste/peking_review/PR1967-11.txt", "5"),
                         "*Peking Review*. 1967. Vol. 10, no. 11, 10 marzo 1967, p. 5.")

    def test_data_inattendibile_diventa_anno(self):
        meta = {"SERIES": "Peking Review", "VOLUME": "X", "ISSUE": "11", "DATE": "1967-03-10", "YEAR": "1967",
                "METADATA_SOURCE": "filename+local_header"}
        self.assertEqual(C.citazione(meta, "riviste/peking_review/PR1967-11.txt"), "*Peking Review*. 1967. Vol. 10, no. 11.")

    def test_numero_doppio_e_supplemento(self):
        self.assertEqual(C.citazione({"SERIES": "Hongqi", "ISSUE": "10-11", "YEAR": "1963"}),
                         "*Hongqi* 红旗. 1963. Nos. 10–11.")
        meta = {"SERIES": "Peking Review", "VOLUME": "XVI", "ISSUE": "41", "DATE": "1973-10-12",
                "FULL_CITATION": "Peking Review (1973), no. 41, supplement"}
        self.assertEqual(C.citazione(meta), "*Peking Review*. 1973. Vol. 16, no. 41, supplement, 12 ottobre 1973.")

    def test_volume_senza_profilo(self):
        meta = {"SERIES": "关于国际共产主义运动总路线的论战", "PUBLISHER": "人民出版社", "PUBLICATION_PLACE": "北京",
                "YEAR": "1965"}
        self.assertEqual(C.citazione(meta, "fonti_primarie/x.txt", "12"), "*关于国际共产主义运动总路线的论战*. 1965. 北京: 人民出版社, p. 12.")

    def test_traduzione_jprs(self):
        meta = {"SERIES": "Red Flag", "ISSUE": "10", "DATE": "1977-10-08", "REPORT_DATE": "1977-12-01",
                "JPRS_ID": "70256"}
        self.assertEqual(C.citazione(meta), "Joint Publications Research Service. 1977. JPRS 70256, 1 dicembre 1977. "
                                            "Trad. ingl. di *Hongqi* 红旗, no. 10, 8 ottobre 1977.")

    def test_pagina_dal_marcatore_e_dal_profilo(self):
        testo = "[SERIES: X]\n\n[[p. 11]]\ntesto\n[[p. 12 | pdf 17]]\nqui il nome\n[[p. 13]]\n"
        self.assertEqual(C.pagina_nel_testo(testo, testo.index("qui")), "12")
        self.assertEqual(C.pagina_nel_testo("[[p. s.n.]]\nnome", 14), "")
        rmrb = "第1版()\n专栏：\n...\n第4版()\n专栏：\n弗朗茨"
        self.assertEqual(C.pagina_nel_testo(rmrb, rmrb.index("弗"), {"pagina_regex": r"第\s*(\d+)\s*版"}), "4")

    def test_mai_file_ne_riga(self):
        meta = {"SERIES": "Renmin Ribao", "DATE": "1971-07-09"}
        cit = C.citazione(meta, "riviste/renmin_ribao/1971-07-09.txt", "5")
        self.assertEqual(cit, "*Renmin ribao* 人民日报. 1971. 9 luglio 1971, p. 5.")
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


class Riallineamento(unittest.TestCase):
    CORPO = ("Greetings were sent.\nThe delegation of the Communist Party of Belgium,\nled by comrade "
             "Jacques Grippa, arrived in Peking.\nOther news.")

    def rec(self, intestazione):
        testo = intestazione + self.CORPO
        a, b = testo.index("Communist Party of Belgium"), testo.index("Grippa")
        ev = (testo[len(intestazione):a] + "⟦Communist Party of Belgium⟧" + testo[a + 26:b] + "⟦Grippa⟧"
              + testo[b + 6:])
        return {"offset": a, "passaggio_evidenziato": " ".join(ev.split())}

    def test_intestazione_allungata(self):
        rec = self.rec("[DATE: 1965-03-26]\n\n")
        nuovo = "[DATE: 1965-03-26]\n[DATE_STATUS: verificata]\n[DATE_NOTE: verificata sul testo]\n\n" + self.CORPO
        self.assertEqual(riallinea(nuovo, rec),
                         (nuovo.index("Communist Party of Belgium"), nuovo.index("Grippa")))

    def test_testo_invariato_e_passaggio_assente(self):
        testo = "[DATE: 1965-03-26]\n\n" + self.CORPO
        rec = self.rec("[DATE: 1965-03-26]\n\n")
        self.assertEqual(riallinea(testo, rec), (rec["offset"], testo.index("Grippa")))
        self.assertIsNone(riallinea("[DATE: 1965]\n\nAltro testo, senza il passaggio.", rec))


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

    def test_csv_con_punto_e_virgola(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "campione.csv"
            V.scrivi_csv(f, ["N", "PASSAGGIO", "GIUDIZIO"], [{"N": 1, "PASSAGGIO": "a; b, «c»\nd", "GIUDIZIO": "sì"}])
            self.assertTrue(f.read_bytes().startswith(b"\xef\xbb\xbfN;PASSAGGIO;GIUDIZIO"))
            self.assertEqual(V.leggi_csv(f), [{"N": "1", "PASSAGGIO": "a; b, «c»\nd", "GIUDIZIO": "sì"}])

    def test_righe_intere_nella_prima_colonna(self):
        # file aperto in Excel con il separatore sbagliato: la riga del CSV resta nella colonna A, il giudizio
        # è scritto nella colonna B
        tabella = [["N,FILE,OFFSET,FORMA,CONTESTO,GIUDIZIO,NOTE,VERIFICATO_DA", ""],
                   ['1,a.txt,10,Strobl,"x, y",,,', "si", "IM"],
                   ["2,a.txt,20,Franz,z,,,", "no"]]
        r = V.righe_da_tabella(tabella)
        # le celle compilate a destra vanno, nell'ordine, a GIUDIZIO, NOTE, VERIFICATO_DA
        self.assertEqual([(x["OFFSET"], x["CONTESTO"], x["GIUDIZIO"], x["NOTE"]) for x in r],
                         [("10", "x, y", "si", "IM"), ("20", "z", "no", "")])

    def test_xlsx(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl non installato: serve solo a scrivere il file di prova")
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "candidati.csv"                   # .xlsx salvato con il nome .csv
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(["N", "FILE", "OFFSET", "FORMA", "GIUDIZIO", "NOTE", "VERIFICATO_DA"])
            ws.append([1, "a.txt", 129801, "施特罗伯尔", "sì", "cognome da solo", "IM"])
            wb.save(f)
            self.assertEqual(V.leggi_csv(f), [{"N": "1", "FILE": "a.txt", "OFFSET": "129801", "FORMA": "施特罗伯尔",
                                               "GIUDIZIO": "sì", "NOTE": "cognome da solo", "VERIFICATO_DA": "IM"}])

    def test_misure(self):
        m = V.misure([("sì", "sì"), ("sì", "incerto"), ("sì", "no"), ("no", "sì"), ("no", "no")])
        self.assertEqual(m["richiamo"], (2, 3))
        self.assertEqual(m["richiamo_stretto"], (1, 3))
        self.assertEqual(m["precisione"], (1, 2))


if __name__ == "__main__":
    unittest.main()

"""
Test dell'estrazione delle occorrenze (estrai_occorrenze.py): tolleranza agli errori dell'OCR.

I testi di prova sono brevi frammenti nella forma in cui compaiono nel corpus (Peking Review, Renmin Ribao),
più qualche caso costruito per i limiti noti. Si eseguono senza corpus né modelli:
  python -m unittest discover -s pipeline/test -v
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))
import estrai_occorrenze as E  # noqa: E402


def rx(*varianti):
    info = {"x": {"varianti": list(varianti)}}
    E.compila(info)
    return info["x"]["rx"]


def trova(testo, *varianti):
    return [m.group(0) for m in rx(*varianti).finditer(testo)]


class Sillabazione(unittest.TestCase):
    def test_trattino_dentro_la_parola(self):
        # Peking Review 1966, no. 46: «Chairman of the Organ-ization»
        self.assertEqual(trova("led by Franz Strobl, Chairman of the Organ-ization; and", "Organization"),
                         ["Organ-ization"])

    def test_trattino_a_fine_riga(self):
        self.assertEqual(trova("the delegation led by Franz Strob-\nl arrived", "Franz Strobl"), ["Franz Strob-\nl"])

    def test_trattino_e_spazi_a_fine_riga(self):
        self.assertTrue(trova("Jacques Grip- \n  pa, First Secretary", "Jacques Grippa"))

    def test_trattino_morbido_e_lineetta(self):
        # U+00AD (trattino morbido) e U+2010 compaiono in alcuni PDF con strato di testo
        self.assertTrue(trova("Jacques Grip­\npa", "Jacques Grippa"))
        self.assertTrue(trova("Jacques Grip‐pa", "Jacques Grippa"))

    def test_nomi_su_due_righe(self):
        self.assertTrue(trova("signed by Comrade Frans\nStrobl, First Secretary", "Frans Strobl"))


class ParoleIncollate(unittest.TestCase):
    def test_parola_precedente_incollata(self):
        # Peking Review 1963, no. 28: «headed byComrade Enver Hoxha»
        self.assertEqual(trova("Party of Labour headed byComrade Enver Hoxha.", "Enver Hoxha"), ["Enver Hoxha"])
        self.assertTrue(trova("the letter signed byJacques Grippa", "Jacques Grippa"))

    def test_spazio_mancante_tra_nome_e_cognome(self):
        self.assertTrue(trova("the delegation led by FranzStrobl, Chairman", "Franz Strobl"))

    def test_parola_seguente_incollata(self):
        self.assertTrue(trova("Marxist-Leninist Organizationof Austria", "Organization"))


class VariantiBrevi(unittest.TestCase):
    def test_confine_di_parola(self):
        # le forme brevi (meno di 5 lettere) non devono comparire dentro altre parole
        self.assertEqual(trova("a “Maoist farce.” This only confirms", "Mao"), [])
        self.assertEqual(trova("Comrade Mao Tse-tung", "Mao"), ["Mao"])
        self.assertEqual(trova("the PKI delegation; SPKIX", "PKI"), ["PKI"])
        self.assertEqual(trova("(PKI)", "PKI"), ["PKI"])

    def test_confine_con_lettere_accentate(self):
        self.assertEqual(trova("Gripès Lin", "Lin"), ["Lin"])
        self.assertEqual(trova("Linéaire", "Lin"), [])

    def test_maiuscole_e_minuscole(self):
        self.assertTrue(trova("FRANZ STROBL, FIRST SECRETARY", "Franz Strobl"))


class Cinese(unittest.TestCase):
    def test_spazi_tra_caratteri(self):
        self.assertEqual(trova("比利时共产党总书记雅克 · 格 里帕同志", "雅克·格里帕"), ["雅克 · 格 里帕"])

    def test_a_capo_tra_caratteri(self):
        self.assertTrue(trova("主编弗朗茨·施特\n罗伯尔率领下", "弗朗茨·施特罗伯尔"))

    def test_punto_centrale_e_varianti(self):
        for forma in ("雅克·格里帕", "雅克・格里帕", "雅克•格里帕", "雅克.格里帕", "雅克‧格里帕", "雅克-格里帕",
                      "雅克格里帕"):
            self.assertTrue(trova(f"同志{forma}同志", "雅克·格里帕"), forma)

    def test_parentesi_larghe_e_strette(self):
        # Renmin Ribao 1967-01-07: «法国共产主义运动（马列）书记马尔蒂»
        for forma in ("法国共产主义运动（马列）", "法国共产主义运动(马列)", "法国共产主义运动（马列)"):
            self.assertTrue(trova(f"{forma}书记马尔蒂", "法国共产主义运动（马列）"), forma)

    def test_virgole(self):
        self.assertTrue(trova("马列，毛泽东思想", "马列,毛泽东思想"))
        self.assertTrue(trova("马列,毛泽东思想", "马列，毛泽东思想"))

    def test_nessun_confine_di_parola_per_il_cinese(self):
        # in cinese le parole non sono separate: la forma si trova anche attaccata ad altri caratteri
        self.assertTrue(trova("奥地利马列主义党中央", "马列主义党"))


class Intestazione(unittest.TestCase):
    def test_intestazione_esclusa(self):
        testo = "[SERIES: Peking Review]\n[FULL_CITATION: Franz Strobl]\n\nTesto con Franz Strobl.\n"
        meta, inizio = E.leggi_intestazione(testo)
        self.assertEqual(meta["SERIES"], "Peking Review")
        self.assertEqual([m.start() for m in rx("Franz Strobl").finditer(testo, inizio)], [testo.rindex("Franz")])

    def test_date_inattendibili(self):
        corpus = Path("/c")
        p = corpus / "riviste" / "peking_review" / "PR1967-11.txt"
        meta = {"SERIES": "Peking Review", "DATE": "1967-03-10", "METADATA_SOURCE": "filename+local_header",
                "YEAR": "1967"}
        _, fonte, _, data, affidabile = E.metadati(p, corpus, meta)
        self.assertEqual((fonte, data, affidabile), ("Peking Review", "1967", False))
        meta["DATE_STATUS"] = "da verificare"
        meta.pop("METADATA_SOURCE")
        self.assertFalse(E.metadati(p, corpus, meta)[4])

    def test_data_dal_nome_del_file(self):
        corpus = Path("/c")
        p = corpus / "riviste" / "renmin_ribao" / "1971-07-09.txt"
        self.assertEqual(E.metadati(p, corpus, {"SERIES": "Renmin Ribao"})[3], "1971-07-09")


class Estrazione(unittest.TestCase):
    """Prova completa di estrai_occorrenze.py su un piccolo corpus temporaneo."""

    def test_passaggi_raggruppati_e_righe(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "corpus" / "riviste" / "pr").mkdir(parents=True)
            (d / "corpus" / "riviste" / "pr" / "PR1967-11.txt").write_text(
                "[SERIES: Peking Review]\n[DATE: 1967-03-10]\n[FULL_CITATION: Peking Review (1967), no. 11]\n\n"
                "riga uno\nwith Com-rade Frans Strobl as its First Secretary. The conference adopted a message\n"
                "signed by Comrade Frans Strobl.\n" + "x " * 600 + "\nlater FranzStrobl again.\n",
                encoding="utf-8")
            (d / "entita.ini").write_text("[Franz Strobl]\nvarianti = Franz Strobl; Frans Strobl\n", encoding="utf-8")
            r = subprocess.run([sys.executable, str(PIPELINE / "estrai_occorrenze.py"), str(d / "corpus"),
                                str(d / "entita.ini"), "--out", str(d / "out"), "--finestra", "200"],
                               capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stderr)
            pas = [json.loads(x) for x in (d / "out" / "passaggi.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(pas), 2)                        # due occorrenze vicine, una lontana
            self.assertEqual(pas[0]["n_occorrenze"], 2)
            self.assertEqual(pas[0]["riga"], 6)
            self.assertEqual(pas[0]["data"], "1967-03-10")
            self.assertIn("⟦Frans Strobl⟧", pas[0]["passaggio_evidenziato"])
            self.assertEqual(pas[1]["varianti_trovate"], ["FranzStrobl"])


class Accenti(unittest.TestCase):
    """L'estrazione e l'indice usano lo stesso pattern: un accento caduto o cambiato nell'OCR
    non deve far sfuggire un'occorrenza (era il punto della revisione 23/10)."""

    def test_accento_caduto(self):
        self.assertTrue(trova("the speech of Desire Grippa", "Désiré Grippa"))
        self.assertTrue(trova("L'Exploite n. 4", "L'Exploité"))

    def test_accento_diverso(self):
        self.assertTrue(trova("Strobl and Ströbl met the delegation", "Ströbl"))

    def test_senza_accenti_uguale_a_pattern_latino(self):
        # indice.py delega a pattern_variante: i due pattern devono restare identici
        import indice as I
        for f in ("Enver Hoxha", "Désiré Grippa", "Linea Rossa"):
            self.assertEqual(I.pattern_latino(f), E.pattern_variante(f))


class IdPassaggio(unittest.TestCase):
    """L'id del passaggio non dipende dalla finestra: cambiando quel parametro in config.ini le
    letture già pagate nell'archivio restano riconosciute."""

    def _gruppi(self, finestra):
        info = {"x": {"varianti": ["Franz Strobl"], "contesto": []}}
        E.compila(info)
        testo = "intro Franz Strobl middle text more words here and Franz Strobl tail"
        return [p for p, g in E.passaggi_del_testo(testo, 0, "a.txt", "x", info["x"], finestra)]

    def test_stesso_id_con_finestre_diverse(self):
        stretti = self._gruppi(5)      # due passaggi distinti
        larghi = self._gruppi(500)     # occorrenze vicine: un solo passaggio
        self.assertEqual(len(stretti), 2)
        self.assertEqual(len(larghi), 1)
        self.assertEqual(larghi[0]["id"], stretti[0]["id"])   # id dalla prima occorrenza, stabile

    def test_riga_calcolata_corretta(self):
        info = {"x": {"varianti": ["Strobl"], "contesto": []}}
        E.compila(info)
        testo = "riga uno\nriga due\nStrobl e basta\nquarta riga"
        pas, _ = E.passaggi_del_testo(testo, 0, "a.txt", "x", info["x"], 10)[0]
        self.assertEqual(pas["riga"], 3)


class ArchiviJsonl(unittest.TestCase):
    """append_jsonl: newline puro, più processi concorrenti non corrompono le righe."""

    def test_append_e_concorrenza(self):
        import json as _json
        from concurrent.futures import ThreadPoolExecutor
        from archivio import append_jsonl
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "letture.jsonl"
            def scrivi(k):
                append_jsonl(f, [_json.dumps({"n": k})])
                return k
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(scrivi, range(60)))
            raw = f.read_bytes()
            self.assertNotIn(b"\r\n", raw)                     # "\n" non diventa "\r\n" su Windows
            righe = [x for x in raw.decode("utf-8").splitlines() if x]
            self.assertEqual(len(righe), 60)
            for x in righe:                                    # ogni riga è JSON integro
                _json.loads(x)


class JsonRobusto(unittest.TestCase):
    """estrai_json tollera parole attorno al JSON e risposte con più oggetti in fila."""

    def setUp(self):
        from llm import estrai_json
        self.estrai = estrai_json

    def test_preamble_e_postfazione(self):
        r = self.estrai('Ecco la risposta:\n{"pertinente": "sì", "nota": "a { b"}\nSpero sia utile.')
        self.assertEqual(r["pertinente"], "sì")

    def test_primo_di_due_oggetti(self):
        r = self.estrai('[{"id": 1}, {"id": 2}] not another json')
        self.assertEqual(r, [{"id": 1}, {"id": 2}])

    def test_graffe_dentro_le_stringhe(self):
        r = self.estrai('noise {"citazione": "Il «manifesto» {1967} dice"} noise')
        self.assertIn("{1967}", r["citazione"])

    def test_ancora_un_json_invalido_segna_errore(self):
        from llm import ErroreModello
        with self.assertRaises(ErroreModello):
            self.estrai("nessun json qui dentro")


if __name__ == "__main__":
    unittest.main()

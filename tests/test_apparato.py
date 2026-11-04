"""
Test dell'apparato editoriale (apparato.py, lavoro 40, A1): testatine e note dei curatori marcate all'importazione,
escluse dai passaggi dell'estrazione e dalle righe dell'indice. Casi presi dalla prova del 3/11/2026 sulla raccolta
Boçe-Bilbili (documenti AQSH pubblicati): la testatina «48 ARMANDO BOÇE, ARBËR BILBILI» prima del brano su un
sospetto agente aveva fatto di Boçe il sospettato nella risposta.
"""
import re
import sys
import tempfile
import unittest
from pathlib import Path

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOTORE))
import apparato as A  # noqa: E402
import estrai_occorrenze as E  # noqa: E402

DISPARI = "Marrëdhëniet e PPSH-së me partitë dhe lëvizjet marksiste-leniniste jashtë kampit socialist l {n}"
PARI = "{n} di ARMANDO BOÇE, ARBËR BILBILI"
CORPO = ("Dinuçi tha se dokumenti duhet të përmblidhet para se të transmetohet nga radio.\n"
         "Shokët e Pizës dhe të Livornos ishin dakord me këtë mendim.")


def pagina(n, corpo=CORPO, testatina=True):
    testa = (PARI if n % 2 == 0 else DISPARI).format(n=n)
    return f"[[p. {n} | pdf {n - 44}]]\n" + (testa + "\n\n" if testatina else "") + corpo


class Testatine(unittest.TestCase):
    def test_ripetute_nelle_pagine(self):
        testi, info = A.marca([pagina(45), pagina(46), pagina(47), pagina(48)])
        self.assertEqual(info["testatine"], 4)
        self.assertIn("[[testatina: 48 di ARMANDO BOÇE, ARBËR BILBILI]]", testi[3])
        self.assertTrue(testi[0].startswith("[[p. 45 | pdf 1]]\n[[testatina: Marrëdhëniet"))
        self.assertIn(CORPO, testi[0])                     # il testo resta com'era

    def test_ocr_diverso_nelle_pagine(self):
        testi, info = A.marca([pagina(45), pagina(46).replace("BOÇE", "BOoçE"), pagina(47),
                               pagina(48).replace(" di ", " d ")])
        self.assertEqual(info["testatine"], 4)

    def test_documento_di_una_pagina_con_le_testatine_della_serie(self):
        _, info = A.marca([pagina(15)])
        self.assertEqual(info["testatine"], 0)             # da solo non si ripete
        note = {A.forma(DISPARI.format(n=45))}
        testi, info = A.marca([pagina(15)], note)
        self.assertEqual(info["testatine"], 1)
        self.assertIn("[[testatina: Marrëdhëniet", testi[0])

    def test_righe_del_testo_ripetute_non_sono_testatine(self):
        # pagine uguali (come nei PDF di prova) o ritornelli: senza numero di pagina né maiuscole non contano
        uguale = "[[p. 1 | pdf 1]]\nThe Albanian leadership has insisted that the country will follow its road.\n" + CORPO
        _, info = A.marca([uguale, uguale.replace("p. 1 | pdf 1", "p. 2 | pdf 2")])
        self.assertEqual(info["testatine"], 0)

    def test_titolo_in_maiuscolo_ripetuto(self):
        p = ["PEKING REVIEW\n\n" + CORPO, "PEKING REVIEW\n\n" + CORPO.replace("radio", "Radio Tirana")]
        _, info = A.marca(p)
        self.assertEqual(info["testatine"], 2)              # breve e in maiuscolo, anche senza numero
        p = [x.replace("PEKING REVIEW", "ZERI") for x in p]
        _, info = A.marca(p)
        self.assertEqual(info["testatine"], 0)              # troppo corta per distinguerla da una parola del testo


class Note(unittest.TestCase):
    def test_nota_con_richiamo_numerico(self):
        t = ("[[p. 40 | pdf 1]]\nPara se të largohej shoku Piro Bita, ftuam për drekë Dinuçinë, që të bisedonim.\n"
             "Ai foli gjatë për gjendjen në Toskanë.\n\n"
             "8 Fosco Dinucci (1921 — 1993), komisar politik partizan gjatë Luftës së Dytë Botërore.")
        testi, info = A.marca([t])
        self.assertEqual(info["note"], 1)
        self.assertIn("[[nota]]\n8 Fosco Dinucci (1921 — 1993), komisar politik partizan gjatë Luftës së Dytë "
                      "Botërore.\n[[/nota]]", testi[0])

    def test_nota_attaccata_al_paragrafo_e_richiamo_letto_come_segno(self):
        # l'OCR non lascia la riga vuota e legge il «18» in apice come «'£»
        t = ("[[p. 50 | pdf 1]]\nDinuçi ish shumë i preokupuar për disa qëndrime të Regisit.\n\n"
             "Dinuçi na përsëriti se sipas detyrës ai qe i ngarkuar për të shkuar\n"
             "'£ Mario Geymonat (1941 — 2012), një ndër bashkëpunëtorët e parë të G. Regis.\n"
             "Oriente”.")
        testi, info = A.marca([t])
        self.assertEqual(info["note"], 1)
        self.assertIn("për të shkuar\n[[nota]]\n'£ Mario Geymonat", testi[0])

    def test_righe_del_testo_che_cominciano_con_un_numero(self):
        for riga in ("2 komunistëve italianë brenda partisë dhe jashtë saj.",      # minuscola dopo il numero
                     "1) Sepse Toliati me shokë kanë tradhtuar.",                  # elenco numerato
                     "29. XII. 1964"):
            t = f"[[p. 1 | pdf 1]]\n{CORPO}\n\nAi tha:\n{riga}"
            _, info = A.marca([t])
            self.assertEqual(info["note"], 0, riga)

    def test_marcare_due_volte_non_cambia_nulla(self):
        t = (pagina(46, CORPO + "\n\n“ Kupto Udine.") .replace("Livornos", "Livornos”"))
        una, _ = A.marca([t, pagina(47), pagina(48)])
        due, info = A.marca(una, {A.forma(PARI.format(n=46))})
        self.assertEqual(una, due)
        self.assertEqual((info["testatine"], info["note"]), (0, 0))


class Estrazione(unittest.TestCase):
    def passaggi(self, testo, forme):
        info = {"varianti": forme, "contesto": []}
        E.compila({"X": info})
        return [r for r, _ in E.passaggi_del_testo(testo, 0, "f.txt", "X", info, 400)]

    def test_testatina_fuori_dai_passaggi(self):
        testo = "\n".join(A.marca([pagina(46), pagina(47, "Dinuçi dhe Balestri tha:\nKemi të bëjmë me një agjent."),
                                   pagina(48, "Dinuçi vazhdoi ai, nuk është tek rezikshmërija e tij."),
                                   pagina(49)])[0])
        p = self.passaggi(testo, ["Dinuçi"])
        self.assertEqual(len(p), 1)
        self.assertNotIn("BOÇE", p[0]["passaggio"])
        self.assertNotIn("socialist", p[0]["passaggio"])
        self.assertEqual(self.passaggi(testo, ["Boçe"]), [])           # la testatina non è un'attestazione

    def test_nota_passaggio_a_se(self):
        t = ("[[p. 40 | pdf 1]]\nPara se të largohej shoku Piro Bita, ftuam për drekë Dinuçinë, që të bisedonim.\n\n"
             "8 Fosco Dinucci (1921 — 1993), komisar politik partizan.")
        testo = A.marca([t])[0][0]
        p = self.passaggi(testo, ["Dinuçinë", "Dinucci"])
        self.assertEqual(len(p), 2)
        testo_doc, nota = (p[0], p[1]) if "apparato" not in p[0] else (p[1], p[0])
        self.assertNotIn("komisar", testo_doc["passaggio"])
        self.assertEqual(nota["apparato"], "nota")
        self.assertEqual(nota["passaggio"], "8 Fosco Dinucci (1921 — 1993), komisar politik partizan.")
        self.assertNotIn("[[", nota["passaggio_evidenziato"])

    def test_identificativi_invariati_senza_apparato(self):
        testo = pagina(45, CORPO, testatina=False)
        p = self.passaggi(testo, ["Dinuçi"])
        self.assertEqual(p[0]["id"], E.id_passaggio("f.txt", "X", testo.index("Dinuçi")))


class FileImportati(unittest.TestCase):
    def test_completa_e_testatine_note(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            intest = "[SERIES: Raccolta]\n[DATE: 1962-05-23]\n\n"
            lungo = d / "MP1963.txt"
            lungo.write_text(intest + "\n".join(A.marca([pagina(45), pagina(46), pagina(47)])[0]), encoding="utf-8")
            breve = d / "MP1962.txt"
            breve.write_text(intest + pagina(15), encoding="utf-8")
            note = A.testatine_note(d)
            self.assertIn(A.forma(DISPARI.format(n=1)), note)
            self.assertTrue(A.completa(breve, note))
            self.assertIn("[[testatina: Marrëdhëniet", breve.read_text(encoding="utf-8"))
            self.assertTrue(breve.read_text(encoding="utf-8").startswith(intest))
            self.assertFalse(A.completa(breve, note))                    # già fatto

    def test_e_marcatore(self):
        for r in ("[[testatina: 46 ARMANDO BOÇE]]", "[[nota]]", "[[/nota]]"):
            self.assertTrue(A.e_marcatore(r), r)
        self.assertFalse(A.e_marcatore("[[p. 3]]"))
        self.assertTrue(re.match(r"^\[\[", "[[nota]]"))


if __name__ == "__main__":
    unittest.main()

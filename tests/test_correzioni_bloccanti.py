"""
Test dei tre difetti bloccanti trovati nella revisione del 3/11/2026:
  - revisione.py: la scelta della data in testa e in coda del documento non finiva mai (un ciclo aggiungeva
    elementi alla lista che stava scorrendo): `importa.py proponi` si bloccava su ogni documento con la data nel testo;
  - llm.py: il timeout della richiesta era ridotto a 30 s (le risposte senza streaming arrivano tutte alla fine, e le
    letture durano spesso di più), e ogni URLError diventava TimeoutException, che prova() non spiegava;
  - classifica.py: con --solo-rapporto le variabili della lettura non esistevano (UnboundLocalError).
Senza modelli.
"""
import email.message
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOTORE))
import llm as L  # noqa: E402
import revisione as R  # noqa: E402


class DateProposte(unittest.TestCase):
    def test_data_in_fondo_accanto_al_luogo(self):
        # caso della prova: la risposta del PPSH cita la lettera del 23.5.1963; la data del documento è in testa
        # con il luogo, quella delle istruzioni di Kapo in fondo accanto alla firma
        a = {"inizio": "Nr. 19\n\ngusht 1962\n\nTirane, me 8\n\nKemi marre letren tuaj te dates 23.5.1963",
             "fine": "fjale " * 400 + "\nHysni Kapo\nTirane, me 7.XII.1962\n"}
        date = R.date_proposte(a)
        self.assertEqual(date[0][:1] + date[0][2:], ("1962-12-07", 4, "letta in fondo al documento"))
        self.assertEqual(date[1][0], "1962-08-08")                       # in testa, con il luogo
        self.assertEqual(date[-1][0], "1963-05-23")                      # citata nel testo: per ultima

    def test_senza_date_e_documento_di_una_pagina(self):
        self.assertEqual(R.date_proposte({"inizio": "Nessuna data qui", "fine": "Nessuna data qui"}), [])
        a = {"inizio": "Rome 12/IV/64", "fine": "Rome 12/IV/64"}           # una pagina: testa e coda coincidono
        self.assertEqual([d[0] for d in R.date_proposte(a)], ["1964-04-12"])

    def test_riga_di_scaricamento_esclusa(self):
        a = {"inizio": "Downloaded on 12.03.2021\nTitolo", "fine": ""}
        self.assertEqual(R.date_proposte(a), [])


class Richieste(unittest.TestCase):
    def llm(self):
        x = L.LLM.__new__(L.LLM)
        x.timeout = 300
        return x

    def test_timeout_del_profilo_per_tutta_la_risposta(self):
        visti = {}

        def urlopen(req, timeout=None):
            visti["timeout"] = timeout
            raise urllib.error.URLError(ConnectionRefusedError("rifiutata"))

        with mock.patch.object(L.urllib.request, "urlopen", urlopen):
            with self.assertRaises(urllib.error.URLError):           # servizio spento: resta URLError
                self.llm()._post("http://127.0.0.1:9/v1/chat/completions", {}, {})
        self.assertEqual(visti["timeout"], 300)

    def test_timeout_di_collegamento_e_di_risposta(self):
        for errore, tipo in ((urllib.error.URLError(socket.timeout("timed out")), "connessione"),
                             (socket.timeout("timed out"), "risposta")):
            def urlopen(req, timeout=None, e=errore):
                raise e
            with mock.patch.object(L.urllib.request, "urlopen", urlopen):
                with self.assertRaises(L.TimeoutException) as c:
                    self.llm()._post("http://x/v1", {}, {})
            self.assertEqual(c.exception.tipo, tipo)

    def test_quota_senza_indicazione_di_attesa(self):
        def urlopen(req, timeout=None):
            raise urllib.error.HTTPError("http://x", 429, "Too Many Requests", email.message.Message(),
                                         io.BytesIO(b""))
        with mock.patch.object(L.urllib.request, "urlopen", urlopen):
            with self.assertRaises(L.LimiteRaggiunto) as c:
                self.llm()._post("http://x/v1", {}, {})
        self.assertEqual(c.exception.attesa, 20.0)


class SoloRapporto(unittest.TestCase):
    def test_rapporto_senza_lettura(self):
        rec = {"id": "a1", "entita": "Fosco Dinucci", "fonte": "Raccolta", "citazione": "Pani. “Relacion.”",
               "data": "1964-07-04", "data_affidabile": True, "file": "f.txt", "riga": 3, "offset": 10,
               "n_occorrenze": 1, "varianti_trovate": ["Dinuçi"], "contesto_presente": False,
               "passaggio": "tha Dinuçi.", "passaggio_evidenziato": "tha ⟦Dinuçi⟧."}
        letto = dict(rec, analisi={"pertinente": "sì", "motivazione": "", "tipo_menzione": "altro",
                                   "citazione_testuale": "tha Dinuçi.", "traduzione_it": "disse Dinucci.",
                                   "sintesi_it": "", "citazione_verificata": True})
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "passaggi.jsonl").write_text(json.dumps(rec, ensure_ascii=False) + "\n", encoding="utf-8")
            (d / "classificati.jsonl").write_text(json.dumps(letto, ensure_ascii=False) + "\n", encoding="utf-8")
            (d / "entities.ini").write_text("[Fosco Dinucci]\ntipo = persona\nvarianti = Dinuçi\n", encoding="utf-8")
            r = subprocess.run([sys.executable, str(MOTORE / "classifica.py"), str(d), str(d / "entities.ini"),
                                "--solo-rapporto"], capture_output=True, text=True, encoding="utf-8",
                               env=dict(os.environ, PYTHONIOENCODING="utf-8"), timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Classificati: 1", r.stdout)
            self.assertTrue((d / "rapporto.md").exists())


class RispostaDaRichiedere(unittest.TestCase):
    """Una risposta di forma inattesa si richiede nello stesso lancio."""
    def llm(self, risposte):
        x = L.LLM.__new__(L.LLM)
        x._chiama = lambda s, u, sc: risposte.pop(0)
        return x

    def test_elenco_poi_oggetto(self):
        x = self.llm(['[{"a": 1}, {"b": 2}]', '{"tono": "neutro"}'])
        self.assertEqual(x.json("s", "u", {"properties": {"tono": {}}}), {"tono": "neutro"})
        self.assertEqual(x.risposte_scartate, 1)

    def test_dopo_i_tentativi_resta_l_errore(self):
        x = self.llm(["niente JSON"] * L.TENTATIVI_FORMA)
        with self.assertRaises(L.ErroreModello):
            x.json("s", "u", {})
        self.assertEqual(x.risposte_scartate, L.TENTATIVI_FORMA - 1)

    def test_altri_errori_non_si_ripetono(self):
        x = L.LLM.__new__(L.LLM)
        chiamate = []

        def chiama(s, u, sc):
            chiamate.append(1)
            raise L.ErroreModello("Il servizio ha risposto con errore 401")
        x._chiama = chiama
        with self.assertRaises(L.ErroreModello):
            x.json("s", "u", {})
        self.assertEqual(len(chiamate), 1)


class TempiDellaLettura(unittest.TestCase):
    """Richieste, tempo del modello e tempo di attesa, per lancio."""
    def test_registro(self):
        import classifica as K
        m = L.LLM.__new__(L.LLM)
        m.richieste, m.secondi_modello, m.secondi_attesa, m.risposte_scartate = 7, 300.0, 90.0, 1
        with tempfile.TemporaryDirectory() as d:
            K.registro_lettura(d, 400.0, 6, {"smistamento": m})
            righe = K.registro_lettura(d, 60.0, 1, {"smistamento": m})
            storia = json.loads((Path(d) / "tempi_lettura.json").read_text(encoding="utf-8"))
        self.assertEqual(len(storia), 2)                                  # una voce per lancio, non sommate
        self.assertEqual(storia[0]["smistamento"]["richieste"], 7)
        self.assertIn("5.0 min di risposta del modello, 1.5 min di attesa", righe[1])

    def test_contatori_delle_chiamate(self):
        m = L.LLM.__new__(L.LLM)
        m.backend, m.pausa, m._ultima, m.max_token = "openai", 0, 0.0, 100
        m._openai = lambda s, u, sc, max_token: "ok"
        self.assertEqual(m._chiama("s", "u", None), "ok")
        self.assertEqual(m.richieste, 1)
        self.assertGreaterEqual(m.secondi_modello, 0)


class CitazioneDaControllare(unittest.TestCase):
    """La frase intera, ma non il passaggio intero quando manca la punteggiatura."""
    def test_frase_intera_e_limite(self):
        import classifica as K
        frase = "Dinuçi tha se dokumenti duhet të përmblidhet para se të transmetohet nga radio."
        rec = {"passaggio": frase, "passaggio_evidenziato": frase.replace("Dinuçi", "⟦Dinuçi⟧", 1)}
        self.assertEqual(K.frase_chiave(rec), frase)
        lungo = ("parola " * 300) + "⟦Dinuçi⟧ " + ("parola " * 300)
        f = K.frase_chiave({"passaggio": lungo, "passaggio_evidenziato": lungo})
        self.assertIn("Dinuçi", f)
        self.assertLessEqual(len(f), K.FRASE_MASSIMA + 10)


class PagineDeiDocumentiBrevi(unittest.TestCase):
    """Documenti di una o due pagine; un anno non è un numero di pagina; una sola pagina all'indietro."""
    def test_brevi_e_anni(self):
        import numerazione as N
        self.assertEqual(N.da_testo(["Marrëdhëniet socialist I 15\n\ntesto\n\nTiranë 1962"])[0], {1: ("15", True)})
        self.assertEqual(N.da_testo(["16 I ARMANDO BOÇE\n\ntesto", "Marrëdhëniet socialist I 17\n\ntesto"])[1], 15)
        self.assertEqual(N.da_testo(["testo\nnë mars të 1964", "testo\nnë prill të 1965"])[0], {})

    def test_una_pagina_indietro(self):
        import numerazione as N
        testi = ["copertina", "senza testatina"] + [f"Titolo corrente {n}\n\ntesto" for n in (42, 43, 44, 45)]
        pagine, scarto = N.da_testo(testi)
        self.assertEqual((scarto, min(pagine), pagine[2]), (39, 2, ("41", False)))


class ProposteDellaProva(unittest.TestCase):
    """Casi dei dieci documenti della prova."""
    def test_date_citate_di_copia_e_rumore(self):
        # «letrën e datës 4/8/62» è un'altra lettera: nessuna proposta
        date = R.date_proposte({"inizio": "Kemi marre letren e dates 4/8/62 neneshkruar nga tre shoke", "fine": ""})
        self.assertTrue(date and date[0][2] == 0)
        # la data di battitura in fondo non vince sulla data del verbale in testa
        a = {"inizio": "NE APARATIN E KQ TE PPSH ME DATEN 19/7/1963", "fine": "Mbajtur nga Ilo Kodra\nDakt. P.K. l 2.X.1963"}
        self.assertEqual(R.date_proposte(a)[0][0], "1963-07-19")
        # «l 3.IV.1964»: la lettura più lunga (13 aprile), non «3.IV.1964»
        self.assertEqual(R.date_proposte({"inizio": "2669 l 3.IV.1964", "fine": ""})[0][0], "1964-04-13")

    def test_cifre_lette_come_lettere(self):
        import numerazione as N
        self.assertIn(52, N.numeri_di_bordo("s2 di ARMANDO BOÇE, ARBËR BILBILI\n\ntesto\ntesto\ntesto\ntesto\nfine"))
        self.assertIn(51, N.numeri_di_bordo("e\nMarrëdhëniet socialist t S1\ntesto\ntesto\ntesto\ntesto\nfine"))
        self.assertNotIn(5, N.numeri_di_bordo("So I tha\ntesto\ntesto\ntesto\ntesto\nfine"))   # senza cifre: no

    def test_pareggio_senza_numero(self):
        import numerazione as N
        # «1» (numero del documento) e «I 15» (testatina) in una sola pagina: nessun numero, non uno sbagliato
        self.assertEqual(N.da_testo(["Marrëdhëniet socialist I 15\n\nITALI\n\n1\n\nAnkesë e Partisë"])[0], {})


class Raccolte(unittest.TestCase):
    """Segnatura nell'intestazione e nella citazione; il volume senza titolo proprio è la serie."""
    def test_citazione(self):
        import citazioni as C
        meta = {"SERIES": "Marrëdhëniet", "TITLE": "Relacion", "AUTHOR": "Pani, Jordan", "DATE": "1964-07-04",
                "PAGES": "50-54", "CALL_NUMBER": "AQSH, F. 14, V. 1964, D. 1, fl. 27-32"}
        v = C.voce(meta, {"tipo": "raccolta"})
        self.assertIn("In *Marrëdhëniet*, 50–54. AQSH, F. 14", v)
        self.assertNotIn("**", v)
        self.assertNotIn("fl. 27-32, Marrëdhëniet", v)                   # la serie non è l'archivio
        v = C.voce(meta, {"tipo": "raccolta", "curatori": "Armando Boçe e Arbër Bilbili"})
        self.assertIn("a cura di Armando Boçe e Arbër Bilbili", v)

    def test_segnatura_dall_importazione(self):
        import importa as I
        v = {"titolo": "Relacion", "autore": "Pani, Jordan", "data_iso": "1964-07-04",
             "segnatura": "AQSH, F. 14, V. 1964, D. 1, fl. 27-32"}
        self.assertIn("fl. 27-32", I.citazione_documento("Marrëdhëniet", {"tipo": "raccolta"}, v, "50-54"))
        rapporto = {"metodo": "ocr", "confidenza": None}
        testa = I.intestazione("Marrëdhëniet", {"tipo": "raccolta", "lingua": "sq"}, dict(v, citazione="x"),
                               rapporto, "o.pdf", "MP1964-07-04-relacion.txt")
        self.assertIn("[CALL_NUMBER: AQSH, F. 14, V. 1964, D. 1, fl. 27-32]", testa)


if __name__ == "__main__":
    unittest.main()

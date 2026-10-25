"""
Test della ricerca con lettura in sessione (sessione.py, skill ricerca-fonti) e di sintesi.py --sintesi-da, su un
progetto temporaneo con due numeri finti del Renmin Ribao: uno pertinente, uno con un omonimo. Senza modelli.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]
PROVA = Path(__file__).resolve().parent / "progetto_prova"

INTESTAZIONE = """[DOC_ID: RMB-{data}]
[SERIES: Renmin Ribao]
[DOC_TYPE: newspaper]
[LANG: zh]
[YEAR: {anno}]
[DATE: {data}]
[FULL_CITATION: Renmin Ribao, {data}]

"""
PERTINENTE = ("第1版() 专栏： 贝林格同志率意共中央代表团抵京 新华社北京四月十四日电 应中国共产党中央委员会邀请，"
              "由总书记贝林格率领的意大利共产党中央代表团今天晚间乘飞机到达北京。")
OMONIMO = ("第6版() 专栏： 外交部新闻处长塞尔乔·贝林格参赞参加了会谈。")
SCHEDA = """[Enrico Berlinguer]
tipo = persona
varianti = 贝林格; 恩里科·贝林格
note = Segretario generale del Partito comunista italiano.
"""


def esegui(*argomenti, env):
    r = subprocess.run([sys.executable, *map(str, argomenti)], cwd=PIPELINE, env=env, capture_output=True,
                       text=True, encoding="utf-8")
    if r.returncode != 0:
        raise AssertionError(f"{argomenti[0]} {argomenti[1] if len(argomenti) > 1 else ''}: {r.stdout}\n{r.stderr}")
    return r.stdout


class RicercaInSessione(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.radice = Path(cls.tmp.name) / "progetto"
        shutil.copytree(PROVA, cls.radice)
        rr = cls.radice / "data" / "riviste" / "renmin_ribao"
        rr.mkdir(parents=True)
        for data, testo in (("1980-04-15", PERTINENTE), ("1977-06-13", OMONIMO)):
            (rr / f"{data}.txt").write_text(INTESTAZIONE.format(data=data, anno=data[:4]) + testo + "\n",
                                            encoding="utf-8")
        (cls.radice / "entita.ini").write_text(SCHEDA, encoding="utf-8")
        cls.env = dict(os.environ, AIRCHIVIST_PROGETTO=str(cls.radice), PYTHONIOENCODING="utf-8")
        cls.cart = cls.radice / "risultati" / "prova_sessione"
        cls.uscita_prepara = esegui("sessione.py", "prepara", "Enrico Berlinguer", "--cartella", "prova_sessione",
                                    env=cls.env)
        cls.passaggi = [json.loads(r) for r in (cls.cart / "passaggi.jsonl").read_text(encoding="utf-8").splitlines()]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def id_di(self, data):
        return next(p["id"] for p in self.passaggi if p["data"] == data)

    def scrivi(self, nome, contenuto):
        f = self.cart / nome
        f.write_text(json.dumps(contenuto, ensure_ascii=False), encoding="utf-8")
        return f

    def test_1_prepara(self):
        self.assertEqual(len(self.passaggi), 2)
        self.assertIn("da leggere: 2 in 1 lotti", self.uscita_prepara)
        lotto = (self.cart / "lotti" / "lotto_01.md").read_text(encoding="utf-8")
        for p in self.passaggi:
            self.assertIn(f"## {p['id']}", lotto)
        self.assertIn("FRASE DA TRADURRE:", lotto)
        self.assertIn("⟦贝林格⟧", lotto)

    def test_2_registra_rifiuta_letture_incomplete(self):
        f = self.scrivi("letture_errate.json", [{"id": self.id_di("1980-04-15"), "pertinente": "sì"},
                                                {"id": "inesistente", "pertinente": "no"},
                                                {"id": self.id_di("1977-06-13"), "pertinente": "forse"}])
        r = subprocess.run([sys.executable, "sessione.py", "registra", str(self.cart), str(f)], cwd=PIPELINE,
                           env=self.env, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 1)
        self.assertIn("manca traduzione_it", r.stdout)
        self.assertIn("id sconosciuto", r.stdout)
        self.assertIn("ancora da leggere: 2", r.stdout)

    def test_3_registra_documenti_sintesi(self):
        f = self.scrivi("letture_01.json", [
            {"id": self.id_di("1980-04-15"), "pertinente": "sì", "motivazione": "arrivo a Pechino",
             "tipo_menzione": "delegazione/visita", "traduzione_it": "Il compagno Berlinguer arriva a Pechino.",
             "sintesi_it": "Il 14 aprile 1980 Berlinguer arriva a Pechino.", "tono": "elogiativo",
             "altri_nominati": [{"nome": "PCC", "ruolo": "invita"}]},
            {"id": self.id_di("1977-06-13"), "pertinente": "no", "motivazione": "Sergio 贝林格: omonimo"}])
        uscita = esegui("sessione.py", "registra", self.cart, f, "--da", "modello-di-prova", env=self.env)
        self.assertIn("ancora da leggere: 0", uscita)
        letture = {c["id"]: c["analisi"] for c in
                   map(json.loads, (self.cart / "classificati.jsonl").read_text(encoding="utf-8").splitlines())}
        a = letture[self.id_di("1980-04-15")]
        self.assertTrue(a["citazione_verificata"])
        self.assertIn("贝林格", a["citazione_testuale"])
        self.assertEqual(a["pagina"], "1")
        self.assertEqual(a["provenienza"]["decisione"], {"livello": "sessione", "da": "modello-di-prova"})
        self.assertEqual(a["provenienza"]["lettura"], {"livello": "sessione", "da": "modello-di-prova"})
        self.assertIsNone(letture[self.id_di("1977-06-13")]["provenienza"]["lettura"])
        # cartella «prova…»: l'archivio unico non viene creato
        self.assertFalse((self.radice / "risultati" / "_archivio" / "letture.jsonl").exists())

        elenco = esegui("sessione.py", "documenti", self.cart, env=self.env)
        self.assertIn("documenti pertinenti: 1", elenco)
        self.assertIn("[1] *Renmin ribao*", elenco)

        s = self.scrivi("sintesi_sessione.json", {
            "da": "modello-di-prova",
            "dati_espliciti": [{"testo": "Berlinguer arriva a Pechino il 14 aprile 1980.", "rif": [1]},
                               {"testo": "Voce senza rimando valido.", "rif": [7]}],
            "inferenze": [{"testo": "La visita è di partito.", "rif": [1], "fondatezza": "media"}],
            "problemi_interpretativi": [],
            "risposta_finale": "Berlinguer arriva a Pechino [1]."})
        esegui("sintesi.py", self.cart, self.cart / "entita_ricerca.ini", "--domanda", "Chi era Berlinguer?",
               "--sintesi-da", s, env=self.env)
        risposta = (self.cart / "risposta.md").read_text(encoding="utf-8")
        self.assertIn("- Berlinguer arriva a Pechino il 14 aprile 1980. [1]", risposta)
        self.assertNotIn("Voce senza rimando valido", risposta)
        self.assertIn("1 affermazioni proposte dal modello sono state scartate", risposta)
        self.assertIn("*Inferenza (fondatezza media):* La visita è di partito. [1]", risposta)
        self.assertIn("Berlinguer arriva a Pechino [1].", risposta.split("## 7. Risposta finale")[1])
        self.assertIn("sintesi modello-di-prova (in sessione)", risposta)
        self.assertIn("lettura assistita in sessione (modello-di-prova) 1", risposta)
        self.assertNotIn("Sintesi non generata", risposta)
        self.assertIn("Traduzione: Il compagno Berlinguer arriva a Pechino.", risposta)


if __name__ == "__main__":
    unittest.main()

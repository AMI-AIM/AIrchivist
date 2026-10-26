"""
Test delle correzioni emerse dai confronti tra la skill source-search e Claude base nella chat (25-26/10/2026):
allegati in /mnt/user-data/attachments, date note solo al mese, numeri di pagina dei documenti d'archivio dopo
l'OCR (timbri sotto il numero, scarto che cambia per pagine mancanti), marcatori di pagina nelle citazioni,
menzioni contate in esplora, sommario dei quotidiani cinesi, strato di testo illeggibile nei PDF.
"""
import argparse
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOTORE))
import citazioni as C  # noqa: E402
import classifica as K  # noqa: E402
import date_interne as D  # noqa: E402
import esplora as E  # noqa: E402
import importa as I  # noqa: E402
import numerazione as N  # noqa: E402

INTESTAZIONE = "[SERIES: Renmin Ribao]\n[LANG: zh]\n[YEAR: 1980]\n[DATE: 1980-04-15]\n\n"
PAROLE = "The Party continued the struggle against revisionism and for the construction of socialism. " * 6
TIMBRO = "25X1\nSECRET\nSanitized Copy Approved for Release 2009/12/03 : CIA-RDP85T00875R001000010042-0"


class AllegatiDellaChat(unittest.TestCase):
    def test_prefisso_tolto(self):
        with tempfile.TemporaryDirectory() as tmp:
            allegati = Path(tmp) / "attachments" / "cb0e9415-42a9-5462-948e-7fc2583f6821"
            allegati.mkdir(parents=True)
            (allegati / "0e86e18d-RMRB1980-04-15.txt").write_text(INTESTAZIONE + "贝林格同志抵京。\n", encoding="utf-8")
            (allegati / "2e798566-1968_-_CIA_Mijal_e_Dinucci.pdf").write_bytes(b"%PDF-1.4\n")
            env = dict(os.environ, AIRCHIVIST_PROGETTO=str(Path(tmp) / "progetto"), PYTHONIOENCODING="utf-8")
            r = subprocess.run([sys.executable, str(MOTORE / "chat.py"), "apri", str(Path(tmp) / "attachments")],
                               cwd=MOTORE, env=env, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            esito = json.loads(r.stdout)
            self.assertEqual(esito["fonti_aggiunte"], 1)
            self.assertTrue((Path(tmp) / "progetto" / "data" / "RMRB1980-04-15.txt").exists())
            self.assertEqual(len(esito["da_importare"]), 1)


class DateAlMese(unittest.TestCase):
    def test_citazione(self):
        self.assertEqual(C.data_it("1971-11"), "novembre 1971")
        self.assertEqual(C.data_it("1971-11-04"), "4 novembre 1971")
        self.assertEqual(C.data_it("1971-13"), "1971-13")
        v = C.valori_da_intestazione({"SERIES": "CIA", "DATE": "1971-11", "TITLE": "The Failure"})
        self.assertEqual(v["data"], "novembre 1971")
        self.assertEqual(v["data_o_anno"], "novembre 1971")

    def test_nessuna_data_interna(self):
        self.assertFalse(D.applicabile({"DATE": "1971-11"}, {"tipo": "volume"}))
        self.assertTrue(D.applicabile({"DATE": "1971"}, {"tipo": "volume"}))

    def test_importazione(self):
        with tempfile.TemporaryDirectory() as tmp:
            radice = Path(tmp)
            (radice / "serie.ini").write_text(
                "[CIA]\ntipo = volume\nlingua = en\ncartella = volumi/cia\ncitazione = {titolo}, {data}\n"
                "autore = Central Intelligence Agency\nchicago = {autore}. *{titolo}*. {data_o_anno}[, {pagina}]\n",
                encoding="utf-8")
            (radice / "rapporto.txt").write_text(PAROLE, encoding="utf-8")
            import configparser
            cfg = configparser.ConfigParser(interpolation=None)
            cfg["percorsi"] = {"dati": str(radice / "data"), "risultati": str(radice / "risultati"),
                               "entita": str(radice / "entita.ini"), "serie": str(radice / "serie.ini"),
                               "problemi": str(radice / "p.csv"),
                               "importazioni": str(radice / "audit" / "checks"),
                               "registro_importazioni": str(radice / "audit" / "imports.csv"),
                               "cache": str(radice / "system" / "cache")}
            originale, I.leggi_config = I.leggi_config, lambda: cfg
            try:
                with redirect_stdout(io.StringIO()):
                    codice = I.main(["importa", str(radice / "rapporto.txt"), "--serie", "CIA", "--data", "1971-11",
                                     "--titolo", "The Failure of Maoist Ideology in Foreign Policy", "--senza-indice"])
            finally:
                I.leggi_config = originale
            testo = next((radice / "data").rglob("*.txt")).read_text(encoding="utf-8")
        self.assertEqual(codice, 0)
        self.assertIn("[DATE: 1971-11]", testo)
        self.assertIn("*The Failure of Maoist Ideology in Foreign Policy*. novembre 1971]", testo)


class PagineDiArchivio(unittest.TestCase):
    def documento(self, pagine):
        """Pagine di un documento declassificato: timbro in testa, numero «-n-» sopra il timbro in piede."""
        return [(f"{TIMBRO}\n{PAROLE}\n-{n}-\n{TIMBRO}" if n else f"{TIMBRO}\n{PAROLE}\n{TIMBRO}") for n in pagine]

    def test_numero_sopra_il_timbro(self):
        testi = self.documento([None, None, 1, 2, 3, 4, None, 6])
        testi[5] = testi[5].replace("-4-", "=-4-")                   # rumore dell'OCR
        pagine, info = N.numera(testi)
        self.assertEqual(pagine[3], ("1", ""))
        self.assertEqual(pagine[6], ("4", ""))
        self.assertEqual(pagine[7], ("5", "dedotta"))
        self.assertIn("scarto costante -2", info["nota"])

    def test_pagine_mancanti_nella_scansione(self):
        # p. 3 e p. 7 mancano nella scansione: lo scarto passa da -1 a 0 e poi a +1
        testi = self.documento([None, 1, 2, 4, 5, 6, 8, 9, 10])
        pagine, info = N.numera(testi)
        self.assertEqual(pagine[2], ("1", ""))
        self.assertEqual(pagine[4], ("4", ""))
        self.assertEqual(pagine[7], ("8", ""))
        self.assertEqual(pagine[9], ("10", ""))
        self.assertIn("scarto per tratti (-1, +0, +1", info["nota"])

    def test_numeri_sparsi_non_valgono(self):
        testi = self.documento([5, 9, 2, 40, 13, 7])
        self.assertEqual(N.numera(testi)[0], {})


class Citazioni(unittest.TestCase):
    def test_marcatore_fuori_dalla_citazione(self):
        t = "[[p. 1 | pdf 1]] ⟦中苏⟧两国领导人互致新年祝贺 华社31日讯 中国共产党致电⟦苏联共产党⟧。下文"
        rec = {"passaggio_evidenziato": t, "passaggio": t.replace("⟦", "").replace("⟧", "")}
        frase = K.frase_chiave(rec)
        self.assertEqual(frase, "中苏两国领导人互致新年祝贺 华社31日讯 中国共产党致电苏联共产党。")
        self.assertTrue(K.verifica(rec, {"citazione_testuale": frase}))

    def test_marcatore_dentro_la_frase(self):
        t = "He said so. The congress of the [[p. 42 | pdf 44]] ⟦Communist Party⟧ opened. Next."
        rec = {"passaggio_evidenziato": t, "passaggio": t.replace("⟦", "").replace("⟧", "")}
        frase = K.frase_chiave(rec)
        self.assertNotIn("[[", frase)
        self.assertNotIn("pdf", frase)
        self.assertTrue(K.verifica(rec, {"citazione_testuale": frase}))


class Lettore:
    def intorno(self, rel, n, k=1):
        return ""

    def pagina(self, rel, n, rx):
        return ""


class MenzioniInEsplora(unittest.TestCase):
    def test_righe_e_menzioni(self):
        righe = [{"serie": "Renmin Ribao", "anno": 1961, "file": "a.txt", "riga": 1, "trovato": "苏联",
                  "testo": "苏联共产党和苏联政府向苏联人民"},
                 {"serie": "Renmin Ribao", "anno": 1961, "file": "a.txt", "riga": 2, "trovato": "苏联",
                  "testo": "苏联钢产量"}]
        r = E.riassunto(righe, Lettore())
        self.assertEqual((r["totale"], r["righe"], r["menzioni"]), (2, 2, 4))


class SommarioCinese(unittest.TestCase):
    def test_今日要目(self):
        s = ("（下转第二版） 1 9 4 8年6月1 5日创刊第 4 5 5 9 号 今 日 要 目第四版 “红旗”半月刊社论：在总路线的伟大"
             "旗帜下前进第一版 ⟦中苏⟧两国领导人互致新年祝贺 社论：团结一致 第二版 鞍钢钢铁钢材生产提前报捷 第三版")
        self.assertTrue(K.e_sommario({"passaggio_evidenziato": s}))

    def test_pagine_del_giornale_non_bastano(self):
        s = "第6版() 专栏： 意共总书记⟦贝林格⟧再次谴责苏联侵略阿富汗 第6版() 专栏： 民柬外交部发言人"
        self.assertFalse(K.e_sommario({"passaggio_evidenziato": s}))


class StratoIllegibile(unittest.TestCase):
    def test_glifi_a_caso(self):
        # come lo restituisce PyMuPDF per i font senza ToUnicode del Renmin Ribao 1961
        rotto = "ѣѤѥѦѧѨ ᐁᐂᐃᐄᐅ ⲀⲁⲂⲃ കഖഗഘ 中苏两国 " * 10
        self.assertTrue(I.strato_corrotto(rotto, "zh"))

    def test_testi_sani(self):
        self.assertFalse(I.strato_corrotto("中苏两国领导人互致新年祝贺，祝中苏友谊万古长青。Moscow 1961 " * 10, "zh"))
        self.assertFalse(I.strato_corrotto(PAROLE, "en"))
        self.assertFalse(I.strato_corrotto("Партия труда Албании " * 10, "ru"))
        self.assertTrue(I.strato_corrotto("Партия труда Албании " * 10, "en"))
        self.assertFalse(I.strato_corrotto("ѣѤ", "zh"))                     # troppo poco per decidere


if __name__ == "__main__":
    unittest.main()

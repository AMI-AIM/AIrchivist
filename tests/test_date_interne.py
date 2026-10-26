"""
Test della data interna dei documenti nelle raccolte (date_interne.py) e del suo uso in cronologia.py,
sintesi.py ed estrai_occorrenze.py. I frammenti riproducono le forme del corpus (中共中央文件选集,
关于国际共产主义运动总路线的论战, 无产阶级文化大革命资料汇编, Selected Works). Senza corpus né modelli.
"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOTORE))
import cronologia as CR  # noqa: E402
import date_interne as D  # noqa: E402
import sintesi as S  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent))
from prova import setUpModule, tearDownModule  # noqa: E402,F401  profili delle serie di prova


def date(testo):
    return [(iso, prec) for _, _, iso, prec, _ in D.date_nel_testo(testo)]


class Riconoscimento(unittest.TestCase):
    def test_numerali_cinesi(self):
        self.assertEqual(date("（一九六三年六月十四日）"), [("1963-06-14", "giorno")])
        self.assertEqual(date("一九六〇年六月二十六日"), [("1960-06-26", "giorno")])
        self.assertEqual(date("一九六○年九月十日"), [("1960-09-10", "giorno")])        # ○ al posto di 〇
        self.assertEqual(date("一九五七年十一月"), [("1957-11", "mese")])

    def test_spazi_e_errori_ocr(self):
        self.assertEqual(date("(一 九六六年六月一日 )"), [("1966-06-01", "giorno")])
        self.assertEqual(date("《一九六四年五月三目"), [("1964-05-03", "giorno")])      # 目 per 日
        self.assertEqual(date("(1967 年 5 月 14 日 }"), [("1967-05-14", "giorno")])

    def test_giorno_illeggibile_resta_il_mese(self):
        self.assertEqual(date("一九六二年二月三十一日"), [("1962-02", "mese")])

    def test_solo_anno_escluso(self):
        self.assertEqual(date("1965 年 4 月北京第 2 次印刷"), [("1965-04", "mese")])
        self.assertEqual(date("一九六五年的形势"), [])

    def test_mesi_in_lettere(self):
        self.assertEqual(date("(December 19, 1950)"), [("1950-12-19", "giorno")])
        self.assertEqual(date("(March 1927)"), [("1927-03", "mese")])
        self.assertEqual(date("le 14 juin 1963"), [("1963-06-14", "giorno")])
        self.assertEqual(date("Tiranë, 8 nëntor 1966"), [("1966-11-08", "giorno")])


class Intestazioni(unittest.TestCase):
    def test_parentesi_e_riga_sola(self):
        t = "标题\n(一九六三年六月十四日)\n正文\n  一九六七年八月十二日 \n下文他在一九六一年十月二十一日发言"
        d = D.DateDelTesto(t)
        self.assertEqual([x["data"] for x in d.intestazioni], ["1963-06-14", "1967-08-12"])

    def test_inizio_riga_con_virgola_e_data_d_agenzia(self):
        t = ("      一九七六年九月十六日，人民日报刊载意大利共产党（马列）的唁电\n"
             "人类历史的前进新华社一九七六年九月十四日讯  当代最伟大\n"
             "我们在一九六三年三月九日发表的文章，\n"
             "    一九六八年八月二十八日《人民日报》发表社论")
        self.assertEqual([x["data"] for x in D.DateDelTesto(t).intestazioni],
                         ["1976-09-16", "1976-09-14", "1968-08-28"])

    def test_date_nella_prosa_scartate(self):
        # 关于国际共产主义运动总路线的论战: date di eventi e di articoli citati, solo al mese
        t = ("一九六○年六月，苏共领导在布加勒斯特会谈中，用突然袭击的手法\n"
             "中国同志在《再论无产阶级专政的历史经验》（一九五六年十二月）中写道：\n"
             "关于保护文物的意见 (1967 年 5 月 14 日 ) 中共中央关于")
        self.assertEqual([(x["data"], x["forza"]) for x in D.DateDelTesto(t).intestazioni], [("1967-05-14", "debole")])

    def test_note_e_fine_frase_scartate(self):
        t = ("② 考茨基给梅林的信（一八九八年七月十五日）。\n"
             "2 The system of military ranks was initiated in September 1955 and abolished in\nMay 1965.\n"
             "ON THE TEN MAJOR RELATIONSHIPS\nApril 25, 1956\n")
        self.assertEqual([x["data"] for x in D.DateDelTesto(t).intestazioni], ["1956-04-25"])

    def test_data_completa_ripetuta_resta(self):
        firma = "菲律宾共产党中央委员会\n一九七六年九月九日\n"
        t = ("毛主席于一九七六年九月九日逝世。" * 12) + firma + "格里巴"
        self.assertEqual(D.DateDelTesto(t).per_offset(t.index("格里巴"))["data"], "1976-09-09")

    def test_passaggio_prende_l_ultima_intestazione(self):
        t = ("关于甲的通知《一九六二年一月二日\n各中央局：……格里巴……\n"
             "关于乙的报告《一九六二年一月四日\n各中央局：……格里巴……")
        d = D.DateDelTesto(t)
        primo, secondo = t.index("格里巴"), t.rindex("格里巴")
        self.assertEqual(d.per_offset(primo)["data"], "1962-01-02")
        di = d.per_offset(secondo)
        self.assertEqual((di["data"], di["precisione"], di["stato"]), ("1962-01-04", "giorno", "dedotto"))
        self.assertIsNone(d.per_offset(0))                        # prima di ogni intestazione

    def test_testatina_ripetuta_esclusa(self):
        pagina = "\n第三十九册 一九六二年一月\n" + "正文" * 50
        t = "(一九六二年一月四日)\n" + pagina * 12 + "格里巴"
        d = D.DateDelTesto(t)
        self.assertEqual(d.per_offset(t.index("格里巴"))["data"], "1962-01-04")

    def test_elenco_di_date_nessuna_data(self):
        indice = "".join(f"文件{i}\n(一九六三年{i}月一日)\n" for i in range(1, 7))
        t = indice + "格里巴" + "正文" * 400 + "\n(一九六四年一月一日)\n" + "格里巴"
        d = D.DateDelTesto(t)
        self.assertIsNone(d.per_offset(t.index("格里巴")))
        self.assertEqual(d.per_offset(t.rindex("格里巴"))["data"], "1964-01-01")

    def test_distanza_massima(self):
        t = "(一九六三年六月十四日)\n" + "字" * 500 + "格里巴"
        self.assertIsNone(D.DateDelTesto(t, distanza=100).per_offset(t.index("格里巴")))
        self.assertEqual(D.DateDelTesto(t, distanza=1000).per_offset(t.index("格里巴"))["data"], "1963-06-14")

    def test_anni_ammessi(self):
        t = "(二〇一三年三月一日)\n(一九六二年一月二日)\n格里巴"
        self.assertEqual(D.anni_ammessi({"YEAR": "2012"}, {}), (1800, 2012))
        self.assertEqual(D.anni_ammessi({"YEAR": "2012"}, {"data_interna_anni": "1949-1976"}), (1949, 1976))
        d = D.DateDelTesto("(一九八二年一月二日)\n" + t, anni=(1949, 1976))
        self.assertEqual([x["data"] for x in d.intestazioni], ["1962-01-02"])

    def test_applicabile(self):
        self.assertTrue(D.applicabile({"YEAR": "2013"}, {}))
        self.assertFalse(D.applicabile({"DATE": "1966-07-15"}, {}))
        self.assertFalse(D.applicabile({"YEAR": "2013"}, {"data_interna": "no"}))
        self.assertTrue(D.applicabile({"DATE": "1966-07-15"}, {"data_interna": "sì"}))
        self.assertFalse(D.applicabile({"YEAR": "1977"}, {"tipo": "periodico"}))     # fascicolo senza data


def passaggio(fonte, data, data_interna=None, file="f.txt", entita="X"):
    c = {"id": f"{file}{data}{data_interna}", "entita": entita, "fonte": fonte, "data": data, "file": file,
         "offset": 10, "riga": 1, "analisi": {"pertinente": "sì"}}
    if data_interna is not False:
        c["data_interna"] = data_interna
    return c


def interna(iso, posizione, precisione="giorno"):
    return {"data": iso, "precisione": precisione, "stato": "dedotto", "forma": iso, "posizione": posizione,
            "distanza": 5}


class AnnoDelDocumento(unittest.TestCase):
    def test_anno_per_il_periodo(self):
        self.assertEqual(D.anno_del_documento(passaggio("Peking Review", "1967-03-10", False)), (1967, None))
        di = interna("1962-01-04", 9)
        self.assertEqual(D.anno_del_documento(passaggio("中共中央文件选集", "2013", di)), (1962, di))
        # raccolta senza data deducibile: anno non noto, mai l'anno di edizione
        self.assertEqual(D.anno_del_documento(passaggio("中共中央文件选集", "2013", None)), (None, None))


class Cronologia(unittest.TestCase):
    def test_data_di(self):
        self.assertEqual(CR.data_di(passaggio("Peking Review", "1967-03-10", False)), (dt.date(1967, 3, 10), 1967, None))
        self.assertEqual(CR.data_di(passaggio("中共中央文件选集", "2013", interna("1962-01-04", 99))),
                         (dt.date(1962, 1, 4), 1962, 99))
        self.assertEqual(CR.data_di(passaggio("中共中央文件选集", "2013", interna("1962-01", 7, "mese"))),
                         (None, 1962, 7))
        self.assertEqual(CR.data_di(passaggio("中共中央文件选集", "2013", None)), (None, None, None))

    def test_raccolte_nella_cronologia(self):
        p = [passaggio("Peking Review", "1964-03-06", False, "PR1964-10.txt"),
             passaggio("中共中央文件选集", "2013", interna("1962-01-04", 100), "v.txt"),
             passaggio("中共中央文件选集", "2013", interna("1962-03-10", 900), "v.txt"),
             passaggio("中共中央文件选集", "2013", None, "v.txt")]
        cr = CR.calcola(p, "X")
        self.assertEqual(cr["estremi"]["X"], (dt.date(1962, 1, 4), dt.date(1964, 3, 6), 3, 2))
        self.assertEqual(cr["per_anno"][1962]["X"], 2)               # due documenti interni dello stesso file
        self.assertIn("2 dalle date dei documenti nelle raccolte, dedotte dal testo", CR.fatti(cr)[0])


class Raggruppamento(unittest.TestCase):
    def setUp(self):
        self._rif = S.riferimento
        S.riferimento = lambda c, con_pagina=True: f"rif {c['file']}"

    def tearDown(self):
        S.riferimento = self._rif

    def test_un_numero_per_documento_interno(self):
        p = [passaggio("中共中央文件选集", "2013", interna("1962-03-10", 900), "v.txt"),
             passaggio("Peking Review", "1962-02-01", False, "PR1962-05.txt"),
             passaggio("中共中央文件选集", "2013", interna("1962-01-04", 100), "v.txt")]
        docs = S.raggruppa(p)
        self.assertEqual([(d["voci"][0]["file"], (d["data_interna"] or {}).get("data")) for d in docs],
                         [("v.txt", "1962-01-04"), ("PR1962-05.txt", None), ("v.txt", "1962-03-10")])
        self.assertEqual(S.nota_data(docs[0]), " — documento del 4 gennaio 1962 (data dedotta dal testo)")
        self.assertEqual(S.data_per_modello(docs[0], docs[0]["voci"][0]), "1962-01-04, dedotta dal testo")

    def test_data_di_edizione_mai_come_data_del_documento(self):
        c = passaggio("中共中央文件选集", "2013", None, "v.txt")
        self.assertEqual(S.data_per_modello({"data_interna": None}, c), "non nota (raccolta o volume del 2013)")


class Estrazione(unittest.TestCase):
    def test_data_interna_e_periodo_nelle_raccolte(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            (d / "corpus" / "raccolte").mkdir(parents=True)
            (d / "corpus" / "raccolte" / "vol.txt").write_text(
                "[SERIES: Raccolta di prova]\n[YEAR: 2013]\n\n"
                "关于甲的通知\n(一九六二年一月二日)\n格里巴同志\n" + "正文。" * 300 +
                "\n关于乙的通知\n(一九七五年一月十七日)\n格里巴同志\n", encoding="utf-8")
            (d / "entita.ini").write_text("[Jacques Grippa]\nvarianti = 格里巴\n", encoding="utf-8")
            comando = [sys.executable, str(MOTORE / "estrai_occorrenze.py"), str(d / "corpus"),
                       str(d / "entita.ini"), "--out", str(d / "out"), "--finestra", "50"]

            def estrai(*extra):
                r = subprocess.run(comando + list(extra), capture_output=True, text=True, encoding="utf-8",
                                   env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))  # come lavori.py
                self.assertEqual(r.returncode, 0, r.stderr)
                return [json.loads(x) for x in (d / "out" / "passaggi.jsonl").read_text(encoding="utf-8").splitlines()]

            pas = estrai()
            self.assertEqual([p["data_interna"]["data"] for p in pas], ["1962-01-02", "1975-01-17"])
            self.assertEqual({p["data"] for p in pas}, {"2013"})              # la data per citare non cambia
            pas = estrai("--al", "1970")                                      # l'anno di edizione non conta
            self.assertEqual([p["data_interna"]["data"] for p in pas], ["1962-01-02"])


if __name__ == "__main__":
    unittest.main()

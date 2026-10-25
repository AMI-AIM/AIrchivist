#!/usr/bin/env python3
"""
Data interna dei documenti nelle raccolte (lavoro 9, fase 2).

La data del contenitore (intestazione del file) serve a citare; la data interna del documento che contiene il
passaggio serve ad analizzare (cronologia, evoluzione). In una raccolta (中共中央文件选集, Selected Works, ...)
l'anno dell'intestazione è quello di edizione: la data del documento va dedotta dal testo, accanto al passaggio.

Regola: la data interna di un passaggio è l'ultima «data d'intestazione» che lo precede nel file. Intestazioni
  forti (valgono con qualsiasi precisione):
  - da sola su una riga (anche la data in calce: «菲律宾共产党中央委员会 / 一九七六年九月九日»);
  - tra parentesi (o dopo una parentesi aperta, come la legge spesso l'OCR) a inizio o a fine riga:
    （一九六三年六月十四日）, 《一九六二年一月四日⏎, (December 19, 1950);
  - data d'agenzia, seguita da 讯 o 电: «新华社一九七六年九月十四日讯».
  Intestazioni deboli (valgono solo se la data ha il giorno, perché si trovano anche nella prosa):
  - tra parentesi in mezzo alla riga: «…的意见 (1967 年 5 月 14 日 ) 中共中央…» (volumi con l'OCR su poche righe);
  - a inizio riga seguita da una virgola o da 《: «一九七六年九月十六日，人民日报刊载…»,
    «一九六八年八月二十八日《人民日报》…».
Le date nel corpo del testo (eventi citati, «从十月四日至二十六日», «一九六○年六月，苏共领导在…»), nelle note
(righe che iniziano con ①②… o 注) e quelle che chiudono una frase (seguite dal punto fermo) non contano.
Si scartano:
  - le testatine: la stessa forma senza giorno ripetuta molte volte nel file (第三十九册 一九六二年一月 a ogni
    pagina); le date complete ripetute restano (一九七六年九月九日 è citata decine di volte, ma è anche una data
    di documenti);
  - gli elenchi: più date d'intestazione fitte intorno al passaggio (indici, sommari) -> nessuna data;
  - gli anni non plausibili: dopo l'anno di edizione o fuori dagli anni dichiarati nel profilo di serie;
  - le intestazioni troppo lontane dal passaggio (in mezzo ci sono probabilmente documenti non riconosciuti).
La data è sempre «dedotta»: non si presenta mai come certa.

Profilo di serie (serie.ini), facoltativo:
  data_interna        sì | no   (predefinito: sì per i file senza data completa del contenitore, salvo i
                                 periodici [tipo = periodico]; no per gli altri)
  data_interna_anni   1949-1976 (anni ammessi per i documenti)
  data_interna_distanza  30000 (caratteri massimi tra l'intestazione e il passaggio; predefinito 30000)

Uso da riga di comando (prova):
  python date_interne.py <file del corpus, relativo a data> [offset]   (senza offset: tutte le intestazioni)
"""
import bisect
import re
import sys
from collections import Counter
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent

# ---------------------------------------------------------------- riconoscimento delle date
CIFRE_ZH = {"〇": 0, "零": 0, "○": 0, "Ｏ": 0, "O": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
            "七": 7, "八": 8, "九": 9}
_C = "〇零○Ｏ一二三四五六七八九十0-9０-９"
_S = r"[ \t　]*"                                    # spazi spuri dell'OCR tra i caratteri
_NUM = rf"[{_C}](?:{_S}[{_C}]){{0,2}}"
DATA_ZH = re.compile(rf"(?P<a>[一1１]{_S}[九9９八8８](?:{_S}[〇零○Ｏ一二三四五六七八九0-9０-９]){{2}}){_S}年"
                     rf"(?:{_S}(?P<m>{_NUM}){_S}月(?:{_S}(?P<g>{_NUM}){_S}[日目曰])?)?")
MESI = {
    "en": ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
           "novembre", "décembre"],
    "it": ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto", "settembre",
           "ottobre", "novembre", "dicembre"],
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
           "noviembre", "diciembre"],
    "de": ["januar", "februar", "märz", "april", "mai", "juni", "juli", "august", "september", "oktober",
           "november", "dezember"],
    "sq": ["janar", "shkurt", "mars", "prill", "maj", "qershor", "korrik", "gusht", "shtator", "tetor",
           "nëntor", "dhjetor"],
}
NUMERO_MESE = {}
for _lista in MESI.values():
    for _i, _m in enumerate(_lista, 1):
        NUMERO_MESE.setdefault(_m, _i)
_NOMI = "|".join(sorted(NUMERO_MESE, key=len, reverse=True))
DATA_LAT = re.compile(rf"(?:(?P<g1>\d{{1,2}})(?:er|\.)?\s+(?:de\s+)?)?(?P<m>{_NOMI})(?:\s+(?P<g2>\d{{1,2}}))?,?"
                      rf"\s+(?:de\s+)?(?P<a>1[6-9]\d\d|20\d\d)\b", re.IGNORECASE)
APERTE, CHIUSE = "（(《〔[【", "）)》〕]】"
DISTANZA = 30000
NOTE = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳*注"     # inizio di una nota a piè di pagina


def _numero_zh(s):
    """Numero da cifre cinesi o arabe, con 十: 二十七 -> 27, 十二 -> 12, 1 2 -> 12. None se non è un numero."""
    s = re.sub(r"\s+", "", s or "").translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    if not s:
        return None
    if s.isdigit():
        return int(s)
    if "十" in s:
        prima, _, dopo = s.partition("十")
        decine = CIFRE_ZH.get(prima, None) if prima else 1
        unita = CIFRE_ZH.get(dopo, None) if dopo else 0
        if decine is None or unita is None or "十" in dopo:
            return None
        return decine * 10 + unita
    cifre = [CIFRE_ZH.get(ch, int(ch) if ch.isdigit() else None) for ch in s]
    return None if None in cifre else int("".join(map(str, cifre)))


def _componi(anno, mese, giorno):
    """(iso, precisione) da numeri già letti; None se la data non esiste."""
    if not anno:
        return None
    if mese is None:
        return f"{anno:04d}", "anno"
    if not 1 <= mese <= 12:
        return None
    if giorno is None:
        return f"{anno:04d}-{mese:02d}", "mese"
    giorni = [31, 29 if anno % 4 == 0 and (anno % 100 or anno % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30,
              31, 30, 31][mese - 1]
    if not 1 <= giorno <= giorni:
        return f"{anno:04d}-{mese:02d}", "mese"           # giorno illeggibile (OCR): resta il mese
    return f"{anno:04d}-{mese:02d}-{giorno:02d}", "giorno"


def date_nel_testo(testo, inizio=0):
    """Tutte le date riconosciute: [(inizio, fine, iso, precisione, forma)] in ordine di posizione.
    Le date con il solo anno («1965 年») sono escluse: troppo spesso sono anni citati, non date di documenti."""
    out = []
    for m in DATA_ZH.finditer(testo, inizio):
        if not m.group("m"):
            continue
        anno = _numero_zh(m.group("a"))
        r = _componi(anno, _numero_zh(m.group("m")), _numero_zh(m.group("g")) if m.group("g") else None)
        if r:
            out.append((m.start(), m.end(), *r, m.group(0)))
    for m in DATA_LAT.finditer(testo, inizio):
        g = m.group("g1") or m.group("g2")
        r = _componi(int(m.group("a")), NUMERO_MESE[m.group("m").lower()], int(g) if g else None)
        if r:
            out.append((m.start(), m.end(), *r, m.group(0)))
    out.sort()
    return out


def _forma_normale(forma):
    return re.sub(r"\s+", "", forma).lower()


def intestazione(testo, a, b):
    """Forza della data come intestazione di documento: «forte», «debole» o None (data nel corpo del testo).
      forte   da sola sulla riga; tra parentesi a inizio o a fine riga; data d'agenzia (seguita da 讯 o 电)
      debole  tra parentesi in mezzo alla riga; a inizio riga seguita da una virgola o da 《
    Le deboli si trovano anche nella prosa («一九六○年六月，苏共领导在…», «《再论…》（一九五六年十二月）中写道»):
    DateDelTesto le accetta solo se precise al giorno."""
    spazi = " \t　"
    dopo = testo[b:b + 3].lstrip(spazi)
    if dopo[:1] in ("讯", "电"):
        return "forte"
    inizio_riga = testo.rfind("\n", 0, a) + 1
    fine_riga = testo.find("\n", b)
    fine_riga = len(testo) if fine_riga < 0 else fine_riga
    prima_riga = testo[inizio_riga:a].strip(spazi)
    if prima_riga and prima_riga[0] in NOTE:                    # nota a piè di pagina: «② 考茨基给梅林的信（一八九八年七月十五日）。»
        return None
    # una data seguita dal punto fermo chiude una frase andata a capo («…abolished in / May 1965.»)
    fine_frase = testo[b:fine_riga].strip(spazi + CHIUSE)[:1] in (".", "。")
    resto_riga = testo[b:fine_riga].strip(spazi + ".,，。" + CHIUSE)
    if prima_riga and prima_riga[-1] in APERTE:
        if fine_frase:
            return "debole"
        return "forte" if not resto_riga or not prima_riga[:-1].strip(spazi) else "debole"
    if prima_riga:
        return None
    if not resto_riga:
        return None if fine_frase else "forte"
    return "debole" if dopo[:1] in ("，", ",", "《") else None


# ---------------------------------------------------------------- data interna di un passaggio
class DateDelTesto:
    """Date d'intestazione di un file, per trovare la data interna di qualsiasi passaggio.

    anni: (minimo, massimo) ammessi per i documenti; ripetute: oltre quante ripetizioni una forma è una testatina;
    elenco: quante date d'intestazione entro 'raggio_elenco' caratteri fanno un indice o un sommario;
    distanza: oltre quanti caratteri dall'intestazione il passaggio resta senza data."""

    def __init__(self, testo, inizio=0, anni=None, ripetute=8, elenco=5, raggio_elenco=300, distanza=DISTANZA):
        self.testo, self.distanza = testo, distanza
        self.raggio_elenco, self.elenco = raggio_elenco, elenco
        tutte = date_nel_testo(testo, inizio)
        conta = Counter(_forma_normale(f) for *_, f in tutte)
        lo, hi = anni or (1800, 2100)
        self.intestazioni = []
        for a, b, iso, prec, f in tutte:
            if not lo <= int(iso[:4]) <= hi or (prec != "giorno" and conta[_forma_normale(f)] > ripetute):
                continue
            forza = intestazione(testo, a, b)
            if forza == "forte" or (forza == "debole" and prec == "giorno"):
                self.intestazioni.append({"posizione": a, "fine": b, "data": iso, "precisione": prec,
                                          "forma": re.sub(r"\s+", " ", f).strip(), "forza": forza})
        self._pos = [d["posizione"] for d in self.intestazioni]

    def in_elenco(self, offset):
        """Vero se intorno al punto ci sono molte date d'intestazione fitte (indice, sommario, cronologia)."""
        a = bisect.bisect_left(self._pos, offset - self.raggio_elenco)
        b = bisect.bisect_right(self._pos, offset + self.raggio_elenco)
        return b - a >= self.elenco

    def per_offset(self, offset):
        """Data interna del passaggio la cui prima occorrenza è in 'offset': dict o None se non si deduce."""
        i = bisect.bisect_right(self._pos, offset) - 1
        if i < 0 or self.in_elenco(offset):
            return None
        d = self.intestazioni[i]
        if self.distanza and offset - d["posizione"] > self.distanza:
            return None
        return {"data": d["data"], "precisione": d["precisione"], "stato": "dedotto", "forma": d["forma"],
                "intestazione": d["forza"], "posizione": d["posizione"], "distanza": offset - d["posizione"]}


def anni_ammessi(meta, profilo):
    """(minimo, massimo) per gli anni dei documenti: dal profilo (data_interna_anni = 1949-1976), altrimenti
    fino all'anno di edizione del contenitore (YEAR), quando c'è."""
    m = re.fullmatch(r"\s*(\d{4})\s*[-–]\s*(\d{4})\s*", (profilo or {}).get("data_interna_anni", ""))
    if m:
        return int(m.group(1)), int(m.group(2))
    anno = re.match(r"\s*(\d{4})", meta.get("YEAR", "") or "")
    return 1800, int(anno.group(1)) if anno else 2100


def applicabile(meta, profilo, data_contenitore=""):
    """La data interna si cerca nei file senza data completa del contenitore (raccolte, volumi), ma non nei
    periodici (un fascicolo senza data resta un fascicolo), salvo che il profilo di serie dica altrimenti
    (data_interna = sì | no)."""
    pr = profilo or {}
    v = pr.get("data_interna", "").strip().lower()
    if v in ("sì", "si", "yes", "true", "1"):
        return True
    if v in ("no", "false", "0") or pr.get("tipo", "").strip() == "periodico":
        return False
    # una data al mese (AAAA-MM, es. un rapporto datato «November 1971») vale come data del contenitore
    return not re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", data_contenitore or meta.get("DATE", "") or "")


def per_file(testo, meta, inizio, rel="", data_contenitore=""):
    """DateDelTesto per un file, o None se la data interna non si applica a quel file."""
    from citazioni import profilo_di
    pr = profilo_di(meta, rel)
    if not applicabile(meta, pr, data_contenitore):
        return None
    distanza = (pr or {}).get("data_interna_distanza", "").strip()
    return DateDelTesto(testo, inizio, anni_ammessi(meta, pr), distanza=int(distanza) if distanza.isdigit() else DISTANZA)


# ---------------------------------------------------------------- passaggi già estratti
_CACHE = {}


def _date_del_file(path, rel):
    if path not in _CACHE:
        if len(_CACHE) > 50:
            _CACHE.clear()
        from estrai_occorrenze import leggi_intestazione
        try:
            testo = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            testo = ""
        meta, inizio = leggi_intestazione(testo)
        _CACHE[path] = per_file(testo, meta, inizio, rel) if testo else None
    return _CACHE[path]


def _dati(dati):
    if dati is None:
        sys.path.insert(0, str(CARTELLA))
        from llm import leggi_config, percorso
        dati = percorso(leggi_config(), "dati")
    return Path(dati)


def per_passaggio(c, dati=None):
    """Data interna di un passaggio di passaggi.jsonl / classificati.jsonl: quella registrata all'estrazione,
    altrimenti calcolata ora dal file (passaggi estratti prima del lavoro 9). None se non si deduce."""
    if "data_interna" in c:
        return c["data_interna"]
    if not c.get("file") or "offset" not in c:
        return None
    d = _date_del_file(_dati(dati) / c["file"], c["file"])
    return d.per_offset(c["offset"]) if d else None


def anno_del_documento(c, dati=None):
    """(anno, data interna) per filtrare un passaggio per periodo. Nelle raccolte vale l'anno della data interna,
    None se non si deduce: mai l'anno di edizione del volume. Negli altri file, l'anno della data del contenitore."""
    data = c.get("data") or ""
    anno_contenitore = int(data[:4]) if data[:4].isdigit() else None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", data):
        return anno_contenitore, None
    if "data_interna" in c:
        di = c["data_interna"]
    else:
        d = _date_del_file(_dati(dati) / c["file"], c["file"]) if c.get("file") and "offset" in c else None
        if d is None:                                   # la data interna non si applica a questo file
            return anno_contenitore, None
        di = d.per_offset(c["offset"])
    return (int(di["data"][:4]) if di else None), di


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    sys.path.insert(0, str(CARTELLA))
    from estrai_occorrenze import leggi_intestazione
    from llm import leggi_config, percorso
    rel = sys.argv[1].replace("\\", "/")
    testo = (percorso(leggi_config(), "dati") / rel).read_text(encoding="utf-8", errors="replace")
    meta, inizio = leggi_intestazione(testo)
    d = per_file(testo, meta, inizio, rel)
    if d is None:
        sys.exit("Data interna non applicabile a questo file (data completa del contenitore o profilo di serie).")
    if len(sys.argv) > 2:
        print(d.per_offset(int(sys.argv[2])) or "nessuna data interna deducibile")
        return
    for x in d.intestazioni:
        print(f"{x['posizione']:>9}  {x['data']:<10}  {'elenco ' if d.in_elenco(x['posizione']) else ''}{x['forma']}")
    print(f"{len(d.intestazioni)} date d'intestazione")


if __name__ == "__main__":
    main()

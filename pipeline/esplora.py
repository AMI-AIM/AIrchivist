#!/usr/bin/env python3
"""
Esplorazione delle fonti prima di creare la scheda di un'entità nuova (usato dal server MCP).

esplora_nome: dato un nome (come lo scrive l'utente) e qualche indizio (paese, partito, in cinese e in
lingua occidentale), restituisce le forme del nome ATTESTATE nelle fonti, con conteggi per serie e anno,
esempi e un controllo del contesto. Le forme cinesi vengono da due vie:
  - le candidate proposte dal modello della chat (trascrizioni secondo l'uso Xinhua), verificate qui;
  - l'allineamento tra le testate dichiarato nei profili (allinea_con): dove una serie nomina la persona (oggi la
    Peking Review), nell'altra serie dei giorni precedenti (oggi il Renmin Ribao, tre settimane) si cercano i nomi
    trascritti con il punto centrale accanto all'indizio (es. 比利时).
  - per le fonti albanesi, le trascrizioni albanesi del nome (la stampa albanese scrive i nomi stranieri come si
    pronunciano e li declina: Grippa -> Gripa, Gripës), generate qui come ipotesi e cercate nei testi albanesi.
Nessuna forma viene proposta per la scheda se non compare nelle fonti.

cerca_testo: ricerca libera di una parola o di una frase, con conteggi ed esempi.
"""
import datetime as dt
import re
from collections import Counter, defaultdict

import profili
from estrai_occorrenze import is_cjk
from sintesi import MESI_IT

NOME_CINESE = re.compile(r"[\u4e00-\u9fff]{1,8}(?:[·・•][\u4e00-\u9fff]{1,8})+")
# Caratteri usati nelle trascrizioni dei nomi occidentali (uso Xinhua, elenco largo): servono a staccare il
# nome dalle parole attaccate prima e dopo ("夫人玛德琳·格里巴为首的" -> "玛德琳·格里巴")
TRASCRIZIONE = set(
    "阿埃艾爱安昂奥澳巴拔邦包保鲍贝本比彼毕庇别宾滨波玻伯勃博布查柴达戴丹道德得登邓迪蒂丁东杜敦多厄恩尔"
    "法范方菲费芬丰冯夫福弗伏盖甘冈高戈哥格根古瓜哈海汉豪赫亨洪胡华怀霍基吉加贾杰捷金津居卡凯坎康柯科克"
    "肯库夸奎昆拉腊莱赖兰朗劳勒雷蕾里理利莉丽列林琳伦卢鲁路吕罗洛马玛迈麦曼芒毛梅美门蒙孟米密敏明莫默"
    "姆穆纳娜奈南内尼妮宁纽努诺欧帕派潘庞佩彭皮珀蒲普齐奇恰乔切钦琴丘萨塞赛桑瑟森沙莎尚绍舍什施舒斯松"
    "苏索塔泰坦汤唐特滕提图托瓦万汪旺威韦维温文沃乌伍武西希锡夏谢辛休许雅亚扬杨耶伊因英尤约泽扎詹兹"
    "茨琼黛缪娅露丝琪薇芙翰蓬荣容瑞若撒热日史鄂贡朱祖佐乔卜契娇廉梭汶沛罕裘讷迦歇顿迭斐惠佳嘉珍韩")
MESI_EN = "january february march april may june july august september october november december".split()


def senza_accenti(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


class Lettore:
    """Righe dei file sorgente, lette una volta sola per chiamata."""

    def __init__(self, dati):
        self.dati, self.cache = dati, {}

    def righe(self, rel):
        if rel not in self.cache:
            if len(self.cache) > 300:
                self.cache.clear()
            try:
                self.cache[rel] = (self.dati / rel).read_text(encoding="utf-8", errors="replace").split("\n")
            except OSError:
                self.cache[rel] = []
        return self.cache[rel]

    def intorno(self, rel, n, k=1):
        r = self.righe(rel)
        return " ".join(r[max(0, n - 1 - k):n + k])

    def pagina(self, rel, n, rx):
        """Pagina più vicina prima della riga, secondo l'espressione del profilo (es. 第N版 del Renmin Ribao)."""
        r = self.righe(rel)
        for i in range(min(n, len(r)) - 1, max(-1, n - 600), -1):
            m = re.search(rx, r[i])
            if m:
                return m.group(1)
        return ""


def riferimento(x, lettore):
    """Riferimento in italiano: «Renmin Ribao, 4 maggio 1966, p. 3». La pagina viene dalla pagina_regex del
    profilo della serie; la data del numero si aggiunge ai periodici la cui citazione non la contiene."""
    cit = x.get("citazione") or x.get("serie") or x["file"]
    m = re.search(r"(\d{1,2}) ([A-Za-z]+) (\d{4})", cit)
    if m and m.group(2).lower() in MESI_EN:
        cit = cit.replace(m.group(0), f"{int(m.group(1))} {MESI_IT[MESI_EN.index(m.group(2).lower())]} {m.group(3)}")
    serie, rel = x.get("serie", ""), x["file"]
    if profili.e_periodico(serie, rel) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", x.get("data") or ""):
        d = dt.date.fromisoformat(x["data"])
        data_it = f"{d.day} {MESI_IT[d.month - 1]} {d.year}"
        if data_it not in cit:
            cit += f", {data_it}"
    rx = profili.pagina_regex(serie, rel)
    p = lettore.pagina(rel, x["riga"], rx) if rx else ""
    if p:
        cit += f", p. {p}"
    return cit


def serie_indice(ind, fonti):
    """Nomi di serie dell'indice per le fonti richieste: i file del gruppo di profili di ciascuna (Hongqi = Hongqi
    + Red Flag; documenti = le raccolte, che nell'indice hanno il proprio nome), più i nomi dati così come sono."""
    gruppi = set().union(*(profili.serie_del_gruppo(f) for f in fonti))
    return {r[2] for r in ind._file().values() if profili.nome_di(r[2], r[1]) in gruppi} | set(fonti)


def estratto(testo, trovato, n=60):
    i = testo.find(trovato)
    if i < 0:
        return testo[:2 * n]
    return ("…" if i > n else "") + testo[max(0, i - n):i + len(trovato) + n] + ("…" if i + len(trovato) + n < len(testo) else "")


def riassunto(righe, lettore, indizi=(), esempi=2):
    """Conteggi per serie e anno, forme trovate, quota di righe con un indizio, esempi."""
    per = defaultdict(Counter)
    for r in righe:
        per[r["serie"]][str(r["anno"] or "senza data")] += 1
    ind = [i.lower() for i in indizi if i.strip()]
    con = sum(1 for r in righe if any(i in lettore.intorno(r["file"], r["riga"]).lower() for i in ind)) if ind else None
    scelti = righe[:1] + righe[len(righe) // 2:len(righe) // 2 + 1] + righe[-1:] if len(righe) > 2 else righe
    return {"totale": len(righe),
            "per_serie_e_anno": {s: dict(sorted(c.items())) for s, c in per.items()},
            "forme_trovate": dict(Counter(r["trovato"] for r in righe).most_common(6)),
            **({"con_indizio": f"{con}/{len(righe)}"} if ind else {}),
            "esempi": [{"riferimento": riferimento(r, lettore), "file_e_riga": f"{r['file']}, riga {r['riga']}",
                        "testo": estratto(r["testo"], r["trovato"])} for r in scelti[:esempi + 1]]}


def pulisci_nome(grezzo):
    """Stacca il nome trascritto dalle parole attaccate: il primo pezzo si accorcia da sinistra, l'ultimo da
    destra, fino al primo carattere che non si usa nelle trascrizioni."""
    pezzi = re.split(r"[·・•]", grezzo)
    primo, ultimo = pezzi[0], pezzi[-1]
    i = len(primo)
    while i > 0 and primo[i - 1] in TRASCRIZIONE:
        i -= 1
    j = 0
    while j < len(ultimo) and ultimo[j] in TRASCRIZIONE:
        j += 1
    pezzi[0], pezzi[-1] = primo[i:], ultimo[:j]
    if not pezzi[0] or len(pezzi[-1]) < 2 or any(not x for x in pezzi):
        return ""
    return "·".join(pezzi)


def candidati_nel_testo(testo, indizi=()):
    """Possibili nomi trascritti in un brano: nomi con il punto centrale e sequenze di 3-7 caratteri da
    trascrizione (anche i cognomi da soli, come 汪德尔林顿). Gli indizi (es. 意大利) vengono prima tolti dal
    testo, perché non si mescolino ai nomi vicini (意大利马列 -> 利马列)."""
    for i in indizi:
        testo = testo.replace(i, "｜")
    out = set()
    for m in NOME_CINESE.finditer(testo):
        nome = pulisci_nome(m.group(0))
        if nome:
            out.add(nome)
    for m in re.finditer(r"[%s]{3,7}" % "".join(sorted(TRASCRIZIONE)), testo):
        out.add(m.group(0))
    return out


def allinea(ind, lettore, righe_latine, indizi_cjk, origine, destinazione, giorni_prima=21, massimo_date=25):
    """Nomi trascritti che compaiono nella serie 'destinazione' vicino a un indizio (entro 3 righe), nei
    'giorni_prima' giorni prima di ogni numero della serie 'origine' che nomina la persona (profili: allinea_con,
    allinea_giorni; oggi Peking Review -> Renmin Ribao, tre settimane). Restituisce
    (forma, numeri in cui compare, numeri esaminati, righe di tutte le fonti che la contengono)."""
    da_origine = serie_indice(ind, [origine])
    date = sorted({r["data"] for r in righe_latine if r["serie"] in da_origine
                   and re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.get("data") or "")})
    if not date or not indizi_cjk:
        return []
    if len(date) > massimo_date:                       # campione distribuito su tutto il periodo
        passo = len(date) / massimo_date
        date = [date[int(i * passo)] for i in range(massimo_date)]
    giorni = {(dt.date.fromisoformat(d) - dt.timedelta(days=k)).isoformat()
              for d in date for k in range(giorni_prima + 1)}
    righe_indizio = []
    for i in indizi_cjk:
        righe_indizio += ind.cerca(i, serie=serie_indice(ind, [destinazione]), solo_date=giorni,
                                   massimo_righe=200000)
    per_data = defaultdict(list)
    for r in righe_indizio:
        per_data[r["data"]].append(r)
    supporto = Counter()
    for d in date:
        fine = dt.date.fromisoformat(d)
        visti = set()
        for k in range(0, giorni_prima + 1):
            for r in per_data.get((fine - dt.timedelta(days=k)).isoformat(), []):
                visti |= candidati_nel_testo(lettore.intorno(r["file"], r["riga"], 3), indizi_cjk)
        for nome in visti:
            if not any(nome in i for i in indizi_cjk):
                supporto[nome] += 1
    soglia = max(2, round(len(date) * 0.3))
    scelti = []
    for nome, n in supporto.most_common(40):
        if n < soglia:
            break
        totale = ind.conta(nome)
        # troppo frequente rispetto alle settimane in cui accompagna la persona: nome di paese, città ecc.
        if totale > 40 * n:
            continue
        scelti.append((nome, n, len(date), totale))
    # tra forme contenute l'una nell'altra con lo stesso sostegno tengo la più lunga
    finali = [x for x in scelti if not any(x[0] != y[0] and x[0] in y[0] and y[1] >= x[1] for y in scelti)]
    return finali[:8]


# ---------------------------------------------------------------- trascrizioni albanesi (ipotesi)
REGOLE_TRASCRIZIONE = {
    "italiano": {"sci": "shi", "sce": "she", "gli": "lj", "gn": "nj", "cci": "çi", "cce": "çe", "ci": "çi",
                 "ce": "çe", "ggi": "xhi", "gge": "xhe", "gi": "xhi", "ge": "xhe", "chi": "ki", "che": "ke",
                 "ghi": "gi", "ghe": "ge", "qu": "ku", "zz": "c", "z": "c", "c": "k", "h": ""},
    "francese": {"cques": "k", "eaux": "o", "eau": "o", "aux": "o", "au": "o", "ou": "u", "oi": "ua", "ch": "sh",
                 "gn": "nj", "qu": "k", "ge": "zhe", "gi": "zhi", "j": "zh", "ce": "se", "ci": "si", "c": "k",
                 "y": "i", "w": "v"},
    "inglese": {"sh": "sh", "ch": "ç", "th": "t", "j": "xh", "w": "u", "y": "j", "ee": "i", "oo": "u", "c": "k"},
    "tedesco o olandese": {"tsch": "ç", "sch": "sh", "ij": "ej", "oe": "u", "w": "v", "z": "c", "ei": "aj",
                           "eu": "oj"},
}
DESINENZE_ALBANESI = ["ës", "ën", "es", "en", "it", "in", "i", "a", "ja", "së", "ut", "un", "u", "ët"]


def _applica(parola, regole):
    rx = re.compile("|".join(sorted(map(re.escape, regole), key=len, reverse=True)))
    return rx.sub(lambda m: regole[m.group(0)], parola)


def forme_albanesi(nome):
    """Ipotesi di trascrizione albanese di un nome straniero, con le radici per trovare le forme declinate.
    Restituisce [(forma, origine)]. Sono solo ipotesi: contano quelle che compaiono nei testi."""
    base = senza_accenti(nome).lower().strip()
    if not base or is_cjk(base):
        return []
    ipotesi = {}

    def aggiungi(forma, origine):
        forma = re.sub(r"\s+", " ", forma).strip()
        if len(forma.replace(" ", "")) < 3:
            return
        forma = " ".join("-".join(p[:1].upper() + p[1:] for p in w.split("-")) for w in forma.split())
        if forma.lower() != base:
            ipotesi.setdefault(forma, origine)

    for lingua, regole in REGOLE_TRASCRIZIONE.items():
        t = _applica(base, regole)
        if lingua == "francese":
            t = re.sub(r"(?<=[aeiou])s(?=[aeiou])", "z", t)
            t = re.sub(r"(?<=[^aeiou\s])(?:es|s|t|x|d)\b", "", t)
        for v in {re.sub(r"([^lr\W])\1", r"\1", t), re.sub(r"(\w)\1", r"\1", t)}:
            aggiungi(v, f"trascrizione albanese ipotetica (pronuncia {lingua})")
    aggiungi(re.sub(r"(\w)\1", r"\1", base), "trascrizione albanese ipotetica (doppie semplificate)")
    # radici per le forme declinate (Gripa -> Gripës, Gripën): oltre 4 lettere trovano anche le desinenze
    for forma in list(ipotesi) + [nome]:
        f2 = senza_accenti(forma)
        radice = re.sub(r"[aeë]$", "", f2)
        if radice == f2:
            continue
        if len(radice.replace(" ", "")) >= 5:
            ipotesi.setdefault(radice, "radice per le forme declinate")
        else:
            for d in DESINENZE_ALBANESI:
                ipotesi.setdefault(radice + d, "forma declinata ipotetica")
    return list(ipotesi.items())


def esplora_nome(ind, dati, nome, indizi=None, candidate=None, dal=None, al=None):
    lettore = Lettore(dati)
    indizi = [i for i in (indizi or []) if i.strip()]
    forme = [nome] + [c for c in (candidate or []) if c.strip() and c.strip() != nome]
    latine = [f for f in forme if not is_cjk(f)]
    cinesi = [f for f in forme if is_cjk(f)]
    out = {"nome": nome, "forme_latine": {}, "forme_cinesi": {}, "forme_albanesi": {}, "dall_allineamento": [],
           "non_attestate": []}

    righe_latine = []
    provate = []
    for f in latine:
        # le fonti spesso omettono gli accenti ("Desire Trifaux"); se la forma intera manca, provo il cognome
        tentativi = [f] + ([senza_accenti(f)] if senza_accenti(f) != f else [])
        for t in tentativi:
            if t in provate:
                continue
            provate.append(t)
            r = ind.cerca(t, dal, al)
            if r:
                out["forme_latine"][t] = riassunto(r, lettore, indizi)
                righe_latine += r
                break
            out["non_attestate"].append(t)
        # il cognome da solo: nelle fonti il nome intero spesso manca ("Comrade Trifaux")
        parole = senza_accenti(f).split()
        if len(parole) > 1 and len(parole[-1]) >= 5 and parole[-1] not in provate:
            provate.append(parole[-1])
            r = ind.cerca(parole[-1], dal, al)
            if r:
                s_ = riassunto(r, lettore, indizi)
                s_["attenzione"] = "solo il cognome: può indicare altre persone con lo stesso cognome"
                out["forme_latine"][parole[-1]] = s_
                righe_latine += r

    # fonti albanesi: trascrizioni e forme declinate, cercate solo nei testi albanesi
    try:
        ci_sono_testi_albanesi = bool(ind.lingue().get("sq"))
    except Exception:
        ci_sono_testi_albanesi = False
    if ci_sono_testi_albanesi:
        gia = set(provate) | set(out["forme_latine"])
        coperte = set()          # righe già trovate da una forma precedente: una forma che non ne aggiunge si scarta
        basi = []
        for f in latine:
            basi.append(f)
            parole = f.split()
            if len(parole) > 1 and len(parole[-1]) >= 4:
                basi.append(parole[-1])
        for b in basi:
            for forma, origine in forme_albanesi(b):
                if forma in gia:
                    continue
                gia.add(forma)
                r = ind.cerca(forma, dal, al, lingue={"sq"})
                nuove = {(x["file"], x["riga"]) for x in r} - coperte
                if not nuove:
                    continue
                coperte |= nuove
                s_ = riassunto(r, lettore, indizi)
                s_["origine"] = origine
                if b != f and b == b.split()[-1] or "radice" in origine or len(forma) <= 5:
                    s_["attenzione"] = ("radice o forma breve: può trovare altre parole o altre persone"
                                        if "radice" in origine or len(forma) <= 5 else
                                        "solo il cognome: può indicare altre persone con lo stesso cognome")
                out["forme_albanesi"][forma] = s_

    # allineamenti tra serie dichiarati nei profili (allinea_con; oggi Peking Review -> Renmin Ribao): le forme
    # trovate così sono solo candidate
    indizi_cjk = [i for i in indizi if is_cjk(i)]
    dall_allineamento, origine_di = [], {}
    for orig, dest, giorni_prima in profili.allineamenti():
        for cand, n, tot, righe_rr in allinea(ind, lettore, righe_latine, indizi_cjk, orig, dest, giorni_prima):
            if cand in origine_di:
                continue
            dall_allineamento.append(cand)
            origine_di[cand] = orig
            out["dall_allineamento"].append({"forma": cand, "settimane_con_la_forma": f"{n}/{tot}",
                                             "allineamento": f"{orig} -> {dest}", "righe_in_tutte_le_fonti": righe_rr})

    date_latine = [dt.date.fromisoformat(r["data"]) for r in righe_latine
                   if re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.get("data") or "")]
    anni_latini = {r["anno"] for r in righe_latine if r["anno"]}
    da_valutare = []
    for f in cinesi + [c for c in dall_allineamento if c not in cinesi]:
        r = ind.cerca(f, dal, al)
        if not r:
            out["non_attestate"].append(f)
            continue
        s = riassunto(r, lettore, indizi)
        anni = {x["anno"] for x in r if x["anno"]}
        if anni_latini:
            s["anni_in_comune_con_le_forme_latine"] = f"{len(anni & anni_latini)}/{len(anni)}"
        vicine = None
        if date_latine:          # quante righe cadono entro 30 giorni da una menzione nelle fonti inglesi
            date_r = [dt.date.fromisoformat(x["data"]) for x in r if re.fullmatch(r"\d{4}-\d{2}-\d{2}", x.get("data") or "")]
            if date_r:
                vicine = sum(1 for d in date_r if any(abs((d - e).days) <= 30 for e in date_latine)) / len(date_r)
                s["vicine_alle_menzioni_inglesi"] = f"{round(100 * vicine)}%"
        breve = len(f) <= 3 and "·" not in f and "・" not in f
        quota = None
        if "con_indizio" in s:
            a_, b_ = s["con_indizio"].split("/")
            quota = int(a_) / max(1, int(b_))
        if breve or (quota is not None and quota < 0.3):
            s["attenzione"] = ("forma breve: può indicare altre persone" if breve else
                               "spesso senza l'indizio accanto: possibili omonimi")
        if f in cinesi:
            out["forme_cinesi"][f] = s
        elif len(r) >= 2 and (quota is None or quota >= 0.5) and (vicine is None or vicine >= 0.5):
            s["origine"] = f"allineamento con {origine_di.get(f, 'un’altra serie')}"
            out["forme_cinesi"][f] = s           # candidata forte: entra nella proposta
        else:
            da_valutare.append(f)
    for x in out["dall_allineamento"]:
        x["esito"] = "proposta" if x["forma"] in out["forme_cinesi"] else \
            "non attestata nel periodo" if x["forma"] in out["non_attestate"] else "debole: probabilmente un altro nome"

    tutte = {**out["forme_latine"], **out["forme_cinesi"], **out["forme_albanesi"]}
    dall_allin = [f for f, s in out["forme_cinesi"].items() if s.get("origine")]
    base = [f for f in tutte if f not in dall_allin and f not in out["forme_albanesi"]]
    out["proposta_di_scheda"] = {
        "varianti": base,
        "da_confermare_dall_allineamento": dall_allin,
        "da_confermare_albanesi": list(out["forme_albanesi"]),
        "forme_ambigue": [f for f in tutte if "attenzione" in tutte[f]],
        "contesto": indizi,
        "nota": "Mostra all'utente le forme con conteggi ed esempi. Le forme trovate con l'allineamento possono "
                "essere nomi di altre persone citate negli stessi articoli: chiedi conferma una per una. Le forme "
                "non attestate e quelle deboli non vanno nella scheda; le forme_ambigue vanno sempre smistate. Le forme albanesi "
                "sono ipotesi di trascrizione trovate nei testi albanesi: mostra gli esempi e chiedi conferma una per una."}
    return out


def cerca_testo(ind, dati, testo, dal=None, al=None, fonti=None, massimo=8, da=0):
    lettore = Lettore(dati)
    serie = serie_indice(ind, fonti) if fonti else None
    r = ind.cerca(testo, dal, al, serie)
    per = defaultdict(Counter)
    for x in r:
        per[x["serie"]][str(x["anno"] or "senza data")] += 1
    da, massimo = int(da or 0), min(int(massimo or 8), 15)
    return {"testo": testo, "totale": len(r), "per_serie_e_anno": {s: dict(sorted(c.items())) for s, c in per.items()},
            "mostrati": f"{da + 1}-{min(da + massimo, len(r))}" if r else "0",
            "risultati": [{"riferimento": riferimento(x, lettore), "file_e_riga": f"{x['file']}, riga {x['riga']}",
                           "testo": estratto(x["testo"], x["trovato"], 90)} for x in r[da:da + massimo]],
            "nota": "Ricerca testuale senza lettura: le righe non sono state valutate per pertinenza. Le parole "
                    "latine di 5 lettere o più si trovano anche dentro parole più lunghe (l'OCR incolla le parole)."}

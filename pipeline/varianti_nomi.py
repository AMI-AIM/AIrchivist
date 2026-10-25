#!/usr/bin/env python3
"""
Varianti dei nomi tra lingue e scritture, generate dal motore per esplora_nome (non affidate al modello della chat).

  indizi_tradotti     paesi, nazionalità e partiti scritti in caratteri latini (italiano, inglese, francese,
                      spagnolo, tedesco, albanese) -> forme cinesi: «Italia», «Italian», «italiano» -> 意大利, 意共
  trascrizioni_cinesi trascrizione approssimata sul modello Xinhua dei nomi in caratteri latini, con varianti
                      (Berlinguer -> 贝林格, 贝尔林格, 贝林格尔 ...; Enrico Berlinguer -> 恩里科·贝林格 ...)
  partiti_cinesi      nomi di partito: Communist Party of Italy (Marxist-Leninist) -> 意大利共产党（马克思列宁主义）,
                      意大利共产党（马列）, 意大利（马列）共产党 ...

Le forme generate sono ipotesi: esplora_nome le cerca nelle fonti e propone solo quelle attestate, con conteggi,
esempi e la quota di righe accanto agli indizi. La trascrizione segue le regole più comuni della tavola Xinhua dei
nomi stranieri, non tutte le sue eccezioni: le varianti per sillaba servono a coprire le scelte più frequenti.
"""
import itertools
import re
import unicodedata

# ---------------------------------------------------------------- paesi e partiti
# (forma cinese del paese, sigle cinesi dei partiti comunisti, forme latine: nome e aggettivo in it/en/fr/es/de/sq)
PAESI = [
    ("意大利", ["意共"], "italia italy italie italien italian italiano italiana italiani italienne italienisch itali italisë italian"),
    ("法国", ["法共"], "francia france frankreich franca francës french francese francais français francés frances französisch"),
    ("比利时", ["比共"], "belgio belgium belgique bélgica belgica belgien belgjika belgjikës belgian belga belge belgisch"),
    ("西班牙", ["西共"], "spagna spain espagne españa espana spanien spanja spanjës spanish spagnolo espagnol español espanol spanisch"),
    ("葡萄牙", ["葡共"], "portogallo portugal portugalia portugalisë portuguese portoghese portugais portugués portugues portugiesisch"),
    ("德国", ["德共"], "germania germany allemagne alemania deutschland gjermania gjermanisë german tedesco allemand alemán aleman deutsch"),
    ("西德", [], "germania occidentale west germany allemagne de l'ouest bundesrepublik"),
    ("奥地利", ["奥共"], "austria autriche österreich osterreich austrisë austrian austriaco autrichien austriaco österreichisch"),
    ("瑞士", [], "svizzera switzerland suisse suiza schweiz zvicra zvicrës swiss svizzero suisse suizo schweizer"),
    ("荷兰", ["荷共"], "olanda paesi bassi netherlands holland pays-bas países bajos niederlande hollanda holandës dutch olandese néerlandais neerlandes holländisch"),
    ("英国", ["英共"], "gran bretagna inghilterra britain great britain england united kingdom royaume-uni angleterre gran bretaña inglaterra großbritannien england britania britanisë british inglese britannique británico britanico britisch"),
    ("瑞典", ["瑞共"], "svezia sweden suède suecia schweden suedia suedisë swedish svedese suédois sueco schwedisch"),
    ("挪威", ["挪共"], "norvegia norway norvège noruega norwegen norvegjia norvegjisë norwegian norvegese norvégien noruego norwegisch"),
    ("丹麦", ["丹共"], "danimarca denmark danemark dinamarca dänemark danimarka danimarkës danish danese danois danés danes dänisch"),
    ("芬兰", ["芬共"], "finlandia finland finlande finnland finlanda finlandës finnish finlandese finlandais finlandés finnisch"),
    ("冰岛", [], "islanda iceland islande islandia island islandës icelandic islandese islandais"),
    ("希腊", ["希共"], "grecia greece grèce griechenland greqia greqisë greek greco grec griego griechisch"),
    ("土耳其", [], "turchia turkey turquie turquía turquia türkei turqia turqisë turkish turco turc türkisch"),
    ("南斯拉夫", ["南共"], "jugoslavia yugoslavia yougoslavie jugoslawien jugosllavia jugosllavisë yugoslav jugoslavo yougoslave"),
    ("阿尔巴尼亚", ["阿劳动党"], "albania albanie albanien shqipëria shqiperia shqipërisë albanian albanese albanais albanés albanisch shqiptar"),
    ("罗马尼亚", ["罗共"], "romania roumanie rumänien rumania rumanisë romanian rumeno roumain rumano rumänisch"),
    ("波兰", ["波兰统一工人党"], "polonia poland pologne polen polonisë polish polacco polonais polaco polnisch"),
    ("苏联", ["苏共"], "unione sovietica urss soviet union ussr union soviétique unión soviética sowjetunion bashkimi sovjetik soviet sovietico soviétique soviético sowjetisch"),
    ("美国", ["美共"], "stati uniti usa united states america états-unis estados unidos vereinigte staaten shtetet e bashkuara american americano américain estadounidense amerikanisch amerikan"),
    ("加拿大", ["加共"], "canada canadá kanada kanadasë canadian canadese canadien canadiense kanadisch"),
    ("巴西", ["巴西共"], "brasile brazil brésil brasil brasilien brazili brazilit brazilian brasiliano brésilien brasileño brasileno brasilianisch"),
    ("阿根廷", ["阿共"], "argentina argentine argentinien argjentina argjentinës argentinian argentino argentin"),
    ("智利", ["智共"], "cile chile chili chiles kili kilit chilean cileno chilien chileno chilenisch"),
    ("秘鲁", ["秘共"], "perù peru pérou perú peruja perusë peruvian peruviano péruvien peruano peruanisch"),
    ("玻利维亚", ["玻共"], "bolivia bolivie bolivien bolivia bolivisë bolivian boliviano bolivien"),
    ("哥伦比亚", ["哥共"], "colombia colombie kolumbien kolumbia kolumbisë colombian colombiano colombien"),
    ("厄瓜多尔", ["厄共"], "ecuador équateur ekuador ekuadorit ecuadorian ecuadoriano équatorien ecuatoriano"),
    ("委内瑞拉", ["委共"], "venezuela vénézuela venezuelës venezuelan venezuelano vénézuélien venezolano"),
    ("乌拉圭", ["乌共"], "uruguay uruguai uruguaj uruguajit uruguayan uruguaiano uruguayen uruguayo"),
    ("海地", [], "haiti haïti haití haitian haitiano haïtien"),
    ("多米尼加", [], "repubblica dominicana dominican republic république dominicaine república dominicana dominican dominicano"),
    ("古巴", ["古共"], "cuba kuba kubës cuban cubano cubain"),
    ("墨西哥", ["墨共"], "messico mexico mexique méxico mexiko meksika meksikës mexican messicano mexicain mexicano"),
    ("日本", ["日共"], "giappone japan japon japón japonia japonisë japanese giapponese japonais japonés japanisch"),
    ("印度尼西亚", ["印尼共"], "indonesia indonésie indonesien indonezia indonezisë indonesian indonesiano indonésien indonesio"),
    ("印度", ["印共"], "india inde indien indisë indian indiano indien indio indisch"),
    ("锡兰", ["锡共"], "ceylon ceylan ceilan cejlon ceylonese cingalese"),
    ("缅甸", ["缅共"], "birmania burma birmanie myanmar birmani birmanisë burmese birmano birman"),
    ("泰国", ["泰共"], "thailandia thailand thaïlande tailandia tajlanda tajlandës thai thailandese thaïlandais tailandés"),
    ("马来亚", ["马共"], "malaya malesia malaysia malaisie malasia malajzia malajzisë malayan malese malais"),
    ("菲律宾", ["菲共"], "filippine philippines filipinas philippinen filipine filipineve filipino philippin filippino"),
    ("越南", ["越南劳动党"], "vietnam viet nam viêt nam vijetnam vietnamit vietnamese vietnamita vietnamien"),
    ("朝鲜", ["朝鲜劳动党"], "corea korea corée kore koresë korean coreano coréen"),
    ("老挝", [], "laos lao laotian laotiano laotien"),
    ("柬埔寨", [], "cambogia cambodia cambodge camboya kambodscha kamboxhia kamboxhias cambodian cambogiano cambodgien kampuchea"),
    ("澳大利亚", ["澳共"], "australia australie australien australisë australian australiano australien"),
    ("新西兰", ["新西兰共产党"], "nuova zelanda new zealand nouvelle-zélande nueva zelanda neuseeland zelanda e re new zealander neozelandese néo-zélandais"),
    ("伊朗", [], "iran irán iranian iraniano iranien persia"),
    ("伊拉克", [], "iraq irak iraqi iracheno irakien"),
    ("黎巴嫩", [], "libano lebanon liban líbano libanon libani libanit lebanese libanese libanais libanés"),
    ("巴勒斯坦", [], "palestina palestine palästina palestinian palestinese palestinien palestino"),
    ("刚果", [], "congo kongo congolese congolais congoleño"),
    ("马达加斯加", [], "madagascar madagaskar malgascio malagasy malgache"),
    ("苏丹", [], "sudan soudan sudán sudanese soudanais sudanés"),
    ("中国", ["中共"], "cina china chine chinas kina kinës chinese cinese chinois chino chinesisch"),
]
PAROLE_PARTITO = [
    # (espressione regolare sul nome latino normalizzato, forma cinese)
    (r"marxist[\s-]*lenin|marxiste[\s-]*l[ée]nin|marxista[\s-]*lenin|marxistisch[\s-]*lenin|\bm[\s-]*l\b|\(m-?l\)|marksist[\s-]*lenin", "马列"),
    (r"communist|comunista|communiste|kommunist|komunist", "共产党"),
    (r"workers|ouvrier|obrero|operaio|arbeiter|punëtor|punetor", "工人党"),
    (r"labou?r|travail|trabajo|lavoro|arbeit|punës|punes", "劳动党"),
    (r"socialist|socialiste|sozialist|socialist", "社会党"),
]


def normale(s):
    """Minuscole senza accenti."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", (s or "").lower()) if not unicodedata.combining(ch))


def paesi_nel_testo(testo):
    """Paesi nominati in un testo latino: [(forma cinese, sigle dei partiti)], nell'ordine della tavola."""
    t = " " + re.sub(r"[^a-z' -]", " ", normale(testo)) + " "
    out = []
    for zh, sigle, forme in PAESI:
        voci = sorted({normale(x) for x in re.split(r"\s{2,}|(?<=[a-z])\s(?=[a-z])", forme)} | set(normale(forme).split()),
                      key=len, reverse=True)
        if any(re.search(rf"(?<![a-z]){re.escape(v)}(?![a-z])", t) for v in voci if len(v) >= 4):
            out.append((zh, sigle))
    return out


def indizi_tradotti(indizi):
    """Forme cinesi di paesi e partiti indicati tra gli indizi in caratteri latini (senza ripetizioni)."""
    out = []
    for i in indizi or []:
        for zh, sigle in paesi_nel_testo(i):
            for f in [zh] + sigle:
                if f not in out:
                    out.append(f)
    return out


# ---------------------------------------------------------------- trascrizione cinese (modello Xinhua)
CONSONANTI = ["ch", "sh", "ts", "b", "p", "m", "f", "v", "d", "t", "n", "l", "g", "k", "h", "j", "r", "s", "z", "w", "y"]
SILLABE = {   # vocale (con eventuale n finale) -> {consonante iniziale: caratteri alternativi}
    "a": {"": "阿", "b": "巴", "p": "帕巴", "m": "马", "f": "法", "v": "瓦", "d": "达", "t": "塔达", "n": "纳", "l": "拉",
          "g": "加", "k": "卡加", "h": "哈", "j": "贾雅", "r": "拉", "s": "萨", "z": "扎", "ch": "查", "sh": "沙", "ts": "察",
          "w": "瓦", "y": "亚雅"},
    "e": {"": "埃", "b": "贝伯", "p": "佩贝", "m": "梅", "f": "费", "v": "韦", "d": "德", "t": "特德", "n": "内",
          "l": "莱勒", "g": "格", "k": "克", "h": "赫", "j": "热", "r": "雷勒", "s": "塞", "z": "泽", "ch": "切契", "sh": "舍契谢",
          "ts": "采", "w": "韦", "y": "耶"},
    "i": {"": "伊", "b": "比", "p": "皮比", "m": "米", "f": "菲", "v": "维", "d": "迪", "t": "蒂迪", "n": "尼", "l": "利里",
          "g": "吉", "k": "基", "h": "希", "j": "吉", "r": "里利", "s": "西", "z": "齐", "ch": "奇齐契", "sh": "希", "ts": "齐",
          "w": "威", "y": "伊"},
    "o": {"": "奥", "b": "博", "p": "波", "m": "莫", "f": "福", "v": "沃", "d": "多", "t": "托多", "n": "诺", "l": "洛",
          "g": "戈", "k": "科戈", "h": "霍", "j": "乔", "r": "罗洛", "s": "索", "z": "佐", "ch": "乔", "sh": "肖", "ts": "措",
          "w": "沃", "y": "约"},
    "u": {"": "乌", "b": "布", "p": "普布", "m": "穆", "f": "富", "v": "武", "d": "杜", "t": "图", "n": "努", "l": "卢",
          "g": "古", "k": "库", "h": "胡", "j": "朱", "r": "鲁", "s": "苏", "z": "祖", "ch": "丘", "sh": "舒", "ts": "楚",
          "w": "武", "y": "尤"},
    "an": {"": "安", "b": "班", "p": "潘", "m": "曼", "f": "凡", "v": "万", "d": "丹", "t": "坦", "n": "南", "l": "兰",
           "g": "甘", "k": "坎", "h": "汉", "j": "让", "r": "兰朗", "s": "桑", "z": "赞", "ch": "钱", "sh": "尚", "ts": "灿",
           "w": "万", "y": "扬"},
    "en": {"": "恩", "b": "本", "p": "彭", "m": "门", "f": "芬", "v": "文", "d": "登", "t": "滕", "n": "嫩", "l": "伦",
           "g": "根", "k": "肯", "h": "亨", "j": "让", "r": "伦", "s": "森", "z": "曾", "ch": "琴", "sh": "申", "ts": "岑",
           "w": "文", "y": "延"},
    "in": {"": "因", "b": "宾", "p": "平", "m": "明", "f": "芬", "v": "温", "d": "丁", "t": "廷", "n": "宁", "l": "林",
           "g": "金", "k": "金", "h": "欣", "j": "金", "r": "林", "s": "辛", "z": "津", "ch": "钦", "sh": "欣", "ts": "津",
           "w": "温", "y": "因"},
    "on": {"": "翁", "b": "邦", "p": "蓬", "m": "蒙", "f": "丰", "v": "冯", "d": "东", "t": "通", "n": "农", "l": "隆",
           "g": "贡", "k": "孔", "h": "洪", "j": "琼", "r": "龙", "s": "松", "z": "宗", "ch": "琼", "sh": "雄", "ts": "聪",
           "w": "翁", "y": "永"},
    "un": {"": "温", "b": "本", "p": "蓬", "m": "蒙", "f": "丰", "v": "文", "d": "敦", "t": "通", "n": "农", "l": "伦",
           "g": "贡", "k": "昆", "h": "洪", "j": "容", "r": "伦", "s": "孙", "z": "尊", "ch": "春", "sh": "顺", "ts": "聪",
           "w": "温", "y": "云"},
}
FINALI = {"b": "布伯", "p": "普", "m": "姆", "f": "夫弗", "v": "夫弗", "d": "德", "t": "特", "n": "恩", "l": "尔",
          "g": "格", "k": "克", "h": "赫", "j": "日", "r": "尔", "s": "斯", "z": "兹茨", "ch": "奇", "sh": "什施",
          "ts": "茨", "w": "", "y": ""}   # caratteri alternativi per la consonante isolata
CADUCHE = {"r", "l", "h"}       # consonanti che la tavola spesso lascia cadere (Berlinguer -> 贝林格)
MASSIMO_VARIANTI = 48


def fonetica(parola):
    """Grafia latina -> grafia fonetica semplificata (regole comuni a italiano, francese, spagnolo, inglese,
    tedesco). Restituisce le varianti più probabili (c/g davanti a e, i: dura o dolce)."""
    p = re.sub(r"[^a-z]", "", normale(parola))
    if not p:
        return []
    varianti_base = [p]
    muta = re.sub(r"(?<=[a-z]{3})(ques|que|es|e|s|t|x|d)$", lambda m: "k" if m.group(1).startswith("qu") else "", p)
    if muta != p:                                            # francese: finali mute (Jacques -> 雅克)
        varianti_base.append(muta)
    if re.match(r"s[tp]", p):                                # tedesco: st, sp iniziali (Strobl -> 施特罗伯尔)
        varianti_base.append("sh" + p[1:])
    out = []
    for base in varianti_base:
        for a, b in (("sch", "sh"), ("ph", "f"), ("th", "t"), ("ck", "k"), ("qu", "ku"), ("gli", "li"), ("gn", "ni"),
                     ("ou", "u"), ("eu", "e"), ("ae", "e"), ("au", "o"), ("x", "ks"), ("y", "i"), ("w", "v"),
                     ("tz", "ts"), ("zz", "ts")):
            base = base.replace(a, b)
        base = re.sub(r"gu(?=[ei])", "G", base)               # Berlinguer, Guevara: g dura (G resta dura)
        base = re.sub(r"gh(?=[ei])", "G", base)
        base = re.sub(r"ch(?=[ei])", "k", base)               # italiano: che, chi
        base = re.sub(r"([bcdfgklmnprstvz])\1", r"\1", base)  # doppie
        dolce = re.sub(r"sc(?=[ei])", "sh", base)
        dolce = re.sub(r"c(?=[ei])", "ch", dolce)             # italiano: Enrico, Dinucci
        dolce = re.sub(r"g(?=[ei])", "j", dolce)
        dura = re.sub(r"c(?=[ei])", "s", base)                # francese, spagnolo
        for v in (dolce, dura, base):
            v = re.sub(r"c(?!h)", "k", v).replace("G", "g")
            if v not in out:
                out.append(v)
    return out


def sillabe(f):
    """Grafia fonetica -> [(consonante iniziale, vocale con n finale o '' per consonante isolata)]."""
    out, i = [], 0
    vocali = "aeiou"
    while i < len(f):
        cons = next((c for c in CONSONANTI if f.startswith(c, i)), "")
        j = i + len(cons)
        if j < len(f) and f[j] in vocali:
            v = f[j]
            # due vocali: la seconda apre una nuova sillaba (Pajetta, Bueno); «ie», «ia» come una sola
            nasale = j + 1 < len(f) and f[j + 1] == "n" and (j + 2 >= len(f) or f[j + 2] not in vocali)
            if nasale and v + "n" in SILLABE:
                out.append((cons, v + "n"))
                i = j + 2
            else:
                out.append((cons, v))
                i = j + 1
        elif cons:
            out.append((cons, ""))
            i = j
        else:
            i += 1                                          # carattere non previsto: si salta
    return out


def trascrivi(parola):
    """Trascrizioni cinesi di una parola (un nome o un cognome), con le varianti più comuni."""
    risultati = []
    for f in fonetica(parola):
        scelte = []
        for k, (cons, voc) in enumerate(sillabe(f)):
            if voc:
                scelte.append(list(SILLABE[voc].get(cons, SILLABE[voc][""])))
            else:
                car = list(FINALI.get(cons, ""))
                scelte.append(car + [""] if cons in CADUCHE or not car else car)
        for combo in itertools.product(*scelte):
            forma = "".join(combo)
            if len(forma) >= 2 and forma not in risultati:
                risultati.append(forma)
            if len(risultati) >= MASSIMO_VARIANTI:
                return risultati
    return risultati


def trascrizioni_cinesi(nome, massimo_combinati=12, cognomi=None):
    """Trascrizioni cinesi di un nome di persona: cognome da solo e nome·cognome. 'cognomi': le trascrizioni del
    cognome già trovate nelle fonti (esplora_nome le cerca prima), da combinare con il nome proprio; senza, si
    combinano le prime varianti generate."""
    parole = [p for p in re.split(r"[\s\-]+", nome or "") if re.search(r"[A-Za-zÀ-ÿ]", p)]
    if not parole:
        return []
    cognome = trascrivi(parole[-1])
    out = list(cognome)
    if len(parole) > 1:
        nomi = trascrivi(parole[0])[:6 if cognomi else 4]
        base = list(cognomi)[:4] if cognomi else cognome[:max(1, massimo_combinati // max(1, len(nomi)))]
        for n, c in itertools.product(nomi, base):
            forma = f"{n}·{c}"
            if forma not in out:
                out.append(forma)
    return out


# ---------------------------------------------------------------- nomi di partito
def partiti_cinesi(nome):
    """Forme cinesi di un nome di partito latino («Communist Party of Italy (Marxist-Leninist)»)."""
    n = normale(nome)
    paesi = paesi_nel_testo(nome)
    if not paesi:
        return []
    tipi = [zh for rx, zh in PAROLE_PARTITO if re.search(rx, n)]
    ml = "马列" in tipi
    tipi = [t for t in tipi if t != "马列"]
    out = []
    for zh, sigle in paesi[:1]:
        if not tipi and ml:                                 # «Marxist-Leninist Party of Austria»
            out += [f"{zh}马克思列宁主义党", f"{zh}马列主义党"]
        for t in tipi:
            out.append(f"{zh}{t}")
            if ml:
                out += [f"{zh}{t}（马克思列宁主义）", f"{zh}{t}（马列）", f"{zh}（马列）{t}", f"{zh}（马克思列宁主义）{t}"]
        if ml and sigle:
            out += [f"{s}（马列）" for s in sigle if s.endswith("共")]
    return list(dict.fromkeys(out))

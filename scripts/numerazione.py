#!/usr/bin/env python3
"""
Pagine stampate dei PDF importati (importa.py), per i marcatori [[p. N | pdf K]] che le citazioni usano.

Tre fonti, nell'ordine (la prima che risponde vale per tutto il documento):
  1. indicazione dell'operatore: --prima-pagina N [--da-pagina K] = la pagina K del PDF è la p. N, le seguenti
     proseguono (le pagine prima di K non ricevono marcatore). Certa.
  2. etichette di pagina del PDF (PageLabels: molti PDF, per esempio di JSTOR, dichiarano «p. 61»). Dichiarate dal
     file, come la pagina stampata delle esportazioni PAGE/ALTO. Non valgono se ripetono soltanto la posizione nel
     PDF (1, 2, 3...: etichette predefinite, non la numerazione stampata).
  3. numero stampato in testa o in piede della pagina (righe di testatina con il numero da solo, o il numero
     all'inizio o alla fine della riga). Si accetta solo uno scarto costante tra numero stampato e posizione nel
     PDF, confermato su almeno 3 pagine e sulla maggior parte delle pagine che hanno un numero. Da lì in poi ogni
     pagina riceve la sua pagina; quelle senza numero leggibile la ricevono per continuità, annotata «dedotta».
     Se lo scarto cambia (pagine mancanti nella scansione), valgono i tratti a scarto costante confermati da
     almeno due pagine ciascuno (da_tratti). Lo stato del campo PAGES è «dedotto».
Altrimenti nessun marcatore: una pagina senza numero non è una pagina «non numerata».
"""
import re
from collections import Counter

# etichetta «p. 61», «Page 61», «61», «xii»: si tiene il numero (arabo o romano)
ETICHETTA = re.compile(r"^\s*(?:p(?:age|ag)?\.?\s*)?([0-9]{1,4}[a-z]?|[ivxlcdm]{1,8})\s*$", re.IGNORECASE)
# numero di pagina in una riga di testatina o di piede
NUMERO_SOLO = re.compile(r"^[\s\-–—.·|=~_]*(?:p(?:age|ag)?\.?\s*)?(\d{1,4})[\s\-–—.·|=~_]*$", re.IGNORECASE)
NUMERO_IN_TESTA = re.compile(r"^(\d{1,4})\s{1,}\S")          # «102 HISTORY OF THE PLA»
NUMERO_IN_CODA = re.compile(r"\S\s{1,}(\d{1,4})$")           # «THE WORLD TODAY 63»
# cifre lette come lettere dall'OCR, in un gruppo che ha già almeno una cifra: s/S -> 5, l/I/i -> 1, o/O -> 0
CIFRE_OCR = str.maketrans("sSlIioO", "5511100")
CONFUSO_IN_TESTA = re.compile(r"^([0-9sSlIioO]{2,4})\s+\S")
CONFUSO_IN_CODA = re.compile(r"\S\s+([0-9sSlIioO]{2,4})$")
RIGHE_DI_BORDO = 2
# il numero da solo sulla riga si cerca più in dentro: nei documenti d'archivio declassificati («-14-») stanno
# sotto di lui il timbro «25X1», la classifica «SECRET» e la dicitura della declassificazione
RIGHE_NUMERO_SOLO = 5
MINIMO_CONFERME = 3
MINIMO_TRATTO = 2            # pagine lette che confermano un tratto a scarto costante (da_tratti)
PAGINE_INDIETRO = 1          # pagine prima della prima letta che ricevono il numero per continuità
ANNO_PROBABILE = 1000        # con meno di MINIMO_CONFERME letture, un numero da qui in su è più probabilmente un anno


def da_etichette(etichette):
    """{posizione nel PDF (da 1): pagina} dalle etichette; {} se mancano o ripetono solo la posizione."""
    pagine = {}
    for k, e in enumerate(etichette or [], 1):
        m = ETICHETTA.match(e or "")
        if m:
            pagine[k] = m.group(1)
    if not pagine or all(p == str(k) for k, p in pagine.items()):
        return {}
    return pagine


def numeri_di_bordo(testo):
    """Numeri candidati a pagina stampata nelle prime e ultime righe non vuote della pagina."""
    righe = [r.strip() for r in (testo or "").splitlines() if r.strip()]

    def bordo(n):
        return righe[:n] + righe[-n:] if len(righe) > 2 * n else righe
    out = set()
    for r in bordo(RIGHE_DI_BORDO):
        for espr in (NUMERO_IN_TESTA, NUMERO_IN_CODA):
            m = espr.search(r) if espr is NUMERO_IN_CODA else espr.match(r)
            if m:
                out.add(int(m.group(1)))
        # l'OCR confonde le cifre delle testatine con lettere: «s2 di ARMANDO», «…socialist t S1» (52, 51)
        for espr in (CONFUSO_IN_TESTA, CONFUSO_IN_CODA):
            m = espr.search(r)
            if m and re.search(r"\d", m.group(1)):
                out.add(int(m.group(1).translate(CIFRE_OCR)))
    for r in bordo(RIGHE_NUMERO_SOLO):
        m = NUMERO_SOLO.match(r)
        if m:
            out.add(int(m.group(1)))
    return out


def da_testo(testi):
    """({posizione: (pagina, letta)}, scarto) dai numeri stampati; ({}, None) se non si ricava una numerazione.
    scarto è un numero se è costante, altrimenti l'elenco degli scarti dei tratti (da_tratti)."""
    candidati = {k: numeri_di_bordo(t) for k, t in enumerate(testi, 1)}
    con_numero = [k for k, c in candidati.items() if c]
    scarti = Counter(n - k for k, c in candidati.items() for n in c)
    if not scarti:
        return {}, None
    # con poche letture un numero che sembra un anno non conta («socialist I 15» e «Tiranë 1962» in una pagina);
    # due scarti diversi con le stesse letture («1», il numero del documento, e «I 15», la testatina) sono
    # un'ambiguità: meglio nessun numero che uno sbagliato
    if scarti.most_common(1)[0][1] < MINIMO_CONFERME:
        scarti = Counter({s: n for s, n in scarti.items() if s + 1 < ANNO_PROBABILE}) or scarti
    (scarto, conferme), *altri = scarti.most_common()
    if conferme < MINIMO_CONFERME and altri and altri[0][1] == conferme:
        return da_tratti(candidati, len(testi), len(con_numero))
    n_pagine = len(testi)
    # i documenti brevi non arrivano a MINIMO_CONFERME pagine: ne bastano tante quante le loro pagine (al più 2),
    # ma un numero di quattro cifre letto una o due volte è più probabilmente un anno («në mars të 1964.»)
    min_conferme = min(MINIMO_CONFERME, n_pagine, 2) if n_pagine <= 3 else MINIMO_CONFERME
    if conferme < min_conferme or conferme * 2 <= len(con_numero) or \
            (conferme < MINIMO_CONFERME and scarto + 1 >= ANNO_PROBABILE):
        return da_tratti(candidati, n_pagine, len(con_numero))
    lette = {k for k, c in candidati.items() if k + scarto in c}
    # la prima pagina di un documento spesso non ha la testatina: la numerazione vale anche per la pagina che
    # precede la prima letta (dedotta), non oltre (copertine e frontespizi non ricevono un numero)
    prima = max(1, min(lette) - PAGINE_INDIETRO)
    return {k: (str(k + scarto), k in lette) for k in range(prima, n_pagine + 1) if k + scarto >= 1}, scarto


def da_tratti(candidati, n_pagine, n_con_numero):
    """Numerazione con lo scarto che cambia lungo il documento (pagine mancanti nella scansione: nei documenti
    d'archivio declassificati p. 10 alla posizione 21, p. 21 alla 31, p. 32 alla 41). Si cerca la sequenza più
    lunga di numeri crescenti con le posizioni; la si divide in tratti a scarto costante e si tengono i tratti
    confermati da almeno MINIMO_TRATTO pagine. Ogni tratto vale dalla sua prima pagina letta all'ultima (l'ultimo
    fino alla fine); le pagine tra un tratto e l'altro restano senza marcatore, perché non si sa dove cada la
    pagina mancante. Serve che i tratti tengano almeno MINIMO_CONFERME pagine e più di metà di quelle con un numero."""
    letti = sorted((k, n) for k, c in candidati.items() for n in c)
    if not letti:
        return {}, None
    # sequenza crescente più lunga (posizione e numero entrambi crescenti, una lettura per posizione)
    lunghezza, prec = [1] * len(letti), [-1] * len(letti)
    for i, (k, n) in enumerate(letti):
        for j in range(i):
            kj, nj = letti[j]
            if kj < k and nj < n and lunghezza[j] + 1 > lunghezza[i]:
                lunghezza[i], prec[i] = lunghezza[j] + 1, j
    i = max(range(len(letti)), key=lambda x: lunghezza[x])
    catena = []
    while i >= 0:
        catena.append(letti[i])
        i = prec[i]
    catena.reverse()
    tratti = []                                       # [scarto, [posizioni lette]]
    for k, n in catena:
        if tratti and tratti[-1][0] == n - k:
            tratti[-1][1].append(k)
        else:
            tratti.append([n - k, [k]])
    tratti = [t for t in tratti if len(t[1]) >= MINIMO_TRATTO]
    tenute = sum(len(t[1]) for t in tratti)
    if len(tratti) < 2 or tenute < MINIMO_CONFERME or tenute * 2 <= n_con_numero:
        return {}, None
    pagine = {}
    for i, (scarto, lette) in enumerate(tratti):
        fine = n_pagine if i == len(tratti) - 1 else max(lette)
        for k in range(min(lette), fine + 1):
            if k + scarto >= 1:
                pagine[k] = (str(k + scarto), k in lette)
    return pagine, [t[0] for t in tratti]


def numera(testi, etichette=None, prima_pagina=None, da_pagina=1):
    """Pagine stampate di un PDF. Restituisce ({posizione: (pagina, annotazione)}, info) con info = {"metodo",
    "stato" ("" o "dedotto"), "nota"}. annotazione è "" oppure "dedotta" (pagina senza numero leggibile)."""
    n = len(testi)
    if prima_pagina:
        da = max(1, int(da_pagina or 1))
        pagine = {k: (str(int(prima_pagina) + k - da), "") for k in range(da, n + 1)}
        return pagine, {"metodo": "indicata all'importazione", "stato": "",
                        "nota": f"pagina {da} del PDF = p. {prima_pagina}"}
    pagine = da_etichette(etichette)
    if pagine:
        return {k: (p, "") for k, p in pagine.items()}, {"metodo": "etichette di pagina del PDF", "stato": "",
                                                         "nota": "dichiarate dal PDF"}
    lette, scarto = da_testo(testi)
    if lette:
        dedotte = sum(1 for _, letta in lette.values() if not letta)
        if isinstance(scarto, list):
            come = (f"scarto per tratti ({', '.join(f'{s:+d}' for s in scarto)}: pagine mancanti nella scansione; "
                    f"le pagine tra un tratto e l'altro sono senza numero)")
        else:
            come = f"scarto costante {scarto:+d} dalla posizione nel PDF"
        return ({k: (p, "" if letta else "dedotta") for k, (p, letta) in lette.items()},
                {"metodo": "numeri stampati nel testo", "stato": "dedotto",
                 "nota": f"numero stampato letto in {len(lette) - dedotte} pagine su {len(lette)}, {come}"
                         + ("; le altre per continuità" if dedotte else "")})
    return {}, {"metodo": "", "stato": "", "nota": ""}


def marcatore(pagina, posizione, annotazione=""):
    """[[p. N | pdf K]], o [[p. N | pdf K, dedotta]]."""
    return f"[[p. {pagina} | pdf {posizione}" + (f", {annotazione}" if annotazione else "") + "]]"

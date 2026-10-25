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
     Lo stato del campo PAGES è «dedotto».
Altrimenti nessun marcatore: una pagina senza numero non è una pagina «non numerata».
"""
import re
from collections import Counter

# etichetta «p. 61», «Page 61», «61», «xii»: si tiene il numero (arabo o romano)
ETICHETTA = re.compile(r"^\s*(?:p(?:age|ag)?\.?\s*)?([0-9]{1,4}[a-z]?|[ivxlcdm]{1,8})\s*$", re.IGNORECASE)
# numero di pagina in una riga di testatina o di piede
NUMERO_SOLO = re.compile(r"^[\s\-–—.·|]*(?:p(?:age|ag)?\.?\s*)?(\d{1,4})[\s\-–—.·|]*$", re.IGNORECASE)
NUMERO_IN_TESTA = re.compile(r"^(\d{1,4})\s{1,}\S")          # «102 HISTORY OF THE PLA»
NUMERO_IN_CODA = re.compile(r"\S\s{1,}(\d{1,4})$")           # «THE WORLD TODAY 63»
RIGHE_DI_BORDO = 2
MINIMO_CONFERME = 3


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
    bordo = righe[:RIGHE_DI_BORDO] + righe[-RIGHE_DI_BORDO:] if len(righe) > 2 * RIGHE_DI_BORDO else righe
    out = set()
    for r in bordo:
        for espr in (NUMERO_SOLO, NUMERO_IN_TESTA, NUMERO_IN_CODA):
            m = espr.search(r) if espr is NUMERO_IN_CODA else espr.match(r)
            if m:
                out.add(int(m.group(1)))
    return out


def da_testo(testi):
    """({posizione: (pagina, letta)}, scarto) dai numeri stampati; ({}, None) se lo scarto non è costante."""
    candidati = {k: numeri_di_bordo(t) for k, t in enumerate(testi, 1)}
    con_numero = [k for k, c in candidati.items() if c]
    scarti = Counter(n - k for k, c in candidati.items() for n in c)
    if not scarti:
        return {}, None
    scarto, conferme = scarti.most_common(1)[0]
    if conferme < MINIMO_CONFERME or conferme * 2 <= len(con_numero):
        return {}, None
    lette = {k for k, c in candidati.items() if k + scarto in c}
    prima = min(lette)
    return {k: (str(k + scarto), k in lette) for k in range(prima, len(testi) + 1) if k + scarto >= 1}, scarto


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
        return ({k: (p, "" if letta else "dedotta") for k, (p, letta) in lette.items()},
                {"metodo": "numeri stampati nel testo", "stato": "dedotto",
                 "nota": f"numero stampato letto in {len(lette) - dedotte} pagine su {len(lette)}, scarto costante "
                         f"{scarto:+d} dalla posizione nel PDF" + ("; le altre per continuità" if dedotte else "")})
    return {}, {"metodo": "", "stato": "", "nota": ""}


def marcatore(pagina, posizione, annotazione=""):
    """[[p. N | pdf K]], o [[p. N | pdf K, dedotta]]."""
    return f"[[p. {pagina} | pdf {posizione}" + (f", {annotazione}" if annotazione else "") + "]]"

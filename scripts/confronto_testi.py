#!/usr/bin/env python3
"""
Confronto tra due letture dello stesso testo: CER (caratteri sbagliati, inseriti o mancanti / caratteri del
testo di confronto). Usato dalla prova dei motori OCR (prova_ocr.py) e dall'importazione, per scegliere tra lo
strato di testo di un PDF e un OCR rifatto (importa.py).

Normalizzazione: Unicode NFKC (parentesi e punteggiatura a larghezza piena = mezza larghezza); per cinese e
giapponese senza spazi né a capo (gli spazi tra i caratteri sono un artefatto dell'OCR); per le lingue in
alfabeto latino spazi ridotti a uno.
"""
import re
import unicodedata

LINGUE_SENZA_SPAZI = ("zh", "ja")


def lingua_da_ocr(lingue):
    """Codice di lingua per la normalizzazione da quello di Tesseract («chi_sim+eng» -> «zh»)."""
    l = (lingue or "").split("+")[0]
    return "zh" if l.startswith("chi") else "ja" if l.startswith("jpn") else l


def normalizza(testo, lingua):
    t = unicodedata.normalize("NFKC", testo or "")
    if lingua in LINGUE_SENZA_SPAZI:
        return re.sub(r"\s+", "", t)
    return re.sub(r"\s+", " ", t).strip()


def senza_punteggiatura(testo):
    return "".join(ch for ch in testo if not unicodedata.category(ch).startswith("P"))


def distanza(a, b):
    """Distanza di Levenshtein (sostituzioni, inserimenti, cancellazioni), con l'algoritmo a vettori di bit di Myers
    (1999) nella forma di Hyyrö (2003): una colonna della tabella è un intero di Python con un bit per carattere di b,
    e ogni carattere di a costa poche operazioni su quell'intero. Stesso risultato della tabella completa, ma una
    pagina di 3000 caratteri si confronta in centesimi di secondo invece che in decine di secondi (G5: era la parte
    più lenta dell'importazione dei documenti brevi)."""
    if len(a) < len(b):
        a, b = b, a
    m = len(b)
    if not m:
        return len(a)
    uguali = {}
    for i, c in enumerate(b):
        uguali[c] = uguali.get(c, 0) | (1 << i)
    tutti, alto = (1 << m) - 1, 1 << (m - 1)
    pv, mv, d = tutti, 0, m
    for c in a:
        eq = uguali.get(c, 0)
        xv = eq | mv
        xh = ((((eq & pv) + pv) & tutti) ^ pv) | eq
        ph = (mv | ~(xh | pv)) & tutti
        mh = pv & xh
        if ph & alto:
            d += 1
        elif mh & alto:
            d -= 1
        ph = ((ph << 1) | 1) & tutti
        mh = (mh << 1) & tutti
        pv = (mh | ~(xv | ph)) & tutti
        mv = ph & xv
    return d


def distanza_tabella(a, b):
    """Distanza di Levenshtein con la tabella completa: lenta, serve da riferimento nei test."""
    if len(a) < len(b):
        a, b = b, a
    prec = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cor = [i]
        for j, cb in enumerate(b, 1):
            cor.append(min(prec[j] + 1, cor[j - 1] + 1, prec[j - 1] + (ca != cb)))
        prec = cor
    return prec[-1]


def cer(letto, riferimento, lingua, punteggiatura=True):
    """(errori, caratteri del riferimento)."""
    r, l = normalizza(riferimento, lingua), normalizza(letto, lingua)
    if not punteggiatura:
        r, l = senza_punteggiatura(r), senza_punteggiatura(l)
    return distanza(l, r), len(r)

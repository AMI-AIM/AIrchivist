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
    """Distanza di Levenshtein (sostituzioni, inserimenti, cancellazioni)."""
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

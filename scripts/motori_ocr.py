#!/usr/bin/env python3
"""
Motori OCR intercambiabili (progettazione, sezione 4): ognuno legge un elenco di immagini e restituisce, per
ciascuna, (testo, confidenza 0-100 o None). Il testo ha una riga per riga stampata.

  tesseract   Tesseract, già usato da importa.py (lingue da LINGUE_OCR, modelli installati nel sistema);
              tesseract:N = con la segmentazione psm N (importa.py usa 1, o 3 senza il modello osd)
  kraken      Kraken: non funziona su Windows (serve Linux, per esempio WSL); dichiarato ma non disponibile

Le confidenze non sono confrontabili tra motori: ognuno le calcola a modo suo.
"""
import sys
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent


class Tesseract:
    nome = "tesseract"

    def __init__(self, cfg, lingua, psm=""):
        sys.path.insert(0, str(CARTELLA))
        from importa import LINGUE_OCR, Ocr
        self.lingue = LINGUE_OCR.get(lingua, lingua)
        self._ocr, self.motivo = None, ""
        try:
            self._ocr = Ocr(cfg, self.lingue)
            if psm:                                 # «tesseract:6»: segmentazione diversa da quella di importa.py
                self._ocr.psm = psm
        except SystemExit as e:                     # Tesseract o modelli mancanti: lo dice il messaggio
            self.motivo = str(e)

    def disponibile(self):
        return self._ocr is not None

    def descrizione(self):
        return f"Tesseract ({self.lingue}, psm {self._ocr.psm})" if self._ocr else "Tesseract"

    def leggi(self, immagini):
        out = []
        for img in immagini:
            testo, conf, _ = self._ocr.leggi_immagine(img)
            out.append((testo, conf))
        return out


class Kraken:
    nome = "kraken"
    motivo = ("Kraken non funziona su Windows: serve Linux (per esempio WSL, da installare con wsl --install, "
              "come amministratore)")

    def __init__(self, cfg, lingua):
        pass

    def disponibile(self):
        return False

    def descrizione(self):
        return "Kraken"

    def leggi(self, immagini):
        raise RuntimeError(self.motivo)


MOTORI = {m.nome: m for m in (Tesseract, Kraken)}


def crea(nome, cfg, lingua):
    """Motore per nome; «tesseract:6» = Tesseract con la segmentazione (psm) indicata."""
    base, _, variante = nome.partition(":")
    if base not in MOTORI:
        raise SystemExit(f"Motore sconosciuto: {nome}. Motori: {', '.join(MOTORI)} (tesseract:N per la psm N)")
    if variante and base != "tesseract":
        raise SystemExit(f"Solo tesseract ha varianti (tesseract:N): {nome}")
    return MOTORI[base](cfg, lingua, variante) if variante else MOTORI[base](cfg, lingua)

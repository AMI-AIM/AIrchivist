#!/usr/bin/env python3
"""
Motori OCR intercambiabili (progettazione, sezione 4): ognuno legge un elenco di immagini e restituisce, per
ciascuna, (testo, confidenza 0-100 o None). Il testo ha una riga per riga stampata.

  tesseract   Tesseract, già usato da importa.py (lingue da LINGUE_OCR, modelli installati nel sistema);
              tesseract:N = con la segmentazione psm N (importa.py usa 1, o 3 senza il modello osd)
  paddleocr   PaddleOCR, in un Python a parte (config.ini, [ocr] paddle_python, predefinito «py -3.13»):
              PaddlePaddle non supporta ancora il Python più recente; l'aiutante è ocr_paddle.py.
              Prova del 25/10/2026: su CPU Windows oneDNN non funziona (PaddlePaddle 3.3.1) e senza oneDNN una
              pagina richiede circa 50 s anche con i modelli mobile (Tesseract: 3-4 s); disinstallato
  kraken      Kraken: non funziona su Windows (serve Linux, per esempio WSL); dichiarato ma non disponibile

Le confidenze non sono confrontabili tra motori: ognuno le calcola a modo suo.
"""
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
LINGUE_PADDLE = {"zh": "ch", "sq": "sq", "en": "en", "fr": "fr", "it": "it", "de": "german", "es": "es",
                 "ru": "ru", "pt": "pt"}
SENZA_FINESTRA = getattr(subprocess, "CREATE_NO_WINDOW", 0)


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


class Paddle:
    nome = "paddleocr"

    def __init__(self, cfg, lingua):
        self.python = shlex.split(cfg.get("ocr", "paddle_python", fallback="") or "py -3.13", posix=False)
        self.lingua = LINGUE_PADDLE.get(lingua, "latin")
        self.motivo = ""
        try:
            r = subprocess.run(self.python + ["-c", "import paddleocr, sys; print(paddleocr.__version__)"],
                               capture_output=True, text=True, timeout=300, creationflags=SENZA_FINESTRA)
            self.versione = r.stdout.strip()
            if r.returncode != 0:
                self.motivo = "PaddleOCR non installato in " + " ".join(self.python)
        except (OSError, subprocess.TimeoutExpired) as e:
            self.versione, self.motivo = "", f"{' '.join(self.python)} non avviabile ({e})"

    def disponibile(self):
        return not self.motivo

    def descrizione(self):
        return f"PaddleOCR {self.versione} (lingua {self.lingua})"

    def leggi(self, immagini):
        r = subprocess.run(self.python + [str(CARTELLA / "ocr_paddle.py"), self.lingua] + [str(i) for i in immagini],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3600,
                           creationflags=SENZA_FINESTRA, env=_env_utf8())
        risultati = {}
        for riga in r.stdout.splitlines():
            if riga.startswith("{"):
                d = json.loads(riga)
                risultati[d["immagine"]] = d
        out = []
        for img in immagini:
            d = risultati.get(str(img))
            if not d or "errore" in d:
                raise RuntimeError((d or {}).get("errore") or (r.stderr.strip()[-600:] or "nessuna risposta"))
            righe = d["righe"]
            testo = "\n".join(t for t, *_ in righe)
            pesate = [(c, len(t)) for t, c, *_ in righe if c is not None and t]
            peso = sum(n for _, n in pesate)
            out.append((testo, round(100 * sum(c * n for c, n in pesate) / peso, 1) if peso else None))
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


MOTORI = {m.nome: m for m in (Tesseract, Paddle, Kraken)}


def _env_utf8():
    return dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")


def crea(nome, cfg, lingua):
    """Motore per nome; «tesseract:6» = Tesseract con la segmentazione (psm) indicata."""
    base, _, variante = nome.partition(":")
    if base not in MOTORI:
        raise SystemExit(f"Motore sconosciuto: {nome}. Motori: {', '.join(MOTORI)} (tesseract:N per la psm N)")
    if variante and base != "tesseract":
        raise SystemExit(f"Solo tesseract ha varianti (tesseract:N): {nome}")
    return MOTORI[base](cfg, lingua, variante) if variante else MOTORI[base](cfg, lingua)

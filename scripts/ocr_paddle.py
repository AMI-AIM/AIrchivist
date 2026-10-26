#!/usr/bin/env python3
"""
Aiutante di motori_ocr.py per PaddleOCR. Gira nel Python in cui PaddleOCR è installato (config.ini, [ocr]
paddle_python; PaddlePaddle non supporta ancora il Python più recente), non importa nulla del progetto.

Uso: python ocr_paddle.py <lingua PaddleOCR> <immagine> [<immagine> ...]
Scrive su stdout una riga JSON per immagine: {"immagine", "righe": [[testo, confidenza 0-1, y, x], ...]} oppure
{"immagine", "errore"}. Il modello si carica una volta sola per tutte le immagini.
"""
import json
import os
import sys

os.environ.setdefault("DISABLE_MODEL_SOURCE_CHECK", "True")    # niente controllo di rete a ogni avvio


def righe_v3(risultato):
    out = []
    for r in risultato:
        d = r.json["res"] if hasattr(r, "json") and "res" in r.json else dict(r)
        testi, punteggi = d.get("rec_texts", []), d.get("rec_scores", [])
        poligoni = d.get("rec_polys", d.get("dt_polys", []))
        for k, t in enumerate(testi):
            p = poligoni[k] if k < len(poligoni) else [[0, 0]]
            ys, xs = [float(q[1]) for q in p], [float(q[0]) for q in p]
            out.append([t, float(punteggi[k]) if k < len(punteggi) else None, min(ys), min(xs)])
    return out


def main():
    lingua, immagini = sys.argv[1], sys.argv[2:]
    from paddleocr import PaddleOCR
    try:
        # enable_mkldnn=False: con oneDNN PaddlePaddle 3 su CPU Windows si ferma con «ConvertPirAttribute2Runtime
        # Attribute not support»; senza è più lento ma funziona
        motore = PaddleOCR(lang=lingua, use_doc_orientation_classify=False, use_doc_unwarping=False,
                           use_textline_orientation=False, enable_mkldnn=False)
        v3 = True
    except TypeError:                                   # PaddleOCR 2.x
        motore, v3 = PaddleOCR(lang=lingua, use_angle_cls=False, show_log=False), False
    for img in immagini:
        try:
            if v3:
                righe = righe_v3(motore.predict(img))
            else:
                righe = [[t, float(c), min(q[1] for q in box), min(q[0] for q in box)]
                         for box, (t, c) in (motore.ocr(img, cls=False)[0] or [])]
            print(json.dumps({"immagine": img, "righe": righe}, ensure_ascii=False), flush=True)
        except Exception as e:
            print(json.dumps({"immagine": img, "errore": f"{type(e).__name__}: {e}"}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

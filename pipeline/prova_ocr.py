#!/usr/bin/env python3
"""
Prova dei motori OCR su campioni di scansioni (lavoro 11, fase 3): quale motore legge meglio una serie.

Ogni campione sta in risultati\\_prove\\ocr\\<nome>\\ (fuori dall'archivio delle letture):
  pNNN.png                    la pagina resa come immagine (dalla scansione, alla risoluzione indicata)
  pNNN.<motore>.txt           il testo letto da ciascun motore (tesseract_psm6 = tesseract:6); strato_pdf = il
                              testo già presente nel PDF, quando c'è, come termine di confronto
  pNNN.riferimento.txt        il testo di riferimento: nasce come copia della lettura di un motore e va corretto
                              a mano sull'immagine; conta solo dopo aver compilato la riga «# VERIFICATO_DA:»
  campione.json               fonte, pagine, lingua, risoluzione, motori, tempi e confidenze

Uso (nella cartella pipeline):
  python prova_ocr.py motori [--lingua zh]                      motori disponibili e perché gli altri no
  python prova_ocr.py prepara <pdf o immagini> --nome cina_icm --lingua zh --pagine 50,200 [--dpi 300]
                      [--motori tesseract,tesseract:3,tesseract:6] [--riferimento tesseract]
  python prova_ocr.py misura <nome> [<nome> ...]                CER per motore sulle pagine verificate

Misura: CER (caratteri sbagliati, inseriti o mancanti / caratteri del riferimento), calcolato dopo la
normalizzazione Unicode NFKC (parentesi e punteggiatura a larghezza piena = mezza larghezza) e senza spazi né a
capo per il cinese, con gli spazi ridotti a uno per le lingue in alfabeto latino; anche senza la punteggiatura.
Ordine delle righe: conta, perché un motore che scambia le colonne sbaglia davvero la lettura.
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
import unicodedata
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARTELLA))
VERIFICA = "# VERIFICATO_DA:"
ISTRUZIONI_RIF = ("# Riferimento per la prova OCR: correggi il testo sotto la riga «# ---» guardando l'immagine {img}\n"
                  "# (stesso ordine di lettura e stesse righe dell'originale; non correggere gli errori di stampa).\n"
                  "# Per il cinese spazi e a capo non contano: basta correggere i caratteri.\n"
                  "# Poi scrivi il tuo nome dopo VERIFICATO_DA: solo allora la pagina entra nella misura.\n"
                  "{verifica} \n"
                  "# Proposta iniziale: lettura di {motore}.\n# ---\n")


def cartella_prove(cfg):
    from llm import percorso
    return percorso(cfg, "risultati") / "_prove" / "ocr"


def leggi_config():
    from llm import leggi_config as lc
    return lc()


# ---------------------------------------------------------------- misura
def file_motore(nome):
    """Nome del motore nei nomi di file: «tesseract:6» -> «tesseract_psm6» (i due punti non valgono su Windows)."""
    return nome.replace(":", "_psm")


def normalizza(testo, lingua):
    t = unicodedata.normalize("NFKC", testo or "")
    if lingua in ("zh", "ja"):
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


def leggi_riferimento(f):
    """(testo, verificato_da) di un file di riferimento; verificato_da '' se la riga non è compilata."""
    righe = f.read_text(encoding="utf-8").splitlines()
    chi = next((r[len(VERIFICA):].strip() for r in righe if r.startswith(VERIFICA)), "")
    corpo = righe[next((k + 1 for k, r in enumerate(righe) if r.strip() == "# ---"), 0):]
    return "\n".join(corpo).strip(), chi


# ---------------------------------------------------------------- comandi
def pagine_da(sorgente, pagine, dpi, dest):
    """Immagini delle pagine richieste (1 = prima pagina) da un PDF, o le immagini indicate così come sono."""
    p = Path(sorgente)
    if p.suffix.lower() != ".pdf":
        return [(k, Path(x)) for k, x in enumerate([p] if p.is_file() else sorted(p.iterdir()), 1)
                if Path(x).suffix.lower() in (".png", ".jpg", ".jpeg", ".tif", ".tiff")]
    from importa import carica_pymupdf
    fitz = carica_pymupdf()
    out = []
    with fitz.open(p) as doc:
        for n in pagine:
            if not 1 <= n <= len(doc):
                raise SystemExit(f"Pagina {n} fuori dal PDF ({len(doc)} pagine).")
            img = dest / f"p{n:03d}.png"
            if not img.exists():
                doc[n - 1].get_pixmap(dpi=dpi, colorspace=fitz.csGRAY).save(img)
            out.append((n, img))
    return out


def cmd_motori(args):
    from motori_ocr import MOTORI, crea
    cfg = leggi_config()
    for nome in MOTORI:
        m = crea(nome, cfg, args.lingua)
        print(f"{nome:10} {'disponibile: ' + m.descrizione() if m.disponibile() else 'non disponibile: ' + m.motivo}")


def cmd_prepara(args):
    from motori_ocr import crea
    cfg = leggi_config()
    dest = cartella_prove(cfg) / args.nome
    dest.mkdir(parents=True, exist_ok=True)
    f_camp = dest / "campione.json"
    camp = json.loads(f_camp.read_text(encoding="utf-8")) if f_camp.exists() else {}
    pagine = [int(x) for x in re.split(r"[,\s]+", args.pagine or "") if x.strip()]
    if Path(args.sorgente).suffix.lower() == ".pdf" and not pagine:
        raise SystemExit("Indica le pagine del PDF: --pagine 12,40")
    immagini = pagine_da(args.sorgente, pagine, args.dpi, dest)
    camp.update({"sorgente": str(Path(args.sorgente).resolve()), "lingua": args.lingua, "dpi": args.dpi,
                 "pagine": [n for n, _ in immagini], "preparato_il": dt.date.today().isoformat()})
    camp.setdefault("motori", {})
    if Path(args.sorgente).suffix.lower() == ".pdf":
        # lo strato di testo già presente nel PDF (vecchio OCR o testo nativo) come termine di confronto:
        # importa.py lo usa al posto dell'OCR quando c'è
        from importa import carica_pymupdf, testo_utile
        with carica_pymupdf().open(args.sorgente) as doc:
            strati = {n: doc[n - 1].get_text("text") for n, _ in immagini}
        if any(testo_utile(t) for t in strati.values()):
            for n, t in strati.items():
                (dest / f"p{n:03d}.strato_pdf.txt").write_text(t.strip() + "\n", encoding="utf-8")
            camp["motori"]["strato_pdf"] = {"disponibile": True, "descrizione": "strato di testo del PDF",
                                            "secondi_per_pagina": 0, "confidenza": None}
    for nome in [m.strip() for m in args.motori.split(",") if m.strip()]:
        m = crea(nome, cfg, args.lingua)
        if not m.disponibile():
            print(f"{nome}: non disponibile ({m.motivo})")
            camp["motori"][nome] = {"disponibile": False, "motivo": m.motivo}
            continue
        print(f"{m.descrizione()}: {len(immagini)} pagine ...")
        t0 = time.time()
        letture = m.leggi([img for _, img in immagini])
        secondi = round((time.time() - t0) / max(1, len(immagini)), 1)
        for (n, img), (testo, conf) in zip(immagini, letture):
            (dest / f"p{n:03d}.{file_motore(nome)}.txt").write_text(testo + "\n", encoding="utf-8")
        confs = [c for _, c in letture if c is not None]
        camp["motori"][nome] = {"disponibile": True, "descrizione": m.descrizione(), "secondi_per_pagina": secondi,
                                "confidenza": round(sum(confs) / len(confs), 1) if confs else None}
        print(f"  {secondi} s per pagina (compreso l'avvio del motore)")
    rif = args.riferimento or next((n for n in ("paddleocr", "tesseract")
                                    if camp["motori"].get(n, {}).get("disponibile")), "")
    for n, img in immagini:
        f = dest / f"p{n:03d}.riferimento.txt"
        if f.exists() or not rif or not (dest / f"p{n:03d}.{file_motore(rif)}.txt").exists():
            continue                                  # un riferimento già esistente non si sovrascrive mai
        f.write_text(ISTRUZIONI_RIF.format(img=img.name, verifica=VERIFICA, motore=rif)
                     + (dest / f"p{n:03d}.{file_motore(rif)}.txt").read_text(encoding="utf-8"), encoding="utf-8")
    f_camp.write_text(json.dumps(camp, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nCampione in {dest}. Correggi i file pNNN.riferimento.txt sulle immagini e compila «VERIFICATO_DA:»; "
          f"poi: python prova_ocr.py misura {args.nome}")


def misura_campione(dest):
    """{motore: {"pagine", "errori", "caratteri", "errori_np", "caratteri_np", ...}} e pagine non verificate."""
    camp = json.loads((dest / "campione.json").read_text(encoding="utf-8"))
    lingua, out, da_verificare = camp["lingua"], {}, []
    for n in camp["pagine"]:
        f = dest / f"p{n:03d}.riferimento.txt"
        if not f.exists():
            da_verificare.append(n)
            continue
        rif, chi = leggi_riferimento(f)
        if not chi:
            da_verificare.append(n)
            continue
        for nome, info in camp["motori"].items():
            letto_f = dest / f"p{n:03d}.{file_motore(nome)}.txt"
            if not info.get("disponibile") or not letto_f.exists():
                continue
            letto = letto_f.read_text(encoding="utf-8")
            e, c = cer(letto, rif, lingua)
            enp, cnp = cer(letto, rif, lingua, punteggiatura=False)
            m = out.setdefault(nome, {"pagine": 0, "errori": 0, "caratteri": 0, "errori_np": 0, "caratteri_np": 0,
                                      "per_pagina": {}, **{k: info.get(k) for k in ("descrizione",
                                                           "secondi_per_pagina", "confidenza")}})
            m["pagine"] += 1
            m["errori"] += e
            m["caratteri"] += c
            m["errori_np"] += enp
            m["caratteri_np"] += cnp
            m["per_pagina"][n] = round(100 * e / c, 1) if c else None
    return camp, out, da_verificare


def cmd_misura(args):
    cfg = leggi_config()
    radice = cartella_prove(cfg)
    righe = [f"# Prova dei motori OCR — {dt.date.today().isoformat()}", ""]
    for nome in args.nomi:
        dest = radice / nome
        if not (dest / "campione.json").exists():
            raise SystemExit(f"Campione «{nome}» non trovato in {radice}: prima python prova_ocr.py prepara")
        camp, out, da_verificare = misura_campione(dest)
        righe += [f"## {nome}", "", f"Fonte: `{Path(camp['sorgente']).name}`; lingua {camp['lingua']}; "
                  f"{camp['dpi']} dpi; pagine verificate {len(camp['pagine']) - len(da_verificare)} di "
                  f"{len(camp['pagine'])}" + (f" (da verificare: {', '.join(map(str, da_verificare))})"
                                              if da_verificare else "") + ".", ""]
        if not out:
            righe += ["Nessuna pagina verificata: nessuna misura.", ""]
        else:
            righe += ["| Motore | Pagine | CER | CER senza punteggiatura | Secondi per pagina | Confidenza (indicativa) |",
                      "|---|---|---|---|---|---|"]
            for m, d in sorted(out.items(), key=lambda x: x[1]["errori"] / max(1, x[1]["caratteri"])):
                righe.append(f"| {d.get('descrizione') or m} | {d['pagine']} | "
                             f"{100 * d['errori'] / max(1, d['caratteri']):.1f}% | "
                             f"{100 * d['errori_np'] / max(1, d['caratteri_np']):.1f}% | "
                             f"{d.get('secondi_per_pagina')} | {d.get('confidenza')} |")
            righe += ["", "CER per pagina: " + "; ".join(
                f"{m} " + ", ".join(f"p. {n} {v}%" for n, v in d["per_pagina"].items()) for m, d in out.items()), ""]
        non = [f"{m} ({i.get('motivo')})" for m, i in camp["motori"].items() if not i.get("disponibile")]
        if non:
            righe += ["Non provati: " + "; ".join(non) + ".", ""]
    testo = "\n".join(righe)
    f = radice / f"misure_{dt.date.today().isoformat()}.md"
    f.write_text(testo, encoding="utf-8")
    print(testo + f"\nMisure in {f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="comando", required=True)
    m = sub.add_parser("motori")
    m.add_argument("--lingua", default="zh")
    p = sub.add_parser("prepara")
    p.add_argument("sorgente")
    p.add_argument("--nome", required=True)
    p.add_argument("--lingua", required=True)
    p.add_argument("--pagine", default="")
    p.add_argument("--dpi", type=int, default=300)
    p.add_argument("--motori", default="tesseract,tesseract:3,tesseract:6,paddleocr,kraken")
    p.add_argument("--riferimento", default="", help="motore la cui lettura fa da proposta di riferimento")
    s = sub.add_parser("misura")
    s.add_argument("nomi", nargs="+")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    {"motori": cmd_motori, "prepara": cmd_prepara, "misura": cmd_misura}[args.comando](args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
FASE 1 - Estrazione esaustiva delle occorrenze (nessuna AI, nessun limite di risultati).

Legge l'intestazione di metadati dei file ([SERIES: ...], [FULL_CITATION: ...], [DATE: ...]),
la esclude dalla ricerca e scarta le date marcate come inattendibili.

Uso:
  python estrai_occorrenze.py <cartella_corpus> <entita.ini> [--out risultati] [--finestra 400]

Produce in <out>/:
  passaggi.jsonl  - un passaggio per riga (input della fase 2)
  passaggi.csv    - la stessa cosa, da aprire in Excel
  riepilogo.txt   - conteggi per entita, variante e anno
"""
import argparse
import configparser
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

# Intestazione di metadati in testa ai file: righe come [DATE: 1966-07-15]
HDR = re.compile(r"^\[([A-Za-z_]+):\s*(.*?)\]\s*$")
# Date estratte dal testo stesso (non dal frontespizio): nel corpus di Peking Review sono inattendibili
FONTI_DATA_INATTENDIBILI = {"filename+local_header"}
# Varianti in caratteri latini piu corte di cosi mantengono il confine di parola (Mao, Lin...)
MIN_SENZA_CONFINE = 5

# Equivalenze tipografiche frequenti nei testi OCR cinesi
EQUIVALENZE = {
    "（": "[（(]", "(": "[（(]",
    "）": "[）)]", ")": "[）)]",
    "·": "[·・•.‧\\-]?", "・": "[·・•.‧\\-]?",
    "，": "[，,]", ",": "[，,]",
}

INIZIO_EVID, FINE_EVID = "⟦", "⟧"
TRATTINI = r"[\-\u00ad\u2010\u2011¬]"          # trattino, trattino morbido (U+00AD), lineette, ¬
SEP_PAROLE = r"[\s\-\u00ad\u2010\u2011¬]"


def leggi_intestazione(testo):
    """Restituisce (metadati, posizione in cui inizia il testo vero e proprio)."""
    meta, pos = {}, 0
    for riga in testo.splitlines(keepends=True):
        m = HDR.match(riga.strip())
        if m:
            meta[m.group(1).upper()] = m.group(2).strip()
        elif riga.strip() == "" and meta:
            pass
        else:
            break
        pos += len(riga)
    return meta, pos


def metadati(path, corpus, meta):
    rel_path = path.relative_to(corpus)
    rel = rel_path.as_posix()
    fonte = meta.get("SERIES") or (rel_path.parts[-2] if len(rel_path.parts) > 1 else path.stem)
    citazione = meta.get("FULL_CITATION", "")

    data, data_affidabile = meta.get("DATE", ""), True
    if meta.get("METADATA_SOURCE") in FONTI_DATA_INATTENDIBILI or meta.get("DATE_STATUS") == "da verificare":
        data, data_affidabile = "", False
    if not data and re.fullmatch(r"\d{4}-\d{2}-\d{2}", path.stem):   # es. Renmin Ribao 1966-07-15.txt
        data = path.stem
    if not data:
        m = re.search(r"(19|20)\d\d", meta.get("YEAR", "") or rel)
        data = m.group(0) if m else ""
    return rel, fonte, citazione, data, data_affidabile


def dividi(valore):
    return [v.strip() for v in re.split(r"[;；]", valore or "") if v.strip()]


def carica_entita(path):
    cp = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    cp.optionxform = str
    cp.read(path, encoding="utf-8")
    entita = {}
    for sezione in cp.sections():
        varianti = dividi(cp.get(sezione, "varianti", fallback=""))
        if not varianti:
            continue
        entita[sezione] = {
            "varianti": varianti,
            "contesto": dividi(cp.get(sezione, "contesto", fallback="")),
            "note": cp.get(sezione, "note", fallback="").strip(),
        }
    return entita


def is_cjk(testo):
    return any("\u3400" <= ch <= "\u9fff" for ch in testo)


def pattern_variante(variante):
    if is_cjk(variante):
        pezzi = []
        for ch in variante:
            if ch.isspace():
                continue
            pezzi.append(EQUIVALENZE.get(ch, re.escape(ch)))
        # tollera spazi e a capo inseriti dall'OCR tra un carattere e l'altro
        return r"\s*".join(pezzi)
    parti = [p for p in re.split(r"[\s\-]+", variante) if p]
    # tollera la sillabazione a fine riga dentro la parola (Federa-\ntion), anche con il trattino morbido
    # (U+00AD), le lineette U+2010/U+2011 e il segno ¬ di alcuni OCR
    corpo = (SEP_PAROLE + "*").join((r"(?:" + TRATTINI + r"\s*)?").join(re.escape(c) for c in p) for p in parti)
    if len("".join(parti)) < MIN_SENZA_CONFINE:
        return r"(?<![A-Za-zÀ-ÿ])" + corpo + r"(?![A-Za-zÀ-ÿ])"
    # niente confine di parola: l'OCR incolla spesso le parole ("byJacques", "Partyand")
    return corpo


def compila(entita):
    for info in entita.values():
        uniche = sorted(set(info["varianti"]), key=len, reverse=True)  # prima le forme piu lunghe
        info["rx"] = re.compile("|".join(pattern_variante(v) for v in uniche), re.IGNORECASE)


def allarga(testo, a, b, extra=150):
    """Sposta i bordi della finestra fino al confine di frase/riga piu vicino (entro 'extra' caratteri)."""
    confini = "\n。！？.!?"
    nuovo_a = a
    for i in range(a, max(0, a - extra), -1):
        if testo[i - 1] in confini:
            nuovo_a = i
            break
    nuovo_b = b
    for i in range(b, min(len(testo), b + extra)):
        if testo[i] in confini:
            nuovo_b = i + 1
            break
    return nuovo_a, nuovo_b


def compatta(s):
    return re.sub(r"\s+", " ", s).strip()


def normalizza(s):
    return re.sub(r"\s+", "", s).lower()


def forma_trovata(t):
    """Forma della variante trovata, senza gli spazi/a capo spuri dell'OCR nei testi cinesi."""
    return re.sub(r"\s+", "", t) if is_cjk(t) else compatta(t)


def id_passaggio(rel, nome, inizio):
    """Identificativo del passaggio: file, entità e posizione della prima occorrenza del gruppo."""
    return hashlib.sha1(f"{rel}|{nome}|{inizio}".encode("utf-8")).hexdigest()[:10]


def passaggi_del_testo(testo, inizio_testo, rel, nome, info, finestra):
    """Passaggi di un'entità in un testo: [(record senza i metadati del file, gruppo di occorrenze)].
    Le occorrenze vicine (entro due finestre) formano un solo passaggio."""
    hits = [(m.start(), m.end(), m.group(0)) for m in info["rx"].finditer(testo, inizio_testo)]
    gruppi = []
    for s, e, t in hits:
        if gruppi and s - finestra <= gruppi[-1]["fine"] + finestra:
            gruppi[-1]["fine"] = e
            gruppi[-1]["hits"].append((s, e, t))
        else:
            gruppi.append({"inizio": s, "fine": e, "hits": [(s, e, t)]})
    out = []
    for g in gruppi:
        a = max(inizio_testo, g["inizio"] - finestra)
        b = min(len(testo), g["fine"] + finestra)
        a, b = allarga(testo, a, b)
        a = max(a, inizio_testo)
        grezzo = testo[a:b]

        evidenziato, cursore = [], a
        for s, e, _ in g["hits"]:
            evidenziato.append(testo[cursore:s])
            evidenziato.append(INIZIO_EVID + testo[s:e] + FINE_EVID)
            cursore = e
        evidenziato.append(testo[cursore:b])

        norm_pass = normalizza(grezzo)
        out.append(({
            "id": id_passaggio(rel, nome, g["inizio"]),
            "entita": nome,
            "file": rel,
            "riga": testo.count("\n", 0, g["inizio"]) + 1,
            "offset": g["inizio"],
            "n_occorrenze": len(g["hits"]),
            "varianti_trovate": sorted({forma_trovata(t) for _, _, t in g["hits"]}),
            "contesto_presente": any(normalizza(c) in norm_pass for c in info["contesto"]),
            "passaggio": compatta(grezzo),
            "passaggio_evidenziato": compatta("".join(evidenziato)),
        }, g))
    return out


def main():
    ap = argparse.ArgumentParser(description="Estrazione esaustiva delle occorrenze")
    ap.add_argument("corpus")
    ap.add_argument("entita")
    ap.add_argument("--out", default="risultati")
    ap.add_argument("--finestra", type=int, default=400, help="caratteri di contesto per lato")
    ap.add_argument("--indice", default=None, help="indice delle fonti (indice.py): legge solo i file candidati")
    ap.add_argument("--dal", type=int, default=None, help="salta i file datati prima di quest'anno")
    ap.add_argument("--al", type=int, default=None, help="salta i file datati dopo quest'anno")
    args = ap.parse_args()

    corpus = Path(args.corpus)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    entita = carica_entita(Path(args.entita))
    if not entita:
        raise SystemExit("Nessuna entita valida nel file di configurazione.")
    compila(entita)

    file_txt = sorted(corpus.rglob("*.txt"))
    n_totale = len(file_txt)
    # con l'indice si leggono solo i file che possono contenere le varianti (stesso risultato, molto prima)
    candidati, ind = None, None
    if args.indice and Path(args.indice).exists():
        from indice import Indice
        ind = Indice(args.indice, corpus)
        if ind.pronto() and not ind.aggiornato():
            try:                          # file aggiunti o corretti dopo la costruzione: si indicizzano solo quelli
                ind.aggiorna(tempo_max=600)
            except Exception as e:
                print(f"Aggiornamento dell'indice non riuscito ({type(e).__name__}: {e})")
        if ind.pronto() and ind.aggiornato():
            candidati = {n: ind.file_candidati(info["varianti"]) for n, info in entita.items()}
            tutti = set().union(*candidati.values()) if candidati else set()
            file_txt = [f for f in file_txt if f.relative_to(corpus).as_posix() in tutti]
            print(f"Indice: {len(file_txt)} file da leggere")
        else:
            print("Indice non aggiornato (le fonti sono cambiate): leggo tutti i file. "
                  "Per aggiornarlo: python indice.py aggiorna")
            ind = None
    if ind and (args.dal or args.al):
        def fuori(f):
            a = ind.anno_di(f.relative_to(corpus).as_posix())
            return bool(a) and ((args.dal and a < args.dal) or (args.al and a > args.al))
        file_txt = [f for f in file_txt if not fuori(f)]
    per_entita = Counter()
    per_variante = defaultdict(Counter)
    per_anno = defaultdict(Counter)
    record = []

    for path in file_txt:
        testo = path.read_text(encoding="utf-8", errors="replace")
        meta, inizio_testo = leggi_intestazione(testo)
        rel, fonte, citazione, data, data_affidabile = metadati(path, corpus, meta)
        for nome, info in entita.items():
            if candidati is not None and rel not in candidati[nome]:
                continue
            for r, g in passaggi_del_testo(testo, inizio_testo, rel, nome, info, args.finestra):
                record.append({"id": r["id"], "entita": nome, "fonte": fonte, "citazione": citazione, "data": data,
                               "data_affidabile": data_affidabile, **r})
                per_entita[nome] += len(g["hits"])
                for _, _, t in g["hits"]:
                    per_variante[nome][forma_trovata(t)] += 1
                per_anno[nome][data[:4] or "s.d."] += len(g["hits"])

    record.sort(key=lambda r: (r["entita"], r["data"], r["file"], r["offset"]))

    with (out / "passaggi.jsonl").open("w", encoding="utf-8") as f:
        for r in record:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with (out / "passaggi.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "entita", "citazione", "data", "data_affidabile", "file", "riga", "n_occorrenze",
                    "varianti_trovate", "contesto_presente", "passaggio"])
        for r in record:
            w.writerow([r["id"], r["entita"], r["citazione"] or r["fonte"], r["data"],
                        "sì" if r["data_affidabile"] else "NO", r["file"], r["riga"],
                        r["n_occorrenze"], "; ".join(r["varianti_trovate"]),
                        "sì" if r["contesto_presente"] else "no", r["passaggio"]])

    nota = []
    if candidati is not None:
        nota.append(f"letti per intero i {len(file_txt)} che possono contenere le varianti, scelti con l'indice")
    if ind and (args.dal or args.al):
        nota.append("esclusi i file datati fuori dal periodo richiesto")
    righe = [f"File analizzati: {n_totale}" + (f" ({'; '.join(nota)})" if nota else ""),
             f"Passaggi estratti: {len(record)}", ""]
    for nome in entita:
        righe.append(f"== {nome}: {per_entita[nome]} occorrenze")
        for v, n in per_variante[nome].most_common():
            righe.append(f"   variante  {v}: {n}")
        for anno, n in sorted(per_anno[nome].items()):
            righe.append(f"   anno      {anno}: {n}")
        righe.append("")
    (out / "riepilogo.txt").write_text("\n".join(righe), encoding="utf-8")
    print("\n".join(righe))
    print(f"Risultati in: {out.resolve()}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
FASE 1 - Estrazione esaustiva delle occorrenze (nessuna AI, nessun limite di risultati).

Legge l'intestazione di metadati dei file ([SERIES: ...], [FULL_CITATION: ...], [DATE: ...]),
la esclude dalla ricerca e scarta le date marcate come inattendibili.

Uso:
  python estrai_occorrenze.py <cartella_corpus> <entities.ini> [--out risultati] [--finestra 400]

Produce in <out>/:
  passaggi.jsonl  - un passaggio per riga (input della fase 2)
  passaggi.csv    - la stessa cosa, da aprire in Excel
  riepilogo.txt   - conteggi per entita, variante e anno
"""
import argparse
import bisect
import configparser
import csv
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

# Intestazione di metadati in testa ai file: righe come [DATE: 1966-07-15]
HDR = re.compile(r"^\[([A-Za-z_]+):\s*(.*?)\]\s*$")
# Date estratte dal testo stesso (non dal frontespizio): nel corpus di Peking Review sono inattendibili
FONTI_DATA_INATTENDIBILI = {"filename+local_header"}

# ---------------------------------------------------------------- stati dei campi dell'intestazione (lavoro 8, fase 2)
# Regole decise:
#   1. ASSENZA di <CAMPO>_STATUS = campo verificato (default implicito). Il valore esplicito «verificato» è
#      ammesso ed equivale all'assenza; così i campi derivati automaticamente possono essere marcati «dedotto»
#      o «da verificare» senza obbligo di scrivere lo stato per i campi controllati a mano.
#   2. Vocabolario chiuso: gli unici valori ammessi sono quelli di STATI_CAMPO.
#   3. Provenienza separata dallo stato: dalle nuove importazioni (punto 4) <CAMPO>_STATUS contiene solo lo stato e
#      <CAMPO>_NOTE la provenienza; i valori storici del corpus («dal nome del file», ...) sono tollerati in
#      lettura, con stato ricavato da PROVENIENZE_TOLLERATE e un avviso di importa.py controlla fino alla
#      migrazione del corpus (punto 5).
STATI_CAMPO = ("dedotto", "da verificare", "verificato")
PROVENIENZE_TOLLERATE = {   # valori storici del corpus -> stato equivalente (tollerati in lettura)
    "dal nome del file": "dedotto",
    "dal file dei metadati": "dedotto",
    "indicata all'importazione": "dedotto",
    "letta nella prima pagina (OCR): da controllare": "da verificare",
}
# stati scritti con altre parole nelle revisioni dei metadati del corpus (22/10/2026), anch'essi tollerati in
# lettura: 909 fascicoli di Peking Review hanno «verificata sul testo», uno «verificata manualmente», cinque
# «probabile (poche occorrenze nel testo)»
STATI_STORICI = {
    "verificata sul testo": "verificato",
    "verificata manualmente": "verificato",
    "verificato sul testo": "verificato",
    "verificato manualmente": "verificato",
}
PREFISSI_STORICI = {"probabile": "dedotto"}     # «probabile (motivo)» -> dedotto


def stato_storico(v):
    """Stato del vocabolario per un valore storico tollerato ('' se il valore non è tra quelli tollerati)."""
    v = (v or "").strip().lower()
    for p, s in PROVENIENZE_TOLLERATE.items():
        if p.lower() == v:
            return s
    if v in STATI_STORICI:
        return STATI_STORICI[v]
    return next((s for p, s in PREFISSI_STORICI.items() if v == p or v.startswith(p + " ")), "")


def stato_del_valore(valore):
    """(stato normalizzato, noto) per il valore di un <CAMPO>_STATUS: noto se appartiene al vocabolario chiuso.
    I valori storici tollerati danno lo stato equivalente con noto=False (importa.py controlla li segnala e
    --migra-stati li riscrive); un valore sconosciuto resta com'è e conta come non verificato."""
    v = (valore or "").strip().lower()
    if not v:
        return "", True
    if v in STATI_CAMPO:
        return v, True
    storico = stato_storico(v)
    if storico:
        return storico, False
    return v, False


def stato_attivo(meta, prefisso):
    """Stato effettivo di un campo: '' (verificato) senza <prefisso>_STATUS, 'da verificare'/'dedotto' se dichiarato.
    Un campo esplicitamente marcato «verificato» equivale a senza _STATUS (regola 1)."""
    s, _ = stato_del_valore(meta.get(prefisso + "_STATUS", ""))
    return "" if s in ("", "verificato") else s


def nota_del_campo(meta, prefisso):
    """Provenienza dichiarata per un campo: <prefisso>_NOTE, o (nei file storici) il valore stesso di
    <prefisso>_STATUS quando è un valore storico tollerato; '' se non c'è."""
    nota = meta.get(prefisso + "_NOTE", "")
    if nota:
        return nota
    status = (meta.get(prefisso + "_STATUS") or "").strip()
    return status if stato_storico(status) else ""
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

# Vocali e consonanti con accento: in un testo OCR l'accento può cadere o cambiare
ACCENTI = {"a": "aàáâäãå", "e": "eèéêë", "i": "iìíîï", "o": "oòóôöõø", "u": "uùúûü",
           "c": "cç", "n": "nñ", "y": "yÿ"}


def senza_accenti(s):
    """Testo senza i segni diacritici: «Désiré» -> «Desire»."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def _car_ignorando_accenti(ch):
    k = ch.lower()
    if ch in "'’‘`":
        return "['’‘`]"
    return f"[{ACCENTI[k]}]" if k in ACCENTI else re.escape(ch)


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

    data, data_affidabile = meta.get("DATE", ""), stato_attivo(meta, "DATE") == ""
    if meta.get("METADATA_SOURCE") in FONTI_DATA_INATTENDIBILI:
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
    # come pattern_latino di indice.py: senza badare agli accenti («Désiré» trova anche «Desire»),
    # così l'estrazione e l'indice non divergono (un nome con l'accento caduto nell'OCR non sfugge)
    base = senza_accenti(variante)
    parti = [p for p in re.split(r"[\s\-]+", base) if p]
    # tollera la sillabazione a fine riga dentro la parola (Federa-\ntion), anche con il trattino morbido
    # (U+00AD), le lineette U+2010/U+2011 e il segno ¬ di alcuni OCR
    corpo = (SEP_PAROLE + "*").join((r"(?:" + TRATTINI + r"\s*)?").join(_car_ignorando_accenti(c) for c in p) for p in parti)
    if len("".join(parti)) < MIN_SENZA_CONFINE:
        return r"(?<![A-Za-zÀ-ÿ])" + corpo + r"(?![A-Za-zÀ-ÿ])"
    # niente confine di parola: l'OCR incolla spesso le parole ("byJacques", "Partyand")
    return corpo


def pattern_latino(forma):
    """Come pattern_variante, ma senza badare agli accenti: mantenuto per compatibilità con indice.py,
    che ora importa direttamente pattern_variante."""
    return pattern_variante(forma)


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
    """Identificativo del passaggio: file, entità e posizione della prima occorrenza del gruppo.

    Non dipende dalla 'finestra': cambiando quel parametro in config.ini i passaggi già letti
    nell'archivio restano riconosciuti e non vengono rimandati al modello (le coordinate nel
    testo - offset della prima occorrenza - non cambiano)."""
    return hashlib.sha1(f"{rel}|{nome}|{inizio}".encode("utf-8")).hexdigest()[:10]


def passaggi_del_testo(testo, inizio_testo, rel, nome, info, finestra):
    """Passaggi di un'entità in un testo: [(record senza i metadati del file, gruppo di occorrenze)].
    Le occorrenze vicine (entro due finestre) formano un solo passaggio.

    L'identificativo del gruppo è la posizione della prima occorrenza, che non dipende dalla
    finestra; il raggruppamento sì, quindi se cambia la finestra possono nascere gruppi nuovi
    (con lo stesso id del gruppo da cui derivano: vale l'ultima lettura registrata)."""
    hits = [(m.start(), m.end(), m.group(0)) for m in info["rx"].finditer(testo, inizio_testo)]
    gruppi = []
    for s, e, t in hits:
        if gruppi and s - finestra <= gruppi[-1]["fine"] + finestra:
            gruppi[-1]["fine"] = e
            gruppi[-1]["hits"].append((s, e, t))
        else:
            gruppi.append({"inizio": s, "fine": e, "hits": [(s, e, t)]})
    out = []
    righe_inizio = [0] + [k + 1 for k, ch in enumerate(testo) if ch == "\n"]   # una volta sola, non per gruppo
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
            "riga": bisect.bisect_right(righe_inizio, g["inizio"]),
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
    def fuori_periodo(a):
        return bool(a) and ((args.dal and a < args.dal) or (args.al and a > args.al))

    if ind and (args.dal or args.al):
        # si saltano solo i periodici: nelle raccolte l'anno del file è quello di edizione, e il periodo si
        # controlla passaggio per passaggio sulla data interna dei documenti (lavoro 9)
        from citazioni import profilo_di

        def fuori(f):
            rel = f.relative_to(corpus).as_posix()
            return profilo_di({}, rel).get("tipo") == "periodico" and fuori_periodo(ind.anno_di(rel))
        file_txt = [f for f in file_txt if not fuori(f)]
    from date_interne import per_file as date_interne_del_file
    per_entita = Counter()
    per_variante = defaultdict(Counter)
    per_anno = defaultdict(Counter)
    record = []

    for path in file_txt:
        testo = path.read_text(encoding="utf-8", errors="replace")
        meta, inizio_testo = leggi_intestazione(testo)
        rel, fonte, citazione, data, data_affidabile = metadati(path, corpus, meta)
        date_doc = None                     # date interne dei documenti (raccolte), calcolate solo se servono
        for nome, info in entita.items():
            if candidati is not None and rel not in candidati[nome]:
                continue
            for r, g in passaggi_del_testo(testo, inizio_testo, rel, nome, info, args.finestra):
                if date_doc is None:
                    date_doc = date_interne_del_file(testo, meta, inizio_testo, rel, data) or False
                interna = date_doc.per_offset(r["offset"]) if date_doc else None
                anno = (interna or {}).get("data", data)[:4]
                if date_doc and interna and fuori_periodo(int(anno)):
                    continue
                if not date_doc and fuori_periodo(int(anno) if anno.isdigit() else None):
                    continue
                rec = {"id": r["id"], "entita": nome, "fonte": fonte, "citazione": citazione, "data": data,
                       "data_affidabile": data_affidabile}
                if date_doc:
                    rec["data_interna"] = interna       # None: raccolta, ma data del documento non deducibile
                record.append({**rec, **r})
                per_entita[nome] += len(g["hits"])
                for _, _, t in g["hits"]:
                    per_variante[nome][forma_trovata(t)] += 1
                per_anno[nome][anno or "s.d."] += len(g["hits"])

    record.sort(key=lambda r: (r["entita"], r["data"], r["file"], r["offset"]))

    with (out / "passaggi.jsonl").open("w", encoding="utf-8") as f:
        for r in record:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with (out / "passaggi.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "entita", "citazione", "data", "data_affidabile", "data_interna", "file", "riga",
                    "n_occorrenze", "varianti_trovate", "contesto_presente", "passaggio"])
        for r in record:
            w.writerow([r["id"], r["entita"], r["citazione"] or r["fonte"], r["data"],
                        "sì" if r["data_affidabile"] else "NO",
                        (r.get("data_interna") or {}).get("data", "") and r["data_interna"]["data"] + " (dedotta)",
                        r["file"], r["riga"],
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

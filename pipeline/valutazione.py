#!/usr/bin/env python3
"""
Strumento di valutazione: insieme di riferimento verificato a mano e misure di precisione e richiamo,
su qualsiasi corpus.

Due misure distinte:
  - estrazione: quante occorrenze vere delle forme del nome trova estrai_occorrenze.py (richiamo);
  - classificazione: quanto sono giuste le decisioni sulla pertinenza, per ogni modello e per ogni livello di
    provenienza delle letture già in archivio (modello, sessione assistita, regola).

Procedura (ogni insieme sta in risultati/_valutazione/<nome>/):
  1. python valutazione.py campione <nome> [--n 100] [--entita "A; B"] [--fonti "Peking Review; ..."]
       Campione stratificato (per serie, lingua, decisione attuale e provenienza) dei passaggi già estratti.
       Scrive campione.csv da compilare: colonna GIUDIZIO = sì / no / incerto (l'entità è davvero quella
       della scheda?), NOTE facoltative, VERIFICATO_DA (iniziali). La decisione attuale NON compare nel file
       (verifica alla cieca): resta in campione_nascosto.jsonl.
  2. python valutazione.py candidati <nome> --entita "A" [--file 60]
       Ricerca larga (cognome da solo, una lettera o un carattere diversi, senza accenti) in un campione di
       file: scrive candidati.csv con le forme che l'estrazione NON trova. GIUDIZIO = sì se è davvero una
       menzione dell'entità sfuggita all'estrazione, no altrimenti.
  3. Compilare i due file (separatore punto e virgola: Excel li apre con un doppio clic). Si possono salvare
     come CSV oppure come cartella di lavoro Excel (campione.xlsx, candidati.xlsx): vale il più recente.
  4. python valutazione.py importa <nome>
       Controlla i CSV compilati e scrive insieme.jsonl (passaggi con il giudizio) ed estrazione.json.
  5. python valutazione.py misura <nome> [--modelli "nome1; nome2"] [--config config.ini]
       Misure sulle letture in archivio (per livello di provenienza), sui modelli indicati (smistamento,
       senza archivio, in una cartella di prova) e sull'estrazione. Scrive misure_<data>.md.

Metriche: richiamo = pertinenti veri trovati come «sì» o «incerto» / pertinenti veri; precisione = «sì»
davvero pertinenti / «sì». Intervalli di confidenza al 95% (Wilson). Un «incerto» del riferimento non entra
nelle misure. Nessun modello è usato nei passi 1-4.
"""
import argparse
import csv
import datetime as dt
import json
import math
import random
import re
import subprocess
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARTELLA))
try:
    sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
except AttributeError:
    pass

GIUDIZI = {"sì": "sì", "si": "sì", "s": "sì", "yes": "sì", "y": "sì",
           "no": "no", "n": "no", "incerto": "incerto", "?": "incerto", "i": "incerto"}


# ---------------------------------------------------------------- utilità
def cartella(cfg, nome):
    from llm import percorso
    d = percorso(cfg, "risultati") / "_valutazione" / re.sub(r"[^\w\-]+", "_", nome).strip("_")
    d.mkdir(parents=True, exist_ok=True)
    return d


def scrivi_csv(path, campi, righe):
    # punto e virgola: è il separatore che Excel in italiano (e nelle lingue con la virgola decimale) si aspetta
    # quando si apre il file con un doppio clic
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, campi, extrasaction="ignore", delimiter=";")
        w.writeheader()
        w.writerows(righe)


def leggi_csv(path):
    """Righe di un file compilato: CSV (separatore virgola, punto e virgola o tabulazione) oppure cartella di
    lavoro Excel (.xlsx), anche se salvata con il nome .csv."""
    import io
    with open(path, "rb") as f:
        inizio = f.read(4)
    if inizio.startswith(b"PK"):
        return righe_da_tabella(leggi_xlsx(path))
    with open(path, encoding="utf-8-sig", newline="") as f:
        testo = f.read()
    prima = testo.split("\n", 1)[0]
    sep = max(",;\t", key=prima.count)              # dalla riga dei titoli delle colonne
    return list(csv.DictReader(io.StringIO(testo, newline=""), delimiter=sep))


def righe_da_tabella(tabella):
    """Dizionari dalle righe di un foglio. Se Excel ha lasciato ogni riga del CSV intera nella prima colonna
    (file aperto con il separatore sbagliato), la ricompone e assegna le celle compilate a destra alle colonne
    da compilare ancora vuote (GIUDIZIO, NOTE, VERIFICATO_DA), nell'ordine."""
    import io
    tabella = [r for r in tabella if any((x or "").strip() for x in r)]
    if not tabella:
        return []
    titoli = [(x or "").strip() for x in tabella[0]]
    if "GIUDIZIO" in titoli:
        return [dict(zip(titoli, [(x or "") for x in r] + [""] * (len(titoli) - len(r)))) for r in tabella[1:]]
    prima = titoli[0]
    if "GIUDIZIO" not in prima:
        sys.exit("Il foglio non ha la colonna GIUDIZIO: è il file giusto?")
    sep = max(",;\t", key=prima.count)
    righe = list(csv.DictReader(io.StringIO("\n".join(r[0] or "" for r in tabella), newline=""), delimiter=sep))
    for d, r in zip(righe, tabella[1:]):
        extra = [(x or "").strip() for x in r[1:] if (x or "").strip()]
        for campo in ("GIUDIZIO", "NOTE", "VERIFICATO_DA"):
            if extra and not (d.get(campo) or "").strip():
                d[campo] = extra.pop(0)
    return righe


def leggi_xlsx(path):
    """Righe del primo foglio di un file .xlsx, come liste di testi (solo libreria standard)."""
    import xml.etree.ElementTree as ET
    import zipfile
    m = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
    rel = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    with zipfile.ZipFile(path) as z:
        condivise = []
        if "xl/sharedStrings.xml" in z.namelist():
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall(f"{m}si"):
                condivise.append("".join(t.text or "" for t in si.findall(f"{m}t") + si.findall(f"{m}r/{m}t")))
        primo = ET.fromstring(z.read("xl/workbook.xml")).find(f"{m}sheets/{m}sheet")
        rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
        dest = next(r.get("Target") for r in rels if r.get("Id") == primo.get(rel))
        foglio = ET.fromstring(z.read(dest.lstrip("/") if dest.startswith("/") else "xl/" + dest))
    tabella = []
    for riga in foglio.iter(f"{m}row"):
        valori = {}
        for i, c in enumerate(riga.findall(f"{m}c")):
            ref = re.match(r"[A-Z]+", c.get("r") or "")
            col = i
            if ref:
                col = 0
                for ch in ref.group(0):
                    col = col * 26 + ord(ch) - 64
                col -= 1
            tipo, v = c.get("t"), c.find(f"{m}v")
            if tipo == "s":
                x = condivise[int(v.text)]
            elif tipo == "inlineStr":
                x = "".join(t.text or "" for t in c.iter(f"{m}t"))
            else:
                x = v.text if v is not None and v.text else ""
                if tipo in (None, "n") and re.fullmatch(r"-?\d+\.0+", x):
                    x = x.split(".")[0]                  # 129801.0 -> 129801 (scostamenti, numeri)
            valori[col] = x
        tabella.append([valori.get(i, "") for i in range(max(valori) + 1)] if valori else [])
    return tabella


def file_compilato(d, base):
    """Il file compilato più recente tra <base>.csv e <base>.xlsx (None se non c'è nessuno dei due)."""
    presenti = [p for p in (d / f"{base}.csv", d / f"{base}.xlsx") if p.exists()]
    return max(presenti, key=lambda p: p.stat().st_mtime) if presenti else None


def wilson(k, n, z=1.96):
    """Intervallo di confidenza al 95% per una proporzione k/n."""
    if not n:
        return None
    p = k / n
    den = 1 + z * z / n
    centro = (p + z * z / (2 * n)) / den
    mezzo = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, centro - mezzo), min(1.0, centro + mezzo)


def proporzione(k, n):
    if not n:
        return "—"
    a, b = wilson(k, n)
    return f"{k}/{n} = {100 * k / n:.0f}% (IC 95%: {100 * a:.0f}-{100 * b:.0f}%)"


def lingua_di(rec, dati, cache={}):
    """Lingua del file: campo LANG dell'intestazione, lingua del profilo di serie, altrimenti dal testo."""
    f = rec["file"]
    if f not in cache:
        from citazioni import leggi_intestazione, profilo_di
        try:
            with open(Path(dati) / f, encoding="utf-8", errors="replace") as fh:
                testa = fh.read(4000)
        except OSError:
            testa = ""
        meta, _ = leggi_intestazione(testa)
        lingua = meta.get("LANG") or profilo_di(meta, f).get("lingua", "")
        if not lingua:
            lingua = "zh" if re.search(r"[㐀-鿿]", rec.get("passaggio", "")) else "?"
        cache[f] = lingua.strip().lower()[:3]
    return cache[f]


# ---------------------------------------------------------------- 1. campione per la classificazione
def passaggi_letti(cfg):
    """Passaggi già estratti e letti (cartelle dei risultati), con la lettura più recente dell'archivio."""
    from archivio import Archivio, file_risultati
    from llm import percorso
    ris = percorso(cfg, "risultati")
    arch = Archivio(ris)
    out = {}
    for f in file_risultati(ris, "classificati.jsonl"):
        with open(f, encoding="utf-8") as fh:
            for r in fh:
                if not r.strip():
                    continue
                try:
                    c = json.loads(r)
                except ValueError:
                    continue
                a = c.get("analisi") or {}
                if a.get("assorbito_da") or not c.get("passaggio"):
                    continue
                v = arch.per_id.get((c["id"], c["entita"]))
                if v:
                    a = v["analisi"]
                if a.get("pertinente") not in ("sì", "no", "incerto"):
                    continue
                out[(c["id"], c["entita"])] = dict(c, analisi=a)
    return list(out.values())


def strato(c, dati):
    from archivio import provenienza
    a = c["analisi"]
    return (c.get("fonte", "?"), lingua_di(c, dati), a["pertinente"], provenienza(a)["decisione"]["livello"])


def campione(args, cfg):
    from llm import percorso
    dati = percorso(cfg, "dati")
    tutti = passaggi_letti(cfg)
    if args.entita:
        scelte = {x.strip() for x in args.entita.split(";") if x.strip()}
        tutti = [c for c in tutti if c["entita"] in scelte]
    if args.fonti:
        scelte = {x.strip() for x in args.fonti.split(";") if x.strip()}
        tutti = [c for c in tutti if c.get("fonte") in scelte]
    if not tutti:
        sys.exit("Nessun passaggio letto con questi filtri: avvia prima qualche ricerca.")
    gruppi = defaultdict(list)
    for c in tutti:
        gruppi[strato(c, dati)].append(c)
    rnd = random.Random(args.seme)
    for g in gruppi.values():
        rnd.shuffle(g)
    # almeno un passaggio per strato (finché basta il campione), il resto in proporzione alla grandezza
    n = min(args.n, len(tutti))
    quote = {k: 0 for k in gruppi}
    for k in sorted(gruppi, key=lambda k: -len(gruppi[k]))[:n]:
        quote[k] = 1
    resto = n - sum(quote.values())
    while resto > 0:
        k = max(gruppi, key=lambda k: (len(gruppi[k]) - quote[k]) / (quote[k] + 1))
        if quote[k] >= len(gruppi[k]):
            break
        quote[k] += 1
        resto -= 1
    scelti = [c for k, q in quote.items() for c in gruppi[k][:q]]
    rnd.shuffle(scelti)

    from citazioni import per_passaggio
    from estrai_occorrenze import carica_entita
    schede = carica_entita(percorso(cfg, "entita"))
    d = cartella(cfg, args.nome)
    righe = []
    for i, c in enumerate(scelti, 1):
        scheda = schede.get(c["entita"])
        descrizione = scheda["note"] if scheda else "(nessuna scheda con questo nome in entita.ini)"
        righe.append({"N": i, "ID": c["id"], "ENTITA": c["entita"], "SCHEDA": descrizione, "SERIE": c.get("fonte", ""),
                      "LINGUA": lingua_di(c, dati), "CITAZIONE": per_passaggio(c, dati)[0],
                      "PASSAGGIO": c.get("passaggio_evidenziato") or c["passaggio"],
                      "GIUDIZIO": "", "NOTE": "", "VERIFICATO_DA": ""})
    scrivi_csv(d / "campione.csv", list(righe[0]), righe)
    with open(d / "campione_nascosto.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for c in scelti:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    info = {"creato_il": dt.datetime.now().isoformat(timespec="seconds"), "seme": args.seme, "richiesti": args.n,
            "estratti": len(scelti), "universo": len(tutti), "filtri": {"entita": args.entita, "fonti": args.fonti},
            "strati": {" | ".join(k): {"universo": len(gruppi[k]), "campione": q} for k, q in quote.items()}}
    (d / "campione_info.json").write_bytes(json.dumps(info, ensure_ascii=False, indent=1).encode("utf-8"))
    print(f"Campione di {len(scelti)} passaggi su {len(tutti)} ({len(gruppi)} strati: serie, lingua, decisione, "
          f"provenienza).\nDa compilare: {d / 'campione.csv'} (colonne GIUDIZIO, NOTE, VERIFICATO_DA).")


# ---------------------------------------------------------------- 2. candidati per il richiamo dell'estrazione
def senza_accenti(s):
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))


def forme_larghe(varianti):
    """Espressioni regolari più larghe delle varianti: cognome da solo, una lettera (o un carattere cinese)
    qualsiasi al posto di una, accenti ignorati. Servono solo a trovare candidati da controllare a mano."""
    from estrai_occorrenze import is_cjk
    forme = set()
    for v in varianti:
        if is_cjk(v):
            nucleo = re.sub(r"[·・•.\s（）()《》，,]", "", v)
            parti = [p for p in re.split(r"[·・•.]", v) if len(p) >= 2]
            if len(nucleo) >= 3:
                for i in range(len(nucleo)):
                    forme.add(r"\s*".join(re.escape(ch) if j != i else r"[㐀-鿿]"
                                          for j, ch in enumerate(nucleo)))
            for p in parti:                              # parti di un nome trascritto (cognome)
                if len(p) >= 3:
                    forme.add(r"\s*".join(map(re.escape, p)))
        else:
            parole = [senza_accenti(p) for p in re.split(r"[\s\-]+", v) if len(p) >= 4]
            for p in parole:
                forme.add(r"(?<![A-Za-z])" + re.escape(p) + r"(?![a-z])")
                if len(p) >= 6:
                    for i in range(1, len(p)):
                        forme.add(r"(?<![A-Za-z])" + re.escape(p[:i]) + "[A-Za-z]" + re.escape(p[i + 1:])
                                  + r"(?![a-z])")
    return re.compile("|".join(sorted(forme, key=len, reverse=True)), re.IGNORECASE) if forme else None


def candidati(args, cfg):
    from estrai_occorrenze import carica_entita, compila, leggi_intestazione
    from llm import percorso
    dati = percorso(cfg, "dati")
    schede = carica_entita(percorso(cfg, "entita"))
    nome = args.entita.strip()
    if nome not in schede:
        sys.exit(f"Scheda «{nome}» non trovata in entita.ini.")
    compila(schede)
    stretta = schede[nome]["rx"]
    larga = forme_larghe(schede[nome]["varianti"])
    file = sorted(dati.rglob("*.txt"))
    # campione stratificato per cartella (serie), con seme fisso
    per_cart = defaultdict(list)
    for f in file:
        per_cart[f.parent].append(f)
    rnd = random.Random(args.seme)
    scelti = []
    while len(scelti) < min(args.file, len(file)):
        for c in sorted(per_cart):
            if per_cart[c] and len(scelti) < args.file:
                scelti.append(per_cart[c].pop(rnd.randrange(len(per_cart[c]))))
    righe, trovate_stretta = [], 0
    for f in scelti:
        testo = f.read_text(encoding="utf-8", errors="replace")
        _, inizio = leggi_intestazione(testo)
        prese = [(m.start(), m.end()) for m in stretta.finditer(testo, inizio)]
        trovate_stretta += len(prese)
        vista = senza_accenti(testo) if len(senza_accenti(testo)) == len(testo) else testo
        for m in (larga.finditer(vista, inizio) if larga else []):
            if any(a <= m.start() < b or a < m.end() <= b for a, b in prese):
                continue
            contesto = re.sub(r"\s+", " ", testo[max(0, m.start() - 120):m.end() + 120])
            righe.append({"N": len(righe) + 1, "FILE": f.relative_to(dati).as_posix(), "OFFSET": m.start(),
                          "FORMA": testo[m.start():m.end()], "CONTESTO": contesto,
                          "GIUDIZIO": "", "NOTE": "", "VERIFICATO_DA": ""})
    d = cartella(cfg, args.nome)
    campi = ["N", "FILE", "OFFSET", "FORMA", "CONTESTO", "GIUDIZIO", "NOTE", "VERIFICATO_DA"]
    scrivi_csv(d / "candidati.csv", campi, righe)
    info = {"creato_il": dt.datetime.now().isoformat(timespec="seconds"), "entita": nome, "seme": args.seme,
            "file_letti": [f.relative_to(dati).as_posix() for f in scelti], "occorrenze_estrazione": trovate_stretta,
            "candidati": len(righe)}
    (d / "candidati_info.json").write_bytes(json.dumps(info, ensure_ascii=False, indent=1).encode("utf-8"))
    print(f"{len(scelti)} file letti: l'estrazione trova {trovate_stretta} occorrenze; la ricerca larga propone "
          f"{len(righe)} candidati in più.\nDa compilare: {d / 'candidati.csv'}")


# ---------------------------------------------------------------- 4. importa
def giudizi(path, chiave):
    out, errori = {}, []
    for r in leggi_csv(path):
        g = GIUDIZI.get((r.get("GIUDIZIO") or "").strip().lower())
        if not g:
            errori.append(f"riga {r.get('N')}: GIUDIZIO «{r.get('GIUDIZIO', '')}» (servono sì, no o incerto)")
            continue
        k = r.get(chiave, "") if isinstance(chiave, str) else tuple(r.get(x, "") for x in chiave)
        if k in out:
            errori.append(f"riga {r.get('N')}: {chiave} «{k}» ripetuto")
            continue
        out[k] = {"giudizio": g, "note": (r.get("NOTE") or "").strip(),
                  "verificato_da": (r.get("VERIFICATO_DA") or "").strip(),
                  "entita_nel_file": (r.get("ENTITA") or "").strip(), "n": r.get("N")}
    return out, errori


def importa(args, cfg):
    d = cartella(cfg, args.nome)
    fatto = False
    f_campione, f_candidati = file_compilato(d, "campione"), file_compilato(d, "candidati")
    if f_campione:
        # i passaggi si ritrovano per ID (unico nel campione): la colonna ENTITA si può correggere a mano
        g, errori = giudizi(f_campione, "ID")
        nascosti = [json.loads(r) for r in (d / "campione_nascosto.jsonl").read_text(encoding="utf-8").splitlines() if r.strip()]
        ids = {c["id"] for c in nascosti}
        errori += [f"passaggio {c['id']} ({c['entita']}) assente dal file compilato" for c in nascosti if c["id"] not in g]
        errori += [f"riga {x['n']}: ID «{i}» non appartiene al campione" for i, x in g.items() if i not in ids]
        if errori:
            print(f"{f_campione.name} non è completo (insieme.jsonl non scritto):\n  " + "\n  ".join(errori[:30])
                  + (f"\n  ... e altre {len(errori) - 30} righe" if len(errori) > 30 else ""))
        else:
            oggi = dt.date.today().isoformat()
            righe, cambiate = [], []
            for c in nascosti:
                x = dict(g[c["id"]], importato_il=oggi)
                nel_file = x.pop("entita_nel_file")
                x.pop("n")
                if nel_file and nel_file != c["entita"]:
                    # entità corretta da chi verifica: il giudizio vale per l'entità indicata nel file
                    x["entita_verificata"] = nel_file
                    cambiate.append(f"{c['id']}: {c['entita']} -> {nel_file} (giudizio {x['giudizio']})")
                c = {k: v for k, v in c.items() if k != "analisi"}
                righe.append(json.dumps(dict(c, riferimento=x), ensure_ascii=False) + "\n")
            tmp = d / "insieme.jsonl.tmp"                  # scritto per intero, poi sostituisce il precedente
            with open(tmp, "w", encoding="utf-8", newline="\n") as f:
                f.writelines(righe)
            tmp.replace(d / "insieme.jsonl")
            if cambiate:
                print("Entità corrette a mano (contate nelle misure solo se i due nomi sono dichiarati equivalenti "
                      "con «archivio.py equivalenza», altrimenti escluse):\n  " + "\n  ".join(cambiate))
            print(f"insieme.jsonl: {len(nascosti)} passaggi verificati ({dict(Counter(x['giudizio'] for x in g.values()))}).")
            fatto = True
    if f_candidati:
        g, errori = giudizi(f_candidati, ("FILE", "OFFSET"))
        if errori:
            print(f"{f_candidati.name} non è completo:\n  " + "\n  ".join(errori[:30]))
        else:
            info = json.loads((d / "candidati_info.json").read_text(encoding="utf-8"))
            info["mancate_confermate"] = sum(1 for x in g.values() if x["giudizio"] == "sì")
            info["giudizi"] = dict(Counter(x["giudizio"] for x in g.values()))
            (d / "estrazione.json").write_bytes(json.dumps(info, ensure_ascii=False, indent=1).encode("utf-8"))
            print(f"estrazione.json: {info['mancate_confermate']} occorrenze sfuggite all'estrazione su "
                  f"{info['candidati']} candidati.")
            fatto = True
    if not fatto:
        sys.exit("Niente da importare: compila prima campione.csv o candidati.csv.")


# ---------------------------------------------------------------- 5. misura
def misure(coppie):
    """coppie: (vero, previsto) con vero in sì/no (gli incerti del riferimento sono già esclusi)."""
    pv = [p for v, p in coppie if v == "sì"]
    si = [v for v, p in coppie if p == "sì"]
    return {"n": len(coppie), "pertinenti": len(pv),
            "richiamo": (sum(1 for p in pv if p in ("sì", "incerto")), len(pv)),
            "richiamo_stretto": (sum(1 for p in pv if p == "sì"), len(pv)),
            "precisione": (sum(1 for v in si if v == "sì"), len(si)),
            "matrice": dict(Counter(f"{v}->{p}" for v, p in coppie))}


def riga_misure(etichetta, m):
    return (f"| {etichetta} | {m['n']} | {proporzione(*m['richiamo'])} | {proporzione(*m['richiamo_stretto'])} | "
            f"{proporzione(*m['precisione'])} |")


def misura(args, cfg):
    from archivio import LIVELLI, Archivio, provenienza
    from llm import percorso
    d = cartella(cfg, args.nome)
    out = [f"# Misure: {args.nome}", "", f"*{dt.datetime.now():%Y-%m-%d %H:%M}*", ""]
    if (d / "insieme.jsonl").exists():
        insieme = [json.loads(r) for r in (d / "insieme.jsonl").read_text(encoding="utf-8").splitlines() if r.strip()]
        attesi = sum(1 for r in (d / "campione_nascosto.jsonl").read_text(encoding="utf-8").splitlines() if r.strip()) \
            if (d / "campione_nascosto.jsonl").exists() else len(insieme)
        if len(insieme) != attesi:
            sys.exit(f"insieme.jsonl ha {len(insieme)} passaggi, il campione {attesi}: rifai «importa».")
        # con l'entità corretta a mano il giudizio riguarda un'altra scheda e non misura la lettura di quella
        # originale, salvo che i due nomi siano dichiarati equivalenti (archivio.py equivalenza): allora conta
        from archivio import equivalenze
        eq = equivalenze(percorso(cfg, "risultati"))
        corrette = [c for c in insieme if c["riferimento"].get("entita_verificata")
                    and eq.get(c["entita"], {}).get("nuovo") != c["riferimento"]["entita_verificata"]]
        equivalenti = [c for c in insieme if c["riferimento"].get("entita_verificata") and c not in corrette]
        validi = [c for c in insieme if c["riferimento"]["giudizio"] in ("sì", "no") and c not in corrette]
        incerti = sum(1 for c in insieme if c["riferimento"]["giudizio"] == "incerto" and c not in corrette)
        out += [f"Insieme di riferimento: {len(insieme)} passaggi verificati a mano ({incerti} «incerti» e "
                f"{len(corrette)} con l'entità corretta a mano esclusi dalle misure).", ""]
        if equivalenti:
            out += ["Entità corrette a mano con un nome equivalente (contate, sulla lettura fatta sotto il nome "
                    "originale):", ""] + [
                f"- {c['id']}: {c['entita']} = {c['riferimento']['entita_verificata']} (giudizio "
                f"{c['riferimento']['giudizio']})" for c in equivalenti] + [""]
        if corrette:
            out += ["Entità corrette a mano, escluse:", ""] + [
                f"- {c['id']}: {c['entita']} -> {c['riferimento']['entita_verificata']} (giudizio "
                f"{c['riferimento']['giudizio']})" for c in corrette] + [""]
        out += ["## Classificazione", "",
                "| chi decide | passaggi | richiamo (sì o incerto) | richiamo (solo sì) | precisione |",
                "|---|---|---|---|---|"]
        arch = Archivio(percorso(cfg, "risultati"))
        per_livello = defaultdict(list)
        for c in validi:
            v = arch.per_id.get((c["id"], c["entita"]))
            if not v:
                continue
            p = provenienza(v["analisi"])["decisione"]
            et = LIVELLI.get(p["livello"], p["livello"]) + (f" ({p['da']})" if p.get("da") else "")
            per_livello[et].append((c["riferimento"]["giudizio"], v["analisi"]["pertinente"]))
            per_livello["archivio, tutte le letture"].append((c["riferimento"]["giudizio"], v["analisi"]["pertinente"]))
        for et, coppie in sorted(per_livello.items(), key=lambda x: -len(x[1])):
            out.append(riga_misure(et, misure(coppie)))
        out += ["", "Richiamo: pertinenti veri riconosciuti / pertinenti veri. Precisione: «sì» davvero pertinenti "
                "/ «sì». IC 95% con il metodo di Wilson: con pochi passaggi l'intervallo è largo.", ""]
        modelli = elenco_modelli(args, cfg)
        if modelli:
            # i passaggi di un nome dichiarato equivalente si leggono con la scheda di destinazione
            da_leggere = []
            for c in validi[:args.limite or None]:
                nuovo = c["riferimento"].get("entita_verificata") if c in equivalenti else eq.get(c["entita"], {}).get("nuovo")
                da_leggere.append(dict(c, entita=nuovo) if nuovo else c)
            out += prova_modelli(args, cfg, d, da_leggere, modelli)
    if (d / "estrazione.json").exists():
        e = json.loads((d / "estrazione.json").read_text(encoding="utf-8"))
        k, mancate = e["occorrenze_estrazione"], e["mancate_confermate"]
        out += ["## Estrazione", "",
                f"Entità: {e['entita']}; file letti: {len(e['file_letti'])}; occorrenze trovate dall'estrazione: {k}; "
                f"occorrenze sfuggite, confermate a mano: {mancate} (su {e['candidati']} candidati della ricerca larga).",
                "", f"Richiamo dell'estrazione (stima): {proporzione(k, k + mancate)}.", "",
                "La stima vale per le forme che la ricerca larga sa proporre (cognome, una lettera o un carattere "
                "diversi, accenti): un errore OCR più grave resta invisibile anche qui.", ""]
    if len(out) <= 4:
        sys.exit("Niente da misurare: esegui prima «importa».")
    f = d / f"misure_{dt.datetime.now():%Y%m%d_%H%M}.md"
    f.write_bytes("\n".join(out).encode("utf-8"))
    print("\n".join(out))
    print(f"\nScritto: {f}")


# modelli che non servono a leggere passaggi: router, filtri di sicurezza, codice, immagini e audio, strumenti
# specializzati (estrazione da documenti, traduzione dedicata, calibrazione)
NON_LETTORI = re.compile(r"^(auto|fusion)\b|guard|safety|topic-control|code|fim\b|vision|llava|moondream|voxtral|"
                         r"robotics|diffusion|parse|translate|calibration|-lora$", re.IGNORECASE)


def elenco_modelli(args, cfg):
    """Modelli da provare: quelli indicati, «tutti» (i modelli attivi nel router, senza i NON_LETTORI e quelli
    di --escludi) oppure la configurazione attuale (--config-attuale)."""
    voce = (args.modelli or "").strip()
    if voce.lower() == "tutti":
        from valuta import modelli_disponibili
        try:
            attivi = sorted(set(modelli_disponibili(cfg)))
        except Exception as e:
            sys.exit(f"Non riesco a leggere i modelli attivi dal router ({e}): FreeLLMAPI è acceso?")
        escludi = [x.strip().lower() for x in (args.escludi or "").split(";") if x.strip()]
        scelti = [m for m in attivi if not NON_LETTORI.search(m) and not any(x in m.lower() for x in escludi)]
        scartati = [m for m in attivi if m not in scelti]
        print(f"Modelli attivi: {len(attivi)}; da provare: {len(scelti)}; esclusi: {', '.join(scartati)}")
        modelli = scelti
    else:
        modelli = [x.strip() for x in voce.split(";") if x.strip()]
    if args.config_attuale:
        modelli.append(None)
    if args.solo_elenco:
        print("\n".join(m or "configurazione attuale" for m in modelli))
        sys.exit(0)
    return modelli


def prova_modelli(args, cfg, d, da_leggere, modelli):
    """Smistamento dei passaggi verificati con ogni modello, a giri: nel primo giro ogni modello legge finché il
    servizio lo ferma (quote al minuto); nei giri successivi riprende da dove era, quando gli altri modelli hanno
    lasciato passare il tempo. Un modello che per due giri di fila non legge nulla si considera fermo (quota del
    giorno esaurita o modello non disponibile). Restituisce le righe della sezione «Modelli»."""
    import time
    from estrai_occorrenze import carica_entita
    from llm import percorso
    schede = carica_entita(percorso(cfg, "entita"))
    leggibili = [c for c in da_leggere if c["entita"] in schede]
    f_mod = d / f"modelli_{dt.datetime.now():%Y%m%d_%H%M}.jsonl"
    stato = {m: {"cartella": prepara_prova(args, cfg, leggibili, m), "letti": 0, "senza_progressi": 0,
                 "fine": "", "giri": 0} for m in modelli}
    print(f"Passaggi da leggere per modello: {len(leggibili)} (su {len(da_leggere)}: gli altri non hanno una scheda).")
    for giro in range(1, args.giri + 1):
        attivi = [m for m in modelli if not stato[m]["fine"]]
        if not attivi:
            break
        inizio = time.time()
        print(f"\n================ Giro {giro} di {args.giri}: {len(attivi)} modelli da completare")
        for i, m in enumerate(attivi, 1):
            s = stato[m]
            print(f"\n######## giro {giro}, [{i}/{len(attivi)}] {m or 'configurazione attuale'} "
                  f"(letti finora {s['letti']}/{len(leggibili)})", flush=True)
            esegui_prova(cfg, s["cartella"])
            prima, s["letti"] = s["letti"], len(letture_prova(s["cartella"]))
            s["giri"] = giro
            if s["letti"] >= len(leggibili):
                s["fine"] = "completo"
            elif s["letti"] == prima:
                s["senza_progressi"] += 1
                if s["senza_progressi"] >= 2:
                    s["fine"] = "fermo (nessuna lettura per due giri: quota esaurita o modello non disponibile)"
            else:
                s["senza_progressi"] = 0
            salva_stato_modelli(f_mod, stato, leggibili)
        resto = 70 - (time.time() - inizio)       # le quote dei servizi gratuiti si contano di solito al minuto
        if giro < args.giri and any(not stato[m]["fine"] for m in modelli) and resto > 0:
            print(f"\nAttendo {resto:.0f} s prima del giro successivo (quote al minuto).", flush=True)
            time.sleep(resto)
    for m in modelli:
        if not stato[m]["fine"]:
            stato[m]["fine"] = f"incompleto dopo {args.giri} giri"
    salva_stato_modelli(f_mod, stato, leggibili)
    out = ["## Modelli (smistamento dei passaggi verificati, senza archivio né regole)", "",
           f"Modelli provati: {len(modelli)}, in {max(s['giri'] for s in stato.values())} giri; passaggi da leggere "
           f"per modello: {len(leggibili)}. Stato dettagliato in `{f_mod.name}`.", "",
           "| modello richiesto | ha risposto | passaggi letti | richiamo (sì o incerto) | richiamo (solo sì) "
           "| precisione | stato |", "|---|---|---|---|---|---|---|"]
    righe = []
    for m in modelli:
        risposto, mm = risultato_prova(stato[m]["cartella"], leggibili)
        righe.append((-(mm["n"] if mm else 0), m or "configurazione attuale", risposto, mm, stato[m]["fine"]))
    for _, nome, risposto, mm, fine in sorted(righe):
        if mm and mm["n"]:
            out.append(f"| {nome} | {risposto} | {mm['n']}/{len(leggibili)} | {proporzione(*mm['richiamo'])} | "
                       f"{proporzione(*mm['richiamo_stretto'])} | {proporzione(*mm['precisione'])} | {fine} |")
        else:
            out.append(f"| {nome} | nessuna risposta | 0/{len(leggibili)} | — | — | — | {fine} |")
    out += ["", "«Ha risposto»: il modello che il router ha usato davvero (se è diverso da quello richiesto, la riga "
            "non misura il modello richiesto). Un modello che non ha letto tutti i passaggi è misurato solo su "
            "quelli letti: i suoi valori non sono confrontabili con quelli dei modelli completi.", ""]
    return out


def salva_stato_modelli(f_mod, stato, leggibili):
    righe = []
    for m, s in stato.items():
        risposto, mm = risultato_prova(s["cartella"], leggibili)
        righe.append(json.dumps({"modello": m or "configurazione attuale", "risposto": risposto, "letti": s["letti"],
                                 "da_leggere": len(leggibili), "giri": s["giri"], "stato": s["fine"] or "in corso",
                                 "cartella": s["cartella"].name, "misure": mm}, ensure_ascii=False) + "\n")
    tmp = f_mod.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(righe)
    tmp.replace(f_mod)


def letture_prova(cartella):
    f = Path(cartella) / "classificati.jsonl"
    pred = {}
    if f.exists():
        for riga in f.read_text(encoding="utf-8").splitlines():
            if riga.strip():
                c = json.loads(riga)
                if not c["analisi"].get("assorbito_da"):
                    pred[(c["id"], c["entita"])] = c["analisi"]
    return pred


def risultato_prova(cartella, leggibili):
    """(modelli che hanno risposto davvero, misure sui passaggi letti) di una cartella di prova."""
    pred = letture_prova(cartella)
    if not pred:
        return "", None
    coppie = [(c["riferimento"]["giudizio"], pred[(c["id"], c["entita"])]["pertinente"])
              for c in leggibili if (c["id"], c["entita"]) in pred]
    usati = Counter(a.get("modello_smistamento", "?") for a in pred.values())
    return ", ".join(m for m, _ in usati.most_common(3)), misure(coppie)


def esegui_prova(cfg, cartella):
    """Un passo di lettura: classifica.py riprende da dove era arrivato e si ferma quando il servizio lo ferma."""
    import os
    from llm import percorso
    r = subprocess.run([sys.executable, "-u", str(CARTELLA / "classifica.py"), str(cartella),
                        str(percorso(cfg, "entita")), "--solo-smistamento", "--config",
                        str(Path(cartella) / "config_prova.ini")],
                       cwd=CARTELLA, env=dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8"))
    return r.returncode


def prepara_prova(args, cfg, validi, modello):
    """Cartella di prova per un modello (o per la configurazione attuale): i passaggi da leggere e una copia di
    config.ini senza archivio e senza le regole che saltano il modello (forme inequivocabili)."""
    import configparser
    from llm import percorso
    from valuta import config_per_modello
    ora = f"{dt.datetime.now():%Y%m%d_%H%M%S}"
    nome = re.sub(r"[^A-Za-z0-9]+", "-", modello or "config")[:40]
    prova = percorso(cfg, "risultati") / "_prove" / f"prova_valutazione_{nome}_{ora}"
    prova.mkdir(parents=True, exist_ok=True)
    (prova / ".senza_archivio").write_text("Cartella di prova: niente archivio unico.\n", encoding="utf-8")
    with open(prova / "passaggi.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for c in validi:
            f.write(json.dumps({k: v for k, v in c.items() if k != "riferimento"}, ensure_ascii=False) + "\n")
    cfg_base = Path(args.config) if args.config else CARTELLA / "config.ini"
    cfg_file = prova / "config_prova.ini"
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#",))
    cp.optionxform = str
    if modello:
        config_per_modello(cfg_base, modello, cfg_file)
        cp.read(cfg_file, encoding="utf-8")
    else:                                   # configurazione attuale, con i percorsi resi assoluti
        cp.read(cfg_base, encoding="utf-8")
        for k in cp["percorsi"]:
            cp["percorsi"][k] = str(percorso(cfg, k))
    if not cp.has_section("estrazione"):
        cp.add_section("estrazione")
    cp["estrazione"]["forme_sicure"] = "no"
    with open(cfg_file, "w", encoding="utf-8") as fc:
        cp.write(fc)
    return prova


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="comando", required=True)
    a = sub.add_parser("campione")
    a.add_argument("nome")
    a.add_argument("--n", type=int, default=100)
    a.add_argument("--entita", default="")
    a.add_argument("--fonti", default="")
    a.add_argument("--seme", type=int, default=2026)
    b = sub.add_parser("candidati")
    b.add_argument("nome")
    b.add_argument("--entita", required=True)
    b.add_argument("--file", type=int, default=60)
    b.add_argument("--seme", type=int, default=2026)
    c = sub.add_parser("importa")
    c.add_argument("nome")
    m = sub.add_parser("misura")
    m.add_argument("nome")
    m.add_argument("--modelli", default="", help="modelli da provare, separati da ';' (nomi del router), "
                                                 "oppure «tutti» (i modelli attivi in FreeLLMAPI)")
    m.add_argument("--escludi", default="", help="con --modelli tutti: parti di nome da escludere, separate da ';'")
    m.add_argument("--solo-elenco", action="store_true", help="mostra i modelli che verrebbero provati ed esce")
    m.add_argument("--limite", type=int, default=None, help="solo i primi N passaggi (prova veloce)")
    m.add_argument("--giri", type=int, default=8, help="giri di lettura al massimo (i modelli fermati dalle quote "
                                                       "riprendono al giro successivo)")
    m.add_argument("--config-attuale", action="store_true", help="prova anche i modelli di config.ini")
    for p in (a, b, c, m):
        p.add_argument("--config", default=None)
    args = ap.parse_args()
    from llm import leggi_config
    cfg = leggi_config(args.config)
    {"campione": campione, "candidati": candidati, "importa": importa, "misura": misura}[args.comando](args, cfg)


if __name__ == "__main__":
    main()

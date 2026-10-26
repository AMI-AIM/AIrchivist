#!/usr/bin/env python3
"""
Strumento di valutazione: insieme di riferimento verificato a mano e misure di precisione e richiamo,
su qualsiasi corpus.

Due misure distinte:
  - estrazione: quante occorrenze vere delle forme del nome trova estrai_occorrenze.py (richiamo);
  - classificazione: quanto sono giuste le decisioni sulla pertinenza, per ogni modello e per ogni livello di
    provenienza delle letture già in archivio (modello, sessione assistita, regola).

Procedura (ogni insieme sta in results/evaluation/<nome>/):
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
  5. python valutazione.py misura <nome> [--modelli "nome1; nome2"] [--profili "p1; p2"] [--config config.ini]
       Misure sulle letture in archivio (per livello di provenienza), sui modelli indicati (smistamento,
       senza archivio, in una cartella di prova) e sull'estrazione. Scrive misure_<data>.md. --modelli: nomi dei
       modelli del router (FreeLLMAPI); --profili: profili di modello di models.ini, di qualsiasi servizio.
       Ogni misura registra il profilo con cui è fatta (nome, servizio, modello: modelli_<data>.jsonl), così
       installa.py modello elenca e lo strumento MCP «modello» sanno se un profilo è misurato su queste fonti.

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

from tabelle import leggi_xlsx  # noqa: F401  (anche per chi la importava da qui)

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
    d = percorso(cfg, "risultati") / "evaluation" / re.sub(r"[^\w\-]+", "_", nome).strip("_")
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
        descrizione = scheda["note"] if scheda else "(nessuna scheda con questo nome in entities.ini)"
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
        sys.exit(f"Scheda «{nome}» non trovata in entities.ini.")
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
            # correzioni fatte dopo la verifica alla cieca (per esempio dopo il confronto con i modelli): sono
            # registrate in correzioni.csv con il motivo e restano visibili nell'insieme e nelle misure
            correzioni = {}
            if (d / "correzioni.csv").exists():
                for r in leggi_csv(d / "correzioni.csv"):
                    v = GIUDIZI.get((r.get("GIUDIZIO") or "").strip().lower())
                    if v and r.get("ID", "").strip() in ids:
                        correzioni[r["ID"].strip()] = {"giudizio": v, "motivo": (r.get("MOTIVO") or "").strip(),
                                                       "il": (r.get("CORRETTO_IL") or "").strip(),
                                                       "da": (r.get("CORRETTO_DA") or "").strip()}
            precedenti = {}                                # giudizi dell'importazione precedente, alla cieca
            if (d / "insieme.jsonl").exists():
                for r in (d / "insieme.jsonl").read_text(encoding="utf-8").splitlines():
                    if r.strip():
                        v = json.loads(r)
                        rif = v["riferimento"]
                        precedenti[v["id"]] = (rif.get("correzione") or {}).get("prima") or rif["giudizio"]
            for c in nascosti:
                x = dict(g[c["id"]], importato_il=oggi)
                nel_file = x.pop("entita_nel_file")
                x.pop("n")
                if c["id"] in correzioni:
                    corr = correzioni[c["id"]]
                    prima = precedenti.get(c["id"], x["giudizio"])
                    x["giudizio"] = corr["giudizio"]
                    x["correzione"] = dict(corr, prima=prima, dopo=corr["giudizio"])
                    del x["correzione"]["giudizio"]
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
            if correzioni:
                print(f"Giudizi corretti dopo la verifica alla cieca (correzioni.csv): {len(correzioni)}")
                for i, corr in correzioni.items():
                    print(f"  {i}: {precedenti.get(i, '?')} -> {corr['giudizio']} ({corr['motivo'][:90]})")
            finali = Counter(json.loads(r)["riferimento"]["giudizio"] for r in righe)
            print(f"insieme.jsonl: {len(nascosti)} passaggi verificati ({dict(finali)}).")
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
        corretti = [c for c in insieme if c["riferimento"].get("correzione")]
        if corretti:
            out += [f"Giudizi corretti dopo la verifica alla cieca (correzioni.csv): {len(corretti)}. Queste "
                    "correzioni non sono alla cieca: possono avvicinare il riferimento alle risposte dei modelli.", ""] + [
                f"- {c['id']} ({c['entita']}): {c['riferimento']['correzione']['prima']} -> "
                f"{c['riferimento']['giudizio']}: {c['riferimento']['correzione']['motivo']}" for c in corretti] + [""]
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


PROFILO = "profilo:"          # voce dell'elenco dei modelli che indica un profilo di models.ini (--profili)


def config_grezza(cfg_file):
    """La configurazione di una prova così com'è scritta, senza il project.ini del progetto in uso: il modello
    misurato è quello della prova anche se il progetto ne sceglie un altro."""
    import configparser
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#",))
    cp.read(cfg_file, encoding="utf-8")
    return cp


def info_profilo(cfg_file):
    """Profilo con cui è fatta una prova: nome, servizio e modello (le misure si legano al profilo)."""
    from llm import ErroreModello, profilo
    try:
        nome, p = profilo(config_grezza(cfg_file), "smistamento")
    except ErroreModello:
        return {}
    return {"profilo": nome, "servizio": p.get("servizio", ""), "modello_profilo": p.get("modello", "")}


def fissa_prova(prova, cfg_file):
    """modelli.json della cartella di prova: classifica.py usa questi profili, qualunque cosa scelga il project.ini
    del progetto in uso (llm.py, AIRCHIVIST_PROFILI_RICERCA)."""
    from llm import RUOLI, profilo
    grezza = config_grezza(cfg_file)
    dati = {"stato": "prova", "ruoli": {r: dict(zip(("nome", "voci"), profilo(grezza, r))) for r in RUOLI}}
    (Path(prova) / "modelli.json").write_text(json.dumps(dati, ensure_ascii=False, indent=1), encoding="utf-8")


def elenco_modelli(args, cfg):
    """Modelli da provare: quelli indicati, «tutti» (i modelli attivi nel router, senza i NON_LETTORI e quelli
    di --escludi), i profili di --profili oppure la configurazione attuale (--config-attuale)."""
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
    profili_chiesti = [x.strip() for x in (getattr(args, "profili", "") or "").split(";") if x.strip()]
    if profili_chiesti:
        from llm import leggi_profili
        esistenti = leggi_profili(cfg)
        assenti = [x for x in profili_chiesti if x not in esistenti]
        if assenti:
            sys.exit(f"Profili inesistenti: {', '.join(assenti)} (profili: {', '.join(esistenti) or 'nessuno'}).")
        modelli += [PROFILO + x for x in profili_chiesti]
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
                                 "cartella": s["cartella"].name, "misure": mm,
                                 **info_profilo(s["cartella"] / "config_prova.ini")}, ensure_ascii=False) + "\n")
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
    from llm import VARIABILE_FISSATI, percorso
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    env.pop(VARIABILE_FISSATI, None)
    if (Path(cartella) / "modelli.json").exists():
        env[VARIABILE_FISSATI] = str(Path(cartella) / "modelli.json")
    r = subprocess.run([sys.executable, "-u", str(CARTELLA / "classifica.py"), str(cartella),
                        str(percorso(cfg, "entita")), "--solo-smistamento", "--config",
                        str(Path(cartella) / "config_prova.ini")],
                       cwd=CARTELLA, env=env)
    return r.returncode


def prepara_prova(args, cfg, validi, modello):
    """Cartella di prova per un modello (o per la configurazione attuale): i passaggi da leggere e una copia di
    config.ini senza archivio e senza le regole che saltano il modello (forme inequivocabili)."""
    import configparser
    from llm import percorso
    from valuta import config_per_modello
    ora = f"{dt.datetime.now():%Y%m%d_%H%M%S}"
    nome = re.sub(r"[^A-Za-z0-9]+", "-", modello or "config")[:40]
    prova = percorso(cfg, "risultati") / "trials" / f"prova_valutazione_{nome}_{ora}"
    prova.mkdir(parents=True, exist_ok=True)
    (prova / ".senza_archivio").write_text("Cartella di prova: niente archivio unico.\n", encoding="utf-8")
    with open(prova / "passaggi.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for c in validi:
            f.write(json.dumps({k: v for k, v in c.items() if k != "riferimento"}, ensure_ascii=False) + "\n")
    cfg_base = Path(args.config) if args.config else CARTELLA / "config.ini"
    cfg_file = prova / "config_prova.ini"
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#",))
    cp.optionxform = str
    if modello and not modello.startswith(PROFILO):
        config_per_modello(cfg_base, modello, cfg_file)
        cp.read(cfg_file, encoding="utf-8")
    else:                                   # configurazione attuale o un profilo, con i percorsi resi assoluti
        from llm import RUOLI, leggi_config
        from progetto import percorsi_assoluti
        cp = leggi_config(cfg_base)         # config.ini più project.ini del progetto in uso
        if cp.has_section("progetto"):
            cp.remove_section("progetto")
        if not cp.has_section("percorsi"):
            cp.add_section("percorsi")
        for k, v in percorsi_assoluti(cfg).items():
            cp["percorsi"][k] = v
        if modello:
            for r in RUOLI:
                cp.remove_option("modello", r)
            cp["modello"]["profilo"] = modello[len(PROFILO):]
    if not cp.has_section("estrazione"):
        cp.add_section("estrazione")
    cp["estrazione"]["forme_sicure"] = "no"
    with open(cfg_file, "w", encoding="utf-8") as fc:
        cp.write(fc)
    fissa_prova(prova, cfg_file)
    return prova


# ---------------------------------------------------------------- 6. prova rapida dei modelli
SCHEMA_MISTO = {
    "type": "object",
    "properties": {"risultati": {"type": "array", "items": {
        "type": "object",
        "properties": {"n": {"type": "integer"}, "pertinente": {"type": "string", "enum": ["sì", "no", "incerto"]}},
        "required": ["n", "pertinente"]}}},
    "required": ["risultati"],
}


def prompt_misto(gruppo, schede, n):
    """Lotto di passaggi di entità diverse: per ciascuno l'entità, le sue forme e le note della scheda."""
    from classifica import ritaglia
    blocchi = []
    for k, c in enumerate(gruppo, 1):
        s = schede[c["entita"]]
        blocchi.append(f"[{k}] Entità cercata: {c['entita']}\nAltre forme del nome: {'; '.join(s['varianti'][:10])}\n"
                       f"Note: {(s['note'] or '-')[:500]}\nFonte: {c.get('citazione') or c.get('fonte', '')}\n"
                       f"PASSAGGIO: {ritaglia(c, n)}")
    return (f"Seguono {len(gruppo)} passaggi numerati, ciascuno con la sua entità cercata. In ogni passaggio le "
            "occorrenze trovate dalla ricerca sono tra ⟦ e ⟧.\nPer OGNI passaggio decidi se le occorrenze si "
            "riferiscono davvero all'entità cercata in quel passaggio:\n"
            "- \"sì\": il passaggio parla dell'entità cercata (anche solo nominandola in un elenco).\n"
            "- \"no\": è un omonimo, un'altra organizzazione, o un uso generico delle stesse parole.\n"
            "- \"incerto\": il testo non basta per decidere.\nValuta ogni passaggio per conto suo.\n\n"
            + "\n\n".join(blocchi)
            + f"\n\nRispondi con JSON: {{\"risultati\": [{{\"n\": 1, \"pertinente\": \"sì\" | \"no\" | \"incerto\"}}, ...]}} "
              f"con una voce per ciascuno dei {len(gruppo)} passaggi.")


def catalogo_router(cfg):
    """Modelli del router con i loro dati (nome, contesto, stato delle quote)."""
    from llm import catalogo_router as catalogo
    return catalogo(cfg)


def scegli_modelli(args, cfg):
    """(da provare, scartati con il motivo) in base ai dati del router, senza nessuna richiesta ai modelli."""
    if args.modelli and args.modelli.strip().lower() != "tutti":
        return [x.strip() for x in args.modelli.split(";") if x.strip()], []
    try:
        cat = catalogo_router(cfg)
    except Exception as e:
        sys.exit(f"Non riesco a leggere i modelli dal router ({e}): FreeLLMAPI è acceso?")
    escludi = [x.strip().lower() for x in (args.escludi or "").split(";") if x.strip()]
    scelti, scartati, visti = [], [], {}
    for m in cat:
        mid, nome = m.get("id", ""), (m.get("name") or "")
        ctx = m.get("context_window") or m.get("context_length")
        motivo = ""
        if NON_LETTORI.search(mid):
            motivo = "non serve a leggere passaggi (router, sicurezza, codice, immagini, audio, strumenti)"
        elif "slot" in nome.lower() or "auto-routed" in nome.lower() or "router" in nome.lower() or ":" in mid:
            motivo = "alias instradato ad altri modelli"
        elif m.get("execution_status") == "exhausted":
            motivo = "quota esaurita adesso (exhausted)"
        elif ctx and ctx < args.contesto_min:
            motivo = f"contesto troppo piccolo ({ctx} token)"
        elif any(x in mid.lower() for x in escludi):
            motivo = "escluso con --escludi"
        else:
            chiave = re.sub(r"[^a-z0-9]", "", nome.lower()) or mid
            if chiave in visti:
                motivo = f"doppione di {visti[chiave]}"
            else:
                visti[chiave] = mid
        (scartati.append((mid, motivo)) if motivo else scelti.append(mid))
    return scelti, scartati


def leggi_con_modello(cfg_file, modello, gruppi, schede, n, stampa):
    """Smistamento dei lotti con un modello: {(id, entita): pertinente}, modelli che hanno risposto, errore finale."""
    from llm import LLM, ErroreModello
    from classifica import SISTEMA
    llm = LLM(config_grezza(cfg_file), "smistamento")
    esiti, usati, errore = {}, Counter(), ""
    for k, gruppo in enumerate(gruppi, 1):
        try:
            r = llm.json(SISTEMA, prompt_misto(gruppo, schede, n), SCHEMA_MISTO)
        except ErroreModello as e:
            # llm.py ha già atteso e ritentato: quota esaurita, modello assente o richiesta troppo grande non
            # passano con altri tentativi, quindi il modello si ferma qui invece di riprovare a ogni lotto
            errore = str(e)[:300]
            stampa(f"  {modello}: lotto {k}/{len(gruppi)} non letto, mi fermo ({errore[:120]})")
            break
        usati[llm.ultimo_modello] += 1
        for voce in r.get("risultati") or []:
            try:
                i = int(voce.get("n"))
            except (TypeError, ValueError):
                continue
            if 1 <= i <= len(gruppo) and voce.get("pertinente") in ("sì", "no", "incerto"):
                c = gruppo[i - 1]
                esiti[(c["id"], c["entita"])] = voce["pertinente"]
        stampa(f"  {modello}: lotto {k}/{len(gruppi)} letto ({len(esiti)} risposte finora)")
    return esiti, usati, errore


def prova_rapida(args, cfg):
    """Prova rapida di molti modelli sull'insieme verificato: lotti misti (passaggi di entità diverse nella stessa
    richiesta), modelli in parallelo, una prima fase su pochi passaggi e la seconda solo per i migliori."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from estrai_occorrenze import carica_entita
    from archivio import equivalenze
    from llm import percorso
    from valuta import config_per_modello
    d = cartella(cfg, args.nome)
    insieme = [json.loads(r) for r in (d / "insieme.jsonl").read_text(encoding="utf-8").splitlines() if r.strip()]
    eq = equivalenze(percorso(cfg, "risultati"))
    schede = carica_entita(percorso(cfg, "entita"))
    passaggi = []
    for c in insieme:
        if c["riferimento"]["giudizio"] not in ("sì", "no"):
            continue
        nuovo = c["riferimento"].get("entita_verificata") or eq.get(c["entita"], {}).get("nuovo")
        if nuovo and nuovo != c["entita"] and eq.get(c["entita"], {}).get("nuovo") != nuovo:
            continue                                  # entità corretta in un'altra non equivalente
        c = dict(c, entita=nuovo) if nuovo else c
        if c["entita"] in schede:
            passaggi.append(c)
    # prima fase: un sottoinsieme bilanciato tra pertinenti e no, con il seme fisso
    rnd = random.Random(args.seme)
    si = [c for c in passaggi if c["riferimento"]["giudizio"] == "sì"]
    no = [c for c in passaggi if c["riferimento"]["giudizio"] == "no"]
    rnd.shuffle(si)
    rnd.shuffle(no)
    meta = min(len(no), args.prima_fase // 2)
    prima = no[:meta] + si[:args.prima_fase - meta]
    rnd.shuffle(prima)
    n = cfg.getint("estrazione", "finestra_modello", fallback=300)
    if args.riprendi:
        # seconda fase di una prova già fatta: la prima fase si legge da prima.jsonl
        prove = Path(args.riprendi)
        if not prove.is_absolute():
            prove = percorso(cfg, "risultati") / "trials" / prove
        if not (prove / "prima.jsonl").exists():
            sys.exit(f"Nella cartella {prove} non c'è prima.jsonl.")
        modelli, scartati = [], []
        ora = prove.name.replace("prova_rapida_", "")
    else:
        modelli, scartati = scegli_modelli(args, cfg)
        print(f"Passaggi verificati utilizzabili: {len(passaggi)}; prima fase: {len(prima)} "
              f"({sum(1 for c in prima if c['riferimento']['giudizio'] == 'sì')} pertinenti).")
        print(f"Modelli da provare: {len(modelli)}; scartati senza richieste: {len(scartati)}")
        for m, motivo in scartati:
            print(f"  - {m}: {motivo}")
        if args.solo_elenco:
            print("\n".join(modelli))
            return
        ora = f"{dt.datetime.now():%Y%m%d_%H%M}"
        prove = percorso(cfg, "risultati") / "trials" / f"prova_rapida_{ora}"
        prove.mkdir(parents=True, exist_ok=True)
        (prove / ".senza_archivio").write_text("Prove dei modelli: niente archivio unico.\n", encoding="utf-8")
        (prove / "scartati.json").write_bytes(json.dumps(scartati, ensure_ascii=False, indent=1).encode("utf-8"))
    cfg_base = Path(args.config) if args.config else CARTELLA / "config.ini"
    blocco = threading.Lock()

    def stampa(t):
        with blocco:
            print(t, flush=True)

    def fase(nome_fase, lista, insieme_fase):
        gruppi = [insieme_fase[i:i + args.lotto] for i in range(0, len(insieme_fase), args.lotto)]
        print(f"\n======== {nome_fase}: {len(lista)} modelli, {len(insieme_fase)} passaggi in {len(gruppi)} "
              f"richieste per modello, {args.paralleli} modelli alla volta", flush=True)

        def uno(m):
            cf = prove / f"config_{re.sub(r'[^A-Za-z0-9]+', '-', m)[:50]}.ini"
            config_per_modello(cfg_base, m, cf)
            esiti, usati, errore = leggi_con_modello(cf, m, gruppi, schede, n, stampa)
            coppie = [(c["riferimento"]["giudizio"], esiti[(c["id"], c["entita"])]) for c in insieme_fase
                      if (c["id"], c["entita"]) in esiti]
            return {"modello": m, "risposto": ", ".join(x for x, _ in usati.most_common(3)), "letti": len(coppie),
                    "da_leggere": len(insieme_fase), "errore": errore, "misure": misure(coppie) if coppie else None,
                    **info_profilo(cf),
                    # decisione del modello su ogni passaggio, per confrontare gli errori tra i modelli
                    "decisioni": {f"{i}|{e}": v for (i, e), v in esiti.items()}}

        with ThreadPoolExecutor(max_workers=args.paralleli) as ex:
            risultati = list(ex.map(uno, lista))
        with open(prove / f"{nome_fase.split()[0].lower()}.jsonl", "w", encoding="utf-8", newline="\n") as f:
            for r in risultati:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        return risultati

    def punteggio(r):
        m = r["misure"]
        if not m or r["letti"] < r["da_leggere"]:
            return (0, 0, 0, 0)
        ric = m["richiamo"][0] / m["richiamo"][1] if m["richiamo"][1] else 0
        pre = m["precisione"][0] / m["precisione"][1] if m["precisione"][1] else 0
        stretto = m["richiamo_stretto"][0] / m["richiamo_stretto"][1] if m["richiamo_stretto"][1] else 0
        return (1, ric, stretto, pre)

    def tabella(risultati):
        righe = ["| modello richiesto | ha risposto | passaggi letti | richiamo (sì o incerto) | richiamo (solo sì) "
                 "| precisione | nota |", "|---|---|---|---|---|---|---|"]
        for r in sorted(risultati, key=punteggio, reverse=True):
            m = r["misure"]
            if m:
                righe.append(f"| {r['modello']} | {r['risposto']} | {r['letti']}/{r['da_leggere']} | "
                             f"{proporzione(*m['richiamo'])} | {proporzione(*m['richiamo_stretto'])} | "
                             f"{proporzione(*m['precisione'])} | {r['errore'][:80]} |")
            else:
                righe.append(f"| {r['modello']} | — | 0/{r['da_leggere']} | — | — | — | {r['errore'][:80]} |")
        return righe

    f = d / f"prova_rapida_{ora}.md"

    def rapporto(r1, r2, migliori, finita):
        out = [f"# Prova rapida dei modelli: {args.nome}", "", f"*{dt.datetime.now():%Y-%m-%d %H:%M}*", "",
               f"Smistamento (pertinente sì/no) dei passaggi verificati a mano, in lotti misti di {args.lotto} "
               "passaggi di entità diverse, senza archivio né regole. Il formato dei lotti differisce da quello delle "
               "ricerche (un'entità per lotto): la misura confronta i modelli tra loro.", "",
               f"Modelli provati: {len(r1)}; scartati senza richieste: {len(scartati)}.", "",
               f"## Seconda fase: i {len(migliori)} migliori su {len(passaggi)} passaggi", ""]
        if r2:
            out += tabella(r2)
        elif not finita:
            out += [f"*(non ancora fatta: python valutazione.py modelli {args.nome} --riprendi {prove.name})*"]
        else:
            out += ["*(nessun modello ha letto tutti i passaggi della prima fase)*"]
        out += ["", f"## Prima fase: {len(prima)} passaggi", ""] + tabella(r1)
        out += ["", "## Modelli scartati senza richieste", ""] + [f"- {m}: {motivo}" for m, motivo in scartati]
        out += ["", "«Ha risposto»: il modello che il router ha usato davvero. Un modello che non ha letto tutti i "
                "passaggi non passa alla seconda fase: i suoi valori riguardano solo i passaggi letti.", ""]
        f.write_bytes("\n".join(out).encode("utf-8"))
        return out

    if args.riprendi:
        r1 = [json.loads(x) for x in (prove / "prima.jsonl").read_text(encoding="utf-8").splitlines() if x.strip()]
        if (prove / "scartati.json").exists():
            scartati = json.loads((prove / "scartati.json").read_text(encoding="utf-8"))
        else:                                   # prove fatte prima che gli scarti si salvassero: si ricalcolano
            scartati = scegli_modelli(args, cfg)[1]
        print(f"Prima fase ripresa da {prove.name}: {len(r1)} modelli, "
              f"{sum(1 for r in r1 if punteggio(r)[0])} con tutti i passaggi letti.")
    else:
        r1 = fase("Prima fase", modelli, prima)
    migliori = [r["modello"] for r in sorted(r1, key=punteggio, reverse=True) if punteggio(r)[0]][:args.migliori]
    rapporto(r1, [], migliori, finita=False)                 # la prima fase resta anche se la seconda si interrompe
    r2 = fase("Seconda fase", migliori, passaggi) if migliori and len(passaggi) > len(prima) else []
    out = rapporto(r1, r2, migliori, finita=True)
    print("\n".join(out[:12 + len(r2)]))
    print(f"\nScritto: {f}")


def errori_comuni(args, cfg):
    """Passaggi su cui i modelli della seconda fase di una prova rapida sbagliano rispetto al giudizio verificato:
    prima quelli sbagliati da tutti, poi quelli sbagliati dalla maggioranza. Per ognuno: giudizio, decisioni dei
    modelli, decisione dell'archivio, note della scheda e testo del passaggio."""
    from archivio import Archivio, descrivi_provenienza, provenienza
    from estrai_occorrenze import carica_entita
    from llm import percorso
    from citazioni import per_passaggio
    d = cartella(cfg, args.nome)
    prove_dir = percorso(cfg, "risultati") / "trials"
    if args.prova:
        prova = Path(args.prova) if Path(args.prova).is_absolute() else prove_dir / args.prova
    else:
        candidate = [p for p in prove_dir.glob("prova_rapida_*") if (p / "seconda.jsonl").exists()
                     and "decisioni" in (p / "seconda.jsonl").read_text(encoding="utf-8")]
        if not candidate:
            sys.exit("Nessuna prova rapida con le decisioni dei modelli: rifai «valutazione.py modelli».")
        prova = max(candidate, key=lambda p: p.stat().st_mtime)
    risultati = [json.loads(r) for r in (prova / "seconda.jsonl").read_text(encoding="utf-8").splitlines() if r.strip()]
    risultati = [r for r in risultati if r.get("decisioni") and r["letti"] == r["da_leggere"]]
    if not risultati:
        sys.exit(f"In {prova.name} nessun modello ha letto tutti i passaggi della seconda fase.")
    schede = carica_entita(percorso(cfg, "entita"))
    from archivio import equivalenze
    eq = equivalenze(percorso(cfg, "risultati"))
    arch = Archivio(percorso(cfg, "risultati"))
    dati = percorso(cfg, "dati")
    insieme = [json.loads(r) for r in (d / "insieme.jsonl").read_text(encoding="utf-8").splitlines() if r.strip()]
    casi = []
    for c in insieme:
        g = c["riferimento"]["giudizio"]
        ent = c["riferimento"].get("entita_verificata") or eq.get(c["entita"], {}).get("nuovo") or c["entita"]
        dec = {r["modello"]: r["decisioni"].get(f"{c['id']}|{ent}") for r in risultati}
        dec = {m: v for m, v in dec.items() if v}
        if g not in ("sì", "no") or not dec:
            continue
        # «incerto» di un modello su un pertinente vale come trovato (richiamo), non come errore
        sbagliati = [m for m, v in dec.items() if (g == "sì" and v == "no") or (g == "no" and v != "no")]
        if len(sbagliati) * 2 > len(dec):
            casi.append((len(sbagliati) == len(dec), c, ent, g, dec))
    casi.sort(key=lambda x: (not x[0], x[3], x[2]))
    # misure dei modelli ricalcolate dalle decisioni salvate sui giudizi attuali (dopo eventuali correzioni)
    tab = ["| modello | passaggi | richiamo (sì o incerto) | richiamo (solo sì) | precisione |", "|---|---|---|---|---|"]
    for r in risultati:
        coppie = []
        for c in insieme:
            g = c["riferimento"]["giudizio"]
            ent = c["riferimento"].get("entita_verificata") or eq.get(c["entita"], {}).get("nuovo") or c["entita"]
            v = r["decisioni"].get(f"{c['id']}|{ent}")
            if g in ("sì", "no") and v:
                coppie.append((g, v))
        mm = misure(coppie)
        tab.append(f"| {r['modello']} | {mm['n']} | {proporzione(*mm['richiamo'])} | "
                   f"{proporzione(*mm['richiamo_stretto'])} | {proporzione(*mm['precisione'])} |")
    corretti = sum(1 for c in insieme if c["riferimento"].get("correzione"))
    out = [f"# Errori comuni dei modelli: {args.nome}", "", f"*{dt.datetime.now():%Y-%m-%d %H:%M}* — prova {prova.name}, "
           f"modelli: {', '.join(r['modello'] for r in risultati)}.", "",
           "## Misure sui giudizi attuali", ""] + tab + [""] + (
           [f"Giudizi corretti dopo la verifica alla cieca: {corretti} (correzioni.csv)."] if corretti else []) + [
           "", f"Passaggi sbagliati da tutti i modelli: {sum(1 for x in casi if x[0])}; dalla maggioranza: "
           f"{sum(1 for x in casi if not x[0])}. Un «incerto» su un passaggio pertinente non conta come errore.", ""]
    for n_caso, (tutti, c, ent, g, dec) in enumerate(casi, 1):
        v = arch.per_id.get((c["id"], c["entita"]))
        a = v["analisi"] if v else {}
        s = schede.get(ent, {})
        out += [f"## {n_caso}. {ent} — {'tutti sbagliano' if tutti else 'la maggioranza sbaglia'}", "",
                f"- Fonte: {per_passaggio(c, dati)[0]}",
                f"- Giudizio verificato: **{g}**" + (f" (nota: {c['riferimento']['note']})" if c["riferimento"].get("note") else ""),
                "- Modelli: " + "; ".join(f"{m} {x}" for m, x in dec.items()),
                f"- Archivio: {a.get('pertinente', '—')}" + (f" ({descrivi_provenienza(provenienza(a))})" if a else ""),
                f"- Forme trovate: {'; '.join(c.get('varianti_trovate', []))}",
                f"- Note della scheda: {s.get('note') or '(nessuna)'}", "",
                "> " + (c.get("passaggio_evidenziato") or c.get("passaggio", ""))[:1500], "",
                f"*Verifica: `{c['file']}`, riga {c.get('riga')}, id {c['id']}.*", ""]
    f = d / f"errori_comuni_{dt.datetime.now():%Y%m%d_%H%M}.md"
    f.write_bytes("\n".join(out).encode("utf-8"))
    print("\n".join(out[:6]))
    print(f"Scritto: {f}")


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
    m.add_argument("--profili", default="", help="profili di modello di models.ini da provare, separati da ';' "
                                                 "(qualsiasi servizio: Ollama, Groq, Anthropic, FreeLLMAPI)")
    m.add_argument("--config-attuale", action="store_true", help="prova anche i modelli di config.ini")
    r = sub.add_parser("modelli", help="prova rapida di molti modelli (lotti misti, in parallelo, a due fasi)")
    r.add_argument("nome")
    r.add_argument("--modelli", default="tutti", help="«tutti» (i modelli attivi in FreeLLMAPI) o nomi separati da ';'")
    r.add_argument("--escludi", default="", help="parti di nome da escludere, separate da ';'")
    r.add_argument("--solo-elenco", action="store_true", help="mostra i modelli scelti e quelli scartati ed esce")
    r.add_argument("--prima-fase", type=int, default=30, help="passaggi della prima fase (metà non pertinenti)")
    r.add_argument("--migliori", type=int, default=6, help="modelli che passano alla seconda fase")
    r.add_argument("--lotto", type=int, default=10, help="passaggi per richiesta")
    r.add_argument("--paralleli", type=int, default=8, help="modelli provati contemporaneamente")
    r.add_argument("--contesto-min", type=int, default=16000, help="contesto minimo dei modelli (token)")
    r.add_argument("--seme", type=int, default=2026)
    r.add_argument("--riprendi", default="", help="cartella di una prova rapida (in results/trials): rifà solo la "
                                                  "seconda fase, partendo dalla prima già fatta")
    e = sub.add_parser("errori", help="passaggi sbagliati da tutti (o dalla maggioranza) dei modelli di una prova")
    e.add_argument("nome")
    e.add_argument("--prova", default="", help="cartella della prova rapida (predefinita: l'ultima con le decisioni)")
    for p in (a, b, c, m, r, e):
        p.add_argument("--config", default=None)
    args = ap.parse_args()
    from llm import leggi_config
    cfg = leggi_config(args.config)
    {"campione": campione, "candidati": candidati, "importa": importa, "misura": misura,
     "modelli": prova_rapida, "errori": errori_comuni}[args.comando](args, cfg)


if __name__ == "__main__":
    main()

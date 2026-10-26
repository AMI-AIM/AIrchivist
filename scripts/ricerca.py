#!/usr/bin/env python3
"""
Motore della ricerca: estrazione esaustiva -> smistamento e analisi con il modello -> risposta finale
(risposta.md). Di norma lo avvia il server MCP (strumento ricerca, azione avvia, dalla chat); a mano serve
solo per prove e manutenzione.

Uso:
  python ricerca.py "Nuova Unità"                     (l'entità deve avere una scheda in entities.ini)
  python ricerca.py "Nuova Unità" --domanda "Come compare Nuova Unità nel Renmin Ribao?"
  python ricerca.py "Nuova Unità" --solo-estrazione   (nessun modello: solo passaggi.csv)
  python ricerca.py "Nuova Unità" --rifai             (rilegge tutto con il modello, ignorando l'archivio unico)
  python ricerca.py "Jacques Grippa" --evoluzione     (evoluzione nel tempo, con le entità del campo "collegate")
  python ricerca.py "Osvaldo Pesce" --collegate "Angiolo Gracci"   (evoluzione con entità collegate scelte qui)
  python ricerca.py "Nuova Unità" --dal 1973 --al 1976 --fonti "Renmin Ribao"   (solo un periodo e alcune fonti)
  python ricerca.py "Nuova Unità" --rileggi-modello gpt-oss-20b   (rilegge con il modello attuale i passaggi letti
                                                                    da un modello che si è rivelato inaffidabile)

Profili di modello: una ricerca usa quelli scelti al suo avvio (registrati in modelli.json della sua cartella).
Se si interrompe (quote, rete) e la si rilancia, riprende con gli stessi profili anche se nel frattempo la scelta è
cambiata; --usa-modello-attuale la fa proseguire con quelli scelti adesso.

Se l'entità non esiste, viene aggiunta a entities.ini una scheda da completare con le varianti del nome.
"""
import argparse
import configparser
import re
import subprocess
import sys
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
try:                                   # messaggi a schermo nell'ordine giusto anche con i sottoprocessi
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass
sys.path.insert(0, str(CARTELLA))
from llm import leggi_config, percorso

MODELLO_SCHEDA = """
[{nome}]
varianti = {nome}
contesto =
note = SCHEDA DA COMPLETARE: aggiungi in "varianti" tutte le forme del nome separate da ";" (caratteri cinesi semplificati e tradizionali, pinyin, Wade-Giles, grafia originale, sigle, titoli con e senza 《》). In "contesto" parole che rendono probabile il riferimento giusto. Qui descrivi l'entità e le omonimie da escludere.
"""


def senza_accenti(s):
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def slug(nome):
    s = re.sub(r"[^\w一-鿿]+", "_", senza_accenti(nome.strip().lower())).strip("_")
    return s or "ricerca"


def riduci_passaggi(cart, nomi, finestra, fino_a=None):
    """Segna i passaggi delle entità collegate già contenuti in un passaggio di un'entità con priorità
    più alta (stesso file, testo sovrapposto): non vengono rimandati al modello ma restano nella cronologia.
    Esclude inoltre i passaggi delle entità collegate successivi a 'fino_a'."""
    import json
    f = cart / "passaggi.jsonl"
    P = [json.loads(r) for r in f.read_text(encoding="utf-8").splitlines() if r.strip()]
    priorita = {n: i for i, n in enumerate(nomi)}
    P.sort(key=lambda p: (priorita.get(p["entita"], 99), p["file"], p["offset"]))
    tenuti, per_file, assorbiti, esclusi = [], {}, 0, 0
    for p in P:
        p.pop("assorbito_da", None)
        anno = int(p["data"][:4]) if p.get("data", "")[:4].isdigit() else None
        if p["entita"] != nomi[0] and fino_a and anno and anno > fino_a and anno < 2000:
            esclusi += 1
            continue
        for q in per_file.get(p["file"], []):
            # solo i passaggi dell'entità principale "assorbono": tra entità collegate decide il modello
            if q["entita"] == nomi[0] != p["entita"] and abs(q["offset"] - p["offset"]) < 2 * finestra:
                p["assorbito_da"] = q["id"]
                assorbiti += 1
                break
        else:
            per_file.setdefault(p["file"], []).append(p)
        tenuti.append(p)
    f.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in tenuti), encoding="utf-8")
    print(f"Passaggi: {len(tenuti)} da considerare, di cui {assorbiti} già contenuti in altri passaggi "
          f"(non rimandati al modello)" + (f"; {esclusi} delle entità collegate dopo il {fino_a} esclusi" if esclusi else ""))


def fonte_ammessa(p, fonti):
    """Vero se il passaggio appartiene a una delle fonti richieste: per nome della serie o per gruppo di profili
    (profili.py: «Hongqi» = Hongqi + Red Flag, «documenti» = le raccolte di documenti)."""
    import profili
    gruppi = set().union(*(profili.serie_del_gruppo(x) for x in fonti))
    return p.get("fonte") in gruppi or profili.nome_di(p.get("fonte", ""), p.get("file", "")) in gruppi


def filtra_passaggi(cart, dal=None, al=None, fonti=None):
    """Tiene solo i passaggi del periodo e delle fonti richieste. Il periodo vale per l'anno del documento: nelle
    raccolte la data interna, non l'anno di edizione (date_interne.anno_del_documento). I documenti senza anno
    noto restano, salvo che non siano esclusi dal filtro sulle fonti."""
    import json
    from date_interne import anno_del_documento
    f = cart / "passaggi.jsonl"
    P = [json.loads(r) for r in f.read_text(encoding="utf-8").splitlines() if r.strip()]
    ammesse = [x.strip() for x in fonti or [] if x.strip()]
    tenuti = []
    for p in P:
        if ammesse and not fonte_ammessa(p, ammesse):
            continue
        anno, _ = anno_del_documento(p)
        if anno and ((dal and anno < dal) or (al and anno > al)):
            continue
        tenuti.append(p)
    f.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in tenuti), encoding="utf-8")
    descr = ", ".join(x for x in (f"dal {dal}" if dal else "", f"al {al}" if al else "",
                                  f"fonti: {'; '.join(sorted(ammesse))}" if ammesse else "") if x)
    print(f"Filtro ({descr}): {len(tenuti)} passaggi su {len(P)}")


FILE_MODELLI = "modelli.json"
MARCATORE_SINTESI = "<!-- sintesi: non generata -->"


def fissa_profili(cart, cfg, usa_attuale=False):
    """Profili di modello della ricerca, in <cartella>/modelli.json, indicati ai sottoprocessi con
    AIRCHIVIST_PROFILI_RICERCA. Una ricerca interrotta (stato «in corso») riprende con i profili con cui era
    partita; una ricerca nuova, o con usa_attuale, usa quelli scelti adesso. Restituisce {ruolo: nome}."""
    import datetime as dt
    import json
    import os
    from llm import RUOLI, VARIABILE_FISSATI, ErroreModello, profilo
    os.environ.pop(VARIABILE_FISSATI, None)
    f = cart / FILE_MODELLI
    try:
        prec = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    except ValueError:
        prec = None
    try:
        attuali = {r: profilo(cfg, r) for r in RUOLI}
    except ErroreModello as e:
        attuali = None
        print(f"ATTENZIONE: profili di modello non validi ({e}).")
    if prec and prec.get("stato") == "in corso" and prec.get("ruoli") and not usa_attuale:
        ruoli = {r: v["nome"] for r, v in prec["ruoli"].items()}
        print(f"Ricerca ripresa con i profili con cui era partita il {prec.get('inizio', '?')}: "
              + ", ".join(f"{r} {n}" for r, n in ruoli.items()) + ".")
        if attuali and any(attuali[r][0] != ruoli.get(r) for r in RUOLI):
            print("  (la scelta attuale è diversa: per usarla in questa ricerca, --usa-modello-attuale)")
        os.environ[VARIABILE_FISSATI] = str(f)
        return ruoli
    if attuali is None:
        return {}
    dati = {"stato": "in corso", "inizio": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "ruoli": {r: {"nome": n, "voci": v} for r, (n, v) in attuali.items()}}
    f.write_text(json.dumps(dati, ensure_ascii=False, indent=1), encoding="utf-8")
    os.environ[VARIABILE_FISSATI] = str(f)
    return {r: n for r, (n, _) in attuali.items()}


def chiudi_profili(cart):
    """Ricerca finita con la risposta completa: la prossima userà i profili scelti in quel momento."""
    import json
    f, risposta = cart / FILE_MODELLI, cart / "risposta.md"
    if not f.exists() or not risposta.exists() or MARCATORE_SINTESI in risposta.read_text(encoding="utf-8"):
        return
    dati = json.loads(f.read_text(encoding="utf-8"))
    dati["stato"] = "completata"
    f.write_text(json.dumps(dati, ensure_ascii=False, indent=1), encoding="utf-8")


def esegui(*argomenti):
    r = subprocess.run([sys.executable, *map(str, argomenti)], cwd=CARTELLA)
    if r.returncode != 0:
        sys.exit(r.returncode)


def main():
    ap = argparse.ArgumentParser(description="Ricerca completa di un'entità nelle fonti")
    ap.add_argument("nome", help="nome della sezione in entities.ini")
    ap.add_argument("--domanda", default="")
    ap.add_argument("--solo-estrazione", action="store_true")
    ap.add_argument("--rifai", action="store_true")
    ap.add_argument("--accetta-incompleti", action="store_true",
                    help="scrive la risposta anche se alcuni passaggi non si riescono a leggere")
    ap.add_argument("--evoluzione", action="store_true",
                    help="analisi dell'evoluzione nel tempo, includendo le entità del campo 'collegate'")
    ap.add_argument("--soglia-mesi", default="6", help="mesi senza menzioni che contano come silenzio")
    ap.add_argument("--collegate-fino-a", type=int, default=None,
                    help="analizza le entità collegate solo fino a quest'anno (l'entità principale sempre per intero)")
    ap.add_argument("--collegate", default=None,
                    help="entità collegate separate da ';' (sostituisce il campo 'collegate'; implica --evoluzione)")
    ap.add_argument("--dal", type=int, default=None, help="solo i documenti da quest'anno")
    ap.add_argument("--al", type=int, default=None, help="solo i documenti fino a quest'anno")
    ap.add_argument("--fonti", default=None, help="solo queste fonti, separate da ';' (es. \"Renmin Ribao; Peking Review\")")
    ap.add_argument("--usa-modello-attuale", action="store_true",
                    help="una ricerca interrotta prosegue con i profili di modello scelti adesso, non con quelli "
                         "con cui era partita")
    ap.add_argument("--rileggi-modello", default=None, metavar="NOME",
                    help="rimanda al modello attuale i passaggi letti da un modello il cui nome contiene NOME "
                         "(la lettura nuova sostituisce la vecchia nell'archivio)")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    if args.collegate:
        args.evoluzione = True
    if args.rileggi_modello is not None and len(args.rileggi_modello.strip()) < 3:
        sys.exit("--rileggi-modello: indica almeno tre caratteri del nome del modello.")

    cfg = leggi_config(args.config)
    f_entita = percorso(cfg, "entita")
    cp = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    cp.optionxform = str
    cp.read(f_entita, encoding="utf-8")
    if args.nome not in cp.sections():
        simili = [s for s in cp.sections() if args.nome.lower() in s.lower() or s.lower() in args.nome.lower()]
        if simili:
            sys.exit(f"Entità '{args.nome}' non trovata. Forse intendevi: {', '.join(simili)}")
        with open(f_entita, "a", encoding="utf-8") as f:
            f.write(MODELLO_SCHEDA.format(nome=args.nome))
        sys.exit(f"Ho aggiunto una scheda vuota per '{args.nome}' in {f_entita}.\n"
                 "Completa le varianti del nome e rilancia lo stesso comando.")

    nomi = [args.nome]
    if args.evoluzione:
        campo = args.collegate if args.collegate is not None else cp.get(args.nome, "collegate", fallback="")
        collegate = [c.strip() for c in campo.replace("；", ";").split(";") if c.strip() and c.strip() != args.nome]
        mancanti = [c for c in collegate if c not in cp.sections()]
        if mancanti:
            sys.exit(f"Entità collegate senza scheda in entities.ini: {', '.join(mancanti)}")
        if not collegate:
            print(f"Nota: la scheda [{args.nome}] non ha entità collegate (campo 'collegate'): analizzo solo lei.")
        nomi += collegate
    from progetto import cartella_ricerche
    cart = cartella_ricerche(cfg) / (slug(args.nome) + ("_evoluzione" if args.evoluzione else ""))
    cart.mkdir(parents=True, exist_ok=True)
    ini = cart / "entita_ricerca.ini"
    singola = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    singola.optionxform = str
    for n in nomi:
        singola[n] = dict(cp[n])
    with open(ini, "w", encoding="utf-8") as f:
        singola.write(f)

    finestra = cfg.get("estrazione", "finestra", fallback="400")
    print("== 1/3 Estrazione")
    from indice import percorso_indice
    con_indice = ["--indice", percorso_indice(cfg)] if percorso_indice(cfg).exists() else []
    periodo = (["--dal", args.dal] if args.dal else []) + (["--al", args.al] if args.al else [])
    esegui("estrai_occorrenze.py", percorso(cfg, "dati"), ini, "--out", cart, "--finestra", finestra,
           *con_indice, *periodo)
    if args.solo_estrazione:
        print(f"Passaggi in {cart / 'passaggi.csv'}")
        return
    if args.dal or args.al or args.fonti:
        filtra_passaggi(cart, args.dal, args.al, [x for x in (args.fonti or "").split(";") if x.strip()])
    if args.evoluzione and len(nomi) > 1:
        riduci_passaggi(cart, nomi, int(finestra), args.collegate_fino_a)
    if args.rifai and (cart / "classificati.jsonl").exists():
        (cart / "classificati.jsonl").unlink()
    extra = ["--config", args.config] if args.config else []
    fissa_profili(cart, cfg, args.usa_modello_attuale or args.rifai or bool(args.rileggi_modello))
    print("== 2/3 Smistamento e analisi dei passaggi")
    esegui("classifica.py", cart, ini, *extra, *(["--senza-archivio"] if args.rifai else []),
           *(["--accetta-incompleti"] if args.accetta_incompleti else []),
           *(["--rileggi-modello", args.rileggi_modello] if args.rileggi_modello else []))
    print("== 3/3 Risposta finale")
    dom = ["--domanda", args.domanda] if args.domanda else []
    if args.evoluzione:
        fino = ["--collegate-fino-a", str(args.collegate_fino_a)] if args.collegate_fino_a else []
        fino += ["--al", str(args.al)] if args.al else []
        esegui("evoluzione.py", cart, ini, "--principale", args.nome, "--soglia-mesi", args.soglia_mesi,
               *fino, *dom, *extra)
    else:
        esegui("sintesi.py", cart, ini, *dom, *extra)
    chiudi_profili(cart)
    print(f"\nFatto. Apri {cart / 'risposta.md'}")


if __name__ == "__main__":
    main()

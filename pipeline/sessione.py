#!/usr/bin/env python3
"""
Ricerca con lettura in sessione: i passaggi li legge l'assistente della chat (per esempio Claude con la skill
ricerca-fonti), non un modello chiamato via API. Il motore fa il resto come in ricerca.py: estrazione
esaustiva, archivio unico, citazioni testuali scelte da Python e verificate, sezioni deterministiche della
risposta. Le letture dichiarano la provenienza «sessione assistita» con il nome dell'assistente (--da).

Uso:
  python sessione.py prepara "Enrico Berlinguer" [--cartella prova_berlinguer] [--dal 1965] [--al 1980]
                     [--fonti "Renmin Ribao; Peking Review"] [--lotto 10] [--senza-archivio]
      estrae i passaggi, riprende dall'archivio quelli già letti e scrive in <cartella>/lotti/ quelli da leggere
  python sessione.py registra <cartella> <letture.json> [--da "claude-opus-5-5"]
      registra le letture di uno o più lotti (classificati.jsonl e archivio unico)
  python sessione.py stato <cartella>
  python sessione.py documenti <cartella>
      elenco numerato dei documenti pertinenti, da cui scrivere sintesi_sessione.json; poi:
  python sintesi.py <cartella> <cartella>/entita_ricerca.ini --domanda "..." --sintesi-da <cartella>/sintesi_sessione.json

<cartella> è il nome di una cartella dentro risultati (o un percorso). Le cartelle il cui nome inizia con
«prova» non leggono e non scrivono l'archivio unico.

Formato di letture.json: elenco di oggetti, uno per passaggio del lotto:
  {"id": "...", "pertinente": "sì" | "no" | "incerto", "motivazione": "una frase",
   "tipo_menzione": "...", "traduzione_it": "...", "sintesi_it": "...", "nuove_varianti": [],
   "altri_nominati": [{"nome": "...", "ruolo": "..."}], "ruolo_entita": "", "tono": "...", "evento": ""}
Per i passaggi esclusi bastano id, pertinente e motivazione.
"""
import argparse
import configparser
import json
import sys
from collections import Counter
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARTELLA))
from archivio import append_jsonl, apri, escluso, livello
from classifica import (TIPI, TONI, REGOLA_ANNO, carica_jsonl, da_archivio, da_completare, e_sommario,
                        forma_sicura, frase_chiave, normalizza, pagina, riga_json, ritaglia, scrivi_csv,
                        scrivi_rapporto, verifica)
from estrai_occorrenze import carica_entita, is_cjk
from glossario import blocco, carica_glossario
from llm import leggi_config, percorso

DA_PREDEFINITO = "assistente della chat"


def cartella(cfg, nome):
    p = Path(nome)
    return p if p.is_absolute() or p.exists() else percorso(cfg, "risultati") / nome


def stima_token(testo):
    """Token approssimativi: un carattere cinese ≈ 1 token, il resto ≈ 4 caratteri per token."""
    cjk = sum(1 for c in testo if is_cjk(c))
    return int(cjk + (len(testo) - cjk) / 4)


def in_italiano(p):
    """Passaggio di una serie in italiano (profilo della serie): la frase citata non va tradotta."""
    import profili
    return profili.di(p.get("fonte", ""), p.get("file", "")).get("lingua", "").strip().lower() == "it"


def letti(cart):
    """{id: lettura} di classificati.jsonl: vale l'ultima riga."""
    return {c["id"]: c for c in carica_jsonl(cart / "classificati.jsonl")}


def da_leggere(cart):
    fatti = letti(cart)
    return [p for p in carica_jsonl(cart / "passaggi.jsonl")
            if p["id"] not in fatti and not p.get("assorbito_da")]


def ambigue(ini):
    cp = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    cp.optionxform = str
    cp.read(ini, encoding="utf-8")
    return {s: {normalizza(x) for x in cp.get(s, "forme_ambigue", fallback="").replace("；", ";").split(";")
                if x.strip()} for s in cp.sections()}


def scrivi_lotti(cart, cfg, dimensione):
    """Un file Markdown per lotto, con tutto ciò che serve per leggere i passaggi senza aprire altri file."""
    ini = cart / "entita_ricerca.ini"
    schede = carica_entita(ini)
    amb = ambigue(ini)
    glossario = carica_glossario(percorso(cfg, "entita"))
    n = cfg.getint("estrazione", "finestra_modello", fallback=0)
    resto = da_leggere(cart)
    d = cart / "lotti"
    d.mkdir(exist_ok=True)
    for vecchio in d.glob("lotto_*.md"):
        vecchio.unlink()
    totale = 0
    for k in range(0, len(resto), dimensione):
        gruppo = resto[k:k + dimensione]
        s = schede[gruppo[0]["entita"]]
        testi = [ritaglia(p, 2 * n if n else 0) for p in gruppo]
        out = [f"# Lotto {k // dimensione + 1} di {-(-len(resto) // dimensione)}", "",
               f"Entità cercata: {gruppo[0]['entita']}",
               f"Forme del nome: {'; '.join(s['varianti'])}",
               f"Note della scheda: {s['note'] or '-'}", ""]
        gl = blocco(glossario, " ".join(testi))
        if gl:
            out += [gl.strip(), ""]
        for p, testo in zip(gruppo, testi):
            regole = []
            if e_sommario(p):
                regole.append("voce di sommario o di elenco: decidi solo la pertinenza, non serve tradurre")
            elif in_italiano(p):
                regole.append("testo in italiano: non serve tradurre (traduzione_it vuota)")
            sicure = [v for v in p.get("varianti_trovate") or []
                      if forma_sicura(v) and normalizza(v) not in amb.get(p["entita"], set())]
            if sicure:
                regole.append(f"forma inequivocabile del nome ({sicure[0]}): probabilmente pertinente")
            pag = pagina(p)
            out += [f"## {p['id']}", "",
                    f"Fonte: {p.get('citazione') or p['fonte']} (data: {p.get('data') or 's.d.'}"
                    + (f"; pagina {pag}" if pag else "") + ")",
                    f"Forme trovate: {'; '.join(p.get('varianti_trovate') or [])}"]
            out += [f"Nota: {r}" for r in regole]
            out += ["", "PASSAGGIO (occorrenze tra ⟦ ⟧):", testo, "", "FRASE DA TRADURRE:", frase_chiave(p), ""]
        f = d / f"lotto_{k // dimensione + 1:02d}.md"
        f.write_text("\n".join(out), encoding="utf-8")
        totale += stima_token(f.read_text(encoding="utf-8"))
    return resto, totale


def chiudi(cart):
    """classificati.csv e rapporto.md, con i passaggi contenuti in altri (stessa valutazione, come classifica.py)."""
    passaggi = carica_jsonl(cart / "passaggi.jsonl")
    fatti = letti(cart)
    for p in passaggi:
        madre = fatti.get(p.get("assorbito_da", ""))
        if madre and p["id"] not in fatti:
            fatti[p["id"]] = dict(p, analisi={"pertinente": madre["analisi"]["pertinente"],
                                              "motivazione": f"contenuto nel passaggio {madre['id']}",
                                              "assorbito_da": madre["id"], "citazione_verificata": False})
    ids = {p["id"] for p in passaggi}
    classificati = sorted((c for c in fatti.values() if c["id"] in ids),
                          key=lambda c: (c["entita"], c["data"], c["file"], c["riga"]))
    scrivi_csv(classificati, cart / "classificati.csv")
    scrivi_rapporto(classificati, cart / "rapporto.md")
    return classificati


# ---------------------------------------------------------------- comandi
def prepara(args, cfg):
    from ricerca import esegui, filtra_passaggi, slug
    from indice import percorso_indice
    f_entita = percorso(cfg, "entita")
    cp = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    cp.optionxform = str
    cp.read(f_entita, encoding="utf-8")
    if args.nome not in cp.sections():
        simili = [s for s in cp.sections() if args.nome.lower() in s.lower() or s.lower() in args.nome.lower()]
        sys.exit(f"Entità '{args.nome}' senza scheda in entita.ini."
                 + (f" Forse: {', '.join(simili)}." if simili else "")
                 + " Prima esplora_nome, conferma delle forme e schede crea (server MCP).")
    cart = cartella(cfg, args.cartella or slug(args.nome))
    cart.mkdir(parents=True, exist_ok=True)
    if args.senza_archivio:
        (cart / ".senza_archivio").touch()
    ini = cart / "entita_ricerca.ini"
    singola = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    singola.optionxform = str
    singola[args.nome] = dict(cp[args.nome])
    with open(ini, "w", encoding="utf-8") as f:
        singola.write(f)
    con_indice = ["--indice", percorso_indice(cfg)] if percorso_indice(cfg).exists() else []
    periodo = (["--dal", args.dal] if args.dal else []) + (["--al", args.al] if args.al else [])
    esegui("estrai_occorrenze.py", percorso(cfg, "dati"), ini, "--out", cart,
           "--finestra", cfg.get("estrazione", "finestra", fallback="400"), *con_indice, *periodo)
    if args.dal or args.al or args.fonti:
        filtra_passaggi(cart, args.dal, args.al, [x for x in (args.fonti or "").split(";") if x.strip()])

    # passaggi già letti in altre ricerche: dall'archivio, come in classifica.py
    dall_archivio = 0
    if not escluso(cart):
        arch = apri(cfg)
        fatti = letti(cart)
        nuovi = []
        for p in carica_jsonl(cart / "passaggi.jsonl"):
            if p["id"] in fatti or p.get("assorbito_da"):
                continue
            a, come = arch.cerca(p)
            if a is None or da_completare(a):
                continue
            a = da_archivio(p, a)
            a["dall_archivio"] = come
            nuovi.append(riga_json(dict(p, analisi=a)))
        if nuovi:
            append_jsonl(cart / "classificati.jsonl", nuovi)
            dall_archivio = len(nuovi)
    resto, token = scrivi_lotti(cart, cfg, args.lotto)
    n_lotti = -(-len(resto) // args.lotto)
    print(f"Cartella: {cart}")
    print(f"Passaggi estratti: {len(carica_jsonl(cart / 'passaggi.jsonl'))}; dall'archivio: {dall_archivio}; "
          f"da leggere: {len(resto)} in {n_lotti} lotti ({cart / 'lotti'})")
    if resto:
        print(f"Testo dei lotti: circa {token // 1000} mila token" if token >= 1000 else
              f"Testo dei lotti: circa {token} token")
    else:
        print("Nessun passaggio da leggere: si può passare a «documenti» e alla sintesi.")
        chiudi(cart)


def registra(args, cfg):
    cart = cartella(cfg, args.cartella)
    voci = json.loads(Path(args.letture).read_text(encoding="utf-8"))
    if isinstance(voci, dict):
        voci = voci.get("letture") or [dict(v, id=k) for k, v in voci.items()]
    passaggi = {p["id"]: p for p in carica_jsonl(cart / "passaggi.jsonl")}
    schede = carica_entita(cart / "entita_ricerca.ini")
    arch = None if escluso(cart) else apri(cfg)
    chi = livello("sessione", args.da)
    righe, problemi = [], []
    for v in voci:
        p = passaggi.get(v.get("id"))
        if p is None:
            problemi.append(f"id sconosciuto: {v.get('id')}")
            continue
        pert = v.get("pertinente")
        if pert not in ("sì", "no", "incerto"):
            problemi.append(f"{p['id']}: pertinente deve essere sì, no o incerto (non {pert!r})")
            continue
        a = {"pertinente": pert, "motivazione": (v.get("motivazione") or "").strip(),
             "tipo_menzione": "", "citazione_testuale": "", "traduzione_it": "", "sintesi_it": "",
             "nuove_varianti": [], "pagina": pagina(p), "classificato_da": "lettura in sessione"}
        if pert != "no" and e_sommario(p):
            a.update({"tipo_menzione": "elenco", "citazione_testuale": frase_chiave(p),
                      "traduzione_it": "(voce di sommario o di elenco: non tradotta)",
                      "sintesi_it": "Il nome compare in un sommario o in un elenco di titoli del numero.",
                      "modello_analisi": "nessuno (voce di sommario)", "sommario": True})
            let = livello("regola", "voce di sommario o di elenco, non tradotta")
        elif pert != "no":
            if not (v.get("traduzione_it") or "").strip() and not in_italiano(p):
                problemi.append(f"{p['id']}: manca traduzione_it")
                continue
            tipo = v.get("tipo_menzione") if v.get("tipo_menzione") in TIPI else "altro"
            tono = v.get("tono") if v.get("tono") in TONI else "non determinabile"
            a.update({"tipo_menzione": tipo, "citazione_testuale": frase_chiave(p),
                      "traduzione_it": (v.get("traduzione_it") or "").strip(),
                      "sintesi_it": (v.get("sintesi_it") or "").strip(),
                      "nuove_varianti": [x for x in v.get("nuove_varianti") or []
                                         if isinstance(x, str) and x and x not in schede[p["entita"]]["varianti"]],
                      "altri_nominati": [x for x in v.get("altri_nominati") or [] if isinstance(x, dict) and x.get("nome")],
                      "ruolo_entita": (v.get("ruolo_entita") or "").strip(), "tono": tono,
                      "evento": (v.get("evento") or "").strip()})
            let = chi
        else:
            let = None
        a["citazione_verificata"] = verifica(p, a) if pert != "no" else False
        a["provenienza"] = {"decisione": chi, "lettura": let}
        righe.append(riga_json(dict(p, analisi=a)))
        if arch is not None:
            arch.aggiungi(p, a, origine=cart.name)
    if righe:
        append_jsonl(cart / "classificati.jsonl", righe)
    classificati = chiudi(cart)
    n = Counter(c["analisi"]["pertinente"] for c in classificati)
    print(f"Registrate: {len(righe)}" + (" (anche nell'archivio unico)" if arch is not None and righe else ""))
    for x in problemi:
        print("  NON REGISTRATA:", x)
    print(f"Classificati: {len(classificati)} | pertinenti {n.get('sì', 0)} | incerti {n.get('incerto', 0)} "
          f"| esclusi {n.get('no', 0)} | ancora da leggere: {len(da_leggere(cart))}")
    nuove = sorted({x for c in classificati for x in c["analisi"].get("nuove_varianti") or []})
    if nuove:
        print("Forme nuove proposte (da confermare prima di aggiungerle alla scheda):", "; ".join(nuove))
    if problemi:
        sys.exit(1)


def stato(args, cfg):
    cart = cartella(cfg, args.cartella)
    classificati = chiudi(cart)
    n = Counter(c["analisi"]["pertinente"] for c in classificati)
    resto = da_leggere(cart)
    print(f"Cartella: {cart}{' (fuori dall archivio unico)' if escluso(cart) else ''}")
    print(f"Passaggi: {len(carica_jsonl(cart / 'passaggi.jsonl'))} | letti {len(classificati)} "
          f"(pertinenti {n.get('sì', 0)}, incerti {n.get('incerto', 0)}, esclusi {n.get('no', 0)}) "
          f"| da leggere {len(resto)}")
    if resto:
        print("Da leggere:", ", ".join(p["id"] for p in resto[:20]) + (" ..." if len(resto) > 20 else ""))


def documenti(args, cfg):
    import sintesi
    cart = cartella(cfg, args.cartella)
    if da_leggere(cart):
        sys.exit(f"Restano {len(da_leggere(cart))} passaggi da leggere: prima registra tutti i lotti.")
    sintesi.DATI = percorso(cfg, "dati")
    correnti = {p["id"] for p in carica_jsonl(cart / "passaggi.jsonl")}
    pertinenti = [c for c in letti(cart).values() if c["id"] in correnti and c["analisi"]["pertinente"] == "sì"]
    docs = sintesi.raggruppa(pertinenti)
    righe = sintesi.elenco_per_modello(docs)
    gl = blocco(carica_glossario(percorso(cfg, "entita")), " ".join(c["passaggio"] for c in pertinenti))
    print(f"{gl}Entità: {pertinenti[0]['entita'] if pertinenti else '-'}  |  documenti pertinenti: {len(docs)}\n")
    print("\n".join(righe))
    print(f"\nRegola delle date: {REGOLA_ANNO}")
    print(f"\nScrivi {cart / 'sintesi_sessione.json'} con dati_espliciti, inferenze, problemi_interpretativi, "
          "risposta_finale (ogni voce con i numeri dei documenti in «rif»), poi lancia sintesi.py --sintesi-da.")


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    ap = argparse.ArgumentParser(description="Ricerca con lettura dei passaggi in sessione")
    sub = ap.add_subparsers(dest="comando", required=True)
    a = sub.add_parser("prepara")
    a.add_argument("nome")
    a.add_argument("--cartella", default=None)
    a.add_argument("--dal", type=int, default=None)
    a.add_argument("--al", type=int, default=None)
    a.add_argument("--fonti", default=None)
    a.add_argument("--lotto", type=int, default=10)
    a.add_argument("--senza-archivio", action="store_true",
                   help="la cartella non legge né scrive l'archivio unico (file .senza_archivio)")
    a = sub.add_parser("registra")
    a.add_argument("cartella")
    a.add_argument("letture")
    a.add_argument("--da", default=DA_PREDEFINITO, help="chi ha letto (es. il nome del modello della chat)")
    for nome in ("stato", "documenti"):
        sub.add_parser(nome).add_argument("cartella")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    cfg = leggi_config(args.config)
    {"prepara": prepara, "registra": registra, "stato": stato, "documenti": documenti}[args.comando](args, cfg)


if __name__ == "__main__":
    main()

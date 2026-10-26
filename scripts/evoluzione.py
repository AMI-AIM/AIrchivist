#!/usr/bin/env python3
"""
Risposta sull'EVOLUZIONE di un'entità nel tempo (persona, partito, testata), usando anche le entità
collegate indicate in entities.ini (campo "collegate").

Struttura della risposta (risposta.md):
 1. Documenti rilevanti  2. Passaggi rilevanti
 3. Cronologia e dati espliciti: tabella per anno, silenzi e discontinuità (Python), dati per anno (modello)
 4. Inferenze: fasi dell'evoluzione e deduzioni (modello, con rimandi)
 5. Limiti e problemi interpretativi  6. Grado di copertura  7. Risposta finale

Uso:
  python evoluzione.py <cartella_risultati> <entita_ricerca.ini> --principale "Jacques Grippa"
                       [--domanda "..."] [--soglia-mesi 6] [--senza-modello] [--config config.ini]
"""
import argparse
import datetime as dt
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classifica import carica_jsonl
import cronologia as _cronologia
from cronologia import calcola, data_di, fatti, tabella
from estrai_occorrenze import carica_entita
from glossario import blocco, carica_glossario
from sintesi import (SISTEMA, avviso_non_letti, avviso_sintesi, elenco_modelli, filtra_rif, nota_data, raggruppa,
                     sez_copertura, sez_documenti, sez_limiti, sez_passaggi, sez_tecnica)

SCHEMA_ANNO = {
    "type": "object",
    "properties": {
        "dati": {"type": "array", "items": {
            "type": "object",
            "properties": {"testo": {"type": "string"}, "rif": {"type": "array", "items": {"type": "integer"}}},
            "required": ["testo", "rif"]}},
        "sintesi": {"type": "string"},
    },
    "required": ["dati", "sintesi"],
}

SCHEMA_EVOLUZIONE = {
    "type": "object",
    "properties": {
        "fasi": {"type": "array", "items": {
            "type": "object",
            "properties": {"periodo": {"type": "string"}, "testo": {"type": "string"},
                           "rif": {"type": "array", "items": {"type": "integer"}}},
            "required": ["periodo", "testo", "rif"]}},
        "inferenze": {"type": "array", "items": {
            "type": "object",
            "properties": {"testo": {"type": "string"},
                           "rif": {"type": "array", "items": {"type": "integer"}},
                           "fondatezza": {"type": "string", "enum": ["alta", "media", "bassa"]}},
            "required": ["testo", "rif", "fondatezza"]}},
        "problemi_interpretativi": {"type": "array", "items": {
            "type": "object",
            "properties": {"testo": {"type": "string"}, "rif": {"type": "array", "items": {"type": "integer"}}},
            "required": ["testo", "rif"]}},
        "risposta_finale": {"type": "string"},
    },
    "required": ["fasi", "inferenze", "problemi_interpretativi", "risposta_finale"],
}


def riga_doc(d, c):
    a = c["analisi"]
    parti = [f"[{d['n']}] {d['rif']}{nota_data(d)} | entità: {c['entita']}"]
    if a.get("ruolo_entita"):
        parti.append(f"ruolo: {a['ruolo_entita']}")
    if a.get("tono"):
        parti.append(f"tono: {a['tono']}")
    if a.get("evento"):
        parti.append(f"evento: {a['evento']}")
    parti.append(f"{a.get('sintesi_it', '')} (frase: «{a.get('traduzione_it', '')}»)")
    altri = "; ".join(f"{x['nome']} ({x.get('ruolo', '')})" for x in (a.get("altri_nominati") or [])[:8])
    if altri:
        parti.append(f"nominati nello stesso passaggio: {altri}")
    return " | ".join(parti)


def per_anno(docs):
    anni = defaultdict(list)
    for d in docs:
        for c in d["voci"]:
            if not c["analisi"].get("citazione_verificata"):
                continue
            anno = data_di(c)[1]                  # periodici: anno del numero; raccolte: della data interna
            anni[anno or "raccolte, data del documento non deducibile"].append(riga_doc(d, c))
    return anni


def scrivi_con_modello(llm, principale, domanda, docs, cr_fatti, glossario, dimensione=25):
    validi = {d["n"] for d in docs}
    testi = " ".join(c["passaggio"] for d in docs for c in d["voci"])
    gl = blocco(glossario or [], testi)
    dati_anno, sintesi_anno, scartati = {}, {}, 0
    anni = per_anno(docs)
    for anno in sorted(anni, key=lambda x: (isinstance(x, str), x)):
        righe = anni[anno]
        dati, sintesi = [], []
        for i in range(0, len(righe), dimensione):
            parte = "\n".join(righe[i:i + dimensione])
            print(f"  anno {anno}: documenti {i + 1}-{min(i + dimensione, len(righe))} di {len(righe)}")
            r = llm.json(SISTEMA, f"""{gl}Entità principale: {principale}
Periodo: {anno}

Documenti (numero, riferimento, entità, ruolo attribuito, tono, evento, contenuto):
{parte}

1. "dati": i fatti che questi documenti attestano su {principale} e sulle entità collegate (eventi, cariche,
   prese di posizione, rapporti con il PCC e con altri partiti), in ordine cronologico, con l'anno e con i
   numeri dei documenti. Usa i nomi del GLOSSARIO. Nessuna deduzione.
2. "sintesi": 2-4 frasi su come le fonti presentano {principale} in questo periodo (ruolo, tono, temi), con
   i numeri dei documenti tra parentesi quadre.
JSON.""", SCHEMA_ANNO)
            tenuti, s = filtra_rif(r.get("dati", []), validi)
            dati += tenuti
            scartati += s
            if r.get("sintesi"):
                sintesi.append(r["sintesi"].strip())
        dati_anno[anno], sintesi_anno[anno] = dati, " ".join(sintesi)

    riassunti = "\n".join(f"- {a}: {t}" for a, t in sintesi_anno.items() if t)
    r = llm.json(SISTEMA, f"""{gl}Entità principale: {principale}
Domanda del ricercatore: {domanda or f"Qual è stata l'evoluzione politica di {principale} secondo queste fonti?"}

CRONOLOGIA CALCOLATA SUI DOCUMENTI (dati certi):
{chr(10).join('- ' + f for f in cr_fatti)}

COME LE FONTI PRESENTANO L'ENTITÀ, ANNO PER ANNO (con i numeri dei documenti):
{riassunti}

1. "fasi": dividi la traiettoria in fasi (da 2 a 6), ciascuna con il periodo, una descrizione basata sui
   documenti e i numeri dei documenti. Tieni conto dei silenzi e della comparsa di nuove entità: un silenzio
   delle fonti è un dato, ma le sue cause non sono nei documenti e non vanno inventate.
2. "inferenze": deduzioni ragionevoli, ciascuna con documenti e fondatezza (alta/media/bassa).
3. "problemi_interpretativi": omonimie, organismi con lo stesso nome, contraddizioni, silenzi non spiegati,
   lacune delle fonti, con i numeri dei documenti.
4. "risposta_finale": risposta alla domanda in 2-4 paragrafi, con i numeri dei documenti tra parentesi quadre.
   Distingui ciò che i documenti attestano da ciò che resta da verificare su altre fonti.
JSON.""", SCHEMA_EVOLUZIONE)
    fasi, s1 = filtra_rif(r.get("fasi", []), validi)
    inferenze, s2 = filtra_rif(r.get("inferenze", []), validi)
    problemi, s3 = filtra_rif(r.get("problemi_interpretativi", []), validi)
    scartati += s1 + s2 + s3
    return dati_anno, fasi, inferenze, problemi, r.get("risposta_finale", "").strip(), scartati


def rif(v):
    return "".join(f"[{x}]" for x in v.get("rif", []))


def main():
    ap = argparse.ArgumentParser(description="Evoluzione di un'entità nel tempo")
    ap.add_argument("cartella")
    ap.add_argument("entita")
    ap.add_argument("--principale", required=True)
    ap.add_argument("--domanda", default="")
    ap.add_argument("--soglia-mesi", type=int, default=6)
    ap.add_argument("--collegate-fino-a", type=int, default=None)
    ap.add_argument("--al", type=int, default=None, help="fine del periodo richiesto")
    ap.add_argument("--senza-modello", action="store_true")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    from llm import leggi_config, percorso
    cfg = leggi_config(args.config)
    import sintesi as _sintesi
    _sintesi.DATI = _cronologia.DATI = percorso(cfg, "dati")
    cart = Path(args.cartella)
    # se un passaggio compare più volte (correzioni manuali aggiunte in fondo) vale l'ultima riga
    classificati = list({c["id"]: c for c in carica_jsonl(cart / "classificati.jsonl")}.values())
    # solo i passaggi della ricerca corrente (classificati.jsonl conserva anche quelli di ricerche precedenti)
    if (cart / "passaggi.jsonl").exists():
        correnti = {c["id"] for c in carica_jsonl(cart / "passaggi.jsonl")}
        classificati = [c for c in classificati if c["id"] in correnti]
    if not classificati:
        if (cart / "passaggi.jsonl").exists() and not carica_jsonl(cart / "passaggi.jsonl"):
            # nessuna occorrenza nel periodo o nelle fonti richieste: risposta esplicita, non un errore
            (cart / "risposta.md").write_text(
                "# Nessun documento\n\n" + (f"*Domanda:* {args.domanda}\n\n" if args.domanda else "")
                + "Nelle fonti, nel periodo e nelle serie richieste non ci sono occorrenze delle forme del nome "
                  "registrate in entities.ini. Se pensi che manchino, controlla le varianti della scheda o "
                  "allarga il periodo o le fonti.\n", encoding="utf-8")
            print("Nessuna occorrenza nel periodo o nelle fonti richieste: risposta vuota scritta.")
            return
        sys.exit("Nessun passaggio classificato: esegui prima classifica.py")
    schede = carica_entita(Path(args.entita))
    scheda_tutte = {"varianti": [v for s in schede.values() for v in s["varianti"]], "note": ""}

    pertinenti = [c for c in classificati if c["analisi"]["pertinente"] == "sì"]
    incerti = [c for c in classificati if c["analisi"]["pertinente"] == "incerto"]
    docs = raggruppa(pertinenti)
    cr = calcola(pertinenti, args.principale, args.soglia_mesi, percorso(cfg, "problemi"), args.collegate_fino_a,
                 fino_a=args.al)
    cr_fatti = fatti(cr)
    m_analisi = elenco_modelli(pertinenti, "modello_analisi") or "nessuno"

    dati_anno, fasi, inferenze, problemi_mod, finale, scartati, m_sintesi = {}, [], [], [], "", 0, ""
    errore_sintesi = ""
    if not args.senza_modello and docs:
        from llm import LLM, ErroreModello
        try:
            llm = LLM(cfg, "sintesi")
            llm.controlla()
            m_sintesi = llm.modello
            print(f"Ricostruzione dell'evoluzione con {llm.modello}...")
            dati_anno, fasi, inferenze, problemi_mod, finale, scartati = scrivi_con_modello(
                llm, args.principale, args.domanda, docs, cr_fatti, carica_glossario(percorso(cfg, "entita")))
        except ErroreModello as e:
            errore_sintesi = str(e)
        except Exception as e:                       # risposta del modello malformata o altro imprevisto
            errore_sintesi = f"{type(e).__name__}: {e}"
        else:
            if not finale:
                errore_sintesi = "il modello non ha restituito la risposta finale"
        if errore_sintesi:
            print(f"ATTENZIONE: sintesi non generata ({errore_sintesi}).\n"
                  "Genero solo le sezioni che non richiedono il modello.")

    out = [f"# {args.principale}: evoluzione nelle fonti", ""]
    out += avviso_sintesi(errore_sintesi)
    if args.domanda:
        out += [f"*Domanda:* {args.domanda}", ""]
    collegate = [e for e in schede if e != args.principale]
    out += [f"*Generato il {dt.date.today().isoformat()} — documenti pertinenti: {len(docs)}"
            + (f"; entità collegate: {', '.join(collegate)}" if collegate else "")
            + (f" (analizzate fino al {args.collegate_fino_a})" if collegate and args.collegate_fino_a else "")
            + ".*", ""]
    out += sez_documenti(docs)
    out += sez_passaggi(docs, m_analisi)

    out += ["## 3. Cronologia e dati espliciti", "", "### Presenza nelle fonti anno per anno", ""]
    out += tabella(cr) + [""]
    out += ["### Silenzi e discontinuità", "",
            f"Calcolati sulle date dei documenti (silenzio = almeno {args.soglia_mesi} mesi senza menzioni). "
            "Le fonti mostrano i silenzi ma non ne spiegano le cause.", ""]
    out += [f"- {f}" for f in cr_fatti] or ["- nessuno"]
    n_incerti = Counter(c["entita"] for c in incerti)
    for ent, n in n_incerti.most_common():
        out += [f"- Attenzione: {ent} ha {n} passaggi «incerti», esclusi da questo calcolo. I suoi silenzi possono "
                "dipendere dalla classificazione dei passaggi e non dalle fonti."]
    out += ["", "### Dati espliciti per anno", ""]
    if dati_anno:
        for anno, dati in dati_anno.items():
            if dati:
                out += [f"**{anno}**", ""] + [f"- {d['testo']} {rif(d)}" for d in dati] + [""]
    else:
        out += ["*(non generati: vedi la tabella e i passaggi)*", ""]

    out += ["## 4. Inferenze", "", "### Fasi dell'evoluzione (interpretazione basata sui documenti)", ""]
    out += [f"- **{f['periodo']}**: {f['testo']} {rif(f)}" for f in fasi] or ["*(non generate)*"]
    out += ["", "### Altre inferenze", ""]
    out += [f"- *Inferenza (fondatezza {i.get('fondatezza', '?')}):* {i['testo']} {rif(i)}" for i in inferenze] \
        or ["*(nessuna)*"]
    out += [""]
    out += sez_limiti(docs, incerti, scartati, percorso(cfg, "problemi"), m_analisi, problemi_mod, classificati,
                      percorso(cfg, "risultati"))
    out = avviso_non_letti(cart, out)
    modelli = ", ".join(x for x in (f"analisi {m_analisi}", f"sintesi {m_sintesi}" if m_sintesi else "") if x)
    out += sez_copertura(scheda_tutte, cart, classificati, modelli)
    out += ["## 7. Risposta finale", "", finale or ("*(non generata: vedi l'avviso in testa)*" if errore_sintesi else "*(non generata)*"), ""]
    out += sez_tecnica(docs, incerti)
    (cart / "risposta.md").write_text("\n".join(out), encoding="utf-8")
    print(f"Risposta: {(cart / 'risposta.md').resolve()}")


if __name__ == "__main__":
    main()

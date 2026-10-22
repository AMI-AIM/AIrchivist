#!/usr/bin/env python3
"""
FASE 3 - Risposta finale nel formato:
 1. Documenti rilevanti  2. Passaggi rilevanti  3. Dati espliciti  4. Inferenze
 5. Limiti e problemi interpretativi  6. Grado di copertura  7. Risposta finale
 8. Dati tecnici per la verifica (file e righe; non fanno parte delle citazioni)

Le sezioni 1, 2, 5, 6, 8 sono costruite da Python con i dati verificati (nessun modello). Le citazioni sono in
stile Chicago standard (citazioni.py, profili in serie.ini) e si fermano alla pagina, quando c'è; ogni passaggio
dichiara la provenienza della lettura (modello, sessione assistita, regola: archivio.py).
Le sezioni 3, 4, 7 sono scritte dal modello leggendo SOLO i passaggi pertinenti; ogni affermazione deve
rimandare a un documento [n]: quelle senza rimando valido vengono scartate.

Uso:
  python sintesi.py <cartella_risultati> <entita.ini> [--domanda "chi era ...?"] [--senza-modello] [--config config.ini]
Output: risposta.md nella cartella dei risultati.
"""
import argparse
import csv
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from classifica import carica_jsonl
from estrai_occorrenze import carica_entita
from glossario import blocco, carica_glossario

MESI_EN = "january february march april may june july august september october november december".split()
MESI_IT = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
           "settembre", "ottobre", "novembre", "dicembre"]

SISTEMA = ("Sei un assistente di ricerca storica. Usi esclusivamente le informazioni fornite, senza "
           "conoscenze esterne. Ogni affermazione rimanda ai documenti con il loro numero. "
           "Rispondi in italiano e solo con il JSON richiesto.")

SCHEMA_DATI = {
    "type": "object",
    "properties": {"dati_espliciti": {"type": "array", "items": {
        "type": "object",
        "properties": {"testo": {"type": "string"}, "rif": {"type": "array", "items": {"type": "integer"}}},
        "required": ["testo", "rif"]}}},
    "required": ["dati_espliciti"],
}

SCHEMA_FINALE = {
    "type": "object",
    "properties": {
        "inferenze": {"type": "array", "items": {
            "type": "object",
            "properties": {"testo": {"type": "string"},
                           "rif": {"type": "array", "items": {"type": "integer"}},
                           "fondatezza": {"type": "string", "enum": ["alta", "media", "bassa"]}},
            "required": ["testo", "rif", "fondatezza"]}},
        "problemi_interpretativi": {"type": "array", "items": {
            "type": "object",
            "properties": {"testo": {"type": "string"},
                           "rif": {"type": "array", "items": {"type": "integer"}}},
            "required": ["testo", "rif"]}},
        "risposta_finale": {"type": "string"},
    },
    "required": ["inferenze", "problemi_interpretativi", "risposta_finale"],
}


# ---------------------------------------------------------------- riferimenti
def data_it(iso):
    try:
        d = dt.date.fromisoformat(iso)
        return f"{d.day} {MESI_IT[d.month - 1]} {d.year}"
    except Exception:
        return iso


def riferimento(c, con_pagina=True):
    """Citazione in stile Chicago del passaggio (con la pagina, se nota) o del suo documento (con_pagina=False)."""
    from citazioni import per_passaggio
    if con_pagina:
        return per_passaggio(c, DATI)[0]
    return per_passaggio(dict(c, offset=0, analisi={}), DATI)[0]


def raggruppa(pertinenti):
    """Un numero [n] per documento (file), in ordine cronologico."""
    per_file = defaultdict(list)
    for c in pertinenti:
        per_file[c["file"]].append(c)
    docs = sorted(per_file.values(), key=lambda v: (v[0]["data"], v[0]["file"]))
    return [{"n": i, "voci": sorted(v, key=lambda c: c["riga"]), "rif": riferimento(v[0], con_pagina=False)}
            for i, v in enumerate(docs, 1)]


# ---------------------------------------------------------------- sezioni deterministiche
def sez_documenti(docs):
    righe = ["## 1. Documenti rilevanti", ""]
    for d in docs:
        tipi = ", ".join(sorted({c["analisi"].get("tipo_menzione", "") for c in d["voci"]} - {""}))
        righe.append(f"[{d['n']}] {d['rif']}{' — ' + tipi if tipi else ''}")
    return righe + [""]


def sez_tecnica(docs, incerti=()):
    """File e righe dei passaggi, per ritrovarli nelle fonti: non fanno parte delle citazioni."""
    from archivio import riga_citazione
    righe = ["## 8. Dati tecnici per la verifica", "",
             "File del corpus e righe dei passaggi citati, per controllarli nelle fonti. Non vanno riportati "
             "nelle citazioni.", ""]
    for d in docs:
        posti = []
        for c in d["voci"]:
            a = c["analisi"]
            if a.get("assorbito_da"):
                continue
            r = riga_citazione(DATI, c["file"], c["riga"], a.get("citazione_testuale", "")) \
                if a.get("citazione_verificata") else c["riga"]
            posti.append(str(r))
        posti = list(dict.fromkeys(posti))
        righe.append(f"- [{d['n']}] `{d['voci'][0]['file']}`, {'righe' if len(posti) > 1 else 'riga'} {', '.join(posti)}")
    if incerti:
        righe += ["", "Passaggi incerti:"] + [f"- {riferimento(c)}: `{c['file']}`, riga {c['riga']}" for c in incerti]
    return righe + [""]


def elenco_modelli(voci, campo):
    """'modello A (n passaggi); modello B (m passaggi)': solo i modelli, dalla provenienza delle letture
    (le letture in sessione e le decisioni per regola sono contate a parte, nella sezione 6)."""
    from archivio import provenienza
    parte = "decisione" if campo == "modello_smistamento" else "lettura"
    conta = Counter()
    for c in voci:
        if c["analisi"].get("assorbito_da"):
            continue
        p = provenienza(c["analisi"]).get(parte)
        if p and p.get("livello") == "modello" and p.get("da"):
            conta[p["da"]] += 1
    if len(conta) == 1:
        return next(iter(conta))
    return "; ".join(f"{m} ({n} passaggi)" for m, n in conta.most_common())


DATI = None          # cartella delle fonti, impostata in main(): serve a indicare la riga esatta delle citazioni


def sez_passaggi(docs, modello):
    righe = ["## 2. Passaggi rilevanti", "",
             "Testo originale citato esattamente dalla fonte; la traduzione va controllata sull'originale.", ""]
    for d in docs:
        righe += [f"### [{d['n']}] {d['rif']}", ""]
        for c in d["voci"]:
            a = c["analisi"]
            if a.get("assorbito_da"):
                continue
            if not a.get("citazione_verificata"):
                righe += ["*(un passaggio con citazione non verificata, omesso: vedi la sezione 8)*", ""]
                continue
            from archivio import descrivi_provenienza, provenienza
            righe += [f"> {a['citazione_testuale']}", "", f"— {riferimento(c)}", ""]
            if (a.get("traduzione_it") or "").strip():
                righe += [f"Traduzione: {a['traduzione_it']}", ""]
            if a.get("sintesi_it"):
                righe += [f"Nel passaggio: {a['sintesi_it']}", ""]
            righe += [f"*Lettura: {descrivi_provenienza(provenienza(a))}.*", ""]
    return righe


def _mese_problema(serie, nome):
    """(anno, mese) di una voce di problemi_residui.csv, se ricavabile."""
    m = re.search(r"(19\d\d)-(\d\d)-(\d\d)", nome)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.search(r"PR(19\d\d)-(\d+)", nome)
    if m:                                               # Peking Review: settimanale
        return int(m.group(1)), min(12, (int(m.group(2)) - 1) * 12 // 52 + 1)
    m = re.search(r"RF(19\d\d)-(\d+)", nome)
    if m:                                               # Hongqi/JPRS: quindicinale dal 1980, mensile prima
        a, n = int(m.group(1)), int(m.group(2))
        return a, min(12, (n + 1) // 2 if a >= 1980 else n)
    m = re.search(r"(19\d\d)", nome)
    return (int(m.group(1)), None) if m else (None, None)


def lacune(cfg_problemi, docs):
    """Lacune delle fonti nei mesi attorno ai documenti trovati (±1 mese), più un conteggio per anno."""
    if not docs or not Path(cfg_problemi).exists():
        return []
    periodici = ("Renmin Ribao", "Peking Review", "Hongqi", "Red Flag")   # per le raccolte l'anno non è quello dei documenti
    mesi, anni = set(), set()
    for d in docs:
        v = d["voci"][0]
        if v["fonte"] not in periodici or not v["data"][:4].isdigit():
            continue
        a = int(v["data"][:4])
        anni.add(a)
        if len(v["data"]) >= 7:
            m = int(v["data"][5:7])
            for k in (-1, 0, 1):
                mm, aa = m + k, a
                if mm < 1:
                    mm, aa = 12, a - 1
                if mm > 12:
                    mm, aa = 1, a + 1
                mesi.add((aa, mm))
    if not anni:
        return []
    chiavi = {"Renmin Ribao": "Renmin", "Peking Review": "Peking", "Hongqi": "Hongqi", "Red Flag": "Hongqi"}
    serie_presenti = {chiavi.get(d["voci"][0]["fonte"], d["voci"][0]["fonte"]) for d in docs}
    vicine, per_anno = defaultdict(list), defaultdict(int)
    with open(cfg_problemi, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            serie = r["serie"]
            if not any(k.lower() in serie.lower() for k in serie_presenti):
                continue
            nome = Path(r["file"]).name.replace(".txt", "")
            a, m = _mese_problema(serie, r["file"])
            if a not in anni:
                continue
            if r["problema"] in ("giorno mancante", "numero mancante", "numeri mancanti"):
                per_anno[(serie, a)] += 1
            if m is None or (a, m) in mesi:
                vicine[(serie, r["problema"])].append(nome)
    righe = []
    for (serie, problema), elenco in sorted(vicine.items()):
        mostra = ", ".join(elenco[:20]) + (f" e altri {len(elenco) - 20}" if len(elenco) > 20 else "")
        righe.append(f"- {serie}, {problema}, nei mesi dei documenti trovati: {mostra}")
    if per_anno:
        righe.append("- Totale di giorni o numeri mancanti negli anni dei documenti: " + "; ".join(
            f"{serie} {a}: {n}" for (serie, a), n in sorted(per_anno.items())))
    return righe


def note_limiti_serie():
    """Serie descritte in serie.ini (fonti importate con importa.py) -> frase per la sezione «Limiti»."""
    import configparser
    cp = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    cp.optionxform = str
    try:
        cp.read(Path(__file__).resolve().parent / "serie.ini", encoding="utf-8")
    except configparser.Error:
        return {}
    return {s: [x.strip() for x in cp.get(s, "nota_limiti", fallback="").split(" | ") if x.strip()]
            for s in cp.sections()}


def sez_limiti(docs, incerti, scartati, problemi, modello, problemi_mod=None):
    righe = ["## 5. Limiti e problemi interpretativi", ""]
    for p in problemi_mod or []:
        righe.append(f"- *Problema interpretativo:* {p['testo']} {''.join(f'[{r}]' for r in p['rif'])}")
    if incerti:
        righe.append(f"- {len(incerti)} passaggi classificati come **incerti**, da controllare a mano: "
                     + "; ".join(riferimento(c) for c in incerti[:30]) + " (file e righe nella sezione 8)")
    fonti = {d["voci"][0]["fonte"] for d in docs}
    if any(("资料" in f or "文件" in f) for f in fonti):
        righe.append("- Per le raccolte di documenti l'anno indicato è quello della raccolta, non dei documenti.")
    note_serie = note_limiti_serie()
    note = []
    for f in sorted(fonti):
        for frase in note_serie.get(f, []):
            if frase not in note:
                note.append(frase)
    if any(f not in note_serie for f in fonti):          # fonti cinesi (quelle non importate con importa.py)
        note.insert(0, "La stampa cinese registra ciò che Pechino sceglieva di pubblicare: l'assenza in queste "
                       "fonti non prova l'assenza dei fatti.")
    righe += [f"- {n}" for n in note]
    righe.append("- Traduzioni e sintesi dei passaggi vanno controllate sull'originale riportato.")
    if scartati:
        righe.append(f"- {scartati} affermazioni proposte dal modello sono state scartate perché prive di "
                     "rimando a un documento.")
    lac = lacune(problemi, docs)
    if lac:
        righe += ["- Lacune delle fonti nel periodo interessato (da `audit_fonti/problemi_residui.csv`):"] + \
                 ["  " + r for r in lac]
    return righe + [""]


def sez_copertura(scheda, cart, classificati, modelli):
    righe = ["## 6. Grado di copertura", "",
             f"- Varianti cercate: {'; '.join(scheda['varianti'])}"]
    riep = Path(cart) / "riepilogo.txt"
    if riep.exists():
        testo = riep.read_text(encoding="utf-8").splitlines()
        if testo:
            righe.append(f"- {testo[0]} — tutte le fonti della cartella `data`")
        righe += ["- " + l.strip() for l in testo if l.strip().startswith("variante")]
    n = defaultdict(int)
    for c in classificati:
        n[c["analisi"]["pertinente"]] += 1
    righe.append(f"- Passaggi esaminati: {len(classificati)} — pertinenti {n['sì']}, incerti {n['incerto']}, "
                 f"esclusi {n['no']}")
    righe.append(f"- Modelli: {modelli}")
    righe += righe_provenienza(classificati)
    return righe + [""]


def righe_provenienza(classificati):
    """Quanti passaggi sono stati decisi e letti da un modello, in sessione o per regola."""
    from archivio import LIVELLI, conta_provenienza

    def elenco(cnt):
        return "; ".join(f"{LIVELLI.get(l_, l_)}{' (' + d + ')' if d else ''} {n}" for (l_, d), n in cnt.most_common())
    righe = []
    for etichetta, gruppo in (("pertinenti", [c for c in classificati if c["analisi"]["pertinente"] == "sì"]),
                              ("esclusi", [c for c in classificati if c["analisi"]["pertinente"] == "no"])):
        if not gruppo:
            continue
        conta = conta_provenienza(gruppo)
        righe.append(f"- Provenienza della decisione, passaggi {etichetta}: {elenco(conta['decisione'])}")
        if etichetta == "pertinenti":
            righe.append(f"- Provenienza della traduzione, passaggi pertinenti: {elenco(conta['lettura'])}")
    return righe


# ---------------------------------------------------------------- sezioni scritte dal modello
def elenco_per_modello(docs):
    righe = []
    for d in docs:
        for c in d["voci"]:
            a = c["analisi"]
            if not a.get("citazione_verificata"):
                continue
            altri = "; ".join(f"{x['nome']} ({x.get('ruolo', '')})" for x in (a.get("altri_nominati") or [])[:12])
            righe.append(f"[{d['n']}] {d['rif']} (data del documento: {c.get('data') or 's.d.'}): "
                         f"{a.get('sintesi_it', '')} (frase: «{a.get('traduzione_it', '')}»)"
                         + (f" | Nominati nello stesso passaggio: {altri}" if altri else ""))
    return righe


def filtra_rif(voci, validi):
    tenute, scartate = [], 0
    for v in voci:
        rif = sorted({r for r in (v.get("rif") or []) if isinstance(r, int) and r in validi})
        if rif and v.get("testo", "").strip():
            v["rif"] = rif
            # i numeri dei documenti si aggiungono dopo: tolgo quelli che il modello ha messo nel testo
            v["testo"] = re.sub(r"\s*\[\s*\d+(?:\s*[,;]\s*\d+)*\s*\]", "", v["testo"]).strip()
            tenute.append(v)
        else:
            scartate += 1
    return tenute, scartate


def scrivi_con_modello(llm, entita, domanda, docs, glossario=None, dimensione=25):
    righe = elenco_per_modello(docs)
    testi = " ".join(c["passaggio"] for d in docs for c in d["voci"])
    gl = blocco(glossario or [], testi)
    validi = {d["n"] for d in docs}
    dati, scartati = [], 0
    for i in range(0, len(righe), dimensione):
        parte = "\n".join(righe[i:i + dimensione])
        r = llm.json(SISTEMA, f"""{gl}Entità: {entita}

Documenti (numero, riferimento, contenuto):
{parte}

Elenca i DATI ESPLICITI che questi documenti attestano sull'entità: fatti, date, ruoli, persone, eventi.
Un dato per voce, in ordine cronologico, ciascuno con i numeri dei documenti che lo attestano.
Indica la data degli eventi come la dà il testo. Se il testo non la dà, non attribuire all'evento la data del
documento: scrivi "(notizia del <data del documento>)".
Usa per persone, partiti e testate i nomi del GLOSSARIO.
Non dedurre e non aggiungere nulla che non sia scritto.
JSON: {{"dati_espliciti": [{{"testo": "...", "rif": [1, 2]}}]}}""", SCHEMA_DATI)
        tenuti, s = filtra_rif(r.get("dati_espliciti", []), validi)
        dati += tenuti
        scartati += s
    elenco_dati = "\n".join(f"- {d['testo']} {d['rif']}" for d in dati)
    contesto = "\n".join(r_ for r_ in righe if "Nominati nello stesso passaggio" in r_)[:6000]
    r = llm.json(SISTEMA, f"""{gl}Entità: {entita}
Domanda del ricercatore: {domanda or 'Chi/che cosa è questa entità e come compare nelle fonti?'}

Dati espliciti attestati (con numeri dei documenti):
{elenco_dati}

Persone e organizzazioni nominate negli stessi passaggi:
{contesto or '-'}

1. "inferenze": deduzioni ragionevoli che si possono trarre da questi dati, ciascuna con i documenti su cui
   si basa e la fondatezza (alta/media/bassa). Non presentarle come certezze.
2. "problemi_interpretativi": ciò che complica la lettura dei documenti, con i numeri dei documenti. In
   particolare: la stessa organizzazione che compare più volte con dirigenti o firmatari diversi; nomi
   uguali per soggetti diversi; contraddizioni tra documenti; identificazioni incerte. Lista vuota se nulla.
3. "risposta_finale": risposta alla domanda in 1-3 paragrafi, basata solo sui dati sopra, con i numeri dei
   documenti tra parentesi quadre, tenendo conto dei problemi interpretativi. Se i dati non bastano, dillo.
JSON.""", SCHEMA_FINALE)
    inferenze, s = filtra_rif(r.get("inferenze", []), validi)
    scartati += s
    problemi, s = filtra_rif(r.get("problemi_interpretativi", []), validi)
    scartati += s
    return dati, inferenze, problemi, r.get("risposta_finale", "").strip(), scartati


# ---------------------------------------------------------------- main
def avviso_non_letti(cart, out):
    """Se alcuni passaggi trovati non sono stati letti dal modello (errori ripetuti), lo dice nella sezione 5."""
    f = Path(cart) / "non_letti.json"
    try:
        n = json.loads(f.read_text(encoding="utf-8")).get("non_letti", 0) if f.exists() else 0
    except ValueError:
        n = 0
    if not n:
        return out
    k = max(i for i, r in enumerate(out) if r.startswith("## 5.")) + 2
    return out[:k] + [f"- **{n} passaggi trovati non sono stati letti dal modello** (errori ripetuti del "
                      "servizio): mancano da questa risposta. Rifacendo la domanda vengono letti."] + out[k:]


def avviso_sintesi(errore):
    """Avviso in testa alla risposta quando la sintesi del modello manca (il marcatore lo legge il server MCP)."""
    if not errore:
        return []
    return ["<!-- sintesi: non generata -->",
            f"> **Sintesi non generata.** Il modello di sintesi non ha risposto ({errore}). Le sezioni 3, 4 e 7 "
            "contengono solo ciò che Python calcola dai documenti; i passaggi della sezione 2 sono completi. "
            "Rifacendo la stessa domanda si rifà solo la sintesi: i passaggi sono già nell'archivio.", ""]


def main():
    ap = argparse.ArgumentParser(description="Risposta finale nel formato documenti / passaggi / dati / inferenze")
    ap.add_argument("cartella")
    ap.add_argument("entita")
    ap.add_argument("--domanda", default="")
    ap.add_argument("--senza-modello", action="store_true", help="solo le sezioni costruite da Python")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

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
                  "registrate in entita.ini. Se pensi che manchino, controlla le varianti della scheda o "
                  "allarga il periodo o le fonti.\n", encoding="utf-8")
            print("Nessuna occorrenza nel periodo o nelle fonti richieste: risposta vuota scritta.")
            return
        sys.exit("Nessun passaggio classificato: esegui prima classifica.py")
    schede = carica_entita(Path(args.entita))
    nome = classificati[0]["entita"]
    scheda = schede.get(nome, {"varianti": [nome], "note": ""})

    from llm import leggi_config, percorso
    cfg = leggi_config(args.config)
    global DATI
    DATI = percorso(cfg, "dati")

    pertinenti = [c for c in classificati if c["analisi"]["pertinente"] == "sì"]
    incerti = [c for c in classificati if c["analisi"]["pertinente"] == "incerto"]
    docs = raggruppa(pertinenti)
    m_analisi = elenco_modelli(pertinenti, "modello_analisi") or "nessuno"
    m_smista = elenco_modelli(classificati, "modello_smistamento")
    dati, inferenze, problemi_mod, finale, scartati, m_sintesi = [], [], [], "", 0, ""
    errore_sintesi = ""
    if not args.senza_modello and docs:
        from llm import LLM, ErroreModello
        try:
            llm = LLM(cfg, "sintesi")
            llm.controlla()
            m_sintesi = llm.modello
            print(f"Scrittura di dati espliciti, inferenze e risposta finale con {llm.modello}...")
            glossario = carica_glossario(percorso(cfg, "entita"))
            dati, inferenze, problemi_mod, finale, scartati = scrivi_con_modello(
                llm, nome, args.domanda, docs, glossario)
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

    out = [f"# {nome}", ""]
    out += avviso_sintesi(errore_sintesi)
    if args.domanda:
        out += [f"*Domanda:* {args.domanda}", ""]
    out += [f"*Generato il {dt.date.today().isoformat()} — documenti pertinenti: {len(docs)}.*", ""]
    out += sez_documenti(docs)
    out += sez_passaggi(docs, m_analisi)
    out += ["## 3. Dati espliciti", ""]
    out += [f"- {d['testo']} {''.join(f'[{r}]' for r in d['rif'])}" for d in dati] or \
           ["*(non generati: vedi i passaggi alla sezione 2)*"]
    out += ["", "## 4. Inferenze", ""]
    out += [f"- *Inferenza (fondatezza {i.get('fondatezza', '?')}):* {i['testo']} "
            f"{''.join(f'[{r}]' for r in i['rif'])}" for i in inferenze] or ["*(nessuna)*"]
    out += [""]
    out += sez_limiti(docs, incerti, scartati, percorso(cfg, "problemi"), m_analisi, problemi_mod)
    out = avviso_non_letti(cart, out)
    modelli = ", ".join(x for x in (f"smistamento {m_smista}" if m_smista else "",
                                     f"analisi {m_analisi}", f"sintesi {m_sintesi}" if m_sintesi else "") if x)
    out += sez_copertura(scheda, cart, classificati, modelli)
    out += ["## 7. Risposta finale", "", finale or ("*(non generata: vedi l'avviso in testa)*" if errore_sintesi else "*(non generata)*"), ""]
    out += sez_tecnica(docs, incerti)
    (cart / "risposta.md").write_text("\n".join(out), encoding="utf-8")
    print(f"Risposta: {(cart / 'risposta.md').resolve()}")


if __name__ == "__main__":
    main()

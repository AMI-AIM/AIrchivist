#!/usr/bin/env python3
"""
FASE 2 - Lettura dei passaggi con un modello, in due passaggi:
  1. smistamento: pertinente / no / incerto, più passaggi per richiesta ([estrazione] lotto_smistamento)
  2. analisi dei pertinenti: tipo di menzione, traduzione, sintesi, un passaggio per richiesta
Per risparmiare richieste:
  - i passaggi già letti in qualsiasi ricerca precedente vengono presi dall'archivio unico (archivio.py);
  - se il passaggio contiene una forma inequivocabile del nome (es. 雅克·格里巴, "Jacques Grippa",
    sigle con parentesi) lo smistamento si salta ([estrazione] forme_sicure = si);
  - le voci di sommario o di elenco (indici della Peking Review) non vengono tradotte né analizzate.
La citazione NON è scelta dal modello: è la frase del testo che contiene l'occorrenza, estratta da Python,
quindi è sempre testuale. Il modello la traduce e la commenta.

Uso:
  python classifica.py <cartella_risultati> <entita.ini> [--limite N] [--solo-rapporto] [--config config.ini]
Riprende da dove si era fermato. Output nella cartella: classificati.jsonl, classificati.csv, rapporto.md
"""
import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from estrai_occorrenze import carica_entita, is_cjk
from glossario import blocco, carica_glossario
from llm import ErroreModello, ModelloNonAmmesso
from archivio import apri, escluso, provenienza

TIPI = ["delegazione/visita", "citazione o sintesi di un articolo", "messaggio/telegramma",
        "notizia", "elenco", "altro"]

TONI = ["elogiativo", "neutro", "critico", "non determinabile"]

SCHEMA_LOTTO = {
    "type": "object",
    "properties": {"risultati": {"type": "array", "items": {
        "type": "object",
        "properties": {"n": {"type": "integer"},
                       "pertinente": {"type": "string", "enum": ["sì", "no", "incerto"]},
                       "motivazione": {"type": "string"}},
        "required": ["n", "pertinente", "motivazione"]}}},
    "required": ["risultati"],
}

# parole che rendono generica una forma latina di più parole ("Communist Party of Belgium" non è sicura)
GENERICHE = {"party", "communist", "communists", "committee", "central", "people", "people's", "peoples", "workers",
             "league", "union", "unity", "red", "line", "new", "group", "front", "organization", "movement",
             "revolutionary", "marxist", "leninist", "marxist-leninist", "socialist", "democratic", "national",
             "liberation", "army", "youth", "student", "students", "voice", "flag", "daily", "review", "the", "of",
             "and", "for", "partito", "comunista", "unità", "nuova", "linea", "rossa", "popolo"}
PARTICELLE = {"de", "di", "da", "del", "della", "la", "le", "van", "von", "der", "y", "e", "do", "dos", "das"}


def forma_sicura(v):
    """Forma del nome che non lascia dubbi sull'identità (lo smistamento si può saltare).
    Un titolo breve tra 《》 NON basta: testate diverse hanno lo stesso nome (《新团结》 è sia «Nuova Unità»
    sia la «Neue Einheit» del KPD/ML tedesco)."""
    v = (v or "").strip()
    if is_cjk(v):
        interno = re.sub(r"[《》\s]", "", v)
        if re.fullmatch(r"《[^《》]+》", re.sub(r"\s", "", v)):
            return len(interno) >= 6
        if re.search(r"[·・（）()]", v):
            return True
        # nome generico di partito (es. 比利时共产党, 意大利共产党): indica anche il partito ufficiale o un'altra
        # formazione con lo stesso nome, quindi non basta a decidere
        if re.search(r"(共产党|工人党|劳动党|社会党|党)$", interno) and not re.search(r"马克思|马列|列宁|毛泽东", interno):
            return False
        return len(interno) >= 6
    compatto = re.sub(r"[\s\-]", "", v.lower())
    if re.search(r"communistparty|partycommunist|partitocomunista|particommuniste|partidocomunista|"
                 r"kommunistischepartei|workers'?party|labou?rparty|socialistparty", compatto) \
            and not re.search(r"marx|lenin|mao|m-?l\b", v.lower()):
        return False                     # nome generico di partito: vale anche per il partito ufficiale
    if "(" in v and len(v) >= 12:
        return True
    parole = re.findall(r"[A-Za-zÀ-ÿ'’\-]+", v)
    if len(parole) < 2 or len(v) < 10:
        return False
    return all(p[0].isupper() for p in parole if p.lower() not in PARTICELLE) and \
        not any(p.lower() in GENERICHE for p in parole)


def e_sommario(rec):
    """Voce di sommario o di elenco: titoli seguiti dal numero di pagina, uno dopo l'altro."""
    t = rec.get("passaggio_evidenziato", "")
    i = t.find("⟦")
    if i < 0:
        return False
    vicino = t[max(0, i - 300): i + 300]
    return len(re.findall(r"[a-zA-Z\)\.,]\s?\d{1,3}\s?(?=[A-Z“\"])", vicino)) >= 3

SCHEMA_SMISTA = {
    "type": "object",
    "properties": {
        "pertinente": {"type": "string", "enum": ["sì", "no", "incerto"]},
        "motivazione": {"type": "string"},
    },
    "required": ["pertinente", "motivazione"],
}

SCHEMA_ANALISI = {
    "type": "object",
    "properties": {
        "tipo_menzione": {"type": "string", "enum": TIPI},
        "traduzione_it": {"type": "string"},
        "sintesi_it": {"type": "string"},
        "nuove_varianti": {"type": "array", "items": {"type": "string"}},
        "altri_nominati": {"type": "array", "items": {
            "type": "object",
            "properties": {"nome": {"type": "string"}, "ruolo": {"type": "string"}},
            "required": ["nome", "ruolo"]}},
        "ruolo_entita": {"type": "string"},
        "tono": {"type": "string", "enum": TONI},
        "evento": {"type": "string"},
    },
    "required": ["tipo_menzione", "traduzione_it", "sintesi_it", "nuove_varianti", "altri_nominati",
                 "ruolo_entita", "tono", "evento"],
}

SISTEMA = ("Sei un assistente di ricerca storica. Lavori solo sul testo che ti viene dato, "
           "senza aggiungere conoscenze esterne. Rispondi in italiano e solo con il JSON richiesto.")


# ---------------------------------------------------------------- utilità sul testo
def normalizza(s):
    """Confronto insensibile a spazi, a capo e trattini dell'OCR."""
    return re.sub(r"[\s\-‐]+", "", (s or "").replace("⟦", "").replace("⟧", "")).lower()


def verifica(rec, analisi):
    cit = analisi.get("citazione_testuale", "")
    return bool(cit) and normalizza(cit) in normalizza(rec["passaggio"])


def frase_chiave(rec, max_car=260):
    """Frase che contiene la prima occorrenza (testo esatto, senza i segni ⟦ ⟧)."""
    t = rec["passaggio_evidenziato"]
    i = t.find("⟦")
    if i < 0:
        return rec["passaggio"][:max_car]
    j = t.find("⟧", i)
    inizio = max(t.rfind(c, 0, i) for c in "。！？!?\n") + 1
    # per l'inglese: fine frase con ". " prima dell'occorrenza
    m = list(re.finditer(r"[.;]\s", t[:i]))
    if m and m[-1].end() > inizio:
        inizio = m[-1].end()
    fine_cand = [k for k in (t.find(c, j) for c in "。！？!?") if k >= 0]
    m2 = re.search(r"[.;]\s", t[j:])
    if m2:
        fine_cand.append(j + m2.start())
    fine = (min(fine_cand) + 1) if fine_cand else len(t)
    if fine - inizio > max_car:          # frase troppo lunga: finestra attorno all'occorrenza
        inizio = max(inizio, i - max_car // 2)
        fine = min(fine, j + max_car // 2)
    return t[inizio:fine].replace("⟦", "").replace("⟧", "").strip()


def pagina(rec):
    """Pagina del Renmin Ribao (第N版) più vicina prima dell'occorrenza, se presente nel passaggio."""
    t = rec["passaggio_evidenziato"]
    i = t.find("⟦")
    trovate = list(re.finditer(r"第\s*(\d+)\s*版", t[:i] if i > 0 else t))
    return trovate[-1].group(1) if trovate else ""


def ritaglia(rec, n):
    """Solo il testo attorno alle occorrenze (n caratteri per lato), per risparmiare token."""
    t = rec["passaggio_evidenziato"]
    if not n or len(t) <= 2 * n + 50:
        return t
    pezzi, fine_prec = [], -1
    for m in re.finditer(r"⟦[^⟧]*⟧", t):
        a, b = max(0, m.start() - n), min(len(t), m.end() + n)
        if pezzi and a <= fine_prec:
            pezzi[-1] = (pezzi[-1][0], b)
        else:
            pezzi.append((a, b))
        fine_prec = b
    return " […] ".join(t[a:b] for a, b in pezzi) or t[:2 * n]


def carica_jsonl(path):
    if not Path(path).exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(r) for r in f if r.strip()]


# ---------------------------------------------------------------- prompt
def prompt_smistamento(rec, scheda, n=0):
    return f"""Entità cercata: {rec['entita']}
Altre forme del nome: {'; '.join(scheda['varianti'])}
Note: {scheda['note'] or '-'}

Fonte: {rec.get('citazione') or rec['fonte']}

Nel passaggio seguente le occorrenze trovate dalla ricerca sono tra ⟦ e ⟧.
Decidi se si riferiscono davvero all'entità cercata.
- "sì": il passaggio parla dell'entità cercata (anche solo nominandola in un elenco).
- "no": è un omonimo, un'altra organizzazione, o un uso generico delle stesse parole.
- "incerto": il testo non basta per decidere.

PASSAGGIO:
{ritaglia(rec, n)}

Rispondi con JSON: {{"pertinente": "sì" | "no" | "incerto", "motivazione": "una frase"}}"""


def prompt_analisi(rec, scheda, frase, n=0, glossario=None):
    testo = ritaglia(rec, n)
    return f"""{blocco(glossario or [], testo + frase)}Entità cercata: {rec['entita']}
Note: {scheda['note'] or '-'}
Fonte: {rec.get('citazione') or rec['fonte']} (data: {rec.get('data') or 's.d.'})

PASSAGGIO (le occorrenze sono tra ⟦ e ⟧):
{testo}

FRASE DA TRADURRE:
{frase}

Compiti:
1. "tipo_menzione": uno tra {', '.join(TIPI)}.
2. "traduzione_it": traduzione italiana fedele della FRASE DA TRADURRE (non del passaggio intero). Per persone, partiti e testate usa i nomi del GLOSSARIO, se presenti. Se un termine è incerto, segnalalo tra parentesi quadre.
3. "sintesi_it": 1-3 frasi su ciò che il passaggio dice ESPLICITAMENTE dell'entità (chi, cosa, quando). Indica le date complete di anno, ricavandolo se necessario dalla data della fonte. Nessuna informazione esterna.
4. "nuove_varianti": altre forme del nome dell'entità presenti nel passaggio e non già note (lista vuota se nessuna).
5. "altri_nominati": altre persone e organizzazioni nominate nel passaggio accanto all'entità, ciascuna con il ruolo o il rapporto con l'entità come risulta dal testo. Se la stessa organizzazione compare più volte con firmatari o dirigenti diversi, riporta ogni voce separatamente.
6. "ruolo_entita": titolo, carica o qualifica che il passaggio attribuisce all'entità (es. "segretario del Comitato centrale", "organo del partito"); stringa vuota se non indicato.
7. "tono": come la fonte presenta l'entità: "elogiativo", "neutro", "critico" oppure "non determinabile".
8. "evento": in poche parole, l'evento o l'occasione a cui il passaggio si riferisce, con la data se indicata.

Rispondi con JSON."""


def prompt_lotto(gruppo, scheda, n=0):
    blocchi = "\n\n".join(f"[{k}] Fonte: {rec.get('citazione') or rec['fonte']}\n{ritaglia(rec, n)}"
                           for k, rec in enumerate(gruppo, 1))
    return f"""Entità cercata: {gruppo[0]['entita']}
Altre forme del nome: {'; '.join(scheda['varianti'])}
Note: {scheda['note'] or '-'}

Seguono {len(gruppo)} passaggi numerati. In ciascuno le occorrenze trovate dalla ricerca sono tra ⟦ e ⟧.
Per OGNI passaggio decidi se le occorrenze si riferiscono davvero all'entità cercata:
- "sì": il passaggio parla dell'entità cercata (anche solo nominandola in un elenco).
- "no": è un omonimo, un'altra organizzazione, o un uso generico delle stesse parole.
- "incerto": il testo non basta per decidere.
Valuta ogni passaggio per conto suo.

{blocchi}

Rispondi con JSON: {{"risultati": [{{"n": 1, "pertinente": "sì" | "no" | "incerto", "motivazione": "una frase"}}, ...]}}
con una voce per ciascuno dei {len(gruppo)} passaggi."""


# ---------------------------------------------------------------- classificazione
def smista_uno(rec, scheda, llm_s, n=0):
    s = llm_s.json(SISTEMA, prompt_smistamento(rec, scheda, n), SCHEMA_SMISTA)
    pert = s.get("pertinente", "incerto")
    return (pert if pert in ("sì", "no", "incerto") else "incerto"), s.get("motivazione", ""), llm_s.ultimo_modello


def smista_lotto(gruppo, scheda, llm_s, n=0):
    """{id: (pertinente, motivazione, modello)} per un gruppo di passaggi, con una sola richiesta.
    I passaggi a cui il modello non risponde vengono smistati uno per uno."""
    esiti = {}
    if len(gruppo) > 1:
        try:
            r = llm_s.json(SISTEMA, prompt_lotto(gruppo, scheda, n), SCHEMA_LOTTO)
            for voce in r.get("risultati") or []:
                try:
                    k = int(voce.get("n"))
                except (TypeError, ValueError):
                    continue
                if 1 <= k <= len(gruppo) and voce.get("pertinente") in ("sì", "no", "incerto"):
                    esiti[gruppo[k - 1]["id"]] = (voce["pertinente"], voce.get("motivazione", ""),
                                                  llm_s.ultimo_modello)
        except ErroreModello as e:
            if isinstance(e, ModelloNonAmmesso):
                raise
            print(f"    smistamento a lotti non riuscito ({str(e)[:80]}): procedo uno per uno")
    for rec in gruppo:
        if rec["id"] not in esiti:
            esiti[rec["id"]] = smista_uno(rec, scheda, llm_s, n)
    return esiti


def analizza(rec, scheda, esito, llm_a, n=0, glossario=None):
    """Completa la lettura di un passaggio già smistato: esito = (pertinente, motivazione, modello)."""
    t0 = time.time()
    pert, motivazione, mod_s = esito
    a = {"pertinente": pert, "motivazione": motivazione, "tipo_menzione": "",
         "citazione_testuale": "", "traduzione_it": "", "sintesi_it": "", "nuove_varianti": [],
         "pagina": pagina(rec), "modello_smistamento": mod_s}
    if pert in ("sì", "incerto") and e_sommario(rec):
        a.update({"tipo_menzione": "elenco", "citazione_testuale": frase_chiave(rec),
                  "traduzione_it": "(voce di sommario o di elenco: non tradotta)",
                  "sintesi_it": "Il nome compare in un sommario o in un elenco di titoli del numero.",
                  "modello_analisi": "nessuno (voce di sommario)", "sommario": True})
    elif pert in ("sì", "incerto") and llm_a is None:
        # solo smistamento (prove dei modelli): niente traduzione né analisi
        a.update({"citazione_testuale": frase_chiave(rec), "modello_analisi": "nessuno (solo smistamento)"})
    elif pert in ("sì", "incerto"):
        frase = frase_chiave(rec)
        r = llm_a.json(SISTEMA, prompt_analisi(rec, scheda, frase, 2 * n if n else 0, glossario), SCHEMA_ANALISI)
        a.update({
            "tipo_menzione": r.get("tipo_menzione", "altro"),
            "citazione_testuale": frase,
            "traduzione_it": r.get("traduzione_it", ""),
            "sintesi_it": r.get("sintesi_it", ""),
            "nuove_varianti": [v for v in (r.get("nuove_varianti") or [])
                               if isinstance(v, str) and v and v not in scheda["varianti"]],
            "altri_nominati": [x for x in (r.get("altri_nominati") or [])
                               if isinstance(x, dict) and x.get("nome")],
            "ruolo_entita": (r.get("ruolo_entita") or "").strip(),
            "tono": r.get("tono") if r.get("tono") in TONI else "non determinabile",
            "evento": (r.get("evento") or "").strip(),
            "modello_analisi": llm_a.ultimo_modello,
        })
    a["citazione_verificata"] = verifica(rec, a) if pert != "no" else False
    a["provenienza"] = provenienza(a)
    a["secondi"] = round(time.time() - t0, 1)
    return a


PERMANENTE = re.compile(r"errore (401|403|404)|non ammess|Manca la chiave|Manca 'modello|Backend sconosciuto",
                        re.IGNORECASE)


def scrivi_non_letti(cart, n):
    """Quanti passaggi sono rimasti da leggere (lo leggono le sezioni 5 delle risposte e il gestore dei lavori)."""
    f = Path(cart) / "non_letti.json"
    if n:
        f.write_text(json.dumps({"non_letti": n}), encoding="utf-8")
    elif f.exists():
        f.unlink()


def da_completare(a):
    """Lettura da rifare in parte: "analisi" se il passaggio è pertinente ma non è mai stato tradotto né
    analizzato (es. classificato per regola in una sessione precedente); "smistamento" se è incerto solo per
    regola, senza che nessuno l'abbia letto. Le correzioni manuali e le voci di sommario restano come sono."""
    if not a or a.get("corretto_a_mano") or a.get("sommario") or a.get("assorbito_da"):
        return None
    if a.get("pertinente") == "sì" and not (a.get("traduzione_it") or "").strip():
        return "analisi"
    if a.get("pertinente") == "incerto" and "per regola" in (a.get("tipo_menzione") or ""):
        return "smistamento"
    return None


def da_archivio(rec, a):
    """Adatta una lettura presa dall'archivio al passaggio corrente (pagina, citazione verificata)."""
    a = dict(a)
    a["pagina"] = pagina(rec)
    if a.get("pertinente") != "no":
        if not (a.get("citazione_testuale") and verifica(rec, a)):
            a["citazione_testuale"] = frase_chiave(rec)
        a["citazione_verificata"] = verifica(rec, a)
    return a


# ---------------------------------------------------------------- output
def scrivi_csv(classificati, path):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["id", "entita", "citazione", "data", "file", "riga", "pagina", "pertinente",
                    "tipo_menzione", "citazione_testuale", "citazione_verificata", "traduzione_it",
                    "sintesi_it", "nuove_varianti", "motivazione", "passaggio",
                    "modello_smistamento", "modello_analisi"])
        for c in classificati:
            a = c["analisi"]
            w.writerow([c["id"], c["entita"], c.get("citazione") or c["fonte"], c["data"], c["file"],
                        c["riga"], a.get("pagina", ""), a.get("pertinente", ""), a.get("tipo_menzione", ""),
                        a.get("citazione_testuale", ""), "sì" if a.get("citazione_verificata") else "",
                        a.get("traduzione_it", ""), a.get("sintesi_it", ""),
                        "; ".join(a.get("nuove_varianti", []) or []), a.get("motivazione", ""),
                        c["passaggio"], a.get("modello_smistamento", "") or a.get("classificato_da", ""),
                        a.get("modello_analisi", "") or a.get("classificato_da", "")])


def scrivi_rapporto(classificati, path):
    per_entita = defaultdict(list)
    for c in classificati:
        per_entita[c["entita"]].append(c)
    out = ["# Rapporto occorrenze", "",
           "Ogni voce rimanda a file e riga. ✔ = citazione ritrovata nel testo sorgente.", ""]
    for etichetta, campo in (("smistamento", "modello_smistamento"), ("analisi", "modello_analisi")):
        conta = Counter(c["analisi"].get(campo) or c["analisi"].get("classificato_da") for c in classificati
                        if c["analisi"].get(campo) or c["analisi"].get("classificato_da"))
        if conta:
            out.append(f"Modelli usati per {etichetta}: " +
                       "; ".join(f"{m} ({n} passaggi)" for m, n in conta.most_common()))
    out.append("")
    for entita, voci in per_entita.items():
        stati = Counter(v["analisi"].get("pertinente", "?") for v in voci)
        out += [f"## {entita}", "",
                f"Passaggi esaminati: {len(voci)} — pertinenti: {stati.get('sì', 0)}, "
                f"incerti: {stati.get('incerto', 0)}, non pertinenti: {stati.get('no', 0)}", ""]
        for etichetta, chiave in (("Occorrenze pertinenti", "sì"), ("Occorrenze incerte (da verificare)", "incerto")):
            sel = sorted((v for v in voci if v["analisi"].get("pertinente") == chiave),
                         key=lambda v: (v["data"], v["file"], v["riga"]))
            if not sel:
                continue
            out += [f"### {etichetta}", ""]
            for v in sel:
                a = v["analisi"]
                segno = "✔" if a.get("citazione_verificata") else "✘"
                mod = a.get("modello_analisi") or a.get("classificato_da") or ""
                pag = f", p. {a['pagina']}" if a.get("pagina") else ""
                out += [f"**{v.get('citazione') or v['fonte']}{pag}** — `{v['file']}`, riga {v['riga']} "
                        f"— {a.get('tipo_menzione', '')}", "",
                        f"- Citazione {segno}: {a.get('citazione_testuale', '')}",
                        f"- Traduzione: {a.get('traduzione_it', '')}",
                        f"- Sintesi: {a.get('sintesi_it', '')}"] + ([f"- Modello: {mod}"] if mod else []) + [""]
        varianti = Counter(nv for v in voci for nv in (v["analisi"].get("nuove_varianti") or []))
        if varianti:
            out += ["### Nuove varianti proposte (da valutare e aggiungere a entita.ini)", ""]
            out += [f"- {nv} ({n})" for nv, n in varianti.most_common()] + [""]
        esclusi = [v for v in voci if v["analisi"].get("pertinente") == "no"]
        if esclusi:
            out += ["### Occorrenze escluse", ""]
            out += [f"- {v.get('citazione') or v['fonte']}, `{v['file']}` r. {v['riga']}: "
                    f"{v['analisi'].get('motivazione', '')}" for v in esclusi] + [""]
    Path(path).write_text("\n".join(out), encoding="utf-8")


def stima(da_fare, n, llm, sicuri=0, lotto=1, sommari=0):
    """Stima approssimativa di richieste e token, per sapere in anticipo quanto durerà."""
    if not da_fare:
        return
    da_smistare = len(da_fare) - sicuri
    tok = sum(len(ritaglia(p, n)) for p in da_fare) * 0.9 + 450 * -(-da_smistare // max(1, lotto))  # smistamento
    analisi = max(0, int(sicuri + 0.5 * da_smistare) - sommari)                 # circa metà pertinenti
    tok += analisi * 1500
    richieste = -(-da_smistare // max(1, lotto)) + analisi
    msg = f"Stima approssimativa: {richieste} richieste e {int(tok / 1000)} mila token"
    if llm.backend == "openai" and "groq" in getattr(llm, "url", ""):
        msg += f"; con il piano gratuito di Groq (circa 200 mila token al giorno) servono circa {max(1, round(tok / 200000))} giorni"
    elif llm.backend == "openai" and ("localhost" in getattr(llm, "url", "") or "127.0.0.1" in getattr(llm, "url", "")):
        msg += "; con un router (FreeLLMAPI) la durata dipende dalle quote dei servizi nella catena"
    print(msg + ". Se si interrompe, rilancia lo stesso comando: riprende da dove era arrivato.")


# ---------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Classificazione dei passaggi con un modello locale o via API")
    ap.add_argument("cartella")
    ap.add_argument("entita")
    ap.add_argument("--limite", type=int, default=None, help="classifica solo i primi N (per prove)")
    ap.add_argument("--solo-rapporto", action="store_true")
    ap.add_argument("--solo-smistamento", action="store_true",
                    help="decide solo la pertinenza, senza traduzione né analisi (per le prove dei modelli)")
    ap.add_argument("--senza-archivio", action="store_true",
                    help="rilegge con il modello anche i passaggi già presenti nell'archivio unico")
    ap.add_argument("--accetta-incompleti", action="store_true",
                    help="finisce normalmente anche se alcuni passaggi non sono stati letti (errori ripetuti)")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    # codici di uscita: 0 = tutto letto; 3 = passaggi rimasti da leggere per limiti temporanei (quote, rete):
    # si riprova più tardi; 4 = errore che non passa da solo (chiave, modello, accesso)
    resto, permanente = 0, False

    cart = Path(args.cartella)
    p_out = cart / "classificati.jsonl"
    schede = carica_entita(Path(args.entita))
    passaggi = carica_jsonl(cart / "passaggi.jsonl")
    fatti = {c["id"]: c for c in carica_jsonl(p_out)}

    if not args.solo_rapporto:
        from llm import LLM, leggi_config, percorso
        cfg = leggi_config(args.config)
        n_mod = cfg.getint("estrazione", "finestra_modello", fallback=0)
        glossario = carica_glossario(percorso(cfg, "entita"))
        da_fare = [p for p in passaggi if p["id"] not in fatti and p["entita"] in schede and not p.get("assorbito_da")]

        # 1. archivio unico: passaggi già letti in altre ricerche
        arch = None
        if not escluso(cart):
            arch = apri(cfg)
            if len(arch) == 0:
                agg = arch.importa(percorso(cfg, "risultati"))
                if agg:
                    print(f"Archivio unico creato con {sum(agg.values())} letture delle ricerche precedenti.")
        dall_archivio = 0
        # correzioni manuali registrate nell'archivio (dall'interfaccia di chat): prevalgono sulle letture già
        # presenti in questa cartella; la riga aggiunta in fondo a classificati.jsonl sostituisce la precedente
        if arch is not None:
            corrette = 0
            with open(p_out, "a", encoding="utf-8") as f:
                for pid, rec in list(fatti.items()):
                    a, _ = arch.cerca(rec)
                    if a and a.get("corretto_a_mano") and not rec["analisi"].get("corretto_a_mano"):
                        nuovo = dict(rec, analisi=da_archivio(rec, a))
                        f.write(json.dumps(nuovo, ensure_ascii=False) + "\n")
                        fatti[pid] = nuovo
                        corrette += 1
            if corrette:
                print(f"Correzioni manuali applicate: {corrette}")
        # letture incomplete (pertinenti mai tradotti, incerti solo per regola): tornano al modello
        gia_pertinenti = {}
        decisione_prec = {}      # provenienza della decisione ripresa da una lettura precedente
        if not args.solo_smistamento:
            correnti = {p["id"]: p for p in passaggi if p["entita"] in schede and not p.get("assorbito_da")}
            for pid, rec in list(fatti.items()):
                k = da_completare(rec.get("analisi"))
                if k and pid in correnti:
                    if k == "analisi":
                        gia_pertinenti[pid] = rec["analisi"].get("motivazione") or "pertinente (lettura precedente)"
                        decisione_prec[pid] = provenienza(rec["analisi"])["decisione"]
                    da_fare.append(correnti[pid])    # la lettura vecchia resta finché non c'è la nuova
        if arch is not None and not args.senza_archivio:
            resto = []
            with open(p_out, "a", encoding="utf-8") as f:
                for p in da_fare:
                    a, come = arch.cerca(p)
                    k = None if args.solo_smistamento else da_completare(a)
                    if k == "analisi":
                        gia_pertinenti[p["id"]] = a.get("motivazione") or "pertinente (lettura precedente)"
                        decisione_prec[p["id"]] = provenienza(a)["decisione"]
                    if a is None or k:
                        resto.append(p)
                        continue
                    a = da_archivio(p, a)
                    a["dall_archivio"] = come
                    rec = dict(p, analisi=a)
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fatti[p["id"]] = rec
                    dall_archivio += 1
            da_fare = resto
            if dall_archivio:
                print(f"Dall'archivio unico (già letti in ricerche precedenti): {dall_archivio} passaggi")
        if gia_pertinenti:
            print(f"Passaggi pertinenti ancora senza traduzione né analisi: {len(gia_pertinenti)} "
                  "(vengono analizzati ora, senza ripetere lo smistamento)")
        if args.limite:
            da_fare = da_fare[:args.limite]
        if da_fare:
            try:
                llm_s, llm_a = LLM(cfg, "smistamento"), LLM(cfg, "analisi")
                llm_s.controlla()
                llm_a.controlla()
            except ErroreModello as e:
                print(f"ERRORE: {e}")
                scrivi_non_letti(cart, len(da_fare))
                sys.exit(4 if PERMANENTE.search(str(e)) else 3)
            print(f"Servizio: {llm_s.backend} | smistamento {llm_s.modello} | analisi {llm_a.modello}"
                  + (f" | modelli ammessi: {'; '.join(llm_s.ammessi)}" if llm_s.ammessi else ""))
        else:
            llm_s = llm_a = None
            print("Nessun passaggio nuovo da leggere: il modello non serve.")

        lotto = max(1, cfg.getint("estrazione", "lotto_smistamento", fallback=6))
        usa_sicure = cfg.get("estrazione", "forme_sicure", fallback="si").strip().lower() in ("si", "sì", "yes", "1", "true")
        # forme che la scheda dichiara ambigue (campo facoltativo "forme_ambigue"): mai considerate sicure
        import configparser
        cp_ent = configparser.ConfigParser(interpolation=None, delimiters=("=",))
        cp_ent.optionxform = str
        cp_ent.read(Path(args.entita), encoding="utf-8")
        ambigue = {s_: {normalizza(x) for x in re.split(r"[;；]", cp_ent.get(s_, "forme_ambigue", fallback="")) if x.strip()}
                   for s_ in cp_ent.sections()}

        def sicuro(p):
            if not usa_sicure:
                return False
            amb = ambigue.get(p["entita"], set())
            return any(forma_sicura(v) and normalizza(v) not in amb for v in p.get("varianti_trovate") or [])
        n_sicuri = sum(1 for p in da_fare if sicuro(p))
        n_sommari = sum(1 for p in da_fare if e_sommario(p))
        print(f"Passaggi da leggere con il modello: {len(da_fare)} (già fatti: {len(fatti)}); "
              f"con forma inequivocabile del nome: {n_sicuri}; voci di sommario: {n_sommari}; "
              f"smistamento a lotti di {lotto}")
        if llm_s:
            stima(da_fare, n_mod, llm_s, n_sicuri, lotto, n_sommari)
        t_inizio = time.time()
        errori_di_fila, ultimo_errore, fatti_ora, interrotto = 0, "", 0, False

        def errore(e, p):
            nonlocal errori_di_fila, ultimo_errore, permanente
            print(f"  ERRORE sul passaggio {p['id']}: {e}")
            errori_di_fila = errori_di_fila + 1 if str(e) == ultimo_errore else 1
            ultimo_errore = str(e)
            if isinstance(e, ModelloNonAmmesso):
                print("Interrompo: il router ha usato un modello non verificato. Nessun passaggio è stato "
                      "salvato con quel modello.")
                permanente = True
                return True
            if PERMANENTE.search(str(e)):
                permanente = True
            if errori_di_fila >= 3 or re.search(r"errore (401|403|404)", str(e)):
                print("Interrompo: lo stesso errore si ripete (chiave, nome del modello, accesso al servizio "
                      "o quote giornaliere esaurite: in quest'ultimo caso rilancia più tardi).")
                return True
            return False

        with open(p_out, "a", encoding="utf-8") as f:
            i = 0
            while i < len(da_fare) and not interrotto:
                p = da_fare[i]
                if p["id"] in gia_pertinenti:
                    gruppo = [p]
                    esiti = {p["id"]: ("sì", gia_pertinenti[p["id"]], "lettura precedente")}
                    i += 1
                elif sicuro(p):
                    gruppo = [p]
                    forma = next(v for v in p["varianti_trovate"] if forma_sicura(v))
                    esiti = {p["id"]: ("sì", f"forma inequivocabile del nome: {forma}", "regola (forma inequivocabile)")}
                    i += 1
                else:
                    gruppo, j = [p], i + 1
                    while (j < len(da_fare) and len(gruppo) < lotto and not sicuro(da_fare[j])
                           and da_fare[j]["id"] not in gia_pertinenti and da_fare[j]["entita"] == p["entita"]):
                        gruppo.append(da_fare[j])
                        j += 1
                    i = j
                    try:
                        esiti = smista_lotto(gruppo, schede[p["entita"]], llm_s, n_mod)
                    except ErroreModello as e:
                        interrotto = errore(e, p)
                        continue
                for q in gruppo:
                    try:
                        a = analizza(q, schede[q["entita"]], esiti[q["id"]],
                                     None if args.solo_smistamento else llm_a, n_mod, glossario)
                    except ErroreModello as e:
                        interrotto = errore(e, q)
                        if interrotto:
                            break
                        continue
                    errori_di_fila = 0
                    if q["id"] in decisione_prec:
                        a["provenienza"]["decisione"] = decisione_prec[q["id"]]
                    rec = dict(q, analisi=a)
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    f.flush()
                    fatti[q["id"]] = rec
                    if arch is not None and not args.solo_smistamento:
                        arch.aggiungi(q, a, origine=cart.name)
                    fatti_ora += 1
                    media = (time.time() - t_inizio) / fatti_ora
                    resto_min = media * (len(da_fare) - fatti_ora) / 60
                    mod = a.get("modello_analisi") or a.get("modello_smistamento", "")
                    print(f"  [{fatti_ora}/{len(da_fare)}] {q['data']} {q['file']} -> {a['pertinente']} "
                          f"({a['secondi']}s, {mod}, fine stimata tra {resto_min:.0f} min)")

    # passaggi contenuti in un altro passaggio: stessa valutazione di quello, senza nuova analisi
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
    n = Counter(c["analisi"]["pertinente"] for c in classificati)
    print(f"Classificati: {len(classificati)} | pertinenti {n.get('sì', 0)} | incerti {n.get('incerto', 0)} "
          f"| esclusi {n.get('no', 0)}")
    if not args.solo_rapporto and not args.limite and not args.solo_smistamento:
        resto = len(da_fare) - fatti_ora if da_fare else 0
        scrivi_non_letti(cart, resto)
        if resto:
            print(f"Passaggi rimasti da leggere: {resto}.")
            if not args.accetta_incompleti:
                sys.exit(4 if permanente else 3)


if __name__ == "__main__":
    main()

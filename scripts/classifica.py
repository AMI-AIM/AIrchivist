#!/usr/bin/env python3
"""
FASE 2 - Lettura dei passaggi con un modello, in due passaggi:
  1. smistamento: pertinente / no / incerto, più passaggi per richiesta ([estrazione] lotto_smistamento)
  2. analisi dei pertinenti: tipo di menzione, traduzione, sintesi, più passaggi della stessa entità per richiesta
     ([estrazione] lotto_analisi e lotto_analisi_caratteri; lavoro 40, G2)
Le richieste partono in parallelo, quante ne dice il profilo del modello («paralleli», G3); le letture si scrivono
una alla volta. Gli esiti dello smistamento restano in smistamento.jsonl finché il passaggio non è letto per intero:
un'interruzione durante l'analisi non fa ripetere lo smistamento.
Per risparmiare richieste:
  - i passaggi già letti in qualsiasi ricerca precedente vengono presi dall'archivio unico (archivio.py);
  - se il passaggio contiene una forma inequivocabile del nome (es. 雅克·格里巴, "Jacques Grippa",
    sigle con parentesi) lo smistamento si salta ([estrazione] forme_sicure = si);
  - le voci di sommario o di elenco (indici della Peking Review) non vengono tradotte né analizzate.
La citazione NON è scelta dal modello: è la frase del testo che contiene l'occorrenza, estratta da Python,
quindi è sempre testuale. Il modello la traduce e la commenta.

Uso:
  python classifica.py <cartella_risultati> <entities.ini> [--limite N] [--solo-rapporto] [--config config.ini]
Con --rileggi-modello NOME i passaggi letti da un modello il cui nome contiene NOME tornano al modello attuale:
la lettura nuova si aggiunge in fondo a classificati.jsonl e all'archivio e sostituisce la vecchia, che resta
nella storia dei file.
Riprende da dove si era fermato. Output nella cartella: classificati.jsonl, classificati.csv, rapporto.md
"""
import argparse
import csv
import json
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:                    # C3: anche con l'uscita in un file o in una pipe l'avanzamento si vede riga per riga
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass
from estrai_occorrenze import carica_entita, is_cjk
from glossario import blocco, carica_glossario
from llm import ErroreModello, ModelloNonAmmesso, ServizioFermo, avviso
from archivio import append_jsonl, apri, escluso, letto_da, modelli_lettori, provenienza


def riga_json(rec):
    """Una lettura in una riga di classificati.jsonl (formato comune a tutti i file JSONL della pipeline)."""
    return json.dumps(rec, ensure_ascii=False)

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


# nomi interi o abbreviati, come parole intere («Hsiang Jung 23» non è una data)
MESI_EN = (r"\b(?:January|February|March|April|May|June|July|August|September|October|November|December|"
           r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec|gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|"
           r"agosto|settembre|ottobre|novembre|dicembre)\b\.?")
# il punto conta (titoli che finiscono col punto: «"Reasonable Step". 27ROUND»), ma non dopo una cifra:
# «1960.14 “The …» è il rimando a una nota dopo una data
NUMERO_DI_PAGINA = re.compile(r"(?:[a-zA-Z\),”\"]|(?<!\d)\.)\s?(\d{1,3})\s?(?=[A-Z“\"])")
PRIMA_DATA = re.compile(r"(?:" + MESI_EN + r"|\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b)[,\s]*$")
DOPO_DATA = re.compile(r"\s?(?:" + MESI_EN + r")")
SOMMARIO_CINESE = re.compile(r"(?:今日|本期|本刊|本报)要目")
PAGINA_CINESE = re.compile(r"第[一二三四五六七八九十\d]{1,3}版")


def e_sommario(rec):
    """Voce di sommario o di elenco: titoli seguiti dal numero di pagina, uno dopo l'altro («Toast 14 Comrade …
    Journalists 15 …»). Non contano come numeri di pagina i rimandi alle note dopo una data («1960.14 “The …»)
    né i numeri delle date («26 October», «Apr. 22», «Sun, 30 Aug»): 25/10/2026, un articolo con note a piè di
    pagina era preso per un sommario e il passaggio non veniva tradotto."""
    t = rec.get("passaggio_evidenziato", "")
    i = t.find("⟦")
    if i < 0:
        return False
    vicino = t[max(0, i - 300): i + 300]
    # sommario dei quotidiani cinesi: «今 日 要 目 第四版 … 第一版 中苏两国领导人…» (Renmin Ribao 1961)
    compatto = re.sub(r"\s+", "", vicino)
    if SOMMARIO_CINESE.search(compatto) and len(PAGINA_CINESE.findall(compatto)) >= 2:
        return True
    pagine = 0
    for m in NUMERO_DI_PAGINA.finditer(vicino):
        if PRIMA_DATA.search(vicino[max(0, m.start() - 12): m.start(1)]) or DOPO_DATA.match(vicino, m.end(1)):
            continue
        pagine += 1
    return pagine >= 3

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

SCHEMA_ANALISI_LOTTO = {
    "type": "object",
    "properties": {"risultati": {"type": "array", "items": {
        "type": "object",
        "properties": {"n": {"type": "integer"}, **SCHEMA_ANALISI["properties"]},
        "required": ["n"] + SCHEMA_ANALISI["required"]}}},
    "required": ["risultati"],
}

SISTEMA = ("Sei un assistente di ricerca storica. Lavori solo sul testo che ti viene dato, "
           "senza aggiungere conoscenze esterne. Rispondi in italiano e solo con il JSON richiesto.")


# ---------------------------------------------------------------- utilità sul testo
# marcatore di pagina dei testi importati ([[p. 61 | pdf 2]], numerazione.py): non fa parte delle citazioni
MARCATORE = re.compile(r"\[\[\s*p[^\]]*\]\]", re.IGNORECASE)


def normalizza(s):
    """Confronto insensibile a spazi, a capo, trattini dell'OCR e marcatori di pagina."""
    return re.sub(r"[\s\-‐]+", "", MARCATORE.sub("", (s or "").replace("⟦", "").replace("⟧", ""))).lower()


def verifica(rec, analisi):
    cit = analisi.get("citazione_testuale", "")
    return bool(cit) and normalizza(cit) in normalizza(rec["passaggio"])


FRASE_MASSIMA = 600          # caratteri al più della citazione (A3: una frase intera, non il passaggio intero)


def frase_chiave(rec):
    """Frase (o frasi adiacenti) che contiene la prima occorrenza.
    Testo esatto, senza i segni ⟦ ⟧ né i marcatori di pagina.
    La citazione deve permettere il controllo (A3): si estende ai confini di frase
    e include la frase che contiene la forma del nome. Non si tronca a lunghezza fissa.
    """
    # i marcatori diventano spazi della stessa lunghezza: le posizioni restano, e il punto di «p.» non
    # chiude più una frase (25/10/2026: «1 | pdf 1]] 中苏两国…» in testa a una citazione)
    t = MARCATORE.sub(lambda m: " " * len(m.group(0)), rec["passaggio_evidenziato"])
    i = t.find("⟦")
    if i < 0:
        return rec["passaggio"]
    j = t.find("⟧", i)
    # inizio: ultimo terminatore di frase prima di ⟦
    inizio = max(t.rfind(c, 0, i) for c in "。！？!?\n") + 1
    # per l'inglese: fine frase con ". " prima dell'occorrenza
    m = list(re.finditer(r"[.;]\s", t[:i]))
    if m and m[-1].end() > inizio:
        inizio = m[-1].end()
    # fine: primo terminatore di frase dopo ⟧
    fine_cand = [k for k in (t.find(c, j) for c in "。！？!?") if k >= 0]
    m2 = re.search(r"[.;]\s", t[j:])
    if m2:
        fine_cand.append(j + m2.start())
    fine = (min(fine_cand) + 1) if fine_cand else len(t)
    # la citazione copre la frase intera; senza punteggiatura (OCR, testi cinesi senza 。) la «frase» sarebbe il
    # passaggio intero: oltre FRASE_MASSIMA si tiene una finestra attorno all'occorrenza, tagliata agli spazi
    if fine - inizio > FRASE_MASSIMA:
        a, b = max(inizio, i - FRASE_MASSIMA // 2), min(fine, j + FRASE_MASSIMA // 2)
        if a > inizio and " " in t[a:i]:
            a = t.index(" ", a) + 1
        if b < fine and " " in t[j:b]:
            b = t.rindex(" ", j, b)
        inizio, fine = a, b
    return re.sub(r" {2,}", " ", t[inizio:fine].replace("⟦", "").replace("⟧", "")).strip()


def pagina(rec):
    """Pagina più vicina prima dell'occorrenza, se indicata nel passaggio secondo la pagina_regex del profilo
    della serie (es. 第N版 del Renmin Ribao); '' se la serie non ne ha."""
    import profili
    t = rec["passaggio_evidenziato"]
    i = t.find("⟦")
    return profili.ultima_pagina(t[:i] if i > 0 else t, rec.get("fonte", ""), rec.get("file", ""))


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
# occorrenza in una nota a piè di pagina dei curatori dell'edizione (apparato.py): non è testo del documento
NOTA_CURATORI = ("Il passaggio è una NOTA DEI CURATORI dell'edizione, non il testo del documento: le informazioni "
                 "vengono dai curatori. Nella sintesi scrivi «secondo la nota dei curatori».")


def avviso_nota(rec):
    return NOTA_CURATORI + "\n" if rec.get("apparato") == "nota" else ""


def prompt_smistamento(rec, scheda, n=0):
    return f"""Entità cercata: {rec['entita']}
Altre forme del nome: {'; '.join(scheda['varianti'])}
Note: {scheda['note'] or '-'}

Fonte: {rec.get('citazione') or rec['fonte']}
{avviso_nota(rec)}
Nel passaggio seguente le occorrenze trovate dalla ricerca sono tra ⟦ e ⟧.
Decidi se si riferiscono davvero all'entità cercata.
- "sì": il passaggio parla dell'entità cercata (anche solo nominandola in un elenco).
- "no": è un omonimo, un'altra organizzazione, o un uso generico delle stesse parole.
- "incerto": il testo non basta per decidere.

PASSAGGIO:
{ritaglia(rec, n)}

Rispondi con JSON: {{"pertinente": "sì" | "no" | "incerto", "motivazione": "una frase"}}"""


# 25/10/2026: «ricavando l'anno dalla data della fonte» ha fatto scrivere «ottobre 1979» per un fatto che un
# articolo del 2 agosto 1979 dà come già avvenuto «in ottobre» (cioè nel 1978). Controllo: archivio.py date_sospette.
REGOLA_ANNO = ("Per le date: scrivi l'anno solo se il passaggio lo indica o se si ricava con certezza. Se il passaggio "
               "dà solo giorno o mese, confrontalo con la data della fonte: un fatto già avvenuto in un mese successivo "
               "a quello della fonte è dell'anno precedente; un fatto annunciato o previsto in un mese precedente è "
               "dell'anno seguente. Se non è certo, scrivi la data senza anno e aggiungi «(anno non indicato)».")


# 3/11/2026 (lavoro 40, A2): in un rapporto della Legazione albanese Dinucci racconta la biografia di un comunista
# di Udine («Deri më 1952 ka qenë social demokrat…», «tha Dinuçi»), e la lettura l'ha attribuita a Dinucci.
REGOLA_DISCORSO = ("Chi dice che cosa: molti documenti riferiscono discorsi (un rapporto riporta ciò che una persona "
                   "ha detto, e quella persona può raccontare di altri). Attribuisci ogni fatto alla persona a cui il "
                   "testo lo riferisce. Formule come «disse X», «tha X», «X ci informò», «said X» indicano chi parla, "
                   "non di chi si parla: se l'entità racconta le azioni, le opinioni o la biografia di un'altra "
                   "persona, scrivi «[entità] riferisce che [altra persona] …», mai come fatti dell'entità stessa. "
                   "Se non è chiaro a chi si riferisce un fatto, dillo.")


# 3/11/2026 (lavoro 40, A4): nella prova un nome comune («vajtje», andata) è stato letto come un altro («vajtim», lutto)
# e la traduzione ha fatto morire una persona; i nomi declinati restavano declinati («Gripen» per Gripa). Gli esempi
# del prompt sono volutamente diversi dal caso della prova, che serve da controllo.
REGOLA_DECLINAZIONI = ("Nomi declinati: molte lingue (albanese, rumeno, lingue slave, greco…) declinano anche i nomi "
                       "propri. Nella traduzione riporta il nome al nominativo (albanese «Hoxhës» → Hoxha, «Shehun» → "
                       "Shehu; rumeno «Ceaușescului» → Ceaușescu). Traduci le parole per quello che sono: se una parola "
                       "somiglia a un'altra di senso molto diverso (un viaggio, una morte, un arresto), scegli il senso "
                       "che il contesto conferma e, se resta il dubbio, segnalalo tra parentesi quadre.")


def prompt_analisi(rec, scheda, frase, n=0, glossario=None):
    testo = ritaglia(rec, n)
    return f"""{blocco(glossario or [], testo + frase)}Entità cercata: {rec['entita']}
Note: {scheda['note'] or '-'}
Fonte: {rec.get('citazione') or rec['fonte']} (data: {rec.get('data') or 's.d.'})
{avviso_nota(rec)}
PASSAGGIO (le occorrenze sono tra ⟦ e ⟧):
{testo}

FRASE DA TRADURRE:
{frase}

Compiti:
{COMPITI_ANALISI}

Rispondi con JSON."""


def prompt_analisi_lotto(gruppo, scheda, frasi, n=0, glossario=None):
    """Analisi di più passaggi della stessa entità con una sola richiesta (G2): stessi compiti dell'analisi di un
    passaggio, una voce per passaggio. I passaggi dello stesso documento stanno nello stesso lotto (la lettura va
    in ordine di file): il modello li legge insieme, ma ciò che scrive di un passaggio deve risultare da quello."""
    testi = [ritaglia(rec, n) for rec in gruppo]
    blocchi = "\n\n".join(
        f"[{k}] Fonte: {rec.get('citazione') or rec['fonte']} (data: {rec.get('data') or 's.d.'})\n{avviso_nota(rec)}"
        f"PASSAGGIO (le occorrenze sono tra ⟦ e ⟧):\n{testo}\n\nFRASE DA TRADURRE:\n{frase}"
        for k, (rec, testo, frase) in enumerate(zip(gruppo, testi, frasi), 1))
    return f"""{blocco(glossario or [], "".join(testi) + "".join(frasi))}Entità cercata: {gruppo[0]['entita']}
Note: {scheda['note'] or '-'}

Seguono {len(gruppo)} passaggi numerati, ciascuno con la sua fonte e la sua FRASE DA TRADURRE. Analizza ogni passaggio per conto suo: ciò che scrivi di un passaggio deve risultare da quel passaggio, anche quando più passaggi vengono dallo stesso documento.

{blocchi}

Compiti, per OGNI passaggio:
{COMPITI_ANALISI}

Rispondi con JSON: {{"risultati": [{{"n": 1, "tipo_menzione": "...", "traduzione_it": "...", "sintesi_it": "...", "nuove_varianti": [], "altri_nominati": [], "ruolo_entita": "", "tono": "...", "evento": "..."}}, ...]}}
con una voce per ciascuno dei {len(gruppo)} passaggi, nello stesso ordine."""


COMPITI_ANALISI = f"""1. "tipo_menzione": uno tra {', '.join(TIPI)}.
2. "traduzione_it": traduzione italiana fedele della FRASE DA TRADURRE (non del passaggio intero). Per persone, partiti e testate usa i nomi del GLOSSARIO, se presenti. {REGOLA_DECLINAZIONI} Se un termine è incerto, segnalalo tra parentesi quadre.
3. "sintesi_it": 1-3 frasi su ciò che il passaggio dice ESPLICITAMENTE dell'entità (chi, cosa, quando): ciò che fa, dice o riferisce. {REGOLA_DISCORSO} {REGOLA_ANNO} Nessuna informazione esterna.
4. "nuove_varianti": altre forme del nome dell'entità presenti nel passaggio e non già note (lista vuota se nessuna).
5. "altri_nominati": altre persone e organizzazioni nominate nel passaggio accanto all'entità, ciascuna con il ruolo o il rapporto con l'entità come risulta dal testo. Se la stessa organizzazione compare più volte con firmatari o dirigenti diversi, riporta ogni voce separatamente.
6. "ruolo_entita": titolo, carica o qualifica che il passaggio attribuisce all'entità (es. "segretario del Comitato centrale", "organo del partito"); stringa vuota se non indicato.
7. "tono": come la fonte presenta l'entità: "elogiativo", "neutro", "critico" oppure "non determinabile".
8. "evento": in poche parole, l'evento o l'occasione a cui il passaggio si riferisce, con la data se indicata."""


def prompt_lotto(gruppo, scheda, n=0):
    blocchi = "\n\n".join(f"[{k}] Fonte: {rec.get('citazione') or rec['fonte']}\n{avviso_nota(rec)}{ritaglia(rec, n)}"
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
            if isinstance(e, (ModelloNonAmmesso, ServizioFermo)):
                raise
            avviso(f"    smistamento a lotti non riuscito ({str(e)[:80]}): procedo uno per uno")
    for rec in gruppo:
        if rec["id"] not in esiti:
            esiti[rec["id"]] = smista_uno(rec, scheda, llm_s, n)
    return esiti


def analizza(rec, scheda, esito, llm_a, n=0, glossario=None):
    """Completa la lettura di un passaggio già smistato: esito = (pertinente, motivazione, modello)."""
    t0 = time.time()
    pert = esito[0]
    a = lettura_iniziale(rec, esito)
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
        risposta_analisi(a, r, frase, scheda, llm_a.ultimo_modello)
    return chiudi_analisi(rec, a, t0)


def lettura_iniziale(rec, esito):
    pert, motivazione, mod_s = esito
    return {"pertinente": pert, "motivazione": motivazione, "tipo_menzione": "",
            "citazione_testuale": "", "traduzione_it": "", "sintesi_it": "", "nuove_varianti": [],
            "pagina": pagina(rec), "modello_smistamento": mod_s}


def risposta_analisi(a, r, frase, scheda, modello):
    """La risposta del modello all'analisi di un passaggio (r) nella lettura a."""
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
        "modello_analisi": modello,
    })


def chiudi_analisi(rec, a, t0, secondi=None):
    a["citazione_verificata"] = verifica(rec, a) if a["pertinente"] != "no" else False
    a["provenienza"] = provenienza(a)
    a["secondi"] = round(time.time() - t0 if secondi is None else secondi, 1)
    return a


def serve_analisi(rec, esito):
    """Vero se la lettura del passaggio richiede l'analisi del modello (pertinente o incerto, non un sommario)."""
    return esito[0] in ("sì", "incerto") and not e_sommario(rec)


def lotti_analisi(da_analizzare, lotto, caratteri, n=0):
    """Gruppi per l'analisi a lotti (G2): passaggi della stessa entità, nell'ordine di lettura (così i passaggi
    dello stesso documento stanno insieme), al più «lotto» per gruppo e al più «caratteri» di testo inviato."""
    gruppi = []
    for rec in da_analizzare:
        lungo = len(ritaglia(rec, n)) + len(frase_chiave(rec))
        g = gruppi[-1] if gruppi else None
        if (g and len(g["passaggi"]) < lotto and g["passaggi"][0]["entita"] == rec["entita"]
                and g["caratteri"] + lungo <= caratteri):
            g["passaggi"].append(rec)
            g["caratteri"] += lungo
        else:
            gruppi.append({"passaggi": [rec], "caratteri": lungo})
    return [g["passaggi"] for g in gruppi]


def analizza_lotto(gruppo, schede, esiti, llm_a, n=0, glossario=None):
    """Analisi di un gruppo di passaggi già smistati con una sola richiesta (G2). Restituisce (letture, errori):
    {id: lettura} e [(passaggio, ErroreModello)]. I passaggi a cui la risposta del lotto non dà una voce completa
    si analizzano uno per uno; un lotto che non riesce (JSON troncato, forma inattesa) anche."""
    if len(gruppo) == 1:
        try:
            return {gruppo[0]["id"]: analizza(gruppo[0], schede[gruppo[0]["entita"]], esiti[gruppo[0]["id"]], llm_a,
                                              n, glossario)}, []
        except ErroreModello as e:
            if isinstance(e, (ModelloNonAmmesso, ServizioFermo)):
                raise
            return {}, [(gruppo[0], e)]
    t0 = time.time()
    scheda = schede[gruppo[0]["entita"]]
    frasi = [frase_chiave(rec) for rec in gruppo]
    letture = {}
    try:
        # una risposta per passaggio: la lunghezza massima cresce con il lotto, fino a 8000 token (molti servizi
        # gratuiti non ne danno di più); una sola richiesta: se il lotto non riesce si legge uno per uno
        r = llm_a.json(SISTEMA, prompt_analisi_lotto(gruppo, scheda, frasi, 2 * n if n else 0, glossario),
                       SCHEMA_ANALISI_LOTTO, tentativi_forma=1,
                       max_token=max(llm_a.max_token, min(llm_a.max_token * len(gruppo), 8000)))
        modello, secondi = llm_a.ultimo_modello, (time.time() - t0) / len(gruppo)
        for voce in r.get("risultati") or []:
            try:
                k = int(voce.get("n"))
            except (TypeError, ValueError, AttributeError):
                continue
            if not (1 <= k <= len(gruppo)) or gruppo[k - 1]["id"] in letture:
                continue
            if not all(isinstance(voce.get(c), str) and voce[c].strip() for c in ("traduzione_it", "sintesi_it")):
                continue
            rec = gruppo[k - 1]
            a = lettura_iniziale(rec, esiti[rec["id"]])
            risposta_analisi(a, voce, frasi[k - 1], scheda, modello)
            a["lotto"] = len(gruppo)
            letture[rec["id"]] = chiudi_analisi(rec, a, t0, secondi)
    except ErroreModello as e:
        if isinstance(e, (ModelloNonAmmesso, ServizioFermo)):
            raise
        avviso(f"    analisi a lotti non riuscita ({str(e)[:80]}): procedo uno per uno")
    errori = []
    mancanti = [rec for rec in gruppo if rec["id"] not in letture]
    if mancanti and len(mancanti) < len(gruppo):
        avviso(f"    analisi a lotti: {len(mancanti)} passaggi su {len(gruppo)} senza risposta completa, li leggo uno per uno")
    for rec in mancanti:
        try:
            letture[rec["id"]] = analizza(rec, schede[rec["entita"]], esiti[rec["id"]], llm_a, n, glossario)
        except ErroreModello as e:
            if isinstance(e, (ModelloNonAmmesso, ServizioFermo)):
                raise
            errori.append((rec, e))
    return letture, errori


def in_parallelo(lavori, funzione, quanti):
    """(lavoro, risultato, errore) di ogni lavoro, man mano che finiscono, con al più «quanti» richieste in corso
    (G3). Le letture si scrivono nel thread di chi legge, una alla volta. Se chi legge smette (interruzione), i
    lavori non ancora partiti si annullano e si aspetta solo la fine di quelli in corso."""
    ex = ThreadPoolExecutor(max_workers=max(1, quanti))
    try:
        futuri = {ex.submit(funzione, l): l for l in lavori}
        for f in as_completed(futuri):
            try:
                yield futuri[f], f.result(), None
            except ErroreModello as e:
                yield futuri[f], None, e
    finally:
        ex.shutdown(wait=True, cancel_futures=True)


PERMANENTE = re.compile(r"errore (401|403|404)|non ammess|Manca la chiave|Manca 'modello|Backend sconosciuto|"
                        r"rifiuta la chiave|non trova il modello", re.IGNORECASE)


def scrivi_non_letti(cart, n):
    """Quanti passaggi sono rimasti da leggere (lo leggono le sezioni 5 delle risposte e il gestore dei lavori)."""
    f = Path(cart) / "non_letti.json"
    if n:
        f.write_text(json.dumps({"non_letti": n}), encoding="utf-8")
    elif f.exists():
        f.unlink()


def registro_lettura(cart, secondi, letti, modelli):
    """Tempi della lettura (G1), in tempi_lettura.json della cartella della ricerca (una voce per lancio) e in due
    righe per il registro: quanta parte del tempo è lavoro del modello e quanta attesa del motore (pause, limiti del
    servizio, errori), quante richieste e quante risposte da richiedere di nuovo. modelli: {ruolo: LLM}."""
    ruoli = {r: {"richieste": m.richieste, "secondi_modello": round(m.secondi_modello, 1),
                 "secondi_attesa": round(m.secondi_attesa, 1), "risposte_scartate": m.risposte_scartate}
             for r, m in modelli.items() if m is not None}
    voce = {"quando": time.strftime("%Y-%m-%d %H:%M"), "secondi": round(secondi, 1), "passaggi_letti": letti,
            **ruoli}
    f = Path(cart) / "tempi_lettura.json"
    try:
        storia = json.loads(f.read_text(encoding="utf-8")) if f.exists() else []
    except (ValueError, OSError):
        storia = []
    f.write_text(json.dumps(storia + [voce], ensure_ascii=False, indent=1), encoding="utf-8")
    righe = [f"Lettura: {letti} passaggi in {secondi / 60:.1f} min"]
    for r, x in ruoli.items():
        righe.append(f"  {r}: {x['richieste']} richieste, {x['secondi_modello'] / 60:.1f} min di risposta del modello, "
                     f"{x['secondi_attesa'] / 60:.1f} min di attesa"
                     + (f", {x['risposte_scartate']} risposte inutilizzabili richieste di nuovo"
                        if x["risposte_scartate"] else ""))
    return righe


def da_completare(a):
    """Lettura da rifare in parte: "analisi" se il passaggio è pertinente ma non è mai stato tradotto né
    analizzato (es. classificato per regola in una sessione precedente); "smistamento" se è incerto solo per
    regola, senza che nessuno l'abbia letto. Le correzioni manuali e le voci di sommario restano come sono."""
    if not a or a.get("corretto_a_mano") or a.get("sommario") or a.get("assorbito_da"):
        return None
    if a.get("pertinente") == "sì" and a.get("da_rileggere") == "analisi":     # archivio.py date_sospette
        return "analisi"
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
            out += ["### Nuove varianti proposte (da valutare e aggiungere a entities.ini)", ""]
            out += [f"- {nv} ({n})" for nv, n in varianti.most_common()] + [""]
        esclusi = [v for v in voci if v["analisi"].get("pertinente") == "no"]
        if esclusi:
            out += ["### Occorrenze escluse", ""]
            out += [f"- {v.get('citazione') or v['fonte']}, `{v['file']}` r. {v['riga']}: "
                    f"{v['analisi'].get('motivazione', '')}" for v in esclusi] + [""]
    Path(path).write_text("\n".join(out), encoding="utf-8")


def stima(da_fare, n, llm, sicuri=0, lotto=1, sommari=0, lotto_analisi=1):
    """Stima approssimativa di richieste e token, per sapere in anticipo quanto durerà. sicuri: passaggi che non
    passano dallo smistamento (forma inequivocabile, già pertinenti, smistati in un lancio precedente)."""
    if not da_fare:
        return
    da_smistare = len(da_fare) - sicuri
    tok = sum(len(ritaglia(p, n)) for p in da_fare) * 0.9 + 450 * -(-da_smistare // max(1, lotto))  # smistamento
    analisi = max(0, int(sicuri + 0.5 * da_smistare) - sommari)                 # circa metà pertinenti
    tok += analisi * 1500
    richieste = -(-da_smistare // max(1, lotto)) + -(-analisi // max(1, lotto_analisi))
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
    ap.add_argument("--rileggi-modello", default=None, metavar="NOME",
                    help="rilegge con il modello attuale i passaggi letti da un modello il cui nome contiene NOME")
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
    # usati anche dopo la lettura: con --solo-rapporto la lettura non c'è
    llm_s = llm_a = None
    t_inizio, fatti_ora = time.time(), 0

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
            corrette = []
            for pid, rec in list(fatti.items()):
                a, _ = arch.cerca(rec)
                if a and a.get("corretto_a_mano") and not rec["analisi"].get("corretto_a_mano"):
                    nuovo = dict(rec, analisi=da_archivio(rec, a))
                    corrette.append(riga_json(nuovo))
                    fatti[pid] = nuovo
            if corrette:
                append_jsonl(p_out, corrette)   # blocco inter-processo + fsync (archivio.append_jsonl)
                print(f"Correzioni manuali applicate: {len(corrette)}")
        # letture di un modello da rifare (--rileggi-modello): il passaggio torna da leggere; nell'archivio vale
        # una lettura più recente di un altro lettore, se c'è
        if args.rileggi_modello:
            correnti = {p["id"]: p for p in passaggi if p["entita"] in schede and not p.get("assorbito_da")}
            rileggere = [pid for pid, rec in fatti.items() if pid in correnti and letto_da(rec["analisi"], args.rileggi_modello)]
            nomi = sorted({m for pid in rileggere for m in modelli_lettori(fatti[pid]["analisi"])
                           if args.rileggi_modello.lower() in m.lower()})
            for pid in rileggere:
                del fatti[pid]
                da_fare.append(correnti[pid])
            print(f"Da rileggere perché letti da «{args.rileggi_modello}»: {len(rileggere)} passaggi"
                  + (f" ({'; '.join(nomi)})" if nomi else ""))
        # letture incomplete (pertinenti mai tradotti, incerti solo per regola): tornano al modello
        gia_pertinenti = {}
        decisione_prec = {}      # provenienza della decisione ripresa da una lettura precedente
        if not args.solo_smistamento:
            correnti = {p["id"]: p for p in passaggi if p["entita"] in schede and not p.get("assorbito_da")}
            for pid, rec in list(fatti.items()):
                k = da_completare(rec.get("analisi"))
                if not k and arch is not None and not args.senza_archivio:
                    # lettura di questa cartella che l'archivio segna da rileggere (archivio.py date_sospette)
                    a_arch, _ = arch.cerca(rec)
                    if a_arch and a_arch.get("da_rileggere"):
                        k = da_completare(a_arch)
                if k and pid in correnti:
                    if k == "analisi":
                        gia_pertinenti[pid] = rec["analisi"].get("motivazione") or "pertinente (lettura precedente)"
                        decisione_prec[pid] = provenienza(rec["analisi"])["decisione"]
                    da_fare.append(correnti[pid])    # la lettura vecchia resta finché non c'è la nuova
        if arch is not None and not args.senza_archivio:
            resto = []
            for p in da_fare:
                a, come = arch.cerca(p)
                if letto_da(a, args.rileggi_modello):
                    resto.append(p)
                    continue
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
                append_jsonl(p_out, [riga_json(rec)])   # subito: la lettura non si perde se il job muore
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
                # C1: una richiesta vera, non solo l'elenco dei modelli: un router può rispondere a /models e non
                # ancora alle richieste. Entro 40 s si sa se il servizio legge.
                llm_s.prova(secondi=40)
                if llm_a.profilo != llm_s.profilo:
                    llm_a.prova(secondi=40)
            except ErroreModello as e:
                print(f"ERRORE: {e}")
                scrivi_non_letti(cart, len(da_fare))
                sys.exit(4 if PERMANENTE.search(str(e)) else 3)
            print(f"Modelli: smistamento {llm_s.modello} ({llm_s.profilo}) | analisi {llm_a.modello} ({llm_a.profilo})"
                  + (f" | modelli ammessi: {'; '.join(llm_s.ammessi)}" if llm_s.ammessi else ""))
            if args.rileggi_modello and any(args.rileggi_modello.lower() in m.lower()
                                            for m in (llm_s.modello, llm_a.modello)):
                print(f"ATTENZIONE: il modello attuale corrisponde a «{args.rileggi_modello}»: la rilettura usa lo "
                      "stesso modello. Scegli prima un altro profilo (python installa.py modello usa <profilo>).")
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
        # esiti dello smistamento già noti: pertinenti di una lettura precedente, smistati in un lancio interrotto
        # prima dell'analisi (smistamento.jsonl), forme inequivocabili del nome
        f_smist = cart / "smistamento.jsonl"
        ids_da_fare = {p["id"] for p in da_fare}
        esiti = {} if args.rileggi_modello else {r["id"]: tuple(r["esito"]) for r in carica_jsonl(f_smist)
                                                 if r.get("id") in ids_da_fare}
        n_ripresi = len(esiti)
        n_sicuri = 0
        for p in da_fare:
            if p["id"] in gia_pertinenti:
                esiti[p["id"]] = ("sì", gia_pertinenti[p["id"]], "lettura precedente")
            elif p["id"] not in esiti and sicuro(p):
                forma = next(v for v in p["varianti_trovate"] if forma_sicura(v))
                esiti[p["id"]] = ("sì", f"forma inequivocabile del nome: {forma}", "regola (forma inequivocabile)")
                n_sicuri += 1
        n_sommari = sum(1 for p in da_fare if e_sommario(p))
        lotto_an = 1 if args.solo_smistamento else max(1, cfg.getint("estrazione", "lotto_analisi", fallback=3))
        car_an = cfg.getint("estrazione", "lotto_analisi_caratteri", fallback=6000)
        print(f"Passaggi da leggere con il modello: {len(da_fare)} (già fatti: {len(fatti)}); "
              f"con forma inequivocabile del nome: {n_sicuri}; voci di sommario: {n_sommari}"
              + (f"; già smistati in un lancio precedente: {n_ripresi}" if n_ripresi else "")
              + f"; smistamento a lotti di {lotto}, analisi a lotti di {lotto_an}"
              + (f", {llm_s.paralleli} richieste alla volta" if llm_s and llm_s.paralleli > 1 else ""))
        if llm_s:
            stima(da_fare, n_mod, llm_s, len(esiti), lotto, n_sommari, lotto_an)
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
            if isinstance(e, ServizioFermo):
                print("Interrompo: il servizio non risponde. Rilancia lo stesso comando più tardi: la ricerca "
                      "riprende da dove era arrivata.")
                return True
            if PERMANENTE.search(str(e)):
                permanente = True
            if errori_di_fila >= 3 or re.search(r"errore (401|403|404)", str(e)):
                print("Interrompo: lo stesso errore si ripete (chiave, nome del modello, accesso al servizio "
                      "o quote giornaliere esaurite: in quest'ultimo caso rilancia più tardi).")
                return True
            return False

        def salva(q, a):
            nonlocal fatti_ora
            if q["id"] in decisione_prec:
                a["provenienza"]["decisione"] = decisione_prec[q["id"]]
            rec = dict(q, analisi=a)
            # append_jsonl: blocco inter-processo + fsync a ogni lettura. Il costo è trascurabile
            # rispetto ai secondi della chiamata al modello, e una riga corrotta o persa vale quanto
            # la quota API spesa per quella lettura.
            append_jsonl(p_out, [riga_json(rec)])
            fatti[q["id"]] = rec
            if arch is not None and not args.solo_smistamento:
                arch.aggiungi(q, a, origine=cart.name)
            fatti_ora += 1
            media = (time.time() - t_inizio) / fatti_ora
            resto_min = media * (len(da_fare) - fatti_ora) / 60
            mod = a.get("modello_analisi") or a.get("modello_smistamento", "")
            print(f"  [{fatti_ora}/{len(da_fare)}] {q['data']} {q['file']} -> {a['pertinente']} "
                  f"({a['secondi']}s, {mod}, fine stimata tra {resto_min:.0f} min)")

        # 1. smistamento a lotti, più richieste alla volta; gli esiti si salvano subito in smistamento.jsonl
        gruppi_s = []
        for p in (p for p in da_fare if p["id"] not in esiti):
            if gruppi_s and len(gruppi_s[-1]) < lotto and gruppi_s[-1][0]["entita"] == p["entita"]:
                gruppi_s[-1].append(p)
            else:
                gruppi_s.append([p])
        if gruppi_s:
            print(f"Smistamento: {sum(map(len, gruppi_s))} passaggi in {len(gruppi_s)} richieste")
            with closing(in_parallelo(gruppi_s, lambda g: smista_lotto(g, schede[g[0]["entita"]], llm_s, n_mod),
                                      llm_s.paralleli)) as risultati:
                for k, (g, es, e) in enumerate(risultati, 1):
                    if e:
                        if errore(e, g[0]):
                            interrotto = True
                            break
                        continue
                    errori_di_fila = 0
                    esiti.update(es)
                    append_jsonl(f_smist, [riga_json({"id": i, "esito": list(v)}) for i, v in es.items()])
                    conta = Counter(v[0] for v in es.values())
                    print(f"  smistamento {k}/{len(gruppi_s)}: {conta.get('sì', 0)} pertinenti, "
                          f"{conta.get('incerto', 0)} incerti, {conta.get('no', 0)} non pertinenti")

        # 2. passaggi che non servono al modello: non pertinenti, voci di sommario, solo smistamento
        analisi_ids = set()
        for q in da_fare:
            if q["id"] not in esiti:
                continue
            if not args.solo_smistamento and serve_analisi(q, esiti[q["id"]]):
                analisi_ids.add(q["id"])
            else:
                salva(q, analizza(q, schede[q["entita"]], esiti[q["id"]], None, n_mod, glossario))

        # 3. analisi a lotti dei pertinenti e degli incerti, più richieste alla volta
        if analisi_ids and not interrotto:
            gruppi_a = lotti_analisi([q for q in da_fare if q["id"] in analisi_ids], lotto_an, car_an,
                                     2 * n_mod if n_mod else 0)
            print(f"Analisi: {len(analisi_ids)} passaggi in {len(gruppi_a)} richieste")
            with closing(in_parallelo(gruppi_a, lambda g: analizza_lotto(g, schede, esiti, llm_a, n_mod, glossario),
                                      llm_a.paralleli)) as risultati:
                for g, r, e in risultati:
                    if e:
                        if errore(e, g[0]):
                            interrotto = True
                            break
                        continue
                    letture, errori = r
                    for q in g:
                        if q["id"] in letture:
                            errori_di_fila = 0
                            salva(q, letture[q["id"]])
                    for q, e2 in errori:
                        interrotto = errore(e2, q) or interrotto
                    if interrotto:
                        break

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
    if llm_s or llm_a:
        modelli = {"smistamento": llm_s} if llm_s is llm_a else {"smistamento": llm_s, "analisi": llm_a}
        print("\n".join(registro_lettura(cart, time.time() - t_inizio, fatti_ora, modelli)))
    n = Counter(c["analisi"]["pertinente"] for c in classificati)
    print(f"Classificati: {len(classificati)} | pertinenti {n.get('sì', 0)} | incerti {n.get('incerto', 0)} "
          f"| esclusi {n.get('no', 0)}")
    if not args.solo_rapporto and not args.limite:
        resto = len(da_fare) - fatti_ora if da_fare else 0
        scrivi_non_letti(cart, resto)
        if resto:
            print(f"Passaggi rimasti da leggere: {resto}.")
            if not args.accetta_incompleti:
                sys.exit(4 if permanente else 3)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Apparato editoriale nei testi importati: testatine e note a piè di pagina dei curatori (lavoro 40, A1).

Le testatine (titolo corrente, autori o curatori, numero di pagina, ripetuti in testa o in piede delle pagine) e le
note dei curatori di un'edizione non sono parole del documento. Lasciate nel testo finiscono nei passaggi e il
modello le attribuisce al documento: nella prova del 3/11/2026 la testatina «48 ARMANDO BOÇE, ARBËR BILBILI»
(i curatori del volume) precedeva il brano su un sospetto agente, e la risposta ha fatto di Boçe il sospettato.

All'importazione (importa.py, dopo la numerazione delle pagine) le righe si marcano nel file di data, su righe
proprie, senza togliere nulla del testo:
  [[testatina: 46 ARMANDO BOÇE, ARBËR BILBILI]]   la riga intera, com'era
  [[nota]]
  8 Fosco Dinucci (1921 - 1993), komisar politik partizan ...
  [[/nota]]
L'estrazione (estrai_occorrenze.py) non legge le testatine e tiene le note fuori dai passaggi del testo; un'occorrenza
dentro una nota diventa un passaggio a sé, segnato come nota dei curatori. L'indice non conta le testatine.

Riconoscimento:
  - testatina: una delle prime o delle ultime due righe di una pagina che si ripete, con le stesse parole, in un'altra
    pagina dello stesso documento o nelle testatine già marcate nei documenti della serie (i documenti di una o
    due pagine non hanno ripetizioni proprie). I numeri e le lettere isolate (l'OCR del filetto «|») non contano.
  - nota: uno degli ultimi paragrafi della pagina che comincia con il richiamo (un numero, o le virgolette in cui
    l'OCR trasforma un numero in apice) seguito da uno spazio, quando lo stesso richiamo compare attaccato a una
    parola più su nella pagina («Dinuçin8», «Balestri”»). Dal primo paragrafo di nota alla fine della pagina.
"""
import difflib
import re
import unicodedata
from pathlib import Path

RIGHE_DI_BORDO = 2
MINIMO_CARATTERI = 12                 # parole della testatina (senza spazi né numeri) per tenerne conto
SOMIGLIANZA = 0.85
PARAGRAFI_IN_FONDO = 3                # paragrafi dal fondo della pagina in cui cercare l'inizio delle note
QUOTA_NOTE = 0.6                      # al più questa parte delle righe di una pagina è fatta di note
RIGHE_MAX_NOTE = 14                   # righe al più del blocco delle note in fondo alla pagina
MASSIMO_MAIUSCOLA = 70                # testatina senza numero: riga breve...
QUOTA_MAIUSCOLE = 0.75                # ...quasi tutta in maiuscolo

MARCATORE = re.compile(r"^\s*\[\[.*\]\]\s*$")
NUMERO_IN_TESTA = re.compile(r"^[^\w]*\d{1,4}\s+\S")              # «46 ARMANDO BOÇE»
NUMERO_IN_CODA = re.compile(r"\S\s+\W*[^\W\d_]?\d{1,4}\W*$")      # «socialist I 45», «socialist t S1»
TESTATINA = re.compile(r"^\[\[testatina:[^\n]*\]\][ \t]*$", re.MULTILINE)
NOTA = re.compile(r"^\[\[nota\]\][ \t]*\n.*?^\[\[/nota\]\][ \t]*$", re.MULTILINE | re.DOTALL)
INIZIO_NOTA = re.compile(r"^\s*(?:(\d{1,3})|([“”\"'’‘*†‡£]{1,2}))\s+(?=\S)")
RIGA_TESTATINA = re.compile(r"^\[\[testatina:\s*(.*?)\]\]\s*$")


def forma(riga):
    """Le parole di una riga, minuscole e senza accenti, di almeno tre lettere: la stessa testatina letta dall'OCR
    in pagine diverse («socialist I 45», «socialist tl 57») dà la stessa forma."""
    s = unicodedata.normalize("NFKD", (riga or "").lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(re.findall(r"[^\W\d_]{3,}", s))


def simili(a, b):
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= SOMIGLIANZA


def _contenuto(righe):
    """Indici delle righe con testo, esclusi i marcatori [[...]]."""
    return [k for k, r in enumerate(righe) if r.strip() and not MARCATORE.match(r)]


def aspetto_di_testatina(riga):
    """Una testatina porta il numero di pagina a un'estremità («46 ARMANDO BOÇE…», «…socialist I 45»,
    «PEKING REVIEW, No. 11»), oppure è una riga breve quasi tutta in maiuscolo. Le righe del testo che si ripetono
    (pagine uguali, ritornelli) non hanno di solito né l'uno né l'altro."""
    r = riga.strip()
    if NUMERO_IN_TESTA.match(r) or NUMERO_IN_CODA.search(r):
        return True
    lettere = [ch for ch in r if ch.isalpha()]
    return len(r) <= MASSIMO_MAIUSCOLA and bool(lettere) and \
        sum(ch.isupper() for ch in lettere) >= QUOTA_MAIUSCOLE * len(lettere)


def _candidate(righe):
    """{indice di riga: forma} delle righe di bordo che possono essere testatine."""
    c = _contenuto(righe)
    bordo = c[:RIGHE_DI_BORDO] + c[-RIGHE_DI_BORDO:] if len(c) > 2 * RIGHE_DI_BORDO else c
    out = {}
    for k in dict.fromkeys(bordo):
        f = forma(righe[k])
        if len(f.replace(" ", "")) >= MINIMO_CARATTERI and " " in f and aspetto_di_testatina(righe[k]):
            out[k] = f
    return out


def _paragrafi(righe, indici):
    """Gruppi di righe consecutive con testo (tra gli indici dati): [[i, j, ...], ...]."""
    out, prec = [], None
    for k in indici:
        if prec is not None and k == prec + 1 and not MARCATORE.match(righe[k]):
            out[-1].append(k)
        else:
            out.append([k])
        prec = k
    return out


def _inizio_nota(riga, corpo):
    """La riga comincia una nota: richiamo, spazio, poi una maiuscola (o virgolette, parentesi). Con un numero per
    richiamo basta anche che lo stesso numero sia attaccato a una parola più su («Dinuçin8»). L'OCR legge spesso
    il numero in apice come un altro segno (' ’ “ ”, «'£») o lo perde nel testo: la maiuscola è il criterio comune."""
    m = INIZIO_NOTA.match(riga)
    if not m:
        return False
    dopo = riga[m.end():m.end() + 1]
    if dopo.isupper() or dopo in "“\"([":
        return True
    return bool(m.group(1)) and re.search(rf"[^\W\d_][”\"’)]?{m.group(1)}(?!\d)", corpo) is not None


def _note(righe):
    """(prima, ultima) riga del blocco delle note in fondo alla pagina, o None. La nota può cominciare a inizio di
    paragrafo o, quando l'OCR non lascia la riga vuota, dentro l'ultimo paragrafo del testo."""
    if any(r.strip() == "[[nota]]" for r in righe):
        return None                               # già marcata
    c = _contenuto(righe)
    paragrafi = _paragrafi(righe, c)
    if len(paragrafi) < 2:
        return None
    in_fondo = [k for p in paragrafi[max(1, len(paragrafi) - PARAGRAFI_IN_FONDO):] for k in p]
    ultima = paragrafi[-1][-1]
    for k in in_fondo:                            # la prima dall'alto: il blocco va da lì alla fine
        resto = sum(1 for j in c if j >= k)
        if resto > RIGHE_MAX_NOTE or resto > QUOTA_NOTE * len(c):
            continue
        if _inizio_nota(righe[k], "\n".join(righe[:k])):
            return k, ultima
    return None


def marca(testi, note=()):
    """Marca testatine e note nelle pagine di un documento (una stringa per pagina, con l'eventuale marcatore di
    pagina in testa). note: forme di testatine già note per la serie (testatine_note). Restituisce (testi,
    {"testatine": n, "note": n, "forme": set})."""
    pagine = [(t or "").split("\n") for t in testi]
    candidate = [_candidate(r) for r in pagine]
    note = list(note)
    forme, n_testatine, n_note = set(), 0, 0
    for i, righe in enumerate(pagine):
        for k, f in candidate[i].items():
            altrove = any(simili(f, g) for j, c in enumerate(candidate) if j != i for g in c.values())
            if altrove or any(simili(f, g) for g in note):
                righe[k] = f"[[testatina: {righe[k].strip()}]]"
                forme.add(f)
                n_testatine += 1
        blocco = _note(righe)
        if blocco:
            prima, ultima = blocco
            righe[ultima + 1:ultima + 1] = ["[[/nota]]"]
            righe[prima:prima] = ["[[nota]]"]
            n_note += 1
    return ["\n".join(r) for r in pagine], {"testatine": n_testatine, "note": n_note, "forme": forme}


def intervalli(testo, da=0):
    """[(inizio, fine, tipo)] dell'apparato nel testo di un file: tipo «testatina» (la riga del marcatore) o «nota»
    (da [[nota]] a [[/nota]] compresi), in ordine."""
    out = [(m.start(), m.end(), "testatina") for m in TESTATINA.finditer(testo, da)]
    out += [(m.start(), m.end(), "nota") for m in NOTA.finditer(testo, da)]
    return sorted(out)


def dove(spazi, pos):
    """Il tratto di apparato che contiene la posizione, o None."""
    for a, b, tipo in spazi:
        if a <= pos < b:
            return a, b, tipo
        if a > pos:
            break
    return None


def senza(testo, a, b, spazi):
    """testo[a:b] senza i tratti di apparato (testatine e note)."""
    pezzi, cursore = [], a
    for x, y, _ in spazi:
        if y <= a or x >= b:
            continue
        if x > cursore:
            pezzi.append(testo[cursore:x])
        cursore = max(cursore, y)
    if cursore < b:
        pezzi.append(testo[cursore:b])
    return "".join(pezzi)


def indietro(testo, da, caratteri, spazi, minimo=0):
    """Posizione da cui comincia la finestra: `caratteri` caratteri di testo del documento prima di `da`, senza
    contare quelli dell'apparato che si attraversano."""
    pos, resto = da, caratteri
    for x, y, _ in reversed([s for s in spazi if s[1] <= da]):
        if pos - resto >= y:
            break
        resto -= pos - y
        pos = x
    return max(minimo, pos - resto)


def avanti(testo, da, caratteri, spazi):
    """Posizione in cui finisce la finestra: `caratteri` caratteri di testo del documento dopo `da`."""
    pos, resto = da, caratteri
    for x, y, _ in [s for s in spazi if s[0] >= da]:
        if pos + resto <= x:
            break
        resto -= x - pos
        pos = y
    return min(len(testo), pos + resto)


def corpo_nota(testo, a, b):
    """(inizio, fine) del testo di una nota, senza le righe [[nota]] e [[/nota]]."""
    inizio = testo.index("\n", a) + 1
    fine = testo.rindex("[[/nota]]", a, b)
    return inizio, fine


def e_testatina(riga):
    return bool(RIGA_TESTATINA.match((riga or "").strip()))


def e_marcatore(riga):
    """Righe dell'apparato che il controllo delle intestazioni deve accettare: [[testatina: …]], [[nota]], [[/nota]]."""
    r = (riga or "").strip()
    return e_testatina(r) or r in ("[[nota]]", "[[/nota]]")


def testatine_note(cartella):
    """Forme delle testatine già marcate nei file di una cartella di data (i documenti della stessa serie)."""
    forme = set()
    for f in sorted(Path(cartella).glob("*.txt")) if Path(cartella).is_dir() else []:
        try:
            testo = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for m in TESTATINA.finditer(testo):
            g = RIGA_TESTATINA.match(m.group(0))
            forme.add(forma(g.group(1)))
    return forme - {""}


def completa(path, note):
    """Marca nel file appena scritto le testatine che si riconoscono solo con quelle della serie (documenti di
    una o due pagine importati prima degli altri). True se il file è cambiato. Si usa solo sui file scritti
    dalla stessa importazione: correggere i file già nel corpus richiede la registrazione in audit."""
    from citazioni import MARCATORE_PAGINA
    from estrai_occorrenze import leggi_intestazione
    testo = Path(path).read_text(encoding="utf-8")
    _, pos = leggi_intestazione(testo)
    corpo = testo[pos:].split("\n")
    inizi = [k for k, r in enumerate(corpo) if MARCATORE_PAGINA.match(r.strip())]
    if not inizi or not note:
        return False
    confini = inizi + [len(corpo)]
    pagine = ["\n".join(corpo[confini[i]:confini[i + 1]]) for i in range(len(inizi))]
    marcate, info = marca(pagine, note)
    if not info["testatine"] and not info["note"]:
        return False
    nuovo = testo[:pos] + "\n".join(corpo[:inizi[0]] + "\n".join(marcate).split("\n"))
    if nuovo == testo:
        return False
    Path(path).write_text(nuovo, encoding="utf-8")
    return True

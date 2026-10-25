#!/usr/bin/env python3
"""
Server MCP (Model Context Protocol) della pipeline: collega la ricerca nelle fonti all'interfaccia di chat di
un LLM (Jan, LM Studio, Open WebUI, ...). Solo libreria standard di Python.

Il modello della chat NON legge le fonti: usa questi strumenti. La lettura dei passaggi resta alla pipeline
(archivio unico + modelli configurati in config.ini); alla chat arrivano solo risultati con citazioni verificate.

Avvio:
  python mcp_server.py                 (stdio: lo avvia Jan; vedi ISTRUZIONI.md)
  python mcp_server.py --http 8766     (HTTP "Streamable", per Open WebUI: http://127.0.0.1:8766/mcp)
"""
import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARTELLA))

# Il canale stdout appartiene al protocollo: tutto ciò che la pipeline stampa va su stderr.
_PROTOCOLLO = sys.stdout.buffer
sys.stdout = sys.stderr

import schede                                   # noqa: E402
import lavori                                   # noqa: E402
import varianti as mod_varianti                 # noqa: E402
from archivio import Archivio, escluso          # noqa: E402
from llm import leggi_config, percorso          # noqa: E402
from sintesi import riferimento as sintesi_rif  # noqa: E402
from classifica import pagina as pagina_di      # noqa: E402

NOME, VERSIONE = "ricerca-fonti", "1.0"
VERSIONI_PROTOCOLLO = ["2025-06-18", "2025-03-26", "2024-11-05"]
CONFIG = None
import profili                                  # noqa: E402
# fonti selezionabili dalla chat: i gruppi dei profili di serie (Hongqi = Hongqi + Red Flag; documenti = raccolte)
FONTI_SCELTE = sorted({profili.gruppo(n) for n in profili.tutti()})

ISTRUZIONI = """Assistente di ricerca di uno storico (Cina maoista, maoismo italiano e internazionale). Rispondi in
italiano. Le fonti (Renmin Ribao, Peking Review, Hongqi/Red Flag, raccolte, Selected Works, 1963-1980) le conosci
solo attraverso questi strumenti: stampa ufficiale cinese (e albanese, se importata), fonti primarie di
carattere propagandistico.

Procedura:
1. elenca_entita. Senza scheda: esplora_nome (indizi in cinese e in inglese, tue trascrizioni come candidate),
   mostra forme, conteggi ed esempi, e dopo conferma dell'utente crea_scheda con le sole forme attestate.
2. Per ogni domanda sulle fonti avvia_ricerca (con i passaggi già in archivio è rapida), poi attendi_ricerca
   finché finito è vero (ogni chiamata attende fino a 75 s; la ricerca continua anche se la chat si chiude e,
   se le quote finiscono, riprende da sola: dillo all'utente).
3. Presenta la risposta della pipeline (risposta_pronta, oppure leggi_risposta senza sezioni): puoi riordinarla,
   abbreviarla e tradurla, ma i fatti, le date, le cariche e i riferimenti sono quelli; conserva le avvertenze.
   Non ricostruire tu la risposta dai passaggi. passaggi_archivio, apri_fonte e cerca_testo servono a mostrare
   un passaggio o a verificare un punto quando l'utente lo chiede.

Regole:
- Ogni affermazione viene da un passaggio degli strumenti, citato con il "riferimento" così com'è, in stile
  Chicago (es. "*Renmin ribao* 人民日报, 20 aprile 1963, 4", "*Peking Review* 10, no. 11 (10 marzo 1967)"):
  la citazione si ferma alla pagina, e la pagina si indica solo se il riferimento la contiene. Non indicare mai file né righe nella risposta ("file_e_riga" serve solo per
  apri_fonte). Mai rimandi tipo [12].
- Per i fatti principali: testo originale invariato, poi «Traduzione:» (senza dire chi l'ha fatta).
- Nessun fatto né cifra che non venga dagli strumenti, anche se lo conosci (semmai a parte, come ipotesi da
  verificare). Non spostare date o cariche da un passaggio a un altro; cariche con la formula del passaggio
  (书记 segretario del CC, 总书记 segretario generale). Se un dato manca, dillo.
- Per un periodo preciso avvia la ricerca con dal/al. Prima di interpretare un'assenza usa copertura_fonti; i
  silenzi di entità con molti passaggi incerti dipendono dalla classificazione.
- Distingui dati espliciti e inferenze, graduate con prudenza. Nomi nella forma delle fonti; le forme
  occidentali ricostruite da una trascrizione cinese vanno segnalate come tali.
- Se la ricerca si interrompe o la sintesi non è generata, dillo e non scrivere tu la ricostruzione mancante;
  se usi una risposta salvata prima, indicane la data.
- Citazioni in stile Chicago con le virgole ("Renmin Ribao, 9 luglio 1971, p. 5"). Mai la parola "corpus".
- Applica queste regole senza enunciarle: non scrivere frasi come "cito in stile Chicago", "riporto
  l'originale e la traduzione" o "non uso conoscenze esterne".
- Se il nome cercato è solo una variante nella scheda di un'altra entità (es. una persona nella scheda del
  suo partito), dillo: i risultati riguardano tutta quell'entità; filtra i passaggi con testo_filtro e, per una
  ricerca sulla persona, proponi esplora_nome e una scheda propria.
- Distingui la data della fonte (pubblicazione) dalla data dell'evento riferito.
- Usa solo gli strumenti di questo server: niente shell né lettura diretta dei file.
- Correzioni dell'utente: correggi_passaggio; nuove forme del nome: varianti (aggiungi), dopo conferma.
- Nuovo materiale: importa_fonti (prima con prova se la serie o la scansione è nuova: mostra qualità e data
  letta), poi stato_importazione finché finita. Serie nuova: elenca_serie, poi crea_serie con i dati che
  l'utente conferma. Le forme albanesi proposte da esplora_nome sono ipotesi: entrano nella scheda solo dopo
  conferma."""


def cfg():
    return leggi_config(CONFIG)


MARCATORE = "<!-- sintesi: non generata -->"          # scritto da sintesi.py ed evoluzione.py
AVVISO_SINTESI = ("Sintesi non generata (il modello di sintesi non ha risposto): dillo all'utente e proponi di "
                  "rifare la stessa domanda più tardi. Non ricostruire tu le sezioni mancanti.")


# ---------------------------------------------------------------- cache dei passaggi (per l'archivio)
_cache = {"chiave": None, "passaggi": {}}


def tutti_i_passaggi(ris):
    from archivio import file_risultati
    files = file_risultati(ris, "passaggi.jsonl")
    chiave = tuple((str(f), f.stat().st_mtime) for f in files)
    if chiave != _cache["chiave"]:
        P = {}
        for f in files:
            if escluso(f.parent):
                continue
            for r in f.read_text(encoding="utf-8").splitlines():
                try:
                    p = json.loads(r)
                except ValueError:
                    continue
                P[(p["id"], p["entita"])] = p
        _cache.update(chiave=chiave, passaggi=P)
    return _cache["passaggi"]


# ---------------------------------------------------------------- strumenti
def t_elenca_entita(filtro=""):
    cp = schede.leggi_schede(percorso(cfg(), "entita"))
    f = (filtro or "").lower()
    if not f:      # elenco breve: solo i nomi (l'elenco completo con varianti sarebbe troppo lungo per la chat)
        return {"schede": cp.sections(), "nota": "Per varianti e note richiama con filtro=<nome>."}
    trovate = set(schede.trova_nel_testo(filtro, cp))
    out = []
    for s in cp.sections():
        var = schede.dividi(cp.get(s, "varianti", fallback=""))
        testo = " ".join([s] + var).lower()
        if f and f not in testo and s not in trovate:
            continue
        nota = cp.get(s, "note", fallback="").strip()
        out.append({"scheda": s, "forma_estesa": schede.forma_estesa(cp, s),
                    "varianti": var[:6], "collegate": schede.dividi(cp.get(s, "collegate", fallback="")),
                    "nota": re.split(r"(?<=[.;])\s", nota)[0][:150] if nota else ""})
    return {"schede": out, "totale": len(out),
            "nota": "Per un'entità senza scheda usa crea_scheda (dopo aver chiesto conferma all'utente)."}


def t_crea_scheda(nome, varianti, descrizione="", contesto=None, forme_ambigue=None, collegate=None, tipo="",
                  forma_estesa=""):
    f = percorso(cfg(), "entita")
    sezioni = schede.leggi_schede(f).sections()
    if nome in sezioni:
        return {"scheda": nome, "nota": "esisteva già"}
    sbagliate = [c for c in (collegate or []) if c not in sezioni]
    if sbagliate:
        return {"errore": f"Schede collegate inesistenti: {', '.join(sbagliate)}"}
    return {"scheda": schede.aggiungi_scheda(f, nome, varianti or [nome], descrizione or "", contesto,
                                             forme_ambigue, collegate, tipo, forma_estesa),
            "nota": "Scheda creata in entita.ini. Ora puoi avviare la ricerca."}


# ---------------------------------------------------------------- indice delle fonti
_indice = {"oggetto": None}


def indice_pronto():
    """(indice, None) se l'indice è pronto; altrimenti (None, risposta per la chat). La prima volta ne avvia
    la costruzione in background."""
    import indice as mod_indice
    if _indice["oggetto"] is None:
        c = cfg()
        _indice["oggetto"] = mod_indice.Indice(mod_indice.percorso_indice(c), percorso(c, "dati"))
    ind = _indice["oggetto"]
    if ind.pronto():
        _indice["avviso"] = None
        # fonti aggiunte o corrette dopo la costruzione: si indicizzano solo quei file (controllo ogni 30 s)
        if time.time() - _indice.get("controllato", 0) > 30 and not ind.costruzione.get("aggiornamento"):
            _indice["controllato"] = time.time()
            if not ind.aggiornato():
                try:
                    if not ind.aggiorna(stampa=lambda *a: print(*a, file=sys.stderr), tempo_max=40):
                        ind.aggiorna_in_background()
                except Exception as e:
                    _indice["avviso"] = f"Aggiornamento dell'indice non riuscito ({type(e).__name__}: {e})."
        if ind.costruzione.get("aggiornamento"):
            _indice["avviso"] = ("Indice in aggiornamento per fonti appena aggiunte: i risultati possono non "
                                 "comprendere ancora i file nuovi. Riprova tra qualche minuto.")
            _indice["controllato"] = 0
        return ind, None
    if ind.costruzione["errore"]:
        return None, {"errore": f"Costruzione dell'indice non riuscita: {ind.costruzione['errore']}. "
                                "Dal Prompt dei comandi, nella cartella pipeline: python indice.py costruisci"}
    ind.costruisci_in_background()
    k = ind.costruzione
    return None, {"errore": "Indice delle fonti in costruzione (serve una volta sola, 10-30 minuti): avvisa "
                            "l'utente e riprova più tardi.",
                  "avanzamento": f"{k['fatti']}/{k['totale'] or '?'} file"}


def t_esplora_nome(nome, indizi=None, candidate=None, dal=None, al=None):
    ind, errore = indice_pronto()
    if errore:
        return errore
    import esplora
    r = esplora.esplora_nome(ind, percorso(cfg(), "dati"), nome, indizi, candidate, dal, al)
    if _indice.get("avviso"):
        r["avviso_indice"] = _indice["avviso"]
    return r


def t_cerca_testo(testo, dal=None, al=None, fonti=None, massimo=8, da=0):
    ind, errore = indice_pronto()
    if errore:
        return errore
    import esplora
    r = esplora.cerca_testo(ind, percorso(cfg(), "dati"), testo, dal, al, fonti, massimo, da)
    if _indice.get("avviso") and isinstance(r, dict):
        r["avviso_indice"] = _indice["avviso"]
    return r


# ---------------------------------------------------------------- importazione di nuovo materiale
def cartella_importazioni():
    return percorso(cfg(), "dati").resolve().parent / "importazioni" / "lavori"


def t_importa_fonti(percorso_file, serie, data="", numero="", titolo="", autore="", anno="", volume="",
                    unisci=False, sovrascrivi=False, prova=0):
    """Avvia l'importazione (OCR se serve) come processo indipendente; lo stato con stato_importazione."""
    import importa
    p = Path(os.path.expandvars(os.path.expanduser((percorso_file or "").strip().strip('"'))))
    if not p.exists():
        return {"errore": f"Non trovo «{percorso_file}» su questo computer."}
    if not importa.leggi_serie().has_section(serie):
        return {"errore": f"La serie «{serie}» non è in serie.ini.", "serie": importa.leggi_serie().sections(),
                "nota": "Per una serie nuova usa crea_serie, dopo aver chiesto all'utente i dati."}
    d = cartella_importazioni() / (dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4])
    d.mkdir(parents=True)
    comando = [sys.executable, "-u", str(CARTELLA / "importa.py"), "--lavoro", str(d), "importa", str(p),
               "--serie", serie]
    for k, v in (("data", data), ("numero", numero), ("titolo", titolo), ("autore", autore), ("anno", anno),
                 ("volume", volume)):
        if str(v or "").strip():
            comando += [f"--{k}", str(v).strip()]
    if unisci:
        comando.append("--unisci")
    if sovrascrivi:
        comando.append("--sovrascrivi")
    if prova:
        comando += ["--prova", str(int(prova))]
    (d / "richiesta.json").write_text(json.dumps({"comando": comando[3:], "inizio": time.time()},
                                                 ensure_ascii=False), encoding="utf-8")
    opzioni = dict(cwd=CARTELLA, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
    if os.name == "nt":
        try:
            subprocess.Popen(comando, creationflags=0x08000000 | 0x00000200 | 0x01000000, **opzioni)
        except OSError:
            subprocess.Popen(comando, creationflags=0x08000000 | 0x00000200, **opzioni)
    else:
        subprocess.Popen(comando, start_new_session=True, **opzioni)
    return {"id": d.name, "avviata": True, "prova": bool(prova),
            "nota": "Controlla con stato_importazione (l'OCR richiede da pochi secondi a un minuto per pagina)."}


def t_stato_importazione(id=""):
    base = cartella_importazioni()
    lavori_ = sorted(base.iterdir()) if base.is_dir() else []
    if not lavori_:
        return {"errore": "Nessuna importazione avviata."}
    d = base / id if id else lavori_[-1]
    if not d.is_dir():
        return {"errore": f"Importazione «{id}» non trovata.", "ultime": [x.name for x in lavori_[-5:]]}
    registro = (d / "registro.txt").read_text(encoding="utf-8", errors="replace") if (d / "registro.txt").exists() else ""
    esito = json.loads((d / "esito.json").read_text(encoding="utf-8")) if (d / "esito.json").exists() else None
    righe = registro.strip().splitlines()
    testo = "\n".join(righe[-40:])
    if len(testo) > 4000:
        testo = "…" + testo[-4000:]
    out = {"id": d.name, "finita": esito is not None, "registro": testo}
    if esito:
        out["esito"] = esito
    elif (d / "registro.txt").exists() and time.time() - (d / "registro.txt").stat().st_mtime > 900:
        out["avviso"] = "Nessuna novità da oltre 15 minuti: il processo potrebbe essersi interrotto."
    return out


def t_elenca_serie():
    import importa
    cp = importa.leggi_serie()
    return {"serie": {s_: dict(cp[s_]) for s_ in cp.sections()},
            "nota": "Le serie sono descritte in pipeline\\serie.ini."}


def t_crea_serie(nome, tipo, lingua, cartella, citazione, sigla="", nota_limiti="", autore="", titolo="",
                 luogo="", editore=""):
    import importa
    msg = importa.aggiungi_serie(nome.strip(), tipo.strip(), lingua.strip().lower(), cartella.strip(),
                                 citazione.strip(), sigla.strip(), nota_limiti.strip(), autore=autore,
                                 titolo=titolo, luogo=luogo, editore=editore)
    return {"esito": msg} if msg.startswith("Serie") else {"errore": msg}


def t_avvia_ricerca(entita, collegate=None, modalita="occorrenze", dal=None, al=None, fonti=None, domanda=""):
    c = cfg()
    sezioni = schede.leggi_schede(percorso(c, "entita")).sections()
    if entita not in sezioni:
        simili = [s_ for s_ in sezioni if entita.lower() in s_.lower() or s_.lower() in entita.lower()]
        return {"errore": f"«{entita}» non è una scheda.", "forse": simili[:10]}
    collegate = [x for x in (collegate or []) if x != entita]
    sbagliate = [x for x in collegate if x not in sezioni]
    if sbagliate:
        return {"errore": f"Schede inesistenti: {', '.join(sbagliate)}"}
    i = {"principale": entita, "collegate": collegate,
         "modalita": "evoluzione" if modalita == "evoluzione" or collegate else "occorrenze",
         "dal": int(dal) if dal else None, "al": int(al) if al else None,
         "fonti": [f for f in (fonti or []) if f in FONTI_SCELTE], "seguito": False}
    if i["modalita"] == "evoluzione" and not collegate:
        i = schede.aggiungi_collegate_scheda(i, schede.leggi_schede(percorso(c, "entita")))
    d, s_ = lavori.attivo(c)
    if d:
        if s_.get("parametri") == i:
            return {"avviata": True, "gia_in_corso": True, **compatto(s_)}
        return {"errore": "C'è già una ricerca in corso: attendi_ricerca o ferma_ricerca.", **compatto(s_)}
    d, s_ = lavori.avvia(c, i, (domanda or "").strip() or f"Occorrenze di {entita}", CONFIG)
    return {"avviata": True, "parametri": i, "nota": "Chiama attendi_ricerca finché finito è vero."}


def compatto(s_):
    """Stato del lavoro in poche parole (ogni chiamata costa token al modello della chat)."""
    finito = s_.get("stato") in lavori.FINALI
    fine = s_.get("battito", time.time()) if finito else time.time()      # durata, non tempo trascorso da allora
    out = {"finito": finito, "stato": s_.get("stato"),
           "minuti": round((fine - s_.get("inizio", fine)) / 60)}
    for k in ("fase", "avanzamento", "prossimo_tentativo", "messaggio", "risposta"):
        if s_.get(k):
            out[k] = s_[k]
    if s_.get("stato") == "completata, ma sintesi non generata":
        out["avviso"] = AVVISO_SINTESI
    if s_.get("stato") in ("errore", "interrotta"):
        out["ultimi_messaggi"] = s_.get("ultimi_messaggi", [])[-6:]
    if finito and s_.get("risposta"):
        f = lavori.cartella_risposte(cfg()) / s_["risposta"]
        if f.is_file():
            out["risposta_pronta"] = presentazione(f)
    return out


def t_attendi_ricerca(secondi=75):
    c = cfg()
    d, s_ = lavori.attivo(c)
    if not d:
        d, s_ = lavori.ultimo(c)
        if not d:
            return {"errore": "Nessuna ricerca avviata."}
        return compatto(s_)
    fine = time.time() + max(1, min(int(secondi or 75), 75))
    iniziale = s_.get("stato")
    while time.time() < fine:
        time.sleep(2)
        s_ = lavori.stato_lavoro(d) or s_
        if s_.get("stato") in lavori.FINALI or s_.get("stato") != iniziale:
            break
    return compatto(s_)


def t_ferma_ricerca():
    d, s_ = lavori.attivo(cfg())
    if not d:
        return {"fermata": False, "nota": "Nessuna ricerca in corso."}
    lavori.ferma(d)
    return {"fermata": True, "nota": "Rifacendo la stessa domanda riprende da dove era (archivio unico)."}


def _sezioni_md(testo):
    parti, cur, titolo = {}, [], "0"
    for r in testo.splitlines():
        m = re.match(r"^## (\d+)\.", r)
        if m:
            parti[titolo] = "\n".join(cur)
            titolo, cur = m.group(1), []
        cur.append(r)
    parti[titolo] = "\n".join(cur)
    return parti


def _filtra_anni(sezione, dal, al):
    """Tiene, nelle sezioni 1 e 2, solo le voci dei documenti datati negli anni richiesti."""
    righe = sezione.split("\n")
    if any(r.startswith("### [") for r in righe):                     # sezione 2: blocchi "### [n] ..."
        blocchi = re.split(r"\n(?=### \[)", sezione)
        tenuti = [blocchi[0]] + [x for x in blocchi[1:] if _anno_ok(x.split("\n", 1)[0], dal, al)]
        return "\n".join(tenuti)
    return "\n".join(r for r in righe if not re.match(r"^\s*(\[\d+\]|\d+\.|-|\|)", r) or _anno_ok(r, dal, al))


def _anno_ok(testo, dal, al):
    m = re.search(r"\b(19[4-9]\d)\b", testo)
    if not m:
        return False
    anno = int(m.group(1))
    return (not dal or anno >= int(dal)) and (not al or anno <= int(al))


def _mappa_riferimenti(sez1):
    """Dalla sezione 1 ("[n] Renmin Ribao, 20 aprile 1963, p. 4 (`file`, riga N) — tipo") al riferimento."""
    mappa = {}
    for r in sez1.splitlines():
        m = re.match(r"^\[(\d+)\]\s+(.*?)\s*$", r.strip())
        if m:
            rif = re.sub(r"\s*\(`[^`]*`,\s*riga\s*\d+\)", "", m.group(2)).split(" — ")[0].strip()
            mappa[int(m.group(1))] = rif
    return mappa


_GRUPPO_RIF = re.compile(r"(?:\s*\[\s*\d+(?:\s*[,;]\s*\d+)*\s*\]\.?)+")


def _risolvi(testo, mappa):
    """Sostituisce i rimandi [3][5] o [3, 5] con i riferimenti completi: (Renmin Ribao, ...; Peking Review, ...)."""
    def sost(m):
        numeri = []
        for n in re.findall(r"\d+", m.group(0)):
            if int(n) not in numeri:
                numeri.append(int(n))
        rif = "; ".join(mappa.get(n, f"documento {n}") for n in numeri)
        return f" ({rif})" + ("." if "." in m.group(0) else "")
    return _GRUPPO_RIF.sub(sost, testo)


def presentazione(f, testo_filtro="", max_dati=3500):
    """La risposta della pipeline pronta da presentare in chat: risposta finale, inferenze, dati espliciti e
    limiti, con i riferimenti già scritti per intero."""
    grezzo = f.read_text(encoding="utf-8")
    testo = re.sub(r"<!--.*?-->\s*", "", grezzo, flags=re.DOTALL)
    parti = _sezioni_md(testo)
    mappa = _mappa_riferimenti(parti.get("1", ""))

    def corpo(k):
        righe = parti.get(k, "").split("\n")[1:]          # senza il titolo "## n. ..."
        return "\n".join(righe).strip()

    dati = corpo("3")
    if testo_filtro:
        forme = [x.strip().lower() for x in re.split(r"[;,]", testo_filtro) if x.strip()]
        dati = "\n".join(r for r in dati.split("\n") if not r.startswith("- ") or any(x in r.lower() for x in forme))
    dati = _risolvi(dati, mappa)
    limiti = [_risolvi(r, mappa) for r in corpo("5").split("\n") if r.startswith("- ")]
    limiti = [r[:400] + ("…" if len(r) > 400 else "") for r in limiti]
    out = {"file": f.name,
           "risposta": _risolvi(corpo("7"), mappa),
           "inferenze": _risolvi(corpo("4"), mappa),
           "dati": dati[:max_dati] + ("\n[…altri dati: leggi_risposta sezioni=[3]]" if len(dati) > max_dati else ""),
           "limiti": limiti[:6],
           "nota": "Presenta questa risposta: puoi riordinare, abbreviare e tradurre, non aggiungere fatti né "
                   "cambiare date, cariche o attribuzioni; conserva i riferimenti e le avvertenze sui limiti."}
    if MARCATORE in grezzo:
        out["avviso"] = AVVISO_SINTESI
    return out


def _filtra_testo(sezione, forme):
    """Sezioni 1 e 2: solo le voci che contengono una delle forme (es. un nome dentro la scheda di un partito)."""
    forme = [f.lower() for f in forme if f.strip()]
    if any(r.startswith("### [") for r in sezione.split("\n")):
        blocchi = re.split(r"\n(?=### \[)", sezione)
        return "\n".join([blocchi[0]] + [x for x in blocchi[1:] if any(f in x.lower() for f in forme)])
    righe = sezione.split("\n")
    return "\n".join(r for r in righe if not re.match(r"^\s*(\[\d+\]|\d+\.|-|\|)", r)
                     or any(f in r.lower() for f in forme))


def t_leggi_risposta(file="", sezioni=None, dal=None, al=None, da=0, testo_filtro="", max_caratteri=7000):
    c = lavori.cartella_risposte(cfg())
    if file:
        f = c / Path(file).name
    else:
        _, s_ = lavori.ultimo(cfg())
        f = c / s_["risposta"] if s_ and s_.get("risposta") else None
        if not f or not f.is_file():
            tutti = sorted(c.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)
            f = tutti[0] if tutti else None
    if not f or not f.is_file():
        return {"errore": "Risposta non trovata. Usa elenca_risposte."}
    if not sezioni:               # risposta pronta da presentare (risposta finale, inferenze, dati, limiti)
        return presentazione(f, testo_filtro)
    grezzo = f.read_text(encoding="utf-8")
    senza_sintesi = MARCATORE in grezzo
    testo = re.sub(r"<!--.*?-->\s*", "", grezzo, flags=re.DOTALL)
    parti = _sezioni_md(testo)
    if dal or al:
        for k in ("1", "2"):
            if k in parti:
                parti[k] = _filtra_anni(parti[k], dal, al)
    if testo_filtro:
        forme = [x.strip() for x in re.split(r"[;,]", testo_filtro) if x.strip()]
        for k in ("1", "2"):
            if k in parti:
                parti[k] = _filtra_testo(parti[k], forme)
    testo = "\n\n".join(parti.get(str(s), "") for s in ["0"] + [str(x) for x in sezioni] if parti.get(str(s)))
    da = max(0, int(da or 0))
    fine = da + max_caratteri
    tronca = len(testo) > fine
    extra = {"avviso": AVVISO_SINTESI} if senza_sintesi else {}
    if tronca:
        extra["continua_da"] = fine
    return {**extra, "file": f.name, "percorso": str(f), "testo": testo[da:fine],
            "troncato": tronca, "sezioni_mostrate": sezioni,
            "nota": ("Altre sezioni su richiesta: 1 Documenti, 2 Passaggi originali, 5 Limiti, 6 Copertura, "
                     "8 Dati tecnici (file e righe, solo per apri_fonte). "
                     + (f"Testo NON finito: richiama con da={fine}, oppure chiedi la sezione 2 un periodo alla "
                        "volta con dal/al. Non trarre conclusioni sugli anni che non hai letto." if tronca else ""))}


def t_elenca_risposte(quante=20):
    c = lavori.cartella_risposte(cfg())
    files = sorted(c.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:int(quante or 20)]
    out = []
    for f in files:
        prima = f.read_text(encoding="utf-8")[:500]
        m = re.search(r"<!-- Domanda: (.*?) \|", prima)
        out.append({"file": f.name, "domanda": m.group(1) if m else f.stem,
                    "data": time.strftime("%d/%m/%Y %H:%M", time.localtime(f.stat().st_mtime))})
    return {"risposte": out}


def t_passaggi_archivio(entita, dal=None, al=None, fonti=None, solo_pertinenti=True, massimo=8, da=0):
    c = cfg()
    ris = percorso(c, "risultati")
    arch = Archivio(ris)
    P = tutti_i_passaggi(ris)
    from ricerca import fonte_ammessa
    ammesse = [x for x in fonti or [] if x]
    sel = []
    dati = percorso(c, "dati")
    from date_interne import anno_del_documento
    for (pid, e), v in arch.per_id.items():
        if e != entita:
            continue
        a = v["analisi"]
        if solo_pertinenti and a.get("pertinente") != "sì":
            continue
        p = P.get((pid, e))
        if not p:
            continue
        if ammesse and not fonte_ammessa(p, ammesse):
            continue
        # raccolte: conta la data interna del documento, non l'anno di edizione del volume (lavoro 9)
        anno, di = anno_del_documento(p, dati)
        if anno and ((dal and anno < int(dal)) or (al and anno > int(al))):
            continue
        if (dal or al) and not anno:
            continue
        sel.append((p, a, di))
    sel.sort(key=lambda x: ((x[2] or {}).get("data") or x[0].get("data", ""), x[0]["file"], x[0].get("offset", 0)))
    da, massimo = int(da or 0), min(int(massimo or 8), 15)
    out = []
    from archivio import riga_citazione
    for p, a, di in sel[da:da + massimo]:
        riga = riga_citazione(dati, p["file"], p["riga"], a.get("citazione_testuale", "")) \
            if a.get("citazione_verificata") else p["riga"]
        # riferimento pronto in stile Chicago (pagina solo se nota); file e riga servono a ritrovare il testo e
        # vanno citati come "file, riga N": il numero di riga NON è una pagina
        rif = sintesi_rif(dict(p, analisi=dict(a, pagina=a.get("pagina") or pagina_di(p))))
        v = {"id": p["id"], "riferimento": rif, "data": p.get("data"),
             "file_e_riga": f"{p['file']}, riga {riga}",
             "originale": (a.get("citazione_testuale") or "")[:300] if a.get("citazione_verificata") else "",
             "traduzione": (a.get("traduzione_it") or "")[:300], "sintesi": (a.get("sintesi_it") or "")[:250]}
        if di:                                  # raccolte: data del documento, dedotta (non entra nella citazione)
            v["data_documento"] = f"{di['data']} (dedotta dal testo)"
        if not solo_pertinenti:
            v["pertinente"] = a.get("pertinente")
        out.append(v)
    return {"entita": entita, "totale": len(sel), "mostrati": f"{da + 1}-{da + len(out)}" if out else "0",
            "passaggi": out,
            "nota": ("Solo passaggi già letti in ricerche precedenti; per una copertura completa usa avvia_ricerca. "
                     "Se totale supera i mostrati, richiama con da=" + str(da + massimo)) if sel else
                    "Nessun passaggio di questa entità nell'archivio: usa avvia_ricerca."}


def t_copertura_fonti(dal, al=None):
    """Quanti numeri di ciascuna serie periodica sono presenti negli anni richiesti, e le lacune registrate."""
    import csv
    from collections import Counter, defaultdict
    c = cfg()
    dati = percorso(c, "dati")
    al = int(al or dal)
    anni = range(int(dal), al + 1)
    conta = defaultdict(Counter)
    for d in sorted((dati / "riviste").iterdir()) if (dati / "riviste").is_dir() else []:
        if not d.is_dir():
            continue
        for f in d.iterdir():
            m = re.search(r"(19[4-9]\d)", f.name)
            if m and int(m.group(1)) in anni:
                conta[d.name][int(m.group(1))] += 1
    lacune = Counter()
    fp = percorso(c, "problemi")
    if Path(fp).exists():
        with open(fp, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                m = re.search(r"(19[4-9]\d)", r.get("file", ""))
                if m and int(m.group(1)) in anni and r.get("problema") == "giorno mancante":
                    lacune[(r.get("serie", ""), int(m.group(1)))] += 1
    return {"numeri_presenti": {serie: {str(a): n.get(a, 0) for a in anni} for serie, n in conta.items()},
            "giorni_mancanti": {f"{s_} {a}": n for (s_, a), n in sorted(lacune.items())},
            "nota": "Un numero basso per una serie può dipendere dall'uscita irregolare della testata in quegli anni "
                    "(non necessariamente da una lacuna dell'archivio)."}


def t_apri_fonte(file, riga, contesto=25, testo="", max_caratteri=6000):
    """Testo attorno a una riga. Le righe della Peking Review possono essere lunghissime (pagine intere
    dell'OCR): la riga indicata si mostra attorno a «testo» (se dato), le altre si accorciano, e il totale
    resta entro max_caratteri, così il risultato non viene tagliato dalla chat."""
    dati = percorso(cfg(), "dati").resolve()
    p = (dati / file).resolve()
    if dati not in p.parents or not p.is_file():
        return {"errore": "File non trovato tra le fonti."}
    righe = p.read_text(encoding="utf-8", errors="replace").splitlines()
    riga, k = int(riga), max(0, min(int(contesto or 25), 80))
    tetto = max(1000, min(int(max_caratteri or 6000), 12000))
    a, b = max(1, riga - k), min(len(righe), riga + k)

    def taglia(t, n, centro=""):
        if len(t) <= n:
            return t
        i = t.lower().find(centro.lower()) if centro else -1
        inizio = max(0, (i if i >= 0 else 0) - n // 3)
        return ("…" if inizio else "") + t[inizio:inizio + n] + ("…" if inizio + n < len(t) else "")

    centrale = taglia(righe[riga - 1], tetto // 2, testo) if 0 < riga <= len(righe) else ""
    resto, fuori = tetto - len(centrale), []
    vicine = sorted(range(a, b + 1), key=lambda n: abs(n - riga))
    for n in vicine:
        if n == riga:
            continue
        t = taglia(righe[n - 1], 300)
        if resto - len(t) < 0:
            break
        resto -= len(t)
        fuori.append(n)
    mostrate = sorted(fuori + ([riga] if centrale else []))
    corpo = "\n".join(f"{n}{'>>' if n == riga else ': '} {centrale if n == riga else taglia(righe[n - 1], 300)}"
                      for n in mostrate)
    return {"file": file, "righe": f"{mostrate[0]}-{mostrate[-1]} di {len(righe)}" if mostrate else "",
            "testo": corpo,
            "nota": "Righe lunghe accorciate (…). Per un'altra parte della riga indicata usa testo=<parola>."}


def t_varianti_proposte(entita=""):
    return mod_varianti.proposte(cfg(), entita or None) or {"nota": "Nessuna nuova variante da controllare."}


def t_aggiungi_varianti(entita, varianti):
    mod_varianti.aggiungi(cfg(), entita, [v for v in varianti if v.strip()])
    return {"aggiunte": varianti, "nota": "Rifai la ricerca: verranno letti solo i passaggi nuovi."}


def t_scarta_varianti(entita, varianti):
    mod_varianti.scarta(cfg(), entita, varianti)
    return {"scartate": varianti}


def t_varianti(azione, entita="", forme=None):
    if azione == "elenca":
        return t_varianti_proposte(entita)
    if not entita or not forme:
        return {"errore": "Servono entita e forme."}
    return t_aggiungi_varianti(entita, forme) if azione == "aggiungi" else t_scarta_varianti(entita, forme)


def t_correggi_passaggio(id, entita, pertinente=None, traduzione=None, nota=""):
    c = cfg()
    ris = percorso(c, "risultati")
    arch = Archivio(ris)
    v = arch.per_id.get((id, entita))
    p = tutti_i_passaggi(ris).get((id, entita))
    if not v or not p:
        return {"errore": "Passaggio non trovato nell'archivio (id ed entità come in passaggi_archivio)."}
    a = dict(v["analisi"])
    if pertinente in ("sì", "no", "incerto"):
        a["pertinente"] = pertinente
    if traduzione:
        a["traduzione_it"] = traduzione
    a["motivazione"] = ("Correzione manuale: " + nota).strip() if nota else "Correzione manuale"
    a["corretto_a_mano"] = True
    a["classificato_da"] = "correzione manuale"
    a["corretto_il"] = dt.date.today().isoformat()
    from archivio import livello, provenienza
    prima = provenienza(v["analisi"])
    a["provenienza"] = {"decisione": livello("sessione", "correzione dalla chat"),
                        "lettura": livello("sessione", "correzione dalla chat") if traduzione else prima.get("lettura")}
    arch.aggiungi(p, a, origine="correzione manuale")
    return {"corretto": True, "nota": "La correzione vale per tutte le ricerche successive che ritrovano il passaggio."}


_S, _I, _B = {"type": "string"}, {"type": "integer"}, {"type": "boolean"}
_L = {"type": "array", "items": _S}
_F = {"type": "array", "items": {"type": "string", "enum": FONTI_SCELTE}}
_SEZ = {"type": "array", "items": _I, "description": "1 Documenti 2 Passaggi 3 Dati 4 Inferenze 5 Limiti "
                                                     "6 Copertura 7 Risposta finale 8 Dati tecnici"}

STRUMENTI = {
    "elenca_entita": (t_elenca_entita, "Nome esatto della scheda di una persona, partito o testata.",
                      {"filtro": _S}, []),
    "esplora_nome": (t_esplora_nome, "Entità senza scheda: forme del nome attestate nelle fonti, con conteggi ed "
                     "esempi. Prima di crea_scheda.",
                     {"nome": _S, "indizi": dict(_L, description="paese e partito in cinese e inglese (比利时, Belgium)"),
                      "candidate": dict(_L, description="tue trascrizioni cinesi da verificare"), "dal": _I, "al": _I},
                     ["nome"]),
    "crea_scheda": (t_crea_scheda, "Crea la scheda con le forme confermate dall'utente.",
                    {"nome": _S, "varianti": _L, "contesto": _L, "forme_ambigue": _L, "collegate": _L,
                     "descrizione": _S,
                     "tipo": {"type": "string", "enum": list(schede.TIPI)},
                     "forma_estesa": dict(_S, description="nome per esteso, se il nome della scheda è una sigla")},
                    ["nome", "varianti"]),
    "cerca_testo": (t_cerca_testo, "Ricerca libera di parole in tutte le fonti (senza valutazione di pertinenza).",
                    {"testo": _S, "dal": _I, "al": _I, "fonti": _F, "massimo": _I, "da": _I}, ["testo"]),
    "avvia_ricerca": (t_avvia_ricerca, "Ricerca completa nelle fonti (processo indipendente); poi attendi_ricerca.",
                      {"entita": _S, "collegate": dict(_L, description="altre schede: modalità evoluzione"),
                       "modalita": {"type": "string", "enum": ["occorrenze", "evoluzione"]}, "dal": _I, "al": _I,
                       "fonti": _F, "domanda": dict(_S, description="la domanda dell'utente per intero")}, ["entita"]),
    "attendi_ricerca": (t_attendi_ricerca, "Attende fino a 75 s un cambiamento e dà lo stato della ricerca.",
                        {"secondi": _I}, []),
    "ferma_ricerca": (t_ferma_ricerca, "Ferma la ricerca in corso.", {}, []),
    "leggi_risposta": (t_leggi_risposta, "Legge una risposta salvata (l'ultima se file è vuoto), per sezioni; "
                       "dal/al e testo_filtro (forme separate da ;) filtrano le sezioni 1 e 2, da continua.",
                       {"file": _S, "sezioni": _SEZ, "dal": _I, "al": _I, "da": _I, "testo_filtro": _S}, []),
    "elenca_risposte": (t_elenca_risposte, "Risposte già salvate.", {"quante": _I}, []),
    "passaggi_archivio": (t_passaggi_archivio, "Passaggi già letti di un'entità, con originale, traduzione e "
                          "riferimento. Immediato; da per scorrere.",
                          {"entita": _S, "dal": _I, "al": _I, "fonti": _F, "solo_pertinenti": _B, "massimo": _I,
                           "da": _I}, ["entita"]),
    "copertura_fonti": (t_copertura_fonti, "Numeri presenti di ogni periodico e giorni mancanti in un periodo.",
                        {"dal": _I, "al": _I}, ["dal"]),
    "apri_fonte": (t_apri_fonte, "Testo del file sorgente attorno a una riga; testo centra la riga su una parola.",
                   {"file": _S, "riga": _I, "contesto": _I, "testo": _S}, ["file", "riga"]),
    "varianti": (t_varianti, "Forme del nome proposte durante la lettura: elenca, aggiungi (dopo conferma), scarta.",
                 {"azione": {"type": "string", "enum": ["elenca", "aggiungi", "scarta"]}, "entita": _S, "forme": _L},
                 ["azione"]),
    "importa_fonti": (t_importa_fonti, "Importa PDF, scansioni, .txt o esportazioni PAGE/ALTO XML (Transkribus, "
                      "eScriptorium: cartella di pagine .xml o .zip = un documento) in una serie (OCR se serve); "
                      "prova = solo le prime N pagine, senza scrivere. Poi stato_importazione.",
                      {"percorso_file": dict(_S, description="file o cartella sul computer dell'utente"),
                       "serie": _S, "data": dict(_S, description="AAAA-MM-GG, per un solo file"), "numero": _S,
                       "titolo": _S, "autore": dict(_S, description="Cognome, Nome"), "anno": _S, "volume": _S,
                       "unisci": dict(_B, description="tutti i file diventano un solo documento"),
                       "sovrascrivi": _B, "prova": _I}, ["percorso_file", "serie"]),
    "stato_importazione": (t_stato_importazione, "Avanzamento ed esito di un'importazione (l'ultima se id è vuoto).",
                           {"id": _S}, []),
    "elenca_serie": (t_elenca_serie, "Serie di fonti importabili (serie.ini).", {}, []),
    "crea_serie": (t_crea_serie, "Aggiunge una serie a serie.ini, dopo conferma dell'utente.",
                   {"nome": _S, "tipo": {"type": "string", "enum": ["periodico", "volume"]},
                    "lingua": dict(_S, description="sq, it, fr, en..."),
                    "cartella": dict(_S, description="dentro data, es. riviste/zeri_i_popullit"),
                    "citazione": dict(_S, description="modello, es. Zëri i Popullit, {data}[, n. {numero}]"),
                    "sigla": _S, "nota_limiti": _S, "autore": _S, "titolo": _S, "luogo": _S, "editore": _S},
                   ["nome", "tipo", "lingua", "cartella", "citazione"]),
    "correggi_passaggio": (t_correggi_passaggio, "Registra una correzione dell'utente su un passaggio.",
                           {"id": _S, "entita": _S, "pertinente": {"type": "string", "enum": ["sì", "no", "incerto"]},
                            "traduzione": _S, "nota": _S}, ["id", "entita"]),
}


# ---------------------------------------------------------------- protocollo JSON-RPC
def elenco_strumenti():
    return [{"name": n, "description": d,
             "inputSchema": {"type": "object", "properties": props, "required": req}}
            for n, (_, d, props, req) in STRUMENTI.items()]


def gestisci(msg):
    """Restituisce la risposta JSON-RPC (dict) oppure None per le notifiche."""
    metodo, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None                                   # notifiche (initialized, cancelled, ...)
    try:
        if metodo == "initialize":
            richiesta = (msg.get("params") or {}).get("protocolVersion", VERSIONI_PROTOCOLLO[0])
            ver = richiesta if richiesta in VERSIONI_PROTOCOLLO else VERSIONI_PROTOCOLLO[0]
            ris = {"protocolVersion": ver, "capabilities": {"tools": {"listChanged": False}},
                   "serverInfo": {"name": NOME, "version": VERSIONE}, "instructions": ISTRUZIONI}
        elif metodo == "ping":
            ris = {}
        elif metodo == "tools/list":
            ris = {"tools": elenco_strumenti()}
        elif metodo == "tools/call":
            p = msg.get("params") or {}
            nome, argomenti = p.get("name"), p.get("arguments") or {}
            if nome not in STRUMENTI:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"Strumento sconosciuto: {nome}"}}
            fn, _, props, _ = STRUMENTI[nome]
            try:
                out = fn(**{k: v for k, v in argomenti.items() if k in props})
                errore = isinstance(out, dict) and "errore" in out
                ris = {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, separators=(",", ":"), default=str)}],
                       "isError": errore}
            except Exception as e:
                ris = {"content": [{"type": "text", "text": f"Errore: {type(e).__name__}: {e}"}], "isError": True}
        elif metodo in ("resources/list", "prompts/list"):
            ris = {metodo.split("/")[0]: []}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Metodo non supportato: {metodo}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": ris}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}


def scrivi(obj):
    _PROTOCOLLO.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
    _PROTOCOLLO.flush()


def servi_stdio():
    blocco = threading.Lock()

    def esegui(msg):
        r = gestisci(msg)
        if r is not None:
            with blocco:
                scrivi(r)

    fili = []
    for riga in sys.stdin.buffer:
        riga = riga.strip()
        if not riga:
            continue
        try:
            msg = json.loads(riga.decode("utf-8"))
        except ValueError:
            scrivi({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON non valido"}})
            continue
        for m in (msg if isinstance(msg, list) else [msg]):
            # attendi_ricerca blocca fino a 25 s: ogni richiesta in un thread, così ping e altre chiamate passano
            t = threading.Thread(target=esegui, args=(m,), daemon=True)
            t.start()
            fili.append(t)
        fili = [t for t in fili if t.is_alive()]
    for t in fili:                       # fine dell'input: completa le richieste ancora in corso
        t.join(timeout=60)


def servi_http(porta):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Gestore(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _invia(self, codice, obj=None, extra=None):
            dati = b"" if obj is None else json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(codice)
            if obj is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dati)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(dati)

        def do_GET(self):
            self._invia(405)

        def do_DELETE(self):
            self._invia(200)

        def do_POST(self):
            if self.path.split("?")[0].rstrip("/") != "/mcp":
                return self._invia(404)
            origine = self.headers.get("Origin") or ""
            if origine and not re.match(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$", origine):
                return self._invia(403)
            n = int(self.headers.get("Content-Length") or 0)
            try:
                msg = json.loads(self.rfile.read(n).decode("utf-8"))
            except ValueError:
                return self._invia(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON non valido"}})
            msgs = msg if isinstance(msg, list) else [msg]
            risposte = [r for r in (gestisci(m) for m in msgs) if r is not None]
            extra = {}
            if any(m.get("method") == "initialize" for m in msgs):
                extra["Mcp-Session-Id"] = uuid.uuid4().hex
            if not risposte:
                return self._invia(202, None, extra)
            self._invia(200, risposte if isinstance(msg, list) else risposte[0], extra)

    server = ThreadingHTTPServer(("127.0.0.1", porta), Gestore)
    print(f"Server MCP su http://127.0.0.1:{porta}/mcp  (chiudi la finestra per spegnerlo)", file=sys.stderr)
    server.serve_forever()


def main():
    global CONFIG
    ap = argparse.ArgumentParser(description="Server MCP della ricerca nelle fonti")
    ap.add_argument("--http", type=int, default=None, help="porta per il trasporto HTTP (Open WebUI)")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    CONFIG = args.config
    if args.http:
        servi_http(args.http)
    else:
        servi_stdio()


if __name__ == "__main__":
    main()

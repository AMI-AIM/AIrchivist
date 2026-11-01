#!/usr/bin/env python3
"""
Conversazione sulle fonti (lavoro 38): una conversazione libera con il modello scelto, che usa gli strumenti del
motore (gli stessi del server MCP, con le stesse istruzioni) e non legge le fonti da sé. È un'aggiunta al percorso
guidato dell'interfaccia, non la sua alternativa: i modelli deboli inventano riferimenti quando ricostruiscono una
risposta, perciò ogni citazione della risposta si controlla sui risultati degli strumenti della conversazione.

Modello: il profilo scelto per la sintesi (di solito quello del menu «Modello», che vale per tutti i ruoli).
Servizi: compatibili OpenAI (anche FreeLLMAPI), API di Anthropic, Ollama. Prima della conversazione una prova con
uno strumento finto dice se il modello sa usare gli strumenti; se no, la conversazione resta disattivata con la
spiegazione e resta il percorso guidato.

Strumenti: tutti quelli del server MCP tranne guida (le istruzioni arrivano come messaggio di sistema), modello,
importa e serie, che nell'interfaccia hanno i loro menu e la scheda «Importazioni». ricerca (azione attendi) aspetta
pochi secondi: la ricerca avviata da qui si segue nel riquadro della ricerca. Con sola_lettura gli strumenti che
scrivono restituiscono una risposta simulata (prove dei modelli: nulla entra nell'archivio delle letture).

Verifica delle citazioni (calcolata, nessun giudizio di un modello): nella risposta si cercano le citazioni, cioè un
titolo di fonte (in corsivo nei riferimenti restituiti, o il nome di una serie del progetto) seguito da anno, data o
pagina, e i rimandi di pagina isolati («p. 3»). Ognuna è
  esatta          se compare così com'è (a meno di corsivi, spazi e virgolette) nei risultati degli strumenti;
  corrispondente  se un riferimento restituito ha lo stesso titolo e tutti i suoi numeri (data, pagina);
  non trovata     altrimenti: un riferimento che gli strumenti non hanno dato.

Uso (nella cartella scripts), prova su più modelli, sempre in sola lettura:
  python conversazione.py prova --profili "groq-qwen; freellmapi-auto" [--domanda "..."]
Risultati in results/trials/conversazione/prova_<data-ora>.md, con le conversazioni in .json.
"""
import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.error
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARTELLA))

from llm import LLM, ErroreModello, LimiteRaggiunto   # noqa: E402

ESCLUSI = {"guida", "modello", "importa", "serie"}
SCRIVONO = {("schede", "crea"), ("ricerca", "avvia"), ("ricerca", "ferma"), ("varianti", "aggiungi"),
            ("varianti", "scarta"), ("correggi_passaggio", None)}
MASSIMO_PASSI = 8            # chiamate al modello per ogni domanda dell'utente
TENTATIVI = 5                # richieste ripetute dopo un limite del servizio
MAX_TOKEN = 2500             # lunghezza massima di ogni risposta del modello: i piani gratuiti contano anche
                             # questa nei token al minuto (Groq: 8000), e la sintesi ne chiede molti di più
ATTESA_RICERCA = 10          # secondi massimi di ricerca (azione attendi): la pagina non resta ferma a lungo
VECCHI_RISULTATI = 1500      # caratteri dei risultati di strumenti dei turni precedenti rimandati al modello
LIMITE_RISULTATO = 6000      # caratteri di un risultato della domanda in corso, quando il servizio rifiuta la richiesta
                             # perché troppo grande (poi la metà, poi un quarto)
DOMANDA_PROVA = "Che cosa dicono le fonti di Enrico Berlinguer? Mostrami i passaggi già letti, con i riferimenti."

AGGIUNTA = """Questa conversazione si svolge nell'interfaccia di AIrchivist, accanto al percorso guidato della \
ricerca. Una ricerca avviata da qui (ricerca, azione avvia) si segue nel riquadro della ricerca dell'interfaccia: \
dopo l'avvio chiama attendi una volta sola; se non è finita, di' all'utente che la risposta comparirà in quel \
riquadro e che poi può chiederti di leggerla (risposte, azione leggi). Importazioni, serie e modelli si gestiscono \
dai menu e dalla scheda «Importazioni», non da qui. Scrivi i riferimenti esattamente come li danno gli strumenti: \
l'interfaccia li confronta con i risultati e segnala quelli che non trova."""


class ErroreConversazione(Exception):
    """Il servizio non risponde o rifiuta la richiesta: da mostrare all'utente così com'è."""


class TroppoGrande(ErroreConversazione):
    """La richiesta supera i token che il servizio accetta (errore 413): si riprova con risultati più corti."""


def _facoltativi_nulli(schema):
    """Lo schema con i parametri facoltativi che accettano anche null: alcuni modelli li mandano vuoti (null) e
    alcuni servizi (Groq) rifiutano la chiamata intera se lo schema non lo ammette. esegui toglie i null."""
    richiesti = set(schema.get("required") or [])
    proprieta = {}
    for k, v in (schema.get("properties") or {}).items():
        if k not in richiesti and isinstance(v.get("type"), str):
            v = dict(v, type=[v["type"], "null"])
            if "enum" in v:
                v["enum"] = list(v["enum"]) + [None]
        proprieta[k] = v
    return dict(schema, properties=proprieta)


def strumenti(server):
    """Gli strumenti del server MCP disponibili nella conversazione: {nome, descrizione, schema}."""
    return [{"nome": t["name"], "descrizione": t["description"], "schema": _facoltativi_nulli(t["inputSchema"])}
            for t in server.elenco_strumenti() if t["name"] not in ESCLUSI]


def _argomenti(v):
    if isinstance(v, dict):
        return v
    try:
        v = json.loads(v or "{}")
    except (TypeError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}


def senza_ragionamento(testo):
    """Il testo della risposta senza il ragionamento che alcuni modelli scrivono fra <think> e </think>."""
    return re.sub(r"<think>.*?(</think>|$)", "", testo or "", flags=re.DOTALL).strip()


class Conversazione:
    """Storia della conversazione nel formato OpenAI (senza il messaggio di sistema), convertita per Anthropic e
    Ollama a ogni richiesta; storia visibile (domande, risposte con la verifica delle citazioni) in self.storia."""

    def __init__(self, cfg, server, nome_profilo=None, sola_lettura=False, ruolo="sintesi"):
        self.llm = LLM(cfg, ruolo, nome_profilo)
        self.max_token = min(self.llm.max_token, MAX_TOKEN)
        self.server = server
        self.sola_lettura = sola_lettura
        self.strumenti = strumenti(server)
        self.sistema = server.istruzioni() + "\n\n" + AGGIUNTA
        self.messaggi = []
        self.risultati = []          # testi restituiti dagli strumenti in tutta la conversazione
        self.storia = []
        self.titoli = set()
        try:
            import profili
            self.titoli = {n for n in profili.tutti()}
        except Exception:            # senza progetto: i titoli vengono solo dai riferimenti
            pass

    @property
    def profilo(self):
        return self.llm.profilo

    # ------------------------------------------------------------ richieste al servizio
    def _chiama(self, messaggi, strumenti_):
        """(testo, chiamate) della risposta del modello; chiamate = [{id, nome, argomenti}]. Un limite del servizio
        si aspetta, se dura al massimo un minuto, fino a quattro volte (con i limiti di token al minuto dei piani
        gratuiti, per esempio 8000 su Groq, passa circa una richiesta al minuto);
        una chiamata di strumento che il servizio scarta perché malformata si riprova una volta; ogni altro errore
        diventa ErroreConversazione."""
        funzione = {"anthropic": self._anthropic, "openai": self._openai, "ollama": self._ollama}[self.llm.backend]
        malformate = 0
        for tentativo in range(TENTATIVI):
            try:
                return funzione(messaggi, strumenti_)
            except LimiteRaggiunto as l:
                if tentativo == TENTATIVI - 1 or l.attesa > 60:
                    raise ErroreConversazione(f"Il servizio adesso non accetta richieste ({l.motivo}): riprova tra "
                                              "poco o scegli un altro modello.")
                time.sleep(l.attesa)
            except ErroreModello as e:
                if malformate == 0 and re.search(r"tool_use_failed|tool call validation", str(e), re.IGNORECASE):
                    malformate += 1
                    continue
                if "errore 413" in str(e):
                    raise TroppoGrande(
                        f"La richiesta (istruzioni, strumenti e risultati) supera i token che il servizio accetta per "
                        f"il modello «{self.llm.modello}» con il tuo piano: scegli un modello con limiti più ampi. "
                        f"Dettaglio: {str(e)[:300]}")
                raise ErroreConversazione(str(e))
            except urllib.error.URLError as e:
                raise ErroreConversazione(f"Il servizio non risponde su {self.llm.url} "
                                          f"({getattr(e, 'reason', e)}).")
            except (OSError, ValueError, KeyError, TypeError) as e:
                raise ErroreConversazione(f"Il servizio non ha dato una risposta valida ({type(e).__name__}: {e}).")

    def _openai(self, messaggi, strumenti_):
        corpo = {"model": self.llm.modello, "temperature": 0.2, "max_tokens": self.max_token,
                 "messages": [{"role": "system", "content": self.sistema}] + messaggi}
        if strumenti_:
            corpo["tools"] = [{"type": "function", "function": {"name": s["nome"], "description": s["descrizione"],
                                                                "parameters": s["schema"]}} for s in strumenti_]
            corpo["tool_choice"] = "auto"
        corpo.update(self.llm.extra)
        intest = {"Authorization": f"Bearer {self.llm.chiave}"} if self.llm.chiave else {}
        r, intestazioni = self.llm._post(self.llm.url, corpo, intest)
        self.llm.ultimo_modello = (intestazioni.get("x-routed-via") or r.get("model") or self.llm.modello).strip()
        msg = ((r.get("choices") or [{}])[0].get("message")) or {}
        chiamate = [{"id": tc.get("id") or f"chiamata_{n}", "nome": (tc.get("function") or {}).get("name", ""),
                     "argomenti": _argomenti((tc.get("function") or {}).get("arguments"))}
                    for n, tc in enumerate(msg.get("tool_calls") or [])]
        return msg.get("content") or "", chiamate

    def _anthropic(self, messaggi, strumenti_):
        corpo = {"model": self.llm.modello, "max_tokens": self.max_token, "temperature": 0.2,
                 "system": self.sistema, "messages": per_anthropic(messaggi)}
        if strumenti_:
            corpo["tools"] = [{"name": s["nome"], "description": s["descrizione"], "input_schema": s["schema"]}
                              for s in strumenti_]
        r, _ = self.llm._post(self.llm.url, corpo, {"x-api-key": self.llm.chiave,
                                                    "anthropic-version": "2023-06-01"})
        self.llm.ultimo_modello = r.get("model") or self.llm.modello
        blocchi = r.get("content") or []
        testo = "".join(b.get("text", "") for b in blocchi if b.get("type") == "text")
        chiamate = [{"id": b.get("id"), "nome": b.get("name", ""), "argomenti": _argomenti(b.get("input"))}
                    for b in blocchi if b.get("type") == "tool_use"]
        return testo, chiamate

    def _ollama(self, messaggi, strumenti_):
        corpo = {"model": self.llm.modello, "stream": False, "keep_alive": "15m",
                 "messages": [{"role": "system", "content": self.sistema}] + per_ollama(messaggi),
                 "options": {"temperature": 0.2, "num_ctx": max(self.llm.num_ctx, 8192),
                             "num_predict": self.max_token}}
        if strumenti_:
            corpo["tools"] = [{"type": "function", "function": {"name": s["nome"], "description": s["descrizione"],
                                                                "parameters": s["schema"]}} for s in strumenti_]
        r, _ = self.llm._post(self.llm.url + "/api/chat", corpo, {})
        self.llm.ultimo_modello = r.get("model") or self.llm.modello
        msg = r.get("message") or {}
        chiamate = [{"id": f"chiamata_{n}", "nome": (tc.get("function") or {}).get("name", ""),
                     "argomenti": _argomenti((tc.get("function") or {}).get("arguments"))}
                    for n, tc in enumerate(msg.get("tool_calls") or [])]
        return msg.get("content") or "", chiamate

    # ------------------------------------------------------------ prova
    def prova_strumenti(self):
        """Il modello sa usare gli strumenti? Una richiesta con uno strumento finto: {sa_usare_strumenti, motivo,
        modello}. Se il servizio non risponde, ErroreConversazione (non è una risposta sul modello)."""
        finto = [{"nome": "conta_documenti", "descrizione": "Conta i documenti di una serie di fonti.",
                  "schema": {"type": "object", "properties": {"serie": {"type": "string"}}, "required": ["serie"]}}]
        domanda = [{"role": "user", "content": "Quanti documenti ha la serie «Prova»? Usa lo strumento "
                                               "conta_documenti con serie = \"Prova\"."}]
        sistema, self.sistema = self.sistema, "Rispondi usando gli strumenti disponibili."
        max_token, self.max_token = self.max_token, min(self.max_token, 1500)
        try:
            testo, chiamate = self._chiama(domanda, finto)
        except ErroreConversazione as e:
            if re.search(r"errore 4\d\d", str(e)) and re.search(r"tool|function", str(e), re.IGNORECASE):
                return {"sa_usare_strumenti": False, "modello": self.llm.modello,
                        "motivo": f"il servizio non accetta strumenti per il modello «{self.llm.modello}»"}
            raise
        finally:
            self.sistema, self.max_token = sistema, max_token
        if any(c["nome"] == "conta_documenti" for c in chiamate):
            return {"sa_usare_strumenti": True, "modello": self.llm.ultimo_modello, "motivo": ""}
        return {"sa_usare_strumenti": False, "modello": self.llm.ultimo_modello,
                "motivo": f"il modello «{self.llm.ultimo_modello}» ha risposto con un testo invece di chiamare lo "
                          "strumento: non sa usare gli strumenti, o non in questo servizio"}

    # ------------------------------------------------------------ strumenti
    def esegui(self, nome, argomenti):
        """Testo del risultato di uno strumento, come lo restituisce il server MCP (accorciato entro il limite)."""
        if nome in ESCLUSI or nome not in self.server.STRUMENTI:
            return json.dumps({"errore": f"Strumento non disponibile in questa conversazione: {nome}."},
                              ensure_ascii=False)
        # parametri lasciati vuoti: alcuni modelli mandano null, altri la parola «null» come testo (llama-3.3-70b)
        argomenti = {k: v for k, v in argomenti.items()
                     if v is not None and not (isinstance(v, str) and v.strip().lower() in ("null", "none"))}
        azione = argomenti.get("azione")
        if self.sola_lettura and ((nome, azione) in SCRIVONO or (nome, None) in SCRIVONO):
            return json.dumps({"simulato": True, "nota": "Prova: operazione non eseguita. Riferisci all'utente."},
                              ensure_ascii=False)
        if nome == "ricerca" and azione not in ("avvia", "ferma"):
            try:
                secondi = int(argomenti.get("secondi") or ATTESA_RICERCA)
            except (TypeError, ValueError):
                secondi = ATTESA_RICERCA
            argomenti = dict(argomenti, secondi=max(1, min(secondi, ATTESA_RICERCA)))
        r = self.server.gestisci({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": nome, "arguments": argomenti}})
        if "error" in r:
            return json.dumps({"errore": r["error"]["message"]}, ensure_ascii=False)
        return r["result"]["content"][0]["text"]

    def _accorcia(self, testo, limite, nota):
        """Il risultato entro `limite` caratteri: JSON ancora valido con l'accorciamento del server MCP, se c'è."""
        if len(testo) <= limite:
            return testo
        adatta = getattr(self.server, "adatta", None)
        try:
            dati = json.loads(testo)
            if adatta and isinstance(dati, dict):
                return adatta(dict(dati, nota_conversazione=nota), limite)
        except ValueError:
            pass
        return testo[:limite] + f"…[{nota}]"

    def _da_inviare(self, riduzione=0):
        """La storia per il modello: i risultati dei turni precedenti accorciati (il contesto dei modelli piccoli
        finirebbe presto); quelli della domanda in corso interi o, a ogni `riduzione` (richiesta troppo grande per il
        servizio), entro LIMITE_RISULTATO, la sua metà, il suo quarto."""
        ultima = max((i for i, m in enumerate(self.messaggi) if m["role"] == "user"), default=0)
        out = []
        for i, m in enumerate(self.messaggi):
            if m["role"] == "tool" and i < ultima:
                m = dict(m, content=self._accorcia(m["content"], VECCHI_RISULTATI >> riduzione,
                                                   "accorciato: risultato di una domanda precedente; richiama lo "
                                                   "strumento"))
            elif m["role"] == "tool" and riduzione:
                m = dict(m, content=self._accorcia(m["content"], LIMITE_RISULTATO >> (riduzione - 1),
                                                   "accorciato per il limite di token del servizio: per il resto "
                                                   "richiama lo strumento con da/massimo"))
            out.append(m)
        return out

    # ------------------------------------------------------------ domanda
    def invia(self, testo):
        """Una domanda dell'utente: il modello chiama gli strumenti finché risponde (al massimo MASSIMO_PASSI
        richieste). Restituisce la voce della storia: risposta, citazioni verificate, strumenti usati, modello."""
        testo = (testo or "").strip()
        if not testo:
            raise ErroreConversazione("Scrivi una domanda.")
        inizio = len(self.messaggi)
        self.messaggi.append({"role": "user", "content": testo})
        usati, risposta, modelli, riduzione = [], None, set(), 0
        try:
            for _ in range(MASSIMO_PASSI):
                while True:
                    try:
                        parole, chiamate = self._chiama(self._da_inviare(riduzione), self.strumenti)
                        break
                    except TroppoGrande:
                        if riduzione >= 3 or not any(m["role"] == "tool" for m in self.messaggi):
                            raise
                        riduzione += 1
                modelli.add(self.llm.ultimo_modello)
                if not chiamate:
                    risposta = senza_ragionamento(parole)
                    self.messaggi.append({"role": "assistant", "content": parole or ""})
                    break
                self.messaggi.append({"role": "assistant", "content": parole or "", "tool_calls": [
                    {"id": c["id"], "type": "function",
                     "function": {"name": c["nome"], "arguments": json.dumps(c["argomenti"], ensure_ascii=False)}}
                    for c in chiamate]})
                for c in chiamate:
                    out = self.esegui(c["nome"], c["argomenti"])
                    self.risultati.append(out)
                    usati.append({"nome": c["nome"], "azione": c["argomenti"].get("azione", "")})
                    self.messaggi.append({"role": "tool", "tool_call_id": c["id"], "name": c["nome"],
                                          "content": out})
        except ErroreConversazione:
            del self.messaggi[inizio:]          # la domanda si può rifare: la storia resta coerente
            raise
        voce_utente = {"ruolo": "utente", "testo": testo}
        if risposta is None:
            risposta = ""
            avviso = (f"Il modello non ha concluso la risposta in {MASSIMO_PASSI} passi: riformula la domanda o "
                      "usa il percorso guidato.")
        else:
            avviso = "" if risposta else "Il modello ha restituito una risposta vuota."
        citazioni = verifica_citazioni(risposta, self.risultati, self.titoli)
        voce = {"ruolo": "modello", "testo": risposta, "citazioni": citazioni, "strumenti": usati,
                "modello": ", ".join(sorted(m for m in modelli if m)), "profilo": self.profilo,
                "verifica": conta(citazioni)}
        if avviso:
            voce["avviso"] = avviso
        self.storia += [voce_utente, voce]
        return voce


def per_anthropic(messaggi):
    """Storia OpenAI -> messaggi dell'API di Anthropic: chiamate come blocchi tool_use, risultati come tool_result
    nel messaggio dell'utente che segue (quelli consecutivi nello stesso messaggio)."""
    out = []
    for m in messaggi:
        if m["role"] == "user":
            out.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            blocchi = [{"type": "text", "text": m["content"]}] if m.get("content") else []
            blocchi += [{"type": "tool_use", "id": tc["id"], "name": tc["function"]["name"],
                         "input": _argomenti(tc["function"].get("arguments"))} for tc in m.get("tool_calls") or []]
            out.append({"role": "assistant", "content": blocchi or "…"})
        elif m["role"] == "tool":
            blocco = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
            prima = out[-1] if out else None
            if prima and prima["role"] == "user" and isinstance(prima["content"], list):
                prima["content"].append(blocco)
            else:
                out.append({"role": "user", "content": [blocco]})
    return out


def per_ollama(messaggi):
    """Storia OpenAI -> messaggi di Ollama (argomenti delle chiamate come oggetti, non come testo JSON)."""
    out = []
    for m in messaggi:
        if m["role"] == "assistant" and m.get("tool_calls"):
            out.append({"role": "assistant", "content": m.get("content") or "", "tool_calls": [
                {"function": {"name": tc["function"]["name"], "arguments": _argomenti(tc["function"]["arguments"])}}
                for tc in m["tool_calls"]]})
        elif m["role"] == "tool":
            out.append({"role": "tool", "content": m["content"], "tool_name": m.get("name", "")})
        else:
            out.append({"role": m["role"], "content": m["content"]})
    return out


# ---------------------------------------------------------------- verifica delle citazioni
PAGINA = re.compile(r"\bpp?\.\s*\d+(?:\s*[-–]\s*\d+)?", re.IGNORECASE)
NUMERO = re.compile(r"\d+")
ANNO = re.compile(r"(?<!\d)\d{4}(?!\d)")
DISTANZA = 40                # caratteri massimi fra due numeri della stessa citazione


def _norm(t):
    t = (t or "").replace("*", "").replace("_", " ")
    t = re.sub(r"[“”«»„\"]", '"', t)
    t = re.sub(r"[‘’`]", "'", t)
    t = re.sub(r"[–—]", "-", t)
    return re.sub(r"\s+", " ", t).strip(" .,;:").lower()


def _foglie(nodo, riferimenti, testi, dati=None):
    """Raccoglie dai risultati (JSON) i riferimenti, con il passaggio che li accompagna, e tutte le stringhe."""
    if isinstance(nodo, dict):
        rif = nodo.get("riferimento")
        if isinstance(rif, str) and rif.strip():
            riferimenti.append((rif, {k: nodo[k] for k in ("originale", "traduzione", "data", "data_documento")
                                      if isinstance(nodo.get(k), str) and nodo[k]}))
        for v in nodo.values():
            _foglie(v, riferimenti, testi)
    elif isinstance(nodo, list):
        for v in nodo:
            _foglie(v, riferimenti, testi)
    elif isinstance(nodo, str):
        testi.append(nodo)


def _materiale(risultati):
    riferimenti, testi = [], []
    for r in risultati:
        try:
            _foglie(json.loads(r), riferimenti, testi)
        except (TypeError, ValueError):
            testi.append(r or "")
    return riferimenti, testi


def _schema_titolo(t):
    return re.compile(r"\*?" + r"[\s*]+".join(re.escape(p) for p in t.split()) + r"\*?", re.IGNORECASE)


# fra due numeri della stessa citazione non ci sono: a capo, punto e virgola, il separatore di una tabella, una
# parentesi chiusa seguita da altro testo, la fine di una frase, l'inizio di un altro titolo in corsivo
STACCO = re.compile(r"\n|;|\||\)\s*[.,:]?\s+\D|[.!?]\s+[A-ZÀ-Ý][a-zà-ÿ']*\s|\*\S")
CORSIVO = re.compile(r"(?<!\*)\*([^*\n]{3,80})\*(?!\*)")     # titoli in corsivo, non il grassetto (**...**)


def _fine_catena(testo, da, limite):
    """Fine dell'ultimo numero di una catena di numeri vicini (data, pagina) che parte da `da`; None se nessuno."""
    fine, pos = None, da
    for m in NUMERO.finditer(testo, da, limite):
        if m.start() - pos > DISTANZA or STACCO.search(testo, pos, m.start()):
            break
        fine = pos = m.end()
    return fine


def verifica_citazioni(testo, risultati, titoli_extra=()):
    """Le citazioni della risposta, ciascuna con lo stato (esatta, corrispondente, non trovata) e la posizione nel
    testo: [{testo, inizio, fine, stato, riferimento, passaggio}]."""
    testo = testo or ""
    riferimenti, testi = _materiale(risultati)
    tutti = [_norm(t) for t in testi]
    frammenti = [(r, d) for r, d in riferimenti] + [(riga, {}) for t in testi for riga in t.splitlines()
                                                     if NUMERO.search(riga)]
    titoli = {m.strip() for x in [r for r, _ in riferimenti] + testi for m in CORSIVO.findall(x)}
    titoli |= {t.strip() for t in titoli_extra if len(t.strip()) >= 3}
    candidati = []
    for t in sorted(titoli, key=len, reverse=True):         # i titoli lunghi prima («Peking Review» e «Review»)
        for m in _schema_titolo(t).finditer(testo):
            if any(a <= m.start() < b for a, b, *_ in candidati):
                continue
            limite = min(len(testo), m.end() + 200)
            a_capo = testo.find("\n", m.end(), limite)
            fine = _fine_catena(testo, m.end(), a_capo if a_capo >= 0 else limite)
            if fine is None:
                continue
            pezzo = testo[m.start():fine]
            if not (ANNO.search(pezzo) or PAGINA.search(pezzo)):
                continue
            candidati.append((m.start(), fine, t))
    for m in PAGINA.finditer(testo):                         # rimandi di pagina fuori da una citazione con titolo
        if any(a <= m.start() < b for a, b, *_ in candidati):
            continue
        prima = max([b for a, b, *_ in candidati if b <= m.start()], default=0)
        inizio = max(testo.rfind("\n", 0, m.start()) + 1, testo.rfind("(", 0, m.start()) + 1, m.start() - 80, prima)
        candidati.append((inizio, m.end(), ""))
    out = []
    for a, b, titolo in sorted(candidati):
        pezzo = testo[a:b]
        n = _norm(pezzo)
        numeri = set(NUMERO.findall(pezzo))
        voce = {"testo": pezzo, "inizio": a, "fine": b,
                "stato": "esatta" if n and any(n in t for t in tutti) else "non trovata"}
        simili = [(r, dati) for r, dati in frammenti
                  if numeri and numeri <= set(NUMERO.findall(r)) and (not titolo or _norm(titolo) in _norm(r))]
        if simili:
            # prima un riferimento che contiene la citazione così com'è, poi uno con il passaggio
            r, dati = sorted(simili, key=lambda x: (n not in _norm(x[0]), not x[1]))[0]
            if voce["stato"] == "non trovata":
                voce["stato"] = "corrispondente"
            voce["riferimento"] = r
            if dati:
                voce["passaggio"] = dati
        out.append(voce)
    return out


def conta(citazioni):
    c = {"esatte": 0, "corrispondenti": 0, "non_trovate": 0}
    for v in citazioni:
        c[{"esatta": "esatte", "corrispondente": "corrispondenti"}.get(v["stato"], "non_trovate")] += 1
    return c


# ---------------------------------------------------------------- prova su più modelli
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("prova", help="la stessa domanda a più profili di modello, in sola lettura")
    p.add_argument("--profili", required=True, help="profili di models.ini separati da ;")
    p.add_argument("--domanda", default=DOMANDA_PROVA)
    p.add_argument("--config")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    _uscita = sys.stdout
    import mcp_server as server                 # sposta stdout su stderr per il protocollo: qui non serve
    sys.stdout = _uscita
    from llm import leggi_config, percorso
    server.CONFIG = args.config
    cfg = leggi_config(args.config)
    dest = percorso(cfg, "risultati") / "trials" / "conversazione"
    dest.mkdir(parents=True, exist_ok=True)
    ora = dt.datetime.now().strftime("%Y%m%d-%H%M")
    righe = [f"# Prova della conversazione sulle fonti — {ora}", "", f"Domanda: «{args.domanda}». Strumenti che "
             "scrivono simulati (sola lettura).", "",
             "| Profilo | Modello | Sa usare gli strumenti | Citazioni | esatte | corrispondenti | non trovate "
             "| strumenti | secondi |", "|" + "---|" * 9]
    esito = 0
    for nome in [x.strip() for x in args.profili.split(";") if x.strip()]:
        t0 = time.time()
        dati = {"profilo": nome}
        try:
            c = Conversazione(cfg, server, nome, sola_lettura=True)
            dati["prova_strumenti"] = c.prova_strumenti()
            if dati["prova_strumenti"]["sa_usare_strumenti"]:
                dati["risposta"] = c.invia(args.domanda)
                dati["messaggi"] = c.messaggi
        except (ErroreModello, ErroreConversazione) as e:
            dati["errore"] = str(e)
        secondi = round(time.time() - t0)
        prova, risposta = dati.get("prova_strumenti") or {}, dati.get("risposta") or {}
        v = risposta.get("verifica") or {}
        if v.get("non_trovate"):
            esito = 1
        (dest / f"prova_{ora}_{re.sub(r'[^\w.-]+', '_', nome)}.json").write_text(
            json.dumps(dati, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        righe.append(f"| {nome} | {risposta.get('modello') or prova.get('modello') or dati.get('errore', '')[:60]} | "
                     f"{'—' if not prova else 'sì' if prova['sa_usare_strumenti'] else 'no'} | "
                     f"{len(risposta.get('citazioni') or []) if risposta else '—'} | {v.get('esatte', '—')} | "
                     f"{v.get('corrispondenti', '—')} | {v.get('non_trovate', '—')} | "
                     f"{' > '.join(u['nome'] for u in risposta.get('strumenti') or [])[:80]} | {secondi} |")
        print(righe[-1])
        for x in risposta.get("citazioni") or []:
            print(f"    {x['stato']}: {x['testo']}")
    f = dest / f"prova_{ora}.md"
    f.write_text("\n".join(righe) + "\n", encoding="utf-8")
    print(f"\nRisultati in {f}")
    return esito


if __name__ == "__main__":
    sys.exit(main())

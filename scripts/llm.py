"""
Collegamento ai modelli linguistici. Tipi di servizio:
  anthropic : Claude via API (a pagamento, a consumo)
  openai    : qualsiasi servizio compatibile con il formato OpenAI, compresi quelli con piano gratuito
              (Groq, Google Gemini, OpenRouter) e i server locali (LM Studio, Ollama /v1)
  router    : FreeLLMAPI, router locale che combina più servizi gratuiti (formato OpenAI)
  ollama    : Ollama in locale (API nativa)
Dopo ogni chiamata, 'ultimo_modello' contiene il modello che ha davvero risposto (con un router può
cambiare da una richiesta all'altra); 'modelli_ammessi' rifiuta le risposte di modelli non verificati.

Profili (lavoro 26): ogni modello configurato è una sezione di models.ini (servizio, modello, indirizzo, variabile
della chiave, parametri propri; modello pubblico: models_template.ini). config.ini o project.ini scelgono il profilo
nella sezione [modello]: «profilo» per tutti i ruoli, «smistamento», «analisi», «sintesi» per un ruolo solo.
Senza profilo scelto vale la configurazione precedente: «backend» e le sezioni [anthropic], [openai], [router],
[ollama] di config.ini (installa.py modello converti la trasforma in profili).
Solo libreria standard di Python.
"""
import configparser
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent


def leggi_config(path=None):
    """config.ini del motore e project.ini del progetto di ricerca scelto (progetto.py)."""
    from progetto import leggi_config as lc
    return lc(path)


def percorso(cfg, chiave):
    """Percorso di un file o di una cartella del progetto di ricerca (progetto.py)."""
    from progetto import percorso as p
    return p(cfg, chiave)


class ErroreModello(Exception):
    pass


class ModelloNonAmmesso(ErroreModello):
    pass


class LimiteRaggiunto(Exception):
    def __init__(self, attesa, motivo="limite del servizio raggiunto"):
        self.attesa = attesa
        self.motivo = motivo


RUOLI = ("smistamento", "analisi", "sintesi")
SERVIZI = ("anthropic", "openai", "router", "ollama")
# voci di un profilo che vengono dalla sezione del servizio nella configurazione precedente
VOCI_SERVIZIO = ("url", "chiave_env", "json", "parametri_extra", "pausa_secondi", "num_ctx", "modelli_ammessi")


def _ini():
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#",))
    cp.optionxform = str
    return cp


def file_profili(cfg):
    """models.ini accanto al codice, o il file indicato in [modello] file_profili (relativo alla cartella scripts)."""
    v = Path(cfg.get("modello", "file_profili", fallback="").strip() or "models.ini")
    return v if v.is_absolute() else CARTELLA / v


def leggi_profili(cfg):
    """{nome: {voce: valore}} dei profili di models.ini, nell'ordine del file; {} se il file non c'è."""
    f = file_profili(cfg)
    if not f.exists():
        return {}
    cp = _ini()
    try:
        cp.read(f, encoding="utf-8")
    except configparser.Error as e:
        raise ErroreModello(f"{f} non si legge: {e}")
    return {s: {k: v.strip() for k, v in cp[s].items()} for s in cp.sections()}


def nome_scelto(cfg, ruolo):
    """Profilo scelto per un ruolo in [modello] (voce del ruolo, poi «profilo»); "" con la configurazione precedente."""
    return (cfg.get("modello", ruolo, fallback="").strip() or cfg.get("modello", "profilo", fallback="").strip())


def usa_profili(cfg):
    return any(nome_scelto(cfg, r) for r in RUOLI)


def profilo_precedente(cfg, ruolo, servizio=None):
    """La configurazione precedente ai profili (backend e sezione del servizio) vista come un profilo."""
    servizio = (servizio or cfg.get("modello", "backend", fallback="anthropic")).strip().lower()
    sez = cfg[servizio] if cfg.has_section(servizio) else {}
    p = {"servizio": servizio, "modello": sez.get(f"modello_{ruolo}", "").strip()}
    for k in VOCI_SERVIZIO:
        if sez.get(k, "").strip():
            p[k] = sez.get(k).strip()
    if servizio == "anthropic":
        p.setdefault("chiave_env", "ANTHROPIC_API_KEY")
    return p


# File dei profili fissati all'avvio di una ricerca (ricerca.py lo indica ai suoi sottoprocessi): una ricerca
# interrotta riprende con i profili con cui era partita, anche se nel frattempo la scelta è cambiata.
VARIABILE_FISSATI = "AIRCHIVIST_PROFILI_RICERCA"


def profili_fissati():
    """{ruolo: {"nome", "voci"}} del file indicato in AIRCHIVIST_PROFILI_RICERCA; {} se non c'è."""
    f = os.environ.get(VARIABILE_FISSATI, "").strip()
    if not f:
        return {}
    try:
        return json.loads(Path(f).read_text(encoding="utf-8")).get("ruoli") or {}
    except (OSError, ValueError):
        return {}


def profilo(cfg, ruolo, nome=None):
    """(nome, voci) del profilo da usare per un ruolo: quello fissato all'avvio della ricerca in corso, altrimenti
    quello scelto nella configurazione. Con nome: quel profilo di models.ini, qualunque sia la scelta."""
    if not nome:
        fissato = profili_fissati().get(ruolo)
        if fissato and fissato.get("voci"):
            return fissato["nome"], dict(fissato["voci"])
    nome = nome or nome_scelto(cfg, ruolo)
    if not nome:
        servizio = cfg.get("modello", "backend", fallback="anthropic").strip().lower()
        return f"config.ini [{servizio}]", profilo_precedente(cfg, ruolo, servizio)
    profili = leggi_profili(cfg)
    if nome not in profili:
        elenco = ", ".join(profili) or "nessuno"
        raise ErroreModello(f"Il profilo di modello «{nome}» non esiste in {file_profili(cfg)} (profili: {elenco}). "
                            "Elenco: python installa.py modello elenca; nuovo profilo: python installa.py modello nuovo")
    return nome, profili[nome]


def profili_attivi(cfg):
    """{ruolo: nome del profilo} per i tre ruoli."""
    return {r: profilo(cfg, r)[0] for r in RUOLI}


def profilo_router(cfg):
    """Voci del profilo del router (FreeLLMAPI), per le prove dei modelli: quello scelto per lo smistamento, se è
    un router; altrimenti il primo router di models.ini; altrimenti la sezione [router] della configurazione
    precedente."""
    p = profilo(cfg, "smistamento")[1]
    if p.get("servizio") == "router":
        return dict(p)
    for p in leggi_profili(cfg).values():
        if p.get("servizio") == "router":
            return dict(p)
    p = profilo_precedente(cfg, "smistamento", "router")
    if p.get("url"):
        return p
    raise ErroreModello("Nessun profilo del router (FreeLLMAPI): creane uno con python installa.py modello nuovo")


def catalogo_router(cfg, solo_disponibili=True):
    """Modelli che il router dichiara (GET /models), con i loro dati."""
    p = profilo_router(cfg)
    chiave = os.environ.get(p.get("chiave_env", ""), "") if p.get("chiave_env") else ""
    req = urllib.request.Request(p.get("url", "").rstrip("/") + "/models" + ("?available=true" if solo_disponibili else ""),
                                 headers={"Authorization": f"Bearer {chiave}", "User-Agent": "ricerca-fonti/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("data", [])


class LLM:
    """ruolo = 'smistamento' | 'analisi' | 'sintesi'; nome_profilo: un profilo di models.ini al posto di quello
    scelto nella configurazione (per provarlo prima di sceglierlo)."""

    def __init__(self, cfg, ruolo, nome_profilo=None):
        self.profilo, p = profilo(cfg, ruolo, nome_profilo)
        scelta = p.get("servizio", "").strip().lower()
        if scelta not in SERVIZI:
            raise ErroreModello(f"Servizio sconosciuto nel profilo «{self.profilo}»: «{scelta}» "
                                f"(ammessi: {', '.join(SERVIZI)})")
        # "router" (FreeLLMAPI) usa il formato OpenAI
        self.backend = "openai" if scelta == "router" else scelta
        self.sezione = scelta

        def intero(voce, predefinito):
            v = p.get(voce, "")
            try:
                return int(v) if v else predefinito
            except ValueError:
                raise ErroreModello(f"«{voce}» nel profilo «{self.profilo}» deve essere un numero intero.")

        self.timeout = intero("timeout", cfg.getint("modello", "timeout", fallback=300))
        # lunghezza massima della risposta, per ruolo (i modelli che "ragionano" prima di rispondere ne consumano
        # una parte: con un limite basso il JSON arriva troncato); prima il profilo, poi [modello]
        self.max_token = intero(f"max_token_{ruolo}", intero("max_token", cfg.getint(
            "modello", f"max_token_{ruolo}", fallback=cfg.getint("modello", "max_token", fallback=3000))))
        self.modello = p.get("modello", "").strip()
        if not self.modello:
            raise ErroreModello(f"Manca «modello_{ruolo}» nella sezione [{scelta}] di config.ini."
                                if self.profilo.startswith("config.ini") else
                                f"Manca «modello» nel profilo «{self.profilo}».")
        try:
            self.pausa = float(p.get("pausa_secondi", "0") or 0)
        except ValueError:
            raise ErroreModello(f"«pausa_secondi» nel profilo «{self.profilo}» deve essere un numero.")
        self._ultima = 0.0
        self.ultimo_modello = self.modello
        # parti di nome (minuscole) dei modelli accettati, separate da ";": vuoto = qualsiasi modello
        self.ammessi = [x.strip().lower() for x in p.get("modelli_ammessi", "").replace("；", ";").split(";")
                        if x.strip()]
        nome_env = p.get("chiave_env", "").strip() or ("ANTHROPIC_API_KEY" if scelta == "anthropic" else "")
        self.chiave_env = nome_env
        self.chiave = os.environ.get(nome_env, "") if nome_env else ""
        if nome_env and not self.chiave:
            raise ErroreModello(f"Manca la chiave: imposta la variabile {nome_env} (vedi docs/user_guide.it.md).")
        if self.backend == "anthropic":
            self.url = "https://api.anthropic.com/v1/messages"
        elif self.backend == "openai":
            self.url = p.get("url", "").rstrip("/") + "/chat/completions"
            if not self.url.startswith("http"):
                raise ErroreModello(f"Manca l'indirizzo («url») del servizio nel profilo «{self.profilo}».")
            self.json_mode = p.get("json", "si").strip().lower() in ("si", "sì", "yes", "true", "1")
            try:
                self.extra = json.loads(p.get("parametri_extra", "") or "{}")
            except ValueError:
                raise ErroreModello(f"«parametri_extra» nel profilo «{self.profilo}» non è JSON valido.")
        else:
            self.url = (p.get("url", "") or "http://localhost:11434").rstrip("/")
            self.num_ctx = intero("num_ctx", 4096)
            self.think = False

    # ---------------- controlli ----------------
    def controlla(self):
        if self.sezione == "router":
            base = self.url.rsplit("/chat/completions", 1)[0]
            try:
                urllib.request.urlopen(urllib.request.Request(base + "/models", headers={
                    "Authorization": f"Bearer {self.chiave}", "User-Agent": "ricerca-fonti/1.0"}), timeout=10).close()
            except urllib.error.HTTPError as e:
                if e.code in (401, 403):
                    raise ErroreModello("Il router rifiuta la chiave: controlla FREELLMAPI_KEY (vedi docs/user_guide.it.md).")
            except Exception:
                raise ErroreModello(f"Il router non risponde su {base}. Avvia FreeLLMAPI e riprova.")
            return
        if self.backend != "ollama":
            return
        try:
            with urllib.request.urlopen(self.url + "/api/tags", timeout=10) as r:
                dati = json.load(r)
        except Exception:
            raise ErroreModello(f"Ollama non risponde su {self.url}. Avvia l'applicazione Ollama e riprova.")
        nomi = {m.get("name", "") for m in dati.get("models", [])}
        if self.modello not in nomi and self.modello + ":latest" not in nomi:
            raise ErroreModello(f"Il modello {self.modello} non è installato. Esegui:  ollama pull {self.modello}")

    def prova(self):
        """Prova del collegamento con una richiesta minima, senza attese né nuovi tentativi: il modello che ha
        risposto, oppure ErroreModello con la spiegazione."""
        self.controlla()
        funzione = {"anthropic": self._anthropic, "openai": self._openai, "ollama": self._ollama}[self.backend]
        max_token, timeout = self.max_token, self.timeout
        # pochi token bastano per sapere se il servizio risponde (i modelli che "ragionano" possono restituire
        # un testo vuoto: conta che la richiesta sia accettata)
        self.max_token, self.timeout = min(self.max_token, 200), min(self.timeout, 90)
        try:
            funzione("Rispondi solo con la parola: ok", "Prova di collegamento.", None)
        except LimiteRaggiunto as l:
            raise ErroreModello(f"il servizio risponde ma adesso non accetta richieste ({l.motivo}): "
                                "riprova più tardi o scegli un altro modello")
        except ModelloNonAmmesso:
            raise
        except ErroreModello as e:
            codice = re.search(r"errore (\d{3})", str(e))
            if codice and codice.group(1) in ("401", "403"):
                raise ErroreModello(f"il servizio rifiuta la chiave (variabile {self.chiave_env or 'nessuna'}): "
                                    "controlla che sia copiata per intero e ancora valida")
            if codice and codice.group(1) == "404":
                raise ErroreModello(f"il servizio non trova il modello «{self.modello}» o l'indirizzo {self.url}: "
                                    "controlla il nome esatto nella console del servizio")
            raise
        except urllib.error.URLError as e:
            raise ErroreModello(f"il servizio non risponde su {self.url} ({getattr(e, 'reason', e)}): "
                                "controlla l'indirizzo e che il servizio sia acceso")
        except (OSError, ValueError) as e:      # timeout, connessione chiusa, risposta che non è JSON
            raise ErroreModello(f"il servizio su {self.url} non ha dato una risposta valida ({e})")
        finally:
            self.max_token, self.timeout = max_token, timeout
        return self.ultimo_modello

    # ---------------- HTTP ----------------
    def _post(self, url, corpo, intestazioni):
        req = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "Accept": "application/json",
                                              # alcuni servizi (Cloudflare) rifiutano l'intestazione predefinita di Python
                                              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ricerca-fonti/1.0",
                                              **intestazioni})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return json.load(r), {k.lower(): v for k, v in r.headers.items()}
        except urllib.error.HTTPError as e:
            testo = e.read().decode("utf-8", "replace")
            e.close()
            if e.code in (429, 503, 529):
                attesa = e.headers.get("retry-after") or e.headers.get("Retry-After")
                try:
                    attesa = float(attesa)
                except (TypeError, ValueError):
                    attesa = 20.0
                raise LimiteRaggiunto(min(max(attesa, 2.0), 120.0))
            if e.code in (500, 502, 504):
                # errore temporaneo del servizio (con un router: tutti i tentativi verso i fornitori falliti,
                # spesso per sovraccarico momentaneo): si riprova dopo una breve attesa
                raise LimiteRaggiunto(15.0, f"errore temporaneo del servizio ({e.code})")
            raise ErroreModello(f"Il servizio ha risposto con errore {e.code}: {testo[:400]}")

    # ---------------- backend ----------------
    def _anthropic(self, sistema, utente, schema):
        if schema:
            utente += "\n\nRispondi SOLO con un oggetto JSON conforme a questo schema:\n" + \
                      json.dumps(schema, ensure_ascii=False)
        corpo = {"model": self.modello, "max_tokens": self.max_token, "temperature": 0,
                 "system": sistema, "messages": [{"role": "user", "content": utente}]}
        r, _ = self._post(self.url, corpo, {"x-api-key": self.chiave, "anthropic-version": "2023-06-01"})
        self.ultimo_modello = r.get("model") or self.modello
        return "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")

    def _openai(self, sistema, utente, schema):
        if schema:
            utente += "\n\nRispondi SOLO con un oggetto JSON conforme a questo schema:\n" + \
                      json.dumps(schema, ensure_ascii=False)
        corpo = {"model": self.modello, "temperature": 0, "max_tokens": self.max_token,
                 "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": utente}]}
        if schema and self.json_mode:
            corpo["response_format"] = {"type": "json_object"}
        corpo.update(self.extra)
        intest = {"Authorization": f"Bearer {self.chiave}"} if self.chiave else {}
        try:
            r, intestazioni = self._post(self.url, corpo, intest)
        except ErroreModello as e:
            if self.extra and "400" in str(e) and any(k in str(e) for k in self.extra):
                print(f"    il modello non accetta {list(self.extra)}: riprovo senza")
                self.extra = {}
                return self._openai(sistema, utente.split("\n\nRispondi SOLO")[0], schema)
            if "response_format" in corpo and "400" in str(e):   # servizio senza modalità JSON
                self.json_mode = False
                return self._openai(sistema, utente.split("\n\nRispondi SOLO")[0], schema)
            raise
        # FreeLLMAPI indica il modello usato nell'intestazione X-Routed-Via (servizio/modello);
        # gli altri servizi nel campo "model" della risposta
        self.ultimo_modello = (intestazioni.get("x-routed-via") or r.get("model") or self.modello).strip()
        if self.ammessi and not any(a in self.ultimo_modello.lower() for a in self.ammessi):
            raise ModelloNonAmmesso(
                f"ha risposto un modello non ammesso ({self.ultimo_modello}): togli quel modello dalla catena "
                f"del router oppure aggiungilo a 'modelli_ammessi' ({self.profilo}) dopo averlo verificato con "
                f"valutazione.py")
        scelte = r.get("choices") or [{}]
        return (scelte[0].get("message") or {}).get("content") or ""

    def _ollama(self, sistema, utente, schema):
        corpo = {"model": self.modello, "stream": False, "keep_alive": "15m",
                 "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": utente}],
                 "options": {"temperature": 0, "num_ctx": self.num_ctx, "num_predict": self.max_token}}
        if schema:
            corpo["format"] = schema
        if self.think is not None:
            corpo["think"] = self.think
        try:
            r, _ = self._post(self.url + "/api/chat", corpo, {})
        except ErroreModello as e:
            if "think" in str(e).lower() and self.think is not None:
                self.think = None
                return self._ollama(sistema, utente, schema)
            raise
        self.ultimo_modello = r.get("model") or self.modello
        return r.get("message", {}).get("content", "")

    # ---------------- interfaccia ----------------
    def testo(self, sistema, utente):
        return self._chiama(sistema, utente, None)

    def json(self, sistema, utente, schema):
        return come_oggetto(estrai_json(self._chiama(sistema, utente, schema)), schema)

    def _chiama(self, sistema, utente, schema, tentativi=6):
        funzione = {"anthropic": self._anthropic, "openai": self._openai, "ollama": self._ollama}[self.backend]
        errore, temporanei = None, 0
        for n in range(tentativi):
            attesa = self.pausa - (time.time() - self._ultima)
            if attesa > 0:
                time.sleep(attesa)
            try:
                self._ultima = time.time()
                return funzione(sistema, utente, schema)
            except LimiteRaggiunto as l:
                if l.motivo.startswith("errore temporaneo"):
                    temporanei += 1
                    if temporanei > 2:        # dopo 3 tentativi si lascia il passaggio per il prossimo lancio
                        raise ErroreModello(f"{l.motivo}, ripetuto 3 volte")
                print(f"    {l.motivo}: attendo {l.attesa:.0f} s...")
                time.sleep(l.attesa)
                errore = l.motivo
            except ErroreModello:
                raise
            except Exception as e:      # rete, timeout
                errore = e
                time.sleep(5 * (n + 1))
        raise ErroreModello(f"Chiamata al modello fallita dopo {tentativi} tentativi: {errore}")


def come_oggetto(dati, schema=None):
    """Le chiamate si aspettano un oggetto JSON. Alcuni modelli rispondono con un elenco: [{...}] vale come
    l'oggetto; un elenco di oggetti, se lo schema ha una sola proprietà elenco (es. «risultati»), va sotto di
    essa. Altre forme sono un errore del passaggio, che si riprova, non della ricerca intera."""
    if isinstance(dati, dict):
        return dati
    if isinstance(dati, list) and all(isinstance(x, dict) for x in dati):
        elenchi = [k for k, v in ((schema or {}).get("properties") or {}).items()
                   if isinstance(v, dict) and v.get("type") == "array"]
        if len((schema or {}).get("properties") or {}) == 1 and len(elenchi) == 1:
            return {elenchi[0]: dati}
        if len(dati) == 1:
            return dati[0]
    raise ErroreModello(f"Il modello ha risposto con JSON di forma inattesa ({type(dati).__name__}).")


def estrai_json(testo):
    testo = re.sub(r"<think>.*?</think>", "", testo or "", flags=re.DOTALL)
    testo = re.sub(r"^```(?:json)?|```$", "", testo.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(testo)
    except Exception:
        pass
    # il modello a volte aggiunge parole attorno al JSON ("Ecco:", note finali, due oggetti in fila):
    # si prende il primo blocco {..} o [..] con parentesi bilanciate, ignorando le stringhe fra virgolette
    inizio = min((i for i in (testo.find("{"), testo.find("[")) if i >= 0), default=-1)
    if inizio >= 0:
        apri_chiuso = {"{": "}", "[": "]"}
        chiudi = apri_chiuso[testo[inizio]]
        depth, in_str, scapp = 0, False, False
        for i in range(inizio, len(testo)):
            ch = testo[i]
            if in_str:
                if scapp:
                    scapp = False
                elif ch == "\\":
                    scapp = True
                elif ch == '"':
                    in_str = False
            elif ch == '"':
                in_str = True
            elif ch == testo[inizio]:
                depth += 1
            elif ch == chiudi:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(testo[inizio:i + 1])
                    except Exception:
                        break
    m = re.search(r"\{.*\}", testo, re.DOTALL)   # ultima prova: dal primo { all'ultimo }
    if not m:
        raise ErroreModello("La risposta del modello non contiene JSON.")
    try:
        return json.loads(m.group(0))
    except Exception:
        raise ErroreModello("La risposta del modello contiene JSON non valido (forse troncato).")

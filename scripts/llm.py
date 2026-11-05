"""
Collegamento ai modelli linguistici. Tipi di servizio:
  anthropic : Claude via API (a pagamento, a consumo)
  openai    : qualsiasi servizio compatibile con il formato OpenAI, compresi quelli con piano gratuito
              (Groq, Google Gemini, OpenRouter) e i server locali (LM Studio, Ollama /v1)
  router    : FreeLLMAPI, router locale che combina più servizi gratuiti (formato OpenAI)
  ollama    : Ollama in locale (API nativa)
Dopo ogni chiamata, 'ultimo_modello' contiene il modello che ha davvero risposto (con un router può
cambiare da una richiesta all'altra); 'modelli_ammessi' rifiuta le risposte di modelli non verificati.

Profili: ogni modello configurato è una sezione di models.ini (servizio, modello, indirizzo, variabile
della chiave, parametri propri; modello pubblico: models_template.ini). config.ini o project.ini scelgono il profilo
nella sezione [modello]: «profilo» per tutti i ruoli, «smistamento», «analisi», «sintesi» per un ruolo solo.
Senza profilo scelto vale la configurazione precedente: «backend» e le sezioni [anthropic], [openai], [router],
[ollama] di config.ini (installa.py modello converti la trasforma in profili).

Attese: un'attesa più lunga di «avviso_dopo» secondi si annuncia con il motivo; dopo
«ferma_dopo» secondi senza una risposta la chiamata si ferma (ServizioFermo) e la ricerca si rilancia più tardi.
Lo stesso oggetto LLM si può usare da più thread («paralleli» richieste contemporanee): la pausa tra le richieste
vale per tutte, e ultimo_modello è quello della richiesta del thread che lo legge.
Solo libreria standard di Python.
"""
import configparser
import json
import os
import re
import socket
import sys
import threading
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


class ServizioFermo(ErroreModello):
    """Nessuna risposta utile per più di «ferma_dopo» secondi: la lettura si ferma e si riprende con un nuovo lancio,
    invece di restare ferma senza dire nulla."""
    pass


class LimiteRaggiunto(Exception):
    def __init__(self, attesa, motivo="limite del servizio raggiunto", tipo="rate_limit"):
        self.attesa = attesa
        self.motivo = motivo
        self.tipo = tipo  # "rate_limit", "connection_error", "service_error"


class TimeoutException(Exception):
    """Timeout separato per connessione vs risposta."""
    def __init__(self, tipo="risposta"):
        self.tipo = tipo  # "connessione" o "risposta"


RUOLI = ("smistamento", "analisi", "sintesi")
# risposte da richiedere di nuovo: senza JSON, JSON troncato, forma inattesa (llm.json)
FORMA_INATTESA = re.compile(r"forma inattesa|non contiene JSON|JSON non valido")
TENTATIVI_FORMA = 3
# secondi senza risposta dopo i quali l'attesa si annuncia, e dopo i quali la chiamata si ferma
AVVISO_DOPO, FERMA_DOPO = 120, 600
# timeout predefinito dello smistamento con un router: meglio un nuovo tentativo, che il router può mandare a un altro
# fornitore, che cinque minuti di attesa su una richiesta che nessuno serve
TIMEOUT_ROUTER = 120


def avviso(testo):
    """Una riga sullo schermo con una sola scrittura: con più thread le righe di print() si mescolano."""
    sys.stdout.write(testo + "\n")
    sys.stdout.flush()
SERVIZI = ("anthropic", "openai", "router", "ollama")
# voci di un profilo che vengono dalla sezione del servizio nella configurazione precedente
VOCI_SERVIZIO = ("url", "chiave_env", "json", "parametri_extra", "pausa_secondi", "num_ctx", "modelli_ammessi")


def _ini():
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#",))
    cp.optionxform = str
    return cp


def file_profili(cfg):
    """models.ini dell'utente (accanto al codice nel modo sviluppo, posizioni.py), o il file indicato in [modello]
    file_profili (relativo alla stessa cartella)."""
    from posizioni import cartella_dati
    v = Path(cfg.get("modello", "file_profili", fallback="").strip() or "models.ini")
    return v if v.is_absolute() else cartella_dati() / v


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
VARIABILE_FISSATI = "PRESSMARK_PROFILI_RICERCA"


def profili_fissati():
    """{ruolo: {"nome", "voci"}} del file indicato in PRESSMARK_PROFILI_RICERCA; {} se non c'è."""
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
                                 headers={"Authorization": f"Bearer {chiave}", "User-Agent": "Pressmark/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r).get("data", [])


class LLM:
    """ruolo = 'smistamento' | 'analisi' | 'sintesi'; nome_profilo: un profilo di models.ini al posto di quello
    scelto nella configurazione (per provarlo prima di sceglierlo)."""
    # conteggi per il registro della ricerca: richieste inviate, secondi passati ad aspettare la risposta del
    # modello e secondi di attesa del motore (pause, limiti del servizio, errori), risposte da richiedere di nuovo.
    # Con più richieste in parallelo i secondi si sommano: possono superare la durata della lettura.
    richieste = 0
    secondi_modello = 0.0
    secondi_attesa = 0.0
    risposte_scartate = 0
    # valori predefiniti (__init__ li prende dal profilo)
    avviso_dopo, ferma_dopo, paralleli = AVVISO_DOPO, FERMA_DOPO, 1
    _blocco, _locale = threading.Lock(), threading.local()

    @property
    def ultimo_modello(self):
        """Il modello che ha risposto all'ultima richiesta di questo thread."""
        return getattr(self._locale, "modello", self.modello)

    @ultimo_modello.setter
    def ultimo_modello(self, valore):
        self._locale.modello = valore

    def _registra_consumo(self, ingresso, uscita, cache=0):
        """Una riga per richiesta riuscita: giorno, servizio, modello, ruolo e token (0 se il servizio non li dice).
        Un errore di scrittura non ferma la lettura: il contatore è un'informazione, non una prova."""
        if not self._file_consumo:
            return
        try:
            from archivio import append_jsonl
            self._file_consumo.parent.mkdir(parents=True, exist_ok=True)
            append_jsonl(self._file_consumo, [json.dumps({
                "giorno": time.strftime("%Y-%m-%d"), "ora": time.strftime("%H:%M:%S"), "servizio": self.servizio,
                "profilo": self.profilo, "modello": self.ultimo_modello, "ruolo": self.ruolo,
                "ingresso": int(ingresso or 0), "uscita": int(uscita or 0), "cache": int(cache or 0)},
                ensure_ascii=False)])
        except Exception:
            pass

    def _conta(self, voce, quanto):
        with self._blocco:
            setattr(self, voce, getattr(self, voce) + quanto)

    def __init__(self, cfg, ruolo, nome_profilo=None):
        self._blocco, self._locale = threading.Lock(), threading.local()
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

        # timeout breve del router solo per lo smistamento, che chiede risposte corte: analisi a lotti e sintesi
        # generano migliaia di token e con 120 s non arrivano mai (prova F, 4/11/2026: sintesi fermata dopo 5 tentativi)
        self.timeout = intero("timeout", min(cfg.getint("modello", "timeout", fallback=300), TIMEOUT_ROUTER)
                              if scelta == "router" and ruolo == "smistamento"
                              else cfg.getint("modello", "timeout", fallback=300))
        self.avviso_dopo = intero("avviso_dopo", cfg.getint("modello", "avviso_dopo", fallback=AVVISO_DOPO))
        self.ferma_dopo = intero("ferma_dopo", cfg.getint("modello", "ferma_dopo", fallback=FERMA_DOPO))
        # richieste contemporanee: con un router, che smista su più fornitori, ne partono 3; con un servizio
        # solo una, salvo che il profilo o [modello] dicano altrimenti
        self.paralleli = max(1, intero("paralleli", cfg.getint("modello", "paralleli",
                                                               fallback=3 if scelta == "router" else 1)))
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
        # consumo di richieste e token, giorno per giorno: system/usage.jsonl del progetto (il contatore dell'interfaccia)
        self.ruolo, self.servizio = ruolo, scelta
        try:
            from progetto import percorso as _percorso
            self._file_consumo = _percorso(cfg, "lavori").parent / "usage.jsonl"
        except Exception:                      # senza progetto (prove di collegamento): non si registra
            self._file_consumo = None
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
                    "Authorization": f"Bearer {self.chiave}", "User-Agent": "Pressmark/1.0"}), timeout=10).close()
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

    def prova(self, secondi=60):
        """Prova del collegamento con una richiesta minima, senza attese né nuovi tentativi: il modello che ha
        risposto, oppure ErroreModello con la spiegazione. Serve anche prima di una lettura: un router può
        rispondere a /models e non ancora alle richieste."""
        self.controlla()
        funzione = {"anthropic": self._anthropic, "openai": self._openai, "ollama": self._ollama}[self.backend]
        timeout = self.timeout
        self.timeout = min(self.timeout, secondi)      # 60 s: una prova resta breve
        try:
            # pochi token bastano per sapere se il servizio risponde (i modelli che "ragionano" possono restituire
            # un testo vuoto: conta che la richiesta sia accettata)
            funzione("Rispondi solo con la parola: ok", "Prova di collegamento.", None, min(self.max_token, 200))
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
        except TimeoutException as t:
            raise ErroreModello(f"il servizio su {self.url} non ha risposto entro {self.timeout:.0f} s "
                                f"(timeout della {t.tipo})")
        except (OSError, ValueError) as e:      # timeout, connessione chiusa, risposta che non è JSON
            raise ErroreModello(f"il servizio su {self.url} non ha dato una risposta valida ({e})")
        finally:
            self.timeout = timeout
        return self.ultimo_modello

    # ---------------- HTTP ----------------
    def _post(self, url, corpo, intestazioni):
        req = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"),
                                     headers={"Content-Type": "application/json", "Accept": "application/json",
                                              # alcuni servizi (Cloudflare) rifiutano l'intestazione predefinita di Python
                                              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Pressmark/1.0",
                                              **intestazioni})
        try:
            # il timeout vale per ogni attesa sul collegamento, compresa quella della risposta intera (senza
            # streaming il modello non manda nulla finché non ha finito): deve restare quello del profilo
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
                    attesa = 20.0          # quota senza indicazione: i piani gratuiti si liberano in decine di secondi
                raise LimiteRaggiunto(min(max(attesa, 2.0), 120.0))
            if e.code in (500, 502, 504):
                # attesa più breve e incremento rapido per i tentativi
                raise LimiteRaggiunto(2.0, f"errore temporaneo del servizio ({e.code})")
            raise ErroreModello(f"Il servizio ha risposto con errore {e.code}: {testo[:400]}")
        except urllib.error.URLError as e:
            # solo il timeout del collegamento diventa TimeoutException; servizio spento, indirizzo sbagliato e
            # simili restano URLError, che prova() spiega («il servizio non risponde»)
            if isinstance(e.reason, (socket.timeout, TimeoutError)):
                raise TimeoutException("connessione")
            raise
        except (socket.timeout, TimeoutError):
            raise TimeoutException("risposta")

    # ---------------- backend ----------------
    # max_token: la lunghezza massima di questa risposta (più lunga per una lettura a lotti)
    def _anthropic(self, sistema, utente, schema, max_token):
        if schema:
            utente += "\n\nRispondi SOLO con un oggetto JSON conforme a questo schema:\n" + \
                      json.dumps(schema, ensure_ascii=False)
        corpo = {"model": self.modello, "max_tokens": max_token, "temperature": 0,
                 "system": sistema, "messages": [{"role": "user", "content": utente}]}
        r, _ = self._post(self.url, corpo, {"x-api-key": self.chiave, "anthropic-version": "2023-06-01"})
        self.ultimo_modello = r.get("model") or self.modello
        u = r.get("usage") or {}
        self._registra_consumo(u.get("input_tokens"), u.get("output_tokens"), u.get("cache_read_input_tokens"))
        return "".join(b.get("text", "") for b in r.get("content", []) if b.get("type") == "text")

    def _openai(self, sistema, utente, schema, max_token):
        if schema:
            utente += "\n\nRispondi SOLO con un oggetto JSON conforme a questo schema:\n" + \
                      json.dumps(schema, ensure_ascii=False)
        corpo = {"model": self.modello, "temperature": 0, "max_tokens": max_token,
                 "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": utente}]}
        if schema and self.json_mode:
            corpo["response_format"] = {"type": "json_object"}
        corpo.update(self.extra)
        intest = {"Authorization": f"Bearer {self.chiave}"} if self.chiave else {}
        try:
            r, intestazioni = self._post(self.url, corpo, intest)
        except ErroreModello as e:
            if self.extra and "400" in str(e) and any(k in str(e) for k in self.extra):
                avviso(f"    il modello non accetta {list(self.extra)}: riprovo senza")
                self.extra = {}
                return self._openai(sistema, utente.split("\n\nRispondi SOLO")[0], schema, max_token)
            if "response_format" in corpo and "400" in str(e):   # servizio senza modalità JSON
                self.json_mode = False
                return self._openai(sistema, utente.split("\n\nRispondi SOLO")[0], schema, max_token)
            raise
        # FreeLLMAPI indica il modello usato nell'intestazione X-Routed-Via (servizio/modello);
        # gli altri servizi nel campo "model" della risposta
        self.ultimo_modello = (intestazioni.get("x-routed-via") or r.get("model") or self.modello).strip()
        if self.ammessi and not any(a in self.ultimo_modello.lower() for a in self.ammessi):
            raise ModelloNonAmmesso(
                f"ha risposto un modello non ammesso ({self.ultimo_modello}): togli quel modello dalla catena "
                f"del router oppure aggiungilo a 'modelli_ammessi' ({self.profilo}) dopo averlo verificato con "
                f"valutazione.py")
        u = r.get("usage") or {}
        self._registra_consumo(u.get("prompt_tokens"), u.get("completion_tokens"),
                               (u.get("prompt_tokens_details") or {}).get("cached_tokens"))
        scelte = r.get("choices") or [{}]
        return (scelte[0].get("message") or {}).get("content") or ""

    def _ollama(self, sistema, utente, schema, max_token):
        corpo = {"model": self.modello, "stream": False, "keep_alive": "15m",
                 "messages": [{"role": "system", "content": sistema}, {"role": "user", "content": utente}],
                 "options": {"temperature": 0, "num_ctx": self.num_ctx, "num_predict": max_token}}
        if schema:
            corpo["format"] = schema
        if self.think is not None:
            corpo["think"] = self.think
        try:
            r, _ = self._post(self.url + "/api/chat", corpo, {})
        except ErroreModello as e:
            if "think" in str(e).lower() and self.think is not None:
                self.think = None
                return self._ollama(sistema, utente, schema, max_token)
            raise
        self.ultimo_modello = r.get("model") or self.modello
        self._registra_consumo(r.get("prompt_eval_count"), r.get("eval_count"))
        return r.get("message", {}).get("content", "")

    # ---------------- interfaccia ----------------
    def testo(self, sistema, utente):
        return self._chiama(sistema, utente, None)

    def json(self, sistema, utente, schema, tentativi_forma=TENTATIVI_FORMA, max_token=None):
        """La risposta come oggetto JSON. Una risposta senza JSON o di forma inattesa (un elenco di più oggetti al
        posto dell'oggetto) si richiede di nuovo, fino a tentativi_forma volte: con un router la richiesta nuova
        può andare a un altro modello della catena. Solo dopo l'ultimo tentativo il passaggio resta da leggere.
        max_token: lunghezza massima di questa risposta, al posto di quella del profilo."""
        for n in range(tentativi_forma):
            try:
                risposta = (self._chiama(sistema, utente, schema) if max_token is None else
                            self._chiama(sistema, utente, schema, max_token=max_token))
                return come_oggetto(estrai_json(risposta), schema)
            except ErroreModello as e:
                if not FORMA_INATTESA.search(str(e)) or n == tentativi_forma - 1:
                    raise
                self._conta("risposte_scartate", 1)
                avviso(f"    risposta del modello non utilizzabile ({e}): la richiedo di nuovo")

    def _turno(self):
        """Secondi da aspettare prima della prossima richiesta perché tra due richieste passino almeno pausa_secondi,
        anche con più thread: ogni thread prenota il suo turno."""
        with self._blocco:
            ora = time.time()
            turno = max(ora, self._ultima + self.pausa)
            self._ultima = turno
            return turno - ora

    def _chiama(self, sistema, utente, schema, tentativi=6, max_token=None):
        funzione = {"anthropic": self._anthropic, "openai": self._openai, "ollama": self._ollama}[self.backend]
        errore, temporanei = None, 0
        attesa_temporanea = 2.0  # attesa iniziale per errori temporanei
        inizio, finito = time.time(), threading.Event()
        motivo = ["attendo la risposta del modello"]

        def aspetta(secondi, perche):   # ogni attesa del motore entra nel registro della ricerca
            motivo[0] = perche
            self._conta("secondi_attesa", secondi)
            time.sleep(secondi)

        def sorveglia():                # un'attesa lunga si annuncia, con il motivo
            while not finito.wait(self.avviso_dopo):
                avviso(f"    nessuna risposta da {(time.time() - inizio) / 60:.0f} min ({motivo[0]}); la lettura si "
                      f"ferma dopo {self.ferma_dopo / 60:.0f} min")

        if self.avviso_dopo > 0:
            threading.Thread(target=sorveglia, daemon=True).start()
        try:
            for n in range(tentativi):
                if n and time.time() - inizio > self.ferma_dopo:
                    raise ServizioFermo(f"il servizio non dà risposte utili da {(time.time() - inizio) / 60:.0f} min "
                                        f"(ultimo errore: {errore}): rilancia lo stesso comando più tardi, riprende "
                                        "da dove era arrivata")
                attesa = self._turno()
                if attesa > 0:
                    aspetta(attesa, "pausa tra le richieste")
                motivo[0] = "attendo la risposta del modello" + (f", tentativo {n + 1}" if n else "")
                t0 = time.time()
                self._conta("richieste", 1)
                try:
                    try:
                        return funzione(sistema, utente, schema, max_token or self.max_token)
                    finally:
                        self._conta("secondi_modello", time.time() - t0)
                except LimiteRaggiunto as l:
                    if l.motivo.startswith("errore temporaneo") or l.tipo == "service_error":
                        temporanei += 1
                        if temporanei > 2:        # dopo 3 tentativi si lascia il passaggio per il prossimo lancio
                            raise ErroreModello(f"{l.motivo}, ripetuto 3 volte")
                        # attesa che cresce con i tentativi (2, 4, 8 s)
                        attesa_temporanea = min(2.0 * (2 ** (temporanei - 1)), 15.0)
                    pausa = max(l.attesa, attesa_temporanea)
                    avviso(f"    {l.motivo}: attendo {pausa:.0f} s...")
                    aspetta(pausa, l.motivo)
                    errore = l.motivo
                except TimeoutException as t:
                    # timeout diversi per connessione vs risposta
                    errore = f"nessuna risposta entro {self.timeout} s (timeout della {t.tipo})"
                    avviso(f"    {errore}: riprovo")
                    # retry veloce per problemi di rete
                    aspetta(min(2 ** n, 10) if t.tipo == "connessione" else min(5 * (n + 1), 30), errore)
                except ErroreModello:
                    raise
                except Exception as e:      # rete, altri errori
                    errore = e
                    aspetta(min(5 * (n + 1), 30), f"errore di collegamento: {e}")  # attesa progressiva, max 30 s
            raise ErroreModello(f"Chiamata al modello fallita dopo {tentativi} tentativi: {errore}")
        finally:
            finito.set()


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

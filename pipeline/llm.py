"""
Collegamento ai modelli linguistici. Tre tipi di servizio ("backend"), scelti in config.ini:
  anthropic : Claude via API (a pagamento, a consumo)
  openai    : qualsiasi servizio compatibile con il formato OpenAI, compresi quelli con piano gratuito
              (Groq, Google Gemini, OpenRouter), i router locali che li combinano (FreeLLMAPI)
              e i server locali (LM Studio, Ollama /v1)
Dopo ogni chiamata, 'ultimo_modello' contiene il modello che ha davvero risposto (con un router può
cambiare da una richiesta all'altra); 'modelli_ammessi' in config.ini rifiuta le risposte di modelli non verificati.
  ollama    : Ollama in locale (API nativa)
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
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#",))
    cp.read(path or CARTELLA / "config.ini", encoding="utf-8")
    return cp


def percorso(cfg, chiave):
    p = Path(cfg.get("percorsi", chiave))
    return p if p.is_absolute() else (CARTELLA / p).resolve()


class ErroreModello(Exception):
    pass


class ModelloNonAmmesso(ErroreModello):
    pass


class LimiteRaggiunto(Exception):
    def __init__(self, attesa, motivo="limite del servizio raggiunto"):
        self.attesa = attesa
        self.motivo = motivo


class LLM:
    """ruolo = 'smistamento' | 'analisi' | 'sintesi'"""

    def __init__(self, cfg, ruolo):
        scelta = cfg.get("modello", "backend", fallback="anthropic").strip().lower()
        if scelta not in ("anthropic", "openai", "ollama", "router"):
            raise ErroreModello(f"Backend sconosciuto: {scelta}")
        sez = cfg[scelta] if cfg.has_section(scelta) else {}
        # "router" (FreeLLMAPI) usa il formato OpenAI, con le impostazioni della sezione [router]
        self.backend = "openai" if scelta == "router" else scelta
        self.sezione = scelta
        self.timeout = cfg.getint("modello", "timeout", fallback=300)
        # lunghezza massima della risposta, per ruolo (i modelli che "ragionano" prima di rispondere ne consumano
        # una parte: con un limite basso il JSON arriva troncato)
        self.max_token = cfg.getint("modello", f"max_token_{ruolo}",
                                    fallback=cfg.getint("modello", "max_token", fallback=3000))
        self.modello = sez.get(f"modello_{ruolo}", "").strip()
        if not self.modello:
            raise ErroreModello(f"Manca 'modello_{ruolo}' nella sezione [{scelta}] di config.ini.")
        self.pausa = float(sez.get("pausa_secondi", "0") or 0)
        self._ultima = 0.0
        self.ultimo_modello = self.modello
        # parti di nome (minuscole) dei modelli accettati, separate da ";": vuoto = qualsiasi modello
        self.ammessi = [x.strip().lower() for x in sez.get("modelli_ammessi", "").replace("；", ";").split(";")
                        if x.strip()]
        if self.backend == "anthropic":
            self.url = "https://api.anthropic.com/v1/messages"
            self.chiave = os.environ.get("ANTHROPIC_API_KEY", "")
            if not self.chiave:
                raise ErroreModello("Manca la chiave: imposta la variabile ANTHROPIC_API_KEY (vedi ISTRUZIONI.md).")
        elif self.backend == "openai":
            self.url = sez.get("url", "").rstrip("/") + "/chat/completions"
            nome_env = sez.get("chiave_env", "").strip()
            self.chiave = os.environ.get(nome_env, "") if nome_env else ""
            if nome_env and not self.chiave:
                raise ErroreModello(f"Manca la chiave: imposta la variabile {nome_env} (vedi ISTRUZIONI.md).")
            self.json_mode = sez.get("json", "si").strip().lower() in ("si", "sì", "yes", "true", "1")
            try:
                self.extra = json.loads(sez.get("parametri_extra", "") or "{}")
            except ValueError:
                raise ErroreModello("'parametri_extra' in config.ini non è JSON valido.")
        else:
            self.url = sez.get("url", "http://localhost:11434").rstrip("/")
            self.num_ctx = int(sez.get("num_ctx", "4096"))
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
                    raise ErroreModello("Il router rifiuta la chiave: controlla FREELLMAPI_KEY (vedi ISTRUZIONI.md).")
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
                f"del router oppure aggiungilo a 'modelli_ammessi' in config.ini dopo averlo verificato con valuta.py")
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
        return estrai_json(self._chiama(sistema, utente, schema))

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


def estrai_json(testo):
    testo = re.sub(r"<think>.*?</think>", "", testo or "", flags=re.DOTALL)
    testo = re.sub(r"^```(?:json)?|```$", "", testo.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(testo)
    except Exception:
        m = re.search(r"\{.*\}", testo, re.DOTALL)
        if not m:
            raise ErroreModello("La risposta del modello non contiene JSON.")
        try:
            return json.loads(m.group(0))
        except Exception:
            raise ErroreModello("La risposta del modello contiene JSON non valido (forse troncato).")

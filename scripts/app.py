#!/usr/bin/env python3
"""
Interfaccia di Pressmark: un server locale, con la sola libreria standard, che apre una finestra
propria (pywebview, opzionale) con i menu «Progetto» e «Modello» e il percorso guidato della ricerca (domanda,
forme del nome attestate da confermare, avvio, avanzamento, risposta come documento). Senza pywebview apre nel
browser. Le funzioni sono quelle del motore (strumenti.py): interfaccia e conversazione sulle fonti fanno le stesse
cose allo stesso modo.

Sicurezza: il server ascolta solo su 127.0.0.1; all'avvio crea un token di sessione e apre la finestra con il
collegamento che lo contiene; il token diventa un cookie (HttpOnly, SameSite=Strict) e senza di esso ogni richiesta
è rifiutata. Si accettano solo richieste con Host 127.0.0.1 o localhost (contro il DNS rebinding); le azioni
(POST) vogliono JSON e l'intestazione X-Pressmark.

Progetto: la scelta vale per l'interfaccia (variabile PRESSMARK_PROGETTO del processo, ereditata dalle ricerche)
e si scrive tra le scelte dell'utente (posizioni.file_config: config.utente.ini o, da installato, il config.ini
nella cartella dei dati), sezione [progetto], perché la segua anche la riga di comando (una copia di
sicurezza al giorno). Il cambio è bloccato mentre una ricerca del progetto è in corso.
Modello: la scelta passa per la prova di collegamento (installa.modello_usa): se fallisce resta il precedente.
Conversazione sulle fonti: con il modello della sintesi e gli strumenti del motore;
disattivata, con la spiegazione, se la prova dice che il modello non sa usare gli strumenti.

Uso (nella cartella scripts):
  python app.py                    avvia il server e apre una finestra propria (o il browser)
  python app.py --porta 8770       porta fissa (predefinita: una libera)
  python app.py --senza-browser    stampa solo il collegamento
"""
import argparse
import base64
import configparser
import datetime as dt
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.parse
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARTELLA))

import posizioni                # noqa: E402

if sys.stdout is None or sys.stderr is None:
    # pythonw.exe (il collegamento del programma installato) non ha console: i messaggi vanno in app.log nella
    # cartella dei dati, utile se qualcosa non va
    _registro = posizioni.cartella_dati() / "app.log"
    _registro.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = sys.stderr = open(_registro, "a", encoding="utf-8", buffering=1)
    print(f"--- {dt.datetime.now():%Y-%m-%d %H:%M:%S} avvio", flush=True)

import strumenti as M           # noqa: E402

import installa                 # noqa: E402
import lavori                   # noqa: E402
import profili                  # noqa: E402
import revisione                # noqa: E402
import schede                   # noqa: E402
from citazioni import MARCATORE_PAGINA   # noqa: E402
from conversazione import Conversazione, ErroreConversazione   # noqa: E402
from estrai_occorrenze import leggi_intestazione   # noqa: E402
from llm import ErroreModello   # noqa: E402
from progetto import VARIABILE, cartella_scelta, leggi_config, percorso   # noqa: E402

PAGINE = CARTELLA / "interfaccia"
MARCHIO = CARTELLA.parent / "assets"   # logotipo e favicon, serviti come /marchio/<file>
TIPI = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
COOKIE = "pressmark"
INTESTAZIONE_AZIONE = "X-Pressmark"
TIPI_SCHEDA = ("persona", "organizzazione", "testata", "stato", "altro")


class Errore(Exception):
    """Errore da mostrare all'utente così com'è (risposta 400 con «errore»)."""


class _Voci(installa.Esito):
    """Esito dei controlli di installa.py che tiene anche le voci una per una, per la pagina «Preparazione»."""

    def __init__(self):
        super().__init__(lambda riga: None)
        self.voci = []

    def __call__(self, stato, voce, dettaglio=""):
        super().__call__(stato, voce, dettaglio)
        self.voci.append({"stato": stato, "voce": voce.strip(), "dettaglio": dettaglio})


class App:
    """Lo stato dell'interfaccia e le sue azioni, indipendenti dal protocollo HTTP (così i test le chiamano)."""

    def __init__(self, config=None, cartella_progetti=None):
        self.config = Path(config).resolve() if config else posizioni.file_config()
        M.CONFIG = str(self.config) if config else None
        installa.FILE_CONFIG = self.config
        self.cartella_progetti = Path(cartella_progetti) if cartella_progetti else posizioni.cartella_progetti()
        self.token = secrets.token_urlsafe(24)
        self._blocco = threading.Lock()
        self._collegamenti = {}            # profilo -> (istante, esito): la prova costa una richiesta di rete
        self._conv, self._conv_chiave = None, None
        self._conv_blocco = threading.Lock()   # una domanda alla volta
        self._prove_strumenti = {}         # (profilo, servizio, modello, url) -> esito della prova degli strumenti
        radice = cartella_scelta(leggi_config(self.config))
        if radice is not None:
            os.environ[VARIABILE] = str(radice)

    def cfg(self):
        return leggi_config(self.config)

    # ------------------------------------------------------------ progetti
    def progetti(self):
        """Progetti nella cartella dei progetti (quelli con project.ini), più quello in uso se sta altrove."""
        attuale = cartella_scelta(self.cfg())
        trovati = []
        if self.cartella_progetti.is_dir():
            trovati = [d for d in sorted(self.cartella_progetti.iterdir()) if (d / "project.ini").is_file()]
        if attuale is not None and (attuale / "project.ini").is_file() and \
                all(d.resolve() != attuale.resolve() for d in trovati):
            trovati.append(attuale)
        out = []
        for d in trovati:
            cp = configparser.ConfigParser(interpolation=None)
            try:
                cp.read(d / "project.ini", encoding="utf-8")
            except configparser.Error:
                pass
            out.append({"cartella": str(d.resolve()), "nome": cp.get("progetto", "nome", fallback=d.name) or d.name,
                        "descrizione": cp.get("progetto", "descrizione", fallback=""),
                        "in_uso": attuale is not None and d.resolve() == attuale.resolve()})
        return out

    def ricerca_in_corso(self):
        try:
            d, s_ = lavori.attivo(self.cfg())
        except Exception:                  # nessun progetto, o cartella dei lavori assente
            return None
        return s_ if d else None

    def cambia_progetto(self, cartella):
        f = Path(cartella or "").expanduser()
        if not (f / "project.ini").is_file():
            raise Errore(f"«{cartella}» non è un progetto (manca project.ini).")
        with self._blocco:
            in_corso = self.ricerca_in_corso()
            attuale = cartella_scelta(self.cfg())
            if attuale is not None and attuale.resolve() == f.resolve():
                return {"cambiato": False, "nota": "È già il progetto in uso."}
            if in_corso:
                raise Errore(f"C'è una ricerca in corso in questo progetto («{in_corso.get('domanda', '')}»): "
                             "aspetta che finisca, o fermala, prima di cambiare progetto.")
            self._scrivi_progetto(f.resolve())
        return {"cambiato": True, "progetto": self.progetto_in_uso()}

    def _scrivi_progetto(self, f):
        os.environ[VARIABILE] = str(f)
        if not any(self.config.parent.glob(f"{self.config.name}.pressmark-{installa.oggi()}*.bak")):
            installa.copia_di_sicurezza(self.config)        # una copia al giorno, non una per ogni cambio
        installa.imposta_voci(self.config, "progetto", {"cartella": str(f)})
        # ciò che il motore tiene in memoria per il progetto di prima
        M._indice.clear()
        M._indice["oggetto"] = None
        M._cache.update({"chiave": None, "passaggi": {}})
        profili.tutti(ricarica=True)
        M.FONTI_SCELTE = sorted({profili.gruppo(n) for n in profili.tutti()})
        self._collegamenti.clear()          # le scelte di modello possono stare in project.ini

    def nuovo_progetto(self, nome, descrizione=""):
        from progetto import cmd_nuovo
        nome = (nome or "").strip()
        if not nome:
            raise Errore("Scrivi il nome del progetto.")
        cartella = self.cartella_progetti / re.sub(r"[^\w\-]+", "_", nome, flags=re.UNICODE).strip("_")
        if cartella.exists():
            raise Errore(f"Esiste già una cartella {cartella}: scegli un altro nome.")
        if self.ricerca_in_corso():
            raise Errore("C'è una ricerca in corso: aspetta che finisca, o fermala, prima di cambiare progetto.")
        righe = []
        argomenti = argparse.Namespace(cartella=str(cartella), nome=nome, descrizione=descrizione or "")
        if cmd_nuovo(argomenti, righe.append):
            raise Errore(" ".join(righe) or "Progetto non creato.")
        with self._blocco:
            self._scrivi_progetto(cartella.resolve())
        return {"creato": True, "progetto": self.progetto_in_uso()}

    def progetto_in_uso(self):
        c = self.cfg()
        radice = cartella_scelta(c)
        if radice is None or not (radice / "project.ini").is_file():
            return None
        from progetto import nome
        dati = percorso(c, "dati")
        return {"nome": nome(c), "cartella": str(radice),
                "documenti": sum(1 for _ in dati.rglob("*.txt")) if dati.is_dir() else 0}

    # ------------------------------------------------------------ modelli
    def modelli(self):
        if not self.progetto_in_uso():
            return {"profili": [], "nota": "Scegli o crea un progetto."}
        return installa.stato_profili(self.cfg())

    def collegamento(self, nome):
        """Pallino del menu: chiave presente e servizio raggiungibile, senza richieste al modello (come
        «controlla»). Si ricorda per un minuto."""
        from llm import leggi_profili
        p = leggi_profili(self.cfg()).get(nome)
        if p is None:
            raise Errore(f"Profilo «{nome}» inesistente.")
        prima = self._collegamenti.get(nome)
        if prima and time.time() - prima[0] < 60:
            return prima[1]
        righe = []
        esito = installa.Esito(righe.append)
        installa.controlla_servizio(esito, nome, p)
        out = {"nome": nome, "ok": not esito.mancanti, "dettaglio": righe[-1] if righe else ""}
        self._collegamenti[nome] = (time.time(), out)
        return out

    def usa_modello(self, nome, gia_provato=False, ruoli=None):
        """La scelta passa per la prova di collegamento: se fallisce resta il profilo di prima. gia_provato: la prova
        è appena riuscita («Aggiungi modello»), non si rifà. ruoli: solo questi (smistamento, analisi, sintesi);
        senza, tutti."""
        if ruoli is not None and not isinstance(ruoli, list):
            raise Errore("«ruoli» va dato come elenco.")
        out = M.t_modello("usa", nome, ruoli=ruoli, gia_provato=gia_provato)
        self._collegamenti.pop(nome, None)
        if out.get("errore"):
            raise Errore(out["errore"])
        return out

    def servizi(self):
        """Le scelte della procedura «Aggiungi modello» (le stesse di installa.py modello)."""
        return {"servizi": [
            {"id": "ollama", "etichetta": "Ollama, sul tuo computer: gratuito, nessuna chiave",
             "url": "http://localhost:11434", "chiave_env": "", "modello": "qwen3.5:9b"},
            *({"id": f"chiave:{n}", "etichetta": n, "url": url, "chiave_env": env, "modello": modello,
               "pausa_secondi": pausa, "dove_chiave": dove} for n, url, env, modello, pausa, dove in installa.SERVIZI_CHIAVE),
            {"id": "openai", "etichetta": "Altro servizio compatibile OpenAI", "url": "", "chiave_env": "",
             "modello": ""},
            {"id": "anthropic", "etichetta": "API di Anthropic (Claude), a consumo", "url": "",
             "chiave_env": "ANTHROPIC_API_KEY", "modello": "claude-sonnet-5-5",
             "dove_chiave": "https://console.anthropic.com/settings/keys"},
            {"id": "router", "etichetta": "FreeLLMAPI (avanzato)", "url": "http://127.0.0.1:31415/v1",
             "chiave_env": "FREELLMAPI_KEY", "modello": "auto:ricerca"}]}

    def _servizio(self, ident):
        for s in self.servizi()["servizi"]:
            if s["id"] == ident:
                return s
        raise Errore(f"Servizio «{ident}» sconosciuto.")

    def elenco_modelli(self, servizio, url="", chiave=""):
        """Modelli che il servizio elenca (Ollama: quelli installati), per non far scrivere un nome sbagliato."""
        s = self._servizio(servizio)
        url = (url or s["url"]).strip()
        if servizio == "ollama":
            elenco = installa.modelli_ollama(url)
            return {"modelli": elenco or [], "raggiungibile": elenco is not None}
        if servizio == "anthropic":
            return {"modelli": [], "raggiungibile": None}
        chiave = (chiave or os.environ.get(s["chiave_env"], "") if s["chiave_env"] else chiave).strip()
        elenco = installa.modelli_servizio(url, chiave) if url else None
        return {"modelli": elenco or [], "raggiungibile": elenco is not None,
                "chiave_presente": bool(s["chiave_env"] and os.environ.get(s["chiave_env"]))}

    def fornitori(self, stato_locale=False):
        """I fornitori dei modelli per la pagina Impostazioni: quelli noti, anche senza profili, e quelli dei profili
        (un indirizzo sconosciuto fa fornitore da sé). «attivo» se la chiave c'è o non serve: l'interfaccia mostra i
        modelli solo dei fornitori attivi."""
        tipi = {"ollama": "ollama", "anthropic": "anthropic", "router": "router"}
        voci = {}
        for s in self.servizi()["servizi"]:
            if s["id"] == "openai":                   # «altro servizio»: è l'azione che aggiunge un fornitore
                continue
            f = installa.fornitore({"servizio": tipi.get(s["id"], "openai"), "url": s["url"]})
            voci[f["id"]] = {**f, "chiave_env": s["chiave_env"], "url": s["url"], "profili": []}
        m = self.modelli()
        for p in m.get("profili", []):
            f = p["fornitore"]
            v = voci.setdefault(f["id"], {**f, "chiave_env": p.get("chiave_env", ""), "url": "", "profili": []})
            v["chiave_env"] = v["chiave_env"] or p.get("chiave_env", "")
            v["profili"].append(p)
        spenti = installa.spenti(self.cfg())
        for v in voci.values():
            env = v["chiave_env"]
            v["url"] = v["url"] or next((p["url"] for p in v["profili"] if p.get("url")), "")
            v["chiave"] = ("presente" if os.environ.get(env) else "assente") if env else "non serve"
            # gli interruttori: un fornitore spento, o la sua chiave spenta, non è attivo anche se la chiave c'è
            v["spento"] = v["id"] in spenti["fornitori"]
            v["chiave_spenta"] = bool(env) and env in spenti["chiavi"]
            v["attivo"] = v["chiave"] != "assente" and not v["spento"] and not v["chiave_spenta"]
            host = v["id"].removeprefix("openai:")
            v["locale"] = v["id"] in ("ollama", "freellmapi") or host in ("localhost", "127.0.0.1", "::1")
            v["raggiungibile"] = None                 # non chiesto: l'interfaccia lo chiede a parte (?locali=1)
            v["installati"] = []
            v["pronto"] = v["attivo"] if not v["locale"] else (False if not v["attivo"] else None)
        if stato_locale:
            self._stato_locale([v for v in voci.values() if v["locale"] and v["attivo"] and v["url"]])
        return {"fornitori": list(voci.values()), "in_uso": m.get("in_uso", {}), "nota": m.get("nota", ""),
                "errore": m.get("errore", ""), "locali": stato_locale}

    @staticmethod
    def _stato_locale(voci):
        """Un servizio sul computer è pronto solo se risponde (Ollama installato e avviato, il router acceso).
        Su Windows una porta chiusa risponde dopo qualche secondo: le domande vanno in parallelo."""
        from concurrent.futures import ThreadPoolExecutor

        def chiedi(v):
            env = v["chiave_env"]
            if v["id"] == "ollama":
                return installa.modelli_ollama(v["url"])
            return installa.modelli_servizio(v["url"], os.environ.get(env, "") if env else "", timeout=3)
        if not voci:
            return
        with ThreadPoolExecutor(max_workers=len(voci)) as gruppo:
            for v, elenco in zip(voci, gruppo.map(chiedi, voci)):
                v["raggiungibile"] = elenco is not None
                v["installati"] = elenco or []
                v["pronto"] = elenco is not None

    def salva_chiave(self, fornitore, chiave, conserva=False):
        """La chiave di un fornitore: prima si prova (dove il servizio elenca i modelli), poi vale subito per questa
        sessione e, se chiesto, tra le variabili dell'utente. Mai in un file del progetto."""
        v = next((x for x in self.fornitori()["fornitori"] if x["id"] == fornitore), None)
        if v is None:
            raise Errore(f"Fornitore «{fornitore}» sconosciuto.")
        env = v["chiave_env"]
        if not env:
            raise Errore(f"{v['nome']} non usa una chiave.")
        chiave = (chiave or "").strip()
        if not chiave:
            raise Errore("Scrivi la chiave.")
        provata = None
        # Anthropic non ha un elenco da provare; Hugging Face e NVIDIA elencano i modelli anche con una chiave sbagliata
        if v["url"] and v["servizio_id"] != "anthropic" and v["nome"] not in installa.ELENCO_SENZA_CHIAVE:
            provata = installa.modelli_servizio(v["url"], chiave) is not None
            if not provata:
                return {"salvata": False, "messaggi": [f"{v['nome']} rifiuta la chiave o non risponde: non l'ho "
                                                       "salvata. Controllala e riprova."]}
        os.environ[env] = chiave
        righe = ["Chiave provata e impostata." if provata else
                 "Chiave impostata: si prova la prima volta che usi un modello di questo fornitore."]
        if conserva:
            installa.salva_variabile(env, chiave, righe.append)
        self._collegamenti.clear()
        return {"salvata": True, "provata": bool(provata), "messaggi": righe}

    # ------------------------------------------------------------ profili: prova, nome, togli
    def _profilo_libero(self, nome):
        """Il profilo esiste e nessun ruolo lo usa (né config.ini né il project.ini del progetto)."""
        from llm import RUOLI, ErroreModello, file_profili, leggi_profili, nome_scelto, profilo
        c = self.cfg()
        if nome not in leggi_profili(c):
            raise Errore(f"Profilo «{nome}» inesistente.")
        usato = {r for r in RUOLI if nome_scelto(c, r) == nome}
        try:
            usato |= {r for r in RUOLI if profilo(c, r)[0] == nome}
        except ErroreModello:
            pass
        if usato:
            raise Errore(f"«{nome}» è in uso per {', '.join(sorted(usato))}: scegli prima un altro modello.")
        return file_profili(c)

    def interruttore(self, tipo, nome, acceso):
        """Accende o spegne un fornitore (per id), una chiave (per variabile) o un profilo. Non si spegne ciò che è in
        uso: prima si sceglie un altro modello. La scelta sta in config.ini, sezione [disattivati]."""
        from llm import RUOLI, ErroreModello, leggi_profili, profilo
        if tipo not in installa.TIPI_SPENTI:
            raise Errore(f"Interruttore «{tipo}» sconosciuto: fornitore, chiave o profilo.")
        nome = (nome or "").strip()
        if not nome or not re.fullmatch(r"[A-Za-z0-9_.:-]+", nome):
            raise Errore("Nome non valido.")
        c = self.cfg()
        profili_ = leggi_profili(c)
        if tipo == "profilo" and nome not in profili_:
            raise Errore(f"Profilo «{nome}» inesistente.")
        if not acceso:
            try:
                in_uso = {profilo(c, r)[0] for r in RUOLI}
            except ErroreModello:
                in_uso = set()
            colpiti = [n for n in in_uso if n in profili_ and (
                (tipo == "profilo" and n == nome) or
                (tipo == "fornitore" and installa.fornitore(profili_[n])["id"] == nome) or
                (tipo == "chiave" and installa.env_chiave(profili_[n]) == nome))]
            if colpiti:
                raise Errore(f"In uso: {', '.join(sorted(colpiti))}. Scegli prima un altro modello, poi spegni.")
        voce = installa.TIPI_SPENTI[tipo]
        insieme = installa.spenti(c)[voce]
        prima = set(insieme)
        (insieme.discard if acceso else insieme.add)(nome)
        if insieme != prima:
            if not any(self.config.parent.glob(f"{self.config.name}.pressmark-{installa.oggi()}*.bak")):
                installa.copia_di_sicurezza(self.config)        # una copia al giorno, come per il progetto
            installa.imposta_voci(self.config, installa.SEZIONE_SPENTI, {voce: ", ".join(sorted(insieme)) or None})
        return {"tipo": tipo, "nome": nome, "acceso": bool(acceso), "cambiato": insieme != prima}

    def prova_modello(self, nome):
        """Prova di collegamento di un profilo, senza cambiare la scelta."""
        out = M.t_modello("prova", nome)
        if out.get("errore"):
            raise Errore(out["errore"])
        self._collegamenti.pop(nome, None)
        return out

    def rinomina_modello(self, nome, nuovo):
        from llm import leggi_profili
        nuovo = (nuovo or "").strip()
        if not installa.NOME_PROFILO.match(nuovo):
            raise Errore("Nome del profilo: solo lettere, cifre, punto, trattino e trattino basso, senza spazi.")
        f = self._profilo_libero(nome)
        if nuovo == nome:
            return {"cambiato": False, "profilo": nome}
        if nuovo in leggi_profili(self.cfg()):
            raise Errore(f"Esiste già un profilo «{nuovo}».")
        copia = installa.copia_di_sicurezza(f)
        installa.rinomina_profilo(f, nome, nuovo)
        self._collegamenti.pop(nome, None)
        return {"cambiato": True, "profilo": nuovo, "messaggi": [f"Copia del file prima della modifica: {copia}."]}

    def togli_modello(self, nome):
        f = self._profilo_libero(nome)
        copia = installa.copia_di_sicurezza(f)
        installa.togli_profilo(f, nome)
        self._collegamenti.pop(nome, None)
        return {"tolto": True, "messaggi": [f"Profilo «{nome}» tolto. Copia del file prima della modifica: {copia}."]}

    def aggiungi_modello(self, servizio, modello, nome="", url="", chiave_env="", chiave="", salva_chiave=False,
                         usa=True):
        """Procedura «Aggiungi modello»: profilo in models.ini (la chiave mai nel file: solo il nome della
        variabile), chiave nell'ambiente e, se chiesto, tra le variabili dell'utente; prova; scelta se riesce."""
        from llm import file_profili, leggi_profili
        s = self._servizio(servizio)
        modello = (modello or "").strip()
        if not modello:
            raise Errore("Scegli o scrivi il modello.")
        tipo = {"ollama": "ollama", "anthropic": "anthropic", "router": "router"}.get(servizio, "openai")
        p = {"servizio": tipo, "modello": modello}
        url = (url or s["url"]).strip()
        if tipo != "anthropic":
            if not url:
                raise Errore("Manca l'indirizzo del servizio.")
            p["url"] = url
        env = (chiave_env or s["chiave_env"]).strip()
        if env:
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", env):
                raise Errore("Il nome della variabile della chiave può contenere solo lettere, cifre e _.")
            p["chiave_env"] = env
        if s.get("pausa_secondi"):
            p["pausa_secondi"] = s["pausa_secondi"]
        if tipo == "ollama":
            p["num_ctx"] = "4096"
        if tipo == "router":
            p["pausa_secondi"] = "2"
        c = self.cfg()
        esistenti = leggi_profili(c)
        nome = (nome or "").strip() or installa.nome_libero(installa.nome_proposto(p), esistenti)
        if not installa.NOME_PROFILO.match(nome):
            raise Errore("Nome del profilo: solo lettere, cifre, punto, trattino e trattino basso, senza spazi.")
        if nome in esistenti:
            raise Errore(f"Esiste già un profilo «{nome}».")
        righe = []
        if env and chiave:
            os.environ[env] = chiave.strip()          # vale subito, per la prova e per le ricerche avviate da qui
            if salva_chiave:
                installa.salva_variabile(env, chiave.strip(), righe.append)
        f = file_profili(c)
        installa.aggiungi_profilo(f, nome, p)
        righe.append(f"Profilo «{nome}» salvato in {f}.")
        riuscita = installa.prova_profilo(self.cfg(), nome, righe.append)
        out = {"profilo": nome, "riuscita": riuscita, "messaggi": righe, "cambiato": False}
        if riuscita and usa:
            u = self.usa_modello(nome, gia_provato=True)    # una prova sola: prima si faceva due volte
            out["cambiato"] = u.get("cambiato", False)
            out["messaggi"] += u.get("messaggi", [])
        elif not riuscita:
            out["messaggi"].append("Il profilo resta salvato ma non è in uso: correggilo o provane un altro.")
        return out

    # ------------------------------------------------------------ preparazione
    def _modello_scelto(self, c):
        """Il profilo in uso, se tutti i ruoli ne hanno uno che esiste; None altrimenti."""
        from llm import RUOLI, ErroreModello, leggi_profili, profilo, usa_profili
        if not usa_profili(c):
            return None
        try:
            nomi = {profilo(c, r)[0] for r in RUOLI}
        except ErroreModello:
            return None
        esistenti = leggi_profili(c)
        return ", ".join(sorted(nomi)) if all(n in esistenti for n in nomi) else None

    def avvio(self):
        """I passi della preparazione, come «installa.py inizia»: progetto e modello necessari, prime fonti
        facoltative. «completo» quando si può cercare."""
        c = self.cfg()
        p = self.progetto_in_uso()
        modello = self._modello_scelto(c) if p else None
        passi = [
            {"id": "progetto", "titolo": "Progetto di ricerca", "fatto": bool(p), "facoltativo": False,
             "dettaglio": f"«{p['nome']}» in {p['cartella']}" if p else
             "Un progetto raccoglie le fonti, le schede dei nomi e le risposte di una ricerca."},
            {"id": "modello", "titolo": "Modello che legge i passaggi", "fatto": bool(modello), "facoltativo": False,
             "dettaglio": f"In uso: {modello}." if modello else
             ("Scegli il servizio e, se serve, la chiave: il sistema prova il collegamento prima di usarlo."
              if p else "Prima crea o scegli un progetto.")},
            {"id": "fonti", "titolo": "Prime fonti", "fatto": bool(p and p["documenti"]), "facoltativo": True,
             "dettaglio": f"{p['documenti']} documenti nel progetto." if p and p["documenti"] else
             "Importa PDF, scansioni o testi: il sistema propone i metadati in una tabella da controllare."},
        ]
        return {"passi": passi, "completo": bool(p and modello)}

    def ambiente(self):
        """I controlli di «installa.py controlla», uno per riga, con l'azione dell'interfaccia che rimedia."""
        c = self.cfg()
        gruppi = []

        def gruppo(titolo, *controlli):
            esito = _Voci()
            for controllo in controlli:
                try:
                    controllo(esito)
                except Exception as e:          # un controllo che si rompe non nasconde gli altri
                    esito("manca", "controllo non riuscito", str(e))
            gruppi.append({"titolo": titolo, "voci": esito.voci})

        progetto = self.progetto_in_uso()
        gruppo("Programma", installa.controlla_python, installa.controlla_sqlite,
               installa.controlla_pywebview)
        gruppo("Progetto e modello", lambda e: installa.controlla_progetto(e, c),
               *([lambda e: installa.controlla_modelli(e, c)] if progetto else []))
        gruppo("Importazione delle fonti", installa.controlla_pymupdf,
               lambda e: installa.controlla_tesseract(e, c))
        for g in gruppi:
            for v in g["voci"]:
                v["azione"] = ("progetto" if v["voce"] == "progetto" and v["stato"] == "manca" else
                               "modello" if v["voce"].startswith("modelli") and v["stato"] == "manca" else "")
        import posizioni
        return {"gruppi": gruppi, "posizioni": posizioni.descrizione(),
                "mancano": [v["voce"] for g in gruppi for v in g["voci"] if v["stato"] == "manca"]}

    def lingue(self):
        """Le lingue OCR: installate, richieste dalle serie, mancanti, e se si possono scaricare da qui."""
        return installa.stato_lingue(self.cfg())

    def scarica_lingua(self, codice):
        """Scarica un modello di lingua di Tesseract nella sua cartella (solo se ci si può scrivere: il Tesseract
        incluso nel programma installato). Può volerci qualche minuto per i modelli grandi (chi_sim, 44 MB)."""
        import importa
        s = installa.stato_lingue(self.cfg())
        if not s["tesseract"]:
            raise Errore("Tesseract non trovato: senza, le lingue non servono.")
        if not s["scrivibile"]:
            raise Errore(f"Non posso scrivere in {s['cartella']} (Tesseract installato nel sistema, serve "
                         "l'amministratore). " + importa.AIUTO_LINGUE.format(codice))
        codice = (codice or "").strip()
        with self._blocco:                       # uno scaricamento alla volta
            try:
                f = importa.scarica_lingua(codice, s["cartella"], stampa=lambda t: None)
            except ValueError as e:
                raise Errore(str(e))
            except OSError as e:
                raise Errore(f"Scaricamento di «{codice}» non riuscito: {e}. Controlla la connessione e riprova.")
        dopo = installa.stato_lingue(self.cfg())
        if codice not in dopo["installate"]:
            raise Errore(f"{f.name} è stato scaricato ma Tesseract non lo vede: controlla {dopo['cartella']}.")
        return {"scaricata": codice, "dimensione_mb": round(f.stat().st_size / 1e6, 1), **dopo}

    def cartella_lingue_propria(self):
        """Le lingue OCR in una cartella dell'utente, per installarne di nuove senza l'amministratore."""
        s = installa.stato_lingue(self.cfg())
        if s["scrivibile"]:
            raise Errore(f"Nella cartella delle lingue ({s['cartella']}) si può già scrivere: non serve copiarla.")
        with self._blocco:
            righe = []
            try:
                installa.usa_cartella_lingue_propria(self.cfg(), self.config, righe.append)
            except ValueError as e:
                raise Errore(str(e))
            except OSError as e:
                raise Errore(f"Copia dei modelli non riuscita: {e}.")
        return {"messaggi": righe, **installa.stato_lingue(self.cfg())}

    # ------------------------------------------------------------ percorso della ricerca
    def entita(self, nome):
        """Passo 1: c'è una scheda per questo nome? Le schede trovate, con le loro forme."""
        nome = (nome or "").strip()
        if not nome:
            raise Errore("Scrivi il nome della persona o dell'ente.")
        cp = schede.leggi_schede(percorso(self.cfg(), "entita"))
        esatte = [s_ for s_ in cp.sections() if s_.lower() == nome.lower()]
        trovate = esatte or schede.trova_nel_testo(nome, cp)
        return {"nome": nome, "schede": [{"nome": s_, "tipo": cp.get(s_, "tipo", fallback=""),
                                          "varianti": schede.dividi(cp.get(s_, "varianti", fallback="")),
                                          "collegate": schede.dividi(cp.get(s_, "collegate", fallback=""))}
                                         for s_ in trovate[:5]]}

    def esplora(self, nome, indizi=None, candidate=None):
        r = M.t_esplora_nome(nome, _elenco(indizi), _elenco(candidate))
        if r.get("errore"):
            return r
        forme = []
        proposta = r.get("proposta_di_scheda", {})
        # le forme che per questo nome si sono già scartate (crea_scheda): restano fuori dalla proposta
        import varianti as mod_varianti
        scartate = set()
        for k, v in mod_varianti.carica_scartate(self.cfg()).items():
            if k.strip().lower() == (nome or "").strip().lower():
                scartate |= v
        ambigue = set(proposta.get("forme_ambigue", []))
        scelte = set(proposta.get("varianti", []))
        for gruppo, origine in (("forme_latine", "nelle fonti"), ("forme_cinesi", ""), ("forme_albanesi", "")):
            for forma, s_ in (r.get(gruppo) or {}).items():
                forme.append({"forma": forma, "totale": s_.get("totale", 0), "origine": s_.get("origine") or origine,
                              "attenzione": s_.get("attenzione", ""), "per_serie_e_anno": s_.get("per_serie_e_anno", {}),
                              "esempi": [{"riferimento": e.get("riferimento", ""), "testo": e.get("testo", "")}
                                         for e in (s_.get("esempi") or [])[:2]],
                              "proposta": forma in scelte and forma not in scartate, "ambigua": forma in ambigue,
                              "scartata_prima": forma in scartate})
        return {"nome": nome, "forme": forme, "non_attestate": r.get("non_attestate", []),
                "contesto": proposta.get("contesto", []), "avviso_indice": r.get("avviso_indice", "")}

    def conta_righe(self, varianti, dal=None, al=None, fonti=None):
        """Quante righe delle fonti contengono almeno una delle forme, con i filtri scelti: il riepilogo prima di
        avviare la ricerca dice così quanto lavoro aspetta il modello. Una riga con due forme conta una volta."""
        forme = _elenco(varianti)
        if not forme:
            return {"righe": 0}
        ind, errore = M.indice_pronto()
        if errore:
            return {"righe": None, "nota": "indice delle fonti in costruzione" if errore.get("avanzamento")
                    else "indice delle fonti non disponibile"}
        import esplora
        serie = esplora.serie_indice(ind, _elenco(fonti)) if _elenco(fonti) else None
        viste = set()
        for f in forme:
            for x in ind.cerca(f, _anno(dal), _anno(al), serie):
                viste.add((x["file"], x["riga"]))
        return {"righe": len(viste)}

    def precedenti(self, entita):
        """Prima di avviare: l'ultima ricerca finita su questa entità, quanti suoi passaggi sono già letti (una
        ricerca nuova li riusa) e il ritmo delle ricerche passate del progetto, in minuti per passaggio estratto, per
        stimare la durata. Il ritmo prende per ogni cartella di ricerca la corsa più lunga: le successive riusano i
        passaggi già letti e sembrerebbero più veloci di quanto è una ricerca nuova."""
        c = self.cfg()
        entita = (entita or "").strip()
        ultima, per_cartella = None, {}
        try:
            elenco = lavori.lavori(c)
        except OSError:
            elenco = []
        for d in elenco:
            s_ = lavori.stato_lavoro(d)
            if not s_ or not str(s_.get("stato", "")).startswith("completata"):
                continue
            par = s_.get("parametri") or {}
            if not par.get("principale"):
                continue
            minuti = max(0.0, (s_.get("battito", 0) - s_.get("inizio", 0)) / 60)
            try:
                cartella = lavori.cartella_ricerca(c, par)
            except (KeyError, TypeError):
                continue
            per_cartella[cartella] = max(per_cartella.get(cartella, 0.0), minuti)
            if par["principale"].lower() == entita.lower():
                ultima = {"quando": dt.datetime.fromtimestamp(s_.get("inizio", 0)).isoformat(timespec="minutes"),
                          "minuti": round(minuti), "domanda": s_.get("domanda", "")}
        ritmi = []
        for cartella, minuti in per_cartella.items():
            n = _righe_jsonl(cartella / "passaggi.jsonl")
            if n >= 5 and minuti >= 1:
                ritmi.append(minuti / n)
        ritmi.sort()
        letti = 0
        if entita:
            try:
                d = lavori.cartella_ricerca(c, {"principale": entita, "modalita": "occorrenze"})
                letti = _righe_jsonl(d / "classificati.jsonl")
            except (OSError, KeyError, TypeError):
                letti = 0
        return {"ultima": ultima, "letti": letti,
                "minuti_per_passaggio": ritmi[len(ritmi) // 2] if ritmi else None, "campioni": len(ritmi)}

    def crea_scheda(self, nome, varianti, forme_ambigue=None, tipo="", contesto=None, scartate=None, cercato="",
                    descrizione=""):
        """Crea la scheda; «scartate»: le forme trovate e non spuntate, che si ricordano per il nome cercato e per
        la scheda (varianti.py, rejected_variants.json), così una nuova esplorazione non le ripropone.
        «descrizione»: chi è (va nelle note). Le forme ambigue sono quelle scelte nella pagina, dove le brevi
        arrivano già segnate (esplora): una scelta diversa di chi crea la scheda resta."""
        varianti = _elenco(varianti)
        if not varianti:
            raise Errore("Conferma almeno una forma del nome.")
        ambigue = [f for f in _elenco(forme_ambigue) if f in varianti]
        tipo = tipo if tipo in TIPI_SCHEDA else ""
        r = M.t_crea_scheda(nome.strip(), varianti, descrizione=re.sub(r"\s+", " ", descrizione or "").strip(),
                            contesto=_elenco(contesto) or None, forme_ambigue=ambigue, tipo=tipo)
        if r.get("errore"):
            raise Errore(r["errore"])
        scartate = [f for f in _elenco(scartate) if f not in varianti]
        if scartate:
            import varianti as mod_varianti
            for chi in {nome.strip(), (cercato or "").strip()} - {""}:
                mod_varianti.scarta(self.cfg(), chi, scartate)
        return r

    # ------------------------------------------------------------ glossario: schede e serie modificabili
    # Ogni modifica: una copia del file al giorno (<file>.pressmark-<data>.bak, come per la configurazione), una
    # riga per campo in audit/changes.csv (revisione.registra_modifiche), e la scrittura riga per riga di
    # schede.modifica_sezione, che lascia commenti e campi sconosciuti come sono.
    def _copia_glossario(self, f):
        if f.exists() and not any(f.parent.glob(f"{f.name}.pressmark-{installa.oggi()}*.bak")):
            installa.copia_di_sicurezza(f)

    def _registra_glossario(self, f, sezione, cambi, motivo):
        import revisione
        rel = f"{f.parent.name}/{f.name} [{sezione}]"
        revisione.registra_modifiche(self.cfg(), [(rel, c, p or "(assente)", d or "(vuoto)", motivo)
                                                  for c, p, d in cambi])

    def _problemi_di(self, nome):
        f = percorso(self.cfg(), "entita")
        return [{"gravita": g, "schede": s, "problema": p} for g, s, p in schede.controlla(f)
                if nome in [x.strip() for x in s.split(" / ")]]

    def verifica_scheda(self, nome, campi, nuova=False):
        """I problemi che la scheda avrebbe con questi campi, prima di salvarla: il controllo gira su una copia del
        glossario con la modifica (o la scheda nuova) già fatta. Il file vero non cambia."""
        import shutil
        import tempfile
        nome = (nome or "").strip()
        campi = campi if isinstance(campi, dict) else {}
        f = percorso(self.cfg(), "entita")
        with tempfile.TemporaryDirectory() as d:
            copia = Path(d) / "entities.ini"
            if f.exists():
                shutil.copy2(f, copia)
            else:
                copia.write_text("", encoding="utf-8")
            try:
                if nuova:
                    if nome in schede.leggi_schede(copia).sections():
                        return {"problemi": [{"gravita": "errore", "schede": nome,
                                              "problema": f"esiste già una scheda «{nome}»"}]}
                    schede.aggiungi_scheda(copia, schede.nome_valido(nome), _elenco(campi.get("varianti")),
                                           campi.get("note") or "descrizione", _elenco(campi.get("contesto")),
                                           _elenco(campi.get("forme_ambigue")), None, campi.get("tipo") or "")
                    if not (campi.get("note") or "").strip():
                        schede.modifica_sezione(copia, nome, {"note": ""})
                else:
                    schede.modifica_scheda(copia, nome, campi)
            except ValueError as e:
                return {"problemi": [{"gravita": "errore", "schede": nome, "problema": str(e)}]}
            problemi = [{"gravita": g, "schede": s, "problema": p} for g, s, p in schede.controlla(copia)
                        if nome in [x.strip() for x in s.split(" / ")]]
        return {"problemi": problemi}

    def correggi_scheda(self, nome="", tipo="", tutte=False):
        """Una correzione automatica (schede.correzioni) di una scheda; con «tutte», tutte quelle di tutte le schede."""
        f = percorso(self.cfg(), "entita")
        da_fare = []
        if tutte:
            for s in schede.leggi_schede(f).sections():
                da_fare += [(s, c["tipo"]) for c in schede.correzioni(f, s)]
        else:
            da_fare = [((nome or "").strip(), tipo)]
        if not da_fare:
            return {"corrette": 0, "nota": "Niente da correggere."}
        self._copia_glossario(f)
        fatte = 0
        for s, t in da_fare:
            try:
                cambi = schede.correggi(f, s, t)
            except ValueError as e:
                raise Errore(str(e))
            if cambi:
                fatte += 1
                self._registra_glossario(f, s, cambi, "correzione automatica dal controllo del glossario")
        return {"corrette": fatte, "nota": f"{fatte} {'correzione fatta' if fatte == 1 else 'correzioni fatte'}."}

    def leggi_scheda(self, nome):
        """I campi di una scheda: quelli noti come elenchi, e tutti come sono nel file («campi»)."""
        nome = (nome or "").strip()
        f = percorso(self.cfg(), "entita")
        s = schede.leggi_scheda(f, nome)
        if s is None:
            raise Errore(f"Scheda «{nome}» non trovata.")
        cp = schede.leggi_schede(f)
        s["campi"] = {k: v.strip() for k, v in cp[nome].items()}
        s["tipi"] = list(schede.TIPI)
        s["schede"] = [x for x in cp.sections() if x != nome]       # per scegliere le collegate
        return s

    def modifica_scheda(self, nome, campi):
        """Cambia i campi della scheda (solo quelli passati). Dice che cosa cambia per le ricerche: forme nuove
        (alla prossima ricerca si leggono solo i loro passaggi) e forme tolte (i passaggi letti restano in archivio)."""
        nome = (nome or "").strip()
        if not isinstance(campi, dict) or not campi:
            raise Errore("Niente da cambiare.")
        f = percorso(self.cfg(), "entita")
        prima = schede.leggi_scheda(f, nome)
        if prima is None:
            raise Errore(f"Scheda «{nome}» non trovata.")
        self._copia_glossario(f)
        try:
            cambi = schede.modifica_scheda(f, nome, campi)
        except ValueError as e:
            raise Errore(str(e))
        self._registra_glossario(f, nome, cambi, "modificata dal glossario dell'interfaccia")
        dopo = schede.leggi_scheda(f, nome)
        nuove = [v for v in dopo["varianti"] if v not in prima["varianti"]]
        tolte = [v for v in prima["varianti"] if v not in dopo["varianti"]]
        nota = []
        if nuove:
            nota.append("Alla prossima ricerca si leggono i passaggi delle forme nuove; quelli già letti si riusano.")
        if tolte:
            nota.append("I passaggi già letti delle forme tolte restano nell'archivio; la prossima ricerca non li cerca più.")
        return {"scheda": nome, "cambiati": [c for c, _, _ in cambi], "nuove": nuove, "tolte": tolte,
                "problemi": self._problemi_di(nome), "nota": " ".join(nota) or ("Scheda salvata." if cambi else
                                                                                   "Nessun cambiamento.")}

    def _sposta_letture(self, vecchio, nuovo):
        """Le letture dell'archivio sotto «vecchio» passano a «nuovo» (equivalenza e riattribuzione, archivio.py):
        le ricerche successive su «nuovo» le riusano. Restituisce una frase su com'è andata."""
        import contextlib
        import io
        import archivio
        ris = percorso(self.cfg(), "risultati")
        if not any(e == vecchio for _, e in archivio.Archivio(ris).per_id):
            return ""
        archivio.registra_equivalenza(ris, vecchio, nuovo, "dal glossario dell'interfaccia")
        uscita = io.StringIO()
        try:
            with contextlib.redirect_stdout(uscita):
                archivio.riattribuisci(self.cfg(), vecchio, nuovo, applica=True)
        except (SystemExit, Exception) as e:          # la scheda è cambiata lo stesso: l'archivio si sistema dopo
            return f"Le letture di «{vecchio}» non si sono spostate ({e}): python archivio.py riattribuisci."
        m = re.search(r"Aggiunte (\d+) letture", uscita.getvalue())
        return f" {m.group(1)} letture dell'archivio passano a «{nuovo}»." if m else ""

    def rinomina_scheda(self, nome, nuovo):
        nome, nuovo = (nome or "").strip(), (nuovo or "").strip()
        f = percorso(self.cfg(), "entita")
        self._copia_glossario(f)
        try:
            vecchio, nuovo, cambiate = schede.rinomina_scheda(f, nome, nuovo)
        except ValueError as e:
            raise Errore(str(e))
        self._registra_glossario(f, nuovo, [("nome", vecchio, nuovo)], "rinominata dal glossario dell'interfaccia")
        letture = self._sposta_letture(vecchio, nuovo)
        return {"vecchio": vecchio, "nuovo": nuovo, "collegate_aggiornate": cambiate,
                "nota": f"Scheda rinominata in «{nuovo}».{letture}"}

    def elimina_scheda(self, nome):
        nome = (nome or "").strip()
        f = percorso(self.cfg(), "entita")
        self._copia_glossario(f)
        try:
            nome, cambiate = schede.elimina_scheda(f, nome)
        except ValueError as e:
            raise Errore(str(e))
        self._registra_glossario(f, nome, [("scheda", nome, "")], "eliminata dal glossario dell'interfaccia")
        return {"scheda": nome, "collegate_aggiornate": cambiate,
                "nota": f"Scheda «{nome}» eliminata. I passaggi già letti restano nell'archivio; una copia del "
                        f"glossario di oggi è accanto al file."}

    def unisci_schede(self, da, verso):
        """Due schede della stessa entità diventano una: forme e collegate di «da» vanno in «verso», le letture
        dell'archivio pure, e «da» si toglie."""
        da, verso = (da or "").strip(), (verso or "").strip()
        f = percorso(self.cfg(), "entita")
        self._copia_glossario(f)
        try:
            cambi = schede.unisci_schede(f, da, verso)
        except ValueError as e:
            raise Errore(str(e))
        self._registra_glossario(f, verso, cambi + [("unita", da, verso)], "unite dal glossario dell'interfaccia")
        letture = self._sposta_letture(da, verso)
        return {"scheda": verso, "nota": f"«{da}» è ora parte di «{verso}».{letture}"}

    def forme_suggerite(self, nome):
        """Forme del nome trovate nei passaggi già letti e non ancora nella scheda (varianti.proposte), con quante
        volte compaiono e un esempio; quelle scartate prima non tornano."""
        import varianti as mod_varianti
        nome = (nome or "").strip()
        try:
            p = mod_varianti.proposte(self.cfg(), nome) or {}
        except Exception:
            p = {}
        voci = p.get(nome, []) if isinstance(p, dict) else []
        return {"scheda": nome, "forme": [{"forma": v.get("variante", ""), "volte": v.get("volte", 0),
                                           "esempio": (v.get("esempio") or {})} for v in voci[:30]]}

    def decidi_forme(self, nome, aggiungi=None, scarta=None):
        """Forme suggerite accettate (entrano tra le varianti) o scartate (non si propongono più)."""
        import varianti as mod_varianti
        nome = (nome or "").strip()
        aggiungi, scarta = _elenco(aggiungi), _elenco(scarta)
        f = percorso(self.cfg(), "entita")
        if aggiungi:
            prima = schede.leggi_scheda(f, nome)
            if prima is None:
                raise Errore(f"Scheda «{nome}» non trovata.")
            self._copia_glossario(f)
            varianti = prima["varianti"] + [x for x in aggiungi if x not in prima["varianti"]]
            try:                                       # le forme brevi entrano già ambigue (schede.forma_breve)
                cambi = schede.modifica_scheda(f, nome, {"varianti": varianti, "forme_ambigue": schede.con_brevi_ambigue(
                    [x for x in varianti if x in aggiungi], prima["forme_ambigue"])})
            except ValueError as e:
                raise Errore(str(e))
            self._registra_glossario(f, nome, cambi, "forme suggerite accettate dal glossario dell'interfaccia")
        if scarta:
            mod_varianti.scarta(self.cfg(), nome, scarta)
        brevi = [x for x in aggiungi if schede.forma_breve(x)]
        nota = "Rifai la ricerca: si leggono solo i passaggi delle forme nuove." if aggiungi else ""
        if brevi:
            nota += f" {'; '.join(brevi)}: forma breve, segnata come ambigua (il modello ne controlla sempre i passaggi)."
        return {"aggiunte": aggiungi, "scartate": scarta, "ambigue": brevi, "nota": nota.strip()}

    def conta_forme(self, forme):
        """{forma: righe delle fonti che la contengono}, una per una (il conteggio accanto a ogni forma mentre si
        modifica una scheda). None se l'indice non è pronto."""
        forme = _elenco(forme)[:40]
        ind, errore = M.indice_pronto()
        if errore:
            return {"conti": {f: None for f in forme}, "esempi": {}, "nota": "indice delle fonti in costruzione"}
        out, esempi = {}, {}
        for f in forme:
            try:
                righe = ind.cerca(f)
            except Exception:
                out[f] = None
                continue
            out[f] = len({(x["file"], x["riga"]) for x in righe})
            if righe:                                   # un esempio: la riga, e da dove viene
                x = righe[len(righe) // 2]
                esempi[f] = {"testo": re.sub(r"\s+", " ", x["testo"]).strip()[:280],
                             "riferimento": x.get("citazione") or x["file"], "file": x["file"], "riga": x["riga"]}
        return {"conti": out, "esempi": esempi, "brevi": [f for f in forme if schede.forma_breve(f)]}

    def pagina_scheda(self, nome):
        """Che cosa si sa già dell'entità, dall'archivio: passaggi letti e pertinenti, per anno e per serie; le
        ricerche fatte e le risposte salvate; le schede collegate."""
        import archivio
        nome = (nome or "").strip()
        c = self.cfg()
        f = percorso(c, "entita")
        s = schede.leggi_scheda(f, nome)
        if s is None:
            raise Errore(f"Scheda «{nome}» non trovata.")
        ris = percorso(c, "risultati")
        P = M.tutti_i_passaggi(ris)
        letti = pertinenti = 0
        per_anno, per_serie = {}, {}
        for (pid, e), v in archivio.Archivio(ris).per_id.items():
            if e != nome:
                continue
            a = v.get("analisi") or {}
            p = P.get((pid, e)) or {}
            letti += 1
            si = a.get("pertinente") == "sì"
            pertinenti += si
            anno = str(p.get("data") or "")[:4]
            if anno.isdigit():
                x = per_anno.setdefault(anno, [0, 0])
                x[0] += 1
                x[1] += si
            if si and p.get("fonte"):
                per_serie[p["fonte"]] = per_serie.get(p["fonte"], 0) + 1
        risposte = []
        try:
            for g in sorted(lavori.cartella_risposte(c).glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True):
                k = _chiave_risposta(g)
                if k and k[0] == nome.lower():
                    t = _intestazione_risposta(g)
                    risposte.append({"file": g.name, "data": _data(g), "domanda": t["domanda"] or nome,
                                     "evoluzione": k[1] == "evoluzione", "pertinenti": t["pertinenti"]})
        except OSError:
            pass
        cp = schede.leggi_schede(f)
        return {"scheda": nome, "tipo": s["tipo"], "letti": letti, "pertinenti": pertinenti,
                "per_anno": dict(sorted(per_anno.items())),
                "per_serie": dict(sorted(per_serie.items(), key=lambda x: -x[1])[:8]),
                "risposte": risposte[:10],
                "collegate": [{"nome": x, "esiste": x in cp.sections()} for x in s["collegate"]],
                "problemi": self._problemi_di(nome)}

    def controllo_glossario(self):
        """I problemi delle schede (schede.controlla, con le schede che hanno gli stessi passaggi): per le coppie
        di schede, «unibili» dice che si possono unire."""
        c = self.cfg()
        f = percorso(c, "entita")
        try:
            righe = schede.controlla(f, percorso(c, "risultati"))
        except Exception as e:
            raise Errore(f"Controllo non riuscito: {e}")
        cp = schede.leggi_schede(f)
        # quale correzione automatica risolve il problema (schede.correzioni); «note»: le scrive chi conosce l'entità
        tipi = (("forme brevi", "brevi"), ("forma ambigua «", "ambigue_fuori"), ("campo nome_completo", "campo:nome_completo"),
                ("campo forma_italiana", "campo:forma_italiana"), ("note vuote", "note"))
        out = []
        for g, s, p in righe:
            coppia = [x.strip() for x in s.split(" / ")]
            unibili = len(coppia) == 2 and all(x in cp.sections() for x in coppia) and bool(
                re.search(r"stessa forma|stessi (\d+ )?passaggi", p))
            x = {"gravita": g, "schede": coppia, "problema": p, "unibili": unibili}
            tipo = next((t for inizio, t in tipi if p.startswith(inizio)), None)
            if tipo and len(coppia) == 1 and coppia[0] in cp.sections():
                if tipo == "note":
                    x["correzione"] = {"tipo": "note", "descrizione": "Scrivi le note"}
                else:
                    c = next((c for c in schede.correzioni(f, coppia[0]) if c["tipo"] == tipo), None)
                    if c:
                        x["correzione"] = c
            out.append(x)
        automatiche = sum(1 for x in out if x.get("correzione") and x["correzione"]["tipo"] != "note")
        return {"problemi": out, "errori": sum(1 for x in out if x["gravita"] == "errore"),
                "avvisi": sum(1 for x in out if x["gravita"] == "avviso"), "automatiche": automatiche}

    # profili delle serie (series.ini): stessi strumenti, con l'anteprima della citazione su un documento vero
    def _file_serie(self):
        return percorso(self.cfg(), "serie")

    def leggi_serie(self, nome):
        nome = (nome or "").strip()
        cp = schede.leggi_schede(self._file_serie())
        if nome not in cp.sections():
            raise Errore(f"Serie «{nome}» non trovata.")
        return {"serie": nome, "campi": {k: v.strip() for k, v in cp[nome].items()},
                "tipi": ["periodico", "articolo", "volume", "archivio", "raccolta"]}

    def modifica_serie(self, nome, campi):
        nome = (nome or "").strip()
        if not isinstance(campi, dict) or not campi:
            raise Errore("Niente da cambiare.")
        f = self._file_serie()
        self._copia_glossario(f)
        try:
            cambi = schede.modifica_sezione(f, nome, campi)
        except ValueError as e:
            raise Errore(str(e))
        self._registra_glossario(f, nome, cambi, "modificata dal glossario dell'interfaccia")
        profili.tutti(ricarica=True)
        return {"serie": nome, "cambiati": [c for c, _, _ in cambi],
                "nota": "Profilo salvato. Le citazioni nuove lo usano; le risposte già scritte restano come sono."
                if cambi else "Nessun cambiamento."}

    def anteprima_serie(self, nome, campi=None):
        """La citazione che il profilo (con le modifiche non ancora salvate) dà su un documento vero della serie."""
        import citazioni
        nome = (nome or "").strip()
        dati = percorso(self.cfg(), "dati")
        cp = schede.leggi_schede(self._file_serie())
        base = {k: v.strip() for k, v in cp[nome].items()} if nome in cp.sections() else {}
        base.update({k: str(v) for k, v in (campi or {}).items()})
        documento, meta = None, None
        for k, f in enumerate(sorted(dati.rglob("*.txt"))):
            if k > 5000:
                break
            try:
                with open(f, encoding="utf-8", errors="replace") as h:
                    m, _ = leggi_intestazione(h.read(6000))
            except OSError:
                continue
            if (m.get("SERIES") or "").strip() == nome:
                documento, meta = f.relative_to(dati).as_posix(), m
                break
        if meta is None:
            return {"documento": "", "citazione": "", "nota": "Nessun documento di questa serie tra le fonti."}
        try:
            profilo = profili.completa(nome, base)
            testo = citazioni.voce(meta, profilo, pagina="12")
        except Exception as e:
            return {"documento": documento, "citazione": "", "errore": f"Il modello non funziona: {e}"}
        out = {"documento": documento, "titolo": meta.get("TITLE") or documento, "citazione": testo,
               "nota": "Con la pagina 12 come esempio."}
        # segnaposti che il motore non conosce (diventerebbero vuoti senza dirlo) o graffe rimaste nel testo
        noti = set(citazioni.valori_da_intestazione(meta, profilo)) | {"pagina"}
        ignoti = [n for n in dict.fromkeys(re.findall(r"\{(\w+)\}", profilo.get("chicago") or "")) if n not in noti]
        resti = re.findall(r"\{[^{}]*\}?", testo)
        if ignoti or resti:
            out["errore"] = "Segnaposti sconosciuti: " + ", ".join("{" + n + "}" for n in ignoti) if ignoti else \
                "Nel modello restano parti non riconosciute: " + ", ".join(dict.fromkeys(resti))
            out["segnaposti"] = sorted(noti)
        return out

    def avvia(self, entita, domanda="", dal=None, al=None, fonti=None, evoluzione=False):
        r = M.t_avvia_ricerca(entita, modalita="evoluzione" if evoluzione else "occorrenze",
                              dal=_anno(dal), al=_anno(al), fonti=_elenco(fonti), domanda=domanda or "")
        if r.get("errore") and not r.get("gia_in_corso"):
            raise Errore(r["errore"] + (f" Forse: {', '.join(r['forse'])}." if r.get("forse") else ""))
        return r

    def stato_ricerca(self):
        """La ricerca in corso, o l'ultima (senza attese: la pagina richiede lo stato ogni pochi secondi)."""
        try:
            c = self.cfg()
            d, s_ = lavori.attivo(c)
            if not d:
                d, s_ = lavori.ultimo(c)
        except Exception:
            return {"nessuna": True}
        if not d:
            return {"nessuna": True}
        out = M.compatto(s_)
        out.pop("nota", None)                # le indicazioni per il modello della chat qui non servono
        par = s_.get("parametri") or {}
        out.update({"id": s_.get("id", d.name), "domanda": s_.get("domanda", ""),
                    "entita": par.get("principale", ""),
                    # i filtri con cui è partita: «Riprova» li riusa, invece di quelli scelti nel frattempo
                    "filtri": {"dal": str(par.get("dal") or ""), "al": str(par.get("al") or ""),
                               "fonti": list(par.get("fonti") or []),
                               "evoluzione": par.get("modalita") == "evoluzione"}})
        if not out.get("finito"):
            ultimi = [m for m in s_.get("ultimi_messaggi") or [] if not m.startswith("---")]
            if ultimi:
                out["ultimo_messaggio"] = ultimi[-1]
            # quanti passaggi sono già letti, dal file della ricerca: non dipende da ciò che il processo stampa
            letti = self._passaggi_letti(s_.get("parametri") or {})
            if letti:
                out["letti"] = letti
        pronta = out.get("risposta_pronta")
        if pronta:
            pronta.pop("nota", None)
            out["documento"] = "/documento?" + urllib.parse.urlencode({"risposta": pronta.get("file", "")})
        return out

    def _passaggi_letti(self, parametri):
        """(letti, estratti, pertinenti) della ricerca: righe distinte di classificati.jsonl e di passaggi.jsonl, e
        quante delle lette il modello ha giudicato pertinenti finora (la pagina lo mostra durante la lettura)."""
        def ids(f, solo_pertinenti=False):
            with open(f, encoding="utf-8") as h:
                return {m.group(1) for r in h
                        if not solo_pertinenti or re.search(r'"pertinente":\s*"s(?:ì|\\u00ec)"', r)
                        for m in [re.search(r'"id":\s*"([^"]+)"', r)] if m}
        try:
            d = lavori.cartella_ricerca(self.cfg(), parametri)
            estratti = ids(d / "passaggi.jsonl")
            letti = ids(d / "classificati.jsonl") & estratti      # non le letture di ricerche precedenti
            pertinenti = ids(d / "classificati.jsonl", True) & estratti
        except (OSError, KeyError, TypeError):
            return None
        return ({"letti": len(letti), "estratti": len(estratti), "pertinenti": len(pertinenti)}
                if estratti else None)

    def ferma(self):
        return M.t_ferma_ricerca()

    def storico(self):
        if not self.progetto_in_uso():
            return {"risposte": [], "ricerche": []}
        c = self.cfg()
        risposte = M.t_elenca_risposte(50).get("risposte", [])
        for r in risposte:
            r["documento"] = "/documento?" + urllib.parse.urlencode({"risposta": r["file"]})
            t = _intestazione_risposta(lavori.cartella_risposte(c) / r["file"])
            r.update(entita=t["entita"], pertinenti=t["pertinenti"], evoluzione=t["evoluzione"])
        ricerche = []
        base = percorso(c, "risultati") / "searches"
        if base.is_dir():
            for d in sorted(base.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                f = d / "risposta.html"
                if f.is_file():
                    t = _intestazione_risposta(d / "risposta.md")
                    entita, domanda = t["entita"], t["domanda"]
                    ricerche.append({"cartella": d.name, "data": _data(f), "entita": entita, "domanda": domanda,
                                     "pertinenti": t["pertinenti"],
                                     "evoluzione": t["evoluzione"] or d.name.endswith("_evoluzione"),
                                     "documento": "/documento?" + urllib.parse.urlencode({"ricerca": d.name})})
        return {"risposte": risposte, "ricerche": ricerche[:50]}

    def documento(self, risposta="", ricerca=""):
        """Il file HTML di una risposta, solo dentro le cartelle delle risposte e delle ricerche del progetto."""
        c = self.cfg()
        if risposta:
            if Path(risposta).name != risposta or not risposta.endswith(".md"):
                raise Errore("Risposta non valida.")
            f = (lavori.cartella_risposte(c) / risposta).with_suffix(".html")
        elif ricerca:
            if Path(ricerca).name != ricerca or ricerca in (".", ".."):
                raise Errore("Ricerca non valida.")
            f = percorso(c, "risultati") / "searches" / ricerca / "risposta.html"
        else:
            raise Errore("Quale documento?")
        # il documento si riscrive dal Markdown se manca o se è più vecchio di documento.py (impaginazione nuova)
        md = f.with_suffix(".md")
        stile = CARTELLA / "documento.py"
        if md.is_file() and (not f.exists() or f.stat().st_mtime < stile.stat().st_mtime):
            from documento import scrivi_html
            try:
                scrivi_html(md)
            except OSError:
                pass                    # si mostra il documento che c'è
        if not f.is_file():
            raise Errore("Documento non trovato.")
        return f

    def corpo_documento(self, risposta="", ricerca=""):
        """Il corpo HTML del documento di una risposta, da mettere nel filo della pagina (documento.py scrive
        testo sempre con escape; la pagina toglie comunque script e attributi on*)."""
        t = self.documento(risposta, ricerca).read_text(encoding="utf-8", errors="replace")
        a, b = t.find("<body>"), t.rfind("</body>")
        return {"corpo": t[a + 6:b] if 0 <= a < b else ""}

    # ------------------------------------------------------------ fili
    # Un filo è una conversazione della pagina: messaggi di chi scrive, ricerche avviate, risposte (il documento),
    # repliche della conversazione con il modello. Un file JSON per filo in results/fili; la pagina lo riscrive
    # intero a ogni messaggio.
    def _cartella_fili(self):
        return percorso(self.cfg(), "risultati") / "fili"

    def _file_filo(self, ident):
        if not re.fullmatch(r"[0-9a-f]{16}", str(ident or "")):
            raise Errore("Conversazione non valida.")
        return self._cartella_fili() / f"{ident}.json"

    def rinomina_filo(self, ident, titolo):
        """Il titolo di una conversazione nei recenti; il contenuto resta com'è."""
        titolo = str(titolo or "").strip()[:200]
        if not titolo:
            raise Errore("Scrivi il nome della conversazione.")
        f = self._file_filo(ident)
        if not f.is_file():
            raise Errore("Conversazione non trovata.")
        dati = json.loads(f.read_text(encoding="utf-8"))
        dati["titolo"] = titolo
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(dati, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(f)
        return {"id": ident, "titolo": titolo}

    def elimina_filo(self, ident):
        """Toglie una conversazione dai recenti. Le risposte e i passaggi letti restano nell'archivio del progetto:
        si cancella solo il file della conversazione."""
        f = self._file_filo(ident)
        if f.is_file():
            f.unlink()
        return {"id": ident, "eliminato": True}

    def fili(self):
        if not self.progetto_in_uso():
            return {"fili": []}
        out = []
        d = self._cartella_fili()
        for f in (d.glob("*.json") if d.is_dir() else []):
            try:
                x = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            messaggi = [m for m in x.get("messaggi") or [] if isinstance(m, dict)]
            tipi = {m.get("tipo") for m in messaggi}
            # lo stato si legge nella barra dei recenti: una risposta, una ricerca partita, o solo una domanda
            stato_filo = ("risposta" if tipi & {"risposta", "conversazione"} else
                          "avviata" if "ricerca" in tipi or x.get("ricerca") else "non avviata")
            # per distinguere le ricerche nei recenti: i filtri dell'ultima ricerca e i documenti pertinenti
            # dell'ultima risposta (i fili di prima non hanno filtri salvati)
            ricerche = [m for m in messaggi if m.get("tipo") == "ricerca"]
            risposte = [m for m in messaggi if m.get("tipo") == "risposta"]
            filtri = ricerche[-1].get("filtri") if ricerche else None
            pertinenti = risposte[-1].get("pertinenti") if risposte else None
            out.append({"id": x.get("id", f.stem), "titolo": x.get("titolo", ""), "entita": x.get("entita", ""),
                        "domanda": x.get("domanda", ""), "stato": stato_filo,
                        "aggiornato": x.get("aggiornato", ""), "ricerca": x.get("ricerca", ""),
                        "filtri": filtri if isinstance(filtri, dict) else None,
                        "pertinenti": "" if pertinenti is None else str(pertinenti),
                        "documenti": [m.get("documento") for m in risposte]})
        out.sort(key=lambda x: x["aggiornato"], reverse=True)
        return {"fili": out[:200]}

    def filo(self, ident):
        f = self._file_filo(ident)
        if not f.is_file():
            raise Errore("Conversazione non trovata.")
        return json.loads(f.read_text(encoding="utf-8"))

    def salva_filo(self, filo):
        if not isinstance(filo, dict) or not isinstance(filo.get("messaggi"), list):
            raise Errore("Conversazione non valida.")
        ident = filo.get("id") or secrets.token_hex(8)
        f = self._file_filo(ident)
        ora = dt.datetime.now().isoformat(timespec="seconds")
        dati = {"id": ident, "titolo": str(filo.get("titolo") or "")[:200], "entita": str(filo.get("entita") or "")[:200],
                "domanda": str(filo.get("domanda") or "")[:1000], "ricerca": str(filo.get("ricerca") or "")[:200],
                "creato": str(filo.get("creato") or ora), "aggiornato": ora,
                "messaggi": [m for m in filo["messaggi"] if isinstance(m, dict)][:1000]}
        testo = json.dumps(dati, ensure_ascii=False, indent=1)
        if len(testo) > 5_000_000:
            raise Errore("Conversazione troppo lunga per essere salvata.")
        f.parent.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(".tmp")
        tmp.write_text(testo, encoding="utf-8")
        tmp.replace(f)
        return {"id": ident, "creato": dati["creato"], "aggiornato": ora}

    def fonti(self):
        if not self.progetto_in_uso():
            return {"fonti": []}
        profili.tutti(ricarica=True)
        M.FONTI_SCELTE = sorted({profili.gruppo(n) for n in profili.tutti()})
        return {"fonti": M.FONTI_SCELTE}

    # ------------------------------------------------------------ visore della fonte, passaggi, glossario
    # La scheda «Fonte» mostra una pagina del documento: il testo di data/ con la riga del passaggio evidenziata e,
    # se l'originale è un PDF in sources/ e c'è PyMuPDF, l'immagine della pagina. Le pagine sono quelle dei
    # marcatori [[p. N | pdf K]]; un file senza marcatori si sfoglia a blocchi di righe (posizione nel file).
    def _file_dati(self, file):
        dati = percorso(self.cfg(), "dati").resolve()
        f = (dati / (file or "").replace("\\", "/")).resolve()
        if dati not in f.parents or not f.is_file() or f.suffix.lower() != ".txt":
            raise Errore("File non trovato tra le fonti del progetto.")
        return f

    def _originale(self, meta):
        """Il PDF originale del documento (SOURCE_FILE, dentro sources/), o None."""
        rel = (meta.get("SOURCE_FILE") or "").replace("\\", "/")
        if not rel.lower().endswith(".pdf"):
            return None
        originali = percorso(self.cfg(), "originali").resolve()
        f = (originali / rel).resolve()
        return f if originali in f.parents and f.is_file() else None

    def fonte(self, file, riga="", pagina="", etichetta="", tra="", ocr=""):
        """Una pagina della fonte. `etichetta` (il numero stampato, «47») sceglie la pagina citata; `tra` (righe
        separate da virgole: quelle del passaggio) dice quale riga evidenziare in quella pagina. «ocr_pagina»: la
        pagina aspetta l'OCR per evidenze e strato; la stessa richiesta con `ocr`=1 lo legge (_pagina_pdf)."""
        f = self._file_dati(file)
        righe = f.read_text(encoding="utf-8", errors="replace").splitlines()
        meta, _ = leggi_intestazione("\n".join(righe[:80]))
        pagine = _pagine(righe)
        riga = int(riga) if str(riga or "").isdigit() else None
        citata = next((k for k, p in enumerate(pagine, 1) if etichetta and p["etichetta"] == f"p. {etichetta}"), None)
        if citata:
            n = citata
            p = pagine[n - 1]
            riga = next((int(x) for x in str(tra or "").split(",")
                         if x.strip().isdigit() and p["da"] <= int(x) <= p["a"]), riga)
        elif str(pagina or "").isdigit() and 1 <= int(pagina) <= len(pagine):
            n = int(pagina)
        elif riga:
            n = next((k for k, p in enumerate(pagine, 1) if p["da"] <= riga <= p["a"]), 1)
        else:
            n = 1
        p = pagine[n - 1]
        immagine, originale, evidenze, strato, serve_ocr = "", "", [], [], False
        if self._originale(meta) is not None:
            originale = "/fonte/pdf?" + urllib.parse.urlencode({"file": file})
            if p.get("pdf"):
                originale += f"#page={p['pdf']}"
                if _fitz() is not None:
                    immagine = "/fonte/pagina?" + urllib.parse.urlencode({"file": file, "pdf": p["pdf"]})
                    evidenze, strato, serve_ocr = self._pagina_pdf(meta, p["pdf"], righe, p, riga, ocr == "1")
        titolo = meta.get("TITLE") or " ".join(x for x in (meta.get("SERIES"), meta.get("DATE")) if x)
        return {"file": file, "titolo": titolo or f.stem, "citazione": meta.get("FULL_CITATION", ""),
                "pagine": [{"etichetta": x["etichetta"], "pdf": x.get("pdf")} for x in pagine], "pagina": n,
                "righe": [{"n": k, "testo": righe[k - 1]} for k in range(p["da"], p["a"] + 1)],
                "evidenzia": riga if riga and p["da"] <= riga <= p["a"] else None, "immagine": immagine,
                "originale": originale, "evidenze": evidenze, "strato": strato, "ocr_pagina": serve_ocr}

    def immagine_pagina(self, file, pdf, dpi=""):
        """La pagina `pdf` (1 = la prima) del PDF originale, in PNG; `dpi` 150 di norma, fino a 300 per l'ingrandimento."""
        f = self._file_dati(file)
        meta, _ = leggi_intestazione(f.read_text(encoding="utf-8", errors="replace")[:20000])
        originale, fitz = self._originale(meta), _fitz()
        if originale is None or fitz is None:
            raise Errore("Originale non disponibile.")
        risoluzione = min(max(int(dpi), 72), 300) if str(dpi or "").isdigit() else 150
        with fitz.open(originale) as doc:
            k = int(pdf) if str(pdf or "").isdigit() else 0
            if not 1 <= k <= len(doc):
                raise Errore("Pagina inesistente.")
            return doc[k - 1].get_pixmap(dpi=risoluzione).tobytes("png")

    def pdf_originale(self, file):
        """(byte, nome) del PDF originale del documento, per aprirlo nel lettore del browser."""
        f = self._file_dati(file)
        meta, _ = leggi_intestazione(f.read_text(encoding="utf-8", errors="replace")[:20000])
        originale = self._originale(meta)
        if originale is None:
            raise Errore("Originale non disponibile.")
        return originale.read_bytes(), originale.name

    def _parole_ocr(self, originale, meta, pdf, leggi):
        """Le parole della pagina `pdf` lette con Tesseract, con la loro posizione (importa.parole_tsv), dalla
        cache del progetto (system/cache/ocr_pagine); se mancano e `leggi`, le legge ora (un paio di secondi a
        pagina) e le conserva. None se mancano, o se Tesseract o le sue lingue non ci sono. L'importazione tiene
        il solo testo dell'OCR: le posizioni si ricavano qui, la prima volta che la pagina si guarda."""
        import hashlib
        import importa
        lingue = importa.LINGUE_OCR.get(meta.get("LANG", ""), meta.get("LANG", "")) or "eng"
        st = originale.stat()
        firma = hashlib.sha1(f"{originale}|{st.st_size}|{st.st_mtime_ns}|{lingue}".encode("utf-8")).hexdigest()[:20]
        f = percorso(self.cfg(), "cache") / "ocr_pagine" / firma / f"{pdf:05d}.json"
        if f.is_file():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                pass
        if not leggi:
            return None
        with _BLOCCO_OCR.setdefault(str(f), threading.Lock()):     # due richieste per la stessa pagina: una lettura
            if f.is_file():
                return json.loads(f.read_text(encoding="utf-8"))
            try:
                ocr = importa.Ocr(self.cfg(), lingue)
            except SystemExit:                  # Tesseract o le lingue del documento mancano
                return None
            fitz = _fitz()
            with fitz.open(originale) as doc:
                pix = doc[pdf - 1].get_pixmap(dpi=ocr.dpi, colorspace=fitz.csGRAY)
            f.parent.mkdir(parents=True, exist_ok=True)
            img = f.with_suffix(".png")
            try:
                pix.save(img)
                parole = ocr.leggi_parole(img, pix.width, pix.height)
            except (OSError, RuntimeError, subprocess.SubprocessError):
                return None
            finally:
                img.unlink(missing_ok=True)
            f.write_text(json.dumps(parole, ensure_ascii=False), encoding="utf-8")
            return parole

    def _pagina_pdf(self, meta, pdf, righe, p, riga, leggi_ocr=False):
        """Che cosa sta sopra l'immagine della pagina `pdf`: (evidenze, strato, serve l'OCR). «evidenze»: le righe
        della pagina dove si ritrova il passaggio, con «citata» quelle della riga citata; «strato»: il testo da
        selezionare, riga per riga; tutto in frazioni della pagina. Il passaggio è il capoverso della riga citata
        (fino a 4 righe prima e dopo, senza uscire dalla pagina).
        Le parole vengono dallo strato di testo del PDF, se la trascrizione viene da lì; altrimenti (scansione
        senza strato, o strato scartato all'importazione perché peggiore dell'OCR) dall'OCR della pagina, che si
        legge una volta e si conserva. «serve l'OCR»: la pagina ne ha bisogno e non è ancora letta (la pagina
        richiede di nuovo con leggi_ocr, così la vista non aspetta Tesseract). Con un riscontro troppo debole:
        niente evidenze, e la pagina mostra l'estratto."""
        fitz, originale = _fitz(), self._originale(meta)
        if fitz is None or originale is None or not pdf:
            return [], [], False
        metodo = meta.get("TEXT_METHOD", "")
        scartato = metodo.startswith("OCR proprio") and "+" not in metodo
        try:
            with fitz.open(originale) as doc:
                if not 1 <= pdf <= len(doc):
                    return [], [], False
                pag = doc[pdf - 1]
                area, giro = pag.rect, pag.rotation_matrix
                parole = []
                if not scartato and area.width and area.height:
                    for w in pag.get_text("words"):
                        r = fitz.Rect(w[:4]) * giro
                        parole.append([r.x0 / area.width, r.y0 / area.height, r.x1 / area.width,
                                       r.y1 / area.height, w[4], w[5], w[6]])
        except Exception:                      # PDF guasto o cifrato: la pagina resta senza evidenze
            return [], [], False
        if not parole:
            parole = self._parole_ocr(originale, meta, pdf, leggi_ocr)
            if parole is None:
                return [], [], not leggi_ocr
        if not parole:
            return [], [], False

        def riquadro(indici):
            return [round(max(0.0, min(parole[i][0] for i in indici)), 4),
                    round(max(0.0, min(parole[i][1] for i in indici)), 4),
                    round(min(1.0, max(parole[i][2] for i in indici)), 4),
                    round(min(1.0, max(parole[i][3] for i in indici)), 4)]

        def per_linea(indici):              # le parole raggruppate per riga (blocco, riga)
            out = {}
            for i in indici:
                out.setdefault((parole[i][5], parole[i][6]), []).append(i)
            return out.values()

        strato = [riquadro(idx) + [" ".join(parole[i][4] for i in idx)] for idx in per_linea(range(len(parole)))]
        evidenze = []
        if riga and p["da"] <= riga <= p["a"]:
            vuota = lambda k: not righe[k - 1].strip() or righe[k - 1].lstrip().startswith("[")
            da = riga
            while da > max(p["da"], riga - 4) and not vuota(da - 1):
                da -= 1
            a = riga
            while a < min(p["a"], riga + 4) and not vuota(a + 1):
                a += 1
            capoverso = _trova_nel_pdf(parole, "\n".join(righe[k - 1] for k in range(da, a + 1)))
            if capoverso:
                # la riga citata: le righe della pagina che ne condividono di più i frammenti (di norma una, due se
                # la trascrizione va a capo altrove)
                cercata = _normale(righe[riga - 1])
                frammenti = {cercata[k:k + 3] for k in range(len(cercata) - 2)}
                linee = list(per_linea(range(capoverso[0], capoverso[1] + 1)))
                quote = []
                for idx in linee:
                    t = _normale("".join(parole[i][4] for i in idx))
                    propri = {t[k:k + 3] for k in range(len(t) - 2)}
                    # una riga di una parola sola starebbe tutta nella citata: conta almeno 8 frammenti
                    quote.append(len(propri & frammenti) / max(8, min(len(propri), len(frammenti))))
                meglio = max(quote, default=0)
                for idx, q in zip(linee, quote):
                    evidenze.append({"r": riquadro(idx), "citata": meglio >= .4 and q >= .75 * meglio})
        return evidenze, strato, False

    def _cartella_ricerca_nome(self, ricerca):
        if not ricerca or Path(ricerca).name != ricerca or ricerca in (".", ".."):
            raise Errore("Ricerca non valida.")
        cartella = percorso(self.cfg(), "risultati") / "searches" / ricerca
        if not cartella.is_dir():
            raise Errore("Ricerca non trovata.")
        return cartella

    def _ricerca_della_risposta(self, md):
        """La cartella della ricerca che ha scritto una risposta salvata, dall'intestazione che lavori.salva_risposta
        mette in cima («<!-- Domanda: … | entità: … | occorrenze -->»); None per le risposte senza intestazione."""
        try:
            with open(md, encoding="utf-8", errors="replace") as h:
                testa = h.read(800)
        except OSError:
            return None
        m = re.search(r"<!-- Domanda: .*? \| entità: (.*?)(?: \+ [^|]*)? \| (occorrenze|evoluzione)", testa)
        if not m:
            return None
        try:
            d = lavori.cartella_ricerca(self.cfg(), {"principale": m.group(1).strip(), "modalita": m.group(2)})
        except (KeyError, TypeError):
            return None
        return d if d.is_dir() else None

    def _lingue_dei_file(self):
        """{file: lingua} dall'indice delle fonti, se è pronto (le faccette dei passaggi); {} altrimenti."""
        try:
            ind, errore = M.indice_pronto()
            if errore:
                return {}
            return {r[1]: r[6] or "" for r in ind._file().values()}
        except Exception:
            return {}

    def passaggi(self, risposta="", ricerca=""):
        """I passaggi del documento aperto: quelli letti dalla ricerca (classificati.jsonl), con pertinenza, chi li
        ha letti, traduzione, serie e lingua (le faccette del pannello); per una risposta salvata, quelli letti dalla
        ricerca che l'ha scritta, con il numero [n] di quelli citati. Senza la cartella della ricerca, solo i citati.
        «rimandi»: [n] della risposta -> file e riga, dalla sezione «Dati tecnici per la verifica» (la pagina li usa
        per aprire la fonte dal documento). «ricerca»: la cartella, per correzioni ed esportazioni."""
        if ricerca:                     # anche le ricerche vecchie, senza il documento HTML
            cartella = self._cartella_ricerca_nome(ricerca)
            md = cartella / "risposta.md"
        else:
            md = self.documento(risposta).with_suffix(".md")
            cartella = self._ricerca_della_risposta(md)
        testo = md.read_text(encoding="utf-8", errors="replace") if md.is_file() else ""
        rimandi = _rimandi(testo)
        out = []
        if cartella is not None and (cartella / "classificati.jsonl").is_file():
            estratti = _ids_jsonl(cartella / "passaggi.jsonl")
            visti = {}
            with open(cartella / "classificati.jsonl", encoding="utf-8") as h:
                for r in h:
                    try:
                        p = json.loads(r)
                    except ValueError:
                        continue
                    if estratti and p.get("id") not in estratti:
                        continue                         # letture di ricerche precedenti
                    visti[p.get("id")] = _vista_lettura(p)      # un passaggio riletto: vale l'ultima lettura
            out = list(visti.values())
            out.sort(key=lambda x: (x["data"], x["file"], int(x["riga"]) if x["riga"].isdigit() else 0))
            # la pagina che il modello non ha indicato si ricava dai marcatori del file (letto una volta per file)
            pagine_file = {}
            for x in out:
                if x["pagina"] or not x["riga"].isdigit():
                    continue
                if x["file"] not in pagine_file:
                    try:
                        testo_f = self._file_dati(x["file"]).read_text(encoding="utf-8", errors="replace")
                        pagine_file[x["file"]] = [p for p in _pagine(testo_f.splitlines())
                                                  if p["etichetta"].startswith("p. ")]
                    except (Errore, OSError):
                        pagine_file[x["file"]] = []
                k = int(x["riga"])
                x["pagina"] = next((p["etichetta"][3:] for p in pagine_file[x["file"]] if p["da"] <= k <= p["a"]), "")
            # i citati nella risposta: il passaggio dello stesso file che comincia più vicino prima della riga citata
            per_file = {}
            for x in out:
                if x["riga"].isdigit():
                    per_file.setdefault(x["file"], []).append(x)
            for n, v in rimandi.items():
                for riga in v.get("righe") or [v["riga"]]:
                    vicini = [x for x in per_file.get(v["file"], []) if int(x["riga"]) <= riga]
                    if vicini:
                        x = max(vicini, key=lambda y: int(y["riga"]))
                        if riga - int(x["riga"]) <= 40 and "n" not in x:
                            x["n"] = n
                            break
            lingue = self._lingue_dei_file()
            for x in out:
                x["lingua"] = lingue.get(x["file"], "")
        else:
            cartella = None
            for n, v in rimandi.items():
                out.append({"n": n, "fonte": v["riferimento"], "pertinente": "sì", "file": v["file"],
                            "riga": str(v["riga"]), "pagina": v.get("pagina", "")})
        return {"passaggi": out, "rimandi": rimandi, "ricerca": cartella.name if cartella is not None else "",
                "tutti": cartella is not None}

    # ------------------------------------------------------------ lettura dal vivo, correzioni, confronti
    def _cartella_attiva(self):
        """(cartella del lavoro, cartella della ricerca) della ricerca in corso, o dell'ultima."""
        c = self.cfg()
        d, s_ = lavori.attivo(c)
        if not d:
            d, s_ = lavori.ultimo(c)
        if not d:
            return None, None
        try:
            return d, lavori.cartella_ricerca(c, (s_ or {}).get("parametri") or {})
        except (KeyError, TypeError):
            return d, None

    def letture_ricerca(self, dopo=0):
        """Le letture scritte in classificati.jsonl dopo la riga «dopo» (al più le ultime 12): la pagina le mostra
        mentre il modello legge. «righe» va ripassato la volta dopo; «azzera»: il file è più corto di prima (una
        ricerca nuova), la pagina ricomincia."""
        dopo = int(dopo) if str(dopo or "").isdigit() else 0
        try:
            _, cart = self._cartella_attiva()
        except Exception:
            cart = None
        if cart is None or not (cart / "classificati.jsonl").is_file():
            return {"righe": 0, "letture": [], "nuove": 0, "azzera": dopo > 0}
        estratti = _ids_jsonl(cart / "passaggi.jsonl")
        nuove, n = [], 0
        with open(cart / "classificati.jsonl", encoding="utf-8") as h:
            for n, r in enumerate(h, 1):
                if n <= dopo or not r.strip():
                    continue
                try:
                    p = json.loads(r)
                except ValueError:
                    continue
                if estratti and p.get("id") not in estratti:
                    continue
                nuove.append(_vista_lettura(p))
        return {"righe": n, "letture": nuove[-12:], "nuove": len(nuove), "azzera": n < dopo,
                "ricerca": cart.name}

    def riprova_ricerca(self):
        """«Riprova ora»: la ricerca in attesa delle quote non aspetta l'orario previsto."""
        d, s_ = lavori.attivo(self.cfg())
        if not d:
            raise Errore("Nessuna ricerca in corso.")
        if (s_ or {}).get("stato") != "in attesa":
            return {"riprova": False, "nota": "La ricerca non è in attesa: sta già lavorando."}
        lavori.riprova_ora(d)
        return {"riprova": True, "nota": "Riprovo adesso: se le quote non sono ancora tornate, la ricerca riaspetta."}

    def correggi_passaggio(self, ricerca, id, pertinente=None, traduzione=None):
        """Una correzione a mano dal pannello dei passaggi: pertinenza e/o traduzione. Si scrive nella lettura della
        ricerca (classificati.jsonl, così il pannello e la prossima sintesi la vedono) e nell'archivio unico, come
        lettura «correzione manuale»: nessuna ricerca successiva la rimanda al modello (archivio.letto_da)."""
        from archivio import LETTURE, NOME, _blocco, append_jsonl, escluso, impronta, livello, provenienza
        if pertinente not in (None, "", "sì", "no", "incerto"):
            raise Errore("Pertinenza non valida: sì, no o incerto.")
        traduzione = (traduzione or "").strip() if traduzione is not None else None
        if not pertinente and not traduzione:
            raise Errore("Niente da correggere.")
        cart = self._cartella_ricerca_nome(ricerca)
        f = cart / "classificati.jsonl"
        if not f.is_file():
            raise Errore("Questa ricerca non ha passaggi letti.")
        oggi = dt.date.today().isoformat()
        da = livello("sessione", "correzione dall'interfaccia")
        trovato, analisi = None, None
        with _blocco(f):
            righe = f.read_text(encoding="utf-8").splitlines(keepends=True)
            for k, r in enumerate(righe):
                if f'"{id}"' not in r:
                    continue
                try:
                    p = json.loads(r)
                except ValueError:
                    continue
                if p.get("id") != id:
                    continue
                a = dict(p.get("analisi") or {})
                prima = provenienza(a)
                if pertinente:
                    a["pertinente"] = pertinente
                if traduzione:
                    a["traduzione_it"] = traduzione
                a.update(corretto_a_mano=True, classificato_da="correzione manuale", corretto_il=oggi,
                         motivazione="Correzione manuale dall'interfaccia")
                a["provenienza"] = {"decisione": da if pertinente else prima.get("decisione"),
                                    "lettura": da if traduzione else prima.get("lettura")}
                p["analisi"] = a
                righe[k] = json.dumps(p, ensure_ascii=False) + "\n"
                trovato, analisi = p, a
            if trovato is None:
                raise Errore("Passaggio non trovato in questa ricerca.")
            tmp = f.with_name(f.name + ".tmp")
            tmp.write_text("".join(righe), encoding="utf-8", newline="\n")
            try:
                os.replace(tmp, f)
            except PermissionError:          # Windows: il file è aperto da un'altra lettura; si riscrive sul posto
                f.write_text("".join(righe), encoding="utf-8", newline="\n")
                tmp.unlink(missing_ok=True)
        if not escluso(cart):
            arch = percorso(self.cfg(), "risultati") / NOME / LETTURE
            arch.parent.mkdir(parents=True, exist_ok=True)
            append_jsonl(arch, [json.dumps({"id": trovato["id"], "entita": trovato.get("entita", ""),
                                            "file": trovato.get("file", ""), "impronta": impronta(trovato),
                                            "origine": "correzione manuale", "letto_il": oggi, "analisi": analisi},
                                           ensure_ascii=False)])
        return {"passaggio": _vista_lettura(trovato),
                "nota": "Corretto. La risposta cambia quando rifai la ricerca: le ricerche successive usano la "
                        "correzione e non rimandano il passaggio al modello."}

    def confronto(self, risposta):
        """Che cosa è cambiato rispetto alla risposta precedente sulla stessa entità (stessa modalità): passaggi
        citati adesso e non prima (nuovi documenti importati, correzioni), citati prima e non più, e la risposta
        breve di allora e di adesso. {"precedente": None} se è la prima."""
        f = self.documento(risposta).with_suffix(".md")
        if not f.is_file():
            raise Errore("Risposta non trovata.")
        chiave = _chiave_risposta(f)
        if not chiave:
            return {"precedente": None}
        prima = [g for g in f.parent.glob("*.md")
                 if g != f and g.stat().st_mtime < f.stat().st_mtime and _chiave_risposta(g) == chiave]
        if not prima:
            return {"precedente": None}
        g = max(prima, key=lambda x: x.stat().st_mtime)
        ra = _rimandi(g.read_text(encoding="utf-8", errors="replace"))
        rb = _rimandi(f.read_text(encoding="utf-8", errors="replace"))
        chiavi = lambda v: {(v["file"], r) for r in v.get("righe") or [v["riga"]]}
        prima_k = set().union(*[chiavi(v) for v in ra.values()]) if ra else set()
        ora_k = set().union(*[chiavi(v) for v in rb.values()]) if rb else set()
        nuovi = [{"n": n, "riferimento": v["riferimento"], "file": v["file"], "riga": v["riga"]}
                 for n, v in rb.items() if not chiavi(v) & prima_k]
        tolti = [{"riferimento": v["riferimento"], "file": v["file"], "riga": v["riga"]}
                 for v in ra.values() if not chiavi(v) & ora_k]
        breve_a, breve_b = _risposta_breve(g), _risposta_breve(f)

        def pulisci(t):
            return re.sub(r"\s+", " ", t or "").strip()
        return {"precedente": {"file": g.name, "data": _data(g),
                               "documento": "/documento?" + urllib.parse.urlencode(
                                   {"risposta": g.name})},
                "nuovi": nuovi, "tolti": tolti, "risposta_prima": breve_a, "risposta_ora": breve_b,
                "risposta_cambiata": pulisci(breve_a) != pulisci(breve_b)}

    def consumo(self):
        """Richieste e token di oggi e degli ultimi 7 giorni (system/usage.jsonl, scritto da llm.py), per profilo,
        e i lotti della lettura, con cui la pagina stima quante richieste costerà una ricerca."""
        c = self.cfg()
        lotti = {"smistamento": c.getint("estrazione", "lotto_smistamento", fallback=6),
                 "analisi": c.getint("estrazione", "lotto_analisi", fallback=3)}
        try:
            f = percorso(c, "lavori").parent / "usage.jsonl"
        except Exception:
            return {"oggi": None, "lotti": lotti}
        oggi = dt.date.today()
        giorni = {(oggi - dt.timedelta(days=k)).isoformat() for k in range(7)}

        def vuoto():
            return {"richieste": 0, "ingresso": 0, "uscita": 0, "cache": 0}
        tot_oggi, tot_sett, per_servizio = vuoto(), vuoto(), {}
        for r in _coda_jsonl(f, 4_000_000):
            g = r.get("giorno")
            if g not in giorni:
                continue
            gruppi = [tot_sett]
            if g == oggi.isoformat():
                gruppi += [tot_oggi, per_servizio.setdefault(r.get("profilo") or r.get("servizio") or "?", vuoto())]
            for t in gruppi:
                t["richieste"] += 1
                for k in ("ingresso", "uscita", "cache"):
                    t[k] += int(r.get(k) or 0)
        return {"oggi": tot_oggi, "settimana": tot_sett, "per_servizio": per_servizio, "lotti": lotti}

    # ------------------------------------------------------------ esportazioni
    def esporta(self, formato, risposta="", ricerca="", base=""):
        """(byte, tipo, nome del file) di un'esportazione (esporta.py). CSL e BibTeX: i documenti citati nella
        risposta, o quelli con passaggi pertinenti; CSV: i passaggi letti; Word: la risposta con le note."""
        import esporta
        if formato not in esporta.FORMATI:
            raise Errore("Formato sconosciuto: csl, bibtex, csv o docx.")
        tipo, est = esporta.FORMATI[formato]
        dati = self.passaggi(risposta, ricerca)
        nome = Path(risposta).stem if risposta else ricerca
        if formato == "csv":
            return esporta.tabella_csv(dati["passaggi"], base).encode("utf-8"), tipo, nome + "_passaggi" + est
        if formato == "docx":
            md = (self.documento(risposta).with_suffix(".md") if risposta
                  else self._cartella_ricerca_nome(ricerca) / "risposta.md")
            if not md.is_file():
                raise Errore("Questa ricerca non ha ancora una risposta da esportare.")
            testo = md.read_text(encoding="utf-8", errors="replace")
            pulito = re.sub(r"<!--.*?-->\s*", "", testo, flags=re.DOTALL)
            sez1 = next((x for x in re.split(r"^(?=## \d+\.)", pulito, flags=re.MULTILINE)
                         if re.match(r"## 1\.", x)), "")
            riferimenti = {n: r.replace("*", "") for n, r in M._mappa_riferimenti(sez1).items()}
            for n, v in dati["rimandi"].items():
                riferimenti.setdefault(int(n), v["riferimento"])
            return esporta.docx(testo, riferimenti), tipo, nome + est
        # documenti: i citati (rimandi) se ci sono, altrimenti quelli con passaggi pertinenti
        pagine = {}
        if dati["rimandi"]:
            for v in dati["rimandi"].values():
                pagine.setdefault(v["file"], set()).add(v.get("pagina") or "")
        else:
            for x in dati["passaggi"]:
                if x.get("pertinente") == "sì":
                    pagine.setdefault(x["file"], set()).add(x.get("pagina") or "")
        documenti = []
        for file, pp in pagine.items():
            try:
                testa = self._file_dati(file).read_text(encoding="utf-8", errors="replace")[:20000]
            except (Errore, OSError):
                continue
            meta, _ = leggi_intestazione(testa)
            documenti.append((meta, file, sorted(p for p in pp if p)))
        documenti.sort(key=lambda d: (d[0].get("DATE") or d[0].get("YEAR") or "", d[1]))
        corpo = esporta.csl(documenti) if formato == "csl" else esporta.bibtex(documenti)
        return corpo.encode("utf-8"), tipo, nome + est

    # ------------------------------------------------------------ salute delle scansioni
    def salute_ocr(self):
        """I documenti importati con un testo sospetto: confidenza dell'OCR sotto 70 (OCR_CONFIDENCE
        dell'intestazione) o troppe «parole» che non sono parole (segni, cifre e lettere mescolate, lettere
        isolate: il segno di un OCR fallito o della lingua sbagliata). Il peggiore per primo."""
        dati = percorso(self.cfg(), "dati")
        out, esaminati = [], 0
        for f in sorted(dati.rglob("*.txt")):
            try:
                with open(f, encoding="utf-8", errors="replace") as h:
                    testo = h.read(40000)
            except OSError:
                continue
            esaminati += 1
            meta, inizio = leggi_intestazione(testo)
            metodo = " ".join((meta.get("TEXT_METHOD") or "", meta.get("METADATA_SOURCE") or "")).lower()
            if not (meta.get("OCR_ENGINE") or meta.get("OCR_CONFIDENCE") or "ocr" in metodo):
                continue                                      # testo nativo o trascrizione: niente OCR da rifare
            try:
                conf = float(meta.get("OCR_CONFIDENCE") or "")
            except ValueError:
                conf = None
            rumore = _rumore(testo[inizio:])
            if (conf is not None and conf < 70) or rumore >= 0.25:
                motivi = []
                if conf is not None and conf < 70:
                    motivi.append(f"confidenza dell'OCR {conf:g}")
                if rumore >= 0.25:
                    motivi.append(f"{round(rumore * 100)}% di parole illeggibili")
                out.append({"file": f.relative_to(dati).as_posix(), "titolo": meta.get("TITLE") or f.stem,
                            "serie": meta.get("SERIES", ""), "lingua": meta.get("LANG", ""),
                            "originale": meta.get("SOURCE_FILE", ""), "confidenza": conf,
                            "rumore": round(rumore, 2), "motivi": motivi,
                            "gravita": (70 - (conf if conf is not None else 70)) / 70 + rumore})
        out.sort(key=lambda x: -x["gravita"])
        return {"documenti": out[:200], "esaminati": esaminati, "sospetti": len(out)}

    def rifai_ocr(self, file, lingue=""):
        """Reimporta un documento dall'originale con l'OCR forzato e le lingue scelte (importa.py --ocr sempre
        --lingue …), conservando serie e metadati principali dell'intestazione. Il documento nuovo sostituisce il
        vecchio; lo stato si segue come ogni importazione."""
        f = self._file_dati(file)
        meta, _ = leggi_intestazione(f.read_text(encoding="utf-8", errors="replace")[:20000])
        rel = (meta.get("SOURCE_FILE") or "").replace("\\", "/")
        if not rel:
            raise Errore("Il documento non ricorda il suo originale (SOURCE_FILE): reimportalo dalla scheda Importa.")
        originali = percorso(self.cfg(), "originali").resolve()
        orig = (originali / rel).resolve()
        if originali not in orig.parents or not orig.is_file():
            raise Errore(f"L'originale «{rel}» non è più in sources/.")
        lingue = "+".join(x for x in re.split(r"[+,;\s]+", lingue or "") if re.fullmatch(r"[a-z_]{3,8}", x))
        r = M.t_importa_fonti(str(orig), meta.get("SERIES", ""), data=meta.get("DATE", ""),
                              numero=meta.get("ISSUE", ""), titolo=meta.get("TITLE", ""),
                              autore=meta.get("AUTHOR", ""), anno=meta.get("YEAR", ""), volume=meta.get("VOLUME", ""),
                              sovrascrivi=True, lingue=lingue, ocr="sempre")
        if r.get("errore"):
            raise Errore(r["errore"])
        r.pop("nota", None)
        return r

    def glossario(self):
        """Schede delle entità e profili delle serie del progetto (si modificano con le API qui sotto)."""
        if not self.progetto_in_uso():
            return {"schede": [], "serie": []}
        c = self.cfg()
        cp = schede.leggi_schede(percorso(c, "entita"))
        out = [{"nome": s, "campi": dict(cp[s])} for s in cp.sections()]
        serie = [{"nome": n, "campi": dict(v)} for n, v in profili.tutti(ricarica=True).items()]
        return {"schede": sorted(out, key=lambda x: x["nome"].lower()),
                "serie": sorted(serie, key=lambda x: x["nome"].lower())}

    # ------------------------------------------------------------ importazione
    # La scheda «Importazioni» fa tutto dall'interfaccia: proposta, tabella di revisione modificabile
    # qui oltre che in Excel, controllo senza scrivere (applica --prova), importazione vera, avanzamento dell'OCR.
    # I processi restano quelli indipendenti avviati dagli strumenti: la pagina chiude, il lavoro continua.
    def importa(self, azione, percorso_file="", serie="", prova=False, sovrascrivi=False):
        if azione not in ("proponi", "applica", "rivedi"):
            raise Errore("Azione d'importazione sconosciuta: proponi, applica o rivedi.")
        if azione == "applica":                      # prima un controllo qui: l'errore arriva subito alla pagina
            self._tabella_safe(percorso_file)
            percorso_file = str(self._tabella_safe(percorso_file))
        elif azione == "proponi" and not (percorso_file or "").strip():
            raise Errore("Indica la cartella o il file da importare.")
        r = M.t_importa(azione, percorso_file=percorso_file, serie=serie,
                        prova=int(bool(prova)) if azione == "applica" else bool(prova),
                        sovrascrivi=bool(sovrascrivi))
        if r.get("errore"):
            raise Errore(r["errore"])
        r.pop("nota", None)
        return r

    @staticmethod
    def _tabella_del_registro(testo):
        """Il percorso della tabella scritta dal processo, dalla riga «Tabella: ...» del registro."""
        m = re.findall(r"^Tabella:\s*(.+?)(?:\s*\(|$)", testo or "", re.MULTILINE)
        return Path(m[-1].strip().strip('"')) if m else None

    def _tabella_safe(self, percorso_file):
        """Percorso di una tabella di revisione: deve esistere ed stare nelle cartelle del progetto (audit o
        system/importazioni): la pagina può così solo leggere e correggere le tabelle che il sistema ha scritto."""
        f = Path(os.path.expandvars(os.path.expanduser((percorso_file or "").strip().strip('"'))))
        if not f.is_file():
            raise Errore(f"Non trovo «{percorso_file}» su questo computer.")
        c = self.cfg()
        permessi = []
        for chiave in ("registro_modifiche", "lavori_importazioni"):
            try:
                p = percorso(c, chiave).resolve()
            except Exception:
                continue
            permessi.append(p.parent if chiave == "registro_modifiche" else p)
        f = f.resolve()
        if not any(p.is_dir() and (p in f.parents or p == f.parent) for p in permessi):
            raise Errore("La tabella deve stare nelle cartelle del progetto (audit o system/importazioni).")
        return f

    def stato_importazione(self, id=""):
        """Lo stato del lavoro (esito, avanzamento dell'OCR) e, se è pronta, la sua tabella. Il registro intero
        resta nel file: alla pagina arrivano poche righe, e l'avanzamento ricavato dall'ultima."""
        r = M.t_stato_importazione(id)
        if r.get("errore"):
            raise Errore(r["errore"])
        registro = r.pop("registro", "")
        righe = [x.strip() for x in registro.splitlines() if x.strip()]
        r["ultime"] = [x[:1000] for x in righe[-4:]]      # il riepilogo di applica elenca tutte le serie nuove
        d = M.cartella_importazioni() / r["id"]
        comando = ""
        if (d / "richiesta.json").is_file():
            comando = json.dumps(json.loads((d / "richiesta.json").read_text(encoding="utf-8")).get("comando"))
        m = self._tabella_del_registro(registro)
        if m is None:                                  # il nome della tabella è deciso prima: lo dice il comando
            a = re.search(r"--out\", \"([^\"]+)\"", comando)
            if not a:
                a = re.search(r'"applica", "([^"]+?\.(?:csv|xlsx))"', comando)
            m = Path(a.group(1)) if a else None
        if m is not None and m.is_file():
            r["tabella"], r["pronta"] = str(m), True
        esito = r.get("esito") or {}
        if esito.get("codice") == 2 and esito.get("errore"):                  # tabella con errori: da correggere
            r["avviso"] = esito["errore"]
        for x in reversed(righe):                    # «esaminati 3/12» o «[2/5] documento»
            a = re.search(r"(\d+)\s*/\s*(\d+)", x)
            if a:
                fatto = int(a.group(1))
                if x.startswith("["):                # «[k/N] documento»: il k-esimo è in corso, non finito
                    fatto -= 1
                r["avanzamento"] = {"fatto": fatto, "totale": int(a.group(2)), "testo": righe[-1][:120]}
                break
        return r

    def tabella(self, id=""):
        """La tabella di revisione letta dal motore, per la tabella modificabile della scheda «Importazioni».
        Le colonne si dividono nella pagina: essenziali quelle che servono davvero, il resto sotto «avanzate».
        Se la tabella ha la colonna «serie», arriva anche l'elenco delle serie del progetto (per i menu a tendina)."""
        f = self._tabella_safe(id)
        righe = revisione.leggi_tabella(f)
        if not righe:
            raise Errore("La tabella è vuota.")
        colonne = list(righe[0].keys())
        essenziali = ["importa", "file", "serie", "tipo_serie", "lingua", "tipo_documento", "data", "stato_data",
                      "numero", "titolo", "autore", "anno", "pagine", "testo", "qualita_ocr", "da_controllare",
                      "file_dati"]
        out = {"tabella": str(f), "file": f.name,
               "tipo": "revisione" if "file_dati" in colonne else "proposta",
               "colonne": [c for c in essenziali if c in colonne] + [c for c in colonne if c not in essenziali],
               "righe": [{k: str(v or "") for k, v in r.items()} for r in righe]}
        if "serie" in colonne:                       # le serie del progetto, per scegliere senza scrivere
            import importa
            out["serie"] = importa.leggi_serie().sections()
        return out

    def salva_tabella(self, id, righe):
        """Sovrascrive la tabella con le righe corrette dalla pagina (CSV ; BOM UTF-8, come proponi). Il file
        delle proposte (.json accanto) non si tocca: applica lo confronta e segna «verificato» ciò che hai
        cambiato tu. Una tabella salvata da Excel come .xlsx non si riscrive (la si rovinerebbe): le correzioni
        vanno nel CSV con lo stesso nome accanto, che diventa la tabella da applicare."""
        f = self._tabella_safe(id)
        vecchie = revisione.leggi_tabella(f)
        if not vecchie:
            raise Errore("La tabella è vuota.")
        colonne = list(vecchie[0].keys())
        if len(righe or []) != len(vecchie):
            raise Errore(f"La pagina ha {len(righe or [])} righe, la tabella {len(vecchie)}: ricaricala.")
        nuove = []
        chiavi = [v.get("percorso") or v.get("file_dati") for v in vecchie]
        if len(set(chiavi)) != len(chiavi):
            raise Errore("La tabella ha righe duplicate: correggila con Excel o LibreOffice.")
        for i, (r, vecchia) in enumerate(zip(righe, vecchie), start=1):
            if not isinstance(r, dict):
                raise Errore(f"Riga {i}: dati non validi.")
            chiave = r.get("percorso") or r.get("file_dati")
            if chiave != chiavi[i - 1]:
                raise Errore(f"Riga {i}: il file non coincide con quello della tabella sul computer: ricaricala.")
            # una cella lasciata vuota nella pagina cancella il valore; una colonna non mandata resta com'è
            nuove.append({c: str(r[c]).strip() if c in r else str(vecchia.get(c) or "") for c in colonne})
        destinazione = f.with_suffix(".csv")         # .xlsx → .csv; un .csv (anche se Excel dentro) resta lui
        revisione.scrivi_tabella(destinazione, colonne, nuove)
        return {"salvata": True, "righe": len(nuove), "tabella": str(destinazione)}

    # ------------------------------------------------------------ conversazione sulle fonti
    # Il modello della sintesi con gli strumenti del motore. La prova degli strumenti si fa una volta per profilo
    # (finché l'interfaccia resta aperta); la conversazione ricomincia quando cambiano progetto o modello.
    def _stato_conversazione(self, riprova=False):
        if not self.progetto_in_uso():
            return {"attiva": False, "motivo": "Scegli o crea un progetto.", "messaggi": []}
        from llm import profilo
        c = self.cfg()
        try:
            nome, voci = profilo(c, "sintesi")
        except ErroreModello as e:
            return {"attiva": False, "motivo": str(e), "messaggi": []}
        prova = (nome, voci.get("servizio", ""), voci.get("modello", ""), voci.get("url", ""))
        chiave = (str(cartella_scelta(c)),) + prova
        if riprova:
            self._prove_strumenti.pop(prova, None)
        if self._conv is None or self._conv_chiave != chiave:
            self._conv = None
            try:
                self._conv = Conversazione(c, M, nome)
            except ErroreModello as e:
                return {"attiva": False, "profilo": nome, "riprova": True, "messaggi": [],
                        "motivo": f"Il modello «{nome}» non si può usare: {e}"}
            self._conv_chiave = chiave
        esito = self._prove_strumenti.get(prova)
        if esito is None:
            try:
                esito = self._conv.prova_strumenti()
            except ErroreConversazione as e:
                return {"attiva": False, "profilo": nome, "riprova": True, "messaggi": self._conv.storia,
                        "motivo": f"Non riesco a provare il modello «{nome}»: {e}"}
            self._prove_strumenti[prova] = esito
        out = {"attiva": esito["sa_usare_strumenti"], "profilo": nome, "modello": esito.get("modello", ""),
               "messaggi": self._conv.storia}
        if not esito["sa_usare_strumenti"]:
            out["riprova"] = True
            out["motivo"] = (f"Conversazione disattivata: {esito['motivo']}. Resta il percorso guidato, che non ne "
                             "ha bisogno; per conversare scegli nel menu «Modello» un modello che sa usare gli "
                             "strumenti.")
        return out

    def conversazione(self, riprova=False):
        if not self._conv_blocco.acquire(blocking=False):
            return {"attiva": False, "occupata": True, "messaggi": self._conv.storia if self._conv else [],
                    "motivo": "Il modello sta rispondendo alla domanda precedente."}
        try:
            return self._stato_conversazione(riprova)
        finally:
            self._conv_blocco.release()

    def conversa(self, testo):
        if not (testo or "").strip():
            raise Errore("Scrivi una domanda.")
        if not self._conv_blocco.acquire(blocking=False):
            raise Errore("Il modello sta ancora rispondendo alla domanda precedente.")
        try:
            s_ = self._stato_conversazione()
            if not s_["attiva"]:
                raise Errore(s_.get("motivo") or "Conversazione non disponibile.")
            try:
                return self._conv.invia(testo)
            except ErroreConversazione as e:
                raise Errore(f"{e} La domanda non è rimasta nella conversazione: puoi rifarla.")
        finally:
            self._conv_blocco.release()

    def nuova_conversazione(self):
        if not self._conv_blocco.acquire(blocking=False):
            raise Errore("Il modello sta ancora rispondendo: aspetta la risposta.")
        try:
            self._conv = None
            return self._stato_conversazione()
        finally:
            self._conv_blocco.release()

    def stato(self):
        return {"progetto": self.progetto_in_uso(), "progetti": self.progetti(),
                "cartella_progetti": str(self.cartella_progetti), "ricerca": self.stato_ricerca()}


def _ids_jsonl(f):
    """Gli «id» di un file .jsonl (insieme vuoto se manca), senza decodificare ogni riga."""
    try:
        with open(f, encoding="utf-8") as h:
            return {m.group(1) for m in (re.search(r'"id":\s*"([^"]+)"', r) for r in h) if m}
    except OSError:
        return set()


def _vista_lettura(p):
    """Una lettura di classificati.jsonl come la mostra la pagina (pannello dei passaggi, lettura dal vivo)."""
    a = p.get("analisi") or {}
    lettura = (a.get("provenienza") or {}).get("lettura") or {}
    decisione = (a.get("provenienza") or {}).get("decisione") or {}
    return {"id": p.get("id", ""), "entita": p.get("entita", ""), "data": p.get("data", "") or "",
            "fonte": p.get("citazione") or p.get("fonte", ""), "serie": p.get("fonte", ""),
            "pagina": str(a.get("pagina") or ""), "pertinente": a.get("pertinente", ""),
            "letto_da": lettura.get("da") or a.get("modello_analisi", "") or decisione.get("da", ""),
            "traduzione": a.get("traduzione_it") or "", "file": p.get("file", ""), "riga": str(p.get("riga", "")),
            "corretto": bool(a.get("corretto_a_mano"))}


def _chiave_risposta(md):
    """(entità, modalità) di una risposta salvata, dall'intestazione: le risposte con la stessa chiave si
    confrontano. None per le risposte senza intestazione."""
    try:
        with open(md, encoding="utf-8", errors="replace") as h:
            testa = h.read(800)
    except OSError:
        return None
    m = re.search(r"<!-- Domanda: .*? \| entità: (.*?) \| (occorrenze|evoluzione)", testa)
    return (m.group(1).strip().lower(), m.group(2)) if m else None


def _risposta_breve(md):
    """La sezione «Risposta finale» di una risposta salvata, con i rimandi [n] com'erano (non i riferimenti
    interi): due di queste si leggono una accanto all'altra nel confronto."""
    try:
        testo = re.sub(r"<!--.*?-->\s*", "", md.read_text(encoding="utf-8", errors="replace"), flags=re.DOTALL)
    except OSError:
        return ""
    m = re.search(r"^## \d+\.\s*Risposta finale[^\n]*\n(.*?)(?=^## |\Z)", testo, flags=re.MULTILINE | re.DOTALL)
    return m.group(1).strip() if m else ""


def _coda_jsonl(f, quanto):
    """Le righe JSON degli ultimi «quanto» byte di un file (il registro dei consumi cresce: basta la coda)."""
    try:
        with open(f, "rb") as h:
            h.seek(0, os.SEEK_END)
            fine = h.tell()
            h.seek(max(0, fine - quanto))
            dati = h.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    righe = dati.splitlines()
    if fine > quanto:
        righe = righe[1:]                    # la prima riga può essere tagliata a metà
    out = []
    for r in righe:
        try:
            out.append(json.loads(r))
        except ValueError:
            continue
    return out


_PAROLA = re.compile(r"\S+")
_BUONA = re.compile(r"^[\(\[«“\"']*[^\W\d_]{2,}(?:[-'’][^\W\d_]+)*[\)\]»”\"'.,;:!?]*$|^\d+[.,]?\d*[.,;:]?$")


def _rumore(testo):
    """La parte (0-1) delle «parole» di un testo che non sono né parole né numeri: mescolanze di lettere, cifre e
    segni («fl;Ja», «t3e»), lettere isolate. Sopra 0,25 un testo stampato è quasi sempre un OCR fallito o letto
    con la lingua sbagliata. Le righe di marcatori ([[p. 3]]) e le scritture senza spazi (cinese) non contano."""
    parole = [w for w in _PAROLA.findall(re.sub(r"\[\[[^\]]*\]\]", " ", testo[:30000]))
              if not re.search(r"[㐀-鿿]", w)]
    if len(parole) < 50:
        return 0.0
    cattive = sum(1 for w in parole if not _BUONA.match(w) and w not in ("-", "–", "—", "e", "a", "o", "i", "y", "à"))
    return cattive / len(parole)


def _righe_jsonl(f):
    """Righe non vuote di un file .jsonl (0 se manca)."""
    try:
        with open(f, encoding="utf-8") as h:
            return sum(1 for r in h if r.strip())
    except OSError:
        return 0


def _elenco(v):
    if not v:
        return []
    if isinstance(v, str):
        v = re.split(r"[;\n]", v)
    return [str(x).strip() for x in v if str(x).strip()]


def _anno(v):
    v = str(v or "").strip()
    if not v:
        return None
    if not re.fullmatch(r"\d{3,4}", v):
        raise Errore(f"Anno non valido: «{v}».")
    return int(v)


def _testa_risposta(md):
    """(entità, domanda) dalle prime righe di una risposta.md («# Nome» e «*Domanda:* ...»); vuote se mancano."""
    t = _intestazione_risposta(md)
    return t["entita"], t["domanda"]


def _intestazione_risposta(md):
    """Le prime righe di una risposta.md: entità («# Nome», senza «: evoluzione nelle fonti»), domanda, documenti
    pertinenti («*Generato il … — documenti pertinenti: N*») e se è una ricerca dell'evoluzione. Servono ai recenti
    per distinguere le risposte di prima dei fili, che non hanno filtri salvati."""
    t = {"entita": "", "domanda": "", "pertinenti": "", "evoluzione": False}
    try:
        with open(md, encoding="utf-8", errors="replace") as h:
            for r, _ in zip(h, range(12)):
                if not t["entita"] and r.startswith("# "):
                    nome = r[2:].strip()
                    if nome.endswith(": evoluzione nelle fonti"):
                        nome, t["evoluzione"] = nome[:-len(": evoluzione nelle fonti")], True
                    t["entita"] = nome
                m = re.match(r"\*Domanda:\*\s*(.+)", r.strip())
                if m:
                    t["domanda"] = m.group(1).strip()
                m = re.search(r"documenti pertinenti:\s*(\d+)", r)
                if m and not t["pertinenti"]:
                    t["pertinenti"] = m.group(1)
    except OSError:
        pass
    return t


def _data(f):
    return dt.datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y %H:%M")


RIGHE_BLOCCO = 60            # pagine di un file senza marcatori: blocchi di righe
PDF_MARCATORE = re.compile(r"\|\s*(?:pdf|img)\s+(\d+)", re.IGNORECASE)


def _pagine(righe):
    """[{etichetta, da, a, pdf}] (righe da 1): una pagina per marcatore [[p. N | pdf K]], con l'intestazione nella
    prima; senza marcatori, blocchi di RIGHE_BLOCCO righe."""
    inizi = []
    for k, r in enumerate(righe, 1):
        m = MARCATORE_PAGINA.match(r.strip())
        if m:
            pdf = PDF_MARCATORE.search(r)
            inizi.append((k, "p. " + m.group(1).strip(), int(pdf.group(1)) if pdf else None))
    if not inizi:
        return [{"etichetta": f"righe {a}-{min(a + RIGHE_BLOCCO - 1, len(righe))}", "da": a,
                 "a": min(a + RIGHE_BLOCCO - 1, len(righe)), "pdf": None}
                for a in range(1, max(len(righe), 1) + 1, RIGHE_BLOCCO)]
    out = []
    for i, (k, etichetta, pdf) in enumerate(inizi):
        fine = inizi[i + 1][0] - 1 if i + 1 < len(inizi) else len(righe)
        out.append({"etichetta": etichetta, "da": 1 if i == 0 else k, "a": fine, "pdf": pdf})
    return out


def _rimandi(testo):
    """{n: {file, riga, riferimento, pagina}} dalla sezione «Dati tecnici per la verifica» di una risposta e dai
    passaggi «### [n] ...»; la pagina è quella della citazione sotto il passaggio («— ..., p. 13.»), se c'è."""
    titoli, pagine = {}, {}
    blocchi = re.split(r"^(?=###\s*\[\d+\])", testo, flags=re.MULTILINE)
    for b in blocchi:
        m = re.match(r"###\s*\[(\d+)\]\s*(.+)", b)
        if not m:
            continue
        titoli[m.group(1)] = m.group(2).strip()
        c = re.search(r"^—.*,\s*pp?\.\s*([0-9A-Za-z]+)\.?\s*$", b.split("\n## ")[0], re.MULTILINE)
        if c:
            pagine[m.group(1)] = c.group(1)
    out = {}
    for m in re.finditer(r"^-\s*\[(\d+)\]\s*`([^`]+)`,\s*rig(?:a|he)\s*([\d,\s]+)", testo, re.MULTILINE):
        righe = [int(x) for x in re.findall(r"\d+", m.group(3))]
        # «righe»: tutte quelle del documento; ogni citazione sotto il passaggio apre la sua pagina (etichetta)
        out[m.group(1)] = {"file": m.group(2), "riga": righe[0], "righe": righe,
                           "riferimento": titoli.get(m.group(1), ""), "pagina": pagine.get(m.group(1), "")}
    return out


_BLOCCO_OCR = {}           # una lettura OCR per pagina alla volta (_parole_ocr)


def _normale(testo):
    """Solo lettere e cifre, minuscole e senza accenti: il confronto tra trascrizione e PDF non guarda spazi,
    punteggiatura, trattini di fine riga né i diacritici che l'OCR perde."""
    return "".join(c for c in unicodedata.normalize("NFKD", testo.lower()) if c.isalnum())


def _trova_nel_pdf(parole, testo, entro=None):
    """(prima, ultima) parola del PDF (indici in `parole`, da get_text("words")) dove si ritrova `testo`, o None.
    Frammenti di 4 caratteri (3 nelle scritture senza spazi, dove ogni carattere conta) del testo cercato votano le
    posizioni della pagina in cui ricorrono, se ci ricorrono al più 3 volte; vince il tratto della pagina lungo
    quanto il testo con più voti. Regge differenze di OCR, accenti, a capo con trattino. `entro` (prima, ultima)
    limita la ricerca a un tratto già trovato."""
    cercato = _normale(testo)
    if len(cercato) < 4:
        return None
    lettere, di_parola = [], []
    for i, w in enumerate(parole):
        if entro and not entro[0] <= i <= entro[1]:
            continue
        for c in _normale(w[4]):
            lettere.append(c)
            di_parola.append(i)
    pagina = "".join(lettere)
    n = 3 if sum(1 for c in cercato if ord(c) > 0x2E80) > len(cercato) / 2 else 4
    dove = {}
    for k in range(len(pagina) - n + 1):
        dove.setdefault(pagina[k:k + n], []).append(k)
    voti = sorted(k for g in {cercato[k:k + n] for k in range(len(cercato) - n + 1)}
                  for k in dove.get(g, ())[:4] if len(dove[g]) <= 3)
    frammenti = max(1, len(cercato) - n + 1)
    if len(voti) < max(2, frammenti * 0.3):     # riscontro troppo debole: meglio nessuna evidenza che una sbagliata
        return None
    lungo = int(len(cercato) * 1.25) + n
    migliore, da = (0, 0, 0), 0
    for a in range(len(voti)):                  # finestra scorrevole sulle posizioni votate
        while voti[a] - voti[da] > lungo:
            da += 1
        if a - da + 1 > migliore[0]:
            migliore = (a - da + 1, voti[da], voti[a] + n - 1)
    if migliore[0] < max(2, frammenti * 0.3):
        return None
    # un voto vale se il frammento sta nella pagina più o meno alla stessa distanza dall'inizio del passaggio a cui
    # sta nel testo cercato: un frammento comune ripetuto poco prima o poco dopo ("con il", "-zione" in un titolo)
    # cade fuori dall'allineamento del resto e non allarga il tratto
    nel_cercato = {}
    for k in range(len(cercato) - n + 1):
        nel_cercato.setdefault(cercato[k:k + n], []).append(k)
    dentro = [k for k in voti if migliore[1] <= k <= migliore[2] - n + 1]
    scarti = sorted(k - t for k in dentro for t in nel_cercato[pagina[k:k + n]])
    centro = scarti[len(scarti) // 2]             # lo scarto della maggior parte dei voti: l'allineamento
    tolleranza = max(12, min(40, len(cercato) * .08))   # la deriva di un OCR imperfetto, non una riga intera
    allineati = [k for k in dentro if min(abs(k - t - centro) for t in nel_cercato[pagina[k:k + n]]) <= tolleranza]
    if len(allineati) < max(2, frammenti * 0.3):
        return None
    return di_parola[allineati[0]], di_parola[min(allineati[-1] + n - 1, len(di_parola) - 1)]


def _fitz():
    try:
        import fitz
        return fitz
    except ImportError:
        return None


# ---------------------------------------------------------------- HTTP
GET = {"/api/stato": lambda a, q: a.stato(),
       "/api/progetti": lambda a, q: {"progetti": a.progetti()},
       "/api/modelli": lambda a, q: a.modelli(),
       "/api/collegamento": lambda a, q: a.collegamento(q.get("nome", "")),
       "/api/servizi": lambda a, q: a.servizi(),
       "/api/fornitori": lambda a, q: a.fornitori(q.get("locali") == "1"),
       "/api/ricerca": lambda a, q: a.stato_ricerca(),
       "/api/storico": lambda a, q: a.storico(),
       "/api/fonti": lambda a, q: a.fonti(),
       "/api/importa": lambda a, q: a.stato_importazione(q.get("id", "")),
       "/api/tabella": lambda a, q: a.tabella(q.get("percorso", "")),
       "/api/conversazione": lambda a, q: a.conversazione(q.get("riprova") == "1"),
       "/api/fonte": lambda a, q: a.fonte(q.get("file", ""), q.get("riga", ""), q.get("pagina", ""),
                                          q.get("etichetta", ""), q.get("tra", ""), q.get("ocr", "")),
       "/api/passaggi": lambda a, q: a.passaggi(q.get("risposta", ""), q.get("ricerca", "")),
       "/api/glossario": lambda a, q: a.glossario(),
       "/api/scheda": lambda a, q: a.leggi_scheda(q.get("nome", "")),
       "/api/scheda/pagina": lambda a, q: a.pagina_scheda(q.get("nome", "")),
       "/api/scheda/forme": lambda a, q: a.forme_suggerite(q.get("nome", "")),
       "/api/glossario/controllo": lambda a, q: a.controllo_glossario(),
       "/api/serie": lambda a, q: a.leggi_serie(q.get("nome", "")),
       "/api/documento": lambda a, q: a.corpo_documento(q.get("risposta", ""), q.get("ricerca", "")),
       "/api/fili": lambda a, q: a.fili(),
       "/api/filo": lambda a, q: a.filo(q.get("id", "")),
       "/api/avvio": lambda a, q: a.avvio(),
       "/api/ambiente": lambda a, q: a.ambiente(),
       "/api/lingue": lambda a, q: a.lingue(),
       "/api/ricerca/letture": lambda a, q: a.letture_ricerca(q.get("dopo", "0")),
       "/api/confronto": lambda a, q: a.confronto(q.get("risposta", "")),
       "/api/consumo": lambda a, q: a.consumo(),
       "/api/salute-ocr": lambda a, q: a.salute_ocr()}
POST = {"/api/progetto": lambda a, d: a.cambia_progetto(d.get("cartella", "")),
        "/api/progetto/nuovo": lambda a, d: a.nuovo_progetto(d.get("nome", ""), d.get("descrizione", "")),
        "/api/modello/usa": lambda a, d: a.usa_modello(d.get("nome", ""), ruoli=d.get("ruoli")),
        "/api/modello/prova": lambda a, d: a.prova_modello(d.get("nome", "")),
        "/api/interruttore": lambda a, d: a.interruttore(d.get("tipo", ""), d.get("nome", ""),
                                                       d.get("acceso") is True),
        "/api/modello/rinomina": lambda a, d: a.rinomina_modello(d.get("nome", ""), d.get("nuovo", "")),
        "/api/modello/togli": lambda a, d: a.togli_modello(d.get("nome", "")),
        "/api/chiave": lambda a, d: a.salva_chiave(d.get("fornitore", ""), d.get("chiave", ""),
                                                   bool(d.get("conserva"))),
        "/api/modello/elenco": lambda a, d: a.elenco_modelli(d.get("servizio", ""), d.get("url", ""),
                                                            d.get("chiave", "")),
        "/api/modello/nuovo": lambda a, d: a.aggiungi_modello(
            d.get("servizio", ""), d.get("modello", ""), d.get("nome", ""), d.get("url", ""),
            d.get("chiave_env", ""), d.get("chiave", ""), bool(d.get("salva_chiave")), d.get("usa", True) is not False),
        "/api/entita": lambda a, d: a.entita(d.get("nome", "")),
        "/api/precedenti": lambda a, d: a.precedenti(d.get("entita", "")),
        "/api/righe": lambda a, d: a.conta_righe(d.get("varianti"), d.get("dal"), d.get("al"), d.get("fonti")),
        "/api/esplora": lambda a, d: a.esplora(d.get("nome", ""), d.get("indizi"), d.get("candidate")),
        "/api/scheda": lambda a, d: a.crea_scheda(d.get("nome", ""), d.get("varianti"), d.get("forme_ambigue"),
                                                 d.get("tipo", ""), d.get("contesto"), d.get("scartate"),
                                                 d.get("cercato", ""), d.get("descrizione", "")),
        "/api/scheda/verifica": lambda a, d: a.verifica_scheda(d.get("nome", ""), d.get("campi"),
                                                               bool(d.get("nuova"))),
        "/api/scheda/correggi": lambda a, d: a.correggi_scheda(d.get("nome", ""), d.get("tipo", ""),
                                                               bool(d.get("tutte"))),
        "/api/ricerca/avvia": lambda a, d: a.avvia(d.get("entita", ""), d.get("domanda", ""), d.get("dal"),
                                                  d.get("al"), d.get("fonti"), bool(d.get("evoluzione"))),
        "/api/ricerca/ferma": lambda a, d: a.ferma(),
        "/api/ricerca/riprova": lambda a, d: a.riprova_ricerca(),
        "/api/scheda/modifica": lambda a, d: a.modifica_scheda(d.get("nome", ""), d.get("campi")),
        "/api/scheda/rinomina": lambda a, d: a.rinomina_scheda(d.get("nome", ""), d.get("nuovo", "")),
        "/api/scheda/elimina": lambda a, d: a.elimina_scheda(d.get("nome", "")),
        "/api/scheda/unisci": lambda a, d: a.unisci_schede(d.get("da", ""), d.get("verso", "")),
        "/api/scheda/forme": lambda a, d: a.decidi_forme(d.get("nome", ""), d.get("aggiungi"), d.get("scarta")),
        "/api/forme/conta": lambda a, d: a.conta_forme(d.get("forme")),
        "/api/serie/modifica": lambda a, d: a.modifica_serie(d.get("nome", ""), d.get("campi")),
        "/api/serie/anteprima": lambda a, d: a.anteprima_serie(d.get("nome", ""), d.get("campi")),
        "/api/passaggio/correggi": lambda a, d: a.correggi_passaggio(d.get("ricerca", ""), d.get("id", ""),
                                                                     d.get("pertinente"), d.get("traduzione")),
        "/api/rifai-ocr": lambda a, d: a.rifai_ocr(d.get("file", ""), d.get("lingue", "")),
        "/api/importa": lambda a, d: a.importa(d.get("azione", ""), d.get("percorso", ""), d.get("serie", ""),
                                               d.get("prova", False), d.get("sovrascrivi", False)),
        "/api/tabella": lambda a, d: a.salva_tabella(d.get("percorso", ""), d.get("righe")),
        "/api/conversazione": lambda a, d: a.conversa(d.get("testo", "")),
        "/api/conversazione/nuova": lambda a, d: a.nuova_conversazione(),
        "/api/lingue": lambda a, d: a.scarica_lingua(d.get("codice", "")),
        "/api/lingue/cartella": lambda a, d: a.cartella_lingue_propria(),
        "/api/filo": lambda a, d: a.salva_filo(d.get("filo")),
        "/api/filo/rinomina": lambda a, d: a.rinomina_filo(d.get("id", ""), d.get("titolo", "")),
        "/api/filo/elimina": lambda a, d: a.elimina_filo(d.get("id", "")),
        "/api/scegli-cartella": lambda a, d: {"percorso": scegli_cartella()},
        "/api/guida": lambda a, d: {"aperta": webbrowser.open(GUIDA)}}

GUIDA = "https://github.com/AMI-AIM/Pressmark/blob/main/docs/user_guide.it.md"
FINESTRA = {}                   # la finestra di pywebview, se c'è: per la scelta della cartella


def scegli_cartella():
    """Il dialogo di sistema per scegliere una cartella: quello di pywebview nella finestra propria, altrimenti
    tkinter (il server gira sullo stesso computer). Stringa vuota se si annulla."""
    w = FINESTRA.get("w")
    if w is not None:
        import webview
        tipo = getattr(getattr(webview, "FileDialog", None), "FOLDER", None) or webview.FOLDER_DIALOG
        scelta = w.create_file_dialog(tipo)
        return scelta[0] if scelta else ""
    try:
        import tkinter
        from tkinter import filedialog
        radice = tkinter.Tk()
        radice.withdraw()
        radice.attributes("-topmost", True)
        try:
            return filedialog.askdirectory(parent=radice, title="Cartella da importare") or ""
        finally:
            radice.destroy()
    except Exception as e:          # tkinter assente o senza schermo
        raise Errore(f"Non riesco ad aprire la scelta della cartella ({e}): scrivi il percorso.")


def gestore(app):
    class Gestore(BaseHTTPRequestHandler):
        server_version = "Pressmark"

        def log_message(self, formato, *a):
            if os.environ.get("PRESSMARK_APP_REGISTRO"):
                sys.stderr.write("app: " + formato % a + "\n")

        def _invia(self, codice, corpo, tipo="application/json; charset=utf-8", intestazioni=None):
            if isinstance(corpo, (dict, list)):
                corpo = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
            elif isinstance(corpo, str):
                corpo = corpo.encode("utf-8")
            self.send_response(codice)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(corpo)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (intestazioni or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(corpo)

        def _host_valido(self):
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            return host in ("127.0.0.1", "localhost")

        def _autorizzato(self):
            c = SimpleCookie(self.headers.get("Cookie") or "")
            return COOKIE in c and secrets.compare_digest(c[COOKIE].value, app.token)

        def _rifiuta(self):
            self._invia(403, "<!doctype html><meta charset=utf-8><title>Pressmark</title><p>Accesso negato. Apri "
                             "l'interfaccia dal collegamento che <code>python app.py</code> stampa all'avvio.</p>",
                        "text/html; charset=utf-8")

        def do_GET(self):
            if not self._host_valido():
                return self._invia(400, {"errore": "Host non ammesso."})
            u = urllib.parse.urlsplit(self.path)
            q = {k: v[-1] for k, v in urllib.parse.parse_qs(u.query).items()}
            if u.path == "/" and q.get("t"):
                if not secrets.compare_digest(q["t"], app.token):
                    return self._rifiuta()
                return self._invia(303, "", "text/plain", {
                    "Location": "/", "Set-Cookie": f"{COOKIE}={app.token}; HttpOnly; SameSite=Strict; Path=/"})
            if not self._autorizzato():
                return self._rifiuta()
            if u.path in GET:
                return self._esegui(lambda: GET[u.path](app, q))
            if u.path == "/documento":
                try:
                    f = app.documento(q.get("risposta", ""), q.get("ricerca", ""))
                except Errore as e:
                    return self._invia(404, f"<!doctype html><meta charset=utf-8><p>{e}</p>", "text/html; charset=utf-8")
                return self._invia(200, f.read_bytes(), "text/html; charset=utf-8",
                                   {"Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; "
                                                               "img-src data:"})
            if u.path == "/esporta":
                try:
                    host = self.headers.get("Host") or ""
                    corpo, tipo, nome = app.esporta(q.get("formato", ""), q.get("risposta", ""), q.get("ricerca", ""),
                                                    f"http://{host}" if host else "")
                except Errore as e:
                    return self._invia(404, f"<!doctype html><meta charset=utf-8><p>{e}</p>", "text/html; charset=utf-8")
                nome_ascii = re.sub(r"[^\w.-]", "_", nome.encode("ascii", "ignore").decode()) or "pressmark"
                return self._invia(200, corpo, tipo, {"Content-Disposition": f"attachment; filename=\"{nome_ascii}\"; "
                                                      f"filename*=UTF-8''{urllib.parse.quote(nome)}"})
            if u.path == "/fonte/pagina":
                try:
                    png = app.immagine_pagina(q.get("file", ""), q.get("pdf", ""), q.get("dpi", ""))
                except Errore as e:
                    return self._invia(404, {"errore": str(e)})
                return self._invia(200, png, "image/png")
            if u.path == "/fonte/pdf":                  # l'originale intero, nel lettore PDF del browser
                try:
                    corpo, nome = app.pdf_originale(q.get("file", ""))
                except Errore as e:
                    return self._invia(404, f"<!doctype html><meta charset=utf-8><p>{e}</p>", "text/html; charset=utf-8")
                return self._invia(200, corpo, "application/pdf",
                                   {"Content-Disposition": f"inline; filename*=UTF-8''{urllib.parse.quote(nome)}"})
            nome = "index.html" if u.path == "/" else u.path.lstrip("/")
            base, tipi = PAGINE, TIPI
            if nome.startswith("marchio/"):              # da assets solo le immagini SVG del marchio
                base, nome, tipi = MARCHIO, nome[len("marchio/"):], {".svg": TIPI[".svg"]}
            f = (base / nome).resolve()
            if base.resolve() not in f.parents or not f.is_file() or f.suffix not in tipi:
                return self._invia(404, {"errore": "Non trovato."})
            self._invia(200, f.read_bytes(), TIPI[f.suffix],
                        {"Content-Security-Policy": "default-src 'self'; style-src 'self'; script-src 'self'; "
                                                    "frame-src 'self'; img-src 'self' data:"})

        def do_POST(self):
            if not self._host_valido():
                return self._invia(400, {"errore": "Host non ammesso."})
            if not self._autorizzato() or self.headers.get(INTESTAZIONE_AZIONE) != "1":
                return self._rifiuta()
            u = urllib.parse.urlsplit(self.path)
            if u.path not in POST:
                return self._invia(404, {"errore": "Non trovato."})
            try:
                lunghezza = int(self.headers.get("Content-Length") or 0)
                dati = json.loads(self.rfile.read(lunghezza) or b"{}") if lunghezza else {}
                if not isinstance(dati, dict):
                    raise ValueError
            except ValueError:
                return self._invia(400, {"errore": "Richiesta non valida."})
            self._esegui(lambda: POST[u.path](app, dati))

        def _esegui(self, azione):
            try:
                self._invia(200, azione())
            except Errore as e:
                self._invia(400, {"errore": str(e)})
            except Exception as e:                    # un errore del motore: lo si mostra, il server resta su
                self._invia(500, {"errore": f"{type(e).__name__}: {e}"})
    return Gestore


def avvia_server(app, porta=0):
    server = ThreadingHTTPServer(("127.0.0.1", porta), gestore(app))
    server.daemon_threads = True
    return server


def _avvia_finestra_propria(server, url, senza_browser):
    """Apre una finestra propria con pywebview, se disponibile. Il server gira in un thread separato mentre la
    finestra è aperta; alla chiusura della finestra il server si ferma. Senza pywebview o con --senza-browser
    restituisce False e si usa il browser."""
    if senza_browser:
        return False
    try:
        import webview
    except ImportError:
        return False
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        try:                                     # le esportazioni (Word, BibTeX, CSV) si scaricano anche qui
            webview.settings["ALLOW_DOWNLOADS"] = True
        except (AttributeError, TypeError):      # pywebview vecchio: niente scaricamenti dalla finestra
            pass
        FINESTRA["w"] = webview.create_window("Pressmark", url, width=1200, height=800, min_size=(900, 600))
        webview.start()
    except Exception as e:          # per esempio WebView2 assente: si ripiega sul browser
        print(f"Finestra propria non disponibile ({e}): apro il browser.", flush=True)
        server.shutdown()
        return False
    server.shutdown()
    return True


def main(argv=None):
    ap = argparse.ArgumentParser(description="Interfaccia di Pressmark")
    ap.add_argument("--porta", type=int, default=0, help="porta locale (predefinita: una libera)")
    ap.add_argument("--senza-browser", action="store_true",
                    help="non aprire né la finestra né il browser (stampa solo il collegamento)")
    ap.add_argument("--config", help="config.ini da usare (prove)")
    args = ap.parse_args(argv)
    app = App(args.config)
    try:
        server = avvia_server(app, args.porta)
    except OSError as e:
        print(f"Non riesco ad aprire la porta {args.porta}: {e}. Prova con un'altra: python app.py --porta 8771")
        return 1
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={app.token}"
    if _avvia_finestra_propria(server, url, args.senza_browser):
        print(f"Pressmark è aperto in una finestra propria. Per chiudere: chiudi la finestra.", flush=True)
        server.server_close()
        return 0
    print(f"Pressmark è aperto nel browser. Se non si apre, copia questo collegamento:\n  {url}\n"
          "Il collegamento vale finché questa finestra resta aperta. Per chiudere: Ctrl+C.", flush=True)
    if not args.senza_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nInterfaccia chiusa. Le ricerche avviate continuano da sole.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

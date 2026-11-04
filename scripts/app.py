#!/usr/bin/env python3
"""
Interfaccia di Pressmark: un server locale, con la sola libreria standard, che apre una finestra
propria (pywebview, opzionale) con i menu «Progetto» e «Modello» e il percorso guidato della ricerca (domanda,
forme del nome attestate da confermare, avvio, avanzamento, risposta come documento). Senza pywebview apre nel
browser. Le funzioni sono quelle del motore (strumenti.py, le stesse del server MCP): interfaccia e chat fanno le stesse cose allo stesso
modo.

Sicurezza: il server ascolta solo su 127.0.0.1; all'avvio crea un token di sessione e apre la finestra con il
collegamento che lo contiene; il token diventa un cookie (HttpOnly, SameSite=Strict) e senza di esso ogni richiesta
è rifiutata. Si accettano solo richieste con Host 127.0.0.1 o localhost (contro il DNS rebinding); le azioni
(POST) vogliono JSON e l'intestazione X-Pressmark.

Progetto: la scelta vale per l'interfaccia (variabile PRESSMARK_PROGETTO del processo, ereditata dalle ricerche)
e si scrive in config.ini, sezione [progetto], perché la seguano anche chat e riga di comando (una copia di
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
import configparser
import datetime as dt
import json
import os
import re
import secrets
import sys
import threading
import time
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
MARCHIO = CARTELLA.parent / "assets" / "marchio"   # logotipo e favicon, serviti come /marchio/<file>
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

    def chat(self):
        """I client di chat noti: se il programma c'è su questo computer, se Pressmark è collegato così com'è
        (la voce avvia proprio questo programma) o se c'è una voce da aggiornare (un'altra copia, impostazioni)."""
        out = []
        for codice, etichetta in installa.CLIENT_GUIDA:
            f = installa.file_client(codice)
            p = installa.prepara_client(codice, f)
            collegato = p["valida"] and p["gia"]
            out.append({"id": codice, "nome": etichetta, "file": str(f), "presente": f.parent.is_dir(),
                        "collegato": collegato,
                        "da_aggiornare": not collegato and installa.voce_presente(codice, f)})
        return out

    def avvio(self):
        """I passi della preparazione, come «installa.py inizia»: progetto e modello necessari, chat e prime
        fonti facoltative. «completo» quando si può cercare."""
        c = self.cfg()
        p = self.progetto_in_uso()
        modello = self._modello_scelto(c) if p else None
        chat = self.chat()
        collegati = [x["nome"] for x in chat if x["collegato"]]
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
            {"id": "chat", "titolo": "Chat (Jan, Claude Desktop, LM Studio)", "fatto": bool(collegati),
             "facoltativo": True,
             "dettaglio": "Collegato a " + ", ".join(collegati) + "." if collegati else
             "Facoltativo: per fare domande sulle fonti anche da un programma di chat."},
        ]
        return {"passi": passi, "completo": bool(p and modello), "chat": chat}

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
            # PYTHONUTF8 riguarda i client di chat, e la loro voce la contiene già
            g["voci"] = [v for v in g["voci"] if v["voce"] != "PYTHONUTF8"]
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

    def _client_noto(self, nome):
        if nome not in dict(installa.CLIENT_GUIDA):
            raise Errore(f"Programma di chat «{nome}» sconosciuto.")

    def client(self, nome):
        """Anteprima del collegamento a un client: il file, che cosa cambia, se il programma è aperto."""
        self._client_noto(nome)
        p = installa.prepara_client(nome)
        return {"id": nome, "nome": dict(installa.CLIENT_GUIDA)[nome], "file": str(p["file"]),
                "esiste": p["esiste"], "modifiche": [m for m in p["modifiche"] if not m.startswith("- ")],
                "gia": p["gia"], "errore": p["illeggibile"] or (None if p["valida"] else "; ".join(p["modifiche"])),
                "avvia": " ".join([installa.voce_server()["command"], *installa.voce_server()["args"]]),
                "aperto": installa.in_esecuzione(nome)}

    def collega_client(self, nome):
        """Scrive la voce di Pressmark nel client (con copia di sicurezza) e prova il server come lo avvierà il
        client. Lo chiede la pagina dopo aver mostrato l'anteprima: è la conferma di «--scrivi»."""
        self._client_noto(nome)
        etichetta = dict(installa.CLIENT_GUIDA)[nome]
        p = installa.prepara_client(nome)
        if p["illeggibile"] or not p["valida"]:
            raise Errore(p["illeggibile"] or "; ".join(p["modifiche"]))
        righe = []
        if p["gia"]:
            righe.append(f"{etichetta} è già collegato: nessuna modifica.")
        else:
            if installa.in_esecuzione(nome):
                raise Errore(f"{etichetta} è aperto: quando si chiude riscrive i suoi file e la modifica andrebbe "
                             "persa. Chiudilo (anche dall'icona accanto all'orologio) e riprova.")
            righe += list(installa.scrivi_client(p))
        prova = installa.client_verifica(argparse.Namespace(), righe.append) == 0
        righe.append(f"Apri {etichetta}: il server Pressmark è acceso." if nome == "jan" else
                     f"Riavvia {etichetta} perché legga la nuova configurazione.")
        return {"scritto": not p["gia"], "prova": prova, "messaggi": righe}

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
        ambigue = set(proposta.get("forme_ambigue", []))
        scelte = set(proposta.get("varianti", []))
        for gruppo, origine in (("forme_latine", "nelle fonti"), ("forme_cinesi", ""), ("forme_albanesi", "")):
            for forma, s_ in (r.get(gruppo) or {}).items():
                forme.append({"forma": forma, "totale": s_.get("totale", 0), "origine": s_.get("origine") or origine,
                              "attenzione": s_.get("attenzione", ""), "per_serie_e_anno": s_.get("per_serie_e_anno", {}),
                              "esempi": [{"riferimento": e.get("riferimento", ""), "testo": e.get("testo", "")}
                                         for e in (s_.get("esempi") or [])[:2]],
                              "proposta": forma in scelte, "ambigua": forma in ambigue})
        return {"nome": nome, "forme": forme, "non_attestate": r.get("non_attestate", []),
                "contesto": proposta.get("contesto", []), "avviso_indice": r.get("avviso_indice", "")}

    def crea_scheda(self, nome, varianti, forme_ambigue=None, tipo="", contesto=None):
        varianti = _elenco(varianti)
        if not varianti:
            raise Errore("Conferma almeno una forma del nome.")
        ambigue = [f for f in _elenco(forme_ambigue) if f in varianti]
        tipo = tipo if tipo in TIPI_SCHEDA else ""
        r = M.t_crea_scheda(nome.strip(), varianti, contesto=_elenco(contesto) or None,
                            forme_ambigue=ambigue or None, tipo=tipo)
        if r.get("errore"):
            raise Errore(r["errore"])
        return r

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
        out.update({"id": s_.get("id", d.name), "domanda": s_.get("domanda", ""),
                    "entita": (s_.get("parametri") or {}).get("principale", "")})
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
        """(letti, estratti) della ricerca: righe distinte di classificati.jsonl e di passaggi.jsonl."""
        def ids(f):
            with open(f, encoding="utf-8") as h:
                return {m.group(1) for m in (re.search(r'"id":\s*"([^"]+)"', r) for r in h) if m}
        try:
            d = lavori.cartella_ricerca(self.cfg(), parametri)
            estratti = ids(d / "passaggi.jsonl")
            letti = ids(d / "classificati.jsonl") & estratti      # non le letture di ricerche precedenti
        except (OSError, KeyError, TypeError):
            return None
        return {"letti": len(letti), "estratti": len(estratti)} if estratti else None

    def ferma(self):
        return M.t_ferma_ricerca()

    def storico(self):
        if not self.progetto_in_uso():
            return {"risposte": [], "ricerche": []}
        c = self.cfg()
        risposte = M.t_elenca_risposte(50).get("risposte", [])
        for r in risposte:
            r["documento"] = "/documento?" + urllib.parse.urlencode({"risposta": r["file"]})
            r["entita"] = _testa_risposta(lavori.cartella_risposte(c) / r["file"])[0]
        ricerche = []
        base = percorso(c, "risultati") / "searches"
        if base.is_dir():
            for d in sorted(base.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                f = d / "risposta.html"
                if f.is_file():
                    entita, domanda = _testa_risposta(d / "risposta.md")
                    ricerche.append({"cartella": d.name, "data": _data(f), "entita": entita, "domanda": domanda,
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
            out.append({"id": x.get("id", f.stem), "titolo": x.get("titolo", ""), "entita": x.get("entita", ""),
                        "aggiornato": x.get("aggiornato", ""), "ricerca": x.get("ricerca", ""),
                        "documenti": [m.get("documento") for m in x.get("messaggi") or []
                                      if isinstance(m, dict) and m.get("tipo") == "risposta"]})
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

    def fonte(self, file, riga="", pagina="", etichetta="", tra=""):
        """Una pagina della fonte. `etichetta` (il numero stampato, «47») sceglie la pagina citata; `tra` (righe
        separate da virgole: quelle del passaggio) dice quale riga evidenziare in quella pagina."""
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
        immagine = ""
        if p.get("pdf") and self._originale(meta) is not None and _fitz() is not None:
            immagine = "/fonte/pagina?" + urllib.parse.urlencode({"file": file, "pdf": p["pdf"]})
        titolo = meta.get("TITLE") or " ".join(x for x in (meta.get("SERIES"), meta.get("DATE")) if x)
        return {"file": file, "titolo": titolo or f.stem, "citazione": meta.get("FULL_CITATION", ""),
                "pagine": [{"etichetta": x["etichetta"], "pdf": x.get("pdf")} for x in pagine], "pagina": n,
                "righe": [{"n": k, "testo": righe[k - 1]} for k in range(p["da"], p["a"] + 1)],
                "evidenzia": riga if riga and p["da"] <= riga <= p["a"] else None, "immagine": immagine}

    def immagine_pagina(self, file, pdf):
        """La pagina `pdf` (1 = la prima) del PDF originale, in PNG."""
        f = self._file_dati(file)
        meta, _ = leggi_intestazione(f.read_text(encoding="utf-8", errors="replace")[:20000])
        originale, fitz = self._originale(meta), _fitz()
        if originale is None or fitz is None:
            raise Errore("Originale non disponibile.")
        with fitz.open(originale) as doc:
            k = int(pdf) if str(pdf or "").isdigit() else 0
            if not 1 <= k <= len(doc):
                raise Errore("Pagina inesistente.")
            return doc[k - 1].get_pixmap(dpi=150).tobytes("png")     # la pagina è ora la vista principale

    def passaggi(self, risposta="", ricerca=""):
        """I passaggi del documento aperto: per una ricerca quelli letti (classificati.jsonl), con pertinenza, chi li
        ha letti e traduzione; per una risposta salvata quelli citati. «rimandi»: [n] della risposta -> file e riga,
        dalla sezione «Dati tecnici per la verifica» (la pagina li usa per aprire la fonte dal documento)."""
        if ricerca:                     # anche le ricerche vecchie, senza il documento HTML
            if Path(ricerca).name != ricerca or ricerca in (".", ".."):
                raise Errore("Ricerca non valida.")
            cartella = percorso(self.cfg(), "risultati") / "searches" / ricerca
            if not cartella.is_dir():
                raise Errore("Ricerca non trovata.")
            md = cartella / "risposta.md"
        else:
            cartella, md = None, self.documento(risposta).with_suffix(".md")
        testo = md.read_text(encoding="utf-8", errors="replace") if md.is_file() else ""
        rimandi = _rimandi(testo)
        out = []
        if cartella is not None and (cartella / "classificati.jsonl").is_file():
            estratti = set()
            if (cartella / "passaggi.jsonl").is_file():
                with open(cartella / "passaggi.jsonl", encoding="utf-8") as h:
                    estratti = {m.group(1) for m in (re.search(r'"id":\s*"([^"]+)"', r) for r in h) if m}
            with open(cartella / "classificati.jsonl", encoding="utf-8") as h:
                for r in h:
                    try:
                        p = json.loads(r)
                    except ValueError:
                        continue
                    if estratti and p.get("id") not in estratti:
                        continue                         # letture di ricerche precedenti
                    a = p.get("analisi") or {}
                    lettura = (a.get("provenienza") or {}).get("lettura") or {}
                    out.append({"data": p.get("data", ""), "fonte": p.get("citazione") or p.get("fonte", ""),
                                "pagina": a.get("pagina", ""), "pertinente": a.get("pertinente", ""),
                                "letto_da": lettura.get("da") or a.get("modello_analisi", ""),
                                "traduzione": a.get("traduzione_it") or "", "file": p.get("file", ""),
                                "riga": str(p.get("riga", ""))})
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
        else:
            for n, v in rimandi.items():
                out.append({"n": n, "fonte": v["riferimento"], "pertinente": "sì", "file": v["file"],
                            "riga": str(v["riga"])})
        return {"passaggi": out, "rimandi": rimandi}

    def glossario(self):
        """Schede delle entità e profili delle serie del progetto (in sola lettura)."""
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
    entita = domanda = ""
    try:
        with open(md, encoding="utf-8", errors="replace") as h:
            for r, _ in zip(h, range(12)):
                if not entita and r.startswith("# "):
                    entita = r[2:].strip()
                m = re.match(r"\*Domanda:\*\s*(.+)", r.strip())
                if m:
                    domanda = m.group(1).strip()
    except OSError:
        pass
    return entita, domanda


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
                                          q.get("etichetta", ""), q.get("tra", "")),
       "/api/passaggi": lambda a, q: a.passaggi(q.get("risposta", ""), q.get("ricerca", "")),
       "/api/glossario": lambda a, q: a.glossario(),
       "/api/documento": lambda a, q: a.corpo_documento(q.get("risposta", ""), q.get("ricerca", "")),
       "/api/fili": lambda a, q: a.fili(),
       "/api/filo": lambda a, q: a.filo(q.get("id", "")),
       "/api/avvio": lambda a, q: a.avvio(),
       "/api/ambiente": lambda a, q: a.ambiente(),
       "/api/client": lambda a, q: a.client(q.get("nome", "")),
       "/api/lingue": lambda a, q: a.lingue()}
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
        "/api/esplora": lambda a, d: a.esplora(d.get("nome", ""), d.get("indizi"), d.get("candidate")),
        "/api/scheda": lambda a, d: a.crea_scheda(d.get("nome", ""), d.get("varianti"), d.get("forme_ambigue"),
                                                 d.get("tipo", ""), d.get("contesto")),
        "/api/ricerca/avvia": lambda a, d: a.avvia(d.get("entita", ""), d.get("domanda", ""), d.get("dal"),
                                                  d.get("al"), d.get("fonti"), bool(d.get("evoluzione"))),
        "/api/ricerca/ferma": lambda a, d: a.ferma(),
        "/api/importa": lambda a, d: a.importa(d.get("azione", ""), d.get("percorso", ""), d.get("serie", ""),
                                               d.get("prova", False), d.get("sovrascrivi", False)),
        "/api/tabella": lambda a, d: a.salva_tabella(d.get("percorso", ""), d.get("righe")),
        "/api/conversazione": lambda a, d: a.conversa(d.get("testo", "")),
        "/api/conversazione/nuova": lambda a, d: a.nuova_conversazione(),
        "/api/client": lambda a, d: a.collega_client(d.get("nome", "")),
        "/api/lingue": lambda a, d: a.scarica_lingua(d.get("codice", "")),
        "/api/lingue/cartella": lambda a, d: a.cartella_lingue_propria(),
        "/api/filo": lambda a, d: a.salva_filo(d.get("filo")),
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
            if u.path == "/fonte/pagina":
                try:
                    png = app.immagine_pagina(q.get("file", ""), q.get("pdf", ""))
                except Errore as e:
                    return self._invia(404, {"errore": str(e)})
                return self._invia(200, png, "image/png")
            nome = "index.html" if u.path == "/" else u.path.lstrip("/")
            base = PAGINE
            if nome.startswith("marchio/"):
                base, nome = MARCHIO, nome[len("marchio/"):]
            f = (base / nome).resolve()
            if base.resolve() not in f.parents or not f.is_file() or f.suffix not in TIPI:
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

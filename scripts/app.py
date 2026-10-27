#!/usr/bin/env python3
"""
Interfaccia di AIrchivist (lavoro 35): un server locale, con la sola libreria standard, che apre nel browser una
pagina con i menu «Progetto» e «Modello» e il percorso guidato della ricerca (domanda, forme del nome attestate da
confermare, avvio, avanzamento, risposta come documento). Le funzioni sono quelle del server MCP e del motore:
interfaccia e chat fanno le stesse cose allo stesso modo.

Sicurezza: il server ascolta solo su 127.0.0.1; all'avvio crea un token di sessione e apre il browser con il
collegamento che lo contiene; il token diventa un cookie (HttpOnly, SameSite=Strict) e senza di esso ogni richiesta
è rifiutata. Si accettano solo richieste con Host 127.0.0.1 o localhost (contro il DNS rebinding); le azioni
(POST) vogliono JSON e l'intestazione X-AIrchivist.

Progetto: la scelta vale per l'interfaccia (variabile AIRCHIVIST_PROGETTO del processo, ereditata dalle ricerche)
e si scrive in config.ini, sezione [progetto], perché la seguano anche chat e riga di comando (una copia di
sicurezza al giorno). Il cambio è bloccato mentre una ricerca del progetto è in corso.
Modello: la scelta passa per la prova di collegamento (installa.modello_usa): se fallisce resta il precedente.

Uso (nella cartella scripts):
  python app.py                    avvia il server e apre il browser
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

_USCITA = sys.stdout
import mcp_server as M          # noqa: E402  (il server MCP sposta stdout su stderr: qui non serve)
sys.stdout = _USCITA

import installa                 # noqa: E402
import lavori                   # noqa: E402
import profili                  # noqa: E402
import schede                   # noqa: E402
from progetto import VARIABILE, cartella_scelta, leggi_config, percorso   # noqa: E402

PAGINE = CARTELLA / "interfaccia"
TIPI = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml"}
COOKIE = "airchivist"
INTESTAZIONE_AZIONE = "X-AIrchivist"
TIPI_SCHEDA = ("persona", "organizzazione", "testata", "stato", "altro")


class Errore(Exception):
    """Errore da mostrare all'utente così com'è (risposta 400 con «errore»)."""


class App:
    """Lo stato dell'interfaccia e le sue azioni, indipendenti dal protocollo HTTP (così i test le chiamano)."""

    def __init__(self, config=None, cartella_progetti=None):
        self.config = Path(config).resolve() if config else CARTELLA / "config.ini"
        M.CONFIG = str(self.config) if config else None
        installa.FILE_CONFIG = self.config
        self.cartella_progetti = Path(cartella_progetti) if cartella_progetti else CARTELLA.parent / "projects"
        self.token = secrets.token_urlsafe(24)
        self._blocco = threading.Lock()
        self._collegamenti = {}            # profilo -> (istante, esito): la prova costa una richiesta di rete
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
        if not any(self.config.parent.glob(f"{self.config.name}.airchivist-{installa.oggi()}*.bak")):
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

    def usa_modello(self, nome):
        """La scelta passa per la prova di collegamento: se fallisce resta il profilo di prima."""
        out = M.t_modello("usa", nome)
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
            u = self.usa_modello(nome)
            out["cambiato"] = u.get("cambiato", False)
            out["messaggi"] += u.get("messaggi", [])
        elif not riuscita:
            out["messaggi"].append("Il profilo resta salvato ma non è in uso: correggilo o provane un altro.")
        return out

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
        ricerche = []
        base = percorso(c, "risultati") / "searches"
        if base.is_dir():
            for d in sorted(base.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
                f = d / "risposta.html"
                if f.is_file():
                    ricerche.append({"cartella": d.name, "data": _data(f),
                                     "documento": "/documento?" + urllib.parse.urlencode({"ricerca": d.name})})
        return {"risposte": risposte, "ricerche": ricerche[:50]}

    def documento(self, risposta="", ricerca=""):
        """Il file HTML di una risposta, solo dentro le cartelle delle risposte e delle ricerche del progetto."""
        c = self.cfg()
        if risposta:
            if Path(risposta).name != risposta or not risposta.endswith(".md"):
                raise Errore("Risposta non valida.")
            f = (lavori.cartella_risposte(c) / risposta).with_suffix(".html")
            md = f.with_suffix(".md")
            if not f.exists() and md.exists():
                from documento import scrivi_html
                scrivi_html(md)
        elif ricerca:
            if Path(ricerca).name != ricerca:
                raise Errore("Ricerca non valida.")
            f = percorso(c, "risultati") / "searches" / ricerca / "risposta.html"
        else:
            raise Errore("Quale documento?")
        if not f.is_file():
            raise Errore("Documento non trovato.")
        return f

    def fonti(self):
        if not self.progetto_in_uso():
            return {"fonti": []}
        profili.tutti(ricarica=True)
        M.FONTI_SCELTE = sorted({profili.gruppo(n) for n in profili.tutti()})
        return {"fonti": M.FONTI_SCELTE}

    # ------------------------------------------------------------ importazione (la tabella si corregge in Excel)
    def importa(self, azione, percorso_file="", prova=False, id=""):
        if azione not in ("proponi", "applica", "stato"):
            raise Errore("Azione d'importazione sconosciuta.")
        r = M.t_importa(azione, percorso_file=percorso_file, prova=bool(prova), id=id)
        if r.get("errore") and azione != "stato":
            raise Errore(r["errore"])
        tabella = re.findall(r"[A-Za-z]:\\[^\n\"]*?review_[\w-]+\.csv|/[^\n\"]*?review_[\w-]+\.csv",
                             r.get("registro", ""))
        if tabella:
            r["tabella"] = tabella[-1]
        r.pop("nota", None)
        return r

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


def _data(f):
    return dt.datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y %H:%M")


# ---------------------------------------------------------------- HTTP
GET = {"/api/stato": lambda a, q: a.stato(),
       "/api/progetti": lambda a, q: {"progetti": a.progetti()},
       "/api/modelli": lambda a, q: a.modelli(),
       "/api/collegamento": lambda a, q: a.collegamento(q.get("nome", "")),
       "/api/servizi": lambda a, q: a.servizi(),
       "/api/ricerca": lambda a, q: a.stato_ricerca(),
       "/api/storico": lambda a, q: a.storico(),
       "/api/fonti": lambda a, q: a.fonti(),
       "/api/importa": lambda a, q: a.importa("stato", id=q.get("id", ""))}
POST = {"/api/progetto": lambda a, d: a.cambia_progetto(d.get("cartella", "")),
        "/api/progetto/nuovo": lambda a, d: a.nuovo_progetto(d.get("nome", ""), d.get("descrizione", "")),
        "/api/modello/usa": lambda a, d: a.usa_modello(d.get("nome", "")),
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
        "/api/importa": lambda a, d: a.importa(d.get("azione", ""), d.get("percorso", ""), d.get("prova", False))}


def gestore(app):
    class Gestore(BaseHTTPRequestHandler):
        server_version = "AIrchivist"

        def log_message(self, formato, *a):
            if os.environ.get("AIRCHIVIST_APP_REGISTRO"):
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
            self._invia(403, "<!doctype html><meta charset=utf-8><title>AIrchivist</title><p>Accesso negato. Apri "
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
            nome = "index.html" if u.path == "/" else u.path.lstrip("/")
            f = (PAGINE / nome).resolve()
            if PAGINE.resolve() not in f.parents or not f.is_file() or f.suffix not in TIPI:
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


def main(argv=None):
    ap = argparse.ArgumentParser(description="Interfaccia di AIrchivist nel browser (lavoro 35)")
    ap.add_argument("--porta", type=int, default=0, help="porta locale (predefinita: una libera)")
    ap.add_argument("--senza-browser", action="store_true", help="non aprire il browser")
    ap.add_argument("--config", help="config.ini da usare (prove)")
    args = ap.parse_args(argv)
    app = App(args.config)
    try:
        server = avvia_server(app, args.porta)
    except OSError as e:
        print(f"Non riesco ad aprire la porta {args.porta}: {e}. Prova con un'altra: python app.py --porta 8771")
        return 1
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={app.token}"
    print(f"AIrchivist è aperto nel browser. Se non si apre, copia questo collegamento:\n  {url}\n"
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

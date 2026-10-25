#!/usr/bin/env python3
"""
Gestore delle ricerche come lavori indipendenti dalla chat.

Ogni ricerca avviata dalla chat (strumento ricerca, azione avvia) gira in un processo a sé, che sopravvive al
riavvio del server MCP o del client, e tiene il proprio stato su disco nella cartella lavori/<id>/ del progetto:
  richiesta.json   parametri della ricerca
  stato.json       stato attuale (lo legge ricerca con azione attendi), aggiornato ogni pochi secondi
  registro.txt     tutti i messaggi della ricerca
  ferma            (file vuoto) chiede al lavoro di fermarsi

Se le quote dei servizi gratuiti si esauriscono, il lavoro non si ferma: aspetta e riprova (dopo 10, 15, 30,
poi ogni 60 minuti, per al massimo 36 ore). La ricerca riparte da dove era: i passaggi già letti sono
nell'archivio. Se manca solo la sintesi, la riprova allo stesso modo.

Uso interno: python lavori.py esegui <id>   (lo lancia il server)
"""
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

FINALI = {"completata", "completata, ma sintesi non generata", "errore", "fermata", "interrotta"}
ATTESE_MINUTI = [10, 15, 30, 60]
DURATA_MASSIMA_ORE = 36
MARCATORE = "<!-- sintesi: non generata -->"
BATTITO_SCADUTO = 180            # secondi senza aggiornamenti: il processo non c'è più
SENZA_FINESTRA, NUOVO_GRUPPO, FUORI_DAL_JOB = 0x08000000, 0x00000200, 0x01000000     # opzioni di Windows


# ---------------------------------------------------------------- percorsi e nomi
def cartella_lavori(cfg):
    from llm import percorso
    d = percorso(cfg, "lavori")
    d.mkdir(parents=True, exist_ok=True)
    return d


def cartella_risposte(cfg):
    from llm import percorso
    d = percorso(cfg, "risposte")
    d.mkdir(parents=True, exist_ok=True)
    return d


def slug(s, n=60):
    s = re.sub(r"[^\w一-鿿]+", "_", s.lower()).strip("_")
    return s[:n].rstrip("_") or "domanda"


def slug_ricerca(nome):
    """Stesso nome di cartella usato da ricerca.py (senza accenti)."""
    import unicodedata
    nome = "".join(c for c in unicodedata.normalize("NFKD", nome.strip().lower()) if not unicodedata.combining(c))
    return re.sub(r"[^\w一-鿿]+", "_", nome).strip("_") or "ricerca"


def cartella_ricerca(cfg, i):
    from llm import percorso
    return percorso(cfg, "risultati") / (slug_ricerca(i["principale"]) +
                                         ("_evoluzione" if i["modalita"] == "evoluzione" else ""))


def comando_ricerca(i, domanda, config=None, accetta_incompleti=False):
    comando = [sys.executable, "-u", str(CARTELLA / "ricerca.py"), i["principale"], "--domanda", domanda]
    if i["modalita"] == "evoluzione":
        comando += ["--evoluzione"]
        if i["collegate"]:
            comando += ["--collegate", "; ".join(i["collegate"])]
    if i["dal"]:
        comando += ["--dal", str(i["dal"])]
    if i["al"]:
        comando += ["--al", str(i["al"])]
    if i["fonti"]:
        comando += ["--fonti", "; ".join(i["fonti"])]
    if config:
        comando += ["--config", config]
    if accetta_incompleti:
        comando += ["--accetta-incompleti"]
    return comando


def salva_risposta(cfg, i, domanda):
    """Copia risposta.md della ricerca in RAG/risposte/ con data e domanda nel nome. Restituisce il percorso."""
    risposta = cartella_ricerca(cfg, i) / "risposta.md"
    if not risposta.exists():
        return None
    dest = cartella_risposte(cfg) / f"{dt.date.today().isoformat()}_{slug(domanda)}.md"
    intest = (f"<!-- Domanda: {domanda} | entità: {i['principale']}"
              + (f" + {'; '.join(i['collegate'])}" if i["collegate"] else "")
              + f" | {i['modalita']}" + (f" | dal {i['dal']}" if i["dal"] else "")
              + (f" | al {i['al']}" if i["al"] else "")
              + (f" | fonti: {'; '.join(i['fonti'])}" if i["fonti"] else "") + " -->\n\n")
    dest.write_text(intest + risposta.read_text(encoding="utf-8"), encoding="utf-8")
    return dest


# ---------------------------------------------------------------- stato su disco
def scrivi_json(f, dati):
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text(json.dumps(dati, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, f)


def leggi_json(f):
    for _ in range(3):
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            time.sleep(0.2)
    return None


def stato_lavoro(d):
    """Stato di un lavoro, con il controllo che il processo sia ancora vivo."""
    s = leggi_json(Path(d) / "stato.json")
    if not s:
        return None
    if s.get("stato") not in FINALI and time.time() - s.get("battito", 0) > BATTITO_SCADUTO:
        s["stato"] = "interrotta"
        s["messaggio"] = ("Il processo della ricerca non risponde più (PC spento o in sospensione, o processo "
                          "chiuso). Rifacendo la stessa domanda riprende da dove era.")
    return s


def lavori(cfg):
    d = cartella_lavori(cfg)
    return sorted((x for x in d.iterdir() if x.is_dir() and (x / "stato.json").exists()),
                  key=lambda x: x.stat().st_mtime)


def attivo(cfg):
    """(cartella, stato) del lavoro in corso, se c'è."""
    for d in reversed(lavori(cfg)):
        s = stato_lavoro(d)
        if s and s.get("stato") not in FINALI:
            return d, s
    return None, None


def ultimo(cfg):
    tutti = lavori(cfg)
    return (tutti[-1], stato_lavoro(tutti[-1])) if tutti else (None, None)


def avvia(cfg, interp, domanda, config=None):
    """Crea il lavoro e lancia il processo indipendente. Restituisce (cartella, stato)."""
    d = cartella_lavori(cfg) / (dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4])
    d.mkdir()
    scrivi_json(d / "richiesta.json", {"interpretazione": interp, "domanda": domanda, "config": config})
    stato = {"id": d.name, "domanda": domanda, "parametri": interp, "stato": "in partenza", "tentativo": 0,
             "inizio": time.time(), "battito": time.time(), "avanzamento": "", "ultimi_messaggi": []}
    scrivi_json(d / "stato.json", stato)
    comando = [sys.executable, "-u", str(CARTELLA / "lavori.py"), "esegui", str(d)]
    if config:
        comando += ["--config", config]
    opzioni = dict(cwd=CARTELLA, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"))
    if os.name == "nt":
        # processo indipendente da Jan (non si chiude quando Jan riavvia o spegne il server) e senza finestre
        try:
            subprocess.Popen(comando, creationflags=SENZA_FINESTRA | NUOVO_GRUPPO | FUORI_DAL_JOB, **opzioni)
        except OSError:                       # Jan non consente l'uscita dal suo gruppo di processi
            subprocess.Popen(comando, creationflags=SENZA_FINESTRA | NUOVO_GRUPPO, **opzioni)
    else:
        subprocess.Popen(comando, start_new_session=True, **opzioni)
    return d, stato


def ferma(d):
    (Path(d) / "ferma").touch()


# ---------------------------------------------------------------- esecuzione (processo indipendente)
class Esecutore:
    def __init__(self, d, config=None):
        from llm import leggi_config
        self.d = Path(d)
        self.req = leggi_json(self.d / "richiesta.json")
        self.config = config or self.req.get("config")
        self.cfg = leggi_config(self.config)
        self.stato = leggi_json(self.d / "stato.json")
        self.registro = open(self.d / "registro.txt", "a", encoding="utf-8")
        self.ultimi, self.blocco = [], threading.Lock()
        self.proc = None
        threading.Thread(target=self._battito, daemon=True).start()

    def aggiorna(self, **k):
        with self.blocco:
            self.stato.update(k)
            if self.stato.get("stato") in FINALI:
                self.stato.pop("prossimo_tentativo", None)
            self.stato["battito"] = time.time()
            self.stato["ultimi_messaggi"] = self.ultimi[-8:]
            scrivi_json(self.d / "stato.json", self.stato)

    def _battito(self):
        while True:
            time.sleep(20)
            self.aggiorna()

    def fermato(self):
        return (self.d / "ferma").exists()

    def log(self, riga):
        self.registro.write(riga + "\n")
        self.registro.flush()
        if riga.strip() and not riga.startswith("   "):
            self.ultimi.append(riga.strip()[:200])
            del self.ultimi[:-30]

    def lancia(self, accetta_incompleti):
        i = self.req["interpretazione"]
        comando = comando_ricerca(i, self.req["domanda"], self.config, accetta_incompleti)
        self.log(f"--- tentativo {self.stato['tentativo']} ({dt.datetime.now():%d/%m %H:%M})")
        self.proc = subprocess.Popen(comando, cwd=CARTELLA, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                                     env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1"),
                                     **({"creationflags": SENZA_FINESTRA} if os.name == "nt" else {}))
        ultimo_agg = 0
        for riga in self.proc.stdout:
            riga = riga.rstrip("\n")
            self.log(riga)
            m = re.match(r"\s*\[(\d+)/(\d+)\]", riga)
            fase = re.match(r"== (\d/3 .*)", riga)
            if fase:
                self.aggiorna(fase=fase.group(1))
            if m and time.time() - ultimo_agg > 5:
                self.aggiorna(avanzamento=f"{m.group(1)}/{m.group(2)} passaggi letti in questo tentativo")
                ultimo_agg = time.time()
            if self.fermato():
                self.proc.terminate()
        return self.proc.wait()

    def non_letti(self):
        f = cartella_ricerca(self.cfg, self.req["interpretazione"]) / "non_letti.json"
        s = leggi_json(f) if f.exists() else None
        return (s or {}).get("non_letti", 0)

    def pochi(self, resto):
        if not resto:
            return False
        f = cartella_ricerca(self.cfg, self.req["interpretazione"]) / "passaggi.jsonl"
        try:
            totale = sum(1 for r in open(f, encoding="utf-8") if r.strip())
        except OSError:
            return False
        return resto <= max(5, totale * 0.02)

    def attendi(self, minuti, motivo):
        prossimo = time.time() + minuti * 60
        self.aggiorna(stato="in attesa", messaggio=motivo,
                      prossimo_tentativo=dt.datetime.fromtimestamp(prossimo).strftime("%H:%M del %d/%m"))
        self.log(f"--- {motivo}: riprovo alle {dt.datetime.fromtimestamp(prossimo):%H:%M}")
        while time.time() < prossimo:
            if self.fermato():
                return False
            time.sleep(5)
        return True

    def esegui(self):
        inizio = self.stato.get("inizio", time.time())
        attese = senza_progresso = sintesi_mancate = 0
        precedenti = None
        while True:
            if self.fermato():
                return self.aggiorna(stato="fermata", messaggio="Ricerca fermata su richiesta.")
            self.aggiorna(stato="in corso", tentativo=self.stato.get("tentativo", 0) + 1, prossimo_tentativo=None,
                          messaggio="", avanzamento="")
            # pochi passaggi che falliscono sempre (risposte del modello malformate): dopo due tentativi senza
            # progressi la risposta si scrive lo stesso, segnalandoli; con molti passaggi rimasti si aspetta
            codice = self.lancia(accetta_incompleti=senza_progresso >= 2 and self.pochi(precedenti))
            if self.fermato():
                return self.aggiorna(stato="fermata", messaggio="Ricerca fermata su richiesta.")
            i = self.req["interpretazione"]
            if codice == 0:
                risposta = cartella_ricerca(self.cfg, i) / "risposta.md"
                senza_sintesi = risposta.exists() and MARCATORE in risposta.read_text(encoding="utf-8")
                if senza_sintesi and sintesi_mancate < 6 and time.time() - inizio < DURATA_MASSIMA_ORE * 3600:
                    sintesi_mancate += 1
                    dest = salva_risposta(self.cfg, i, self.req["domanda"])     # intanto la parte già pronta
                    self.aggiorna(risposta=dest.name if dest else None)
                    if not self.attendi(ATTESE_MINUTI[min(attese, 3)],
                                        "passaggi letti, ma il modello di sintesi non ha risposto"):
                        return self.aggiorna(stato="fermata", messaggio="Ricerca fermata su richiesta.")
                    attese += 1
                    continue
                dest = salva_risposta(self.cfg, i, self.req["domanda"])
                nl = self.non_letti()
                return self.aggiorna(
                    stato="completata, ma sintesi non generata" if senza_sintesi else "completata",
                    risposta=dest.name if dest else None, prossimo_tentativo=None,
                    messaggio=(f"{nl} passaggi non letti per errori ripetuti (segnalati nella sezione 5)."
                               if nl else ""))
            if codice == 3 and time.time() - inizio < DURATA_MASSIMA_ORE * 3600:
                resto = self.non_letti()
                senza_progresso = senza_progresso + 1 if precedenti is not None and resto >= precedenti else 0
                precedenti = resto
                motivo = (f"quote dei servizi gratuiti esaurite o servizio non raggiungibile; restano {resto} "
                          "passaggi da leggere" if resto else "servizio dei modelli non raggiungibile")
                if not self.attendi(ATTESE_MINUTI[min(attese, 3)], motivo):
                    return self.aggiorna(stato="fermata", messaggio="Ricerca fermata su richiesta.")
                attese += 1
                continue
            if codice == 3:
                return self.aggiorna(stato="interrotta", messaggio=f"Quote non disponibili per {DURATA_MASSIMA_ORE} "
                                     "ore: rifai la domanda più tardi, riprende da dove era.")
            return self.aggiorna(stato="errore", messaggio="La ricerca si è fermata con un errore che non passa da "
                                 "solo (chiave, modello o accesso al servizio): vedi ultimi_messaggi.")


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "esegui":
        config = sys.argv[sys.argv.index("--config") + 1] if "--config" in sys.argv else None
        e = Esecutore(sys.argv[2], config)
        try:
            e.esegui()
        except Exception as x:
            e.log(f"ERRORE del gestore: {type(x).__name__}: {x}")
            e.aggiorna(stato="errore", messaggio=f"Errore del gestore della ricerca: {type(x).__name__}: {x}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()

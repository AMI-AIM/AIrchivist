#!/usr/bin/env python3
"""
Archivio unico delle letture: ogni passaggio letto (dal modello o a mano) viene conservato una volta sola,
qualunque sia la ricerca che lo ha prodotto. Una ricerca successiva che ritrova lo stesso passaggio
(stesso file, stessa entità, stessa posizione) o una sua copia identica in un altro file non lo rimanda
al modello.

File: <risultati>/_archivio/letture.jsonl  (una riga per lettura; se un passaggio è riletto vale l'ultima)

Le cartelle di prova non leggono e non scrivono l'archivio: quelle il cui nome inizia con "prova" e quelle
che contengono il file ".senza_archivio" (lo crea valuta.py prepara), così le prove misurano davvero il modello.

Uso da riga di comando:
  python archivio.py importa      (aggiunge all'archivio le letture già presenti nelle cartelle dei risultati)
  python archivio.py stato        (quante letture per entità e per livello di provenienza)
  python archivio.py provenienza [--prova]
                                  (registra la provenienza nelle letture che non l'hanno; --prova: solo conteggi)
  python archivio.py equivalenza "nome vecchio" "nome della scheda" [nota]
                                  (dichiara che due nomi indicano la stessa entità: risultati/_archivio/equivalenze.json)
  python archivio.py riattribuisci "nome vecchio" "nome della scheda" [--applica]
                                  (piano per portare le letture sotto la scheda; --applica le aggiunge all'archivio)
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

NOME = "_archivio"


class _blocco:
    """Lucchetto inter-processo basato su file (msvcrt su Windows, fcntl altrove).

    Serve quando più processi possono scrivere sullo stesso JSONL (job paralleli, correzioni
    manuali dall'interfaccia di chat): senza blocco, due scritture in coda possono mescolarsi e
    generare righe corrotte. Se la libreria di blocco non è disponibile il file viene aperto lo
    stesso in append: su POSIX le scritture brevi sono atomiche in pratica, e il rischio residuo
    è preferito a un blocco duro che impedirebbe di lavorare."""
    def __init__(self, path):
        self.file = str(path) + ".lock"
        self.fd = None

    def __enter__(self):
        try:
            import msvcrt   # Windows
            self.fd = os.open(self.file, os.O_RDWR | os.O_CREAT)
            msvcrt.locking(self.fd, msvcrt.LK_LOCK, 1)
        except ImportError:
            try:
                import fcntl  # Linux/macOS
                self.fd = os.open(self.file, os.O_RDWR | os.O_CREAT)
                fcntl.flock(self.fd, fcntl.LOCK_EX)
            except ImportError:
                self.fd = None
        return self

    def __exit__(self, *eccezione):
        if self.fd is None:
            return False
        try:
            import msvcrt
            msvcrt.locking(self.fd, msvcrt.LK_UNLCK, 1)
        except ImportError:
            try:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            except ImportError:
                pass
        os.close(self.fd)
        self.fd = None
        return False


def append_jsonl(path, righe):
    """Aggiunge righe JSON a un file in modalità testo puro ("\n" non diventa "\r\n" su Windows),
    sotto blocco inter-processo e con fsync prima di restituire il controllo: una lettura già
    pagata al modello non si perde se il PC si spegne e due processi concorrenti non scrivono
    sopra la stessa riga."""
    with _blocco(path), open(path, "a", encoding="utf-8", newline="\n") as f:
        for riga in righe:
            f.write(riga if riga.endswith("\n") else riga + "\n")
        f.flush()
        os.fsync(f.fileno())


def normalizza_testo(s):
    return re.sub(r"[\s\-‐⟦⟧]+", "", s or "").lower()


def impronta(rec):
    """Impronta del testo del passaggio (per riconoscere copie identiche in file diversi)."""
    return hashlib.sha1((rec["entita"] + "|" + normalizza_testo(rec.get("passaggio", ""))).encode("utf-8")).hexdigest()[:16]


SOTTOCARTELLE = ("_riferimenti", "_sessioni_precedenti")      # raccolgono cartelle di risultati
PROVE = "_prove"


def escluso(cartella):
    cartella = Path(cartella)
    return (cartella.name.lower().startswith("prova") or cartella.parent.name == PROVE
            or (cartella / ".senza_archivio").exists())


def cartelle_risultati(risultati):
    """Cartelle dei risultati, comprese quelle raccolte in _riferimenti e _sessioni_precedenti
    (non le prove né l'archivio)."""
    ris = Path(risultati)
    out = []
    for d in sorted(ris.iterdir()) if ris.is_dir() else []:
        if not d.is_dir() or d.name in (NOME, PROVE, "_valutazione"):
            continue
        if d.name in SOTTOCARTELLE:
            out += [x for x in sorted(d.iterdir()) if x.is_dir()]
        else:
            out.append(d)
    return [d for d in out if not escluso(d)]


def file_risultati(risultati, nome):
    """Tutti i file 'nome' (es. passaggi.jsonl) delle cartelle dei risultati."""
    return [d / nome for d in cartelle_risultati(risultati) if (d / nome).exists()]


class Archivio:
    def __init__(self, risultati):
        self.dir = Path(risultati) / NOME
        self.file = self.dir / "letture.jsonl"
        self.per_id, self.per_impronta = {}, {}
        if self.file.exists():
            with open(self.file, encoding="utf-8") as f:
                for riga in f:
                    if riga.strip():
                        try:
                            self._indicizza(json.loads(riga))
                        except ValueError:
                            continue

    def _indicizza(self, voce):
        self.per_id[(voce["id"], voce["entita"])] = voce
        if voce.get("impronta"):
            self.per_impronta[voce["impronta"]] = voce

    def __len__(self):
        return len(self.per_id)

    def cerca(self, rec):
        """(analisi, come) se il passaggio è già stato letto; altrimenti (None, None)."""
        v = self.per_id.get((rec["id"], rec["entita"]))
        if v:
            return dict(v["analisi"]), "stesso passaggio"
        v = self.per_impronta.get(impronta(rec))
        if v:
            a = dict(v["analisi"])
            a["motivazione"] = (a.get("motivazione", "") + f" [copia identica del passaggio di {v.get('file', '?')}]").strip()
            return a, "copia identica"
        return None, None

    def aggiungi(self, rec, analisi, origine=""):
        self.dir.mkdir(parents=True, exist_ok=True)
        voce = {"id": rec["id"], "entita": rec["entita"], "file": rec.get("file", ""), "impronta": impronta(rec),
                "origine": origine, "letto_il": dt.date.today().isoformat(), "analisi": analisi}
        # append_jsonl: scrittura singola + fsync (vedi la sua documentazione)
        append_jsonl(self.file, [json.dumps(voce, ensure_ascii=False)])
        self._indicizza(voce)

    def importa(self, risultati):
        """Porta nell'archivio le letture delle cartelle dei risultati (solo quelle non ancora presenti)."""
        aggiunte = Counter()
        for f in file_risultati(risultati, "classificati.jsonl"):
            with open(f, encoding="utf-8") as fh:
                for riga in fh:
                    if not riga.strip():
                        continue
                    try:
                        r = json.loads(riga)
                    except ValueError:
                        continue
                    a = r.get("analisi") or {}
                    if a.get("pertinente") not in ("sì", "no", "incerto") or a.get("assorbito_da"):
                        continue
                    if (r["id"], r["entita"]) in self.per_id:
                        continue
                    self.aggiungi(r, a, origine=f.parent.name)
                    aggiunte[f.parent.name] += 1
        return aggiunte


_FILE_CACHE = {}


def riga_citazione(dati, file, riga, citazione):
    """Riga del file sorgente in cui si trova davvero la citazione (il campo 'riga' del passaggio indica
    l'inizio del passaggio, che può precedere di qualche riga la frase citata)."""
    try:
        riga = int(riga)
    except (TypeError, ValueError):
        return riga
    chiave = normalizza_testo(citazione)[:24]
    if not chiave or not dati:
        return riga
    p = Path(dati) / file
    if p not in _FILE_CACHE:
        if len(_FILE_CACHE) > 200:
            _FILE_CACHE.clear()
        try:
            _FILE_CACHE[p] = p.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return riga
    righe = _FILE_CACHE[p]
    for n in range(max(1, riga - 3), min(len(righe), riga + 300) + 1):
        corrente = normalizza_testo(righe[n - 1])
        seguente = normalizza_testo(righe[n]) if n < len(righe) else ""
        # la frase può cominciare alla fine di una riga e proseguire nella successiva
        if chiave in corrente or chiave in corrente + seguente[:len(chiave)]:
            return n
    return riga


def etichetta_lettore(nome):
    """Nome leggibile di chi ha letto il passaggio."""
    if nome == "lettura manuale":
        return "lettura assistita da Claude nelle sessioni di lavoro (non verificata a mano)"
    return nome


# ---------------------------------------------------------------- provenienza delle letture
# Ogni lettura dichiara, separatamente per la decisione sulla pertinenza e per la lettura vera e propria
# (citazione, traduzione, sintesi), uno di tre livelli:
#   modello   letto da un modello (campo "da": quale)
#   sessione  lettura assistita in una sessione di lavoro (in chat), non verificata a mano
#   regola    deciso per regola, senza leggere il passaggio (campo "da": quale regola)
# analisi["provenienza"] = {"decisione": {"livello": ..., "da": ...}, "lettura": {...} oppure None}
# "lettura" è None quando il passaggio non è stato tradotto né analizzato.
LIVELLI = {"modello": "letto da un modello", "sessione": "lettura assistita in sessione",
           "regola": "deciso per regola"}


def livello(liv, da=""):
    return {"livello": liv, "da": da}


def provenienza(a):
    """Provenienza di una lettura: quella registrata, altrimenti dedotta dai campi delle letture precedenti
    (classificato_da, modello_smistamento, modello_analisi, tipo_menzione)."""
    a = a or {}
    if a.get("provenienza"):
        return a["provenienza"]
    manuale = a.get("classificato_da") in ("lettura manuale", "correzione manuale") or \
        not (a.get("modello_smistamento") or a.get("modello_analisi"))
    mod_s = a.get("modello_smistamento") or ""
    if a.get("corretto_a_mano"):
        dec = livello("sessione", "correzione dalla chat")
    elif "per regola" in (a.get("tipo_menzione") or ""):
        dec = livello("regola", "classificazione per regola in una sessione assistita")
    elif manuale:
        dec = livello("sessione")
    elif mod_s.startswith("regola"):
        dec = livello("regola", mod_s[mod_s.find("(") + 1:].rstrip(")") if "(" in mod_s else mod_s)
    elif mod_s == "lettura precedente":
        dec = livello("sessione", "lettura precedente")
    else:
        dec = livello("modello", mod_s)
    mod_a = a.get("modello_analisi") or ""
    if a.get("sommario") or mod_a.startswith("nessuno (voce di sommario"):
        let = livello("regola", "voce di sommario o di elenco, non tradotta")
    elif not (a.get("traduzione_it") or "").strip():
        let = None
    elif mod_a and not mod_a.startswith("nessuno"):
        let = livello("modello", mod_a)
    else:
        let = livello("sessione")
    return {"decisione": dec, "lettura": let}


def descrivi_provenienza(prov):
    """Frase per le risposte: «pertinenza decisa per regola (forma inequivocabile); traduzione del modello X»."""
    def parte(p, cosa):
        if not p:
            return ""
        liv, da = p.get("livello"), p.get("da") or ""
        if liv == "modello":
            prep = "dal" if cosa.startswith("pertinenza") else "del"
            return f"{cosa} {prep} modello {da}" if da else f"{cosa} {prep[:2]} un modello"
        if liv == "regola":
            return f"{cosa} per regola" + (f" ({da})" if da else "")
        return f"{cosa} in una sessione assistita" + (f" ({da})" if da else "") + ", non verificata a mano"
    d_, l_ = prov.get("decisione") or {}, prov.get("lettura") or {}
    if d_.get("livello") == l_.get("livello") == "sessione" and d_.get("da") == l_.get("da"):
        return "pertinenza e traduzione in una sessione assistita" + (f" ({d_['da']})" if d_.get("da") else "") +             ", non verificate a mano"
    if d_.get("livello") == l_.get("livello") == "modello" and d_.get("da") == l_.get("da") and d_.get("da"):
        return f"pertinenza e traduzione del modello {d_['da']}"
    dec = parte(prov.get("decisione"), "pertinenza decisa")
    let = parte(prov.get("lettura"), "traduzione")
    if not prov.get("lettura"):
        let = "passaggio non tradotto"
    return "; ".join(x for x in (dec, let) if x)


def conta_provenienza(voci):
    """Conteggi per livello di decisione e di lettura: {'decisione': Counter, 'lettura': Counter}."""
    dec, let = Counter(), Counter()
    for c in voci:
        a = c.get("analisi") or {}
        if a.get("assorbito_da"):
            continue
        p = provenienza(a)
        d = p["decisione"]
        dec[(d["livello"], d.get("da") or "")] += 1
        l_ = p.get("lettura")
        let[(l_["livello"], l_.get("da") or "") if l_ else ("non tradotto", "")] += 1
    return {"decisione": dec, "lettura": let}


def migra_provenienza(risultati, soglia_blocco=5, prova=False):
    """Scrive analisi["provenienza"] nelle letture che non l'hanno (archivio e cartelle dei risultati).
    In più rispetto a provenienza(): le esclusioni in sessione con la stessa motivazione ripetuta in almeno
    'soglia_blocco' passaggi della stessa entità valgono come esclusioni per regola (in blocco); le decisioni
    riprese da una «lettura precedente» ereditano il livello di quella lettura, se è nell'archivio."""
    ris = Path(risultati)
    f_arch = ris / NOME / "letture.jsonl"
    righe = [json.loads(r) for r in f_arch.read_text(encoding="utf-8").splitlines() if r.strip()]
    ripetute = Counter((v["entita"], (v["analisi"].get("motivazione") or "").strip()) for v in righe
                       if v["analisi"].get("pertinente") == "no" and v["analisi"].get("classificato_da") == "lettura manuale")
    precedenti = {}

    def calcola(chiave, a):
        if a.get("provenienza"):
            return a["provenienza"]
        p = provenienza(a)
        mot = (a.get("motivazione") or "").strip()
        if (a.get("pertinente") == "no" and a.get("classificato_da") == "lettura manuale"
                and ripetute[(chiave[1], mot)] >= soglia_blocco):
            p["decisione"] = livello("regola", "esclusione in blocco in una sessione assistita")
        if p["decisione"].get("da") == "lettura precedente" and chiave in precedenti:
            p["decisione"] = dict(precedenti[chiave], da=(precedenti[chiave].get("da") or "") + " (lettura precedente)")
        return p

    conta = Counter()
    for v in righe:                                   # in ordine: una lettura precedente viene prima
        k = (v["id"], v["entita"])
        if not v["analisi"].get("provenienza"):
            v["analisi"]["provenienza"] = calcola(k, v["analisi"])
            conta["archivio"] += 1
        precedenti[k] = v["analisi"]["provenienza"]["decisione"]
    finali = {(v["id"], v["entita"]): v["analisi"]["provenienza"] for v in righe}
    if not prova:
        _riscrivi(f_arch, righe)
    for f in file_risultati(ris, "classificati.jsonl"):
        recs = [json.loads(r) for r in f.read_text(encoding="utf-8").splitlines() if r.strip()]
        cambiati = 0
        for r in recs:
            a = r.get("analisi") or {}
            if a.get("provenienza") or a.get("assorbito_da"):
                continue
            k = (r["id"], r["entita"])
            a["provenienza"] = finali.get(k) or calcola(k, a)
            cambiati += 1
        if cambiati:
            conta[str(f.parent.relative_to(ris))] += cambiati
            if not prova:
                _riscrivi(f, recs)
    return conta


def _riscrivi(f, voci):
    tmp = f.with_suffix(f.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as out:
        for v in voci:
            out.write(json.dumps(v, ensure_ascii=False) + "\n")
    tmp.replace(f)


def apri(cfg):
    from llm import percorso
    return Archivio(percorso(cfg, "risultati"))


# ---------------------------------------------------------------- nomi equivalenti e riattribuzione
def equivalenze(risultati):
    """Nomi di entità dichiarati equivalenti: {nome vecchio: {"nuovo": ..., "dichiarata_il": ..., "nota": ...}}."""
    f = Path(risultati) / NOME / "equivalenze.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def registra_equivalenza(risultati, vecchio, nuovo, nota=""):
    eq = equivalenze(risultati)
    eq[vecchio] = {"nuovo": nuovo, "dichiarata_il": dt.date.today().isoformat(), "nota": nota}
    f = Path(risultati) / NOME / "equivalenze.json"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(json.dumps(eq, ensure_ascii=False, indent=1).encode("utf-8"))


def piano_riattribuzione(cfg, vecchio, nuovo):
    """Per ogni lettura dell'entità 'vecchio': il passaggio che la scheda 'nuovo' estrarrebbe nello stesso punto
    (stessi criteri di estrai_occorrenze.py), e che cosa farne. Esiti:
      riattribuire          nessuna lettura per il passaggio della scheda nuova: si copia quella vecchia
      gia_letto             il passaggio ha già una lettura sotto la scheda nuova: resta quella
      decisioni_diverse     come sopra, ma con decisione diversa da quella vecchia: da controllare
      letture_discordi      più letture vecchie confluiscono in un passaggio nuovo con decisioni diverse
      fuori_dalla_scheda    la scheda nuova non trova nulla in quel punto (forma che non ha tra le varianti)
    Restituisce (righe del piano, nuove voci da aggiungere all'archivio)."""
    from estrai_occorrenze import carica_entita, compila, leggi_intestazione, passaggi_del_testo
    from llm import percorso
    ris, dati = percorso(cfg, "risultati"), percorso(cfg, "dati")
    schede = carica_entita(percorso(cfg, "entita"))
    if nuovo not in schede:
        sys.exit(f"La scheda «{nuovo}» non c'è in entita.ini.")
    scheda = {nuovo: schede[nuovo]}
    compila(scheda)
    finestra = cfg.getint("estrazione", "finestra", fallback=400)
    arch = Archivio(ris)
    vecchie = {i: v for (i, e), v in arch.per_id.items() if e == vecchio}
    if not vecchie:
        sys.exit(f"Nessuna lettura sotto «{vecchio}» nell'archivio.")
    record = {}
    for nome_f in ("passaggi.jsonl", "classificati.jsonl"):
        for f in file_risultati(ris, nome_f):
            with open(f, encoding="utf-8") as fh:
                for r in fh:
                    if r.strip():
                        c = json.loads(r)
                        if c.get("entita") == vecchio and c["id"] in vecchie and "offset" in c:
                            record.setdefault(c["id"], c)
    per_file = {}
    for i, v in vecchie.items():
        per_file.setdefault(v.get("file") or (record.get(i) or {}).get("file", ""), []).append(i)
    righe, assegnati = [], {}
    for rel, ids in sorted(per_file.items()):
        try:
            testo = (dati / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            testo = ""
        _, inizio = leggi_intestazione(testo)
        estratti = passaggi_del_testo(testo, inizio, rel, nuovo, scheda[nuovo], finestra) if testo else []
        nuovi = [r for r, _ in estratti]
        fini = {r["id"]: g["fine"] for r, g in estratti}
        for i in ids:
            a = vecchie[i]["analisi"]
            rec = record.get(i)
            riga = {"id_vecchio": i, "file": rel, "decisione_vecchia": a.get("pertinente"),
                    "provenienza": descrivi_provenienza(provenienza(a)),
                    "forme_vecchie": "; ".join((rec or {}).get("varianti_trovate", [])),
                    "id_nuovo": "", "forme_nuove": "", "decisione_nuova": "", "esito": ""}
            if not rec:
                riga["esito"] = "fuori_dalla_scheda"
                riga["nota"] = "passaggio vecchio non trovato nelle cartelle dei risultati (manca la posizione)"
                righe.append(riga)
                continue
            p = next((n for n in nuovi if n["offset"] <= rec["offset"] <= fini[n["id"]]), None)
            if not p:
                riga["esito"] = "fuori_dalla_scheda"
                righe.append(riga)
                continue
            riga["id_nuovo"], riga["forme_nuove"] = p["id"], "; ".join(p["varianti_trovate"])
            gia = arch.per_id.get((p["id"], nuovo))
            if not gia:
                c_imp = arch.per_impronta.get(impronta(p))
                gia = c_imp if c_imp and c_imp["entita"] == nuovo else None
            if gia:
                riga["decisione_nuova"] = gia["analisi"].get("pertinente")
                riga["esito"] = "gia_letto" if riga["decisione_nuova"] == a.get("pertinente") else "decisioni_diverse"
            else:
                assegnati.setdefault(p["id"], []).append((i, a, p))
                riga["esito"] = "riattribuire"
            righe.append(riga)
    oggi = dt.date.today().isoformat()
    voci = []
    for pid, gruppo in assegnati.items():
        decisioni = {a.get("pertinente") for _, a, _ in gruppo}
        if len(decisioni) > 1:
            for r in righe:
                if r["id_nuovo"] == pid:
                    r["esito"] = "letture_discordi"
            continue
        # se più letture vecchie confluiscono nello stesso passaggio, vale quella tradotta (o la prima)
        i, a, p = sorted(gruppo, key=lambda x: not (x[1].get("traduzione_it") or "").strip())[0]
        analisi = dict(a, riattribuita_da={"entita": vecchio, "id": i, "il": oggi})
        voci.append({"id": pid, "entita": nuovo, "file": p["file"], "impronta": impronta(p),
                     "origine": f"riattribuzione da {vecchio}", "letto_il": vecchie[i].get("letto_il", oggi),
                     "analisi": analisi})
    return righe, voci


def riattribuisci(cfg, vecchio, nuovo, applica=False):
    import csv
    from llm import percorso
    ris = percorso(cfg, "risultati")
    if equivalenze(ris).get(vecchio, {}).get("nuovo") != nuovo:
        sys.exit(f"Prima dichiara l'equivalenza: python archivio.py equivalenza \"{vecchio}\" \"{nuovo}\"")
    righe, voci = piano_riattribuzione(cfg, vecchio, nuovo)
    slug = re.sub(r"[^\w]+", "_", vecchio).strip("_")
    f_piano = ris / NOME / f"riattribuzione_{slug}_{dt.date.today():%Y%m%d}.csv"
    campi = ["esito", "id_vecchio", "id_nuovo", "file", "decisione_vecchia", "decisione_nuova", "forme_vecchie",
             "forme_nuove", "provenienza", "nota"]
    with open(f_piano, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, campi, delimiter=";", extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(righe, key=lambda r: (r["esito"], r["file"])))
    conta = Counter(r["esito"] for r in righe)
    print(f"Letture sotto «{vecchio}»: {len(righe)}")
    for esito, n in conta.most_common():
        dec = Counter(r["decisione_vecchia"] for r in righe if r["esito"] == esito)
        print(f"  {esito}: {n} ({', '.join(f'{k} {v}' for k, v in dec.most_common())})")
    fuori = Counter(f for r in righe if r["esito"] == "fuori_dalla_scheda" and r["decisione_vecchia"] != "no"
                    for f in r["forme_vecchie"].split("; ") if f)
    if fuori:
        print("Forme dei passaggi pertinenti o incerti che la scheda nuova non trova: "
              + "; ".join(f"{f} ({n})" for f, n in fuori.most_common(15)))
    print(f"Nuove letture da aggiungere sotto «{nuovo}»: {len(voci)}\nPiano: {f_piano}")
    if applica:
        arch = Archivio(ris)
        dest = Path(__file__).resolve().parent / "_backup" / f"{dt.date.today().isoformat()}_riattribuzione"
        dest.mkdir(parents=True, exist_ok=True)
        import shutil
        shutil.copy2(arch.file, dest / f"letture_{dt.datetime.now():%H%M%S}.jsonl")
        append_jsonl(arch.file, [json.dumps(v, ensure_ascii=False) for v in voci])
        print(f"Aggiunte {len(voci)} letture (copia dell'archivio in {dest}). Le letture sotto «{vecchio}» restano "
              "nell'archivio come storia; le ricerche usano quelle nuove.")
    else:
        print("Nessuna modifica: per applicare, aggiungi --applica.")


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from llm import leggi_config, percorso
    cfg = leggi_config()
    ris = percorso(cfg, "risultati")
    arch = Archivio(ris)
    azione = sys.argv[1] if len(sys.argv) > 1 else "stato"
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    if azione == "equivalenza":
        if len(sys.argv) < 4:
            sys.exit('Uso: python archivio.py equivalenza "nome vecchio" "nome della scheda" [nota]')
        registra_equivalenza(ris, sys.argv[2], sys.argv[3], " ".join(sys.argv[4:]))
        print(f"Registrato: «{sys.argv[2]}» = «{sys.argv[3]}» ({ris / NOME / 'equivalenze.json'})")
    elif azione == "riattribuisci":
        if len(sys.argv) < 4:
            sys.exit('Uso: python archivio.py riattribuisci "nome vecchio" "nome della scheda" [--applica]')
        riattribuisci(cfg, sys.argv[2], sys.argv[3], "--applica" in sys.argv)
    elif azione == "importa":
        agg = arch.importa(ris)
        for k, n in agg.most_common():
            print(f"  {k}: {n} letture aggiunte")
        print(f"Archivio: {len(arch)} letture ({arch.file})")
    elif azione == "provenienza":
        prova = "--prova" in sys.argv
        conta = migra_provenienza(ris, prova=prova)
        print(("Da aggiornare" if prova else "Aggiornate") + f": {sum(conta.values())} letture")
        for k, n in conta.most_common():
            print(f"  {k}: {n}")
    else:
        conta = Counter(e for (_, e) in arch.per_id)
        print(f"Archivio: {len(arch)} letture ({arch.file})")
        for e, n in conta.most_common():
            print(f"  {e}: {n}")
        prov = conta_provenienza([{"analisi": v["analisi"]} for v in arch.per_id.values()])
        for parte, titolo in (("decisione", "Decisione sulla pertinenza"), ("lettura", "Traduzione e analisi")):
            print(f"{titolo}:")
            for (liv, da), n in prov[parte].most_common():
                print(f"  {LIVELLI.get(liv, liv)}{' (' + da + ')' if da else ''}: {n}")


if __name__ == "__main__":
    main()

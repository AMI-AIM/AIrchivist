#!/usr/bin/env python3
"""
Nuove varianti dei nomi proposte dal modello durante la lettura dei passaggi: elenco, aggiunta a entities.ini,
scarto. Si usa dalla chat con lo strumento "varianti" del server MCP.

Vengono mostrate solo le forme che compaiono davvero nel testo del passaggio da cui sono state proposte.
Dopo aver aggiunto varianti si rifà la ricerca: troverà i nuovi passaggi, e quelli già letti non verranno
rimandati al modello.
"""
import configparser
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARTELLA))
try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass
from archivio import Archivio, normalizza_testo
from llm import leggi_config, percorso


def schede(f_entita):
    cp = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    cp.optionxform = str
    cp.read(f_entita, encoding="utf-8")
    return cp


def dividi(s):
    return [x.strip() for x in (s or "").replace("；", ";").split(";") if x.strip()]


def file_scartate(cfg):
    from archivio import NOME
    return percorso(cfg, "risultati") / NOME / "rejected_variants.json"


def carica_scartate(cfg):
    f = file_scartate(cfg)
    try:
        return {k: set(v) for k, v in json.loads(f.read_text(encoding="utf-8")).items()}
    except (OSError, ValueError):
        return {}


def salva_scartate(cfg, scartate):
    f = file_scartate(cfg)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({k: sorted(v) for k, v in scartate.items()}, ensure_ascii=False, indent=1),
                 encoding="utf-8")


def proposte(cfg, solo=None):
    """{entità: [{"variante", "volte", "esempio": {citazione, file, riga, testo}}]} ordinate per frequenza."""
    ris = percorso(cfg, "risultati")
    cp = schede(percorso(cfg, "entita"))
    scartate = carica_scartate(cfg)
    letture = list(Archivio(ris).per_id.values())
    # anche le letture delle cartelle, nel caso l'archivio non sia ancora stato creato
    from archivio import file_risultati
    for f in file_risultati(ris, "classificati.jsonl"):
        for riga in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(riga)
            except ValueError:
                continue
            letture.append({"id": r["id"], "entita": r["entita"], "file": r.get("file", ""), "analisi": r.get("analisi", {}),
                            "_rec": r})
    testi = {}
    for f in file_risultati(ris, "passaggi.jsonl"):
        for riga in f.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(riga)
            except ValueError:
                continue
            testi[(r["id"], r["entita"])] = r
    out = defaultdict(dict)
    for v in letture:
        e = v["entita"]
        if (solo and e != solo) or e not in cp.sections():
            continue
        note = {normalizza_testo(x) for x in dividi(cp.get(e, "varianti", fallback=""))}
        rec = v.get("_rec") or testi.get((v["id"], e))
        for nv in v["analisi"].get("nuove_varianti") or []:
            if not isinstance(nv, str) or not nv.strip():
                continue
            nv = nv.strip()
            k = normalizza_testo(nv)
            if not k or k in note or nv in scartate.get(e, set()):
                continue
            if rec and k not in normalizza_testo(rec.get("passaggio", "")):
                continue                     # il modello l'ha proposta ma nel testo non c'è
            voce = out[e].setdefault(k, {"variante": nv, "volte": 0, "ids": set(), "esempio": None})
            if v["id"] in voce["ids"]:
                continue
            voce["ids"].add(v["id"])
            voce["volte"] += 1
            if rec and not voce["esempio"]:
                t = rec.get("passaggio", "")
                j = t.find(nv)
                if j < 0:
                    j = max(0, t.find(nv[:2]))
                voce["esempio"] = {"citazione": rec.get("citazione") or rec.get("fonte", ""),
                                   "file": rec.get("file", ""), "riga": rec.get("riga", ""),
                                   "testo": t[max(0, j - 120): j + 160].replace("\n", " ")}
    return {e: sorted((dict(v, ids=None) for v in d.values()), key=lambda v: -v["volte"]) for e, d in out.items() if d}


def aggiungi(cfg, entita, nuove):
    """Aggiunge le varianti alla riga 'varianti =' della scheda, senza toccare il resto del file."""
    f = percorso(cfg, "entita")
    righe = f.read_text(encoding="utf-8").splitlines(keepends=True)
    dentro, fatto = False, False
    for k, r in enumerate(righe):
        m = re.match(r"^\[(.+)\]\s*$", r.strip("\r\n"))
        if m:
            dentro = m.group(1) == entita
            continue
        if dentro and re.match(r"^varianti\s*=", r):
            fine = "\r\n" if r.endswith("\r\n") else "\n" if r.endswith("\n") else ""
            corpo = r.rstrip("\r\n").rstrip()
            presenti = {normalizza_testo(x) for x in dividi(corpo.split("=", 1)[1])}
            agg = [v for v in nuove if normalizza_testo(v) not in presenti]
            if agg:
                righe[k] = corpo + ("; " if corpo.split("=", 1)[1].strip() else " ") + "; ".join(agg) + fine
            fatto = True
            break
    if not fatto:
        raise ValueError(f"Scheda [{entita}] o riga 'varianti' non trovata in {f.name}")
    f.write_text("".join(righe), encoding="utf-8")


def scarta(cfg, entita, varianti):
    s = carica_scartate(cfg)
    s.setdefault(entita, set()).update(varianti)
    salva_scartate(cfg, s)

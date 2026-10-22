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
  python archivio.py stato        (quante letture per entità)
"""
import datetime as dt
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

NOME = "_archivio"


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
        if not d.is_dir() or d.name in (NOME, PROVE):
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
        with open(self.file, "a", encoding="utf-8") as f:
            f.write(json.dumps(voce, ensure_ascii=False) + "\n")
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


def apri(cfg):
    from llm import percorso
    return Archivio(percorso(cfg, "risultati"))


def main():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from llm import leggi_config, percorso
    cfg = leggi_config()
    ris = percorso(cfg, "risultati")
    arch = Archivio(ris)
    azione = sys.argv[1] if len(sys.argv) > 1 else "stato"
    if azione == "importa":
        agg = arch.importa(ris)
        for k, n in agg.most_common():
            print(f"  {k}: {n} letture aggiunte")
        print(f"Archivio: {len(arch)} letture ({arch.file})")
    else:
        conta = Counter(e for (_, e) in arch.per_id)
        print(f"Archivio: {len(arch)} letture ({arch.file})")
        for e, n in conta.most_common():
            print(f"  {e}: {n}")


if __name__ == "__main__":
    main()

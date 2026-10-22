#!/usr/bin/env python3
"""
Registra la classificazione dei passaggi fatta in chat (senza API), verifica le citazioni e genera il rapporto.

Uso:
  python registra_analisi.py <cartella_risultati> <entita.ini>

La cartella deve contenere:
  passaggi.jsonl          (prodotto da estrai_occorrenze.py)
  analisi_manuale.json    { "<id>": [pertinente, tipo_menzione, citazione_testuale, traduzione_it, sintesi_it, [nuove_varianti]], ... }
                          pertinente = "sì" | "no" | "incerto". Gli id non elencati vengono registrati come "no".
Produce: classificati.jsonl, classificati.csv, rapporto.md. Stampa le citazioni NON ritrovate nel testo sorgente.
"""
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from archivio import livello
from classifica import verifica, carica_jsonl, scrivi_csv, scrivi_rapporto

def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cart = Path(sys.argv[1])
    A = json.loads((cart / "analisi_manuale.json").read_text(encoding="utf-8"))
    A = {k: v for k, v in A.items() if not k.startswith("_")}
    P = carica_jsonl(cart / "passaggi.jsonl")
    ids = {p["id"] for p in P}
    ignoti = [k for k in A if k not in ids]
    out, non_verificate = [], []
    for p in P:
        if p["id"] in A:
            pert, tipo, cit, trad, sint, var = (A[p["id"]] + [""] * 6)[:6]
            a = dict(pertinente=pert, tipo_menzione=tipo, citazione_testuale=cit, traduzione_it=trad,
                     sintesi_it=sint, nuove_varianti=var or [],
                     motivazione=sint if pert == "no" else "Riferimento all'entità cercata.")
        else:
            a = dict(pertinente="no", tipo_menzione="altro", citazione_testuale="", traduzione_it="",
                     sintesi_it="", nuove_varianti=[], motivazione="Non pertinente (uso generico, omonimo o altro).")
        a["classificato_da"] = "lettura manuale"
        if p["id"] in A:
            per_regola = "per regola" in (a["tipo_menzione"] or "")
            a["provenienza"] = {"decisione": livello("regola", "classificazione per regola in una sessione assistita")
                                if per_regola else livello("sessione"),
                                "lettura": livello("sessione") if (a["traduzione_it"] or "").strip() else None}
        else:
            a["provenienza"] = {"decisione": livello("regola", "non elencato nella lettura in sessione: escluso"),
                                "lettura": None}
        a["citazione_verificata"] = verifica(p, a) if a["pertinente"] in ("sì", "incerto") else False
        if a["pertinente"] in ("sì", "incerto") and not a["citazione_verificata"]:
            non_verificate.append((p["id"], p.get("citazione") or p["file"], a["citazione_testuale"][:60]))
        out.append(dict(p, analisi=a))
    with (cart / "classificati.jsonl").open("w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    out.sort(key=lambda c: (c["entita"], c["data"], c["file"], c["riga"]))
    scrivi_csv(out, cart / "classificati.csv")
    scrivi_rapporto(out, cart / "rapporto.md")
    n = {k: sum(1 for r in out if r["analisi"]["pertinente"] == k) for k in ("sì", "incerto", "no")}
    print(f"Passaggi: {len(out)} | pertinenti {n['sì']} | incerti {n['incerto']} | esclusi {n['no']}")
    if ignoti: print("ATTENZIONE id non trovati in passaggi.jsonl:", ignoti)
    print("Citazioni NON verificate:", non_verificate if non_verificate else "nessuna")
    print("Rapporto:", (cart / "rapporto.md").resolve())

if __name__ == "__main__":
    main()

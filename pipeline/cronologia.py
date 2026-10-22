"""
Cronologia calcolata da Python (nessun modello): presenze per anno, prima e ultima menzione,
silenzi, comparsa di entità collegate, lacune delle fonti dentro i silenzi.
"""
import csv
import datetime as dt
import re
from collections import Counter, defaultdict
from pathlib import Path

PERIODICI = ("Renmin Ribao", "Peking Review", "Hongqi", "Red Flag")
FINE_FONTI = dt.date(1980, 12, 31)       # ultimo numero disponibile di Renmin Ribao e Peking Review
INIZIO_FONTI = dt.date(1963, 1, 1)


def data_piena(c):
    if c["fonte"] not in PERIODICI:
        return None
    try:
        return dt.date.fromisoformat(c.get("data", "")[:10])
    except ValueError:
        return None


def mesi_tra(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month) + (b.day - a.day) / 30.0


def it(d):
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
            "settembre", "ottobre", "novembre", "dicembre"]
    return f"{d.day} {mesi[d.month - 1]} {d.year}"


def giorni_mancanti(problemi):
    """Date dei numeri del Renmin Ribao assenti dalle fonti."""
    out = []
    if problemi and Path(problemi).exists():
        with open(problemi, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r["serie"] == "Renmin Ribao" and r["problema"] == "giorno mancante":
                    m = re.search(r"(\d{4}-\d{2}-\d{2})", r["file"])
                    if m:
                        out.append(dt.date.fromisoformat(m.group(1)))
    return out


def calcola(pertinenti, principale, soglia_mesi=6, problemi=None, collegate_fino_a=None, fino_a=None):
    """Restituisce un dizionario con tutti i dati della cronologia."""
    date_per_entita = defaultdict(set)
    per_anno = defaultdict(Counter)            # anno -> entità -> n. documenti
    ruoli = defaultdict(lambda: defaultdict(Counter))   # entità -> anno -> ruolo
    toni = defaultdict(lambda: defaultdict(Counter))
    eventi = defaultdict(lambda: defaultdict(list))
    visti = set()
    for c in pertinenti:
        d = data_piena(c)
        if not d:
            continue
        e = c["entita"]
        a = c["analisi"]
        date_per_entita[e].add(d)
        chiave = (e, c["file"])
        if chiave not in visti:
            visti.add(chiave)
            per_anno[d.year][e] += 1
        if a.get("ruolo_entita"):
            ruoli[e][d.year][a["ruolo_entita"]] += 1
        if a.get("tono"):
            toni[e][d.year][a["tono"]] += 1
        if a.get("evento") and len(eventi[e][d.year]) < 6:
            eventi[e][d.year].append(a["evento"])

    mancanti = giorni_mancanti(problemi)
    silenzi = []
    estremi = {}
    for e, date in date_per_entita.items():
        date = sorted(date)
        estremi[e] = (date[0], date[-1], len(date))
        for x, y in zip(date, date[1:]):
            if mesi_tra(x, y) >= soglia_mesi:
                silenzi.append({"entita": e, "da": x, "a": y, "mesi": round(mesi_tra(x, y)),
                                "lacune": sum(1 for g in mancanti if x < g < y), "finale": False})
        fine = FINE_FONTI
        if fino_a:
            fine = min(fine, dt.date(fino_a, 12, 31))
        if collegate_fino_a and e != principale:
            fine = min(fine, dt.date(collegate_fino_a, 12, 31))
        if mesi_tra(date[-1], fine) >= soglia_mesi:
            silenzi.append({"entita": e, "da": date[-1], "a": fine,
                            "mesi": round(mesi_tra(date[-1], fine)), "limite_ricerca": fine != FINE_FONTI,
                            "lacune": sum(1 for g in mancanti if date[-1] < g <= fine), "finale": True})
    silenzi.sort(key=lambda s: (s["da"], s["entita"]))
    return {"principale": principale, "per_anno": per_anno, "ruoli": ruoli, "toni": toni,
            "eventi": eventi, "silenzi": silenzi, "estremi": estremi, "soglia": soglia_mesi}


def fatti(cr):
    """Frasi descrittive, solo dati, da passare al modello e da mostrare nella risposta."""
    righe = []
    p = cr["principale"]
    for e, (prima, ultima, n) in sorted(cr["estremi"].items(), key=lambda x: x[1][0]):
        righe.append(f"{e}: {n} date di menzione nei periodici, dalla prima del {it(prima)} all'ultima del {it(ultima)}.")
    for s in cr["silenzi"]:
        lac = (f" (in questo intervallo mancano dalle fonti {s['lacune']} "
               f"{'numero' if s['lacune'] == 1 else 'numeri'} del Renmin Ribao)") if s["lacune"] else ""
        if s["finale"] and s.get("limite_ricerca"):
            righe.append(f"Dopo il {it(s['da'])} {s['entita']} non è più menzionato fino al limite della ricerca "
                         f"({it(s['a'])}): {s['mesi']} mesi{lac}.")
        elif s["finale"]:
            righe.append(f"Dopo il {it(s['da'])} {s['entita']} non è più menzionato fino alla fine delle fonti "
                         f"periodiche disponibili ({it(s['a'])}): {s['mesi']} mesi{lac}.")
        else:
            righe.append(f"{s['entita']}: nessuna menzione tra il {it(s['da'])} e il {it(s['a'])} "
                         f"({s['mesi']} mesi){lac}.")
    if p in cr["estremi"]:
        ultima_p = cr["estremi"][p][1]
        for e, (prima, ultima, n) in cr["estremi"].items():
            if e != p and prima > ultima_p:
                righe.append(f"{e} compare per la prima volta il {it(prima)}, {round(mesi_tra(ultima_p, prima))} mesi "
                             f"dopo l'ultima menzione di {p}.")
    return righe


def tabella(cr):
    entita = sorted({e for c in cr["per_anno"].values() for e in c},
                    key=lambda e: (e != cr["principale"], e))
    intest = "| Anno | " + " | ".join(f"Documenti: {e}" for e in entita) + \
             f" | Ruoli attribuiti a {cr['principale']} | Tono prevalente | Eventi |"
    righe = [intest, "|" + "---|" * (len(entita) + 4)]
    anni = sorted(cr["per_anno"])
    if anni:
        anni = list(range(anni[0], anni[-1] + 1))
    p = cr["principale"]
    for a in anni:
        conti = " | ".join(str(cr["per_anno"].get(a, {}).get(e, 0) or "–") for e in entita)
        ruoli = "; ".join(r for r, _ in cr["ruoli"][p][a].most_common(3)) or "–"
        tono = ", ".join(f"{t} {n}" for t, n in cr["toni"][p][a].most_common(2)) or "–"
        ev = "; ".join(cr["eventi"][p][a][:3]) or "–"
        righe.append(f"| {a} | {conti} | {ruoli} | {tono} | {ev} |")
    return righe

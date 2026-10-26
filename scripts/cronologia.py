"""
Cronologia calcolata da Python (nessun modello): presenze per anno, prima e ultima menzione,
silenzi, comparsa di entità collegate, lacune delle fonti dentro i silenzi.

Date: per i periodici la data del numero; per le raccolte la data interna del documento, dedotta dal testo
(date_interne.py). Le date interne precise al giorno entrano in prime e ultime menzioni e nei silenzi; quelle
al mese o all'anno solo nella presenza per anno. I fatti dichiarano quante date sono dedotte.

Dai profili di serie (profili.py): quali fonti sono periodici (tipo), fin dove arrivano (periodo: i silenzi
finali si calcolano fino all'ultimo numero disponibile tra le serie in cui l'entità compare), lacune di tutte le
serie (open_issues.csv).
"""
import csv
import datetime as dt
import re
from collections import Counter, defaultdict
from pathlib import Path

import profili

DATI = None          # cartella delle fonti (per le date interne dei passaggi estratti prima del lavoro 9)


def periodico(c):
    return profili.e_periodico(c.get("fonte", ""), c.get("file", ""))


def data_piena(c):
    if not periodico(c):
        return None
    try:
        return dt.date.fromisoformat(c.get("data", "")[:10])
    except ValueError:
        return None


def data_di(c):
    """(data o None, anno o None, documento) del passaggio. Periodici: data del numero (solo l'anno per i
    fascicoli datati all'anno), documento None. Raccolte: data interna dedotta (data solo se precisa al giorno);
    documento = posizione dell'intestazione."""
    d = data_piena(c)
    if d:
        return d, d.year, None
    if periodico(c):
        anno = (c.get("data") or "")[:4]
        return None, (int(anno) if anno.isdigit() else None), None
    from date_interne import per_passaggio
    di = per_passaggio(c, DATI)
    if not di:
        return None, None, None
    try:
        d = dt.date.fromisoformat(di["data"]) if di.get("precisione") == "giorno" else None
    except ValueError:
        d = None
    return d, int(di["data"][:4]), di["posizione"]


def mesi_tra(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month) + (b.day - a.day) / 30.0


def it(d):
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno", "luglio", "agosto",
            "settembre", "ottobre", "novembre", "dicembre"]
    return f"{d.day} {mesi[d.month - 1]} {d.year}"


def serie_della_lacuna(nome_csv):
    """Profilo di una serie come è scritta in open_issues.csv («Hongqi (JPRS)» -> gruppo Hongqi)."""
    nome = (nome_csv or "").strip()
    if nome in profili.tutti():
        return nome
    return next((n for n in profili.tutti() if nome.lower().startswith(profili.gruppo(n).lower())), nome)


def giorni_mancanti(problemi):
    """[(data, serie)] dei numeri assenti dalle fonti («giorno mancante» in open_issues.csv)."""
    out = []
    if problemi and Path(problemi).exists():
        with open(problemi, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if r.get("problema") == "giorno mancante" and r.get("file"):
                    m = re.search(r"(\d{4}-\d{2}-\d{2})", r["file"])
                    if m:
                        out.append((dt.date.fromisoformat(m.group(1)), serie_della_lacuna(r["serie"])))
    return out


def lacune_tra(mancanti, da, a, fine_inclusa=False):
    """Numeri mancanti tra due date, per serie: Counter {serie: n}. Contano tutte le serie, non solo quelle in cui
    l'entità compare: un numero mancante di qualsiasi fonte cercata può nascondere una menzione."""
    return Counter(s for g, s in mancanti if da < g and (g <= a if fine_inclusa else g < a))


def calcola(pertinenti, principale, soglia_mesi=6, problemi=None, collegate_fino_a=None, fino_a=None):
    """Restituisce un dizionario con tutti i dati della cronologia."""
    date_per_entita = defaultdict(set)
    dedotte = defaultdict(set)                 # entità -> date che vengono da date interne delle raccolte
    periodiche = defaultdict(set)              # entità -> date dei numeri dei periodici
    per_anno = defaultdict(Counter)            # anno -> entità -> n. documenti
    ruoli = defaultdict(lambda: defaultdict(Counter))   # entità -> anno -> ruolo
    toni = defaultdict(lambda: defaultdict(Counter))
    eventi = defaultdict(lambda: defaultdict(list))
    serie_entita = defaultdict(set)            # entità -> periodici in cui compare (per fine delle fonti e lacune)
    visti = set()
    for c in pertinenti:
        d, anno, documento = data_di(c)
        if not anno:
            continue
        e = c["entita"]
        a = c["analisi"]
        if periodico(c):
            serie_entita[e].add(profili.nome_di(c.get("fonte", ""), c.get("file", "")))
        if d:
            date_per_entita[e].add(d)
            (dedotte[e] if documento is not None else periodiche[e]).add(d)
        chiave = (e, c["file"], documento)      # nelle raccolte conta ogni documento interno
        if chiave not in visti:
            visti.add(chiave)
            per_anno[anno][e] += 1
        if a.get("ruolo_entita"):
            ruoli[e][anno][a["ruolo_entita"]] += 1
        if a.get("tono"):
            toni[e][anno][a["tono"]] += 1
        if a.get("evento") and len(eventi[e][anno]) < 6:
            eventi[e][anno].append(a["evento"])

    mancanti = giorni_mancanti(problemi)
    silenzi = []
    estremi = {}
    for e, date in date_per_entita.items():
        date = sorted(date)
        estremi[e] = (date[0], date[-1], len(date), len(dedotte[e] - periodiche[e]))
        serie = serie_entita[e]
        for x, y in zip(date, date[1:]):
            if mesi_tra(x, y) >= soglia_mesi:
                silenzi.append({"entita": e, "da": x, "a": y, "mesi": round(mesi_tra(x, y)),
                                "lacune": lacune_tra(mancanti, x, y), "finale": False})
        fine_fonti = profili.fine_fonti(serie or None)          # ultimo numero tra le serie dell'entità
        if not fine_fonti:
            continue                                            # nessun periodo dichiarato nei profili
        fine = fine_fonti
        if fino_a:
            fine = min(fine, dt.date(fino_a, 12, 31))
        if collegate_fino_a and e != principale:
            fine = min(fine, dt.date(collegate_fino_a, 12, 31))
        if mesi_tra(date[-1], fine) >= soglia_mesi:
            silenzi.append({"entita": e, "da": date[-1], "a": fine,
                            "mesi": round(mesi_tra(date[-1], fine)), "limite_ricerca": fine != fine_fonti,
                            "lacune": lacune_tra(mancanti, date[-1], fine, True), "finale": True})
    silenzi.sort(key=lambda s: (s["da"], s["entita"]))
    return {"principale": principale, "per_anno": per_anno, "ruoli": ruoli, "toni": toni,
            "eventi": eventi, "silenzi": silenzi, "estremi": estremi, "soglia": soglia_mesi}


def fatti(cr):
    """Frasi descrittive, solo dati, da passare al modello e da mostrare nella risposta."""
    righe = []
    p = cr["principale"]
    for e, (prima, ultima, n, n_dedotte) in sorted(cr["estremi"].items(), key=lambda x: x[1][0]):
        dove = (f" ({n_dedotte} dalle date dei documenti nelle raccolte, dedotte dal testo)" if n_dedotte
                else " nei periodici")
        righe.append(f"{e}: {n} date di menzione{dove}, dalla prima del {it(prima)} all'ultima del {it(ultima)}.")
    for s in cr["silenzi"]:
        lac = ""
        if s["lacune"]:
            parti = [f"{n} {'numero' if n == 1 else 'numeri'} di {serie}" for serie, n in sorted(s["lacune"].items())]
            lac = f" (in questo intervallo mancano dalle fonti {', '.join(parti)})"
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
        for e, (prima, ultima, n, _) in cr["estremi"].items():
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

#!/usr/bin/env python3
"""
Schede delle entità (entita.ini): lettura, ricerca di un nome, aggiunta di una scheda nuova.
Usato dal server MCP (mcp_server.py).
"""
import configparser
import datetime as dt
import re


def leggi_schede(path):
    cp = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    cp.optionxform = str
    cp.read(path, encoding="utf-8")
    return cp


def dividi(s):
    return [x.strip() for x in (s or "").replace("；", ";").split(";") if x.strip()]


def cjk(s):
    return any("㐀" <= ch <= "鿿" for ch in s)


def trova_nel_testo(testo, cp):
    """Schede il cui nome o una variante compare letteralmente nel testo, nell'ordine in cui compaiono.
    Una scheda trovata solo grazie a una forma già usata da un'altra (es. "Grippa" dentro "PCB-Grippa")
    viene tralasciata."""
    d = testo.lower()
    trovate = []
    for s in cp.sections():
        forme = [s, cp.get(s, "forma_italiana", fallback="")] + dividi(cp.get(s, "varianti", fallback=""))
        usate, pos = set(), None
        for f in forme:
            f = f.strip()
            nome = re.sub(r"\s*\(.*?\)\s*$", "", f).lower()      # "PCMLB (Belgio)" -> "pcmlb"
            for forma in {f.lower(), nome}:
                if len(forma) < (2 if cjk(forma) else 4):
                    continue
                m = re.search(re.escape(forma) if cjk(forma) else r"(?<!\w)" + re.escape(forma) + r"(?!\w)", d)
                if m:
                    usate.add((m.start(), m.end()))
                    pos = m.start() if pos is None else min(pos, m.start())
        if usate:
            trovate.append((pos, -max(e - a for a, e in usate), s, usate))
    trovate.sort()
    scelte, coperte = [], set()
    for _, _, s, usate in sorted(trovate, key=lambda x: x[1]):          # prima le corrispondenze più lunghe
        if all(any(a >= a2 and e <= e2 for a2, e2 in coperte) for a, e in usate):
            continue
        scelte.append(s)
        coperte |= usate
    ordine = {s: (pos, l) for pos, l, s, _ in trovate}
    return sorted(scelte, key=lambda s: ordine[s])


def aggiungi_collegate_scheda(i, cp):
    """Per l'evoluzione si usano sempre anche le entità del campo 'collegate' della scheda principale."""
    if i["modalita"] == "evoluzione" and i["principale"]:
        for c in dividi(cp.get(i["principale"], "collegate", fallback="")):
            if c in cp.sections() and c not in i["collegate"] and c != i["principale"]:
                i["collegate"].append(c)
    return i


def aggiungi_scheda(f_entita, nome, varianti, descrizione="", contesto=None, forme_ambigue=None, collegate=None):
    """Aggiunge in fondo a entita.ini una scheda con le forme confermate dall'utente."""
    def pulisci(xs):
        return [re.sub(r"[;\n]", "", x).strip() for x in (xs or []) if x and x.strip()]
    nome = re.sub(r"[\[\]\n]", "", nome).strip()
    varianti = pulisci(varianti) or [nome]
    righe = [f"[{nome}]", f"varianti = {'; '.join(varianti)}", f"contesto = {'; '.join(pulisci(contesto))}"]
    if forme_ambigue:
        righe.append(f"forme_ambigue = {'; '.join(pulisci(forme_ambigue))}")
    if collegate:
        righe.append(f"collegate = {'; '.join(pulisci(collegate))}")
    nota = re.sub(r"\s+", " ", descrizione or "").strip()
    righe.append(f"note = {nota} Scheda creata il {dt.date.today().isoformat()} dalla chat, con le forme "
                 "attestate nelle fonti e confermate dall'utente.".strip())
    with open(f_entita, "a", encoding="utf-8") as f:
        f.write("\n" + "\n".join(righe) + "\n")
    return nome

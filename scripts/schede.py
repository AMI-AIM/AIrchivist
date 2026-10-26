#!/usr/bin/env python3
"""
Schede delle entità (entities.ini): lettura, ricerca di un nome, aggiunta di una scheda nuova.
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


def forma_estesa(cp, s):
    """Nome per esteso di un ente indicato da una sigla (campo forma_estesa; forma_italiana è il nome vecchio)."""
    return (cp.get(s, "forma_estesa", fallback="") or cp.get(s, "forma_italiana", fallback="")).strip()


def trova_nel_testo(testo, cp):
    """Schede il cui nome o una variante compare letteralmente nel testo, nell'ordine in cui compaiono.
    Una scheda trovata solo grazie a una forma già usata da un'altra (es. "Grippa" dentro "PCB-Grippa")
    viene tralasciata."""
    d = testo.lower()
    trovate = []
    for s in cp.sections():
        forme = [s, forma_estesa(cp, s)] + dividi(cp.get(s, "varianti", fallback=""))
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


def aggiungi_scheda(f_entita, nome, varianti, descrizione="", contesto=None, forme_ambigue=None, collegate=None,
                    tipo="", estesa=""):
    """Aggiunge in fondo a entities.ini una scheda con le forme confermate dall'utente."""
    def pulisci(xs):
        return [re.sub(r"[;\n]", "", x).strip() for x in (xs or []) if x and x.strip()]
    nome = re.sub(r"[\[\]\n]", "", nome).strip()
    varianti = pulisci(varianti) or [nome]
    righe = [f"[{nome}]"]
    if tipo in TIPI:
        righe.append(f"tipo = {tipo}")
    if estesa and estesa.strip():
        righe.append("forma_estesa = " + re.sub(r"[;\n]", "", estesa).strip())
    righe += [f"varianti = {'; '.join(varianti)}", f"contesto = {'; '.join(pulisci(contesto))}"]
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


# ---------------------------------------------------------------- controllo delle schede
TIPI = ("persona", "organizzazione", "testata", "stato", "altro")
CAMPI = {"varianti", "contesto", "note", "tipo", "forma_estesa", "forme_ambigue", "collegate"}


def forma_breve(v):
    """Forma che da sola può indicare altro (va in forme_ambigue): meno di 5 lettere latine, 2 caratteri
    cinesi o meno, una parola latina sola (cognome, nome comune)."""
    nucleo = re.sub(r"[《》（）()·・\s]", "", v)
    if cjk(v):
        return len(nucleo) <= 2
    return len(nucleo) < 5 or (" " not in v.strip() and "-" not in v and not v.isupper() and len(nucleo) < 8)


def sigla(nome):
    """Nome canonico che comincia con una sigla (PCdoB, MLPÖ (Austria), PCd'I (m-l), CPA(ML) (Australia)), senza
    il nome per esteso nel titolo stesso («PTE - Partito del Lavoro di Spagna»)."""
    primo = re.split(r"[\s(\-/]", nome.strip(), maxsplit=1)[0]
    if sum(1 for ch in primo if ch.isupper()) < 2:
        return False
    return not re.search(r"\s-\s+\w+\s+\w+", nome)


def norm(v):
    return re.sub(r"[\s·・•.\-（）()《》]", "", v).lower()


def ambigue_non_cercate(varianti, forme_ambigue):
    """Forme ambigue che non sono tra le varianti. La ricerca cerca solo le varianti: forme_ambigue dice quali di
    queste il modello deve controllare sempre, non aggiunge forme da cercare (25/10/2026: «Berlinguer», solo
    tra le forme ambigue, non è stato cercato e Peking Review 1980, no. 18 è sfuggito)."""
    cercate = {norm(v) for v in varianti}
    return [a for a in forme_ambigue if a and a.strip() and norm(a) not in cercate]


def controlla(f_entita, risultati=None):
    """Problemi delle schede, come righe (gravità, scheda, problema). Vedi docs/schede_entita.md."""
    cp = leggi_schede(f_entita)
    out = []
    forme = {}
    for s in cp.sections():
        x = cp[s]
        for campo in x:
            if campo == "forma_italiana":
                out.append(("avviso", s, "campo forma_italiana: si chiama ora forma_estesa"))
            elif campo not in CAMPI:
                out.append(("avviso", s, f"campo sconosciuto «{campo}»"))
        if sigla(s) and not forma_estesa(cp, s) and x.get("tipo", "").strip() != "persona":
            out.append(("info", s, "il nome è una sigla: manca forma_estesa (il nome per esteso dell'ente)"))
        var = dividi(x.get("varianti", ""))
        if not var:
            out.append(("errore", s, "nessuna variante"))
        if re.search(r"\b(dirigenti|varianti|forma|forme|altre|altri)\b", s, re.IGNORECASE):
            out.append(("avviso", s, "il nome indica un gruppo di persone o un insieme di forme, non un'entità: "
                                     "le forme vanno nella scheda dell'entità, le persone in schede proprie"))
        if not x.get("note", "").strip():
            out.append(("avviso", s, "note vuote: manca la descrizione dell'entità (chi è, periodo, omonimi)"))
        tipo = x.get("tipo", "").strip()
        if not tipo:
            out.append(("info", s, "manca il campo tipo (" + ", ".join(TIPI) + ")"))
        elif tipo not in TIPI:
            out.append(("errore", s, f"tipo «{tipo}» non previsto (" + ", ".join(TIPI) + ")"))
        ambigue = {norm(a) for a in dividi(x.get("forme_ambigue", ""))}
        for a in ambigue_non_cercate(var, dividi(x.get("forme_ambigue", ""))):
            out.append(("avviso", s, f"forma ambigua «{a}» non compare tra le varianti: la ricerca non la cerca "
                                     "(aggiungerla alle varianti, o toglierla dalle forme ambigue)"))
        brevi = [v for v in var if forma_breve(v) and norm(v) not in ambigue]
        if brevi:
            out.append(("avviso", s, "forme brevi o generiche non dichiarate in forme_ambigue: " + "; ".join(brevi)))
        for c in dividi(x.get("collegate", "")):
            if c not in cp.sections():
                out.append(("errore", s, f"entità collegata «{c}» senza scheda"))
            elif c == s:
                out.append(("errore", s, "collegata a sé stessa"))
        for v in var:
            forme.setdefault(norm(v), []).append((s, v))
    for n, usi in forme.items():
        schede_ = sorted({s for s, _ in usi})
        if len(schede_) > 1:
            out.append(("errore", " / ".join(schede_), f"stessa forma in più schede: «{usi[0][1]}» (unire le schede, "
                                                        "oppure lasciare la forma a una sola e dichiararla ambigua)"))
    # forma di una scheda contenuta in una forma di un'altra: relazione da dichiarare (collegate) o omonimia
    lunghe = [(n, s) for n, usi in forme.items() for s in {s for s, _ in usi} if len(n) >= 4]
    coppie = {}
    for n, s in lunghe:
        for n2, s2 in lunghe:
            if s2 != s and n != n2 and n in n2:
                coll = set(dividi(cp.get(s, "collegate", fallback=""))) | set(dividi(cp.get(s2, "collegate", fallback="")))
                if s not in coll and s2 not in coll:
                    coppie.setdefault((s, s2), []).append((n, n2))
    for (s, s2), es in coppie.items():
        n, n2 = es[0]
        out.append(("info", f"{s} / {s2}", f"una forma di {s} è contenuta in {len(es)} forme di {s2} (es. «{n}» in "
                                          f"«{n2}»): i passaggi di {s2} vengono estratti anche per {s} "
                                          "(dichiarare collegate o forme_ambigue?)"))
    if risultati:
        out += passaggi_identici(cp, risultati)
    ordine = {"errore": 0, "avviso": 1, "info": 2}
    return sorted(set(out), key=lambda r: (ordine[r[0]], r[1], r[2]))


def passaggi_identici(cp, risultati):
    """Schede che nell'archivio hanno esattamente gli stessi passaggi (stessi file e posizioni): doppioni."""
    import json
    from pathlib import Path
    from archivio import LETTURE, NOME
    f = Path(risultati) / NOME / LETTURE
    if not f.exists():
        return []
    per_entita = {}
    with open(f, encoding="utf-8") as fh:
        for r in fh:
            if r.strip():
                v = json.loads(r)
                per_entita.setdefault(v["entita"], set()).add((v.get("file"), v.get("impronta")))
    gruppi = {}
    for e, ps in per_entita.items():
        if e in cp.sections() and len(ps) >= 5:
            gruppi.setdefault(frozenset(ps), []).append(e)
    out = [("errore", " / ".join(sorted(es)), f"le schede hanno gli stessi {len(ps)} passaggi nell'archivio: "
                                               "probabile doppione")
           for ps, es in gruppi.items() if len(es) > 1]
    # letture registrate sotto un nome che non ha più una scheda (scheda rinominata o unita a un'altra)
    from archivio import equivalenze
    eq = equivalenze(risultati)
    for e, ps in sorted(per_entita.items()):
        if e not in cp.sections() and eq.get(e, {}).get("nuovo") in cp.sections():
            out.append(("info", e, f"{len(ps)} passaggi nell'archivio sotto un nome dichiarato equivalente a "
                                   f"«{eq[e]['nuovo']}» (python archivio.py riattribuisci per riportarli sotto la scheda)"))
        elif e not in cp.sections():
            simili = [s for s in cp.sections() if norm(re.sub(r"\(.*?\)", "", s)) == norm(re.sub(r"\(.*?\)", "", e))]
            out.append(("avviso", e, f"{len(ps)} passaggi nell'archivio sotto un nome senza scheda"
                        + (f" (simile a «{simili[0]}»: scheda rinominata?)" if simili else "")))
    return out


def main():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from llm import leggi_config, percorso
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    if len(sys.argv) < 2 or sys.argv[1] != "controlla":
        sys.exit("Uso: python schede.py controlla [--solo-errori]")
    cfg = leggi_config()
    righe = controlla(percorso(cfg, "entita"), percorso(cfg, "risultati"))
    if "--solo-errori" in sys.argv:
        righe = [r for r in righe if r[0] == "errore"]
    for g, s, p in righe:
        print(f"{g:7} {s}: {p}")
    conta = {g: sum(1 for r in righe if r[0] == g) for g in ("errore", "avviso", "info")}
    print(f"\n{len(cp_sezioni(percorso(cfg, 'entita')))} schede: {conta['errore']} errori, {conta['avviso']} avvisi, "
          f"{conta['info']} informazioni. Regole: docs/schede_entita.md")


def cp_sezioni(f):
    return leggi_schede(f).sections()


if __name__ == "__main__":
    main()

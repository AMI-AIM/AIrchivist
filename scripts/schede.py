#!/usr/bin/env python3
"""
Schede delle entità (entities.ini): lettura, ricerca di un nome, aggiunta di una scheda nuova, modifica.
Usato dagli strumenti del motore (strumenti.py).
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


# ---------------------------------------------------------------- modifica delle schede
def leggi_scheda(f_entita, nome):
    """Legge i campi di una scheda esistente."""
    cp = leggi_schede(f_entita)
    if nome not in cp.sections():
        return None
    x = cp[nome]
    return {
        "nome": nome,
        "tipo": x.get("tipo", "").strip(),
        "forma_estesa": x.get("forma_estesa", "").strip(),
        "varianti": dividi(x.get("varianti", "")) or [nome],
        "contesto": dividi(x.get("contesto", "")),
        "forme_ambigue": dividi(x.get("forme_ambigue", "")),
        "collegate": dividi(x.get("collegate", "")),
        "note": x.get("note", "").strip(),
    }


# Le schede (e i profili delle serie, stesso formato) si riscrivono riga per riga: commenti, ordine dei campi e campi
# che l'interfaccia non conosce (nome_completo, forma_italiana…) restano come sono. Si toccano solo le righe dei campi
# cambiati; un campo nuovo va in fondo alla sua sezione.
ELENCHI = ("varianti", "contesto", "forme_ambigue", "collegate")
_TESTA = re.compile(r"^\s*\[([^\]]+)\]\s*$")
_CAMPO = re.compile(r"^([^\s=#;][^=]*?)\s*=")


def _sezioni(righe):
    """{nome: (inizio, fine)}: la riga della testata e la prima riga dopo la sezione (la testata seguente, o la
    fine del file). I commenti subito prima di una testata appartengono alla sezione che segue."""
    teste = [(i, m.group(1).strip()) for i, r in enumerate(righe) for m in [_TESTA.match(r)] if m]
    out = {}
    for k, (i, nome) in enumerate(teste):
        fine = teste[k + 1][0] if k + 1 < len(teste) else len(righe)
        while fine > i + 1 and righe[fine - 1].lstrip().startswith(("#", ";")):
            fine -= 1                                      # il commento è della sezione seguente
        out[nome] = (i, fine)
    return out


def _campi_della_sezione(righe, inizio, fine):
    """{campo: (prima riga, riga dopo l'ultima)}: un valore può continuare sulle righe rientrate che seguono."""
    out, k = {}, inizio + 1
    while k < fine:
        m = _CAMPO.match(righe[k])
        if m:
            j = k + 1
            while j < fine and righe[j].strip() and righe[j][:1] in (" ", "\t"):
                j += 1
            out[m.group(1).strip()] = (k, j)
            k = j
        else:
            k += 1
    return out


def _valore(v):
    if isinstance(v, (list, tuple)):
        return "; ".join(x for x in (re.sub(r"[;\n\r]", " ", str(i)).strip() for i in v) if x)
    return re.sub(r"\s*[\n\r]+\s*", " ", str(v or "")).strip()


def _leggi_righe(f):
    testo = f.read_text(encoding="utf-8")
    fine = "\r\n" if "\r\n" in testo else "\n"
    return testo.splitlines(), fine


def _scrivi_righe(f, righe, fine):
    f.write_text(fine.join(righe).rstrip() + fine, encoding="utf-8", newline="")


def nome_valido(nome):
    nome = re.sub(r"\s+", " ", nome or "").strip()
    if not nome or re.search(r"[\[\]=;]", nome):
        raise ValueError("Il nome non può essere vuoto né contenere [ ] = ;")
    return nome


def modifica_sezione(f, nome, campi):
    """Cambia i campi di una sezione di un file INI (scheda o serie). campi: {campo: valore} (un elenco diventa
    «a; b; c»). Restituisce [(campo, valore di prima, valore nuovo)] dei soli campi cambiati."""
    righe, fine = _leggi_righe(f)
    sez = _sezioni(righe)
    if nome not in sez:
        raise ValueError(f"«{nome}» non trovata")
    inizio, termine = sez[nome]
    esistenti = _campi_della_sezione(righe, inizio, termine)
    cambiati, nuove = [], []
    sostituzioni = {}
    for campo, v in campi.items():
        campo = campo.strip()
        if not re.fullmatch(r"[A-Za-z_][\w]*", campo):
            raise ValueError(f"Nome di campo non valido: «{campo}»")
        nuovo = _valore(v)
        if campo in esistenti:
            a, b = esistenti[campo]
            prima = " ".join(x.strip() for x in [righe[a].split("=", 1)[1]] + righe[a + 1:b]).strip()
            if v is None:                              # None: il campo si toglie (righe di continuazione comprese)
                sostituzioni[(a, b)] = None
                cambiati.append((campo, prima, ""))
                continue
            if prima == nuovo:
                continue
            sostituzioni[(a, b)] = f"{campo} = {nuovo}".rstrip()
            cambiati.append((campo, prima, nuovo))
        elif nuovo and v is not None:
            nuove.append(f"{campo} = {nuovo}")
            cambiati.append((campo, "", nuovo))
    if not cambiati:
        return []
    out, k = [], 0
    while k < len(righe):
        blocco = next(((a, b) for (a, b) in sostituzioni if a == k), None)
        if blocco:
            if sostituzioni[blocco] is not None:
                out.append(sostituzioni[blocco])
            k = blocco[1]
            continue
        out.append(righe[k])
        k += 1
    if nuove:                                          # in fondo alla sezione, prima delle righe vuote
        sez = _sezioni(out)
        inizio, termine = sez[nome]
        dove = termine
        while dove > inizio + 1 and not out[dove - 1].strip():
            dove -= 1
        out[dove:dove] = nuove
    _scrivi_righe(f, out, fine)
    return cambiati


def modifica_scheda(f_entita, nome, campi):
    """I campi della scheda «nome» (varianti, tipo, forma_estesa, contesto, forme_ambigue, collegate, note e
    qualsiasi altro). Restituisce [(campo, prima, dopo)]. Le varianti non possono restare vuote."""
    campi = dict(campi)
    if "tipo" in campi and campi["tipo"] and campi["tipo"] not in TIPI:
        raise ValueError(f"Tipo «{campi['tipo']}» non previsto ({', '.join(TIPI)})")
    if "varianti" in campi and not _valore(campi["varianti"]):
        raise ValueError("Una scheda ha almeno una forma del nome")
    return modifica_sezione(f_entita, nome, campi)


def _togli_dalle_collegate(righe, nome, sostituto=None):
    """Nelle «collegate» di tutte le sezioni, «nome» diventa «sostituto» (o sparisce). [(sezione, prima, dopo)]."""
    cambi = []
    for s, (inizio, fine) in _sezioni(righe).items():
        campi = _campi_della_sezione(righe, inizio, fine)
        if "collegate" not in campi:
            continue
        a, b = campi["collegate"]
        prima = dividi(" ".join([righe[a].split("=", 1)[1]] + righe[a + 1:b]))
        if nome not in prima:
            continue
        dopo = []
        for c in prima:
            c = sostituto if c == nome else c
            if c and c != s and c not in dopo:
                dopo.append(c)
        righe[a] = f"collegate = {'; '.join(dopo)}".rstrip()
        del righe[a + 1:b]
        cambi.append((s, "; ".join(prima), "; ".join(dopo)))
    return cambi


def rinomina_scheda(f_entita, vecchio, nuovo):
    """Cambia il nome della sezione e lo aggiorna nelle «collegate» delle altre schede. Il nome vecchio resta tra le
    varianti se c'era. Restituisce (vecchio, nuovo, [schede le cui collegate sono cambiate])."""
    nuovo = nome_valido(nuovo)
    righe, fine = _leggi_righe(f_entita)
    sez = _sezioni(righe)
    if vecchio not in sez:
        raise ValueError(f"Scheda «{vecchio}» non trovata")
    if nuovo in sez and nuovo != vecchio:
        raise ValueError(f"Esiste già una scheda «{nuovo}»")
    righe[sez[vecchio][0]] = f"[{nuovo}]"
    cambi = _togli_dalle_collegate(righe, vecchio, nuovo)
    _scrivi_righe(f_entita, righe, fine)
    return vecchio, nuovo, [c[0] for c in cambi]


def elimina_scheda(f_entita, nome):
    """Toglie la sezione (con i commenti che la precedono) e il suo nome dalle «collegate» delle altre schede.
    Restituisce (nome, [schede le cui collegate sono cambiate])."""
    righe, fine = _leggi_righe(f_entita)
    sez = _sezioni(righe)
    if nome not in sez:
        raise ValueError(f"Scheda «{nome}» non trovata")
    inizio, termine = sez[nome]
    while inizio > 0 and righe[inizio - 1].lstrip().startswith(("#", ";")):
        inizio -= 1
    while termine < len(righe) and not righe[termine].strip():
        termine += 1
    del righe[inizio:termine]
    cambi = _togli_dalle_collegate(righe, nome)
    _scrivi_righe(f_entita, righe, fine)
    return nome, [c[0] for c in cambi]


def unisci_schede(f_entita, da, verso):
    """Porta forme, forme ambigue, contesto e collegate di «da» in «verso» (senza doppioni) e toglie «da».
    Restituisce i cambi di «verso» [(campo, prima, dopo)]."""
    cp = leggi_schede(f_entita)
    for s in (da, verso):
        if s not in cp.sections():
            raise ValueError(f"Scheda «{s}» non trovata")
    if da == verso:
        raise ValueError("Una scheda non si unisce a sé stessa")
    campi = {}
    for c in ELENCHI:
        tutti = dividi(cp.get(verso, c, fallback=""))
        for x in dividi(cp.get(da, c, fallback="")) + ([da] if c == "varianti" else []):
            if x not in tutti and not (c == "collegate" and x in (da, verso)):
                tutti.append(x)
        campi[c] = tutti
    nota = cp.get(verso, "note", fallback="").strip()
    campi["note"] = (nota + f" Unita con la scheda «{da}» il {dt.date.today().isoformat()}.").strip()
    cambi = modifica_sezione(f_entita, verso, campi)
    elimina_scheda(f_entita, da)
    righe, fine = _leggi_righe(f_entita)
    if _togli_dalle_collegate(righe, da, verso):
        _scrivi_righe(f_entita, righe, fine)
    return cambi


# ---------------------------------------------------------------- creazione di schede
TIPI = ("persona", "organizzazione", "testata", "stato", "altro")
CAMPI = {"varianti", "contesto", "note", "tipo", "forma_estesa", "forme_ambigue", "collegate"}


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
def forma_breve(v):
    """Forma che da sola può indicare altro (va in forme_ambigue): meno di 5 lettere latine, 2 caratteri
    cinesi o meno, una parola latina sola (cognome, nome comune)."""
    nucleo = re.sub(r"[《》（）()·・\s]", "", v)
    if cjk(v):
        return len(nucleo) <= 2
    return len(nucleo) < 5 or (" " not in v.strip() and "-" not in v and not v.isupper() and len(nucleo) < 8)


def brevi_non_dichiarate(varianti, ambigue):
    """Le forme brevi o generiche (forma_breve) che non sono tra le ambigue."""
    dichiarate = {norm(a) for a in ambigue}
    return [v for v in varianti if forma_breve(v) and norm(v) not in dichiarate]


def con_brevi_ambigue(varianti, ambigue):
    """Le forme ambigue con in più le forme brevi delle varianti: la regola che ogni ingresso di forme applica
    (creazione, forme suggerite, esplorazione), così il controllo non ha niente da segnalare dopo."""
    ambigue = list(ambigue or [])
    return ambigue + [v for v in brevi_non_dichiarate(varianti, ambigue) if v not in ambigue]


# campi di prima: il nome per esteso ora sta in forma_estesa; se ripete il nome della scheda non serve
CAMPI_VECCHI = ("forma_italiana", "nome_completo")


def correzioni(f_entita, nome):
    """Le correzioni che si possono fare da sole sulla scheda: [{"tipo", "descrizione"}]."""
    cp = leggi_schede(f_entita)
    if nome not in cp.sections():
        return []
    x = cp[nome]
    var, amb = dividi(x.get("varianti", "")), dividi(x.get("forme_ambigue", ""))
    out = []
    brevi = brevi_non_dichiarate(var, amb)
    if brevi:
        out.append({"tipo": "brevi", "descrizione": "Segna come ambigue: " + "; ".join(brevi)})
    fuori = ambigue_non_cercate(var, amb)
    if fuori:
        out.append({"tipo": "ambigue_fuori", "descrizione": "Togli dalle forme ambigue: " + "; ".join(fuori)})
    for c in CAMPI_VECCHI:
        if c not in x:
            continue
        v = x.get(c, "").strip()
        if v and norm(v) != norm(nome) and not x.get("forma_estesa", "").strip():
            out.append({"tipo": "campo:" + c, "descrizione": f"Sposta «{c}» in forma_estesa"})
        else:
            out.append({"tipo": "campo:" + c, "descrizione": f"Togli «{c}» (ripete il nome della scheda)"})
    return out


def correggi(f_entita, nome, tipo):
    """Applica una correzione di correzioni(); restituisce [(campo, prima, dopo)]."""
    cp = leggi_schede(f_entita)
    if nome not in cp.sections():
        raise ValueError(f"Scheda «{nome}» non trovata")
    x = cp[nome]
    var, amb = dividi(x.get("varianti", "")), dividi(x.get("forme_ambigue", ""))
    if tipo == "brevi":
        return modifica_sezione(f_entita, nome, {"forme_ambigue": con_brevi_ambigue(var, amb)})
    if tipo == "ambigue_fuori":
        fuori = {norm(a) for a in ambigue_non_cercate(var, amb)}
        return modifica_sezione(f_entita, nome, {"forme_ambigue": [a for a in amb if norm(a) not in fuori]})
    if tipo.startswith("campo:") and tipo[6:] in CAMPI_VECCHI:
        c = tipo[6:]
        v = x.get(c, "").strip()
        campi = {c: None}
        if v and norm(v) != norm(nome) and not x.get("forma_estesa", "").strip():
            campi["forma_estesa"] = v
        return modifica_sezione(f_entita, nome, campi)
    raise ValueError(f"Correzione sconosciuta: «{tipo}»")


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
            elif campo == "nome_completo":
                out.append(("avviso", s, "campo nome_completo: il nome per esteso va in forma_estesa (o via, se "
                                         "ripete il nome della scheda)"))
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
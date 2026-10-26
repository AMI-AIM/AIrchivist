#!/usr/bin/env python3
"""
Punto d'ingresso della skill ricerca-fonti nelle chat degli assistenti (claude.ai, ChatGPT, Claude Code e simili):
un corpus piccolo caricato nella conversazione, anche in .zip, o una cartella di file sul computer diventa un
progetto temporaneo del motore. Le schede delle entità e i profili delle serie si creano qui; i passaggi li legge
l'assistente (sessione.py), senza archivio delle letture.

Uso (dalla cartella del motore):
  python chat.py ambiente                       dove si trova la skill: sistema completo sul computer, file caricati
                                                nella conversazione o nessuna fonte; lettori di PDF e OCR presenti
  python chat.py apri [file o cartelle ...]     crea il progetto (se non c'è), estrae gli zip, mette nelle fonti i
                                                .txt con intestazione [SERIES: ...], copia entita.ini, serie.ini e
                                                audit_fonti/*.csv, elenca il resto da importare, costruisce l'indice
                                                (senza argomenti: i file caricati nella conversazione, nelle
                                                cartelle di CARICATI)
  python chat.py stato
  python chat.py serie                          profili delle serie
  python chat.py serie-crea "Nome" --tipo periodico|volume --lingua it --cartella riviste/nome
                     --citazione "..." [--sigla XX] [--nota-limiti "..."] [--campo chiave=valore ...]
  python chat.py importa <file o cartella> --serie "Nome" [opzioni di importa.py]
  python chat.py schede [filtro]
  python chat.py esplora "Nome" [--indizi "Italia; PCI"] [--candidate "贝林格; 伯林格"] [--dal AAAA --al AAAA]
  python chat.py cerca "testo" [--massimo 8]
  python chat.py scheda-crea "Nome" --varianti "forma; forma" [--descrizione "..."] [--ambigue "..."]
                     [--contesto "..."] [--tipo persona|organizzazione|...] [--forma-estesa "..."]
  python chat.py prepara "Nome" [--dal AAAA] [--al AAAA] [--fonti "..."] [--cartella prova_x] [--lotto 10]
  python chat.py registra <cartella> <letture.json> [--da "modello"]
  python chat.py documenti <cartella>
  python chat.py sintesi <cartella> --domanda "..." [--sintesi-da <file.json>]
  python chat.py consegna <cartella>            copia risposta, schede e serie nella cartella di consegna
                                                (claude.ai: /mnt/user-data/outputs; ChatGPT: /mnt/data/consegna;
                                                altrove: consegna dentro il progetto)

Il progetto sta in AIRCHIVIST_PROGETTO, altrimenti in ~/airchivist_progetto (progetto temporaneo, senza archivio
delle letture). Nel motore di un'installazione completa (accanto c'è mcp_server.py), senza AIRCHIVIST_PROGETTO,
il progetto è quello in uso (config.ini, [progetto] cartella) e le letture vanno nell'archivio unico; lì apri,
importa, serie-crea e consegna non si usano: fonti e serie si aggiungono con gli strumenti del sistema.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARTELLA))
SISTEMA = (CARTELLA / "mcp_server.py").is_file()     # questo è il motore di un'installazione completa
if not SISTEMA:
    os.environ.setdefault("AIRCHIVIST_PROGETTO", str(Path.home() / "airchivist_progetto"))
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
SEGNO_TEMPORANEO = ".progetto_chat"     # file che chat.py apri lascia nei progetti temporanei che crea
# file caricati nella conversazione: chat di Claude (uploads, attachments); ChatGPT (/mnt/data: posizione non
# documentata da OpenAI, da verificare con le prove)
CARICATI = [Path("/mnt/user-data/uploads"), Path("/mnt/user-data/attachments"), Path("/mnt/data")]
ALLEGATO = re.compile(r"^[0-9a-f]{8}-")     # prefisso che la chat di Claude aggiunge ai nomi degli allegati
NON_FONTI = {"consegna"}                    # sottocartelle dei caricati scritte dalla skill stessa
DOCUMENTI = {".pdf", ".txt", ".xml", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}
NOMI_PROGETTO = {"entita.ini", "serie.ini", "istruzioni.md"}
AVVISO_DIMENSIONE = 60_000_000          # oltre circa 60 MB di testo la lettura in chat diventa troppo lunga


def stampa(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def cfg():
    from llm import leggi_config
    return leggi_config()


def percorso(k):
    from llm import percorso as p
    return p(cfg(), k)


def radice():
    """Cartella del progetto: quella di AIRCHIVIST_PROGETTO o, nel sistema completo, quella in uso."""
    if os.environ.get("AIRCHIVIST_PROGETTO", "").strip():
        return Path(os.environ["AIRCHIVIST_PROGETTO"])
    from progetto import cartella_scelta
    return cartella_scelta(cfg()) or CARTELLA.parent


def temporaneo():
    """True per i progetti della chat (fuori dal sistema completo, o creati da chat.py apri in una cartella
    scelta con AIRCHIVIST_PROGETTO): niente archivio unico, e fonti e serie si aggiungono da qui."""
    if not SISTEMA:
        return True
    if not os.environ.get("AIRCHIVIST_PROGETTO", "").strip():
        return False
    r = radice()
    return (r / SEGNO_TEMPORANEO).exists() or not (r / "progetto.ini").exists()


def solo_temporaneo(comando):
    if not temporaneo():
        sys.exit(f"«{comando}» non si usa sul progetto del sistema completo ({radice()}): fonti e serie si "
                 "aggiungono con gli strumenti del sistema (importa.py, vedi pipeline/ISTRUZIONI.md).")


def motore(script, *argomenti):
    """Esegue uno script del motore con il progetto della chat; esce con il suo codice se fallisce."""
    r = subprocess.run([sys.executable, str(CARTELLA / script), *map(str, argomenti)], cwd=CARTELLA)
    if r.returncode:
        sys.exit(r.returncode)


def intestato(f):
    """True se il .txt ha già l'intestazione del motore ([SERIES: ...] nelle prime righe)."""
    try:
        with open(f, encoding="utf-8", errors="replace") as h:
            return any(r.startswith("[SERIES:") for r in (h.readline() for _ in range(30)))
    except OSError:
        return False


def relativo_nelle_fonti(rel):
    """Percorso dentro data: toglie un «data/» iniziale (zip di una cartella di progetto) e la radice dello zip."""
    parti = list(Path(rel).parts)
    if "data" in parti:
        parti = parti[parti.index("data") + 1:]
    return Path(*parti) if parti else Path(rel).name


def cartella_consegna():
    """Dove lasciare i file per l'utente: la cartella che la chat offre per scaricarli, altrimenti il progetto."""
    if Path("/mnt/user-data").is_dir():
        return Path("/mnt/user-data/outputs")
    if Path("/mnt/data").is_dir():
        return Path("/mnt/data/consegna")
    return radice() / "consegna"


def sistema_completo(partenza=None):
    """Cartella del motore di un'installazione completa di AIrchivist (con config.ini e server MCP), cercata in
    AIRCHIVIST_MOTORE e poi nella cartella di lavoro e in quelle sopra; None se non c'è. Il motore copiato
    dentro la skill non conta: non ha il server MCP."""
    candidate = [Path(os.environ["AIRCHIVIST_MOTORE"])] if os.environ.get("AIRCHIVIST_MOTORE") else []
    qui = Path(partenza or Path.cwd()).resolve()
    for d in (qui, *qui.parents):
        candidate += [d, d / "pipeline"]
    for c in candidate:
        if (c / "mcp_server.py").is_file() and (c / "sessione.py").is_file() and (c / "config.ini").is_file():
            return c.resolve()
    return None


def file_caricati():
    """{cartella dei caricati: numero di file} per le cartelle presenti e non vuote."""
    out = {}
    for c in CARICATI:
        if c.is_dir():
            n = sum(1 for f in c.rglob("*") if f.is_file() and not NON_FONTI & set(f.relative_to(c).parts[:1]))
            if n:
                out[str(c)] = n
    return out


def lettori():
    """Lettore dei PDF e OCR disponibili in questo ambiente."""
    pdf = "nessuno"
    for modulo, nome in (("pymupdf", "PyMuPDF"), ("fitz", "PyMuPDF"), ("pypdf", "pypdf")):
        try:
            __import__(modulo)
            pdf = nome
            break
        except ImportError:
            continue
    try:
        from importa import cerca_tesseract
        ocr = bool(cerca_tesseract(cfg()))
    except Exception:
        ocr = False
    return {"pdf": pdf, "ocr": ocr}


def ambiente(args):
    motore_completo = sistema_completo()
    caricati = file_caricati()
    out = {"modo": "sistema" if motore_completo else "conversazione" if caricati else "nessuna_fonte"}
    if motore_completo:
        out["motore"] = str(motore_completo)
    out["caricati"] = caricati
    out["progetto"] = str(radice()) if (radice() / "progetto.ini").exists() or not temporaneo() else None
    out["temporaneo"] = temporaneo()
    out.update(lettori())
    if temporaneo():
        out["consegna"] = str(cartella_consegna())
    stampa(out)


def crea_progetto():
    r = radice()
    if (r / "progetto.ini").exists():
        return False
    import progetto
    from contextlib import redirect_stdout
    import io
    with redirect_stdout(io.StringIO()):
        progetto.cmd_nuovo(argparse.Namespace(cartella=str(r), nome="Corpus caricato nella chat",
                                              descrizione=""))
    (r / "istruzioni.md").unlink(missing_ok=True)
    (r / SEGNO_TEMPORANEO).write_text("Progetto temporaneo creato da chat.py apri: niente archivio unico.\n",
                                      encoding="utf-8")
    return True


# ---------------------------------------------------------------- comandi
def apri(args):
    solo_temporaneo("apri")
    nuovo = crea_progetto()
    dati = percorso("dati")
    sorgenti = [Path(x) for x in args.file] or [c for c in CARICATI if c.is_dir()]
    if not sorgenti:
        sys.exit("Nessun file indicato e nessuna cartella dei file caricati "
                 f"({', '.join(c.as_posix() for c in CARICATI)}).")
    lavoro = radice() / "_caricati"
    lavoro.mkdir(exist_ok=True)
    elementi = []                                      # (file, percorso relativo da conservare)
    for s in sorgenti:
        if s.is_dir() and s.name == "attachments":
            # allegati della chat: attachments/<conversazione>/<prefisso>-<nome>; conta solo il nome
            elementi += [(f, Path(ALLEGATO.sub("", f.name))) for f in sorted(s.rglob("*")) if f.is_file()]
        elif s.is_dir():
            elementi += [(f, f.relative_to(s)) for f in sorted(s.rglob("*"))
                         if f.is_file() and not (s in CARICATI and NON_FONTI & set(f.relative_to(s).parts[:1]))]
        elif s.is_file():
            elementi.append((s, Path(s.name)))
        else:
            print(f"Non trovo {s}", file=sys.stderr)
    esito = {"progetto": str(radice()), "creato_ora": nuovo, "fonti_aggiunte": 0, "da_importare": [],
             "file_di_progetto": [], "ignorati": []}
    da_vedere = []
    for f, rel in elementi:
        if f.suffix.lower() == ".zip":
            dest = lavoro / f.stem
            with zipfile.ZipFile(f) as z:
                # le esportazioni PAGE/ALTO in zip sono un documento: si importano intere
                if any(n.lower().endswith(".xml") for n in z.namelist()) and \
                        not any(n.lower().endswith(".txt") for n in z.namelist()):
                    esito["da_importare"].append(str(f))
                    continue
                for n in z.namelist():
                    p = Path(n)
                    if n.endswith("/") or ".." in p.parts or p.is_absolute():
                        continue
                    z.extract(n, dest)
            da_vedere += [(x, x.relative_to(dest)) for x in sorted(dest.rglob("*")) if x.is_file()]
        else:
            da_vedere.append((f, rel))
    for f, rel in da_vedere:
        nome = f.name.lower()
        if nome in NOMI_PROGETTO or (f.suffix.lower() == ".csv" and f.parent.name == "audit_fonti"):
            dest = radice() / ("audit_fonti" if f.suffix.lower() == ".csv" else "") / f.name
            if nome in ("entita.ini", "serie.ini") and dest.exists() and dest.read_text(encoding="utf-8").strip() \
                    and not nuovo and dest.read_bytes() != f.read_bytes():
                esito["file_di_progetto"].append(f"{f.name}: non sostituito (il progetto ne ha già uno)")
                continue
            shutil.copyfile(f, dest)
            esito["file_di_progetto"].append(f.name)
        elif f.suffix.lower() == ".txt" and intestato(f):
            dest = dati / relativo_nelle_fonti(rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(f, dest)
            esito["fonti_aggiunte"] += 1
        elif f.suffix.lower() in DOCUMENTI:
            esito["da_importare"].append(str(f))
        elif not nome.startswith(".") and nome != "progetto.ini":
            esito["ignorati"].append(str(rel))
    if esito["fonti_aggiunte"]:
        import profili
        profili.tutti(ricarica=True)
    esito.update(riepilogo())
    stampa(esito)


def riepilogo():
    """Fonti, serie trovate nelle intestazioni e serie senza profilo; aggiorna l'indice."""
    import profili
    from estrai_occorrenze import leggi_intestazione
    dati = percorso("dati")
    file = sorted(dati.rglob("*.txt")) if dati.is_dir() else []
    per_serie, senza_profilo, dimensione = {}, {}, 0
    profili.tutti(ricarica=True)
    for f in file:
        dimensione += f.stat().st_size
        meta, _ = leggi_intestazione(f.read_text(encoding="utf-8", errors="replace")[:6000])
        s = meta.get("SERIES", "").strip() or "(senza serie)"
        per_serie[s] = per_serie.get(s, 0) + 1
        rel = f.relative_to(dati).as_posix()
        if not profili.nome_di(s, rel):
            senza_profilo.setdefault(s, str(f.parent.relative_to(dati).as_posix()))
    out = {"fonti": len(file), "megabyte": round(dimensione / 1e6, 1), "serie": per_serie,
           "serie_senza_profilo": senza_profilo}
    if dimensione > AVVISO_DIMENSIONE and temporaneo():
        out["avviso"] = ("Corpus grande per una chat: la skill è pensata per corpus piccoli. Restringi la ricerca "
                         "(--dal, --al, --fonti) o usa la pipeline locale.")
    if file:
        import indice
        ind = indice.Indice(indice.percorso_indice(cfg()), dati)
        from contextlib import redirect_stdout
        import io
        with redirect_stdout(io.StringIO()):
            (ind.aggiorna if ind.pronto() else ind.costruisci)()
        out["indice"] = "pronto"
    return out


def stato(args):
    if temporaneo() and not (radice() / "progetto.ini").exists():
        sys.exit("Nessun progetto: prima python chat.py apri")
    out = {"progetto": str(radice()), "temporaneo": temporaneo(), **riepilogo(),
           "schede": __import__("schede").leggi_schede(percorso("entita")).sections()}
    ris = percorso("risultati")
    out["ricerche"] = sorted(d.name for d in ris.iterdir() if d.is_dir() and not d.name.startswith("_")) \
        if ris.is_dir() else []
    stampa(out)


def serie(args):
    import importa
    cp = importa.leggi_serie()
    stampa({s: dict(cp[s]) for s in cp.sections()})


def serie_crea(args):
    solo_temporaneo("serie-crea")
    import importa
    extra = {}
    for c in args.campo or []:
        k, _, v = c.partition("=")
        if not k.strip() or not v.strip():
            sys.exit(f"--campo vuole chiave=valore, non «{c}»")
        extra[k.strip()] = v.strip()
    msg = importa.aggiungi_serie(args.nome.strip(), args.tipo, args.lingua.lower(), args.cartella, args.citazione,
                                 args.sigla or "", args.nota_limiti or "", **extra)
    print(msg)
    if not msg.startswith("Serie"):
        sys.exit(1)


def importa_(args, resto):
    solo_temporaneo("importa")
    import importa
    codice = importa.main(["importa", args.percorso, "--serie", args.serie, *resto])
    if codice:
        sys.exit(codice)
    stampa(riepilogo())


def schede_(args):
    import schede
    cp = schede.leggi_schede(percorso("entita"))
    f = (args.filtro or "").lower()
    stampa({s: dict(cp[s]) for s in cp.sections() if not f or f in s.lower()
            or f in cp.get(s, "varianti", fallback="").lower()})


def indice_pronto():
    import indice
    ind = indice.Indice(indice.percorso_indice(cfg()), percorso("dati"))
    if not ind.pronto():
        sys.exit("Indice non pronto: prima python chat.py apri")
    return ind


def lista(s):
    return [x.strip() for x in (s or "").replace("；", ";").split(";") if x.strip()]


def esplora_(args):
    import esplora
    stampa(esplora.esplora_nome(indice_pronto(), percorso("dati"), args.nome, lista(args.indizi),
                                lista(args.candidate), args.dal, args.al))


def cerca(args):
    import esplora
    stampa(esplora.cerca_testo(indice_pronto(), percorso("dati"), args.testo, args.dal, args.al,
                               lista(args.fonti) or None, args.massimo, 0))


def scheda_crea(args):
    import schede
    f = percorso("entita")
    if args.nome in schede.leggi_schede(f).sections():
        sys.exit(f"La scheda «{args.nome}» c'è già.")
    varianti = lista(args.varianti) or [args.nome]
    ambigue = lista(args.ambigue)
    nome = schede.aggiungi_scheda(f, args.nome, varianti, args.descrizione or "", lista(args.contesto) or None,
                                  ambigue or None, None, args.tipo or "", args.forma_estesa or "")
    out = {"scheda": nome}
    non_cercate = schede.ambigue_non_cercate(varianti, ambigue)
    if non_cercate:
        out["avviso"] = ("Forme ambigue che non sono tra le varianti e quindi non verranno cercate: "
                         + "; ".join(non_cercate))
    stampa(out)


def prepara(args):
    extra = [x for k, v in (("--dal", args.dal), ("--al", args.al), ("--fonti", args.fonti),
                             ("--cartella", args.cartella)) if v for x in (k, v)]
    archivio = ["--senza-archivio"] if temporaneo() else []
    motore("sessione.py", "prepara", args.nome, *archivio, "--lotto", args.lotto, *extra)


def sintesi_(args):
    cart = cartella(args.cartella)
    extra = ["--sintesi-da", args.sintesi_da] if args.sintesi_da else ["--senza-modello"]
    motore("sintesi.py", cart, cart / "entita_ricerca.ini", "--domanda", args.domanda or "", *extra)


def cartella(nome):
    p = Path(nome)
    return p if p.is_absolute() or p.exists() else percorso("risultati") / nome


def consegna(args):
    solo_temporaneo("consegna")
    cart = cartella(args.cartella)
    dest = Path(args.dest) if args.dest else cartella_consegna()
    dest.mkdir(parents=True, exist_ok=True)
    copiati = []
    for f, nome in ((cart / "risposta.md", f"risposta_{cart.name}.md"), (percorso("entita"), "entita.ini"),
                    (percorso("serie"), "serie.ini")):
        if f.exists():
            shutil.copyfile(f, dest / nome)
            copiati.append(str(dest / nome))
    stampa({"consegnati": copiati})


def main():
    for flusso in (sys.stdout, sys.stderr):
        try:
            flusso.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="comando", required=True)
    sub.add_parser("ambiente")
    a = sub.add_parser("apri")
    a.add_argument("file", nargs="*")
    sub.add_parser("stato")
    sub.add_parser("serie")
    a = sub.add_parser("serie-crea")
    a.add_argument("nome")
    for k in ("tipo", "lingua", "cartella", "citazione"):
        a.add_argument(f"--{k}", required=True)
    a.add_argument("--sigla")
    a.add_argument("--nota-limiti")
    a.add_argument("--campo", action="append", help="altro campo del profilo, chiave=valore (es. chicago=...)")
    a = sub.add_parser("importa")
    a.add_argument("percorso")
    a.add_argument("--serie", required=True)
    a = sub.add_parser("schede")
    a.add_argument("filtro", nargs="?")
    a = sub.add_parser("esplora")
    a.add_argument("nome")
    a.add_argument("--indizi")
    a.add_argument("--candidate")
    a.add_argument("--dal", type=int)
    a.add_argument("--al", type=int)
    a = sub.add_parser("cerca")
    a.add_argument("testo")
    a.add_argument("--dal", type=int)
    a.add_argument("--al", type=int)
    a.add_argument("--fonti")
    a.add_argument("--massimo", type=int, default=8)
    a = sub.add_parser("scheda-crea")
    a.add_argument("nome")
    a.add_argument("--varianti", required=True)
    for k in ("descrizione", "ambigue", "contesto", "tipo", "forma-estesa"):
        a.add_argument(f"--{k}")
    a = sub.add_parser("prepara")
    a.add_argument("nome")
    a.add_argument("--dal")
    a.add_argument("--al")
    a.add_argument("--fonti")
    a.add_argument("--cartella", help="cartella dei risultati (prova_...: senza archivio unico)")
    a.add_argument("--lotto", default="10")
    a = sub.add_parser("registra")
    a.add_argument("cartella")
    a.add_argument("letture")
    a.add_argument("--da", default="assistente della chat")
    sub.add_parser("documenti").add_argument("cartella")
    a = sub.add_parser("sintesi")
    a.add_argument("cartella")
    a.add_argument("--domanda", default="")
    a.add_argument("--sintesi-da")
    a = sub.add_parser("consegna")
    a.add_argument("cartella")
    a.add_argument("--dest")
    args, resto = ap.parse_known_args()
    if resto and args.comando != "importa":
        ap.error(f"argomenti non riconosciuti: {' '.join(resto)}")
    if args.comando == "registra":
        motore("sessione.py", "registra", cartella(args.cartella), args.letture, "--da", args.da)
    elif args.comando == "documenti":
        motore("sessione.py", "documenti", cartella(args.cartella))
    elif args.comando == "importa":
        importa_(args, resto)
    else:
        {"ambiente": ambiente, "apri": apri, "stato": stato, "serie": serie, "serie-crea": serie_crea, "schede": schede_,
         "esplora": esplora_, "cerca": cerca, "scheda-crea": scheda_crea, "prepara": prepara,
         "sintesi": sintesi_, "consegna": consegna}[args.comando](args)


if __name__ == "__main__":
    main()

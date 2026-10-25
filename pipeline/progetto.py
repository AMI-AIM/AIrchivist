#!/usr/bin/env python3
"""
Progetti di ricerca separati dal motore (lavoro 13, fase 4).

Il motore è la cartella pipeline con config.ini (modelli, router, parametri). I dati di una ricerca stanno in una
cartella di progetto:

  <progetto>/
    progetto.ini            nome del progetto ed eventuali impostazioni proprie (vedi sotto)
    entita.ini              schede delle entità
    serie.ini               profili delle serie
    istruzioni.md           regole proprie del progetto per l'IA della chat (le invia il server MCP)
    data/                   le fonti
    audit_fonti/            registro_modifiche.csv, problemi_residui.csv
    indice/fonti.sqlite     indice delle fonti
    risultati/, risposte/, lavori/, importazioni/, _backup/

Quale progetto: la variabile d'ambiente AIRCHIVIST_PROGETTO, altrimenti config.ini, sezione [progetto], voce
«cartella» (relativa alla cartella pipeline o assoluta). Con un progetto scelto, i percorsi della sezione [percorsi]
di config.ini non valgono: contano quelli predefiniti dentro la cartella del progetto e quelli di progetto.ini
(relativi alla cartella del progetto). Senza progetto scelto vale la disposizione storica: [percorsi] di config.ini
relativi a pipeline, entita.ini e serie.ini in pipeline, indice/lavori/risposte accanto a risultati, importazioni
accanto a data.

progetto.ini può contenere [progetto] nome, descrizione; [percorsi] per spostare qualcosa (es. entita =
pipeline/entita.ini); e qualsiasi altra sezione di config.ini da cambiare solo per questo progetto (es.
[estrazione] finestra = 300).

Uso (nella cartella pipeline):
  python progetto.py stato                     progetto in uso e dove stanno i suoi file
  python progetto.py nuovo <cartella> --nome "Stampa albanese 1960-1978"   crea un progetto vuoto
"""
import argparse
import configparser
import datetime as dt
import os
import sys
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
VARIABILE = "AIRCHIVIST_PROGETTO"
# percorsi di progetto e loro posizione predefinita dentro la cartella del progetto
PERCORSI = {
    "dati": "data",
    "risultati": "risultati",
    "entita": "entita.ini",
    "serie": "serie.ini",
    "problemi": "audit_fonti/problemi_residui.csv",
    "registro_modifiche": "audit_fonti/registro_modifiche.csv",
    "indice": "indice/fonti.sqlite",
    "risposte": "risposte",
    "lavori": "lavori",
    "importazioni": "importazioni",
    "backup": "_backup",
    "istruzioni": "istruzioni.md",     # regole proprie del progetto per l'IA della chat (server MCP)
}


def _assoluto(valore, base):
    p = Path(valore)
    return p if p.is_absolute() else (base / p).resolve()


def cartella_scelta(cfg):
    """Cartella del progetto scelto (variabile d'ambiente o config.ini [progetto] cartella); None se nessuno."""
    v = os.environ.get(VARIABILE, "").strip() or (cfg.get("progetto", "cartella", fallback="") or "").strip()
    return _assoluto(v, CARTELLA) if v else None


def leggi_config(path=None):
    """config.ini del motore, più progetto.ini del progetto scelto (le sue voci prevalgono; i suoi percorsi,
    relativi alla cartella del progetto, diventano assoluti)."""
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#",))
    cp.read(path or CARTELLA / "config.ini", encoding="utf-8")
    radice = cartella_scelta(cp)
    if radice is None:
        return cp
    if cp.has_section("percorsi"):
        cp.remove_section("percorsi")      # con un progetto scelto contano solo i suoi percorsi
    f = radice / "progetto.ini"
    if f.exists():
        prog = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#",))
        prog.read(f, encoding="utf-8")
        for sezione in prog.sections():
            if not cp.has_section(sezione):
                cp.add_section(sezione)
            for k, v in prog[sezione].items():
                cp[sezione][k] = str(_assoluto(v, radice)) if sezione == "percorsi" else v
    if not cp.has_section("progetto"):
        cp.add_section("progetto")
    cp["progetto"]["cartella"] = str(radice)
    return cp


def percorso(cfg, chiave):
    """Percorso di un file o di una cartella del progetto (chiavi in PERCORSI)."""
    v = cfg.get("percorsi", chiave, fallback="")
    if v:
        return _assoluto(v, CARTELLA)
    radice = cartella_scelta(cfg)
    if radice is not None:
        if chiave not in PERCORSI:
            raise configparser.NoOptionError(chiave, "percorsi")
        return (radice / PERCORSI[chiave]).resolve()
    # disposizione storica (nessun progetto scelto)
    storici = {"dati": CARTELLA.parent / "data", "risultati": CARTELLA.parent / "risultati",
               "entita": CARTELLA / "entita.ini", "serie": CARTELLA / "serie.ini",
               "problemi": CARTELLA.parent / "audit_fonti" / "problemi_residui.csv",
               "registro_modifiche": CARTELLA.parent / "audit_fonti" / "registro_modifiche.csv",
               "backup": CARTELLA / "_backup", "istruzioni": CARTELLA.parent / "istruzioni.md"}
    if chiave in storici:
        return storici[chiave].resolve()
    if chiave in ("indice", "lavori", "risposte"):
        sopra = percorso(cfg, "risultati").parent
        return (sopra / "indice" / "fonti.sqlite" if chiave == "indice" else sopra / chiave).resolve()
    if chiave == "importazioni":
        return (percorso(cfg, "dati").parent / "importazioni").resolve()
    raise configparser.NoOptionError(chiave, "percorsi")


def percorsi_assoluti(cfg):
    """{chiave: percorso assoluto} per tutte le chiavi: per le configurazioni temporanee delle prove, che così
    non dipendono da dove stanno né dal progetto scelto."""
    return {k: str(percorso(cfg, k)) for k in PERCORSI}


def nome(cfg):
    return cfg.get("progetto", "nome", fallback="") or (cartella_scelta(cfg) or CARTELLA.parent).name


# ---------------------------------------------------------------- comandi
INTESTAZIONE_CSV = {
    "registro_modifiche": "file,campo,valore_precedente,valore_nuovo,motivo",
    "problemi": "serie,file,problema,dettaglio",
}
ENTITA_VUOTO = """# Schede delle entità del progetto: una sezione per entità.
# Campi: varianti (forme del nome, separate da ;), tipo, forma_estesa, contesto, forme_ambigue, collegate, note.
# Le schede si creano anche dalla chat (esplora_nome, poi schede con azione crea). Regole: docs/schede_entita.md.
"""


ISTRUZIONI_VUOTO = """# Regole proprie di questo progetto per l'IA della chat

Il server MCP le aggiunge alle regole generali e all'elenco delle fonti (ricavato da serie.ini). Scrivi qui solo
ciò che vale per questa ricerca: argomento e taglio, carattere delle fonti, convenzioni sui nomi e sulle cariche,
esempi di citazione. Le righe che iniziano con «#» non vengono inviate.
"""


def serie_vuoto():
    """serie.ini di un progetto nuovo: la descrizione dei campi presa dal serie.ini del motore, senza serie."""
    f = CARTELLA / "serie.ini"
    righe = []
    if f.exists():
        for r in f.read_text(encoding="utf-8").splitlines():
            if r.startswith("[") or (r and not r.startswith("#")):
                break
            righe.append(r)
    return "\n".join(righe).rstrip() + "\n\n# Nessuna serie: aggiungile copiando l'esempio o chiedendo in Jan («crea la serie ...»).\n"


def cmd_nuovo(args):
    radice = Path(args.cartella).resolve()
    if radice.exists() and any(radice.iterdir()):
        sys.exit(f"La cartella {radice} esiste e non è vuota: per sicurezza non creo un progetto lì.")
    for k in ("dati", "risultati", "risposte", "lavori", "importazioni"):
        (radice / PERCORSI[k]).mkdir(parents=True, exist_ok=True)
    (radice / "risultati" / "_archivio").mkdir(parents=True, exist_ok=True)
    (radice / "audit_fonti").mkdir(parents=True, exist_ok=True)
    for k, testa in INTESTAZIONE_CSV.items():          # CSV con BOM UTF-8 e CRLF, come quelli del corpus
        (radice / PERCORSI[k]).write_bytes(("﻿" + testa + "\r\n").encode("utf-8"))
    (radice / "entita.ini").write_text(ENTITA_VUOTO, encoding="utf-8")
    (radice / "istruzioni.md").write_text(ISTRUZIONI_VUOTO, encoding="utf-8")
    (radice / "serie.ini").write_text(serie_vuoto(), encoding="utf-8")
    (radice / "progetto.ini").write_text(
        f"[progetto]\nnome = {args.nome or radice.name}\ndescrizione = {args.descrizione or ''}\n"
        f"creato_il = {dt.date.today().isoformat()}\n", encoding="utf-8")
    print(f"Progetto creato in {radice}.\nPer usarlo: in config.ini, sezione [progetto], cartella = {radice}\n"
          f"oppure, solo per una finestra del Prompt dei comandi: set {VARIABILE}={radice}\n"
          f"Poi: aggiungi le serie in serie.ini, importa le fonti (importa.py) e costruisci l'indice "
          f"(python indice.py costruisci).")


def cmd_stato(args):
    cfg = leggi_config()
    radice = cartella_scelta(cfg)
    origine = (f"variabile d'ambiente {VARIABILE}" if os.environ.get(VARIABILE, "").strip() else
               "config.ini, [progetto] cartella") if radice else "nessun progetto scelto: disposizione storica"
    print(f"Progetto: {nome(cfg)} ({radice or CARTELLA.parent}) — {origine}")
    for k in PERCORSI:
        p = percorso(cfg, k)
        print(f"  {k:19} {'  ' if p.exists() else '! '}{p}")
    print("(! = non esiste ancora)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="comando", required=True)
    sub.add_parser("stato")
    n = sub.add_parser("nuovo")
    n.add_argument("cartella")
    n.add_argument("--nome", default="")
    n.add_argument("--descrizione", default="")
    args = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    {"stato": cmd_stato, "nuovo": cmd_nuovo}[args.comando](args)


if __name__ == "__main__":
    main()

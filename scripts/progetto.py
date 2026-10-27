#!/usr/bin/env python3
"""
Progetti di ricerca separati dal motore (lavoro 13, fase 4).

Il motore è la cartella scripts con config.ini (modelli, router, parametri). I dati di una ricerca stanno in una
cartella di progetto (di solito in projects/, accanto al motore e fuori da git):

  <progetto>/
    project.ini             nome del progetto ed eventuali impostazioni proprie (vedi sotto)
    glossary/               entities.ini (schede delle entità), series.ini (profili delle serie), instructions.md
                            (regole proprie del progetto per l'IA della chat, le invia il server MCP)
    sources/                documenti originali caricati, immutabili
    data/                   documenti processati (.txt con intestazione)
    audit/                  changes.csv, open_issues.csv, imports.csv, checks/ (controlli delle importazioni)
    results/                archive/ (archivio unico delle letture), searches/ (una cartella per ricerca), answers/,
                            references/, past_sessions/, trials/, evaluation/
    system/                 index/sources.sqlite, jobs/, import_jobs/, cache/, backups/ (rigenerabili o temporanei)

Quale progetto: la variabile d'ambiente AIRCHIVIST_PROGETTO, altrimenti config.ini, sezione [progetto], voce
«cartella» (relativa alla cartella scripts o assoluta). Con un progetto scelto, i percorsi della sezione [percorsi]
di config.ini non valgono: contano quelli predefiniti dentro la cartella del progetto e quelli di project.ini
(relativi alla cartella del progetto). Senza progetto scelto valgono solo i percorsi scritti in [percorsi] (le
configurazioni temporanee delle prove); per gli altri il motore chiede di scegliere o di creare un progetto.

project.ini può contenere [progetto] nome, descrizione; [percorsi] per spostare qualcosa (es. entita =
schede/entities.ini); e qualsiasi altra sezione di config.ini da cambiare solo per questo progetto (es.
[estrazione] finestra = 300).

Uso (nella cartella scripts):
  python progetto.py stato                     progetto in uso e dove stanno i suoi file
  python progetto.py nuovo <cartella> --nome "Stampa albanese 1960-1978"   crea un progetto vuoto
"""
import argparse
import configparser
import datetime as dt
import os
import re
import sys
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
VARIABILE = "AIRCHIVIST_PROGETTO"
# percorsi di progetto e loro posizione predefinita dentro la cartella del progetto
PERCORSI = {
    "dati": "data",
    "originali": "sources",
    "risultati": "results",
    "entita": "glossary/entities.ini",
    "serie": "glossary/series.ini",
    "istruzioni": "glossary/instructions.md",     # regole proprie del progetto per l'IA della chat (server MCP)
    "problemi": "audit/open_issues.csv",
    "registro_modifiche": "audit/changes.csv",
    "registro_importazioni": "audit/imports.csv",
    "importazioni": "audit/checks",
    "risposte": "results/answers",
    "indice": "system/index/sources.sqlite",
    "lavori": "system/jobs",
    "lavori_importazioni": "system/import_jobs",
    "cache": "system/cache",
    "backup": "system/backups",
    "cambi_modello": "system/model_changes.csv",   # cambi di profilo di modello (installa.py modello usa)
}
# sottocartelle di results/: ricerche, archivio unico, letture di riferimento, sessioni con Claude, prove, valutazione
RICERCHE, ARCHIVIO, RIFERIMENTI, SESSIONI, PROVE, VALUTAZIONE = (
    "searches", "archive", "references", "past_sessions", "trials", "evaluation")
NESSUN_PROGETTO = ("Nessun progetto di ricerca scelto: indicalo in config.ini, sezione [progetto], voce cartella "
                   f"(o con la variabile d'ambiente {VARIABILE}), oppure creane uno con "
                   "python progetto.py nuovo <cartella> --nome \"...\"")


class NessunProgetto(RuntimeError):
    """Un percorso di progetto chiesto senza progetto scelto e senza [percorsi] che lo indichi."""


def _assoluto(valore, base):
    p = Path(valore)
    return p if p.is_absolute() else (base / p).resolve()


def cartella_scelta(cfg):
    """Cartella del progetto scelto (variabile d'ambiente o config.ini [progetto] cartella); None se nessuno."""
    v = os.environ.get(VARIABILE, "").strip() or (cfg.get("progetto", "cartella", fallback="") or "").strip()
    return _assoluto(v, CARTELLA) if v else None


def leggi_config(path=None):
    """config.ini del motore, più project.ini del progetto scelto (le sue voci prevalgono; i suoi percorsi,
    relativi alla cartella del progetto, diventano assoluti)."""
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#",))
    cp.read(path or CARTELLA / "config.ini", encoding="utf-8")
    radice = cartella_scelta(cp)
    if radice is None:
        return cp
    if cp.has_section("percorsi"):
        cp.remove_section("percorsi")      # con un progetto scelto contano solo i suoi percorsi
    f = radice / "project.ini"
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
    if chiave not in PERCORSI:
        raise configparser.NoOptionError(chiave, "percorsi")
    radice = cartella_scelta(cfg)
    if radice is None:
        raise NessunProgetto(NESSUN_PROGETTO)
    return (radice / PERCORSI[chiave]).resolve()


def cartella_ricerche(cfg):
    """Cartella delle ricerche, una sottocartella per ricerca (results/searches)."""
    return percorso(cfg, "risultati") / RICERCHE


def percorsi_assoluti(cfg):
    """{chiave: percorso assoluto} per tutte le chiavi: per le configurazioni temporanee delle prove, che così
    non dipendono da dove stanno né dal progetto scelto."""
    return {k: str(percorso(cfg, k)) for k in PERCORSI}


def nome(cfg):
    radice = cartella_scelta(cfg)
    return cfg.get("progetto", "nome", fallback="") or (radice.name if radice else "nessun progetto")


# ---------------------------------------------------------------- comandi
INTESTAZIONE_CSV = {
    "registro_modifiche": "file,campo,valore_precedente,valore_nuovo,motivo",
    "problemi": "serie,file,problema,dettaglio",
}
ENTITA_VUOTO = """# Schede delle entità del progetto: una sezione per entità.
# Campi: varianti (forme del nome, separate da ;), tipo, forma_estesa, contesto, forme_ambigue, collegate, note.
# Le schede si creano anche dalla chat (esplora_nome, poi schede con azione crea). Regole: docs/schede_entita.md.
"""


# tutte righe con «#»: finché non le scrivi, nessuna regola di progetto arriva alla chat (25/10/2026: la
# spiegazione senza «#» veniva inviata come regola)
ISTRUZIONI_VUOTO = """# Regole proprie di questo progetto per l'IA della chat
#
# Il server MCP le aggiunge alle regole generali e all'elenco delle fonti (ricavato da series.ini). Scrivi qui solo
# ciò che vale per questa ricerca: argomento e taglio, carattere delle fonti (primarie o studi, propaganda),
# convenzioni sui nomi e sulle cariche, esempi di citazione. Le righe che iniziano con «#» non vengono inviate.
#
# Esempio:
# Le fonti sono di due tipi: la stampa e le pubblicazioni ufficiali albanesi (fonti primarie, propagandistiche) e
# gli studi (fonti secondarie). Nelle risposte distingui sempre gli uni dagli altri.
"""


def serie_vuoto():
    """series.ini di un progetto nuovo: descrizione dei campi ed esempio dal modello del motore, senza serie."""
    f = CARTELLA / "series_template.ini"
    testo = f.read_text(encoding="utf-8").rstrip() + "\n" if f.exists() else ""
    return testo + "\n# Nessuna serie: aggiungile copiando l'esempio o chiedendo in Jan («crea la serie ...»).\n"


def cmd_nuovo(args, stampa=print):
    """Crea un progetto vuoto; 0 riuscito, 1 la cartella esiste già con qualcosa dentro, 2 nome non ammesso.
    Con «stampa» si può raccogliere il messaggio altrove (l'avvio guidato, lavoro 28)."""
    radice = Path(args.cartella).resolve()
    if radice.exists() and any(radice.iterdir()):
        stampa(f"La cartella {radice} esiste e non è vuota: per sicurezza non creo un progetto lì.")
        return 1
    if args.nome and not re.fullmatch(r"[^/\\:*?\"<>|]+", args.nome):
        stampa("Il nome del progetto non va bene: niente barre o altri segni proibiti nei nomi dei file.")
        return 2
    for k in ("dati", "originali", "importazioni", "risposte", "lavori", "backup"):
        (radice / PERCORSI[k]).mkdir(parents=True, exist_ok=True)
    for sotto in (ARCHIVIO, RICERCHE):
        (radice / PERCORSI["risultati"] / sotto).mkdir(parents=True, exist_ok=True)
    for k in ("entita", "indice"):
        (radice / PERCORSI[k]).parent.mkdir(parents=True, exist_ok=True)
    for k, testa in INTESTAZIONE_CSV.items():          # CSV con BOM UTF-8 e CRLF, come quelli del corpus
        (radice / PERCORSI[k]).write_bytes(("﻿" + testa + "\r\n").encode("utf-8"))
    (radice / PERCORSI["entita"]).write_text(ENTITA_VUOTO, encoding="utf-8")
    (radice / PERCORSI["istruzioni"]).write_text(ISTRUZIONI_VUOTO, encoding="utf-8")
    (radice / PERCORSI["serie"]).write_text(serie_vuoto(), encoding="utf-8")
    (radice / "project.ini").write_text(
        f"[progetto]\nnome = {args.nome or radice.name}\ndescrizione = {args.descrizione or ''}\n"
        f"creato_il = {dt.date.today().isoformat()}\n", encoding="utf-8")
    stampa(f"Progetto creato in {radice}.\nPer usarlo: in config.ini, sezione [progetto], cartella = {radice}\n"
           f"oppure, solo per il terminale aperto: "
           f"{f'set {VARIABILE}={radice}' if os.name == 'nt' else f'export {VARIABILE}={radice}'}\n"
           f"Poi importa le fonti: python importa.py proponi <cartella dei documenti> (docs/quickstart.it.md).")
    return 0


def cmd_stato(args):
    cfg = leggi_config()
    radice = cartella_scelta(cfg)
    if radice is None:
        sys.exit(NESSUN_PROGETTO)
    origine = (f"variabile d'ambiente {VARIABILE}" if os.environ.get(VARIABILE, "").strip() else
               "config.ini, [progetto] cartella")
    print(f"Progetto: {nome(cfg)} ({radice}) — {origine}")
    for k in PERCORSI:
        p = percorso(cfg, k)
        print(f"  {k:22} {'  ' if p.exists() else '! '}{p}")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())

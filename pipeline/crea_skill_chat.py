#!/usr/bin/env python3
"""
Costruisce lo zip della skill ricerca-fonti per la chat di Claude (claude.ai, Claude Desktop): SKILL.md e
config.ini da skill_chat/, i moduli del motore che servono alla lettura in sessione e serie_modello.ini.
Lo zip si carica in Impostazioni → Funzionalità → Skill (serve l'esecuzione del codice).

Uso:
  python crea_skill_chat.py [--out ../dist/ricerca-fonti.zip]
"""
import argparse
import ast
import sys
import zipfile
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
SORGENTE = CARTELLA.parent / "skill_chat"
NOME = "ricerca-fonti"
# moduli del motore: chat.py e quelli che importa, direttamente o no (calcolati da dipendenze())
INIZIO = ["chat", "sessione", "sintesi", "importa", "esplora", "schede", "progetto", "indice"]
FILE_FISSI = ["serie_modello.ini"]


def dipendenze(inizio):
    """Moduli della cartella pipeline raggiungibili da quelli indicati, seguendo gli import."""
    locali = {p.stem for p in CARTELLA.glob("*.py")}
    visti, da_fare = set(), list(inizio)
    while da_fare:
        m = da_fare.pop()
        if m in visti:
            continue
        visti.add(m)
        albero = ast.parse((CARTELLA / f"{m}.py").read_text(encoding="utf-8"))
        for nodo in ast.walk(albero):
            nomi = [a.name for a in nodo.names] if isinstance(nodo, ast.Import) else \
                [nodo.module] if isinstance(nodo, ast.ImportFrom) and nodo.module else []
            da_fare += [n.split(".")[0] for n in nomi if n.split(".")[0] in locali]
    return sorted(visti)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(CARTELLA.parent / "dist" / f"{NOME}.zip"))
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    moduli = dipendenze(INIZIO)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(SORGENTE / "SKILL.md", f"{NOME}/SKILL.md")
        z.write(SORGENTE / "config.ini", f"{NOME}/motore/config.ini")
        z.write(CARTELLA.parent / "LICENSE", f"{NOME}/LICENSE")
        for m in moduli:
            z.write(CARTELLA / f"{m}.py", f"{NOME}/motore/{m}.py")
        for f in FILE_FISSI:
            z.write(CARTELLA / f, f"{NOME}/motore/{f}")
    print(f"{out} ({out.stat().st_size // 1024} KB): SKILL.md e {len(moduli)} moduli: {', '.join(moduli)}")


if __name__ == "__main__":
    sys.exit(main())

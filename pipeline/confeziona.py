#!/usr/bin/env python3
"""
Confezioni della skill ricerca-fonti, dalla fonte unica skills/ricerca-fonti/ (SKILL.md, config.ini) più i moduli
del motore che servono alla lettura in sessione, copiati qui e non tenuti a mano nella fonte. Scrive in dist/:

  ricerca-fonti-claude.zip     per claude.ai e Claude Desktop (Customize → Skills → Upload a skill): la cartella
                               ricerca-fonti/ alla radice dello zip
  claude-code/                 marketplace di Claude Code con il plugin plugins/ricerca-fonti/
                               (claude plugin marketplace add ./claude-code; claude plugin install
                               ricerca-fonti@airchivist); la skill sola, per ~/.claude/skills/, è
                               plugins/ricerca-fonti/skills/ricerca-fonti/
  ricerca-fonti-chatgpt.zip    lo stesso plugin, con il manifesto portabile plugin.json, per ChatGPT (console
                               dell'area di lavoro o portale dei plugin, percorso «Skills only»)

Ogni confezione ha un LEGGIMI.md (da skills/leggimi/) e la licenza.

Uso:
  python confeziona.py [--dist ../dist]
"""
import argparse
import ast
import json
import shutil
import sys
import zipfile
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
RADICE = CARTELLA.parent
SORGENTE = RADICE / "skills" / "ricerca-fonti"
LEGGIMI = RADICE / "skills" / "leggimi"
NOME = "ricerca-fonti"
VERSIONE = "0.1.0"
DESCRIZIONE = ("Trova tutte le occorrenze di una persona o di un ente nelle fonti primarie e risponde con i passaggi "
               "originali, la traduzione e il riferimento in stile Chicago.")
AUTORE = {"name": "Ivan Masci"}
SITO = "https://github.com/AMI-AIM/AIrchivist"
LICENZA = "AGPL-3.0-or-later"
MARKETPLACE = "airchivist"
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


def file_della_skill():
    """{percorso dentro la cartella della skill: file sorgente}."""
    out = {"SKILL.md": SORGENTE / "SKILL.md", "motore/config.ini": SORGENTE / "config.ini"}
    out.update({f"motore/{m}.py": CARTELLA / f"{m}.py" for m in dipendenze(INIZIO)})
    out.update({f"motore/{f}": CARTELLA / f for f in FILE_FISSI})
    return out


def manifesto(portabile=False):
    m = {"name": NOME, "version": VERSIONE, "description": DESCRIZIONE, "author": AUTORE, "homepage": SITO,
         "repository": SITO, "license": LICENZA, "keywords": ["ricerca storica", "fonti primarie", "citazioni"]}
    return {"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json", **m} if portabile else m


def scrivi_json(f, dati):
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(dati, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def zip_claude(out, skill):
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, f in skill.items():
            z.write(f, f"{NOME}/{rel}")
        z.write(LEGGIMI / "claude_ai.md", f"{NOME}/LEGGIMI.md")
        z.write(RADICE / "LICENSE", f"{NOME}/LICENSE")


def plugin(cartella, skill):
    """Cartella del plugin: skills/ricerca-fonti/, manifesti di Claude Code e portabile, LEGGIMI, licenza."""
    for rel, f in skill.items():
        dest = cartella / "skills" / NOME / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(f, dest)
    scrivi_json(cartella / ".claude-plugin" / "plugin.json", manifesto())
    scrivi_json(cartella / "plugin.json", manifesto(portabile=True))
    shutil.copyfile(LEGGIMI / "plugin.md", cartella / "LEGGIMI.md")
    shutil.copyfile(RADICE / "LICENSE", cartella / "LICENSE")


def confeziona(dist):
    dist = Path(dist)
    dist.mkdir(parents=True, exist_ok=True)
    skill = file_della_skill()
    zip_claude(dist / f"{NOME}-claude.zip", skill)

    mercato = dist / "claude-code"
    if mercato.exists():
        shutil.rmtree(mercato)                 # cartella generata: si rifà da capo
    cart = mercato / "plugins" / NOME
    plugin(cart, skill)
    scrivi_json(mercato / ".claude-plugin" / "marketplace.json",
                {"name": MARKETPLACE, "description": "Skill di AIrchivist per la ricerca nelle fonti primarie",
                 "owner": AUTORE,
                 "plugins": [{"name": NOME, "source": f"./plugins/{NOME}", "description": DESCRIZIONE}]})

    with zipfile.ZipFile(dist / f"{NOME}-chatgpt.zip", "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(cart.rglob("*")):
            if f.is_file():
                z.write(f, f.relative_to(cart).as_posix())
    return {"claude": dist / f"{NOME}-claude.zip", "claude_code": mercato, "chatgpt": dist / f"{NOME}-chatgpt.zip",
            "moduli": sorted(Path(r).stem for r in skill if r.endswith(".py"))}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dist", default=str(RADICE / "dist"))
    args = ap.parse_args(argv)
    esito = confeziona(args.dist)
    for k in ("claude", "claude_code", "chatgpt"):
        p = esito[k]
        dim = f" ({p.stat().st_size // 1024} KB)" if p.is_file() else ""
        print(f"{k:12} {p}{dim}")
    print(f"{len(esito['moduli'])} moduli del motore: {', '.join(esito['moduli'])}")


if __name__ == "__main__":
    sys.exit(main())

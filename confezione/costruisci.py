#!/usr/bin/env python3
"""
Costruzione del programma installabile per Windows (lavoro 39, fase 3).

Prepara in confezione/uscita/AIrchivist la cartella che l'installatore copia sul computer del ricercatore, e
l'installatore stesso se Inno Setup è presente:

  AIrchivist/
    python/           Python «embeddable» ufficiale (python.org), con PyMuPDF e pywebview in Lib/site-packages
    scripts/          il motore (i file sotto git), config.ini senza scelte personali, installazione.ini
    tesseract/        Tesseract (copiato da un'installazione esistente) con le lingue scelte
    docs/             guide per gli utenti, LICENSE, TERZE_PARTI.txt

installazione.ini mette il motore nel modo installato (posizioni.py): configurazione e profili nella cartella dei
dati dell'utente (%APPDATA%\\AIrchivist), progetti in Documenti\\AIrchivist. Il programma non scrive mai nella
propria cartella, salvo le lingue OCR scaricate dall'interfaccia (tesseract/tessdata).

Requisiti per costruire (solo su questo computer, non per chi installa): Python della stessa versione minore del
Python incluso, con pip; Tesseract installato (UB Mannheim); Inno Setup 6 per l'installatore. I file scaricati
(Python embeddable, pacchetti da PyPI) restano in confezione/cache, fuori da git.

Uso (dalla cartella del repository):
  python confezione/costruisci.py                       cartella del programma e, se c'è Inno Setup, installatore
  python confezione/costruisci.py --lingue eng,chi_sim,sqi,ita   solo queste lingue OCR (predefinite: tutte)
  python confezione/costruisci.py --senza-installatore
"""
import argparse
import configparser
import datetime as dt
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

CONFEZIONE = Path(__file__).resolve().parent
RADICE = CONFEZIONE.parent
SCRIPTS = RADICE / "scripts"
sys.path.insert(0, str(SCRIPTS))

URL_PYTHON = "https://www.python.org/ftp/python/{v}/python-{v}-embed-amd64.zip"
# file di Tesseract che servono al programma: l'eseguibile e le sue librerie (non gli strumenti di addestramento)
TESSDATA_SEMPRE = ("osd", "eng")                  # orientamento della pagina e inglese, sempre
DOCUMENTI = ("quickstart.it.md", "quickstart.md", "user_guide.it.md", "user_guide.md", "troubleshooting.it.md",
             "troubleshooting.md")
TERZE_PARTI = """Componenti di terze parti inclusi in AIrchivist per Windows

AIrchivist è distribuito con licenza GNU AGPL-3.0 (LICENSE). Il programma include:

- Python {python} (python.org, distribuzione «embeddable»): Python Software Foundation License
  (python/LICENSE.txt).
- Librerie Python in python/Lib/site-packages, ciascuna con la propria licenza nella cartella
  <nome>.dist-info: {pacchetti}.
  PyMuPDF è distribuito con licenza GNU AGPL-3.0.
- Tesseract OCR {tesseract} (https://github.com/tesseract-ocr/tesseract, build Windows di UB Mannheim):
  Apache License 2.0; le librerie DLL che lo accompagnano (Leptonica e altre) hanno licenze libere proprie.
- Modelli delle lingue di Tesseract (tesseract/tessdata, da tessdata_best): Apache License 2.0.
"""


def stampa(t=""):
    print(t, flush=True)


def scarica(url, dest):
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    stampa(f"  scarico {url}")
    parziale = dest.with_suffix(dest.suffix + ".parziale")
    with urllib.request.urlopen(url, timeout=120) as r, open(parziale, "wb") as f:
        shutil.copyfileobj(r, f)
    parziale.replace(dest)
    return dest


def versione_programma():
    """Data e commit: 2026.11.01+e21b46b (con «-modificato» se ci sono cambi non registrati)."""
    oggi = dt.date.today().strftime("%Y.%m.%d")
    try:
        commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RADICE, capture_output=True,
                                text=True, check=True).stdout.strip()
        sporco = subprocess.run(["git", "status", "--porcelain", "--", "scripts"], cwd=RADICE,
                                capture_output=True, text=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return oggi
    return f"{oggi}+{commit}" + ("-modificato" if sporco else "")


# ---------------------------------------------------------------- Python
def prepara_python(dest, versione, cache):
    """Python embeddable estratto in dest, con site-packages e la cartella scripts nel percorso dei moduli."""
    zip_ = scarica(URL_PYTHON.format(v=versione), cache / f"python-{versione}-embed-amd64.zip")
    with zipfile.ZipFile(zip_) as z:
        z.extractall(dest)
    pth = next(dest.glob("python3*._pth"))
    righe = [r for r in pth.read_text(encoding="utf-8").splitlines() if r.strip() and r.strip() != "#import site"]
    # i moduli del motore si importano per nome (anche dai processi delle ricerche e dal server MCP)
    righe += ["Lib\\site-packages", "..\\scripts", "import site"]
    pth.write_text("\n".join(righe) + "\n", encoding="utf-8")
    (dest / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)


def installa_pacchetti(dest, cache):
    """Le librerie di requirements.txt nel site-packages del Python incluso. Prima si fanno le ruote con il Python
    che esegue lo script (stessa versione minore, Windows a 64 bit: lo controlla main), così anche i pacchetti
    distribuiti solo come sorgente (proxy_tools, per pywebview) diventano ruote; poi si installano da lì, senza
    rete."""
    ruote = cache / "ruote"
    pip = [sys.executable, "-m", "pip", "--disable-pip-version-check"]
    subprocess.run(pip + ["wheel", "-q", "-w", str(ruote), "-r", str(RADICE / "requirements.txt")], check=True)
    subprocess.run(pip + ["install", "-q", "--no-compile", "--no-index", "--find-links", str(ruote),
                          "--target", str(dest / "Lib" / "site-packages"), "-r", str(RADICE / "requirements.txt")],
                   check=True)
    return sorted(re.sub(r"-[^-]+\.dist-info$", "", d.name) for d in (dest / "Lib" / "site-packages").glob("*.dist-info"))


# ---------------------------------------------------------------- motore
def file_del_motore():
    """I file di scripts sotto git: niente models.ini, copie .bak, cache o file personali."""
    r = subprocess.run(["git", "ls-files", "-z", "scripts"], cwd=RADICE, capture_output=True, check=True)
    return [RADICE / p for p in r.stdout.decode("utf-8").split("\0") if p]


def config_pulito(testo):
    """config.ini senza le scelte di chi costruisce: nessun progetto, nessun profilo di modello scelto (il primo
    avvio li chiede nella «Preparazione»). Il resto (commenti, parametri) resta com'è."""
    fuori, sezione = [], ""
    for riga in testo.splitlines():
        m = re.match(r"^\s*\[([^\]]+)\]", riga)
        if m:
            sezione = m.group(1).strip()
        voce = re.match(r"^\s*([A-Za-z_]+)\s*=", riga)
        if voce and sezione == "progetto" and voce.group(1) == "cartella":
            riga = "cartella ="
        elif voce and sezione == "modello" and voce.group(1) in ("profilo", "smistamento", "analisi", "sintesi",
                                                                 "file_profili"):
            continue
        elif voce and sezione == "ocr" and voce.group(1) in ("tesseract", "modelli"):
            riga = f"{voce.group(1)} ="
        fuori.append(riga)
    return "\n".join(fuori) + "\n"


INSTALLAZIONE_INI = """# Questo file mette AIrchivist nel modo «installato» (scripts/posizioni.py): la cartella del programma non si
# modifica, le scelte dell'utente vanno in %APPDATA%\\AIrchivist (config.ini, models.ini), i progetti nuovi in
# Documenti\\AIrchivist. Voci facoltative:
#   dati = <cartella>       altrove i dati dell'utente (relativa alla cartella del programma: copia portatile)
#   progetti = <cartella>   altrove i progetti nuovi
[installazione]
versione = {versione}
"""


def copia_motore(dest, versione):
    for f in file_del_motore():
        rel = f.relative_to(SCRIPTS)
        d = dest / rel
        d.parent.mkdir(parents=True, exist_ok=True)
        if rel.as_posix() == "config.ini":
            d.write_bytes(config_pulito(f.read_bytes().decode("utf-8")).encode("utf-8"))
        else:
            shutil.copy2(f, d)
    (dest / "installazione.ini").write_text(INSTALLAZIONE_INI.format(versione=versione), encoding="utf-8")


# ---------------------------------------------------------------- Tesseract
def copia_tesseract(origine, dest, lingue):
    """Eseguibile e DLL di Tesseract, configurazioni e modelli delle lingue scelte (None = tutte)."""
    origine = Path(origine)
    dest.mkdir(parents=True)
    for f in origine.iterdir():
        if f.is_file() and (f.name.lower() == "tesseract.exe" or f.suffix.lower() == ".dll"):
            shutil.copy2(f, dest / f.name)
    td_o, td_d = origine / "tessdata", dest / "tessdata"
    td_d.mkdir()
    for sotto in ("configs", "tessconfigs"):
        if (td_o / sotto).is_dir():
            shutil.copytree(td_o / sotto, td_d / sotto)
    if (td_o / "pdf.ttf").exists():
        shutil.copy2(td_o / "pdf.ttf", td_d / "pdf.ttf")
    disponibili = sorted(f.stem for f in td_o.glob("*.traineddata"))
    scelte = disponibili if lingue is None else sorted(set(lingue) | set(TESSDATA_SEMPRE))
    mancanti = [l for l in scelte if l not in disponibili]
    if mancanti:
        raise SystemExit(f"Lingue OCR assenti in {td_o}: {', '.join(mancanti)} (disponibili: {', '.join(disponibili)})")
    for l in scelte:
        shutil.copy2(td_o / f"{l}.traineddata", td_d / f"{l}.traineddata")
    r = subprocess.run([str(dest / "tesseract.exe"), "--version"], capture_output=True)
    versione = (r.stdout + r.stderr).decode("utf-8", "replace").splitlines()[0].replace("tesseract", "").strip()
    return versione, scelte


# ---------------------------------------------------------------- documenti e prova
def copia_documenti(dest, testo_terze_parti):
    dest.mkdir()
    for nome in DOCUMENTI:
        if (RADICE / "docs" / nome).exists():
            shutil.copy2(RADICE / "docs" / nome, dest / nome)
    for nome in ("LICENSE", "README.md", "README.it.md"):
        shutil.copy2(RADICE / nome, dest / nome)
    (dest / "TERZE_PARTI.txt").write_text(testo_terze_parti, encoding="utf-8")


def prova_cartella(prog, dati_prova):
    """Il Python incluso avvia il motore nel modo installato, trova le librerie e il proprio Tesseract.
    Le scritture della prova vanno in una cartella a parte (AIRCHIVIST_DATI), non nella cartella dell'utente."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON") and k != "AIRCHIVIST_PROGETTO"}
    env["AIRCHIVIST_DATI"] = str(dati_prova)
    codice = ("import sys, posizioni, importa, installa, pymupdf, webview, sqlite3; "
              "from progetto import leggi_config; "
              "e = installa.Esito(); installa.controlla_sqlite(e); "
              "print('modo', 'installato' if posizioni.installato() else 'sviluppo'); "
              "print('python', sys.executable); print('pymupdf', pymupdf.VersionBind); "
              "print('tesseract', importa.cerca_tesseract(leggi_config())); "
              "print('lingue', sorted(importa.lingue_installate(importa.cerca_tesseract(leggi_config())))); "
              "sys.exit(len(e.mancanti))")
    r = subprocess.run([str(prog / "python" / "python.exe"), "-c", codice], cwd=prog / "scripts", env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    stampa("  " + (r.stdout + r.stderr).strip().replace("\n", "\n  "))
    if r.returncode:
        raise SystemExit("La prova della cartella del programma non è riuscita.")
    atteso = str((prog / "tesseract" / "tesseract.exe").resolve())
    if atteso not in r.stdout:
        raise SystemExit(f"Il motore non usa il Tesseract incluso ({atteso}).")


# ---------------------------------------------------------------- installatore
def cerca_iscc():
    trovato = shutil.which("iscc")
    if trovato:
        return trovato
    for base in (os.environ.get("ProgramFiles(x86)"), os.environ.get("ProgramFiles"),
                 os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs")):
        if base and (Path(base) / "Inno Setup 6" / "ISCC.exe").exists():
            return str(Path(base) / "Inno Setup 6" / "ISCC.exe")
    return None


def costruisci_installatore(iscc, uscita, versione):
    numerica = versione.split("+")[0]
    cmd = [iscc, f"/DVersione={versione}", f"/DVersioneNumerica={numerica}", f"/DCartella={uscita / 'AIrchivist'}",
           f"/O{uscita}", str(CONFEZIONE / "airchivist.iss")]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode:
        raise SystemExit("Inno Setup non è riuscito:\n" + (r.stdout + r.stderr)[-3000:])
    return uscita / f"AIrchivist-{numerica}-setup.exe"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--python", default=".".join(map(str, sys.version_info[:3])),
                    help="versione del Python incluso (predefinita: quella che esegue lo script)")
    ap.add_argument("--tesseract", help="cartella di un Tesseract installato (predefinita: quella del sistema)")
    ap.add_argument("--lingue", help="lingue OCR da includere, separate da virgole (predefinite: tutte quelle "
                                     "installate; osd ed eng sempre)")
    ap.add_argument("--uscita", default=str(CONFEZIONE / "uscita"))
    ap.add_argument("--senza-installatore", action="store_true")
    args = ap.parse_args(argv)
    if os.name != "nt":
        raise SystemExit("Per ora si costruisce solo il programma per Windows, su Windows.")
    if args.python.split(".")[:2] != list(map(str, sys.version_info[:2])):
        raise SystemExit(f"Esegui lo script con Python {'.'.join(args.python.split('.')[:2])}: pip scarica le "
                         "librerie per la versione del Python incluso, e le prova con la stessa.")
    uscita = Path(args.uscita).resolve()
    prog = uscita / "AIrchivist"
    cache = CONFEZIONE / "cache"
    versione = versione_programma()
    stampa(f"AIrchivist {versione}: costruzione in {prog}")
    if prog.exists():
        shutil.rmtree(prog)
    prog.mkdir(parents=True)

    stampa(f"1. Python {args.python} embeddable")
    prepara_python(prog / "python", args.python, cache)
    stampa("2. Librerie (requirements.txt)")
    pacchetti = installa_pacchetti(prog / "python", cache)
    stampa("   " + ", ".join(pacchetti))
    stampa("3. Motore")
    copia_motore(prog / "scripts", versione)
    stampa("4. Tesseract")
    if args.tesseract:
        origine = Path(args.tesseract)
    else:
        from importa import cerca_tesseract
        trovato = cerca_tesseract(configparser.ConfigParser())
        if not trovato:
            raise SystemExit("Tesseract non trovato: installalo (winget install -e --id UB-Mannheim.TesseractOCR) "
                             "o indica la cartella con --tesseract.")
        origine = Path(trovato).parent
    lingue = [l.strip() for l in args.lingue.split(",") if l.strip()] if args.lingue else None
    v_tess, scelte = copia_tesseract(origine, prog / "tesseract", lingue)
    stampa(f"   {v_tess} da {origine}; lingue: {', '.join(scelte)}")
    stampa("5. Documenti e licenze")
    copia_documenti(prog / "docs", TERZE_PARTI.format(python=args.python, pacchetti=", ".join(pacchetti),
                                                      tesseract=v_tess))
    stampa("6. Prova della cartella")
    dati_prova = uscita / "prova_dati"
    shutil.rmtree(dati_prova, ignore_errors=True)
    prova_cartella(prog, dati_prova)
    shutil.rmtree(dati_prova, ignore_errors=True)
    for d in prog.rglob("__pycache__"):                     # la prova li ha creati: non si distribuiscono
        shutil.rmtree(d)
    dimensione = sum(f.stat().st_size for f in prog.rglob("*") if f.is_file())
    stampa(f"   cartella pronta: {dimensione / 1e6:.0f} MB")

    if args.senza_installatore:
        return 0
    iscc = cerca_iscc()
    if not iscc:
        stampa("7. Installatore: Inno Setup non trovato. Installalo (gratuito: winget install -e --id "
               "JRSoftware.InnoSetup) e rilancia, oppure distribuisci la cartella così com'è.")
        return 0
    stampa("7. Installatore (Inno Setup)")
    setup = costruisci_installatore(iscc, uscita, versione)
    stampa(f"   {setup} ({setup.stat().st_size / 1e6:.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

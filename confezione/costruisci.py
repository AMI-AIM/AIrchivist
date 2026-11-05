#!/usr/bin/env python3
"""
Costruzione del programma installabile per Windows.

Prepara in confezione/uscita/Pressmark la cartella che l'installatore copia sul computer del ricercatore, e
l'installatore stesso se Inno Setup è presente:

  Pressmark/
    python/           Python «embeddable» ufficiale (python.org), con PyMuPDF e pywebview in Lib/site-packages
    scripts/          il motore (i file sotto git), config.ini senza scelte personali, installazione.ini
    assets/          logotipo e favicon (SVG, per l'interfaccia) e pressmark.ico (collegamenti, installatore)
    tesseract/        Tesseract (copiato da un'installazione esistente: l'eseguibile e le sole DLL che carica)
                      con le lingue scelte
    docs/             guide per gli utenti, LICENSE, TERZE_PARTI.txt

installazione.ini mette il motore nel modo installato (posizioni.py): configurazione e profili nella cartella dei
dati dell'utente (%APPDATA%\\Pressmark), progetti in Documenti\\Pressmark. Il programma non scrive mai nella
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
import hashlib
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
# SHA-256 dello zip embeddable per versione: il file scaricato (o già nella cache) si usa solo se corrisponde. Per una
# versione nuova si copia l'hash dalla pagina della versione su python.org (o si passa --sha256-python).
SHA256_PYTHON = {
    "3.14.6": "df901e84a896ff1ee720ad03377e0c8d8c2244fda79808aeeaff6316df1cb75c",
}
# file di Tesseract che servono al programma: l'eseguibile e le sue librerie (non gli strumenti di addestramento)
TESSDATA_SEMPRE = ("osd", "eng")                  # orientamento della pagina e inglese, sempre
DOCUMENTI = ("quickstart.it.md", "quickstart.md", "user_guide.it.md", "user_guide.md", "troubleshooting.it.md",
             "troubleshooting.md")
TERZE_PARTI = """Componenti di terze parti inclusi in Pressmark per Windows

Pressmark è distribuito con licenza GNU AGPL-3.0 (LICENSE). Il programma include:

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


def sha256(f):
    h = hashlib.sha256()
    with open(f, "rb") as d:
        for blocco in iter(lambda: d.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


def scarica(url, dest, atteso=None, apri=None):
    """Scarica url in dest (prima in un file .parziale, tolto se qualcosa va storto). Con `atteso` (SHA-256) il file,
    scaricato ora o già nella cache, si usa solo se corrisponde."""
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        stampa(f"  scarico {url}")
        parziale = dest.with_suffix(dest.suffix + ".parziale")
        try:
            with (apri or urllib.request.urlopen)(url, timeout=120) as r, open(parziale, "wb") as f:
                shutil.copyfileobj(r, f)
        except BaseException:
            parziale.unlink(missing_ok=True)
            raise
        parziale.replace(dest)
    if atteso:
        trovato = sha256(dest)
        if trovato != atteso.lower():
            dest.unlink()
            raise SystemExit(f"{dest.name}: SHA-256 {trovato}, atteso {atteso}. File tolto dalla cache: non lo uso.")
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
def prepara_python(dest, versione, cache, atteso=None):
    """Python embeddable estratto in dest, con site-packages e la cartella scripts nel percorso dei moduli. Lo zip
    si verifica con il suo SHA-256 (atteso, o quello di SHA256_PYTHON per la versione)."""
    atteso = atteso or SHA256_PYTHON.get(versione)
    if not atteso:
        raise SystemExit(f"Nessuno SHA-256 noto per Python {versione}: copialo dalla pagina della versione su "
                         "python.org (file «Windows embeddable package (64-bit)») in SHA256_PYTHON, o passalo con "
                         "--sha256-python.")
    zip_ = scarica(URL_PYTHON.format(v=versione), cache / f"python-{versione}-embed-amd64.zip", atteso)
    with zipfile.ZipFile(zip_) as z:
        z.extractall(dest)
    pth = next(dest.glob("python3*._pth"))
    righe = [r for r in pth.read_text(encoding="utf-8").splitlines() if r.strip() and r.strip() != "#import site"]
    # i moduli del motore si importano per nome (anche dai processi delle ricerche)
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


# sezioni della configurazione precedente ai profili (llm.profilo_precedente): servizi, indirizzi e modelli di chi
# costruisce, che nel programma installato non servono (il modello si sceglie con un profilo)
SEZIONI_PRECEDENTI = ("anthropic", "openai", "router", "ollama")


def config_pulito(testo):
    """config.ini senza le scelte di chi costruisce: nessun progetto, nessun profilo di modello scelto, nessun
    servizio della configurazione precedente (il primo avvio li chiede nella «Preparazione»). Il resto (commenti,
    parametri) resta com'è."""
    fuori, sezione = [], ""
    for riga in testo.splitlines():
        m = re.match(r"^\s*\[([^\]]+)\]", riga)
        if m:
            sezione = m.group(1).strip()
        if sezione in SEZIONI_PRECEDENTI:
            continue
        voce = re.match(r"^\s*([A-Za-z_]+)\s*=", riga)
        if voce and sezione == "progetto" and voce.group(1) == "cartella":
            riga = "cartella ="
        elif voce and sezione == "modello" and voce.group(1) in ("profilo", "smistamento", "analisi", "sintesi",
                                                                 "file_profili", "backend"):
            continue
        elif voce and sezione == "ocr" and voce.group(1) in ("tesseract", "modelli"):
            riga = f"{voce.group(1)} ="
        fuori.append(riga)
    return "\n".join(fuori) + "\n"


INSTALLAZIONE_INI = """# Questo file mette Pressmark nel modo «installato» (scripts/posizioni.py): la cartella del programma non si
# modifica, le scelte dell'utente vanno in %APPDATA%\\Pressmark (config.ini, models.ini), i progetti nuovi in
# Documenti\\Pressmark. Voci facoltative:
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


MARCHIO = RADICE / "assets"
LATI_ICONA = (16, 24, 32, 48, 64, 256)


def icona_ico(svg, lati=LATI_ICONA):
    """Il favicon SVG come file .ico (una PNG per ogni lato, come accetta Windows da Vista), disegnato con PyMuPDF."""
    import struct
    import fitz
    doc = fitz.open(stream=svg.read_bytes(), filetype="svg")
    pagina = doc[0]
    immagini = []
    for lato in lati:
        scala = lato / pagina.rect.width
        immagini.append(pagina.get_pixmap(matrix=fitz.Matrix(scala, scala), alpha=True).tobytes("png"))
    testa = struct.pack("<HHH", 0, 1, len(immagini))
    voci, dati, posizione = b"", b"", 6 + 16 * len(immagini)
    for lato, png in zip(lati, immagini):
        voci += struct.pack("<BBBBHHII", lato % 256, lato % 256, 0, 0, 1, 32, len(png), posizione + len(dati))
        dati += png
    return testa + voci + dati


def copia_marchio(dest):
    """Logotipo e favicon (serviti dall'interfaccia come /marchio/...) e pressmark.ico per i collegamenti."""
    dest.mkdir(parents=True, exist_ok=True)
    for f in sorted(MARCHIO.glob("*.svg")):
        shutil.copy2(f, dest / f.name)
    (dest / "pressmark.ico").write_bytes(icona_ico(MARCHIO / "pressmark-favicon-chiaro.svg"))


# ---------------------------------------------------------------- Tesseract
def importazioni_pe(f):
    """Nomi (minuscoli) delle DLL che un eseguibile o una DLL di Windows importa: tabella delle importazioni e
    importazioni ritardate. Solo libreria standard."""
    import struct
    b = Path(f).read_bytes()
    pe = struct.unpack_from("<I", b, 0x3C)[0]
    if b[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"{f}: non è un file PE")
    n_sezioni, dim_opz = struct.unpack_from("<H", b, pe + 6)[0], struct.unpack_from("<H", b, pe + 20)[0]
    opz = pe + 24
    cartelle = opz + (112 if struct.unpack_from("<H", b, opz)[0] == 0x20B else 96)   # PE32+ o PE32
    sezioni = [struct.unpack_from("<IIII", b, opz + dim_opz + i * 40 + 8) for i in range(n_sezioni)]

    def posizione(rva):
        for dim_virt, va, dim_dati, inizio in sezioni:
            if va <= rva < va + max(dim_virt, dim_dati):
                return rva - va + inizio
        return None

    def nome(rva):
        p = posizione(rva)
        return b[p:b.index(b"\0", p)].decode("ascii", "replace").lower() if p is not None else ""

    nomi = []
    for indice, passo, campo in ((1, 20, 12), (13, 32, 4)):          # importazioni, importazioni ritardate
        rva = struct.unpack_from("<I", b, cartelle + indice * 8)[0]
        p = posizione(rva) if rva else None
        while p is not None and p + passo <= len(b):
            rva_nome = struct.unpack_from("<I", b, p + campo)[0]
            if not rva_nome:
                break
            nomi.append(nome(rva_nome))
            p += passo
    return nomi


def dll_necessarie(cartella, eseguibile="tesseract.exe"):
    """Le DLL della cartella che l'eseguibile carica, direttamente o tramite altre DLL della cartella. La build di
    UB Mannheim porta anche le librerie degli strumenti di addestramento (pango, cairo, ICU...): il programma usa
    solo tesseract.exe, quindi quelle restano fuori."""
    locali = {f.name.lower(): f for f in Path(cartella).iterdir() if f.is_file() and f.suffix.lower() == ".dll"}
    trovate, da_vedere = set(), [Path(cartella) / eseguibile]
    while da_vedere:
        for n in importazioni_pe(da_vedere.pop()):
            if n in locali and n not in trovate:
                trovate.add(n)
                da_vedere.append(locali[n])
    return sorted(locali[n] for n in trovate)


def prova_ocr(cartella_tess):
    """Il Tesseract copiato legge una riga di prova, senza il PATH del sistema (deve bastare la sua cartella)."""
    import fitz
    prova = cartella_tess.parent / "prova_ocr"
    prova.mkdir(exist_ok=True)
    try:
        doc = fitz.open()
        doc.new_page(width=600, height=200).insert_text((40, 100), "Pressmark 2026", fontsize=28)
        doc[0].get_pixmap(dpi=200).save(prova / "riga.png")
        env = {**os.environ, "PATH": os.environ.get("SystemRoot", r"C:\Windows") + r"\System32"}
        r = subprocess.run([str(cartella_tess / "tesseract.exe"), str(prova / "riga.png"), "-", "-l", "eng",
                            "--tessdata-dir", str(cartella_tess / "tessdata")], capture_output=True, env=env)
        letto = r.stdout.decode("utf-8", "replace")
        if r.returncode or "Pressmark" not in letto:
            raise SystemExit("Il Tesseract incluso non legge la riga di prova (manca una DLL?):\n"
                             + (letto + r.stderr.decode("utf-8", "replace"))[-2000:])
    finally:
        shutil.rmtree(prova, ignore_errors=True)


def copia_tesseract(origine, dest, lingue):
    """Eseguibile e DLL che carica, configurazioni e modelli delle lingue scelte (None = tutte)."""
    origine = Path(origine)
    dest.mkdir(parents=True)
    shutil.copy2(origine / "tesseract.exe", dest / "tesseract.exe")
    for f in dll_necessarie(origine):
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
    Le scritture della prova vanno in una cartella a parte (PRESSMARK_DATI), non nella cartella dell'utente."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON") and k != "PRESSMARK_PROGETTO"}
    env["PRESSMARK_DATI"] = str(dati_prova)
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
    cmd = [iscc, f"/DVersione={versione}", f"/DVersioneNumerica={numerica}", f"/DCartella={uscita / 'Pressmark'}",
           f"/O{uscita}", str(CONFEZIONE / "pressmark.iss")]
    r = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    if r.returncode:
        raise SystemExit("Inno Setup non è riuscito:\n" + (r.stdout + r.stderr)[-3000:])
    return uscita / f"Pressmark-{numerica}-setup.exe"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--python", default=".".join(map(str, sys.version_info[:3])),
                    help="versione del Python incluso (predefinita: quella che esegue lo script)")
    ap.add_argument("--sha256-python", dest="sha256_python",
                    help="SHA-256 dello zip embeddable, per una versione che SHA256_PYTHON non conosce")
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
    prog = uscita / "Pressmark"
    cache = CONFEZIONE / "cache"
    versione = versione_programma()
    stampa(f"Pressmark {versione}: costruzione in {prog}")
    if prog.exists():
        shutil.rmtree(prog)
    prog.mkdir(parents=True)

    stampa(f"1. Python {args.python} embeddable")
    prepara_python(prog / "python", args.python, cache, args.sha256_python)
    stampa("2. Librerie (requirements.txt)")
    pacchetti = installa_pacchetti(prog / "python", cache)
    stampa("   " + ", ".join(pacchetti))
    stampa("3. Motore")
    copia_motore(prog / "scripts", versione)
    copia_marchio(prog / "assets")
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
    prova_ocr(prog / "tesseract")
    n_dll = len(list((prog / "tesseract").glob("*.dll")))
    stampa(f"   {v_tess} da {origine} ({n_dll} DLL, OCR provato); lingue: {', '.join(scelte)}")
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

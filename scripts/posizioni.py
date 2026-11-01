#!/usr/bin/env python3
"""
Dove stanno i file dell'utente: configurazione, profili dei modelli, progetti (applicazione installabile, fase 1).

Due modi di funzionare:
- sviluppo (repository o copia scaricata, il modo di sempre): configurazione in scripts/config.ini, profili in
  scripts/models.ini, progetti nuovi in projects/ accanto al motore;
- installato: c'è scripts/installazione.ini (lo mette l'installatore) o la variabile d'ambiente AIRCHIVIST_DATI.
  La cartella del programma non si modifica: scripts/config.ini porta solo i valori predefiniti, le scelte
  dell'utente vanno nel config.ini della cartella dei dati, letto dopo e quindi prevalente; models.ini e le copie
  di sicurezza della configurazione stanno lì; i progetti nuovi vanno in Documenti/AIrchivist.

Cartella dei dati: AIRCHIVIST_DATI; altrimenti, se installato, [installazione] dati di installazione.ini (relativa
alla cartella del programma, per una copia portatile) o quella del sistema: Windows %APPDATA%\\AIrchivist, macOS
~/Library/Application Support/AIrchivist, Linux $XDG_CONFIG_HOME/airchivist (~/.config/airchivist).
Cartella dei progetti nuovi: [installazione] progetti, altrimenti quella predefinita del modo in uso.

installazione.ini (facoltative tutte le voci):
  [installazione]
  dati = dati                 # copia portatile: i dati accanto al programma
  progetti = D:\\Ricerche
"""
import configparser
import os
import sys
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
CONFIG_BASE = CARTELLA / "config.ini"
FILE_INSTALLAZIONE = CARTELLA / "installazione.ini"
VARIABILE_DATI = "AIRCHIVIST_DATI"
NOME = "AIrchivist"


def _installazione():
    cp = configparser.ConfigParser(interpolation=None, inline_comment_prefixes=("#",))
    if FILE_INSTALLAZIONE.is_file():
        cp.read(FILE_INSTALLAZIONE, encoding="utf-8")
    return cp


def _voce(chiave):
    return (_installazione().get("installazione", chiave, fallback="") or "").strip()


def _assoluto(valore, base):
    p = Path(os.path.expandvars(valore)).expanduser()
    return p if p.is_absolute() else (base / p).resolve()


def installato():
    """Vero se il motore funziona da programma installato (installazione.ini o AIRCHIVIST_DATI)."""
    return bool(os.environ.get(VARIABILE_DATI, "").strip()) or FILE_INSTALLAZIONE.is_file()


def cartella_sistema(piattaforma=None):
    """Cartella dei dati delle applicazioni dell'utente sul sistema in uso."""
    piattaforma = piattaforma or sys.platform
    casa = Path.home()
    if piattaforma.startswith("win"):
        return Path(os.environ.get("APPDATA") or casa / "AppData" / "Roaming") / NOME
    if piattaforma == "darwin":
        return casa / "Library" / "Application Support" / NOME
    return Path(os.environ.get("XDG_CONFIG_HOME") or casa / ".config") / NOME.lower()


def cartella_dati():
    """Dove stanno config.ini e models.ini dell'utente: la cartella scripts nel modo sviluppo."""
    v = os.environ.get(VARIABILE_DATI, "").strip()
    if v:
        return _assoluto(v, Path.cwd())
    if not installato():
        return CARTELLA
    v = _voce("dati")
    return _assoluto(v, CARTELLA.parent) if v else cartella_sistema()


def file_config():
    """Il config.ini in cui si scrivono le scelte dell'utente (progetto, modello)."""
    return cartella_dati() / "config.ini"


def file_profili():
    """models.ini predefinito: i profili dei modelli dell'utente."""
    return cartella_dati() / "models.ini"


def file_letti(path=None):
    """I file .ini da leggere, nell'ordine (l'ultimo prevale). Da installato, il config.ini dell'utente si legge
    sopra i valori predefiniti del programma; un file indicato a mano (prove, --config) si legge da solo."""
    f = Path(path) if path else file_config()
    if installato() and f.resolve() == file_config().resolve() and f.resolve() != CONFIG_BASE.resolve():
        return [CONFIG_BASE, f]
    return [f]


def documenti(piattaforma=None):
    """La cartella Documenti dell'utente (su Windows anche se spostata, per esempio in OneDrive)."""
    piattaforma = piattaforma or sys.platform
    if piattaforma.startswith("win") and os.name == "nt":
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(260)
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:   # CSIDL_PERSONAL
                return Path(buf.value)
        except (OSError, AttributeError):
            pass
    return Path.home() / "Documents"


def cartella_progetti():
    """Dove proporre i progetti nuovi: projects/ accanto al motore, o Documenti/AIrchivist da installato."""
    v = _voce("progetti")
    if v:
        return _assoluto(v, CARTELLA.parent)
    return documenti() / NOME if installato() else CARTELLA.parent / "projects"


def descrizione():
    """Righe per i riepiloghi: modo di funzionamento e posizioni."""
    modo = "installato" if installato() else "sviluppo"
    righe = [f"Modo: {modo}", f"Programma: {CARTELLA.parent}", f"Configurazione: {file_config()}"]
    if installato():
        righe.append(f"Valori predefiniti: {CONFIG_BASE}")
    righe += [f"Profili dei modelli: {file_profili()}", f"Progetti nuovi: {cartella_progetti()}"]
    return righe


if __name__ == "__main__":
    print("\n".join(descrizione()))

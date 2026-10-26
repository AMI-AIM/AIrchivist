"""
Progetto di prova per i test che leggono i profili delle serie (citazioni, cronologia): così non dipendono dal
progetto di ricerca in uso. Nel modulo di test:

    from prova import setUpModule, tearDownModule  # noqa: F401
"""
import os
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent / "test_project"
VARIABILE = "AIRCHIVIST_PROGETTO"
_precedente = None


def _ricarica():
    import profili
    profili.tutti(ricarica=True)


def setUpModule():
    global _precedente
    _precedente = os.environ.get(VARIABILE)
    os.environ[VARIABILE] = str(CARTELLA)
    _ricarica()


def tearDownModule():
    if _precedente is None:
        os.environ.pop(VARIABILE, None)
    else:
        os.environ[VARIABILE] = _precedente
    _ricarica()

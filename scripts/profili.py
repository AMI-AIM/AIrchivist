#!/usr/bin/env python3
"""
Profili di serie (series.ini): lettura unica e regole che dipendono dalla serie (lavoro 12, fase 3).
Il motore resta generico: ciò che vale per una sola testata o raccolta sta nel suo profilo.

Un file appartiene a un profilo per il nome della serie ([SERIES] dell'intestazione = nome della sezione),
altrimenti per la cartella (campo «cartella»: il file sta in quella cartella dentro data, o più in profondità).

Campi usati qui, oltre a quelli descritti in testa a series.ini:
  tipo            periodico | volume: i periodici hanno date di numero; i volumi e le raccolte no (per i documenti
                  delle raccolte vale la data interna, date_interne.py)
  periodo         primo e ultimo numero disponibili, es. 1963-01-01 / 1980-12-31: fine delle fonti per i silenzi
                  della cronologia
  periodicita     quotidiano | settimanale | quindicinale | mensile, con cambi datati: «mensile; 1980: quindicinale»
                  (per collocare nel mese le lacune dei fascicoli indicati per numero, es. PR1967-11)
  gruppo          nome comune di serie da cercare insieme (Hongqi e la sua traduzione Red Flag: gruppo = Hongqi)
  righe_intere    sì = testo digitale, un paragrafo per riga: le forme del nome non si spezzano tra due righe e
                  l'indice può scegliere i file da leggere con certezza
  allinea_con     serie in cui cercare, nei giorni precedenti, i nomi trascritti dove questa serie nomina una
                  persona (esplora_nome); allinea_giorni = quanti giorni (predefinito 21)
"""
import configparser
import datetime as dt
import re
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
_PROFILI = None


def file_serie():
    """series.ini del progetto di ricerca in uso (progetto.py)."""
    from progetto import leggi_config, percorso
    return percorso(leggi_config(), "serie")


def tutti(ricarica=False):
    """{nome della serie: campi} dal series.ini del progetto."""
    global _PROFILI
    if _PROFILI is None or ricarica:
        cp = configparser.ConfigParser(interpolation=None, delimiters=("=",))
        cp.optionxform = str
        try:
            cp.read(file_serie(), encoding="utf-8")
        except configparser.Error:
            pass
        _PROFILI = {s: {k: v.strip() for k, v in cp[s].items()} for s in cp.sections()}
    return _PROFILI


def nome_di(serie="", file=""):
    """Nome del profilo di un file: per serie, altrimenti per cartella (la più specifica); '' se non c'è."""
    pr = tutti()
    if serie in pr:
        return serie
    file = (file or "").replace("\\", "/")
    trovati = [(len(c), n) for n, p in pr.items()
               if (c := (p.get("cartella") or "").strip().strip("/")) and (file == c or file.startswith(c + "/"))]
    return max(trovati)[1] if trovati else ""


def di(serie="", file=""):
    """Campi del profilo di un file ({} se non c'è)."""
    return tutti().get(nome_di(serie, file), {})


def di_passaggio(c):
    """Profilo di un passaggio di passaggi.jsonl / classificati.jsonl (fonte = serie, file = percorso in data)."""
    return di(c.get("fonte", ""), c.get("file", ""))


def e_periodico(serie="", file=""):
    return di(serie, file).get("tipo") == "periodico"


def vero(valore):
    return (valore or "").strip().lower() in ("sì", "si", "yes", "true", "1")


# ---------------------------------------------------------------- gruppi di serie
def gruppo(nome):
    """Nome del gruppo di una serie (il proprio nome se non ne ha)."""
    return tutti().get(nome, {}).get("gruppo") or nome


def serie_breve(serie):
    """Nome con cui l'indice registra una serie: il gruppo, se la serie è un profilo che ne dichiara uno
    (Red Flag -> Hongqi); altrimenti il nome stesso (le raccolte restano col proprio nome)."""
    return gruppo(serie) if serie in tutti() else serie


def serie_del_gruppo(nome):
    """Nomi di serie da cercare insieme a 'nome' (stesso gruppo), compreso 'nome'. Senza profili: {nome}."""
    pr, cercato = tutti(), nome.strip().lower()
    g = next((gruppo(n) for n in pr if cercato in (n.lower(), gruppo(n).lower())), None)
    return {n for n in pr if gruppo(n) == g} if g else {nome.strip()}


# ---------------------------------------------------------------- date
def _data(s):
    try:
        return dt.date.fromisoformat(s.strip())
    except (ValueError, AttributeError):
        return None


def periodo(nome):
    """(primo, ultimo) numero disponibile della serie, come date; (None, None) se il profilo non lo dichiara."""
    parti = re.split(r"\s*[/–]\s*|\s+-\s+", tutti().get(nome, {}).get("periodo", ""))
    return (_data(parti[0]), _data(parti[1])) if len(parti) == 2 else (None, None)


def fine_fonti(serie=None):
    """Ultimo numero disponibile tra i periodici indicati (tutti se None): data o None."""
    nomi = [n for n, p in tutti().items() if p.get("tipo") == "periodico" and (serie is None or n in serie)]
    fini = [f for f in (periodo(n)[1] for n in nomi) if f]
    return max(fini) if fini else None


def periodicita(nome, anno=None):
    """Periodicità della serie nell'anno indicato («mensile; 1980: quindicinale» -> quindicinale dal 1980)."""
    voce = tutti().get(nome, {}).get("periodicita", "")
    corrente = ""
    for parte in [x.strip() for x in voce.split(";") if x.strip()]:
        m = re.fullmatch(r"(\d{4})\s*:\s*(\w+)", parte)
        if not m:
            corrente = parte
        elif anno and anno >= int(m.group(1)):
            corrente = m.group(2)
    return corrente


NUMERI_PER_ANNO = {"settimanale": 52, "quindicinale": 24, "mensile": 12}


def mese_del_numero(nome, anno, numero):
    """Mese probabile del numero N di un anno, dalla periodicità; None se non si può dire."""
    per_anno = NUMERI_PER_ANNO.get(periodicita(nome, anno))
    return min(12, (numero - 1) * 12 // per_anno + 1) if per_anno else None


# ---------------------------------------------------------------- pagine e allineamenti
def pagina_regex(serie="", file=""):
    return di(serie, file).get("pagina_regex", "")


def ultima_pagina(testo, serie="", file=""):
    """Ultima pagina indicata nel testo dalla pagina_regex del profilo ('' se il profilo non ne ha)."""
    rx = pagina_regex(serie, file)
    trovate = re.findall(rx, testo) if rx else []
    return trovate[-1] if trovate else ""


def righe_intere():
    """Serie con un paragrafo per riga (le forme del nome non si spezzano)."""
    return {n for n, p in tutti().items() if vero(p.get("righe_intere"))}


def allineamenti():
    """[(serie d'origine, serie in cui cercare, giorni)] dai campi allinea_con / allinea_giorni."""
    out = []
    for n, p in tutti().items():
        if p.get("allinea_con"):
            giorni = p.get("allinea_giorni", "")
            out.append((n, p["allinea_con"], int(giorni) if giorni.isdigit() else 21))
    return out

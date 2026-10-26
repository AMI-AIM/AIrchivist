#!/usr/bin/env python3
"""
Profili di serie (series.ini): lettura unica e regole che dipendono dalla serie (lavoro 12, fase 3).
Il motore resta generico: ciò che vale per una sola testata o raccolta sta nel suo profilo.

Un file appartiene a un profilo per il nome della serie ([SERIES] dell'intestazione = nome della sezione),
altrimenti per la cartella (campo «cartella»: il file sta in quella cartella dentro data, o più in profondità).

Profilo minimo (lavoro 30): nome della sezione, tipo e lingua. Gli altri campi hanno un valore predefinito
(completa): cartella dentro data dal tipo e dal nome, sigla dei file dalle iniziali del nome; la citazione Chicago
si genera dal tipo (citazioni.py) se il profilo non ha il campo chicago.

Campi usati qui, oltre a quelli descritti in testa a series.ini:
  tipo            periodico | articolo | volume | archivio. periodico: fascicoli (un file per numero), con le date
                  dei numeri; articolo: articoli di una rivista, un file per articolo con autore e titolo; volume:
                  libri e raccolte (per i documenti delle raccolte vale la data interna, date_interne.py);
                  archivio: documenti d'archivio datati (rapporti, lettere), con il fondo e l'archivio
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
TIPI = ("periodico", "articolo", "volume", "archivio")
# cartella predefinita dentro data, per tipo (i periodici in riviste/, come li conta copertura_fonti)
CARTELLE = {"periodico": "riviste", "articolo": "riviste", "volume": "volumi", "archivio": "archivi"}
DATATI = ("periodico", "articolo", "archivio")         # tipi con una data per documento


def slug(s):
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_") or "serie"


def sigla_predefinita(nome):
    """Iniziali delle parole con la maiuscola (Zëri i Popullit -> ZP), al massimo quattro; altrimenti le prime
    lettere del nome."""
    iniziali = "".join(p[0] for p in re.findall(r"[^\W\d_]+", nome) if p[0].isupper())
    import unicodedata
    iniziali = unicodedata.normalize("NFKD", iniziali).encode("ascii", "ignore").decode()
    return (iniziali if len(iniziali) >= 2 else slug(nome).replace("_", "")[:3].upper())[:4]


def completa(nome, p):
    """Profilo con i valori predefiniti dei campi non scritti (profilo minimo: nome, tipo, lingua)."""
    p = dict(p)
    tipo = (p.get("tipo") or "periodico").strip()
    p["tipo"] = tipo
    if not (p.get("cartella") or "").strip():
        p["cartella"] = f"{CARTELLE.get(tipo, 'altre_fonti')}/{slug(nome)}"
    if tipo in DATATI and not (p.get("sigla") or "").strip():
        p["sigla"] = sigla_predefinita(nome)
    return p


def datato(profilo):
    """Vero se i documenti della serie hanno una data ciascuno (dal nome del file, dalla prima pagina)."""
    return (profilo.get("tipo") or "periodico").strip() in DATATI


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
        _PROFILI = {s: completa(s, {k: v.strip() for k, v in cp[s].items()}) for s in cp.sections()}
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

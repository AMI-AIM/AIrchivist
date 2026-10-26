"""
Glossario dei nomi ricavato da entities.ini.

Per ogni scheda: nome di riferimento = titolo della scheda, con il nome per esteso (campo "forma_estesa") per gli
enti indicati da una sigla.
Al modello vengono passate solo le varianti inequivocabili che compaiono nel testo in esame:
  - cinese: forme con punto centrale (nomi di persona), con 《》 (testate), con parentesi (sigle di partito)
            oppure lunghe almeno 6 caratteri;
  - caratteri latini: solo forme con parentesi, es. "Communist Party of Italy (Marxist-Leninist)".
Le forme brevi o generiche (新团结, 红色路线, "New Unity", cognomi isolati) restano escluse.
"""
import configparser
import re

from estrai_occorrenze import is_cjk, normalizza
from schede import forma_estesa


def _univoca(v):
    if is_cjk(v):
        return bool(re.search(r"[·・《》（）()]", v)) or len(re.sub(r"\s", "", v)) >= 6
    return "(" in v and len(v) >= 12


def carica_glossario(path):
    cp = configparser.ConfigParser(interpolation=None, delimiters=("=",))
    cp.optionxform = str
    cp.read(path, encoding="utf-8")
    voci = []
    for sez in cp.sections():
        estesa = forma_estesa(cp, sez)
        nome = f"{sez} ({estesa})" if estesa and estesa not in sez else sez
        nota = cp.get(sez, "note", fallback="").strip()
        nota = re.split(r"(?<=[.;])\s", nota)[0][:180] if nota else ""
        for v in re.split(r"[;；]", cp.get(sez, "varianti", fallback="")):
            v = v.strip()
            if v and _univoca(v):
                voci.append((v, normalizza(v), nome, nota))
    voci.sort(key=lambda x: -len(x[1]))          # prima le forme più lunghe
    return voci


def voci_per_testo(glossario, testo, massimo=25):
    """Righe di glossario pertinenti a un testo: 'forma nel testo = nome di riferimento (nota)'."""
    t = normalizza(testo)
    righe, visti = [], set()
    for v, vn, nome, nota in glossario:
        if vn in t and (v, nome) not in visti:
            visti.add((v, nome))
            righe.append(f"- {v} = {nome}" + (f" ({nota})" if nota and nota != nome else ""))
            if len(righe) >= massimo:
                break
    return righe


def blocco(glossario, testo):
    righe = voci_per_testo(glossario, testo)
    if not righe:
        return ""
    return ("GLOSSARIO (forme che compaiono nel testo e nome da usare in italiano; usa questi nomi nelle traduzioni):\n"
            + "\n".join(righe) + "\n\n")

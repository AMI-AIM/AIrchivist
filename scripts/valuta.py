#!/usr/bin/env python3
"""
Valuta i modelli (e le regole di smistamento) su un caso già classificato a mano.

Uso semplice (fa tutto da solo):
  python valuta.py "Nuova Unità"
      trova la cartella di riferimento in risultati (quella con analisi_manuale.json), crea una cartella
      di prova nuova (prova_<nome>_<data e ora>), fa leggere i passaggi ai modelli configurati in
      config.ini SENZA usare l'archivio unico, e confronta il risultato con la lettura manuale.
  python valuta.py "Nuova Unità" --limite 40     (solo i primi 40 passaggi, per una prova veloce)
  python valuta.py "Nuova Unità" --modelli "glm-4.7; nemotron-3-ultra; dots3"
      prova uno per uno i modelli indicati (parte del nome, come nel catalogo di FreeLLMAPI) e alla fine
      stampa una tabella di confronto. Serve un profilo del router (FreeLLMAPI).
La prova misura lo SMISTAMENTO (pertinente sì/no): traduzione e analisi non vengono fatte, così ogni
modello costa circa una richiesta ogni 6 passaggi.

Uso a passi:
  python valuta.py prepara <cartella_riferimento> <cartella_prova>
  python classifica.py <cartella_prova> entities.ini
  python valuta.py confronta <cartella_riferimento> <cartella_prova>

Metrica decisiva: il RICHIAMO sui pertinenti (quanti ne trova il modello). Un pertinente perso è
peggio di un falso positivo, che si scarta a mano.
"""
import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from collections import Counter
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARTELLA))
try:
    sys.stdout.reconfigure(line_buffering=True)
except AttributeError:
    pass


def carica(p):
    with open(p, encoding="utf-8") as f:
        return [json.loads(r) for r in f if r.strip()]


def semplice(s):
    s = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in s if c.isalnum())


def trova_riferimento(nome, risultati):
    """Cartella dei risultati con analisi_manuale.json che corrisponde al nome (accenti e spazi ignorati)."""
    from archivio import cartelle_risultati
    candidati = [d for d in cartelle_risultati(risultati) if (d / "analisi_manuale.json").exists()]
    # i riferimenti dedicati hanno la precedenza
    candidati.sort(key=lambda d: d.parent.name != "references")
    for d in candidati:
        if semplice(d.name) == semplice(nome):
            return d, candidati
    for d in candidati:
        if semplice(nome) in semplice(d.name):
            return d, candidati
    return None, candidati


def prepara(rif, prova):
    prova.mkdir(parents=True, exist_ok=True)
    for nome in ("passaggi.jsonl", "riepilogo.txt"):
        if (rif / nome).exists():
            shutil.copy2(rif / nome, prova / nome)
    # le prove devono misurare il modello: niente archivio unico in questa cartella
    (prova / ".senza_archivio").write_text("Cartella di prova: classifica.py non usa l'archivio unico.\n",
                                           encoding="utf-8")
    print(f"Pronto. Ora esegui:\n  python classifica.py \"{prova}\" entities.ini")


def confronta(rif, prova):
    gold = json.loads((rif / "analisi_manuale.json").read_text(encoding="utf-8"))
    gold = {k: v[0] for k, v in gold.items() if not k.startswith("_")}
    pred = {c["id"]: c for c in carica(prova / "classificati.jsonl") if not c["analisi"].get("assorbito_da")}
    ids = list(pred)
    if not ids:
        print("Nessun passaggio classificato nella cartella di prova.")
        return
    vero = {i: gold.get(i, "no") for i in ids}              # id non annotati = "no"
    mod = {i: pred[i]["analisi"]["pertinente"] for i in ids}

    pos_veri = [i for i in ids if vero[i] == "sì"]
    trovati = [i for i in pos_veri if mod[i] == "sì"]
    trovati_o_incerti = [i for i in pos_veri if mod[i] in ("sì", "incerto")]
    segnalati = [i for i in ids if mod[i] == "sì"]
    corretti = [i for i in segnalati if vero[i] == "sì"]
    tempi = [pred[i]["analisi"].get("secondi", 0) for i in ids]

    stats = {"passaggi": len(ids), "pertinenti": len(pos_veri),
             "richiamo": (len(trovati_o_incerti), len(pos_veri)), "precisione": (len(corretti), len(segnalati)),
             "persi": [pred[i].get("citazione") or pred[i]["file"] for i in pos_veri if mod[i] == "no"]}
    print(f"\n=== Confronto con la lettura manuale ({rif.name})")
    print(f"Passaggi confrontati: {len(ids)} (pertinenti secondo il riferimento: {len(pos_veri)})")
    print(f"Matrice (riferimento -> modello): {dict(Counter((vero[i], mod[i]) for i in ids))}")
    if pos_veri:
        print(f"RICHIAMO  (pertinenti trovati come 'sì'):            {len(trovati)}/{len(pos_veri)} = "
              f"{100 * len(trovati) / len(pos_veri):.0f}%")
        print(f"RICHIAMO  (pertinenti trovati come 'sì' o 'incerto'): {len(trovati_o_incerti)}/{len(pos_veri)} = "
              f"{100 * len(trovati_o_incerti) / len(pos_veri):.0f}%   (obiettivo: almeno 95%)")
    if segnalati:
        print(f"PRECISIONE ('sì' del modello davvero pertinenti):    {len(corretti)}/{len(segnalati)} = "
              f"{100 * len(corretti) / len(segnalati):.0f}%")
    if tempi:
        print(f"Tempo medio per passaggio: {sum(tempi) / len(tempi):.1f} s")
    modelli = Counter(pred[i]["analisi"].get("modello_smistamento", "?") for i in ids)
    print("\nPer chi ha deciso la pertinenza (modello o regola):")
    for m, n in modelli.most_common():
        sel = [i for i in ids if pred[i]["analisi"].get("modello_smistamento", "?") == m]
        pv = [i for i in sel if vero[i] == "sì"]
        ok = [i for i in pv if mod[i] in ("sì", "incerto")]
        fp = [i for i in sel if mod[i] == "sì" and vero[i] != "sì"]
        print(f"  {m}: {n} passaggi; richiamo {len(ok)}/{len(pv)}" +
              (f" = {100 * len(ok) / len(pv):.0f}%" if pv else "") + f"; falsi positivi {len(fp)}")
    persi = [i for i in pos_veri if mod[i] == "no"]
    if persi:
        print("\nPertinenti PERSI (da esaminare per migliorare prompt o varianti):")
        for i in persi:
            c = pred[i]
            print(f"  {c.get('citazione') or c['file']} | {c['analisi'].get('modello_smistamento', '')} | "
                  f"{c['analisi'].get('motivazione', '')[:120]}")
    falsi = [i for i in segnalati if vero[i] != "sì"]
    if falsi:
        print(f"\nFalsi positivi (il modello dice 'sì', la lettura manuale no): {len(falsi)}")
        for i in falsi[:15]:
            c = pred[i]
            print(f"  {c.get('citazione') or c['file']} | {c['analisi'].get('modello_smistamento', '')} | "
                  f"{c['analisi'].get('motivazione', '')[:120]}")
    return stats


def modelli_disponibili(cfg):
    """Identificativi dei modelli che il router può usare adesso (GET /models?available=true)."""
    from llm import catalogo_router
    return [m.get("id", "") for m in catalogo_router(cfg) if m.get("id")]


def config_per_modello(cfg_path, modello, dest):
    """Copia della configurazione (config.ini più project.ini del progetto in uso) con il router fissato su un
    solo modello e nessun filtro sui modelli ammessi: un profilo «prova» in un models.ini accanto a dest."""
    import configparser
    from llm import RUOLI, leggi_config, profilo_router
    cp = leggi_config(cfg_path)
    prof = configparser.ConfigParser(interpolation=None)
    prof.optionxform = str
    prof["prova"] = dict(profilo_router(cp), servizio="router", modello=modello, modelli_ammessi="")
    file_prof = Path(dest).with_name(Path(dest).stem + "_models.ini")
    with open(file_prof, "w", encoding="utf-8") as f:
        prof.write(f)
    for r in RUOLI:
        cp.remove_option("modello", r)
    cp["modello"]["file_profili"] = str(file_prof)
    cp["modello"]["profilo"] = "prova"
    # la prova misura il modello: niente decisioni per regola sulle forme inequivocabili del nome
    if not cp.has_section("estrazione"):
        cp.add_section("estrazione")
    cp["estrazione"]["forme_sicure"] = "no"
    # tutti i percorsi del progetto in uso, assoluti: la configurazione della prova non dipende da dove sta
    from llm import leggi_config
    from progetto import percorsi_assoluti
    if cp.has_section("progetto"):
        cp.remove_section("progetto")
    if not cp.has_section("percorsi"):
        cp.add_section("percorsi")
    for k, v in percorsi_assoluti(leggi_config(cfg_path)).items():
        cp["percorsi"][k] = v
    with open(dest, "w", encoding="utf-8") as f:
        cp.write(f)


def prova(rif, prova_dir, cfg_file, limite):
    from llm import leggi_config, percorso
    cfg = leggi_config(cfg_file)
    prepara(rif, prova_dir)
    comando = [sys.executable, str(CARTELLA / "classifica.py"), str(prova_dir), str(percorso(cfg, "entita")),
               "--solo-smistamento"]
    if limite:
        comando += ["--limite", str(limite)]
    if cfg_file:
        comando += ["--config", str(cfg_file)]
    print("\nSmistamento dei passaggi (senza archivio, senza traduzione)...\n")
    subprocess.run(comando, cwd=CARTELLA)
    if not (prova_dir / "classificati.jsonl").exists():
        print("Nessun passaggio letto: il modello non ha risposto (vedi i messaggi sopra).")
        return None
    return confronta(rif, prova_dir)


def automatico(nome, limite=None, config=None, modelli=None):
    from llm import leggi_config, percorso
    cfg = leggi_config(config)
    risultati = percorso(cfg, "risultati")
    rif, candidati = trova_riferimento(nome, risultati)
    if not rif:
        sys.exit(f"Nessuna cartella di riferimento per «{nome}» (serve analisi_manuale.json). "
                 f"Disponibili: {', '.join(d.name for d in candidati) or 'nessuna'}")
    ora = f"{dt.datetime.now():%Y%m%d_%H%M}"
    print(f"Riferimento: {rif}")
    if not modelli:
        st = prova(rif, risultati / "trials" / f"prova_{rif.name}_{ora}", config, limite)
        return
    cfg_base = Path(config) if config else CARTELLA / "config.ini"
    try:
        disponibili = modelli_disponibili(cfg)
    except Exception as e:
        sys.exit(f"Non riesco a leggere l'elenco dei modelli dal router ({e}). FreeLLMAPI è acceso e c'è un suo profilo?")
    tabella = []
    for termine in modelli:
        trovati = [m for m in disponibili if termine.lower() in m.lower()]
        if not trovati:
            print(f"\n### «{termine}»: nessun modello disponibile con questo nome. Disponibili: "
                  f"{', '.join(sorted(disponibili))[:1500]}")
            tabella.append((termine, "non trovato", None))
            continue
        modello = sorted(trovati, key=len)[0]
        if len(trovati) > 1:
            print(f"\n(«{termine}» corrisponde a più modelli: {', '.join(trovati[:8])}; uso {modello})")
        print(f"\n################ Modello: {modello}")
        cart = risultati / "trials" / f"prova_{rif.name}_{re.sub(r'[^A-Za-z0-9]+', '-', modello)[:40]}_{ora}"
        cart.mkdir(parents=True, exist_ok=True)
        cfg_m = cart / "config_prova.ini"
        config_per_modello(cfg_base, modello, cfg_m)
        st = prova(rif, cart, cfg_m, limite)
        tabella.append((termine, modello, st))
    print("\n\n================ CONFRONTO DEI MODELLI (smistamento su " + rif.name + ")")
    print(f"{'modello':45} {'passaggi':>8} {'richiamo':>14} {'precisione':>14}")
    for termine, modello, st in tabella:
        if not st:
            print(f"{modello:45} {'—':>8} {'nessun risultato':>14}")
            continue
        r, pr = st["richiamo"], st["precisione"]
        rr = f"{r[0]}/{r[1]} = {100 * r[0] / r[1]:.0f}%" if r[1] else "—"
        pp = f"{pr[0]}/{pr[1]} = {100 * pr[0] / pr[1]:.0f}%" if pr[1] else "—"
        print(f"{modello[:45]:45} {st['passaggi']:>8} {rr:>14} {pp:>14}")
    print("\nObiettivo: richiamo almeno 95%. I modelli che lo raggiungono si possono aggiungere alla catena "
          "«ricerca» in FreeLLMAPI.")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) == 3 and a[0] in ("prepara", "confronta"):
        azione, rif, prova = a[0], Path(a[1]), Path(a[2])
        prepara(rif, prova) if azione == "prepara" else confronta(rif, prova)
    elif a and a[0] not in ("prepara", "confronta", "-h", "--help"):
        import argparse
        ap = argparse.ArgumentParser(description="Valutazione automatica su un caso letto a mano")
        ap.add_argument("nome")
        ap.add_argument("--limite", type=int, default=None)
        ap.add_argument("--modelli", default=None, help="modelli da provare, separati da ';'")
        ap.add_argument("--config", default=None)
        x = ap.parse_args(a)
        automatico(x.nome, x.limite, x.config,
                   [m.strip() for m in (x.modelli or "").split(";") if m.strip()] or None)
    else:
        sys.exit(__doc__)

#!/usr/bin/env python3
"""
Istruzioni per l'IA della chat, consegnate dal server MCP (lavoro 14, fase 4): non dipendono dal client né dal
corpus. Si compongono di tre parti:
  1. regole generali del motore (questo modulo): come usare gli strumenti, come citare, cosa non fare;
  2. fonti del progetto, ricavate dai profili di serie (series.ini) e da project.ini (nome, descrizione);
  3. regole proprie del progetto, dal file instructions.md della cartella del progetto (righe con «#» escluse).

Impostazioni (config.ini o project.ini, sezione [mcp]):
  lingua            lingua delle risposte (predefinita: italiano)
  attesa_massima    secondi di attesa di ogni chiamata ricerca(azione=attendi) (predefinita: 75); va tenuta sotto
                    il tempo massimo che il client concede a uno strumento

Il server le invia nel campo «instructions» di initialize, come prompt MCP «istruzioni» e con lo strumento
«guida», per i client che non mostrano le istruzioni del server al modello.
"""

GENERALI = """Rispondi in {lingua}. Le fonti le conosci solo attraverso gli strumenti di questo server: non le leggi \
tu, le legge la pipeline, che restituisce passaggi con citazioni verificate.

Procedura:
1. schede (azione elenca, con filtro) per trovare il nome esatto della scheda. Per un'entità senza scheda: \
esplora_nome, mostra all'utente forme, conteggi ed esempi e, dopo la sua conferma, schede (azione crea) con le sole \
forme attestate.
2. Per ogni domanda sulle fonti: ricerca (azione avvia, con la domanda dell'utente per intero; con i passaggi già \
letti è rapida), poi ricerca (azione attendi) finché finito è vero. Ogni attesa dura al massimo {attesa} secondi; la \
ricerca continua anche se la chat si chiude e, se le quote dei modelli finiscono, riprende da sola: dillo all'utente.
3. Presenta la risposta della pipeline (risposta_pronta, oppure risposte con azione leggi): puoi riordinarla, \
abbreviarla e tradurla, ma fatti, date, cariche e riferimenti restano quelli; conserva le avvertenze. Non \
ricostruire tu la risposta dai passaggi. passaggi_archivio, apri_fonte e cerca_testo servono a mostrare un \
passaggio o a verificare un punto quando l'utente lo chiede.

Regole:
- Ogni affermazione viene da un passaggio restituito dagli strumenti e si cita con il suo "riferimento" così com'è \
(stile Chicago; la pagina solo se il riferimento la contiene). Mai file né righe nella risposta: "solo_per_apri_fonte" \
serve solo ad apri_fonte e i suoi numeri sono righe di file, non pagine. Mai rimandi tipo [12].
- Per i fatti principali: testo originale invariato, poi «Traduzione:», senza dire chi l'ha fatta.
- Nessun fatto né cifra che non venga dagli strumenti, anche se lo conosci (semmai a parte, come ipotesi da \
verificare). Non spostare date, cariche o attribuzioni da un passaggio a un altro. Se un dato manca, dillo.
- Distingui la data della fonte (pubblicazione) da quella dell'evento riferito, e i dati espliciti dalle inferenze, \
graduate con prudenza.
- Per un periodo preciso avvia la ricerca con dal/al. Prima di interpretare un'assenza usa copertura_fonti; i \
silenzi di entità con molti passaggi incerti dipendono dalla classificazione.
- Se il nome cercato è solo una variante nella scheda di un'altra entità (una persona nella scheda del suo \
partito), dillo: i risultati riguardano tutta quell'entità; filtra con testo_filtro e proponi una scheda propria.
- Se la ricerca si interrompe o la sintesi non è generata, dillo e non scrivere tu la parte mancante; se usi una \
risposta salvata prima, indicane la data.
- Correzioni dell'utente: correggi_passaggio. Nuove forme del nome: varianti (aggiungi), dopo conferma. Nuovo \
materiale: importa (azione avvia, prima con prova se la serie o la scansione è nuova), poi importa (azione stato) \
finché finita; serie nuova: serie (azione elenca, poi crea con i dati che l'utente conferma).
- Usa solo gli strumenti di questo server: niente shell né lettura diretta dei file.
- Applica queste regole senza enunciarle."""


def _righe_progetto(testo):
    """Testo di instructions.md senza le righe di commento («#»)."""
    return "\n".join(r for r in (testo or "").splitlines() if not r.lstrip().startswith("#")).strip()


def fonti(profili_):
    """Elenco delle fonti dai profili di serie: «- Renmin Ribao (periodico, zh, 1963-01-01 / 1980-12-31)»."""
    righe = []
    for nome, p in sorted(profili_.items(), key=lambda x: (x[1].get("tipo") != "periodico", x[0])):
        dettagli = [p.get("tipo") or "", p.get("lingua") or "", p.get("periodo") or ""]
        if p.get("gruppo") and p["gruppo"] != nome:
            dettagli.append(f"gruppo {p['gruppo']}")
        righe.append(f"- {nome} ({', '.join(d for d in dettagli if d)})")
    return righe


def componi(cfg):
    """Istruzioni complete per il progetto in uso."""
    import profili
    from progetto import nome, percorso
    lingua = cfg.get("mcp", "lingua", fallback="italiano")
    attesa = cfg.getint("mcp", "attesa_massima", fallback=75)
    parti = [GENERALI.format(lingua=lingua, attesa=attesa)]
    descr = cfg.get("progetto", "descrizione", fallback="").strip()
    elenco = fonti(profili.tutti())
    parti.append(f"Progetto: {nome(cfg)}" + (f". {descr}" if descr else "") + "\nFonti (profili di serie; la "
                 "copertura reale per anno si controlla con copertura_fonti):\n" + ("\n".join(elenco) or "- nessuna"))
    try:
        proprie = _righe_progetto(percorso(cfg, "istruzioni").read_text(encoding="utf-8"))
    except OSError:
        proprie = ""
    if proprie:
        parti.append("Regole di questo progetto:\n" + proprie)
    return "\n\n".join(parti)

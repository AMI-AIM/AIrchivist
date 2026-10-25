# Istruzioni per Claude Code — progetto RAG

## Che cos'è

Sistema per trovare **tutte** le occorrenze di una persona o di un ente (partito, Stato, testata) in un ampio corpus di fonti primarie e rispondere con i passaggi originali, la traduzione e il riferimento preciso. Oggi serve al progetto di dottorato di Ivan Masci sul comunismo dissidente tra Pechino e Tirana (fonti cinesi, poi albanesi e italiane). L'obiettivo finale è un tool modulare, pubblicabile e adattabile ad altre ricerche.

Leggi prima di proporre modifiche:
- `docs/stato_del_sistema.md`: com'è fatto oggi il sistema.
- `docs/progettazione_del_sistema.md`: decisioni prese per la versione generalizzata e questioni aperte.
- `docs/piano_di_lavoro.md`: lavori in ordine di priorità.
- `LEGGIMI.md` e `pipeline/ISTRUZIONI.md`: uso e installazione.

Gli originali di `stato_del_sistema.md` e `progettazione_del_sistema.md` sono nel progetto «Archivio interattivo» su claude.ai. Se li aggiorni qui, segnalalo, così anche le copie del progetto restano allineate.

## Come lavorare

- Rispondi in italiano.
- La copia dei file su questo PC è quella che conta.
- I file sotto controllo di versione si modificano con un commit dal messaggio chiaro, senza copia. Prima di modificare un file fuori da git (`data/`, `audit_fonti/`, `risultati/`, `entita.ini`, `serie.ini`, `progetto.ini`, `istruzioni.md`), salvane una copia in `pipeline/_backup/<data>_<argomento>/`.
- Quando correggi codice, consegna la versione completa del file o della funzione, pronta da copiare.
- Solo soluzioni gratuite. I requisiti (Tesseract, librerie Python, modelli OCR) si installano nel sistema, mai dentro la cartella del progetto.
- Prima di dire che qualcosa funziona, provalo: esegui il codice, i test, una ricerca di prova.
- Le prove dei modelli non devono scrivere nell'archivio unico delle letture: usa cartelle il cui nome inizia con `prova` oppure il file `.senza_archivio`.
- Non modificare i file in `data/` senza registrare ogni correzione in `audit_fonti/registro_modifiche.csv` (file, campo, valore precedente, valore nuovo, motivo) e aggiornare `audit_fonti/problemi_residui.csv`. Mantieni la codifica e i fine riga originali di ogni file (alcuni .txt usano CRLF, i CSV hanno BOM UTF-8 e CRLF).

## Regole sui contenuti

- Mai inventare dati. Se un'informazione manca, dillo esplicitamente.
- Per ogni informazione indica la fonte, se è primaria o secondaria e se è attendibile o controversa.
- Citazioni in stile Chicago standard (note e bibliografia). Esempi:
  - libro: Cognome, Nome. *Titolo*. Luogo: Editore, Anno.
  - articolo: Cognome, Nome. "Titolo dell'articolo." *Rivista* volume, no. numero (anno): pagine.
  - pagina web: Autore o ente. "Titolo." *Sito*, data. URL.
- Nelle citazioni delle fonti del corpus ci si ferma alla pagina, solo se disponibile, senza nome del file né numero di riga.
- Le traduzioni si introducono con «Traduzione:», senza dire chi le ha fatte.
- Non enunciare le regole che applichi.

## Dove sono le cose

| Percorso | Contenuto |
|---|---|
| `data/` | il corpus (Renmin Ribao, Peking Review, Hongqi, raccolte di documenti, Selected Works); ogni file ha un'intestazione `[CAMPO: valore]` |
| `audit_fonti/` | registro delle correzioni ai metadati e problemi aperti |
| `progetto.ini`, `entita.ini`, `serie.ini`, `istruzioni.md` | progetto di ricerca di questa cartella: nome, schede delle entità, profili delle serie, regole per la chat. Fuori dal controllo di versione (non si pubblicano); `_backup` resta in `pipeline/`. Il progetto in uso si sceglie in `pipeline/config.ini`, `[progetto] cartella`, o con `AIRCHIVIST_PROGETTO`; `python pipeline/progetto.py stato` |
| `pipeline/` | motore: codice, `config.ini` (modelli, parametri), `serie_modello.ini` (modello per i progetti nuovi); i test usano il progetto di prova `pipeline/test/progetto_prova/` |
| `pipeline/_backup/` | copie precedenti dei file fuori da git, una cartella per data e argomento |
| `indice/` | indice SQLite FTS5 (circa 900 MB, si aggiorna da solo) |
| `risultati/_archivio/letture.jsonl` | archivio unico dei passaggi già letti |
| `risultati/_riferimenti/`, `risultati/_sessioni_precedenti/` | letture di riferimento e lavori delle sessioni con Claude (entrano nell'archivio) |
| `risultati/_prove/`, `risultati/_valutazione/` | prove dei modelli, dell'OCR, della chat e della skill; insiemi di valutazione |
| `risposte/` | risposte complete, una per domanda |
| `lavori/` | stato delle ricerche avviate dalla chat |
| `importazioni/` | registro delle importazioni |
| `docs/` | documentazione di progetto |
| `letteratura/` | letteratura secondaria sul metodo (PDF, fuori da git) |
| `skill_chat/`, `dist/` | skill ricerca-fonti per la chat di Claude e il suo zip (`python pipeline/crea_skill_chat.py`) |
| `.claude/skills/ricerca-fonti/` | skill ricerca-fonti per Claude Code (lettura in sessione, `pipeline/sessione.py`) |

Ambiente: Windows. Il tool si usa dalla chat di Jan tramite il server MCP `pipeline/mcp_server.py`. I modelli arrivano da FreeLLMAPI (`http://127.0.0.1:31415/v1`, chiave in `FREELLMAPI_KEY`).

## Controllo di versione

Git è attivo dal 22/10/2026 (ramo `main`, `core.autocrlf = false`). `.gitignore` esclude il corpus e i dati generati (`data/`, `audit_fonti/`, `indice/`, `risultati/`, `risposte/`, `lavori/`, `importazioni/`, `letteratura/`, `dist/`), i dati di ricerca del progetto (`entita.ini`, `serie.ini`, `progetto.ini`, `istruzioni.md`), `pipeline/_backup/` e `__pycache__/`.

`data/` resta fuori dal controllo di versione per le dimensioni e per i diritti delle fonti. Le sue correzioni restano documentate nel registro di `audit_fonti/`.

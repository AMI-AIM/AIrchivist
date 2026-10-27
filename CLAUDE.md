# Istruzioni per Claude Code — progetto RAG

## Che cos'è

Sistema per trovare **tutte** le occorrenze di una persona o di un ente (partito, Stato, testata) in un ampio corpus di fonti primarie e rispondere con i passaggi originali, la traduzione e il riferimento preciso. Oggi serve al progetto di dottorato di Ivan Masci sul comunismo dissidente tra Pechino e Tirana (fonti cinesi, poi albanesi e italiane). L'obiettivo finale è un tool modulare, pubblicabile e adattabile ad altre ricerche.

Leggi prima di proporre modifiche:
- `docs/stato_del_sistema.md`: com'è fatto oggi il sistema.
- `docs/progettazione_del_sistema.md`: decisioni prese per la versione generalizzata e questioni aperte.
- `docs/piano_di_lavoro.md`: lavori in ordine di priorità.
- `README.it.md` e `docs/user_guide.it.md`: uso e installazione.

Gli originali di `stato_del_sistema.md` e `progettazione_del_sistema.md` sono nel progetto «Archivio interattivo» su claude.ai. Se li aggiorni qui, segnalalo, così anche le copie del progetto restano allineate.

## Come lavorare

- Rispondi in italiano.
- La copia dei file su questo PC è quella che conta.
- I file sotto controllo di versione si modificano con un commit dal messaggio chiaro, senza copia. Prima di modificare un file fuori da git (tutto ciò che sta in `projects/`: `data/`, `audit/`, `results/`, `glossary/`, `project.ini`), salvane una copia in `projects/<progetto>/system/backups/<data>_<argomento>/`.
- Quando correggi codice, consegna la versione completa del file o della funzione, pronta da copiare.
- Solo soluzioni gratuite. I requisiti (Tesseract, librerie Python, modelli OCR) si installano nel sistema, mai dentro la cartella del progetto.
- Prima di dire che qualcosa funziona, provalo: esegui il codice, i test, una ricerca di prova.
- Le prove dei modelli non devono scrivere nell'archivio unico delle letture: usa cartelle il cui nome inizia con `prova` oppure il file `.senza_archivio`.
- Non modificare i file in `data/` senza registrare ogni correzione in `audit/changes.csv` (file, campo, valore precedente, valore nuovo, motivo) e aggiornare `audit/open_issues.csv`. Mantieni la codifica e i fine riga originali di ogni file (alcuni .txt usano CRLF, i CSV hanno BOM UTF-8 e CRLF). Le intestazioni del corpus che citano `audit_fonti/registro_modifiche.csv` non si riscrivono: la corrispondenza dei nomi è in `audit/README.md`.

## Regole sui contenuti

- Mai inventare dati. Se un'informazione manca, dillo esplicitamente.
- Per ogni informazione indica la fonte, se è primaria o secondaria e se è attendibile o controversa.
- Citazioni in stile Chicago, 17ª edizione, sistema autore-data, nella forma della voce di bibliografia (non la nota a piè di pagina). Esempi:
  - libro: Cognome, Nome. Anno. *Titolo*. Luogo: Editore.
  - articolo: Cognome, Nome. Anno. "Titolo dell'articolo." *Rivista* volume, no. numero (mese): pagine.
  - quotidiano senza autore: *Testata*. Anno. Giorno mese anno.
  - pagina web: Autore o ente. Anno. "Titolo." *Sito*. Data. URL.
- Nelle citazioni delle fonti del corpus la pagina citata va in coda alla voce («…, p. 3.»), solo se disponibile, senza nome del file né numero di riga.
- Le traduzioni si introducono con «Traduzione:», senza dire chi le ha fatte.
- Non enunciare le regole che applichi.

## Dove sono le cose

Motore (repository, pubblicabile):

| Percorso | Contenuto |
|---|---|
| `scripts/` | motore: moduli Python, `config.ini` (modelli, parametri, progetto in uso), `series_template.ini` (modello per i progetti nuovi) |
| `tests/` | test (`python -m unittest discover -s tests`); progetto di prova in `tests/test_project/` |
| `skills/source-search/` | skill source-search, fonte unica senza nomi di provider (`SKILL.md`, `config.ini`); `skills/readme/`: README delle confezioni |
| `skills/package.py` | confezioni della skill in `skills/build/` (fuori da git): `source-search-claude.zip` per claude.ai, `claude-code/` marketplace con il plugin per Claude Code, `source-search-chatgpt.zip` per ChatGPT |
| `docs/` | documentazione di progetto; per gli utenti, in italiano e in inglese: `quickstart(.it).md` (primi passi), `user_guide(.it).md` (guida d'uso), `troubleshooting(.it).md` (problemi frequenti) |
| `letteratura/` | letteratura secondaria sul metodo (PDF, fuori da git; da spostare fuori dal repository) |

Progetti di ricerca, in `projects/` (fuori da git). Quello in uso si sceglie in `scripts/config.ini`, `[progetto] cartella` (oggi `../projects/dissident_communism`), o con `AIRCHIVIST_PROGETTO`; `python scripts/progetto.py stato` mostra dove stanno i suoi file. Dentro `projects/dissident_communism/`:

| Percorso | Contenuto |
|---|---|
| `project.ini` | nome e descrizione del progetto, impostazioni proprie |
| `glossary/` | `entities.ini` (schede delle entità), `series.ini` (profili delle serie), `instructions.md` (regole per la chat) |
| `sources/` | documenti originali caricati, immutabili (vuota per il corpus attuale) |
| `data/` | il corpus processato (Renmin Ribao, Peking Review, Hongqi, raccolte di documenti, Selected Works); ogni file ha un'intestazione `[CAMPO: valore]` |
| `audit/` | `changes.csv` (correzioni ai metadati), `open_issues.csv` (problemi aperti), `imports.csv` (registro delle importazioni), `checks/` (controlli delle intestazioni); `README.md` con i nomi precedenti |
| `results/archive/readings.jsonl` | archivio unico dei passaggi già letti (`equivalences.json`: nomi equivalenti) |
| `results/searches/` | una cartella per ricerca |
| `results/answers/` | risposte complete, una per domanda |
| `results/references/`, `results/past_sessions/` | letture di riferimento e lavori delle sessioni con Claude (entrano nell'archivio) |
| `results/trials/`, `results/evaluation/` | prove dei modelli, dell'OCR, della chat e della skill; insiemi di valutazione |
| `system/` | `index/sources.sqlite` (indice SQLite FTS5, circa 900 MB, si aggiorna da solo), `jobs/` (ricerche avviate dalla chat), `import_jobs/`, `cache/`, `backups/` (copie precedenti dei file fuori da git, una cartella per data e argomento) |

Ambiente: Windows. Il tool si usa dalla chat di Jan tramite il server MCP `scripts/mcp_server.py`. I modelli arrivano da FreeLLMAPI (`http://127.0.0.1:31415/v1`, chiave in `FREELLMAPI_KEY`).

## Controllo di versione

Git è attivo dal 22/10/2026 (ramo `main`, `core.autocrlf = false`). `.gitignore` esclude i progetti di ricerca (`projects/`: corpus, schede, serie, risultati, indice, copie di sicurezza), `letteratura/`, `skills/build/` e `__pycache__/`.

I progetti restano fuori dal controllo di versione per le dimensioni e per i diritti delle fonti. Le correzioni a `data/` restano documentate in `audit/` del progetto.

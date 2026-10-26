# Riorganizzazione della cartella

Istruzioni per Claude Code (26/10/2026). Decisioni di Ivan:
- nomi di cartelle e file in inglese;
- progetti di ricerca dentro il repository, in `projects/`, esclusi da git;
- per ora si rinominano **solo cartelle e file**. Codice, nomi dei moduli, funzioni, messaggi, campi delle schede e comandi restano in italiano: la traduzione è un lavoro successivo, prima della pubblicazione.



## 1. Struttura di arrivo

```
AIrchivist/                        repository (pubblicabile)
  scripts/                         motore: moduli .py, config.ini, series_template.ini
  tests/                           test; tests/test_project/ (progetto di prova)
  skills/                          fonte della skill unica + package.py
    build/                         zip generati (fuori da git)
  docs/
  README.md, README.it.md, LICENSE, requirements.txt, CLAUDE.md, .claude/, .gitignore
  projects/                        progetti di ricerca (fuori da git)
    dissident_communism/           il progetto di Ivan (nome modificabile)
      project.ini
      glossary/                    entities.ini, series.ini, instructions.md
      sources/                     documenti originali caricati, immutabili
      data/                        documenti processati (.txt con intestazione)
      audit/                       changes.csv, open_issues.csv, checks/
      results/
        archive/                   archivio unico delle letture
        searches/                  una cartella per ricerca
        answers/                   risposte complete
        references/                letture di riferimento
        past_sessions/             lavori delle sessioni con Claude
        trials/                    prove di modelli, OCR, chat, skill
        evaluation/                insiemi di valutazione
      system/                      index/, jobs/, backups/ (rigenerabili o temporanei)
```



## 2. Mappa dei percorsi

### Motore (con `git mv`, per conservare la storia)

| Oggi | Dopo |
|---|---|
| `pipeline/*.py` | `scripts/*.py` |
| `pipeline/config.ini` | `scripts/config.ini` |
| `pipeline/serie_modello.ini` | `scripts/series_template.ini` |
| `pipeline/test/` | `tests/` |
| `pipeline/test/progetto_prova/` | `tests/test_project/` (con i file interni rinominati come un progetto vero: `project.ini`, `glossary/...`) |
| `pipeline/ISTRUZIONI.md` | `docs/user_guide.it.md` |
| `LEGGIMI.md` | `README.it.md` |
| `pipeline/crea_skill_chat.py` | `skills/package.py` (sarà esteso nella fase C di `roadmap_skill.md`) |
| `skill_chat/` | `skills/source-search/` (punto di partenza della skill unica; il campo `name` di `SKILL.md` diventa `source-search`) |
| `.claude/skills/ricerca-fonti/` | resta fino alla fase C di `roadmap_skill.md`, che la elimina |
| `dist/` | eliminata: `package.py` scrive in `skills/build/` (fuori da git) |
| `pipeline/__pycache__/` | eliminata |

### Progetto di ricerca (con `mv`, fuori da git)

| Oggi | Dopo (in `projects/dissident_communism/`) |
|---|---|
| `progetto.ini` | `project.ini` |
| `entita.ini` | `glossary/entities.ini` |
| `serie.ini` | `glossary/series.ini` |
| `istruzioni.md` | `glossary/instructions.md` |
| `data/` | `data/` |
| — | `sources/` (nuova, vuota: vedi sezione 4) |
| `audit_fonti/registro_modifiche.csv` | `audit/changes.csv` |
| `audit_fonti/problemi_residui.csv` | `audit/open_issues.csv` |
| `importazioni/controllo_*.csv` | `audit/checks/` |
| `importazioni/registro.csv` (quando esiste) | `audit/imports.csv` |
| `indice/fonti.sqlite` | `system/index/sources.sqlite` |
| `lavori/` | `system/jobs/` |
| `pipeline/_backup/` | `system/backups/` |
| `risultati/_archivio/` | `results/archive/` |
| `risultati/_archivio/letture.jsonl` | `results/archive/readings.jsonl` |
| `risultati/_archivio/equivalenze.json` | `results/archive/equivalences.json` |
| `risultati/_archivio/varianti_scartate.json` (quando esiste) | `results/archive/rejected_variants.json` |
| `risultati/_archivio/riattribuzione_*.csv`, `date_sospette_*.csv` | `results/archive/` (nomi invariati: sono file generati) |
| `risultati/<ricerca>/` | `results/searches/<ricerca>/` |
| `risultati/_riferimenti/` | `results/references/` |
| `risultati/_sessioni_precedenti/` | `results/past_sessions/` |
| `risultati/_prove/` | `results/trials/` |
| `risultati/_valutazione/` | `results/evaluation/` |
| `risposte/` | `results/answers/` |

### Fuori dal sistema

- `letteratura/`: letteratura secondaria, non materiale del tool. Va spostata fuori dal repository, in una cartella che Ivan indicherà. Fino ad allora resta dov'è, esclusa da git.

### Cosa NON si rinomina in questa fase

- I file generati dentro le cartelle delle ricerche (`passaggi.jsonl`, `classificati.jsonl`, `risposta.md`, `rapporto.md`, `riepilogo.txt`, `non_letti.json`, `entita_ricerca.ini`, `lotti/`): sono il contratto tra i moduli e cambiano con la traduzione del codice.
- I nomi delle cartelle delle singole ricerche e delle risposte (derivano dai nomi delle entità e dalle domande).
- Le chiavi di `config.ini` e `project.ini` (`[percorsi]`, `dati`, `risultati`...) e i campi delle schede (`varianti`, `forme_ambigue`...).
- Il contenuto dei file del corpus. Molte intestazioni contengono il testo «vedi audit_fonti/registro_modifiche.csv» in `METADATA_SOURCE`: **non si riscrivono**. Riscriverle sposterebbe le posizioni dei passaggi e farebbe ricostruire l'indice per migliaia di file. Al loro posto, un file `audit/README.md` dichiara la corrispondenza tra i nomi vecchi e i nuovi.



## 3. Ordine delle operazioni

1. **Condizioni di partenza.**
   - Nessuna ricerca in corso (`lavori/` senza processi attivi); Jan chiuso o server «Pipeline» fermo; FreeLLMAPI non serve.
   - `git status` pulito; nuovo ramo `riorganizzazione`.
   - Copia di sicurezza dei file piccoli e non rigenerabili fuori da git: `risultati/_archivio/`, `entita.ini`, `serie.ini`, `progetto.ini`, `istruzioni.md`, `audit_fonti/`. `data/` e `indice/` si spostano senza modifiche: non serve copiarli.
2. **Motore.** `git mv` secondo la mappa. Poi il codice:
   - `progetto.py`: posizioni predefinite (`PERCORSI`) secondo la nuova struttura; nomi `project.ini`, `glossary/entities.ini`, `glossary/series.ini`, `glossary/instructions.md`, `audit/changes.csv`, `audit/open_issues.csv`, `system/index/sources.sqlite`, `system/jobs`, `system/backups`, `results/answers`, `audit/checks`; `progetto.py nuovo` crea la nuova struttura. La «disposizione storica» senza progetto (percorsi ricavati dalla cartella `pipeline`) si toglie: senza progetto scelto il motore lo dice e indica `progetto.py nuovo`.
   - `archivio.py`: `NOME`, `SOTTOCARTELLE`, `PROVE` e `letture.jsonl` secondo la mappa; le ricerche si cercano in `results/searches/`. Stessa cosa in `schede.py` (riga con `_archivio/letture.jsonl`) e `varianti.py` (`varianti_scartate.json`).
   - Tutti i riferimenti a `pipeline/`, `_prove`, `_valutazione`, `_riferimenti`, `_sessioni_precedenti`, `audit_fonti` nei moduli e nei test (almeno: `archivio.py`, `chat.py`, `mcp_server.py`, `pagine_xml.py`, `progetto.py`, `prova_chat.py`, `prova_ocr.py`, `schede.py`, `sintesi.py`, `valuta.py`, `valutazione.py`, `varianti.py`, `test_anno_fonte.py`, `test_chat.py`, `test_citazioni_provenienza.py`, `test_estrai_occorrenze.py`, `test_progetto.py`, `test_sessione.py`). Cercali con `grep`, non a memoria.
   - `installa.py client`: percorso di `scripts/mcp_server.py` nelle configurazioni dei client.
   - Test: importazione dei moduli da `scripts/` (non più dalla cartella superiore).
   - `skills/package.py`: sorgente `skills/source-search/`, moduli da `scripts/`, uscita in `skills/build/`.
3. **Progetto.** Crea `projects/dissident_communism/` e sposta i file secondo la mappa con `mv` (stesso disco: nessuna copia). Scrivi `audit/README.md` con la corrispondenza dei nomi.
4. **Configurazione.** `scripts/config.ini`, `[progetto] cartella = ../projects/dissident_communism`. Aggiorna `AIRCHIVIST_PROGETTO` dove è impostata.
5. **`.gitignore`.** Escludi `projects/`, `skills/build/`, `__pycache__/`, `letteratura/`; togli le righe dei percorsi che non esistono più.
6. **Documentazione.** Aggiorna percorsi e nomi in `CLAUDE.md` (tabella «Dove sono le cose»), `README.md`, `README.it.md`, `docs/user_guide.it.md`, `docs/stato_del_sistema.md`, `docs/piano_di_lavoro.md`, `docs/roadmap_skill.md`, `docs/schede_entita.md`. I file di `system/backups/` restano come sono.



## 4. sources/: gli originali

La cartella `sources/` nasce vuota per il corpus attuale: i suoi originali (PDF, pagine web, file di MIA e CIA) non sono nella cartella di lavoro. Regola per le importazioni future, da applicare in `importa.py`:
- l'originale importato (PDF, scansione, esportazione PAGE/ALTO, Word, TXT) si copia in `sources/`, con la stessa struttura di sottocartelle di `data/`, e non si modifica più;
- quando l'acquisizione è già un testo, anche quel testo va in `sources/`, intatto;
- `SOURCE_FILE` e `SOURCE_HASH` nell'intestazione del file processato rimandano all'originale in `sources/`.

Il recupero degli originali del corpus attuale (dove esistono) non fa parte di questa riorganizzazione.



## 5. Verifiche

Nessun passo si considera fatto senza queste prove:

1. Tutti i test passano (`python -m unittest discover -s tests`), con e senza PyMuPDF se possibile.
2. `python scripts/progetto.py stato`: tutti i percorsi risolti nella nuova struttura ed esistenti.
3. `python scripts/installa.py controlla`: nessun requisito necessario mancante.
4. Indice: l'aggiornamento incrementale non trova file nuovi né modificati (i percorsi nell'indice sono relativi a `data/`). Se li trova, capire perché prima di ricostruirlo.
5. Archivio: stesso numero di letture di prima (10.840 al 22/10, più quelle aggiunte dopo); `python scripts/archivio.py stato` identico.
6. Ricerca di prova senza modelli: `ricerca.py "Jacques Grippa" --solo-estrazione`, stesso numero di passaggi di prima; poi una ricerca completa su un'entità già tutta in archivio: risposta identica, salvo i percorsi nella sezione tecnica.
7. Server MCP avviato in stdio; configurazione di Jan e di Claude Desktop rifatta con `installa.py client`; una domanda di prova in Jan.
8. `skills/package.py` produce lo zip in `skills/build/`.

Poi commit sul ramo `riorganizzazione`, unione in `main`, annotazione in `stato_del_sistema.md` (nuova struttura, mappa dei percorsi, esito delle verifiche).

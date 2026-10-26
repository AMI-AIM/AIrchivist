# Ricerca nelle fonti — guida rapida

Sistema per trovare **tutte** le occorrenze di una persona, un partito o una testata nelle fonti primarie
(Renmin Ribao, Peking Review, Hongqi/Red Flag, raccolte di documenti, Selected Works) e rispondere con i
passaggi originali, la traduzione e il riferimento esatto. Nuovo materiale (anche scansioni in PDF, con OCR)
si aggiunge con `scripts\importa.py` o chiedendo in Jan.

## Installazione

Serve Python 3.10 o successivo (quello di python.org). I requisiti si installano nel sistema, mai dentro la
cartella. Dalla cartella del repository:

```
python scripts\installa.py librerie
python scripts\installa.py modello
python scripts\installa.py controlla
python scripts\installa.py client jan
```

- `librerie`: installa le librerie facoltative di `requirements.txt` (PyMuPDF, per importare i PDF).
- `modello`: procedura guidata per il modello che legge i passaggi (Ollama, un servizio con una chiave, API di
  Anthropic o FreeLLMAPI); si cambia quando si vuole con `installa.py modello usa <profilo>`.
- `controlla`: verifica Python, l'indice FTS5, il modello scelto (chiave e raggiungibilità), il progetto
  in uso, PyMuPDF, Tesseract e le lingue OCR richieste dalle serie. Se manca qualcosa di necessario, lo dice.
- `client`: mostra cosa scrivere nel client per collegare il server MCP (`jan`, `claude`, `lmstudio`, `json`);
  con `--scrivi` aggiunge o aggiorna da sé la voce nel file del client (copia di sicurezza, conferma prima di
  scrivere); `client --verifica` controlla che il server risponda come lo avvierebbe il client.

## Come si usa

1. Avvia il servizio del modello scelto, se gira sul tuo PC (**FreeLLMAPI** od Ollama).
2. Apri **Jan**, nuova chat con l'assistente «Ricerca fonti» e il modello `auto:chat`.
3. Scrivi la domanda, per esempio «Cosa dicono le fonti di Jacques Grippa nel 1964?».

Jan usa gli strumenti del server MCP «Pipeline» (`scripts\mcp_server.py`). Con questi:
- cerca la scheda dell'entità;
- consulta i passaggi già letti oppure avvia la ricerca completa;
- risponde con originali, traduzioni e riferimenti.

## Dove sono le cose

Il repository contiene il motore:

| Cartella | Contenuto |
|---|---|
| `scripts` | programmi, `config.ini` (profilo di modello in uso, parametri, progetto in uso), `models_template.ini` (esempi di profili di modello) e `series_template.ini` (modello per i progetti nuovi) |
| `tests` | test automatici e progetto di prova (`tests\test_project`) |
| `skills` | skill source-search, scritta una volta sola (`source-search`), i README delle confezioni (`readme`) e `package.py`, che produce le confezioni in `skills\build`: zip per claude.ai, plugin per Claude Code, zip per ChatGPT (ognuna con il suo `README.md`) |
| `docs` | documentazione di progetto: stato, progettazione, piano di lavoro, schede delle entità, guida d'uso (`user_guide.it.md`) |
| `letteratura` | letteratura secondaria sul metodo |
| `projects` | i progetti di ricerca, fuori dal controllo di versione |

Ogni progetto di ricerca (qui `projects\dissident_communism`) ha la stessa struttura:

| Cartella | Contenuto |
|---|---|
| `project.ini` | nome e impostazioni del progetto. Per un'altra ricerca: `python scripts\progetto.py nuovo projects\<nome>` (vedi `docs\user_guide.it.md`, «Progetti di ricerca») |
| `glossary` | schede delle entità (`entities.ini`), serie di fonti (`series.ini`) e regole per la chat (`instructions.md`) |
| `sources` | documenti originali caricati, che non si modificano |
| `data` | le fonti processate |
| `audit` | registro delle correzioni fatte ai metadati delle fonti (`changes.csv`), lacune ancora aperte (`open_issues.csv`), registro delle importazioni (`imports.csv`) e controlli delle intestazioni (`checks`) |
| `results\archive` | i passaggi già letti (non vengono mai riletti) |
| `results\searches` | una cartella per ogni ricerca |
| `results\answers` | tutte le risposte complete, una per domanda |
| `results\references` | letture di riferimento per provare i modelli |
| `results\past_sessions` | lavori delle sessioni con Claude |
| `results\trials` | prove dei modelli, dell'OCR, della chat e della skill |
| `results\evaluation` | insiemi di riferimento verificati a mano e misure di precisione e richiamo |
| `system` | indice di ricerca delle fonti (`index`), stato e registro di ogni ricerca avviata dalla chat (`jobs`), copie dei file prima delle modifiche (`backups`) |

## Per approfondire

`docs\user_guide.it.md` spiega:
- la configurazione di FreeLLMAPI e di Jan;
- le schede delle entità e le varianti dei nomi;
- l'importazione di nuove fonti (OCR);
- la valutazione dei modelli;
- i problemi frequenti.

In inglese: `README.md`.

## Licenza

Il codice è distribuito con la licenza GNU Affero General Public License, versione 3 (`LICENSE`). Chi offre
una versione modificata come servizio in rete, anche come server MCP usato da altri, deve renderne disponibile il
codice. La licenza non riguarda le fonti del corpus, che restano soggette ai propri diritti.

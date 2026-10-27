# AIrchivist — ricerca nelle fonti

Sistema per trovare **tutte** le occorrenze di una persona o di un ente (partito, Stato, testata) in un ampio
corpus di fonti primarie e rispondere con i passaggi originali, la traduzione e il riferimento esatto, con
citazioni Chicago autore-data fino alla pagina. La ricerca gira in Python sul tuo computer; i modelli linguistici
(gratuiti, locali o a pagamento, a tua scelta) leggono solo i passaggi. Le domande si fanno da un client di chat
collegato al server MCP del motore (Jan, Claude Desktop, LM Studio) o da riga di comando. Funziona su Windows,
macOS e Linux.

Nato per un progetto di dottorato sul comunismo dissidente tra Pechino e Tirana (fonti cinesi, poi albanesi e
italiane), è pensato per adattarsi ad altre ricerche: le fonti si importano da PDF, scansioni (con OCR), `.txt` ed
esportazioni PAGE/ALTO XML di Transkribus o eScriptorium.

## Per cominciare

- [`docs/quickstart.it.md`](docs/quickstart.it.md): dall'installazione alla prima risposta in circa 15 minuti.
- [`docs/user_guide.it.md`](docs/user_guide.it.md): la guida completa.
- [`docs/troubleshooting.it.md`](docs/troubleshooting.it.md): problemi frequenti.

In inglese: [`README.md`](README.md), [`docs/quickstart.md`](docs/quickstart.md),
[`docs/user_guide.md`](docs/user_guide.md), [`docs/troubleshooting.md`](docs/troubleshooting.md).

## Installazione

Serve Python 3.10 o successivo (quello di python.org, o su macOS di Homebrew). I requisiti si installano nel
sistema, mai dentro la cartella. Dalla cartella `scripts` del repository (su macOS e Linux, `python3`):

```
python installa.py inizia
```

`inizia` guida i passi per la prima volta (ambiente, modello, primo progetto, chat, riepilogo); si possono fare
anche uno per volta:

```
python installa.py librerie
python installa.py modello
python installa.py controlla
python installa.py client jan --scrivi
```

- `librerie`: installa le librerie facoltative di `requirements.txt` (PyMuPDF, per importare i PDF).
- `modello`: procedura guidata per il modello che legge i passaggi (Ollama, un servizio con una chiave, API di
  Anthropic o FreeLLMAPI); si cambia quando si vuole con `installa.py modello usa <profilo>`.
- `controlla`: verifica Python, l'indice FTS5, il modello scelto (chiave e raggiungibilità), il progetto
  in uso, PyMuPDF, Tesseract e le lingue OCR richieste dalle serie. Se manca qualcosa di necessario, lo dice e
  indica il comando per il sistema in uso.
- `client`: mostra cosa scrivere nel client per collegare il server MCP (`jan`, `claude`, `lmstudio`, `json`);
  con `--scrivi` aggiunge o aggiorna da sé la voce nel file del client (copia di sicurezza, conferma prima di
  scrivere); `client --verifica` controlla che il server risponda come lo avvierebbe il client.

## Come si usa

1. Importa le fonti: `python importa.py proponi <cartella>` scrive una tabella di revisione dei metadati da
   controllare in Excel o LibreOffice, `python importa.py applica <tabella>` importa.
2. Nel client di chat, scrivi la domanda, per esempio «Cosa dicono le fonti di Jacques Grippa nel 1964?».
3. L'assistente propone le forme del nome attestate nelle fonti; dopo la tua conferma avvia la ricerca e, alla
   fine, indica il documento della risposta (HTML, da aprire nel browser e stampare).

Senza chat: scheda dell'entità in `glossary/entities.ini` del progetto e `python ricerca.py "Nome" --apri`.

## Dove sono le cose

Il repository contiene il motore:

| Cartella | Contenuto |
|---|---|
| `scripts` | programmi, `config.ini` (profilo di modello in uso, parametri, progetto in uso), `models_template.ini` (esempi di profili di modello) e `series_template.ini` (modello per i progetti nuovi) |
| `tests` | test automatici e progetto di prova (`tests/test_project`) |
| `skills` | skill source-search, scritta una volta sola (`source-search`), i README delle confezioni (`readme`) e `package.py`, che produce le confezioni in `skills/build`: zip per claude.ai, plugin per Claude Code, zip per ChatGPT (ognuna con il suo `README.md`) |
| `docs` | primi passi, guida d'uso, problemi frequenti (in italiano e in inglese); documenti di progetto: stato, progettazione, piano di lavoro, schede delle entità |
| `projects` | i progetti di ricerca, fuori dal controllo di versione |

Ogni progetto di ricerca (`projects/<nome>`) ha la stessa struttura:

| Cartella | Contenuto |
|---|---|
| `project.ini` | nome e impostazioni del progetto. Per un'altra ricerca: `python progetto.py nuovo ../projects/<nome>` (vedi `docs/user_guide.it.md`, «Progetti di ricerca») |
| `glossary` | schede delle entità (`entities.ini`), serie di fonti (`series.ini`) e regole per la chat (`instructions.md`) |
| `sources` | documenti originali caricati, che non si modificano |
| `data` | le fonti processate |
| `audit` | registro delle correzioni fatte ai metadati delle fonti (`changes.csv`), lacune ancora aperte (`open_issues.csv`), registro delle importazioni (`imports.csv`), tabelle di revisione e controlli delle intestazioni (`checks`) |
| `results/archive` | i passaggi già letti (non vengono mai riletti) |
| `results/searches` | una cartella per ogni ricerca |
| `results/answers` | tutte le risposte complete delle ricerche avviate dalla chat, una per domanda |
| `results/references` | letture di riferimento per provare i modelli |
| `results/past_sessions` | lavori delle sessioni assistite |
| `results/trials` | prove dei modelli, dell'OCR, della chat e della skill |
| `results/evaluation` | insiemi di riferimento verificati a mano e misure di precisione e richiamo |
| `system` | indice di ricerca delle fonti (`index`), stato e registro di ogni ricerca avviata dalla chat (`jobs`), copie dei file prima delle modifiche (`backups`) |

## Licenza

Il codice è distribuito con la licenza GNU Affero General Public License, versione 3 (`LICENSE`). Chi offre
una versione modificata come servizio in rete, anche come server MCP usato da altri, deve renderne disponibile il
codice. La licenza non riguarda le fonti del corpus, che restano soggette ai propri diritti.

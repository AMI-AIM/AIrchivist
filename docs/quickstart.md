# AIrchivist: quickstart

From installation to your first answer in about 15 minutes of active work, on Windows, macOS or Linux. You need:
- a few documents of your own: PDFs (with text or scanned), page scans or `.txt` files. Two or three PDFs are
  enough for a first try;
- a model to read the passages: a free key for a service (Groq, Google Gemini, OpenRouter) or Ollama on your
  computer;
- optional, to ask questions in a conversation: a chat client that supports MCP servers (Jan, Claude Desktop,
  LM Studio).

The full guide is [`user_guide.md`](user_guide.md); if something goes wrong, see
[`troubleshooting.md`](troubleshooting.md). The system's commands, messages and field names are in Italian; this
page tells you what each one means.

## 1. Install Python (and, if you will need it, Tesseract)

| | Python 3.10 or later | Tesseract (only for scans) |
|---|---|---|
| Windows | https://www.python.org/downloads/ — during installation tick **"Add python.exe to PATH"** | `winget install -e --id UB-Mannheim.TesseractOCR`; tick the languages you need in the installer |
| macOS | https://www.python.org/downloads/ or `brew install python` | `brew install tesseract tesseract-lang` |
| Linux | usually already there (`python3 --version`); otherwise `sudo apt install python3` | `sudo apt install tesseract-ocr tesseract-ocr-<language>` (e.g. `tesseract-ocr-fra`) |

On macOS and Linux the command may be `python3` rather than `python`: use that in the commands below. After an
installation, close and reopen the terminal. Everything is installed system-wide, never inside the engine folder.

## 2. Download AIrchivist

With git:
```
git clone <repository URL> AIrchivist
cd AIrchivist/scripts
```
Or download the repository as a `.zip` archive, extract it wherever you like and open a terminal in its `scripts`
folder. Every command on this page is run from there.

## 3. Guided setup

```
python installa.py inizia
```

(`installa` = install, `inizia` = start.) Five steps; each asks one question at a time and proposes an answer
(press Enter to accept it). Answers are `s` (yes) or `n` (no), or the number of an option:
1. **Environment** (*Controllo dell'ambiente*): checks Python and SQLite. PyMuPDF (for PDFs) and Tesseract are
   optional; if PyMuPDF is missing: `python installa.py librerie`.
2. **Model** (*Modello che legge i passaggi*): choose the service. The simplest is option 2, "a service with a
   single key" (*un servizio con una sola chiave*), for example Groq: the procedure tells you where to create the
   free key, asks for it (it is not shown as you type), saves it as an environment variable of your user, lists
   the models the service offers and runs a test request. Ollama needs no key.
3. **First project** (*Il tuo primo progetto*): the name of your research and its folder (the proposed one,
   inside `projects/`, is fine).
4. **Chat** (*Collegamento con la chat*): choose the client you use (Jan, Claude Desktop, LM Studio) or "none for
   now" (*nessuno, per ora*). The system shows what will change in the client's configuration file and writes
   only after you confirm, with a backup copy. Jan must be closed while the file is written.
5. **Summary** (*Riepilogo*): "Tutto pronto" (all set) if nothing is missing.

You can stop and rerun `inizia` whenever you like: it does not redo completed steps.

## 4. Import your documents

Put the documents in a folder (for example `documents_to_import` in your home folder), then:

```
python importa.py proponi <documents folder>
```

(`importa` = import, `proponi` = propose.) The system reads the files without importing them and writes a table,
`audit/review_<date>.csv` in the project folder: one row per document, with the proposed series (*serie*: the
journal, newspaper or book), date (*data*), title (*titolo*), author (*autore*), language (*lingua*) and pages
(*pagine*). Open it in Excel or LibreOffice: the **da_controllare** (to check) column explains the doubts. Fix
what is wrong or missing (above all the series names and the language: `en`, `fr`, `it`, `sq`, `zh`...), write
`no` in the `importa` column to skip a document, save, and then:

```
python importa.py applica <path of the table> --prova
python importa.py applica <path of the table>
```

(`applica` = apply, `--prova` = dry run.) The first command checks the table and says what it would do; the second
imports (with OCR where needed) and builds the source index.

## 5. Your first question

### From the chat

Restart the client if it was open. Check that the "airchivist" server is switched on in the client's MCP settings
and that the chat model can use tools (in Jan: **Tools** enabled on the model, **Web Search** off). Then write, for
example:

> What do the sources say about Google Books?

The assistant searches the sources for the forms of the name that are actually attested (with counts and examples)
and shows them to you: confirm the right ones. The search starts and the assistant follows its progress; a search
over a few documents takes a few minutes. When it is over you get a summary and the path of the **answer
document**, an `.html` file to open in your browser: original passages, translation, citations with the page,
limits and coverage. Translations and summaries in the answer are in Italian for now. The chat assistant answers in
Italian unless you set `lingua = English` in `scripts/config.ini`, section `[mcp]`.

### Without a chat client

Write the entity card (*scheda*) in `glossary/entities.ini` in the project folder, with the forms of the name the
search must find:

```
[Google Books]
tipo = organizzazione
varianti = Google Books
```

(`tipo` = type: `persona`, `organizzazione`, `testata` for a newspaper, `stato`, `altro`; `varianti` = the forms
of the name, separated by `;`.) Then:

```
python ricerca.py "Google Books" --apri
```

(`ricerca` = search, `--apri` = open.) The search extracts the passages, has the model read them and finally opens
the answer document (in Italian, like the chat answers) in your browser (with a free service and a few documents,
two or three minutes). The document
stays in `results/searches/<name>/risposta.html` in the project; answers to searches started from the chat are
also collected in `results/answers/`.

## What next

- More documents: repeat step 4 with a new folder.
- Change the model that reads the passages: `python installa.py modello` (new profile) and
  `python installa.py modello usa <profile>`.
- Several projects, citations, Transkribus or eScriptorium exports, measuring how reliable the models are: the
  [full guide](user_guide.md).

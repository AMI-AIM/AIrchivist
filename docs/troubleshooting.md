# Troubleshooting

Problems met in real trials of the system, with their solution. For almost everything, the first check is:

```
python installa.py controlla
```

It says what is missing and how to fix it; it exits with status 1 if a required item is missing. Commands are run
in the engine's `scripts` folder; on macOS and Linux the command may be `python3`. Messages are in Italian: the
quoted Italian text below is what you will see.

## Installation

- **"python" is not recognised** (Windows): Python is not on the PATH. Reinstall it ticking "Add python.exe to
  PATH", or use `py` instead of `python`. Close and reopen the terminal after installing.
- **"SQLite con FTS5: FTS5 non disponibile"** (FTS5 not available): the Python in use was built without SQLite's
  full-text search. Use the python.org build (or Homebrew's on macOS), which includes it.
- **`installa.py librerie` fails with "externally-managed-environment"** (Debian, Ubuntu and other recent Linux
  distributions): the system does not let pip install libraries into the system Python. Install PyMuPDF from the
  distribution's packages: `sudo apt install python3-fitz`.
- **"Tesseract non trovato"** (not found): install it (Windows `winget install -e --id UB-Mannheim.TesseractOCR`,
  macOS `brew install tesseract tesseract-lang`, Linux `sudo apt install tesseract-ocr`) and reopen the terminal;
  if it lives in a non-standard folder, give its path in `config.ini`, section `[ocr]`, key `tesseract`.
- **OCR languages missing** (`controlla` lists those the project's series need): on Windows rerun the Tesseract
  installer and tick the languages; on macOS `tesseract-lang` contains them all; on Linux
  `sudo apt install tesseract-ocr-<code>` (e.g. `tesseract-ocr-sqi` for Albanian). Alternatively copy
  `<code>.traineddata` from https://github.com/tesseract-ocr/tessdata_best into Tesseract's `tessdata` folder.

## The model that reads the passages

- **The model test fails with "il servizio non trova il modello"** (the service cannot find the model): that model
  name does not exist (any more) at the service; free services often retire models. Create another profile with
  `python installa.py modello`: once it has the key, the procedure lists the models the service really offers.
- **"Manca la chiave" or "variabile … assente"** (key or variable missing): the environment variable holding the
  key is not visible in the terminal (or chat client) in use. After saving it (Windows `setx NAME "..."`; macOS and
  Linux a line `export NAME="..."` in `~/.zprofile` or `~/.profile`) close and reopen the terminal and restart the
  chat client: programs that were already open do not see new variables.
- **Error 401 or 403**: wrong or expired key. **Error 404**: model retired. Check with
  `python installa.py modello prova <profile>`.
- **"Il profilo di modello … non esiste"** (the model profile does not exist): the name chosen in `[modello]` of
  `config.ini` or `project.ini` is not in `models.ini`. `python installa.py modello elenca` lists the profiles;
  `python installa.py modello usa <profile>` selects one.
- **"limite del servizio raggiunto: attendo…"** (service limit reached: waiting) during a search: normal with free
  services, which limit requests per minute. The search waits and carries on by itself; when the daily quota is
  used up, it retries at growing intervals for up to 36 hours.
- **The search still uses the previous model**: it is an interrupted search, which resumes with the profiles it
  started with. To continue with the one selected now: `--usa-modello-attuale`, or ask for it in the chat.

## Project and import

- **No project selected, the engine does not start**: create a project with `python installa.py inizia --passi 3`
  (or `python progetto.py nuovo <folder>`); the choice is written to `config.ini`.
- **The review table opens as a single column**: Excel did not recognise the separator. Open it with "Data > From
  Text/CSV" and choose the semicolon, or use LibreOffice, which asks when opening.
- **"serie da indicare"** (series to be given) in the da_controllare column: for a single article the system does
  not know which journal published it; write the journal's name in the `serie` column. For several authors, write
  them as they should be cited (`Surname, Name; Surname, Name`).
- **OCR full of errors**: low-resolution or skewed scan; rescan at 300 dpi, greyscale. For texts with many words in
  another language, put for example `ocr_lingue = sqi+eng` in the series profile (`glossary/series.ini`).
- **The search misses a name that is in the texts**: the search looks only for the forms written in the card's
  `varianti`. A form listed only in `forme_ambigue` (ambiguous forms) is not searched: it must be in `varianti`
  too. `python schede.py controlla` reports it.
- **"Indice delle fonti in costruzione"** (source index being built): the first time, on a large corpus, the index
  takes 10-30 minutes; meanwhile the chat says so. By hand: `python indice.py costruisci`.

## Chat (Jan, Claude Desktop, LM Studio)

- **The AIrchivist server does not appear or is off**: restart the client after `installa.py client <name>
  --scrivi`. In Jan an entry written while the program is open is lost (Jan rewrites its files when it closes):
  close Jan, rerun the command, reopen Jan. Then check the connection with `python installa.py client --verifica`.
- **The client cannot find `python`**: the server entry's command must be the full path of the interpreter;
  `installa.py client <name> --scrivi` writes it that way.
- **The chat answers without using the tools**: the chat model must support tool use (in Jan: **Tools** enabled on
  the model) and web search must be off. If the server's instructions do not reach the model, write at the start
  of the conversation "call the guida tool".
- **The chat says the search never ends**: searches run as separate processes and continue even if the chat stops
  waiting. Ask "how far has the search got?": the assistant finds it again.
- **A tool result is cut off**: the client accepts fewer characters than the server sends. In Jan the right value
  (8000) is set by `installa.py client jan --scrivi`; for other clients lower `[mcp] max_caratteri` in
  `config.ini`.
- **"All models exhausted"** (FreeLLMAPI): the free quotas for the chat model are used up for now. Try again later;
  searches already started wait and resume by themselves.

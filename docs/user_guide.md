# Searching the sources: user guide

To get started in a few minutes: [`quickstart.md`](quickstart.md). If something goes wrong:
[`troubleshooting.md`](troubleshooting.md). In Italian: [`user_guide.it.md`](user_guide.it.md).

The system is used from a **chat client** connected to the engine through the MCP server `mcp_server.py`: Jan,
Claude Desktop, LM Studio or any other client that supports MCP servers. The chat model does not read the sources:
it uses the engine's tools and reports what they return. The same steps can also be run from the command line.

The work is divided like this:
- **Python, on your computer**: finding the occurrences, checking the citations and laying out the answer.
- **The model you choose** (a free service with a key, Ollama on your computer, the Anthropic API or FreeLLMAPI):
  only reading the passages (sorting, translation, summary). You can change it whenever you like (see "Models that
  read the passages").

It runs on Windows, macOS and Linux. The commands in this guide are typed in a terminal (on Windows, Command Prompt
or PowerShell), in the engine's `scripts` folder; on macOS and Linux the command may be `python3` rather than
`python`. Paths are written with `/`, which works on Windows too.

**About the language.** The system was written in Italian: command names (`installa` = install, `importa` =
import, `ricerca` = search, `proponi` = propose, `applica` = apply, `controlla` = check, `elenca` = list, `usa` =
use, `prova` = test/dry run), configuration keys, messages, the eight section titles of an answer, and the
translations and summaries of the passages are in Italian. This guide gives the meaning of each the first time it
appears. The chat assistant can answer in another language (`[mcp] lingua` in `config.ini`).

## Folder layout

```
AIrchivist/                 the repository (the engine: it can be published)
  README.it.md, README.md   overview (in Italian and English)
  LICENSE, requirements.txt licence (AGPL-3.0) and optional libraries
  docs/                     documentation: quickstart, this guide, troubleshooting, project documents (Italian)
  skills/
    source-search/          the source-search skill, single source (SKILL.md, config.ini)
    readme/                 READMEs of the packages
    package.py              builds the skill packages into skills/build/ (outside version control):
                            source-search-claude.zip (claude.ai), claude-code/ (marketplace with the plugin),
                            source-search-chatgpt.zip
  tests/                    automated tests (python -m unittest discover -s tests); test_project/: sample project
  scripts/
    installa.py             guided setup, libraries, environment check, model profiles, chat clients
    app.py, interfaccia/    the browser interface (local server and page)
    mcp_server.py           the server that connects the chat to the engine; istruzioni.py: the rules it sends
    ricerca.py              the engine: extraction -> reading -> answer (started by the server)
    estrai_occorrenze.py, classifica.py, sintesi.py, evoluzione.py, cronologia.py, date_interne.py,
    glossario.py, archivio.py, schede.py, varianti.py, llm.py   the parts of the engine
    indice.py, esplora.py   source index, exploration of new names and free-text search
    varianti_nomi.py        Chinese transcriptions and translated forms proposed by esplora_nome
    lavori.py               runs searches as processes independent of the chat
    progetto.py, profili.py research projects (new, status, paths) and series profiles
    importa.py, revisione.py   import of new material (PDF, scans, .txt, PAGE/ALTO XML) and the metadata
                            review table
    pagine_xml.py, numerazione.py, colonne.py, motori_ocr.py, ocr_paddle.py, confronto_testi.py, tabelle.py
                            parts of the import: XML, page numbers, column order in newspapers, OCR engines,
                            text comparison, reading tables (.csv, .xlsx)
    citazioni.py            Chicago author-date citations from the file headers and series profiles
    documento.py            the answer as a self-contained HTML document, to open in a browser and print
    sessione.py             reading passages in a session (source-search skill)
    chat.py                 commands of the source-search skill (chat.py ambiente: where it is running)
    valuta.py               quick test of the models against a reference reading
    valutazione.py          hand-verified reference set; precision and recall measurements
    prova_ocr.py, prova_chat.py   tests of OCR engines and of chat models
    config.ini              engine configuration (model profile in use, parameters, project in use)
    models.ini              your model profiles (outside version control; created by installa.py modello)
    models_template.ini     example model profiles, with a description of every key
    series_template.ini     template of series.ini for new projects
  projects/                 research projects (outside version control)
    <project>/              a research project
      project.ini           project name and settings
      glossary/
        entities.ini        entity cards
        series.ini          series profiles (including citations)
        instructions.md     project rules for the chat model
      sources/              original uploaded documents, never modified
      data/                 the processed sources, one .txt per document with a metadata header
      audit/
        changes.csv         every correction made to the sources' metadata
        open_issues.csv     gaps still open (missing days and issues): used in sections 5 and 6 of the answers
                            and by the copertura_fonti tool
        imports.csv         import log
        review_<date>.csv   import review tables
        checks/             header checks
      results/
        archive/            single archive of the passages already read
        searches/           one folder per search (modelli.json: the model profiles it started with)
        answers/            the full answers of searches started from the chat (one per question)
        references/         reference readings for valuta.py
        past_sessions/      work from assisted sessions (readings, tables, reports)
        trials/             tests of models, OCR, chat and skill (they do not enter the archive)
        evaluation/         hand-verified reference sets and measurements (valutazione.py)
      system/
        index/              search index of the sources (updates itself when you add files)
        jobs/               one folder per search started from the chat: status and message log
        import_jobs/, cache/   imports started from the chat and pages already read by OCR
        backups/            copies of files outside version control (sources, archive, cards),
                            one folder per date and subject
        model_changes.csv   log of model changes (installa.py modello usa)
```

## Requirements (once)

| | Windows | macOS | Linux |
|---|---|---|---|
| **Python** 3.10 or later (required) | https://www.python.org/downloads/, ticking "Add python.exe to PATH" | python.org or `brew install python` | usually present; otherwise `sudo apt install python3` |
| **PyMuPDF** (to import PDFs) | `python installa.py librerie` | `python3 installa.py librerie` | `python3 installa.py librerie`, or `sudo apt install python3-fitz` |
| **Tesseract** (to import scans) | `winget install -e --id UB-Mannheim.TesseractOCR` | `brew install tesseract tesseract-lang` | `sudo apt install tesseract-ocr tesseract-ocr-<language>` |

You also need **a model to read the passages** (see "Models that read the passages") and, to ask questions in a
conversation, **a chat client** (see "Connecting the chat"). The engine uses only Python's standard library.
Everything is installed system-wide, never inside the project folder.

From the `scripts` folder:

```
python installa.py inizia
```

`inizia` (start) is the guided setup for first-time users: it checks the environment, creates the model profile,
creates the first project and selects it, connects the chat, and ends with a summary that re-runs the required
checks. Each step can be skipped (`--saltati 4`, skipped) or run alone (`--passi 3`, steps); run again, it does not
redo completed steps. The same things one at a time:

```
python installa.py librerie
python installa.py modello
python installa.py controlla
python installa.py client jan --scrivi
```

- `librerie` (libraries) installs the optional libraries in `requirements.txt` (PyMuPDF) into the system Python. On
  Linux distributions that do not allow it ("externally-managed-environment"), use the distribution's package.
- `modello` (model) creates the first model profile with a guided procedure (see below).
- `controlla` (check) checks Python, SQLite with FTS5, the model profiles in use (key present, service
  reachable), the project in use, PyMuPDF, Tesseract with the languages of the series, and PaddleOCR, and gives the
  right command for your system for whatever is missing. It exits with status 1 if a required item is missing;
  `--rapido` (quick) skips PaddleOCR.
- `client` configures the chat: see "Connecting the chat".

### Models that read the passages (profiles)

There are two models, and they are different:
- the **model that reads the passages** (sorting, translation, summary), chosen here;
- the **chat model**, which uses the tools and presents the answer: it is chosen in the client (Jan, Claude
  Desktop, LM Studio).

Every configured model is a **profile** with a name, in `scripts/models.ini`: service, model name, address, name of
the environment variable holding the key, and its own parameters (pause between requests, maximum response
length, JSON mode...). The key is never written in the file. Commented examples and a description of every key are
in `scripts/models_template.ini`.

In the `scripts` folder:
```
python installa.py modello                       guided procedure for a new profile (same as "modello nuovo")
python installa.py modello elenca                profiles, those in use, keys present
python installa.py modello prova groq-qwen       connection test with a minimal request
python installa.py modello usa groq-qwen         selects the profile for all roles
python installa.py modello usa ollama-qwen-9b --ruolo sintesi    for one role only
python installa.py modello usa groq-qwen --progetto              for the project in use only (project.ini)
python installa.py modello togli gemini-flash    removes a profile not in use (with a copy of the file)
```

The roles (`--ruolo`) are `smistamento` (sorting: relevant or not), `analisi` (analysis: translation and summary of
each passage) and `sintesi` (synthesis: the final answer).

**Guided procedure.** It asks for the service:
1. Ollama, on your computer: free, no key, needs a fairly powerful computer. It proposes the models already
   installed (`ollama pull <name>` to download one).
2. A service with a single key: Groq, Google Gemini, OpenRouter or another OpenAI-compatible one. For the three
   known services it says where to create the key, asks for it straight away and proposes the models the service
   lists (the first is the recommended one, if the service still offers it).
3. The Anthropic API (Claude), pay as you go.
4. FreeLLMAPI (advanced): several free services in a chain, see below.

Then the model name, if you have not already picked it from the list, and the profile name (it proposes one). If a
key is needed and the variable is not set, it asks for it (it is not shown as you type) and, if you agree, saves it
as an environment variable of your user (on Windows with `setx`; on macOS and Linux it gives the line to add to
`~/.zprofile` or `~/.profile`). Finally it tests the connection and asks whether to use the profile straight away.
New variables apply to terminals and programs opened afterwards: reopen the terminal and restart the chat client.

**Selecting a profile.** `usa` (use) first tests the connection and changes the selection **only if the test
succeeds**; otherwise the previous profile stays and the message explains the problem (key refused, model does not
exist, service off, quota used up). The selection is in `config.ini`, section `[modello]`:
```
[modello]
profilo = groq-qwen          for all roles
sintesi = ollama-qwen-9b     optional: a different profile for smistamento, analisi or sintesi
```
The same section in `project.ini` takes precedence, for that project only. Every change is logged in the
project's `system/model_changes.csv` (date, role, previous and new profile).

**Changing model in the middle of a project.** Readings already done stay in the archive with the name of the
model that made them, and are not read again just because the model changed. A search uses the profiles selected
when it started (see "Long searches and exhausted quotas"). If a model turns out to be unreliable, its passages can
be read again (see "Re-reading the passages of a model"). Section 5 of every answer says which models read the
passages and whether they have been measured on these sources.

**Earlier configuration.** If no profile is selected in `[modello]`, the earlier configuration still applies: the
`backend` key and the `[anthropic]`, `[openai]`, `[router]`, `[ollama]` sections of `config.ini`.
`python installa.py modello converti` (convert) turns it into profiles: it shows what it will do, asks for
confirmation, saves a copy of `config.ini` and `models.ini` (`<file>.airchivist-<date>.bak`) and selects the profile
matching the previous `backend`.

### FreeLLMAPI (free models in a chain)

FreeLLMAPI runs on your computer. When the quota of one free service runs out, it moves on to the next service by
itself. It is the advanced choice: to get started, a service with a single key is enough.

1. Install FreeLLMAPI from https://github.com/tashfeenahmed/freellmapi/releases/latest (there is an `.exe` for
   Windows; for other systems follow the project's instructions) and start it.
2. In its panel add the keys of the services (for example Google AI Studio, Groq, NVIDIA, OpenRouter, Cloudflare,
   Z.ai). **Use only official API keys.** The keys stay inside FreeLLMAPI: do not write them in the files of the
   folder.
3. On the **Fallback Chain** page you need two chains:
   - `ricerca` (search): the models verified with `valuta.py` or `valutazione.py`, used by the engine to read the
     passages;
   - `chat`: only models able to use tools, used by the chat client.
4. Routing strategy: **Custom**, with reliability 0%, speed 40% and intelligence 60%.
5. Copy the single key (`freellmapi-…`, **Keys** page) and save it in the environment variable `FREELLMAPI_KEY`
   (Windows: `setx FREELLMAPI_KEY "..."`; macOS and Linux: `export FREELLMAPI_KEY="..."` in the shell profile).
   Then close and reopen the terminal.
6. Create the profile with `python installa.py modello` (option 4). The proposed address is
   `http://127.0.0.1:31415/v1`; if it changes, you find it under **Keys > Unified API key > Base URL**. The model
   `auto:ricerca` is the `ricerca` chain.

`modelli_ammessi` (allowed models; a key of the FreeLLMAPI profile in `models.ini`) is a safety net: if you fill it
in and a model not in the list answers, the reading stops without saving anything. The connection test of
`installa.py modello usa` fails too, so you notice before starting a search.

Every passage records the model that actually answered, in the `modello_smistamento` and `modello_analisi` columns
of `classificati.csv`.

## The browser interface

```
python app.py
```

Starts a server on your computer and opens the interface in your browser; the terminal shows the link, to copy if
the browser does not open (it is valid while the window stays open; Ctrl+C to close). No chat client is needed: the
interface calls the same functions as the MCP server. Its labels are in Italian.

- **"Progetto" (project) menu**: the projects in the `projects` folder; the choice also applies to the chat and the
  command line (it is written to `config.ini`, section `[progetto]`). "Nuovo progetto…" creates one. While a search
  of the project is running, switching is blocked.
- **"Modello" (model) menu**: the model profiles, marked "misurato" or "non misurato" (measured or not on these
  sources), with a dot for the connection (green: key present and service reachable). The choice goes through the
  connection test: if it fails, the previous model stays and the message says why. "Aggiungi modello…" (add model)
  creates a profile like `installa.py modello` (the key goes into environment variables, never into files).
- **Search path** (right column): 1. the name (and, if you like, the question, the period, the sources); 2. if the
  card exists, the forms the search looks for; otherwise the forms of the name attested in the sources, with counts
  and examples, to confirm with the tick boxes (the card is created with those only); 3. progress, which you find
  again if you close and reopen the page; 4. the summary of the answer and the full document, which opens in the
  left column.
- **Importa** (import): the documents folder, "Proponi" (writes the review table, to be corrected in Excel or
  LibreOffice), then "Controlla" (check) and "Importa" (see "Importing new sources").
- **Storico** (history): the project's previous answers and searches.

The server listens only on your computer (`127.0.0.1`) and accepts only the browser opened with the session link.
Options: `--porta 8770` (fixed port), `--senza-browser` (do not open the browser).

## Connecting the chat

```
python installa.py client claude --scrivi
python installa.py client --verifica
```

`client <name>` (`jan`, `claude`, `lmstudio`) finds the client's configuration file on your system, shows what will
change and, with `--scrivi` (write), adds or updates only the AIrchivist entry (command: the full path of the
Python interpreter; argument: `scripts/mcp_server.py`; variable `PYTHONUTF8=1`), after a backup copy
(`<file>.airchivist-<date>.bak`) and your confirmation. The other entries stay untouched. Without `--scrivi` it
only shows what it would write. `client json` prints the generic `mcpServers` block, to paste into other clients.
`client --verifica` (verify) starts the server the way the client would and checks the MCP handshake and the tool
list. For clients that use HTTP: `python mcp_server.py --http 8765`.

Restart the client after writing. Claude Desktop exists for Windows and macOS; on Linux use Jan or LM Studio.

### Jan

1. Install Jan from https://jan.ai (free, open source; Windows, macOS, Linux).
2. Add the service of the chat model: Settings → Model Providers (a service already listed, or **Add Provider** with
   address and key, for example FreeLLMAPI with `http://127.0.0.1:31415/v1` and the model `auto:chat`). For the
   chosen model, with the pencil icon, enable **Tools**.
3. **With Jan closed**, from the `scripts` folder: `python installa.py client jan --scrivi`. Jan rewrites its files
   when it closes, so a change made while Jan is open would be lost. The command updates the server entry (also if
   it is called "Pipeline") and switches it on, raises the tool timeout to at least 90 seconds, turns smart routing
   off, raises tool results to 8000 characters and turns web search off (files `mcp_config.json` and
   `settings.json` in Jan's data folder).

   By hand, instead: Settings → **MCP Servers** → **+ Add MCP Server**, type STDIO, Command the full path of Python
   (`where python` on Windows, `which python3` on macOS and Linux), Arguments the path of `scripts/mcp_server.py`
   in the engine folder, environment variable `PYTHONUTF8` = `1`; then, in the MCP settings, tool timeout 90 seconds
   and smart routing off, and **Web Search** off.
4. An **assistant** (for example "Source search") with the chosen model. The working rules (sources, citations,
   translations) are sent by the server (see "Instructions for the chat AI"): in the assistant's instructions it is
   enough to write "At the start of every conversation call the guida tool and follow its instructions".

After every engine update, switch the AIrchivist server off and on again in the client's MCP settings.

## Research projects

The engine (the `scripts` folder, with `config.ini`) is separate from the data of a piece of research, which live in
a **project folder**, usually inside `projects`: `project.ini` (project name and any settings of its own),
`glossary` (`entities.ini`, `series.ini`, `instructions.md`), `sources`, `data`, `audit`, `results` and `system`
(see "Folder layout"). Projects are research data: git ignores the `projects` folder, so the engine repository can
be published without them.

```
python progetto.py stato
python progetto.py nuovo ../projects/albanian_press --nome "Albanian press 1960-1978"
```

- `stato` (status): which project is in use and where its files are.
- `nuovo` (new): creates an empty project, with the folders, the two `audit` CSV files, `glossary/entities.ini`,
  `glossary/series.ini` (with the description of the fields) and `project.ini`. It does not touch a folder that
  already contains something. `installa.py inizia` (step 3) also creates and selects the first project.

Without a selected project the engine does not start: it says so and points to `progetto.py nuovo`.

**Which project to use**: in `config.ini`, section `[progetto]`, key `cartella` (folder); or the environment
variable `AIRCHIVIST_PROGETTO`, which takes precedence. A chat client can have several MCP servers, one per project:
same command and arguments, with the environment variable `AIRCHIVIST_PROGETTO` pointing to the project folder.

In `project.ini` you can also change, for that project only, the settings of `config.ini` (for example
`[estrazione] finestra = 300`) and move a file with the `[percorsi]` (paths) section (paths relative to the project
folder).

## Use

New conversation with the assistant connected to the server, then type the question. Examples (from the project
the system was built for, on dissident communism between Beijing and Tirana):
- "What do the sources say about Jacques Grippa in 1964?"
- "How did Grippa's politics evolve up to 1972?"
- "How does Nuova Unità appear in the Renmin Ribao between 1973 and 1976?"
- "Open the Renmin Ribao passage of 2 April 1967."
- "Which new variants are there for Grippa?"
- "Passage X is not relevant: correct it."

Tools available to the chat model (14; those with several operations take the `azione` (action) parameter):

| Tool | What it does |
|---|---|
| `guida` (guide) | working instructions and the project's sources (for clients that do not show them to the model) |
| `schede` (cards) | `elenca`: finds the exact name of a card; `crea`: creates the card with the forms you confirmed |
| `esplora_nome` (explore name) | for an entity without a card: the forms of the name attested in the sources, with counts and examples |
| `cerca_testo` (search text) | free search for a word or phrase in all sources (no relevance assessment) |
| `ricerca` (search) | `avvia` (start), `attendi` (wait: progress and model profiles in use; short waits, `[mcp] attesa_massima`), `ferma` (stop): full search in the sources. With `avvia`, on your request: `usa_modello_attuale`, `rileggi_modello` (see below) |
| `modello` (model) | `elenca`: profiles, those in use, keys present, whether the model is measured on these sources; `prova`: connection test; `usa`: selects a profile (also for some roles or for the project only), only if the test succeeds |
| `risposte` (answers) | `elenca`, `leggi` (read): the answers saved in the project's `results/answers` folder, by section |
| `passaggi_archivio` (archive passages) | passages already read (original, translation, reference): immediate answer |
| `copertura_fonti` (source coverage) | how many issues of each periodical (series profiles) exist in a period and which are missing |
| `apri_fonte` (open source) | the text of the source file around a line |
| `varianti` (variants) | forms of the name proposed during reading: list, add, discard |
| `correggi_passaggio` (correct passage) | records your correction: it applies to all later searches |
| `importa` (import) | `proponi`, `applica`, `rivedi`, `avvia`, `stato`: import of new sources (see "Importing new sources") |
| `serie` (series) | `elenca`, `crea`: the project's series profiles |

The names used until 25/10/2026 (`elenca_entita`, `avvia_ricerca`, `leggi_risposta`...) are still accepted, so an
assistant that uses them keeps working.

From the chat you can ask which model reads the passages ("Which model reads the passages? Is it measured?") and
change it ("Use the ollama-qwen-9b profile for the synthesis"): the `modello` tool runs the same test as
`installa.py modello usa`. A new profile can only be created from the command line, so that the key does not pass
through the chat. The chat model itself is changed in the client.

**Without a chat client.** A search can also be started from the command line, on an entity that has a card (see
"Entity cards and glossary"): `python ricerca.py "Card name"`, with `--apri` (open) to open the answer document when
the search ends. Useful options: `--dal` and `--al` (from and to, years), `--fonti "Series 1; Series 2"` (sources),
`--evoluzione` (evolution over time, including the related entities). The answer stays in
`results/searches/<name>/`.

### Instructions for the chat AI

The server composes them every time (`istruzioni.py`) from three parts: the engine's general rules (how to use the
tools, how to cite, what not to do), the list of sources derived from `series.ini` with the name and description
from `project.ini`, and the project's own rules written in `instructions.md` in the project folder (subject,
character of the sources, conventions on names and offices, citation examples; lines starting with `#` are not
sent). It delivers them in three ways, because not every client shows them to the model: in the `instructions`
field of the MCP protocol, as the MCP prompt `istruzioni`, and through the `guida` tool. Language of the chat
answers (`lingua = italiano`, or `English`, or another) and maximum wait: `config.ini` (or `project.ini`), section
`[mcp]`. Translations and summaries of the passages are, for now, always in Italian.

Every full search started from the chat saves the answer in the project's `results/answers` folder, with the date
and the question in the file name. The answer has eight sections (titles in Italian):
1. Documents (*Documenti rilevanti*)
2. Original passages (*Passaggi rilevanti*)
3. Explicit data (*Dati espliciti*)
4. Inferences (*Inferenze*)
5. Limits (*Limiti*; also: which models read the passages, how many each, and whether they are measured on these
   sources)
6. Coverage (*Copertura*)
7. Final answer (*Risposta finale*)
8. Technical data for verification (*Dati tecnici per la verifica*: files and lines, which do not enter the
   citations)

Next to every answer (`.md`) is the same text as an **HTML document** (`.html`, a single file, nothing loaded from
the internet): it opens with a double click in the browser and can be printed (also to PDF, from the browser's Print
command). It has the same sections; the [n] references link to the cited passage. In the chat, when the search is
over, you get a summary (the final answer, the number of documents, the first limits) and the path of the document:
the full answer is read there, and the chat model does not rewrite it. The other sections can be requested
separately (`risposte` tool).

From the command line: `python ricerca.py "Name" --apri` opens the document when the search ends; `python
documento.py <answer.md or folder>` writes the document for answers saved earlier (`--apri` to open it).

Citations follow the Chicago Manual of Style, 17th edition, author-date system: the reference-list entry, with the
cited page at the end when the file gives it ("*Renmin ribao* 人民日报. 1965. 28 giugno 1965, p. 4."). The entry is
built from the file header and from the series profile in `series.ini` (type, title of the newspaper, `chicago`
field). Under every passage the "Lettura" (reading) line says who decided the relevance and who translated: a model
(which one), an assisted session, a rule. Section 6 gives the counts. Month names in citations are in Italian.

### Long searches and exhausted quotas

Every search runs in its own process, with its status saved in the project's `system/jobs/`: it continues even if
you restart the server or close the chat, and the assistant finds it again at the next question ("how far has the
search got?"). When the free quotas run out, the search does not stop: it waits and retries by itself (after 10, 15,
30 minutes, then every hour, for up to 36 hours) and resumes where it was. The same applies to the synthesis, if
the model does not answer: the answer saved in the meantime contains the parts already done. If some passages keep
failing (invalid responses from the model), after two attempts the answer is written anyway and section 5 says how
many passages are missing.

A search stops only for errors that do not go away by themselves (missing or wrong key, retired model): the
assistant reports the message. If the computer shuts down or goes to sleep, the search is interrupted: asking the
question again resumes it where it was. The full log of every search is in the project's
`system/jobs/<date-time>/registro.txt`.

**Model profiles of a search.** When it starts, a search records the profiles in use in `modelli.json`, in its folder
inside `results/searches`. If it is interrupted and resumes (by itself or because you ask again), it continues with
those profiles even if you have selected another model in the meantime: this way a search does not mix models
because of a change made halfway. The change applies from the next search. To make an interrupted search continue
with the model selected now: ask for it explicitly in the chat (option `usa_modello_attuale`), or from the command
line `python ricerca.py "Name" --usa-modello-attuale`. When the search ends with a full answer, the next one uses
the profiles selected at that moment.

## Entity cards and glossary

Searches work only on entities that have a card in `entities.ini`. Example:
```
[PCd'I (m-l)]
forma_estesa = Partito comunista d'Italia (marxista-leninista)
varianti = 意大利共产党（马克思列宁主义）; ...
collegate = ...
forme_ambigue = ...
note = ...
```
Fields:
- `varianti` (variants): every form of the name the search must find, separated by `;`.
- `tipo` (type): `persona`, `organizzazione`, `testata` (newspaper), `stato` (state), `altro` (other).
- `forma_estesa` (full form): the name in full, for bodies known by an acronym.
- `collegate` (related): entities to analyse together in questions about evolution over time, for example the party
  or its newspaper.
- `forme_ambigue` (ambiguous forms): forms that may also refer to another entity; for these the passage is always
  checked by the model. They must also be in `varianti`: the search looks only for the variants. `schede.py
  controlla` reports those missing, and the server tells the chat when it creates such a card.
- `note`: notes for the model that reads the passages.

Rules for merging or splitting cards, for leaders, newspapers and ambiguous forms: `docs/schede_entita.md`
(Italian). Automatic check (duplicates, shared forms, undeclared short forms, readings under names without a card):
```
python schede.py controlla
```

### New entities

If you ask about a person or an organisation that has no card, the assistant uses `esplora_nome`:
- it searches the sources in Latin script for the forms of the name, tolerating OCR errors;
- it translates the clues written in Latin script (countries, nationalities, parties, in Italian, English, French,
  Spanish, German and Albanian) into the Chinese forms: "Italian", "Italia" → 意大利, 意共 (`varianti_nomi.py`);
- it generates the Chinese transcriptions of the name by itself, on the Xinhua model and with the most common
  variants (Berlinguer → 贝林格, 贝尔林格…; the first name is combined with the surnames found: 恩里科·贝林格), and the
  translations of party names (Communist Party of Italy (Marxist-Leninist) → 意大利共产党（马列） …); it keeps only
  the attested ones and, among them, proposes those that appear next to the clues;
- it also checks the Chinese transcriptions proposed by the chat model;
- it compares the newspapers: where one series names the person, it looks in the other series of the previous days
  for transcribed names next to the country or party, and proposes them (alignment declared in the profiles, for
  example Peking Review and Renmin Ribao);
- when Albanian texts are present it also looks for the probable Albanian transcriptions and the stems of the
  declined forms;
- for every form it reports counts by series and year, examples with references, how often it appears next to the
  clues, and flags short forms or forms often without context (possible homonyms).

The generated forms and those from the alignment are attested, but they may refer to other people or words (贝林格
also appears in 贝林格韦, a region of Zimbabwe): they must be confirmed one by one and, if short, go among the
ambiguous forms, which the model always sorts.

The assistant shows you the attested forms and creates the card only after your confirmation: no form enters the
card unless it appears in the sources. Then the search proceeds as for the other entities. Without a chat client
the card is written by hand in `glossary/entities.ini` (`tipo` and `varianti` are enough).

The **source index** (in the project's `system/index/`; for a corpus of a few thousand files, almost 1 GB) is used
by `esplora_nome`, `cerca_testo` and the extraction of occurrences: with the index each search reads in full only
the files that may contain the name, with the same result as a full reading. The first import creates it; when you
add or correct files in `data/`, it updates itself at the next search (it indexes only new or changed files: a few
seconds). By hand, in the `scripts` folder: `python indice.py aggiorna` (update); `python indice.py stato` says
whether it matches the sources. After many corrections it is worth rebuilding it from scratch to clean it up
(`python indice.py costruisci` (build); on a large corpus 10-30 minutes).

`entities.ini` also works as a glossary. When a passage contains the Chinese or English form of a name that has a
card, the model is told which Italian name to use.

## Importing new sources

`importa.py` brings new material into the system: PDFs with text, scanned PDFs, photos or scans of pages (jpg,
png, tif), `.txt` files and PAGE XML / ALTO XML exports. For every document it takes the PDF's text when there is
one, otherwise it runs **OCR** with Tesseract (free, runs on your computer); it writes a `.txt` file with the metadata
header into `data/`, like the other sources; it logs the method, pages, OCR quality and warnings in
`audit/imports.csv`; it updates the index (the first import creates it). In PDFs it marks the printed pages (see
"PDF pages"), so citations reach the page.

The original (PDF, scan, PAGE/ALTO export, `.txt`) is copied untouched into `sources/`, in the same subfolder the
`.txt` has in `data/`; a document made of several files (XML pages, `--unisci`) becomes a folder named after the
document. `SOURCE_FILE` in the header points to that copy (path relative to `sources/`) and `SOURCE_HASH` gives its
SHA-256 fingerprint (for a folder: the fingerprint of the list of files with their fingerprints). Originals in
`sources/` are never modified again: importing the same file again reuses the copy; if a different file has the
same name, the new one is kept alongside with the first 8 digits of its fingerprint in the name. With `--prova`
(dry run) nothing is copied.

**Preparation (once)**: PyMuPDF and Tesseract with the languages you need (see "Requirements"), then, in the
`scripts` folder:

```
python importa.py prepara
```

Tesseract, PyMuPDF and the language models stay installed in the system, not in the project folder. On Windows,
during the Tesseract installation, under "Additional language data", tick the languages you need; to add one later:
rerun the installer, or copy `<language>.traineddata` from https://github.com/tesseract-ocr/tessdata_best into
Tesseract's `tessdata` folder (administrator rights needed). On macOS `tesseract-lang` contains every language; on
Linux there is one package per language (`tesseract-ocr-sqi`, `tesseract-ocr-ita`...). `prepara` (prepare) checks
that Tesseract, PyMuPDF and the languages required by the series in `series.ini` are present (Albanian: `sqi`). If
Tesseract or the models live in non-default folders, give them in `config.ini`, section `[ocr]` (`tesseract = ...`,
`modelli = ...`).

**Series.** Every newspaper, journal, book or archival fonds has a profile in the project's `series.ini`. Three
fields are enough:
```
[Zëri i Popullit]
tipo = periodico
lingua = sq
```
`tipo` (type) is `periodico` (periodical: issues, one file per issue), `articolo` (journal articles, one file per
article with author and title), `volume` (book or collection) or `archivio` (dated archival documents). Everything
else has defaults: folder inside `data/` (`riviste/zeri_i_popullit`, `volumi/...`, `archivi/...`), file-name prefix
(the initials: `ZP`), and the Chicago 17 author-date citation (reference-list entry, with the cited page at the
end), generated from the type:
- periodical and article: "Putnam, Lara. 2016. “The Transnational and the Text-Searchable.” *The American
  Historical Review* 121, no. 2 (aprile): 377–402, p. 380."; without an author the newspaper takes its place:
  "*Zëri i Popullit*. 1967. 12 gennaio 1967, p. 3.";
- volume: "Hoxha, Enver. 1969. *Vepra*. Vol. 2. Tirana: Naim Frashëri, p. 45.";
- archive: "Central Intelligence Agency. 1971. “Chinese Support for Foreign Communist Parties.” 3 marzo 1971.
  CIA-RDP85T00875R001100010023-9, CIA FOIA Electronic Reading Room, p. 12." (optional profile fields `archivio`,
  `fondo`, `segnatura`: archive, fonds, shelfmark).

In the header the author is written "Surname, Name" (several authors separated by `;`: in the entry the first stays
"Surname, Name", the others become "Name Surname"). Unknown year: "s.d.". `nome_citazione` gives the name of the
newspaper as it should be written (e.g. `*Renmin ribao* 人民日报`). The `chicago` field is needed only for a form
different from the type's (e.g. the JPRS translations of Red Flag). The advanced fields are described at the top
of `series.ini` (template: `scripts/series_template.ini`). Series are added with the guided import (below), by
writing the block, or by asking in the chat ("create the series ..."). The profile also tells the rest of the system
how to treat the series: whether it is a periodical (`tipo`), how far its issues go (`periodo`, period, for the
silences in the chronology), how often it comes out (`periodicita`), which other series to search it with
(`gruppo`, group), how to find the page in the text (`pagina_regex`). A series without `periodo` has no final
silences in the chronology.

**Guided import with the review table** (the simplest way for a folder of new documents: you do not need to know
beforehand what series and metadata are). In the `scripts` folder:

```
python importa.py proponi <documents folder>
python importa.py applica <project>/audit/review_<date>.csv --prova
python importa.py applica <project>/audit/review_<date>.csv
```

1. `proponi` (propose) reads all the files **without importing them** (no OCR: text and metadata of the PDFs, page
   labels and numbers, file name, resolution of the scans, JSTOR cover page) and writes the table
   `review_<date>.csv` into the project's `audit/`, one row per document. It proposes the series (a subfolder whose
   files look alike, such as `ZP1967-01-12.pdf`, `ZP1967-01-13.pdf`, is a periodical; a book or a single article
   forms a series of its own, or goes into its journal), and for every document the type (issue, article, volume),
   the date with its status and source, number, title, author, year, language, printed pages, native text or scan,
   expected OCR quality. The **da_controllare** (to check) column explains the doubts.
2. Open the table in Excel or LibreOffice (semicolon-separated: it opens already split into columns), fix the
   values, write `no` in the `importa` column to skip a document, save (also as `.xlsx`). For a new series, name,
   `tipo_serie` (periodico, articolo or volume) and language are enough: folder and prefix, if empty, are derived
   from the name.
3. `applica --prova` checks the table and says what it would do; without `--prova` it creates the series missing
   from `series.ini`, imports the documents (with OCR where needed) with the table's values and updates the index. A
   value you changed counts as "verificato" (verified); one left as it was stays "dedotto" (inferred) or "da
   verificare" (to be verified), with its source (`DATE_NOTE`). Imports go into `audit/imports.csv`, the values you
   corrected compared with the proposal into `audit/changes.csv`.

For documents **already imported**, the same table: `python importa.py rivedi --serie "Zëri i Popullit"
--solo-dubbi` (review, doubtful only) writes `audit/review_rivedi_<date>.csv` with the headers (only documents with
inferred, to-be-verified or missing values); correct it and `applica` rewrites only the changed fields (encoding and
line endings stay those of the file), with a copy of the previous version in `system/backups/` and one row per field
in `audit/changes.csv`. A corrected value becomes verified.

From the chat, the same path: `importa` tool, actions `proponi`, `applica` (first with `prova`) and `rivedi`; the
chat says which file to open and does not fill in the table for you.

**Importing a file into an existing series.** In the chat: "import the folder <path of the scans> into the series
Zëri i Popullit". The first time for a series or a kind of scan the assistant runs a **test** on the first pages and
shows the text, quality and date read. Or from the command line:

```
python importa.py importa "<scans folder>" --serie "Zëri i Popullit" --prova 2
python importa.py importa "<scans folder>" --serie "Zëri i Popullit"
```

- **Date**: for periodicals it is taken from the file name (`1967-01-12`, `12.01.1967`, `12 janar 1967`...); if
  missing, from the masthead of the first page (marked "da controllare", to check); or `--data`, or a file
  `--metadati list.csv` with the columns `file, data, numero, titolo, autore, anno, volume` (file, date, number,
  title, author, year, volume).
- **Articles** of a periodical: `--titolo` and `--autore` go into the header (`TITLE`, `AUTHOR`) and into the
  citation ("Larrabee, F. Stephen. 1978. “Whither Albania?” *The World Today* 34, no. 2 (febbraio).").
- `--unisci` (merge): the page photos of a single issue become a single document.
- The import can be interrupted: pages already read stay in `system/cache/imports` and are not read again when it
  resumes. Documents already imported are skipped (`--sovrascrivi`, overwrite, to redo them).
- **Quality**: for every document the average OCR confidence (0-100) and the weak pages (below 60) are in
  `registro.csv` and in the header (`[OCR_CONFIDENCE]`). Below 70 it is worth checking samples or rescanning
  (300 dpi, greyscale).

**PDF pages.** Every page gets the marker `[[p. 61 | pdf 2]]` (printed page | position in the PDF), which the
citations use. The printed page comes, in this order:
1. from `--prima-pagina N` (first page; with `--da-pagina K`, from page, default 1): page K of the PDF is p. N and
   the following ones continue; pages before K get no marker. For many files: columns `prima_pagina` and
   `da_pagina` in the `--metadati` CSV;
2. from the page labels declared by the PDF (JSTOR PDFs have "p. 61", "p. 62"...), unless they merely repeat the
   position in the file;
3. from the numbers printed at the top or bottom of the page, if the offset from the position in the PDF is
   constant (at least 3 pages and most of those with a number). Pages without a readable number get the page by
   continuity, marked "dedotta" (inferred) in the marker; the header has `[PAGES_STATUS: dedotto]` and `PAGES_NOTE`
   says how many pages were read. It is worth checking samples.

If none of the three applies (irregular numbering, plates, gaps), no marker: the citation stops at the document. The
test (`--prova`) says which way was used. `--senza-pagine` (without pages) does not mark the pages.

**Scanned PDFs with a text layer.** Many archival PDFs already contain an old OCR, often poor. If the pages are scans
(an image covers the page) and have a text layer, `importa.py` re-runs OCR on 3 pages of the body of the volume (at
25%, 50% and 75%) and compares it with the layer:
- if they agree within 2% of the characters, it keeps the layer (no need to redo OCR);
- if they disagree and the OCR is confident (average confidence at least 85), it discards the layer and redoes OCR
  on the whole document, reusing the pages already read;
- if they disagree but the OCR is not confident, it keeps the layer and flags it in the warnings as to be checked.

The choice appears in `TEXT_METHOD`, in the warnings and in the log. A PDF with native text (no scans) is used as it
is. Options: `--campione N` (sample: pages compared; 0 = no comparison), `--ocr strato` (always use the layer),
`--ocr sempre` (always redo OCR).

**PAGE XML and ALTO XML exports** (Transkribus, eScriptorium and other tools): no OCR needed. Give the export
folder or its `.zip` archive, which must not be extracted:

```
python importa.py importa "<export folder>/ZP1967-01-12" --serie "Zëri i Popullit" --prova 3
python importa.py importa "<export folder>/ZP1967-01-12" --serie "Zëri i Popullit"
```

- A folder of `.xml` pages, or a `.zip`, becomes **one document**; pages follow the natural order of the names (2
  before 10). The folder name serves as the name of the imported file (for periodicals: the date, such as
  `ZP1967-01-12`).
- The reading order of the regions declared in the file is respected. Lines break as in the original; there is a
  blank line between two regions.
- Where the file declares the printed page number (in PAGE the "page-number" region, in ALTO `PRINTED_IMG_NR`) the
  marker `[[p. 12 | img 3]]` (printed page | image of the export) is written, which the citations use. Without a
  declared number no marker is written.
- The header records `TEXT_METHOD` (PAGE/ALTO import), `OCR_ENGINE` (the tool named in the file: Transkribus,
  Kraken...), `PAGES` (printed pages) and `OCR_CONFIDENCE`: the confidence of the original engine, on a 0-100 scale,
  is indicative and not comparable with Tesseract's.
- XML files that are not pages (METS, metadata) are ignored and listed among the warnings.

**Header check**: `python importa.py controlla` (or a subfolder: `controlla riviste/zeri_i_popullit`) reports errors
(missing citation, invalid date, empty text) and warnings (repeated document numbers, dates to check, weak OCR,
`DATE_STATUS` outside the field vocabulary, page markers not recognised or out of order) in
`audit/checks/controllo_<date>.csv`.

**Migrating the statuses**: older files with a `DATE_STATUS` that contains a source ("dal nome del file", from the
file name; "letta nella prima pagina (OCR): da controllare", read on the first page...) are brought onto the closed
vocabulary with `python importa.py controlla --migra-stati`: the status becomes `dedotto`/`da verificare`, the
source moves to `DATE_NOTE`. Only the header lines are rewritten, never the text. For a preliminary check on a
subfolder: `controlla <subfolder> --migra-stati`.

**Names in Albanian sources.** The Albanian press writes foreign names as they are pronounced and declines them
(Grippa: "Gripa", "Gripës", "Gripën"). The forms already in the cards are not enough: for each entity ask the chat
for `esplora_nome`, which, when Albanian texts are present, also looks for the probable Albanian transcriptions and
the stems of the declined forms, and proposes only the attested ones; they enter the card after your confirmation.

**Before using results in a new language**, it is worth running a quick test of the models on reading that
language (twenty or so passages verified by you), as for new models (see "Measurements on a hand-verified set").

## Testing OCR engines

`prova_ocr.py` measures which engine reads a series best, on the same pages. In the `scripts` folder:

```
python prova_ocr.py motori --lingua zh
python prova_ocr.py prepara "<scan.pdf>" --nome china_icm --lingua zh --pagine 50,200,320
python prova_ocr.py misura china_icm
```

1. `motori` (engines): which engines are available and why the others are not. Today: Tesseract, also with
   different page segmentations (`tesseract:3`, `tesseract:6`). PaddleOCR is used from a separate Python (see
   `ocr_paddle.py`); on the author's computer it was too slow, about 50 seconds per page. Kraken needs Linux (on
   Windows, WSL).
2. `prepara` (prepare): renders the pages as images and has every engine read them; if the PDF already has a text
   layer, it adds it to the comparison (`strato_pdf`). Everything goes into `results/trials/ocr/<name>/`, outside
   the archive. For every page it writes `pNNN.riferimento.txt`, a proposal to be corrected by hand by looking at
   `pNNN.png`.
3. Correct the references and write your name after `# VERIFICATO_DA:` (verified by). An unverified page does not
   enter the measurement. For Chinese, spaces and line breaks do not count.
4. `misura` (measure): CER (percentage of wrong, inserted or missing characters), also without punctuation, and
   seconds per page for each engine, in `results/trials/ocr/misure_<date>.md`.

## Single archive of readings

Every passage read is kept in `results/archive/readings.jsonl`, whether read by the model or corrected by you. A
later search does not send the same passage to the model again, nor an identical copy of it in another file. So
repeated questions, follow-up questions or questions on other periods of the same entity cost very little.

Corrections recorded with `correggi_passaggio` take precedence over the model's readings.

Incomplete readings are completed at the first search that finds those passages again:
- relevant passages never translated or analysed (for example those classified only by the form of the name in
  earlier sessions) go to analysis, without repeating the sorting;
- "uncertain" passages decided only by a rule, without reading, go back to sorting.

If the synthesis model does not answer, the saved answer says so at the top and the assistant reports it: asking the
same question again redoes only what is missing.

`python archivio.py stato` shows how many readings there are per entity and who made them. Every reading records its
own provenance, separately for the relevance decision and for the translation:
- read by a model (which one);
- assisted reading in a session (in the chat), not verified by hand;
- decided by a rule (which rule: unambiguous form of the name, block classification or exclusion in a session,
  table-of-contents entry).

`python archivio.py provenienza` records the provenance in old readings that lack it (`--prova`: counts only). For
exclusions made in a session there is one more rule: if the same reason recurs in at least 5 passages of the same
entity, the exclusion counts as made in a block, that is, by rule.

When a card is renamed or merged with another, the readings stay in the archive under the old name. To bring them
back under the card:
```
python archivio.py equivalenza "old name" "card name" "note"
python archivio.py riattribuisci "old name" "card name"
python archivio.py riattribuisci "old name" "card name" --applica
```
The first command records that the two names refer to the same entity (`results/archive/equivalences.json`). The
second recomputes the passages as the card would extract them and writes the plan into `results/archive/` without
touching anything. Every old reading falls into one of these cases: already read under the card, to be reassigned,
with a different decision, outside the card (a form the card does not have). The third adds to the archive only the
readings to be reassigned, after making a copy in `system/backups`.

**Suspect dates in summaries.** Until 25/10/2026 the analysis prompt asked to complete the year of dates "from the
date of the source". A past event in a month later than the source's month thus ended up in the source's year
instead of the year before (Renmin ribao, 2 August 1979: Berlinguer in Moscow "in October", read as October 1979).
Now the rule compares the month with the date of the source and, if it is not certain, leaves the date without a
year. To find and re-read the readings already in the archive:
```
python archivio.py date_sospette
python archivio.py date_sospette --applica
```
The first command writes the plan into `results/archive/date_sospette_<date>.csv` without touching anything:
relevant readings whose summary has a date after the source's, in the same year, that the original sentence does
not write. The second, after a copy in `system/backups`, marks for re-reading those read by a model: at the next
search on that entity (also from the chat) the model redoes only translation and summary, and the relevance decision
stays. Readings made in a session appear in the plan as "da controllare a mano" (to check by hand). It can be
limited to one card: `python archivio.py date_sospette "Enrico Berlinguer"`. The check does not see the opposite
error (an announcement in a month before the source's, which belongs to the following year).

### Re-reading the passages of a model

If a model turns out to be unreliable (for example after the measurements of `valutazione.py`), first select another
profile (`installa.py modello usa`), then run the search again asking to re-read that model's passages:
```
python ricerca.py "Enrico Berlinguer" --rileggi-modello gpt-oss-20b
```
In the chat: "Run the search on Berlinguer again, re-reading the passages read by gpt-oss-20b" (option
`rileggi_modello`). The search's passages whose relevance or translation comes from a model whose name contains that
word (at least three characters; the exact names are in section 5 of the answers and in the "Lettura" line of the
passages) go back to the current model. Corrections made by hand are never re-read. The new reading replaces the old
one in the archive, which however stays in the `readings.jsonl` file as history. If the current model matches the
same name, the search says so: re-reading would use the same model.

## Fewer requests to the model

The settings are in `config.ini`, section `[estrazione]` (extraction):
- `lotto_smistamento = 6` (sorting batch): how many passages are sorted (relevant yes/no) with a single request.
- `forme_sicure = si` (safe forms): if the passage contains a form of the name that leaves no doubt, sorting is
  skipped. These count as safe:
  - Chinese forms with the middle dot, such as 雅克·格里巴;
  - acronyms with brackets;
  - full first names and surnames.

  Short titles in 《》 do not count (《新团结》, for example, is also the "Neue Einheit" of the KPD/ML), nor generic
  party names without a qualifier (比利时共产党, "Belgian Communist Party", 意大利共产党), which also refer to the
  official party.
- Table-of-contents or list entries are recognised and recorded without translation or analysis. An example is the
  indexes of the Peking Review.

## Validating a new model

In the `scripts` folder:
```
python valuta.py "Nuova Unità"                                         (the current configuration)
python valuta.py "Nuova Unità" --modelli "glm-4.7; nemotron-3-ultra"   (one by one, with a comparison table)
```
The script compares the models' sorting with a reference reading in the project's `results/references/<name>` (in
the author's project, `nuova_unita`: an assisted reading, not verified by hand). Tests go into `results/trials/` and
do not touch the archive. Target: recall ≥ 95%. With `--modelli` (and in `valutazione.py modelli` and `misura`) the
models are requested from FreeLLMAPI, through its profile: the one in use, if it is a FreeLLMAPI profile, otherwise
the first in `models.ini`. For measurements on any corpus and with any service, see "Measurements on a
hand-verified set".

## Testing chat models

Chat models do not read the passages: they use the tools. To choose them, `prova_chat.py` simulates the client on a
real question (real tools, those that write are simulated: it changes nothing) and computes a score out of 8: guida
called first, procedure followed, no answer reconstructed with apri_fonte, confirmation asked, expected Chinese form,
no files or lines, no "corpus", text without stray characters.

```
python prova_chat.py --modelli "auto:chat; gpt-oss-120b; nemotron-3-ultra"
python prova_chat.py --modelli "gpt-oss-120b" --domanda "..." --forma 格里巴 --istruzioni-complete
```

Results and conversations in `results/trials/chat/`. The score measures the procedure and the cleanliness of the
text, not the quality of the choices: the answers must be read (for example, a model may propose as a form of the
name another person found through the alignment).

## Measurements on a hand-verified set

`valutazione.py` builds a reference set verified by you and measures on it both the extraction and the readings (by
model and by provenance level). It works on any corpus. In the `scripts` folder:
```
python valutazione.py campione test1 --n 100
python valutazione.py candidati test1 --entita "Franz Strobl" --file 60
python valutazione.py importa test1
python valutazione.py misura test1 --modelli "gemma4; nemotron-3-ultra"
```
1. `campione` (sample): draws a stratified sample (series, language, decision, provenance) of the passages already
   read and writes `results/evaluation/test1/campione.csv`. Fill in the GIUDIZIO (judgement: sì / no / incerto,
   yes / no / uncertain) and VERIFICATO_DA (verified by) columns. The current decision does not appear in the file,
   so the verification is blind.
2. `candidati` (candidates): searches a sample of files for broader forms of the name (surname alone, one letter or
   character different, accents) that the extraction does not find. In `candidati.csv` mark GIUDIZIO = sì for the
   true mentions that were missed.
3. `importa`: checks the two completed files and saves the reference set. The files use the semicolon as separator,
   so Excel opens them already split into columns. They can be saved as CSV or as an Excel workbook
   (`campione.xlsx`, `candidati.xlsx`): the file saved last counts.
4. `misura` (measure): computes recall and precision, with a 95% confidence interval, and writes
   `misure_<date>.md`. The measurements concern the archive's readings (by provenance level), the models given (in
   `results/trials/`, without archive) and the extraction. `--profili "groq-qwen; ollama-qwen-9b"` measures your
   model profiles, of any service (not only FreeLLMAPI): every measurement records profile, service and model, so
   `installa.py modello elenca` and the `modello` tool say whether a profile is measured on these sources ("questo
   profilo", this profile; "stesso modello, altro servizio", same model, other service; or "no").

To compare all the active models in FreeLLMAPI quickly (a few minutes):
```
python valutazione.py modelli reference_1 --solo-elenco
python valutazione.py modelli reference_1
```
The first command shows the models chosen and those discarded with the reason, using the router's data without
making requests: routers and aliases, quota used up, context below 16,000 tokens, duplicates, models not meant for
reading texts. The second has every model read 30 verified passages (half of them not relevant) and then, for the 6
best, the whole verified set. Requests contain 10 passages of different entities and the models work 8 at a time.
The result is in `prova_rapida_<date>.md`. Options: `--prima-fase`, `--migliori`, `--lotto`, `--paralleli`,
`--escludi`. In searches every batch concerns a single entity: the quick test is for comparing models with each
other.

The full measurement, slow, with the same format as the searches (FreeLLMAPI must be running):
```
python valutazione.py misura reference_1 --modelli tutti --solo-elenco
python valutazione.py misura reference_1 --modelli tutti
```
The first command only shows the list of models that would be tested. Routers (`auto`, `fusion`), safety filters,
models for code, images and audio, and specialised tools are excluded; others can be excluded with `--escludi "part
of the name; ..."`. Every model reads the verified passages without archive and without the unambiguous-form rule,
so the measurement concerns only the model. Results are saved as they come in `modelli_<date>.jsonl`; the final
table goes into `misure_<date>.md`. `--limite 6` runs a quick test.

## Troubleshooting

Collected in [`troubleshooting.md`](troubleshooting.md): installation on the three systems, the model that reads the
passages, project and import, chat clients.

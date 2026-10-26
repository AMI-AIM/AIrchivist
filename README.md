# AIrchivist

AIrchivist finds **every** occurrence of a person or an organisation (party, state, newspaper) in a large corpus of
primary sources. It answers with the original passages, a translation and a precise reference. The search itself
(pattern extraction tolerant of OCR errors, indexing, citations, page layout of the answer) runs locally in Python.
Language models do only one job: they read the passages to decide whether each one is relevant, translate it and
summarise. The models can be free ones, reached through [FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi),
Ollama or any OpenAI-compatible service. You ask questions from a chat client connected to the engine's MCP server.

AIrchivist was built for a PhD project on dissident communism between Beijing and Tirana, using Chinese sources first
and Albanian and Italian sources after them. It is designed so that it can be adapted to other research projects.
The full documentation is in Italian (`README.it.md`, `docs/user_guide.it.md`); this page summarises it.

## How it works

1. **Entity card** (`glossary/entities.ini`): every form of the name that the search must find, the full name, related
   entities and ambiguous forms. For a new entity the `esplora_nome` tool proposes only forms attested in the
   sources (including generated Chinese transcriptions), and the card is created after you confirm them.
2. **Extraction** (`estrai_occorrenze.py`): regular expressions that tolerate OCR errors such as hyphenation,
   spaces between CJK characters and glued words. A SQLite FTS5 index selects the files to read.
3. **Reading** (`classifica.py`): the models sort the passages and translate the relevant ones. Everything that has
   been read is stored in a single archive (`results/archive/readings.jsonl`) and is never read twice. Each
   reading records who decided and who translated: a named model, an assisted session or a rule.
4. **Answer** (`sintesi.py`, `evoluzione.py`): eight sections (documents, original passages, explicit data,
   inferences, limits, coverage, final answer, technical data for verification). Citations follow the Chicago
   style and are built from each file's header and from the series profile (`glossary/series.ini`).

Long searches run as separate processes. When the free quotas run out, they wait and resume on their own.

## Requirements

| | Needed for | Notes |
|---|---|---|
| Python 3.10 or later, with SQLite FTS5 | everything | The python.org builds include FTS5. The engine uses only the standard library. |
| A model service | reading passages | Ollama, an OpenAI-compatible service (Groq, Gemini, OpenRouter), the Anthropic API or FreeLLMAPI: a model profile in `scripts/models.ini`, created with `installa.py modello` |
| An MCP client | asking questions | Jan, Claude Desktop, LM Studio, or any client that speaks MCP over STDIO or HTTP |
| PyMuPDF | importing PDFs (optional) | `requirements.txt` |
| Tesseract with the language data you need | importing scans (optional) | Windows: [UB Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki) |
| PaddleOCR in a separate Python | alternative OCR engine (optional) | see "Prova dei motori OCR" in `docs/user_guide.it.md` |

Install requirements system-wide, never inside the project folder.

## Installation

```bash
git clone <repository URL> AIrchivist
cd AIrchivist
python scripts/installa.py inizia
```

`inizia` is a guided first setup: environment check, model profile, first research project, chat client, and a
summary that re-runs the required checks. Each step can be skipped (`--saltati 4`) or run alone (`--passi 3`); run
again, it does not redo completed steps. The same steps one at a time:

```bash
python scripts/installa.py librerie
python scripts/installa.py modello
python scripts/installa.py controlla
```

`librerie` installs the optional libraries listed in `requirements.txt` into the system Python. `modello` walks you
through a model profile (service, model, the name of the environment variable holding the key) and switches to it
only if a test request succeeds; `installa.py modello elenca | usa | prova` list, switch and test profiles later.
`controlla` checks Python, FTS5, the model profiles in use (key and reachability), the research project in use, PyMuPDF, Tesseract and the
OCR languages that the project's series require. It exits with status 1 if a required item is missing.

The engine stays where you put it. `scripts/config.ini` (model profile in use, parameters) sits next to the code so
that you can edit it.

### Connecting a client

```bash
python scripts/installa.py client claude --scrivi
python scripts/installa.py client --verifica
```

`client <name>` prints the MCP server entry (Python interpreter, path of `scripts/mcp_server.py`, `PYTHONUTF8=1`) and
the client's configuration file; with `--scrivi` it adds or updates only the AIrchivist entry in that file — a backup
copy is made first and nothing is written until you confirm. Other values: `jan` (with `--scrivi`, run while Jan is closed: it
also sets the tool timeout, smart routing, tool output size and web search in Jan's own files), `lmstudio` and `json` (the generic `mcpServers` block, no file). `client
--verifica` starts the server the way the client would and checks the MCP handshake and the tool list. For clients
that use HTTP: `python scripts/mcp_server.py --http 8765`.

The server sends the working rules (how to use the tools, how to cite, what not to do) in three ways: in the MCP
`instructions` field, as the MCP prompt `istruzioni`, and through the `guida` tool. If your client ignores the
first two, tell the assistant to call `guida` at the start of each conversation.

## Research projects

The engine (`scripts/`) is separate from the data of a research project. Projects live in `projects/`, next to
the engine and outside version control. A project folder holds `project.ini`, `glossary/` (`entities.ini`,
`series.ini`, `instructions.md` with project-specific rules for the chat model), `sources/` (original uploads,
never modified), `data/` (the processed sources, one `.txt` file per document with a `[FIELD: value]` header),
`audit/` (metadata corrections, open issues, import checks), `results/` (reading archive, searches, answers,
trials, evaluation sets) and `system/` (index, jobs, backups).

```bash
python scripts/progetto.py nuovo projects/albanian_press --nome "Albanian press 1960-1978"
python scripts/progetto.py stato
```

You choose the project in `scripts/config.ini` (`[progetto] cartella`) or with the `AIRCHIVIST_PROGETTO`
environment variable. To serve several projects, run one MCP server per project, each with its own value of that
variable.

New sources (PDF, scans, `.txt`, PAGE XML and ALTO XML exports from Transkribus or eScriptorium) are added with
`scripts/importa.py` or the `importa` tool.

## Skill for chat assistants

A smaller version of the method runs inside a chat assistant, without installing the engine: the `source-search`
skill, written once in `skills/source-search/` and packaged for three places by `python skills/package.py`
(output in `skills/build/`, outside version control):

- `source-search-claude.zip` for claude.ai and Claude Desktop (upload under Customize > Skills);
- `claude-code/`, a Claude Code plugin marketplace (`claude plugin marketplace add ./skills/build/claude-code`,
  then `claude plugin install source-search@airchivist`);
- `source-search-chatgpt.zip`, the same plugin as a skills-only ChatGPT plugin.

The skill works on a small corpus uploaded to the conversation, with no reading archive. When it finds a full
AIrchivist installation on the computer, it uses that project and its archive instead. It is a way to try the
method on a few documents, not a replacement for the engine.

## Tests

```bash
python -m unittest discover -s tests
```

Without PyMuPDF the PDF tests are skipped.

## Status

The tool works on the author's corpus (7,858 files in Chinese and English). Before a general release it still needs
a hand-verified reference set to measure precision and recall (`scripts/valutazione.py`), tests on period scans
and on real Transkribus or eScriptorium exports, a copyright-free example corpus, and an English translation of
the full manual. The repository contains only the engine. The author's research data (corpus, entity cards, series
profiles, chat rules) are not distributed. The tests use their own sample project in `tests/test_project/`.

A fresh clone has no project yet. Create one with `python scripts/progetto.py nuovo projects/<name>`, then select
it in `scripts/config.ini` (`[progetto] cartella = ../projects/<name>`) or with `AIRCHIVIST_PROGETTO`. The field
descriptions for `series.ini` come from `scripts/series_template.ini`.

## Licence

Copyright (C) 2026 Ivan Masci.

The code is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
License, version 3 (see `LICENSE`). If you run a modified version as a network service, including as an MCP server
that other people use, you must make its source code available to those users. The licence does not cover the
sources in the corpus, which remain subject to their own rights.

# AIrchivist

AIrchivist finds **every** occurrence of a person or an organisation (party, state, newspaper) in a large corpus of
primary sources. It answers with the original passages, a translation and a precise reference. The search itself
(pattern extraction tolerant of OCR errors, indexing, citations, page layout of the answer) runs locally in Python.
Language models do only one job: they read the passages to decide whether each one is relevant, translate it and
summarise. The models can be free ones, reached through [FreeLLMAPI](https://github.com/tashfeenahmed/freellmapi),
Ollama or any OpenAI-compatible service. You ask questions from a chat client connected to the engine's MCP server.

AIrchivist was built for a PhD project on dissident communism between Beijing and Tirana, using Chinese sources first
and Albanian and Italian sources after them. It is designed so that it can be adapted to other research projects.
The full documentation is in Italian (`LEGGIMI.md`, `pipeline/ISTRUZIONI.md`); this page summarises it.

## How it works

1. **Entity card** (`entita.ini`): every form of the name that the search must find, the full name, related
   entities and ambiguous forms. For a new entity the `esplora_nome` tool proposes only forms attested in the
   sources (including generated Chinese transcriptions), and the card is created after you confirm them.
2. **Extraction** (`estrai_occorrenze.py`): regular expressions that tolerate OCR errors such as hyphenation,
   spaces between CJK characters and glued words. A SQLite FTS5 index selects the files to read.
3. **Reading** (`classifica.py`): the models sort the passages and translate the relevant ones. Everything that has
   been read is stored in a single archive (`risultati/_archivio/letture.jsonl`) and is never read twice. Each
   reading records who decided and who translated: a named model, an assisted session or a rule.
4. **Answer** (`sintesi.py`, `evoluzione.py`): eight sections (documents, original passages, explicit data,
   inferences, limits, coverage, final answer, technical data for verification). Citations follow the Chicago
   style and are built from each file's header and from the series profile (`serie.ini`).

Long searches run as separate processes. When the free quotas run out, they wait and resume on their own.

## Requirements

| | Needed for | Notes |
|---|---|---|
| Python 3.10 or later, with SQLite FTS5 | everything | The python.org builds include FTS5. The engine uses only the standard library. |
| A model service | reading passages | FreeLLMAPI (default), Ollama, an OpenAI-compatible service or the Anthropic API (`pipeline/config.ini`, `[modello] backend`) |
| An MCP client | asking questions | Jan, Claude Desktop, LM Studio, or any client that speaks MCP over STDIO or HTTP |
| PyMuPDF | importing PDFs (optional) | `requirements.txt` |
| Tesseract with the language data you need | importing scans (optional) | Windows: [UB Mannheim build](https://github.com/UB-Mannheim/tesseract/wiki) |
| PaddleOCR in a separate Python | alternative OCR engine (optional) | see "Prova dei motori OCR" in `pipeline/ISTRUZIONI.md` |

Install requirements system-wide, never inside the project folder.

## Installation

```bash
git clone <repository URL> AIrchivist
cd AIrchivist
python pipeline/installa.py librerie
python pipeline/installa.py controlla
```

`librerie` installs the optional libraries listed in `requirements.txt` into the system Python. `controlla` checks
Python, FTS5, the model service (key and reachability), the research project in use, PyMuPDF, Tesseract and the
OCR languages that the project's series require. It exits with status 1 if a required item is missing.

The engine stays where you put it. `pipeline/config.ini` (models, router, parameters) sits next to the code so
that you can edit it.

### Connecting a client

```bash
python pipeline/installa.py client claude
```

This prints the MCP server entry (Python interpreter, path of `pipeline/mcp_server.py`, `PYTHONUTF8=1`) and the
client's configuration file. It does not change that file. Other values: `jan` (the fields to fill in Jan's MCP
settings), `lmstudio` and `json` (the generic `mcpServers` block). For clients that use HTTP:
`python pipeline/mcp_server.py --http 8765`.

The server sends the working rules (how to use the tools, how to cite, what not to do) in three ways: in the MCP
`instructions` field, as the MCP prompt `istruzioni`, and through the `guida` tool. If your client ignores the
first two, tell the assistant to call `guida` at the start of each conversation.

## Research projects

The engine (`pipeline/`) is separate from the data of a research project. A project folder holds `data/` (the
sources, one `.txt` file per document with a `[FIELD: value]` header), `entita.ini`, `serie.ini`, `istruzioni.md`
(project-specific rules for the chat model), `audit_fonti/`, the index, results and answers.

```bash
python pipeline/progetto.py nuovo "C:\Research\Albanian press" --nome "Albanian press 1960-1978"
python pipeline/progetto.py stato
```

You choose the project in `pipeline/config.ini` (`[progetto] cartella`) or with the `AIRCHIVIST_PROGETTO`
environment variable. To serve several projects, run one MCP server per project, each with its own value of that
variable.

New sources (PDF, scans, `.txt`, PAGE XML and ALTO XML exports from Transkribus or eScriptorium) are added with
`pipeline/importa.py` or the `importa` tool.

## Skill for chat assistants

A smaller version of the method runs inside a chat assistant, without installing the engine: the `ricerca-fonti`
skill, written once in `skills/ricerca-fonti/` and packaged for three places by `python pipeline/confeziona.py`
(output in `dist/`):

- `ricerca-fonti-claude.zip` for claude.ai and Claude Desktop (upload under Customize > Skills);
- `claude-code/`, a Claude Code plugin marketplace (`claude plugin marketplace add ./dist/claude-code`, then
  `claude plugin install ricerca-fonti@airchivist`);
- `ricerca-fonti-chatgpt.zip`, the same plugin as a skills-only ChatGPT plugin.

The skill works on a small corpus uploaded to the conversation, with no reading archive. When it finds a full
AIrchivist installation on the computer, it uses that project and its archive instead. It is a way to try the
method on a few documents, not a replacement for the engine.

## Tests

```bash
python -m unittest discover -s pipeline/test
```

Without PyMuPDF the PDF tests are skipped.

## Status

The tool works on the author's corpus (7,858 files in Chinese and English). Before a general release it still needs
a hand-verified reference set to measure precision and recall (`pipeline/valutazione.py`), tests on period scans
and on real Transkribus or eScriptorium exports, a copyright-free example corpus, and an English translation of
the full manual. The repository contains only the engine. The author's research data (corpus, entity cards, series
profiles, chat rules) are not distributed. The tests use their own sample project in `pipeline/test/progetto_prova/`.

A fresh clone has no project yet. Create one with `python pipeline/progetto.py nuovo <folder>`, then select it in
`pipeline/config.ini` or with `AIRCHIVIST_PROGETTO`. The field descriptions for `serie.ini` come from
`pipeline/serie_modello.ini`.

## Licence

Copyright (C) 2026 Ivan Masci.

The code is free software: you can redistribute it and/or modify it under the terms of the GNU Affero General Public
License, version 3 (see `LICENSE`). If you run a modified version as a network service, including as an MCP server
that other people use, you must make its source code available to those users. The licence does not cover the
sources in the corpus, which remain subject to their own rights.

<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/marchio/pressmark-logotipo-scuro.svg">
    <img src="assets/marchio/pressmark-logotipo-chiaro.svg" alt="Pressmark" width="360">
  </picture>
</h1>

<p align="center">
  <b>Every mention of a name in your sources, with the original passage and an exact citation.</b><br>
  <a href="https://github.com/AMI-AIM/Pressmark/releases/latest">Download for Windows</a> ·
  <a href="docs/quickstart.md">Quickstart</a> ·
  <a href="docs/user_guide.md">User guide</a> ·
  <a href="README.it.md">Italiano</a>
</p>

Pressmark is a desktop application for historians and other researchers who work with large collections of primary
sources: newspapers, periodicals, archival documents, scans. Ask about a person or an organisation (a party, a
state, a newspaper) and Pressmark finds **every** occurrence in your corpus, then answers with the original
passages, their translation and a citation down to the page.

The search runs on your computer. A language model of your choice only reads the passages that the search has
found: it decides whether each one is relevant, translates it and helps write the answer. It never makes up
the sources.

## What it does

- **Finds every form of a name**, including spelling variants, OCR errors (broken hyphenation, glued words, spaces
  between characters) and non-Latin scripts. For a new name it proposes only the forms actually attested in your
  sources, and you confirm them.
- **Answers with evidence**: original passages, translations, explicit facts kept apart from inferences, known
  limits and coverage. Citations follow the Chicago Manual of Style and are built from each document's metadata.
- **Lets you check everything**: each citation opens the page it comes from, the scan if there is one. In the
  conversation, a reference that no source supports is marked in red.
- **Imports your material**: PDFs, page scans (with OCR), `.txt` files, and PAGE XML or ALTO XML exports from
  Transkribus or eScriptorium. You review the metadata in a table before anything is imported.
- **Never reads the same passage twice**: every reading is archived with the model that made it, so new questions
  cost less and you can see who decided what.

## Installation

### Windows

Download `Pressmark-<version>-setup.exe` from the [latest release](https://github.com/AMI-AIM/Pressmark/releases/latest)
and run it. It needs no administrator rights and includes everything: Python, PDF support, OCR (English and
Italian, more languages can be downloaded from the app). Open **Pressmark** from the Start menu. On first launch,
the setup window walks you through creating a project, choosing a model and importing your first sources.

Windows 10 or 11, 64-bit. The installer is not signed yet: if SmartScreen warns you, choose "More info" → "Run
anyway". Updating or uninstalling never touches your projects, which are kept in `Documents\Pressmark`.

### macOS, Linux, or from source

You need Python 3.10 or later.

```bash
git clone https://github.com/AMI-AIM/Pressmark.git
cd Pressmark
python scripts/installa.py inizia
python scripts/app.py
```

`installa.py inizia` checks your system and tells you what is missing, with the command for your system: PyMuPDF
for PDFs (`python scripts/installa.py librerie`), Tesseract for scans. `app.py` opens the interface. On macOS and
Linux the command may be `python3`.

## Choosing a model

Pressmark works with the model you prefer, and you can switch at any time:

| Option | Examples | Notes |
|---|---|---|
| Local | Ollama | Free, nothing leaves your computer; needs a capable machine |
| Service with an API key | Groq, OpenRouter, Gemini, any OpenAI-compatible service | Many offer a free tier |
| Anthropic API | Claude | Pay as you go |
| A router across free services | FreeLLMAPI | Moves to another service when a quota runs out |

Keys stay in your environment variables, never in Pressmark's files. Before switching, Pressmark tests the
connection, and it tells you which models have been measured on your sources.

## How it works

1. **The name**: a card lists every form the search must find, and the forms that are ambiguous.
2. **The search**: a full-text index and OCR-tolerant patterns find every occurrence. This is plain code: it is
   exhaustive and repeatable.
3. **The reading**: the model sorts the passages and translates the relevant ones, a few at a time. Long
   searches run in the background and resume on their own if a free quota runs out.
4. **The answer**: a document to read, print or keep, with the answer first and then the evidence behind it.

You can also ask questions from a chat client such as Jan, Claude Desktop or LM Studio: Pressmark includes an MCP
server with the same tools, and the setup window connects it for you.

## Documentation

- [Quickstart](docs/quickstart.md): from installation to your first answer in about 15 minutes.
- [User guide](docs/user_guide.md): everything in detail, including the command line.
- [Troubleshooting](docs/troubleshooting.md): common problems and their solutions.

The interface is in Italian for now, and so are the translations of the passages. The guides are in English and
Italian, and the English guide explains every Italian term you will meet.

## Development

```bash
python -m unittest discover -s tests
python confezione/costruisci.py --lingue ita
```

The first command runs the tests, which use their own sample project in `tests/test_project/`. The second builds the
Windows installer (it needs Python of the version to bundle, Tesseract and Inno Setup 6). Research projects live
outside version control: the repository contains only the application.

## Licence

Copyright (C) 2026 Ivan Masci. Pressmark is free software under the GNU Affero General Public License, version 3
([`LICENSE`](LICENSE)). If you run a modified version as a network service, including as an MCP server other people
use, you must make its source code available to them. The licence does not cover your sources, which remain
subject to their own rights.

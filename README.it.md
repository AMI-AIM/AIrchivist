<h1 align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/marchio/pressmark-logotipo-scuro.svg">
    <img src="assets/marchio/pressmark-logotipo-chiaro.svg" alt="Pressmark" width="360">
  </picture>
</h1>

<p align="center">
  <b>Ogni menzione di un nome nelle tue fonti, con il passaggio originale e la citazione esatta.</b><br>
  <a href="https://github.com/AMI-AIM/Pressmark/releases/latest">Scarica per Windows</a> ·
  <a href="docs/quickstart.it.md">Primi passi</a> ·
  <a href="docs/user_guide.it.md">Guida d'uso</a> ·
  <a href="README.md">English</a>
</p>

Pressmark è un'applicazione per storici e ricercatori che lavorano su grandi raccolte di fonti primarie: giornali,
riviste, documenti d'archivio, scansioni. Chiedi di una persona o di un ente (un partito, uno Stato, una testata) e
Pressmark trova **tutte** le occorrenze nel tuo corpus, poi risponde con i passaggi originali, la loro traduzione e
la citazione fino alla pagina.

La ricerca gira sul tuo computer. Il modello linguistico che scegli legge soltanto i passaggi trovati dalla ricerca:
decide se ciascuno è pertinente, lo traduce e aiuta a scrivere la risposta. Le fonti non le inventa mai.

## Che cosa fa

- **Trova ogni forma di un nome**, comprese varianti di grafia, errori dell'OCR (sillabazioni spezzate, parole
  attaccate, spazi tra i caratteri) e scritture non latine. Per un nome nuovo propone solo le forme davvero
  attestate nelle tue fonti, e sei tu a confermarle.
- **Risponde con le prove**: passaggi originali, traduzioni, dati espliciti tenuti distinti dalle inferenze, limiti e
  copertura della ricerca. Le citazioni seguono il Chicago Manual of Style e si ricavano dai metadati di ogni
  documento.
- **Ti fa controllare tutto**: ogni citazione apre la pagina da cui viene, con la scansione se c'è. Nella
  conversazione, un riferimento che nessuna fonte sostiene è segnato in rosso.
- **Importa il tuo materiale**: PDF, scansioni di pagine (con OCR), file `.txt` ed esportazioni PAGE XML o ALTO XML di
  Transkribus o eScriptorium. Prima di importare, controlli i metadati in una tabella.
- **Non rilegge mai lo stesso passaggio**: ogni lettura è archiviata con il modello che l'ha fatta, così le domande
  nuove costano meno e si vede chi ha deciso che cosa.

## Installazione

### Windows

Scarica `Pressmark-<versione>-setup.exe` dall'[ultima release](https://github.com/AMI-AIM/Pressmark/releases/latest)
e avvialo. Non servono diritti di amministratore e c'è già tutto: Python, la lettura dei PDF, l'OCR (inglese e
italiano; le altre lingue si scaricano dal programma). Apri **Pressmark** dal menu Start. Al primo avvio la finestra
«Preparazione» ti guida a creare un progetto, scegliere un modello e importare le prime fonti.

Serve Windows 10 o 11 a 64 bit. L'installatore non è ancora firmato: se SmartScreen avvisa, scegli «Ulteriori
informazioni» → «Esegui comunque». Aggiornare o disinstallare il programma non tocca i tuoi progetti, che stanno in
`Documenti\Pressmark`.

### macOS, Linux o dal codice

Serve Python 3.10 o successivo.

```bash
git clone https://github.com/AMI-AIM/Pressmark.git
cd Pressmark
python scripts/installa.py inizia
python scripts/app.py
```

`installa.py inizia` controlla il sistema e ti dice che cosa manca, con il comando per il tuo sistema: PyMuPDF per i
PDF (`python scripts/installa.py librerie`), Tesseract per le scansioni. `app.py` apre l'interfaccia. Su macOS e
Linux il comando può essere `python3`.

## Scegliere il modello

Pressmark funziona con il modello che preferisci, e lo cambi quando vuoi:

| Scelta | Esempi | Note |
|---|---|---|
| In locale | Ollama | Gratuito, nulla esce dal tuo computer; serve una macchina capace |
| Un servizio con una chiave | Groq, OpenRouter, Gemini, qualsiasi servizio compatibile OpenAI | Molti hanno un piano gratuito |
| API di Anthropic | Claude | A consumo |
| Un router tra servizi gratuiti | FreeLLMAPI | Passa a un altro servizio quando una quota finisce |

Le chiavi restano nelle variabili d'ambiente, mai nei file di Pressmark. Prima di cambiare modello Pressmark prova il
collegamento, e ti dice quali modelli sono stati misurati sulle tue fonti.

## Come funziona

1. **Il nome**: una scheda elenca tutte le forme che la ricerca deve trovare, e quelle ambigue.
2. **La ricerca**: un indice del testo e schemi che tollerano gli errori dell'OCR trovano tutte le occorrenze. È
   codice, non un modello: completa e ripetibile.
3. **La lettura**: il modello smista i passaggi e traduce quelli pertinenti, qualcuno alla volta. Le ricerche lunghe
   vanno avanti da sole e, se una quota gratuita finisce, riprendono per conto loro.
4. **La risposta**: un documento da leggere, stampare o conservare, con la risposta in testa e dopo le prove su cui
   si fonda.

Le domande si possono fare anche da un client di chat come Jan, Claude Desktop o LM Studio: Pressmark include un
server MCP con gli stessi strumenti, e la «Preparazione» lo collega per te.

## Documentazione

- [Primi passi](docs/quickstart.it.md): dall'installazione alla prima risposta in circa 15 minuti.
- [Guida d'uso](docs/user_guide.it.md): tutto nel dettaglio, compresa la riga di comando.
- [Problemi frequenti](docs/troubleshooting.it.md): i problemi più comuni e come risolverli.

L'interfaccia per ora è in italiano, e in italiano sono anche le traduzioni dei passaggi. Le guide ci sono in
italiano e in inglese.

## Sviluppo

```bash
python -m unittest discover -s tests
python confezione/costruisci.py --lingue ita
```

Il primo comando esegue i test, che usano un progetto di prova proprio (`tests/test_project/`). Il secondo costruisce
l'installatore per Windows (servono Python della versione da includere, Tesseract e Inno Setup 6). I progetti di
ricerca stanno fuori dal controllo di versione: il repository contiene solo l'applicazione.

## Licenza

Copyright (C) 2026 Ivan Masci. Pressmark è software libero con licenza GNU Affero General Public License, versione 3
([`LICENSE`](LICENSE)). Chi offre una versione modificata come servizio in rete, anche come server MCP usato da altri,
deve renderne disponibile il codice. La licenza non riguarda le tue fonti, che restano soggette ai propri diritti.

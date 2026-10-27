# AIrchivist: primi passi

Dall'installazione alla prima risposta in circa 15 minuti di lavoro attivo, su Windows, macOS o Linux. Servono:
- qualche documento tuo: PDF (con testo o scansionati), scansioni delle pagine o file `.txt`. Per la prima prova
  bastano due o tre PDF;
- un modello che legga i passaggi: una chiave gratuita di un servizio (Groq, Google Gemini, OpenRouter) oppure
  Ollama sul tuo computer;
- facoltativo, per fare domande in conversazione: un client di chat che usi server MCP (Jan, Claude Desktop, LM
  Studio).

La guida completa è in [`user_guide.it.md`](user_guide.it.md); se qualcosa non va, vedi
[`troubleshooting.it.md`](troubleshooting.it.md). Comandi, messaggi e nomi dei campi del sistema sono in italiano.

## 1. Installa Python (e, se servirà, Tesseract)

| | Python 3.10 o successivo | Tesseract (solo per le scansioni) |
|---|---|---|
| Windows | https://www.python.org/downloads/ — durante l'installazione spunta **«Add python.exe to PATH»** | `winget install -e --id UB-Mannheim.TesseractOCR`; nella procedura spunta le lingue che servono |
| macOS | https://www.python.org/downloads/ oppure `brew install python` | `brew install tesseract tesseract-lang` |
| Linux | di solito già presente (`python3 --version`); altrimenti `sudo apt install python3` | `sudo apt install tesseract-ocr tesseract-ocr-<lingua>` (es. `tesseract-ocr-ita`) |

Su macOS e Linux il comando può chiamarsi `python3` invece di `python`: usa quello nei comandi seguenti. Dopo
un'installazione chiudi e riapri il terminale. Tutto si installa nel sistema, mai dentro la cartella del motore.

## 2. Scarica AIrchivist

Con git:
```
git clone <indirizzo del repository> AIrchivist
cd AIrchivist/scripts
```
Oppure scarica l'archivio `.zip` del repository, estrailo dove vuoi e apri un terminale nella sua cartella
`scripts`. Tutti i comandi di questa pagina si danno da lì.

## 3. Avvio guidato

```
python installa.py inizia
```

Cinque passi; ognuno fa una domanda alla volta e propone una risposta (Invio per accettarla):
1. **Ambiente**: controlla Python e SQLite. PyMuPDF (per i PDF) e Tesseract sono facoltativi; se manca PyMuPDF:
   `python installa.py librerie`.
2. **Modello**: scegli il servizio. Il più semplice è «un servizio con una sola chiave», per esempio Groq: la
   procedura dice dove creare la chiave gratuita, te la chiede (non si vede mentre la scrivi), la salva come
   variabile d'ambiente del tuo utente e fa una prova. Con Ollama non serve nessuna chiave.
3. **Primo progetto**: nome della tua ricerca e cartella (va bene quella proposta, dentro `projects/`).
4. **Chat**: scegli il client che usi (Jan, Claude Desktop, LM Studio) oppure «nessuno, per ora». Il sistema
   mostra che cosa cambierà nel file del client e scrive solo dopo la tua conferma, con una copia di sicurezza.
   Jan dev'essere chiuso mentre si scrive.
5. **Riepilogo**: «Tutto pronto» se non manca nulla.

Puoi interrompere e rilanciare `inizia` quando vuoi: non rifà i passi già completati.

## 4. Importa i tuoi documenti

Metti i documenti in una cartella (per esempio `documenti_da_importare` nella tua cartella personale), poi:

```
python importa.py proponi <cartella dei documenti>
```

Il sistema legge i file senza importarli e scrive una tabella, `audit/review_<data>.csv` nella cartella del
progetto: una riga per documento, con la serie proposta (la rivista, il giornale, il libro), la data, il titolo,
l'autore, la lingua, le pagine. Aprila con Excel o LibreOffice: la colonna **da_controllare** spiega i dubbi.
Correggi ciò che è sbagliato o manca (soprattutto i nomi delle serie e la lingua: `it`, `en`, `fr`, `sq`, `zh`...),
salva, e poi:

```
python importa.py applica <percorso della tabella> --prova
python importa.py applica <percorso della tabella>
```

Il primo comando controlla la tabella e dice che cosa farebbe; il secondo importa (con l'OCR dove serve) e
prepara l'indice delle fonti.

## 5. La prima domanda

### Dalla chat

Riavvia il client se era aperto. Controlla che il server «airchivist» risulti acceso nelle impostazioni MCP del
client e che il modello della chat sappia usare gli strumenti (in Jan: **Tools** attivo sul modello, **Web Search**
spento). Poi scrivi, per esempio:

> Cosa dicono le fonti di Enver Hoxha?

L'assistente cerca nelle fonti le forme del nome effettivamente attestate (con conteggi ed esempi) e te le mostra:
conferma quelle giuste. La ricerca parte e l'assistente ne segue l'avanzamento; una ricerca su pochi documenti
dura qualche minuto. A ricerca finita ricevi un riassunto e il percorso del **documento della risposta**, un file
`.html` da aprire con il browser: passaggi originali, traduzione, citazioni con la pagina, limiti e copertura.

### Senza chat

Scrivi la scheda dell'entità in `glossary/entities.ini` della cartella del progetto, con le forme del nome che
la ricerca deve trovare:

```
[Enver Hoxha]
tipo = persona
varianti = Enver Hoxha; Hoxha; Enver Hoxhës
```

Poi:

```
python ricerca.py "Enver Hoxha" --apri
```

La ricerca estrae i passaggi, li fa leggere al modello e, alla fine, apre il documento della risposta nel
browser (con un servizio gratuito e pochi documenti, due o tre minuti). Il documento resta in
`results/searches/<nome>/risposta.html` del progetto; le risposte delle ricerche fatte dalla chat si raccolgono
anche in `results/answers/`.

## E adesso

- Altri documenti: rifai il passo 4 con una cartella nuova.
- Cambiare il modello che legge i passaggi: `python installa.py modello` (profilo nuovo) e
  `python installa.py modello usa <profilo>`.
- Più progetti, citazioni, esportazioni di Transkribus o eScriptorium, misure di affidabilità dei modelli: la
  [guida completa](user_guide.it.md).

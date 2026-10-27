# Problemi frequenti

Casi incontrati nelle prove reali del sistema, con la soluzione. Il primo controllo, per quasi tutto, è:

```
python installa.py controlla
```

Dice che cosa manca e come rimediare; esce con 1 se manca un requisito necessario. I comandi si danno nella
cartella `scripts` del motore; su macOS e Linux il comando può chiamarsi `python3`.

## Installazione

- **«python» non è riconosciuto** (Windows): Python non è nel PATH. Reinstallalo spuntando «Add python.exe to
  PATH», oppure usa `py` al posto di `python`. Chiudi e riapri il terminale dopo l'installazione.
- **«SQLite con FTS5: FTS5 non disponibile»**: il Python in uso è compilato senza la ricerca a testo pieno di
  SQLite. Usa il Python di python.org (o, su macOS, quello di Homebrew), che la include.
- **`installa.py librerie` fallisce con «externally-managed-environment»** (Debian, Ubuntu e altre distribuzioni
  Linux recenti): il sistema non lascia installare librerie con pip nel Python di sistema. Installa PyMuPDF dai
  pacchetti della distribuzione: `sudo apt install python3-fitz`.
- **«Tesseract non trovato»**: installalo (Windows `winget install -e --id UB-Mannheim.TesseractOCR`, macOS
  `brew install tesseract tesseract-lang`, Linux `sudo apt install tesseract-ocr`) e riapri il terminale; se è
  in una cartella non standard, indicane il percorso in `config.ini`, sezione `[ocr]`, voce `tesseract`.
- **Mancano le lingue dell'OCR** (`controlla` le elenca per le serie del progetto): su Windows riesegui
  l'installazione di Tesseract e spunta le lingue; su macOS `tesseract-lang` le contiene tutte; su Linux
  `sudo apt install tesseract-ocr-<codice>` (es. `tesseract-ocr-sqi` per l'albanese). In alternativa copia
  `<codice>.traineddata` da https://github.com/tesseract-ocr/tessdata_best nella cartella `tessdata` di Tesseract.

## Modello che legge i passaggi

- **La prova del modello fallisce con «il servizio non trova il modello»**: il nome del modello non esiste (più)
  presso il servizio; i servizi gratuiti ritirano spesso i modelli. Crea un altro profilo con
  `python installa.py modello`: con la chiave, la procedura elenca i modelli che il servizio offre davvero.
- **«Manca la chiave» o «variabile … assente»**: la variabile d'ambiente della chiave non c'è nel terminale (o
  nel client di chat) in uso. Dopo averla salvata (Windows `setx NOME "..."`; macOS e Linux una riga
  `export NOME="..."` in `~/.zprofile` o `~/.profile`) chiudi e riapri il terminale e riavvia il client di chat:
  i programmi già aperti non vedono le variabili nuove.
- **Errore 401 o 403**: chiave sbagliata o scaduta. **Errore 404**: modello ritirato. Controlla con
  `python installa.py modello prova <profilo>`.
- **«Il profilo di modello … non esiste»**: il nome scelto in `[modello]` di `config.ini` o `project.ini` non è in
  `models.ini`. `python installa.py modello elenca` mostra i profili; `python installa.py modello usa <profilo>`
  ne sceglie uno.
- **«limite del servizio raggiunto: attendo…»** durante una ricerca: è normale con i servizi gratuiti, che
  limitano le richieste al minuto. La ricerca aspetta e prosegue da sola; quando la quota del giorno è finita,
  riprova a intervalli crescenti per al massimo 36 ore.
- **La ricerca usa ancora il modello di prima**: è una ricerca interrotta, che riprende con i profili con cui era
  partita. Per proseguire con quello scelto adesso: `--usa-modello-attuale`, o chiedilo in chat.

## Progetto e importazione

- **«Senza un progetto scelto il motore non parte»**: crea un progetto con `python installa.py inizia --passi 3`
  (oppure `python progetto.py nuovo <cartella>`); la scelta si scrive in `config.ini`.
- **La tabella di revisione si apre in una sola colonna**: Excel non ha riconosciuto il separatore. Aprila con
  «Dati > Da testo/CSV» indicando il punto e virgola, oppure con LibreOffice, che lo chiede all'apertura.
- **«serie da indicare» nella colonna da_controllare**: per un articolo isolato il sistema non sa in quale rivista
  è uscito; scrivi il nome della rivista nella colonna `serie`. Per più autori, scrivili come vanno citati
  (`Cognome, Nome; Cognome, Nome`).
- **OCR pieno di errori**: scansione a bassa risoluzione o storta; rifalla a 300 dpi, in scala di grigi. Per testi
  con molte parole in un'altra lingua, nel profilo della serie (`glossary/series.ini`) metti per esempio
  `ocr_lingue = sqi+eng`.
- **La ricerca non trova un nome che c'è nei testi**: la ricerca cerca solo le forme scritte in `varianti` della
  scheda. Una forma messa solo in `forme_ambigue` non viene cercata: va anche in `varianti`.
  `python schede.py controlla` lo segnala.
- **«Indice delle fonti in costruzione»**: la prima volta, su un corpus grande, l'indice richiede 10-30 minuti;
  nel frattempo la chat lo dice. A mano: `python indice.py costruisci`.

## Chat (Jan, Claude Desktop, LM Studio)

- **Il server di AIrchivist non compare o è spento**: riavvia il client dopo `installa.py client <nome>
  --scrivi`. In Jan la voce scritta a programma aperto si perde (Jan riscrive i suoi file quando si chiude):
  chiudi Jan, rilancia il comando, riapri Jan. Controlla poi il collegamento con
  `python installa.py client --verifica`.
- **Il client non trova `python`**: il comando della voce del server dev'essere il percorso completo
  dell'interprete; `installa.py client <nome> --scrivi` lo scrive così.
- **La chat risponde senza usare gli strumenti**: il modello della chat deve saper usare gli strumenti (in Jan:
  **Tools** attivo sul modello) e la ricerca web dev'essere spenta. Se le istruzioni del server non arrivano al
  modello, scrivi all'inizio della conversazione «chiama lo strumento guida».
- **La chat dice che la ricerca non finisce**: le ricerche girano in un processo a sé e continuano anche se la
  chat smette di aspettare. Chiedi «a che punto è la ricerca?»: l'assistente la ritrova.
- **Il risultato di uno strumento è tagliato**: il client accetta meno caratteri di quelli che il server manda.
  In Jan il valore giusto (8000) lo imposta `installa.py client jan --scrivi`; per altri client abbassa `[mcp]
  max_caratteri` in `config.ini`.
- **«All models exhausted»** (FreeLLMAPI): le quote gratuite del momento sono finite per il modello della chat.
  Riprova più tardi; le ricerche già avviate aspettano e riprendono da sole.

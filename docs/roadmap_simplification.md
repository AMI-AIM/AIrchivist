# Roadmap: semplificazione dell'installazione e dell'uso

Istruzioni per Claude Code (26/10/2026). Riguardano la fase 7 del piano di lavoro (`piano_di_lavoro.md`, lavori 26-38).



## Obiettivo

Un ricercatore esterno, senza competenze di programmazione, con un proprio corpus di PDF, deve poter installare il sistema, importare le fonti e fare la prima ricerca **in meno di un'ora di lavoro attivo**, su Windows, macOS e Linux, senza aprire file di configurazione a mano.

Oggi (analisi del 26/10) ci vuole circa mezza giornata per un utente esperto. I punti in cui un utente esterno abbandona sono tre:
1. il servizio dei modelli (account e chiavi presso più fornitori, catene di FreeLLMAPI);
2. la configurazione della chat (campi MCP da compilare a mano);
3. serie e metadati (concetti tecnici, revisione delle intestazioni senza uno strumento).

Vincoli che restano:
- solo soluzioni gratuite;
- nessun modello imposto: il ricercatore sceglie il proprio e lo cambia quando vuole (lavori 16 e 26);
- ogni scrittura in file che non appartengono al progetto (configurazione dei client, variabili d'ambiente) avviene solo dopo conferma esplicita, con copia di sicurezza;
- l'interfaccia propria è il punto di arrivo (sezione seguente); l'eseguibile unico che la contiene resta rimandato a dopo la verifica del bisogno (lavoro 17).



## Punto di arrivo: l'interfaccia di AIrchivist

Deciso da Ivan il 26/10/2026. Il riferimento per la struttura è l'interfaccia di Chronos (schermate in https://github.com/ai-historian/chronos, cartella `assets/`, in particolare `guide-04-session-panel.png`, `guide-05-choose-provider.png`, `guide-06-import-picker.png`, `guide-07-source-loaded.png`): intestazione con menu a tendina, visore della fonte a sinistra, conversazione a destra, citazioni di pagina cliccabili. Si riprende la struttura, non il codice (licenza PolyForm Noncommercial).

```
+--------------------------------------------------------------------------------------------+
| AIrchivist   Progetto [dissident_communism ▼]   Modello [groq-llama ▼] ●   Importa  Storico  Nuova |
+------------------------------------------------+-------------------------------------------+
| [Fonte] [Passaggi] [Glossario] [Importazioni]  |  Domanda: Cosa dicono le fonti su X?      |
|                                                |  Forme attestate: [x] 贝林格 (167)          |
|  < 12 / 48 >    Peking Review 1980, no. 18     |                   [x] Berlinguer (213)    |
|  +------------------------------------------+  |                   [ ] Enrico (escluso)    |
|  |  pagina della fonte (immagine o testo)   |  |  [Avvia ricerca]   avanzamento 34/60      |
|  |  con il passaggio evidenziato            |  |                                           |
|  +------------------------------------------+  |  Risposta (documento): ... p. 12 ...      |
|                                                |  [Conversa sulle fonti...]       [Invia]  |
+------------------------------------------------+-------------------------------------------+
```

- **Menu «Progetto»**: elenca le cartelle di `projects/`; la scelta cambia corpus, glossario, archivio delle letture, indice e risposte. Voce «Nuovo progetto…» (procedura del lavoro 28). Il cambio è bloccato, con spiegazione, mentre una ricerca del progetto è in corso.
- **Menu «Modello»**: elenca i profili di modello (lavoro 26) con lo stato del collegamento (pallino) e l'indicazione «misurato / non misurato» su questo progetto. Voce «Aggiungi modello…» (procedura guidata, chiave salvata come variabile d'ambiente). La scelta passa per la prova del collegamento: se fallisce resta il modello precedente.
- **Scheda «Fonte»**: la pagina dell'originale (immagine renderizzata da `sources/` con PyMuPDF, oppure il testo di `data/` quando l'originale manca), con navigazione per pagina stampata e posizione nel file, e il passaggio evidenziato.
- **Scheda «Passaggi»**: tabella dei passaggi della ricerca corrente (data, fonte, pertinenza, chi ha letto, traduzione), filtrabile; un clic apre la pagina nella scheda «Fonte».
- **Scheda «Glossario»**: schede delle entità e profili di serie, con modifica guidata.
- **Scheda «Importazioni»**: importazione di file o cartelle e tabella di revisione dei metadati (lavoro 29), modificabile direttamente nell'interfaccia oltre che in Excel.
- **Colonna destra**: il percorso della ricerca è **guidato e deterministico** (domanda, forme attestate da confermare con le caselle, avvio, avanzamento, risposta come documento del lavoro 31); ogni citazione «p. N» è un collegamento che apre la pagina nel visore. Sotto, una conversazione libera sulle fonti che usa gli stessi strumenti del server MCP con il modello scelto: è un'aggiunta, non la via principale, perché i modelli deboli inventano riferimenti quando ricostruiscono la risposta.

### Scelta tecnica (da confermare in fase di progetto)

| Strada | Pro | Contro |
|---|---|---|
| **Applicazione web locale servita da Python** (libreria standard: `http.server`), pagina HTML con JavaScript senza passaggi di compilazione, aperta nel browser | nessun requisito nuovo; usa direttamente le funzioni del motore; funziona su tre sistemi; si potrà confezionare in un eseguibile che apre il browser | da curare: sicurezza (solo `127.0.0.1`, token di sessione), aggiornamenti in tempo reale (polling o Server-Sent Events) |
| Estensione di VS Code, come Chronos | editor ricco, integrazione con i file | richiede VS Code e Node.js; per uno storico è un ambiente estraneo |
| Applicazione desktop (Electron, Tauri) | aspetto da programma | catena di compilazione pesante, contraria al vincolo «solo libreria standard» |

Raccomandata la prima. Librerie JavaScript solo se indispensabili, incluse nel repository (nessun caricamento da internet), con licenza compatibile con AGPL-3.0. Il server MCP resta per chi preferisce Claude Desktop, Jan o altri client: interfaccia e MCP chiamano le stesse funzioni del motore.

Effetto sui lavori di questa roadmap: 26, 29, 30 e 31 diventano anche parti dell'interfaccia (stessa logica, esposta sia da riga di comando sia nell'interfaccia); il 27 (configurazione dei client) resta utile ma perde priorità; il 28 (avvio guidato) si conclude aprendo l'interfaccia; il 33 confeziona interfaccia e motore insieme.



## Ordine dei lavori

I lavori 26-28 hanno l'effetto maggiore e vanno fatti per primi. Il 29 è il più impegnativo e il più importante per l'uso reale. I lavori 35-38 costruiscono l'interfaccia sopra i precedenti (35 e 36 subito dopo 26 e 31). Il 34 chiude il ciclo con utenti veri, sull'interfaccia.



### 26. Scelta del modello, modificabile in ogni momento

Il ricercatore deve poter cambiare modello (o servizio) quando vuole, anche a metà di un progetto, senza che il sistema smetta di funzionare e senza perdere o confondere le letture già fatte.

**Profili di modello.** Ogni modello configurato è un profilo con un nome, in un file del motore fuori dal repository pubblico (per esempio `scripts/models.ini`, escluso da git; nel repository solo `models_template.ini` con gli esempi):
- servizio (Ollama, compatibile OpenAI, Anthropic, FreeLLMAPI), indirizzo, nome del modello, variabile d'ambiente della chiave;
- parametri propri del modello (`json`, `max_token` per ruolo, `parametri_extra`, pausa tra le richieste, timeout): oggi stanno in `config.ini` e valgono per tutti; devono seguire il modello;
- la chiave non si scrive mai nel file: solo il nome della variabile d'ambiente.

**Scelta attiva.** `config.ini` (o `project.ini`, che prevale) indica solo quale profilo usare, anche diverso per ruolo:
```
[modello]
smistamento = groq-llama
analisi = groq-llama
sintesi = ollama-qwen
```

**Comandi.**
- `python scripts/installa.py modello`: procedura guidata per creare un profilo (Ollama, un servizio con una sola chiave, API Anthropic, FreeLLMAPI avanzato).
- `python scripts/installa.py modello elenca | usa <profilo> [--ruolo ...] [--progetto] | prova <profilo> | togli <profilo>`.
- `usa` prova prima il collegamento con una richiesta minima e cambia la scelta **solo se la prova riesce**; altrimenti lascia attivo il profilo precedente e spiega l'errore in parole semplici. Ogni cambio si annota (data, profilo precedente, profilo nuovo) in `system/model_changes.csv` del progetto.
- Dalla chat: strumento MCP (per esempio `modello` con azioni elenca, usa, prova) con la stessa logica e la stessa conferma.

**Cosa garantisce il sistema quando il modello cambia.**
- **Ricerche in corso:** una ricerca usa i profili attivi al suo avvio, registrati nello stato del lavoro (`system/jobs/<id>`). Un cambio vale per le ricerche successive; una ricerca interrotta per quote riprende con il profilo con cui è partita, salvo `--usa-modello-attuale`.
- **Archivio delle letture:** ogni lettura registra già il modello che ha risposto. Le letture di modelli diversi convivono; nulla si rilegge per il solo cambio di modello.
- **Rilettura facoltativa:** `ricerca.py ... --rileggi-modello <nome>` (e l'equivalente nello strumento MCP) rimanda al modello attuale i passaggi letti da un modello indicato, per esempio dopo aver scoperto che era inaffidabile. La lettura nuova sostituisce la vecchia nell'archivio; la vecchia resta nella storia del file.
- **Risposte:** quando i passaggi di una risposta sono stati letti da più modelli, la sezione «Limiti» li elenca con il numero di passaggi di ciascuno e dice quali sono misurati (lavoro 16).
- **Misure:** i risultati di `valutazione.py modelli` si legano al profilo (servizio + modello). Cambiando modello, il sistema sa se quello nuovo è misurato su queste fonti e lo dichiara.
- **Filtro facoltativo:** se `modelli_ammessi` è compilato e il profilo scelto non vi rientra, `usa` avvisa e chiede conferma invece di lasciar fallire la ricerca dopo.
- **Modello della chat:** è separato da quello che legge i passaggi e si cambia nel client (Jan, Claude Desktop, LM Studio). La documentazione lo spiega in una riga, perché l'utente non confonda le due scelte.

Compatibilità: le impostazioni attuali di `config.ini` (`backend`, sezioni `[router]`, `[openai]`, `[anthropic]`, `[ollama]`) si convertono in profili al primo avvio, con copia di sicurezza; il motore continua a leggerle finché la conversione non è fatta.

Completo quando:
- test automatici con servizi finti: creazione di un profilo, cambio riuscito, cambio rifiutato per collegamento fallito (resta il precedente), ricerca avviata con un profilo e ripresa dopo un cambio (usa ancora il primo), `--rileggi-modello`, risposta con letture di due modelli («Limiti» corretti);
- su un PC senza configurazione, ciascuna delle tre scelte semplici porta a `installa.py controlla` superato;
- prova reale: cambio da un servizio gratuito a Ollama (o viceversa) a metà progetto, con una ricerca prima e una dopo, annotata in `stato_del_sistema.md`.



### 27. Configurazione automatica della chat

`python scripts/installa.py client <jan|claude|lmstudio> --scrivi`:
- trova il file di configurazione del client sul sistema in uso (Windows, macOS, Linux);
- ne salva una copia accanto (`<file>.airchivist-<data>.bak`);
- aggiunge o aggiorna solo la voce del server AIrchivist, senza toccare le altre;
- mostra le modifiche e chiede conferma prima di scrivere.

`python scripts/installa.py client --verifica`: avvia il server come lo avvierebbe il client e controlla l'handshake MCP e l'elenco degli strumenti.

Per Jan: verificare se le impostazioni che oggi si cambiano a mano (timeout degli strumenti, smart routing, ricerca web) sono in un file modificabile. Se non lo sono, la procedura le elenca come passaggi manuali.

**Stato (26/10/2026): fatto, salvo la prova manuale nei client.** `--scrivi` e `--verifica` implementati in `installa.py`. Le impostazioni di Jan sono in file modificabili (verifica sul file reale del 26/10, che corregge un'annotazione precedente): timeout degli strumenti e smart routing in `mcp_config.json`, sezione `mcpSettings`; ricerca web in `settings.json`, voce `setting-web-search`. `--scrivi` le sistema insieme alla voce del server, a Jan chiuso. Test automatici in `tests/test_installa.py`. Difetto corretto il 26/10: `--scrivi` senza `--si` con tastiera assente (EOFError, pipe o avvio automatico) andava in errore; ora la conferma senza risposta vale «no», il comando annulla con esito 0 e lascia il file intatto (test nuovo: `test_non_interattiva_eof_non_scrive`). Da fare sul PC reale: la prova manuale in Jan e Claude Desktop qui sotto; dettagli ed esiti in `stato_del_sistema.md` (sezione «Configurazione dei client MCP»).

Completo quando: su una configurazione vuota e su una con altri server già presenti, il file risultante è valido e il client avvia il server (prova manuale in Jan e Claude Desktop, annotata in `stato_del_sistema.md`).



### 28. Avvio guidato

`python scripts/installa.py inizia`: un solo comando per chi installa per la prima volta.
1. Controllo dell'ambiente (`controlla`), con istruzioni per ciò che manca: Python, PyMuPDF, Tesseract e lingue, per ogni sistema operativo.
2. Scelta del modello (lavoro 26).
3. Creazione del primo progetto: chiede nome e cartella, esegue `progetto.py nuovo` e lo imposta come progetto in uso, senza modificare `config.ini` a mano.
4. Configurazione della chat (lavoro 27).
5. Riepilogo finale: che cosa è installato, dove sta il progetto, prossimo passo (importare le fonti, lavoro 29).

Si interrompe e riprende senza rifare i passi già completati. Ogni passo si può saltare.

**Stato (26/10/2026):** fatto su Windows (copia pulita del repository fino al riepilogo, vedi `stato_del_sistema.md`, «Avvio guidato»); da provare su un altro sistema.

Completo quando: una copia pulita del repository, su Windows e su almeno un altro sistema, arriva al riepilogo finale senza modifiche manuali ai file.



### 29. Importazione guidata con tabella di revisione

Il lavoro più importante per l'uso reale: trasforma serie e metadati da concetti tecnici in una tabella da controllare.

`python scripts/importa.py proponi <cartella di PDF>`:
- legge tutti i file della cartella senza importarli;
- propone le serie: raggruppa i file per sottocartella, per schema del nome, per titolo ricorrente della prima pagina, per metadati del PDF;
- per ogni file propone i metadati con il loro stato (`dedotto`): tipo (fascicolo, volume, articolo), serie, data (dal nome, dai metadati del PDF, dal frontespizio, dalla sequenza dei numeri), numero, titolo, autore, lingua, pagine (etichette del PDF o numeri stampati), testo nativo o scansione, qualità prevista dell'OCR;
- scrive in `audit/review_<data>.csv` (punto e virgola, apribile in Excel e LibreOffice) una riga per file, con una colonna «da controllare» che spiega i dubbi. Accetta anche la tabella salvata in `.xlsx`, come già fa `valutazione.py`.

`python scripts/importa.py applica audit/review_<data>.csv`:
- crea o aggiorna i profili di serie con i valori confermati;
- importa i file con i metadati della tabella;
- registra tutto in `audit/imports.csv` e `audit/changes.csv`.

`python scripts/importa.py rivedi [--serie ...]`: la stessa tabella per documenti già importati. Esporta le intestazioni, il ricercatore le corregge, `applica` le riscrive registrando ogni modifica. È la revisione in foglio di calcolo prevista in `progettazione_del_sistema.md` (sezione 3).

Dalla chat, lo strumento MCP `importa` guida la stessa procedura e indica il file da aprire.

Completo quando: su un corpus di prova misto (articoli nativi digitali con etichette di pagina, scansioni di un periodico con la data nel nome, un volume) la tabella proposta ha i campi giusti per la maggior parte dei file e i dubbi segnalati per gli altri; l'applicazione produce intestazioni che passano `importa.py controlla`. Test automatici su PDF generati, come quelli attuali.

**Stato (26/10/2026): fatto** (`revisione.py`; dettagli e prova reale in `stato_del_sistema.md`, «Importazione guidata»). Non fatto: data dalla sequenza dei numeri.



### 30. Serie con meno campi

- Profilo minimo: nome, tipo (periodico, volume, articolo, archivio), lingua. Tutti gli altri campi hanno valori predefiniti o si deducono dai documenti.
- Il modello della citazione Chicago si genera dal tipo, senza scriverlo a mano. Il campo `chicago` resta per chi vuole personalizzarlo.
- `series_template.ini` divide i campi in «essenziali» e «avanzati».

Completo quando: un profilo con tre campi produce citazioni Chicago corrette per ciascun tipo (test sulle citazioni esistenti).

**Stato (26/10/2026): fatto** (`tests/test_citazioni_tipo.py`; confronto delle citazioni del corpus in `stato_del_sistema.md`, «Serie con meno campi»).



### 31. La risposta come documento

- Ogni risposta, oltre a `risposta.md`, si scrive anche in HTML autonomo (un solo file, apribile con il browser, stampabile): sezioni, passaggi originali, «Traduzione:», citazioni Chicago, copertura e limiti.
- Lo strumento MCP che consegna la risposta restituisce un riassunto breve e il percorso del file, e indica al modello della chat di non riscrivere la risposta.
- `python scripts/ricerca.py ... --apri` apre il file a fine ricerca.

Completo quando: la risposta di una ricerca già fatta (per esempio Franz Strobl) produce un HTML con lo stesso contenuto di `risposta.md` (test di confronto) e il server MCP restituisce percorso e riassunto entro `[mcp] max_caratteri`.

**Stato (26/10/2026): fatto** (`documento.py`, `tests/test_documento.py`; prova sulle 12 risposte salvate del progetto e su Franz Strobl in `stato_del_sistema.md`, «La risposta come documento»).



### 32. Documentazione per utenti esterni

- `docs/quickstart.md` (inglese) e `docs/quickstart.it.md`: dall'installazione alla prima risposta in 15 minuti, con il corpus d'esempio.
- Traduzione inglese completa di `docs/user_guide.it.md`.
- Istruzioni per Windows, macOS e Linux. Nessun percorso del PC dell'autore negli esempi.
- Pagina «Problemi frequenti» costruita sui casi reali delle prove (lavoro 34).

Completo quando: un lettore che segue solo il quickstart arriva alla prima risposta (verificato nel lavoro 34).

**Stato (27/10/2026): fatto, salvo la verifica con utenti esterni (lavoro 34) e la prova su macOS e Linux.** Quickstart in
inglese e in italiano, guida completa in inglese (`docs/user_guide.md`), pagina dei problemi frequenti in due lingue
(`docs/troubleshooting.md`, `troubleshooting.it.md`), guida italiana senza percorsi del PC dell'autore e con le istruzioni
per i tre sistemi. Il corpus d'esempio non c'è ancora (lavoro 33): il quickstart usa i documenti del lettore. Prova e
correzioni in `stato_del_sistema.md`, «Documentazione per utenti esterni».



### 33. Corpus d'esempio e confezione

- **Corpus d'esempio** libero da diritti: pochi documenti di pubblico dominio o con licenza aperta, misti (un periodico in scansione, un volume, un articolo nativo digitale), con un progetto già configurato e una domanda di prova. Verificare e dichiarare la licenza di ogni documento, con la fonte.
- **Installatore** per Windows con strumenti gratuiti: mette il motore in una cartella dell'utente, verifica o installa Python e Tesseract nel sistema, crea un collegamento a `installa.py inizia`. Il codice resta accessibile e aggiornabile.
- **MCP Bundle (`.mcpb`) per Claude Desktop**: prima verificare nella specifica del manifest (https://github.com/modelcontextprotocol/mcpb, `MANIFEST.md`) se un server Python, o un eseguibile, è supportato senza Python installato. Se sì, bundle con le impostazioni per cartella del progetto e chiave del servizio; se no, annotarlo e fermarsi.
- **Eseguibile unico** che contiene motore e interfaccia (lavori 35-38) e apre il browser: rimandato. Si riconsidera dopo i lavori 17 e 34.

Completo quando: l'installatore funziona su un Windows pulito (macchina virtuale o account nuovo) e il corpus d'esempio dà la risposta di prova.



### 34. Prova con utenti esterni

- 2-3 ricercatori (anche tra quelli della verifica del bisogno, lavoro 17) installano il sistema da soli seguendo solo il quickstart, ciascuno con il proprio corpus di PDF.
- Si registrano: tempo per ogni passo, dove si sono bloccati, domande fatte, utilità percepita della prima risposta.
- Le correzioni si fanno sulla documentazione e sugli strumenti, non spiegando a voce.
- Esito in `stato_del_sistema.md` e in `results/trials/utenti/` del progetto.

Completo quando: almeno un utente esterno arriva alla prima risposta in meno di un'ora di lavoro attivo senza aiuto.



### 35. Interfaccia: struttura e menu

`python scripts/app.py` avvia il server locale e apre il browser. Intestazione con i menu «Progetto» e «Modello» (comportamento descritto in «Punto di arrivo»), pulsanti Importa, Storico (risposte e ricerche precedenti), Nuova. Colonna destra con il percorso guidato della ricerca. Server solo su `127.0.0.1`, con token di sessione.

Completo quando: dall'interfaccia si cambia progetto e modello (anche con un collegamento che fallisce: resta il precedente) e si completa una ricerca su un'entità già in archivio, con lo stesso risultato della riga di comando (test automatici sulle risposte del server; prova manuale annotata).



### 36. Interfaccia: visore della fonte e citazioni cliccabili

Scheda «Fonte» con la pagina dell'originale (PyMuPDF; ripiego sul testo di `data/` senza originale o senza PyMuPDF), navigazione per pagina stampata, passaggio evidenziato; schede «Passaggi» e «Glossario». Ogni citazione «p. N» della risposta apre la pagina.

Completo quando: per una risposta con citazioni a pagina (per esempio la prova sui PDF del 25/10) ogni citazione apre la pagina giusta con il passaggio evidenziato.



### 37. Interfaccia: importazione e revisione

Scheda «Importazioni»: scelta di file o cartelle, proposta di serie e metadati (lavoro 29) in una tabella modificabile nell'interfaccia, applicazione, avanzamento dell'OCR, avvisi.

Completo quando: il corpus di prova misto del lavoro 29 si importa interamente dall'interfaccia.



### 38. Interfaccia: conversazione sulle fonti

Conversazione libera con il modello scelto, che usa gli strumenti del motore (gli stessi del server MCP) e mostra le citazioni come collegamenti. Regole e avvertenze come nel server MCP; se il modello scelto non sa usare gli strumenti, la conversazione si disattiva con una spiegazione e resta il percorso guidato.

Completo quando: con almeno due modelli diversi la conversazione risponde citando solo passaggi esistenti (verifica automatica delle citazioni restituite).

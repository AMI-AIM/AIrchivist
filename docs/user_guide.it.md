# Ricerca nelle fonti: istruzioni

Il sistema si usa dalla chat di **Jan**. Jan è collegato alla pipeline dal server MCP `mcp_server.py`. Il
modello della chat non legge le fonti: usa gli strumenti della pipeline e riporta ciò che restituiscono.

Il lavoro è diviso così:
- **Python, sul tuo PC**: la ricerca delle occorrenze, la verifica delle citazioni e l'impaginazione della
  risposta.
- **Il modello che scegli** (un servizio gratuito con una chiave, Ollama sul tuo PC, l'API di Anthropic o
  FreeLLMAPI): solo la lettura dei passaggi (smistamento, traduzione, sintesi). Lo si cambia quando si vuole
  (vedi «Modelli che leggono i passaggi»).

## Organizzazione delle cartelle

```
AIrchivist\                 il repository (il motore: si può pubblicare)
  README.it.md, README.md   guida rapida (in italiano e in inglese)
  LICENSE, requirements.txt licenza (AGPL-3.0) e librerie facoltative
  docs\                     documentazione di progetto (stato, progettazione, piano di lavoro, schede, questa guida)
  skills\
    source-search\          skill source-search, fonte unica (SKILL.md, config.ini)
    readme\                 README delle confezioni
    package.py              confezioni della skill, in skills\build\ (fuori dal controllo di versione):
                            source-search-claude.zip (claude.ai), claude-code\ (marketplace con il plugin),
                            source-search-chatgpt.zip
  tests\                    test automatici (python -m unittest discover -s tests); test_project\: progetto di prova
  letteratura\              letteratura secondaria sul metodo (PDF, fuori dal controllo di versione)
  scripts\
    installa.py             installazione delle librerie, controllo dell'ambiente, profili dei modelli,
                            configurazione dei client
    mcp_server.py           il server che collega Jan alla pipeline; istruzioni.py: le regole che consegna
    ricerca.py              il motore: estrazione -> lettura -> risposta (lo avvia il server)
    estrai_occorrenze.py, classifica.py, sintesi.py, evoluzione.py, cronologia.py, date_interne.py,
    glossario.py, archivio.py, schede.py, varianti.py, llm.py   le parti del motore
    indice.py, esplora.py   indice delle fonti, esplorazione dei nomi nuovi e ricerca libera nel testo
    varianti_nomi.py        trascrizioni cinesi e forme tradotte proposte da esplora_nome
    lavori.py               fa girare le ricerche come processi indipendenti dalla chat
    progetto.py, profili.py progetti di ricerca (nuovo, stato, percorsi) e profili delle serie
    importa.py              importazione di nuovo materiale (PDF, scansioni, .txt, PAGE/ALTO XML)
    pagine_xml.py, numerazione.py, colonne.py, motori_ocr.py, ocr_paddle.py, confronto_testi.py
                            parti dell'importazione: XML, numeri di pagina, ordine delle colonne nei giornali,
                            motori OCR, confronto dei testi
    citazioni.py            citazioni Chicago autore-data dalle intestazioni e dai profili di serie
    sessione.py             lettura dei passaggi in sessione (skill source-search)
    chat.py                 comandi della skill source-search (chat.py ambiente: dove si trova)
    valuta.py               prova rapida dei modelli su una lettura di riferimento
    valutazione.py          insieme di riferimento verificato a mano; misure di precisione e richiamo
    prova_ocr.py, prova_chat.py   prove dei motori OCR e dei modelli della chat
    config.ini              configurazione del motore (profilo di modello in uso, parametri, progetto in uso)
    models.ini              i tuoi profili di modello (fuori dal controllo di versione; lo crea installa.py modello)
    models_template.ini     esempi di profili di modello, con la descrizione delle voci
    series_template.ini     modello di series.ini per i progetti nuovi
  projects\                 i progetti di ricerca (fuori dal controllo di versione)
    dissident_communism\    il progetto di questa cartella
      project.ini           nome e impostazioni del progetto
      glossary\
        entities.ini        schede delle entità
        series.ini          profili delle serie (anche citazioni)
        instructions.md     regole del progetto per il modello della chat
      sources\              documenti originali caricati, che non si modificano
      data\                 le fonti processate (Renmin Ribao, Peking Review, Hongqi, raccolte, Selected Works)
      audit\
        changes.csv         ogni correzione fatta ai metadati delle fonti (le intestazioni dei file la citano con
                            il nome di prima, audit_fonti\registro_modifiche.csv: vedi audit\README.md)
        open_issues.csv     lacune ancora aperte (giorni e numeri mancanti): usato nelle sezioni 5 e 6 delle
                            risposte e dallo strumento copertura_fonti
        imports.csv         registro delle importazioni
        checks\             controlli delle intestazioni
      results\
        archive\            archivio unico dei passaggi già letti
        searches\           una cartella per ogni ricerca (modelli.json: i profili di modello con cui è partita)
        answers\            tutte le risposte complete (una per domanda)
        references\         letture di riferimento per valuta.py (nuova_unita, grippa)
        past_sessions\      lavori delle sessioni con Claude (letture assistite, tabelle, rapporti)
        trials\             prove dei modelli, dell'OCR, della chat e della skill (non entrano nell'archivio)
        evaluation\         insiemi di riferimento verificati a mano e misure (valutazione.py)
      system\
        index\              indice di ricerca delle fonti (si aggiorna da solo quando aggiungi file)
        jobs\               una cartella per ogni ricerca avviata dalla chat: stato e registro dei messaggi
        import_jobs\, cache\   importazioni avviate dalla chat e pagine già lette dall'OCR
        backups\            copie dei file fuori dal controllo di versione (fonti, archivio, schede),
                            una cartella per data e argomento
        model_changes.csv   registro dei cambi di modello (installa.py modello usa)
```

## Requisiti (una volta sola)

1. **Python per Windows** (3.10 o successivo), da https://www.python.org/downloads/. Durante l'installazione spunta **"Add python.exe to PATH"**. Il motore usa solo la libreria standard.
2. **Un modello per leggere i passaggi**: vedi «Modelli che leggono i passaggi».
3. **Jan**: vedi sotto.
4. Solo per importare nuovo materiale (vedi «Importare nuove fonti»): **Tesseract** e **PyMuPDF**.

Dalla cartella `scripts`:

```
python installa.py inizia
```

`inizia` è l'avvio guidato per chi installa per la prima volta: controlla l'ambiente, crea il profilo del modello,
crea il primo progetto e lo sceglie, collega la chat e chiude con un riepilogo che rifà i controlli necessari. Ogni
passo si può saltare (`--saltati 4`) o fare da solo (`--passi 3`); rilanciato, non rifà i passi già completati. Le
stesse cose, una per volta:

```
python installa.py librerie
python installa.py modello
python installa.py controlla
python installa.py client jan --scrivi
```

- `librerie` installa nel Python di sistema le librerie facoltative di `requirements.txt` (PyMuPDF).
- `modello` crea il primo profilo di modello con una procedura guidata (vedi sotto).
- `controlla` verifica Python, SQLite con FTS5, i profili di modello in uso (chiave presente, servizio
  raggiungibile), il progetto in uso, PyMuPDF, Tesseract con le lingue delle serie e PaddleOCR. Esce con 1 se
  manca un requisito necessario; `--rapido` salta PaddleOCR.
- `client` configura la chat: senza opzioni stampa cosa scrivere nel client (`jan`, `claude`, `lmstudio`, `json`);
  con `--scrivi` aggiunge o aggiorna solo la voce di AIrchivist nel file del client (copia di sicurezza prima,
  conferma a schermo); `client --verifica` avvia il server come lo avvierebbe il client e controlla l'handshake MCP
  e l'elenco degli strumenti. Per Jan, `--scrivi` va usato **a Jan chiuso** (alla chiusura Jan riscrive i suoi
  file): aggiorna la voce del server (anche se si chiama «Pipeline») e la accende, porta il timeout degli strumenti
  ad almeno 90 secondi, spegne lo smart routing, alza a 8000 caratteri i risultati degli strumenti e spegne la
  ricerca web (file `mcp_config.json` e `settings.json` nella cartella dei dati di Jan).

### Modelli che leggono i passaggi (profili)

I modelli sono due, e diversi:
- il **modello che legge i passaggi** (smistamento, traduzione, sintesi), scelto qui;
- il **modello della chat**, che usa gli strumenti e presenta la risposta: si sceglie nel client (Jan, Claude
  Desktop, LM Studio).

Ogni modello configurato è un **profilo** con un nome, in `scripts\models.ini`: servizio, nome del modello,
indirizzo, nome della variabile d'ambiente che contiene la chiave e parametri propri (pausa tra le richieste,
lunghezza massima delle risposte, modalità JSON...). La chiave non si scrive mai nel file. Esempi commentati e
descrizione di tutte le voci in `scripts\models_template.ini`.

Nella cartella `scripts`:
```
python installa.py modello                       procedura guidata per un profilo nuovo (come «modello nuovo»)
python installa.py modello elenca                profili, quelli in uso, chiavi presenti
python installa.py modello prova groq-qwen       prova di collegamento con una richiesta minima
python installa.py modello usa groq-qwen         sceglie il profilo per tutti i ruoli
python installa.py modello usa ollama-qwen-9b --ruolo sintesi    solo per un ruolo
python installa.py modello usa groq-qwen --progetto              solo per il progetto in uso (project.ini)
python installa.py modello togli gemini-flash    toglie un profilo non in uso (con copia del file)
```

**Procedura guidata.** Chiede il servizio:
1. Ollama, sul tuo PC: gratuito, nessuna chiave, serve un PC abbastanza potente. Propone i modelli già
   installati (`ollama pull <nome>` per scaricarne uno).
2. Un servizio con una sola chiave: Groq, Google Gemini, OpenRouter o un altro compatibile OpenAI. Indica dove si
   crea la chiave.
3. API di Anthropic (Claude), a consumo.
4. FreeLLMAPI (avanzato): più servizi gratuiti in catena, vedi sotto.

Poi il nome del modello e quello del profilo (ne propone uno). Se serve una chiave e la variabile non c'è, la
chiede (non si vede mentre la scrivi) e, se confermi, la salva come variabile d'ambiente del tuo utente (su
Windows con `setx`; su macOS e Linux indica la riga da aggiungere al profilo della shell). Infine prova il
collegamento e chiede se usare subito il profilo.

**Scelta del profilo.** `usa` prova prima il collegamento e cambia la scelta **solo se la prova riesce**;
altrimenti resta il profilo di prima e il messaggio spiega il problema (chiave rifiutata, modello inesistente,
servizio spento, quota esaurita). La scelta sta in `config.ini`, sezione `[modello]`:
```
[modello]
profilo = groq-qwen          per tutti i ruoli
sintesi = ollama-qwen-9b     facoltativo: un profilo diverso per smistamento, analisi o sintesi
```
La stessa sezione in `project.ini` prevale, solo per quel progetto. Ogni cambio si annota in
`system\model_changes.csv` del progetto (data, ruolo, profilo precedente e nuovo).

**Cambiare modello a metà progetto.** Le letture già fatte restano nell'archivio con il nome del modello che le
ha fatte e non si rileggono per il solo cambio. Una ricerca usa i profili scelti al suo avvio (vedi «Ricerche
lunghe e quote esaurite»). Se un modello si rivela inaffidabile, i suoi passaggi si possono far rileggere (vedi
«Rileggere i passaggi di un modello»). La sezione 5 di ogni risposta dice quali modelli hanno letto i passaggi e
se sono misurati su queste fonti.

**Configurazione precedente.** Se in `[modello]` non c'è nessun profilo scelto, vale ancora la configurazione di
prima: voce `backend` e sezioni `[anthropic]`, `[openai]`, `[router]`, `[ollama]` di `config.ini`.
`python installa.py modello converti` la trasforma in profili: mostra che cosa farà, chiede conferma, salva una
copia di `config.ini` e di `models.ini` (`<file>.airchivist-<data>.bak`) e sceglie il profilo che corrisponde al
`backend` di prima.

### FreeLLMAPI (i modelli gratuiti in catena)

FreeLLMAPI gira sul tuo PC. Quando la quota di un servizio gratuito si esaurisce, passa da solo al servizio successivo.

1. Installa l'app per Windows (`.exe`) da https://github.com/tashfeenahmed/freellmapi/releases/latest e avviala.
2. Nel pannello aggiungi le chiavi dei servizi:
   - Google AI Studio
   - Groq
   - NVIDIA
   - OpenRouter
   - Cloudflare
   - Z.ai

   **Usa solo chiavi API ufficiali.** Le chiavi restano dentro FreeLLMAPI: non scriverle nei file della cartella.
3. Nella pagina **Fallback Chain** servono due catene:
   - `ricerca`: i modelli verificati con `valuta.py`, usati dalla pipeline per leggere i passaggi;
   - `chat`: solo modelli capaci di usare strumenti, usati da Jan.
4. Strategia di instradamento: **Personalizzato**, con affidabilità 0%, velocità 40% e intelligenza 60%.
5. Copia la chiave unica (`freellmapi-…`, pagina **Chiavi**) e salvala nel Prompt dei comandi con `setx FREELLMAPI_KEY "..."`. Poi chiudi e riapri il Prompt.
6. Crea il profilo con `python installa.py modello` (scelta 4). L'indirizzo proposto è `http://127.0.0.1:31415/v1`; se cambia, lo trovi in **Chiavi > Chiave API unificata > URL di base**. Il modello `auto:ricerca` è la catena `ricerca`.

`modelli_ammessi` (voce del profilo FreeLLMAPI in `models.ini`) è una rete di sicurezza: se la compili e risponde un modello che non è nell'elenco, la lettura si ferma senza salvare nulla. Anche la prova di collegamento di `installa.py modello usa` fallisce, così te ne accorgi prima di avviare una ricerca.

Ogni passaggio registra il modello che ha davvero risposto, nelle colonne `modello_smistamento` e `modello_analisi` di `classificati.csv`.

Le quote giornaliere di Gemini si rinnovano alle 9 del mattino, ora italiana.

### Jan (la chat)

1. Installa Jan da https://jan.ai (gratuito, open source).
2. **Provider**: Settings → Model Providers → **Add Provider**.
   - Nome: `FreeLLMAPI`
   - Base URL: `http://127.0.0.1:31415/v1`
   - API key: la chiave `freellmapi-…`

   Aggiungi i modelli `auto:chat` e `auto:ricerca`. Per ciascuno, con la matita, attiva **Tools**.
3. **Server MCP**: Settings → **MCP Servers** → **+ Add MCP Server**.
   - Nome: `Pipeline`
   - Tipo: STDIO
   - Command: `python`
   - Arguments: `C:\Users\ivan_\Desktop\AIrchivist\scripts\mcp_server.py`
   - Variabile d'ambiente: `PYTHONUTF8` = `1`

   Attiva il server (pallino verde). Se Jan non trova `python`, metti in Command il percorso completo che ottieni con `where python`.
4. Nelle impostazioni MCP:
   - timeout degli strumenti a **90 secondi**;
   - **smart routing** disattivato;
   - **Web Search** disattivato, così le risposte vengono solo dalle fonti.
5. **Assistente «Ricerca fonti»**, con il modello `auto:chat`. Le regole di lavoro (fonti, citazioni, traduzioni)
   le consegna il server (vedi «Istruzioni per l'IA della chat»): nelle istruzioni dell'assistente basta scrivere
   «All'inizio di ogni conversazione chiama lo strumento guida e segui le sue istruzioni».

Dopo ogni aggiornamento dei programmi, spegni e riaccendi il server «Pipeline» in Jan.

## Progetti di ricerca

Il motore (la cartella `scripts`, con `config.ini`) è separato dai dati di una ricerca, che stanno in una
**cartella di progetto** dentro `projects`: `project.ini` (nome del progetto ed eventuali impostazioni proprie),
`glossary` (`entities.ini`, `series.ini`, `instructions.md`), `sources`, `data`, `audit`, `results` e `system`
(vedi «Organizzazione delle cartelle»). Il progetto attuale è `projects\dissident_communism`. I progetti sono dati
di ricerca: git ignora la cartella `projects`, così il repository del motore si può pubblicare senza.

```
python progetto.py stato
python progetto.py nuovo ..\projects\stampa_albanese --nome "Stampa albanese 1960-1978"
```

- `stato`: quale progetto è in uso e dove stanno i suoi file.
- `nuovo`: crea un progetto vuoto, con le cartelle, i due CSV di `audit`, `glossary\entities.ini`,
  `glossary\series.ini` (con la descrizione dei campi) e `project.ini`. Non tocca una cartella che contiene già
  qualcosa.

Senza un progetto scelto il motore non parte: lo dice e indica `progetto.py nuovo`.

**Quale progetto usare**: in `config.ini`, sezione `[progetto]`, voce `cartella`; oppure la variabile d'ambiente
`AIRCHIVIST_PROGETTO`, che prevale. In Jan si possono avere più server MCP, uno per progetto: stesso comando e
stessi argomenti, con la variabile d'ambiente `AIRCHIVIST_PROGETTO` che indica la cartella del progetto.

In `project.ini` si possono anche cambiare, solo per quel progetto, le impostazioni di `config.ini` (per esempio
`[estrazione] finestra = 300`) e spostare un file con la sezione `[percorsi]` (percorsi relativi alla cartella del
progetto).

## Uso

Nuova chat con l'assistente «Ricerca fonti», poi scrivi la domanda. Esempi:
- «Cosa dicono le fonti di Jacques Grippa nel 1964?»
- «Qual è stata l'evoluzione politica di Grippa fino al 1972?»
- «Come compare Nuova Unità nel Renmin Ribao tra il 1973 e il 1976?»
- «Apri il passaggio del Renmin Ribao del 2 aprile 1967.»
- «Quali varianti nuove ci sono per Grippa?»
- «Il passaggio X non è pertinente: correggilo.»

Strumenti a disposizione del modello della chat (14; quelli con più operazioni hanno il parametro `azione`):

| Strumento | Cosa fa |
|---|---|
| `guida` | istruzioni di lavoro e fonti del progetto (per i client che non le mostrano al modello) |
| `schede` | `elenca`: trova il nome esatto della scheda; `crea`: crea la scheda con le forme che hai confermato |
| `esplora_nome` | per un'entità senza scheda: le forme del nome attestate nelle fonti, con conteggi ed esempi |
| `cerca_testo` | ricerca libera di una parola o frase in tutte le fonti (senza valutazione di pertinenza) |
| `ricerca` | `avvia`, `attendi` (l'avanzamento e i profili di modello in uso; attese brevi, `[mcp] attesa_massima`), `ferma`: ricerca completa nelle fonti. Con `avvia`, su tua richiesta: `usa_modello_attuale`, `rileggi_modello` (vedi sotto) |
| `modello` | `elenca`: profili, quelli in uso, chiavi presenti, se il modello è misurato su queste fonti; `prova`: prova di collegamento; `usa`: sceglie un profilo (anche per alcuni ruoli o per il solo progetto), solo se la prova riesce |
| `risposte` | `elenca`, `leggi`: le risposte salvate nella cartella `results\answers` del progetto, per sezioni |
| `passaggi_archivio` | passaggi già letti (originale, traduzione, riferimento): risposta immediata |
| `copertura_fonti` | quanti numeri di ogni periodico (profili di serie) ci sono in un periodo e quali mancano |
| `apri_fonte` | il testo del file sorgente attorno a una riga |
| `varianti` | forme del nome proposte durante la lettura: elenca, aggiungi, scarta |
| `correggi_passaggio` | registra una tua correzione: vale per tutte le ricerche successive |
| `importa` | `avvia`, `stato`: importazione di nuove fonti (vedi «Importare nuove fonti») |
| `serie` | `elenca`, `crea`: profili delle serie del progetto |

I nomi usati fino al 25/10/2026 (`elenca_entita`, `avvia_ricerca`, `leggi_risposta`...) restano accettati, così un
assistente che li nomina continua a funzionare.

Dalla chat si può chiedere quale modello legge i passaggi («Quale modello legge i passaggi? È misurato?») e
cambiarlo («Usa il profilo ollama-qwen-9b per la sintesi»): lo strumento `modello` fa la stessa prova di
`installa.py modello usa`. Un profilo nuovo si crea solo da riga di comando, perché la chiave non passi dalla
chat. Il modello della chat stessa si cambia nel client.

### Istruzioni per l'IA della chat

Il server le compone ogni volta (`istruzioni.py`) da tre parti: le regole generali del motore (come usare gli
strumenti, come citare, cosa non fare), l'elenco delle fonti ricavato da `series.ini` con nome e descrizione da
`project.ini`, e le regole proprie del progetto scritte in `instructions.md` nella cartella del progetto
(argomento, carattere delle fonti, convenzioni su nomi e cariche, esempi di citazione; le righe con `#` non si
inviano). Le consegna in tre modi, perché non tutti i client le mostrano al modello: nel campo `instructions` del
protocollo MCP, come prompt MCP `istruzioni` e con lo strumento `guida`. Lingua delle risposte e attesa massima:
`config.ini` (o `project.ini`), sezione `[mcp]`.

Ogni ricerca completa salva la risposta nella cartella `results\answers` del progetto, con data e domanda nel nome del file. La
risposta ha otto sezioni:
1. Documenti
2. Passaggi originali
3. Dati espliciti
4. Inferenze
5. Limiti (anche: quali modelli hanno letto i passaggi, quanti ciascuno, e se sono misurati su queste fonti)
6. Copertura
7. Risposta finale
8. Dati tecnici per la verifica (file e righe, che non entrano nelle citazioni)

In chat compaiono per prime le sezioni 3, 4 e 7; le altre si chiedono a parte.

Le citazioni sono in stile Chicago, 17ª edizione, sistema autore-data: la voce della bibliografia, con la pagina
citata in coda quando il file la indica («*Renmin ribao* 人民日报. 1965. 28 giugno 1965, p. 4.»). La voce nasce
dall'intestazione del file e dal profilo della serie in `series.ini` (tipo, nome della testata, campo `chicago`). Sotto ogni passaggio
la riga «Lettura» dice chi ha deciso la pertinenza e chi ha tradotto: un modello (quale), una sessione
assistita, una regola. La sezione 6 riporta i conteggi.

### Ricerche lunghe e quote esaurite

Ogni ricerca gira in un processo a sé, con lo stato salvato in `system\jobs\` del progetto: continua anche se riavvii il
server «Pipeline» o chiudi la chat, e Jan la ritrova alla domanda successiva («a che punto è la ricerca?»).
Quando le quote gratuite si esauriscono, la ricerca non si ferma: aspetta e riprova da sola (dopo 10, 15, 30
minuti, poi ogni ora, per al massimo 36 ore) e riprende da dove era. Lo stesso vale per la sintesi, se il
modello non risponde: la risposta salvata intanto contiene le parti già pronte. Se alcuni passaggi falliscono
sempre (risposte del modello non valide), dopo due tentativi la risposta viene scritta lo stesso e la sezione 5
dice quanti passaggi mancano.

La ricerca si ferma solo per errori che non passano da soli (chiave mancante o sbagliata, modello ritirato):
Jan riporta il messaggio. Se il PC si spegne o va in sospensione, la ricerca si interrompe: rifacendo la
domanda riprende da dove era. Il registro completo di ogni ricerca è in `system\jobs\<data-ora>\registro.txt` del progetto.

**Profili di modello di una ricerca.** All'avvio la ricerca registra i profili in uso in `modelli.json`, nella sua
cartella dentro `results\searches`. Se si interrompe e riprende (da sola o rifacendo la domanda), continua con
quei profili anche se nel frattempo hai scelto un altro modello: così una ricerca non mescola modelli per un cambio
fatto a metà. Il cambio vale dalla ricerca successiva. Per far proseguire una ricerca interrotta con il modello
scelto adesso: in chat chiedilo esplicitamente (opzione `usa_modello_attuale`), da riga di comando
`python ricerca.py "Nome" --usa-modello-attuale`. Quando la ricerca finisce con la risposta completa, la successiva
usa i profili scelti in quel momento.

## Schede delle entità e glossario

Le ricerche funzionano solo su entità che hanno una scheda in `entities.ini`. Esempio:
```
[PCd'I (m-l)]
forma_estesa = Partito comunista d'Italia (marxista-leninista)
varianti = 意大利共产党（马克思列宁主义）; ...
collegate = ...
forme_ambigue = ...
note = ...
```
Campi:
- `varianti`: tutte le forme del nome che la ricerca deve trovare.
- `tipo`: persona, organizzazione, testata, stato, altro.
- `forma_estesa`: il nome per esteso, per gli enti indicati da una sigla.
- `collegate`: entità da analizzare insieme nelle domande sull'evoluzione nel tempo, per esempio il partito o l'organo di stampa.
- `forme_ambigue`: forme che possono indicare anche un'altra entità; per queste il passaggio viene sempre controllato dal modello.
  Devono stare anche in `varianti`: la ricerca cerca solo le varianti. `schede.py controlla` segnala quelle che mancano,
  e il server lo dice alla chat quando crea una scheda così.
- `note`: indicazioni per il modello che legge i passaggi.

Regole per unire o separare le schede, per dirigenti, organi di stampa e forme ambigue: `docs\schede_entita.md`.
Controllo automatico (doppioni, forme in comune, forme brevi non dichiarate, letture sotto nomi senza scheda):
```
python schede.py controlla
```

### Entità nuove

Se chiedi di una persona o di un'organizzazione che non ha una scheda, Jan usa `esplora_nome`:
- cerca nelle fonti inglesi le forme latine del nome, tollerando gli errori dell'OCR;
- traduce gli indizi in caratteri latini (paesi, nazionalità, partiti, in italiano, inglese, francese, spagnolo,
  tedesco e albanese) nelle forme cinesi: «Italian», «Italia» → 意大利, 意共 (`varianti_nomi.py`);
- genera da sé le trascrizioni cinesi del nome, sul modello Xinhua e con le varianti più comuni (Berlinguer →
  贝林格, 贝尔林格…; il nome proprio si combina con i cognomi trovati: 恩里科·贝林格), e le traduzioni dei nomi di
  partito (Communist Party of Italy (Marxist-Leninist) → 意大利共产党（马列） …); tiene solo quelle attestate e,
  tra queste, propone quelle che compaiono accanto agli indizi;
- verifica anche le trascrizioni cinesi che propone il modello della chat;
- confronta le testate: dove la Peking Review nomina la persona, cerca nel Renmin Ribao delle tre settimane
  precedenti i nomi trascritti accanto al paese o al partito, e li propone (allineamento dichiarato nei profili);
- per ogni forma riporta conteggi per serie e anno, esempi con riferimento, quante volte compare accanto agli
  indizi, e segnala le forme brevi o spesso senza contesto (possibili omonimi).

Le forme generate e quelle dell'allineamento sono attestate, ma possono indicare altre persone o parole (贝林格
compare anche in 贝林格韦, una regione dello Zimbabwe): vanno confermate una per una e, se brevi, finiscono tra le
forme ambigue, che il modello smista sempre.

Jan ti mostra le forme attestate e crea la scheda solo dopo la tua conferma: nessuna forma entra nella scheda
se non compare nelle fonti. Poi la ricerca procede come per le altre entità.

L'**indice delle fonti** (circa 900 MB in `system\index\` del progetto) serve a `esplora_nome`, a `cerca_testo` e
all'estrazione delle occorrenze: con l'indice ogni ricerca legge per intero solo i file che possono contenere
il nome (tutti i file OCR e, del Renmin Ribao, solo i numeri in cui la forma compare), con lo stesso risultato
della lettura completa. Quando aggiungi o correggi file in `data\`, l'indice si aggiorna da solo alla prima ricerca
(indicizza solo i file nuovi o cambiati: pochi secondi). A mano, dal Prompt dei comandi nella cartella
`scripts`: `python indice.py aggiorna`; `python indice.py stato` dice se è allineato alle fonti. Dopo molte
correzioni conviene ricostruirlo da capo per ripulirlo (`python indice.py costruisci`, 10-30 minuti).

`entities.ini` fa anche da glossario. Quando un passaggio contiene la forma cinese o inglese di un nome che ha una scheda, al modello viene indicato il nome italiano da usare.

## Importare nuove fonti

`importa.py` porta nel sistema materiale nuovo (per ora pensato per le fonti albanesi): PDF con testo, PDF
scansionati, foto o scansioni delle pagine (jpg, png, tif), file `.txt` ed esportazioni PAGE XML / ALTO XML. Per ogni documento prende il testo
del PDF quando c'è, altrimenti fa l'**OCR** con Tesseract (gratuito, gira sul tuo PC); scrive in `data\` un
file `.txt` con l'intestazione dei metadati, come le altre fonti; registra in `audit\imports.csv`
il metodo, le pagine, la qualità dell'OCR e gli avvisi; aggiorna l'indice. Nei PDF segna le pagine stampate (vedi
«Pagine dei PDF»), così le citazioni arrivano alla pagina.

L'originale (PDF, scansione, esportazione PAGE/ALTO, `.txt`) si copia intatto in `sources\`, nella
stessa sottocartella che il `.txt` ha in `data\`; un documento di più file (pagine XML, `--unisci`) diventa una
cartella con il nome del documento. `SOURCE_FILE` dell'intestazione indica quella copia (percorso relativo a
`sources\`) e `SOURCE_HASH` la sua impronta SHA-256 (per una cartella: l'impronta dell'elenco dei file con le loro
impronte). Gli originali in `sources\` non si modificano più: reimportando lo stesso file si riusa la copia; se un
file diverso ha lo stesso nome, il nuovo si conserva accanto con le prime 8 cifre dell'impronta nel nome. Con
`--prova` non si copia nulla.

**Preparazione (una volta sola)**, dal Prompt dei comandi:

```
winget install -e --id UB-Mannheim.TesseractOCR
python -m pip install pymupdf
cd C:\Users\ivan_\Desktop\AIrchivist\scripts
python importa.py prepara
```

Tesseract, PyMuPDF e i modelli delle lingue restano installati nel sistema, non nella cartella del progetto.
Durante l'installazione di Tesseract, in «Additional language data», spunta le lingue che servono (Albanian,
più Italian o French se importerai testi in quelle lingue). Per aggiungerne una dopo: riesegui l'installazione,
oppure copia `<lingua>.traineddata` da https://github.com/tesseract-ocr/tessdata_best nella cartella
`tessdata` di Tesseract (serve l'amministratore). Dopo `winget` chiudi e riapri il Prompt dei comandi.
`prepara` controlla che ci siano Tesseract, PyMuPDF e le lingue richieste dalle serie di `series.ini`
(albanese: `sqi`). Se Tesseract o i modelli sono in cartelle diverse da quelle predefinite, indicale in
`config.ini`, sezione `[ocr]` (`tesseract = ...`, `modelli = ...`).

**Serie.** Ogni testata, rivista, libro o fondo d'archivio ha una scheda nel `series.ini` del progetto. Bastano
tre campi:
```
[Zëri i Popullit]
tipo = periodico
lingua = sq
```
`tipo` è `periodico` (fascicoli, un file per numero), `articolo` (articoli di una rivista, un file per articolo
con autore e titolo), `volume` (libro o raccolta) o `archivio` (documenti d'archivio datati). Il resto ha valori
predefiniti: cartella dentro `data\` (`riviste\zeri_i_popullit`, `volumi\...`, `archivi\...`), sigla dei nomi dei
file (le iniziali: `ZP`), e la citazione Chicago 17 autore-data (voce di bibliografia, con la pagina citata in
coda), che si genera dal tipo:
- periodico e articolo: «Putnam, Lara. 2016. “The Transnational and the Text-Searchable.” *The American
  Historical Review* 121, no. 2 (aprile): 377–402, p. 380.»; senza autore la testata ne prende il posto:
  «*Zëri i Popullit*. 1967. 12 gennaio 1967, p. 3.»;
- volume: «Hoxha, Enver. 1969. *Vepra*. Vol. 2. Tirana: Naim Frashëri, p. 45.»;
- archivio: «Central Intelligence Agency. 1971. “Chinese Support for Foreign Communist Parties.” 3 marzo 1971.
  CIA-RDP85T00875R001100010023-9, CIA FOIA Electronic Reading Room, p. 12.» (campi facoltativi del profilo
  `archivio`, `fondo`, `segnatura`).

Nell'intestazione l'autore si scrive «Cognome, Nome» (più autori separati da `;`: nella voce il primo resta
«Cognome, Nome», gli altri diventano «Nome Cognome»). Anno sconosciuto: «s.d.». `nome_citazione` dà il nome della
testata come va scritto (es. `*Renmin ribao* 人民日报`). Il campo `chicago` serve solo per una forma diversa da
quella del tipo (es. le traduzioni JPRS di Red Flag). I campi avanzati sono descritti in testa a
`series.ini` (modello: `scripts\series_template.ini`). Le serie si aggiungono con l'importazione guidata (qui
sotto), scrivendo il blocco o chiedendo in Jan («crea la serie ...»). Il profilo dice anche
al resto del sistema come trattare la serie: se è un periodico (`tipo`), fin dove arrivano i numeri (`periodo`,
per i silenzi della cronologia), ogni quanto esce (`periodicita`), con quali altre serie cercarla (`gruppo`),
come trovare la pagina nel testo (`pagina_regex`). L'elenco dei campi è in testa a `series.ini`. Una serie senza
`periodo` non ha silenzi finali nella cronologia.

**Importazione guidata con la tabella di revisione** (il modo più semplice per una cartella di documenti nuovi:
non serve sapere prima che cosa sono serie e metadati). Dalla cartella `scripts`:

```
python importa.py proponi "C:\documenti da importare"
python importa.py applica "<progetto>\audit\review_<data>.csv" --prova
python importa.py applica "<progetto>\audit\review_<data>.csv"
```

1. `proponi` legge tutti i file **senza importarli** (niente OCR: testo e metadati dei PDF, etichette e numeri di
   pagina, nome del file, risoluzione delle scansioni, frontespizio di JSTOR) e scrive in `audit\` del progetto
   la tabella `review_<data>.csv`, una riga per documento. Propone le serie (una sottocartella i cui file si
   somigliano, come `ZP1967-01-12.pdf`, `ZP1967-01-13.pdf`, è un periodico; un libro o un articolo da solo fa
   serie a sé, o va nella sua rivista), e per ogni documento tipo (fascicolo, articolo, volume), data con il suo
   stato e la sua provenienza, numero, titolo, autore, anno, lingua, pagine stampate, testo nativo o scansione,
   qualità prevista dell'OCR. La colonna **da_controllare** spiega i dubbi.
2. Apri la tabella con Excel o LibreOffice (punto e virgola: si apre già divisa in colonne), correggi i valori,
   scrivi `no` nella colonna `importa` per saltare un documento, salva (anche come `.xlsx`). Per una serie nuova
   bastano nome, `tipo_serie` (periodico o volume) e lingua: cartella e sigla, se vuote, si ricavano dal nome.
3. `applica --prova` controlla la tabella e dice che cosa farebbe; senza `--prova` crea le serie che mancano in
   `series.ini`, importa i documenti (con l'OCR dove serve) con i valori della tabella e aggiorna l'indice. Un valore
   che hai cambiato vale «verificato»; uno lasciato com'era resta «dedotto» o «da verificare», con la provenienza
   (`DATE_NOTE`). Le importazioni vanno in `audit\imports.csv`, i valori che hai corretto rispetto alla proposta in
   `audit\changes.csv`.

Per i documenti **già importati**, la stessa tabella: `python importa.py rivedi --serie "Zëri i Popullit"
--solo-dubbi` scrive `audit\review_rivedi_<data>.csv` con le intestazioni (solo i documenti con valori dedotti, da
verificare o mancanti); correggi e `applica` riscrive solo i campi cambiati (codifica e fine riga restano quelli del
file), con una copia di prima in `system\backups\` e una riga per campo in `audit\changes.csv`. Un valore corretto
diventa verificato.

Dalla chat lo stesso percorso: strumento `importa`, azioni `proponi`, `applica` (prima con `prova`) e `rivedi`;
la chat dice quale file aprire e non compila la tabella al posto tuo.

**Importare un file in una serie che c'è già.** In Jan: «importa la cartella C:\...\scansioni nella serie Zëri i Popullit». La prima volta
per una serie o un tipo di scansione Jan fa una **prova** sulle prime pagine e mostra testo, qualità e data
letta. Oppure dal Prompt dei comandi:

```
python importa.py importa "C:\scansioni\ZP 1967" --serie "Zëri i Popullit" --prova 2
python importa.py importa "C:\scansioni\ZP 1967" --serie "Zëri i Popullit"
```

- **Data**: per i periodici si prende dal nome del file (`1967-01-12`, `12.01.1967`, `12 janar 1967`...);
  se manca, dalla testata della prima pagina (segnata «da controllare»); oppure `--data`, o un file
  `--metadati elenco.csv` con le colonne `file, data, numero, titolo, autore, anno, volume`.
- **Articoli** di un periodico: `--titolo` e `--autore` entrano nell'intestazione (`TITLE`, `AUTHOR`) e nella
  citazione («Larrabee, F. Stephen. 1978. “Whither Albania?” *The World Today* 34, no. 2 (febbraio).»).
- `--unisci`: le foto delle pagine di un solo numero diventano un solo documento.
- L'importazione si può interrompere: le pagine già lette restano in `system\cache\imports` e alla ripresa
  non si rileggono. I documenti già importati si saltano (`--sovrascrivi` per rifarli).
- **Qualità**: per ogni documento la confidenza media dell'OCR (0-100) e le pagine deboli (sotto 60) sono in
  `registro.csv` e nell'intestazione (`[OCR_CONFIDENCE]`). Sotto 70 conviene controllare a campione o
  rifare la scansione (300 dpi, in scala di grigi).

**Pagine dei PDF.** Ogni pagina riceve il marcatore `[[p. 61 | pdf 2]]` (pagina stampata | posizione nel PDF), che
le citazioni usano. La pagina stampata viene, nell'ordine:
1. da `--prima-pagina N` (con `--da-pagina K`, predefinito 1): la pagina K del PDF è la p. N e le seguenti
   proseguono; le pagine prima di K restano senza marcatore. Per molti file: colonne `prima_pagina` e `da_pagina`
   nel CSV di `--metadati`;
2. dalle etichette di pagina dichiarate dal PDF (i PDF di JSTOR hanno «p. 61», «p. 62»...), se non ripetono
   soltanto la posizione nel file;
3. dai numeri stampati in testa o in piede della pagina, se lo scarto dalla posizione nel PDF è costante (almeno 3
   pagine e la maggior parte di quelle con un numero). Le pagine senza numero leggibile ricevono la pagina per
   continuità, annotata «dedotta» nel marcatore; l'intestazione ha `[PAGES_STATUS: dedotto]` e in `PAGES_NOTE`
   quante pagine sono state lette. Conviene controllare a campione.

Se nessuna delle tre vale (numerazione irregolare, tavole, salti), nessun marcatore: la citazione si ferma al
documento. La prova (`--prova`) dice quale via è stata usata. `--senza-pagine` non segna le pagine.

**PDF scansionati con uno strato di testo.** Molti PDF d'archivio contengono già un vecchio OCR, spesso
scadente. Se le pagine sono scansioni (un'immagine copre la pagina) e hanno uno strato di testo, `importa.py`
rifà l'OCR su 3 pagine del corpo del volume (al 25%, 50% e 75%) e lo confronta con lo strato:
- se concordano entro il 2% dei caratteri, tiene lo strato (non serve rifare l'OCR);
- se discordano e l'OCR è sicuro (confidenza media almeno 85), scarta lo strato e rifà l'OCR di tutto il
  documento, riusando le pagine già lette;
- se discordano ma l'OCR è poco sicuro, tiene lo strato e lo segnala negli avvisi come da controllare.

La scelta compare in `TEXT_METHOD`, negli avvisi e nel registro. Un PDF con testo nativo (senza scansioni) si usa
com'è. Opzioni: `--campione N` (pagine del confronto; 0 = nessun confronto), `--ocr strato` (usa sempre lo
strato, come prima), `--ocr sempre` (rifà sempre l'OCR).

**Esportazioni PAGE XML e ALTO XML** (Transkribus, eScriptorium e altri strumenti): non serve l'OCR.
Indica la cartella dell'esportazione o il suo archivio `.zip`, che non va estratto:

```
python importa.py importa "C:\esportazioni\ZP1967-01-12" --serie "Zëri i Popullit" --prova 3
python importa.py importa "C:\esportazioni\ZP1967-01-12" --serie "Zëri i Popullit"
```

- Una cartella di pagine `.xml`, o un `.zip`, diventa **un documento**; le pagine seguono l'ordine naturale dei
  nomi (2 prima di 10). Il nome della cartella vale come nome del file importato (per i periodici: la data,
  come `ZP1967-01-12`).
- Si rispetta l'ordine di lettura delle regioni dichiarato nel file. Le righe vanno a capo come nell'originale;
  tra due regioni c'è una riga vuota.
- Dove il file dichiara il numero di pagina stampato (in PAGE la regione «page-number», in ALTO
  `PRINTED_IMG_NR`) si scrive il marcatore `[[p. 12 | img 3]]` (pagina stampata | immagine dell'esportazione),
  che le citazioni usano. Senza numero dichiarato non si scrive nessun marcatore.
- L'intestazione registra `TEXT_METHOD` (importazione PAGE/ALTO), `OCR_ENGINE` (lo strumento indicato nel file:
  Transkribus, Kraken...), `PAGES` (pagine stampate) e `OCR_CONFIDENCE`: la confidenza del motore d'origine, in
  scala 0-100, è indicativa e non confrontabile con quella di Tesseract.
- I file XML che non sono pagine (METS, metadati) si ignorano e compaiono tra gli avvisi.

**Controllo delle intestazioni**: `python importa.py controlla` (o una sottocartella: `controlla
riviste\zeri_i_popullit`) segnala errori (citazione mancante, data non valida, testo vuoto) e avvisi
(numeri di documento ripetuti, date da controllare, OCR debole, `DATE_STATUS` fuori dal vocabolario dei
campi, marcatori di pagina non riconosciuti o non in ordine) in `audit\checks\controllo_<data>.csv`.

**Migrazione degli stati (lavoro 8)**: i file storici con un `DATE_STATUS` che contiene una provenienza
(«dal nome del file», «letta nella prima pagina (OCR): da controllare»...) si portano sul vocabolario chiuso
con `python importa.py controlla --migra-stati`: lo stato diventa `dedotto`/`da verificare`, la provenienza
passa in `DATE_NOTE`. Solo le righe dell'intestazione vengono riscritte, mai il testo. Conviene eseguire il
comando con il corpus committato e pulito (`git status` senza modifiche), così il diff mostra cosa è cambiato;
per una verifica preliminare su una copia: `controlla <sottocartella> --migra-stati`.

**Nomi nelle fonti albanesi.** La stampa albanese scrive i nomi stranieri come si pronunciano e li declina
(Grippa: «Gripa», «Gripës», «Gripën»). Le forme già nelle schede non bastano: per ogni entità chiedi a Jan
`esplora_nome`, che con testi albanesi presenti cerca anche le trascrizioni albanesi probabili e le radici
delle forme declinate, e propone solo quelle attestate; entrano nella scheda dopo la tua conferma.

**Prima di usare i risultati albanesi**, conviene una prova rapida dei modelli sulla lettura dell'albanese
(una ventina di passaggi verificati da te), come per i modelli nuovi.

## Prova dei motori OCR

`prova_ocr.py` misura quale motore legge meglio una serie, sulle stesse pagine. Nella cartella `scripts`:

```
python prova_ocr.py motori --lingua zh
python prova_ocr.py prepara "C:\...\scansione.pdf" --nome cina_icm --lingua zh --pagine 50,200,320
python prova_ocr.py misura cina_icm
```

1. `motori`: quali motori sono disponibili e perché gli altri no. Oggi: Tesseract, anche con segmentazioni
   diverse (`tesseract:3`, `tesseract:6`). PaddleOCR è previsto ma non installato: su questo PC era troppo lento,
   circa 50 secondi per pagina. Kraken richiede Linux (WSL).
2. `prepara`: rende le pagine come immagini e le fa leggere a ogni motore; se il PDF ha già uno strato di testo,
   lo aggiunge al confronto (`strato_pdf`). Tutto va in `results\trials\ocr\<nome>\`, fuori dall'archivio.
   Per ogni pagina scrive `pNNN.riferimento.txt`, una proposta da correggere a mano guardando `pNNN.png`.
3. Correggi i riferimenti e scrivi il tuo nome dopo `# VERIFICATO_DA:`. Una pagina non verificata non entra nella
   misura. Per il cinese spazi e a capo non contano.
4. `misura`: CER (percentuale di caratteri sbagliati, inseriti o mancanti), anche senza la punteggiatura, e
   secondi per pagina di ogni motore, in `results\trials\ocr\misure_<data>.md`.

## Archivio unico delle letture

Ogni passaggio letto è conservato in `results\archive\readings.jsonl`, che sia stato letto dal modello o corretto da te. Una ricerca successiva non rimanda al modello lo stesso passaggio, né una sua copia identica in un altro file. Così le domande ripetute, di seguito o su altri periodi della stessa entità costano pochissimo.

Le correzioni registrate con `correggi_passaggio` prevalgono sulle letture del modello.

Le letture incomplete vengono completate alla prima ricerca che ritrova quei passaggi:
- i passaggi pertinenti mai tradotti né analizzati (per esempio quelli classificati solo in base alla forma del
  nome nelle sessioni precedenti) vanno all'analisi, senza ripetere lo smistamento;
- i passaggi «incerti» decisi solo per regola, senza lettura, tornano allo smistamento.

Se il modello di sintesi non risponde, la risposta salvata lo dice in testa e Jan lo riferisce: rifacendo la
stessa domanda si rifà solo ciò che manca.

`python archivio.py stato` mostra quante letture ci sono per entità e chi le ha fatte. Ogni lettura registra
la propria provenienza, separatamente per la decisione sulla pertinenza e per la traduzione:
- letto da un modello (quale);
- lettura assistita in sessione (in chat), non verificata a mano;
- deciso per regola (quale regola: forma inequivocabile del nome, classificazione o esclusione in blocco in una
  sessione, voce di sommario).

`python archivio.py provenienza` registra la provenienza nelle letture vecchie che non l'hanno (`--prova`: solo
conteggi). Per le esclusioni fatte in sessione vale una regola in più: se la stessa motivazione si ripete in almeno
5 passaggi della stessa entità, l'esclusione conta come fatta in blocco, cioè per regola.

Quando una scheda viene rinominata o unita a un'altra, le letture restano nell'archivio sotto il nome vecchio.
Per riportarle sotto la scheda:
```
python archivio.py equivalenza "nome vecchio" "nome della scheda" "nota"
python archivio.py riattribuisci "nome vecchio" "nome della scheda"
python archivio.py riattribuisci "nome vecchio" "nome della scheda" --applica
```
Il primo comando registra che i due nomi indicano la stessa entità (`results\archive\equivalences.json`). Il
secondo ricalcola i passaggi come li estrarrebbe la scheda e scrive il piano in `results\archive\` senza
toccare nulla. Ogni lettura vecchia risulta in uno di questi casi: già letta sotto la scheda, da riattribuire,
con decisione diversa, fuori dalla scheda (forma che la scheda non ha). Il terzo aggiunge all'archivio solo le
letture da riattribuire, dopo averne fatto una copia in `system\backups`.

**Date sospette nelle sintesi.** Fino al 25/10/2026 il prompt di analisi chiedeva di completare l'anno delle date
«dalla data della fonte». Un fatto già avvenuto in un mese successivo a quello della fonte finiva così nell'anno
della fonte invece che in quello precedente (Renmin ribao, 2 agosto 1979: Berlinguer a Mosca «in ottobre», letto
come ottobre 1979). Ora la regola confronta mese e data della fonte e, se non è certo, lascia la data senza anno.
Per trovare e far rileggere le letture già nell'archivio:
```
python archivio.py date_sospette
python archivio.py date_sospette --applica
```
Il primo comando scrive il piano in `results\archive\date_sospette_<data>.csv` senza toccare nulla: letture
pertinenti la cui sintesi ha una data dopo quella della fonte, nello stesso anno, che la frase originale non
scrive. Il secondo, dopo una copia in `system\backups`, segna da rileggere quelle lette da un modello: alla
prossima ricerca su quell'entità (anche dalla chat) il modello rifà solo traduzione e sintesi, e la decisione sulla
pertinenza resta. Le letture fatte in sessione compaiono nel piano come «da controllare a mano». Si può limitare a
una scheda: `python archivio.py date_sospette "Enrico Berlinguer"`. Il controllo non vede l'errore opposto (un
annuncio di un mese precedente alla fonte, che è dell'anno seguente).

### Rileggere i passaggi di un modello

Se un modello si rivela inaffidabile (per esempio dopo le misure di `valutazione.py`), scegli prima un altro
profilo (`installa.py modello usa`), poi rifai la ricerca chiedendo di rileggere i passaggi di quel modello:
```
python ricerca.py "Enrico Berlinguer" --rileggi-modello gpt-oss-20b
```
In chat: «Rifai la ricerca su Berlinguer rileggendo i passaggi letti da gpt-oss-20b» (opzione `rileggi_modello`).
Tornano al modello attuale i passaggi della ricerca la cui pertinenza o traduzione viene da un modello il cui nome
contiene quella parola (almeno tre caratteri; i nomi esatti sono nella sezione 5 delle risposte e nella riga
«Lettura» dei passaggi). Le correzioni fatte a mano non si rileggono mai. La lettura nuova sostituisce la vecchia
nell'archivio, che però resta nel file `readings.jsonl` come storia. Se il modello attuale corrisponde allo stesso
nome, la ricerca lo segnala: la rilettura userebbe lo stesso modello.

## Meno richieste al modello

Le impostazioni sono in `config.ini`, sezione `[estrazione]`:
- `lotto_smistamento = 6`: quanti passaggi vengono smistati (pertinente sì/no) con una sola richiesta.
- `forme_sicure = si`: se il passaggio contiene una forma del nome che non lascia dubbi, lo smistamento si salta. Contano come sicure:
  - forme cinesi con il punto centrale, come 雅克·格里巴;
  - sigle con parentesi;
  - nomi e cognomi per intero.

  Non contano i titoli brevi tra 《》 (《新团结》, per esempio, è anche la «Neue Einheit» del KPD/ML) né i nomi
  generici di partito senza qualificazione (比利时共产党, «Belgian Communist Party», 意大利共产党), che valgono anche per
  il partito ufficiale.
- Le voci di sommario o di elenco vengono riconosciute e registrate senza traduzione né analisi. Un esempio sono gli indici della Peking Review.

## Validazione di un nuovo modello

Nel Prompt dei comandi, nella cartella `scripts`:
```
python valuta.py "Nuova Unità"                                         (la configurazione attuale)
python valuta.py "Nuova Unità" --modelli "glm-4.7; nemotron-3-ultra"   (uno per uno, con tabella di confronto)
```
Lo script confronta lo smistamento dei modelli con la lettura di riferimento in `results\references\nuova_unita`. Quel riferimento è una lettura assistita da Claude, non verificata a mano. Le prove vanno in `results\trials\` e non toccano l'archivio. Obiettivo: richiamo ≥ 95%. Un modello entra nella catena `ricerca` solo dopo questa prova. Con `--modelli` (e in `valutazione.py modelli` e `misura`) i modelli si chiedono a FreeLLMAPI, attraverso il suo profilo: quello in uso, se è di FreeLLMAPI, altrimenti il primo di `models.ini`.

## Prova dei modelli della chat

I modelli della chat (catena `chat` di FreeLLMAPI, usata da Jan) non leggono i passaggi: usano gli strumenti. Per
sceglierli, `prova_chat.py` simula il client su una domanda vera (strumenti veri, quelli che scrivono simulati:
non modifica nulla) e calcola un punteggio su 8: guida chiamata per primo, procedura seguita, nessuna risposta
ricostruita con apri_fonte, conferma chiesta, forma cinese attesa, niente file o righe, niente «corpus», testo
senza caratteri estranei.

```
python prova_chat.py --modelli "auto:chat; gpt-oss-120b; nemotron-3-ultra"
python prova_chat.py --modelli "gpt-oss-120b" --domanda "..." --forma 格里巴 --istruzioni-complete
```

Risultati e conversazioni in `results\trials\chat\`. Il punteggio misura la procedura e la pulizia del testo, non
la bontà delle scelte: le risposte vanno lette (per esempio, un modello può proporre come forma del nome un'altra
persona trovata con l'allineamento).

## Misure su un insieme verificato a mano

`valutazione.py` costruisce un insieme di riferimento verificato da te e misura su quello sia l'estrazione sia le
letture (per modello e per livello di provenienza). Funziona su qualsiasi corpus. Nella cartella `scripts`:
```
python valutazione.py campione prova1 --n 100
python valutazione.py candidati prova1 --entita "Franz Strobl" --file 60
python valutazione.py importa prova1
python valutazione.py misura prova1 --modelli "gemma4; nemotron-3-ultra"
```
1. `campione`: estrae un campione stratificato (serie, lingua, decisione, provenienza) dei passaggi già letti e
   scrive `results\evaluation\prova1\campione.csv`. Compila la colonna GIUDIZIO (sì / no / incerto) e
   VERIFICATO_DA. La decisione attuale non compare nel file, così la verifica è alla cieca.
2. `candidati`: cerca in un campione di file le forme più larghe del nome (cognome da solo, una lettera o un
   carattere diversi, accenti) che l'estrazione non trova. In `candidati.csv` segna GIUDIZIO = sì per le vere
   menzioni sfuggite.
3. `importa`: controlla i due file compilati e salva l'insieme di riferimento. I file usano il punto e virgola
   come separatore, così Excel li apre già divisi in colonne. Si possono salvare come CSV oppure come cartella di
   lavoro Excel (`campione.xlsx`, `candidati.xlsx`): vale il file salvato per ultimo.
4. `misura`: calcola richiamo e precisione, con un intervallo di confidenza al 95%, e scrive `misure_<data>.md`.
   Le misure riguardano le letture dell'archivio (per livello di provenienza), i modelli indicati (in
   `results\trials\`, senza archivio) e l'estrazione. `--profili "groq-qwen; ollama-qwen-9b"` misura i tuoi
   profili di modello, di qualsiasi servizio (non solo FreeLLMAPI): ogni misura registra profilo, servizio e
   modello, così `installa.py modello elenca` e lo strumento `modello` dicono se un profilo è misurato su queste
   fonti («questo profilo», «stesso modello, altro servizio» o «no»).

Per confrontare rapidamente tutti i modelli attivi in FreeLLMAPI (pochi minuti):
```
python valutazione.py modelli riferimento_1 --solo-elenco
python valutazione.py modelli riferimento_1
```
Il primo comando mostra i modelli scelti e quelli scartati con il motivo, usando i dati del router senza fare
richieste: router e alias (gli «slot» Claude), quota esaurita, contesto sotto i 16.000 token, doppioni, modelli
che non servono a leggere testi. Il secondo fa leggere a ogni modello 30 passaggi verificati (metà non
pertinenti) e poi, ai 6 migliori, tutto l'insieme verificato. Le richieste contengono 10 passaggi di entità
diverse e i modelli lavorano 8 alla volta. Il risultato è in `prova_rapida_<data>.md`. Opzioni: `--prima-fase`,
`--migliori`, `--lotto`, `--paralleli`, `--escludi`. Nelle ricerche ogni lotto riguarda una sola entità: la prova
rapida serve a confrontare i modelli tra loro.

La misura completa, lenta, con lo stesso formato delle ricerche (FreeLLMAPI deve essere acceso):
```
python valutazione.py misura riferimento_1 --modelli tutti --solo-elenco
python valutazione.py misura riferimento_1 --modelli tutti
```
Il primo comando mostra solo l'elenco dei modelli che verrebbero provati. Sono esclusi i router (`auto`, `fusion`), i
filtri di sicurezza, i modelli per il codice, per immagini e audio e gli strumenti specializzati; altri si escludono
con `--escludi "parte del nome; ..."`. Ogni modello legge i passaggi verificati senza archivio e senza la regola
delle forme inequivocabili, così la misura riguarda solo il modello. I risultati si salvano man mano in
`modelli_<data>.jsonl`; la tabella finale va in `misure_<data>.md`. `--limite 6` fa una prova veloce.

## Problemi frequenti

- *«All models exhausted»* in Jan: le quote gratuite del momento sono finite per il modello della chat. Riprova più tardi; le quote di Gemini si rinnovano alle 9. Le ricerche già avviate aspettano e riprendono da sole.
- *«Tesseract non trovato»*: installalo (vedi «Importare nuove fonti») e riapri il Prompt dei comandi, oppure riavvia Jan; o indica il percorso in `config.ini`, sezione `[ocr]`.
- *OCR pieno di errori*: scansione a bassa risoluzione o storta; rifalla a 300 dpi. Per testi con molte parole in un'altra lingua, in `series.ini` metti ad es. `ocr_lingue = sqi+eng`.
- *Il server «Pipeline» non parte*: controlla che FreeLLMAPI sia acceso e che in Command ci sia il percorso giusto di Python.
- *Errore 401/403*: chiave sbagliata o scaduta (in FreeLLMAPI, o nella variabile d'ambiente del profilo). *Errore 404*: modello ritirato; disattivalo nel pannello di FreeLLMAPI o correggi il nome nel profilo. Controlla con `python installa.py modello prova <profilo>`.
- *«Il profilo di modello … non esiste»*: il nome scelto in `[modello]` di `config.ini` o `project.ini` non è in `models.ini`. `python installa.py modello elenca` mostra i profili; `usa` ne sceglie uno.
- *La ricerca usa ancora il modello di prima*: è una ricerca interrotta, che riprende con i profili con cui era partita (vedi «Ricerche lunghe e quote esaurite»); usa `--usa-modello-attuale`, o chiedilo in chat.
- *Jan risponde senza usare gli strumenti*: controlla che sia scelto l'assistente «Ricerca fonti», che il modello abbia **Tools** attivo e che Web Search sia spento.

# Ricerca nelle fonti: istruzioni

Il sistema si usa dalla chat di **Jan**. Jan è collegato alla pipeline dal server MCP `mcp_server.py`. Il
modello della chat non legge le fonti: usa gli strumenti della pipeline e riporta ciò che restituiscono.

Il lavoro è diviso così:
- **Python, sul tuo PC**: la ricerca delle occorrenze, la verifica delle citazioni e l'impaginazione della
  risposta.
- **Modelli gratuiti, tramite FreeLLMAPI**: solo la lettura dei passaggi (smistamento, traduzione, sintesi).

## Organizzazione delle cartelle

```
RAG\
  LEGGIMI.md
  data\                     le fonti (Renmin Ribao, Peking Review, Hongqi, raccolte, Selected Works)
  audit_fonti\
    registro_modifiche.csv  ogni correzione fatta ai metadati delle fonti (citato nelle intestazioni dei file)
    problemi_residui.csv    lacune ancora aperte (giorni e numeri mancanti): usato nelle sezioni 5 e 6 delle
                            risposte e dallo strumento copertura_fonti
  risposte\                 tutte le risposte complete (una per domanda)
  indice\                   indice di ricerca delle fonti (si aggiorna da solo quando aggiungi file)
  importazioni\             registro delle importazioni (registro.csv) e dei controlli delle intestazioni
  lavori\                   una cartella per ogni ricerca avviata dalla chat: stato e registro dei messaggi
  risultati\
    _archivio\              archivio unico dei passaggi già letti
    _riferimenti\           letture di riferimento per valuta.py (nuova_unita, grippa)
    _sessioni_precedenti\   lavori delle sessioni con Claude (letture assistite, tabelle, rapporti)
    _prove\                 prove dei modelli (non entrano nell'archivio)
    _valutazione\           insiemi di riferimento verificati a mano e misure (valutazione.py)
    <nome_entità>\          una cartella per ogni ricerca
  pipeline\
    mcp_server.py           il server che collega Jan alla pipeline
    ricerca.py              il motore: estrazione -> lettura -> risposta (lo avvia il server)
    estrai_occorrenze.py, classifica.py, sintesi.py, evoluzione.py, cronologia.py, glossario.py,
    archivio.py, schede.py, varianti.py, llm.py   le parti del motore
    indice.py, esplora.py   indice delle fonti, esplorazione dei nomi nuovi e ricerca libera nel testo
    lavori.py               fa girare le ricerche come processi indipendenti dalla chat
    importa.py, serie.ini   importazione di nuovo materiale (OCR) e profili delle serie (anche citazioni)
    citazioni.py            citazioni in stile Chicago dalle intestazioni e dai profili di serie
    valuta.py               prova rapida dei modelli su una lettura di riferimento
    valutazione.py          insieme di riferimento verificato a mano; misure di precisione e richiamo
    test\                   test automatici (python -m unittest discover -s pipeline/test)
    registra_analisi.py     usato dalla skill di Claude «ricerca-occorrenze-fonti»
    config.ini, entita.ini  configurazione e schede delle entità
    _backup\                copie precedenti di entita.ini
```

## Requisiti (una volta sola)

1. **Python per Windows**, da https://www.python.org/downloads/. Durante l'installazione spunta **"Add python.exe to PATH"**. Non servono librerie aggiuntive.
2. **FreeLLMAPI**: vedi sotto.
3. **Jan**: vedi sotto.
4. Solo per importare nuovo materiale (vedi «Importare nuove fonti»): **Tesseract** e **PyMuPDF**.

### FreeLLMAPI (i modelli gratuiti)

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
6. In `config.ini`, sezione `[router]`, l'indirizzo è `http://127.0.0.1:31415/v1`. Se cambia, lo trovi in **Chiavi > Chiave API unificata > URL di base**.

`modelli_ammessi` (sezione `[router]`) è una rete di sicurezza: se la compili e risponde un modello che non è nell'elenco, la lettura si ferma senza salvare nulla.

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
   - Arguments: `C:\Users\ivan_\Desktop\RAG\pipeline\mcp_server.py`
   - Variabile d'ambiente: `PYTHONUTF8` = `1`

   Attiva il server (pallino verde). Se Jan non trova `python`, metti in Command il percorso completo che ottieni con `where python`.
4. Nelle impostazioni MCP:
   - timeout degli strumenti a **90 secondi**;
   - **smart routing** disattivato;
   - **Web Search** disattivato, così le risposte vengono solo dalle fonti.
5. **Assistente «Ricerca fonti»**, con le regole di lavoro (fonti, citazioni, traduzioni). Usa sempre questo, con il modello `auto:chat`.

Dopo ogni aggiornamento dei programmi, spegni e riaccendi il server «Pipeline» in Jan.

## Uso

Nuova chat con l'assistente «Ricerca fonti», poi scrivi la domanda. Esempi:
- «Cosa dicono le fonti di Jacques Grippa nel 1964?»
- «Qual è stata l'evoluzione politica di Grippa fino al 1972?»
- «Come compare Nuova Unità nel Renmin Ribao tra il 1973 e il 1976?»
- «Apri il passaggio del Renmin Ribao del 2 aprile 1967.»
- «Quali varianti nuove ci sono per Grippa?»
- «Il passaggio X non è pertinente: correggilo.»

Strumenti a disposizione del modello della chat:

| Strumento | Cosa fa |
|---|---|
| `elenca_entita` | trova il nome esatto della scheda |
| `esplora_nome` | per un'entità senza scheda: le forme del nome attestate nelle fonti, con conteggi ed esempi |
| `crea_scheda` | crea la scheda di un'entità nuova con le forme che hai confermato |
| `cerca_testo` | ricerca libera di una parola o frase in tutte le fonti (senza valutazione di pertinenza) |
| `passaggi_archivio` | passaggi già letti (originale, traduzione, riferimento): risposta immediata |
| `avvia_ricerca`, `attendi_ricerca`, `ferma_ricerca` | ricerca completa nelle fonti, con l'avanzamento (attese fino a 75 secondi) |
| `leggi_risposta`, `elenca_risposte` | le risposte salvate in `RAG\risposte\`, per sezioni |
| `copertura_fonti` | quanti numeri di ogni periodico ci sono in un periodo e quali giorni mancano |
| `apri_fonte` | il testo del file sorgente attorno a una riga |
| `varianti` | forme del nome proposte durante la lettura: elenca, aggiungi, scarta |
| `correggi_passaggio` | registra una tua correzione: vale per tutte le ricerche successive |

Ogni ricerca completa salva la risposta in `RAG\risposte\` con data e domanda nel nome del file. La
risposta ha otto sezioni:
1. Documenti
2. Passaggi originali
3. Dati espliciti
4. Inferenze
5. Limiti
6. Copertura
7. Risposta finale
8. Dati tecnici per la verifica (file e righe, che non entrano nelle citazioni)

In chat compaiono per prime le sezioni 3, 4 e 7; le altre si chiedono a parte.

Le citazioni sono in stile Chicago e si fermano alla pagina, quando il file la indica. La citazione nasce
dall'intestazione del file e dal profilo della serie in `serie.ini` (campo `chicago`). Sotto ogni passaggio
la riga «Lettura» dice chi ha deciso la pertinenza e chi ha tradotto: un modello (quale), una sessione
assistita, una regola. La sezione 6 riporta i conteggi.

### Ricerche lunghe e quote esaurite

Ogni ricerca gira in un processo a sé, con lo stato salvato in `RAG\lavori\`: continua anche se riavvii il
server «Pipeline» o chiudi la chat, e Jan la ritrova alla domanda successiva («a che punto è la ricerca?»).
Quando le quote gratuite si esauriscono, la ricerca non si ferma: aspetta e riprova da sola (dopo 10, 15, 30
minuti, poi ogni ora, per al massimo 36 ore) e riprende da dove era. Lo stesso vale per la sintesi, se il
modello non risponde: la risposta salvata intanto contiene le parti già pronte. Se alcuni passaggi falliscono
sempre (risposte del modello non valide), dopo due tentativi la risposta viene scritta lo stesso e la sezione 5
dice quanti passaggi mancano.

La ricerca si ferma solo per errori che non passano da soli (chiave mancante o sbagliata, modello ritirato):
Jan riporta il messaggio. Se il PC si spegne o va in sospensione, la ricerca si interrompe: rifacendo la
domanda riprende da dove era. Il registro completo di ogni ricerca è in `RAG\lavori\<data-ora>\registro.txt`.

## Schede delle entità e glossario

Le ricerche funzionano solo su entità che hanno una scheda in `entita.ini`. Esempio:
```
[PCd'I (m-l)]
forma_italiana = Partito comunista d'Italia (marxista-leninista)
varianti = 意大利共产党（马克思列宁主义）; ...
collegate = ...
forme_ambigue = ...
note = ...
```
Campi:
- `varianti`: tutte le forme del nome che la ricerca deve trovare.
- `tipo`: persona, organizzazione, testata, stato, altro.
- `collegate`: entità da analizzare insieme nelle domande sull'evoluzione nel tempo, per esempio il partito o l'organo di stampa.
- `forme_ambigue`: forme che possono indicare anche un'altra entità; per queste il passaggio viene sempre controllato dal modello.
- `note`: indicazioni per il modello che legge i passaggi.

Regole per unire o separare le schede, per dirigenti, organi di stampa e forme ambigue: `docs\schede_entita.md`.
Controllo automatico (doppioni, forme in comune, forme brevi non dichiarate, letture sotto nomi senza scheda):
```
python schede.py controlla
```

### Entità nuove

Se chiedi di una persona o di un'organizzazione che non ha una scheda, Jan usa `esplora_nome`:
- cerca nelle fonti inglesi le forme latine del nome, tollerando gli errori dell'OCR;
- verifica le trascrizioni cinesi che propone il modello della chat;
- confronta le testate: dove la Peking Review nomina la persona, cerca nel Renmin Ribao delle tre settimane
  precedenti i nomi trascritti con il punto centrale accanto al paese o al partito (es. 比利时), e li propone;
- per ogni forma riporta conteggi per serie e anno, esempi con riferimento, quante volte compare accanto agli
  indizi, e segnala le forme brevi o spesso senza contesto (possibili omonimi).

Jan ti mostra le forme attestate e crea la scheda solo dopo la tua conferma: nessuna forma entra nella scheda
se non compare nelle fonti. Poi la ricerca procede come per le altre entità.

L'**indice delle fonti** (circa 900 MB in `RAG\indice\`) serve a `esplora_nome`, a `cerca_testo` e
all'estrazione delle occorrenze: con l'indice ogni ricerca legge per intero solo i file che possono contenere
il nome (tutti i file OCR e, del Renmin Ribao, solo i numeri in cui la forma compare), con lo stesso risultato
della lettura completa. Quando aggiungi o correggi file in `data\`, l'indice si aggiorna da solo alla prima ricerca
(indicizza solo i file nuovi o cambiati: pochi secondi). A mano, dal Prompt dei comandi nella cartella
`pipeline`: `python indice.py aggiorna`; `python indice.py stato` dice se è allineato alle fonti. Dopo molte
correzioni conviene ricostruirlo da capo per ripulirlo (`python indice.py costruisci`, 10-30 minuti).

`entita.ini` fa anche da glossario. Quando un passaggio contiene la forma cinese o inglese di un nome che ha una scheda, al modello viene indicato il nome italiano da usare.

## Importare nuove fonti

`importa.py` porta nel sistema materiale nuovo (per ora pensato per le fonti albanesi): PDF con testo, PDF
scansionati, foto o scansioni delle pagine (jpg, png, tif) e file `.txt`. Per ogni documento prende il testo
del PDF quando c'è, altrimenti fa l'**OCR** con Tesseract (gratuito, gira sul tuo PC); scrive in `data\` un
file `.txt` con l'intestazione dei metadati, come le altre fonti; registra in `importazioni\registro.csv`
il metodo, le pagine, la qualità dell'OCR e gli avvisi; aggiorna l'indice. Non inserisce marcatori di pagina.

**Preparazione (una volta sola)**, dal Prompt dei comandi:

```
winget install -e --id UB-Mannheim.TesseractOCR
python -m pip install pymupdf
cd C:\Users\ivan_\Desktop\RAG\pipeline
python importa.py prepara
```

Tesseract, PyMuPDF e i modelli delle lingue restano installati nel sistema, non nella cartella del progetto.
Durante l'installazione di Tesseract, in «Additional language data», spunta le lingue che servono (Albanian,
più Italian o French se importerai testi in quelle lingue). Per aggiungerne una dopo: riesegui l'installazione,
oppure copia `<lingua>.traineddata` da https://github.com/tesseract-ocr/tessdata_best nella cartella
`tessdata` di Tesseract (serve l'amministratore). Dopo `winget` chiudi e riapri il Prompt dei comandi.
`prepara` controlla che ci siano Tesseract, PyMuPDF e le lingue richieste dalle serie di `serie.ini`
(albanese: `sqi`). Se Tesseract o i modelli sono in cartelle diverse da quelle predefinite, indicale in
`config.ini`, sezione `[ocr]` (`tesseract = ...`, `modelli = ...`).

**Serie.** Ogni testata o raccolta ha una scheda in `pipeline\serie.ini`: tipo (periodico o volume),
lingua, cartella dentro `data\`, sigla dei file e modello della citazione (es. `Zëri i Popullit, {data}[, n.
{numero}]`, che diventa «Zëri i Popullit, 12 gennaio 1967»). Ci sono già Zëri i Popullit e Rruga e Partisë;
le altre si aggiungono copiando un blocco o chiedendo in Jan («crea la serie ...»).

**Importare.** In Jan: «importa la cartella C:\...\scansioni nella serie Zëri i Popullit». La prima volta
per una serie o un tipo di scansione Jan fa una **prova** sulle prime pagine e mostra testo, qualità e data
letta. Oppure dal Prompt dei comandi:

```
python importa.py importa "C:\scansioni\ZP 1967" --serie "Zëri i Popullit" --prova 2
python importa.py importa "C:\scansioni\ZP 1967" --serie "Zëri i Popullit"
```

- **Data**: per i periodici si prende dal nome del file (`1967-01-12`, `12.01.1967`, `12 janar 1967`...);
  se manca, dalla testata della prima pagina (segnata «da controllare»); oppure `--data`, o un file
  `--metadati elenco.csv` con le colonne `file, data, numero, titolo, autore, anno, volume`.
- `--unisci`: le foto delle pagine di un solo numero diventano un solo documento.
- L'importazione si può interrompere: le pagine già lette restano in `importazioni\_cache` e alla ripresa
  non si rileggono. I documenti già importati si saltano (`--sovrascrivi` per rifarli).
- **Qualità**: per ogni documento la confidenza media dell'OCR (0-100) e le pagine deboli (sotto 60) sono in
  `registro.csv` e nell'intestazione (`[OCR_CONFIDENCE]`). Sotto 70 conviene controllare a campione o
  rifare la scansione (300 dpi, in scala di grigi).

**Controllo delle intestazioni**: `python importa.py controlla` (o una sottocartella: `controlla
riviste\zeri_i_popullit`) segnala errori (citazione mancante, data non valida, testo vuoto) e avvisi
(numeri di documento ripetuti, date da controllare, OCR debole) in `importazioni\controllo_<data>.csv`.

**Nomi nelle fonti albanesi.** La stampa albanese scrive i nomi stranieri come si pronunciano e li declina
(Grippa: «Gripa», «Gripës», «Gripën»). Le forme già nelle schede non bastano: per ogni entità chiedi a Jan
`esplora_nome`, che con testi albanesi presenti cerca anche le trascrizioni albanesi probabili e le radici
delle forme declinate, e propone solo quelle attestate; entrano nella scheda dopo la tua conferma.

**Prima di usare i risultati albanesi**, conviene una prova rapida dei modelli sulla lettura dell'albanese
(una ventina di passaggi verificati da te), come per i modelli nuovi.

## Archivio unico delle letture

Ogni passaggio letto è conservato in `risultati\_archivio\letture.jsonl`, che sia stato letto dal modello o corretto da te. Una ricerca successiva non rimanda al modello lo stesso passaggio, né una sua copia identica in un altro file. Così le domande ripetute, di seguito o su altri periodi della stessa entità costano pochissimo.

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
Il primo comando registra che i due nomi indicano la stessa entità (`risultati\_archivio\equivalenze.json`). Il
secondo ricalcola i passaggi come li estrarrebbe la scheda e scrive il piano in `risultati\_archivio\` senza
toccare nulla. Ogni lettura vecchia risulta in uno di questi casi: già letta sotto la scheda, da riattribuire,
con decisione diversa, fuori dalla scheda (forma che la scheda non ha). Il terzo aggiunge all'archivio solo le
letture da riattribuire, dopo averne fatto una copia in `pipeline\_backup`.

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

Nel Prompt dei comandi, nella cartella `pipeline`:
```
python valuta.py "Nuova Unità"                                         (i modelli della catena attuale)
python valuta.py "Nuova Unità" --modelli "glm-4.7; nemotron-3-ultra"   (uno per uno, con tabella di confronto)
```
Lo script confronta lo smistamento dei modelli con la lettura di riferimento in `risultati\_riferimenti\nuova_unita`. Quel riferimento è una lettura assistita da Claude, non verificata a mano. Le prove vanno in `risultati\_prove\` e non toccano l'archivio. Obiettivo: richiamo ≥ 95%. Un modello entra nella catena `ricerca` solo dopo questa prova.

## Misure su un insieme verificato a mano

`valutazione.py` costruisce un insieme di riferimento verificato da te e misura su quello sia l'estrazione sia le
letture (per modello e per livello di provenienza). Funziona su qualsiasi corpus. Nella cartella `pipeline`:
```
python valutazione.py campione prova1 --n 100
python valutazione.py candidati prova1 --entita "Franz Strobl" --file 60
python valutazione.py importa prova1
python valutazione.py misura prova1 --modelli "gemma4; nemotron-3-ultra"
```
1. `campione`: estrae un campione stratificato (serie, lingua, decisione, provenienza) dei passaggi già letti e
   scrive `risultati\_valutazione\prova1\campione.csv`. Compila la colonna GIUDIZIO (sì / no / incerto) e
   VERIFICATO_DA. La decisione attuale non compare nel file, così la verifica è alla cieca.
2. `candidati`: cerca in un campione di file le forme più larghe del nome (cognome da solo, una lettera o un
   carattere diversi, accenti) che l'estrazione non trova. In `candidati.csv` segna GIUDIZIO = sì per le vere
   menzioni sfuggite.
3. `importa`: controlla i due file compilati e salva l'insieme di riferimento. I file usano il punto e virgola
   come separatore, così Excel li apre già divisi in colonne. Si possono salvare come CSV oppure come cartella di
   lavoro Excel (`campione.xlsx`, `candidati.xlsx`): vale il file salvato per ultimo.
4. `misura`: calcola richiamo e precisione, con un intervallo di confidenza al 95%, e scrive `misure_<data>.md`.
   Le misure riguardano le letture dell'archivio (per livello di provenienza), i modelli indicati (in
   `risultati\_prove\`, senza archivio) e l'estrazione.

## Problemi frequenti

- *«All models exhausted»* in Jan: le quote gratuite del momento sono finite per il modello della chat. Riprova più tardi; le quote di Gemini si rinnovano alle 9. Le ricerche già avviate aspettano e riprendono da sole.
- *«Tesseract non trovato»*: installalo (vedi «Importare nuove fonti») e riapri il Prompt dei comandi, oppure riavvia Jan; o indica il percorso in `config.ini`, sezione `[ocr]`.
- *OCR pieno di errori*: scansione a bassa risoluzione o storta; rifalla a 300 dpi. Per testi con molte parole in un'altra lingua, in `serie.ini` metti ad es. `ocr_lingue = sqi+eng`.
- *Il server «Pipeline» non parte*: controlla che FreeLLMAPI sia acceso e che in Command ci sia il percorso giusto di Python.
- *Errore 401/403*: chiave sbagliata o scaduta (in FreeLLMAPI). *Errore 404*: modello ritirato; disattivalo nel pannello.
- *Jan risponde senza usare gli strumenti*: controlla che sia scelto l'assistente «Ricerca fonti», che il modello abbia **Tools** attivo e che Web Search sia spento.

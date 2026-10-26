# Stato del sistema

Copia del documento «Stato del sistema» del progetto «Archivio interattivo» (versione del 22/10/2026).



## Obiettivo

Costruzione di un tool scientifico-storiografico volto a trovare tutte le occorrenze di una persona o un ente (Stato, partito, testata giornalistica…) all'interno di un largo corpus di fonti documentarie primarie e rispondere con i passaggi originali, la loro traduzione e il riferimento preciso. L'obiettivo finale è pubblicare un tool modulare, adattabile a documenti relativi argomenti differenti. Questa pubblicazione potrà avere forme variabili, a seconda delle opportunità (Server MCP, Plugin per LLM, Applicazione proprietaria…).



## Tentativi precedenti

Il progetto è partito con il tentativo di costruire un sistema RAG locale, ma questo si è rivelato presto lento, pesante ed inefficace, in quanto il sistema si limitava a rispondere con i primi due o tre riferimenti alle fonti, invece di compiere una ricerca esaustiva delle occorrenze. Successivamente è stato utilizzato un GPT personalizzato, tramite ChatGPT, nel cui contesto sono stati caricati i documenti indagati. Il risultato, grazie ad un prompt preciso, è stato migliore ma non abbastanza. Il risultato migliore è stato raggiunto trasformando il progetto in una skill Claude /ricerca-occorrenze-fonti, tuttavia voglio rendere questo progetto gratuito ed autonomo da abbonamenti. La soluzione scelta è stata combinare una pipeline locale programmata in Python a dei modelli LLM in cloud, forniti da chiavi API gratuite.



## Situazione attuale

Il tool è attualmente adattato alla mia ricerca sul "marxismo-leninismo globale", tendenza comunista emersa negli anni Sessanta del Novecento e collegata alla Cina maoista e l'Albania enverista.

Il corpus documentario è contenuto nella cartella `data` del progetto (`projects\dissident_communism\data`), ed è così suddiviso:
- `riviste\renmin_ribao` (testo digitale, un paragrafo per riga; pagine 第N版 rilevate), `riviste\peking_review`, `riviste\hongqi_1963-1976` (cinese), `riviste\hongqi_1977-1988` (traduzioni JPRS);
- `fonti_primarie\` (raccolte di documenti: 中共中央文件选集, 文化大革命 ecc., K.H. Fan 1968);
- `opere\` (Selected Works, voll. 1-5).

In tutto 7858 file .txt (6712 cinesi, 1146 in lingue occidentali). Ogni file ha un'intestazione `[SERIES]`, `[DATE]`, `[FULL_CITATION]`, `[LANG]`, `[YEAR]`, `[DATE_STATUS]`... letta da `estrai_occorrenze.leggi_intestazione`.

`audit\` contiene `changes.csv` (correzioni ai metadati, citato nelle intestazioni come `audit_fonti/registro_modifiche.csv`) e `open_issues.csv` (lacune e problemi aperti).



## Struttura tecnica

Il tool si usa attualmente dalla chat del programma Jan (assistente «Ricerca fonti», modello `auto:chat`), che raggiunge la pipeline attraverso il server MCP «Pipeline». I modelli sono gratuiti, forniti da FreeLLMAPI (sul PC, http://127.0.0.1:31415/v1).

### Come funziona una ricerca

- Scheda dell'entità in `glossary\entities.ini` (cartella del progetto) (varianti, contesto, forme ambigue, collegate); fa anche da glossario. Entità nuove: `esplora_nome` propone solo forme attestate (anche per allineamento Peking Review -> Renmin Ribao), poi `crea_scheda` dopo conferma.
- `avvia_ricerca` lancia un processo indipendente (`lavori.py`; stato in `system\jobs\<id>` del progetto): estrazione con espressioni regolari tolleranti all'OCR (`estrai_occorrenze.py`), smistamento e analisi con i modelli (`classifica.py`), sintesi (`sintesi.py` / `evoluzione.py`). Attese automatiche quando finiscono le quote (10, 15, 30, poi 60 minuti, fino a 36 ore). Codici d'uscita di classifica: 0 tutto letto, 3 limiti temporanei, 4 errore permanente.
- Archivio unico dei passaggi già letti (`results\archive\readings.jsonl`): non si rilegge nulla.
- La risposta salvata in `results\answers\` ha 7 sezioni; Jan presenta «risposta_pronta» (presentazione della pipeline) senza ricostruirla.
- Indice SQLite FTS5 (`system\index\sources.sqlite`, circa 870 MB): serve a `esplora_nome`, `cerca_testo` e a scegliere i file del Renmin Ribao da leggere. Si aggiorna da solo (solo file nuovi o modificati).

### Provenienza, citazioni, valutazione (fase 1, 22/10/2026)

- **Provenienza delle letture** (`archivio.py`): ogni lettura dichiara chi ha deciso la pertinenza e chi ha tradotto, su tre livelli (modello e quale, sessione assistita, regola e quale). Registrata il 22/10 in tutte le 10.840 letture dell'archivio e nelle cartelle dei risultati (copie precedenti in `pipeline\_backup\2026-10-22_provenienza`). Decisioni: 9.461 per regola (7.362 classificazioni per regola in sessione, 1.980 esclusioni in blocco, 64 forme inequivocabili, 55 riprese da letture per regola), 1.295 in sessione, 84 da un modello. Traduzioni: 9.500 passaggi non tradotti, 1.152 in sessione, 180 da un modello, 8 voci di sommario.
- **Citazioni** (`citazioni.py`, campo `chicago` di `serie.ini`): stile Chicago, fino alla pagina (marcatore `[[p. N]]` o `pagina_regex`, oggi solo 第N版 del Renmin Ribao). Nelle risposte non compaiono più file e righe, che passano alla sezione 8. Le `FULL_CITATION` del corpus restano quelle di prima: le risposte non le usano più.
- **Test automatici** in `pipeline\test` (128): estrazione, citazioni, provenienza, riallineamento dei passaggi, date interne, esportazioni PAGE/ALTO, prova OCR, scelta tra strato del PDF e OCR, profili di serie, progetti di ricerca, server MCP, calcoli della valutazione.
- **Strumento di valutazione** (`valutazione.py`): campione alla cieca, candidati sfuggiti all'estrazione, misure con IC 95%. Nessun insieme verificato a mano esiste ancora. In una prova, la ricerca larga ha trovato 施特罗伯尔 (Franz Strobl, solo cognome) in una raccolta del 1976: è una forma assente dalla scheda.
- **Schede delle entità**: regole confermate in `docs\schede_entita.md`, controllo automatico `schede.py controlla`. Al 24/10: 91 schede, 0 errori, 75 avvisi, 153 informazioni. Tra gli avvisi: 42 schede senza note; 6 nomi che indicano gruppi o insiemi di forme; forme brevi non dichiarate in `forme_ambigue`.
- **Riattribuzione delle letture** (24/10): i nomi senza scheda sono dichiarati equivalenti (`risultati\_archivio\equivalenze.json`) e le loro letture copiate sotto le schede attuali con `archivio.py riattribuisci` (piani in `risultati\_archivio\riattribuzione_*_20261024.csv`, copia dell'archivio in `pipeline\_backup\2026-10-24_riattribuzione`). Aggiunte 560 letture: 319 PCB (da «PCB-Grippa (Belgio)»), 128 Dirigenti ORT/PTE/PT (Spagna), 107 KPD/ML (da «KPD/ML (Germania Ovest)» e «Communist party of Germany»), 6 PCd'I (m-l). Le 47 di «Partito Marxista-Leninista d'Austria» erano già lette sotto MLPÖ (Austria); le 26 di «PCB-Grippa» con il solo nome Grippa sono già lette sotto Jacques Grippa. Il piano riallinea le posizioni dei passaggi spostate dalle modifiche alle intestazioni (`archivio.riallinea`).

### Data interna dei documenti nelle raccolte (fase 2, lavoro 9, 24/10/2026)

- `date_interne.py`: per i file senza data completa che non sono periodici (raccolte, volumi) la data del documento che contiene il passaggio è l'ultima data d'intestazione che lo precede. Intestazioni forti: data sola sulla riga, tra parentesi a inizio o fine riga, data d'agenzia (新华社…讯/电). Deboli, valide solo se al giorno: tra parentesi in mezzo alla riga, a inizio riga seguita da virgola o da 《. Scartate: note (①…), date a fine frase, testatine senza giorno ripetute, elenchi fitti (indici), anni oltre l'edizione, intestazioni a più di 30.000 caratteri. Riconosce date cinesi (numerali e cifre, con errori OCR come 目 per 日) e date con i mesi in en, fr, it, es, de, sq. Stato sempre «dedotto». Profilo di serie: `data_interna`, `data_interna_anni`, `data_interna_distanza`.
- Uso: `estrai_occorrenze.py` registra `data_interna` in ogni passaggio delle raccolte e applica `--dal/--al` sulla data del documento, non sull'anno di edizione (prima le raccolte del 2012-2013 restavano fuori da ogni periodo storico). `cronologia.py` usa le date al giorno per estremi e silenzi, tutte per la presenza per anno, e conta ogni documento interno; i fatti dichiarano quante date sono dedotte. `sintesi.py` numera un documento per ogni documento interno, annota «documento del … (data dedotta dal testo)» fuori dalla citazione e non passa più al modello l'anno di edizione come data del documento. `evoluzione.py` raggruppa per anno del documento. Lo strumento MCP `passaggi_archivio` filtra per anno del documento e restituisce `data_documento`. I passaggi estratti prima del lavoro 9 ricevono la data al momento, dal file.
- Prova del 24/10 sui 282 passaggi delle raccolte nell'archivio: 270 con data (tutte al giorno). Campione di 25 verificato a mano: 21 corretti, 2 errati (data in una frase andata a capo; firma del documento precedente quando l'apertura del successivo è solo al mese), 2 dubbi (intestazione a oltre 25.000 caratteri). Senza data: Selected Works (anni stampati con cifre illeggibili, es. «August!(#&») e *The Chinese Cultural Revolution - Selected Documents*.

### Profili di serie (fase 3, lavoro 12, 25/10/2026)

Le regole che il codice scriveva per le serie del corpus attuale stanno ora nei profili di `glossary\series.ini` (cartella del progetto), letti da `scripts\profili.py`. Un file appartiene a un profilo per serie o per cartella (la più specifica).
- Campi nuovi: `periodo` (primo e ultimo numero: fine delle fonti per i silenzi), `periodicita` (anche con cambi datati, per collocare nel mese le lacune dei fascicoli indicati per numero), `gruppo` (Hongqi + Red Flag; «documenti» per le raccolte), `righe_intere` (il Renmin Ribao: l'indice sceglie con certezza i file da leggere), `allinea_con`/`allinea_giorni` (Peking Review -> Renmin Ribao, 21 giorni, per `esplora_nome`); `pagina_regex` ora vale anche per la pagina dei passaggi e per i riferimenti di `cerca_testo`. Nuovo profilo «Raccolte di documenti» (cartella `fonti_primarie`).
- Codice: `cronologia.py` (periodici dal profilo; fine delle fonti = ultimo numero tra le serie in cui l'entità compare; lacune di tutte le serie, con il nome della serie; i fascicoli datati all'anno contano nella presenza per anno), `sintesi.py` (lacune e mesi dalle sigle e periodicità dei profili; note dei «Limiti» dal profilo di ogni documento, senza più la frase doppia sulla stampa cinese; frase sulle raccolte solo per i documenti senza data dedotta), `indice.py`, `classifica.py`, `esplora.py`, `ricerca.py`, `mcp_server.py` (fonti selezionabili = gruppi dei profili, compresi «documenti» e le serie albanesi).
- Corretto un residuo del lavoro 9: `ricerca.py` rifiltrava i passaggi per anno di edizione dopo l'estrazione, così con `--al` le raccolte del 2012-2013 sparivano di nuovo.
- Non regressione: 229 citazioni identiche; `esplora_nome` (Jacques Grippa) identico salvo la dicitura dell'allineamento; evoluzione di Jacques Grippa senza modello: differenze solo volute (un fascicolo Hongqi 1964 in più, fine delle fonti al 29/12/1980 per un'entità presente solo nella Peking Review, nota doppia tolta). 10 test nuovi su profili finti di serie albanesi.
- Restano nel codice: le forme generiche di partito di `classifica.forma_sicura` (regole di lingua, non di serie), il valore `filename+local_header` di METADATA_SOURCE e le istruzioni del server MCP, che descrivono il corpus (lavoro 14).
- Da correggere nel corpus: `RF1980-02.txt` ha data 1930-01-16.

### Progetti di ricerca separati dal motore (fase 4, lavoro 13, 25/10/2026)

- `pipeline\progetto.py`: il motore (`pipeline`, `config.ini`) è separato dalla cartella di progetto, che contiene `data`, `audit_fonti`, `indice\fonti.sqlite`, `risultati`, `risposte`, `lavori`, `importazioni`, `entita.ini`, `serie.ini`, `_backup` e `progetto.ini`. Il progetto si sceglie in `config.ini`, `[progetto] cartella`, o con la variabile d'ambiente `AIRCHIVIST_PROGETTO` (prevale: in Jan un server MCP per progetto). `progetto.ini` dà il nome, sposta singoli file (`[percorsi]`, relativi al progetto) e può cambiare qualsiasi impostazione di `config.ini` solo per quel progetto. Senza progetto scelto vale la disposizione di prima.
- Comandi: `python progetto.py stato`, `python progetto.py nuovo <cartella> --nome "..."` (cartelle, CSV di `audit_fonti` con BOM e CRLF, `entita.ini`, `serie.ini` con la descrizione dei campi, `progetto.ini`; non tocca una cartella non vuota).
- Tutto il codice prende i percorsi da `llm.percorso` (ora in `progetto.py`): tolti i percorsi ricavati a mano per `serie.ini` (`profili.py`, `importa.py`), `importazioni`, `indice`, `lavori`, `risposte`, `_backup`; le prove dei modelli (`valuta.py`, `valutazione.py`) scrivono configurazioni temporanee con tutti i percorsi del progetto, assoluti, e con le sue impostazioni.
- Questo progetto: `config.ini` sceglie `cartella = ..`; `progetto.ini` nella radice («Comunismo dissidente tra Pechino e Tirana») tiene `_backup` in `pipeline`; dal 25/10 `entita.ini` e `serie.ini` stanno nella radice (vedi «Dati di ricerca separati dal motore»). Nessun file del corpus spostato; percorsi risolti identici a prima.
- Prova completa su un progetto nuovo nello scratchpad (variabile d'ambiente): creazione, serie aggiunta, importazione di un'esportazione PAGE/ALTO, indice, `cerca_testo` dal server MCP, scheda creata ed estrazione delle occorrenze; nel progetto vero nessun file toccato. 5 test nuovi.

### Server MCP generico (fase 4, lavoro 14, 25/10/2026)

Strumenti (13; con `azione` quelli che uniscono più operazioni): guida, schede (elenca, crea), esplora_nome, cerca_testo, ricerca (avvia, attendi, ferma), risposte (elenca, leggi), passaggi_archivio, copertura_fonti, apri_fonte, varianti (elenca, aggiungi, scarta), correggi_passaggio, importa (avvia, stato), serie (elenca, crea). I 18 nomi di prima (elenca_entita, crea_scheda, avvia_ricerca, attendi_ricerca, ferma_ricerca, leggi_risposta, elenca_risposte, importa_fonti, stato_importazione, elenca_serie, crea_serie...) restano accettati come alias, non elencati.
- Istruzioni non più scritte nel server per questo corpus e per Jan: `pipeline\istruzioni.py` le compone da regole generali del motore, elenco delle fonti dai profili di serie (con nome e descrizione del progetto) e `istruzioni.md` del progetto (qui: argomento, carattere delle fonti, cariche cinesi, esempi di citazione, «mai la parola corpus»). Lingua delle risposte e attesa massima di `ricerca` in `[mcp]` di `config.ini` o `progetto.ini` (prima 75 s fissi, tarati su Jan). Consegna in tre modi: campo `instructions` di initialize, prompt MCP `istruzioni` (nuova capacità `prompts`), strumento `guida`; in Jan l'assistente può limitarsi a chiamare `guida`.
- `copertura_fonti` conta i periodici dai profili di serie (non più dalla sola cartella `data\riviste`) e registra anche i numeri mancanti; filtri per anno senza il limite 1940-1999; descrizioni degli strumenti senza esempi del corpus.
- Test: server avviato in stdio su un progetto nuovo (istruzioni senza nulla del corpus attuale né del client, 13 strumenti, prompt, alias, errori, guida).
- Prova in Jan del 25/10 («Cosa dicono le fonti riguardo Enrico Berlinguer», entità senza scheda): risposta non usabile. Il modello non ha chiamato `guida`, ha ricostruito la risposta con `cerca_testo` e `apri_fonte`, ha inventato riferimenti (Renmin Ribao, 4 maggio e 9 luglio 1965) e date (Rinascita del 13 «giugno», nel testo 13 marzo), ha citato file e righe e prodotto testo degenerato (catena `auto:chat`). Correzioni lato server: regole essenziali nelle descrizioni degli strumenti (le sole che ogni client mostra sempre: `guida` per primo, `ricerca` come modo di rispondere, `cerca_testo` e `apri_fonte` solo per verificare, mai file e righe); i risultati di `cerca_testo` e `apri_fonte` iniziano con un'avvertenza (testo grezzo, non è una risposta) e `cerca_testo` indica il prossimo passo (ricerca sulla scheda corrispondente, o esplora_nome se non c'è); `passaggi_archivio` e `ricerca` per un'entità senza scheda indicano esplora_nome, conferma, schede crea, ricerca. Lato utente: assistente di Jan che chiama `guida` all'inizio e catena `auto:chat` limitata a modelli affidabili negli strumenti. Seconda prova in Jan: procedura corretta (guida, schede, esplora_nome, conferma), ma righe dei file presentate come pagine («p. 117» da `file_e_riga`), «corpus», parole storpiate, e soprattutto Berlinguer dato come presente «solo nella Peking Review», mentre 贝林格 compare 167 volte nel Renmin Ribao (1965-1980).
- Correzioni (25/10): `pipeline\varianti_nomi.py` genera nel motore le varianti che prima dipendevano dalla chat: indizi latini (paesi, nazionalità, partiti in sei lingue) tradotti in cinese, trascrizioni cinesi sul modello Xinhua con varianti per sillaba (il nome proprio si combina con i cognomi attestati), traduzioni dei nomi di partito; `esplora_nome` propone le attestate vicine agli indizi («da_confermare_generate»). Su 15 nomi del progetto la forma reale è sempre tra le generate. L'allineamento non preferisce più un frammento raro (扬贝林格, 1 riga) alla forma vera (贝林格, 167). File e riga nei risultati stanno in `solo_per_apri_fonte`. Non coperte: grafie Wade-Giles dei nomi cinesi (Peking Review prima del 1979).
- `pipeline\prova_chat.py`, prova dei modelli della chat sulla domanda vera (25/10, Berlinguer): 8/8 per auto:chat (tre giri: gemini-3.6-flash, qwen3.8-27b, glm-4.7-flash), gpt-oss-120b, nemotron-3-ultra, glm-4.7-flash; non misurati per quote o errori del servizio gemini-3.8-flash, gemini-3.5-flash, gemma-4-31b, nemotron-3-super-120b. Alla lettura: gpt-oss-120b la risposta migliore; glm-4.7-flash propone come forme il solo nome proprio («Enrico», 恩里科) e un altro membro della delegazione emerso dall'allineamento. Il testo degenerato visto in Jan non si è ripetuto.

### Risposte incomplete in Jan (25/10/2026, pomeriggio)

- **Ricerca fermata da un'eccezione**: la ricerca su Berlinguer del mattino si è fermata a 25/60 passaggi perché un modello ha risposto all'analisi con un elenco JSON (`[{...}]`) e `classifica.analizza` si aspettava un oggetto. Ora `llm.come_oggetto` accetta un elenco con un solo oggetto, mette un elenco di oggetti sotto l'unica proprietà elenco dello schema (smistamento a lotti) e tratta le altre forme come errore del passaggio, che si riprova (`test_llm.py`). Rilanciata dal server MCP: completata in 27 minuti (60 passaggi, 56 pertinenti, sintesi 4 minuti).
- **Risultati tagliati da Jan**: `maxToolOutputChars` di Jan è 8000 e la risposta pronta supera quel limite (Dinucci 9.730 caratteri, Berlinguer 8.184): Jan tagliava la fine del JSON (limiti, nota, parte dei dati) senza dirlo al modello. Ora il server tiene ogni risultato entro `[mcp] max_caratteri` (7500): accorcia le parti più lunghe, mai la risposta finale e le indicazioni, e aggiunge `avviso_lunghezza` (`mcp_server.adatta`, 3 test).
- **Attesa abbandonata**: su Dinucci (tutto in archivio) la sintesi ha richiesto 12 minuti (errore 502 del servizio); il modello della chat ha smesso di attendere dopo circa 10 e ha detto che la ricerca non finiva. Lo stato in corso ora dice al modello quanto può durare la sintesi e cosa dire all'utente se smette di attendere.
- **Forme ambigue non cercate**: le 203 occorrenze di Berlinguer stanno in 60 passaggi, 44 file e 40 documenti pertinenti (quattro esclusi per omonimia), ma la ricerca ha mancato Peking Review 1980, no. 18 (13 menzioni del solo cognome, anche «NRICO Berlinguer» e «ComradeBerlinguer»): «Berlinguer» è in `forme_ambigue` ma non in `varianti`, e la ricerca cerca solo le varianti. `schede.py controlla` lo segnalava già (anche per MLPÖ e PCd'I (m-l) Linea rossa); ora il messaggio dice che la forma non viene cercata e `schede crea` avvisa la chat (`schede.ambigue_non_cercate`, `test_schede.py`). La scheda di Berlinguer non è stata cambiata; contiene anche 巴什塔, che nel Renmin Ribao indica un altro dirigente del PCI (1939) e una diga jugoslava.
- **Anno ricavato dalla data della fonte**: nella risposta su Berlinguer «visitò Mosca nell'ottobre 1979» viene da un articolo del 2 agosto 1979 («贝林格十月访问莫斯科以后»): il fatto è passato, quindi ottobre 1978. Causa: il prompt di analisi chiedeva di ricavare l'anno dalla data della fonte. Ora `classifica.REGOLA_ANNO` confronta mese e data della fonte (fatto passato in un mese successivo: anno precedente; annuncio in un mese precedente: anno seguente) e altrimenti lascia la data senza anno. `archivio.py date_sospette` trova le letture già fatte: su 8.263 pertinenti, 596 hanno date in italiano nella sintesi, 1 sola sospetta (questa); 30 hanno già l'anno precedente. `--applica` le segna da rileggere (`da_rileggere`): `classifica.da_completare` rimanda all'analisi, senza smistamento, anche i passaggi già presenti nella cartella della ricerca (`test_anno_fonte.py`). Non ancora applicato all'archivio.
- **Prova di un progetto nuovo con PDF** (25/10/2026, progetto di prova nello scratchpad con *History of the PLA*, 606 pagine di testo nativo, e Larrabee, «Whither Albania?», *The World Today* 1978, scansione con strato di testo): creazione, serie, prova e importazione, controllo, indice, esplora_nome, scheda e ricerca funzionano (Mehmet Shehu: 3 passaggi, uno escluso perché riguarda Abedin Shehu; l'edizione 1982 della *History of the PLA* non nomina Mehmet Shehu). Corretti: il modello di `istruzioni.md` mandava la spiegazione alla chat come regola (ora tutto commentato); `importa.py` scriveva `TITLE` solo per i volumi, e la citazione dell'articolo prendeva il nome della rivista come titolo; «?.» nelle citazioni (`citazioni.dopo_punto_interrogativo`); `classifica.e_sommario` prendeva per sommario un articolo con note a piè di pagina e date (ora non contano i numeri delle date né i rimandi alle note dopo una data; mesi come parole intere: «Hsiang Jung 23» non è giugno). Sui passaggi di tutte le ricerche: 28 sommari su 30 restano tali, escono i due elenchi di note di PR1964-06, nessun sommario nuovo. Le letture già in archivio segnate come sommario non si rileggono da sole. `test_progetto_nuovo.py` (7 test). Aperte: date al mese.
- **Pagine dei PDF** (25/10/2026): `pipeline\numerazione.py` e `importa.py` scrivono `[[p. N | pdf K]]` in ogni pagina dei PDF importati, dalla pagina indicata (`--prima-pagina N --da-pagina K`, anche nel CSV dei metadati), dalle etichette di pagina del PDF o dai numeri stampati in testa e in piede con scarto costante (stato `PAGES_STATUS: dedotto`, nota con le pagine lette; pagine senza numero annotate «dedotta»). Provato sui due PDF: Larrabee, etichette di JSTOR, pp. 61-69 (copertina senza pagina); *History of the PLA*, numero in prima riga letto in 594 pagine su 594, pp. 13-606. Nelle risposte le citazioni arrivano alla pagina (Larrabee: 66 e 68; *History of the PLA*: 261 per Abedin Shehu, 572 per il Partito comunista italiano), verificate sul PDF. L'importazione toglie anche i caratteri di controllo (280 caratteri nulli nella riga di download di JSTOR). `test_numerazione.py` (15 test).
- Da decidere: `modelli_ammessi` in `config.ini` è vuoto, quindi leggono i passaggi anche modelli non misurati (glm-4.7-flash, qwen3.8-27b, nemotron-3-ultra nella ricerca su Berlinguer); in Jan il server «Pipeline» risulta disattivato in `mcp_config.json` e va riavviato dopo queste modifiche.

### Modelli (FreeLLMAPI)

Profilo «ricerca» attivo, strategia custom (affidabilità 0,3, velocità 0,2, intelligenza 0,5). Catena «ricerca» 26 modelli, «chat» 17. Provati con la prova rapida (21 passaggi Nuova Unità, 21/10): Nemotron Ultra (NVIDIA) 21/21, GPT-OSS 120B (Ollama) 21/21, Gemma 4 31B (Ollama) 21/21, Nemotron 3 Super (Ollama) 15/15, Muse Glimmer 30B (NVIDIA) 15/15, Ministral 14B (Mistral) 20/21; scartato Nemotron 3.5 Lightning (0/15). Regola: stesso modello su un nuovo fornitore non va riprovato; modello nuovo -> prova rapida; `valuta.py` completo solo nei casi dubbi. I risultati sono quelli riportati qui (il file della prova, `risultati\_prove\prova_rapida_2026-10-21.md`, è stato tolto il 25/10). `config.ini`: max_token 4000 (sintesi 8000).

Prova rapida del 22/10 (`valutazione.py modelli`) sui 97 passaggi verificati a mano. La prima fase ha provato 50 modelli su 30 passaggi; 13 li hanno letti tutti, gli altri sono stati fermati da quote o errori del servizio. Seconda fase sui 97 passaggi (pertinenti riconosciuti; «sì» giusti):

| Modello | Pertinenti riconosciuti | «Sì» giusti |
|---|---|---|
| gpt-oss-20b | 66/70 | 65/69 |
| gemma-4-31b | 65/70 | 65/66 |
| gpt-oss-120b | 65/70 | 61/65 |
| nemotron-3-super | 64/70 | 61/68 |

`modelli_ammessi` contiene ora gpt-oss-20b, gemma-4-31b e gpt-oss-120b, sia nella forma con i due punti sia in quella con il trattino. La catena «ricerca» di FreeLLMAPI contiene però anche altri modelli: se risponde uno di questi, la lettura si ferma. La catena va quindi ridotta ai tre modelli ammessi. Il filtro vale anche per la sintesi, i cui modelli non sono ancora stati misurati.

### Importazione di nuove fonti

`pipeline\importa.py` + `serie.ini` (schede delle serie: Zëri i Popullit, Rruga e Partisë). Testo del PDF se c'è, altrimenti OCR con Tesseract (TSV con confidenza); intestazione standard; registro in `importazioni\registro.csv`; cache delle pagine per riprendere; aggiornamento dell'indice. Comandi: prepara, serie, importa (--prova N, --data, --metadati csv, --unisci, --sovrascrivi), controlla.

Esportazioni PAGE XML e ALTO XML (fase 3, lavoro 10, 25/10/2026): `pipeline\pagine_xml.py` legge PAGE (qualsiasi versione dello schema; ordine di lettura da ReadingOrder, anche con gruppi annidati, o dall'attributo `readingOrder` di Transkribus; testo delle righe o delle parole; confidenza `conf`) e ALTO v2-v4 (String, SP, HYP; confidenza `WC`; più pagine per file), anche dentro un `.zip` senza estrarlo. `importa.py` fa di una cartella di pagine XML, o di un `.zip`, un documento, con le pagine in ordine naturale; scrive `[[p. N | img K]]` dove il file dichiara la pagina stampata (regione «page-number» in PAGE, `PRINTED_IMG_NR` in ALTO) e nell'intestazione `TEXT_METHOD`, `OCR_ENGINE`, `PAGES`; ignora e segnala i file XML che non sono pagine (METS). Provato su esportazioni costruite sugli schemi PAGE 2019 e ALTO v4 (13 test, compresa un'importazione completa in una cartella temporanea e il controllo delle intestazioni): manca la prova su esportazioni vere di Transkribus ed eScriptorium. Non ancora fatti: metadati proposti dai file METS, numerazione delle pagine dedotta quando il file non la dichiara (progettazione, sezione 5, passo 4).

Prova dei motori OCR (fase 3, lavoro 11, 25/10/2026, in corso): `pipeline\motori_ocr.py` (motori intercambiabili: Tesseract con segmentazione a scelta, PaddleOCR in un Python a parte tramite `ocr_paddle.py`, Kraken dichiarato) e `pipeline\prova_ocr.py` (prepara, misura del CER su riferimenti verificati a mano, tempi; confronto anche con lo strato di testo del PDF). Esito sui motori:
- **PaddleOCR 3.7.0** (PaddlePaddle 3.3.1, Python 3.13): su CPU Windows oneDNN si ferma con «ConvertPirAttribute2RuntimeAttribute not support», anche disattivando PIR; senza oneDNN una pagina richiede circa 50 s, con i modelli medium o mobile e qualsiasi limite del rilevatore (Tesseract: 3-4 s). Tempo giudicato inaccettabile: disinstallato con i suoi modelli. RapidOCR (stessi modelli su ONNX Runtime) non provato per scelta.
- **Kraken**: non provato, non funziona su Windows senza WSL (da installare come amministratore).
- **Tesseract 5.5.3** (`chi_sim`, `sqi`): psm 1, 3 e 6.
Campioni in `risultati\_prove\ocr\`: `cina_icm` (国际共产主义运动史.pdf, pp. 50, 200, 320, scansione con un vecchio strato di testo) e `albania_guerilas` (Guerilas made in Albania.pdf, pp. 30, 90, 150). Sono stampe recenti, non stampa d'epoca. Misura del 25/10 (`misure_2026-10-25.md`), su riferimenti preparati da Claude come lettura assistita sulle immagini, non verificati a mano e nati dalla correzione della lettura di Tesseract psm 1 (quindi possibilmente favorevoli a Tesseract):

| Campione | Motore | CER | CER senza punteggiatura | Secondi per pagina |
|---|---|---|---|---|
| cina_icm | Tesseract chi_sim psm 6 | 1,4% | 0,7% | 2,8 |
| cina_icm | Tesseract chi_sim psm 1 / psm 3 | 1,5% | 0,8% | 3,9 / 2,9 |
| cina_icm | strato di testo del PDF | 1,9% | 1,6% | 0 |
| albania_guerilas | Tesseract sqi psm 1 / 3 / 6 | 0,5% | 0,3% | 2,0 / 1,4 / 1,3 |

Esito provvisorio: su stampa recente pulita Tesseract basta per cinese e albanese; la segmentazione non cambia la qualità (psm 6 è la più rapida); lo strato di testo di quel PDF è un po' peggiore di un OCR rifatto. Di conseguenza (25/10) `importa.py` non preferisce più lo strato a prescindere: per i PDF scansionati con strato di testo rifà l'OCR su 3 pagine del corpo (25%, 50%, 75%) e tiene lo strato solo se concorda entro il 2% dei caratteri, o se l'OCR è poco sicuro (confidenza media sotto 85, con avviso); altrimenti rifà l'OCR di tutto il documento riusando le pagine del campione (`confronto_testi.py`, 8 test). Sul PDF cinese: discordanza 4,3%, confidenza OCR 94,3, strato scartato. I PDF con testo nativo non vengono confrontati. Soglie (2%, 85) scelte a giudizio, da tarare su altri campioni. Gli errori di Tesseract sul cinese sono soprattutto virgolette di chiusura lette come d'apertura e caratteri simili (遗/遍, 帐/帮, 人/入). Restano da fare: verifica a mano dei riferimenti, campioni di stampa d'epoca (Renmin Ribao, Zëri i Popullit), Kraken con WSL. I due libri non sono serie di `serie.ini`: nessun profilo aggiornato.

### Distribuzione (fase 4, lavoro 15, 25/10/2026)

- `pipeline\installa.py`: `librerie` (installa `requirements.txt` nel Python di sistema), `controlla` (Python, SQLite FTS5, servizio dei modelli con chiave e raggiungibilità, progetto in uso, PyMuPDF, Tesseract con le lingue delle serie, PaddleOCR; esce con 1 se manca un requisito necessario), `client` (configurazione del server MCP per Jan, Claude Desktop, LM Studio o generica, con i percorsi del PC; non scrive nei file dei client).
- `requirements.txt` (solo PyMuPDF, facoltativo), `LICENSE` (AGPL-3.0, testo ufficiale di gnu.org), `README.md` in inglese; `LEGGIMI.md` e `ISTRUZIONI.md` con l'installazione.
- Python minimo 3.10: i 140 test passano con 3.10, 3.13 e 3.14 (senza PyMuPDF i test sui PDF si saltano invece di fallire). Provata un'installazione pulita (copia dei soli file del repository, Python 3.10 senza librerie, progetto nuovo vuoto): controllo superato.
- Restano: corpus d'esempio libero da diritti (rimandato), traduzione inglese di `ISTRUZIONI.md`, dati di ricerca dell'autore (`entita.ini`, `serie.ini`, `progetto.ini`, `istruzioni.md`) da separare prima di pubblicare il repository.

### Dati di ricerca separati dal motore (fase 4, lavoro 15, 25/10/2026)

- `entita.ini` e `serie.ini` spostati da `pipeline` alla radice del progetto (posizione predefinita); `progetto.ini` non li sposta più. Con `istruzioni.md` e `progetto.ini` sono fuori dal controllo di versione (`.gitignore`, `git rm --cached`): restano sul disco; le versioni precedenti sono nella storia di git.
- Il motore porta `pipeline\serie_modello.ini` (descrizione dei campi ed esempio), da cui `progetto.py nuovo` scrive il `serie.ini` dei progetti nuovi.
- I test non leggono più il progetto in uso: i profili delle serie su cui sono scritti stanno in `pipeline\test\progetto_prova` (`prova.py` lo sceglie con `AIRCHIVIST_PROGETTO` per i moduli delle citazioni e della cronologia); le importazioni di prova si scrivono il proprio `serie.ini`. Provato su una copia dei soli file del repository: 140 test con Python 3.10 e 3.14, `installa.py controlla` (segnala schede e serie mancanti e come creare un progetto), server MCP avviato senza progetto (`schede` vuote, `guida`). Sul progetto vero: 92 schede, 8 serie, 0 errori.
- Restano nella storia di git: le versioni precedenti dei quattro file sono nei commit fino al 25/10. Per pubblicare serve un repository nuovo senza storia o una storia riscritta.
- Restano da valutare prima della pubblicazione: `CLAUDE.md` e `docs/` (stato, piano, schede) parlano di questa ricerca; `config.ini` ha `cartella = ..`.

### Riordino della cartella (25/10/2026)

- Tolto `pipeline\registra_analisi.py` (registrava le letture fatte in chat per la vecchia skill «ricerca-occorrenze-fonti»; lo sostituisce `sessione.py registra`). Resta nella storia di git.
- `pipeline\_backup`: tolte le copie di codice e documenti identiche a una versione già in git; restano le copie dei file fuori da git (fonti, archivio, risultati, schede) e le versioni intermedie mai committate. I file sparsi (`entita.ini.bak*`, `config.ini.prima_max_token`) sono in cartelle per data (`2026-10-15_entita`, `2026-10-20_entita`, `2026-10-21_config`).
- `risultati\_prove`: tolte le prove di smistamento dei modelli del 20-23/10 (i risultati sono riassunti in «Modelli»); restano `chat`, `ocr` e la prova della skill (`prova_skill_enrico_berlinguer`, spostata da `risultati`).
- `risposte`: tolta la seconda risposta su Enrico Berlinguer del 25/10 (stessa domanda, cinque minuti dopo).
- `ISTRUZIONI.md`, `LEGGIMI.md`, `CLAUDE.md`: elenco delle cartelle e dei programmi aggiornato; `.gitignore` senza le righe di `pipeline\entita.ini` e `pipeline\serie.ini`.

### Skill ricerca-fonti (25-26/10/2026)

Due skill con lo stesso nome: in Claude Code (`.claude\skills\ricerca-fonti`) legge i passaggi del corpus del PC, con l'archivio unico; nella chat di Claude (`skill_chat`, zip con `pipeline\crea_skill_chat.py`) lavora su un corpus piccolo caricato nella conversazione, senza archivio delle letture, e crea schede e serie con l'utente. In entrambe Claude legge i passaggi al posto dei modelli via API (`sessione.py`: prepara, registra, documenti; `sintesi.py --sintesi-da`); le letture dichiarano «sessione assistita» con il nome del modello.
- Prova su Enrico Berlinguer in Claude Code (25/10, `risultati\_prove\prova_skill_enrico_berlinguer`): stessa pertinenza della risposta dei modelli gratuiti (61 pertinenti, 3 omonimi), senza una decina di errori di data (fatti datati con la data della fonte o del dispaccio); circa 120-130 mila token.
- Confronti nella chat (25/10, stessa domanda con e senza skill). Renmin Ribao 1-10 gennaio 1961, PDF con lo strato di testo illeggibile (font CID senza ToUnicode): con la skill 10 minuti, 297 menzioni dell'URSS in 60 passaggi, ma il testo decodificato da uno script della chat; la seconda chat ha caricato la skill da sola (la descrizione corrisponde alla domanda) e ha scelto l'OCR di 72 pagine (circa 30 secondi per pagina), interrotta dopo 45 minuti. Cinque documenti sui partiti m-l filo-cinesi (volume del V congresso del PLA del 1966, quattro documenti CIA 1963-1971): con la skill 14 minuti, 76 passaggi; Claude base 4 minuti, risposta più ricca (critica delle fonti, contesto) e pagine dei documenti CIA giuste, ma lettura solo parziale del volume del 1966. Citazioni controllate sui PDF: giuste in entrambe.
- Correzioni (26/10): `chat.py apri` legge anche `/mnt/user-data/attachments`; date al mese (`--data 1971-11`: `[DATE: 1971-11]`, citazione «novembre 1971», nessuna data interna dedotta), in `importa.py`, `citazioni.py`, `date_interne.py`, `sintesi.py`; `numerazione.py` cerca il numero isolato fino alla quinta riga dal bordo (sotto il numero, nei documenti declassificati, ci sono «25X1», «SECRET» e la dicitura di declassificazione) e accetta tratti a scarto costante quando nella scansione mancano pagine (rapporto CIA del 1971: posizione 21 = p. 10, 31 = p. 21, 41 = p. 32, verificate sull'OCR); `classifica.frase_chiave` non comprende più i marcatori di pagina («1 | pdf 1]] 中苏…» in testa a una citazione) e `normalizza` li ignora; `esplora` conta anche le `menzioni` (prima solo le righe: 苏联 121 righe, 238 menzioni); sommario dei quotidiani cinesi («今日要目» con più «第N版»: nessun passaggio delle ricerche già fatte cambia); `importa.strato_corrotto` riconosce lo strato di testo illeggibile dalle scritture estranee alla lingua della serie (tutte le pagine del Renmin Ribao 1961, nessuna del volume del 1966): le pagine vanno all'OCR o restano fuori con un avviso. `SKILL.md`: gruppi e categorie (leggere le fonti per trovare le forme, comprese le grafie d'epoca), strato illeggibile, date al mese, niente script sostitutivi del motore. Test: `test_confronti_chat.py` (14).
- Ordine delle colonne (26/10): `pipeline\colonne.py` rimette i blocchi dello strato di testo nell'ordine di lettura (XY-cut: tagli lungo le strisce bianche che nessun blocco attraversa, orizzontali o verticali secondo la più larga; le parti che non si tagliano dall'alto in basso se i blocchi sono impilati, altrimenti nell'ordine del file). `importa.testo_pagina` lo usa per i periodici, o secondo il campo `ordine_lettura` (colonne | pdf) del profilo di serie. Sulla prima pagina del Renmin Ribao del 1° gennaio 1961 (geometria dei blocchi, testo decodificato con la regola della chat) l'articolo principale si legge ora per intero (colonne 1-3, firme) prima del telegramma al Sudan; nelle zone con articoli incastrati a «L» (metà bassa della p. 4) vale l'ordine del file. L'OCR di Tesseract (psm 1 e 3) ordina già le colonne correttamente, ma a 300 dpi su quella stampa legge circa 6.000 caratteri della prima pagina. Test: `test_colonne.py` (6).
- Skill unica (26/10, fase B di `roadmap_skill.md`): fonte in `skills\ricerca-fonti` (`SKILL.md` senza nomi di provider, `config.ini`); `crea_skill_chat.py` prende da lì `SKILL.md` e `config.ini` e copia i moduli del motore al momento dello zip. `chat.py ambiente` dice dove si trova la skill: `sistema` (installazione completa trovata in `AIRCHIVIST_MOTORE` o nella cartella di lavoro e in quelle sopra: c'è `mcp_server.py`), `conversazione` (file caricati: chat di Claude in `/mnt/user-data/uploads` e `attachments`; ChatGPT in `/mnt/data`, posizione non documentata), `nessuna_fonte`; più lettore dei PDF (PyMuPDF, pypdf, nessuno), OCR e cartella di consegna (claude.ai `/mnt/user-data/outputs`, ChatGPT `/mnt/data/consegna`, altrove `consegna` nel progetto). Nel motore completo, senza `AIRCHIVIST_PROGETTO`, `chat.py` lavora sul progetto in uso con l'archivio unico (`prepara --cartella prova_...` per le prove) e rifiuta `apri`, `importa`, `serie-crea` e `consegna`; i progetti creati da `apri` hanno il segno `.progetto_chat` e restano senza archivio. `registra --da` predefinito: «assistente della chat». Provato sul progetto vero (Enrico Berlinguer, 1980, cartella di prova: 53 passaggi in 6 lotti). Test: `test_chat.py` (+4).
- Confezioni (26/10, fase C): `pipeline\confeziona.py` (sostituisce `crea_skill_chat.py`) scrive in `dist`: `ricerca-fonti-claude.zip` (claude.ai: cartella `ricerca-fonti/` alla radice), `claude-code\` (marketplace `airchivist` con il plugin `plugins\ricerca-fonti`: `.claude-plugin\plugin.json`, `plugin.json` portabile per ChatGPT, `skills\ricerca-fonti\` con il motore), `ricerca-fonti-chatgpt.zip` (lo stesso plugin, manifesti alla radice); ognuna con `LEGGIMI.md` (da `skills\leggimi`) e `LICENSE`. `claude plugin validate` passa sul marketplace e sul plugin (un solo avviso: manca l'icona) e Claude Code carica il plugin con la sua skill (circa 130 token sempre presenti, 3.100 quando parte). Tolte `skill_chat`, `.claude\skills\ricerca-fonti` e `crea_skill_chat.py`: in questa cartella la skill si usa installando il plugin. Le confezioni non sono ancora provate su claude.ai e su ChatGPT (fase D). Test: `test_chat.py` (confezioni, 3).
- Aperti: per un'entità molto frequente si cita solo la prima frase di ogni passaggio (297 menzioni, 60 citazioni); una decodifica generale dei font senza ToUnicode non c'è; qualità dell'OCR sulla stampa minuta del Renmin Ribao del 1961 da misurare.

Requisiti di sistema (da installare): Tesseract UB Mannheim con la lingua Albanian (sqi), PyMuPDF. Nessun modello OCR dentro la cartella del progetto.

- `indice.py`: aggiorna (incrementale), lingua reale dei file (`[LANG]`), filtro per lingua.
- `esplora.py`: trascrizioni albanesi ipotetiche e forme declinate (Grippa -> Gripa, Gripës), cercate solo nei testi albanesi e proposte solo se attestate.
- `sintesi.py`: frase dei «Limiti» per serie (`nota_limiti` in `serie.ini`); quella sulla stampa cinese solo per le fonti cinesi.

Provato solo su una scansione sintetica: mancano prove su scansioni vere e una prova dei modelli sulla lettura dell'albanese.

### Skill e plugin presso i provider: verifiche (fase 5, fase A di `roadmap_skill.md`, 26/10/2026)

Verifiche sulla documentazione ufficiale (fonti primarie, elenco in fondo alla sezione), lette il 26/10. Dove la documentazione tace è scritto.

**Claude, skill su claude.ai**
- Zip: la cartella della skill alla radice dello zip, con lo stesso nome della skill (`ricerca-fonti.zip` → `ricerca-fonti/SKILL.md`), non i file sciolti. Caricamento da Customize > Skills > «+» > Create skill > Upload a skill.
- Intestazione: `name` (max 64 caratteri, solo minuscole, cifre e trattini, senza «anthropic» né «claude») e `description` obbligatori. Il centro assistenza indica per `description` un massimo di **200 caratteri**, la documentazione per sviluppatori **1.024**; l'attuale `skill_chat/SKILL.md` ne ha 620 ed è stata caricata senza errori il 25/10. Campi accettati nel caricamento: `name`, `description`, `license`, `compatibility`, `metadata`, `allowed-tools`.
- Dimensione massima dello zip: non indicata («ZIP file exceeds size limits» tra le cause d'errore, senza il valore). File caricati nella conversazione: 30 MB per file; i PDF più grandi si elaborano nell'ambiente di calcolo senza entrare nel contesto.
- Piani: il centro assistenza indica Free, Pro, Max, Team ed Enterprise, con l'esecuzione del codice attiva; la pagina per sviluppatori dice ancora Pro, Max, Team ed Enterprise. Le skill caricate sono personali; su Team ed Enterprise si possono condividere o pubblicare nell'organizzazione.
- Rete: Free, Pro e Max con accesso attivo ai gestori di pacchetti (PyPI, npm, GitHub e pochi altri domini); Team ed Enterprise secondo le impostazioni dell'organizzazione (l'articolo è contraddittorio sul valore iniziale per Team). Claude può installare pacchetti da PyPI quando la rete lo consente.
- Pacchetti Python preinstallati su claude.ai: nessun elenco ufficiale. Per l'ambiente dell'API (strumento di esecuzione del codice) l'elenco c'è: Python 3.11, pypdf, pdfplumber, pypdfium2, pdf2image, pandas, ecc., sqlite; **PyMuPDF e Tesseract non ci sono**; nessuna rete, 5 GiB di RAM e di disco.
- Posizione dei file caricati (`/mnt/user-data/uploads`, `/mnt/user-data/attachments`): non documentata; nota solo dalle prove del 25-26/10.
- Le skill attive sull'account claude.ai si scaricano anche in Claude Code (v2.1.273 o successive, accesso con l'account claude.ai), in `~/.claude/skills/synced/`, in sola lettura.

**Claude Code**
- Posizioni: personale `~/.claude/skills/<nome>/SKILL.md` (tutti i progetti della macchina), di progetto `.claude/skills/<nome>/` (solo quella cartella o repository), aziendale, plugin `<plugin>/skills/<nome>/SKILL.md`. Precedenza: aziendale > personale > progetto; le skill dei plugin hanno lo spazio dei nomi (`/plugin:skill`) e convivono con le altre.
- Plugin: cartella con `.claude-plugin/plugin.json` e `skills/`; si installa da un marketplace (anche un repository GitHub con `.claude-plugin/marketplace.json`) o da una cartella (`--plugin-dir`). Conviene quando si vogliono installazione con un comando e aggiornamenti; per un uso personale basta la cartella in `~/.claude/skills/`.
- Rete e pacchetti: quelli del computer dell'utente; installazioni globali sconsigliate.

**ChatGPT, plugin**
- Un plugin può contenere **solo skill**, senza app né server MCP: la documentazione lo dice espressamente («Skills only»; «Some plugins include only skills»).
- Formato portabile: `plugin.json` alla radice (schema Agent Plugins, `name` in minuscole e trattini, max 64 caratteri) e `skills/<nome>/SKILL.md`; impostazioni OpenAI in `extensions.com.openai`. Plugin Creator genera invece la disposizione di compatibilità `.codex-plugin/plugin.json`. OpenAI accetta anche i manifesti di Claude: un archivio con `.claude-plugin/plugin.json` (con `description` non vuota) e almeno `skills/<nome>/SKILL.md` si carica direttamente come plugin di sole skill e il portale lo converte. Le istruzioni che nominano Claude vanno rese neutre («the model»).
- Creazione: con `@plugin-creator` (in Work o in Codex) oppure a mano. Prova locale: marketplace personale `~/.agents/plugins/marketplace.json` nell'app desktop di ChatGPT.
- Distribuzione: (1) caricamento dello zip nella console d'amministrazione, solo per proprietari e amministratori di un'area di lavoro; (2) pubblicazione nell'area di lavoro, solo amministratori; (3) directory pubblica, condivisa da ChatGPT e Codex: zip caricato nel portale `platform.openai.com/plugins`, percorso «Skills only», con verifica dell'identità (individuale o aziendale) e revisione. Per le sole skill non servono casi di prova né video.
- Piani: la directory dei plugin è visibile su tutti i piani; installare e usare un plugin «dipende da piano, area di lavoro, ruolo, regione»; su Free e Go niente estensioni dei plugin. Le skill personali sono indicate per Business, Enterprise, Healthcare ed Edu. **Se un utente Plus possa installare un plugin pubblico di sole skill, o crearne uno personale con Plugin Creator, la documentazione non lo dice**: va provato su un account Plus.

**ChatGPT, skill**
- Stesso standard (agentskills.io): cartella con `SKILL.md`, `name` e `description` obbligatori, poi `scripts/`, `references/`, `assets/`; facoltativo `agents/openai.yaml` (presentazione, dipendenze MCP).
- Dove funzionano: le skill sciolte nell'app desktop di ChatGPT, in Codex CLI e nell'estensione per gli IDE; quelle dentro un plugin anche in Chat e Work, sul web, sul desktop e sul cellulare. Posizioni locali: `~/.agents/skills`, `.agents/skills` del repository.
- `/home/oai/skills`: non compare nella documentazione ufficiale (solo in Willison 2025).
- Esecuzione degli script nella chat: non documentata per le skill. L'analisi dei dati usa un notebook Jupyter con Python, **senza richieste alla rete**; nessun elenco dei pacchetti; posizione dei file caricati non documentata.
- File caricati: 512 MB per documento, 2 milioni di token per file di testo, 80 file ogni 3 ore (Free: 3 al giorno).

**Ripiego per ChatGPT**
- Il GPT personalizzato non è un ripiego: sui piani personali (Free, Go, Plus, Pro) **non si possono più creare GPT nuovi**, e i GPT personalizzati saranno ritirati l'**11 dicembre 2026** (per le aree Enterprise con proroga l'11 febbraio 2027), con migrazione verso i plugin.
- Resta, non verificato, un progetto di ChatGPT con istruzioni e file (Plus: fino a 25 file per progetto); che vi si possano eseguire gli script della skill non è documentato.

**Conseguenze per le fasi B e C**
- Una sola cartella con `.claude-plugin/plugin.json` e `skills/ricerca-fonti/` serve da plugin di Claude Code e, così com'è, da zip di sole skill per la directory di ChatGPT; un `plugin.json` portabile alla radice la rende installabile anche dal marketplace locale di ChatGPT. Lo zip per claude.ai resta a parte (cartella `ricerca-fonti/` alla radice).
- `SKILL.md` neutro rispetto al provider è richiesto da OpenAI per la pubblicazione, non solo una scelta di stile.
- `description` sotto i 1.024 caratteri; sotto i 200 se si vuole stare nel limite del centro assistenza di Claude.
- Nessun ambiente garantisce PyMuPDF né la rete: il ripiego su pypdf (`importa.carica_pymupdf`) è necessario; pypdf è preinstallato almeno nell'ambiente dell'API di Claude.
- Da provare nella fase D: piano Plus di ChatGPT (installazione e creazione di plugin, esecuzione degli script, posizione dei file caricati); limite reale di dimensione dello zip su claude.ai.

Fonti (lette il 26/10/2026; tutte primarie e ufficiali):
- Anthropic. "Agent Skills." *Claude Platform Docs*. https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview.
- Anthropic. "Code Execution Tool." *Claude Platform Docs*. https://platform.claude.com/docs/en/agents-and-tools/tool-use/code-execution-tool.
- Anthropic. "How to Create Custom Skills." *Claude Help Center*. https://support.claude.com/en/articles/12512198-creating-custom-skills.
- Anthropic. "Using Skills in Claude." *Claude Help Center*. https://support.claude.com/en/articles/12512180-using-skills-in-claude.
- Anthropic. "Create and Edit Files with Claude." *Claude Help Center*. https://support.claude.com/en/articles/12111783-create-and-edit-files-with-claude.
- Anthropic. "Extend Claude with Skills." *Claude Code Docs*. https://code.claude.com/docs/en/skills.
- Anthropic. "Plugins." *Claude Code Docs*. https://code.claude.com/docs/en/plugins/overview.
- OpenAI. "Skills in ChatGPT." *OpenAI Help Center*. https://help.openai.com/en/articles/20001066-skills-in-chatgpt.
- OpenAI. "Plugins in ChatGPT." *OpenAI Help Center*. https://help.openai.com/en/articles/20001256-plugins-in-chatgpt.
- OpenAI. "Troubleshooting Plugins and Apps in ChatGPT." *OpenAI Help Center*. https://help.openai.com/en/articles/20001497-troubleshooting-plugins-and-apps-in-chatgpt.
- OpenAI. "Custom GPT Retirement and Migration FAQ." *OpenAI Help Center*. https://help.openai.com/en/articles/20001519-custom-gpt-retirement-and-migration-faq.
- OpenAI. "Creating and Editing GPTs." *OpenAI Help Center*. https://help.openai.com/en/articles/8554397-creating-and-editing-gpts.
- OpenAI. "Data Analysis with ChatGPT." *OpenAI Help Center*. https://help.openai.com/en/articles/8437071-data-analysis-with-chatgpt.
- OpenAI. "Uploading Files and Audio to ChatGPT." *OpenAI Help Center*. https://help.openai.com/en/articles/8555545-uploading-files-and-audio-to-chatgpt.
- OpenAI. "Plugin Architecture"; "Build Skills"; "Package Your Plugin"; "Connect and Test Your Plugin"; "Upload and Submit Your Plugin"; "Submit Your Claude Code Plugin to OpenAI." *OpenAI Developers*. https://developers.openai.com/plugins/.
- OpenAI. "Agent Skills." *OpenAI Developers (Codex)*. https://developers.openai.com/codex/skills.

### Riorganizzazione della cartella (26/10/2026)

Istruzioni in `reorganization.md`. Nomi di cartelle e file in inglese; codice, moduli, funzioni, messaggi, campi delle schede, chiavi di `config.ini` e `project.ini` e file generati dentro le ricerche (`passaggi.jsonl`, `classificati.jsonl`, `risposta.md`...) restano in italiano fino alla traduzione del codice. Nelle sezioni precedenti, datate, i percorsi sono quelli dell'epoca: vale la mappa qui sotto.

Struttura: il repository contiene il motore (`scripts\`, con `config.ini` e `series_template.ini`), i test (`tests\`, progetto di prova `tests\test_project\`), la skill (`skills\source-search\`, `skills\readme\`, `skills\package.py`, che scrive in `skills\build\`), `docs\`, `README.md`, `README.it.md`. I progetti di ricerca stanno in `projects\` (fuori da git); questo è `projects\dissident_communism\`, scelto in `scripts\config.ini` (`[progetto] cartella = ../projects/dissident_communism`).

| Prima | Dopo |
|---|---|
| `pipeline\*.py`, `config.ini`, `serie_modello.ini` | `scripts\*.py`, `config.ini`, `series_template.ini` |
| `pipeline\test\`, `pipeline\test\progetto_prova\` | `tests\`, `tests\test_project\` (`project.ini`, `glossary\`) |
| `pipeline\ISTRUZIONI.md`, `LEGGIMI.md` | `docs\user_guide.it.md`, `README.it.md` |
| `pipeline\confeziona.py`, `dist\` | `skills\package.py`, `skills\build\` |
| `skills\ricerca-fonti\`, `skills\leggimi\` | `skills\source-search\` (`name: source-search`), `skills\readme\`; nelle confezioni `README.md` al posto di `LEGGIMI.md` e il motore in `scripts\` al posto di `motore\` |
| `progetto.ini` | `project.ini` |
| `entita.ini`, `serie.ini`, `istruzioni.md` | `glossary\entities.ini`, `glossary\series.ini`, `glossary\instructions.md` |
| — | `sources\` (originali caricati; vuota per il corpus attuale) |
| `data\` | `data\` |
| `audit_fonti\registro_modifiche.csv`, `problemi_residui.csv` | `audit\changes.csv`, `audit\open_issues.csv` |
| `importazioni\controllo_*.csv`, `registro.csv`, `_cache\` | `audit\checks\`, `audit\imports.csv`, `system\cache\imports\` |
| importazioni avviate dalla chat (`importazioni\lavori\`) | `system\import_jobs\` |
| `indice\fonti.sqlite` | `system\index\sources.sqlite` |
| `lavori\`, `pipeline\_backup\` | `system\jobs\`, `system\backups\` |
| `risultati\_archivio\letture.jsonl`, `equivalenze.json`, `varianti_scartate.json` | `results\archive\readings.jsonl`, `equivalences.json`, `rejected_variants.json` |
| `risultati\<ricerca>\` | `results\searches\<ricerca>\` |
| `risultati\_riferimenti\`, `_sessioni_precedenti\`, `_prove\`, `_valutazione\` | `results\references\`, `past_sessions\`, `trials\`, `evaluation\` |
| `risposte\` | `results\answers\` |

- Codice: `progetto.py` ha le posizioni nuove (chiavi nuove: `originali`, `registro_importazioni`, `lavori_importazioni`, `cache`; `cartella_ricerche()` per `results\searches`); `progetto.py nuovo` crea la struttura nuova. Tolta la disposizione storica: senza progetto scelto valgono solo i percorsi scritti in `[percorsi]` e per gli altri il motore lo dice e indica `progetto.py nuovo`. `archivio.py` cerca le letture in `results\searches`, `references` e `past_sessions`. `chat.py` accetta i file di progetto caricati con i nomi nuovi e con quelli di prima.
- Le intestazioni del corpus che citano `audit_fonti/registro_modifiche.csv` (917 file) non sono state riscritte: la corrispondenza è in `audit\README.md` del progetto.
- `project.ini` non tiene più `backup = pipeline/_backup`. Configurazione di Jan (`%APPDATA%\Jan\data\mcp_config.json`): server «Pipeline» su `scripts\mcp_server.py` (copia precedente in `system\backups\2026-10-26_riorganizzazione\`). Claude Desktop non ha una configurazione su questo PC. `AIRCHIVIST_PROGETTO` non è impostata nelle variabili d'utente né di sistema.
- Copia di sicurezza prima dello spostamento: `system\backups\2026-10-26_riorganizzazione\` (archivio, schede, serie, `progetto.ini`, `istruzioni.md`, `audit_fonti`, `importazioni`).

Verifiche (26/10):
1. Test: 212, tutti superati; con PyMuPDF bloccato 212, 14 saltati in modo esplicito, nessun errore.
2. `progetto.py stato`: tutti i percorsi nella struttura nuova; `audit\imports.csv` nasce alla prima importazione.
3. `installa.py controlla`: requisiti necessari presenti.
4. Indice: 0 file nuovi, 0 modificati, 0 tolti; firma allineata alle fonti, nessuna ricostruzione.
5. Archivio: 14.320 letture prima e dopo; `archivio.py stato` identico salvo il percorso del file.
6. `ricerca.py "Jacques Grippa" --solo-estrazione`: 166 passaggi, `passaggi.jsonl` identico byte per byte a quello di prima. Ricerca completa su Franz Strobl (21 passaggi, tutti nell'archivio), con il codice di prima e con quello nuovo su due copie del progetto e senza modelli (sintesi `--senza-modello`): `passaggi.jsonl`, `classificati.jsonl` e `rapporto.md` identici; `risposta.md` identica salvo il percorso di `open_issues.csv` nei «Limiti».
7. Server MCP avviato in stdio sul progetto nuovo: 13 strumenti; `schede`, `passaggi_archivio`, `risposte`, `serie` rispondono. Domanda di prova in Jan: da fare.
8. `skills\package.py`: `source-search-claude.zip`, `claude-code\`, `source-search-chatgpt.zip` in `skills\build\`.

### Ambiente (verificato il 22/10/2026)

- Windows 11 Home; Python 3.14.6 (`C:\Python314\python.exe`).
- Librerie: il codice usa la libreria standard più PyMuPDF (1.28.0, MuPDF 1.29.0), solo in `importa.py`. SQLite 3.50.4 con FTS5 funzionante.
- Tesseract 5.5.3 in `C:\Program Files\Tesseract-OCR` (non nel PATH: `importa.py` lo trova nella cartella consueta). Lingue: deu, eng, fra, ita, ita_old, osd, rus, spa, sqi; al 25/10 anche chi_sim e chi_sim_vert (manca chi_tra).
- FreeLLMAPI: app desktop installata (`%LOCALAPPDATA%\Programs\freellmapi-desktop`), chiave `FREELLMAPI_KEY` presente nelle variabili d'utente. Al momento della verifica il servizio **non era avviato** (nessuna risposta su 127.0.0.1:31415): le ricerche richiedono di aprire prima l'app.
- Controllo di versione: git attivo dal 22/10/2026 (ramo `main`, `core.autocrlf = false` per conservare i fine riga). Esclusi, dal 26/10: `projects/` (corpus, schede, serie, risultati, indice, copie di sicurezza), `letteratura/`, `skills/build/`, `__pycache__/`.



## Metadati delle fonti

Correzioni del 22/10 (41 campi in `audit_fonti\registro_modifiche.csv`, 15 righe tolte da `problemi_residui.csv`; copie precedenti in `pipeline\_backup\2026-10-22_metadati`):
- RF1981-23 e RF1981-24: fascicoli del 1° e 16 dicembre 1981 (note di provenienza degli articoli «No 23, 1 Dec 81» e «No 24, 16 Dec 81»; rapporti JPRS di gennaio e marzo 1982; il n. 24 contiene l'indice dei nn. 13-24 del 1981); il frontespizio JPRS stampa per errore «1982». Corretti DOC_ID, YEAR, DATE, DATE_ORIGINAL, FULL_CITATION; aggiunto il campo `[DATE_NOTE]`.
- RF1985-11: YEAR e DOC_ID (1198 -> 1985); REPORT_DATE 1985-07-29 dal frontespizio.
- DOC_ID distinti per supplementi e indici: HONGQI-1964-S01, HONGQI-1965-S01, PR1973-41S, PR1973-46S, PR1974-15S, PR1978-26I, PR1979-26I; FULL_CITATION che indicano supplemento o indice. PR1973-46Supplement e PR1979-26-IndexSupplement: data verificata sul testo.
- PR1970-19X e PR1970-21X non sono doppioni ma numeri speciali (Special Issue dell'8 e del 23 maggio 1970): DOC_ID PR1970-SP0508 e PR1970-SP0523, citazione «special issue».

Nel corpus non restano DOC_ID ripetuti né valori di YEAR anomali. Sempre il 22/10, dopo queste correzioni, Ivan ha corretto a mano altre date di Peking Review e alcune di Hongqi: `problemi_residui.csv` va riallineato.



## Da fare

Il piano dettagliato è in `docs/piano_di_lavoro.md`.

Metadati ancora aperti (`problemi_residui.csv`): PR1974-15s (supplemento senza data né numero nel testo; discorso di Teng Hsiao-ping all'ONU del 10/04/1974, pubblicato anche in PR1974-16); PR1978-26-Index (data non verificabile); date del fascicolo o del rapporto JPRS mancanti in vari Hongqi 1977-1988; numeri mancanti; Renmin Ribao con giorni mancanti o numeri brevi.

Rimandati: verificare a mano il primo insieme di riferimento con `valutazione.py`; PCd'I (m-l): controllare 23 passaggi pertinenti per regola sotto il nome vecchio e già letti sotto la scheda attuale con decisione diversa (22 «no», 1 «incerto»; esito `decisioni_diverse` nel piano `riattribuzione_PCd_I_m_l_Italia_20261024.csv`, dove compaiono anche 3 sommari o duplicati della Peking Review esclusi in sessione).

Il 24/10 la scheda PCd'I (m-l) ha ricevuto le forme «Communist Party of Italy (M-L)», «Italian Communist Party (M-L)» (tolte da «Altre organizzazioni m-l italiane», per non averle in due schede) e 意大利共产党（马列主义）. I 9 passaggi del nome vecchio con queste forme risultano già letti sotto la scheda: 6 pertinenti, 3 esclusi come sommari o duplicati.

### Verso un tool modulare e pubblicabile (obiettivo finale)

Parti oggi legate a questa ricerca, da separare dal motore:
- dati di progetto: `entita.ini`, `serie.ini`, glossario, letture di riferimento, istruzioni della chat (ora in `mcp_server.py`, scritte per stampa cinese) -> una cartella per progetto, scelta in `config.ini`;
- regole specifiche delle fonti: pagine 第N版 del Renmin Ribao, abbreviazioni delle serie (`SERIE_BREVE`), allineamento Peking Review -> Renmin Ribao, nomi dei partiti generici in `classifica.forma_sicura`, frasi fisse dei «Limiti» -> moduli per tipo di fonte, attivabili;
- percorsi Windows e istruzioni d'installazione in italiano -> documentazione anche in inglese, licenza, file dei requisiti, test automatici, esempi con fonti libere da diritti.

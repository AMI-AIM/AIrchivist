# Stato del sistema

Copia del documento «Stato del sistema» del progetto «Archivio interattivo» (versione del 22/10/2026).



## Obiettivo

Costruzione di un tool scientifico-storiografico volto a trovare tutte le occorrenze di una persona o un ente (Stato, partito, testata giornalistica…) all'interno di un largo corpus di fonti documentarie primarie e rispondere con i passaggi originali, la loro traduzione e il riferimento preciso. L'obiettivo finale è pubblicare un tool modulare, adattabile a documenti relativi argomenti differenti. Questa pubblicazione potrà avere forme variabili, a seconda delle opportunità (Server MCP, Plugin per LLM, Applicazione proprietaria…).



## Tentativi precedenti

Il progetto è partito con il tentativo di costruire un sistema RAG locale, ma questo si è rivelato presto lento, pesante ed inefficace, in quanto il sistema si limitava a rispondere con i primi due o tre riferimenti alle fonti, invece di compiere una ricerca esaustiva delle occorrenze. Successivamente è stato utilizzato un GPT personalizzato, tramite ChatGPT, nel cui contesto sono stati caricati i documenti indagati. Il risultato, grazie ad un prompt preciso, è stato migliore ma non abbastanza. Il risultato migliore è stato raggiunto trasformando il progetto in una skill Claude /ricerca-occorrenze-fonti, tuttavia voglio rendere questo progetto gratuito ed autonomo da abbonamenti. La soluzione scelta è stata combinare una pipeline locale programmata in Python a dei modelli LLM in cloud, forniti da chiavi API gratuite.



## Situazione attuale

Il tool è attualmente adattato alla mia ricerca sul "marxismo-leninismo globale", tendenza comunista emersa negli anni Sessanta del Novecento e collegata alla Cina maoista e l'Albania enverista.

Il corpus documentario è contenuto nella cartella `data`, ed è così suddiviso:
- `riviste\renmin_ribao` (testo digitale, un paragrafo per riga; pagine 第N版 rilevate), `riviste\peking_review`, `riviste\hongqi_1963-1976` (cinese), `riviste\hongqi_1977-1988` (traduzioni JPRS);
- `fonti_primarie\` (raccolte di documenti: 中共中央文件选集, 文化大革命 ecc., K.H. Fan 1968);
- `opere\` (Selected Works, voll. 1-5).

In tutto 7858 file .txt (6712 cinesi, 1146 in lingue occidentali). Ogni file ha un'intestazione `[SERIES]`, `[DATE]`, `[FULL_CITATION]`, `[LANG]`, `[YEAR]`, `[DATE_STATUS]`... letta da `estrai_occorrenze.leggi_intestazione`.

`audit_fonti\` contiene `registro_modifiche.csv` (correzioni ai metadati, citato nelle intestazioni) e `problemi_residui.csv` (lacune e problemi aperti).



## Struttura tecnica

Il tool si usa attualmente dalla chat del programma Jan (assistente «Ricerca fonti», modello `auto:chat`), che raggiunge la pipeline attraverso il server MCP «Pipeline». I modelli sono gratuiti, forniti da FreeLLMAPI (sul PC, http://127.0.0.1:31415/v1).

### Come funziona una ricerca

- Scheda dell'entità in `pipeline\entita.ini` (varianti, contesto, forme ambigue, collegate); fa anche da glossario. Entità nuove: `esplora_nome` propone solo forme attestate (anche per allineamento Peking Review -> Renmin Ribao), poi `crea_scheda` dopo conferma.
- `avvia_ricerca` lancia un processo indipendente (`lavori.py`; stato in `RAG\lavori\<id>`): estrazione con espressioni regolari tolleranti all'OCR (`estrai_occorrenze.py`), smistamento e analisi con i modelli (`classifica.py`), sintesi (`sintesi.py` / `evoluzione.py`). Attese automatiche quando finiscono le quote (10, 15, 30, poi 60 minuti, fino a 36 ore). Codici d'uscita di classifica: 0 tutto letto, 3 limiti temporanei, 4 errore permanente.
- Archivio unico dei passaggi già letti (`risultati\_archivio\letture.jsonl`): non si rilegge nulla.
- La risposta salvata in `risposte\` ha 7 sezioni; Jan presenta «risposta_pronta» (presentazione della pipeline) senza ricostruirla.
- Indice SQLite FTS5 (`indice\fonti.sqlite`, circa 870 MB): serve a `esplora_nome`, `cerca_testo` e a scegliere i file del Renmin Ribao da leggere. Si aggiorna da solo (solo file nuovi o modificati).

### Provenienza, citazioni, valutazione (fase 1, 22/10/2026)

- **Provenienza delle letture** (`archivio.py`): ogni lettura dichiara chi ha deciso la pertinenza e chi ha tradotto, su tre livelli (modello e quale, sessione assistita, regola e quale). Registrata il 22/10 in tutte le 10.840 letture dell'archivio e nelle cartelle dei risultati (copie precedenti in `pipeline\_backup\2026-10-22_provenienza`). Decisioni: 9.461 per regola (7.362 classificazioni per regola in sessione, 1.980 esclusioni in blocco, 64 forme inequivocabili, 55 riprese da letture per regola), 1.295 in sessione, 84 da un modello. Traduzioni: 9.500 passaggi non tradotti, 1.152 in sessione, 180 da un modello, 8 voci di sommario.
- **Citazioni** (`citazioni.py`, campo `chicago` di `serie.ini`): stile Chicago, fino alla pagina (marcatore `[[p. N]]` o `pagina_regex`, oggi solo 第N版 del Renmin Ribao). Nelle risposte non compaiono più file e righe, che passano alla sezione 8. Le `FULL_CITATION` del corpus restano quelle di prima: le risposte non le usano più.
- **Test automatici** in `pipeline\test` (126): estrazione, citazioni, provenienza, riallineamento dei passaggi, date interne, esportazioni PAGE/ALTO, prova OCR, scelta tra strato del PDF e OCR, profili di serie, progetti di ricerca, server MCP, calcoli della valutazione.
- **Strumento di valutazione** (`valutazione.py`): campione alla cieca, candidati sfuggiti all'estrazione, misure con IC 95%. Nessun insieme verificato a mano esiste ancora. In una prova, la ricerca larga ha trovato 施特罗伯尔 (Franz Strobl, solo cognome) in una raccolta del 1976: è una forma assente dalla scheda.
- **Schede delle entità**: regole confermate in `docs\schede_entita.md`, controllo automatico `schede.py controlla`. Al 24/10: 91 schede, 0 errori, 75 avvisi, 153 informazioni. Tra gli avvisi: 42 schede senza note; 6 nomi che indicano gruppi o insiemi di forme; forme brevi non dichiarate in `forme_ambigue`.
- **Riattribuzione delle letture** (24/10): i nomi senza scheda sono dichiarati equivalenti (`risultati\_archivio\equivalenze.json`) e le loro letture copiate sotto le schede attuali con `archivio.py riattribuisci` (piani in `risultati\_archivio\riattribuzione_*_20261024.csv`, copia dell'archivio in `pipeline\_backup\2026-10-24_riattribuzione`). Aggiunte 560 letture: 319 PCB (da «PCB-Grippa (Belgio)»), 128 Dirigenti ORT/PTE/PT (Spagna), 107 KPD/ML (da «KPD/ML (Germania Ovest)» e «Communist party of Germany»), 6 PCd'I (m-l). Le 47 di «Partito Marxista-Leninista d'Austria» erano già lette sotto MLPÖ (Austria); le 26 di «PCB-Grippa» con il solo nome Grippa sono già lette sotto Jacques Grippa. Il piano riallinea le posizioni dei passaggi spostate dalle modifiche alle intestazioni (`archivio.riallinea`).

### Data interna dei documenti nelle raccolte (fase 2, lavoro 9, 24/10/2026)

- `date_interne.py`: per i file senza data completa che non sono periodici (raccolte, volumi) la data del documento che contiene il passaggio è l'ultima data d'intestazione che lo precede. Intestazioni forti: data sola sulla riga, tra parentesi a inizio o fine riga, data d'agenzia (新华社…讯/电). Deboli, valide solo se al giorno: tra parentesi in mezzo alla riga, a inizio riga seguita da virgola o da 《. Scartate: note (①…), date a fine frase, testatine senza giorno ripetute, elenchi fitti (indici), anni oltre l'edizione, intestazioni a più di 30.000 caratteri. Riconosce date cinesi (numerali e cifre, con errori OCR come 目 per 日) e date con i mesi in en, fr, it, es, de, sq. Stato sempre «dedotto». Profilo di serie: `data_interna`, `data_interna_anni`, `data_interna_distanza`.
- Uso: `estrai_occorrenze.py` registra `data_interna` in ogni passaggio delle raccolte e applica `--dal/--al` sulla data del documento, non sull'anno di edizione (prima le raccolte del 2012-2013 restavano fuori da ogni periodo storico). `cronologia.py` usa le date al giorno per estremi e silenzi, tutte per la presenza per anno, e conta ogni documento interno; i fatti dichiarano quante date sono dedotte. `sintesi.py` numera un documento per ogni documento interno, annota «documento del … (data dedotta dal testo)» fuori dalla citazione e non passa più al modello l'anno di edizione come data del documento. `evoluzione.py` raggruppa per anno del documento. Lo strumento MCP `passaggi_archivio` filtra per anno del documento e restituisce `data_documento`. I passaggi estratti prima del lavoro 9 ricevono la data al momento, dal file.
- Prova del 24/10 sui 282 passaggi delle raccolte nell'archivio: 270 con data (tutte al giorno). Campione di 25 verificato a mano: 21 corretti, 2 errati (data in una frase andata a capo; firma del documento precedente quando l'apertura del successivo è solo al mese), 2 dubbi (intestazione a oltre 25.000 caratteri). Senza data: Selected Works (anni stampati con cifre illeggibili, es. «August!(#&») e *The Chinese Cultural Revolution - Selected Documents*.

### Profili di serie (fase 3, lavoro 12, 25/10/2026)

Le regole che il codice scriveva per le serie del corpus attuale stanno ora nei profili di `pipeline\serie.ini`, letti da `pipeline\profili.py`. Un file appartiene a un profilo per serie o per cartella (la più specifica).
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
- Questo progetto: `config.ini` sceglie `cartella = ..`; `progetto.ini` nella radice («Comunismo dissidente tra Pechino e Tirana») tiene `entita.ini`, `serie.ini` e `_backup` in `pipeline`. Nessun file del corpus spostato; percorsi risolti identici a prima.
- Prova completa su un progetto nuovo nello scratchpad (variabile d'ambiente): creazione, serie aggiunta, importazione di un'esportazione PAGE/ALTO, indice, `cerca_testo` dal server MCP, scheda creata ed estrazione delle occorrenze; nel progetto vero nessun file toccato. 5 test nuovi.

### Server MCP generico (fase 4, lavoro 14, 25/10/2026)

Strumenti (13; con `azione` quelli che uniscono più operazioni): guida, schede (elenca, crea), esplora_nome, cerca_testo, ricerca (avvia, attendi, ferma), risposte (elenca, leggi), passaggi_archivio, copertura_fonti, apri_fonte, varianti (elenca, aggiungi, scarta), correggi_passaggio, importa (avvia, stato), serie (elenca, crea). I 18 nomi di prima (elenca_entita, crea_scheda, avvia_ricerca, attendi_ricerca, ferma_ricerca, leggi_risposta, elenca_risposte, importa_fonti, stato_importazione, elenca_serie, crea_serie...) restano accettati come alias, non elencati.
- Istruzioni non più scritte nel server per questo corpus e per Jan: `pipeline\istruzioni.py` le compone da regole generali del motore, elenco delle fonti dai profili di serie (con nome e descrizione del progetto) e `istruzioni.md` del progetto (qui: argomento, carattere delle fonti, cariche cinesi, esempi di citazione, «mai la parola corpus»). Lingua delle risposte e attesa massima di `ricerca` in `[mcp]` di `config.ini` o `progetto.ini` (prima 75 s fissi, tarati su Jan). Consegna in tre modi: campo `instructions` di initialize, prompt MCP `istruzioni` (nuova capacità `prompts`), strumento `guida`; in Jan l'assistente può limitarsi a chiamare `guida`.
- `copertura_fonti` conta i periodici dai profili di serie (non più dalla sola cartella `data\riviste`) e registra anche i numeri mancanti; filtri per anno senza il limite 1940-1999; descrizioni degli strumenti senza esempi del corpus.
- Test: server avviato in stdio su un progetto nuovo (istruzioni senza nulla del corpus attuale né del client, 13 strumenti, prompt, alias, errori, guida).

### Modelli (FreeLLMAPI)

Profilo «ricerca» attivo, strategia custom (affidabilità 0,3, velocità 0,2, intelligenza 0,5). Catena «ricerca» 26 modelli, «chat» 17. Provati con la prova rapida (21 passaggi Nuova Unità, 21/10): Nemotron Ultra (NVIDIA) 21/21, GPT-OSS 120B (Ollama) 21/21, Gemma 4 31B (Ollama) 21/21, Nemotron 3 Super (Ollama) 15/15, Muse Glimmer 30B (NVIDIA) 15/15, Ministral 14B (Mistral) 20/21; scartato Nemotron 3.5 Lightning (0/15). Regola: stesso modello su un nuovo fornitore non va riprovato; modello nuovo -> prova rapida; `valuta.py` completo solo nei casi dubbi. Risultati in `risultati\_prove\prova_rapida_2026-10-21.md`. `config.ini`: max_token 4000 (sintesi 8000).

Prova rapida del 22/10 (`valutazione.py modelli`) sui 97 passaggi verificati a mano. La prima fase ha provato 50 modelli su 30 passaggi; 13 li hanno letti tutti, gli altri sono stati fermati da quote o errori del servizio. Seconda fase sui 97 passaggi (pertinenti riconosciuti; «sì» giusti):

| Modello | Pertinenti riconosciuti | «Sì» giusti |
|---|---|---|
| gpt-oss-20b | 66/70 | 65/69 |
| gemma-4-31b | 65/70 | 65/66 |
| gpt-oss-120b | 65/70 | 61/65 |
| nemotron-3-super | 64/70 | 61/68 |

`modelli_ammessi` contiene ora gpt-oss-20b, gemma-4-31b e gpt-oss-120b, sia nella forma con i due punti sia in quella con il trattino. La catena «ricerca» di FreeLLMAPI contiene però anche altri modelli: se risponde uno di questi, la lettura si ferma. La catena va quindi ridotta ai tre modelli ammessi. Il filtro vale anche per la sintesi, i cui modelli non sono ancora stati misurati.

### Importazione di nuove fonti

`pipeline\importa.py` + `pipeline\serie.ini` (schede delle serie: Zëri i Popullit, Rruga e Partisë). Testo del PDF se c'è, altrimenti OCR con Tesseract (TSV con confidenza); intestazione standard; registro in `importazioni\registro.csv`; cache delle pagine per riprendere; aggiornamento dell'indice. Comandi: prepara, serie, importa (--prova N, --data, --metadati csv, --unisci, --sovrascrivi), controlla.

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

Requisiti di sistema (da installare): Tesseract UB Mannheim con la lingua Albanian (sqi), PyMuPDF. Nessun modello OCR dentro la cartella del progetto.

- `indice.py`: aggiorna (incrementale), lingua reale dei file (`[LANG]`), filtro per lingua.
- `esplora.py`: trascrizioni albanesi ipotetiche e forme declinate (Grippa -> Gripa, Gripës), cercate solo nei testi albanesi e proposte solo se attestate.
- `sintesi.py`: frase dei «Limiti» per serie (`nota_limiti` in `serie.ini`); quella sulla stampa cinese solo per le fonti cinesi.

Provato solo su una scansione sintetica: mancano prove su scansioni vere e una prova dei modelli sulla lettura dell'albanese.

### Ambiente (verificato il 22/10/2026)

- Windows 11 Home; Python 3.14.6 (`C:\Python314\python.exe`).
- Librerie: il codice usa la libreria standard più PyMuPDF (1.28.0, MuPDF 1.29.0), solo in `importa.py`. SQLite 3.50.4 con FTS5 funzionante.
- Tesseract 5.5.3 in `C:\Program Files\Tesseract-OCR` (non nel PATH: `importa.py` lo trova nella cartella consueta). Lingue: deu, eng, fra, ita, ita_old, osd, rus, spa, sqi. **Mancano chi_sim e chi_tra**: oggi non è possibile l'OCR del cinese con Tesseract.
- FreeLLMAPI: app desktop installata (`%LOCALAPPDATA%\Programs\freellmapi-desktop`), chiave `FREELLMAPI_KEY` presente nelle variabili d'utente. Al momento della verifica il servizio **non era avviato** (nessuna risposta su 127.0.0.1:31415): le ricerche richiedono di aprire prima l'app.
- Controllo di versione: git attivo dal 22/10/2026 (ramo `main`, `core.autocrlf = false` per conservare i fine riga). Esclusi: `data/`, `indice/`, `risultati/`, `risposte/`, `lavori/`, `importazioni/`, `pipeline/_backup/`.



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

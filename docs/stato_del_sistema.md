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

### Strumenti MCP (18)

elenca_entita, esplora_nome, crea_scheda, cerca_testo, avvia_ricerca, attendi_ricerca, ferma_ricerca, leggi_risposta, elenca_risposte, passaggi_archivio, copertura_fonti, apri_fonte, varianti, correggi_passaggio, importa_fonti, stato_importazione, elenca_serie, crea_serie.

### Modelli (FreeLLMAPI)

Profilo «ricerca» attivo, strategia custom (affidabilità 0,3, velocità 0,2, intelligenza 0,5). Catena «ricerca» 26 modelli, «chat» 17. Provati con la prova rapida (21 passaggi Nuova Unità, 21/10): Nemotron Ultra (NVIDIA) 21/21, GPT-OSS 120B (Ollama) 21/21, Gemma 4 31B (Ollama) 21/21, Nemotron 3 Super (Ollama) 15/15, Muse Glimmer 30B (NVIDIA) 15/15, Ministral 14B (Mistral) 20/21; scartato Nemotron 3.5 Lightning (0/15). Regola: stesso modello su un nuovo fornitore non va riprovato; modello nuovo -> prova rapida; `valuta.py` completo solo nei casi dubbi. Risultati in `risultati\_prove\prova_rapida_2026-10-21.md`. `config.ini`: max_token 4000 (sintesi 8000).

### Importazione di nuove fonti

`pipeline\importa.py` + `pipeline\serie.ini` (schede delle serie: Zëri i Popullit, Rruga e Partisë). Testo del PDF se c'è, altrimenti OCR con Tesseract (TSV con confidenza); intestazione standard; registro in `importazioni\registro.csv`; cache delle pagine per riprendere; aggiornamento dell'indice. Comandi: prepara, serie, importa (--prova N, --data, --metadati csv, --unisci, --sovrascrivi), controlla.

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

Rimandati: separare la scheda PCMLB (Vanderlinden) da PCB (m-l) «L'Exploité» (Trifaux); test automatici; un insieme di riferimento di 80-100 passaggi verificati a mano.

### Verso un tool modulare e pubblicabile (obiettivo finale)

Parti oggi legate a questa ricerca, da separare dal motore:
- dati di progetto: `entita.ini`, `serie.ini`, glossario, letture di riferimento, istruzioni della chat (ora in `mcp_server.py`, scritte per stampa cinese) -> una cartella per progetto, scelta in `config.ini`;
- regole specifiche delle fonti: pagine 第N版 del Renmin Ribao, abbreviazioni delle serie (`SERIE_BREVE`), allineamento Peking Review -> Renmin Ribao, nomi dei partiti generici in `classifica.forma_sicura`, frasi fisse dei «Limiti» -> moduli per tipo di fonte, attivabili;
- percorsi Windows e istruzioni d'installazione in italiano -> documentazione anche in inglese, licenza, file dei requisiti, test automatici, esempi con fonti libere da diritti.

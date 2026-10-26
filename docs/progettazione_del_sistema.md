# Progettazione del sistema

Documento di progettazione della versione generalizzata del tool (22/10/2026). Raccoglie le decisioni prese e le questioni aperte. Lo stato del sistema attuale è in «Stato del sistema».



## 1. Scopo e posizionamento

Un ricercatore porta nel sistema un corpus (PDF, Word, TXT, oppure trascrizioni già fatte con altri strumenti). Il sistema lo trasforma in file di testo standardizzati, con metadati bibliografici e archivistici in testa e pagine segnate. Su questo corpus si svolgono poi le indagini: la prima è la ricerca esaustiva delle occorrenze di una persona o di un ente, con passaggi originali, traduzione e riferimento.

Il tool si usa in proprio, dal proprio computer, collegandolo all'IA che il ricercatore già usa.

**Contributo specifico.** La ricerca esaustiva e verificabile: esaustività dichiarata, tolleranza agli errori dell'OCR, citazioni testuali verificate, copertura e lacune esplicite, multilinguismo (cinese, lingue occidentali, albanese), costo zero, indipendenza dal modello. È anche uno strumento di critica della fonte digitale, tema discusso nella storiografia sulla ricerca per parole chiave nelle fonti digitalizzate.

**Ciò che non si rifà.** L'acquisizione «universale» (OCR e trascrizione di qualsiasi materiale) è già coperta da strumenti consolidati come Transkribus ed eScriptorium. Il sistema li integra invece di sostituirli, e mantiene un OCR proprio, gratuito e locale, come motore predefinito.

**Strategia.**
- Il «corpus qualsiasi» resta un principio di progettazione, non un obiettivo immediato: il sistema si costruisce sui casi di prova (sezione 11).
- Il contributo si pubblica come metodo con misure (richiamo e precisione su un insieme di riferimento verificato a mano), con il software come materiale aperto.
- Prima di generalizzare, verifica del bisogno presso 5-10 ricercatori di ambiti vicini (stampa comunista, Guerra fredda, storia transnazionale).

Riferimenti per il posizionamento (fonti secondarie):
- Denbo, Seth. “Googling History: The AHR Explores Implications of Using Digital Sources for Historians.” *Perspectives on History*, May 16, 2016. https://www.historians.org/perspectives-article/googling-history-the-ahr-explores-implications-of-using-digital-sources-for-historians-may-2016/. Riassume Putnam, Lara. “The Transnational and the Text-Searchable.” *American Historical Review*, 2016 (non consultato direttamente).
- Hufe, Lorenz, Niclas Griesshaber, Gavin Greif, Sebastian Oliver Eck, and Philip Torr. “Towards the AI Historian: Agentic Information Extraction from Primary Sources.” arXiv, 2026. https://arxiv.org/html/2604.03553v1. Sistema Chronos: estrazione di dati strutturati, non ricerca di entità; nessuna misura di accuratezza riportata.
- “How Do We Talk about LLMs?” *Active History*, September 9, 2026. https://activehistory.ca/blog/2026/09/09/how-do-we-talk-about-llms/. Testimonianza della divisione della professione sull'IA.



## 2. Decisioni prese

| Tema | Decisione |
|---|---|
| Originale | Il file caricato è immutabile. Il .txt è un derivato («edizione di lavoro») che dichiara la propria provenienza. |
| Livello di citazione | Il contenitore: fascicolo, numero, rapporto, volume, busta. Un file .txt per contenitore. |
| Oggetto citato | Si cita l'oggetto effettivamente consultato, con le sue pagine. Traduzioni, riproduzioni e ristampe citano l'originale come informazione aggiuntiva, senza pagine proprie. |
| Riferimento interno | La pagina stampata dell'oggetto consultato. Se non c'è numerazione stampata, la citazione si ferma al contenitore. |
| Stile delle citazioni | Chicago standard (note e bibliografia). |
| Pagine nel testo | Marcatore in linea, su una riga propria. |
| Metadati | Solo nell'intestazione del file, che è l'unica fonte. Il registro delle modifiche resta il giornale delle correzioni. |
| Stato dei metadati | Ogni campo dichiara se è verificato, dedotto o da verificare. Un campo dedotto non si presenta mai come certo. |
| Date | Data del contenitore, per citare. Data interna del documento o dell'evento, dedotta accanto al passaggio, per analizzare. |
| Regole delle fonti | Dichiarate in profili di serie, non scritte nel codice. |
| Revisione umana | Obbligatoria prima dell'ingresso nel corpus: proposte in tabella, conferme in blocco, segnalazione dei casi dubbi. |
| Utente | Il ricercatore in proprio, sul proprio computer. |
| Collegamento alle IA | Server MCP come adattatore di un motore indipendente. |
| Motori di testo | Intercambiabili: OCR proprio (predefinito), importazione da Transkribus, eScriptorium e altri strumenti (PAGE XML, ALTO XML), API di servizi esterni come modulo facoltativo. |
| Sviluppo | Codice e prove in Claude Code, nella cartella RAG; progettazione e ricerca nel progetto «Archivio interattivo». |
| Schede delle entità | Una scheda per soggetto storico (persona, organizzazione, testata): si uniscono i nomi diversi dello stesso soggetto, si separano scissioni, rifondazioni e omonimi. Dirigenti e organi di stampa hanno schede proprie, legate con `collegate`. Le forme brevi, i cognomi soli, i nomi generici e le forme condivise vanno in `forme_ambigue`. Gli enti indicati da sigle hanno `forma_estesa`. Regole complete in `docs/schede_entita.md`. |



## 3. Architettura

```
          IA del ricercatore (Claude Desktop, Gemini CLI, Jan, Cursor, VS Code, ...)
                                   |
                         adattatore MCP (locale)
                                   |
  ---------------------------- MOTORE (Python) ----------------------------
  ingresso -> motore di testo -> formato interno -> pagine -> metadati proposti
           -> revisione -> corpus -> indice -> moduli d'indagine
                                                     |
                                     lettore configurabile (modelli)
```

**Motore.** Libreria Python con comandi da terminale. Funziona per intero senza chat: è la garanzia che il tool sopravviva ai cambi di piattaforma.

**Adattatore MCP.** Espone gli strumenti del motore a qualsiasi client compatibile. Contiene le istruzioni di comportamento per l'IA della chat: non inventare, dichiarare i limiti, presentare la risposta della pipeline senza ricostruirla. Così il comportamento non dipende dal client.
- **Modalità locale (predefinita):** il corpus non esce dal computer.
- **Modalità remota (facoltativa):** necessaria solo per i client che non accettano server locali, come ChatGPT. Espone il corpus su internet, quindi resta una scelta esplicita dell'utente, con le avvertenze sui diritti delle fonti.

**Lettore.** La lettura dei passaggi (smistamento, traduzione, analisi) resta nel motore, tramite un'interfaccia compatibile OpenAI: FreeLLMAPI, Ollama, Groq o servizi a pagamento. L'IA della chat orchestra e presenta, non legge: l'esaustività e la riproducibilità non possono dipendere dal modello della conversazione. Il tool deve funzionare anche con un modello locale, perché i servizi gratuiti cambiano spesso.

**Revisione in foglio di calcolo.** Il motore esporta le intestazioni proposte in una tabella (CSV/XLSX), con lo stato di ogni campo e i casi dubbi in evidenza. Il ricercatore corregge in Excel o LibreOffice; il motore riapplica la tabella alle intestazioni e registra le modifiche nel giornale. L'interfaccia grafica propria è rimandata.

Supporto dei client a MCP, verificato il 22/10/2026 su fonti secondarie non ufficiali, da confermare sulla documentazione dei client:
- ContextBolt. “AI Tools That Support MCP.” Updated October 20, 2026. https://contextbolt.com/blog/ai-tools-mcp-support/.
- zehranur. “How Claude, ChatGPT and Gemini Each Built MCP Differently.” *DEV Community*, July 2026. https://dev.to/zehranur/how-claude-chatgpt-and-gemini-each-built-mcp-differently-3kd.



## 4. Motori di testo e vie d'ingresso

Ogni motore produce lo stesso **formato interno**: pagine nell'ordine del file, righe, confidenza se disponibile. Dal formato interno si genera il .txt standard. L'intestazione dichiara l'origine del testo (`TEXT_METHOD`, `OCR_ENGINE`); il motore di ricerca non dipende dal motore di testo.

**1. Importazione da file esportati (via principale, gratuita).**
- PAGE XML e ALTO XML: standard aperti, un file per pagina con testo e impaginazione. Un lettore per ciascuno dei due formati accoglie i lavori fatti con Transkribus, eScriptorium e altri strumenti che li esportano (da verificare caso per caso).
- Transkribus: su tutti i piani, compreso quello gratuito, esporta PAGE XML, TXT, DOCX, PDF, immagini; ALTO XML, TEI e METS solo sui piani a pagamento (Scholar e superiori). Fonte primaria del produttore: Transkribus. “Downloading.” *Transkribus Help Center*. Accessed October 22, 2026. https://help.transkribus.org/downloading.
- eScriptorium (open source, basato su Kraken): esporta testo, PAGE XML e ALTO XML, con immagini e file METS. Documentazione ufficiale: eScriptorium. “Export Data from eScriptorium.” *eScriptorium Documentation*. Accessed October 22, 2026. https://escriptorium.readthedocs.io/en/latest/export/.
- I file METS, quando presenti, forniscono una prima proposta di metadati, con stato «dedotto».

**2. Collegamento via API (modulo facoltativo).**
- L'API di Transkribus richiede almeno il piano Scholar (a pagamento); un'immagine per lavoro; risultati in JSON, PAGE XML, ALTO XML; immagini e risultati cancellati dopo 48 ore. Fonte primaria del produttore: Transkribus. “metagrapho.” Accessed October 22, 2026. https://transkribus.org/en/metagrapho.
- Non è la via predefinita (non gratuita). Si attiva se l'utente ha già un abbonamento, anche tramite la propria istituzione. Lo stesso schema vale per altri servizi con API.

**3. OCR proprio (motore predefinito, gratuito e locale).**
- Tesseract per l'albanese e le lingue occidentali.
- Per il cinese, motore da scegliere dopo una prova sul corpus: PaddleOCR o Kraken. Da verificare se i modelli Kraken addestrati in eScriptorium si possano usare in locale.

**4. Testi nativi digitali.**
- PDF con strato di testo: si misura la qualità dello strato e lo si usa solo se non è peggiore di un nuovo OCR (molti PDF d'archivio hanno un vecchio OCR scadente). Fatto il 25/10/2026 in `importa.py`: confronto con un OCR rifatto su 3 pagine del corpo; strato tenuto se concorda entro il 2% dei caratteri o se l'OCR è poco sicuro (con avviso), altrimenti OCR di tutto il documento. Solo per le pagine scansionate: il testo nativo si usa com'è.
- Word e TXT: estrazione diretta; il campo `WITNESS` dichiara se si tratta di trascrizione, traduzione, edizione.

**Confronto tra motori.** Sugli stessi campioni il sistema misura quale motore funziona meglio per ciascuna serie e lo registra nel profilo di serie.

**Limiti.**
- Le confidenze non sono confrontabili tra motori: ognuno le calcola a modo suo. Si riportano come indicative, salvo ricalcolo uniforme sui campioni verificati.
- I file esportati danno l'ordine delle immagini, non la numerazione stampata: il rilevamento delle pagine (sezione 5, passo 4) vale per tutte le vie d'ingresso.



## 5. Flusso di acquisizione

1. **Ingresso.** Il file originale (o l'esportazione PAGE/ALTO con le immagini) viene copiato nell'archivio degli originali e registrato con la sua impronta (hash). Non viene mai modificato.
2. **Motore di testo.** Scelto secondo la via d'ingresso e il profilo di serie (sezione 4).
3. **Formato interno.** Pagine, righe, confidenza.
4. **Pagine.** Il sistema propone la corrispondenza tra pagina del file e pagina stampata (scarto di base più eccezioni: tavole, pagine non numerate, salti), leggendo i numeri in testa o a piè di pagina. Il ricercatore la conferma. Fatto per i PDF il 25/10/2026 (`numerazione.py`): indicazione dell'operatore (`--prima-pagina`/`--da-pagina`), poi etichette di pagina del PDF, poi numeri stampati con scarto costante (stato «dedotto», pagine senza numero annotate «dedotta»). Non ancora: eccezioni dentro lo stesso documento (più scarti, tavole fuori testo), e la stessa deduzione per le immagini e le esportazioni PAGE/ALTO che non dichiarano la pagina.
5. **Divisione dei contenitori.** Solo quando un file contiene più contenitori, come un'annata rilegata: il ricercatore indica gli intervalli di pagine una volta sola.
6. **Metadati proposti.** Dal profilo di serie, dal frontespizio, dalla sequenza dei numeri e delle date, dai file METS. Ogni campo arriva con il suo stato.
7. **Revisione** in tabella (sezione 3).
8. **Ingresso nel corpus.** Controllo delle intestazioni, aggiornamento dell'indice.



## 6. Formato del file .txt

### Intestazione

Una riga per campo, `[CAMPO: valore]`, come nel corpus attuale. Campi proposti:

**Identità e tipo**
- `DOC_ID`: identificativo unico nel corpus.
- `CONTAINER_TYPE`: fascicolo, supplemento, numero speciale, indice, rapporto, volume di raccolta, busta, documento singolo.
- `WITNESS`: natura del testimone (facsimile, trascrizione, traduzione, ristampa, edizione).

**Bibliografici**
- `SERIES`, `TITLE`, `AUTHOR`, `ISSUE`, `VOLUME`, `DATE`, `DATE_ORIGINAL`, `PLACE`, `PUBLISHER`, `LANG`.
- Per traduzioni e riproduzioni: `ORIGINAL_SERIES`, `ORIGINAL_ISSUE`, `ORIGINAL_DATE`, `TRANSLATOR`, `REPORT_ID`, `REPORT_DATE`.

**Archivistici**
- `REPOSITORY` (ente conservatore), `FONDS` (fondo), `ARCHIVE_SERIES`, `BOX` (busta), `FILE_UNIT` (fascicolo), `SHELFMARK` (segnatura), `DIGITIZATION` (provenienza della riproduzione: scansione propria, microfilm, MIA, CIA-FOIA...).

**Provenienza del testo**
- `SOURCE_FILE`, `SOURCE_HASH`, `TEXT_METHOD` (strato PDF, OCR proprio, importazione PAGE/ALTO, API, estrazione Word, trascrizione), `OCR_ENGINE` (con versione o piattaforma d'origine), `OCR_LANGS`, `OCR_CONFIDENCE` (indicativa), `PAGES` (intervallo delle pagine stampate presenti).

**Citazione**
- `FULL_CITATION`: generata in stile Chicago standard dal modello di citazione del profilo di serie, non scritta a mano.

**Stato dei campi**
- Per ogni campo che non è verificato: `<CAMPO>_STATUS` con valore `dedotto` o `da verificare`, più eventuale `<CAMPO>_NOTE`. Esempio: `[DATE_STATUS: dedotto]`, `[DATE_NOTE: dalla sequenza dei numeri]`. È la generalizzazione dell'attuale `DATE_STATUS`.
- Questione aperta: se l'assenza di `_STATUS` debba valere «verificato» (intestazioni più snelle) o «non dichiarato» (segnalato dal controllo). Proposta: «verificato» solo per i campi confermati durante la revisione, registrata nel giornale.

### Marcatore di pagina

Su una riga propria, prima del testo della pagina:

```
[[p. 12]]
[[p. s.n.]]          pagina non numerata
[[p. 12 | pdf 17]]   forma estesa, con la pagina del file originale
```

La sintassi esatta è da fissare, con due vincoli: non deve poter comparire nel testo delle fonti e non deve essere scambiata per un'intestazione.



## 7. Profili di serie

Estensione dell'attuale `series.ini` (prima `serie.ini`). Ogni profilo dichiara:
- lingua e scrittura, impaginazione (colonne, scrittura verticale);
- motore di testo preferito, scelto dopo il confronto sui campioni;
- periodicità e numerazione (per proporre numeri e date dalla sequenza);
- dove si trovano data e numero (testata, frontespizio, piè di pagina);
- come sono numerate le pagine;
- modello di citazione in stile Chicago standard;
- frase dei «Limiti» nelle risposte;
- regole specifiche attivabili (pagine 第N版 del Renmin Ribao, note di provenienza JPRS, allineamento tra serie).

Le regole oggi scritte nel codice vengono trasferite nei profili. Il motore resta generico. Fatto il 25/10/2026 (`profili.py`): tipo, periodo, periodicità, gruppo, pagine (`pagina_regex`), righe intere, allineamento tra serie, note dei «Limiti». Restano da definire nei profili: impaginazione (colonne, scrittura verticale), motore di testo preferito, posizione di data e numero.



## 8. Indagine

Moduli che lavorano sullo stesso corpus standardizzato:
- ricerca esaustiva delle occorrenze (quella attuale);
- concordanze e ricerca libera nel testo;
- cronologia delle menzioni, basata sulla data interna dove disponibile;
- co-occorrenze (chi compare con chi);
- confronto tra serie sullo stesso evento.

Ogni risposta riporta la copertura effettiva: fonti lette, lacune note, pagine con OCR di bassa qualità.

Ogni lettura conserva la propria provenienza, su tre livelli distinti: letto da un modello (quale), letto in una sessione assistita, deciso per regola. Le risposte la dichiarano correttamente.



## 9. Valutazione

- Insieme di riferimento di 80-100 passaggi verificati a mano, rappresentativo delle lingue e delle serie.
- Misure: richiamo dell'estrazione (occorrenze vere trovate), precisione e richiamo della classificazione per modello, qualità dei motori di testo per serie.
- Test automatici dell'estrazione su casi OCR reali (sillabazione, spazi tra caratteri cinesi, parole incollate).
- Le misure sono la base dell'articolo metodologico e della credibilità del tool.



## 10. Distribuzione

- Pacchetto installabile con un solo comando; requisiti (Tesseract o altro motore OCR, librerie) installati nel sistema, non nella cartella del progetto. Deciso il 25/10/2026: il motore non diventa un pacchetto pip (i moduli si importano per nome dalla cartella `pipeline` e `config.ini` deve restare accanto al codice, modificabile); si scarica con git o come archivio e `python pipeline/installa.py librerie` installa nel Python di sistema le librerie facoltative di `requirements.txt` (solo PyMuPDF: il motore usa la libreria standard, Python 3.10 o successivo). `installa.py controlla` verifica l'ambiente; `installa.py client` stampa la configurazione MCP per Jan, Claude Desktop, LM Studio o in forma generica, senza modificare i file dei client. Licenza: AGPL-3.0, perché copre anche l'uso come servizio in rete (server MCP).
- Un file di configurazione unico; una cartella per progetto di ricerca (corpus, profili, schede delle entità, glossario, risultati). Fatto il 25/10/2026 (`progetto.py`): config.ini del motore più project.ini (prima progetto.ini) del progetto scelto (config.ini o variabile d'ambiente AIRCHIVIST_PROGETTO); `progetto.py nuovo` crea un progetto vuoto.
- Istruzioni di collegamento per i client principali; documentazione in italiano e in inglese; licenza; test automatici; corpus d'esempio libero da diritti.



## 11. Casi di prova

- Il corpus cinese attuale, da far rientrare nel nuovo formato.
- Le fonti albanesi (Zëri i Popullit, Rruga e Partisë), primo vero caso di acquisizione da scansione.
- Un'esportazione PAGE XML o ALTO XML da Transkribus o eScriptorium, per provare la via d'importazione.

Se il formato regge tutti e tre, il disegno è verificato.



## 12. Questioni aperte

1. **Motore OCR per il cinese.** Tesseract è debole sul cinese a colonne o in verticale. Alternative gratuite da provare su un campione del corpus: PaddleOCR, Kraken.
2. **Sintassi definitiva del marcatore di pagina** e valore predefinito dei campi senza `_STATUS`.
3. **Migrazione del corpus attuale** nel nuovo formato. I rapporti JPRS non hanno pagine: vanno recuperate con un nuovo OCR dei PDF originali, se disponibili. Peking Review e Hongqi vanno verificati.
4. **Data interna per le raccolte di documenti** (中共中央文件选集 ecc.): decisa il 24/10/2026 (`date_interne.py`). È l'ultima data d'intestazione prima del passaggio: forte (sola sulla riga, tra parentesi a inizio o fine riga, data d'agenzia con 讯/电) a qualsiasi precisione, debole (tra parentesi in mezzo alla riga, a inizio riga con virgola) solo se precisa al giorno. Si scartano testatine, elenchi fitti, anni non plausibili e intestazioni a più di 30.000 caratteri. È sempre «dedotta»; nelle risposte annota il documento ma non entra nella citazione. Nella cronologia le date al giorno entrano in estremi e silenzi, quelle al mese o all'anno solo nella presenza per anno; ogni documento interno conta come un documento. Resta aperto: misurarne la precisione su un campione verificato a mano (strumento di valutazione).
5. **Elenco degli strumenti MCP** della versione generalizzata, ridotto e generico rispetto ai 18 attuali. Deciso il 25/10/2026: 13 strumenti (guida, schede, esplora_nome, cerca_testo, ricerca, risposte, passaggi_archivio, copertura_fonti, apri_fonte, varianti, correggi_passaggio, importa, serie), con `azione` dove uniscono più operazioni; istruzioni composte dal server (regole generali, fonti dai profili, istruzioni.md del progetto) e consegnate anche come prompt MCP e strumento `guida`. Resta da verificare con altri client (Claude Desktop, LM Studio, Open WebUI) se leggono il campo `instructions`.
6. **Formato del foglio di revisione** (colonne, stati, segnalazioni).
7. **Modelli Kraken di eScriptorium in locale**: compatibilità da verificare.
8. **Verifica del bisogno**: chi contattare e con quale dimostrazione.

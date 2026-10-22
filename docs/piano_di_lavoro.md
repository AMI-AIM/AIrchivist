# Piano di lavoro

Lavori in ordine di priorità (22/10/2026). Le ragioni delle scelte sono in `progettazione_del_sistema.md`, lo stato attuale in `stato_del_sistema.md`. Un lavoro si considera finito solo quando è stato provato.



## Fase 0 — Ambiente di sviluppo

1. **Controllo di versione con git** (vedi `CLAUDE.md`): `.gitignore`, primo commit.
2. **Verifica dell'ambiente**: versione di Python, librerie usate, Tesseract e lingue installate, raggiungibilità di FreeLLMAPI. Il risultato va annotato in `stato_del_sistema.md`.



## Fase 1 — Affidabilità del sistema attuale

3. **Provenienza delle letture.** Nell'archivio (`risultati/_archivio/letture.jsonl`, 10.840 voci al 22/10) quasi tutte le voci risultano «lettura manuale»:
   - 6.504 pertinenti e 858 incerte sono state decise **per regola** (`tipo_menzione` contiene «per regola»), non lette;
   - 2.121 escluse sono in gran parte esclusioni in blocco con motivazioni identiche;
   - circa 960 sono letture vere e tradotte;
   - circa 250 voci sono state lette dai modelli gratuiti.

   Da fare:
   - introdurre tre livelli distinti: letto da un modello (quale), lettura assistita in sessione, deciso per regola;
   - correggere `archivio.etichetta_lettore` e le risposte, in modo che dichiarino il livello giusto;
   - stimare il costo della lettura dei circa 7.000 pertinenti senza traduzione.
4. **Filtro dei modelli.** `config.ini` > `[router]` > `modelli_ammessi` è vuoto: la catena «ricerca» ha 26 modelli, la prova rapida del 21/10 ne ha promossi 6. Va compilato con i nomi esatti dei modelli promossi, ricavati dalla colonna `modello` dei risultati delle prove, e va provato.
5. **Citazioni nelle risposte.** `sintesi.py` stampa «(`file`, riga N)» sotto le citazioni. Le citazioni devono invece fermarsi alla pagina, quando c'è, in stile Chicago standard. Va anche allineato il formato di `FULL_CITATION` (oggi «Hongqi (1981), no. 23, December 1, 1981, ...»), poi generato dal profilo di serie (fase 2). File e riga possono restare in una sezione tecnica separata, per la verifica.
6. **Test automatici dell'estrazione** (`estrai_occorrenze.py`) su casi OCR reali presi dal corpus: sillabazione a fine riga, spazi e a capo tra caratteri cinesi, parole incollate, varianti brevi con confine di parola, equivalenze tipografiche (·・, parentesi, virgole).
7. **Insieme di riferimento** di 80-100 passaggi verificati a mano, rappresentativo di lingue e serie, con la risposta corretta (pertinente / non pertinente). Su questo si misurano precisione e richiamo di ogni modello. Claude prepara la proposta, Ivan verifica.
8. **Schede delle entità** (`entita.ini`, 91 schede):
   - doppioni: «PCd'I (m-l)» e «PCd'I (m-l) (Italia)», 176 passaggi ciascuna;
   - il PCdoB è diviso in 5 schede;
   - da separare: PCMLB (Vanderlinden) e PCB (m-l) «L'Exploité» (Trifaux).

   Vanno fissate regole scritte su quando unire o separare le schede e su come trattare dirigenti e organi di stampa.



## Fase 2 — Formato del corpus

9. **Sintassi del marcatore di pagina** (`[[p. N]]`, varianti per pagine non numerate e forma estesa) e **stato dei campi** dell'intestazione (`<CAMPO>_STATUS`, valore predefinito da decidere). Estensione di `importa.py controlla` alla validazione dei nuovi campi.
10. **Migrazione del corpus attuale.**
    - Rapporti JPRS (Hongqi 1977-1988): mancano le pagine. Vanno recuperate dai PDF originali con un nuovo OCR, se i PDF sono disponibili.
    - Peking Review e Hongqi 1963-1976: verificare se le pagine sono ricostruibili.
    - Renmin Ribao: convertire le pagine 第N版 nel marcatore standard.
11. **Data interna** per le raccolte di documenti (中共中央文件选集 ecc.): rilevamento accanto al passaggio e uso nella cronologia (`cronologia.py`, `evoluzione.py`).



## Fase 3 — Acquisizione

12. **Importazione PAGE XML e ALTO XML** (esportazioni di Transkribus ed eScriptorium) nel formato interno e poi nel .txt standard.
13. **Prova dei motori OCR**: per il cinese PaddleOCR e Kraken, su un campione del corpus; per l'albanese Tesseract, su scansioni vere. Poi la prova dei modelli sulla lettura dell'albanese.
14. **Profili di serie**: trasferire nei profili le regole oggi scritte nel codice (第N版, `SERIE_BREVE`, allineamento Peking Review -> Renmin Ribao, frasi dei «Limiti», forme generiche di `classifica.forma_sicura`).



## Fase 4 — Generalizzazione e pubblicazione

15. **Separare i dati di progetto dal motore**: una cartella per progetto di ricerca, scelta in `config.ini`.
16. **Server MCP generico**: strumenti ridotti e generici, istruzioni di comportamento consegnate dal server e non scritte per un solo client.
17. **Distribuzione**: pacchetto installabile, file dei requisiti, documentazione in italiano e in inglese, licenza, corpus d'esempio libero da diritti.
18. **Verifica del bisogno** presso 5-10 ricercatori di ambiti vicini.
19. **Articolo metodologico** con le misure della fase 1.

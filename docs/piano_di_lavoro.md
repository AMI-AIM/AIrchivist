# Piano di lavoro

Lavori in ordine di priorità per la generalizzazione dello strumento (22/10/2026). Le ragioni delle scelte sono in `progettazione_del_sistema.md`, lo stato attuale in `stato_del_sistema.md`. Un lavoro si considera finito solo quando è stato provato.



## Fase 0 — Ambiente di sviluppo

1. **Controllo di versione con git** (vedi `CLAUDE.md`): `.gitignore`, primo commit.
2. **Verifica dell'ambiente**: versione di Python, librerie usate, Tesseract e lingue installate, raggiungibilità di FreeLLMAPI. Il risultato va annotato in `stato_del_sistema.md`.



## Fase 1 — Affidabilità del motore

3. **Provenienza delle letture.** Il modello dati dell'archivio distingue tre livelli: letto da un modello (quale), lettura assistita in sessione, deciso per regola. Le risposte dichiarano il livello di ogni passaggio.
4. **Citazioni.** Generate in stile Chicago standard dal profilo di serie, fino alla pagina quando c'è, senza nome del file né numero di riga. File e riga possono restare in una sezione tecnica separata, per la verifica.
5. **Test automatici dell'estrazione** (`estrai_occorrenze.py`): sillabazione a fine riga, spazi e a capo tra caratteri cinesi, parole incollate, varianti brevi con confine di parola, equivalenze tipografiche (·・, parentesi, virgole).
6. **Strumento di valutazione.** Procedura e comandi per costruire, su qualsiasi corpus, un insieme di riferimento verificato a mano e misurare precisione e richiamo dell'estrazione e di ogni modello.
7. **Schede delle entità.** Formato e regole scritte: quando unire o separare due schede, come trattare dirigenti e organi di stampa, forme ambigue ed entità collegate.



## Fase 2 — Formato del corpus

8. **Sintassi del marcatore di pagina** (`[[p. N]]`, varianti per pagine non numerate e forma estesa) e **stato dei campi** dell'intestazione (`<CAMPO>_STATUS`, valore predefinito da decidere). Estensione di `importa.py controlla` alla validazione dei nuovi campi.
9. **Data interna** dei documenti nelle raccolte: rilevamento accanto al passaggio e uso nella cronologia (`cronologia.py`, `evoluzione.py`).



## Fase 3 — Acquisizione

10. **Importazione PAGE XML e ALTO XML** (esportazioni di Transkribus ed eScriptorium) nel formato interno e poi nel .txt standard.
11. **Prova dei motori OCR** su campioni: per il cinese PaddleOCR e Kraken, per l'albanese Tesseract su scansioni vere. Poi la prova dei modelli sulla lettura dell'albanese.
12. **Profili di serie**: trasferire nei profili le regole oggi scritte nel codice (第N版, `SERIE_BREVE`, allineamento Peking Review -> Renmin Ribao, frasi dei «Limiti», forme generiche di `classifica.forma_sicura`).



## Fase 4 — Generalizzazione e pubblicazione

13. **Separare i dati di progetto dal motore**: una cartella per progetto di ricerca, scelta in `config.ini`.
14. **Server MCP generico**: strumenti ridotti e generici, istruzioni di comportamento consegnate dal server e non scritte per un solo client.
15. **Distribuzione**: pacchetto installabile, file dei requisiti, documentazione in italiano e in inglese, licenza, corpus d'esempio libero da diritti.
16. **Verifica del bisogno** presso 5-10 ricercatori di ambiti vicini.
17. **Articolo metodologico** con le misure dello strumento di valutazione.

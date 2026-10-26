# Piano di lavoro

Lavori in ordine di priorità per la generalizzazione dello strumento (22/10/2026, aggiornato il 26/10/2026). Le ragioni delle scelte sono in `progettazione_del_sistema.md`, lo stato attuale in `stato_del_sistema.md`. Un lavoro si considera finito solo quando è stato provato.

Al 26/10/2026 i lavori 1-14 sono fatti e il 15 in parte (dettagli in `stato_del_sistema.md`). Restano aperti i lavori indicati come tali qui sotto.



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
15. **Distribuzione**: pacchetto installabile, file dei requisiti, documentazione in italiano e in inglese, licenza, corpus d'esempio libero da diritti. Fatti il 25/10/2026: `installa.py` (librerie, controllo dell'ambiente, configurazione dei client), `requirements.txt`, licenza AGPL-3.0, `README.md` in inglese. **Restano:** corpus d'esempio (rimandato), traduzione inglese di `ISTRUZIONI.md`, separazione dei dati di ricerca dell'autore dal repository pubblico.
16. **Modello scelto dal ricercatore** (aperto). Nessun filtro imposto: il motore offre la struttura su cui il ricercatore innesta il modello che preferisce.
    - `modelli_ammessi` resta facoltativo, vuoto di default, impostabile per progetto (`progetto.ini`).
    - Ogni risposta dichiara quale modello ha letto i passaggi e se è stato misurato su quelle fonti. Senza misura, la sezione «Limiti» lo dice.
    - Documentazione (italiano e inglese) del percorso per innestare un modello: servizio (FreeLLMAPI, Ollama, servizio compatibile OpenAI, API Anthropic), insieme di riferimento, `valutazione.py modelli`, filtro facoltativo.
17. **Verifica del bisogno** (aperto) presso 5-10 ricercatori di ambiti vicini.



## Prima della fase 5 — Riorganizzazione della cartella

Struttura in inglese, progetti in `projects/` fuori da git, solo cartelle e file rinominati: istruzioni in `reorganization.md`. Va fatta prima della fase 5, che usa già i percorsi nuovi.



## Fase 5 — Sistemi minori: skill e plugin

Istruzioni dettagliate in `roadmap_skill.md`. Accanto al sistema principale, una skill unica che porta il metodo nella chat di Claude e di ChatGPT, presentata come sistema minore e più limitato.

18. **Verifiche sui provider** (aperto): documentazione ufficiale di skill e plugin per claude.ai, Claude Code e ChatGPT (formati, piani, ambienti di esecuzione, plugin di sole skill).
19. **Skill unica** (aperto): fonte unica `skills/source-search/` con `SKILL.md` neutro rispetto al provider, riconoscimento dell'ambiente, vincoli degli ambienti (solo libreria standard, niente rete né OCR dati per scontati).
20. **Confezioni** (aperto): `skills/package.py` produce lo zip per claude.ai, la cartella o il plugin per Claude Code, il plugin per ChatGPT.
21. **Pulizia** (aperto): eliminare `.claude/skills/ricerca-fonti/`; aggiornare `CLAUDE.md`, `README.md`, `README.it.md`, `docs/user_guide.it.md`.
22. **Prove** (aperto): una per ambiente sulla stessa domanda e sullo stesso corpus piccolo, con confronto senza skill; test delle confezioni; test dei PDF corretti per il caso «PyMuPDF assente» (oggi 9 test falliscono invece di essere saltati o di provare il ripiego su pypdf).
23. **Presentazione** (aperto): tabella di confronto tra sistema principale e sistemi minori nel `README.md` e nelle confezioni.



## Fase 6 — Metodo

24. **Insieme di riferimento verificato a mano** (aperto) con `valutazione.py`, e misure di precisione e richiamo. Va fatto da Ivan: è la condizione per ogni dato pubblicato.
25. **Articolo metodologico** (aperto) con le misure dello strumento di valutazione.

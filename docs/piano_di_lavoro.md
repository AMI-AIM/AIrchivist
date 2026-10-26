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
15. **Distribuzione**: pacchetto installabile, file dei requisiti, documentazione in italiano e in inglese, licenza, corpus d'esempio libero da diritti. Fatti il 25/10/2026: `installa.py` (librerie, controllo dell'ambiente, configurazione dei client), `requirements.txt`, licenza AGPL-3.0, `README.md` in inglese. **Restano:** corpus d'esempio (rimandato), traduzione inglese di `docs/user_guide.it.md`, separazione dei dati di ricerca dell'autore dal repository pubblico.
16. **Modello scelto dal ricercatore** (aperto). Nessun filtro imposto: il motore offre la struttura su cui il ricercatore innesta il modello che preferisce.
    - `modelli_ammessi` resta facoltativo, vuoto di default, impostabile per progetto (`project.ini`).
    - Ogni risposta dichiara quale modello ha letto i passaggi e se è stato misurato su quelle fonti. Senza misura, la sezione «Limiti» lo dice.
    - Documentazione (italiano e inglese) del percorso per innestare un modello: servizio (FreeLLMAPI, Ollama, servizio compatibile OpenAI, API Anthropic), insieme di riferimento, `valutazione.py modelli`, filtro facoltativo.
17. **Verifica del bisogno** (aperto) presso 5-10 ricercatori di ambiti vicini.



## Prima della fase 5 — Riorganizzazione della cartella

Struttura in inglese, progetti in `projects/` fuori da git, solo cartelle e file rinominati: istruzioni in `reorganization.md`. Va fatta prima della fase 5, che usa già i percorsi nuovi. Fatta il 26/10/2026 (mappa dei percorsi ed esito delle verifiche in `stato_del_sistema.md`). Regola di `sources/` per le importazioni future (`reorganization.md`, sezione 4) applicata in `importa.py` lo stesso giorno.



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


## Fase 7 — Semplificazione dell'installazione e dell'uso

Istruzioni dettagliate in `roadmap_simplification.md`. Obiettivo: un ricercatore esterno, con un proprio corpus di PDF, installa il sistema, importa le fonti e fa la prima ricerca in meno di un'ora di lavoro attivo, su Windows, macOS e Linux, senza modificare file di configurazione a mano. Punto di arrivo: un'interfaccia propria sul modello di Chronos (menu a tendina per progetto e modello, visore della fonte, citazioni cliccabili). I lavori 26-28 vanno fatti per primi; l'eseguibile unico che contiene l'interfaccia è rimandato a dopo i lavori 17 e 34.

26. **Scelta del modello, modificabile in ogni momento** (in corso): profili di modello (servizio, modello, parametri propri, variabile della chiave); `installa.py modello` per crearli, `usa` per cambiarli solo dopo una prova riuscita; ricerche in corso legate al profilo con cui sono partite; rilettura facoltativa dei passaggi di un modello; «Limiti» con i modelli che hanno letto e se sono misurati. Fatto il 26/10: profili in `models.ini` (`models_template.ini`), scelta in `[modello] profilo` o per ruolo, configurazione precedente ancora letta; `installa.py modello nuovo | elenca | usa | prova | togli | converti`, con i cambi annotati in `system/model_changes.csv`; ogni ricerca fissa i profili al suo avvio (`modelli.json` nella sua cartella, «profili» nello stato del lavoro) e, se interrotta, riprende con quelli salvo `--usa-modello-attuale`; `ricerca.py --rileggi-modello`; «Limiti» con i modelli che hanno letto, i passaggi di ciascuno e se sono misurati (prove di `valutazione.py` sul progetto); test con un servizio finto. strumento MCP `modello` (elenca, prova, usa) e opzioni `usa_modello_attuale` e `rileggi_modello` dello strumento `ricerca`. Da fare: misure legate al profilo, guida d'uso, prova reale con una ricerca prima e dopo il cambio.
27. **Configurazione automatica della chat** (aperto): `installa.py client <nome> --scrivi` (con copia e conferma) e `--verifica`.
28. **Avvio guidato** (aperto): `installa.py inizia` (controllo, modello, primo progetto, chat, riepilogo).
29. **Importazione guidata con tabella di revisione** (aperto): `importa.py proponi`, `applica`, `rivedi`; serie e metadati proposti con il loro stato, corretti in Excel o LibreOffice.
30. **Serie con meno campi** (aperto): profilo minimo (nome, tipo, lingua), citazione Chicago generata dal tipo.
31. **La risposta come documento** (aperto): HTML autonomo accanto a `risposta.md`; il server MCP consegna riassunto e percorso.
32. **Documentazione per utenti esterni** (aperto): quickstart in inglese e in italiano, guida completa in inglese, Windows, macOS e Linux.
33. **Corpus d'esempio e confezione** (aperto): corpus libero da diritti con progetto pronto; installatore per Windows; MCP Bundle per Claude Desktop se la specifica lo consente.
34. **Prova con utenti esterni** (aperto): 2-3 ricercatori installano da soli con il proprio corpus; tempi, blocchi, correzioni.

35. **Interfaccia: struttura e menu** (aperto): `app.py`, server locale con libreria standard aperto nel browser; menu a tendina «Progetto» e «Modello»; percorso guidato della ricerca.
36. **Interfaccia: visore della fonte e citazioni cliccabili** (aperto): pagina dell'originale con il passaggio evidenziato; schede «Passaggi» e «Glossario».
37. **Interfaccia: importazione e revisione** (aperto): file o cartelle, tabella dei metadati modificabile nell'interfaccia.
38. **Interfaccia: conversazione sulle fonti** (aperto): con il modello scelto e gli strumenti del motore; disattivata con spiegazione se il modello non sa usare gli strumenti.

# Roadmap: skill e plugin per Claude e ChatGPT

Istruzioni per Claude Code (26/10/2026). Riguardano la fase 5 del piano di lavoro (`piano_di_lavoro.md`, lavori 18-23). Si eseguono dopo la riorganizzazione della cartella (`reorganization.md`): i percorsi qui sotto sono quelli nuovi.



## Obiettivo

Accanto al sistema principale (motore, server MCP, modelli scelti dal ricercatore) AIrchivist offre **sistemi minori**: una skill che porta il metodo della ricerca esaustiva direttamente nella chat di Claude e di ChatGPT, senza installare il motore.

- **Una sola skill**, `source-search`, scritta senza riferimenti a un provider.
- **Tre confezioni**: zip per claude.ai, cartella (o plugin) per Claude Code, plugin per ChatGPT.
- **Presentate come sistemi minori**, con i limiti dichiarati (sezione 6).

Decisioni già prese da Ivan:
- si elimina la skill solo per Claude Code (`.claude/skills/ricerca-fonti/`);
- la skill unica serve sia la chat di Claude sia Claude Code;
- per ChatGPT si usa la strada dei plugin (sezione 4).



## Fase A — Verifiche prima di scrivere codice

Le informazioni sui provider qui sotto vengono in parte da fonti secondarie (sezione 7). Prima di costruire le confezioni, verifica sulla documentazione ufficiale e annota in `stato_del_sistema.md` cosa hai trovato e dove:

1. **Claude, skill su claude.ai:** formato dello zip, limiti di dimensione, piani richiesti, pacchetti Python disponibili nell'ambiente, accesso alla rete, dove finiscono i file caricati dall'utente.
2. **Claude Code:** cartella personale (`~/.claude/skills/`) o di progetto (`.claude/skills/`); se conviene distribuire la skill anche come plugin di Claude Code.
3. **ChatGPT, plugin (dal luglio 2026):** formato di un plugin, se può contenere **solo skill** senza app/server MCP, come si crea (Plugin Creator o pacchetto caricato), come si condivide o pubblica, piani richiesti (Plus compreso?).
4. **ChatGPT, skill:** formato (`SKILL.md`, stesso standard Agent Skills), posizione nell'ambiente (`/home/oai/skills` secondo fonti secondarie), esecuzione degli script nell'interprete del codice, pacchetti Python disponibili, rete, file caricati.
5. **Ripiego per ChatGPT:** se i plugin di sole skill non sono possibili sul piano dell'utente tipo, valuta un GPT personalizzato (istruzioni, file, interprete del codice) e i suoi requisiti.

Se un'informazione non si trova nella documentazione ufficiale, scrivilo: non va supposta.



## Fase B — Skill unica

1. **Fonte unica** in una cartella nuova del repository, per esempio `skills/source-search/`:
   - `SKILL.md` con nome, descrizione e istruzioni neutre (parla di «assistente», non di Claude o ChatGPT);
   - i moduli del motore che servono, copiati in fase di confezione e non duplicati a mano (come fa `crea_skill_chat.py`, ora `skills/package.py`, con `dipendenze()`);
   - `config.ini` minimo per la lettura in sessione.
2. **Punto di partenza:** `skills/source-search/SKILL.md` (ex `skill_chat/SKILL.md`) (versione per la chat di Claude, la più generale). Integra ciò che serve della skill di Claude Code (`.claude/skills/ricerca-fonti/SKILL.md`): uso dell'archivio unico e di `sessione.py` quando il motore e un progetto sono presenti.
3. **Riconoscimento dell'ambiente**, all'inizio della skill:
   - motore e progetto presenti sul computer (Claude Code accanto al sistema completo): usa il progetto, l'archivio unico e `sessione.py`;
   - file caricati nella conversazione (chat di Claude: `/mnt/user-data/uploads` e `/mnt/user-data/attachments`; ChatGPT: posizione da verificare in fase A): corpus temporaneo nella conversazione, senza archivio;
   - nessuna fonte: chiedi all'utente di caricarle.
4. **Vincoli degli ambienti:**
   - solo libreria standard di Python, più PyMuPDF o pypdf se presenti (ripiego già in `importa.carica_pymupdf`);
   - nessuna installazione di pacchetti e nessun accesso alla rete dati per scontati;
   - niente OCR se Tesseract manca: le scansioni senza strato di testo si segnalano e restano fuori;
   - nessuno script sostitutivo del motore (regola già in `skills/source-search/SKILL.md`).
5. **Regole di contenuto** uguali al sistema principale: forme del nome solo attestate e confermate, citazioni testuali verificate da Python, Chicago fino alla pagina, «Traduzione:», copertura e lacune dichiarate, provenienza delle letture («sessione assistita» con il nome del modello che legge).



## Fase C — Confezioni

1. **`skills/package.py`** (nella riorganizzazione nasce da `pipeline/crea_skill_chat.py`): dalla fonte unica produce in `skills/build/` (fuori da git):
   - `source-search-claude.zip` per claude.ai;
   - la cartella per Claude Code (installabile in `~/.claude/skills/` o come plugin di Claude Code, secondo la fase A);
   - il pacchetto del plugin per ChatGPT (formato secondo la fase A).
2. Ogni confezione contiene un `LEGGIMI` breve con installazione, limiti e rimando al sistema principale.
3. **Eliminare** `.claude/skills/ricerca-fonti/` (`skill_chat/` è già diventata `skills/source-search/` nella riorganizzazione). Aggiornare `CLAUDE.md` (tabella «Dove sono le cose»), `README.md`, `README.it.md`, `docs/user_guide.it.md`.



## Fase D — Prove

Una prova per ambiente, sulla stessa domanda e sullo stesso corpus piccolo (per esempio i cinque documenti sui partiti m-l filo-cinesi già usati il 25/10), con i risultati in `results/trials/skill/` del progetto:

1. claude.ai (zip caricato);
2. Claude Code (cartella installata), sia con il progetto completo sia con soli file sparsi;
3. ChatGPT (plugin).

Per ciascuna annota: tempo, passaggi estratti e letti, citazioni controllate sul PDF, pagine giuste o no, errori di data, comportamento con PDF senza strato di testo, cosa non ha funzionato. Confronta con la stessa domanda senza skill, come nella prova del 25/10.

Test automatici:
- la fonte unica contiene tutti i moduli che `SKILL.md` richiama;
- ogni confezione si apre e contiene i file attesi;
- i test sui PDF distinguono «PyMuPDF assente, ripiego su pypdf» da un guasto: oggi, senza PyMuPDF, 9 test di `test_numerazione.py` e `test_scelta_strato.py` falliscono invece di essere saltati o di provare il ripiego.



## Fase E — Documentazione e presentazione

Nel `README.md` e nei `LEGGIMI` delle confezioni, una tabella che confronta sistema principale e sistemi minori:

| | Sistema principale | Skill / plugin |
|---|---|---|
| Installazione | Python, motore, client MCP, servizio dei modelli | caricare uno zip o installare un plugin |
| Corpus | grande, persistente, con indice | piccolo, caricato nella conversazione |
| Archivio delle letture | sì, nessun passaggio letto due volte | no, ogni conversazione riparte |
| Chi legge i passaggi | il modello scelto dal ricercatore, anche gratuito o locale | il modello della chat, con l'abbonamento del provider |
| OCR | Tesseract e altri motori, importazione PAGE/ALTO | solo strato di testo dei PDF, salvo ambienti con OCR |
| Esaustività | su tutto il corpus | limitata da tempo e contesto della sessione |
| Costo | gratuito possibile | consuma i limiti del piano |

Le skill si presentano come un modo di **provare il metodo** su pochi documenti, non come alternativa al sistema principale.



## Fonti delle informazioni sui provider (26/10/2026)

- Anthropic. "Agent Skills." *Claude Platform Docs*. Accessed October 26, 2026. https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview. Fonte primaria ufficiale: stesso formato `SKILL.md` su claude.ai, Claude Code e API; nessuna sincronizzazione tra le superfici; su claude.ai zip caricato dalle impostazioni, piani a pagamento con esecuzione del codice; in Claude Code cartelle personali o di progetto, condivisione anche tramite plugin.
- OpenAI. "Using Skills." *OpenAI Academy*, April 10, 2026. https://openai.com/academy/skills/. Fonte primaria ufficiale, generica: skill con `SKILL.md`, create in ChatGPT o caricate, condivisibili nel workspace.
- Willison, Simon. "OpenAI Are Quietly Adopting Skills, Now Available in ChatGPT and Codex CLI." *Simon Willison's Weblog*, December 12, 2025. https://simonwillison.net/2025/Dec/12/openai-skills/. Fonte secondaria attendibile: formato simile a quello di Anthropic, skill in `/home/oai/skills` nell'ambiente dell'interprete del codice.
- Gradually.ai. "The New ChatGPT Plugins: Apps, Skills and MCP Explained." Accessed October 26, 2026. https://www.gradually.ai/en/chatgpt-plugins/. Fonte secondaria commerciale, da verificare: plugin dal 9 luglio 2026, con app (MCP), skill e modelli di app; utenti Free e Go senza estensioni; skill personali solo sui piani a pagamento; creazione con Plugin Creator; server MCP personalizzati solo remoti in HTTPS. Che un plugin possa contenere solo skill è una deduzione dell'articolo, non un'affermazione.
- Skillselion. "What Are ChatGPT Skills?" Accessed October 26, 2026. https://skillselion.com/guides/what-are-chatgpt-skills. Fonte secondaria commerciale, da verificare: skill personali documentate per Business, Enterprise, Healthcare, Edu; rimanda alla pagina d'aiuto di OpenAI «Skills in ChatGPT».

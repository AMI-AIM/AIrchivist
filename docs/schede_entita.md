# Schede delle entità

Formato e regole delle schede in `pipeline/entita.ini` (22/10/2026). Le regole valgono per qualsiasi corpus. Il controllo automatico è `python schede.py controlla` (dalla cartella `pipeline`); `--solo-errori` mostra solo i problemi che falsano le ricerche.

## 1. Formato

Una sezione per entità: il nome della sezione è il nome canonico, quello che compare nelle risposte.

```ini
[Fosco Dinucci]
tipo = persona
varianti = 福斯科·迪努齐; 迪努齐; Fosco Dinucci; F. Dinucci
forme_ambigue = 迪努齐; Dinucci
contesto = 意大利; 新团结
collegate = PCd'I (m-l)
note = Segretario generale del PCd'I (m-l). Non confondere con Manlio Dinucci (scheda propria).
```

| Campo | Obbligatorio | Contenuto |
|---|---|---|
| `varianti` | sì | Tutte le forme del nome attestate nel corpus, separate da `;`: scritture, trascrizioni, sigle, epiteti. Spazi e a capo dell'OCR, punto centrale, parentesi piene o mezze e sillabazione sono già tollerati: non vanno scritti come varianti. |
| `tipo` | consigliato | `persona`, `organizzazione`, `testata`, `stato`, `altro`. |
| `note` | consigliato | Chi è, periodo, omonimi da escludere, provenienza delle forme. È il testo che il modello legge per decidere la pertinenza. Le forme non ancora verificate nel corpus si segnano come «ipotesi». |
| `forme_ambigue` | consigliato | Varianti che da sole possono indicare altro: non decidono mai la pertinenza per regola, il passaggio va sempre letto. Devono comparire anche tra le `varianti`. |
| `contesto` | facoltativo | Parole che rendono più probabile la pertinenza. Non filtrano nulla. |
| `collegate` | facoltativo | Schede di entità legate a questa (dirigenti, organi di stampa, predecessori). Le ricerche sull'evoluzione le includono. |
| `forma_estesa` | per le sigle | Nome per esteso dell'ente, quando il nome canonico è una sigla (PCdoB → Partido Comunista do Brasil). |

## 2. Una scheda per soggetto storico

**Regola generale.** Una scheda corrisponde a un solo soggetto storico identificabile: una persona, un'organizzazione, una testata. Una scheda non può raccogliere più soggetti, né un solo soggetto può essere diviso in più schede.

**Unire** due schede quando indicano lo stesso soggetto:
- nomi diversi dello stesso soggetto: sigla e nome esteso, traduzioni, trascrizioni, grafie dell'OCR;
- cambio di nome senza discontinuità: stessa organizzazione, stessa direzione. Il periodo di ciascun nome va nelle `note`;
- schede che dividono le forme di un solo soggetto, come «forma abbreviata», «varianti attestate» o «forma cinese»: le forme vanno nella scheda del soggetto.

**Separare** quando i soggetti sono diversi, anche se il nome è uguale:
- scissioni e organizzazioni concorrenti con lo stesso nome (il partito ufficiale e la sua frazione m-l; due gruppi che rivendicano la stessa sigla);
- rifondazioni: un'organizzazione nuova che riprende il nome di una precedente;
- omonimi (persone con lo stesso cognome, testate con lo stesso titolo in paesi diversi).

Nei casi separati, la forma condivisa resta in tutte e due le schede, ma va dichiarata in `forme_ambigue` in entrambe. Le `note` dicono come distinguerle: periodo, dirigenti, paese.

**Gruppi.** Insiemi come «altre organizzazioni» o «dirigenti di X» non sono entità. Ogni membro rilevante ha una scheda propria, collegata all'organizzazione. Finché la scheda di un gruppo esiste, le sue letture non vanno citate come se riguardassero un solo soggetto.

**Rinominare** una scheda lascia nell'archivio le letture sotto il nome vecchio. Il controllo le segnala («passaggi nell'archivio sotto un nome senza scheda»). Vanno riattribuite al nome nuovo prima di rifare le ricerche, così non si rileggono passaggi già letti.

## 3. Dirigenti e organi di stampa

- **Dirigenti.** Scheda propria di tipo `persona`. `collegate` indica l'organizzazione e l'organizzazione indica i suoi dirigenti principali. Cariche e titoli («segretario generale», «compagno») non sono varianti: vanno nelle `note`, con il periodo e la fonte che li attesta. Il nome dell'organizzazione non entra tra le varianti della persona.
- **Organi di stampa.** Scheda propria di tipo `testata`, collegata all'organizzazione che la pubblica. Le testate hanno spesso titoli generici, condivisi da testate di altri paesi (《新团结》 è sia «Nuova Unità» sia la «Neue Einheit»): il titolo breve va in `forme_ambigue`, le `note` spiegano come distinguerle.
- Una menzione della testata non è una menzione dell'organizzazione, e viceversa: ogni scheda trova i propri passaggi. Il legame si ricostruisce con `collegate`.

## 4. Forme ambigue

Vanno in `forme_ambigue`:
- forme brevi: meno di 5 lettere latine, 2 caratteri cinesi o meno;
- il cognome da solo, o il nome da solo (Pesce, Dinucci, 贝契);
- sigle e nomi generici di partito senza qualificazione (意大利共产党, Communist Party of X), che indicano anche il partito ufficiale;
- titoli brevi di testate;
- qualsiasi forma condivisa con un'altra scheda (sezione 2).

Una forma ambigua non viene scartata: il passaggio viene estratto e letto, ma la pertinenza non si decide mai per regola. Il controllo segnala le forme brevi non dichiarate («avviso»): non sempre sono ambigue, ma la decisione va presa e scritta.

## 5. Entità collegate

`collegate` serve a due cose:
- nelle ricerche sull'evoluzione di un'entità, includere i soggetti legati (dirigenti, organi, predecessori);
- dichiarare che una forma di una scheda contenuta in una forma di un'altra è voluta. Il controllo lo segnala con «una forma di A è contenuta in forme di B», perché i passaggi di B vengono estratti anche per A.

Il legame si dichiara in tutte e due le schede, quando vale in tutte e due le direzioni (organizzazione e dirigente). Per gli omonimi non si usa `collegate`: si usano `forme_ambigue` e le `note`.

## 6. Provenienza delle forme

- Si aggiungono solo forme attestate nel corpus. `esplora_nome` propone le forme trovate, e il ricercatore le conferma prima di `crea_scheda`.
- Le forme ipotetiche (trascrizioni non ancora trovate) si segnano nelle `note` come «ipotesi», con la loro origine.
- Le forme sfuggite all'estrazione si trovano con `valutazione.py candidati`. Ogni forma aggiunta si registra nelle `note`, con la fonte in cui è attestata.

## 7. Controllo automatico

`schede.py controlla` segnala:

| Gravità | Problema |
|---|---|
| errore | stessa forma in più schede; due schede con gli stessi passaggi nell'archivio; collegata senza scheda; tipo non previsto; scheda senza varianti |
| avviso | forme brevi o generiche non dichiarate ambigue; forma ambigua assente dalle varianti; note vuote; nome di scheda che indica un gruppo; letture dell'archivio sotto un nome senza scheda; campi sconosciuti o col nome vecchio (`forma_italiana`) |
| info | una forma contenuta nelle forme di un'altra scheda, senza `collegate`; campo `tipo` mancante; sigla senza `forma_estesa`; letture sotto un nome dichiarato equivalente |

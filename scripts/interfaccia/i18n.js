// Lingua dell'interfaccia. L'interfaccia è scritta in italiano (index.html, app.js); in inglese la traduce questo
// file sul posto, mentre si disegna: i testi e gli attributi (placeholder, title, aria-label) che coincidono con una
// voce del catalogo, o con uno dei modelli per le frasi che contengono numeri e nomi. Ciò che si legge (risposte,
// trascrizioni, citazioni, quello che scrive chi usa Pressmark) non si tocca mai: sta dentro NON_TRADURRE.
// Una frase che manca dal catalogo resta in italiano: si aggiunge qui, senza toccare app.js.
window.Lingua = (() => {
"use strict";

const LINGUA = (() => {
  try {
    const q = new URLSearchParams(location.search).get("lingua");
    if (q === "it" || q === "en") localStorage.setItem("pressmark-lingua", q);
    return localStorage.getItem("pressmark-lingua") || "it";
  } catch (e) {
    return "it";
  }
})();

function scegliLingua(l) {
  try { localStorage.setItem("pressmark-lingua", l); } catch (e) { /* la scelta vale solo per questa pagina */ }
  location.reload();
}

const NON_TRADURRE = [".documento", ".fonte-testo", ".estratto", ".msg.utente", "blockquote", ".traduzione",
  ".traduzione-lettura", ".fonte-lettura", "#fonte-titolo", "#fonte-trascrizione .t", ".strato",
  ".nome-forma", "#gl-schede dd", "#gl-serie dd", ".nome-voce",
  "tr.gruppo", ".conv-messaggio .testo", ".documento-breve", ".confronto-dettagli li", "#cm-elenco .testo-comando",
  ".titolo-ricerca", "code", "pre", ".registro", "[translate='no']"].join(",");

const EN = {
  // --- barra, filo, casella
  "Progetto e ricerche": "Project and searches", "Nascondi la barra laterale": "Hide the sidebar",
  "Mostra la barra laterale": "Show the sidebar", "Barra laterale (Ctrl+B)": "Sidebar (Ctrl+B)",
  "Progetto": "Project", "Nuovo progetto": "New project", "Nuova ricerca (Ctrl+N)": "New search (Ctrl+N)",
  "Nuova ricerca": "New search", "Recenti": "Recent", "Filtra per nome o domanda": "Filter by name or question",
  "Filtra le ricerche recenti": "Filter recent searches", "Carico le ricerche…": "Loading searches…",
  "Glossario": "Glossary", "Importa fonti": "Import sources",
  "Impostazioni: progetti, modelli, ambiente (Ctrl+,)": "Settings: projects, models, environment (Ctrl+,)",
  "Impostazioni": "Settings", "Larghezza della barra laterale": "Sidebar width",
  "Trascina per allargare o stringere; doppio clic o Invio: larghezza iniziale": "Drag to widen or narrow; double-click or Enter: initial width",
  "Chiudi l'avviso": "Close the notice", "Ricerca": "Search", "Che cosa cerchi nelle fonti?": "What are you looking for in the sources?",
  "Scrivi un": "Type a", "nome": "name", "per trovarne le menzioni, oppure una": "to find its mentions, or a",
  "domanda": "question",
  "che nomina chi o che cosa ti interessa. Ogni affermazione della risposta rimanda al passaggio della fonte da cui viene.":
    "that names who or what you are interested in. Every statement in the answer points to the source passage it comes from.",
  "Già cercati:": "Already searched:", "Menzioni": "Mentions", "Oggi": "Today", "Ieri": "Yesterday", "Questa settimana": "This week", "Prima": "Earlier",
  "Ancora nessuna ricerca.": "No searches yet.", "Senza titolo": "Untitled",
  "Dal": "From", "Al": "To", "anno": "year", "Evoluzione anno per anno": "Year-by-year evolution",
  "Solo queste serie (nessuna = tutte)": "Only these series (none = all)", "Domanda o nome da cercare": "Question or name to search for",
  "Fai una domanda sulle fonti, o scrivi un nome": "Ask a question about the sources, or type a name",
  "La ricerca è in corso…": "The search is running…", "Periodo e serie": "Period and series",
  "Richieste e token usati oggi": "Requests and tokens used today", "Modello": "Model",
  "Collegamento: non provato": "Connection: not tested", "Fornitori e modelli": "Providers and models", "Invia": "Send",
  "Invia (Invio)": "Send (Enter)", "Ferma la ricerca": "Stop the search", "tutto": "all", "tutte": "all",
  // --- pannello laterale
  "Fonti e glossario": "Sources and glossary", "Larghezza del pannello": "Panel width", "Pannello": "Panel", "Fonte": "Source",
  "Passaggi": "Passages", "Chiudi il pannello": "Close the panel", "Chiudi (Esc)": "Close (Esc)",
  "Qui compare la pagina di una fonte: aprila con «Apri la fonte» nel documento della risposta o da un passaggio.":
    "A source page appears here: open it with “Open the source” in the answer or from a passage.",
  "Pagina precedente": "Previous page", "Pagina precedente (freccia sinistra)": "Previous page (left arrow)", "Pagina": "Page",
  "Pagina successiva": "Next page", "Pagina successiva (freccia destra)": "Next page (right arrow)", "Testo trascritto": "Transcribed text",
  "Scheda tecnica": "Technical details", "Pagina dell'originale": "Page of the original",
  "Testo": "Text", "Vista": "View", "Ingrandimento": "Zoom", "Riduci": "Zoom out", "Riduci (−)": "Zoom out (−)",
  "Ingrandisci": "Zoom in", "Ingrandisci (+)": "Zoom in (+)", "Adatta alla larghezza (0)": "Fit to width (0)",
  "Apri il PDF originale": "Open the original PDF", "Apri il PDF originale a questa pagina": "Open the original PDF at this page",
  "Il passaggio, non ritrovato sulla pagina": "The passage, not found on the page",
  "Leggo il testo della pagina…": "Reading the page's text…",
  "Fonte: ingrandisci, riduci, adatta alla larghezza": "Source: zoom in, zoom out, fit to width",
  "Fonte: ingrandisci attorno al puntatore": "Source: zoom around the pointer", "rotella": "wheel",
  "Apri una risposta o una ricerca dallo Storico: qui compaiono i suoi passaggi.": "Open an answer or a search from Recent: its passages appear here.",
  "Apri una risposta (o una ricerca dai recenti): qui compaiono i suoi passaggi.": "Open an answer (or a search from Recent): its passages appear here.",
  "filtra per fonte, data, traduzione": "filter by source, date, translation", "Filtra i passaggi": "Filter the passages",
  "Solo pertinenti": "Relevant only", "Solo citati": "Cited only", "Togli periodo, serie e lingue": "Clear period, series and languages",
  "Dove": "Where", "Pertinente": "Relevant", "Traduzione": "Translation", "Letto da": "Read by", "n.": "no.",
  "Correggi": "Correct", "Correggi la traduzione": "Correct the translation", "Corretto a mano": "Corrected by hand",
  "a mano": "by hand", "Traduzione corretta": "Corrected translation", "Traduzione corretta.": "Translation corrected.",
  "Salva": "Save", "sì": "yes", "no": "no", "incerto": "uncertain", "pertinente": "relevant", "non pertinente": "not relevant",
  "Questa risposta non ha più la sua ricerca: non si può correggere da qui.": "This answer no longer has its search: it cannot be corrected from here.",
  "Serie": "Series", "Lingua": "Language", "italiano": "Italian", "inglese": "English", "francese": "French", "tedesco": "German",
  "spagnolo": "Spanish", "portoghese": "Portuguese", "albanese": "Albanian", "cinese": "Chinese", "russo": "Russian",
  "greco": "Greek", "arabo": "Arabic", "ebraico": "Hebrew",
  "Le schede si leggono qui e da ognuna si avvia una ricerca. Una scheda nuova nasce quando cerchi un nome e confermi le sue forme.":
    "Entity cards are listed here, and each one can start a search. A new card is created when you search for a name and confirm its forms.",
  "filtra per nome o forma": "filter by name or form", "Filtra il glossario": "Filter the glossary",
  "Schede delle entità": "Entity cards", "Nessuna.": "None.", "Tipo": "Type", "Forme del nome": "Name forms",
  "Forme ambigue": "Ambiguous forms", "Contesto": "Context", "Note": "Notes", "Sigla": "Abbreviation", "Lingue": "Languages",
  "Luogo": "Place", "Editore": "Publisher", "Periodicità": "Frequency", "Formato": "Format", "Citazione": "Citation",
  "Citazione (Chicago)": "Citation (Chicago)", "Nome completo": "Full name",
  "C'è già una ricerca in corso: aspetta che finisca.": "A search is already running: wait for it to finish.",
  "Apri la fonte": "Open the source", "Dettagli tecnici: file e righe nel corpus": "Technical details: files and lines in the corpus",
  "Limiti e problemi interpretativi": "Limits and interpretive problems", "Grado di copertura": "Coverage",
  // --- comandi e scorciatoie
  "Comandi": "Commands", "Cerca un comando, una ricerca, una scheda o un progetto": "Search for a command, a search, a card or a project",
  "Cerca un comando, una ricerca recente, una scheda o un progetto": "Search for a command, a recent search, a card or a project",
  "Risultati": "Results", "per scegliere ·": "to choose ·", "Invio": "Enter", "per aprire ·": "to open ·", "per chiudere": "to close",
  "Scorciatoie da tastiera": "Keyboard shortcuts", "Comandi: azioni, ricerche recenti, schede, progetti": "Commands: actions, recent searches, cards, projects",
  "Vai alla casella della domanda": "Go to the question box", "Mostra o nascondi la barra laterale": "Show or hide the sidebar",
  "Chiudi il pannello, il menu o il dialogo aperto": "Close the open panel, menu or dialog",
  "Pagina precedente o successiva della scansione": "Previous or next page of the scan", "Chiudi il pannello": "Close the panel",
  "Passaggi: il seguente e il precedente": "Passages: next and previous", "Passaggi: apri la fonte": "Passages: open the source",
  "Passaggi: correggi la pertinenza (sì ↔ no)": "Passages: correct relevance (yes ↔ no)",
  "Fonte: pagina precedente e seguente": "Source: previous and next page", "Spazio": "Space",
  "Forme del nome: accendi o spegni, segna ambigua": "Name forms: switch on or off, mark ambiguous", "Questo elenco": "This list",
  "Chiudi": "Close", "Annulla": "Cancel", "Azioni": "Actions", "Schede": "Cards", "Progetti": "Projects",
  "Passaggi della risposta aperta": "Passages of the open answer", "schede delle entità e serie": "entity cards and series",
  "progetti, modelli, lingue": "projects, models, languages", "PDF, scansioni, testi": "PDFs, scans, texts",
  "Controlla la qualità dell'OCR": "Check OCR quality", "documenti con un testo sospetto": "documents with suspect text",
  "cerca nelle fonti": "search the sources", "passa a questo progetto": "switch to this project", "in uso": "in use",
  "Nessun risultato.": "No results.",
  // --- dialoghi
  "Nome della ricerca": "Name of the research project", "Descrizione (facoltativa)": "Description (optional)", "Crea": "Create",
  "Aggiungi modello": "Add model", "Servizio": "Service", "Indirizzo": "Address", "Variabile d'ambiente della chiave": "Key environment variable",
  "Chiave": "Key", "lascia vuoto se la variabile è già impostata": "leave empty if the variable is already set",
  "Conserva la chiave tra le variabili d'ambiente del tuo utente": "Keep the key in your user environment variables",
  "Elenca i modelli del servizio": "List the service's models", "Nome del profilo (facoltativo)": "Profile name (optional)",
  "La chiave non si scrive mai nei file: nel profilo resta solo il nome della variabile. Prima di usare il modello, il sistema fa una prova di collegamento.":
    "The key is never written to files: the profile keeps only the variable name. Before using the model, the system tests the connection.",
  "Aggiungi e prova": "Add and test",
  // --- importazione
  "Importare documenti": "Importing documents", "Torna alla ricerca": "Back to the search",
  "PDF, scansioni, file di testo (.txt) o trascrizioni già fatte in formato PAGE o ALTO. Il sistema propone serie e metadati, tu li controlli, poi importi. Il lavoro continua anche se chiudi la pagina.":
    "PDFs, scans, text files (.txt) or existing transcriptions in PAGE or ALTO format. The system proposes series and metadata, you check them, then import. The work continues even if you close the page.",
  "Scegli i file": "Choose the files", "Cartella o file": "Folder or file", "scegli con Sfoglia… o incolla il percorso": "choose with Browse… or paste the path",
  "Sfoglia…": "Browse…", "Serie per tutti i file (facoltativo)": "Series for all files (optional)",
  "di solito la propone il sistema": "usually proposed by the system", "Proponi i metadati": "Propose the metadata",
  "oppure rivedi i documenti già importati": "or review documents already imported", "Controlla la tabella": "Check the table",
  "Compare qui quando la proposta è pronta.": "Appears here when the proposal is ready.", "Salva le correzioni": "Save the corrections",
  "Ricarica": "Reload", "Solo le righe da controllare": "Only the rows to check", "Colonne avanzate": "Advanced columns",
  "Importa": "Import", "Sostituisci i documenti già importati": "Replace documents already imported", "Prova senza scrivere": "Dry run",
  "Avanzamento dell'importazione": "Import progress", "Importa e sostituisci": "Import and replace",
  "Sostituire i documenti già importati?": "Replace documents already imported?",
  "Lavoro avviato: lo seguo io, non serve che aspetti.": "Job started: I'll follow it, no need to wait.", "Finito.": "Done.",
  "La tabella ha errori da correggere: salva le correzioni e riprova.": "The table has errors to fix: save the corrections and try again.",
  "Lavoro in corso…": "Working…", "Indica prima la cartella dei documenti.": "First choose the documents folder.",
  "Indica prima la tabella di revisione.": "First choose the review table.",
  "Qualità dell'OCR": "OCR quality",
  "Un OCR fallito o letto con la lingua sbagliata nasconde i nomi alla ricerca. Il controllo cerca i documenti con una confidenza bassa o con molte parole illeggibili; da qui puoi rifare l'OCR dall'originale con altre lingue.":
    "Failed OCR, or OCR read with the wrong language, hides names from the search. The check looks for documents with low confidence or many unreadable words; from here you can redo the OCR from the original with other languages.",
  "Controlla la qualità": "Check quality", "Controlla di nuovo": "Check again", "Controllo i documenti importati…": "Checking imported documents…",
  "L'originale non è registrato: reimporta il documento dalla tabella.": "The original is not recorded: reimport the document from the table.",
  "Rifai l'OCR": "Redo OCR", "OCR avviato": "OCR started", "Lingue ": "Languages ",
  // --- impostazioni
  "Sezioni delle impostazioni": "Settings sections", "Generale": "General", "Modelli": "Models", "Lingue delle scansioni": "Scan languages",
  "Controllo dell'ambiente": "Environment check", "Fornitori dei modelli": "Model providers",
  "Aggiungi un servizio compatibile OpenAI": "Add an OpenAI-compatible service", "Aggiungi un fornitore": "Add a provider",
  "Sul computer": "On this computer", "Online": "Online", "Nuovo progetto…": "New project…", "Preparazione": "Setup", "Aiuto": "Help",
  "Guida all'uso": "User guide", "Come si importano le fonti, si cerca un nome e si leggono le risposte.": "How to import sources, search for a name and read the answers.",
  "Apri la guida": "Open the guide", "Tutte le scorciatoie": "All shortcuts",
  "Passaggi: il seguente, il precedente, correggi la pertinenza": "Passages: next, previous, correct relevance", "Lingua dell'interfaccia": "Interface language",
  "Le risposte e le traduzioni dei passaggi restano nella lingua scelta per il progetto.": "Answers and passage translations stay in the language chosen for the project.",
  "Il modello legge i passaggi delle fonti, li traduce e scrive la risposta. Qui compaiono solo i modelli dei fornitori attivi: un fornitore si attiva con la sua chiave, nella sua pagina.":
    "The model reads the source passages, translates them and writes the answer. Only models from active providers appear here: a provider is activated with its key, on its page.",
  "Le lingue in cui il riconoscimento del testo (OCR, con Tesseract) legge le scansioni. Servono quelle delle serie del progetto.":
    "The languages in which text recognition (OCR, with Tesseract) reads scans. The project's series need theirs.",
  "Lingue installate": "Installed languages", "Controllo in corso…": "Checking…", "Installa una lingua": "Install a language",
  "Lingua da installare": "Language to install", "Installa": "Install", "Esito dei controlli": "Check results",
  "Si scaricano i modelli più precisi di Tesseract, da 1 a 50 MB ciascuno, nella cartella": "The most accurate Tesseract models are downloaded, 1 to 50 MB each, into the folder",
  "Tesseract non trovato: senza, le scansioni non si importano.": "Tesseract not found: without it, scans cannot be imported.",
  "Scarica le mancanti": "Download the missing ones", "Ci sono tutte le lingue richieste dalle serie del progetto.": "All languages required by the project's series are installed.",
  "sceglie i passaggi pertinenti": "picks the relevant passages", "legge e traduce i passaggi": "reads and translates the passages",
  "scrive la risposta": "writes the answer", "Smistamento": "Sorting", "Analisi": "Analysis", "Sintesi": "Synthesis",
  "prova in corso": "test running", "Prova di collegamento in corso…": "Testing the connection…", "Acceso: clic per spegnere": "On: click to turn off",
  "Spento: clic per accendere": "Off: click to turn on", "Prova il collegamento": "Test the connection", "Rinomina…": "Rename…", "Togli…": "Remove…",
  "Collegamento riuscito.": "Connection succeeded.", "Nome invariato.": "Name unchanged.", "Un modello diverso per ruolo": "A different model per role",
  "Impostazioni del fornitore": "Provider settings", "Chiave API": "API key", "Usa la chiave": "Use the key", "Dove si crea": "Where to create it",
  "Sostituisci la chiave": "Replace the key", "Sostituisci e prova": "Replace and test", "Salva e prova": "Save and test", "Provo la chiave…": "Testing the key…",
  "Risponde.": "Responds.", "Non risponde a questo indirizzo.": "Does not respond at this address.", "Non serve.": "Not needed.",
  "Modelli scaricati": "Downloaded models", "Chiedo l'elenco al servizio…": "Asking the service for its list…", "Mostra tutti": "Show all",
  "Nessun modello con questo nome.": "No model with this name.", "Aggiungi a mano…": "Add manually…", "Aggiungi modello…": "Add model…",
  "Usa questo fornitore": "Use this provider", "Fornitore acceso o spento": "Provider on or off", "Modelli in Pressmark": "Models in Pressmark",
  "modelli diversi per ruolo": "different models per role", "— nessun modello —": "— no model —", "— nessun progetto —": "— no project —",
  "Nessun progetto in uso": "No project in use", "Nessun progetto ancora: creane uno.": "No projects yet: create one.", "Cambia progetto": "Change project",
  "gratuito": "free", "piano gratuito": "free tier", "a consumo": "pay as you go",
  "Tutto il necessario è pronto: puoi cercare. I passi facoltativi si fanno quando vuoi.": "Everything needed is ready: you can search. Optional steps can be done whenever you like.",
  "Prima di cercare servono un progetto e un modello. Ogni passo si fa da qui, senza terminale.": "Before searching you need a project and a model. Every step can be done from here, without a terminal.",
  "Cambia…": "Change…", "Scegli…": "Choose…", "Importa…": "Import…", "Scegli il modello…": "Choose the model…",
  "Controllo in corso (anche il collegamento al modello)…": "Checking (including the model connection)…",
  "Niente di necessario manca. I segni «–» indicano parti facoltative.": "Nothing required is missing. “–” marks optional parts.",
  "(non risponde)": "(not responding)", "(senza chiave)": "(no key)", "(chiave spenta)": "(key off)",
  "(controllo in corso)": "(checking)", "(non trovato)": "(not found)", "(non disponibile)": "(not available)",
  "non risponde": "not responding", "Usa": "Use", "Progetto di ricerca": "Research project",
  "Modello che legge i passaggi": "Model that reads the passages", "Prime fonti (facoltativo)": "First sources (optional)",
  "Chiude il pannello, il menu o il dialogo aperto": "Closes the open panel, menu or dialog",
  "Ollama non risponde: non è installato o non è avviato. Si scarica da https://ollama.com; una volta avviato, i modelli scaricati compaiono qui sotto.":
    "Ollama is not responding: it is not installed or not running. Download it from https://ollama.com; once it runs, the downloaded models appear below.",
  "Di solito basta un modello per tutto. Qui si può dare a un ruolo un modello diverso, per esempio uno più economico per lo smistamento.":
    "One model for everything is usually enough. Here a role can get a different model, for example a cheaper one for sorting.",
  "I ruoli usano modelli diversi. «Usa» nell'elenco sopra sceglie un modello per tutti.": "The roles use different models. “Use” in the list above picks one model for all.",
  "Per le serie": "For the series", "Orientamento della pagina e scrittura": "Page orientation and script",
  "Usa una cartella mia…": "Use my own folder…", "SQLite con FTS5": "SQLite with FTS5", "Progetto e modello": "Project and model",
  "progetto": "project", "serie": "series", "Importazione delle fonti": "Source import", "lingue installate": "installed languages",
  "lingue OCR delle serie": "OCR languages of the series", "Cartella": "Folder", "Prova, rinomina, togli": "Test, rename, remove",
  "Modo": "Mode", "Programma": "Program", "Configurazione": "Configuration", "Profili dei modelli": "Model profiles", "sviluppo": "development",
  "installato": "installed", "Mostra tutti": "Show all", "Copia e usa": "Copy and use", "Copio i modelli…": "Copying the models…",
  "Usare una cartella delle lingue tua?": "Use your own language folder?", "Tesseract resta com'è.": "Tesseract stays as it is.",
  "Modelli che girano sul tuo computer: gratuiti, senza chiave, e i testi non escono dal computer.":
    "Models that run on your computer: free, no key, and the texts never leave the computer.",
  "Router avviato sul tuo computer che passa da un servizio gratuito all'altro.": "A router running on your computer that moves from one free service to another.",
  "I modelli Claude, a consumo.": "Claude models, pay as you go.", "Piano gratuito, risposte veloci.": "Free tier, fast answers.",
  "Piano gratuito sui modelli Flash: i testi possono essere usati da Google.": "Free tier on the Flash models: texts may be used by Google.",
  "I modelli con nome che finisce in «:free» sono gratuiti (50 richieste al giorno senza acquisti).": "Models whose name ends in “:free” are free (50 requests a day without purchases).",
  "I modelli GPT, a consumo.": "GPT models, pay as you go.", "Modelli Mistral, con un piano gratuito a richieste limitate.": "Mistral models, with a free tier with limited requests.",
  "I modelli Grok, a consumo.": "Grok models, pay as you go.", "Modelli MiniMax, a consumo.": "MiniMax models, pay as you go.",
  "Modelli aperti di più fornitori, attraverso il router di Hugging Face. La chiave è un token dell'account; si prova la prima volta che usi un modello.":
    "Open models from several providers, through the Hugging Face router. The key is an account token; it is tested the first time you use a model.",
  "Modelli aperti ospitati da NVIDIA, con crediti gratuiti. La chiave si prova la prima volta che usi un modello.":
    "Open models hosted by NVIDIA, with free credits. The key is tested the first time you use a model.",
  "I suoi modelli accesi si possono scegliere nella pagina Modelli.": "Its switched-on models can be chosen on the Models page.",
  "L'interruttore di un modello lo toglie dalla scelta senza cancellarlo.": "A model's switch removes it from the choice without deleting it.",
  "Conserva la chiave tra le sessioni (variabile dell'utente, mai nei file del progetto)": "Keep the key between sessions (user variable, never in project files)",
  "non attivo": "not active", "attivo": "active",
  // --- glossario modificabile
  "Apri una scheda per vedere che cosa sa già l'archivio, cercarla nelle fonti o modificarla. Una scheda nuova nasce quando cerchi un nome e confermi le sue forme.":
    "Open a card to see what the archive already knows, search the sources for it or edit it. A new card is created when you search for a name and confirm its forms.",
  "Errori nel glossario": "Errors in the glossary", "Carico ciò che l'archivio sa di questa entità…": "Loading what the archive knows about this entity…",
  "Nessun passaggio ancora letto: avvia una ricerca.": "No passages read yet: start a search.", "Nelle serie:": "In the series:",
  "Risposte salvate": "Saved answers", "Collegate:": "Related:", "Cerca nelle fonti": "Search the sources", "Modifica": "Edit",
  "Unisci a…": "Merge into…", "Elimina…": "Delete…", "Aggiungi": "Add", "Scarta": "Reject", "Rinomina": "Rename", "Unisci": "Merge",
  "Compaiono nei passaggi già letti e non sono nella scheda. «Aggiungi» le mette tra le forme (la prossima ricerca legge solo i passaggi nuovi); «Scarta» non le ripropone più.":
    "They appear in passages already read and are not in the card. “Add” puts them among the forms (the next search reads only the new passages); “Reject” stops suggesting them.",
  "Forma estesa": "Full form", "il nome per esteso, se la scheda è una sigla": "the name in full, if the card is an abbreviation",
  "parole che aiutano il modello a riconoscerla, separate da ;": "words that help the model recognise it, separated by ;",
  "Collegate": "Related", "chi è, il periodo, gli omonimi da non confondere": "who it is, the period, namesakes not to confuse",
  "aggiungi una forma, poi Invio (più forme: separate da ;)": "add a form, then Enter (several forms: separated by ;)",
  "Aggiungi una forma del nome": "Add a name form", "aggiungi una scheda collegata…": "add a related card…",
  "Segna o togli «ambigua»": "Mark or unmark “ambiguous”", "Righe delle fonti con questa forma: un clic mostra un esempio": "Source lines with this form: click to see an example",
  "Nessuna riga delle fonti contiene questa forma.": "No source line contains this form.", "Nuovo nome della scheda": "New name of the card",
  "Scheda in cui unire": "Card to merge into", "Errore:": "Error:", "Avviso:": "Warning:", "Nota:": "Note:",
  "Anteprima della citazione": "Citation preview", "aggiungi un campo…": "add a field…", "Aggiungi un campo al profilo": "Add a field to the profile",
  "Segnaposti tra graffe: {autore_bib}, {titolo}, {data_o_anno}, {pagine}, {pagina}…; le parti tra [ ] spariscono se il loro segnaposto è vuoto.":
    "Placeholders in braces: {autore_bib}, {titolo}, {data_o_anno}, {pagine}, {pagina}…; parts in [ ] disappear when their placeholder is empty.",
  "Una scheda ha almeno una forma del nome.": "A card has at least one name form.", "Non ci sono altre schede a cui unirla.": "There are no other cards to merge it into.",
  "Nessun cambiamento.": "No changes.", "Scheda salvata.": "Card saved.", "Con la pagina 12 come esempio.": "With page 12 as an example.",
  "Nessun documento di questa serie tra le fonti.": "No document of this series among the sources.",
  "Profilo salvato. Le citazioni nuove lo usano; le risposte già scritte restano come sono.": "Profile saved. New citations use it; answers already written stay as they are.",
  "Rifai la ricerca: si leggono solo i passaggi delle forme nuove.": "Run the search again: only the passages of the new forms are read.",
  "Alla prossima ricerca si leggono i passaggi delle forme nuove; quelli già letti si riusano.": "The next search reads the passages of the new forms; those already read are reused.",
  "I passaggi già letti delle forme tolte restano nell'archivio; la prossima ricerca non li cerca più.": "Passages already read for removed forms stay in the archive; the next search no longer looks for them.",
  "Chi è (note della scheda)": "Who it is (card notes)", "Prima di creare la scheda:": "Before creating the card:",
  "Prima di salvare:": "Before saving:", "Nessun problema: la scheda è in ordine.": "No problems: the card is in order.",
  "Scrivi le note": "Write the notes", "Niente da correggere.": "Nothing to fix.",
  "Curatori": "Editors", "Titolo del volume": "Volume title", "Autore": "Author", "Titolo": "Title", "Nota sui limiti": "Note on limits",
  "Lingue dell'OCR": "OCR languages", "Cartella": "Folder", "Periodo": "Period",
  // --- riepilogo, schede, forme
  "Domanda": "Question", "Periodo": "Period", "Costo": "Cost", "Modo": "Mode", "evoluzione anno per anno": "year-by-year evolution",
  "Nelle fonti": "In the sources", "conto le righe…": "counting lines…", "1 riga con queste forme": "1 line with these forms",
  "Già letti": "Already read", "Ultima ricerca": "Last search", "Durata": "Duration", "Richieste": "Requests", "conto non riuscito": "count failed",
  "non contate": "not counted", "Forme": "Forms", "nessuna spuntata": "none selected",
  "La scheda entra nel glossario. La ricerca si avvia nel passo dopo, con il suo riepilogo.": "The card goes into the glossary. The search starts in the next step, with its summary.",
  "Di chi parli? Più schede corrispondono.": "Who do you mean? Several cards match.",
  "Di chi o di che cosa cerchi le menzioni? Scrivi il nome qui sotto.": "Whose mentions are you looking for? Type the name below.",
  "Fai la domanda al modello, senza scegliere una scheda": "Ask the model, without choosing a card", "Domanda al modello, senza una scheda.": "Question to the model, without a card.",
  "Il nome della persona, del partito, della testata…": "The name of the person, party, newspaper…",
  "Di chi parli? Scegli una scheda o scrivi il nome.": "Who do you mean? Choose a card or type the name.", "Avvia la ricerca": "Start the search",
  "Più schede corrispondono: scegli quella giusta.": "Several cards match: choose the right one.", "È un omonimo: cerca altre forme": "It's a namesake: look for other forms",
  "Era quella giusta": "It was the right one", "Forme del nome pronte: controlla il riepilogo e avvia la ricerca.": "Name forms ready: check the summary and start the search.",
  "Nome della scheda nuova": "Name of the new card", "Indizi (facoltativi)": "Clues (optional)", "paese, partito… separati da ;": "country, party… separated by ;",
  "Altre forme da verificare (facoltative)": "Other forms to check (optional)", "per esempio una trascrizione; separate da ;": "for example a transliteration; separated by ;",
  "Cerca le forme nelle fonti": "Find the forms in the sources", "Cerca di nuovo con questi indizi": "Search again with these clues",
  "Cerco le forme in tutte le fonti: di solito servono da 10 a 30 secondi.": "Searching all sources for the forms: this usually takes 10 to 30 seconds.",
  "Accendi le forme che indicano davvero questa entità; il numero è quante righe delle fonti la contengono. «Ambigua»: la forma può indicare anche altro (un cognome da solo, per esempio), e quei passaggi li controlla sempre il modello.":
    "Switch on the forms that really refer to this entity; the number is how many source lines contain it. “Ambiguous”: the form may refer to something else too (a surname alone, for example), and the model always checks those passages.",
  "Da tastiera: frecce tra le forme, Spazio accende o spegne, A segna ambigua, Invio crea la scheda.": "Keyboard: arrows between forms, Space switches on or off, A marks ambiguous, Enter creates the card.",
  "Forme trovate": "Forms found", "Forme scartate l'altra volta": "Forms rejected last time", "Tipo di entità": "Entity type", "Tipo di entità ": "Entity type ",
  "persona": "person", "organizzazione": "organization", "testata": "newspaper", "stato": "state", "altro": "other", "ambigua": "ambiguous",
  "Crea la scheda": "Create the card", "Accendi almeno una forma del nome.": "Switch on at least one name form.",
  "Dai un nome alla scheda nuova: deve distinguerla da quella che esiste già.": "Give the new card a name that tells it apart from the existing one.",
  "Usa la scheda esistente": "Use the existing card", "L'avevi scartata l'altra volta che hai cercato questo nome.": "You rejected it last time you searched for this name.",
  // --- ricerca in corso e risposta
  "Questa ricerca era già in corso: ne seguo l'avanzamento.": "This search was already running: following its progress.",
  "Riprova": "Try again", "Cambia modello": "Change model", "Estrazione": "Extraction", "Lettura dei passaggi": "Reading the passages",
  "Risposta": "Answer", "La ricerca si è interrotta per un errore.": "The search stopped because of an error.",
  "La ricerca si è interrotta.": "The search was interrupted.", "Ricerca fermata.": "Search stopped.",
  "Avanzamento della ricerca": "Search progress", "Fasi della ricerca": "Search stages", "Riprova ora": "Retry now",
  "Ultimi passaggi letti": "Latest passages read", "In partenza…": "Starting…", "Continua anche se chiudi questa pagina.": "It continues even if you close this page.",
  "circa un minuto alla fine della lettura": "about a minute until reading ends", "Riprovo adesso…": "Retrying now…", "In corso…": "Running…",
  "in corso": "running", "in attesa": "waiting", "completata": "completed", "fermata": "stopped", "errore": "error", "interrotta": "interrupted",
  "Ricerca fermata su richiesta.": "Search stopped on request.", "Riprendi la ricerca": "Resume the search",
  "I passaggi già letti restano salvati e la nuova ricerca li riusa.": "Passages already read stay saved and the new search reuses them.",
  "Fermare la ricerca?": "Stop the search?", "La ricerca si interrompe qui. I passaggi già letti restano salvati e una ricerca successiva li riusa.":
    "The search stops here. Passages already read stay saved and a later search reuses them.",
  "Carico la risposta…": "Loading the answer…", "Fonti di questa risposta": "Sources of this answer", "Documento completo": "Full document",
  "Apre la risposta intera in una finestra a parte, da stampare o salvare": "Opens the whole answer in a separate window, to print or save",
  "Risposta pronta.": "Answer ready.", "Esporta": "Export", "Word, con le note a piè di pagina": "Word, with footnotes",
  "la risposta in stile Chicago": "the answer in Chicago style", "Zotero o Mendeley (CSL-JSON)": "Zotero or Mendeley (CSL-JSON)",
  "i documenti citati": "the cited documents", "Tabella dei passaggi (CSV)": "Table of passages (CSV)", "per Excel o LibreOffice": "for Excel or LibreOffice",
  "la risposta breve è cambiata": "the short answer changed", "Citati adesso, non la volta prima": "Cited now, not last time",
  "Citati la volta prima, non adesso": "Cited last time, not now", "Apri la risposta di prima": "Open the previous answer", "Adesso": "Now", "nuovo": "new",
  "Mostra": "Show", "Altre azioni": "More actions", "Elimina": "Delete", "Rinomina": "Rename", "Nuovo nome della conversazione": "New name of the conversation",
  // --- consumo
  "nessuna richiesta oggi": "no requests today", "Oggi per modello": "Today by model", "7 giorni": "7 days",
  "I piani gratuiti hanno limiti al giorno e al minuto: quando finiscono, la ricerca aspetta e riprende da sola. Con un servizio a consumo, il costo segue i token.":
    "Free tiers have daily and per-minute limits: when they run out, the search waits and resumes by itself. With a pay-as-you-go service, cost follows tokens.",
  "poche: i passaggi sono già letti, resta la risposta": "few: the passages are already read, only the answer remains",
  // --- conversazione
  "Compare così nei risultati degli strumenti": "Appears like this in the tools' results",
  "Un riferimento restituito dagli strumenti ha lo stesso titolo, data e pagina": "A reference returned by the tools has the same title, date and page",
  "Nessuno strumento ha restituito questo riferimento: non usarlo senza verificarlo": "No tool returned this reference: don't use it without checking",
  "Nessuna citazione nella risposta.": "No citations in the answer.", "Il modello sta consultando le fonti con gli strumenti…": "The model is consulting the sources with its tools…",
  "Conversazione non disponibile.": "Conversation not available.", "Riprova la verifica del modello": "Retry the model check",
  "Clic: apri la pagina della fonte": "Click: open the source page", "Apro la ricerca…": "Opening the search…",
  // --- errori frequenti
  "L'interfaccia non risponde: controlla che la finestra di app.py sia ancora aperta.": "The interface is not responding: check that the app.py window is still open.",
  "Sessione scaduta: riapri l'interfaccia dal collegamento stampato da app.py.": "Session expired: reopen the interface from the link printed by app.py.",
  "Scrivi il nome della persona o dell'ente.": "Type the name of the person or organization.",
  "Nessuna ricerca in corso.": "No search running.", "Ricerca non trovata.": "Search not found.", "Ricerca non valida.": "Invalid search.",
  "Passaggio non trovato in questa ricerca.": "Passage not found in this search.",
  "La ricerca non è in attesa: sta già lavorando.": "The search isn't waiting: it is already working.",
  "Riprovo adesso: se le quote non sono ancora tornate, la ricerca riaspetta.": "Retrying now: if the quota hasn't come back yet, the search waits again.",
  "Corretto. La risposta cambia quando rifai la ricerca: le ricerche successive usano la correzione e non rimandano il passaggio al modello.":
    "Corrected. The answer changes when you run the search again: later searches use the correction and don't send the passage back to the model.",
};

const pl = (n, uno, molti) => (+n === 1 ? uno : molti);
const MESI = { gennaio: "January", febbraio: "February", marzo: "March", aprile: "April", maggio: "May", giugno: "June", luglio: "July",
  agosto: "August", settembre: "September", ottobre: "October", novembre: "November", dicembre: "December" };

// frasi con numeri e nomi: [espressione, funzione che scrive la frase inglese]; t() traduce i pezzi che sono a loro volta voci
const MODELLI_EN = [
  [/^(\d+) (?:passaggio letto|passaggi letti) in (\d+) (?:documento|documenti)(?:, (\d+) (?:citato|citati) nella risposta)?\.( Un clic su «sì» o «no» corregge la pertinenza\.)?$/,
    (m) => `${m[1]} ${pl(m[1], "passage", "passages")} read in ${m[2]} ${pl(m[2], "document", "documents")}` +
      (m[3] ? `, ${m[3]} cited in the answer.` : ".") + (m[4] ? " Click “yes” or “no” to correct relevance." : "")],
  [/^(\d+) (?:passaggio citato|passaggi citati) nella risposta\.$/, (m) => `${m[1]} ${pl(m[1], "passage", "passages")} cited in the answer.`],
  [/^(\d+) (?:passaggio mostrato|passaggi mostrati)$/, (m) => `${m[1]} ${pl(m[1], "passage", "passages")} shown`],
  [/^(\d+) (?:passaggio|passaggi) senza data\.$/, (m) => `${m[1]} ${pl(m[1], "passage", "passages")} without a date.`],
  [/^(\d+) di (\d+) passaggi letti$/, (m) => `${m[1]} of ${m[2]} passages read`],
  [/^(\d+) (pertinente|pertinenti) finora$/, (m) => `${m[1]} relevant so far`],
  [/^(\d+) (riga|righe)$/, (m) => `${m[1]} ${pl(m[1], "line", "lines")}`],
  [/^(\d+) (?:documento|documenti)$/, (m) => `${m[1]} ${pl(m[1], "document", "documents")}`],
  [/^(\d+) righe con queste forme$/, (m) => `${m[1]} lines with these forms`],
  [/^(\d+) min$/, (m) => `${m[1]} min`],
  [/^circa (\d+) min alla fine della lettura$/, (m) => `about ${m[1]} min until reading ends`],
  [/^circa (.+), dalle ricerche passate del progetto$/, (m) => `about ${m[1].replace("ore", "hours")}, based on the project's past searches`],
  [/^Quote finite: riprovo tra (\d+:\d+) \(alle (.+)\)\.$/, (m) => `Quota exhausted: retrying in ${m[1]} (at ${m[2]}).`],
  [/^Nuovo tentativo: (.+)\.$/, (m) => `Next attempt: ${m[1].replace(" del ", " on ")}.`],
  [/^Modello: (.+)\.$/, (m) => `Model: ${m[1]}.`],
  [/^Modelli: (.+)\.$/, (m) => `Models: ${m[1].replace(/\bsmistamento\b/g, "sorting").replace(/\blettura\b/g, "reading").replace(/\brisposta\b/g, "answer")}.`],
  [/^Ricerca avviata: (.+)\.$/, (m) => `Search started: ${m[1]}.`],
  [/^Ricerca finita: «(.+)»\. La trovi tra i recenti\.$/, (m) => `Search finished: “${m[1]}”. You'll find it under Recent.`],
  [/^Ricerca: (.+)\.$/, (m) => `Search: ${m[1]}.`],
  [/^Cerca «(.+)» nelle fonti$/, (m) => `Search the sources for “${m[1]}”`],
  [/^Cerco «(.+)» in queste forme del nome:$/, (m) => `Searching for “${m[1]}” in these name forms:`],
  [/^Non c'è ancora una scheda per «(.+)»: cerco nelle fonti le forme attestate\.$/, (m) => `There is no card for “${m[1]}” yet: looking for its attested forms in the sources.`],
  [/^Cerco nelle fonti altre forme di «(.+)», per una scheda nuova\.$/, (m) => `Looking for other forms of “${m[1]}” in the sources, for a new card.`],
  [/^Nessuna forma di «(.+)» compare nelle fonti\.(.*)$/, (m) => `No form of “${m[1]}” appears in the sources.${m[2].replace("Non attestate:", "Not attested:")}`],
  [/^Cerco le forme in tutte le fonti \(di solito da 10 a 30 secondi\)… (\d+) s$/, (m) => `Searching all sources for the forms (usually 10 to 30 seconds)… ${m[1]} s`],
  [/^(\d+) forme trovate: accendi quelle giuste\.$/, (m) => `${m[1]} forms found: switch on the right ones.`],
  [/^Scartate l'altra volta \((\d+)\): restano spente$/, (m) => `Rejected last time (${m[1]}): they stay off`],
  [/^Non attestate \(non entrano nella scheda\): (.+)$/, (m) => `Not attested (not added to the card): ${m[1]}`],
  [/^Scheda «(.+)» creata: (\d+) (?:forma|forme)(?:, (\d+) (?:ambigua|ambigue))?\.$/, (m) => `Card “${m[1]}” created: ${m[2]} ${pl(m[2], "form", "forms")}` + (m[3] ? `, ${m[3]} ambiguous.` : ".")],
  [/^Scheda «(.+)» creata\.$/, (m) => `Card “${m[1]}” created.`],
  [/^La scheda «(.+)» esiste già$/, (m) => `The card “${m[1]}” already exists`],
  [/^Uso la scheda esistente «(.+)»\.$/, (m) => `Using the existing card “${m[1]}”.`],
  [/^(.+): (ambigua|non ambigua)\.$/, (m) => `${m[1]}: ${m[2] === "ambigua" ? "ambiguous" : "not ambiguous"}.`],
  [/^Forma «(.+)», (\d+) righe$/, (m) => `Form “${m[1]}”, ${m[2]} lines`],
  [/^Fonti \((\d+) (?:documento|documenti)\)$/, (m) => `Sources (${m[1]} ${pl(m[1], "document", "documents")})`],
  [/^Apri la fonte, p\. (.+)$/, (m) => `Open the source, p. ${m[1]}`],
  [/^Prove: documenti, passaggi(?: \((\d+)\))?, dati e inferenze$/, (m) => `Evidence: documents, passages${m[1] ? ` (${m[1]})` : ""}, data and inferences`],
  [/^riga (\d+)$/, (m) => `line ${m[1]}`],
  [/^Pertinente: (.+)\. Correggi in (sì|no)$/, (m) => `Relevant: ${t(m[1])}. Correct to ${t(m[2])}`],
  [/^Correggi: (pertinente|non pertinente) \(R\)$/, (m) => `Correct: ${t(m[1])} (R)`],
  [/^Passaggio segnato come (pertinente|non pertinente)\.$/, (m) => `Passage marked as ${t(m[1])}.`],
  [/^Passaggi per (mese|anno): scegli un periodo$/, (m) => `Passages per ${m[1] === "mese" ? "month" : "year"}: choose a period`],
  [/^(.+): (\d+) (?:passaggio|passaggi), (\d+) pertinenti$/, (m) => `${data(m[1])}: ${m[2]} ${pl(m[2], "passage", "passages")}, ${m[3]} relevant`],
  [/^(.+): (\d+) letti, (\d+) pertinenti$/, (m) => `${data(m[1])}: ${m[2]} read, ${m[3]} relevant`],
  [/^Rispetto alla risposta del (.+?): (.+)\.$/, (m) => `Compared with the answer of ${m[1]}: ${m[2].split(", ").map(t).join(", ")}.`],
  [/^(\d+) (?:passaggio nuovo|passaggi nuovi)$/, (m) => `${m[1]} new ${pl(m[1], "passage", "passages")}`],
  [/^(\d+) non più (?:citato|citati)$/, (m) => `${m[1]} no longer cited`],
  [/^Uguale alla risposta del (.+): stessi passaggi citati\.$/, (m) => `Same as the answer of ${m[1]}: the same passages cited.`],
  [/^Non era citato nella risposta del (.+)$/, (m) => `Not cited in the answer of ${m[1]}`],
  [/^Il (\d\d\/\d\d\/\d{4}.*)$/, (m) => `On ${m[1]}`],
  [/^Esporto: (.+)\.$/, (m) => `Exporting: ${t(m[1])}.`],
  [/^(\d[\d,.]*(?: mila| mln)?) (?:richiesta|richieste) oggi$/, (m) => `${num(m[1])} ${pl(m[1], "request", "requests")} today`],
  [/^Consumo di oggi: (\d+) richieste, (\d+) token\. Dettagli$/, (m) => `Today's usage: ${m[1]} requests, ${m[2]} tokens. Details`],
  [/^(\d+) richieste · (.+) token letti, (.+) scritti(?: · (.+) dalla cache)?$/, (m) => `${m[1]} requests · ${num(m[2])} tokens read, ${num(m[3])} written` + (m[4] ? ` · ${num(m[4])} from cache` : "")],
  [/^(\d+) richieste · (.+) token$/, (m) => `${m[1]} requests · ${num(m[2])} tokens`],
  [/^(\d+) · (.+) token$/, (m) => `${m[1]} · ${num(m[2])} tokens`],
  [/^da (\d+) a (\d+) al modello \(lotti di (\d+) passaggi\)$/, (m) => `${m[1]} to ${m[2]} to the model (batches of ${m[3]} passages)`],
  [/^(\d+) passaggi di ricerche precedenti: si riusano$/, (m) => `${m[1]} passages from previous searches: they are reused`],
  [/^(.+), durata (\d+) min$/, (m) => `${data(m[1])}, took ${m[2]} min`],
  [/^Nessun documento sospetto tra i (\d+) esaminati\.$/, (m) => `No suspect documents among the ${m[1]} checked.`],
  [/^(\d+) (?:documento sospetto|documenti sospetti) su (\d+)(?: \(qui i (\d+) peggiori\))?\.$/, (m) => `${m[1]} suspect ${pl(m[1], "document", "documents")} out of ${m[2]}` + (m[3] ? ` (the ${m[3]} worst shown here)` : "") + "."],
  [/^confidenza dell'OCR ([\d.]+)$/, (m) => `OCR confidence ${m[1]}`],
  [/^(\d+)% di parole illeggibili$/, (m) => `${m[1]}% unreadable words`],
  [/^Rifare l'OCR di «(.+)»\?$/, (m) => `Redo the OCR of “${m[1]}”?`],
  [/^OCR di «(.+)» avviato: lo seguo io, non serve che aspetti\.$/, (m) => `OCR of “${m[1]}” started: I'll follow it, no need to wait.`],
  [/^Lingue dell'OCR per (.+)$/, (m) => `OCR languages for ${m[1]}`],
  [/^Il testo si rifà dall'originale con (.+) e sostituisce quello di adesso; serie, data, numero, titolo e autore restano\. I passaggi già letti restano nell'archivio; la prossima ricerca trova anche le forme che l'OCR vecchio nascondeva\.$/,
    (m) => `The text is redone from the original with ${m[1]} and replaces the current one; series, date, issue, title and author are kept. Passages already read stay in the archive; the next search also finds forms the old OCR hid.`],
  [/^Passare a «(.+)»\?$/, (m) => `Switch to “${m[1]}”?`],
  [/^Progetto in uso: (.+)\.$/, (m) => `Project in use: ${m[1]}.`],
  [/^Usa il progetto (.+)$/, (m) => `Use the project ${m[1]}`],
  [/^Altre azioni per «(.+)»$/, (m) => `More actions for “${m[1]}”`],
  [/^Cerca di nuovo le menzioni di (.+)$/, (m) => `Search again for mentions of ${m[1]}`],
  [/^Eliminare «(.+)» dai recenti\?$/, (m) => `Remove “${m[1]}” from Recent?`],
  [/^«(.+)» eliminata dai recenti\.$/, (m) => `“${m[1]}” removed from Recent.`],
  [/^Nessuna ricerca con «(.+)»\.$/, (m) => `No searches with “${m[1]}”.`],
  [/^(\d+) documenti · (.+)$/, (m) => `${m[1]} documents · ${data(m[2])}`],
  [/^(\d+) ricerche · ultima (.+)$/, (m) => `${m[1]} searches · latest ${data(m[2])}`],
  [/^Prova di collegamento con «(.+)»…$/, (m) => `Testing the connection with “${m[1]}”…`],
  [/^Modello in uso: (.+)\.$/, (m) => `Model in use: ${m[1]}.`],
  [/^(\d+)% della finestra$/, (m) => `${m[1]}% of the window`],
  [/^Il lavoro è finito con codice (\d+)(.*)\.$/, (m) => `The job ended with code ${m[1]}${m[2]}.`],
  [/^Avviare la ricerca con (.+)\?$/, (m) => `Start the search with ${m[1].replace(" e ", " and ")}?`],
  [/^Citazioni: (\d+) trovate nei risultati degli strumenti(?:, (\d+) non trovate \(in rosso\))?$/, (m) => `Citations: ${m[1]} found in the tools' results` + (m[2] ? `, ${m[2]} not found (in red)` : "")],
  [/^In uso: (.+)\.$/, (m) => `In use: ${m[1]}.`],
  [/^(\d+) documenti nel progetto\.$/, (m) => `${m[1]} documents in the project.`],
  [/^La cartella si crea in (.+)\.$/, (m) => `The folder is created in ${m[1]}.`],
  [/^Impostazioni di (.+)$/, (m) => `${m[1]} settings`],
  [/^Usa per (smistamento|analisi|sintesi)$/, (m) => `Use for ${{ smistamento: "sorting", analisi: "analysis", sintesi: "synthesis" }[m[1]]}`],
  [/^Usa (.+)$/, (m) => `Use ${t(m[1])}`],
  [/^Tesseract tiene le lingue in (.+), dove servono i diritti di amministratore\.$/, (m) => `Tesseract keeps its languages in ${m[1]}, which needs administrator rights.`],
  [/^Pressmark può usare una cartella delle lingue tua, (.+): ci copia le (\d+) lingue già installate \(circa (\d+) MB\) e da lì installa le nuove\.(.*)$/,
    (m) => `Pressmark can use a language folder of your own, ${m[1]}: it copies the ${m[2]} languages already installed (about ${m[3]} MB) and installs new ones there.${m[4]}`],
  [/^modelli: (.+)$/, (m) => `models: ${m[1]}`],
  [/^(.+) \((.+)\) per ((?:smistamento|analisi|sintesi)(?:, (?:smistamento|analisi|sintesi))*)$/,
    (m) => `${m[1]} (${m[2]}) for ${m[3].replace("smistamento", "sorting").replace("analisi", "analysis").replace("sintesi", "synthesis")}`],
  [/^(.+) \(importazione dei PDF\)$/, (m) => `${m[1]} (PDF import)`],
  [/^Altri fornitori \((\d+)\)$/, (m) => `Other providers (${m[1]})`],
  [/^Modelli di (.+)$/, (m) => `${m[1]} models`],
  [/^Modelli offerti da (.+)$/, (m) => `Models offered by ${m[1]}`],
  [/^(.+) non risponde$/, (m) => `${m[1]} is not responding`],
  [/^Impostata, nella variabile (.+)\.$/, (m) => `Set, in the variable ${m[1]}.`],
  [/^Pressmark usa la chiave di (.+)\.$/, (m) => `Pressmark uses the key in ${m[1]}.`],
  // glossario modificabile
  [/^(\d+) (?:passaggio letto|passaggi letti), (\d+) (?:pertinente|pertinenti)(?: · (.+))?$/,
    (m) => `${m[1]} ${pl(m[1], "passage", "passages")} read, ${m[2]} relevant` + (m[3] ? ` · ${m[3]}` : "")],
  [/^(\d+) (?:forma suggerita|forme suggerite)$/, (m) => `${m[1]} suggested ${pl(m[1], "form", "forms")}`],
  [/^Forme suggerite dai passaggi letti \((\d+)\)$/, (m) => `Forms suggested by the passages read (${m[1]})`],
  [/^(\d+) (?:volta|volte)$/, (m) => `${m[1]} ${pl(m[1], "time", "times")}`],
  [/^(\d+) righe in tutto \(una riga con due forme conta due volte\)\. Clic sul nome: ambigua; sul numero: un esempio\.$/,
    (m) => `${m[1]} lines in all (a line with two forms counts twice). Click the name: ambiguous; the number: an example.`],
  [/^Togli «(.+)» dalle collegate$/, (m) => `Remove “${m[1]}” from related`],
  [/^Togli «(.+)»$/, (m) => `Remove “${m[1]}”`],
  [/^Unisci «(.+)» a «(.+)»$/, (m) => `Merge “${m[1]}” into “${m[2]}”`],
  [/^Unisci «(.+)» a$/, (m) => `Merge “${m[1]}” into`],
  [/^Unire «(.+)» a «(.+)»\?$/, (m) => `Merge “${m[1]}” into “${m[2]}”?`],
  [/^Forme, forme ambigue e collegate di «(.+)» passano a «(.+)», e così le letture dell'archivio; «.+» si toglie dal glossario\. Una copia del glossario di oggi resta accanto al file\.$/,
    (m) => `Forms, ambiguous forms and related cards of “${m[1]}” move to “${m[2]}”, and so do the archive's readings; “${m[1]}” is removed from the glossary. Today's copy of the glossary stays next to the file.`],
  [/^Eliminare la scheda «(.+)»\?$/, (m) => `Delete the card “${m[1]}”?`],
  [/^La scheda esce dal glossario e dalle collegate delle altre\. I passaggi già letti restano nell'archivio, e una copia del glossario di oggi resta accanto al file\.$/,
    () => "The card leaves the glossary and the related lists of the others. Passages already read stay in the archive, and today's copy of the glossary stays next to the file."],
  [/^Controllo del glossario: (.+)$/, (m) => `Glossary check: ${m[1].replace(/(\d+) error[ei]/, (x, n) => `${n} ${pl(n, "error", "errors")}`)
    .replace(/(\d+) avvis[oi]/, (x, n) => `${n} ${pl(n, "warning", "warnings")}`).replace(/(\d+) not[ae]/, (x, n) => `${n} ${pl(n, "note", "notes")}`)}`],
  [/^(.+): (.+) righe\. Mostra un esempio$/, (m) => `${m[1]}: ${m[2].replace("righe non ancora contate", "lines not yet counted")} lines. Show an example`],
  [/^Altri campi, che restano come sono: (.+)\.$/, (m) => `Other fields, kept as they are: ${m[1]}.`],
  [/^Scheda «(.+)» salvata\.$/, (m) => `Card “${m[1]}” saved.`],
  [/^Scheda rinominata in «(.+?)»\.(?: (\d+) letture dell'archivio passano a «.+»\.)?$/,
    (m) => `Card renamed to “${m[1]}”.` + (m[2] ? ` ${m[2]} archive readings move to “${m[1]}”.` : "")],
  [/^«(.+)» è ora parte di «(.+?)»\.(?: (\d+) letture dell'archivio passano a «.+»\.)?$/,
    (m) => `“${m[1]}” is now part of “${m[2]}”.` + (m[3] ? ` ${m[3]} archive readings move to “${m[2]}”.` : "")],
  [/^Scheda «(.+)» eliminata\..*$/, (m) => `Card “${m[1]}” deleted. Passages already read stay in the archive; today's copy of the glossary is next to the file.`],
  [/^(.+): (aggiunta alla scheda|scartata)\.$/, (m) => `${m[1]}: ${m[2] === "scartata" ? "rejected" : "added to the card"}.`],
  [/^Segnaposti sconosciuti: (.+)$/, (m) => `Unknown placeholders: ${m[1]}`],
  [/^Nel modello restano parti non riconosciute: (.+)$/, (m) => `Unrecognised parts remain in the template: ${m[1]}`],
  [/^Quelli che esistono: (.+)$/, (m) => `Available ones: ${m[1]}`],
  [/^Con la pagina 12 come esempio\. Documento: (.+)\.$/, (m) => `With page 12 as an example. Document: ${m[1]}.`],
  [/^(.+) \(evoluzione\)$/, (m) => `${m[1]} (evolution)`],
  [/^(.+) \(senza scheda\)$/, (m) => `${m[1]} (no card)`],
  // prevenzione: controllo prima di salvare, correzioni automatiche
  [/^Correggi tutto ciò che si corregge da sé \((\d+)\)$/, (m) => `Fix everything that fixes itself (${m[1]})`],
  [/^Segna come ambigue: (.+)$/, (m) => `Mark as ambiguous: ${m[1]}`],
  [/^Togli dalle forme ambigue: (.+)$/, (m) => `Remove from the ambiguous forms: ${m[1]}`],
  [/^Sposta «(.+)» in forma_estesa$/, (m) => `Move “${m[1]}” to forma_estesa`],
  [/^Togli «(.+)» \(ripete il nome della scheda\)$/, (m) => `Remove “${m[1]}” (it repeats the card's name)`],
  [/^(\d+) (?:correzione fatta|correzioni fatte)\.$/, (m) => `${m[1]} ${pl(m[1], "fix", "fixes")} made.`],
  [/^(.+): forma breve, segnata ambigua\.$/, (m) => `${m[1]}: short form, marked ambiguous.`],
  [/^(.*?)(?:Rifai la ricerca: si leggono solo i passaggi delle forme nuove\. )?(.+): forma breve, segnata come ambigua \(il modello ne controlla sempre i passaggi\)\.$/,
    (m) => `Run the search again: only the passages of the new forms are read. ${m[2]}: short form, marked ambiguous (the model always checks its passages).`],
  [/^campo nome_completo: .*$/, () => "field nome_completo: the full name goes in forma_estesa (or nowhere, if it repeats the card's name)"],
  [/^campo forma_italiana: .*$/, () => "field forma_italiana: it is now called forma_estesa"],
  [/^esiste già una scheda «(.+)»$/, (m) => `a card “${m[1]}” already exists`],
  // problemi delle schede (schede.controlla)
  [/^campo sconosciuto «(.+)»$/, (m) => `unknown field “${m[1]}”`],
  [/^forme brevi o generiche non dichiarate in forme_ambigue: (.+)$/, (m) => `short or generic forms not declared in forme_ambigue: ${m[1]}`],
  [/^note vuote: manca la descrizione dell'entità \(chi è, periodo, omonimi\)$/, () => "empty notes: the entity's description is missing (who, period, namesakes)"],
  [/^manca il campo tipo \((.+)\)$/, (m) => `the type field is missing (${m[1]})`],
  [/^forma ambigua «(.+)» non compare tra le varianti: .*$/, (m) => `ambiguous form “${m[1]}” is not among the forms: the search does not look for it (add it to the forms, or remove it from the ambiguous ones)`],
  [/^stessa forma in più schede: «(.+)» .*$/, (m) => `same form in several cards: “${m[1]}” (merge the cards, or leave the form to one card and declare it ambiguous)`],
  [/^entità collegata «(.+)» senza scheda$/, (m) => `related entity “${m[1]}” has no card`],
  [/^le schede hanno gli stessi (\d+) passaggi nell'archivio.*$/, (m) => `the cards have the same ${m[1]} passages in the archive: probably the same entity`],
  // «Etichetta: valore» con un'etichetta del catalogo, e «profilo» dentro un nome composto
  [/^([^:]{2,40}): (.+)$/, (m) => { const e = t(m[1]); return e !== m[1] ? `${e}: ${t(m[2])}` : undefined; }],
  [/^(.*)\bprofilo\b(.*)$/, (m) => `${m[1]}profile${m[2]}`],
  [/^Altre azioni per (.+)$/, (m) => `More actions for ${m[1]}`],
  [/^Modello (.+) (acceso|spento)$/, (m) => `Model ${m[1]} ${m[2] === "acceso" ? "on" : "off"}`],
  [/^filtra tra (\d+) modelli$/, (m) => `filter among ${m[1]} models`],
  [/^Filtra i modelli di (.+)$/, (m) => `Filter ${m[1]} models`],
  [/^Manca: la variabile (.+) non è impostata\. Con la chiave compaiono qui i modelli di (.+)\.$/,
    (m) => `Missing: the variable ${m[1]} is not set. With the key, ${m[2]} models appear here.`],
];

// le date scritte in italiano dall'interfaccia (aprile 1964, 4 nov, ieri, 20:20) in inglese
function data(s) {
  return String(s).replace(/\b(gennaio|febbraio|marzo|aprile|maggio|giugno|luglio|agosto|settembre|ottobre|novembre|dicembre)\b/g, (x) => MESI[x])
    .replace(/\bieri\b/g, "yesterday").replace(/\boggi\b/g, "today").replace(/\balle\b/g, "at");
}
function num(s) { return String(s).replace(" mila", "k").replace(" mln", "M").replace(",", "."); }

const DIZ = LINGUA === "en" ? new Map(Object.entries(EN).map(([k, v]) => [k.replace(/\s+/g, " ").trim(), v])) : null;
const MANCATE = new Set();

// la traduzione di un testo, o il testo com'è
function t(s) {
  if (!DIZ || !s) return s;
  const pulito = s.replace(/\s+/g, " ").trim();
  if (!pulito || MANCATE.has(pulito) || !/[a-zà-ù]/i.test(pulito)) return s;
  let fatto = DIZ.get(pulito);
  if (fatto === undefined) {
    for (const [rx, f] of MODELLI_EN) {
      const m = rx.exec(pulito);
      if (m) { fatto = f(m); if (fatto !== undefined) break; }
    }
  }
  if (fatto === undefined) {
    // «Nome · dettaglio», «Etichetta: valore»: si traducono i pezzi che sono voci
    const pezzi = pulito.split(/( · )/);
    if (pezzi.length > 1) {
      const tradotti = pezzi.map((p) => (p === " · " ? p : t(p)));
      if (tradotti.some((p, i) => p !== pezzi[i])) fatto = tradotti.join("");
    }
  }
  if (fatto === undefined) { MANCATE.add(pulito); return s; }
  const prima = s.match(/^\s*/)[0];
  const dopo = s.match(/\s*$/)[0];
  return prima + fatto + dopo;
}

const ATTRIBUTI = ["placeholder", "title", "aria-label", "aria-valuetext"];

function escluso(n) {
  const e = n.nodeType === 1 ? n : n.parentElement;
  return !e || !!e.closest(NON_TRADURRE) || e.tagName === "SCRIPT" || e.tagName === "STYLE";
}

function traduciNodo(radice) {
  if (!DIZ) return;
  if (radice.nodeType === 3) {
    if (!escluso(radice)) {
      const v = t(radice.nodeValue);
      if (v !== radice.nodeValue) radice.nodeValue = v;
    }
    return;
  }
  if (radice.nodeType !== 1 && radice.nodeType !== 9 && radice.nodeType !== 11) return;
  const passa = document.createTreeWalker(radice, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.nodeType === 1 && n.matches(NON_TRADURRE) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  const nodi = [];
  if (radice.nodeType === 1 && !escluso(radice)) nodi.push(radice);
  else if (radice.nodeType === 1) return;
  for (let n = passa.nextNode(); n; n = passa.nextNode()) nodi.push(n);
  for (const n of nodi) {
    if (n.nodeType === 3) {
      const v = t(n.nodeValue);
      if (v !== n.nodeValue) n.nodeValue = v;
    } else {
      for (const a of ATTRIBUTI) {
        const v = n.getAttribute(a);
        if (v) { const w = t(v); if (w !== v) n.setAttribute(a, w); }
      }
    }
  }
}

if (LINGUA === "en") {
  document.documentElement.lang = "en";
  const osserva = new MutationObserver((cambi) => {
    for (const c of cambi) {
      if (c.type === "childList") c.addedNodes.forEach(traduciNodo);
      else if (c.type === "characterData") traduciNodo(c.target);
      else if (c.type === "attributes" && !escluso(c.target)) {
        const v = c.target.getAttribute(c.attributeName);
        if (v) { const w = t(v); if (w !== v) c.target.setAttribute(c.attributeName, w); }
      }
    }
  });
  document.addEventListener("DOMContentLoaded", () => {
    traduciNodo(document.body);
    document.title = t(document.title);
    osserva.observe(document.body, { childList: true, subtree: true, characterData: true, attributes: true,
      attributeFilter: ATTRIBUTI });
  });
}

return { lingua: LINGUA, scegli: scegliLingua, traduci: t };
})();

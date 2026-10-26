# source-search per la chat di Claude (claude.ai, Claude Desktop)

Versione minore di AIrchivist: trova tutte le occorrenze di una persona o di un ente in un **corpus piccolo**
caricato nella conversazione (file .txt, PDF con testo, esportazioni PAGE/ALTO, anche dentro archivi .zip) e
risponde con i passaggi originali, la traduzione e il riferimento in stile Chicago. Serve a provare il metodo su
pochi documenti; per un corpus grande e persistente si usa il sistema principale.

## Installazione

1. In *Settings → Capabilities* attiva *Code execution and file creation* (nella nuova disposizione: *Create and
   edit files*).
2. In *Customize → Skills* scegli «+», poi *Create skill → Upload a skill*, e carica `source-search-claude.zip`.
3. Attiva la skill nell'elenco.

(Nomi dei menu come nella guida in inglese di Anthropic; nell'interfaccia italiana possono essere tradotti.)

Le skill caricate su claude.ai sono personali; se usi anche Claude Code con lo stesso account, vi arrivano da
sole.

## Uso

In una chat nuova carica le fonti (anche uno zip) e chiedi, per esempio, «Cosa dicono queste fonti riguardo
Enrico Berlinguer?». L'assistente apre le fonti, crea con te i profili delle serie e la scheda dell'entità
(solo con forme attestate e confermate da te), estrae tutti i passaggi, li legge a lotti e ti consegna
`risposta_<entità>.md`, `entities.ini` e `series.ini`. Ricaricando `entities.ini` e `series.ini` in una chat
successiva, schede e serie non si rifanno.

## Limiti

- Il progetto vive solo nella conversazione: ogni chat riparte dalle fonti caricate, le letture non si
  conservano.
- Solo lo strato di testo dei PDF: le scansioni senza testo restano fuori, salvo ambienti con OCR.
- Senza PyMuPDF i PDF si leggono con pypdf.
- I passaggi li legge il modello della chat: i token contano sui limiti del piano (per circa 60 passaggi,
  120-130 mila token).

## Sistema principale

AIrchivist: https://github.com/AMI-AIM/AIrchivist (motore in Python, indice persistente, archivio delle letture,
modelli scelti dal ricercatore, anche gratuiti o locali). Licenza: GNU AGPL v3 (`LICENSE`).

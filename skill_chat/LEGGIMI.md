# Skill ricerca-fonti per la chat di Claude

Versione della ricerca delle occorrenze che funziona nella chat di Claude (claude.ai, Claude Desktop) su un
**corpus piccolo** caricato nella conversazione: file .txt, PDF con testo, esportazioni PAGE/ALTO, anche dentro
archivi .zip. Indicativamente fino a qualche migliaio di documenti o qualche decina di MB: per corpus più grandi
si usa la pipeline locale.

## Installazione

1. Costruisci lo zip, dalla cartella `pipeline`:

   ```
   python crea_skill_chat.py
   ```

   Lo zip esce in `dist/ricerca-fonti.zip` e contiene `SKILL.md` e i moduli del motore che servono.
2. Su claude.ai: *Impostazioni → Funzionalità*, attiva l'esecuzione del codice e la creazione di file, poi
   carica lo zip in *Skill*.

## Uso

In una chat nuova carica le fonti (anche uno zip) e chiedi, per esempio, «Cosa dicono queste fonti riguardo
Enrico Berlinguer?». Claude:

1. apre il corpus e costruisce l'indice;
2. crea con te i profili delle serie (come citarle) e importa i PDF;
3. cerca le forme del nome attestate e crea la scheda dell'entità dopo la tua conferma;
4. estrae tutti i passaggi, li legge a lotti e scrive la risposta in otto sezioni;
5. ti consegna `risposta_<entità>.md`, `entita.ini` e `serie.ini`.

Ricaricando `entita.ini` e `serie.ini` in una chat successiva insieme alle fonti, schede e serie non si
rifanno. Le letture dei passaggi non si conservano tra una chat e l'altra.

## Limiti

- Il progetto vive solo nella conversazione: ogni chat riparte dalle fonti caricate.
- Le scansioni senza strato di testo richiedono Tesseract, che l'ambiente della chat di solito non ha: quei
  file non vengono importati e Claude lo dice.
- Senza PyMuPDF i PDF si leggono con pypdf (solo lo strato di testo).
- Leggendo Claude, i token contano sui limiti del piano: per circa 60 passaggi, 120-130 mila token.

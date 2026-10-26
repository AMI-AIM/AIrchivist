---
name: source-search
description: Trova tutte le occorrenze di una persona, di un ente (partito, Stato, testata) o di un gruppo di soggetti nelle fonti primarie caricate nella conversazione (file .txt, PDF, esportazioni PAGE/ALTO, anche in .zip) o in un progetto AIrchivist sul computer, e risponde con i passaggi originali, la traduzione e il riferimento in stile Chicago. Usala quando l'utente chiede che cosa dicono le fonti su qualcuno o qualcosa, chi era, come compare, quando è nominato. Nella chat è adatta a corpus piccoli.
---

# Ricerca delle occorrenze nelle fonti

Il motore (Python, solo libreria standard; PyMuPDF o pypdf per i PDF) trova i passaggi con espressioni regolari
su tutte le fonti: l'esaustività dipende da lui e dalle forme della scheda, non da te. Tu crei schede e serie con
l'utente, leggi i passaggi (pertinenza, traduzione, sintesi) e scrivi la sintesi finale. Le citazioni originali le
sceglie il motore e le verifica sul testo: non riscriverle.

Non sostituire i passi del motore con script tuoi (decodifiche, OCR, estrazioni) e non installare pacchetti
senza chiedere: se un passo non funziona, dillo all'utente e chiedi come procedere.

## 0. Ambiente

```
python <cartella di questa skill>/scripts/chat.py ambiente
```

Con `PYTHONIOENCODING=utf-8`. Il risultato dice dove ti trovi (`modo`):

- `sistema`: c'è un'installazione completa di AIrchivist (`motore`, con il progetto in uso e l'archivio unico
  delle letture). Usa il **suo** motore, non la copia nella skill: d'ora in poi `M` = la cartella `motore`
  indicata. Salta i passi 1-3: fonti e serie si aggiungono con gli strumenti del sistema (`importa.py`, vedi
  `docs/user_guide.it.md` del sistema); `apri`, `importa`, `serie-crea` e `consegna` lì non si usano. I passaggi già
  letti si riprendono dall'archivio; per una prova che non deve toccarlo, `prepara ... --cartella prova_<nome>`.
- `conversazione`: ci sono file caricati (`caricati`). `M` = `<cartella di questa skill>/scripts`. Il progetto è
  temporaneo, vive per tutta la conversazione e non si conserva; nessun archivio delle letture.
- `nessuna_fonte`: chiedi all'utente di caricare le fonti. Se lavori sul suo computer, può indicarti invece una
  cartella: `python M/chat.py apri <cartella>`, con `M` = `<cartella di questa skill>/scripts`.

Il risultato dice anche con che cosa si leggono i PDF (`pdf`: PyMuPDF, pypdf o nessuno) e se c'è l'OCR (`ocr`).
Tutti i comandi che seguono sono `python M/chat.py <comando> ...`.

## 1. Apertura delle fonti (solo progetto temporaneo)

```
python M/chat.py apri [file o cartelle]
```

Senza argomenti legge i file caricati nella conversazione; estrae gli zip e costruisce l'indice. Riferisci
all'utente numero di fonti, serie e dimensione. Il risultato elenca:
- `serie_senza_profilo`: serie presenti nelle intestazioni dei .txt ma senza profilo (passo 2);
- `da_importare`: PDF, testi senza intestazione, esportazioni PAGE/ALTO, immagini (passo 3);
- `avviso`: fonti troppo grandi per la conversazione; proponi di restringere periodo o fonti.

Se l'utente carica altri file più avanti, rilancia `apri`. Se carica `entities.ini` o `series.ini` di un progetto
precedente, `apri` li usa.

## 2. Serie (solo progetto temporaneo)

Ogni serie di fonti (una testata, una raccolta, un libro, un fondo d'archivio) ha un profilo che dice come
citarla. Per creare una serie chiedi all'utente ciò che non si ricava dalle intestazioni o dai documenti; non
inventare dati bibliografici.

```
python M/chat.py serie-crea "Nome" --tipo periodico|articolo|volume|archivio --lingua it \
  [--cartella riviste/nome] [--sigla XX] [--nota-limiti "frase per la sezione Limiti"] \
  [--campo "archivio=Nome dell'archivio"] [--campo "chicago=..."] [--campo "pagina_regex=..."]
```

Bastano nome, tipo e lingua. Tipi: `periodico` (fascicoli, un file per numero), `articolo` (articoli di una
rivista, un file per articolo con autore e titolo), `volume` (libro o raccolta), `archivio` (documenti d'archivio
datati; `--campo "archivio=..."` e `--campo "fondo=..."` per archivio e fondo). `--cartella` serve solo per una
cartella già esistente (quella indicata in `serie_senza_profilo`); senza, vale `riviste/<nome>`, `volumi/<nome>` o
`archivi/<nome>`. La citazione Chicago (nota) si genera dal tipo: rivista «Nome Cognome, “Titolo,” *Rivista* 121,
no. 2 (aprile 2016): 377», quotidiano «*Giornale*, 12 gennaio 1967, 3», libro «Nome Cognome, *Titolo*, vol. 2
(Luogo: Editore, 1971), 45», archivio «Nome Cognome, “Titolo,” 3 marzo 1971, fondo, archivio, 12». Il campo
`chicago` la sostituisce solo per una forma particolare (segnaposto in `series_template.ini`). `python M/chat.py
serie` mostra i profili.
Nei periodici il testo dei PDF si legge per colonne (i giornali non mescolano più articoli diversi); per un
volume impaginato a più colonne aggiungi `--campo "ordine_lettura=colonne"`, per un periodico a colonna unica
con un'impaginazione insolita `--campo "ordine_lettura=pdf"`.

## 3. Importazione (solo progetto temporaneo)

```
python M/chat.py importa <file o cartella> --serie "Nome" [--data AAAA-MM-GG | AAAA-MM] \
  [--titolo "..."] [--autore "Cognome, Nome"] [--anno AAAA] [--luogo ...] [--editore ...] [--numero N] \
  [--prima-pagina N --da-pagina K] [--unisci]
```

Scrive il testo con l'intestazione e i marcatori di pagina (dalle etichette del PDF o dai numeri stampati,
anche dopo l'OCR) e aggiorna l'indice. Date: quella che il documento dà, alla precisione che dà; un documento
datato «November 1971» si importa con `--data 1971-11`, mai con un giorno inventato.

- PDF con testo: si leggono con PyMuPDF o, se manca, con pypdf (solo lo strato di testo). Se non c'è nessuno
  dei due (`pdf: nessuno`), dillo all'utente: può caricare i testi in .txt, oppure, se l'ambiente ha la rete,
  autorizzarti a installare pypdf.
- Scansioni senza testo: servono l'OCR (`ocr: true`) e i dati della lingua (`tesseract --list-langs`). Senza
  OCR quelle pagine restano fuori: dillo all'utente.
- **Strato di testo illeggibile** (l'importazione lo segnala: font senza tabella dei caratteri, caratteri a
  caso): le pagine vanno all'OCR, se c'è con la lingua; altrimenti restano fuori. Dillo all'utente e chiedigli
  se preferisce caricare i testi in .txt oppure installare un motore OCR, con una stima del tempo (circa 30
  secondi per pagina di giornale). Non procedere da solo.

Riferisci gli avvisi dell'importazione (OCR debole, pagine senza numero, strato illeggibile).

## 4. Scheda dell'entità

1. `python M/chat.py schede [filtro]` elenca le schede.
2. Se l'entità non ha una scheda: `python M/chat.py esplora "Nome" --indizi "paese; partito" \
   --candidate "forme in altre scritture"`. In `--candidate` metti le trascrizioni probabili (per il cinese,
   l'uso Xinhua). Proponi all'utente **solo le forme attestate** che il comando restituisce, con il numero di
   `menzioni` (non `totale`, che conta le righe), e chiedigli conferma.
3. `python M/chat.py scheda-crea "Nome" --varianti "forma; forma" --descrizione "chi è" \
   [--ambigue "forme brevi che possono indicare altri"] [--tipo persona|organizzazione|testata|stato|altro]`.
   Se il comando avvisa che una forma ambigua non sarà cercata, chiedi all'utente se aggiungerla alle varianti.

**Gruppi e categorie** («i partiti filo-cinesi», «i gruppi m-l europei»): non hanno un nome solo. Prima di
proporre le forme, guarda come le fonti chiamano quei soggetti, compresi i nomi dei singoli partiti e le grafie
d'epoca («Peiping», «pro-Peking», «splinter groups», «Communist Party (M-L) of Italy»), e verificale con
`esplora` o `cerca`. In un progetto temporaneo, se le fonti in tutto sono poche (`chat.py stato`: fino a circa
0,4 MB di testo), leggile per intero; altrimenti leggi indici, titoli e le parti che ne parlano.

`cerca "testo"` serve solo a verificare: il suo risultato non è una risposta.

## 5. Estrazione e lettura

```
python M/chat.py prepara "Nome" [--dal AAAA] [--al AAAA] [--fonti "Serie; Serie"] [--cartella prova_<nome>]
```

Scrive i passaggi da leggere in `results/searches/<cartella>/lotti/` del progetto. Riferisci numero di passaggi, stima
dei token e del tempo; oltre 150 passaggi chiedi prima di procedere e proponi di restringere periodo o fonti
(o, se l'ambiente lo permette, di affidare i lotti a sotto-assistenti, uno o due lotti ciascuno, con queste
stesse regole).

Leggi ogni `lotto_NN.md` per intero. Per ogni passaggio:

- **pertinente**: `sì` se le occorrenze tra ⟦ ⟧ si riferiscono davvero all'entità (anche solo in un elenco);
  `no` per omonimi, altre organizzazioni, usi generici; `incerto` se il testo non basta. Decidi su ciò che è
  scritto nel passaggio, non su ciò che sai dell'entità. La nota «forma inequivocabile» è un indizio, non una
  decisione.
- per `sì` e `incerto`:
  - `traduzione_it`: traduzione italiana fedele della sola FRASE DA TRADURRE, con i nomi del glossario;
    termini incerti tra parentesi quadre; vuota per le fonti in italiano (il lotto lo indica);
  - `sintesi_it`: 1-3 frasi su ciò che il passaggio dice esplicitamente dell'entità. Se il passaggio contiene
    più menzioni o più articoli, riassumile tutte. Date: la data dell'evento, non quella della fonte né quella
    del dispaccio; l'anno solo se il testo lo dà o si ricava con certezza; un fatto già avvenuto in un mese
    successivo a quello della fonte è dell'anno precedente, uno annunciato in un mese precedente dell'anno
    seguente; se non è certo, data senza anno e «(anno non indicato)». Nessuna conoscenza esterna;
  - `tipo_menzione` (delegazione/visita, citazione o sintesi di un articolo, messaggio/telegramma, notizia,
    elenco, altro), `altri_nominati` (nome e ruolo come risulta dal testo), `ruolo_entita`, `tono`
    (elogiativo, neutro, critico, non determinabile), `evento`, `nuove_varianti` (forme non già nella scheda);
- per le voci di sommario basta la pertinenza.

Scrivi le letture del lotto in `<cartella>/letture_NN.json`:

```json
[{"id": "...", "pertinente": "sì", "motivazione": "una frase", "tipo_menzione": "notizia",
  "traduzione_it": "...", "sintesi_it": "...", "nuove_varianti": [],
  "altri_nominati": [{"nome": "...", "ruolo": "..."}], "ruolo_entita": "", "tono": "neutro", "evento": ""},
 {"id": "...", "pertinente": "no", "motivazione": "omonimo: ..."}]
```

e registrale subito, prima del lotto successivo:

```
python M/chat.py registra <cartella> <cartella>/letture_NN.json --da "<il tuo id di modello>"
```

Le letture risultano dalla «sessione assistita» con il nome che dai in `--da`. Se il comando segnala passaggi
non registrati, correggi e registra di nuovo. Se dalla lettura (dei lotti o dei documenti, al passo 4)
emergono parti pertinenti che l'estrazione non ha preso, perché usano forme che la scheda non ha, proponi
all'utente quelle forme: confermate, aggiungile alla scheda (campo `varianti` in `entities.ini`) e rifai
`prepara`. Così anche quelle parti diventano passaggi con la citazione verificata.

## 6. Sintesi

```
python M/chat.py documenti <cartella>
```

Dall'elenco numerato scrivi `<cartella>/sintesi_sessione.json`:

```json
{"da": "<il tuo id di modello>",
 "dati_espliciti": [{"testo": "...", "rif": [1, 2]}],
 "inferenze": [{"testo": "...", "rif": [3], "fondatezza": "alta|media|bassa"}],
 "problemi_interpretativi": [{"testo": "...", "rif": [4]}],
 "risposta_finale": "1-3 paragrafi con i numeri dei documenti tra parentesi quadre"}
```

Solo ciò che l'elenco attesta; ogni voce con i numeri dei documenti (le voci senza vengono scartate). Dati in
ordine cronologico, con la data dell'evento; se il testo non la dà, «(notizia del <data del documento>)». Nei
problemi: omonimie, contraddizioni, identificazioni incerte, la stessa organizzazione con dirigenti diversi, la
stessa notizia in più fonti, parti censurate o illeggibili. Per ogni fonte di' se è primaria o secondaria e
quanto è attendibile (propaganda, analisi di un servizio avversario, dispaccio d'agenzia ripreso). Poi:

```
python M/chat.py sintesi <cartella> --domanda "<domanda dell'utente>" --sintesi-da <cartella>/sintesi_sessione.json
```

e, nel progetto temporaneo, `python M/chat.py consegna <cartella>`, che copia risposta, `entities.ini` e
`series.ini` dove l'utente può scaricarli.

Non modificare a mano la risposta prodotta: se contiene un errore, correggi la causa (scheda, serie, data
all'importazione, letture) e rigenera.

## 7. Risposta all'utente

Presenta la risposta (`risposta.md`, otto sezioni) senza ricostruirla: riassumi in testa la sezione 7. Nel
progetto temporaneo allega i file consegnati, che l'utente può ricaricare in una conversazione successiva per non
rifare schede e serie; nel sistema completo indica il percorso del file. Nelle citazioni ci si ferma alla
pagina: mai nomi di file né numeri di riga (stanno solo nella sezione 8). Le traduzioni si introducono con
«Traduzione:». Non usare la parola «corpus» con l'utente. Proponi le forme nuove emerse (`nuove_varianti`)
come da confermare: se l'utente le conferma, aggiungile alla scheda e rifai `prepara`.

---
name: ricerca-fonti
description: Trova tutte le occorrenze di una persona, di un ente (partito, Stato, testata) o di un gruppo di soggetti (per esempio «i partiti marxisti-leninisti filo-cinesi») in un corpus piccolo di fonti caricato nella chat (file .txt, PDF, esportazioni PAGE/ALTO, anche dentro archivi .zip; indicativamente fino a qualche migliaio di documenti o qualche decina di MB) e risponde con i passaggi originali, la traduzione e il riferimento in stile Chicago. Usala quando l'utente carica delle fonti e chiede che cosa dicono su qualcuno o qualcosa, chi era, come compare, quando è nominato. Non adatta a corpus di grandi dimensioni.
---

# Ricerca delle occorrenze in un corpus caricato nella chat

Il motore in `motore/` (Python, solo libreria standard; PyMuPDF o pypdf per i PDF) trova i passaggi con
espressioni regolari su tutto il corpus caricato: l'esaustività dipende da lui e dalle forme della scheda, non da
te. Tu crei schede e serie con l'utente, leggi i passaggi (pertinenza, traduzione, sintesi) e scrivi la sintesi
finale. Le citazioni originali le sceglie il motore e le verifica sul testo: non riscriverle.

Tutti i comandi: `python <cartella di questa skill>/motore/chat.py <comando> ...`, con `PYTHONIOENCODING=utf-8`.
Il progetto vive in `~/airchivist_progetto` per tutta la conversazione; non si conserva tra una chat e l'altra.
Non sostituire i passi del motore con script tuoi (decodifiche, OCR, estrazioni): se un passo non funziona,
dillo all'utente e chiedi come procedere.

## 1. Apertura del corpus

```
python .../motore/chat.py apri
```

Legge i file caricati nella chat (`/mnt/user-data/uploads` e `/mnt/user-data/attachments`), estrae gli zip e
costruisce l'indice. Riferisci all'utente numero di fonti, serie e dimensione. Il risultato elenca:
- `serie_senza_profilo`: serie presenti nelle intestazioni dei .txt ma senza profilo (passo 2);
- `da_importare`: PDF, testi senza intestazione, esportazioni PAGE/ALTO, immagini (passo 3);
- `avviso`: corpus troppo grande per la chat; proponi di restringere periodo o fonti.

Se l'utente carica altri file più avanti, rilancia `apri`. Se carica `entita.ini` o `serie.ini` di un progetto
precedente, `apri` li usa.

## 2. Serie

Ogni serie di fonti (una testata, una raccolta, un libro, un fondo d'archivio) ha un profilo che dice come
citarla. Per creare una serie chiedi all'utente ciò che non si ricava dalle intestazioni o dai documenti; non
inventare dati bibliografici.

```
python .../motore/chat.py serie-crea "Nome" --tipo periodico|volume --lingua it --cartella riviste/nome \
  --citazione "Nome, {data}" [--sigla XX] [--nota-limiti "frase per la sezione Limiti"] \
  [--campo "chicago=*Nome*[, {numero_lbl}] ({data_o_anno})[: {pagina}]"] [--campo "pagina_regex=..."]
```

`--cartella` è quella indicata in `serie_senza_profilo`, oppure, per i documenti da importare, una nuova
(`riviste/<nome>` per i periodici, `volumi/<nome>` per libri e documenti singoli). Il campo `chicago` dà la
citazione in stile Chicago standard; segnaposto: `{autore} {titolo} {data} {data_o_anno} {anno} {numero}
{numero_lbl} {volume} {luogo} {editore} {pagina}`; un tratto tra `[ ]` sparisce se manca un suo segnaposto;
`*...*` è il corsivo. Esempi: periodico `*Rinascita*[ {volume}][, {numero_lbl}] ({data_o_anno})[: {pagina}]`;
libro `{autore}. *{titolo}*. {luogo}: {editore}, {anno}[, {pagina}]`; documento d'archivio
`{autore}. *{titolo}*. {data_o_anno}[, {pagina}]`. `python .../motore/chat.py serie` mostra i profili.

## 3. Importazione

```
python .../motore/chat.py importa <file o cartella> --serie "Nome" [--data AAAA-MM-GG | AAAA-MM] \
  [--titolo "..."] [--autore "Cognome, Nome"] [--anno AAAA] [--luogo ...] [--editore ...] [--numero N] \
  [--prima-pagina N --da-pagina K] [--unisci]
```

Scrive il testo con l'intestazione e i marcatori di pagina (dalle etichette del PDF o dai numeri stampati,
anche dopo l'OCR) e aggiorna l'indice. Date: quella che il documento dà, alla precisione che dà; un documento
datato «November 1971» si importa con `--data 1971-11`, mai con un giorno inventato.

- PDF con testo: si leggono direttamente. Se manca PyMuPDF, prova `pip install pymupdf`; senza, il motore usa
  pypdf.
- Scansioni senza testo: servono Tesseract e i dati della lingua (`tesseract --list-langs`).
- **Strato di testo illeggibile** (l'importazione lo segnala: font senza tabella dei caratteri, caratteri a
  caso): le pagine vanno all'OCR, se c'è la lingua; altrimenti restano fuori. In quel caso dillo all'utente e
  chiedigli se preferisce caricare i testi in .txt oppure installare un motore OCR, con una stima del tempo
  (circa 30 secondi per pagina di giornale su questa macchina). Non procedere da solo.

Riferisci gli avvisi dell'importazione (OCR debole, pagine senza numero, strato illeggibile).

## 4. Scheda dell'entità

1. `python .../motore/chat.py schede` elenca le schede.
2. Se l'entità non ha una scheda: `python .../motore/chat.py esplora "Nome" --indizi "paese; partito" \
   --candidate "forme in altre scritture"`. In `--candidate` metti le trascrizioni probabili (per il cinese,
   l'uso Xinhua). Proponi all'utente **solo le forme attestate** che il comando restituisce, con il numero di
   `menzioni` (non `totale`, che conta le righe), e chiedigli conferma.
3. `python .../motore/chat.py scheda-crea "Nome" --varianti "forma; forma" --descrizione "chi è" \
   [--ambigue "forme brevi che possono indicare altri"] [--tipo persona|ente]`. Se il comando avvisa che una
   forma ambigua non sarà cercata, chiedi all'utente se aggiungerla alle varianti.

**Gruppi e categorie** («i partiti filo-cinesi», «i gruppi m-l europei»): non hanno un nome solo. Prima di
proporre le forme, scorri i documenti per vedere come le fonti chiamano quei soggetti, compresi i nomi dei
singoli partiti e le grafie d'epoca («Peiping», «pro-Peking», «splinter groups», «Communist Party (M-L) of
Italy»), e verificale con `esplora` o `cerca`. Se le fonti in tutto sono poche (`chat.py stato`: fino a circa
0,4 MB di testo), leggile per intero; altrimenti leggi indici, titoli e le parti che ne parlano.

`cerca "testo"` serve solo a verificare: il suo risultato non è una risposta.

## 5. Estrazione e lettura

```
python .../motore/chat.py prepara "Nome" [--dal AAAA] [--al AAAA] [--fonti "Serie; Serie"]
```

Scrive i passaggi in `~/airchivist_progetto/risultati/<cartella>/lotti/`. Riferisci numero di passaggi, stima dei
token e del tempo; oltre 150 passaggi chiedi prima di procedere e proponi di restringere periodo o fonti.

Leggi ogni `lotto_NN.md` per intero. Per ogni passaggio:

- **pertinente**: `sì` se le occorrenze tra ⟦ ⟧ si riferiscono davvero all'entità (anche solo in un elenco);
  `no` per omonimi, altre organizzazioni, usi generici; `incerto` se il testo non basta. Decidi su ciò che è
  scritto nel passaggio, non su ciò che sai dell'entità.
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
python .../motore/chat.py registra <cartella> <cartella>/letture_NN.json --da "<il tuo id di modello>"
```

Se il comando segnala passaggi non registrati, correggi e registra di nuovo. Se dalla lettura (dei lotti o dei
documenti, al passo 4) emergono parti pertinenti che l'estrazione non ha preso, perché usano forme che la scheda
non ha, proponi all'utente quelle forme: confermate, aggiungile alla scheda (modifica `entita.ini`) e rifai
`prepara`. Così anche quelle parti diventano passaggi con la citazione verificata.

## 6. Sintesi

```
python .../motore/chat.py documenti <cartella>
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
problemi: omonimie, contraddizioni, identificazioni incerte, la stessa notizia in più fonti, parti censurate o
illeggibili. Per ogni fonte di' se è primaria o secondaria e quanto è attendibile (propaganda, analisi di un
servizio avversario, dispaccio d'agenzia ripreso). Poi:

```
python .../motore/chat.py sintesi <cartella> --domanda "<domanda dell'utente>" --sintesi-da <cartella>/sintesi_sessione.json
python .../motore/chat.py consegna <cartella>
```

Non modificare a mano la risposta prodotta: se contiene un errore, correggi la causa (scheda, serie, data
all'importazione, letture) e rigenera.

## 7. Risposta all'utente

Presenta la risposta (`risposta.md`, otto sezioni) senza ricostruirla: riassumi in testa la sezione 7 e
allega i file consegnati (risposta, `entita.ini`, `serie.ini`), che l'utente può ricaricare in una chat
successiva per non rifare schede e serie. Nelle citazioni ci si ferma alla pagina: mai nomi di file né numeri
di riga (stanno solo nella sezione 8). Le traduzioni si introducono con «Traduzione:». Non usare la parola
«corpus» con l'utente. Proponi le forme nuove emerse (`nuove_varianti`) come da confermare: se l'utente le
conferma, aggiungile alla scheda (modifica `entita.ini`) e rifai `prepara`.

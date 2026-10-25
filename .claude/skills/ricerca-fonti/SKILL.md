---
name: ricerca-fonti
description: Trova tutte le occorrenze di una persona o di un ente (partito, Stato, testata) nelle fonti primarie di un progetto AIrchivist e risponde con i passaggi originali, la traduzione e il riferimento in stile Chicago. Usala quando l'utente chiede che cosa dicono le fonti su qualcuno o qualcosa, chi era, come compare, quando è nominato. I passaggi li legge Claude; estrazione, archivio e citazioni li fa la pipeline Python.
---

# Ricerca delle occorrenze nelle fonti (lettura in sessione)

La pipeline (`pipeline/`) trova i passaggi con espressioni regolari su tutto il corpus: l'esaustività dipende
da lei e dalle forme della scheda, non da te. Tu leggi i passaggi (pertinenza, traduzione, sintesi) e scrivi la
sintesi finale. Le citazioni originali le sceglie Python e le verifica sul testo: non riscriverle.

Esegui i comandi dalla cartella `pipeline` con il Python di sistema. Se l'output contiene caratteri cinesi,
imposta `PYTHONIOENCODING=utf-8`.

## 1. Scheda dell'entità

1. Controlla che l'entità abbia una scheda: cerca la sezione `[Nome]` in `entita.ini` del progetto
   (`python progetto.py stato` dice dov'è).
2. Se non c'è, non inventare forme. Usa lo strumento MCP `esplora_nome` (o `esplora.py`), proponi all'utente
   solo le forme attestate, con il numero di `menzioni` (`totale` conta le righe), e crea la scheda dopo la sua
   conferma (`schede crea`).
3. Avvisa se una forma è in `forme_ambigue` ma non in `varianti`: non viene cercata
   (`python schede.py controlla`).
4. Per un gruppo o una categoria («i partiti filo-cinesi»), che non ha un nome solo, cerca prima con
   `cerca_testo` come le fonti chiamano quei soggetti (nomi dei singoli partiti, grafie d'epoca come «Peiping»,
   «pro-Peking», «splinter groups») e proponi quelle forme.

## 2. Estrazione

```
python sessione.py prepara "<Nome>" [--dal AAAA] [--al AAAA] [--fonti "Serie; Serie"] [--lotto 10]
```

Riprende dall'archivio unico i passaggi già letti e scrive gli altri in `risultati/<cartella>/lotti/`.
Per una prova che non deve toccare l'archivio: `--cartella prova_<nome>`.
Riferisci all'utente il numero di passaggi e la stima dei token. Oltre 150 passaggi da leggere, chiedi prima
di procedere e proponi di leggere i lotti con sottoagenti (uno o due lotti ciascuno, con queste stesse regole).

## 3. Lettura, un lotto alla volta

Leggi ogni `lotto_NN.md` per intero. Per ogni passaggio:

- **pertinente**: `sì` se le occorrenze tra ⟦ ⟧ si riferiscono davvero all'entità (anche solo in un elenco);
  `no` per omonimi, altre organizzazioni, usi generici; `incerto` se il testo non basta. Decidi su ciò che è
  scritto nel passaggio, non su ciò che sai dell'entità. La nota «forma inequivocabile» è un indizio, non una
  decisione.
- per `sì` e `incerto`:
  - `traduzione_it`: traduzione italiana fedele della sola FRASE DA TRADURRE, con i nomi del glossario; termini
    incerti tra parentesi quadre; vuota per le fonti in italiano (il lotto lo indica);
  - `sintesi_it`: 1-3 frasi su ciò che il passaggio dice esplicitamente dell'entità. Date: l'anno solo se il
    testo lo dà o si ricava con certezza; un fatto già avvenuto in un mese successivo a quello della fonte è
    dell'anno precedente, uno annunciato in un mese precedente dell'anno seguente; se non è certo, data senza
    anno e «(anno non indicato)». Nessuna conoscenza esterna;
  - `tipo_menzione` (delegazione/visita, citazione o sintesi di un articolo, messaggio/telegramma, notizia,
    elenco, altro), `altri_nominati` (nome e ruolo come risulta dal testo), `ruolo_entita`, `tono`
    (elogiativo, neutro, critico, non determinabile), `evento`, `nuove_varianti` (forme non già nella scheda);
- per le voci di sommario basta la pertinenza.

Scrivi le letture del lotto in `risultati/<cartella>/letture_NN.json` (formato nella docstring di
`sessione.py`) e registrale subito, prima di passare al lotto successivo:

```
python sessione.py registra <cartella> <cartella>/letture_NN.json --da "<il tuo id di modello>"
```

Se il comando segnala passaggi non registrati, correggi e registra di nuovo. `python sessione.py stato
<cartella>` dice quanti ne restano.

## 4. Sintesi

```
python sessione.py documenti <cartella>
```

Dall'elenco numerato scrivi `risultati/<cartella>/sintesi_sessione.json`:

```json
{"da": "<il tuo id di modello>",
 "dati_espliciti": [{"testo": "...", "rif": [1, 2]}],
 "inferenze": [{"testo": "...", "rif": [3], "fondatezza": "alta|media|bassa"}],
 "problemi_interpretativi": [{"testo": "...", "rif": [4]}],
 "risposta_finale": "1-3 paragrafi con i numeri dei documenti tra parentesi quadre"}
```

Solo ciò che l'elenco attesta; ogni voce con i numeri dei documenti (le voci senza vengono scartate). Dati in
ordine cronologico; se il testo non dà la data dell'evento scrivi «(notizia del <data del documento>)». Nei
problemi: omonimie, contraddizioni, identificazioni incerte, la stessa organizzazione con dirigenti diversi.
Poi:

```
python sintesi.py <cartella> <cartella>/entita_ricerca.ini --domanda "<domanda dell'utente>" --sintesi-da <cartella>/sintesi_sessione.json
```

## 5. Risposta all'utente

Presenta `risposta.md` così com'è, senza ricostruirla: puoi riassumere in testa la sezione 7 e indicare il
percorso del file. Nelle citazioni ci si ferma alla pagina: mai nomi di file né numeri di riga (stanno solo
nella sezione 8). Le traduzioni si introducono con «Traduzione:». Non usare la parola «corpus». Proponi le
forme nuove emerse (`nuove_varianti`) come da confermare, senza aggiungerle da solo alla scheda.

# Ricerca nelle fonti — guida rapida

Sistema per trovare **tutte** le occorrenze di una persona, un partito o una testata nelle fonti primarie
(Renmin Ribao, Peking Review, Hongqi/Red Flag, raccolte di documenti, Selected Works) e rispondere con i
passaggi originali, la traduzione e il riferimento esatto. Nuovo materiale (anche scansioni in PDF, con OCR)
si aggiunge con `pipeline\importa.py` o chiedendo in Jan.

## Installazione

Serve Python 3.10 o successivo (quello di python.org). I requisiti si installano nel sistema, mai dentro la
cartella. Dalla cartella del progetto:

```
python pipeline\installa.py librerie
python pipeline\installa.py controlla
python pipeline\installa.py client jan
```

- `librerie`: installa le librerie facoltative di `requirements.txt` (PyMuPDF, per importare i PDF).
- `controlla`: verifica Python, l'indice FTS5, il servizio dei modelli (chiave e raggiungibilità), il progetto
  in uso, PyMuPDF, Tesseract e le lingue OCR richieste dalle serie. Se manca qualcosa di necessario, lo dice.
- `client`: mostra cosa scrivere nel client per collegare il server MCP (`jan`, `claude`, `lmstudio`, `json`).

## Come si usa

1. Avvia **FreeLLMAPI** (fornisce i modelli gratuiti).
2. Apri **Jan**, nuova chat con l'assistente «Ricerca fonti» e il modello `auto:chat`.
3. Scrivi la domanda, per esempio «Cosa dicono le fonti di Jacques Grippa nel 1964?».

Jan usa gli strumenti del server MCP «Pipeline» (`pipeline\mcp_server.py`). Con questi:
- cerca la scheda dell'entità;
- consulta i passaggi già letti oppure avvia la ricerca completa;
- risponde con originali, traduzioni e riferimenti.

## Dove sono le cose

| Cartella | Contenuto |
|---|---|
| `data` | le fonti |
| `audit_fonti` | registro delle correzioni fatte ai metadati delle fonti e lacune ancora aperte (giorni e numeri mancanti) |
| `risposte` | tutte le risposte complete, una per domanda |
| `indice` | indice di ricerca delle fonti |
| `importazioni` | registro dei materiali importati e controlli delle intestazioni |
| `lavori` | stato e registro di ogni ricerca avviata dalla chat |
| `risultati\_archivio` | i passaggi già letti (non vengono mai riletti) |
| `risultati\_riferimenti` | letture di riferimento per provare i modelli |
| `risultati\_sessioni_precedenti` | lavori delle sessioni con Claude |
| `risultati\_prove` | prove dei modelli |
| `pipeline` | programmi e `config.ini` (il motore); qui anche `entita.ini` (schede delle entità) e `serie.ini` (serie di fonti) di questo progetto |
| `progetto.ini` | nome e impostazioni di questo progetto di ricerca. Per un'altra ricerca: `python pipeline\progetto.py nuovo <cartella>` (vedi `pipeline\ISTRUZIONI.md`, «Progetti di ricerca») |

## Per approfondire

`pipeline\ISTRUZIONI.md` spiega:
- la configurazione di FreeLLMAPI e di Jan;
- le schede delle entità e le varianti dei nomi;
- l'importazione di nuove fonti (OCR);
- la valutazione dei modelli;
- i problemi frequenti.

In inglese: `README.md`.

## Licenza

Il codice è distribuito con la licenza GNU Affero General Public License, versione 3 (`LICENSE`). Chi offre
una versione modificata come servizio in rete, anche come server MCP usato da altri, deve renderne disponibile il
codice. La licenza non riguarda le fonti del corpus, che restano soggette ai propri diritti.

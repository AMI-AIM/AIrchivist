# ricerca-fonti: plugin per Claude Code e ChatGPT

Versione minore di AIrchivist: trova tutte le occorrenze di una persona o di un ente nelle fonti primarie e
risponde con i passaggi originali, la traduzione e il riferimento in stile Chicago. Lavora su un **corpus
piccolo** (file caricati nella conversazione o una cartella indicata) oppure, se sul computer c'è il sistema
principale di AIrchivist, sul suo progetto, con l'archivio delle letture.

La cartella è un plugin con una sola skill (`skills/ricerca-fonti/`, con il motore in `motore/`) e due manifesti:
`.claude-plugin/plugin.json` per Claude Code e `plugin.json` (formato Agent Plugins) per ChatGPT.

## Claude Code

Come plugin, da un terminale, nella cartella che contiene `.claude-plugin/marketplace.json` (la cartella
`claude-code` della distribuzione):

```
claude plugin marketplace add ./claude-code
claude plugin install ricerca-fonti@airchivist
```

La skill si richiama come `/ricerca-fonti:ricerca-fonti` o parte da sola quando la domanda corrisponde.
In alternativa, come skill personale: copia `skills/ricerca-fonti/` in `~/.claude/skills/ricerca-fonti/`.

## ChatGPT

- **Prova sul proprio computer** (app desktop di ChatGPT): copia questa cartella in `~/.codex/plugins/ricerca-fonti`,
  aggiungi la voce del plugin a `~/.agents/plugins/marketplace.json`, riavvia l'app e installa il plugin dalla
  directory dei plugin. Il file, se non c'è già:

  ```json
  {"name": "personale",
   "plugins": [{"name": "ricerca-fonti",
                "source": {"source": "local", "path": "./.codex/plugins/ricerca-fonti"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Productivity"}]}
  ```
- **Area di lavoro** (Business, Enterprise, Edu): un amministratore carica `ricerca-fonti-chatgpt.zip` dalla
  console (*Plugins → Add → Upload plugin*).
- **Directory pubblica**: lo zip si invia dal portale dei plugin di OpenAI, percorso «Skills only», con verifica
  dell'identità e revisione.

Le skill personali di ChatGPT sono documentate per Business, Enterprise, Healthcare ed Edu; per Plus la
documentazione non dice se si possano installare plugin di sole skill.

## Limiti

- Nella conversazione il progetto è temporaneo: le letture non si conservano tra una conversazione e l'altra.
- Solo lo strato di testo dei PDF: le scansioni senza testo restano fuori, salvo ambienti con OCR.
- Senza PyMuPDF i PDF si leggono con pypdf; senza nessuno dei due servono testi in .txt.
- I passaggi li legge il modello della chat: i token contano sui limiti del piano.

## Sistema principale

AIrchivist: https://github.com/AMI-AIM/AIrchivist (motore in Python, indice persistente, archivio delle letture,
modelli scelti dal ricercatore, anche gratuiti o locali). Licenza: GNU AGPL v3 (`LICENSE`).

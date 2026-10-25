#!/usr/bin/env python3
"""
Prova dei modelli della chat (quelli che usano gli strumenti del server MCP, non quelli che leggono i passaggi):
simula un client come Jan su una domanda vera e misura se il modello segue la procedura e scrive senza errori.

Il modello riceve gli strumenti veri del server (stesse descrizioni) e, come istruzioni di sistema, solo quanto
si scrive nell'assistente del client («All'inizio chiama lo strumento guida...»); con --istruzioni-complete riceve
le istruzioni del server per intero, come un client che le passa. Gli strumenti in sola lettura girano davvero;
quelli che scrivono (schede crea, ricerca avvia, correggi_passaggio, varianti aggiungi/scarta, importa avvia,
serie crea) restituiscono una risposta simulata: la prova non modifica nulla.

Punteggio (tutto calcolato, nessun giudizio di un modello):
  guida_per_primo      il primo strumento chiamato è guida
  procedura            usa schede ed esplora_nome (domanda su un'entità senza scheda)
  nessuna_ricostruzione non chiama apri_fonte e chiama cerca_testo al massimo una volta
  chiede_conferma      la risposta finale chiede conferma all'utente
  forme_cinesi         la risposta riporta la forma cinese attesa (--forma, es. 贝林格)
  niente_file_righe    nessun nome di file, «riga» o numero di riga spacciato per pagina
  niente_corpus        la parola «corpus» non compare (regola del progetto)
  testo_pulito         meno dell'1% di caratteri di scritture estranee (né latine né cinesi) e nessuna parola
                       mescolata (lettere latine e caratteri cinesi nella stessa parola)

Uso (nella cartella pipeline; FreeLLMAPI acceso):
  python prova_chat.py --modelli "auto:chat; gemini-3.8-flash; gpt-oss-120b" [--domanda "..."] [--forma 贝林格]
Risultati in risultati\\_prove\\chat\\prova_<data-ora>.md, con le conversazioni in .json.
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARTELLA))
DOMANDA = "Cosa dicono le fonti riguardo Enrico Berlinguer?"
ASSISTENTE = "All'inizio di ogni conversazione chiama lo strumento guida e segui le sue istruzioni."
SCRIVONO = {("schede", "crea"), ("ricerca", "avvia"), ("ricerca", "ferma"), ("importa", "avvia"), ("serie", "crea"),
            ("varianti", "aggiungi"), ("varianti", "scarta"), ("correggi_passaggio", None)}
MASSIMO_TURNI = 10


def strumenti_openai(server):
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t["inputSchema"]}} for t in server.elenco_strumenti()]


def esegui_strumento(server, nome, argomenti):
    """Risultato di uno strumento: vero per quelli in sola lettura, simulato per quelli che scrivono."""
    azione = argomenti.get("azione")
    if (nome, azione) in SCRIVONO or (nome, None) in SCRIVONO:
        return json.dumps({"simulato": True, "nota": "Prova: operazione non eseguita. Riferisci all'utente."},
                          ensure_ascii=False)
    r = server.gestisci({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                         "params": {"name": nome, "arguments": argomenti}})
    if "error" in r:
        return json.dumps({"errore": r["error"]["message"]}, ensure_ascii=False)
    return r["result"]["content"][0]["text"][:8000]


def chiama_modello(url, chiave, modello, messaggi, strumenti, timeout=180):
    corpo = {"model": modello, "messages": messaggi, "tools": strumenti, "tool_choice": "auto",
             "temperature": 0.2, "max_tokens": 2500}
    req = urllib.request.Request(url, data=json.dumps(corpo).encode("utf-8"), method="POST",
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {chiave}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.load(r)
    return d["choices"][0]["message"], d.get("model", modello)


def conversazione(server, url, chiave, modello, domanda, sistema):
    messaggi = [{"role": "system", "content": sistema}, {"role": "user", "content": domanda}]
    strumenti, chiamate, risposto_da = strumenti_openai(server), [], set()
    for _ in range(MASSIMO_TURNI):
        msg, chi = chiama_modello(url, chiave, modello, messaggi, strumenti)
        risposto_da.add(chi)
        voce = {"role": "assistant", "content": msg.get("content") or ""}
        if msg.get("tool_calls"):
            voce["tool_calls"] = msg["tool_calls"]
            messaggi.append(voce)
            for tc in msg["tool_calls"]:
                nome = tc["function"]["name"]
                try:
                    arg = json.loads(tc["function"].get("arguments") or "{}")
                except ValueError:
                    arg = {}
                chiamate.append((nome, arg))
                messaggi.append({"role": "tool", "tool_call_id": tc.get("id", nome),
                                 "content": esegui_strumento(server, nome, arg)})
            continue
        messaggi.append(voce)
        return voce["content"], chiamate, messaggi, sorted(risposto_da)
    return "", chiamate, messaggi, sorted(risposto_da)


ESTRANEI = re.compile(r"[^\s\x00-ɏ -⁯　-〿㐀-鿿＀-￯·«»“”‘’–—…•]")
MESCOLATE = re.compile(r"[A-Za-z][一-鿿]|[一-鿿][A-Za-z]")


def punteggio(testo, chiamate, forma, righe_note=()):
    nomi = [n for n, _ in chiamate]
    t = testo or ""
    estranei = len(ESTRANEI.findall(t))
    numeri_riga = [n for n in righe_note if re.search(rf"\bp(?:ag)?\.\s*{n}\b|\briga\s*{n}\b", t)]
    voci = {
        "guida_per_primo": bool(nomi) and nomi[0] == "guida",
        "procedura": "schede" in nomi and "esplora_nome" in nomi,
        "nessuna_ricostruzione": "apri_fonte" not in nomi and nomi.count("cerca_testo") <= 1,
        "chiede_conferma": "?" in t[-600:] or bool(re.search(r"\bconferm", t, re.IGNORECASE)),
        "forme_cinesi": (forma in t) if forma else True,
        "niente_file_righe": not re.search(r"\.txt\b|\briga\b|\brighe\b", t, re.IGNORECASE) and not numeri_riga,
        "niente_corpus": "corpus" not in t.lower(),
        "testo_pulito": bool(t) and estranei <= len(t) * 0.01 and not MESCOLATE.search(t),
    }
    voci["totale"] = sum(1 for k, v in voci.items() if v is True)
    return voci


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--modelli", required=True, help="modelli separati da ;")
    ap.add_argument("--domanda", default=DOMANDA)
    ap.add_argument("--forma", default="贝林格", help="forma cinese che la risposta dovrebbe riportare")
    ap.add_argument("--istruzioni-complete", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    import mcp_server as server
    from llm import leggi_config, percorso
    cfg = leggi_config()
    url = cfg.get("router", "url").rstrip("/") + "/chat/completions"
    chiave = os.environ.get(cfg.get("router", "chiave_env", fallback="FREELLMAPI_KEY"), "")
    sistema = server.istruzioni() if args.istruzioni_complete else ASSISTENTE
    dest = percorso(cfg, "risultati") / "_prove" / "chat"
    dest.mkdir(parents=True, exist_ok=True)
    ora = dt.datetime.now().strftime("%Y%m%d-%H%M")
    righe = [f"# Prova dei modelli della chat — {ora}", "", f"Domanda: «{args.domanda}». Istruzioni di sistema: "
             + ("quelle del server, complete." if args.istruzioni_complete else f"«{ASSISTENTE}»"), "",
             "| Modello | Ha risposto | Totale /8 | guida | procedura | niente ricostruzione | conferma | forma cinese "
             "| niente file/righe | niente corpus | testo pulito | strumenti | secondi |", "|" + "---|" * 13]
    for modello in [m.strip() for m in args.modelli.split(";") if m.strip()]:
        t0 = time.time()
        try:
            testo, chiamate, messaggi, chi = conversazione(server, url, chiave, modello, args.domanda, sistema)
            errore = ""
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, KeyError, ValueError) as e:
            testo, chiamate, messaggi, chi, errore = "", [], [], [], f"{type(e).__name__}: {e}"
        secondi = round(time.time() - t0)
        p = punteggio(testo, chiamate, args.forma)
        nome_f = re.sub(r"[^\w.-]+", "_", modello)
        (dest / f"prova_{ora}_{nome_f}.json").write_text(json.dumps(
            {"modello": modello, "risposto_da": chi, "errore": errore, "chiamate": chiamate, "risposta": testo,
             "punteggio": p, "messaggi": messaggi}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        segno = (lambda v: "—") if errore else (lambda v: "sì" if v else "no")     # errore del servizio: non misurato
        righe.append(f"| {modello} | {', '.join(chi) or errore[:60]} | {p['totale'] if not errore else '—'} | "
                     + " | ".join(segno(p[k]) for k in ("guida_per_primo", "procedura", "nessuna_ricostruzione",
                                                       "chiede_conferma", "forme_cinesi", "niente_file_righe",
                                                       "niente_corpus", "testo_pulito"))
                     + f" | {' > '.join(n for n, _ in chiamate)[:80]} | {secondi} |")
        print(righe[-1])
    f = dest / f"prova_{ora}.md"
    f.write_text("\n".join(righe) + "\n", encoding="utf-8")
    print(f"\nRisultati in {f}")


if __name__ == "__main__":
    main()

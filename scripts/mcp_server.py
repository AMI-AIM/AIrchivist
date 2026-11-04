#!/usr/bin/env python3
"""
Server MCP (Model Context Protocol): espone gli strumenti del motore (strumenti.py) a un client di chat esterno
(Claude Desktop, Jan, LM Studio, Open WebUI, ...). È un'uscita facoltativa: l'interfaccia (app.py) e la sua
conversazione sulle fonti usano gli stessi strumenti direttamente, senza passare di qui. Solo libreria standard.

Qui c'è solo il protocollo (JSON-RPC su stdio o HTTP "Streamable"). Le istruzioni per il modello della chat
(istruzioni.py) arrivano in tre modi, perché non tutti i client le mostrano al modello: campo «instructions» di
initialize, prompt MCP «istruzioni», strumento «guida».

Avvio:
  python mcp_server.py                 (stdio: lo avvia il client; vedi docs/user_guide.it.md)
  python mcp_server.py --http 8766     (HTTP "Streamable", per Open WebUI: http://127.0.0.1:8766/mcp)
"""
import argparse
import json
import re
import sys
import threading
import uuid
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARTELLA))

# Il canale stdout appartiene al protocollo: tutto ciò che la pipeline stampa va su stderr.
_PROTOCOLLO = sys.stdout.buffer
sys.stdout = sys.stderr

import strumenti as S                           # noqa: E402

NOME, VERSIONE = "ricerca-fonti", "1.0"
VERSIONI_PROTOCOLLO = ["2025-06-18", "2025-03-26", "2024-11-05"]


def gestisci(msg):
    """Restituisce la risposta JSON-RPC (dict) oppure None per le notifiche."""
    metodo, mid = msg.get("method"), msg.get("id")
    if mid is None:
        return None                                   # notifiche (initialized, cancelled, ...)
    try:
        if metodo == "initialize":
            richiesta = (msg.get("params") or {}).get("protocolVersion", VERSIONI_PROTOCOLLO[0])
            ver = richiesta if richiesta in VERSIONI_PROTOCOLLO else VERSIONI_PROTOCOLLO[0]
            ris = {"protocolVersion": ver,
                   "capabilities": {"tools": {"listChanged": False}, "prompts": {"listChanged": False}},
                   "serverInfo": {"name": NOME, "version": VERSIONE}, "instructions": S.istruzioni()}
        elif metodo == "ping":
            ris = {}
        elif metodo == "tools/list":
            ris = {"tools": S.elenco_strumenti()}
        elif metodo == "tools/call":
            p = msg.get("params") or {}
            try:
                testo, errore = S.chiama(p.get("name"), p.get("arguments") or {})
            except S.StrumentoSconosciuto as e:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": str(e)}}
            ris = {"content": [{"type": "text", "text": testo}], "isError": errore}
        elif metodo == "prompts/list":
            ris = {"prompts": [{"name": "istruzioni", "description": "Istruzioni di lavoro e fonti del progetto "
                                                                     "di ricerca, da dare al modello della chat."}]}
        elif metodo == "prompts/get":
            if (msg.get("params") or {}).get("name") != "istruzioni":
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "Prompt sconosciuto"}}
            ris = {"description": "Istruzioni di lavoro e fonti del progetto di ricerca",
                   "messages": [{"role": "user", "content": {"type": "text", "text": S.istruzioni()}}]}
        elif metodo == "resources/list":
            ris = {"resources": []}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Metodo non supportato: {metodo}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": ris}
    except Exception as e:
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e)}}


def scrivi(obj):
    _PROTOCOLLO.write((json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8"))
    _PROTOCOLLO.flush()


def servi_stdio():
    blocco = threading.Lock()

    def esegui(msg):
        r = gestisci(msg)
        if r is not None:
            with blocco:
                scrivi(r)

    fili = []
    for riga in sys.stdin.buffer:
        riga = riga.strip()
        if not riga:
            continue
        try:
            msg = json.loads(riga.decode("utf-8"))
        except ValueError:
            scrivi({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON non valido"}})
            continue
        for m in (msg if isinstance(msg, list) else [msg]):
            # attendi_ricerca blocca fino a 25 s: ogni richiesta in un thread, così ping e altre chiamate passano
            t = threading.Thread(target=esegui, args=(m,), daemon=True)
            t.start()
            fili.append(t)
        fili = [t for t in fili if t.is_alive()]
    for t in fili:                       # fine dell'input: completa le richieste ancora in corso
        t.join(timeout=60)


def servi_http(porta):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Gestore(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _invia(self, codice, obj=None, extra=None):
            dati = b"" if obj is None else json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(codice)
            if obj is not None:
                self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(dati)))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(dati)

        def do_GET(self):
            self._invia(405)

        def do_DELETE(self):
            self._invia(200)

        def do_POST(self):
            if self.path.split("?")[0].rstrip("/") != "/mcp":
                return self._invia(404)
            origine = self.headers.get("Origin") or ""
            if origine and not re.match(r"^https?://(127\.0\.0\.1|localhost)(:\d+)?$", origine):
                return self._invia(403)
            n = int(self.headers.get("Content-Length") or 0)
            try:
                msg = json.loads(self.rfile.read(n).decode("utf-8"))
            except ValueError:
                return self._invia(400, {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON non valido"}})
            msgs = msg if isinstance(msg, list) else [msg]
            risposte = [r for r in (gestisci(m) for m in msgs) if r is not None]
            extra = {}
            if any(m.get("method") == "initialize" for m in msgs):
                extra["Mcp-Session-Id"] = uuid.uuid4().hex
            if not risposte:
                return self._invia(202, None, extra)
            self._invia(200, risposte if isinstance(msg, list) else risposte[0], extra)

    server = ThreadingHTTPServer(("127.0.0.1", porta), Gestore)
    print(f"Server MCP su http://127.0.0.1:{porta}/mcp  (chiudi la finestra per spegnerlo)", file=sys.stderr)
    server.serve_forever()


def main():
    ap = argparse.ArgumentParser(description="Server MCP della ricerca nelle fonti")
    ap.add_argument("--http", type=int, default=None, help="porta per il trasporto HTTP (Open WebUI)")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()
    S.CONFIG = args.config
    if args.http:
        servi_http(args.http)
    else:
        servi_stdio()


if __name__ == "__main__":
    main()

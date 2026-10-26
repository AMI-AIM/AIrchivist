#!/usr/bin/env python3
"""
La risposta come documento (lavoro 31): accanto a risposta.md, un file HTML autonomo (uno solo, senza file
esterni né caricamenti da internet) che si apre con il browser e si stampa. Stesso contenuto della risposta:
sezioni, passaggi originali, «Traduzione:», citazioni, limiti, copertura; i rimandi [n] portano al passaggio.

Converte solo il Markdown che sintesi.py ed evoluzione.py scrivono: titoli (#, ##, ###), paragrafi (le righe
restano righe), citazioni (>), elenchi (-, anche annidati di un livello), tabelle (|), *corsivo*, **grassetto**,
`codice`, commenti HTML (restano commenti). Solo libreria standard.

Uso:
  python documento.py <risposta.md | cartella>     scrive <nome>.html accanto a ogni .md (le risposte già salvate)
  python documento.py <risposta.md> --apri         e lo apre nel browser
"""
import argparse
import html
import re
import sys
import webbrowser
from pathlib import Path

STILE = """
:root { --testo: #1d1d1f; --tenue: #5f6368; --bordo: #d9d9de; --fondo: #ffffff; --citazione: #f6f6f8;
        --accento: #8a1c1c; }
@media (prefers-color-scheme: dark) {
  :root { --testo: #e8e8ea; --tenue: #a0a4ab; --bordo: #3a3a40; --fondo: #18181b; --citazione: #232327;
          --accento: #e07a7a; } }
html { background: var(--fondo); color: var(--testo); }
body { font-family: Georgia, "Noto Serif", "Songti SC", "SimSun", serif; line-height: 1.55; max-width: 46rem;
       margin: 2rem auto; padding: 0 1rem; font-size: 1.05rem; }
h1 { font-size: 1.7rem; margin-bottom: .3rem; }
h2 { font-size: 1.3rem; margin-top: 2.2rem; border-bottom: 1px solid var(--bordo); padding-bottom: .2rem; }
h3 { font-size: 1.05rem; margin-top: 1.6rem; }
blockquote { margin: .8rem 0; padding: .6rem .9rem; background: var(--citazione); border-left: 3px solid var(--accento); }
p { margin: .6rem 0; }
ul { padding-left: 1.4rem; }
li { margin: .2rem 0; }
table { border-collapse: collapse; width: 100%; font-size: .9rem; margin: 1rem 0; }
th, td { border: 1px solid var(--bordo); padding: .3rem .45rem; text-align: left; vertical-align: top; }
code { font-family: Consolas, "Courier New", monospace; font-size: .85em; }
a { color: var(--accento); text-decoration: none; }
a:hover { text-decoration: underline; }
.rimando { white-space: nowrap; }
@media print {
  body { max-width: none; margin: 0; font-size: 11pt; }
  a { color: inherit; }
  h2 { break-after: avoid; }
  blockquote, tr { break-inside: avoid; }
}
"""


def inline(testo, ancore=frozenset(), corsivo=True):
    """Elementi in linea: testo sicuro (escape), **grassetto**, *corsivo*, `codice`, rimandi [n] ai passaggi.
    corsivo=False nei passaggi originali (>), dove un asterisco può essere del testo (OCR) e resta com'è."""
    pezzi = re.split(r"(`[^`]*`)", testo)
    out = []
    for p in pezzi:
        if p.startswith("`") and p.endswith("`") and len(p) > 1:
            out.append(f"<code>{html.escape(p[1:-1])}</code>")
            continue
        s = html.escape(p, quote=False)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        if corsivo:
            s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"<em>\1</em>", s)
        s = re.sub(r"\[(\d{1,4})\]", lambda m: (f'<a class="rimando" href="#doc-{m.group(1)}">[{m.group(1)}]</a>'
                                               if m.group(1) in ancore else m.group(0)), s)
        out.append(s)
    return "".join(out)


def celle(riga):
    return [c.strip() for c in riga.strip().strip("|").split("|")]


def md_a_html(testo, titolo=""):
    """Documento HTML completo dal Markdown della risposta."""
    righe = testo.replace("\r\n", "\n").split("\n")
    # i passaggi della sezione 2 («### [n] ...») sono le ancore dei rimandi [n]
    ancore = {m.group(1) for r in righe for m in [re.match(r"###\s+\[(\d+)\]", r)] if m}
    corpo, i = [], 0
    while i < len(righe):
        r = righe[i]
        s = r.strip()
        if not s:
            i += 1
            continue
        if s.startswith("<!--"):                          # commenti: restano commenti (domanda, marcatori)
            blocco = [r]
            while "-->" not in blocco[-1] and i + 1 < len(righe):
                i += 1
                blocco.append(righe[i])
            corpo.append("\n".join(blocco).replace("--!>", ""))
            i += 1
            continue
        m = re.match(r"(#{1,4})\s+(.*)", s)
        if m:
            n = len(m.group(1))
            ref = re.match(r"\[(\d+)\]", m.group(2))
            ident = f' id="doc-{ref.group(1)}"' if n == 3 and ref else ""
            corpo.append(f"<h{n}{ident}>{inline(m.group(2), ancore)}</h{n}>")
            titolo = titolo or (re.sub(r"[*`]", "", m.group(2)) if n == 1 else "")
            i += 1
            continue
        if s.startswith(">"):
            blocco = []
            while i < len(righe) and righe[i].strip().startswith(">"):
                blocco.append(re.sub(r"^\s*>\s?", "", righe[i]))
                i += 1
            paragrafi = "\n".join(blocco).split("\n\n")
            corpo.append("<blockquote>" + "".join(
                f"<p>{'<br>'.join(inline(x, ancore, corsivo=False) for x in p.split(chr(10)) if x.strip())}</p>"
                for p in paragrafi if p.strip()) + "</blockquote>")
            continue
        if s.startswith("|") and i + 1 < len(righe) and re.fullmatch(r"\|?[\s:|-]+\|?", righe[i + 1].strip()):
            testa = celle(r)
            i += 2
            file_ = []
            while i < len(righe) and righe[i].strip().startswith("|"):
                file_.append(celle(righe[i]))
                i += 1
            corpo.append("<table><thead><tr>" + "".join(f"<th>{inline(c, ancore)}</th>" for c in testa) +
                         "</tr></thead><tbody>" + "".join(
                             "<tr>" + "".join(f"<td>{inline(c, ancore)}</td>" for c in f) + "</tr>" for f in file_) +
                         "</tbody></table>")
            continue
        if re.match(r"-\s", s) and not r.startswith(" "):
            voci = []
            while i < len(righe) and (re.match(r"\s*-\s", righe[i]) or
                                      (righe[i].startswith("  ") and righe[i].strip() and voci)):
                riga = righe[i]
                if re.match(r"\s{2,}-\s", riga):                       # elenco annidato
                    voci[-1][1].append(re.sub(r"^\s*-\s", "", riga))
                elif re.match(r"-\s", riga):
                    voci.append([riga[2:], []])
                else:                                                  # riga che continua la voce
                    voci[-1][0] += "\n" + riga.strip()
                i += 1
            parti = []
            for testo_voce, sotto in voci:
                h = "<br>".join(inline(x, ancore) for x in testo_voce.split("\n"))
                if sotto:
                    h += "<ul>" + "".join(f"<li>{inline(x, ancore)}</li>" for x in sotto) + "</ul>"
                parti.append(f"<li>{h}</li>")
            corpo.append("<ul>" + "".join(parti) + "</ul>")
            continue
        blocco = []                                         # paragrafo: le righe restano righe
        while i < len(righe) and righe[i].strip() and not re.match(r"\s*(#{1,4}\s|>|<!--|\||-\s)", righe[i]):
            blocco.append(righe[i].strip())
            i += 1
        if not blocco:                                      # riga che nessuna regola prende: testo semplice
            blocco, i = [s], i + 1
        corpo.append("<p>" + "<br>".join(inline(x, ancore) for x in blocco) + "</p>")
    return ("<!doctype html>\n<html lang=\"it\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
            f"<title>{html.escape(titolo or 'Risposta')}</title>\n<style>{STILE}</style>\n</head>\n<body>\n"
            + "\n".join(corpo) + "\n</body>\n</html>\n")


def scrivi_html(md):
    """Scrive <nome>.html accanto alla risposta <nome>.md; restituisce il percorso."""
    md = Path(md)
    dest = md.with_suffix(".html")
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(md_a_html(md.read_text(encoding="utf-8")), encoding="utf-8")
    tmp.replace(dest)
    return dest


def apri(f):
    """Apre il documento nel browser predefinito."""
    return webbrowser.open(Path(f).resolve().as_uri())


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("percorso")
    ap.add_argument("--apri", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    p = Path(args.percorso)
    file_ = sorted(p.glob("*.md")) if p.is_dir() else [p]
    for f in file_:
        dest = scrivi_html(f)
        print(dest)
        if args.apri:
            apri(dest)


if __name__ == "__main__":
    sys.exit(main())

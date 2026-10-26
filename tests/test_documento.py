"""
Test della risposta come documento (lavoro 31: documento.py): l'HTML autonomo ha lo stesso testo di risposta.md
(confronto del testo senza la sintassi), i rimandi [n] portano ai passaggi, i passaggi originali restano come
sono (asterischi dell'OCR compresi), il documento non carica niente da fuori; il server MCP consegna riassunto e
percorso entro il limite di caratteri.
"""
import html
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOTORE))
import documento as D  # noqa: E402

RISPOSTA = """<!-- Domanda: Chi è Franz Strobl? | entità: Franz Strobl | occorrenze -->

# Franz Strobl

*Domanda:* Chi è Franz Strobl?

*Generato il 2026-10-26 — documenti pertinenti: 2.*

## 1. Documenti rilevanti

[1] *Renmin ribao* 人民日报. 1965. 28 giugno 1965. — delegazione/visita
[2] *Peking Review*. 1967. Vol. 10, no. 11, 10 marzo 1967. — notizia

## 2. Passaggi rilevanti

### [1] *Renmin ribao* 人民日报. 1965. 28 giugno 1965.

> 奥地利《红旗》半月刊代表团到京 在《红旗》半月刊主编弗朗茨·施特罗伯尔率领下 <到达> & "北京"

— *Renmin ribao* 人民日报. 1965. 28 giugno 1965, p. 4.

Traduzione: La delegazione arriva a Pechino.

### [2] *Peking Review*. 1967. Vol. 10, no. 11, 10 marzo 1967.

> We *can surmount these difficulties ‘of the People’s Army* and win.
> Seconda riga del passaggio.

## 3. Dati espliciti

- Strobl guida la delegazione. [1][2]
- Un dato con sotto-voci:
  - prima
  - seconda

## 5. Limiti e problemi interpretativi

- I passaggi (2) sono stati letti dal modello `qwen/qwen3.8-27b`: **non misurato**.

| Anno | Documenti | Eventi |
|---|---|---|
| 1965 | 1 | visita |
| 1967 | 1 | – |

## 7. Risposta finale

Franz Strobl dirige *Rote Fahne* [1] e nel 1967 è citato dalla stampa cinese [2].
"""


def testo_md(t):
    t = re.sub(r"<!--.*?-->", " ", t, flags=re.DOTALL)
    righe = []
    for r in t.split("\n"):
        s = r.strip()
        if re.fullmatch(r"\|?[\s:|-]+\|?", s) and "-" in s:
            continue
        citazione = s.startswith(">")
        s = re.sub(r"^#{1,4}\s+", "", s)
        s = re.sub(r"^(>\s?)+", "", s)
        s = re.sub(r"^-\s+", "", s)
        if s.startswith("|"):
            s = " ".join(c.strip() for c in s.strip("|").split("|"))
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = re.sub(r"`([^`]*)`", r"\1", s)
        if not citazione:
            s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", s)
        righe.append(s)
    return re.sub(r"\s+", " ", " ".join(righe)).strip()


def testo_html(t):
    corpo = t.split("<body>", 1)[1].split("</body>")[0]
    corpo = re.sub(r"<!--.*?-->", " ", corpo, flags=re.DOTALL)
    corpo = re.sub(r"</?(p|br|h\d|li|ul|blockquote|table|thead|tbody|tr|th|td)\b[^>]*>", " ", corpo)
    corpo = re.sub(r"<[^>]+>", "", corpo)
    return re.sub(r"\s+", " ", html.unescape(corpo)).strip()


class Documento(unittest.TestCase):
    def setUp(self):
        self.html = D.md_a_html(RISPOSTA)

    def test_stesso_testo(self):
        self.assertEqual(testo_html(self.html), testo_md(RISPOSTA))

    def test_struttura(self):
        h = self.html
        self.assertTrue(h.startswith("<!doctype html>"))
        self.assertIn("<title>Franz Strobl</title>", h)
        self.assertIn('<h3 id="doc-1">', h)
        self.assertIn('<a class="rimando" href="#doc-1">[1]</a><a class="rimando" href="#doc-2">[2]</a>', h)
        self.assertIn("<em>Renmin ribao</em>", h)
        self.assertIn("<strong>non misurato</strong>", h)
        self.assertIn("<code>qwen/qwen3.8-27b</code>", h)
        self.assertIn("<th>Anno</th>", h)
        self.assertIn("<ul><li>prima</li><li>seconda</li></ul>", h)
        self.assertIn("<!-- Domanda: Chi è Franz Strobl?", h)          # commenti: restano commenti
        self.assertIn("&lt;到达&gt; &amp; \"北京\"", h)                  # testo sicuro

    def test_passaggi_originali_intatti(self):
        # nei passaggi gli asterischi dell'OCR sono testo, non corsivo
        self.assertIn("We *can surmount these difficulties ‘of the People’s Army* and win.<br>Seconda riga", self.html)

    def test_autonomo(self):
        self.assertNotRegex(self.html, r"(src|href)=\"https?://")
        self.assertNotIn("<script", self.html)
        self.assertIn("@media print", self.html)

    def test_scrivi_accanto(self):
        f = Path(tempfile.mkdtemp()) / "2026-10-26_chi_è_franz_strobl.md"
        f.write_text(RISPOSTA, encoding="utf-8")
        dest = D.scrivi_html(f)
        self.assertEqual(dest, f.with_suffix(".html"))
        self.assertEqual(testo_html(dest.read_text(encoding="utf-8")), testo_md(RISPOSTA))


class Consegna(unittest.TestCase):
    def test_riassunto_e_percorso(self):
        import mcp_server as M
        f = Path(tempfile.mkdtemp()) / "risposta.md"
        lunga = RISPOSTA.replace("Franz Strobl dirige", "Franz Strobl dirige " + "molto " * 600)
        f.write_text(lunga, encoding="utf-8")
        out = M.riassunto(f)
        self.assertEqual(out["documento"], str(f.with_suffix(".html")))
        self.assertTrue(Path(out["documento"]).exists())
        self.assertEqual(out["documenti_pertinenti"], 2)
        self.assertTrue(out["risposta"].endswith("…[segue nel documento]"))
        self.assertIn("Non riscriverla", out["nota"])
        testo = M._testo({"finito": True, "risposta_pronta": out})
        self.assertLessEqual(len(testo), M.LIMITE_CARATTERI)
        self.assertEqual(json.loads(testo)["risposta_pronta"]["documento"], out["documento"])


if __name__ == "__main__":
    unittest.main()

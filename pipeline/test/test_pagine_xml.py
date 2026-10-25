"""
Test della lettura delle esportazioni PAGE XML e ALTO XML (pagine_xml.py) e della loro importazione
(importa.py). Gli esempi seguono gli schemi PAGE 2019-07-15 e ALTO v4 nelle forme usate da Transkribus ed
eScriptorium. L'importazione scrive solo in una cartella temporanea (configurazione sostituita, senza indice).
"""
import argparse
import configparser
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

PIPELINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PIPELINE))
import importa as I  # noqa: E402
import pagine_xml as X  # noqa: E402

NS_PAGE = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"


def page(regioni, ordine="", creatore="Transkribus", immagine="0001.jpg"):
    return (f'<?xml version="1.0" encoding="UTF-8"?>\n<PcGts xmlns="{NS_PAGE}"><Metadata><Creator>{creatore}'
            f'</Creator><Created>2026-10-01T10:00:00</Created><LastChange>2026-10-01T10:00:00</LastChange>'
            f'</Metadata><Page imageFilename="{immagine}" imageWidth="2000" imageHeight="3000">{ordine}{regioni}'
            f'</Page></PcGts>').encode("utf-8")


def riga(testo, conf="", custom=""):
    c = f' conf="{conf}"' if conf else ""
    cu = f' custom="{custom}"' if custom else ""
    return (f'<TextLine id="l{abs(hash(testo)) % 10**6}"{cu}><Coords points="0,0 1,1"/>'
            f'<TextEquiv{c}><Unicode>{testo}</Unicode></TextEquiv></TextLine>')


def regione(rid, righe, tipo="paragraph", custom=""):
    cu = f' custom="{custom}"' if custom else ""
    return f'<TextRegion id="{rid}" type="{tipo}"{cu}><Coords points="0,0 1,1"/>{righe}</TextRegion>'


ALTO = b"""<?xml version="1.0" encoding="UTF-8"?>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#">
  <Description><MeasurementUnit>pixel</MeasurementUnit>
    <sourceImageInformation><fileName>ZP1967-01-12_p3.tif</fileName></sourceImageInformation>
    <OCRProcessing ID="p1"><ocrProcessingStep><processingSoftware>
      <softwareName>Kraken</softwareName><softwareVersion>5.2</softwareVersion>
    </processingSoftware></ocrProcessingStep></OCRProcessing>
  </Description>
  <Layout>
    <Page ID="pag3" PHYSICAL_IMG_NR="3" PRINTED_IMG_NR="3" HEIGHT="3000" WIDTH="2000">
      <PrintSpace>
        <TextBlock ID="b1">
          <TextLine ID="t1"><String CONTENT="Shoku" WC="0.90"/><SP/><String CONTENT="Jacques" WC="0.80"/><SP/>
            <String CONTENT="Grip" WC="0.70"/><HYP CONTENT="-"/></TextLine>
          <TextLine ID="t2"><String CONTENT="pa" WC="0.60"/><SP/><String CONTENT="foli." WC="1.0"/></TextLine>
        </TextBlock>
        <TextBlock ID="b2">
          <TextLine ID="t3" WC="0.5"><String CONTENT="Rruga"/><String CONTENT="e"/><String CONTENT="Partise"/></TextLine>
        </TextBlock>
      </PrintSpace>
    </Page>
  </Layout>
</alto>"""

METS = b"""<?xml version="1.0"?><mets:mets xmlns:mets="http://www.loc.gov/METS/"><mets:fileSec/></mets:mets>"""


class Page(unittest.TestCase):
    def test_ordine_di_lettura_e_numero_di_pagina(self):
        regioni = (regione("r1", riga("Seconda colonna", "0.5")) + regione("r2", riga("Titolo", "0.9"))
                   + regione("r3", riga("12"), tipo="page-number"))
        ordine = ('<ReadingOrder><OrderedGroup id="g1"><RegionRefIndexed index="1" regionRef="r1"/>'
                  '<RegionRefIndexed index="0" regionRef="r2"/></OrderedGroup></ReadingOrder>')
        (pg,) = X.leggi_xml(page(regioni, ordine))
        self.assertEqual(pg["testo"], "Titolo\n\nSeconda colonna")      # r3 è il numero di pagina
        self.assertEqual((pg["pagina_stampata"], pg["formato"], pg["motore"]), ("12", "PAGE XML", "Transkribus"))
        self.assertEqual(pg["confidenza"], round((90 * 6 + 50 * 15) / 21, 1))

    def test_ordine_custom_di_transkribus(self):
        regioni = (regione("r1", riga("dopo", custom="readingOrder {index:1;}"), custom="readingOrder {index:1;}")
                   + regione("r2", riga("b", custom="readingOrder {index:1;}") + riga("a", custom="readingOrder {index:0;}"),
                             custom="readingOrder {index:0;}"))
        self.assertEqual(X.leggi_xml(page(regioni))[0]["testo"], "a\nb\n\ndopo")

    def test_gruppi_annidati(self):
        regioni = regione("r1", riga("uno")) + regione("r2", riga("due")) + regione("r3", riga("tre"))
        ordine = ('<ReadingOrder><OrderedGroup id="g"><RegionRefIndexed index="1" regionRef="r3"/>'
                  '<OrderedGroupIndexed id="g2" index="0"><RegionRefIndexed index="0" regionRef="r1"/>'
                  '<RegionRefIndexed index="1" regionRef="r2"/></OrderedGroupIndexed></OrderedGroup></ReadingOrder>')
        self.assertEqual(X.leggi_xml(page(regioni, ordine))[0]["testo"], "uno\n\ndue\n\ntre")

    def test_riga_fatta_di_parole_e_numero_non_numerico(self):
        parole = ('<TextLine id="lw"><Word id="w1"><TextEquiv conf="0.8"><Unicode>格里巴</Unicode></TextEquiv></Word>'
                  '<Word id="w2"><TextEquiv><Unicode>同志</Unicode></TextEquiv></Word></TextLine>')
        regioni = regione("r1", parole) + regione("r2", riga("Chapter Two"), tipo="page-number")
        (pg,) = X.leggi_xml(page(regioni))
        self.assertEqual(pg["testo"], "格里巴 同志\n\nChapter Two")           # non è un numero: resta nel testo
        self.assertEqual(pg["pagina_stampata"], "")

    def test_numeri_di_pagina(self):
        self.assertEqual([X.pagina_stampata(t) for t in ("12", "[12]", "xiv", "12a", "- 12 -", "Capitolo")],
                         ["12", "12", "xiv", "12a", "", ""])


class Alto(unittest.TestCase):
    def test_parole_spazi_trattini_e_confidenza(self):
        (pg,) = X.leggi_xml(ALTO)
        self.assertEqual(pg["testo"], "Shoku Jacques Grip-\npa foli.\n\nRruga e Partise")
        self.assertEqual((pg["pagina_stampata"], pg["formato"], pg["motore"]), ("3", "ALTO XML", "Kraken 5.2"))
        self.assertEqual(pg["confidenza"], round((90 * 5 + 80 * 7 + 70 * 4 + 60 * 2 + 100 * 5 + 50 * 15) / 38, 1))

    def test_marcatore(self):
        self.assertEqual(X.marcatore({"pagina_stampata": "3"}, 7), "[[p. 3 | img 7]]")
        self.assertEqual(X.marcatore({"pagina_stampata": ""}, 7), "")

    def test_marcatore_riconosciuto_dalle_citazioni(self):
        import citazioni as C
        testo = "[[p. 3 | img 7]]\nGrippa\n"
        self.assertEqual(C.pagina_nel_testo(testo, testo.index("Grippa")), "3")


class FileEArchivi(unittest.TestCase):
    def test_zip_in_ordine_naturale_e_mets_ignorato(self):
        with tempfile.TemporaryDirectory() as tmp:
            z = Path(tmp) / "esportazione.zip"
            with zipfile.ZipFile(z, "w") as f:
                f.writestr("doc/page/p10.xml", page(regione("r", riga("dieci"))))
                f.writestr("doc/page/p2.xml", page(regione("r", riga("due"))))
                f.writestr("doc/mets.xml", METS)
            pagine, ignorati = X.leggi(z)
            self.assertEqual([p["testo"] for p in pagine], ["due", "dieci"])
            self.assertEqual(ignorati, ["doc/mets.xml"])

    def test_xml_non_valido(self):
        with self.assertRaises(ValueError):
            X.leggi_xml(b"<PcGts><Page>", "rotto.xml")


def configurazione(radice):
    """config.ini sostituito: dati, risultati e importazioni nella cartella temporanea."""
    (radice / "serie.ini").write_text(SERIE, encoding="utf-8")
    cfg = configparser.ConfigParser(interpolation=None)
    cfg["percorsi"] = {"dati": str(radice / "data"), "risultati": str(radice / "risultati"),
                       "entita": str(radice / "entita.ini"), "serie": str(radice / "serie.ini"),
                       "problemi": str(radice / "p.csv")}
    return cfg


SERIE = """[Zëri i Popullit]
tipo = periodico
lingua = sq
cartella = riviste/zeri_i_popullit
sigla = ZP
citazione = Zëri i Popullit, {data}[, n. {numero}]
chicago = *Zëri i Popullit*[, {numero_lbl}][, {contenitore}], {data_o_anno}[, {pagina}]
"""


class Importazione(unittest.TestCase):
    def importa(self, sorgente, controlla=False):
        with tempfile.TemporaryDirectory() as tmp:
            radice = Path(tmp)
            cfg = configurazione(radice)
            originale, I.leggi_config = I.leggi_config, lambda: cfg
            try:
                codice = I.main(["importa", str(sorgente(radice)), "--serie", "Zëri i Popullit", "--senza-indice"])
                controllo = ""
                if controlla:
                    I.cmd_controlla(argparse.Namespace(cartella=None, lingua=False, migra_stati=False),
                                    stampa=lambda *a: None, cfg=cfg)
                    controllo = next((radice / "importazioni").glob("controllo_*.csv")).read_text(encoding="utf-8-sig")
            finally:
                I.leggi_config = originale
            scritti = sorted((radice / "data").rglob("*.txt"))
            return codice, [(f.name, f.read_text(encoding="utf-8")) for f in scritti], controllo

    def test_cartella_di_pagine_e_un_documento(self):
        def sorgente(radice):
            d = radice / "esportazioni" / "ZP1967-01-12"
            d.mkdir(parents=True)
            (d / "p10.xml").write_bytes(page(regione("r", riga("Grippa foli")) + regione("n", riga("10"), "page-number")))
            (d / "p2.xml").write_bytes(ALTO.replace(b'PRINTED_IMG_NR="3"', b'PRINTED_IMG_NR="2"'))
            (d / "mets.xml").write_bytes(METS)
            return radice / "esportazioni"
        codice, scritti, _ = self.importa(sorgente)
        self.assertEqual(codice, 0)
        self.assertEqual([n for n, _ in scritti], ["ZP1967-01-12.txt"])
        testo = scritti[0][1]
        self.assertIn("[DATE: 1967-01-12]", testo)                            # dal nome della cartella
        self.assertIn("[TEXT_METHOD: importazione ALTO XML + importazione PAGE XML]", testo)
        self.assertIn("[OCR_ENGINE: Kraken 5.2; Transkribus]", testo)
        self.assertIn("[PAGES: 2-10]", testo)
        corpo = testo.split("\n\n", 1)[1]
        self.assertLess(corpo.index("[[p. 2 | img 1]]"), corpo.index("[[p. 10 | img 2]]"))   # ordine naturale
        self.assertIn("Grip-\npa", corpo)

    def test_controllo_delle_intestazioni_senza_errori(self):
        def sorgente(radice):
            d = radice / "esportazioni" / "ZP1967-01-12"
            d.mkdir(parents=True)
            lungo = ('<TextBlock ID="b9"><TextLine ID="t9"><String CONTENT="'
                     + "Partia e Punes dhe populli shqiptar " * 4 + '"/></TextLine></TextBlock></PrintSpace>').encode()
            for n in (1, 2):
                (d / f"p{n}.xml").write_bytes(ALTO.replace(b'PRINTED_IMG_NR="3"', f'PRINTED_IMG_NR="{n}"'.encode())
                                              .replace(b"</PrintSpace>", lungo))
            return d
        codice, scritti, controllo = self.importa(sorgente, controlla=True)
        self.assertEqual((codice, len(scritti)), (0, 1))
        self.assertNotIn("errore", controllo.lower().split("\n", 1)[1])
        self.assertNotIn("marcator", controllo.lower())

    def test_nessuna_pagina_leggibile(self):
        def sorgente(radice):
            d = radice / "esportazioni" / "solo_mets"
            d.mkdir(parents=True)
            (d / "mets.xml").write_bytes(METS)
            return d
        codice, scritti, _ = self.importa(sorgente)
        self.assertEqual((codice, scritti), (4, []))


if __name__ == "__main__":
    unittest.main()

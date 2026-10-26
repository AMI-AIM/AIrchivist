"""
Test degli originali delle importazioni (importa.py, conserva_originale): ogni documento importato lascia in
sources/ una copia intatta dell'originale, nella stessa sottocartella che il .txt ha in data/; SOURCE_FILE e
SOURCE_HASH dell'intestazione rimandano a quella copia; un originale già in sources/ non si modifica mai.
"""
import configparser
import hashlib
import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

MOTORE = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(MOTORE))
import importa as I  # noqa: E402
from estrai_occorrenze import leggi_intestazione  # noqa: E402

SERIE = ("[CIA]\ntipo = volume\nlingua = en\ncartella = volumi/cia\ncitazione = {titolo}, {data}\n"
         "autore = Central Intelligence Agency\nchicago = {autore}. *{titolo}*. {data_o_anno}[, {pagina}]\n")
PAROLE = ("The Chinese leadership continued to support the Marxist-Leninist parties abroad, although the "
          "volume of propaganda declined after the Ninth Congress. ") * 6


def sha(dati):
    return "sha256:" + hashlib.sha256(dati).hexdigest()


class Originali(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.radice = r = Path(self._tmp.name)
        (r / "series.ini").write_text(SERIE, encoding="utf-8")
        self.cfg = configparser.ConfigParser(interpolation=None)
        self.cfg["percorsi"] = {"dati": str(r / "data"), "risultati": str(r / "results"),
                                "entita": str(r / "entities.ini"), "serie": str(r / "series.ini"),
                                "problemi": str(r / "p.csv"), "importazioni": str(r / "audit" / "checks"),
                                "registro_importazioni": str(r / "audit" / "imports.csv"),
                                "cache": str(r / "system" / "cache"), "originali": str(r / "sources")}
        self.fuori = r / "caricati"
        self.fuori.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def importa(self, *argomenti):
        originale, I.leggi_config = I.leggi_config, lambda: self.cfg
        try:
            with redirect_stdout(io.StringIO()) as uscita:
                codice = I.main(["importa", *map(str, argomenti), "--serie", "CIA", "--senza-indice"])
        finally:
            I.leggi_config = originale
        self.assertEqual(codice, 0, uscita.getvalue())
        return uscita.getvalue()

    def intestazione(self, nome):
        f = self.radice / "data" / "volumi" / "cia" / nome
        return leggi_intestazione(f.read_text(encoding="utf-8"))[0]

    def scrivi(self, nome, testo):
        f = self.fuori / nome
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(testo.encode("utf-8"))
        return f

    def test_originale_copiato_e_citato(self):
        f = self.scrivi("rapporto.txt", PAROLE + "\r\n")            # anche i fine riga restano quelli
        self.importa(f, "--data", "1971-11", "--titolo", "Rapporto")
        copia = self.radice / "sources" / "volumi" / "cia" / "rapporto.txt"
        self.assertEqual(copia.read_bytes(), f.read_bytes())
        meta = self.intestazione(next((self.radice / "data" / "volumi" / "cia").glob("*.txt")).name)
        self.assertEqual(meta["SOURCE_FILE"], "volumi/cia/rapporto.txt")
        self.assertEqual(meta["SOURCE_HASH"], sha(f.read_bytes()))

    def test_originale_mai_modificato(self):
        f = self.scrivi("rapporto.txt", PAROLE)
        self.importa(f, "--data", "1971-11", "--titolo", "Rapporto")
        copia = self.radice / "sources" / "volumi" / "cia" / "rapporto.txt"
        prima = copia.read_bytes()
        self.importa(f, "--data", "1971-11", "--titolo", "Rapporto", "--sovrascrivi")     # stesso file: riusato
        self.assertEqual(len(list(copia.parent.iterdir())), 1)
        f.write_bytes((PAROLE + " Revised.").encode("utf-8"))                              # stesso nome, altro testo
        uscita = self.importa(f, "--data", "1971-11", "--titolo", "Rapporto", "--sovrascrivi")
        self.assertEqual(copia.read_bytes(), prima)
        nuovo = copia.parent / f"rapporto-{hashlib.sha256(f.read_bytes()).hexdigest()[:8]}.txt"
        self.assertEqual(nuovo.read_bytes(), f.read_bytes())
        self.assertIn("originale conservato come", uscita)
        meta = self.intestazione(next((self.radice / "data" / "volumi" / "cia").glob("*.txt")).name)
        self.assertEqual(meta["SOURCE_FILE"], f"volumi/cia/{nuovo.name}")
        self.assertEqual(meta["SOURCE_HASH"], sha(f.read_bytes()))

    def test_documento_di_piu_file(self):
        a = self.scrivi("pagine/p1.txt", PAROLE)
        b = self.scrivi("pagine/sotto/p2.txt", PAROLE.upper())
        self.importa(a, b, "--unisci", "--data", "1971-11", "--titolo", "Rapporto unito")
        nome = next((self.radice / "data" / "volumi" / "cia").glob("*.txt")).name
        cartella = self.radice / "sources" / "volumi" / "cia" / Path(nome).stem
        self.assertEqual((cartella / "p1.txt").read_bytes(), a.read_bytes())
        self.assertEqual((cartella / "sotto" / "p2.txt").read_bytes(), b.read_bytes())
        meta = self.intestazione(nome)
        self.assertEqual(meta["SOURCE_FILE"], f"volumi/cia/{Path(nome).stem}/")
        self.assertEqual(meta["SOURCE_HASH"], "sha256:" + I.impronta_cartella(cartella))
        self.assertFalse(any(p.name.endswith(".parziale") for p in cartella.parent.iterdir()))

    def test_la_prova_non_copia(self):
        f = self.scrivi("rapporto.txt", PAROLE)
        self.importa(f, "--prova", "1")
        self.assertFalse((self.radice / "sources").exists())


if __name__ == "__main__":
    unittest.main()

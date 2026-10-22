#!/usr/bin/env python3
"""
Indice di ricerca testuale delle fonti (SQLite FTS5, libreria standard di Python).

Serve a cercare in pochi istanti una forma di un nome in tutte le fonti, invece di rileggere ogni volta
circa 1 GB di testo: lo usano gli strumenti esplora_nome e cerca_testo del server MCP.
L'indice contiene solo i riferimenti (file e riga), non il testo: i passaggi si rileggono dai file originali.

Uso:
  python indice.py costruisci     (la prima volta, o per ripulirlo dopo molte correzioni; 10-30 minuti)
  python indice.py aggiorna       (dopo aver aggiunto o corretto file in data\\: indicizza solo quelli; pochi secondi)
  python indice.py stato          (file indicizzati e data di costruzione)
  python indice.py cerca "格里巴"  (prova: occorrenze per serie e anno)
"""
import bisect
import datetime as dt
import re
import sqlite3
import sys
import threading
import time
from collections import Counter, defaultdict
from pathlib import Path

CARTELLA = Path(__file__).resolve().parent
sys.path.insert(0, str(CARTELLA))
# pattern_variante è ora unico per estrazione e indice: ignora gli accenti (come faceva pattern_latino),
# così una forma con l'accento caduto nell'OCR non può sfuggire all'estrazione pur essendo nell'indice
from estrai_occorrenze import is_cjk, leggi_intestazione, metadati, pattern_variante, senza_accenti   # noqa: E402

RIGHE_PER_FILE = 10_000_000          # rowid = id del file * RIGHE_PER_FILE + numero di riga
CJK = re.compile(r"([㐀-鿿豈-﫿])")
SERIE_BREVE = {"Red Flag": "Hongqi"}


def percorso_indice(cfg):
    from llm import percorso
    try:
        return percorso(cfg, "indice")
    except Exception:
        return percorso(cfg, "risultati").parent / "indice" / "fonti.sqlite"


def prepara(testo):
    """Ogni carattere cinese diventa una parola: così le ricerche di frase trovano qualsiasi sequenza."""
    return CJK.sub(r" \1 ", testo)


def pattern_latino(forma):
    """Delegata a pattern_variante (unica per estrazione e indice): ora tollera anche sillabazione con
    trattini morbidi/lineette, spazi e a capo spezzati dall'OCR dentro i nomi in caratteri latini."""
    return pattern_variante(forma)


def lingua_testo(meta, inizio):
    """"zh" per i testi cinesi (dall'intestazione [LANG] o dalla quota di caratteri cinesi); per gli altri il
    codice di [LANG] ("sq", "it", "fr"...), oppure "en" se manca."""
    lang = (meta.get("LANG") or "").lower().strip()
    if lang:
        return "zh" if lang.startswith("zh") else lang[:2]
    lettere = [ch for ch in inizio if ch.isalpha()]
    cinesi = sum(1 for ch in lettere if "\u3400" <= ch <= "\u9fff")
    return "zh" if lettere and cinesi / len(lettere) > 0.3 else "en"


def lingua_di(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            testo = f.read(6000)
    except OSError:
        return "en"
    meta, pos = leggi_intestazione(testo)
    return lingua_testo(meta, testo[pos:])


def stato_dati(dati):
    """Firma della cartella delle fonti (numero di file, dimensione, ultima modifica)."""
    n, dim, ultima = 0, 0, 0.0
    for f in Path(dati).rglob("*.txt"):
        s = f.stat()
        n, dim, ultima = n + 1, dim + s.st_size, max(ultima, s.st_mtime)
    return f"{n}|{dim}|{int(ultima)}"


class Indice:
    def __init__(self, db, dati):
        self.db, self.dati = Path(db), Path(dati)
        self.costruzione = {"in_corso": False, "fatti": 0, "totale": 0, "errore": "", "aggiornamento": False}
        self._blocco = threading.Lock()

    # ------------------------------------------------------------ costruzione
    def pronto(self):
        if not self.db.exists() or self.costruzione["in_corso"]:
            return False
        try:
            with sqlite3.connect(self.db) as c:
                r = c.execute("SELECT valore FROM info WHERE chiave='firma'").fetchone()
            return bool(r)
        except sqlite3.Error:
            return False

    def aggiornato(self):
        try:
            with sqlite3.connect(self.db) as c:
                r = c.execute("SELECT valore FROM info WHERE chiave='firma'").fetchone()
            return bool(r) and r[0] == stato_dati(self.dati)
        except sqlite3.Error:
            return False

    def costruisci(self, stampa=print, tempo_max=None):
        """Costruisce l'indice. Con tempo_max (secondi) si ferma prima e riprende alla chiamata successiva
        da dove era arrivato; restituisce True quando l'indice è completo."""
        with self._blocco:
            self.costruzione.update(in_corso=True, errore="")
            try:
                return self._costruisci(stampa, tempo_max)
            except Exception as e:
                self.costruzione["errore"] = f"{type(e).__name__}: {e}"
                raise
            finally:
                self.costruzione["in_corso"] = False

    def _costruisci(self, stampa, tempo_max):
        self.db.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.db.with_name(self.db.name + ".parziale")
        files = sorted(Path(self.dati).rglob("*.txt"))
        firma = stato_dati(self.dati)
        self.costruzione["totale"] = len(files)
        c = sqlite3.connect(tmp)
        c.executescript("""
            PRAGMA synchronous=OFF;
            CREATE TABLE IF NOT EXISTS info(chiave TEXT PRIMARY KEY, valore TEXT);
            CREATE TABLE IF NOT EXISTS file(id INTEGER PRIMARY KEY, percorso TEXT, serie TEXT, citazione TEXT,
                                            data TEXT, anno INTEGER, inizio INTEGER, lingua TEXT);
            CREATE VIRTUAL TABLE IF NOT EXISTS testo USING fts5(t, content='',
                                                                tokenize='unicode61 remove_diacritics 2');
            CREATE TABLE IF NOT EXISTS stato_file(id INTEGER PRIMARY KEY, dim INTEGER, mtime INTEGER);
        """)
        vecchia = c.execute("SELECT valore FROM info WHERE chiave='firma_parziale'").fetchone()
        if vecchia and vecchia[0] != firma:            # le fonti sono cambiate a metà: si ricomincia
            c.close()
            tmp.unlink()
            return self._costruisci(stampa, tempo_max)
        c.execute("INSERT OR REPLACE INTO info VALUES ('firma_parziale', ?)", (firma,))
        fatti = c.execute("SELECT coalesce(max(id), 0) FROM file").fetchone()[0]
        t0 = time.time()
        for fid, f in enumerate(files, 1):
            if fid <= fatti:
                continue
            self._indicizza(c, fid, f)
            self.costruzione["fatti"] = fid
            if fid % 200 == 0:
                c.commit()
            if fid % 500 == 0:
                stampa(f"  {fid}/{len(files)} file")
            if tempo_max and time.time() - t0 > tempo_max:
                c.commit()
                c.close()
                stampa(f"Indice parziale: {fid}/{len(files)} file. Rilancia per continuare.")
                return False
        c.execute("INSERT OR REPLACE INTO info VALUES ('firma', ?)", (firma,))
        c.execute("INSERT OR REPLACE INTO info VALUES ('costruito_il', ?)",
                  (dt.datetime.now().isoformat(timespec="minutes"),))
        c.commit()
        c.close()
        tmp.replace(self.db)
        stampa(f"Indice completo: {len(files)} file ({self.db}).")
        return True

    def _indicizza(self, c, fid, f):
        """Aggiunge un file all'indice con il numero fid."""
        st = f.stat()
        testo = f.read_text(encoding="utf-8", errors="replace")
        meta, pos = leggi_intestazione(testo)
        rel, fonte, citazione, data, _ = metadati(f, self.dati, meta)
        anno = int(data[:4]) if data[:4].isdigit() else None
        inizio = testo[:pos].count("\n") + 1          # prima riga del testo vero e proprio
        righe = testo.split("\n")
        c.executemany("INSERT INTO testo(rowid, t) VALUES (?, ?)",
                      ((fid * RIGHE_PER_FILE + n, prepara(r)) for n, r in enumerate(righe, 1)
                       if n >= inizio and r.strip()))
        c.execute("INSERT INTO file VALUES (?,?,?,?,?,?,?,?)",
                  (fid, rel, SERIE_BREVE.get(fonte, fonte), citazione, data, anno, inizio,
                   lingua_testo(meta, testo[pos:pos + 4000])))
        c.execute("INSERT OR REPLACE INTO stato_file VALUES (?,?,?)", (fid, st.st_size, int(st.st_mtime)))

    def differenze(self, c=None):
        """(nuovi, modificati, tolti) rispetto all'indice: percorsi relativi alla cartella delle fonti."""
        chiudi = c is None
        c = c or sqlite3.connect(self.db, timeout=30)
        try:
            c.execute("CREATE TABLE IF NOT EXISTS stato_file(id INTEGER PRIMARY KEY, dim INTEGER, mtime INTEGER)")
            indicizzati = {r[1]: r[0] for r in c.execute("SELECT id, percorso FROM file")}
            stati = {r[0]: (r[1], r[2]) for r in c.execute("SELECT id, dim, mtime FROM stato_file")}
            quando = c.execute("SELECT valore FROM info WHERE chiave='costruito_il'").fetchone()
            try:
                costruito = dt.datetime.fromisoformat(quando[0]).timestamp() if quando else None
            except ValueError:
                costruito = None
            presenti = {f.relative_to(self.dati).as_posix(): f for f in sorted(self.dati.rglob("*.txt"))}
            nuovi, modificati = [], []
            for rel, f in presenti.items():
                st = f.stat()
                firma = (st.st_size, int(st.st_mtime))
                fid = indicizzati.get(rel)
                if fid is None:
                    nuovi.append(rel)
                elif fid in stati:
                    if stati[fid] != firma:
                        modificati.append(rel)
                elif costruito and st.st_mtime > costruito + 60:
                    modificati.append(rel)        # indice di prima versione: vale la data di costruzione
                else:
                    c.execute("INSERT OR REPLACE INTO stato_file VALUES (?,?,?)", (fid, *firma))
            c.commit()
            tolti = [rel for rel in indicizzati if rel not in presenti]
            return nuovi, modificati, tolti
        finally:
            if chiudi:
                c.close()

    def aggiorna(self, stampa=print, tempo_max=None):
        """Allinea l'indice alle fonti senza ricostruirlo: indicizza i file nuovi o modificati e toglie quelli
        cancellati. Con tempo_max (secondi) si ferma prima e riprende alla chiamata successiva. Restituisce True
        quando l'indice è di nuovo aggiornato. Se l'indice non esiste, lo costruisce da capo."""
        if not self.pronto():
            return self.costruisci(stampa, tempo_max)
        with self._blocco:
            self.costruzione.update(aggiornamento=True, errore="")
            try:
                return self._aggiorna(stampa, tempo_max)
            except Exception as e:
                self.costruzione["errore"] = f"{type(e).__name__}: {e}"
                raise
            finally:
                self.costruzione["aggiornamento"] = False

    def _aggiorna(self, stampa, tempo_max):
        t0 = time.time()
        c = sqlite3.connect(self.db, timeout=60)
        try:
            nuovi, modificati, tolti = self.differenze(c)
            if not (nuovi or modificati or tolti):
                c.execute("INSERT OR REPLACE INTO info VALUES ('firma', ?)", (stato_dati(self.dati),))
                c.commit()
                return True
            stampa(f"Aggiorno l'indice: {len(nuovi)} file nuovi, {len(modificati)} modificati, {len(tolti)} tolti.")
            # i file tolti o modificati escono dalla tabella dei file; le loro righe restano nell'indice di testo
            # (non si possono cancellare da un indice senza contenuto) ma non vengono più considerate
            vecchi = [r for r in modificati + tolti]
            for rel in vecchi:
                fid = c.execute("SELECT id FROM file WHERE percorso=?", (rel,)).fetchone()
                if fid:
                    c.execute("DELETE FROM file WHERE id=?", fid)
                    c.execute("DELETE FROM stato_file WHERE id=?", fid)
            orfani = int((c.execute("SELECT valore FROM info WHERE chiave='file_orfani'").fetchone() or [0])[0])
            c.execute("INSERT OR REPLACE INTO info VALUES ('file_orfani', ?)", (str(orfani + len(vecchi)),))
            c.commit()
            # numeri mai usati prima (anche da file tolti), così le righe orfane non si confondono con le nuove
            ultimo = max(c.execute("SELECT coalesce(max(id), 0) FROM file").fetchone()[0],
                         (c.execute("SELECT coalesce(max(rowid), 0) FROM testo").fetchone()[0]) // RIGHE_PER_FILE)
            da_fare = sorted(nuovi + modificati)
            for k, rel in enumerate(da_fare, 1):
                ultimo += 1
                self._indicizza(c, ultimo, self.dati / rel)
                if k % 50 == 0:
                    c.commit()
                    stampa(f"  {k}/{len(da_fare)} file")
                if tempo_max and time.time() - t0 > tempo_max and k < len(da_fare):
                    c.commit()
                    stampa(f"Aggiornamento parziale: {k}/{len(da_fare)} file. Rilancia per continuare.")
                    return False
            c.execute("INSERT OR REPLACE INTO info VALUES ('firma', ?)", (stato_dati(self.dati),))
            c.execute("INSERT OR REPLACE INTO info VALUES ('aggiornato_il', ?)",
                      (dt.datetime.now().isoformat(timespec="minutes"),))
            c.commit()
        finally:
            c.close()
            self._tab_file, self._anni, self._freq = None, None, {}
        stampa(f"Indice aggiornato ({len(da_fare)} file indicizzati).")
        return True

    def aggiorna_in_background(self):
        if self.costruzione["in_corso"] or self.costruzione["aggiornamento"]:
            return
        threading.Thread(target=self.aggiorna, kwargs={"stampa": lambda *a: print(*a, file=sys.stderr)},
                         daemon=True).start()

    def costruisci_in_background(self):
        if self.costruzione["in_corso"]:
            return
        threading.Thread(target=self.costruisci, kwargs={"stampa": lambda *a: print(*a, file=sys.stderr)},
                         daemon=True).start()

    # ------------------------------------------------------------ ricerca
    def _connetti(self):
        return sqlite3.connect(f"file:{self.db}?mode=ro", uri=True, check_same_thread=False)

    def _file(self):
        """Tabella dei file (con la lingua, aggiunta qui se l'indice è stato costruito senza)."""
        if getattr(self, "_tab_file", None) is None:
            with sqlite3.connect(self.db) as c:
                colonne = [r[1] for r in c.execute("PRAGMA table_info(file)")]
                if "lingua" not in colonne:
                    c.execute("ALTER TABLE file ADD COLUMN lingua TEXT")
                    for fid, rel in c.execute("SELECT id, percorso FROM file").fetchall():
                        c.execute("UPDATE file SET lingua=? WHERE id=?", (lingua_di(self.dati / rel), fid))
                self._tab_file = {r[0]: r for r in c.execute(
                    "SELECT id, percorso, serie, citazione, data, anno, lingua FROM file")}
        return self._tab_file

    def cerca(self, forma, dal=None, al=None, serie=None, massimo_righe=20000, solo_date=None, lingue=None):
        """Righe che contengono la forma, con le stesse tolleranze della ricerca completa (spezzature
        dell'OCR, sillabazione, punto centrale facoltativo). Le forme cinesi si cercano con l'indice; quelle
        in caratteri latini scorrendo i file non cinesi (l'OCR incolla spesso le parole: "byJacques")."""
        forma = (forma or "").strip()
        if not forma:
            return []
        rx = re.compile(pattern_variante(forma) if is_cjk(forma) else pattern_latino(forma), re.IGNORECASE)
        file = self._file()

        def ammesso(fid):
            _, rel, s, cit, data, anno, lingua = file[fid]
            if serie and s not in serie:
                return False
            if lingue and lingua not in lingue:
                return False
            if solo_date is not None and data not in solo_date:
                return False
            if (dal or al) and not anno:
                return False
            return not (anno and ((dal and anno < int(dal)) or (al and anno > int(al))))

        out = []
        if is_cjk(forma):
            car = CJK.findall(forma)
            with self._connetti() as c:
                ids = [r[0] for r in c.execute("SELECT rowid FROM testo WHERE testo MATCH ? LIMIT ?",
                                               ('"' + " ".join(car) + '"', massimo_righe))]
            per_file = defaultdict(set)
            for rid in ids:
                per_file[rid // RIGHE_PER_FILE].add(rid % RIGHE_PER_FILE)
            for fid, righe in per_file.items():
                if fid not in file or not ammesso(fid):
                    continue
                _, rel, s, cit, data, anno, _l = file[fid]
                testo = (self.dati / rel).read_text(encoding="utf-8", errors="replace").split("\n")
                for n in sorted(righe):
                    riga = testo[n - 1] if n <= len(testo) else ""
                    unita = riga + (" " + testo[n] if n < len(testo) else "")   # forma spezzata dall'a capo
                    m = rx.search(unita)
                    if m and m.start() < len(riga):
                        out.append({"file": rel, "riga": n, "serie": s, "citazione": cit, "data": data,
                                    "anno": anno, "trovato": m.group(0), "testo": riga})
        else:
            for fid, (_, rel, s, cit, data, anno, lingua) in file.items():
                if lingua == "zh" or not ammesso(fid):
                    continue
                testo = (self.dati / rel).read_text(encoding="utf-8", errors="replace")
                inizi, viste = None, set()
                for m in rx.finditer(testo):
                    if inizi is None:
                        inizi = [0] + [k + 1 for k, ch in enumerate(testo) if ch == "\n"]
                    n = bisect.bisect_right(inizi, m.start())
                    if n in viste:
                        continue
                    viste.add(n)
                    fine = testo.find("\n", inizi[n - 1])
                    out.append({"file": rel, "riga": n, "serie": s, "citazione": cit, "data": data, "anno": anno,
                                "trovato": re.sub(r"\s+", " ", m.group(0)),
                                "testo": testo[inizi[n - 1]:fine if fine >= 0 else None]})
                    if len(out) >= massimo_righe:
                        break
        out.sort(key=lambda x: (x["data"] or "9999", x["file"], x["riga"]))
        return out

    def file_candidati(self, varianti):
        """File che possono contenere almeno una delle varianti (insieme largo: la ricerca vera la fa poi
        l'espressione regolare su questi file).
        Solo il Renmin Ribao (testo digitale, un paragrafo per riga: i nomi non vengono spezzati) viene
        filtrato con l'indice; gli altri file (OCR, dove un nome può essere spezzato da un a capo o incollato
        alle parole vicine) si leggono sempre tutti."""
        file = self._file()
        trovati = {r[1] for r in file.values() if r[2] != "Renmin Ribao"}
        rr = {fid: r[1] for fid, r in file.items() if r[2] == "Renmin Ribao"}
        domande = set()
        for v in varianti:
            car = CJK.findall(v)
            if car:
                domande.add('"' + " ".join(car) + '"')
            parole = [re.sub(r"[^a-z]", "", senza_accenti(w).lower())
                      for w in re.split(r"[^A-Za-zÀ-ÿ]+", v) if len(w) >= 3]
            parole = [w for w in parole if len(w) >= 3]
            if parole:            # basta la parola più rara: se la forma c'è, c'è anche lei
                domande.add(min((w[:5] + "*" for w in parole), key=self._frequenza))
        with self._connetti() as c:
            for d in domande:
                minimo, massimo = min(rr) * RIGHE_PER_FILE, (max(rr) + 1) * RIGHE_PER_FILE
                ultimo = None
                for (rid,) in c.execute("SELECT rowid FROM testo WHERE testo MATCH ? AND rowid BETWEEN ? AND ?",
                                        (d, minimo, massimo)):
                    fid = rid // RIGHE_PER_FILE
                    if fid != ultimo and fid in rr:
                        trovati.add(rr[fid])
                        ultimo = fid
        return trovati

    def _frequenza(self, domanda):
        if not hasattr(self, "_freq"):
            self._freq = {}
        if domanda not in self._freq:
            with self._connetti() as c:
                try:
                    self._freq[domanda] = c.execute("SELECT count(*) FROM testo WHERE testo MATCH ?",
                                                    (domanda,)).fetchone()[0]
                except sqlite3.Error:
                    self._freq[domanda] = 10 ** 12
        return self._freq[domanda]

    def anno_di(self, rel):
        if getattr(self, "_anni", None) is None:
            self._anni = {r[1]: r[5] for r in self._file().values()}
        return self._anni.get(rel)

    def lingue(self):
        """Lingue presenti nell'indice, con il numero di file."""
        return dict(Counter(r[6] for r in self._file().values()))

    def conta(self, forma):
        """Numero di righe che contengono una forma cinese (solo indice, senza rileggere i file; può includere
        le righe di file tolti o modificati dopo la costruzione)."""
        car = CJK.findall(forma or "")
        if not car:
            return 0
        with self._connetti() as c:
            return c.execute("SELECT count(*) FROM testo WHERE testo MATCH ?", ('"' + " ".join(car) + '"',)
                             ).fetchone()[0]

    def riga(self, rel, n):
        try:
            return (self.dati / rel).read_text(encoding="utf-8", errors="replace").split("\n")[n - 1]
        except (OSError, IndexError):
            return ""

    def righe_in_date(self, serie, da_data, a_data):
        """File di una serie tra due date (per allineare Peking Review e Renmin Ribao)."""
        with self._connetti() as c:
            return [r[0] for r in c.execute("SELECT percorso FROM file WHERE serie=? AND data BETWEEN ? AND ? "
                                            "ORDER BY data", (serie, da_data, a_data))]


def riepilogo(righe):
    per = defaultdict(Counter)
    for r in righe:
        per[r["serie"]][r["anno"] or "senza data"] += 1
    return {s: dict(sorted(c.items(), key=lambda x: str(x[0]))) for s, c in per.items()}


def main():
    from llm import leggi_config, percorso
    cfg = leggi_config()
    ind = Indice(percorso_indice(cfg), percorso(cfg, "dati"))
    azione = sys.argv[1] if len(sys.argv) > 1 else "stato"
    if azione == "costruisci":
        print(f"Costruisco l'indice di {percorso(cfg, 'dati')} in {ind.db} ...")
        ind.costruisci()
    elif azione == "aggiorna":
        ind.aggiorna()
    elif azione == "cerca" and len(sys.argv) > 2:
        if not ind.pronto():
            sys.exit("Indice assente: python indice.py costruisci")
        t0 = time.time()
        r = ind.cerca(sys.argv[2])
        print(f"{len(r)} righe in {time.time() - t0:.1f} s")
        for s, c in riepilogo(r).items():
            print(f"  {s}: {c}")
        for x in r[:5]:
            print(f"  {x['citazione'] or x['file']} ({x['file']}, riga {x['riga']}): …{x['trovato']}…")
    else:
        if not ind.db.exists():
            print("Indice assente: python indice.py costruisci")
            return
        with sqlite3.connect(ind.db) as c:
            n = c.execute("SELECT count(*) FROM file").fetchone()[0]
            quando = (c.execute("SELECT valore FROM info WHERE chiave='costruito_il'").fetchone() or ["?"])[0]
            agg = c.execute("SELECT valore FROM info WHERE chiave='aggiornato_il'").fetchone()
            orfani = c.execute("SELECT valore FROM info WHERE chiave='file_orfani'").fetchone()
        print(f"Indice: {n} file, costruito il {quando}" + (f", aggiornato il {agg[0]}" if agg else "") + "; "
              f"{'allineato alle fonti' if ind.aggiornato() else 'NON aggiornato (python indice.py aggiorna)'}. "
              f"({ind.db})")
        if orfani and int(orfani[0]) > 300:
            print(f"  {orfani[0]} file tolti o modificati dopo la costruzione: per ripulire l'indice, "
                  "python indice.py costruisci")
        print("  Lingue: " + ", ".join(f"{k} {v}" for k, v in sorted(ind.lingue().items())))


if __name__ == "__main__":
    main()

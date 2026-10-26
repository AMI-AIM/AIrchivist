#!/usr/bin/env python3
"""
Ordine di lettura dei blocchi di testo di una pagina a più colonne (giornali), per importa.py.

Lo strato di testo dei PDF restituisce i blocchi nell'ordine in cui sono scritti nel file, che nei giornali non è
quello di lettura: nel Renmin Ribao del 1° gennaio 1961, dopo l'inizio della risposta di Chruščëv (colonna 2)
viene un articolo sul Sudan (sotto, colonne 2-3) e solo dopo il seguito della risposta (colonna 3). I passaggi
estratti mescolavano così articoli diversi.

Metodo (XY-cut): la pagina si taglia lungo le strisce bianche che nessun blocco attraversa, orizzontali (fasce,
dall'alto in basso) o verticali (colonne, da sinistra a destra; da destra a sinistra per la scrittura cinese
verticale); a ogni livello vale la direzione con la striscia più larga, e ogni parte si taglia di nuovo. Una
parte che non si può tagliare si legge dall'alto in basso se i blocchi sono impilati, altrimenti conserva l'ordine
del file. Nessuna conoscenza della testata: solo la geometria.
"""

STRISCIA_ORIZZONTALE = 4.0      # punti tipografici: più dell'interlinea tra paragrafi della stessa colonna
STRISCIA_VERTICALE = 3.0        # lo spazio tra due colonne (circa 5 punti nel Renmin Ribao del 1961)


def strisce(riquadri, ids, asse, minimo):
    """Strisce bianche lungo un asse (0 = x, colonne; 1 = y, fasce) tra le proiezioni dei blocchi:
    elenco di (inizio, fine) larghe almeno `minimo`."""
    intervalli = sorted((riquadri[i][asse], riquadri[i][asse + 2]) for i in ids)
    out, fine = [], intervalli[0][1]
    for a, b in intervalli[1:]:
        if a - fine >= minimo:
            out.append((fine, a))
        fine = max(fine, b)
    return out


def ordina(riquadri, da_destra=False):
    """Indici dei riquadri (x0, y0, x1, y1) nell'ordine di lettura."""
    def taglia(ids):
        if len(ids) <= 1:
            return ids
        fasce = strisce(riquadri, ids, 1, STRISCIA_ORIZZONTALE)
        colonne = strisce(riquadri, ids, 0, STRISCIA_VERTICALE)
        if not fasce and not colonne:
            # parte che non si taglia. Blocchi impilati (l'ultima riga di una colonna staccata di 2 punti):
            # dall'alto in basso. Blocchi sovrapposti (un titolo verticale dentro il riquadro del testo): l'ordine
            # del file, che in uno spazio così piccolo di solito è quello giusto
            per_altezza = sorted(ids, key=lambda i: riquadri[i][1])
            impilati = all(riquadri[a][3] <= riquadri[b][1] + 1 for a, b in zip(per_altezza, per_altezza[1:]))
            return per_altezza if impilati else sorted(ids)
        larghezza = lambda s: max(b - a for a, b in s) if s else 0       # noqa: E731
        asse, tagli = (1, fasce) if larghezza(fasce) >= larghezza(colonne) else (0, colonne)
        confini = [(a + b) / 2 for a, b in tagli]
        gruppi = [[] for _ in range(len(confini) + 1)]
        for i in ids:
            centro = (riquadri[i][asse] + riquadri[i][asse + 2]) / 2
            gruppi[sum(1 for c in confini if centro > c)].append(i)
        if asse == 0 and da_destra:
            gruppi.reverse()
        return [i for g in gruppi for i in taglia(g)]
    return taglia(list(range(len(riquadri))))

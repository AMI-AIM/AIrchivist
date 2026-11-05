// Interfaccia di Pressmark: barra laterale, filo della ricerca con la
// casella in basso, pannello laterale per fonte, passaggi e glossario.
// Tutto passa dalle API di app.py; i testi delle fonti si inseriscono sempre come testo, mai come HTML. L'unica
// eccezione è il corpo del documento della risposta, scritto da documento.py con escape e ripulito in inserisciDocumento.
"use strict";

const $ = (id) => document.getElementById(id);
// date e ore nella lingua dell'interfaccia (i18n.js): in inglese, giorno e mese all'europea
const LOCALE = window.Lingua && window.Lingua.lingua === "en" ? "en-GB" : "it-IT";
const stato = { attesa: null, attesaImporta: null, ultimaRisposta: "", doc: null, cachePassaggi: {}, glossario: null,
  fonte: null, thread: null, ricercaEl: null, filoRicerca: null, inCorso: false, convNuova: true, attesaChi: null,
  recenti: [], fili: [], nDocumenti: 0, codaSalvataggi: Promise.resolve(), elenchi: {}, filtroElenco: {},
  elencoIntero: {}, azioniProfilo: null, rinomina: null, recentiAperti: new Set() };

async function api(percorso, dati) {
  const opzioni = { credentials: "same-origin" };
  if (dati !== undefined) {
    opzioni.method = "POST";
    opzioni.headers = { "Content-Type": "application/json", "X-Pressmark": "1" };
    opzioni.body = JSON.stringify(dati);
  }
  let r;
  try {
    r = await fetch(percorso, opzioni);
  } catch (e) {
    throw new Error("L'interfaccia non risponde: controlla che la finestra di app.py sia ancora aperta.");
  }
  let corpo = {};
  try { corpo = await r.json(); } catch (e) { /* risposta non JSON */ }
  if (r.status === 403) throw new Error("Sessione scaduta: riapri l'interfaccia dal collegamento stampato da app.py.");
  if (!r.ok) throw new Error(corpo.errore || `Errore ${r.status}`);
  return corpo;
}

function avviso(testo, errore = false) {
  const a = $("avviso");
  const t = $("avviso-testo");
  const uguale = !a.hidden && t.textContent === testo && a.classList.contains("errore") === errore;
  t.textContent = testo || "";
  a.hidden = !testo;
  a.classList.toggle("errore", errore);
  if (testo && !uguale) annuncia(testo, errore);    // lo stesso avviso rimesso (cambiaModello) non si ripete
}

// lettori di schermo: il testo va nella regione giusta (status o alert); la stessa frase si riannuncia solo se
// la regione è stata svuotata prima
function annuncia(testo, errore = false) {
  const r = $(errore ? "annuncio-errore" : "annuncio");
  $(errore ? "annuncio" : "annuncio-errore").textContent = "";
  r.textContent = "";
  setTimeout(() => { r.textContent = testo; }, 50);
}

function avanzamento(id, percento) {
  const p = Math.round(Math.min(100, Math.max(0, percento)));
  $(id).setAttribute("aria-valuenow", String(p));
  return `${p}%`;
}

function el(tag, testo, classe) {
  const e = document.createElement(tag);
  if (testo !== undefined && testo !== null) e.textContent = testo;
  if (classe) e.className = classe;
  return e;
}

function mostra(id, visibile) { $(id).hidden = !visibile; }

// il riassunto arriva in Markdown: qui basta togliere i segni di corsivo e grassetto
function senzaMarkdown(testo) { return (testo || "").replace(/\*\*([^*]+)\*\*/g, "$1").replace(/\*([^*\s][^*]*)\*/g, "$1"); }

// ------------------------------------------------------------------ viste, pannello laterale, barra
// La pagina è impostata come una conversazione: a sinistra la barra (progetto, recenti, glossario, importazioni, preparazione),
// al centro il filo della ricerca con la casella in basso, a destra il pannello (fonte, passaggi, glossario) che si
// apre quando serve. L'importazione è una vista intera al posto del filo.
function apriScheda(nome) {
  document.querySelectorAll(".schede button").forEach((b) => {
    const attiva = b.dataset.scheda === nome;
    b.classList.toggle("attiva", attiva);
    b.setAttribute("aria-selected", String(attiva));
    b.tabIndex = attiva ? 0 : -1;               // una sola scheda nel giro del tasto Tab; le frecce scorrono le altre
  });
  document.querySelectorAll(".pannello").forEach((p) => { p.hidden = p.dataset.pannello !== nome; });
  if (nome === "passaggi") caricaPassaggi();
  if (nome === "glossario") caricaGlossario();
  segnaPulsantiPannello();
}

// la scheda del pannello che si vede ora; "" se il pannello è chiuso
function schedaAperta() {
  if ($("laterale").hidden) return "";
  const b = document.querySelector(".schede button.attiva");
  return b ? b.dataset.scheda : "";
}

// i pulsanti che aprono il pannello (Glossario nella barra) dicono se la loro scheda è aperta
function segnaPulsantiPannello() {
  const aperta = schedaAperta();
  document.querySelectorAll("[data-pannello-apri]").forEach((b) => {
    b.setAttribute("aria-expanded", String(aperta === b.dataset.pannelloApri));
  });
}

function apriLaterale(nome) {
  mostra("laterale", true);
  apriScheda(nome);
  segnaManiglia("laterale");
  // la risposta non deve stringersi sotto i 30rem (circa 60 caratteri di Georgia): in una finestra stretta la barra
  // dei recenti si chiude finché il pannello resta aperto, come nelle Impostazioni, senza cambiare la scelta ricordata
  const centro = document.querySelector(".centro");
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
  if (centro && centro.offsetWidth < 30 * rem && !$("app").classList.contains("barra-chiusa")) {
    barraLaterale(false, false);
    stato.barraDaRiaprirePannello = true;
  }
}

// un pulsante del pannello apre la sua scheda; premuto di nuovo con la scheda già aperta, chiude il pannello
function alternaLaterale(nome) {
  if (schedaAperta() === nome) chiudiLaterale();
  else apriLaterale(nome);
}

function chiudiLaterale() {
  if ($("laterale").hidden) return;
  const dentro = $("laterale").contains(document.activeElement);
  mostra("laterale", false);
  segnaPulsantiPannello();
  if (stato.barraDaRiaprirePannello) {
    stato.barraDaRiaprirePannello = false;
    barraLaterale(true, false);
  }
  if (dentro) $("testo").focus();
}

// ------------------------------------------------- larghezza della barra e del pannello, trascinandone il bordo
// Il bordo interno di ciascuno è una maniglia: si trascina col mouse, o con le frecce dalla tastiera (Maiusc: passi
// più lunghi); un doppio clic torna alla larghezza di partenza. La larghezza scelta si ricorda in questo browser.
const LARGHEZZE = {
  barra: { variabile: "--larghezza-barra", min: 180, max: 440, verso: 1 },      // bordo a destra: si allarga verso destra
  laterale: { variabile: "--larghezza-laterale", min: 320, max: 1100, verso: -1 }, // bordo a sinistra: verso sinistra
};
const CENTRO_MINIMO = 420;          // il filo della ricerca resta sempre leggibile

function limitaLarghezza(chi, px) {
  const l = LARGHEZZE[chi];
  const altro = chi === "barra" ? ($("laterale").hidden ? 0 : $("laterale").offsetWidth) : $("app").querySelector(".fianco").offsetWidth;
  const spazio = window.innerWidth - altro - CENTRO_MINIMO;
  return Math.round(Math.max(l.min, Math.min(l.max, spazio, px)));
}

function mettiLarghezza(chi, px, ricordaScelta = true) {
  const m = $("maniglia-" + chi);
  if (px === null) {
    document.documentElement.style.removeProperty(LARGHEZZE[chi].variabile);
    if (ricordaScelta) ricorda("larghezza-" + chi, "");
  } else {
    px = limitaLarghezza(chi, px);
    document.documentElement.style.setProperty(LARGHEZZE[chi].variabile, px + "px");
    if (ricordaScelta) ricorda("larghezza-" + chi, String(px));
  }
  segnaManiglia(chi);
}

// il valore della maniglia per i lettori di schermo: i pixel, e a parole la parte della finestra
function segnaManiglia(chi) {
  const m = $("maniglia-" + chi);
  const ora = (chi === "barra" ? $("app").querySelector(".fianco") : $("laterale")).offsetWidth;
  if (!ora) return;
  m.setAttribute("aria-valuenow", String(ora));
  m.setAttribute("aria-valuetext", `${Math.round((ora / window.innerWidth) * 100)}% della finestra`);
}

function preparaManiglia(chi) {
  const m = $("maniglia-" + chi);
  const l = LARGHEZZE[chi];
  const elemento = () => (chi === "barra" ? $("app").querySelector(".fianco") : $("laterale"));
  m.setAttribute("aria-valuemin", String(l.min));
  m.setAttribute("aria-valuemax", String(l.max));
  m.addEventListener("pointerdown", (e) => {
    if (e.button !== 0) return;
    e.preventDefault();
    m.setPointerCapture(e.pointerId);
    const x0 = e.clientX;
    const w0 = elemento().offsetWidth;
    document.documentElement.classList.add("trascina-bordo");
    const muovi = (ev) => mettiLarghezza(chi, w0 + (ev.clientX - x0) * l.verso, false);
    const lascia = () => {
      m.removeEventListener("pointermove", muovi);
      document.documentElement.classList.remove("trascina-bordo");
      mettiLarghezza(chi, elemento().offsetWidth);              // ricordata solo a trascinamento finito
    };
    m.addEventListener("pointermove", muovi);
    m.addEventListener("pointerup", lascia, { once: true });
    m.addEventListener("pointercancel", lascia, { once: true });
  });
  m.addEventListener("dblclick", () => mettiLarghezza(chi, null));
  m.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); mettiLarghezza(chi, null); return; }   // come il doppio clic
    const passo = e.shiftKey ? 64 : 16;
    const d = { ArrowRight: passo, ArrowLeft: -passo }[e.key];
    if (d === undefined) return;
    e.preventDefault();
    mettiLarghezza(chi, elemento().offsetWidth + d * l.verso);
  });
  const salvata = parseInt(ricordato("larghezza-" + chi), 10);
  if (salvata) document.documentElement.style.setProperty(l.variabile, salvata + "px");
  requestAnimationFrame(() => segnaManiglia(chi));
}

// una finestra rimpicciolita non deve schiacciare il filo: le larghezze scelte si riducono quanto serve
function rispettaLarghezze() {
  for (const chi of Object.keys(LARGHEZZE)) {
    if (document.documentElement.style.getPropertyValue(LARGHEZZE[chi].variabile)) {
      const el_ = chi === "barra" ? $("app").querySelector(".fianco") : $("laterale");
      if (el_.offsetWidth) mettiLarghezza(chi, el_.offsetWidth, false);
    }
  }
}

function mostraVista(nome) {
  mostra("vista-thread", nome === "thread");
  mostra("vista-importazioni", nome === "importazioni");
  mostra("vista-impostazioni", nome === "impostazioni");
  mostra("composer", nome === "thread");
  if (nome === "impostazioni") $("b-impostazioni").setAttribute("aria-current", "page");
  else $("b-impostazioni").removeAttribute("aria-current");
  // due colonne di navigazione in una finestra stretta lasciano poco ai riquadri: la barra si chiude finché si
  // resta nelle Impostazioni, senza cambiare la scelta ricordata
  const aperta = !$("app").classList.contains("barra-chiusa");
  if (nome === "impostazioni" && aperta && window.innerWidth < 1100) {
    barraLaterale(false, false);
    stato.barraDaRiaprire = true;
  } else if (nome !== "impostazioni" && stato.barraDaRiaprire) {
    stato.barraDaRiaprire = false;
    barraLaterale(true, false);
  }
  if (nome === "importazioni") $("imp-cartella").focus();
}

function barraLaterale(aperta, ricordaScelta = true) {
  $("app").classList.toggle("barra-chiusa", !aperta);
  $("b-barra").setAttribute("aria-expanded", String(aperta));
  $("b-barra").setAttribute("aria-label", aperta ? "Nascondi la barra laterale" : "Mostra la barra laterale");
  if (ricordaScelta) ricorda("barra", aperta ? "" : "chiusa");
}

function tastiSchede(e) {
  const schede = [...document.querySelectorAll(".schede button")];
  const i = schede.indexOf(document.activeElement);
  if (i < 0) return;
  const j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: schede.length - 1 }[e.key];
  if (j === undefined) return;
  e.preventDefault();
  const b = schede[(j + schede.length) % schede.length];
  apriScheda(b.dataset.scheda);
  b.focus();
}

// scorciatoie della finestra: Ctrl+N nuova ricerca, Ctrl+B barra, Esc chiude il pannello (se nessun dialogo è aperto)
function tastiFinestra(e) {
  if (document.querySelector("dialog[open]")) return;
  const ctrl = e.ctrlKey || e.metaKey;
  if (ctrl && e.key.toLowerCase() === "k") { e.preventDefault(); apriComandi(); }
  else if (ctrl && e.key.toLowerCase() === "n") { e.preventDefault(); nuovoThread(); }
  else if (ctrl && e.key.toLowerCase() === "b") {
    e.preventDefault();
    stato.barraDaRiaprirePannello = false;
    barraLaterale($("app").classList.contains("barra-chiusa"));
  }
  else if (ctrl && e.key === ",") { e.preventDefault(); apriImpostazioniRicordate(); }
  else if (e.key === "Escape" && !$("laterale").hidden) chiudiLaterale();
  else if (e.key === "Escape" && !$("vista-impostazioni").hidden) { mostraVista("thread"); $("testo").focus(); }
}

// frecce su e giù tra le voci della colonna delle Impostazioni (sezioni e fornitori, nell'ordine in cui si vedono)
function tastiImpostazioni(e) {
  const voci = [...document.querySelectorAll(".cfg-nav .voce-barra")];
  const i = voci.indexOf(document.activeElement);
  if (i < 0) return;
  const j = { ArrowDown: i + 1, ArrowUp: i - 1, Home: 0, End: voci.length - 1 }[e.key];
  if (j === undefined) return;
  e.preventDefault();
  voci[Math.max(0, Math.min(voci.length - 1, j))].focus();
}

// ------------------------------------------------------------------ fonte, passaggi, glossario
// i passaggi e i rimandi di un documento, una richiesta per documento (nel filo possono essercene più d'uno)
async function datiPassaggi(doc = stato.doc) {
  if (!doc) return null;
  const chiave = new URLSearchParams(doc).toString();
  if (!stato.cachePassaggi[chiave]) stato.cachePassaggi[chiave] = await api("/api/passaggi?" + chiave);
  return stato.cachePassaggi[chiave];
}

// Il documento diventa un messaggio: senza titolo e domanda (sono già nel filo), la risposta subito, limiti e
// copertura chiusi, le prove (documenti, passaggi, dati) chiuse in fondo; i rimandi [n] mostrano un'anteprima al
// passaggio del mouse e, come «Apri la fonte», aprono la pagina citata nel pannello a destra.
async function arricchisciDocumento(radice, doc, pref) {
  const primo = radice.querySelector("h1");
  for (let s = primo && primo.nextElementSibling; s && s.tagName === "P"; s = s.nextElementSibling) {
    if (/^Domanda:/.test(s.textContent.trim())) s.classList.add("via-nel-filo");
  }
  const titoli = [...radice.querySelectorAll(":scope > h2")];
  const sezione = (h) => {                       // il titolo e ciò che segue fino al titolo successivo
    const out = [];
    for (let s = h.nextElementSibling; s && s.tagName !== "H2"; s = s.nextElementSibling) out.push(s);
    return out;
  };
  const chiudi = (h, testo, classe) => {
    const dentro = sezione(h);
    if (!dentro.some((x) => x.textContent.trim())) { dentro.forEach((x) => x.remove()); h.remove(); return; }  // niente da aprire
    const det = el("details", null, classe || "");
    det.append(el("summary", testo), ...dentro);
    h.replaceWith(det);
  };
  titoli.forEach((h) => {
    const t = h.textContent.trim();
    if (/^Risposta finale/.test(t)) h.classList.add("via-nel-filo");
    else if (/^Limiti/.test(t) || /^Grado di copertura/.test(t)) chiudi(h, t);
  });
  const prima = titoli.find((h) => h.isConnected && !/^(Risposta finale|Limiti|Grado di copertura)/.test(h.textContent.trim()));
  if (prima) {
    const prove = el("details", null, "prove");
    const passaggi = radice.querySelectorAll("h3[id]").length;
    const resto = [];
    for (let s = prima; s; s = s.nextElementSibling) resto.push(s);
    prima.before(prove);
    prove.append(el("summary", `Prove: documenti, passaggi${passaggi ? ` (${passaggi})` : ""}, dati e inferenze`), ...resto);
    // file e righe del corpus servono a chi verifica, non a chi legge: dentro le prove, chiusi a parte
    const tecnici = [...prove.querySelectorAll(":scope > h2")].find((h) => /^Dati tecnici/.test(h.textContent.trim()));
    if (tecnici) chiudi(tecnici, "Dettagli tecnici: file e righe nel corpus", "dettagli-tecnici");
  }
  let r;
  try { r = await datiPassaggi(doc); } catch (e) { return; }
  if (!r || !Object.keys(r.rimandi).length) return;
  // ogni citazione («— ..., p. 47.») apre la SUA pagina, non quella del primo passaggio del documento
  const apri = (v, pagina) => apriFonte(v.file, v.riga, null,
    pagina ? { etichetta: pagina, tra: (v.righe || [v.riga]).join(",") } : null);
  const pulsante = (x, v, pagina) => {
    if (x.querySelector(".apri-fonte")) return;
    const p = pagina || v.pagina;
    const b = pulsanteMsg(p ? `Apri la fonte, p. ${p}` : "Apri la fonte", () => apri(v, pagina), "apri-fonte");
    b.title = v.file;
    x.append(b);
  };
  radice.querySelectorAll("h3, li").forEach((x) => {
    const m = /^\[(\d+)\]/.exec(x.textContent.trim());
    const v = m && r.rimandi[m[1]];
    if (!v) return;
    pulsante(x, v);
    for (let s = x.nextElementSibling; x.tagName === "H3" && s && !/^H[1-3]$/.test(s.tagName); s = s.nextElementSibling) {
      const t = s.textContent.trim();
      if (s.tagName !== "P" || !t.startsWith("—")) continue;
      const pg = /,\s*pp?\.\s*([0-9A-Za-z]+)(?:\s*[-–]\s*[0-9A-Za-z]+)?\.?\s*$/.exec(t);
      pulsante(s, v, pg ? pg[1] : "");
    }
  });
  radice.querySelectorAll("a.rimando").forEach((a) => {
    const n = (/\d+/.exec(a.textContent) || [])[0];
    const v = r.rimandi[n];
    if (!v) return;
    // «[7]» letto così non dice che cosa apre: numero, fonte (accorciata) e pagina
    const rif = String(v.riferimento || "").replace(/\s+/g, " ").trim();
    const breve = rif.length > 110 ? rif.slice(0, 108).replace(/\s+\S*$/, "") + "…" : rif;
    a.setAttribute("aria-label", [`Passaggio ${n}`, breve, v.pagina ? `p. ${v.pagina}` : ""].filter(Boolean).join(", "));
    a.addEventListener("click", (e) => { e.preventDefault(); nascondiAnteprima(); apri(v, v.pagina); });
    const mostraA = () => mostraAnteprima(a, v, radice, pref, n);
    a.addEventListener("mouseenter", () => anteprimaDopo(mostraA));
    a.addEventListener("focus", mostraA);                 // da tastiera subito: chi ci arriva l'ha cercata
    a.addEventListener("mouseleave", nascondiAnteprima);
    a.addEventListener("blur", nascondiAnteprima);
  });
}

// righe di servizio del file: [CHIAVE: valore] in testa vanno nella scheda tecnica; [[p. N | pdf K]] doppia il
// selettore delle pagine e non si mostra; gli altri [[...]] restano, come piccole etichette
const RIGA_SCHEDA = /^\s*\[([A-Z_]+):\s*(.*)\]\s*$/;
const RIGA_PAGINA = /^\s*\[\[\s*pp?\.\s*[^\]]*\]\]\s*$/;

async function apriFonte(file, riga, pagina, citata, origine) {
  const q = { file };
  if (riga) q.riga = riga;
  if (pagina) q.pagina = pagina;
  if (citata) Object.assign(q, citata);
  let r;
  try {
    r = await api("/api/fonte?" + new URLSearchParams(q));
  } catch (e) {
    avviso(e.message, true);
    return;
  }
  stato.fonte = r;
  mostra("fonte-vuota", false);
  mostra("fonte", true);
  $("fonte-titolo").textContent = r.titolo;
  $("fonte-titolo").title = r.titolo;
  const sel = $("fonte-pagine");
  // l'etichetta basta: la posizione nel volume serve solo quando le pagine sono molte e la si cerca nell'elenco
  sel.replaceChildren(...r.pagine.map((p, i) => new Option(r.pagine.length > 1 ? `${p.etichetta} · ${i + 1}/${r.pagine.length}` : p.etichetta, i + 1)));
  sel.value = String(r.pagina);
  sel.disabled = r.pagine.length < 2;
  $("fonte-prima").disabled = r.pagina <= 1;
  $("fonte-dopo").disabled = r.pagina >= r.pagine.length;
  const orig = $("fonte-originale");
  orig.hidden = !r.originale;
  if (r.originale) orig.href = r.originale;

  // il testo trascritto: le righe di servizio in testa vanno nella scheda tecnica, in fondo e chiusa
  const scheda = el("dl");
  const box = $("fonte-testo");
  box.replaceChildren();
  let evidenziata = null;
  let inNota = false;                           // righe tra [[nota]] e [[/nota]]: note dei curatori (apparato.py)
  for (const x of r.righe) {
    const s = RIGA_SCHEDA.exec(x.testo);
    if (s && !evidenziata && box.children.length === 0) {
      scheda.append(el("dt", s[1].toLowerCase().replace(/_/g, " ")), el("dd", s[2]));
      continue;
    }
    if (RIGA_PAGINA.test(x.testo)) continue;
    if (!x.testo.trim() && box.children.length === 0) continue;   // righe vuote tra la scheda e il testo
    const riga_ = el("div", null, "riga-fonte");
    if (/^\s*\[\[nota\]\]\s*$/.test(x.testo)) inNota = true;
    const marcatore = /^\s*\[\[(.*)\]\]\s*$/.exec(x.testo);
    if (marcatore) riga_.classList.add("marcatore");
    else if (inNota) riga_.classList.add("nota");
    if (/^\s*\[\[\/nota\]\]\s*$/.test(x.testo)) inNota = false;
    riga_.append(el("span", String(x.n), "n"), el("span", marcatore ? marcatore[1] : x.testo, "t"));
    if (x.n === r.evidenzia) {
      riga_.classList.add("evidenziata");
      evidenziata = riga_;
    }
    box.append(riga_);
  }
  $("fonte-scheda").hidden = !scheda.children.length;
  $("fonte-scheda").replaceChildren(el("summary", "Scheda tecnica"), scheda);

  // la pagina dell'originale, con il passaggio evidenziato sopra e il suo testo selezionabile
  stato.fonteEvidenziata = evidenziata;
  sopraLaPagina(r);
  $("fonte-strato").replaceChildren();
  const img = $("fonte-img");
  img.alt = `Pagina ${r.pagine[r.pagina - 1].etichetta} dell'originale` + (r.titolo ? `: ${r.titolo}` : "");
  if (r.immagine) {
    const pronta = () => { stratoTesto(r); vaiAlPassaggio(); };
    img.onload = pronta;
    const src = srcPagina(r.immagine);
    if (img.getAttribute("src") !== src) img.src = src;
    else if (img.complete) requestAnimationFrame(pronta);
  }
  // una scansione senza strato di testo utilizzabile: le parole e la loro posizione vengono dall'OCR della pagina,
  // letto dal server la prima volta (un paio di secondi) e poi conservato; la pagina intanto è già in vista
  $("fonte-ocr").hidden = !r.ocr_pagina;
  if (r.ocr_pagina) leggiPagina(q, r);
  vistaFonte(r.immagine ? (stato.fonteVista || "pagina") : "testo", false);

  apriLaterale("fonte");
  // aperta dalla tastiera, il fuoco era su un pulsante ora nascosto (passaggi) o dentro il documento: passa al visore
  const fuoco = document.activeElement;
  if ((fuoco && fuoco.tagName === "IFRAME") || (fuoco && fuoco !== document.body && !fuoco.offsetParent)) {
    $("p-fonte").focus({ preventScroll: true });
  }
  if (!r.immagine) vaiAlPassaggio();
}

// evidenze del passaggio sulla pagina e, quando non si è potuto evidenziare (riscontro troppo debole), il passaggio
// a parole sopra la pagina
function sopraLaPagina(r) {
  const evidenze = r.evidenze || [];
  $("fonte-evidenze").replaceChildren(...evidenze.map((e) => {
    const d = el("div", null, e.citata ? "evidenza citata" : "evidenza");
    const [x0, y0, x1, y1] = e.r;
    Object.assign(d.style, { left: `${x0 * 100}%`, top: `${y0 * 100}%`, width: `${(x1 - x0) * 100}%`, height: `${(y1 - y0) * 100}%` });
    return d;
  }));
  const estratto = $("fonte-estratto");
  estratto.replaceChildren();
  if (stato.fonteEvidenziata && r.immagine && !evidenze.length && !r.ocr_pagina) {
    const i = r.righe.findIndex((x) => x.n === r.evidenzia);
    const testo = r.righe.slice(i, i + 3).map((x) => x.testo).filter((t) => t.trim() && !/^\s*\[\[/.test(t));
    estratto.append(el("span", "Il passaggio, non ritrovato sulla pagina", "etichetta"), el("p", testo.join(" ")));
  }
  estratto.hidden = $("fonte-foglio").hidden || !estratto.children.length;
}

// la seconda richiesta di una pagina che aspetta l'OCR: arrivata la lettura, evidenze e strato si aggiungono alla
// pagina già in vista, se è ancora quella
async function leggiPagina(q, r) {
  let n = null;
  try { n = await api("/api/fonte?" + new URLSearchParams({ ...q, pagina: r.pagina, ocr: "1" })); } catch (e) { /* resta senza strato */ }
  if (stato.fonte !== r) return;                // sfogliata nel frattempo: la pagina nuova fa da sé
  $("fonte-ocr").hidden = true;
  r.ocr_pagina = false;
  if (n) Object.assign(r, { evidenze: n.evidenze, strato: n.strato });
  sopraLaPagina(r);
  stratoTesto(r);
  vaiAlPassaggio();
}

// l'immagine della pagina: più definita quando la si ingrandisce
function srcPagina(base) {
  return (stato.fonteZoom || 1) > 1.4 ? `${base}&dpi=300` : base;
}

// «pagina» o «testo»: l'originale (se c'è) o la trascrizione, una alla volta, ciascuna con il suo scorrimento
function vistaFonte(vista, scelta = true) {
  const r = stato.fonte;
  if (!r) return;
  if (scelta) stato.fonteVista = vista;
  const pagina = vista === "pagina" && !!r.immagine;
  $("fonte-viste").hidden = !r.immagine;
  $("fonte-viste").querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String((b.dataset.vista === "pagina") === pagina)));
  $("fonte-zoom").hidden = !pagina;
  $("fonte-foglio").hidden = !pagina;
  $("fonte-estratto").hidden = !pagina || !$("fonte-estratto").children.length;
  $("fonte-trascrizione").hidden = pagina;
  if (scelta) vaiAlPassaggio();
}

// porta in vista il passaggio: sulla pagina la prima riga evidenziata (la citata, se c'è), nel testo la riga citata
function vaiAlPassaggio() {
  if (!$("fonte-foglio").hidden) {
    const foglio = $("fonte-foglio");
    const e = $("fonte-evidenze").querySelector(".citata") || $("fonte-evidenze").firstElementChild;
    if (!e) { foglio.scrollTop = 0; foglio.scrollLeft = 0; return; }
    foglio.scrollTop = e.offsetTop - foglio.clientHeight / 3;
    foglio.scrollLeft = e.offsetLeft - 16;
  } else {
    const box = $("fonte-trascrizione");
    const r = stato.fonteEvidenziata;
    box.scrollTop = r ? r.offsetTop - box.clientHeight / 2 + r.offsetHeight / 2 : 0;
  }
}

// lo strato di testo sopra l'immagine: righe trasparenti nella posizione delle righe del PDF, da selezionare e
// copiare. Grandezza in cqw (la larghezza della pagina), così segue l'ingrandimento senza ricalcoli; la larghezza
// di ogni riga si adatta con scaleX, misurata una volta sola.
function stratoTesto(r) {
  const img = $("fonte-img");
  const strato = $("fonte-strato");
  if (stato.fonte !== r || !img.naturalWidth || !(r.strato || []).length) return strato.replaceChildren();
  const alto = img.naturalHeight / img.naturalWidth;              // altezza della pagina in larghezze
  const ctx = (stratoTesto.ctx ||= document.createElement("canvas").getContext("2d"));
  ctx.font = "100px sans-serif";
  strato.replaceChildren(...r.strato.flatMap(([x0, y0, x1, y1, testo]) => {
    const s = el("span", testo);
    const corpo = (y1 - y0) * alto * 100 * 0.88;                  // in cqw: l'altezza della riga, meno l'interlinea
    const largo = ctx.measureText(testo).width / 100 * corpo;      // in cqw, al corpo scelto
    Object.assign(s.style, { left: `${x0 * 100}%`, top: `${y0 * 100}%`, fontSize: `${corpo}cqw`,
      transform: `scaleX(${largo ? ((x1 - x0) * 100) / largo : 1})` });
    return [s, document.createElement("br")];                     // copiate, le righe restano righe
  }));
}

// ingrandimento della pagina: 1 = larghezza del pannello; da 0.5 a 4
function zoomFonte(z, perno) {
  const foglio = $("fonte-foglio");
  const prima = stato.fonteZoom || 1;
  z = Math.min(4, Math.max(0.5, Math.round(z * 100) / 100));
  if (z === prima || foglio.hidden) return;
  // il punto sotto il puntatore (o il centro) resta dov'è
  const px = perno ? perno.x : foglio.clientWidth / 2, py = perno ? perno.y : foglio.clientHeight / 2;
  const fx = (foglio.scrollLeft + px) / foglio.scrollWidth, fy = (foglio.scrollTop + py) / foglio.scrollHeight;
  stato.fonteZoom = z;
  $("fonte-carta").style.width = `${z * 100}%`;
  $("fonte-adatta").textContent = `${Math.round(z * 100)}%`;
  $("fonte-meno").disabled = z <= 0.5;
  $("fonte-piu").disabled = z >= 4;
  foglio.scrollLeft = fx * foglio.scrollWidth - px;
  foglio.scrollTop = fy * foglio.scrollHeight - py;
  const img = $("fonte-img");
  if (stato.fonte && stato.fonte.immagine && img.getAttribute("src") !== srcPagina(stato.fonte.immagine)) {
    // la versione più definita sostituisce l'altra quando è pronta, senza lampi
    const nuova = new Image();
    nuova.onload = () => { if (stato.fonte && stato.fonte.immagine && nuova.src.endsWith(srcPagina(stato.fonte.immagine))) { img.onload = null; img.src = nuova.src; } };
    nuova.src = srcPagina(stato.fonte.immagine);
  }
}

// pressioni rapide si sommano: si parte dalla pagina già chiesta, non da quella ancora mostrata
function sfoglia(passo) {
  const r = stato.fonte;
  if (!r) return;
  const n = (stato.paginaChiesta || r.pagina) + passo;
  if (n < 1 || n > r.pagine.length) return;
  stato.paginaChiesta = n;
  apriFonte(r.file, null, n).finally(() => { if (stato.paginaChiesta === n) stato.paginaChiesta = 0; });
}

// nel visore: frecce sinistra e destra (o Pagina su e giù) sfogliano, se il fuoco non è in un campo
function tastiFonte(e) {
  if (/^(SELECT|INPUT|TEXTAREA)$/.test(e.target.tagName) || e.altKey || e.ctrlKey || e.metaKey) return;
  const z = { "+": 1.25, "=": 1.25, "-": 0.8 }[e.key];
  if (z || e.key === "0") {
    e.preventDefault();
    return zoomFonte(z ? (stato.fonteZoom || 1) * z : 1);
  }
  const passo = { ArrowLeft: -1, PageUp: -1, ArrowRight: 1, PageDown: 1 }[e.key];
  if (!passo) return;
  e.preventDefault();
  sfoglia(passo);
}

async function caricaPassaggi() {
  const t = $("passaggi-tabella");
  if (!stato.doc) {
    t.replaceChildren();
    mostra("passaggi-strumenti", false);
    mostra("passaggi-faccette", false);
    $("passaggi-nota").textContent = "Apri una risposta (o una ricerca dai recenti): qui compaiono i suoi passaggi.";
    return;
  }
  let r;
  try { r = await datiPassaggi(); } catch (e) { $("passaggi-nota").textContent = e.message; return; }
  stato.passaggiDati = r;
  // «letti»: i passaggi letti dalla ricerca (anche per una risposta salvata, se la sua ricerca c'è ancora): si
  // filtrano, si correggono, hanno la linea del tempo. Altrimenti solo quelli citati nella risposta
  const letti = !!r.tutti;
  const citati = r.passaggi.filter((p) => p.n).length;
  const documenti = new Set(r.passaggi.map((p) => p.file)).size;
  $("passaggi-nota").textContent = letti
    ? `${r.passaggi.length} ${r.passaggi.length === 1 ? "passaggio letto" : "passaggi letti"} in ` +
      `${documenti} ${documenti === 1 ? "documento" : "documenti"}` +
      (citati ? `, ${citati} ${citati === 1 ? "citato" : "citati"} nella risposta.` : ".") +
      " Un clic su «sì» o «no» corregge la pertinenza."
    : `${r.passaggi.length} ${r.passaggi.length === 1 ? "passaggio citato" : "passaggi citati"} nella risposta.`;
  mostra("passaggi-strumenti", r.passaggi.length > 0);
  $("passaggi-pertinenti").closest("label").hidden = !letti;
  $("passaggi-citati").closest("label").hidden = !(letti && citati);
  // per i letti: un gruppo per documento (la citazione una volta sola), poi i suoi passaggi
  const colonne = colonnePassaggi(letti, citati > 0);
  const testa = el("tr");
  for (const [, nome] of colonne) testa.append(el("th", nome));
  const corpo = document.createElement("tbody");
  let gruppo = null;
  r.passaggi.forEach((p) => {
    if (letti && p.file !== (gruppo && gruppo.dataset.file)) {
      gruppo = el("tr", null, "gruppo");
      gruppo.dataset.file = p.file;
      const th = el("th", null);
      th.colSpan = colonne.length;
      th.scope = "colgroup";
      th.append(el("span", senzaMarkdown(p.fonte)), el("span", p.data || "", "etichetta"));
      gruppo.append(th);
      corpo.append(gruppo);
    }
    corpo.append(rigaPassaggio(p, colonne, letti));
  });
  const intestazione = document.createElement("thead");
  intestazione.append(testa);
  t.replaceChildren(intestazione, corpo);
  disegnaFaccette(letti ? r.passaggi : []);
  filtraPassaggi();
}

function colonnePassaggi(letti, citati) {
  // «Dove»: «p. 47» se la pagina è nota, altrimenti «riga 117»
  return letti
    ? [...(citati ? [["n", "n."]] : []), ["pagina", "Dove"], ["pertinente", "Pertinente"], ["traduzione", "Traduzione"],
       ["letto_da", "Letto da"]]
    : [["n", "n."], ["fonte", "Fonte"]];
}

function rigaPassaggio(p, colonne, letti) {
  const tr = el("tr");
  tr.tabIndex = -1;                                  // j/k e le frecce ci portano il fuoco (tastiPassaggi)
  const apri = () => apriFonte(p.file, p.riga, null, null, "passaggi");
  for (const [k] of colonne) {
    const td = el("td");
    if (k === "pagina" || k === "fonte") {        // il pulsante porta la riga anche alla tastiera
      const etichetta = k === "fonte" ? senzaMarkdown(p.fonte) : p.pagina ? `p. ${p.pagina}` : `riga ${p.riga}`;
      const b = el("button", etichetta, "apri-passaggio");
      b.type = "button";
      b.addEventListener("click", (e) => { e.stopPropagation(); apri(); });
      td.append(b);
    } else if (k === "pertinente" && letti && p.id) {
      td.append(pulsantePertinenza(p, tr));
    } else if (k === "traduzione") {              // quattro righe; il testo intero al passaggio del mouse
      td.className = "traduzione";
      td.append(el("div", p[k] || "", "taglia"));
      td.title = p[k] || "";
      if (letti && p.id && p.pertinente === "sì") {
        const modifica = el("button", "Correggi", "discreto correggi-traduzione");
        modifica.type = "button";
        modifica.setAttribute("aria-label", "Correggi la traduzione");
        modifica.addEventListener("click", (e) => { e.stopPropagation(); correggiTraduzione(p, td); });
        td.append(modifica);
      }
    } else if (k === "letto_da") {                // l'ultimo pezzo dell'identificativo; quello intero nel titolo
      td.textContent = p.corretto ? "a mano" : (p[k] || "").split("/").pop();
      td.title = p.corretto ? "Corretto a mano" : p[k] || "";
      td.className = "letto-da" + (p.corretto ? " a-mano" : "");
    } else if (k === "n") {
      td.textContent = p.n ? `[${p.n}]` : "";
      td.className = "n-citato";
    } else {
      td.textContent = p[k] || "";
    }
    tr.append(td);
  }
  if (letti && p.pertinente !== "sì") tr.classList.add("no");
  tr.dataset.cerca = Object.values(p).join(" ").toLowerCase();
  tr.dataset.file = p.file;
  tr.dataset.anno = (p.data || "").slice(0, 4);
  tr.dataset.mese = (p.data || "").slice(0, 7);
  tr.dataset.serie = p.serie || "";
  tr.dataset.lingua = p.lingua || "";
  if (p.n) tr.dataset.citato = "1";
  tr.addEventListener("click", apri);
  tr._passaggio = p;
  return tr;
}

// la pertinenza come pulsante: un clic la capovolge (sì ↔ no; «incerto» diventa sì) e la scrive come correzione
function pulsantePertinenza(p, tr) {
  const b = el("button", p.pertinente || "?", "pertinenza");
  b.type = "button";
  const altro = p.pertinente === "sì" ? "no" : "sì";
  b.title = `Correggi: ${altro === "sì" ? "pertinente" : "non pertinente"} (R)`;
  b.setAttribute("aria-label", `Pertinente: ${p.pertinente || "non deciso"}. Correggi in ${altro}`);
  b.addEventListener("click", (e) => { e.stopPropagation(); correggiPertinenza(p, tr); });
  return b;
}

async function correggiPassaggio(p, modifiche) {
  const ricerca = stato.passaggiDati && stato.passaggiDati.ricerca;
  if (!ricerca) throw new Error("Questa risposta non ha più la sua ricerca: non si può correggere da qui.");
  const r = await api("/api/passaggio/correggi", Object.assign({ ricerca, id: p.id }, modifiche));
  const n = p.n;
  Object.assign(p, r.passaggio);                  // l'oggetto è quello in cache: la prossima apertura lo vede già
  if (n) p.n = n;
  return r;
}

async function correggiPertinenza(p, tr) {
  const nuovo = p.pertinente === "sì" ? "no" : "sì";
  try {
    const r = await correggiPassaggio(p, { pertinente: nuovo });
    sostituisciRiga(tr, p);
    annuncia(`Passaggio segnato come ${nuovo === "sì" ? "pertinente" : "non pertinente"}.`);
    if (!stato.notaCorrezione) { avviso(r.nota); stato.notaCorrezione = true; }
  } catch (e) {
    avviso(e.message, true);
  }
}

function correggiTraduzione(p, td) {
  const area = document.createElement("textarea");
  area.value = p.traduzione || "";
  area.rows = 4;
  area.setAttribute("aria-label", "Traduzione corretta");
  area.className = "traduzione-modifica";
  const salva = el("button", "Salva", "primario");
  const annulla = el("button", "Annulla");
  salva.type = annulla.type = "button";
  const riga = el("div", null, "riga");
  riga.append(salva, annulla);
  const tr = td.closest("tr");
  td.replaceChildren(area, riga);
  td.addEventListener("click", (e) => e.stopPropagation());
  area.addEventListener("keydown", (e) => {
    e.stopPropagation();
    if (e.key === "Escape") annulla.click();
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) salva.click();
  });
  annulla.addEventListener("click", (e) => { e.stopPropagation(); sostituisciRiga(tr, p); });
  salva.addEventListener("click", async (e) => {
    e.stopPropagation();
    const testo = area.value.trim();
    if (!testo || testo === (p.traduzione || "").trim()) { sostituisciRiga(tr, p); return; }
    salva.disabled = true;
    try {
      await correggiPassaggio(p, { traduzione: testo });
      sostituisciRiga(tr, p);
      annuncia("Traduzione corretta.");
    } catch (err) {
      salva.disabled = false;
      avviso(err.message, true);
    }
  });
  area.focus();
}

// la riga ridisegnata con i dati nuovi, al suo posto e con il fuoco se lo aveva
function sostituisciRiga(tr, p) {
  const r = stato.passaggiDati;
  const nuova = rigaPassaggio(p, colonnePassaggi(true, r.passaggi.some((x) => x.n)), true);
  const aveva = tr.contains(document.activeElement);
  tr.replaceWith(nuova);
  if (aveva) nuova.focus();
  disegnaFaccette(r.passaggi, true);
  filtraPassaggi();
}

// ---------------------------------------- linea del tempo e faccette dei passaggi
// Quante volte il nome compare nel tempo, per anno (o per mese se gli anni sono al più tre): una barra per periodo,
// la parte pertinente piena. Un clic sceglie il periodo; serie e lingue sono pulsanti da accendere e spegnere.
function filtroPassaggiVuoto() { return { periodo: "", serie: new Set(), lingue: new Set() }; }

function nomePeriodo(k, lungo) {
  if (k.length === 4) return k;
  return new Date(+k.slice(0, 4), +k.slice(5) - 1).toLocaleDateString(LOCALE,
    { month: lungo ? "long" : "short", year: "numeric" });
}

function disegnaFaccette(passaggi, conserva = false) {
  const box = $("passaggi-faccette");
  if (!conserva || !stato.filtroP) stato.filtroP = filtroPassaggiVuoto();
  const f = stato.filtroP;
  box.replaceChildren();
  const datati = passaggi.filter((p) => /^\d{4}/.test(p.data || ""));
  box.hidden = passaggi.length < 2;
  if (box.hidden) return;
  const anni = [...new Set(datati.map((p) => +p.data.slice(0, 4)))].sort((a, b) => a - b);
  if (anni.length) {
    const mensile = anni[anni.length - 1] - anni[0] < 3 && datati.every((p) => /^\d{4}-\d{2}/.test(p.data));
    const chiave = (p) => (mensile ? p.data.slice(0, 7) : p.data.slice(0, 4));
    let periodi = [];
    for (let a = anni[0]; a <= anni[anni.length - 1]; a++) {
      if (mensile) for (let m = 1; m <= 12; m++) periodi.push(`${a}-${String(m).padStart(2, "0")}`);
      else periodi.push(String(a));
    }
    if (mensile) {
      const usati = datati.map(chiave).sort();
      periodi = periodi.filter((k) => k >= usati[0] && k <= usati[usati.length - 1]);
    }
    const conti = Object.fromEntries(periodi.map((k) => [k, { tutti: 0, si: 0 }]));
    for (const p of datati) {
      const c = conti[chiave(p)];
      if (c) { c.tutti++; if (p.pertinente === "sì") c.si++; }
    }
    const massimo = Math.max(1, ...Object.values(conti).map((c) => c.tutti));
    const tempo = el("div", null, "linea-tempo");
    tempo.setAttribute("role", "group");
    tempo.setAttribute("aria-label", `Passaggi per ${mensile ? "mese" : "anno"}: scegli un periodo`);
    tempo.dataset.mensile = mensile ? "1" : "";
    const barre = el("div", null, "barre-tempo");
    for (const k of periodi) {
      const c = conti[k];
      const b = el("button", null, "periodo");
      b.type = "button";
      b.dataset.periodo = k;
      b.disabled = !c.tutti;
      b.setAttribute("aria-pressed", String(f.periodo === k));
      const nome = nomePeriodo(k, true);
      b.setAttribute("aria-label", `${nome}: ${c.tutti} ${c.tutti === 1 ? "passaggio" : "passaggi"}, ${c.si} pertinenti`);
      b.title = `${nome}: ${c.tutti} letti, ${c.si} pertinenti`;
      const colonna = el("span", null, "colonna");
      colonna.style.setProperty("--alto", String(c.tutti / massimo));
      colonna.style.setProperty("--pieno", String(c.tutti ? c.si / c.tutti : 0));
      b.append(colonna);
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        f.periodo = f.periodo === k ? "" : k;
        barre.querySelectorAll(".periodo").forEach((x) => x.setAttribute("aria-pressed", String(f.periodo === x.dataset.periodo)));
        filtraPassaggi();
      });
      barre.append(b);
    }
    const asse = el("div", null, "asse-tempo");
    asse.append(el("span", nomePeriodo(periodi[0])), el("span", periodi.length > 1 ? nomePeriodo(periodi[periodi.length - 1]) : ""));
    asse.setAttribute("aria-hidden", "true");
    tempo.append(barre, asse);
    box.append(tempo);
    const senzaData = passaggi.length - datati.length;
    if (senzaData) box.append(el("p", `${senzaData} ${senzaData === 1 ? "passaggio" : "passaggi"} senza data.`, "nota"));
  }
  const gruppoChip = (titolo, valori, scelti, nomeDi) => {
    if (valori.length < 2) return;
    const riga = el("div", null, "chip-riga faccetta");
    riga.setAttribute("role", "group");
    riga.setAttribute("aria-label", titolo);
    riga.append(el("span", titolo, "etichetta-faccetta"));
    for (const [v, n] of valori) {
      const b = el("button", null, "chip");
      b.type = "button";
      b.append(document.createTextNode(nomeDi(v) + " "), el("span", String(n), "conto-chip"));
      b.setAttribute("aria-pressed", String(scelti.has(v)));
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        if (scelti.has(v)) scelti.delete(v); else scelti.add(v);
        b.setAttribute("aria-pressed", String(scelti.has(v)));
        filtraPassaggi();
      });
      riga.append(b);
    }
    box.append(riga);
  };
  const conta = (k) => [...passaggi.reduce((m, p) => m.set(p[k] || "", (m.get(p[k] || "") || 0) + 1), new Map())]
    .filter(([v]) => v).sort((a, b) => b[1] - a[1]);
  gruppoChip("Serie", conta("serie"), f.serie, (v) => senzaMarkdown(v));
  gruppoChip("Lingua", conta("lingua"), f.lingue, (v) => NOMI_LINGUE[v] || v);
}

const NOMI_LINGUE = { it: "italiano", en: "inglese", fr: "francese", de: "tedesco", es: "spagnolo", pt: "portoghese",
  sq: "albanese", zh: "cinese", ru: "russo", el: "greco", ar: "arabo", he: "ebraico" };

function filtraPassaggi() {
  const testo = $("passaggi-filtro").value.trim().toLowerCase();
  const letti = !!(stato.passaggiDati && stato.passaggiDati.tutti);
  const solo = $("passaggi-pertinenti").checked && letti;
  const soloCitati = $("passaggi-citati").checked && letti;
  const f = stato.filtroP || filtroPassaggiVuoto();
  const mensile = !!document.querySelector("#passaggi-faccette .linea-tempo[data-mensile='1']");
  const visibili = new Set();
  let n = 0;
  $("passaggi-tabella").querySelectorAll("tbody tr:not(.gruppo)").forEach((tr) => {
    const d = tr.dataset;
    tr.hidden = (!!testo && !d.cerca.includes(testo)) || (solo && tr.classList.contains("no")) ||
      (soloCitati && !d.citato) ||
      (!!f.periodo && (mensile ? d.mese : d.anno) !== f.periodo) ||
      (f.serie.size > 0 && !f.serie.has(d.serie)) || (f.lingue.size > 0 && !f.lingue.has(d.lingua));
    if (!tr.hidden) { visibili.add(d.file); n++; }
  });
  $("passaggi-tabella").querySelectorAll("tbody tr.gruppo").forEach((g) => { g.hidden = !visibili.has(g.dataset.file); });
  const filtrato = !!(testo || solo || soloCitati || f.periodo || f.serie.size || f.lingue.size);
  const conto = $("passaggi-conto");
  conto.hidden = !filtrato;
  conto.textContent = filtrato ? `${n} ${n === 1 ? "passaggio mostrato" : "passaggi mostrati"}` : "";
  $("passaggi-azzera").hidden = !(f.periodo || f.serie.size || f.lingue.size);
}

function azzeraFaccette() {
  stato.filtroP = filtroPassaggiVuoto();
  if (stato.passaggiDati) disegnaFaccette(stato.passaggiDati.tutti ? stato.passaggiDati.passaggi : [], true);
  filtraPassaggi();
}

// j/k (o le frecce dentro la tabella) tra le righe visibili; Invio o O apre la fonte; R capovolge la pertinenza
function tastiPassaggi(e) {
  if (e.target.closest("input, textarea, select") || e.ctrlKey || e.metaKey || e.altKey) return;
  const righe = [...$("passaggi-tabella").querySelectorAll("tbody tr:not(.gruppo):not([hidden])")];
  if (!righe.length) return;
  const ora = e.target.closest("tbody tr:not(.gruppo)");
  const i = righe.indexOf(ora);
  const tasto = e.key.toLowerCase();
  const su = tasto === "k" || (ora && e.key === "ArrowUp");
  const giu = tasto === "j" || (ora && e.key === "ArrowDown");
  if (su || giu) {
    e.preventDefault();
    const j = i < 0 ? 0 : Math.max(0, Math.min(righe.length - 1, i + (giu ? 1 : -1)));
    righe[j].focus();
    righe[j].scrollIntoView({ block: "nearest" });
  } else if (ora && (tasto === "o" || (e.key === "Enter" && e.target === ora))) {
    e.preventDefault();
    ora.click();
  } else if (ora && tasto === "r" && ora._passaggio && ora._passaggio.id && stato.passaggiDati.tutti) {
    e.preventDefault();
    correggiPertinenza(ora._passaggio, ora);
  }
}

// i campi delle schede e dei profili delle serie hanno nomi da file (forme_ambigue): nel glossario si leggono in
// italiano; un campo che qui non c'è perde solo i trattini bassi
const ETICHETTE_CAMPI = { tipo: "Tipo", varianti: "Forme del nome", forme_ambigue: "Forme ambigue",
  contesto: "Contesto", note: "Note", sigla: "Sigla", lingua: "Lingua", lingue: "Lingue", luogo: "Luogo",
  editore: "Editore", periodicita: "Periodicità", formato: "Formato", citazione: "Citazione",
  chicago: "Citazione (Chicago)", nome_completo: "Nome completo", forma_estesa: "Forma estesa", collegate: "Collegate",
  curatori: "Curatori", titolo_volume: "Titolo del volume", autore: "Autore", titolo: "Titolo",
  nota_limiti: "Nota sui limiti", ocr_lingue: "Lingue dell'OCR", cartella: "Cartella", periodo: "Periodo" };
function etichettaCampo(k) {
  if (ETICHETTE_CAMPI[k]) return ETICHETTE_CAMPI[k];
  const t = String(k).replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
}

async function caricaGlossario(riapri) {
  if (stato.glossario && !riapri) return;
  let r;
  try { r = await api("/api/glossario"); } catch (e) { avviso(e.message, true); return; }
  stato.glossario = r;
  const voci = (box, elenco, tipo) => {
    box.replaceChildren();
    for (const v of elenco) box.append(voceGlossario(v, tipo));
    if (!elenco.length) box.append(el("p", "Nessuna.", "nota"));
  };
  voci($("gl-schede"), r.schede, "scheda");
  voci($("gl-serie"), r.serie, "serie");
  $("gl-n-schede").textContent = `(${r.schede.length})`;
  $("gl-n-serie").textContent = `(${r.serie.length})`;
  filtraGlossario();
  controllaGlossario();
  if (riapri) apriVoceGlossario(riapri.tipo, riapri.nome);
}

// una voce del glossario: chiusa, il nome; aperta, la pagina dell'entità (schede) o il profilo (serie), le azioni
function voceGlossario(v, tipo) {
  const d = el("details", null, "voce-glossario");
  d.dataset.nome = v.nome;
  d.dataset.tipo = tipo;
  const titolo = el("summary");
  titolo.append(el("span", v.nome, "nome-voce"));           // il nome non si traduce, i segni accanto sì (i18n.js)
  d.append(titolo);
  const corpo = el("div", null, "corpo-voce");
  d.append(corpo);
  d.dataset.cerca = (v.nome + " " + Object.values(v.campi).join(" ")).toLowerCase();
  d.addEventListener("toggle", () => { if (d.open && !corpo.childElementCount) mostraVoce(d, v, tipo); });
  return d;
}

function apriVoceGlossario(tipo, nome) {
  const d = [...document.querySelectorAll(".voce-glossario")].find((x) => x.dataset.tipo === tipo && x.dataset.nome === nome);
  if (!d) return;
  d.hidden = false;
  d.open = true;
  d.scrollIntoView({ block: "nearest" });
  d.querySelector("summary").focus({ preventScroll: true });
}

function campiLetti(v) {
  const dl = el("dl");
  for (const [k, val] of Object.entries(v.campi)) {
    if (!String(val).trim()) continue;
    dl.append(el("dt", etichettaCampo(k)), el("dd", val));
  }
  return dl;
}

function mostraVoce(d, v, tipo) {
  const corpo = d.querySelector(".corpo-voce");
  corpo.replaceChildren();
  if (tipo === "serie") {
    corpo.append(campiLetti(v));
    const azioni = el("div", null, "azioni-scheda");
    azioni.append(pulsante("Modifica", () => modificaSerie(d, v)));
    corpo.append(azioni);
    return;
  }
  const pagina = el("div", null, "pagina-scheda");
  pagina.append(el("p", "Carico ciò che l'archivio sa di questa entità…", "nota in-attesa"));
  const suggerite = el("div", null, "forme-suggerite");
  corpo.append(pagina, campiLetti(v), suggerite, azioniScheda(d, v));
  disegnaPaginaScheda(pagina, v.nome);
  disegnaSuggerite(suggerite, v.nome, d);
}

function cercaDalGlossario(nome, evoluzione) {
  if (stato.inCorso) { avviso("C'è già una ricerca in corso: aspetta che finisca.", true); return; }
  nuovoThread();
  if ($("evoluzione")) { $("evoluzione").checked = !!evoluzione; riassumiFiltri(); }
  $("testo").value = nome;
  invia();
}

function azioniScheda(d, v) {
  const azioni = el("div", null, "azioni-scheda");
  azioni.append(
    pulsante("Cerca nelle fonti", () => cercaDalGlossario(v.nome, false), true),
    pulsante("Evoluzione anno per anno", () => cercaDalGlossario(v.nome, true)),
    pulsante("Modifica", () => modificaScheda(d, v.nome)),
    pulsante("Rinomina…", () => rinominaScheda(d, v.nome)),
    pulsante("Unisci a…", () => unisciScheda(d, v.nome)));
  const elimina = pulsante("Elimina…", () => eliminaScheda(v.nome));
  elimina.classList.add("pericolo");
  azioni.append(elimina);
  return azioni;
}

// ---------------------------------------- la pagina dell'entità: che cosa sa già l'archivio
async function disegnaPaginaScheda(box, nome) {
  let r;
  try { r = await api("/api/scheda/pagina?" + new URLSearchParams({ nome })); } catch (e) {
    box.replaceChildren(el("p", e.message, "nota attenzione-testo"));
    return;
  }
  box.replaceChildren();
  const anni = Object.keys(r.per_anno);
  box.append(el("p", r.letti
    ? `${r.letti} ${r.letti === 1 ? "passaggio letto" : "passaggi letti"}, ${r.pertinenti} ${r.pertinenti === 1 ? "pertinente" : "pertinenti"}` +
      (anni.length ? ` · ${anni[0]}${anni.length > 1 ? "–" + anni[anni.length - 1] : ""}` : "")
    : "Nessun passaggio ancora letto: avvia una ricerca.", "riassunto-scheda"));
  if (anni.length > 1) box.append(tempoScheda(r.per_anno));
  const serie = Object.entries(r.per_serie);
  if (serie.length) {
    const p = el("p", null, "nota serie-scheda");
    p.append(el("span", "Nelle serie: ", "etichetta-faccetta"),
      document.createTextNode(serie.map(([s, n]) => `${senzaMarkdown(s)} (${n})`).join(" · ")));
    box.append(p);
  }
  if (r.risposte.length) {
    const ul = el("ul", null, "risposte-scheda");
    for (const x of r.risposte) {
      const li = el("li");
      const b = el("button", x.domanda + (x.evoluzione ? " (evoluzione)" : ""), "apri-passaggio");
      b.type = "button";
      b.addEventListener("click", () => apriDalloStorico({ documento: "/documento?" + new URLSearchParams({ risposta: x.file }),
        domanda: x.domanda, entita: nome }));
      li.append(b, el("span", x.data, "nota"));
      ul.append(li);
    }
    box.append(el("h4", "Risposte salvate"), ul);
  }
  if (r.collegate.length) {
    const p = el("p", null, "collegate-scheda");
    p.append(el("span", "Collegate: ", "etichetta-faccetta"));
    r.collegate.forEach((c, i) => {
      if (i) p.append(document.createTextNode(" · "));
      if (c.esiste) {
        const b = el("button", c.nome, "apri-passaggio");
        b.type = "button";
        b.addEventListener("click", () => apriVoceGlossario("scheda", c.nome));
        p.append(b);
      } else {
        p.append(el("span", `${c.nome} (senza scheda)`, "attenzione-testo"));
      }
    });
    box.append(p);
  }
  if (r.problemi.length) box.append(elencoProblemi(r.problemi, true));
}

// la linea del tempo della scheda: le stesse colonne del pannello dei passaggi, senza filtri
function tempoScheda(perAnno) {
  const anni = Object.keys(perAnno).map(Number);
  const tutti = [];
  for (let a = anni[0]; a <= anni[anni.length - 1]; a++) tutti.push(String(a));
  const massimo = Math.max(1, ...Object.values(perAnno).map((x) => x[0]));
  const tempo = el("div", null, "linea-tempo piccola");
  tempo.setAttribute("role", "img");
  tempo.setAttribute("aria-label", "Passaggi letti per anno: " +
    Object.entries(perAnno).map(([a, [n, si]]) => `${a}: ${n}, ${si} pertinenti`).join("; "));
  const barre = el("div", null, "barre-tempo");
  for (const a of tutti) {
    const [n, si] = perAnno[a] || [0, 0];
    const b = el("span", null, "periodo");
    b.title = `${a}: ${n} letti, ${si} pertinenti`;
    const c = el("span", null, "colonna");
    c.style.setProperty("--alto", String(n / massimo));
    c.style.setProperty("--pieno", String(n ? si / n : 0));
    b.append(c);
    barre.append(b);
  }
  const asse = el("div", null, "asse-tempo");
  asse.append(el("span", tutti[0]), el("span", tutti[tutti.length - 1]));
  tempo.append(barre, asse);
  return tempo;
}

// ---------------------------------------- forme suggerite dai passaggi letti
async function disegnaSuggerite(box, nome, d) {
  let r;
  try { r = await api("/api/scheda/forme?" + new URLSearchParams({ nome })); } catch (e) { return; }
  box.replaceChildren();
  if (!r.forme.length) return;
  const det = el("details", null, "suggerite");
  det.append(el("summary", `Forme suggerite dai passaggi letti (${r.forme.length})`));
  det.append(el("p", "Compaiono nei passaggi già letti e non sono nella scheda. «Aggiungi» le mette tra le forme " +
    "(la prossima ricerca legge solo i passaggi nuovi); «Scarta» non le ripropone più.", "nota"));
  const ul = el("ul", null, "elenco-suggerite");
  for (const f of r.forme) {
    const li = el("li");
    const testa = el("div", null, "testa");
    testa.append(el("strong", f.forma), el("span", `${f.volte} ${f.volte === 1 ? "volta" : "volte"}`, "nota"));
    const agg = pulsante("Aggiungi", () => decidiForma(nome, f.forma, true, li, d));
    const sca = pulsante("Scarta", () => decidiForma(nome, f.forma, false, li, d));
    sca.classList.add("discreto");
    testa.append(agg, sca);
    li.append(testa);
    if (f.esempio && f.esempio.testo) {
      const q = el("blockquote", f.esempio.testo.trim().slice(0, 240));
      q.title = senzaMarkdown(f.esempio.citazione || "");
      li.append(q);
    }
    ul.append(li);
  }
  det.append(ul);
  box.append(det);
  segnaSuggerite(nome, r.forme.length);
}

function segnaSuggerite(nome, n) {
  const d = [...document.querySelectorAll(".voce-glossario")].find((x) => x.dataset.tipo === "scheda" && x.dataset.nome === nome);
  if (!d) return;
  const s = d.querySelector("summary");
  let segno = s.querySelector(".segno-suggerite");
  if (!n) { if (segno) segno.remove(); return; }
  if (!segno) { segno = el("span", "", "segno-suggerite"); s.append(segno); }
  segno.textContent = `${n} ${n === 1 ? "forma suggerita" : "forme suggerite"}`;
}

async function decidiForma(nome, forma, aggiungi, li, d) {
  try {
    const r = await api("/api/scheda/forme", aggiungi ? { nome, aggiungi: [forma] } : { nome, scarta: [forma] });
    li.remove();
    annuncia(`${forma}: ${aggiungi ? "aggiunta alla scheda" : "scartata"}.`);
    if (r.nota) avviso(r.nota);
    const resto = d.querySelectorAll(".elenco-suggerite > li").length;
    segnaSuggerite(nome, resto);
    if (!resto) d.querySelector(".forme-suggerite").replaceChildren();
    if (aggiungi) { precedentiDi.clear(); await caricaGlossario({ tipo: "scheda", nome }); }
  } catch (e) {
    avviso(e.message, true);
  }
}

// ---------------------------------------- modifica di una scheda, nel pannello
// Le forme sono chip: il numero accanto dice quante righe delle fonti la contengono (si contano mentre si scrive),
// un clic sul nome la segna ambigua, × la toglie. Si salvano solo i campi cambiati; i campi che il modulo non conosce
// restano nel file come sono.
async function modificaScheda(d, nome) {
  let s;
  try { s = await api("/api/scheda?" + new URLSearchParams({ nome })); } catch (e) { avviso(e.message, true); return; }
  const corpo = d.querySelector(".corpo-voce");
  const modulo = el("form", null, "modulo-scheda");
  modulo.noValidate = true;
  const ambigue = new Set(s.forme_ambigue);
  const forme = [...s.varianti];
  const conti = {};
  const esempi = {};
  const lista = el("div", null, "forme-chip modifica");
  lista.setAttribute("role", "list");
  lista.setAttribute("aria-label", "Forme del nome");
  const esempio = el("div", null, "esempio-forma");
  esempio.hidden = true;
  const totale = el("p", "", "nota totale-forme");
  let controllaPrima = () => {};               // assegnata più sotto, quando tutti i campi esistono
  const disegnaForme = () => {
    lista.replaceChildren();
    for (const f of forme) {
      const chip = el("span", null, "chip-forma modifica" + (ambigue.has(f) ? " ambigua" : ""));
      chip.setAttribute("role", "listitem");
      const nomeF = el("button", f, "nome-forma");
      nomeF.type = "button";
      nomeF.setAttribute("aria-pressed", String(ambigue.has(f)));
      nomeF.title = "Segna o togli «ambigua»";
      nomeF.addEventListener("click", () => { if (ambigue.has(f)) ambigue.delete(f); else ambigue.add(f); disegnaForme(); });
      const conto = el("button", conti[f] === undefined ? "…" : conti[f] === null ? "?" : String(conti[f]), "conto");
      conto.type = "button";
      conto.title = "Righe delle fonti con questa forma: un clic mostra un esempio";
      conto.setAttribute("aria-label", `${f}: ${conti[f] ?? "righe non ancora contate"} righe. Mostra un esempio`);
      if (conti[f] === 0) chip.classList.add("vuota");
      conto.addEventListener("click", () => mostraEsempio(f));
      const togli = el("button", "×", "togli-forma");
      togli.type = "button";
      togli.setAttribute("aria-label", `Togli «${f}»`);
      togli.addEventListener("click", () => {
        forme.splice(forme.indexOf(f), 1);
        ambigue.delete(f);
        disegnaForme();
        nuova.focus();
      });
      chip.append(nomeF, conto, togli);
      lista.append(chip);
    }
    const noti = forme.filter((f) => typeof conti[f] === "number");
    totale.textContent = noti.length ? `${noti.reduce((n, f) => n + conti[f], 0)} righe in tutto (una riga con due forme ` +
      "conta due volte). Clic sul nome: ambigua; sul numero: un esempio." : "";
    controllaPrima();
  };
  const mostraEsempio = (f) => {
    const e = esempi[f];
    esempio.hidden = false;
    esempio.replaceChildren(el("strong", f), e ? el("blockquote", e.testo) : el("p", "Nessuna riga delle fonti contiene questa forma.", "nota"));
    if (e) {
      const a = el("button", senzaMarkdown(e.riferimento), "apri-passaggio");
      a.type = "button";
      a.addEventListener("click", () => apriFonte(e.file, e.riga, null, null, "glossario"));
      esempio.append(a);
    }
  };
  // segna: le forme appena aggiunte che sono brevi (un cognome da solo, una sigla corta) entrano già ambigue,
  // come fanno la creazione e le forme suggerite: il controllo del glossario non ha più niente da dire dopo
  const conta = async (nuove, segna) => {
    const da = nuove.filter((f) => !(f in conti));
    if (!da.length) return;
    try {
      const r = await api("/api/forme/conta", { forme: da });
      Object.assign(conti, r.conti);
      Object.assign(esempi, r.esempi || {});
      const brevi = segna ? (r.brevi || []).filter((f) => nuove.includes(f) && forme.includes(f)) : [];
      for (const f of brevi) ambigue.add(f);
      if (brevi.length) annuncia(`${brevi.join("; ")}: forma breve, segnata ambigua.`);
    } catch (e) { for (const f of da) conti[f] = null; }
    disegnaForme();
  };
  const nuova = document.createElement("input");
  nuova.type = "text";
  nuova.placeholder = "aggiungi una forma, poi Invio (più forme: separate da ;)";
  nuova.setAttribute("aria-label", "Aggiungi una forma del nome");
  nuova.addEventListener("keydown", (e) => {
    if (e.key !== "Enter") return;
    e.preventDefault();
    const nuove = nuova.value.split(/[;；]/).map((x) => x.trim()).filter((x) => x && !forme.includes(x));
    if (!nuove.length) return;
    forme.push(...nuove);
    nuova.value = "";
    disegnaForme();
    conta(nuove, true);
  });
  const campo = (etichetta, controllo, spiega) => {
    const l = el("label", null, "campo-scheda");
    l.append(el("span", etichetta, "etichetta-campo"), controllo);
    if (spiega) l.append(el("span", spiega, "nota"));
    return l;
  };
  const tipo = document.createElement("select");
  tipo.append(new Option("—", ""));
  for (const t of s.tipi) tipo.append(new Option(t, t));
  tipo.value = s.tipo || "";
  const estesa = document.createElement("input");
  estesa.type = "text";
  estesa.value = s.forma_estesa;
  const contesto = document.createElement("input");
  contesto.type = "text";
  contesto.value = s.contesto.join("; ");
  const collegate = new Set(s.collegate);
  const boxColl = el("div", null, "chip-riga");
  const sceltaColl = document.createElement("select");
  const disegnaColl = () => {
    boxColl.replaceChildren();
    for (const c of collegate) {
      const chip = el("span", null, "chip statico");
      const x = el("button", "×", "togli-forma");
      x.type = "button";
      x.setAttribute("aria-label", `Togli «${c}» dalle collegate`);
      x.addEventListener("click", () => { collegate.delete(c); disegnaColl(); });
      chip.append(document.createTextNode(c + " "), x);
      boxColl.append(chip);
    }
    sceltaColl.replaceChildren(new Option("aggiungi una scheda collegata…", ""));
    for (const c of s.schede) if (!collegate.has(c)) sceltaColl.append(new Option(c, c));
    controllaPrima();
  };
  sceltaColl.addEventListener("change", () => { if (sceltaColl.value) { collegate.add(sceltaColl.value); disegnaColl(); } });
  const note = document.createElement("textarea");
  note.rows = 3;
  note.value = s.note;
  const noti = new Set(["tipo", "forma_estesa", "varianti", "contesto", "forme_ambigue", "collegate", "note"]);
  const altri = Object.keys(s.campi).filter((k) => !noti.has(k) && String(s.campi[k]).trim());
  const esito = el("div", null, "esito-scheda");
  const salva = el("button", "Salva", "primario");
  salva.type = "submit";
  const annulla = el("button", "Annulla");
  annulla.type = "button";
  annulla.addEventListener("click", () => {
    const v = stato.glossario.schede.find((x) => x.nome === nome);
    mostraVoce(d, v, "scheda");
  });
  const riga = el("div", null, "riga");
  riga.append(salva, annulla);
  const gruppoForme = el("div", null, "campo-scheda");
  gruppoForme.append(el("span", "Forme del nome", "etichetta-campo"), lista, nuova, totale, esempio);
  modulo.append(gruppoForme,
    campo("Tipo", tipo),
    campo("Forma estesa", estesa, "il nome per esteso, se la scheda è una sigla"),
    campo("Contesto", contesto, "parole che aiutano il modello a riconoscerla, separate da ;"),
    campo("Collegate", boxColl), sceltaColl,
    campo("Note", note, "chi è, il periodo, gli omonimi da non confondere"));
  if (altri.length) modulo.append(el("p", `Altri campi, che restano come sono: ${altri.join(", ")}.`, "nota"));
  // il controllo della scheda così com'è nel modulo, prima di salvare (una copia del glossario, il file non cambia)
  const prima = el("div", null, "controllo-prima");
  prima.setAttribute("aria-live", "polite");
  let attesaControllo = null;
  controllaPrima = () => {
    clearTimeout(attesaControllo);
    attesaControllo = setTimeout(async () => {
      if (!forme.length) return;
      try {
        const v = await api("/api/scheda/verifica", { nome, campi: {
          varianti: forme, forme_ambigue: forme.filter((f) => ambigue.has(f)), tipo: tipo.value,
          forma_estesa: estesa.value, contesto: contesto.value, collegate: [...collegate], note: note.value } });
        prima.replaceChildren(...(v.problemi.length ? [el("p", "Prima di salvare:", "nota"), elencoProblemi(v.problemi, true)]
          : [el("p", "Nessun problema: la scheda è in ordine.", "nota esito-ocr-ok")]));
      } catch (e) { prima.replaceChildren(); }
    }, 500);
  };
  for (const c of [tipo, estesa, contesto, note]) c.addEventListener("input", controllaPrima);
  modulo.append(prima, riga, esito);
  modulo.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); annulla.click(); } });
  modulo.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!forme.length) { avviso("Una scheda ha almeno una forma del nome.", true); nuova.focus(); return; }
    salva.disabled = true;
    try {
      const r = await api("/api/scheda/modifica", { nome, campi: {
        varianti: forme, forme_ambigue: forme.filter((f) => ambigue.has(f)), tipo: tipo.value,
        forma_estesa: estesa.value, contesto: contesto.value, collegate: [...collegate], note: note.value } });
      precedentiDi.clear();
      contiRighe.clear();
      annuncia(r.cambiati.length ? `Scheda «${nome}» salvata.` : "Nessun cambiamento.");
      await caricaGlossario({ tipo: "scheda", nome });
      const dopo = [...document.querySelectorAll(".voce-glossario")].find((x) => x.dataset.tipo === "scheda" && x.dataset.nome === nome);
      if (dopo) {
        const box = el("div", null, "esito-scheda");
        box.append(el("p", r.nota, "nota"));
        if (r.problemi.length) box.append(elencoProblemi(r.problemi, true));
        dopo.querySelector(".corpo-voce").prepend(box);
      }
    } catch (err) {
      salva.disabled = false;
      esito.replaceChildren(el("p", err.message, "nota attenzione-testo"));
    }
  });
  corpo.replaceChildren(modulo);
  disegnaForme();
  disegnaColl();
  nuova.focus();
  conta(forme);
}

async function rinominaScheda(d, nome) {
  const corpo = d.querySelector(".corpo-voce");
  if (corpo.querySelector(".modulo-rinomina")) return;
  const f = el("form", null, "modulo-rinomina riga");
  const i = document.createElement("input");
  i.type = "text";
  i.value = nome;
  i.setAttribute("aria-label", "Nuovo nome della scheda");
  const ok = el("button", "Rinomina", "primario");
  ok.type = "submit";
  const no = el("button", "Annulla");
  no.type = "button";
  no.addEventListener("click", () => f.remove());
  f.append(i, ok, no);
  f.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); f.remove(); } });
  f.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nuovo = i.value.trim();
    if (!nuovo || nuovo === nome) { f.remove(); return; }
    try {
      const r = await api("/api/scheda/rinomina", { nome, nuovo });
      avviso(r.nota);
      precedentiDi.clear();
      await caricaGlossario({ tipo: "scheda", nome: r.nuovo });
    } catch (err) { avviso(err.message, true); }
  });
  corpo.querySelector(".azioni-scheda").after(f);
  i.select();
}

async function unisciScheda(d, nome) {
  const corpo = d.querySelector(".corpo-voce");
  if (corpo.querySelector(".modulo-unisci")) return;
  const altre = (stato.glossario.schede || []).map((x) => x.nome).filter((x) => x !== nome);
  if (!altre.length) { avviso("Non ci sono altre schede a cui unirla.", true); return; }
  const f = el("form", null, "modulo-unisci riga");
  const sel = document.createElement("select");
  sel.setAttribute("aria-label", "Scheda in cui unire");
  for (const x of altre) sel.append(new Option(x, x));
  const ok = el("button", "Unisci", "primario");
  ok.type = "submit";
  const no = el("button", "Annulla");
  no.type = "button";
  no.addEventListener("click", () => f.remove());
  f.append(el("span", `Unisci «${nome}» a`), sel, ok, no);
  f.addEventListener("submit", async (e) => { e.preventDefault(); await unisciSchede(nome, sel.value); });
  corpo.querySelector(".azioni-scheda").after(f);
  sel.focus();
}

async function unisciSchede(da, verso) {
  if (!await conferma(`Unire «${da}» a «${verso}»?`, `Forme, forme ambigue e collegate di «${da}» passano a «${verso}», ` +
    `e così le letture dell'archivio; «${da}» si toglie dal glossario. Una copia del glossario di oggi resta accanto al file.`,
    "Unisci")) return;
  try {
    const r = await api("/api/scheda/unisci", { da, verso });
    avviso(r.nota);
    precedentiDi.clear();
    await caricaGlossario({ tipo: "scheda", nome: verso });
  } catch (e) { avviso(e.message, true); }
}

async function eliminaScheda(nome) {
  if (!await conferma(`Eliminare la scheda «${nome}»?`, "La scheda esce dal glossario e dalle collegate delle altre. " +
    "I passaggi già letti restano nell'archivio, e una copia del glossario di oggi resta accanto al file.", "Elimina")) return;
  try {
    const r = await api("/api/scheda/elimina", { nome });
    avviso(r.nota);
    await caricaGlossario({});
  } catch (e) { avviso(e.message, true); }
}

// ---------------------------------------- salute del glossario
function elencoProblemi(problemi, breve) {
  const ul = el("ul", null, "problemi-glossario");
  const segni = { errore: "!", avviso: "!", info: "i" };
  for (const p of problemi) {
    const li = el("li", null, "grav-" + p.gravita);      // «avviso» è già la barra degli avvisi
    const segno = el("span", segni[p.gravita] || "·", "segno-problema");
    segno.setAttribute("aria-hidden", "true");
    li.append(segno);
    const testo = el("span", null, "testo-problema");
    testo.append(el("span", p.gravita === "errore" ? "Errore: " : p.gravita === "avviso" ? "Avviso: " : "Nota: ", "solo-lettori"));
    if (!breve) {
      const schede_ = Array.isArray(p.schede) ? p.schede : [p.schede];
      schede_.forEach((s, i) => {
        if (i) testo.append(document.createTextNode(" / "));
        const b = el("button", s, "apri-passaggio");
        b.type = "button";
        b.addEventListener("click", () => apriVoceGlossario("scheda", s));
        testo.append(b);
      });
      testo.append(document.createTextNode(": "));
    }
    testo.append(document.createTextNode(p.problema));
    li.append(testo);
    if (p.unibili) {
      const [a, b] = p.schede;
      const azioni = el("span", null, "azioni-problema");
      azioni.append(pulsante(`Unisci «${a}» a «${b}»`, () => unisciSchede(a, b)),
        pulsante(`Unisci «${b}» a «${a}»`, () => unisciSchede(b, a)));
      li.append(azioni);
    }
    if (p.correzione && !breve) {
      const s = Array.isArray(p.schede) ? p.schede[0] : p.schede;
      const azioni = el("span", null, "azioni-problema");
      const b = pulsante(p.correzione.tipo === "note" ? "Scrivi le note" : "Correggi", () =>
        p.correzione.tipo === "note" ? scriviNote(s) : correggiProblema(s, p.correzione.tipo, b));
      b.title = p.correzione.descrizione;
      azioni.append(b, el("span", p.correzione.tipo === "note" ? "" : p.correzione.descrizione, "nota"));
      li.append(azioni);
    }
    ul.append(li);
  }
  return ul;
}

async function controllaGlossario() {
  const box = $("gl-controllo");
  let r;
  try { r = await api("/api/glossario/controllo"); } catch (e) { box.hidden = true; return; }
  const seri = r.problemi.filter((p) => p.gravita !== "info");
  box.hidden = !r.problemi.length;
  const segno = $("gl-segno");
  if (segno) {
    segno.hidden = !r.errori;
    segno.textContent = r.errori ? String(r.errori) : "";
  }
  if (!r.problemi.length) return;
  const aperto = box.querySelector("details") && box.querySelector("details").open;
  const det = el("details", null, "controllo-glossario" + (r.errori ? " con-errori" : ""));
  const parti = [];
  if (r.errori) parti.push(`${r.errori} ${r.errori === 1 ? "errore" : "errori"}`);
  if (r.avvisi) parti.push(`${r.avvisi} ${r.avvisi === 1 ? "avviso" : "avvisi"}`);
  const note = r.problemi.length - seri.length;
  if (note) parti.push(`${note} ${note === 1 ? "nota" : "note"}`);
  det.append(el("summary", `Controllo del glossario: ${parti.join(", ")}`));
  if (r.automatiche > 1) {
    const tutte = pulsante(`Correggi tutto ciò che si corregge da sé (${r.automatiche})`, async () => {
      tutte.disabled = true;
      try {
        const x = await api("/api/scheda/correggi", { tutte: true });
        avviso(x.nota);
        await caricaGlossario({});
      } catch (e) { tutte.disabled = false; avviso(e.message, true); }
    }, true);
    tutte.classList.add("correggi-tutto");
    det.append(tutte);
  }
  det.append(elencoProblemi(r.problemi, false));
  det.open = aperto || r.errori > 0;
  box.replaceChildren(det);
}

async function correggiProblema(nome, tipo, b) {
  b.disabled = true;
  try {
    const r = await api("/api/scheda/correggi", { nome, tipo });
    annuncia(r.nota);
    precedentiDi.clear();
    await caricaGlossario({ tipo: "scheda", nome });
  } catch (e) { b.disabled = false; avviso(e.message, true); }
}

// le note non si scrivono da sole: si apre la scheda in modifica, con il cursore nelle note
async function scriviNote(nome) {
  apriVoceGlossario("scheda", nome);
  const d = [...document.querySelectorAll(".voce-glossario")].find((x) => x.dataset.tipo === "scheda" && x.dataset.nome === nome);
  if (!d) return;
  await modificaScheda(d, nome);
  const t = d.querySelector(".modulo-scheda textarea");
  if (t) { t.focus(); t.scrollIntoView({ block: "center" }); }
}

// ---------------------------------------- profili delle serie, con l'anteprima della citazione
const CAMPI_SERIE = ["tipo", "lingua", "sigla", "chicago", "citazione", "autore", "titolo", "luogo", "editore",
  "curatori", "titolo_volume", "periodicita", "nota_limiti", "ocr_lingue"];

async function modificaSerie(d, v) {
  let s;
  try { s = await api("/api/serie?" + new URLSearchParams({ nome: v.nome })); } catch (e) { avviso(e.message, true); return; }
  const corpo = d.querySelector(".corpo-voce");
  const modulo = el("form", null, "modulo-scheda modulo-serie");
  const campi = {};
  const anteprima = el("div", null, "anteprima-citazione");
  anteprima.setAttribute("aria-live", "polite");
  let attesa = null;
  const aggiornaAnteprima = () => {
    clearTimeout(attesa);
    attesa = setTimeout(async () => {
      const valori = Object.fromEntries(Object.entries(campi).map(([k, c]) => [k, c.value]));
      let r;
      try { r = await api("/api/serie/anteprima", { nome: v.nome, campi: valori }); } catch (e) { return; }
      anteprima.replaceChildren(el("span", "Anteprima della citazione", "etichetta-campo"));
      if (r.citazione) {
        const p = el("p", null, "citazione-anteprima");
        // corsivo del Markdown (*Titolo*) come nella risposta
        for (const [k, pezzo] of r.citazione.split(/\*([^*]+)\*/).entries()) p.append(k % 2 ? el("em", pezzo) : document.createTextNode(pezzo));
        anteprima.append(p);
      }
      if (r.errore) anteprima.append(el("p", r.errore, "nota attenzione-testo"));
      if (r.segnaposti) anteprima.append(el("p", "Quelli che esistono: " + r.segnaposti.map((n) => `{${n}}`).join(" "), "nota"));
      anteprima.append(el("p", r.documento ? `${r.nota || ""} Documento: ${r.titolo || r.documento}.` : r.nota, "nota"));
    }, 350);
  };
  const aggiungiCampo = (k, val) => {
    if (campi[k]) { campi[k].focus(); return; }
    const lungo = ["chicago", "citazione", "nota_limiti"].includes(k);
    let c;
    if (k === "tipo") {
      c = document.createElement("select");
      for (const t of s.tipi) c.append(new Option(t, t));
      if (val && !s.tipi.includes(val)) c.append(new Option(val, val));
    } else {
      c = document.createElement(lungo ? "textarea" : "input");
      if (lungo) c.rows = 3; else c.type = "text";
    }
    c.value = val || "";
    c.addEventListener("input", aggiornaAnteprima);
    c.addEventListener("change", aggiornaAnteprima);
    campi[k] = c;
    const l = el("label", null, "campo-scheda");
    l.append(el("span", etichettaCampo(k), "etichetta-campo"), c);
    if (k === "chicago") l.append(el("span", "Segnaposti tra graffe: {autore_bib}, {titolo}, {data_o_anno}, {pagine}, " +
      "{pagina}…; le parti tra [ ] spariscono se il loro segnaposto è vuoto.", "nota"));
    elenco.append(l);
    return c;
  };
  const elenco = el("div", null, "campi-serie");
  for (const [k, val] of Object.entries(s.campi)) aggiungiCampo(k, val);
  const nuovo = document.createElement("select");
  const disegnaNuovo = () => {
    nuovo.replaceChildren(new Option("aggiungi un campo…", ""));
    for (const k of CAMPI_SERIE) if (!campi[k]) nuovo.append(new Option(etichettaCampo(k), k));
  };
  nuovo.setAttribute("aria-label", "Aggiungi un campo al profilo");
  nuovo.addEventListener("change", () => {
    if (!nuovo.value) return;
    const c = aggiungiCampo(nuovo.value, "");
    disegnaNuovo();
    c.focus();
  });
  disegnaNuovo();
  const esito = el("div", null, "esito-scheda");
  const salva = el("button", "Salva", "primario");
  salva.type = "submit";
  const annulla = el("button", "Annulla");
  annulla.type = "button";
  annulla.addEventListener("click", () => mostraVoce(d, v, "serie"));
  const riga = el("div", null, "riga");
  riga.append(salva, annulla);
  modulo.append(elenco, nuovo, anteprima, riga, esito);
  modulo.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); annulla.click(); } });
  modulo.addEventListener("submit", async (e) => {
    e.preventDefault();
    salva.disabled = true;
    try {
      const valori = Object.fromEntries(Object.entries(campi).map(([k, c]) => [k, c.value]));
      const r = await api("/api/serie/modifica", { nome: v.nome, campi: valori });
      annuncia(r.nota);
      avviso(r.nota);
      await caricaGlossario({ tipo: "serie", nome: v.nome });
    } catch (err) {
      salva.disabled = false;
      esito.replaceChildren(el("p", err.message, "nota attenzione-testo"));
    }
  });
  corpo.replaceChildren(modulo);
  aggiornaAnteprima();
  const primo = elenco.querySelector("input, textarea, select");
  if (primo) primo.focus();
}

function filtraGlossario() {
  const f = $("gl-filtro").value.trim().toLowerCase();
  document.querySelectorAll(".voce-glossario").forEach((d) => { d.hidden = !!f && !d.dataset.cerca.includes(f); });
}

// al cambio di progetto: documenti, passaggi, fonte e glossario erano del progetto di prima
function dimenticaProgetto() {
  stato.doc = null;
  stato.cachePassaggi = {};
  stato.glossario = null;
  stato.fonte = null;
  mostra("fonte", false);
  mostra("fonte-vuota", true);
  $("passaggi-tabella").replaceChildren();
}

// ------------------------------------------------------------------ progetto
async function caricaTutto() {
  let s;
  try {
    s = await api("/api/stato");
  } catch (e) {
    avviso(e.message, true);
    return;
  }
  stato.progetti = s.progetti || [];
  const sel = $("progetto");
  sel.replaceChildren();
  if (!s.progetto) sel.append(new Option("— nessun progetto —", "", true, true));
  for (const p of stato.progetti) {
    const o = new Option(p.nome, p.cartella, p.in_uso, p.in_uso);
    o.title = p.cartella;
    sel.append(o);
  }
  sel.dataset.attuale = s.progetto ? s.progetto.cartella : "";
  sel.title = s.progetto ? `${s.progetto.nome}: ${s.progetto.cartella}` : "Nessun progetto in uso";
  disegnaProgetti();
  $("np-dove").textContent = `La cartella si crea in ${s.cartella_progetti}.`;
  if (!s.progetto) {
    avviso("Nessun progetto in uso: scegline uno dal menu in alto a sinistra o creane uno nuovo.");
  } else if (!s.progetto.documenti) {
    avviso(`Il progetto «${s.progetto.nome}» non ha ancora documenti: usa «Importa fonti».`);
  } else {
    avviso("");
  }
  $("vuoto-progetto").textContent = s.progetto ?
    `${s.progetto.nome}${s.progetto.documenti ? ` · ${s.progetto.documenti} documenti` : ""}` : "";
  await Promise.all([caricaModelli(), caricaFonti(), caricaStorico()]);
  await mostraRicerca(s.ricerca, true);
  if (s.progetto) controllaGlossario();          // il segno sul pulsante Glossario, se ci sono errori nelle schede
}

function apriNuovoProgetto() {
  $("np-nome").value = "";
  $("np-descrizione").value = "";
  $("d-progetto").showModal();
}

// Un menu che cambia progetto o modello fa qualcosa di pesante (chiude il filo, prova il collegamento): da tastiera le
// frecce sul menu chiuso scorrono le voci senza agire, e la scelta vale con Invio o quando il fuoco lascia il menu.
// Con il mouse (menu aperto, clic su una voce) vale subito.
function sceltaConConferma(sel, agisci) {
  let sospesa = false;
  const conferma_ = () => {
    sospesa = false;
    sel.classList.remove("in-sospeso");
    if (sel.value !== sel.dataset.attuale) agisci();
  };
  sel.addEventListener("keydown", (e) => {
    if (e.altKey || e.key === " " || e.key === "F4") return;          // aprono la tendina: lì la scelta è esplicita
    if (e.key === "Enter") { if (sospesa) { e.preventDefault(); conferma_(); } return; }
    if (e.key === "Escape" && sospesa) {
      e.preventDefault();
      e.stopPropagation();
      sospesa = false;
      sel.classList.remove("in-sospeso");
      sel.value = sel.dataset.attuale;
      return;
    }
    if (/^(Arrow|Home|End|Page)/.test(e.key) || e.key.length === 1) sospesa = true;
  });
  sel.addEventListener("change", () => {
    if (sospesa) { sel.classList.toggle("in-sospeso", sel.value !== sel.dataset.attuale); return; }
    agisci();
  });
  sel.addEventListener("blur", () => { if (sospesa) conferma_(); });
}

// i progetti nella sezione Generale delle Impostazioni: il cambio è un'azione esplicita, con conferma se c'è una
// ricerca aperta (la conversazione resta tra i Recenti del progetto di prima)
function disegnaProgetti() {
  const ul = $("cfg-progetti");
  const parti = (stato.progetti || []).map((p) => {
    const li = el("li", null, "modello-voce progetto-voce" + (p.in_uso ? " in-uso" : ""));
    const testa = el("div", null, "testa");
    testa.append(el("span", p.nome, "nome"));
    if (p.descrizione) testa.append(el("span", p.descrizione, "profilo"));
    // la cartella per intero è lunga e uguale in testa per tutti: si vedono le ultime due parti, il resto nel titolo
    const parti_ = String(p.cartella || "").split(/[\\/]+/).filter(Boolean);
    const cartella = el("span", parti_.length > 2 ? "…\\" + parti_.slice(-2).join("\\") : p.cartella, "cartella");
    cartella.title = p.cartella;
    li.append(testa, cartella);
    const azione = el("div", null, "azione");
    if (p.in_uso) azione.append(el("span", "in uso", "segno ok"));
    else {
      const b = pulsante("Usa", () => cambiaProgetto(p));
      b.setAttribute("aria-label", "Usa il progetto " + p.nome);
      azione.append(b);
    }
    li.append(azione);
    if (stato.esitoProgetto && stato.esitoProgetto.cartella === p.cartella) {
      li.append(el("span", stato.esitoProgetto.testo, "esito attenzione-testo"));
    }
    return li;
  });
  if (!parti.length) parti.push(el("li", "Nessun progetto ancora: creane uno.", "nota vuoto-progetti"));
  ridisegna(ul, parti);
}

// dal menu della barra: il menu torna subito al progetto in uso, e cambia solo se il cambio riesce
function sceltaProgetto() {
  const sel = $("progetto");
  const scelto = sel.value;
  sel.value = sel.dataset.attuale;
  const p = (stato.progetti || []).find((x) => x.cartella === scelto);
  if (p && !p.in_uso) cambiaProgetto(p);
}

async function cambiaProgetto(p) {
  const aperta = stato.inCorso || $("messaggi").children.length > 0;
  if (aperta && !await conferma(`Passare a «${p.nome}»?`, "La ricerca aperta si chiude: la ritrovi tra i Recenti " +
    "quando torni a questo progetto. Una ricerca in corso impedisce il cambio.", "Cambia progetto")) return;
  stato.esitoProgetto = null;
  try {
    await api("/api/progetto", { cartella: p.cartella });
    dimenticaProgetto();
    nuovoThread();
    chiudiLaterale();
    stato.elenchi = {};
    await caricaTutto();
    if (!$("vista-impostazioni").hidden) mostraVista("impostazioni");   // nuovoThread torna al filo
    aggiornaAvvio();
    annuncia(`Progetto in uso: ${p.nome}.`);
  } catch (e) {
    stato.esitoProgetto = { cartella: p.cartella, testo: e.message };   // il progetto non cambia
    disegnaProgetti();
    annuncia(e.message, true);
  }
}

async function creaProgetto(evento) {
  evento.preventDefault();
  const nome = $("np-nome").value.trim();
  if (!nome) { $("np-nome").reportValidity(); $("np-nome").focus(); return; }
  try {
    await api("/api/progetto/nuovo", { nome, descrizione: $("np-descrizione").value.trim() });
    $("d-progetto").close();
    dimenticaProgetto();
    nuovoThread();
    await caricaTutto();
    aggiornaAvvio();
  } catch (e) {
    avviso(e.message, true);
    $("d-progetto").close();
  }
}

// ------------------------------------------------------------------ modello
// La scelta del modello sta nelle Impostazioni: la pagina «Modelli» raccoglie i modelli dei fornitori attivi, ogni
// fornitore ha la sua pagina (chiave e modelli). Un fornitore è attivo se ha la chiave o non ne ha bisogno: i
// modelli degli altri non si mostrano. Nella casella resta il nome del modello in uso, con il pallino.
const RUOLI = [["smistamento", "Smistamento", "sceglie i passaggi pertinenti"],
  ["analisi", "Analisi", "legge e traduce i passaggi"], ["sintesi", "Sintesi", "scrive la risposta"]];

// le icone dei marchi (fornitori.svg, LobeHub icons, MIT); un indirizzo sconosciuto ha l'icona di un servizio
const ICONE = new Set(["ollama", "anthropic", "groq", "google-gemini", "openrouter", "freellmapi", "openai",
  "mistral", "xai", "minimax", "hugging-face", "nvidia-nim"]);

const DESCRIZIONI = {
  ollama: "Modelli che girano sul tuo computer: gratuiti, senza chiave, e i testi non escono dal computer.",
  freellmapi: "Router avviato sul tuo computer che passa da un servizio gratuito all'altro.",
  anthropic: "I modelli Claude, a consumo.",
  groq: "Piano gratuito, risposte veloci.",
  "google-gemini": "Piano gratuito sui modelli Flash: i testi possono essere usati da Google.",
  openrouter: "I modelli con nome che finisce in «:free» sono gratuiti (50 richieste al giorno senza acquisti).",
  openai: "I modelli GPT, a consumo.",
  mistral: "Modelli Mistral, con un piano gratuito a richieste limitate.",
  xai: "I modelli Grok, a consumo.",
  minimax: "Modelli MiniMax, a consumo.",
  "hugging-face": "Modelli aperti di più fornitori, attraverso il router di Hugging Face. La chiave è un token " +
    "dell'account; si prova la prima volta che usi un modello.",
  "nvidia-nim": "Modelli aperti ospitati da NVIDIA, con crediti gratuiti. La chiave si prova la prima volta che " +
    "usi un modello.",
};

function icona(fornitore) {
  const ns = "http://www.w3.org/2000/svg";
  const s = document.createElementNS(ns, "svg");
  s.setAttribute("class", "logo");
  s.setAttribute("viewBox", "0 0 24 24");
  s.setAttribute("aria-hidden", "true");
  const u = document.createElementNS(ns, "use");
  u.setAttribute("href", "fornitori.svg#f-" + (ICONE.has(fornitore.id) ? fornitore.id : "server"));
  s.append(u);
  return s;
}

// i modelli accesi di un fornitore (spenti per interruttore no; quello in uso resta sempre visibile)
const sceglibili = (f) => f.profili.filter((p) => !p.bloccato || p.in_uso_per.length);
const fornitoriAttivi = () => (stato.fornitori || []).filter((f) => f.attivo);

// il modello in uso: un nome se tutti i ruoli usano lo stesso profilo, null se sono diversi o se manca
function modelloUnico() {
  const nomi = new Set(Object.values(stato.inUso || {}));
  return nomi.size === 1 ? [...nomi][0] : null;
}

function profiloDi(nome) {
  for (const f of stato.fornitori || []) {
    const p = f.profili.find((x) => x.nome === nome);
    if (p) return p;
  }
  return null;
}

function nomeModello(nome) {
  const p = profiloDi(nome);
  return p ? `${p.modello || p.nome} · ${p.fornitore.nome}` : nome;
}

// nuovaConversazione: false quando cambia solo ciò che si vede (una chiave, l'apertura delle Impostazioni)
async function caricaModelli(nuovaConversazione = true) {
  let m;
  try {
    m = await api("/api/fornitori");
  } catch (e) {
    avviso(e.message, true);
    return;
  }
  ricevi(m);
  if (nuovaConversazione) stato.convNuova = true;    // progetto o modello cambiati: la conversazione ricomincia
  aggiornaLocali();                               // senza aspettarlo: chi chiama non resta fermo
}

// lo stato dei servizi sul computer arriva dopo: su Windows una porta chiusa risponde dopo qualche secondo
async function aggiornaLocali() {
  const n = (stato.richiestaLocali = (stato.richiestaLocali || 0) + 1);
  try {
    const l = await api("/api/fornitori?locali=1");
    if (n === stato.richiestaLocali) ricevi(l);   // una richiesta più recente vince
  } catch (e) { /* resta lo stato «da controllare» */ }
}

function ricevi(m) {
  // senza la domanda ai servizi sul computer, si tiene lo stato già saputo
  const prima = Object.fromEntries((stato.fornitori || []).map((f) => [f.id, f]));
  stato.fornitori = (m.fornitori || []).map((f) => (!m.locali && f.locale && f.pronto === null && prima[f.id] ?
    { ...f, raggiungibile: prima[f.id].raggiungibile, installati: prima[f.id].installati, pronto: prima[f.id].pronto } :
    f));
  if (m.locali) for (const f of stato.fornitori) if (f.id === "ollama") delete stato.elenchi.ollama;
  stato.inUso = m.in_uso || {};
  stato.notaModelli = m.nota || "";
  const unico = modelloUnico();
  menuModelli(unico);
  if (m.errore) avviso(m.errore, true);
  aggiornaPallino();
  disegnaFornitoriNav();
  disegnaModelli();
  disegnaFornitore();
}

// il colore del pallino non basta: lo stato va anche nel testo letto dai lettori di schermo
const STATI_PALLINO = { "": "non provato", attesa: "prova in corso", ok: "collegato", male: "non raggiungibile" };

function pallino(stato_, dettaglio) {
  const p = $("pallino");
  p.className = "pallino" + (stato_ ? " " + stato_ : "");
  const nome = "Collegamento: " + STATI_PALLINO[stato_];
  const testo = dettaglio && dettaglio !== STATI_PALLINO[stato_] ? `${nome} (${dettaglio})` : nome;
  $("pallino-stato").textContent = testo;
  $("pallino").title = testo;
}

async function aggiornaPallino() {
  const nome = modelloUnico();
  pallino("");
  if (!nome) return;
  pallino("attesa");
  try {
    const c = await api("/api/collegamento?nome=" + encodeURIComponent(nome));
    pallino(c.ok ? "ok" : "male", c.dettaglio || (c.ok ? "collegato" : "non raggiungibile"));
  } catch (e) {
    pallino("male", e.message);
  }
}

// usa un profilo per tutti i ruoli o per quelli dati; la prova di collegamento decide, e l'esito resta accanto al
// modello scelto (stato.esitoModello) anche dopo che la pagina si ridisegna
async function usaModello(nome, ruoli) {
  const chiave = ruoli ? "ruolo:" + ruoli.join(",") : nome;
  stato.esitoModello = { chiave, testo: `Prova di collegamento con «${nome}»…`, attesa: true };
  disegnaModelli();
  disegnaFornitore();
  if (!ruoli) pallino("attesa", "Prova di collegamento in corso…");
  annuncia(stato.esitoModello.testo);
  let esito;
  try {
    const r = await api("/api/modello/usa", ruoli ? { nome, ruoli } : { nome });
    esito = r.cambiato ?
      { testo: "Collegato: in uso." + (r.ricerca_in_corso ? " " + r.ricerca_in_corso : "") } :
      { testo: "Non cambiato: " + (r.messaggi || []).join(" "), errore: true };
  } catch (e) {
    esito = { testo: e.message, errore: true };
  }
  stato.esitoModello = { chiave, ...esito };
  await caricaModelli();                       // la pagina mostra la scelta vera, anche se la prova è fallita
  annuncia(esito.testo, esito.errore);
  aggiornaAvvio();
}

function esitoModello(chiave) {
  const e = stato.esitoModello;
  if (!e || e.chiave !== chiave) return null;
  return el("span", e.testo, "esito " + (e.errore ? "attenzione-testo" : e.attesa ? "nota" : "esito-ok"));
}

// interruttore accessibile (role=switch): l'azione riceve il nuovo stato; durante la richiesta resta fermo
function interruttore(etichetta, acceso, azione) {
  const b = el("button", null, "interruttore");
  b.type = "button";
  b.setAttribute("role", "switch");
  b.setAttribute("aria-checked", String(acceso));
  b.setAttribute("aria-label", etichetta);
  b.title = acceso ? "Acceso: clic per spegnere" : "Spento: clic per accendere";
  b.append(el("span", null, "levetta"));
  b.addEventListener("click", async () => {
    b.disabled = true;
    await azione(!acceso);
  });
  return b;
}

// fornitore (per id), chiave (per variabile) o profilo: l'esito resta accanto all'interruttore se non riesce
async function cambiaInterruttore(tipo, nome, acceso, etichetta) {
  let errore = "";
  try {
    await api("/api/interruttore", { tipo, nome, acceso });
  } catch (e) {
    errore = e.message;
  }
  stato.esitoInterruttore = errore ? { tipo, nome, testo: errore } : null;
  if (!errore) delete stato.elenchi[stato.fornitoreAperto];
  await caricaModelli(false);
  annuncia(errore || `${etichetta}: ${acceso ? "acceso" : "spento"}.`, Boolean(errore));
}

function esitoInterruttore(tipo, nome) {
  const e = stato.esitoInterruttore;
  return e && e.tipo === tipo && e.nome === nome ? el("span", e.testo, "esito attenzione-testo") : null;
}

// una riga per profilo: nome, misura, «Usa»; le altre azioni (prova, nome, togli) in un pannello che si apre
// sotto la riga, per non mettere quattro pulsanti su ogni modello
function rigaModello(p, unico, conInterruttori = false) {
  const li = el("li", null, "modello-voce" + (p.spento ? " spento" : ""));
  const inUso = p.nome === unico || p.in_uso_per.length > 0;
  const testa = el("div", null, "testa");
  testa.append(el("span", p.modello || p.nome, "nome"));
  if (p.modello && p.modello !== p.nome) testa.append(el("span", p.nome, "profilo"));
  li.append(testa);
  const misura = p.misurato && p.misurato !== "no";
  // «misurato»: la qualità del modello è stata provata con la valutazione su queste fonti. Solo allora la riga lo
  // dice: «non ancora provata» starebbe su quasi tutti i modelli e non aiuterebbe a scegliere
  if (misura) {
    const segnoMisura = el("span", "qualità provata su queste fonti", "misura si");
    segnoMisura.title = "La valutazione confronta le letture del modello con un campione controllato a mano.";
    li.append(segnoMisura);
  }
  const azione = el("div", null, "azione");
  const occupato = Boolean(stato.esitoModello && stato.esitoModello.attesa);
  if (conInterruttori) {
    azione.append(interruttore(`Modello ${p.modello || p.nome} acceso`, !p.spento,
      (acceso) => cambiaInterruttore("profilo", p.nome, acceso, p.modello || p.nome)));
  }
  if (p.nome === unico) {
    li.classList.add("in-uso");
    azione.append(el("span", "in uso", "segno ok"));
  } else if ((stato.fornitori || []).some((x) => x.id === p.fornitore.id && x.pronto === false)) {
    // il fornitore non risponde: il motivo al posto di un «Usa» che fallirebbe
    azione.append(el("span", "non risponde", "segno"));
  } else {
    const b = pulsante("Usa", () => usaModello(p.nome));
    const f = (stato.fornitori || []).find((x) => x.id === p.fornitore.id);
    b.disabled = occupato || Boolean(p.bloccato) || Boolean(f && f.pronto === false);   // fallirebbe comunque
    if (p.bloccato) b.title = "Non si può usare: " + p.bloccato;
    if (f && f.pronto === false) b.title = `${f.nome} non risponde`;
    // due profili dello stesso modello (due catene di un router) si distinguono per il nome del profilo
    b.setAttribute("aria-label", `Usa ${p.modello || p.nome} (${p.fornitore.nome}` +
      (p.modello && p.modello !== p.nome ? `, profilo ${p.nome})` : ")"));
    azione.append(b);
  }
  const aperto = stato.azioniProfilo === p.nome;
  const altro = el("button", null, "icona altro");
  altro.type = "button";
  altro.setAttribute("aria-label", "Altre azioni per " + p.nome);
  altro.setAttribute("aria-expanded", String(aperto));
  altro.title = "Prova, rinomina, togli";
  altro.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1"/><circle cx="12" ' +
    'cy="12" r="1"/><circle cx="19" cy="12" r="1"/></svg>';
  altro.addEventListener("click", () => {
    stato.azioniProfilo = aperto ? null : p.nome;
    stato.rinomina = null;
    ridisegnaModelli();
  });
  azione.append(altro);
  if (p.in_uso_per.length && !unico) li.append(el("span", "in uso per " + p.in_uso_per.join(", "), "ruoli-uso"));
  li.append(azione);
  if (aperto) li.append(pannelloProfilo(p, inUso));
  const e = esitoModello(p.nome) || esitoInterruttore("profilo", p.nome);
  if (e) li.append(e);
  return li;
}

function pannelloProfilo(p, inUso) {
  const d = el("div", null, "pannello-profilo");
  if (stato.rinomina === p.nome) {
    const id = "cfg-rinomina-" + p.nome.replace(/[^A-Za-z0-9-]/g, "-");
    const l = el("label", "Nuovo nome del profilo", "solo-lettori");
    l.htmlFor = id;
    const input = el("input");
    input.type = "text";
    input.id = id;
    input.value = p.nome;
    input.spellcheck = false;
    const salva = pulsante("Rinomina", () => rinominaProfilo(p.nome, input.value), true);
    const annulla = pulsante("Annulla", () => { stato.rinomina = null; ridisegnaModelli(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); salva.click(); }
      if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); annulla.click(); }
    });
    d.append(l, input, salva, annulla);
    setTimeout(() => { input.focus(); input.select(); }, 0);
    return d;
  }
  const prova = pulsante("Prova il collegamento", () => provaProfilo(p.nome));
  const rinomina = pulsante("Rinomina…", () => { stato.rinomina = p.nome; ridisegnaModelli(); });
  const togli = pulsante("Togli…", () => togliProfilo(p));
  togli.classList.add("pericolo");
  for (const b of [rinomina, togli]) {
    b.disabled = inUso;
    if (inUso) b.title = "In uso: scegli prima un altro modello";
  }
  d.append(prova, rinomina, togli);
  if (inUso) d.append(el("span", "Un modello in uso non si rinomina e non si toglie.", "nota"));
  return d;
}

function ridisegnaModelli() {
  disegnaModelli();
  disegnaFornitore();
}

async function provaProfilo(nome) {
  stato.esitoModello = { chiave: nome, testo: `Prova di collegamento con «${nome}»…`, attesa: true };
  ridisegnaModelli();
  let esito;
  try {
    const r = await api("/api/modello/prova", { nome });
    esito = r.riuscita ? { testo: "Collegamento riuscito." } :
      { testo: "Non risponde: " + (r.messaggi || []).slice(-2).join(" "), errore: true };
  } catch (e) {
    esito = { testo: e.message, errore: true };
  }
  stato.esitoModello = { chiave: nome, ...esito };
  ridisegnaModelli();
  annuncia(esito.testo, esito.errore);
}

async function rinominaProfilo(nome, nuovo) {
  try {
    const r = await api("/api/modello/rinomina", { nome, nuovo: nuovo.trim() });
    stato.rinomina = null;
    stato.azioniProfilo = r.profilo;
    stato.esitoModello = { chiave: r.profilo, testo: r.cambiato ? `Ora si chiama «${r.profilo}».` : "Nome invariato." };
  } catch (e) {
    stato.esitoModello = { chiave: nome, testo: e.message, errore: true };
  }
  await caricaModelli(false);
  annuncia(stato.esitoModello.testo, stato.esitoModello.errore);
}

async function togliProfilo(p) {
  const si = await conferma(`Togliere «${p.nome}»?`, `Il profilo di ${p.modello || p.nome} (${p.fornitore.nome}) ` +
    "esce da models.ini; prima si fa una copia del file. Le risposte già scritte con questo modello restano come " +
    "sono.", "Togli");
  if (!si) return;
  try {
    const r = await api("/api/modello/togli", { nome: p.nome });
    stato.azioniProfilo = null;
    annuncia((r.messaggi || []).join(" "));
  } catch (e) {
    stato.esitoModello = { chiave: p.nome, testo: e.message, errore: true };
  }
  await caricaModelli(false);
}

function elencoModelli(profili, unico, conInterruttori = false) {
  const ul = el("ul", null, "modelli-fornitore");
  ul.append(...profili.map((p) => rigaModello(p, unico, conInterruttori)));
  return ul;
}

// ridisegna un contenitore senza perdere il fuoco della tastiera (lo stesso controllo, per id o per nome)
function ridisegna(c, parti) {
  const a = document.activeElement;
  const segno = a && c.contains(a) ? a.id || a.getAttribute("aria-label") || a.textContent : null;
  c.replaceChildren(...parti);
  if (!segno) return;
  const dopo = $(segno) || [...c.querySelectorAll("button, select, input")].find((x) =>
    (x.getAttribute("aria-label") || x.textContent) === segno);
  if (dopo && !dopo.disabled) dopo.focus();
}

function sceltaPerRuolo() {
  const d = el("details", null, "riquadro per-ruolo");
  d.id = "cfg-per-ruolo";
  const unico = modelloUnico();
  d.open = !unico && Object.keys(stato.inUso || {}).length > 0;
  d.append(el("summary", "Un modello diverso per ruolo"));
  d.append(el("p", unico ? "Di solito basta un modello per tutto. Qui si può dare a un ruolo un modello diverso, " +
    "per esempio uno più economico per lo smistamento." :
    "I ruoli usano modelli diversi. «Usa» nell'elenco sopra sceglie un modello per tutti.", "nota"));
  for (const [ruolo, etichetta, compito] of RUOLI) {
    const riga = el("div", null, "riga-ruolo");
    const id = "cfg-ruolo-" + ruolo;
    const l = el("label", null);
    l.htmlFor = id;
    l.append(el("span", etichetta, "titolo"), el("span", compito, "nota"));
    const sel = el("select");
    sel.id = id;
    const attuale = (stato.inUso || {})[ruolo];
    for (const f of fornitoriAttivi().filter((x) => sceglibili(x).length)) {
      const og = el("optgroup");
      og.label = f.nome;
      for (const p of sceglibili(f)) {
        // due profili possono usare lo stesso modello (due catene di un router): il nome del profilo li distingue
        og.append(new Option(p.modello && p.modello !== p.nome ? `${p.modello} (${p.nome})` : p.nome, p.nome));
      }
      sel.append(og);
    }
    if (attuale && !profiloDi(attuale)) sel.append(new Option(attuale + " (non trovato)", attuale));
    sel.value = attuale || "";
    const b = pulsante("Usa", () => usaModello(sel.value, [ruolo]));
    b.setAttribute("aria-label", "Usa per " + etichetta.toLowerCase());
    const aggiorna = () => { b.disabled = !sel.value || sel.value === attuale ||
      Boolean(stato.esitoModello && stato.esitoModello.attesa); };
    sel.addEventListener("change", aggiorna);
    aggiorna();
    riga.append(l, sel, b);
    const e = esitoModello("ruolo:" + ruolo);
    if (e) riga.append(e);
    d.append(riga);
  }
  return d;
}

// pagina «Modelli»: i modelli dei fornitori attivi, per fornitore
function disegnaModelli() {
  const c = $("cfg-modelli");
  const ruoloAperto = $("cfg-per-ruolo") ? $("cfg-per-ruolo").open : null;
  const unico = modelloUnico();
  const gruppi = fornitoriAttivi().filter((f) => sceglibili(f).length);
  const parti = [];
  if (!gruppi.length) {
    const r = el("section", null, "riquadro");
    r.append(el("p", stato.notaModelli || "Nessun modello pronto. Apri un fornitore qui a sinistra: Ollama per i " +
      "modelli sul tuo computer, oppure un servizio online con la sua chiave.", "nota"));
    parti.push(r);
  }
  for (const f of gruppi) {
    const r = el("section", null, "riquadro fornitore");
    const h = el("h3", null, "con-logo");
    h.append(icona(f), el("span", f.nome));
    const apri = el("button", "Impostazioni del fornitore", "discreto");
    apri.type = "button";
    apri.setAttribute("aria-label", "Impostazioni di " + f.nome);
    apri.addEventListener("click", () => mostraSezione("fornitore", f.id));
    const testa = el("div", null, "cfg-testa");
    testa.append(h, apri);
    r.append(testa);
    // in rosso solo se un suo modello è in uso: un servizio facoltativo spento non è un guasto
    const inUso = f.profili.some((p) => p.in_uso_per && p.in_uso_per.length);
    if (f.pronto === false) r.append(el("p", SE_SPENTO[f.id] || `${f.nome} non risponde: i suoi modelli non funzionano finché ` +
      "non torna raggiungibile.", inUso ? "nota attenzione-testo" : "nota"));
    r.append(elencoModelli(sceglibili(f), unico));
    parti.push(r);
  }
  if (gruppi.length) {
    const r = sceltaPerRuolo();
    if (ruoloAperto !== null && unico) r.open = ruoloAperto;
    parti.push(r);
  }
  ridisegna(c, parti);
}

// quanto costa un fornitore: l'informazione che conta di più per scegliere il primo
const COSTI = { ollama: "gratuito", freellmapi: "gratuito", groq: "piano gratuito", "google-gemini": "piano gratuito",
  openrouter: "piano gratuito", mistral: "piano gratuito", "hugging-face": "piano gratuito",
  "nvidia-nim": "piano gratuito", anthropic: "a consumo", openai: "a consumo", xai: "a consumo", minimax: "a consumo" };

// elenco dei fornitori nella colonna delle Impostazioni: sul computer, poi online in ordine di nome. Il pallino
// verde vuol dire «pronto»: chiave presente e, per i servizi sul computer, programma che risponde
function disegnaFornitoriNav() {
  const voce = (f) => {
    const li = el("li");
    const b = el("button", null, "voce-barra fornitore-nav" + (f.pronto ? " pronto" : ""));
    b.type = "button";
    b.dataset.fornitore = f.id;
    const testo = el("span", null, "testo");
    testo.append(el("span", f.nome, "nome"));
    if (f.spento) testo.append(el("span", "spento", "costo"));
    else if (COSTI[f.id]) testo.append(el("span", COSTI[f.id], "costo"));
    b.append(icona(f), testo);
    b.append(el("span", null, "segno-pronto" + (f.pronto ? " si" : "")));
    b.append(el("span", f.pronto ? " (pronto)" : f.spento ? " (spento)" : f.chiave_spenta ? " (chiave spenta)" :
      !f.attivo ? " (senza chiave)" : f.pronto === null ?
      " (controllo in corso)" : " (non risponde)", "solo-lettori"));
    if (stato.sezione === "fornitore" && stato.fornitoreAperto === f.id) b.setAttribute("aria-current", "page");
    b.addEventListener("click", () => mostraSezione("fornitore", f.id));
    li.append(b);
    return li;
  };
  const tutti = stato.fornitori || [];
  ridisegna($("cfg-locali"), tutti.filter((f) => f.locale).map(voce));
  // online: in vista quelli già impostati (con la chiave, anche spenti) e quello aperto; gli altri, da attivare,
  // stanno sotto «Altri fornitori», che resta chiuso finché non serve
  const remoti = tutti.filter((f) => !f.locale).sort((a, b) => a.nome.localeCompare(b.nome));
  const impostato = (f) => f.attivo || f.spento || f.chiave_spenta || f.chiave === "presente" ||
    (stato.sezione === "fornitore" && stato.fornitoreAperto === f.id);
  const altri = remoti.filter((f) => !impostato(f));
  const righe = remoti.filter(impostato).map(voce);
  if (altri.length) {
    const li = el("li", null, "altri-fornitori");
    const d = el("details");
    d.open = Boolean(stato.altriFornitoriAperti);
    d.addEventListener("toggle", () => { stato.altriFornitoriAperti = d.open; });
    d.append(el("summary", `Altri fornitori (${altri.length})`, "voce-barra"));
    const ul = el("ul", null, "cfg-voci");
    ul.append(...altri.map(voce));
    d.append(ul);
    li.append(d);
    righe.push(li);
  }
  ridisegna($("cfg-remoti"), righe);
}

function impostazione(titolo, descrizione, controllo) {
  const d = el("div", null, "impostazione");
  d.append(el("span", titolo, "titolo"));
  if (descrizione) d.append(typeof descrizione === "string" ? el("span", descrizione, "descrizione") : descrizione);
  if (controllo) {
    const c = el("div", null, "controllo");
    c.append(...[].concat(controllo));
    d.append(c);
  }
  return d;
}

function riquadroChiave(f) {
  const r = el("section", null, "riquadro");
  r.setAttribute("aria-label", "Chiave");
  r.append(el("h3", "Chiave API"));
  const desc = f.chiave === "presente" ? `Impostata, nella variabile ${f.chiave_env}.` :
    `Manca: la variabile ${f.chiave_env} non è impostata. Con la chiave compaiono qui i modelli di ${f.nome}.`;
  const etichettaStato = f.spento ? "fornitore spento" : f.chiave_spenta ? "chiave spenta" :
    f.attivo ? "attivo" : "non attivo";
  r.append(impostazione("Stato", desc, el("span", etichettaStato, "stato-fornitore" + (f.attivo ? " si" : ""))));
  // per smettere di usare un fornitore basta il suo interruttore qui sopra: quello della chiave si mostra solo se
  // la chiave è già spenta (da prima, o da un altro fornitore con la stessa variabile), per poterla riaccendere
  if (f.chiave_spenta) {
    const riga = impostazione("Usa la chiave", f.chiave_spenta ?
      `Spenta: Pressmark la ignora e i modelli di ${f.nome} non si possono scegliere. Resta nella variabile ` +
      `${f.chiave_env}.` : `Pressmark usa la chiave di ${f.chiave_env}.`,
    interruttore(`Chiave ${f.chiave_env} accesa`, !f.chiave_spenta,
      (acceso) => cambiaInterruttore("chiave", f.chiave_env, acceso, "Chiave " + f.chiave_env)));
    const e = esitoInterruttore("chiave", f.chiave_env);
    if (e) riga.append(e);
    r.append(riga);
  }
  if (f.dove_chiave) {
    r.append(impostazione("Dove si crea", el("span", f.dove_chiave, "descrizione indirizzo"), null));
  }
  const modulo = el("form", null, "modulo-chiave");
  const id = "cfg-chiave-" + f.id.replace(/[^a-z0-9-]/gi, "-");
  const l = el("label", f.chiave === "presente" ? "Sostituisci la chiave" : "Chiave");
  l.htmlFor = id;
  const input = el("input");
  input.type = "password";
  input.id = id;
  input.autocomplete = "off";
  input.spellcheck = false;
  const conserva = el("input");
  conserva.type = "checkbox";
  conserva.checked = true;
  const lc = el("label", null, "casella");
  lc.append(conserva, " Conserva la chiave tra le sessioni (variabile dell'utente, mai nei file del progetto)");
  const b = el("button", f.chiave === "presente" ? "Sostituisci e prova" : "Salva e prova",
    f.attivo ? "" : "primario");
  b.type = "submit";
  const uscita = el("p", null, "nota esito-chiave");
  uscita.setAttribute("role", "status");
  const e = stato.esitoChiave;
  if (e && e.id === f.id) {
    uscita.textContent = e.testo;
    uscita.classList.toggle("attenzione-testo", Boolean(e.errore));
  }
  const riga = el("div", null, "riga");
  riga.append(input, b);
  modulo.append(l, riga, lc, uscita);
  modulo.addEventListener("submit", (ev) => { ev.preventDefault(); salvaChiave(f, input, conserva, uscita, b); });
  r.append(modulo);
  return r;
}

async function salvaChiave(f, input, conserva, uscita, b) {
  uscita.classList.remove("attenzione-testo");
  uscita.textContent = "Provo la chiave…";
  b.disabled = true;
  let r;
  try {
    r = await api("/api/chiave", { fornitore: f.id, chiave: input.value, conserva: conserva.checked });
  } catch (e) {
    r = { salvata: false, messaggi: [e.message] };
  }
  b.disabled = false;
  const testo = (r.messaggi || []).join(" ");
  if (!r.salvata) {                              // la chiave scritta resta nel campo, da correggere
    uscita.textContent = testo;
    uscita.classList.add("attenzione-testo");
    return;
  }
  stato.esitoChiave = { id: f.id, testo };
  delete stato.elenchi[f.id];                    // con la chiave nuova il servizio può elencare altri modelli
  await caricaModelli(false);
  annuncia(testo);
}

// stato di un servizio sul computer: risponde o no, e come rimediare
const SE_SPENTO = {
  ollama: "Ollama non risponde: non è installato o non è avviato. Si scarica da https://ollama.com; una volta " +
    "avviato, i modelli scaricati compaiono qui sotto.",
  freellmapi: "FreeLLMAPI non risponde: avvialo sul computer (app desktop o da sorgente) e controlla l'indirizzo.",
};

function riquadroCollegamento(f) {
  const r = el("section", null, "riquadro");
  r.setAttribute("aria-label", "Collegamento");
  r.append(el("h3", "Collegamento"));
  if (f.url) r.append(impostazione("Indirizzo", el("span", f.url, "descrizione indirizzo"), null));
  if (f.locale && f.attivo) {
    const ok = f.raggiungibile;
    const ricontrolla = pulsante("Controlla di nuovo", () => caricaModelli(false));
    ricontrolla.disabled = ok === null;
    r.append(impostazione("Stato", ok === null ? "Controllo in corso…" : ok ? "Risponde." :
      SE_SPENTO[f.id] || "Non risponde a questo indirizzo.",
    [el("span", ok === null ? "controllo…" : ok ? "pronto" : "non risponde", "stato-fornitore" + (ok ? " si" : "")),
      ricontrolla]));
  }
  if (!f.chiave_env) r.append(impostazione("Chiave", "Non serve.", null));
  return r;
}

// i modelli che il servizio offre, da aggiungere con un clic (Ollama: quelli scaricati). L'elenco si chiede al
// servizio quando la pagina si apre, una volta per fornitore e sessione
function servizioElenca(f) {
  return f.pronto && f.servizio_id !== "anthropic";
}

async function caricaElencoServizio(f, ricarica = false) {
  const voce = stato.elenchi[f.id];
  if (voce && !ricarica) return;
  if (f.id === "ollama") {
    stato.elenchi[f.id] = { modelli: f.installati, ok: true };
    return;
  }
  stato.elenchi[f.id] = { attesa: true, modelli: [] };
  try {
    const r = await api("/api/modello/elenco", { servizio: f.servizio_id, url: f.url });
    stato.elenchi[f.id] = { modelli: r.modelli || [], ok: r.raggiungibile !== false };
  } catch (e) {
    stato.elenchi[f.id] = { modelli: [], ok: false, errore: e.message };
  }
  if (stato.fornitoreAperto === f.id) disegnaFornitore();
}

const MOSTRATI = 30;

function riquadroElencoServizio(f) {
  const r = el("section", null, "riquadro elenco-servizio");
  r.setAttribute("aria-label", "Modelli offerti da " + f.nome);
  const testa = el("div", null, "cfg-testa");
  testa.append(el("h3", f.id === "ollama" ? "Modelli scaricati" : `Modelli offerti da ${f.nome}`));
  const voce = stato.elenchi[f.id] || { attesa: true, modelli: [] };
  if (f.id !== "ollama") testa.append(pulsante("Aggiorna", () => caricaElencoServizio(f, true)));
  r.append(testa);
  if (voce.attesa) {
    r.append(el("p", "Chiedo l'elenco al servizio…", "nota"));
    return r;
  }
  if (!voce.ok) {
    r.append(el("p", voce.errore || "Il servizio non ha dato l'elenco dei modelli: aggiungi il modello a mano.",
      "nota attenzione-testo"));
    return r;
  }
  if (!voce.modelli.length) {
    r.append(el("p", f.id === "ollama" ? "Nessun modello scaricato. Per scaricarne uno: ollama pull qwen3.5:9b" :
      "Il servizio non elenca modelli.", "nota"));
    return r;
  }
  const filtro = el("input");
  filtro.type = "search";
  filtro.id = "cfg-filtro-" + f.id.replace(/[^a-z0-9-]/gi, "-");
  filtro.placeholder = `filtra tra ${voce.modelli.length} modelli`;
  filtro.setAttribute("aria-label", "Filtra i modelli di " + f.nome);
  filtro.value = stato.filtroElenco[f.id] || "";
  const ul = el("ul", null, "modelli-fornitore elenco-offerti");
  const presenti = new Set(f.profili.map((p) => p.modello));
  const piede = el("p", null, "nota");
  const disegna = () => {
    const q = filtro.value.trim().toLowerCase();
    stato.filtroElenco[f.id] = filtro.value;
    const trovati = voce.modelli.filter((m) => m.toLowerCase().includes(q));
    const tutti = stato.elencoIntero[f.id];
    ul.replaceChildren(...trovati.slice(0, tutti ? undefined : MOSTRATI).map((m) => {
      const li = el("li", null, "modello-voce");
      li.append(el("span", m, "nome"));
      const azione = el("div", null, "azione");
      if (presenti.has(m)) {
        azione.append(el("span", "aggiunto", "segno ok"));
      } else {
        const b = pulsante("Aggiungi", () => aggiungiDaElenco(f, m, b));
        b.setAttribute("aria-label", "Aggiungi " + m);
        azione.append(b);
      }
      li.append(azione);
      const e = esitoModello("nuovo:" + m);
      if (e) li.append(e);
      return li;
    }));
    piede.replaceChildren();
    if (!trovati.length) piede.append("Nessun modello con questo nome.");
    else if (trovati.length > MOSTRATI && !tutti) {
      piede.append(`Ne vedi ${MOSTRATI} su ${trovati.length}. `,
        pulsante("Mostra tutti", () => { stato.elencoIntero[f.id] = true; disegna(); }));
    }
  };
  filtro.addEventListener("input", disegna);
  disegna();
  r.append(filtro, ul, piede);
  if (f.id === "ollama") r.append(el("p", "Altri modelli si scaricano dal terminale: ollama pull <nome>.", "nota"));
  return r;
}

// un profilo nuovo per il modello scelto dall'elenco: il sistema lo prova ma non lo mette in uso
async function aggiungiDaElenco(f, modello, b) {
  b.disabled = true;
  stato.esitoModello = { chiave: "nuovo:" + modello, testo: "Aggiungo e provo il collegamento…", attesa: true };
  disegnaFornitore();
  let esito;
  try {
    const r = await api("/api/modello/nuovo", { servizio: f.servizio_id, modello, url: f.url,
      chiave_env: f.chiave_env, usa: false });
    esito = r.riuscita ? { testo: `Aggiunto come «${r.profilo}»: ora è tra i modelli qui sopra.` } :
      { testo: `Aggiunto come «${r.profilo}», ma la prova non è riuscita: ` +
        (r.messaggi || []).slice(-2).join(" "), errore: true };
  } catch (e) {
    esito = { testo: e.message, errore: true };
  }
  stato.esitoModello = { chiave: "nuovo:" + modello, ...esito };
  await caricaModelli(false);
  annuncia(esito.testo, esito.errore);
}

// pagina di un fornitore: costo e descrizione, collegamento o chiave, i modelli in uso e quelli offerti; i modelli
// solo se il fornitore è attivo
function disegnaFornitore() {
  const c = $("cfg-fornitore");
  const f = (stato.fornitori || []).find((x) => x.id === stato.fornitoreAperto);
  if (!f) {
    c.replaceChildren();
    return;
  }
  const parti = [];
  const h = el("h2", null, "con-logo");
  h.append(icona(f), el("span", f.nome));
  if (COSTI[f.id]) h.append(el("span", COSTI[f.id], "stato-fornitore costo-titolo"));
  parti.push(h, el("p", DESCRIZIONI[f.id] || `Servizio compatibile OpenAI su ${f.nome}.`, "nota"));
  const acceso = el("section", null, "riquadro");
  acceso.setAttribute("aria-label", "Fornitore acceso o spento");
  const riga = impostazione("Usa questo fornitore", f.spento ?
    "Spento: i suoi modelli non compaiono nella scelta e non si possono usare. Chiave e profili restano salvati." :
    "I suoi modelli accesi si possono scegliere nella pagina Modelli.",
  interruttore(`Fornitore ${f.nome} acceso`, !f.spento,
    (acceso_) => cambiaInterruttore("fornitore", f.id, acceso_, f.nome)));
  const e = esitoInterruttore("fornitore", f.id);
  if (e) riga.append(e);
  acceso.append(riga);
  parti.push(acceso);
  if (f.chiave_env) parti.push(riquadroChiave(f));
  if (f.locale || !f.chiave_env) parti.push(riquadroCollegamento(f));
  // senza chiave i modelli non si mostrano; con la chiave sì, anche se fornitore o chiave sono spenti
  if (f.attivo || (f.chiave !== "assente" && f.profili.length)) {
    const r = el("section", null, "riquadro");
    r.setAttribute("aria-label", "Modelli di " + f.nome + " in Pressmark");
    r.append(el("h3", "Modelli in Pressmark"));
    if (!f.attivo) r.append(el("p", f.spento ? "Il fornitore è spento: questi modelli non si possono usare." :
      "La chiave è spenta: questi modelli non si possono usare.", "nota"));
    if (f.profili.length) {
      r.append(el("p", "L'interruttore di un modello lo toglie dalla scelta senza cancellarlo.", "nota"));
      r.append(elencoModelli(f.profili, modelloUnico(), true));
    }
    else r.append(el("p", servizioElenca(f) ? "Nessuno ancora: aggiungine uno dall'elenco qui sotto." :
      `Nessun modello di ${f.nome} ancora.`, "nota"));
    const piede = el("div", null, "riga piede-modelli");
    piede.append(pulsante(servizioElenca(f) ? "Aggiungi a mano…" : "Aggiungi modello…",
      () => apriAggiungiModello(f.servizio_id)));
    r.append(piede);
    parti.push(r);
  }
  if (servizioElenca(f)) {
    parti.push(riquadroElencoServizio(f));
    caricaElencoServizio(f);
  }
  ridisegna(c, parti);
}

// il menu della casella: solo i modelli disponibili (fornitore attivo e pronto, modello acceso), per fornitore; con
// ruoli che usano modelli diversi, o un modello in uso non più disponibile, la prima voce dice com'è adesso

function menuModelli(unico) {
  const sel = $("modello");
  // un menu aperto non si ricostruisce sotto il cursore: si rifà quando perde il fuoco
  if (document.activeElement === sel && !sel.disabled) {
    sel.addEventListener("blur", () => menuModelli(modelloUnico()), { once: true });
    return;
  }
  sel.replaceChildren();
  const gruppi = fornitoriAttivi().filter((f) => f.pronto !== false)
    .map((f) => [f, f.profili.filter((p) => !p.bloccato)]).filter(([, profili]) => profili.length);
  const disponibile = gruppi.some(([, profili]) => profili.some((p) => p.nome === unico));
  if (!unico) {
    sel.append(new Option(Object.keys(stato.inUso || {}).length ? "modelli diversi per ruolo" : "— nessun modello —",
      "", true, true));
  } else if (!disponibile) {
    sel.append(new Option(nomeModello(unico) + " (non disponibile)", unico, true, true));
  }
  for (const [f, profili] of gruppi) {
    const og = el("optgroup");
    og.label = f.nome;
    for (const p of profili) {
      // due profili possono usare lo stesso modello (due catene di un router): il nome del profilo li distingue
      // un nome di profilo fatto in automatico (fornitore-modello-2) non dice nulla: basta il numero
      const gemelli = profili.filter((x) => x.modello === p.modello);
      const automatico = /^[a-z0-9-]+-\d+$/.test(p.nome) || p.nome.startsWith(f.id + "-");
      const etichetta = gemelli.length < 2 ? p.modello || p.nome :
        automatico ? `${p.modello} · profilo ${gemelli.indexOf(p) + 1}` : `${p.modello} (${p.nome})`;
      const o = new Option(etichetta, p.nome, false, p.nome === unico);
      o.title = `${f.nome}: ${p.modello} · profilo ${p.nome}` +
        (p.misurato && p.misurato !== "no" ? " · misurato su queste fonti" : "");
      og.append(o);
    }
    sel.append(og);
  }
  sel.dataset.attuale = sel.value;
  sel.title = unico ? nomeModello(unico) : "";
}

// dal menu: «Usa» come nelle Impostazioni (prova di collegamento prima); se non riesce il menu torna alla scelta vera
async function sceltaModello() {
  const sel = $("modello");
  const scelto = sel.value;
  sel.value = sel.dataset.attuale;
  if (!scelto || scelto === modelloUnico()) return;
  sel.disabled = true;
  avviso(`Prova di collegamento con «${scelto}»…`);
  await usaModello(scelto);
  sel.disabled = false;
  // riuscito: lo dicono il menu e il pallino (e l'annuncio di usaModello); non riuscito: l'avviso resta
  const e = stato.esitoModello;
  if (e && e.chiave === scelto && e.errore) avviso(e.testo, true);
  else avviso("");
}

let servizi = [];
// servizio: la voce da proporre (dal gruppo di un fornitore senza chiave); dai pulsanti arriva l'evento del clic
async function apriAggiungiModello(servizio) {
  if (!servizi.length) {
    try { servizi = (await api("/api/servizi")).servizi; } catch (e) { avviso(e.message, true); return; }
    const s = $("am-servizio");
    for (const x of servizi) s.append(new Option(x.etichetta, x.id));
  }
  if (typeof servizio === "string" && servizi.some((x) => x.id === servizio)) $("am-servizio").value = servizio;
  $("am-messaggi").hidden = true;
  $("am-chiave").value = "";
  $("am-nome").value = "";
  scegliServizio();
  $("d-modello").showModal();
}

function scegliServizio() {
  const x = servizi.find((s) => s.id === $("am-servizio").value) || servizi[0];
  $("am-url").value = x.url || "";
  $("am-env").value = x.chiave_env || "";
  $("am-modello").value = x.modello || "";
  $("am-modelli").replaceChildren();
  $("am-dove").textContent = x.dove_chiave ? `La chiave si crea qui: ${x.dove_chiave}` : "";
  $("am-url-l").hidden = x.id === "anthropic";
  const conChiave = x.id !== "ollama";
  for (const id of ["am-env-l", "am-chiave-l", "am-salva-l"]) $(id).hidden = !conChiave;
}

async function elencaModelli() {
  const m = $("am-messaggi");
  try {
    const r = await api("/api/modello/elenco", { servizio: $("am-servizio").value, url: $("am-url").value,
      chiave: $("am-chiave").value });
    const d = $("am-modelli");
    d.replaceChildren(...r.modelli.map((n) => new Option(n, n)));
    m.textContent = r.raggiungibile === false ? "Il servizio non risponde o rifiuta la chiave." :
      r.modelli.length ? `${r.modelli.length} modelli: scegli dal campo «Modello».` : "Nessun modello elencato.";
    if (r.modelli.length && !r.modelli.includes($("am-modello").value)) $("am-modello").value = r.modelli[0];
  } catch (e) {
    m.textContent = e.message;
  }
  m.hidden = false;
}

async function aggiungiModello(evento) {
  evento.preventDefault();
  const m = $("am-messaggi");
  m.hidden = false;
  m.textContent = "Salvo il profilo e provo il collegamento…";
  $("am-aggiungi").disabled = true;
  try {
    const r = await api("/api/modello/nuovo", {
      servizio: $("am-servizio").value, modello: $("am-modello").value, nome: $("am-nome").value,
      url: $("am-url").value, chiave_env: $("am-env").value, chiave: $("am-chiave").value,
      salva_chiave: $("am-salva").checked });
    m.textContent = (r.messaggi || []).join("\n");
    $("am-chiave").value = "";
    await caricaModelli();
    if (r.cambiato) avviso(`Modello in uso: ${r.profilo}.`);
    aggiornaAvvio();
  } catch (e) {
    m.textContent = e.message;
  } finally {
    $("am-aggiungi").disabled = false;
  }
}

// ------------------------------------------------------------------ impostazioni
// Una pagina con le sezioni a sinistra (generale, modelli, lingue OCR, ambiente) e i fornitori dei modelli,
// ognuno con la sua pagina. La «Preparazione» è il primo riquadro della sezione Generale.
const SEGNI = { ok: "✓", manca: "✗", facoltativo: "–", info: "" };

function pulsante(testo, azione, primario) {
  const b = el("button", testo, primario ? "primario" : "");
  b.type = "button";
  b.addEventListener("click", azione);
  return b;
}

function apriImpostazioni(sezione = "generale", fornitore) {
  mostraVista("impostazioni");
  mostraSezione(sezione, fornitore);
  caricaModelli(false);                         // chiavi e profili possono essere cambiati da fuori
}

function mostraSezione(nome, fornitore) {
  stato.sezione = nome;
  if (fornitore) stato.fornitoreAperto = fornitore;
  ricorda("sezione", nome === "fornitore" ? "fornitore:" + stato.fornitoreAperto : nome);
  for (const s of document.querySelectorAll(".cfg-sezione")) s.hidden = s.dataset.sezione !== nome;
  for (const b of document.querySelectorAll(".cfg-nav [data-sezione]")) {
    if (b.dataset.sezione === nome) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  }
  for (const b of document.querySelectorAll(".cfg-nav [data-fornitore]")) {
    if (nome === "fornitore" && b.dataset.fornitore === stato.fornitoreAperto) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  }
  $("cfg-contenuto").scrollTop = 0;
  if (nome === "generale") caricaAvvio();
  else if (nome === "modelli") disegnaModelli();
  else if (nome === "fornitore") disegnaFornitore();
  else if (nome === "ocr") caricaLingue();
  else if (nome === "ambiente") caricaAmbiente();
}

// dalla barra e da Ctrl+,: l'ultima sezione vista (un fornitore solo se c'è ancora)
function apriImpostazioniRicordate() {
  const r = ricordato("sezione");
  const sezioni = ["generale", "modelli", "ocr", "ambiente"];
  if (r.startsWith("fornitore:") && (stato.fornitori || []).some((f) => f.id === r.slice(10))) {
    apriImpostazioni("fornitore", r.slice(10));
  } else {
    apriImpostazioni(sezioni.includes(r) ? r : "generale");
  }
}

// dopo un passo fatto da un dialogo (progetto, modello) la pagina mostra lo stato nuovo
function aggiornaAvvio() {
  if (!$("vista-impostazioni").hidden && stato.sezione === "generale") caricaAvvio();
}

async function caricaAvvio() {
  let r;
  try {
    r = await api("/api/avvio");
  } catch (e) {
    $("av-intro").textContent = e.message;
    return r;
  }
  $("av-intro").textContent = r.completo ?
    "Tutto il necessario è pronto: puoi cercare. I passi facoltativi si fanno quando vuoi." :
    "Prima di cercare servono un progetto e un modello. Ogni passo si fa da qui, senza terminale.";
  const azioni = {
    // con un progetto già pronto il pulsante sta solo nel riquadro Progetti, qui sopra
    progetto: (p) => (p.fatto ? [] : [pulsante("Nuovo progetto…", apriNuovoProgetto, true)]),
    modello: (p) => [pulsante(p.fatto ? "Cambia…" : "Scegli…", () => mostraSezione("modelli"), !p.fatto)],
    fonti: () => [pulsante("Importa…", () => mostraVista("importazioni"))],
  };
  const progettoFatto = r.passi.find((p) => p.id === "progetto").fatto;
  ridisegna($("av-passi"), r.passi.map((p) => {
    const li = el("li");
    const segno = p.fatto ? "ok" : p.facoltativo ? "facoltativo" : "manca";
    li.append(el("span", p.fatto ? "✓" : p.facoltativo ? "○" : "●", "segno " + segno),
      el("span", p.titolo + (p.facoltativo ? " (facoltativo)" : ""), "titolo"));
    const a = el("div", null, "azioni");
    // il modello e le fonti appartengono a un progetto: senza progetto si comincia da quello
    if (progettoFatto || p.id === "progetto") a.append(...azioni[p.id](p));
    li.append(a, el("span", p.dettaglio, "dettaglio"));
    return li;
  }));
  return r;
}

async function caricaAmbiente() {
  const d = $("av-controlli");
  d.replaceChildren(el("p", "Controllo in corso (anche il collegamento al modello)…", "nota"));
  let r;
  try {
    r = await api("/api/ambiente");
  } catch (e) {
    d.replaceChildren(el("p", e.message, "nota attenzione-testo"));
    return;
  }
  const parti = [];
  for (const g of r.gruppi) {
    parti.push(el("h3", g.titolo));
    for (const v of g.voci) {
      const riga = el("div", null, "voce-ambiente");
      riga.append(el("span", SEGNI[v.stato] || "", v.stato), el("span", v.voce), el("span", v.dettaglio, "d"));
      if (v.azione === "progetto") riga.append(pulsante("Nuovo progetto…", apriNuovoProgetto));
      if (v.azione === "modello") riga.append(pulsante("Scegli il modello…", () => mostraSezione("modelli")));
      parti.push(riga);
    }
  }
  parti.unshift(el("p", r.mancano.length ? "Manca: " + r.mancano.join(", ") + "." :
    "Niente di necessario manca. I segni «–» indicano parti facoltative.", "nota"));
  d.replaceChildren(...parti);
  $("av-posizioni").textContent = r.posizioni.join(" · ");
}

async function caricaLingue(dopo) {
  const d = $("av-lingue");
  let s;
  try {
    s = dopo || await api("/api/lingue");
  } catch (e) {
    d.replaceChildren(el("p", e.message, "nota attenzione-testo"));
    return;
  }
  if (!s.tesseract) {
    d.replaceChildren(el("p", "Tesseract non trovato: senza, le scansioni non si importano.", "nota"));
    mostra("av-aggiungi", false);                  // senza Tesseract non c'è niente da installare
    return;
  }
  mostra("av-aggiungi", true);
  // una riga per lingua installata o richiesta dalle serie: codice, nome per esteso, se serve, se c'è
  const nomi = s.nomi || {};
  const richieste = new Set(s.richieste);
  const installate = new Set(s.installate);
  const parti = [];
  const sopra = el("div", null, "riga");
  if (s.mancanti.length) {
    sopra.append(el("span", "Mancano per le serie del progetto: " +
      s.mancanti.map((c) => `${nomi[c] || c} (${c})`).join(", "), "attenzione-testo"));
    if (s.scrivibile) sopra.append(pulsante("Scarica le mancanti", () => scaricaLingue(s.mancanti), true));
  } else {
    sopra.append(el("span", "Ci sono tutte le lingue richieste dalle serie del progetto.", "segno ok"));
  }
  parti.push(sopra);
  const tab = el("table", null, "tabella-lingue");
  const testa = el("tr");
  for (const [testo, classe] of [["Codice", ""], ["Lingua", ""], ["Per le serie", ""], ["Stato", "stato"]]) {
    const th = el("th", testo, classe);
    th.scope = "col";
    testa.append(th);
  }
  const thead = el("thead");
  thead.append(testa);
  const tbody = el("tbody");
  for (const c of [...new Set([...installate, ...richieste])].sort()) {
    const tr = el("tr", null, installate.has(c) ? "" : "manca");
    const codice = el("td");
    codice.append(el("code", c));
    const uso = c === "osd" ? "sempre (orientamento)" : richieste.has(c) ? "richiesta" : "";
    const st = el("td", null, "stato");
    if (installate.has(c)) st.append(el("span", "installata", "segno ok"));
    else {
      st.append(el("span", "manca", "attenzione-testo"));
      if (s.scrivibile) {
        const b = pulsante("Scarica", () => scaricaLingue([c]));
        b.setAttribute("aria-label", `Scarica ${nomi[c] || c}`);
        st.append(" ", b);
      }
    }
    tr.append(codice, el("td", nomi[c] || "—"), el("td", uso, "nota"), st);
    tbody.append(tr);
  }
  tab.append(thead, tbody);
  parti.push(tab);
  d.replaceChildren(...parti);
  // installare: tutte le lingue che mancano, per nome; se la cartella chiede l'amministratore, la proposta di una
  // cartella propria (le lingue installate si copiano, Tesseract resta com'è)
  const sel = $("av-lingua");
  const prima = sel.value;
  sel.replaceChildren(...s.proposte.slice().sort((a, b) => (nomi[a] || a).localeCompare(nomi[b] || b, "it"))
    .map((c) => new Option(nomi[c] ? `${nomi[c]} (${c})` : c, c)));
  if (s.proposte.includes(prima)) sel.value = prima;
  $("av-lingue-dove").textContent = s.cartella || "";
  mostra("av-lingue-scarica", s.scrivibile && s.proposte.length > 0);
  const propria = $("av-lingue-propria");
  propria.replaceChildren();
  if (!s.scrivibile) {
    propria.append(el("p", `Tesseract tiene le lingue in ${s.cartella}, dove servono i diritti di amministratore.`,
      "nota"));
    if (!s.propria) {
      propria.append(el("p", `Pressmark può usare una cartella delle lingue tua, ${s.cartella_utente}: ci copia le ` +
        `${s.installate.length} lingue già installate (circa ${s.dimensione_mb} MB) e da lì installa le nuove. ` +
        "Tesseract resta com'è."), pulsante("Usa una cartella mia…", () => cartellaLinguePropria(s), true));
    } else {
      propria.append(el("p", "Neanche la cartella indicata in config.ini ([ocr] modelli) si può scrivere: " +
        "controllane i permessi.", "attenzione-testo"));
    }
  }
  mostra("av-lingue-propria", !s.scrivibile);
}

async function cartellaLinguePropria(s) {
  const si = await conferma("Usare una cartella delle lingue tua?", `Copio ${s.installate.length} modelli ` +
    `(circa ${s.dimensione_mb} MB) da ${s.cartella} in ${s.cartella_utente} e lo scrivo in config.ini ` +
    "([ocr] modelli, con una copia di sicurezza). Da lì si installano le lingue nuove.", "Copia e usa");
  if (!si) return;
  const st = $("av-lingue-stato");
  for (const b of document.querySelectorAll("#av-lingue-propria button")) b.disabled = true;
  st.textContent = "Copio i modelli…";
  try {
    const r = await api("/api/lingue/cartella", {});
    st.textContent = (r.messaggi || []).slice(-1).join(" ");
    await caricaLingue(r);
  } catch (e) {
    st.textContent = e.message;
    for (const b of document.querySelectorAll("#av-lingue-propria button")) b.disabled = false;
  }
}

async function scaricaLingue(codici) {
  const st = $("av-lingue-stato");
  for (const b of document.querySelectorAll("#av-lingue button, #av-lingua-scarica, #av-lingua")) b.disabled = true;
  let ultimo = null;
  try {
    for (const c of codici) {
      st.textContent = `Scarico ${c} (i modelli grandi, come chi_sim, pesano decine di MB: può volerci qualche minuto)…`;
      ultimo = await api("/api/lingue", { codice: c });
      st.textContent = `${c}: scaricata (${ultimo.dimensione_mb} MB).`;
    }
  } catch (e) {
    st.textContent = e.message;
  } finally {
    for (const b of document.querySelectorAll("#av-lingue button, #av-lingua-scarica, #av-lingua")) b.disabled = false;
    await caricaLingue(ultimo);
  }
}

// azioni costose o che non si annullano: un dialogo con Annulla in evidenza come uscita (Esc chiude)
function conferma(titolo, testo, azione) {
  const d = $("d-conferma");
  $("cf-titolo").textContent = titolo;
  $("cf-testo").textContent = testo;
  $("cf-si").textContent = azione;
  d.returnValue = "";
  d.showModal();
  return new Promise((risolvi) => d.addEventListener("close", () => risolvi(d.returnValue === "si"), { once: true }));
}

// l'ultima cartella importata: solo una comodità di questo browser, se la memoria locale c'è
function ricorda(chiave, valore) {
  try { localStorage.setItem("pressmark." + chiave, valore); } catch (e) { /* memoria non disponibile */ }
}

function ricordato(chiave) {
  try {   // anche la chiave col nome di prima (airchivist.), salvata prima del cambio di nome
    return localStorage.getItem("pressmark." + chiave) || localStorage.getItem("airchivist." + chiave) || "";
  } catch (e) { return ""; }
}

async function sfogliaCartella() {
  try {
    const r = await api("/api/scegli-cartella", {});
    if (r.percorso) $("imp-cartella").value = r.percorso;
  } catch (e) {
    avviso(e.message, true);
  }
  $("imp-cartella").focus();
}

// ------------------------------------------------------------------ il filo della ricerca
// Una sola casella: il testo si confronta con le schede delle entità. Un nome riconosciuto avvia il percorso
// guidato (forme del nome, riepilogo, ricerca, risposta) come messaggi del filo; se il nome non è chiaro il sistema
// chiede «Di chi parli?»; dopo una risposta, una domanda che non nomina un'altra entità va alla conversazione con il
// modello (gli stessi strumenti del motore), nello stesso filo.
async function caricaFonti() {
  const f = $("fonti");
  f.querySelectorAll("label").forEach((x) => x.remove());
  try {
    for (const nome of (await api("/api/fonti")).fonti) {
      const l = el("label");
      const c = document.createElement("input");
      c.type = "checkbox";
      c.value = nome;
      l.append(c, document.createTextNode(nome));
      f.append(l);
    }
  } catch (e) { /* senza progetto: nessuna fonte */ }
  riassumiFiltri();
}

function filtriScelti() {
  return { dal: $("dal").value.trim(), al: $("al").value.trim(), evoluzione: $("evoluzione").checked,
    fonti: [...$("fonti").querySelectorAll("input:checked")].map((c) => c.value) };
}

// i filtri attivi, come etichetta accanto al pulsante: si vedono senza aprire il riquadro
function descriviFiltri(f) {
  if (!f) return "";
  const parti = [];
  if (f.dal || f.al) parti.push(`${f.dal || "…"}–${f.al || "…"}`);
  const fonti = f.fonti || [];
  if (fonti.length) parti.push(fonti.length === 1 ? fonti[0] : `${fonti.length} serie`);
  if (f.evoluzione) parti.push("evoluzione");
  return parti.join(" · ");
}

function riassumiFiltri() {
  $("filtri-riassunto").textContent = descriviFiltri(filtriScelti());
  if (stato.aggiornaRiepilogo) stato.aggiornaRiepilogo();     // il riepilogo della scheda aperta segue i filtri
}

function alternaFiltri() {
  const aperto = $("filtri").hidden;
  mostra("filtri", aperto);
  $("b-filtri").setAttribute("aria-expanded", String(aperto));
  if (aperto) $("dal").focus();
}

// il costo del modello in uso, dal suo fornitore (gratuito, piano gratuito, a consumo); null con modelli per ruolo
function costoModello() {
  const p = modelloUnico() && profiloDi(modelloUnico());
  return p ? { fornitore: p.fornitore.nome, costo: COSTI[p.fornitore.id] || "" } : null;
}

function notaCosto(c) {
  const base = "Il modello legge ogni passaggio trovato: più righe, più tempo.";
  if (!c || !c.costo) return base + " Con un servizio a pagamento, anche più costo.";
  if (c.costo === "gratuito") return `${base} Con ${c.fornitore} non si paga nulla.`;
  if (c.costo === "piano gratuito") return `${base} Rientra nel piano gratuito di ${c.fornitore}: se le quote ` +
    "finiscono, la ricerca aspetta e riprende da sola.";
  return `${base} ${c.fornitore} si paga a consumo: ogni passaggio letto ha un costo.`;
}

// le righe delle forme con i filtri scelti: una domanda per combinazione, ricordata (le caselle si spuntano spesso)
const contiRighe = new Map();
function contaRighe(varianti) {
  const f = filtriScelti();
  const chiave = JSON.stringify([[...varianti].sort(), f.dal, f.al, [...f.fonti].sort()]);
  if (!contiRighe.has(chiave)) {
    const p = api("/api/righe", { varianti, dal: f.dal, al: f.al, fonti: f.fonti });
    p.catch(() => contiRighe.delete(chiave));
    contiRighe.set(chiave, p);
  }
  return contiRighe.get(chiave);
}

// i fornitori a consumo tra i modelli in uso (anche con un modello diverso per ruolo): per loro l'avvio si conferma
function fornitoriAConsumo() {
  const nomi = new Set();
  for (const nome of new Set(Object.values(stato.inUso || {}))) {
    const p = profiloDi(nome);
    if (p && COSTI[p.fornitore.id] === "a consumo") nomi.add(p.fornitore.nome);
  }
  return [...nomi];
}

// le ricerche già fatte su un'entità e il ritmo del progetto (da /api/precedenti); si richiede dopo ogni ricerca
const precedentiDi = new Map();
function precedenti(entita) {
  if (!precedentiDi.has(entita)) {
    const p = api("/api/precedenti", { entita });
    p.catch(() => precedentiDi.delete(entita));
    precedentiDi.set(entita, p);
  }
  return precedentiDi.get(entita);
}

function quandoBreve(iso) {
  const d = new Date(iso);
  if (isNaN(d)) return "";
  return d.toLocaleDateString(LOCALE, { day: "numeric", month: "short" }) + " alle " +
    d.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" });
}

// la durata attesa: i passaggi nuovi (righe meno quelli già letti) al ritmo delle ricerche passate; senza passaggi
// nuovi resta la sintesi, che dura più o meno come l'ultima volta
function stimaDurata(righe, p) {
  if (!p || !p.minuti_per_passaggio) return "";
  const nuovi = Math.max(0, righe - (p.letti || 0));
  let min = Math.round(nuovi * p.minuti_per_passaggio);
  if (p.ultima) min = Math.max(min, nuovi ? 0 : p.ultima.minuti);
  min = Math.max(1, min);
  return `circa ${min < 60 ? min + " min" : Math.round(min / 6) / 10 + " ore"}, dalle ricerche passate del progetto`;
}

// riepilogo prima di avviare: cosa cerca, dove, con quale modello, su quante righe, quanto dura e a che costo. Le
// forme si vedono già sopra (etichette). opz.varianti: le forme da contare; opz.entita: per le ricerche precedenti;
// opz.alConto(n, precedenti): per il pulsante che dice la portata e per la conferma
function riepilogo(domanda, opz = {}) {
  const f = filtriScelti();
  const dl = el("dl", null, "riepilogo");
  const c = costoModello();
  const voci = [
    ...(domanda ? [["Domanda", domanda]] : []),
    ["Periodo", f.dal || f.al ? `${f.dal || "…"}–${f.al || "…"}` : "tutto"],
    ["Serie", f.fonti.length ? f.fonti.join("; ") : "tutte"],
    ["Modello", modelloUnico() ? nomeModello(modelloUnico()) : "modelli diversi per ruolo"],
  ];
  if (c && c.costo) voci.push(["Costo", c.costo]);
  if (f.evoluzione) voci.push(["Modo", "evoluzione anno per anno"]);
  for (const [k, v] of voci) dl.append(el("dt", k), el("dd", v));
  const box = el("div", null, "riepilogo-box");
  box.append(dl, el("p", notaCosto(c), "nota"));
  if (!opz.varianti) return box;
  const dd = el("dd", "conto le righe…", "in-attesa");
  dl.append(el("dt", "Nelle fonti"), dd);
  const turno = stato.turnoConto = (stato.turnoConto || 0) + 1;    // conta solo l'ultimo riepilogo chiesto
  const prec = opz.entita ? precedenti(opz.entita).catch(() => null) : Promise.resolve(null);
  const mostraConto = async (n) => {
    dd.classList.remove("in-attesa");
    dd.textContent = n === 1 ? "1 riga con queste forme" : `${n} righe con queste forme`;
    const p = await prec;
    if (p && p.letti) dl.append(el("dt", "Già letti"), el("dd", `${p.letti} passaggi di ricerche precedenti: si riusano`));
    if (p && p.ultima) dl.append(el("dt", "Ultima ricerca"), el("dd", `${quandoBreve(p.ultima.quando)}, durata ${p.ultima.minuti} min`));
    const durata = stimaDurata(n, p);
    if (durata) dl.append(el("dt", "Durata"), el("dd", durata));
    const richieste = stimaRichieste(n, p);
    if (richieste) dl.append(el("dt", "Richieste"), el("dd", richieste));
    if (opz.alConto && turno === stato.turnoConto) opz.alConto(n, p);
  };
  if (!opz.varianti.length) { mostraConto(0); return box; }
  contaRighe(opz.varianti).then((r) => {
    if (r.righe === null || r.righe === undefined) { dd.classList.remove("in-attesa"); dd.textContent = r.nota || "non contate"; return; }
    mostraConto(r.righe);
  }, () => { dd.classList.remove("in-attesa"); dd.textContent = "conto non riuscito"; });
  return box;
}

// prima di creare una scheda: solo ciò che si crea (le forme e le righe che le contengono), non la ricerca dopo
function riepilogoScheda(varianti, ambigue, righe, tipo) {
  const dl = el("dl", null, "riepilogo");
  const voci = [
    ["Forme", varianti.length ? varianti.join("; ") : "nessuna spuntata"],
    ...(ambigue.length ? [["Ambigue", ambigue.join("; ")]] : []),
    ["Tipo", tipo],
    ["Nelle fonti", varianti.length > 1 ? `circa ${righe} righe (una riga con due forme conta due volte)` :
      `${righe} righe`],
  ];
  for (const [k, v] of voci) dl.append(el("dt", k), el("dd", v));
  const box = el("div", null, "riepilogo-box");
  box.append(dl, el("p", "La scheda entra nel glossario. La ricerca si avvia nel passo dopo, con il suo riepilogo.",
    "nota"));
  return box;
}

// il pulsante dice su quante righe parte la ricerca
function portata(b, testo, n) {
  b.textContent = n ? `${testo} su ${n === 1 ? "1 riga" : n + " righe"}` : testo;
}

// una scheda decisa che non serve più rileggere (scartata, sostituita): resta una riga che dice che cosa è successo
function riduciScheda(m, testo) {
  m.replaceChildren(el("p", testo, "traccia"));
  m.classList.add("decisa", "ridotta");
}

// --------------------------------------------- messaggi
function messaggio(ruolo, ...figli) {
  const m = el("div", null, "msg " + ruolo);
  m.append(...figli);
  $("messaggi").append(m);
  mostra("vuoto", false);
  scorriInFondo();
  return m;
}

function scorriInFondo() {
  const t = $("vista-thread");
  requestAnimationFrame(() => { t.scrollTop = t.scrollHeight; });
}

function pulsanteMsg(testo, azione, classe) {
  const b = el("button", testo, classe || "");
  b.type = "button";
  b.addEventListener("click", azione);
  return b;
}

// una scheda già decisa non si usa più: i suoi pulsanti si spengono, la scelta resta leggibile
function chiudiScheda(m) {
  m.querySelectorAll("button, input, select").forEach((x) => { x.disabled = true; });
  m.classList.add("decisa");
}

function nuovoThread() {
  $("messaggi").replaceChildren();
  mostra("vuoto", true);
  nascondiAnteprima();
  stato.thread = null;
  stato.attesaChi = null;
  stato.aggiornaRiepilogo = null;
  stato.convNuova = true;                       // stato.ricercaEl resta: una ricerca in corso finisce da sé
  stato.doc = null;
  segnaCorrente(() => false);
  $("testo").placeholder = "Fai una domanda sulle fonti, o scrivi un nome";
  mostraVista("thread");
  avviso("");
  $("testo").focus();
}

function autoAltezza() {
  const t = $("testo");
  t.style.height = "auto";
  t.style.height = Math.min(t.scrollHeight, 200) + "px";
}

// --------------------------------------------- riconoscere l'entità
function normalizza(t) { return (t || "").normalize("NFD").replace(/\p{M}/gu, "").toLowerCase(); }

function contiene(testo, forma) {
  if (/[　-鿿가-힯]/.test(forma)) return testo.includes(forma);   // CJK: niente confini di parola
  const f = forma.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  return new RegExp(`(^|[^\\p{L}\\p{N}])${f}($|[^\\p{L}\\p{N}])`, "u").test(testo);
}

// le schede il cui nome o una cui forma compare nel testo (forme di almeno tre caratteri)
function trovaEntita(testo) {
  const t = normalizza(testo);
  const trovate = [];
  for (const s of (stato.glossario && stato.glossario.schede) || []) {
    const forme = [s.nome, ...String(s.campi.varianti || "").split(/[;\n]/)].map((x) => x.trim()).filter((x) => x.length >= 3);
    if (forme.some((f) => contiene(t, normalizza(f)))) trovate.push(s.nome);
  }
  return trovate;
}

function sembraNome(testo) { return !/[?¿]/.test(testo) && testo.split(/\s+/).length <= 5; }

async function invia(e) {
  if (e) e.preventDefault();
  const testo = $("testo").value.trim();
  if (!testo || stato.inCorso) return;
  $("testo").value = "";
  autoAltezza();
  mostraVista("thread");
  if (stato.attesaChi) {                         // la risposta a «Di chi parli?»
    const prosegui = stato.attesaChi;
    stato.attesaChi = null;
    $("testo").placeholder = "Fai una domanda sulle fonti, o scrivi un nome";
    messaggio("utente", el("p", testo));
    registra(filoCorrente(), { tipo: "utente", testo });
    return prosegui(testo);
  }
  await caricaGlossario();
  const trovate = trovaEntita(testo);
  const t = stato.thread;
  if (t && t.risposta && (!trovate.length || (trovate.length === 1 && trovate[0] === t.entita))) {
    return seguito(testo);
  }
  if (t && (t.risposta || t.avviata)) nuovoThread();
  messaggio("utente", el("p", testo));
  registra(filoCorrente(), { tipo: "utente", testo });
  if (trovate.length === 1) return formeDelNome(trovate[0], testo);
  if (trovate.length > 1) return chiediChi(testo, trovate);
  if (sembraNome(testo)) return formeDelNome(testo, testo);
  return chiediChi(testo, []);
}

function chiediChi(testo, candidati) {
  const m = messaggio("assistente scheda");
  m.append(el("p", candidati.length ? "Di chi parli? Più schede corrispondono." :
    "Di chi o di che cosa cerchi le menzioni? Scrivi il nome qui sotto."));
  const scelte = el("div", null, "chip-riga");
  for (const nome of candidati) {
    scelte.append(pulsanteMsg(nome, () => {
      riduciScheda(m, `Scheda scelta: «${nome}».`);
      stato.attesaChi = null;
      formeDelNome(nome, testo);
    }, "chip"));
  }
  const libera = pulsanteMsg("Fai la domanda al modello, senza scegliere una scheda", () => {
    riduciScheda(m, "Domanda al modello, senza una scheda.");
    stato.attesaChi = null;
    seguito(testo, true);
  }, "discreto");
  m.append(scelte, libera);
  stato.attesaChi = (nome) => { riduciScheda(m, `Cerco «${nome}».`); return formeDelNome(nome, testo); };
  $("testo").placeholder = "Il nome della persona, del partito, della testata…";
  annuncia("Di chi parli? Scegli una scheda o scrivi il nome.");
  $("testo").focus();
}

function domandaDi(testo, entita) { return normalizza(testo) === normalizza(entita) ? "" : testo; }

// passo 2: le forme del nome, da una scheda esistente o cercandole nelle fonti
async function formeDelNome(entita, testo) {
  const domanda = domandaDi(testo, entita);
  Object.assign(filoCorrente(), { entita, domanda });     // il filo resta, con i suoi messaggi
  let r;
  try {
    r = await api("/api/entita", { nome: entita });
  } catch (e) {
    const m = messaggio("assistente errore", el("p", e.message));
    m.append(pulsanteMsg("Riprova", () => { m.remove(); formeDelNome(entita, testo); }, "discreto"));
    return;
  }
  if (!r.schede.length) return esploraForme(entita, domanda);
  const m = messaggio("assistente scheda");
  const scelta = { scheda: r.schede[0] };
  const sommario = el("div");
  const forme = el("div", null, "chip-riga");
  const conto = { righe: null, precedenti: null };
  const aggiorna = () => {
    forme.replaceChildren(...scelta.scheda.varianti.map((v) => el("span", v, "chip statico")));
    portata(avvia, "Avvia la ricerca");
    conto.righe = null;
    sommario.replaceChildren(riepilogo(domanda, { varianti: scelta.scheda.varianti, entita: scelta.scheda.nome,
      alConto: (n, p) => { Object.assign(conto, { righe: n, precedenti: p }); portata(avvia, "Avvia la ricerca", n); } }));
  };
  m.append(el("p", r.schede.length > 1 ? "Più schede corrispondono: scegli quella giusta." :
    `Cerco «${r.schede[0].nome}» in queste forme del nome:`));
  if (r.schede.length > 1) {
    const gruppo = el("div", null, "scelte-scheda");
    r.schede.forEach((s, i) => {
      const l = el("label", null, "casella scelta-scheda");
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "scheda-" + Date.now();
      radio.checked = i === 0;
      radio.addEventListener("change", () => { scelta.scheda = s; aggiorna(); });
      l.append(radio, document.createTextNode(`${s.nome}${s.tipo ? " (" + s.tipo + ")" : ""}`));
      gruppo.append(l);
    });
    m.append(gruppo);
  }
  const avvia = pulsanteMsg("Avvia la ricerca", async () => {
    // con un servizio a consumo l'avvio costa: si conferma, dicendo quanto lavoro aspetta il modello
    const aConsumo = fornitoriAConsumo();
    if (aConsumo.length) {
      const letti = (conto.precedenti && conto.precedenti.letti) || 0;
      const portata_ = conto.righe === null ? "le righe con queste forme" :
        `${conto.righe} righe con queste forme` + (letti ? `, di cui circa ${letti} già lette che si riusano` : "");
      if (!await conferma(`Avviare la ricerca con ${aConsumo.join(" e ")}?`, `${aConsumo.join(" e ")} si paga a ` +
        `consumo: il modello legge ${portata_}, e ogni passaggio letto ha un costo.`, "Avvia la ricerca")) return;
    }
    chiudiScheda(m);
    avviaRicerca(scelta.scheda.nome, domanda);
  }, "primario");
  m.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.type === "radio") avvia.click(); });
  const altra = pulsanteMsg("È un omonimo: cerca altre forme", () => {
    const scartata = scelta.scheda.nome;
    riduciScheda(m, `Scheda «${scartata}» scartata: cerco altre forme nelle fonti.`);
    const nuova = esploraForme(entita, domanda, scartata);
    // ripensamento: la scheda scartata torna com'era, e la ricerca delle forme si toglie
    m.querySelector(".traccia").append(" ", pulsanteMsg("Era quella giusta", () => {
      nuova.remove();
      m.remove();
      formeDelNome(entita, testo);
    }, "discreto"));
  }, "discreto");
  aggiorna();
  stato.aggiornaRiepilogo = () => { if (!m.classList.contains("decisa")) aggiorna(); };
  const azioni = el("div", null, "riga");
  azioni.append(avvia, altra);
  m.append(forme, sommario, azioni);
  annuncia("Forme del nome pronte: controlla il riepilogo e avvia la ricerca.");
  scorriInFondo();
}

// scartata: il nome della scheda che l'utente ha detto non essere quella giusta (un omonimo, di solito)
function esploraForme(entita, domanda, scartata) {
  const m = messaggio("assistente scheda");
  m.append(el("p", scartata ? `Cerco nelle fonti altre forme di «${entita}», per una scheda nuova.` :
    `Non c'è ancora una scheda per «${entita}»: cerco nelle fonti le forme attestate.`));
  const campo = (etichetta, segnaposto, valore = "") => {
    const l = el("label", etichetta);
    const i = document.createElement("input");
    i.type = "text";
    i.placeholder = segnaposto;
    i.value = valore;
    l.append(i);
    return [l, i];
  };
  // un omonimo ha bisogno di un nome suo: due schede non possono chiamarsi allo stesso modo
  // il campo parte vuoto: con lo stesso nome si finirebbe dritti nella scheda che si è appena scartata
  const [ln, nome] = scartata ? campo("Nome della scheda nuova", `per esempio «${entita} (1900–1964)»`) : [null, null];
  const omonimo = [];
  if (ln) {
    const spiega = el("p", `«${scartata}» esiste già: dai alla scheda nuova un nome che la distingua, con le date o ` +
      "il ruolo.", "nota spiega-nome");
    spiega.id = "spiega-nome-" + Date.now();
    nome.setAttribute("aria-describedby", spiega.id);
    omonimo.push(ln, spiega);
  }
  const [li, indizi] = campo("Indizi (facoltativi)", "paese, partito… separati da ;");
  const [lc, candidate] = campo("Altre forme da verificare (facoltative)", "per esempio una trascrizione; separate da ;");
  const esito = el("div");
  const cerca = pulsanteMsg("Cerca le forme nelle fonti", async () => {
    cerca.disabled = true;
    // la ricerca delle forme scorre tutte le fonti: i secondi che passano dicono che sta lavorando
    const inizio = Date.now();
    const attesa = el("p", "Cerco le forme in tutte le fonti: di solito servono da 10 a 30 secondi.", "nota in-attesa");
    esito.replaceChildren(attesa);
    const orologio = setInterval(() => {
      attesa.textContent = "Cerco le forme in tutte le fonti (di solito da 10 a 30 secondi)… " +
        `${Math.round((Date.now() - inizio) / 1000)} s`;
    }, 1000);
    try {
      const r = await api("/api/esplora", { nome: entita, indizi: indizi.value, candidate: candidate.value });
      mostraFormeTrovate(m, esito, r, entita, domanda, nome);
      // trovate le forme, la ricerca si rifà solo cambiando gli indizi: il pulsante diventa secondario
      cerca.textContent = "Cerca di nuovo con questi indizi";
      cerca.className = "discreto";
    } catch (e) {
      esito.replaceChildren(el("p", e.message + " Puoi riprovare con lo stesso pulsante.", "attenzione"));
    } finally {
      clearInterval(orologio);
      cerca.disabled = false;
      scorriInFondo();
    }
    // il pulsante premuto si era spento e il fuoco era caduto sulla pagina: passa alla prima forma trovata
    (esito.querySelector("input.sceglie") || cerca).focus({ preventScroll: true });
  }, "primario");
  m.append(...omonimo, li, lc, cerca, esito);
  (nome || indizi).focus();
  return m;
}

function mostraFormeTrovate(m, box, r, entita, domanda, campoNome) {
  box.replaceChildren();
  if (r.errore) {
    box.append(el("p", r.errore + (r.avanzamento ? ` (${r.avanzamento})` : ""), "attenzione"));
    return;
  }
  if (r.avviso_indice) box.append(el("p", r.avviso_indice, "nota"));
  if (!r.forme.length) {
    box.append(el("p", `Nessuna forma di «${entita}» compare nelle fonti.` +
      (r.non_attestate.length ? ` Non attestate: ${r.non_attestate.join("; ")}.` : ""), "nota"));
    return;
  }
  const spiega = el("p", "Accendi le forme che indicano davvero questa entità; il numero è quante righe delle fonti " +
    "la contengono. «Ambigua»: la forma può indicare anche altro (un cognome da solo, per esempio), e quei passaggi " +
    "li controlla sempre il modello.", "nota");
  const tasti = el("p", "Da tastiera: frecce tra le forme, Spazio accende o spegne, A segna ambigua, Invio crea la scheda.",
    "nota tasti-forme");
  box.append(spiega, tasti);
  // le forme come chip (la casella vera è dentro: Spazio e Tab funzionano da sé); sotto, il dettaglio di quella
  // scelta con la tastiera o col mouse: esempio, serie e anni, la casella «ambigua»
  const dettagli = el("div", null, "forme-dettagli");
  dettagli.setAttribute("aria-live", "polite");
  const gruppo = (forme, etichetta) => {
    const g = el("div", null, "forme-chip");
    g.setAttribute("role", "group");
    g.setAttribute("aria-label", etichetta);
    for (const f of forme) {
      const [chip, d] = formaChip(f);
      g.append(chip);
      dettagli.append(d);
      const mostraDettaglio = () => {
        dettagli.querySelectorAll(".dettaglio-forma").forEach((x) => { x.hidden = x !== d; });
        box.querySelectorAll(".chip-forma").forEach((x) => x.classList.toggle("attiva", x === chip));
      };
      chip.addEventListener("focusin", mostraDettaglio);
      chip.addEventListener("pointerenter", mostraDettaglio);
    }
    return g;
  };
  const nuove = r.forme.filter((f) => !f.scartata_prima);
  const vecchie = r.forme.filter((f) => f.scartata_prima);
  if (nuove.length) box.append(gruppo(nuove, "Forme trovate"));
  if (vecchie.length) {
    const d = el("details", null, "forme-scartate");
    d.append(el("summary", `Scartate l'altra volta (${vecchie.length}): restano spente`), gruppo(vecchie, "Forme scartate l'altra volta"));
    box.append(d);
  }
  box.append(dettagli);
  const primo = dettagli.querySelector(".dettaglio-forma");
  if (primo) primo.hidden = false;
  if (r.non_attestate.length) box.append(el("p", `Non attestate (non entrano nella scheda): ${r.non_attestate.join("; ")}`, "nota"));
  const sommario = el("div");
  const scelte = () => [...box.querySelectorAll("input.sceglie:checked")].map((c) => c.value);
  const tipo = document.createElement("select");
  for (const t of ["persona", "organizzazione", "testata", "stato", "altro"]) tipo.append(new Option(t, t));
  // chi è: va nelle note della scheda; senza, il controllo del glossario la segnalerebbe dopo
  const descr = document.createElement("textarea");
  descr.rows = 2;
  descr.placeholder = "chi è, il periodo, gli omonimi da non confondere";
  const ld = el("label", "Chi è (note della scheda)", "campo-scheda descrizione-nuova");
  ld.append(descr);
  // il controllo della scheda prima di crearla: gli stessi problemi che il glossario segnalerebbe dopo
  const controlloNuova = el("div", null, "controllo-prima");
  controlloNuova.setAttribute("aria-live", "polite");
  let attesaVerifica = null;
  const verifica = () => {
    clearTimeout(attesaVerifica);
    attesaVerifica = setTimeout(async () => {
      const varianti = scelte();
      if (!varianti.length) { controlloNuova.replaceChildren(); return; }
      const nomeScheda = (campoNome && campoNome.value.trim()) || entita;
      try {
        const v = await api("/api/scheda/verifica", { nome: nomeScheda, nuova: true, campi: {
          varianti, forme_ambigue: [...box.querySelectorAll("input.ambigua:checked")].map((c) => c.value),
          tipo: tipo.value, note: descr.value } });
        controlloNuova.replaceChildren(...(v.problemi.length ? [el("p", "Prima di creare la scheda:", "nota"),
          elencoProblemi(v.problemi, true)] : []));
      } catch (e) { controlloNuova.replaceChildren(); }
    }, 450);
  };
  const aggiorna = () => {
    const varianti = scelte();
    const ambigue = [...box.querySelectorAll("input.ambigua:checked")].map((c) => c.value).filter((f) => varianti.includes(f));
    const righe = r.forme.filter((f) => varianti.includes(f.forma)).reduce((n, f) => n + (f.totale || 0), 0);
    sommario.replaceChildren(riepilogoScheda(varianti, ambigue, righe, tipo.value));
    box.querySelectorAll(".chip-forma").forEach((c) => {
      const a = box.querySelector(`input.ambigua[data-i="${c.dataset.i}"]`);
      c.classList.toggle("ambigua", !!(a && a.checked));
    });
    verifica();
  };
  box.addEventListener("change", (e) => {
    if (e.target.classList.contains("sceglie") || e.target.classList.contains("ambigua") || e.target === tipo) aggiorna();
  });
  descr.addEventListener("input", verifica);
  if (campoNome) campoNome.addEventListener("input", verifica);
  const lt = el("label", "Tipo di entità ");
  lt.append(tipo);
  // creare la scheda e avviare la ricerca sono due passi: la scheda resta nel glossario anche se non si avvia nulla
  const crea = pulsanteMsg("Crea la scheda", async () => {
    const varianti = scelte();
    const ambigue = [...box.querySelectorAll("input.ambigua:checked")].map((c) => c.value).filter((f) => varianti.includes(f));
    if (!varianti.length) { avviso("Accendi almeno una forma del nome.", true); return; }
    if (campoNome && !campoNome.value.trim()) {
      avviso("Dai un nome alla scheda nuova: deve distinguerla da quella che esiste già.", true);
      campoNome.focus();
      return;
    }
    const nomeScheda = (campoNome && campoNome.value.trim()) || entita;
    await caricaGlossario();
    const doppia = ((stato.glossario && stato.glossario.schede) || []).find((s) => normalizza(s.nome) === normalizza(nomeScheda));
    if (doppia) {
      if (!await conferma(`La scheda «${doppia.nome}» esiste già`, "Le forme scelte qui non la cambiano. Puoi " +
        "cercare con le forme della scheda che c'è, oppure annullare e dare alla scheda nuova un altro nome.",
        "Usa la scheda esistente")) return;
      riduciScheda(m, `Uso la scheda esistente «${doppia.nome}».`);
      return formeDelNome(doppia.nome, domanda || doppia.nome);
    }
    crea.disabled = true;
    // le forme lasciate spente si ricordano: la prossima esplorazione di questo nome non le ripropone accese
    const scartate = r.forme.map((f) => f.forma).filter((f) => !varianti.includes(f));
    try {
      const s = await api("/api/scheda", { nome: nomeScheda, varianti, forme_ambigue: ambigue, tipo: tipo.value,
        contesto: r.contesto, scartate, cercato: entita, descrizione: descr.value });
      if (s.avviso) avviso(s.avviso);
      stato.glossario = null;                      // la scheda nuova entra nel glossario
      const creata = s.scheda || nomeScheda;
      riduciScheda(m, `Scheda «${creata}» creata: ${varianti.length === 1 ? "1 forma" : varianti.length + " forme"}` +
        (ambigue.length ? `, ${ambigue.length === 1 ? "1 ambigua" : ambigue.length + " ambigue"}.` : "."));
      annuncia(`Scheda «${creata}» creata.`);
      await formeDelNome(creata, domanda || creata);
    } catch (e) {
      crea.disabled = false;
      avviso(e.message, true);
    }
  }, "primario");
  box.addEventListener("keydown", (e) => tastiForme(e, box, crea));
  aggiorna();
  stato.aggiornaRiepilogo = () => { if (!m.classList.contains("decisa")) aggiorna(); };
  box.append(lt, ld, sommario, controlloNuova, crea);
  annuncia(`${r.forme.length} forme trovate: accendi quelle giuste.`);
}

// frecce tra le forme (anche quelle scartate, se il loro elenco è aperto), A per «ambigua», Invio per creare
function tastiForme(e, box, crea) {
  if (!e.target.classList || !e.target.classList.contains("sceglie")) return;
  const caselle = [...box.querySelectorAll("input.sceglie")].filter((c) => c.offsetParent !== null);
  const i = caselle.indexOf(e.target);
  const passo = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
  if (passo) {
    e.preventDefault();
    caselle[(i + passo + caselle.length) % caselle.length].focus();
  } else if (e.key === "Home" || e.key === "End") {
    e.preventDefault();
    caselle[e.key === "Home" ? 0 : caselle.length - 1].focus();
  } else if (e.key.toLowerCase() === "a" && !e.ctrlKey && !e.metaKey && !e.altKey) {
    e.preventDefault();
    const a = box.querySelector(`input.ambigua[data-i="${e.target.dataset.i}"]`);
    if (a) {
      a.checked = !a.checked;
      a.dispatchEvent(new Event("change", { bubbles: true }));
      annuncia(`${e.target.value}: ${a.checked ? "ambigua" : "non ambigua"}.`);
    }
  } else if (e.key === "Enter") {
    e.preventDefault();
    crea.click();
  }
}

// una forma: il chip con la casella che la sceglie, e il suo dettaglio (esempio, serie e anni, «ambigua»)
let contaForme = 0;
function formaChip(f) {
  const i = String(++contaForme);
  const chip = el("label", null, "chip-forma");
  chip.dataset.i = i;
  const c = document.createElement("input");
  c.type = "checkbox";
  c.className = "sceglie";
  c.value = f.forma;
  c.checked = f.proposta;
  c.dataset.i = i;
  c.setAttribute("aria-describedby", "dettaglio-forma-" + i);
  chip.append(c, el("span", f.forma, "nome-forma"), el("span", String(f.totale), "conto"));
  if (f.attenzione) chip.append(el("span", "!", "segno-attenzione"));
  const d = el("div", null, "dettaglio-forma");
  d.id = "dettaglio-forma-" + i;
  d.hidden = true;
  const testa = el("div", null, "testa");
  testa.append(el("strong", f.forma), el("span", `${f.totale} ${f.totale === 1 ? "riga" : "righe"}`, "conto"));
  if (f.origine && f.origine !== "nelle fonti") testa.append(el("span", f.origine, "conto"));
  const la = el("label", null, "casella");
  const a = document.createElement("input");
  a.type = "checkbox";
  a.className = "ambigua";
  a.value = f.forma;
  a.checked = f.ambigua;
  a.dataset.i = i;
  la.append(a, document.createTextNode("ambigua"));
  testa.append(la);
  d.append(testa);
  if (f.scartata_prima) d.append(el("div", "L'avevi scartata l'altra volta che hai cercato questo nome.", "nota"));
  if (f.attenzione) d.append(el("div", f.attenzione, "attenzione"));
  const serie = Object.entries(f.per_serie_e_anno || {}).map(([s, anni]) =>
    `${s}: ${Object.entries(anni).map(([an, n]) => `${an} (${n})`).join(", ")}`);
  if (serie.length) d.append(el("div", serie.join("; "), "nota"));
  for (const e of (f.esempi || []).slice(0, 1)) {
    const q = el("blockquote", e.testo);
    q.title = e.riferimento;
    d.append(q);
    if (e.riferimento) d.append(el("div", e.riferimento, "nota riferimento-esempio"));
  }
  return [chip, d];
}

// --------------------------------------------- la ricerca e la risposta
// filtri: quelli di una ricerca da ripetere (Riprova); senza, quelli scelti adesso nel riquadro
async function avviaRicerca(entita, domanda, filtri) {
  const f = filtri || filtriScelti();
  try {
    const r = await api("/api/ricerca/avvia", { entita, domanda: domanda || "", dal: f.dal, al: f.al, fonti: f.fonti,
      evoluzione: f.evoluzione });
    if (r.gia_in_corso) avviso("Questa ricerca era già in corso: ne seguo l'avanzamento.");
    else avviso("");
    const filo = Object.assign(filoCorrente(), { entita, domanda, avviata: true });
    filo.titolo = domanda || entita;
    registra(filo, { tipo: "ricerca", entita, domanda: domanda || "", filtri: f });
    stato.filoRicerca = filo;
    stato.ultimaRisposta = "";
    stato.tappaAnnunciata = "";
    messaggioRicerca(domanda || entita);
    annuncia(`Ricerca avviata: ${entita}.`);
    inCorso(true);
    segui();
  } catch (e) {
    // la ricerca non è partita: il motivo e, accanto, le due strade (riprovare, o cambiare il modello)
    const rimedi = el("div", null, "riga rimedi-ricerca");
    const m = messaggio("assistente errore", el("p", e.message), rimedi);
    rimedi.append(pulsanteMsg("Riprova", () => { m.remove(); avviaRicerca(entita, domanda, f); }, "primario"),
      pulsanteMsg("Cambia modello", () => apriImpostazioni("modelli"), "discreto"));
  }
}

const TAPPE_RICERCA = ["Estrazione", "Lettura dei passaggi", "Risposta"];

// la fine della ricerca come frase (gli stati di lavori.py sono participi: «Ricerca errore» non si legge)
function fraseFine(s) {
  return { errore: "La ricerca si è interrotta per un errore.", interrotta: "La ricerca si è interrotta.",
    fermata: "Ricerca fermata." }[s] || `Ricerca ${s}.`;
}

// il messaggio dell'avanzamento: si aggiorna sul posto, come una risposta che arriva
function messaggioRicerca(titolo) {
  const barra = el("div", null, "barra");
  barra.setAttribute("role", "progressbar");
  barra.setAttribute("aria-label", "Avanzamento della ricerca");
  barra.setAttribute("aria-valuemin", "0");
  barra.setAttribute("aria-valuemax", "100");
  barra.setAttribute("aria-valuenow", "0");
  const riempi = el("div");
  barra.append(riempi);
  // le tre fasi di ricerca.py, con quella in corso segnata: si vede a che punto è senza leggere la riga di stato
  const tappe = el("ol", null, "tappe-ricerca");
  tappe.setAttribute("aria-label", "Fasi della ricerca");
  tappe.append(...TAPPE_RICERCA.map((t) => el("li", t)));
  // in attesa delle quote: il conto alla rovescia e «Riprova ora»
  const quota = el("div", null, "attesa-quota");
  quota.hidden = true;
  const conto = el("span", "", "conto-quota");
  const riprova = pulsanteMsg("Riprova ora", riprovaOra, "discreto");
  quota.append(conto, riprova);
  // gli ultimi passaggi letti, mentre il modello legge: che cosa ha deciso e su quale fonte
  const vive = el("ol", null, "letture-vive");
  vive.setAttribute("aria-label", "Ultimi passaggi letti");
  vive.hidden = true;
  const m = messaggio("assistente ricerca", el("p", titolo, "titolo-ricerca"), tappe, barra,
    el("p", "In partenza…", "nota stato-ricerca"),
    el("p", "", "nota dettaglio-ricerca"), quota, vive,
    el("p", "Continua anche se chiudi questa pagina.", "nota"));
  stato.ricercaEl = m;
  stato.righeLette = 0;
  stato.ritmo = null;
  return m;
}

// ------------------------------------------------ lettura dal vivo, tempo che resta, attesa delle quote
const LETTURE_VISIBILI = 6;

// le letture nuove (dal punto in cui si era arrivati) entrano in cima all'elenco; le più vecchie escono
async function aggiornaLetture(m) {
  let r;
  try { r = await api("/api/ricerca/letture?dopo=" + (stato.righeLette || 0)); } catch (e) { return; }
  const vive = m.querySelector(".letture-vive");
  if (!vive) return;
  if (r.azzera) { vive.replaceChildren(); stato.righeLette = 0; }
  stato.righeLette = r.righe || 0;
  for (const p of r.letture || []) vive.prepend(rigaLettura(p));
  while (vive.children.length > LETTURE_VISIBILI) vive.lastChild.remove();
  vive.hidden = !vive.children.length;
}

function rigaLettura(p) {
  const si = p.pertinente === "sì";
  const li = el("li", null, si ? "si" : p.pertinente === "incerto" ? "incerto" : "no");
  const segno = el("span", si ? "✓" : p.pertinente === "incerto" ? "?" : "–", "segno");
  segno.setAttribute("aria-hidden", "true");
  const testa = el("span", null, "testa-lettura");
  testa.append(el("span", si ? "pertinente" : p.pertinente === "incerto" ? "incerto" : "non pertinente", "solo-lettori"),
    el("span", senzaMarkdown(p.fonte) || p.file, "fonte-lettura"), el("span", p.data || "", "data-lettura"));
  li.append(segno, testa);
  if (si && p.traduzione) li.append(el("span", p.traduzione, "traduzione-lettura"));
  if (p.letto_da) li.title = "Letto da " + p.letto_da;
  li.addEventListener("click", () => apriFonte(p.file, p.riga, null, null, "passaggi"));
  return li;
}

// minuti alla fine della lettura, dal ritmo osservato da quando questa pagina la segue (servono due misure)
function tempoCheResta(l) {
  if (!l || !l.estratti) return "";
  const ora = Date.now();
  if (!stato.ritmo || l.letti < stato.ritmo.letti) stato.ritmo = { t: ora, letti: l.letti };
  const fatti = l.letti - stato.ritmo.letti;
  const secondi = (ora - stato.ritmo.t) / 1000;
  if (fatti < 3 || secondi < 20) return "";
  const resto = (l.estratti - l.letti) / (fatti / secondi);
  if (!isFinite(resto) || resto <= 0) return "";
  return resto < 90 ? "circa un minuto alla fine della lettura" : `circa ${Math.round(resto / 60)} min alla fine della lettura`;
}

function mostraAttesaQuota(m, r) {
  const box = m.querySelector(".attesa-quota");
  if (!box) return;
  clearInterval(stato.orologioQuota);
  const ts = r.stato === "in attesa" && r.prossimo_ts ? r.prossimo_ts * 1000 : 0;
  box.hidden = !ts;
  if (!ts) return;
  const conto = box.querySelector(".conto-quota");
  const segna = () => {
    const s = Math.max(0, Math.round((ts - Date.now()) / 1000));
    const ore = new Date(ts).toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" });
    conto.textContent = s ? `Quote finite: riprovo tra ${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")} (alle ${ore}).`
      : "Riprovo adesso…";
  };
  segna();
  stato.orologioQuota = setInterval(segna, 1000);
}

async function riprovaOra() {
  try {
    const r = await api("/api/ricerca/riprova", {});
    avviso(r.nota || "");
    segui();
  } catch (e) {
    avviso(e.message, true);
  }
}

function descriviProfili(p) {
  if (!p || typeof p !== "object") return "";
  const nomi = { smistamento: "smistamento", analisi: "lettura", sintesi: "risposta" };
  const parti = Object.entries(p).filter(([, v]) => v).map(([k, v]) => `${nomi[k] || k} ${nomeModello(v)}`);
  if (!parti.length) return "";
  const unici = new Set(Object.values(p).filter(Boolean));
  return unici.size === 1 ? `Modello: ${nomeModello([...unici][0])}.` : `Modelli: ${parti.join(", ")}.`;
}

function inCorso(si) {
  stato.inCorso = si;
  mostra("b-invia", !si);
  mostra("b-ferma", si);
  $("testo").placeholder = si ? "La ricerca è in corso…" : "Fai una domanda sulle fonti, o scrivi un nome";
}

function segui() {
  clearTimeout(stato.attesa);
  stato.attesa = setTimeout(async () => {
    try {
      await mostraRicerca(await api("/api/ricerca"), false);
    } catch (e) {
      avviso(e.message, true);
      segui();
    }
  }, 2500);
}

async function mostraRicerca(r, allAvvio) {
  if (!r || r.nessuna) return;
  if (allAvvio && r.finito) return;          // all'apertura: si segue solo una ricerca in corso
  if (allAvvio) {                            // una ricerca in corso all'apertura: il suo filo, se è salvato
    const salvato = (stato.fili || []).find((x) => x.ricerca && x.ricerca === r.id);
    if (salvato && await apriFilo(salvato.id)) {
      stato.filoRicerca = stato.thread;
    } else {
      nuovoThread();
      const filo = Object.assign(filoCorrente(), { entita: r.entita, domanda: r.domanda, avviata: true, ricerca: r.id });
      messaggio("utente", el("p", r.domanda || r.entita));
      registra(filo, { tipo: "utente", testo: r.domanda || r.entita });
      stato.filoRicerca = filo;
    }
    messaggioRicerca(r.domanda || r.entita);
  } else if (!stato.ricercaEl) {             // avviata dalla conversazione: si segue nel filo aperto
    stato.filoRicerca = Object.assign(filoCorrente(), { entita: r.entita, domanda: r.domanda, avviata: true });
    messaggioRicerca(r.domanda || r.entita);
  }
  const filo = stato.filoRicerca;
  if (filo && r.id && filo.ricerca !== r.id) { filo.ricerca = r.id; salvaFilo(filo); }   // per ritrovarlo alla riapertura
  const m = stato.ricercaEl;
  // la riga di stato dice i numeri che contano (letti, pertinenti finora, minuti); sotto, più tenue, l'ultimo
  // messaggio della ricerca e l'eventuale nuovo tentativo
  const f = /(\d)\s*\/\s*3/.exec(r.fase || "");
  const l = r.letti;
  const letti = l ? `${l.letti} di ${l.estratti} passaggi letti` +
    (l.pertinenti !== undefined ? ` · ${l.pertinenti} ${l.pertinenti === 1 ? "pertinente" : "pertinenti"} finora` : "") : "";
  const faseTesto = f ? "" : r.fase;                         // una fase senza numero si dice per esteso
  const resta = !r.finito && r.stato !== "in attesa" ? tempoCheResta(l) : "";
  const parti = [r.stato && r.stato !== "in corso" ? r.stato : "", faseTesto, letti || r.avanzamento,
    r.minuti ? `${r.minuti} min` : "", resta].filter(Boolean);
  m.querySelector(".stato-ricerca").textContent = parti.join(" · ") || "In corso…";
  const dettagli = [];
  if (r.prossimo_tentativo && !r.prossimo_ts) dettagli.push(`Nuovo tentativo: ${r.prossimo_tentativo}.`);
  if (r.ultimo_messaggio && !(r.fase && r.ultimo_messaggio.includes(r.fase))) dettagli.push(r.ultimo_messaggio);
  const modelli = descriviProfili(r.profili);
  if (modelli) dettagli.push(modelli);
  const dett = m.querySelector(".dettaglio-ricerca");
  if (dett) { dett.textContent = dettagli.join(" "); dett.hidden = !dettagli.length; }
  mostraAttesaQuota(m, r);
  if (!r.finito && (l || (f && +f[1] >= 2))) aggiornaLetture(m);
  const tappe = m.querySelectorAll(".tappe-ricerca > li");
  tappe.forEach((li, i) => {
    const n = f ? +f[1] - 1 : -1;
    const completata = r.finito && String(r.stato || "").startsWith("completata");
    const stato_ = completata || i < n ? "fatta" : i === n ? (r.finito ? "fermata" : "in-corso") : "";
    li.className = stato_;
    if (stato_ === "in-corso") li.setAttribute("aria-current", "step"); else li.removeAttribute("aria-current");
  });
  // la barra segue le tre fasi (estrazione, lettura, risposta) e, dentro la lettura, i passaggi letti
  const barra = m.querySelector(".barra");
  const n = /(\d+)\s*\/\s*(\d+)/.exec(r.avanzamento || "");
  const segna = (p) => {
    const v = Math.round(Math.min(100, Math.max(0, p)));
    barra.setAttribute("aria-valuenow", String(v));
    barra.firstChild.style.transform = `scaleX(${v / 100})`;
  };
  if (f) {
    const fase = +f[1];
    const dentro = fase !== 2 ? 0 : r.letti && r.letti.estratti ? r.letti.letti / r.letti.estratti
      : n && +n[2] ? n[1] / n[2] : 0;
    segna(((fase - 1 + dentro) / 3) * 100);
  }
  // si annunciano i cambi di fase e la fine, non ogni aggiornamento dei conteggi
  const tappa = r.finito ? `fine ${r.stato}` : r.fase || "";
  if (tappa && tappa !== stato.tappaAnnunciata) {
    stato.tappaAnnunciata = tappa;
    if (!allAvvio) annuncia(r.finito ? fraseFine(r.stato) : `Ricerca: ${r.fase}.`);
  }
  inCorso(!r.finito);
  if (!r.finito) { segui(); return; }
  clearInterval(stato.orologioQuota);
  aggiornaConsumo();
  segna(100);
  if (r.ultimi_messaggi && r.ultimi_messaggi.length) {
    avviso(`Ricerca ${r.stato}: ${r.ultimi_messaggi.slice(-2).join(" ")}`, true);
  }
  if (r.avviso) avviso(r.avviso, true);
  const p = r.risposta_pronta;
  stato.ricercaEl = null;
  precedentiDi.clear();                      // una ricerca finita cambia i passaggi già letti e la durata attesa
  stato.filoRicerca = null;
  if (p && stato.ultimaRisposta !== r.documento) {
    stato.ultimaRisposta = r.documento;
    // la risposta entra nel filo della ricerca anche se intanto se ne guarda un altro
    if (filo) registra(filo, { tipo: "risposta", documento: r.documento, pertinenti: p.documenti_pertinenti });
    if (filo) filo.risposta = r.documento;
    if (m.isConnected) {
      m.remove();
      messaggioRisposta(r.documento, p.documenti_pertinenti);
    } else {
      avviso(`Ricerca finita: «${r.domanda || r.entita}». La trovi tra i recenti.`);
    }
  } else if (m.isConnected) {
    // senza risposta (errore, quote finite, fermata): che cosa è successo e che cosa si può fare adesso
    m.querySelector(".stato-ricerca").textContent = fraseFine(r.stato) +
      (r.messaggio && r.messaggio !== "Ricerca fermata su richiesta." ? ` ${r.messaggio}` : "");
    m.querySelector(".barra").hidden = true;
    const riprova = () => {
      m.remove();
      avviaRicerca(r.entita, r.domanda || "", r.filtri);
    };
    const rimedi = el("div", null, "riga rimedi-ricerca");
    rimedi.append(pulsanteMsg(r.stato === "fermata" ? "Riprendi la ricerca" : "Riprova", riprova, "primario"));
    if (r.stato !== "fermata") rimedi.append(pulsanteMsg("Cambia modello", () => apriImpostazioni("modelli"), "discreto"));
    m.querySelectorAll(".nota:not(.stato-ricerca):not(.dettaglio-ricerca)").forEach((x) => x.remove());
    m.append(el("p", "I passaggi già letti restano salvati e la nuova ricerca li riusa.", "nota"), rimedi);
  }
  caricaStorico();
}

async function ferma() {
  if (!await conferma("Fermare la ricerca?", "La ricerca si interrompe qui. I passaggi già letti restano salvati " +
    "e una ricerca successiva li riusa.", "Ferma la ricerca")) return;
  try {
    const r = await api("/api/ricerca/ferma", {});
    avviso(r.nota || "");
  } catch (e) {
    avviso(e.message, true);
  }
}

// la risposta: il documento nel filo, come testo della pagina; le prove restano chiuse sotto
function messaggioRisposta(url, pertinenti) {
  const q = new URL(url, location.href).searchParams;
  const doc = q.get("risposta") ? { risposta: q.get("risposta") } : q.get("ricerca") ? { ricerca: q.get("ricerca") } : null;
  stato.doc = doc;
  const corpo = el("div", null, "documento");
  corpo.append(el("p", "Carico la risposta…", "nota"));
  const azioni = el("div", null, "riga azioni-risposta");
  // un'azione sola per le fonti, con il loro numero; il documento completo resta un collegamento secondario.
  // Premuto di nuovo con i passaggi di questa stessa risposta già aperti, chiude il pannello
  const n = pertinenti !== null && pertinenti !== undefined && pertinenti !== "" ? String(pertinenti) : "";
  const fonti = pulsanteMsg(n ? `Fonti (${n} ${n === "1" ? "documento" : "documenti"})` : "Fonti di questa risposta", () => {
    if (schedaAperta() === "passaggi" && stato.doc === doc) return chiudiLaterale();
    stato.doc = doc;
    apriLaterale("passaggi");
  }, "fonti-risposta");
  fonti.setAttribute("aria-controls", "laterale");
  const a = el("a", "Documento completo");
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener";
  a.title = "Apre la risposta intera in una finestra a parte, da stampare o salvare";
  azioni.append(fonti, a, menuEsporta(doc));
  const confronto = el("div", null, "confronto");
  confronto.hidden = true;
  const m = messaggio("assistente risposta", confronto, corpo, azioni);
  (async () => {
    try {
      const r = await api("/api/documento?" + new URLSearchParams(doc));
      corpo.replaceChildren();
      const pref = inserisciDocumento(corpo, r.corpo);
      await arricchisciDocumento(corpo, doc, pref);
      if (doc.risposta) await mostraConfronto(confronto, corpo, doc);
    } catch (e) {
      corpo.replaceChildren(el("p", e.message, "attenzione"));
    }
  })();
  annuncia("Risposta pronta.");
  return m;
}

/// ------------------------------------------------------------------ esportazioni e confronto con la risposta di prima
const ESPORTAZIONI = [
  ["docx", "Word, con le note a piè di pagina", "la risposta in stile Chicago"],
  ["csl", "Zotero o Mendeley (CSL-JSON)", "i documenti citati"],
  ["bibtex", "BibTeX", "i documenti citati"],
  ["csv", "Tabella dei passaggi (CSV)", "per Excel o LibreOffice"],
];

// un menu a tendina accanto a «Documento completo»: ogni voce scarica il file (il server lo prepara al momento)
function menuEsporta(doc) {
  const d = el("details", null, "menu-esporta");
  const s = el("summary", "Esporta");
  d.append(s);
  const lista = el("ul");
  for (const [formato, testo, dettaglio] of ESPORTAZIONI) {
    const li = el("li");
    const a = el("a", testo);
    a.href = "/esporta?" + new URLSearchParams(Object.assign({ formato }, doc));
    a.setAttribute("download", "");
    a.addEventListener("click", () => { d.open = false; annuncia(`Esporto: ${testo}.`); });
    li.append(a, el("span", dettaglio, "nota"));
    lista.append(li);
  }
  d.append(lista);
  d.addEventListener("keydown", (e) => { if (e.key === "Escape" && d.open) { e.stopPropagation(); d.open = false; s.focus(); } });
  return d;
}

// La risposta rifatta sulla stessa entità: che cosa è cambiato rispetto a quella prima. Sopra il documento, una
// riga che lo dice (si apre per i dettagli); nel documento i rimandi [n] dei passaggi nuovi portano «nuovo».
async function mostraConfronto(box, corpo, doc) {
  let r;
  try { r = await api("/api/confronto?" + new URLSearchParams({ risposta: doc.risposta })); } catch (e) { return; }
  if (!r.precedente) return;
  const nuovi = r.nuovi || [];
  const tolti = r.tolti || [];
  if (!nuovi.length && !tolti.length && !r.risposta_cambiata) {
    box.append(el("p", `Uguale alla risposta del ${r.precedente.data}: stessi passaggi citati.`, "nota"));
    box.hidden = false;
    return;
  }
  const parti = [];
  if (nuovi.length) parti.push(`${nuovi.length} ${nuovi.length === 1 ? "passaggio nuovo" : "passaggi nuovi"}`);
  if (tolti.length) parti.push(`${tolti.length} non più ${tolti.length === 1 ? "citato" : "citati"}`);
  if (r.risposta_cambiata) parti.push("la risposta breve è cambiata");
  const d = el("details", null, "confronto-dettagli");
  d.append(el("summary", `Rispetto alla risposta del ${r.precedente.data}: ${parti.join(", ")}.`));
  if (nuovi.length) {
    d.append(el("h4", "Citati adesso, non la volta prima"));
    const ul = el("ul");
    for (const x of nuovi) ul.append(el("li", `[${x.n}] ${senzaMarkdown(x.riferimento)}`));
    d.append(ul);
  }
  if (tolti.length) {
    d.append(el("h4", "Citati la volta prima, non adesso"));
    const ul = el("ul");
    for (const x of tolti) ul.append(el("li", senzaMarkdown(x.riferimento) || x.file));
    d.append(ul);
  }
  if (r.risposta_cambiata && r.risposta_prima) {
    const due = el("div", null, "due-risposte");
    const colonna = (titolo, testo) => {
      const c = el("div");
      c.append(el("h4", titolo), el("p", senzaMarkdown(testo), "documento-breve"));
      return c;
    };
    due.append(colonna(`Il ${r.precedente.data}`, r.risposta_prima), colonna("Adesso", r.risposta_ora));
    d.append(due);
  }
  const a = el("a", "Apri la risposta di prima");
  a.href = r.precedente.documento;
  a.target = "_blank";
  a.rel = "noopener";
  d.append(a);
  box.append(d);
  box.hidden = false;
  const numeri = new Set(nuovi.map((x) => String(x.n)));
  const segnati = new Set();
  corpo.querySelectorAll("a.rimando").forEach((x) => {
    const n = (/\d+/.exec(x.textContent) || [])[0];
    if (!numeri.has(n) || segnati.has(n)) return;
    segnati.add(n);
    const s = el("span", "nuovo", "segno-nuovo");
    s.title = `Non era citato nella risposta del ${r.precedente.data}`;
    x.after(s);
  });
}

// --------------------------------------------- recenti
async function caricaStorico() {
  const ul = $("storico");
  let s;
  let fili;
  try {
    [s, fili] = await Promise.all([api("/api/storico"), api("/api/fili")]);
  } catch (e) {
    ul.replaceChildren(el("li", e.message, "nota"));
    return;
  }
  stato.fili = fili.fili;
  // i fili salvati; poi le risposte e le ricerche di prima, che nessun filo contiene
  const nei = new Set(fili.fili.flatMap((f) => f.documenti));
  const quando = (d) => {
    const m = /(\d+)\/(\d+)\/(\d+) (\d+):(\d+)/.exec(d || "");
    return m ? `${m[3]}-${m[2]}-${m[1]}T${m[4]}:${m[5]}` : d || "";
  };
  const voci = [
    ...fili.fili.map((f) => ({ filo: f, titolo: f.titolo || f.entita || "Senza titolo", quando: f.aggiornato,
      dettaglio: f.entita, domanda: f.domanda || "", stato: f.stato || "", filtri: f.filtri || null,
      pertinenti: f.pertinenti || "" })),
    ...[...s.risposte, ...s.ricerche].filter((r) => !nei.has(r.documento)).map((r) => ({ vecchia: r,
      titolo: r.domanda || r.entita || r.cartella || r.file, quando: quando(r.data), dettaglio: r.entita,
      // le risposte di prima dei fili: niente filtri salvati, ma i documenti pertinenti e l'evoluzione sì
      domanda: r.domanda || "", stato: "risposta", pertinenti: r.pertinenti || "",
      filtri: r.evoluzione ? { evoluzione: true } : null })),
  ].sort((a, b) => b.quando.localeCompare(a.quando));
  stato.recenti = voci;
  disegnaRecenti();
  suggerimenti();
}

// I recenti: le ricerche sulla stessa entità stanno insieme (una riga con il nome, che si apre sulle sue ricerche),
// in gruppi per data dell'ultima. Con un filtro l'elenco diventa piatto, con le sole voci che corrispondono.
function disegnaRecenti() {
  const ul = $("storico");
  const voci = stato.recenti || [];
  const filtro = normalizza($("recenti-filtro").value.trim());
  const corrente = stato.thread && stato.thread.id;
  const oggi = new Date();
  oggi.setHours(0, 0, 0, 0);
  const gruppo = (q) => {
    const d = new Date(q);
    if (isNaN(d)) return "Prima";
    const giorni = Math.floor((oggi - new Date(d.getFullYear(), d.getMonth(), d.getDate())) / 864e5);
    return giorni <= 0 ? "Oggi" : giorni === 1 ? "Ieri" : giorni < 7 ? "Questa settimana" : "Prima";
  };
  const giorno = (q) => {
    const d = new Date(q);
    if (isNaN(d)) return "";
    return gruppo(q) === "Oggi" || gruppo(q) === "Ieri" ? d.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" }) :
      d.toLocaleDateString(LOCALE, { day: "numeric", month: "short", ...(d.getFullYear() !== oggi.getFullYear() ? { year: "numeric" } : {}) });
  };
  // dentro un gruppo le ricerche possono stare in giorni diversi: l'ora sola basta solo per oggi
  const quandoPreciso = (q) => {
    const d = new Date(q);
    if (isNaN(d)) return "";
    const ora = d.toLocaleTimeString(LOCALE, { hour: "2-digit", minute: "2-digit" });
    const g = gruppo(q);
    return g === "Oggi" ? ora : g === "Ieri" ? `ieri, ${ora}` : `${giorno(q)}, ${ora}`;
  };
  // un solo lessico: con una risposta la riga dice quanti documenti; senza, perché non c'è
  const statoFilo = (v) => v.stato === "non avviata" ? "mai avviata" :
    v.stato === "avviata" ? (stato.inCorso && stato.filoRicerca && v.filo && stato.filoRicerca.id === v.filo.id ?
      "in corso" : "senza risposta") : "";
  // un titolo scelto dall'utente (Rinomina) vale più del nome dell'entità
  const rinominata = (v) => v.filo && v.titolo &&
    ![v.domanda, v.dettaglio].filter(Boolean).some((x) => normalizza(x) === normalizza(v.titolo));

  if (filtro) {
    const trovate = voci.filter((v) => normalizza([v.titolo, v.dettaglio, v.domanda].join(" ")).includes(filtro));
    ul.replaceChildren(...trovate.map((v) => voceRecente(v, false)));
    if (!trovate.length) ul.append(el("li", `Nessuna ricerca con «${$("recenti-filtro").value.trim()}».`, "nota"));
    return;
  }
  // i gruppi per entità, nell'ordine dell'ultima ricerca di ciascuna; le domande senza entità restano da sole
  const gruppi = [];
  const perNome = new Map();
  for (const v of voci) {
    const chiave = v.dettaglio && !rinominata(v) ? normalizza(v.dettaglio) : null;
    if (chiave && perNome.has(chiave)) { perNome.get(chiave).push(v); continue; }
    const g = [v];
    if (chiave) perNome.set(chiave, g);
    gruppi.push(g);
  }
  const righe = [];
  let ultimo = null;
  for (const g of gruppi) {
    const d = gruppo(g[0].quando);
    if (d !== ultimo) { righe.push(el("li", d, "gruppo-recenti")); ultimo = d; }
    righe.push(g.length === 1 ? voceRecente(g[0], false) : gruppoEntita(g));
  }
  ul.replaceChildren(...righe);
  if (!voci.length) ul.append(el("li", "Ancora nessuna ricerca.", "nota"));

  // più ricerche sulla stessa entità: il nome con il numero, e sotto le singole ricerche (domanda, stato, data)
  function gruppoEntita(g) {
    const li = el("li", null, "entita-recente");
    const d = el("details");
    d.open = g.some((v) => v.filo && v.filo.id === corrente) || stato.recentiAperti.has(normalizza(g[0].dettaglio));
    d.addEventListener("toggle", () => {
      stato.recentiAperti[d.open ? "add" : "delete"](normalizza(g[0].dettaglio));
    });
    const s = el("summary", null, "voce-recente");
    s.append(el("span", g[0].dettaglio, "titolo"), el("span", `${g.length} ricerche · ultima ${giorno(g[0].quando)}`,
      "dettaglio"));
    const sotto = el("ul", null, "sottovoci");
    sotto.append(...g.map((v) => voceRecente(v, true)));
    d.append(s, sotto);
    li.append(d);
    return li;
  }

  function voceRecente(v, sottovoce) {
    const li = el("li", null, "riga-recente");
    const b = el("button", null, "voce-recente");
    b.type = "button";
    // in testa il nome dell'entità (o il titolo scelto); dentro un gruppo, la domanda: il nome è già sopra
    // «Occorrenze di X» è la domanda che le versioni di prima scrivevano da sole per una ricerca sul solo nome
    const domandaDiversa = v.domanda && normalizza(v.domanda) !== normalizza(v.dettaglio || "") &&
      normalizza(v.domanda) !== normalizza(`Occorrenze di ${v.dettaglio || ""}`) ? v.domanda : "";
    // senza domanda la ricerca trova le menzioni del nome (come dice la pagina vuota); sotto, quello che distingue
    // una ricerca dall'altra: filtri, documenti pertinenti e, dentro un gruppo, giorno e ora
    const testa = rinominata(v) ? v.titolo : sottovoce ? domandaDiversa || "Menzioni" : v.dettaglio || v.titolo;
    const pert = v.pertinenti !== "" && v.pertinenti !== undefined && v.pertinenti !== null ?
      `${v.pertinenti} ${v.pertinenti === "1" ? "documento" : "documenti"}` : "";
    const sf = statoFilo(v);
    if (sf === "mai avviata") li.classList.add("mai-avviata");
    const sotto = [sottovoce ? "" : domandaDiversa, sf, descriviFiltri(v.filtri), pert,
      sottovoce ? quandoPreciso(v.quando) : giorno(v.quando)]
      .filter((x) => x && x !== testa).join(" · ");
    b.append(el("span", testa, "titolo"), el("span", sotto, "dettaglio"));
    const data = new Date(v.quando);
    b.title = [v.titolo, isNaN(data) ? "" : data.toLocaleString(LOCALE, { day: "numeric", month: "long",
      year: "numeric", hour: "2-digit", minute: "2-digit" })].filter(Boolean).join(" · ");
    if (v.filo) {
      b.dataset.id = v.filo.id;
      if (v.filo.id === corrente) b.setAttribute("aria-current", "true");
      b.addEventListener("click", () => apriFilo(v.filo.id));
    } else {
      b.dataset.documento = v.vecchia.documento;
      b.addEventListener("click", () => apriDalloStorico(v.vecchia));
    }
    li.append(b);
    if (v.filo) li.append(...azioniRecente(v, testa));
    return li;
  }
}

// le azioni di una conversazione salvata: un pulsante discreto che apre Rinomina ed Elimina sotto la riga
function azioniRecente(v, nome) {
  const altro = el("button", null, "icona altro-recente");
  altro.type = "button";
  altro.setAttribute("aria-label", `Altre azioni per «${nome}»`);
  altro.setAttribute("aria-expanded", "false");
  altro.title = "Rinomina, elimina";
  altro.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1"/><circle cx="12" ' +
    'cy="12" r="1"/><circle cx="19" cy="12" r="1"/></svg>';
  const pannello = el("div", null, "azioni-recente");
  pannello.hidden = true;
  const chiudi = () => { pannello.hidden = true; altro.setAttribute("aria-expanded", "false"); };
  altro.addEventListener("click", () => {
    const apri = pannello.hidden;
    pannello.hidden = !apri;
    altro.setAttribute("aria-expanded", String(apri));
    if (apri) mostraAzioni();
  });
  pannello.addEventListener("keydown", (e) => { if (e.key === "Escape") { e.stopPropagation(); chiudi(); altro.focus(); } });
  function mostraAzioni() {
    const rinomina = pulsante("Rinomina", mostraCampo);
    const elimina = pulsante("Elimina", async () => {
      if (!await conferma(`Eliminare «${nome}» dai recenti?`, "Si cancella solo la conversazione. Le risposte e i " +
        "passaggi già letti restano nell'archivio del progetto, e una ricerca nuova sulla stessa entità li riusa.",
        "Elimina")) return;
      try {
        await api("/api/filo/elimina", { id: v.filo.id });
        if (stato.thread && stato.thread.id === v.filo.id) nuovoThread();
        annuncia(`«${nome}» eliminata dai recenti.`);
        caricaStorico();
      } catch (e) { avviso(e.message, true); }
    });
    elimina.classList.add("pericolo");
    pannello.replaceChildren(rinomina, elimina);
    rinomina.focus();
  }
  function mostraCampo() {
    const campo = document.createElement("input");
    campo.type = "text";
    campo.value = v.titolo;
    campo.setAttribute("aria-label", "Nuovo nome della conversazione");
    const salva = async () => {
      try {
        await api("/api/filo/rinomina", { id: v.filo.id, titolo: campo.value });
        if (stato.thread && stato.thread.id === v.filo.id) stato.thread.titolo = campo.value.trim();
        caricaStorico();
      } catch (e) { avviso(e.message, true); }
    };
    campo.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); salva(); } });
    pannello.replaceChildren(campo, pulsante("Salva", salva, true), pulsante("Annulla", () => { chiudi(); altro.focus(); }));
    campo.focus();
    campo.select();
  }
  return [altro, pannello];
}

// una risposta di prima dei fili: si apre come filo nuovo, che si salva al primo seguito
function apriDalloStorico(r) {
  nuovoThread();
  segnaCorrente((b) => b.dataset.documento === r.documento);
  const testo = r.domanda || r.entita || r.cartella;
  stato.thread = { entita: r.entita || "", domanda: r.domanda || "", titolo: testo, risposta: r.documento,
    messaggi: [{ tipo: "utente", testo }, { tipo: "risposta", documento: r.documento }] };
  messaggio("utente", el("p", testo));
  messaggioRisposta(r.documento);
}

// filo vuoto: qualche entità recente da cui ripartire
function suggerimenti() {
  const box = $("suggerimenti");
  const visti = new Set();
  const nomi = (stato.recenti || []).map((v) => v.dettaglio).filter((n) => n && !visti.has(n) && visti.add(n)).slice(0, 4);
  // i nomi già cercati: un clic rifà la ricerca delle menzioni (si passa comunque dalla conferma delle forme)
  const chip = nomi.map((n) => {
    const b = pulsanteMsg(n, () => { $("testo").value = n; invia(); }, "chip");
    b.title = `Cerca di nuovo le menzioni di ${n}`;
    return b;
  });
  box.replaceChildren(...(chip.length ? [el("span", "Già cercati:", "suggerimenti-guida"), ...chip] : []));
}

// ------------------------------------------------------------------ importazione
// Tutto nella scheda «Importazioni»: proposta, tabella di revisione modificabile qui (oltre che in Excel),
// prova senza scrivere e importazione. I lavori sono processi indipendenti: la pagina ne segue l'avanzamento
// e, se la chiudi, il lavoro continua (i file restano sul computer: basta il percorso).
const COLONNE_AVANZATE = ["cartella_serie", "sigla", "stato_numero", "volume", "luogo", "editore",
                          "prima_pagina", "da_pagina", "formato", "percorso"];

async function avviaImporta(azione, percorso, prova) {
  if ((azione === "proponi" || azione === "applica") && !percorso) {
    avviso("Indica prima " + (azione === "proponi" ? "la cartella dei documenti." : "la tabella di revisione."), true);
    return;
  }
  if (azione === "proponi") ricorda("cartella", percorso);
  if (azione === "applica" && !prova && $("imp-sovrascrivi").checked) {
    const n = daImportare();
    if (!await conferma("Sostituire i documenti già importati?", `${n} documenti della tabella prendono il posto ` +
      "di quelli già importati con lo stesso nome: testo e metadati di prima non si recuperano dall'interfaccia.",
      "Importa e sostituisci")) return;
  }
  try {
    const r = await api("/api/importa", { azione, percorso, serie: $("imp-serie").value.trim(),
                                          prova: !!prova, sovrascrivi: $("imp-sovrascrivi").checked });
    stato.importaId = r.id;
    stato.tabella = null;
    mostraTabella(null);
    $("imp-stato").textContent = "Lavoro avviato: lo seguo io, non serve che aspetti.";
    seguiImporta(r.id);
  } catch (e) {
    avviso(e.message, true);
  }
}

function importaEsito(r) {
  const e = r.esito || {};
  if (!r.finita) return "";
  if (e.codice === 0) return "Finito.";
  if (e.codice === 2) return "La tabella ha errori da correggere: salva le correzioni e riprova.";
  return `Il lavoro è finito con codice ${e.codice}${e.errore ? ": " + e.errore : ""}.`;
}

function seguiImporta(id) {
  clearTimeout(stato.attesaImporta);
  stato.attesaImporta = setTimeout(async () => {
    let r;
    try {
      r = await api("/api/importa?id=" + encodeURIComponent(id));
    } catch (e) {
      $("imp-stato").textContent = e.message;
      return;
    }
    if (id !== stato.importaId) return;               // un lavoro più recente ha preso il suo posto
    const a = r.avanzamento;
    $("imp-avanzamento").hidden = !a || !!r.finita;
    if (a) $("imp-barra").style.transform =
      `scaleX(${parseInt(avanzamento("imp-avanzamento", (a.fatto / Math.max(1, a.totale)) * 100), 10) / 100})`;
    $("imp-stato").textContent = [r.finita ? "" : (a ? a.testo : "Lavoro in corso…"), importaEsito(r)]
      .filter(Boolean).join(" ");
    const esiti = (r.ultime || []).join("\n");
    $("imp-esiti").textContent = esiti;
    $("imp-esiti").hidden = !esiti;
    if (r.pronta && r.tabella && (!stato.tabella || stato.tabella.tabella !== r.tabella)) caricaTabella(r.tabella);
    if (!r.finita) { seguiImporta(id); return; }
    annuncia("Importazione: " + importaEsito(r), (r.esito || {}).codice !== 0);
    caricaTutto();                                     // i documenti nuovi entrano fra le fonti
  }, 2000);
}

async function caricaTabella(percorso) {
  let t;
  try {
    t = await api("/api/tabella?percorso=" + encodeURIComponent(percorso));
  } catch (e) {
    $("imp-stato").textContent = e.message;
    return;
  }
  stato.tabella = t;
  mostraTabella(t);
}

// righe che la tabella importerebbe (colonna «importa» diversa da no)
function daImportare() {
  const t = stato.tabella;
  return t ? t.righe.filter((r) => !/^\s*no\s*$/i.test(r.importa || "")).length : 0;
}

// un passo alla volta: finché non c'è la tabella, i passi 2 e 3 restano spenti e il pulsante principale è «Proponi»
function passiImporta(conTabella) {
  $("imp-passo-2").classList.toggle("spento", !conTabella);
  $("imp-passo-3").classList.toggle("spento", !conTabella);
  $("imp-proponi").classList.toggle("primario", !conTabella);
  $("imp-applica").classList.toggle("primario", conTabella);
  // anche le caselle dei passi spenti: sembrerebbero usabili, e non fanno nulla finché non c'è la tabella
  for (const id of ["imp-carica", "imp-salva", "imp-prova", "imp-applica", "imp-dubbi", "imp-avanzate",
    "imp-sovrascrivi"]) $(id).disabled = !conTabella;
  etichettaImporta();
}

function etichettaImporta() {
  $("imp-applica").textContent = $("imp-sovrascrivi").checked ? "Importa e sostituisci" : "Importa";
}

function mostraTabella(t) {
  const box = $("imp-tabella");
  box.replaceChildren();
  passiImporta(!!t);
  if (!t) {
    box.hidden = true;
    $("imp-tabella-nome").textContent = "Compare qui quando la proposta è pronta.";
    return;
  }
  const dubbi = t.righe.filter((r) => (r.da_controllare || "").trim()).length;
  $("imp-tabella-nome").textContent = `${t.file}: ${t.righe.length} righe` +
    (t.tipo === "revisione" ? " (documenti già importati)" : "") +
    (dubbi ? `, ${dubbi} da controllare` : "") + ". La colonna «importa» accetta sì o no.";
  const colonne = t.colonne.filter((c) => $("imp-avanzate").checked || !COLONNE_AVANZATE.includes(c));
  const tab = el("table", null, "revisione");
  const intestazione = el("tr");
  for (const c of colonne) intestazione.append(el("th", c));
  tab.append(intestazione);
  t.righe.forEach((riga, n) => {
    const tr = el("tr");
    if ((riga.da_controllare || "").trim()) tr.className = "dubbio";
    else if ($("imp-dubbi").checked) tr.hidden = true;
    for (const c of colonne) {
      const td = el("td");
      const i = document.createElement("input");
      i.type = "text";
      i.value = riga[c] || "";
      i.dataset.colonna = c;
      i.dataset.riga = n;
      i.setAttribute("aria-label", `${c}, riga ${n + 1}`);
      if (["file", "file_dati", "percorso", "da_controllare"].includes(c)) i.readOnly = true;
      td.append(i);
      tr.append(td);
    }
    tab.append(tr);
  });
  const scroll = el("div", null, "scorrimento");
  scroll.append(tab);
  box.append(scroll);
  box.hidden = false;
}

async function salvaTabella() {
  const t = stato.tabella;
  if (!t) return;
  const righe = t.righe.map((riga) => {
    const r = {};
    for (const c of t.colonne) r[c] = riga[c] || "";       // le colonne nascoste restano come sono
    return r;
  });
  // un solo giro sulle celle (prima: tutte le celle per ogni riga, lento con centinaia di righe)
  for (const i of $("imp-tabella").querySelectorAll("input")) righe[+i.dataset.riga][i.dataset.colonna] = i.value.trim();
  try {
    const s = await api("/api/tabella", { percorso: t.tabella, righe });
    const nome = s.tabella !== t.tabella ? ` in ${s.tabella} (il file Excel resta com'era)` : "";
    $("imp-stato").textContent =
      `Tabella salvata${nome} (${s.righe} righe): «Prova senza scrivere», poi «Importa».`;
    await caricaTabella(s.tabella || t.tabella);
  } catch (e) {
    avviso(e.message, true);
  }
}

/// ------------------------------------------------------------------ qualità dell'OCR
// I documenti sospetti, il peggiore per primo: perché (confidenza, parole illeggibili), un'occhiata al testo e, se
// l'originale c'è, «Rifai l'OCR» con le lingue scelte (le installate di Tesseract). Il nuovo testo sostituisce il
// vecchio con un'importazione normale, che si segue sopra come le altre.
async function controllaOcr() {
  const box = $("ocr-esito");
  const b = $("ocr-controlla");
  b.disabled = true;
  box.replaceChildren(el("p", "Controllo i documenti importati…", "nota in-attesa"));
  let r, lingue = [];
  try {
    [r, lingue] = await Promise.all([api("/api/salute-ocr"),
      api("/api/lingue").then((s) => (s.installate || []).filter((c) => c !== "osd"), () => [])]);
  } catch (e) {
    box.replaceChildren(el("p", e.message, "nota attenzione-testo"));
    return;
  } finally {
    b.disabled = false;
  }
  b.textContent = "Controlla di nuovo";
  if (!r.sospetti) {
    box.replaceChildren(el("p", `Nessun documento sospetto tra i ${r.esaminati} esaminati.`, "nota esito-ocr-ok"));
    return;
  }
  const testa = el("p", `${r.sospetti} ${r.sospetti === 1 ? "documento sospetto" : "documenti sospetti"} su ` +
    `${r.esaminati}` + (r.sospetti > r.documenti.length ? ` (qui i ${r.documenti.length} peggiori)` : "") + ".", "nota");
  const ul = el("ul", null, "elenco-ocr");
  for (const d of r.documenti) ul.append(rigaOcr(d, lingue));
  box.replaceChildren(testa, ul);
}

function rigaOcr(d, lingue) {
  const li = el("li");
  const testa = el("div", null, "testa");
  const apri = el("button", d.titolo, "apri-passaggio");
  apri.type = "button";
  apri.title = d.file;
  apri.addEventListener("click", () => apriFonte(d.file, null, "1", null, "ocr"));
  testa.append(apri, el("span", [d.serie, d.lingua].filter(Boolean).join(" · "), "nota"));
  li.append(testa, el("div", d.motivi.join("; "), "motivi-ocr"));
  if (!d.originale) {
    li.append(el("div", "L'originale non è registrato: reimporta il documento dalla tabella.", "nota"));
    return li;
  }
  const riga = el("div", null, "riga");
  const sel = document.createElement("select");
  sel.multiple = false;
  sel.setAttribute("aria-label", `Lingue dell'OCR per ${d.titolo}`);
  const proposte = new Set();
  const attuale = { it: "ita", en: "eng", fr: "fra", de: "deu", es: "spa", pt: "por", sq: "sqi", ru: "rus",
    zh: "chi_sim", el: "ell" }[d.lingua];
  if (attuale && lingue.includes(attuale)) proposte.add(attuale + (attuale !== "eng" && lingue.includes("eng") ? "+eng" : ""));
  for (const c of lingue) proposte.add(c);
  for (const v of proposte) sel.append(new Option(v.replace(/\+/g, " + "), v));
  const rifai = pulsante("Rifai l'OCR", async () => {
    if (!await conferma(`Rifare l'OCR di «${d.titolo}»?`, `Il testo si rifà dall'originale con ${sel.value.replace(/\+/g, " + ")} ` +
      "e sostituisce quello di adesso; serie, data, numero, titolo e autore restano. I passaggi già letti restano " +
      "nell'archivio; la prossima ricerca trova anche le forme che l'OCR vecchio nascondeva.", "Rifai l'OCR")) return;
    rifai.disabled = true;
    try {
      const r = await api("/api/rifai-ocr", { file: d.file, lingue: sel.value });
      stato.importaId = r.id;
      mostraTabella(null);
      $("imp-stato").textContent = `OCR di «${d.titolo}» avviato: lo seguo io, non serve che aspetti.`;
      seguiImporta(r.id);
      li.classList.add("rifatto");
      rifai.textContent = "OCR avviato";
    } catch (e) {
      rifai.disabled = false;
      avviso(e.message, true);
    }
  });
  if (!lingue.length) { sel.disabled = rifai.disabled = true; }
  const l = el("label", "Lingue ");
  l.append(sel);
  riga.append(l, rifai);
  li.append(riga);
  return li;
}

// ------------------------------------------------------------------ conversazione sulle fonti
// Il modello scelto usa gli strumenti del motore; il server confronta ogni citazione della risposta con i risultati
// degli strumenti e ne dà la posizione nel testo: qui diventa un segno verde (trovata) o rosso (non trovata), e un
// clic sulle citazioni di passaggi già letti mostra originale e traduzione.
const STATI_CITAZIONE = {
  "esatta": "Compare così nei risultati degli strumenti",
  "corrispondente": "Un riferimento restituito dagli strumenti ha lo stesso titolo, data e pagina",
  "non trovata": "Nessuno strumento ha restituito questo riferimento: non usarlo senza verificarlo",
};

function testoConCitazioni(testo, citazioni, voce) {
  const div = el("div", null, "testo");
  let pos = 0;
  for (const c of citazioni || []) {
    if (c.inizio < pos) continue;
    div.append(document.createTextNode(testo.slice(pos, c.inizio)));
    const span = el("span", testo.slice(c.inizio, c.fine), "citazione");
    span.title = STATI_CITAZIONE[c.stato] || c.stato;
    if (c.stato === "non trovata") span.classList.add("non-trovata");
    // l'esito non sta solo nel colore: un segno visibile e, per i lettori di schermo, le parole
    const trovata = c.stato !== "non trovata";
    const segno = el("span", null, "segno-citazione");
    segno.setAttribute("aria-hidden", "true");
    segno.innerHTML = trovata ? '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>' :
      '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7.5v5.5M12 16.5v.01"/></svg>';
    span.append(segno, el("span", trovata ? " (citazione verificata)" : " (citazione non trovata nei risultati)",
      "solo-lettori"));
    if (c.passaggio) {
      span.classList.add("con-passaggio");
      span.tabIndex = 0;
      span.setAttribute("role", "button");
      span.setAttribute("aria-expanded", "false");
      span.title += " — clic per il passaggio";
      const apri = () => {
        const aperto = mostraPassaggio(voce, c);
        voce.querySelectorAll(".con-passaggio").forEach((s) => s.setAttribute("aria-expanded", "false"));
        span.setAttribute("aria-expanded", String(aperto));
      };
      span.addEventListener("click", apri);
      span.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); apri(); }
      });
    }
    div.append(span);
    pos = c.fine;
  }
  div.append(document.createTextNode(testo.slice(pos)));
  return div;
}

function mostraPassaggio(voce, c) {
  const vecchio = voce.querySelector(".conv-passaggio");
  const stesso = vecchio && vecchio.dataset.inizio === String(c.inizio);
  if (vecchio) vecchio.remove();
  if (stesso) return false;
  const q = el("blockquote", null, "conv-passaggio");
  q.dataset.inizio = String(c.inizio);
  q.append(el("p", c.riferimento));
  if (c.passaggio.originale) q.append(el("p", c.passaggio.originale));
  if (c.passaggio.traduzione) q.append(el("p", "Traduzione: " + c.passaggio.traduzione));
  if (c.passaggio.data_documento) q.append(el("p", "Data del documento: " + c.passaggio.data_documento, "nota"));
  voce.append(q);
  return true;
}

function messaggioConversazione(m) {
  const voce = el("div", null, "conv-messaggio " + (m.ruolo === "utente" ? "utente" : "modello"));
  if (m.ruolo === "utente") {
    voce.append(el("div", m.testo, "testo"));
    return voce;
  }
  voce.append(testoConCitazioni(m.testo || "", m.citazioni, voce));
  if (m.avviso) voce.append(el("div", m.avviso, "dettagli attenzione-testo"));
  const v = m.verifica || {};
  const trovate = (v.esatte || 0) + (v.corrispondenti || 0);
  const parti = [];
  if (trovate || v.non_trovate) {
    parti.push(`Citazioni: ${trovate} trovate nei risultati degli strumenti` +
      (v.non_trovate ? `, ${v.non_trovate} non trovate (in rosso)` : ""));
  } else {
    parti.push("Nessuna citazione nella risposta.");
  }
  if ((m.strumenti || []).length) {
    parti.push("Strumenti: " + m.strumenti.map((s) => s.nome + (s.azione ? ` (${s.azione})` : "")).join(" › "));
  }
  if (m.modello) parti.push("Modello: " + m.modello);
  voce.append(el("div", parti.join(" · "), "dettagli" + (v.non_trovate ? " attenzione-testo" : "")));
  return voce;
}

// --------------------------------------------- seguito: la conversazione con il modello, nello stesso filo
async function seguito(testo, giaMostrato) {
  const filo = filoCorrente();
  if (!giaMostrato) {
    messaggio("utente", el("p", testo));
    registra(filo, { tipo: "utente", testo });
  }
  const attesa = messaggio("assistente", el("p", "Il modello sta consultando le fonti con gli strumenti…", "nota"));
  let c;
  try {
    if (stato.convNuova) {
      c = await api("/api/conversazione/nuova", {});
      stato.convNuova = false;
      filo.conversato = false;
    } else {
      c = await api("/api/conversazione");
    }
  } catch (e) {
    attesa.replaceChildren(el("p", e.message, "attenzione-testo"));
    return;
  }
  if (!c.attiva) {
    attesa.replaceChildren(el("p", c.motivo || "Conversazione non disponibile.", "attenzione-testo"));
    if (c.riprova) attesa.append(pulsanteMsg("Riprova la verifica del modello", async () => {
      attesa.remove();
      try { await api("/api/conversazione?riprova=1"); } catch (e) { /* il motivo arriva al prossimo tentativo */ }
      seguito(testo, true);
    }, "discreto"));
    return;
  }
  // al primo seguito la conversazione del server riparte: la domanda porta con sé l'entità e la domanda della ricerca
  const contesto = filo.entita && !filo.conversato ?
    `[Ricerca su «${filo.entita}»${filo.domanda ? `, domanda: «${filo.domanda}»` : ""}] ` : "";
  try {
    const voce = await api("/api/conversazione", { testo: contesto + testo });
    filo.conversato = true;
    attesa.replaceWith(rispostaConversazione(voce));
    registra(filo, { tipo: "conversazione", voce });
    // una ricerca avviata dalla conversazione si segue nel filo
    if ((voce.strumenti || []).some((s) => s.nome === "ricerca" && s.azione === "avvia")) {
      await mostraRicerca(await api("/api/ricerca"), false);
    }
  } catch (e) {
    attesa.replaceChildren(el("p", e.message, "attenzione-testo"));
  }
  scorriInFondo();
}

function rispostaConversazione(m) {
  const voce = messaggioConversazione(m);
  voce.className = "msg assistente conversazione conv-messaggio";
  return voce;
}

// Il corpo del documento nella pagina: documento.py scrive tutto con escape; qui si tolgono comunque script,
// stili e attributi on*, e gli id prendono un prefisso (nel filo possono esserci più risposte).
function inserisciDocumento(corpo, html) {
  const d = new DOMParser().parseFromString(`<body>${html}</body>`, "text/html");
  d.querySelectorAll("script, style, iframe, object, embed, link, meta, form").forEach((x) => x.remove());
  d.querySelectorAll("*").forEach((x) => [...x.attributes].forEach((a) => {
    if (/^on/i.test(a.name) || (a.name === "href" && !a.value.startsWith("#")) || a.name === "src") x.removeAttribute(a.name);
  }));
  const pref = "r" + (++stato.nDocumenti);
  d.querySelectorAll("[id]").forEach((x) => { x.id = `${pref}-${x.id}`; });
  d.querySelectorAll("a[href^='#']").forEach((a) => a.setAttribute("href", `#${pref}-${a.getAttribute("href").slice(1)}`));
  corpo.append(...d.body.childNodes);
  return pref;
}

// anteprima di un rimando [n]: il riferimento e l'inizio della traduzione del passaggio, presi dal documento stesso
function mostraAnteprima(a, v, radice, pref, n) {
  const box = $("anteprima");
  const parti = [el("p", senzaMarkdown(v.riferimento).replace(/[.\s]+$/, "") + (v.pagina ? `, p. ${v.pagina}` : ""),
    "riferimento")];
  const h = radice.querySelector(`#${pref}-doc-${n}`);
  for (let s = h && h.nextElementSibling; s && !/^H[1-3]$/.test(s.tagName); s = s.nextElementSibling) {
    const t = s.textContent.trim();
    if (s.tagName === "P" && t.startsWith("Traduzione:")) {
      const testo = t.replace(/^Traduzione:\s*/, "");
      parti.push(el("p", testo.length > 320 ? testo.slice(0, 320).replace(/\s+\S*$/, "") + "…" : testo));
      break;
    }
  }
  parti.push(el("p", "Clic: apri la pagina della fonte", "etichetta"));
  clearTimeout(stato.attesaAnteprima);
  // appena chiusa un'altra anteprima (si scorre lungo i rimandi) questa arriva senza movimento
  box.classList.toggle("subito", Date.now() - (stato.anteprimaChiusa || 0) < ANTEPRIMA_CATENA);
  box.replaceChildren(...parti);
  box.hidden = false;
  const r = a.getBoundingClientRect();
  const larga = box.offsetWidth;
  const alta = box.offsetHeight;
  const sopra = r.top - alta - 8 > 8;
  const sinistra = Math.max(8, Math.min(r.left, innerWidth - larga - 8));
  box.style.left = sinistra + "px";
  box.style.top = (sopra ? r.top - alta - 8 : r.bottom + 8) + "px";
  box.style.transformOrigin = `${Math.round(r.left + r.width / 2 - sinistra)}px ${sopra ? "100%" : "0"}`;
  a.setAttribute("aria-describedby", "anteprima");
}

// col mouse la prima anteprima aspetta un attimo (passare sopra un rimando non basta ad aprirla); le successive,
// a catena, si aprono subito
const ANTEPRIMA_ATTESA = 300;
const ANTEPRIMA_CATENA = 400;
function anteprimaDopo(mostraA) {
  clearTimeout(stato.attesaAnteprima);
  if (Date.now() - (stato.anteprimaChiusa || 0) < ANTEPRIMA_CATENA) mostraA();
  else stato.attesaAnteprima = setTimeout(mostraA, ANTEPRIMA_ATTESA);
}

function nascondiAnteprima() {
  clearTimeout(stato.attesaAnteprima);
  if (!$("anteprima").hidden) stato.anteprimaChiusa = Date.now();
  $("anteprima").hidden = true;
  document.querySelectorAll("[aria-describedby=anteprima]").forEach((x) => x.removeAttribute("aria-describedby"));
}

// ------------------------------------------------- fili salvati: ogni messaggio si scrive sul server (results/fili)
function filoCorrente() {
  if (!stato.thread) stato.thread = { messaggi: [] };
  return stato.thread;
}

function registra(filo, voce) {
  (filo.messaggi = filo.messaggi || []).push(voce);
  filo.titolo = filo.titolo || filo.domanda || filo.entita || (voce.tipo === "utente" ? voce.testo.slice(0, 120) : "");
  // una domanda sola non si salva: il filo entra nei recenti quando parte una ricerca o arriva una risposta,
  // così le prove lasciate a metà non riempiono la barra
  if (!filo.id && voce.tipo === "utente" && !filo.avviata && !filo.risposta) return;
  salvaFilo(filo);
}

// i salvataggi vanno in fila: il primo assegna l'id, i successivi riscrivono lo stesso file
function salvaFilo(filo) {
  stato.codaSalvataggi = stato.codaSalvataggi.then(async () => {
    const nuovo = !filo.id;
    try {
      const r = await api("/api/filo", { filo });
      Object.assign(filo, { id: r.id, creato: r.creato, aggiornato: r.aggiornato });
      if (nuovo) caricaStorico();
    } catch (e) {
      avviso("Conversazione non salvata: " + e.message, true);
    }
  });
  return stato.codaSalvataggi;
}

async function apriFilo(id) {
  // subito un segno che la ricerca si sta aprendo: il file del filo può arrivare dopo un attimo
  segnaCorrente((b) => b.dataset.id === id);
  mostraVista("thread");
  mostra("vuoto", false);
  $("messaggi").replaceChildren(el("p", "Apro la ricerca…", "nota in-attesa apertura-filo"));
  let f;
  try { f = await api("/api/filo?id=" + encodeURIComponent(id)); } catch (e) {
    $("messaggi").replaceChildren();
    mostra("vuoto", true);
    avviso(e.message, true);
    return;
  }
  nuovoThread();
  segnaCorrente((b) => b.dataset.id === id);
  stato.thread = f;
  // i messaggi di un filo salvato erano già lì: entrano senza animazione (la classe resta fino al disegno)
  const elenco = $("messaggi");
  elenco.classList.add("ripristino");
  requestAnimationFrame(() => requestAnimationFrame(() => elenco.classList.remove("ripristino")));
  for (const m of f.messaggi) {
    if (m.tipo === "utente") messaggio("utente", el("p", m.testo));
    else if (m.tipo === "risposta") { messaggioRisposta(m.documento, m.pertinenti); f.risposta = m.documento; }
    else if (m.tipo === "conversazione") messaggio("assistente").replaceWith(rispostaConversazione(m.voce));
  }
  // un filo riaperto si legge dall'ultima domanda in giù (la risposta arriva sotto e non sposta la vista); in
  // fondo si va solo seguendo una ricerca o una conversazione dal vivo
  const domande = $("messaggi").querySelectorAll(".msg.utente");
  const ultima = domande[domande.length - 1];
  if (ultima) requestAnimationFrame(() => {
    const t = $("vista-thread");
    t.scrollTop = Math.max(0, t.scrollTop + ultima.getBoundingClientRect().top - t.getBoundingClientRect().top - 16);
  });
  else scorriInFondo();
  return f;
}

function segnaCorrente(prova) {
  document.querySelectorAll("#storico button").forEach((b) => {
    if (prova(b)) b.setAttribute("aria-current", "true");
    else b.removeAttribute("aria-current");
  });
}

//// ------------------------------------------------------------------ consumo: richieste e token
// Accanto al modello, quante richieste e quanti token il progetto ha usato oggi (system/usage.jsonl, scritto a ogni
// risposta del modello). Un clic apre il dettaglio per modello e la settimana. Prima di avviare, il riepilogo dice
// quante richieste costerà la lettura, dai lotti della configurazione.
function numeroBreve(n) {
  n = Number(n) || 0;
  if (n < 1000) return String(n);
  if (n < 1e6) return (n / 1000).toFixed(n < 1e4 ? 1 : 0).replace(".", ",") + " mila";
  return (n / 1e6).toFixed(1).replace(".", ",") + " mln";
}

// i passaggi nuovi si smistano a lotti; i pertinenti (non si sa quanti prima) si leggono a lotti più piccoli; poi
// una o due richieste per la risposta. Da qui una forbice, non un numero solo
function stimaRichieste(righe, p) {
  const lotti = stato.consumo && stato.consumo.lotti;
  if (!lotti || !righe) return "";
  const nuovi = Math.max(0, righe - ((p && p.letti) || 0));
  if (!nuovi) return "poche: i passaggi sono già letti, resta la risposta";
  const min = Math.ceil(nuovi / Math.max(1, lotti.smistamento)) + 1;
  const max = min + Math.ceil(nuovi / Math.max(1, lotti.analisi)) + 1;
  return `da ${min} a ${max} al modello (lotti di ${lotti.smistamento} passaggi)`;
}

async function aggiornaConsumo() {
  let r;
  try { r = await api("/api/consumo"); } catch (e) { return; }
  stato.consumo = r;
  const b = $("consumo");
  const o = r.oggi;
  b.hidden = !o;
  if (!o) return;
  const token = o.ingresso + o.uscita;
  $("consumo-breve").textContent = o.richieste ? `${numeroBreve(o.richieste)} ${o.richieste === 1 ? "richiesta" : "richieste"} oggi` : "nessuna richiesta oggi";
  $("consumo-sommario").setAttribute("aria-label", `Consumo di oggi: ${o.richieste} richieste, ${token} token. Dettagli`);
  const d = $("consumo-dettaglio");
  d.replaceChildren();
  const dl = el("dl", null, "riepilogo");
  dl.append(el("dt", "Oggi"), el("dd", `${o.richieste} richieste · ${numeroBreve(o.ingresso)} token letti, ` +
    `${numeroBreve(o.uscita)} scritti` + (o.cache ? ` · ${numeroBreve(o.cache)} dalla cache` : "")));
  const s = r.settimana;
  if (s) dl.append(el("dt", "7 giorni"), el("dd", `${s.richieste} richieste · ${numeroBreve(s.ingresso + s.uscita)} token`));
  d.append(dl);
  const servizi = Object.entries(r.per_servizio || {}).sort((a, b) => b[1].richieste - a[1].richieste);
  if (servizi.length) {
    d.append(el("h4", "Oggi per modello"));
    const ul = el("ul", null, "consumo-servizi");
    for (const [nome, v] of servizi) {
      const li = el("li");
      li.append(el("span", nomeModello(nome), "nome"), el("span", `${v.richieste} · ${numeroBreve(v.ingresso + v.uscita)} token`, "conto"));
      ul.append(li);
    }
    d.append(ul);
  }
  d.append(el("p", "I piani gratuiti hanno limiti al giorno e al minuto: quando finiscono, la ricerca aspetta e " +
    "riprende da sola. Con un servizio a consumo, il costo segue i token.", "nota"));
}

// ------------------------------------------------------------------ comandi (Ctrl+K) e scorciatoie
// Una casella sola per arrivare ovunque: azioni, ricerche recenti, schede del glossario (avviano la ricerca),
// progetti. Si filtra scrivendo (senza accenti né maiuscole), frecce e Invio come in un menu.
function editabile(t) {
  return !!(t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName)));
}

function vociComandi() {
  const voci = [];
  const azione = (testo, dettaglio, fa, tasto) => voci.push({ gruppo: "Azioni", testo, dettaglio, fa, tasto });
  azione("Nuova ricerca", "", () => { nuovoThread(); $("testo").focus(); }, "Ctrl+N");
  azione("Importa fonti", "PDF, scansioni, testi", () => mostraVista("importazioni"));
  azione("Impostazioni", "progetti, modelli, lingue", () => apriImpostazioniRicordate(), "Ctrl+,");
  azione("Glossario", "schede delle entità e serie", () => apriLaterale("glossario"));
  if (stato.doc) azione("Passaggi della risposta aperta", "", () => apriLaterale("passaggi"));
  azione("Mostra o nascondi la barra laterale", "", () => barraLaterale($("app").classList.contains("barra-chiusa")), "Ctrl+B");
  azione("Controlla la qualità dell'OCR", "documenti con un testo sospetto", () => { mostraVista("importazioni"); controllaOcr(); });
  azione("Scorciatoie da tastiera", "", apriTasti, "?");
  document.querySelectorAll("#storico button.voce-recente").forEach((b) => {
    const titolo = b.querySelector(".titolo");
    const det = b.querySelector(".dettaglio");
    voci.push({ gruppo: "Recenti", testo: titolo ? titolo.textContent : b.textContent,
      dettaglio: det ? det.textContent : "", fa: () => b.click() });
  });
  for (const s of (stato.glossario && stato.glossario.schede) || []) {
    voci.push({ gruppo: "Schede", testo: s.nome, dettaglio: "cerca nelle fonti", fa: () => {
      if (stato.inCorso) { avviso("C'è già una ricerca in corso: aspetta che finisca.", true); return; }
      nuovoThread();
      $("testo").value = s.nome;
      invia();
    } });
  }
  for (const p of stato.progetti || []) {
    voci.push({ gruppo: "Progetti", testo: p.nome, dettaglio: p.in_uso ? "in uso" : "passa a questo progetto",
      fa: () => { if (!p.in_uso) cambiaProgetto(p); } });
  }
  return voci;
}

async function apriComandi() {
  const d = $("d-comandi");
  if (d.open) return;
  stato.comandiDa = document.activeElement;
  if (!stato.glossario) caricaGlossario().then(() => d.open && filtraComandi()).catch(() => {});
  $("cm-cerca").value = "";
  d.showModal();
  filtraComandi();
  $("cm-cerca").focus();
}

function filtraComandi() {
  const q = normalizza($("cm-cerca").value.trim());
  const parole = q.split(/\s+/).filter(Boolean);
  const voci = vociComandi().filter((v) => {
    const t = normalizza(`${v.testo} ${v.dettaglio} ${v.gruppo}`);
    return parole.every((p) => t.includes(p));
  });
  // senza testo: le azioni e i primi recenti; con il testo, i primi risultati di ogni gruppo
  const perGruppo = {};
  const mostrate = voci.filter((v) => (perGruppo[v.gruppo] = (perGruppo[v.gruppo] || 0) + 1) <= (q ? 8 : v.gruppo === "Azioni" ? 10 : 5));
  const ul = $("cm-elenco");
  ul.replaceChildren();
  let gruppo = "";
  mostrate.forEach((v, i) => {
    if (v.gruppo !== gruppo) {
      gruppo = v.gruppo;
      const t = el("li", gruppo, "gruppo-comandi");
      t.setAttribute("role", "presentation");
      ul.append(t);
    }
    const li = el("li", null, "comando");
    li.id = "cm-" + i;
    li.setAttribute("role", "option");
    li.append(el("span", v.testo, "testo-comando"));
    if (v.dettaglio) li.append(el("span", v.dettaglio, "dettaglio-comando"));
    if (v.tasto) li.append(el("kbd", v.tasto));
    li.addEventListener("pointerdown", (e) => e.preventDefault());       // il fuoco resta nella casella
    li.addEventListener("click", () => eseguiComando(v));
    li._voce = v;
    ul.append(li);
  });
  if (!mostrate.length) ul.append(el("li", "Nessun risultato.", "nota vuoto-comandi"));
  scegliComando(0);
}

function scegliComando(i) {
  const opzioni = [...$("cm-elenco").querySelectorAll("li.comando")];
  opzioni.forEach((o, k) => o.setAttribute("aria-selected", String(k === i)));
  const scelta = opzioni[i];
  if (scelta) {
    $("cm-cerca").setAttribute("aria-activedescendant", scelta.id);
    scelta.scrollIntoView({ block: "nearest" });
  } else {
    $("cm-cerca").removeAttribute("aria-activedescendant");
  }
}

function tastiComandi(e) {
  const opzioni = [...$("cm-elenco").querySelectorAll("li.comando")];
  const i = opzioni.findIndex((o) => o.getAttribute("aria-selected") === "true");
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    if (opzioni.length) scegliComando((i + (e.key === "ArrowDown" ? 1 : -1) + opzioni.length) % opzioni.length);
  } else if (e.key === "Enter") {
    e.preventDefault();
    if (opzioni[i]) eseguiComando(opzioni[i]._voce);
  }
}

function eseguiComando(v) {
  $("d-comandi").close();
  v.fa();
}

function apriTasti() {
  const d = $("d-tasti");
  if (!d.open) d.showModal();
}

// «/» porta nella casella della domanda, «?» mostra le scorciatoie (fuori dai campi di testo)
function tastiGlobali(e) {
  if (document.querySelector("dialog[open]") || e.ctrlKey || e.metaKey || e.altKey || editabile(e.target)) return;
  if (e.key === "/") {
    e.preventDefault();
    mostraVista("thread");
    $("testo").focus();
  } else if (e.key === "?") {
    e.preventDefault();
    apriTasti();
  }
}

// ------------------------------------------------------------------ avvio
document.addEventListener("DOMContentLoaded", () => {
  if (ricordato("barra") === "chiusa") barraLaterale(false);
  $("b-barra").addEventListener("click", () => {
    stato.barraDaRiaprirePannello = false;          // una scelta a mano vale più della chiusura automatica
    barraLaterale($("app").classList.contains("barra-chiusa"));
  });
  // gli anni: solo cifre, al massimo quattro (il campo non accetta altro, invece di rifiutarlo all'avvio)
  for (const id of ["dal", "al"]) {
    $(id).addEventListener("input", (e) => {
      const pulito = e.target.value.replace(/\D/g, "").slice(0, 4);
      if (pulito !== e.target.value) e.target.value = pulito;
    });
  }
  $("recenti-filtro").addEventListener("input", disegnaRecenti);
  $("recenti-filtro").addEventListener("keydown", (e) => {
    if (e.key === "Escape" && e.target.value) { e.stopPropagation(); e.target.value = ""; disegnaRecenti(); }
  });
  preparaManiglia("barra");
  preparaManiglia("laterale");
  window.addEventListener("resize", rispettaLarghezze);
  sceltaConConferma($("progetto"), sceltaProgetto);
  $("b-nuovo-progetto").addEventListener("click", apriNuovoProgetto);
  $("b-modelli").addEventListener("click", () => apriImpostazioni("modelli"));
  $("cfg-nuovo-progetto").addEventListener("click", apriNuovoProgetto);
  sceltaConConferma($("modello"), sceltaModello);
  // Invio nei campi preme il primo pulsante d'invio del modulo: per questo Annulla e Chiudi sono pulsanti semplici
  $("np-crea").addEventListener("click", creaProgetto);
  $("np-annulla").addEventListener("click", () => $("d-progetto").close());
  $("am-chiudi").addEventListener("click", () => $("d-modello").close());
  $("am-servizio").addEventListener("change", scegliServizio);
  $("am-elenca").addEventListener("click", elencaModelli);
  $("am-aggiungi").addEventListener("click", aggiungiModello);
  // la casella: Invio invia, Maiusc+Invio va a capo; si allunga con il testo
  $("composer").addEventListener("submit", invia);
  $("testo").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); invia(); }
  });
  $("testo").addEventListener("input", autoAltezza);
  $("b-filtri").addEventListener("click", alternaFiltri);
  $("filtri").addEventListener("change", riassumiFiltri);
  $("filtri").addEventListener("input", riassumiFiltri);
  $("b-ferma").addEventListener("click", ferma);
  $("b-nuova").addEventListener("click", nuovoThread);
  $("b-importa").addEventListener("click", () => mostraVista("importazioni"));
  document.querySelectorAll(".torna-thread").forEach((b) => b.addEventListener("click", () => { mostraVista("thread"); $("testo").focus(); }));
  document.querySelectorAll("[data-pannello-apri]").forEach((b) =>
    b.addEventListener("click", () => alternaLaterale(b.dataset.pannelloApri)));
  $("b-chiudi-laterale").addEventListener("click", chiudiLaterale);
  $("b-chiudi-avviso").addEventListener("click", () => { avviso(""); $("testo").focus(); });
  // ciò che si apre da tastiera arriva senza movimento (app.css, html[data-tastiera]): si segna l'ultimo modo d'uso
  document.addEventListener("keydown", (e) => {
    if (!["Shift", "Control", "Alt", "Meta"].includes(e.key)) document.documentElement.dataset.tastiera = "";
  }, true);
  document.addEventListener("pointerdown", () => { delete document.documentElement.dataset.tastiera; }, true);
  document.addEventListener("keydown", tastiFinestra);
  document.addEventListener("keydown", tastiGlobali);
  // un menu Esporta aperto si chiude con un clic altrove
  document.addEventListener("click", (e) => {
    document.querySelectorAll("details.menu-esporta[open]").forEach((d) => { if (!d.contains(e.target)) d.open = false; });
  });
  $("cm-cerca").addEventListener("input", filtraComandi);
  $("cm-cerca").addEventListener("keydown", tastiComandi);
  $("d-comandi").addEventListener("click", (e) => { if (e.target === $("d-comandi")) $("d-comandi").close(); });
  $("d-comandi").addEventListener("close", () => {
    const da = stato.comandiDa;
    if (da && da.isConnected && document.activeElement === document.body) da.focus();
  });
  $("imp-sfoglia").addEventListener("click", sfogliaCartella);
  $("ocr-controlla").addEventListener("click", controllaOcr);
  $("cfg-lingua").value = window.Lingua ? window.Lingua.lingua : "it";
  $("cfg-lingua").addEventListener("change", () => window.Lingua && window.Lingua.scegli($("cfg-lingua").value));
  $("imp-cartella").value = ricordato("cartella");
  $("imp-sovrascrivi").addEventListener("change", etichettaImporta);
  $("imp-dubbi").addEventListener("change", () => stato.tabella && mostraTabella(stato.tabella));
  $("passaggi-pertinenti").addEventListener("change", filtraPassaggi);
  $("passaggi-citati").addEventListener("change", filtraPassaggi);
  $("passaggi-azzera").addEventListener("click", azzeraFaccette);
  $("p-passaggi").addEventListener("keydown", tastiPassaggi);
  $("av-guida").addEventListener("click", () => api("/api/guida", {}).catch((e) => avviso(e.message, true)));
  $("imp-proponi").addEventListener("click", () => avviaImporta("proponi", $("imp-cartella").value.trim()));
  $("imp-rivedi").addEventListener("click", () => avviaImporta("rivedi", ""));
  $("imp-carica").addEventListener("click", () => stato.tabella && caricaTabella(stato.tabella.tabella));
  $("imp-salva").addEventListener("click", salvaTabella);
  $("imp-avanzate").addEventListener("change", () => stato.tabella && mostraTabella(stato.tabella));
  $("imp-prova").addEventListener("click", () => stato.tabella && avviaImporta("applica", stato.tabella.tabella, true));
  $("imp-applica").addEventListener("click", () => stato.tabella && avviaImporta("applica", stato.tabella.tabella));
  document.querySelectorAll(".schede button").forEach((b) => b.addEventListener("click", () => apriScheda(b.dataset.scheda)));
  document.querySelector(".schede").addEventListener("keydown", tastiSchede);
  $("fonte-prima").addEventListener("click", () => sfoglia(-1));
  $("fonte-dopo").addEventListener("click", () => sfoglia(1));
  $("fonte-pagine").addEventListener("change", () => stato.fonte && apriFonte(stato.fonte.file, null, $("fonte-pagine").value));
  $("p-fonte").addEventListener("keydown", tastiFonte);
  $("fonte-viste").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) vistaFonte(b.dataset.vista); });
  $("fonte-meno").addEventListener("click", () => zoomFonte((stato.fonteZoom || 1) / 1.25));
  $("fonte-piu").addEventListener("click", () => zoomFonte((stato.fonteZoom || 1) * 1.25));
  $("fonte-adatta").addEventListener("click", () => zoomFonte(1));
  // Ctrl + rotella ingrandisce attorno al puntatore; la rotella sola scorre la pagina
  $("fonte-foglio").addEventListener("wheel", (e) => {
    if (!e.ctrlKey && !e.metaKey) return;
    e.preventDefault();
    const b = $("fonte-foglio").getBoundingClientRect();
    zoomFonte((stato.fonteZoom || 1) * (e.deltaY < 0 ? 1.15 : 1 / 1.15), { x: e.clientX - b.left, y: e.clientY - b.top });
  }, { passive: false });
  $("passaggi-filtro").addEventListener("input", filtraPassaggi);
  $("gl-filtro").addEventListener("input", filtraGlossario);
  $("b-impostazioni").addEventListener("click", apriImpostazioniRicordate);
  document.querySelector(".cfg-nav").addEventListener("keydown", tastiImpostazioni);
  document.querySelectorAll(".cfg-nav [data-sezione]").forEach((b) =>
    b.addEventListener("click", () => mostraSezione(b.dataset.sezione)));
  $("cfg-aggiungi-fornitore").addEventListener("click", () => apriAggiungiModello("openai"));
  $("cfg-ricontrolla").addEventListener("click", caricaAmbiente);
  $("av-lingua-scarica").addEventListener("click", () => {
    const c = $("av-lingua").value.trim();
    if (c) scaricaLingue([c]);
  });
  stato.convNuova = true;
  $("testo").focus();
  // il contatore dei consumi: all'avvio e ogni minuto, se la finestra si vede
  aggiornaConsumo();
  setInterval(() => { if (!document.hidden) aggiornaConsumo(); }, 60000);
  $("consumo").addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $("consumo").open) { e.stopPropagation(); $("consumo").open = false; $("consumo-sommario").focus(); }
  });
  document.addEventListener("click", (e) => { if ($("consumo").open && !$("consumo").contains(e.target)) $("consumo").open = false; });
  // un collegamento a un passaggio (la tabella CSV esportata): /?fonte=<file>&riga=<n> apre la fonte
  const q = new URLSearchParams(location.search);
  if (q.get("fonte")) {
    apriFonte(q.get("fonte"), q.get("riga") || null, null, null, "passaggi");
    history.replaceState(null, "", "/");
  }
  // al primo avvio (o se manca il progetto o il modello) la preparazione si apre da sé
  caricaTutto().then(() => api("/api/avvio")).then((r) => { if (!r.completo) apriImpostazioni("generale"); })
    .catch(() => {});
});

// Interfaccia di Pressmark (lavoro 35; come client di chat dal lavoro 41): barra laterale, filo della ricerca con la
// casella in basso, pannello laterale per fonte, passaggi e glossario.
// Tutto passa dalle API di app.py; i testi delle fonti si inseriscono sempre come testo, mai come HTML. L'unica
// eccezione è il corpo del documento della risposta, scritto da documento.py con escape e ripulito in inserisciDocumento.
"use strict";

const $ = (id) => document.getElementById(id);
const stato = { attesa: null, attesaImporta: null, ultimaRisposta: "", doc: null, cachePassaggi: {}, glossario: null,
  fonte: null, thread: null, ricercaEl: null, filoRicerca: null, inCorso: false, convNuova: true, attesaChi: null,
  recenti: [], fili: [], nDocumenti: 0, codaSalvataggi: Promise.resolve(), elenchi: {}, filtroElenco: {},
  elencoIntero: {}, azioniProfilo: null, rinomina: null };

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
  const uguale = !a.hidden && a.textContent === testo && a.classList.contains("errore") === errore;
  a.textContent = testo || "";
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
// La pagina è un client di chat: a sinistra la barra (progetto, recenti, glossario, importazioni, preparazione),
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
}

function apriLaterale(nome) {
  mostra("laterale", true);
  apriScheda(nome);
}

function chiudiLaterale() {
  if ($("laterale").hidden) return;
  const dentro = $("laterale").contains(document.activeElement);
  mostra("laterale", false);
  if (dentro) $("testo").focus();
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
  if (ctrl && e.key.toLowerCase() === "n") { e.preventDefault(); nuovoThread(); }
  else if (ctrl && e.key.toLowerCase() === "b") { e.preventDefault(); barraLaterale($("app").classList.contains("barra-chiusa")); }
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

// ------------------------------------------------------------------ fonte, passaggi, glossario (lavoro 36)
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
  const chiudi = (h, testo) => {
    const det = el("details");
    det.append(el("summary", testo), ...sezione(h));
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
    a.addEventListener("click", (e) => { e.preventDefault(); nascondiAnteprima(); apri(v, v.pagina); });
    const mostraA = () => mostraAnteprima(a, v, radice, pref, n);
    a.addEventListener("mouseenter", mostraA);
    a.addEventListener("focus", mostraA);
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
  $("fonte-citazione").textContent = senzaMarkdown(r.citazione);
  const sel = $("fonte-pagine");
  sel.replaceChildren(...r.pagine.map((p, i) => new Option(`${p.etichetta} (${i + 1}/${r.pagine.length})`, i + 1)));
  sel.value = String(r.pagina);
  $("fonte-prima").disabled = r.pagina <= 1;
  $("fonte-dopo").disabled = r.pagina >= r.pagine.length;

  // la pagina dell'originale è la vista principale; il testo trascritto resta sotto, chiuso se c'è l'immagine
  const img = $("fonte-img");
  if (r.immagine && img.getAttribute("src") !== r.immagine) img.src = r.immagine;
  img.hidden = !r.immagine;
  img.alt = `Pagina ${r.pagine[r.pagina - 1].etichetta} dell'originale`;
  const trascrizione = $("fonte-trascrizione");
  if (!r.immagine || !stato.fonteAperta) trascrizione.open = !r.immagine;
  $("fonte-trascrizione-titolo").textContent = r.immagine ? "Testo trascritto" :
    "Testo trascritto (l'originale non è un PDF disponibile)";

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

  // il passaggio citato, sopra l'immagine: la riga evidenziata e le due che seguono, per ritrovarlo sulla pagina
  const estratto = $("fonte-estratto");
  estratto.replaceChildren();
  if (evidenziata) {
    const i = r.righe.findIndex((x) => x.n === r.evidenzia);
    const testo = r.righe.slice(i, i + 3).map((x) => x.testo).filter((t) => t.trim() && !/^\s*\[\[/.test(t));
    estratto.append(el("span", `Riga ${r.evidenzia}`, "etichetta"), el("p", testo.join(" ")));
  }
  estratto.hidden = !evidenziata || !r.immagine;

  apriLaterale("fonte");
  // aperta dalla tastiera, il fuoco era su un pulsante ora nascosto (passaggi) o dentro il documento: passa al visore
  const fuoco = document.activeElement;
  if ((fuoco && fuoco.tagName === "IFRAME") || (fuoco && fuoco !== document.body && !fuoco.offsetParent)) {
    $("p-fonte").focus({ preventScroll: true });
  }
  if (evidenziata && trascrizione.open && !r.immagine) evidenziata.scrollIntoView({ block: "center" });
  else $("p-fonte").scrollTop = 0;
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
    $("passaggi-nota").textContent = "Apri una risposta (o una ricerca dai recenti): qui compaiono i suoi passaggi.";
    return;
  }
  let r;
  try { r = await datiPassaggi(); } catch (e) { $("passaggi-nota").textContent = e.message; return; }
  const ricerca = !!stato.doc.ricerca;
  const documenti = new Set(r.passaggi.map((p) => p.file)).size;
  $("passaggi-nota").textContent = ricerca
    ? `${r.passaggi.length} passaggi letti in questa ricerca, in ${documenti} documenti.`
    : `${r.passaggi.length} passaggi citati nella risposta.`;
  mostra("passaggi-strumenti", r.passaggi.length > 0);
  $("passaggi-pertinenti").closest("label").hidden = !ricerca;
  // per una ricerca: un gruppo per documento (la citazione una volta sola), poi i suoi passaggi
  const colonne = ricerca
    ? [["pagina", "Pagina"], ["pertinente", "Pertinente"], ["traduzione", "Traduzione"], ["letto_da", "Letto da"]]
    : [["n", "n."], ["fonte", "Fonte"]];
  const testa = el("tr");
  for (const [, nome] of colonne) testa.append(el("th", nome));
  const corpo = document.createElement("tbody");
  let gruppo = null;
  r.passaggi.forEach((p) => {
    if (ricerca && p.file !== (gruppo && gruppo.dataset.file)) {
      gruppo = el("tr", null, "gruppo");
      gruppo.dataset.file = p.file;
      const th = el("th", null);
      th.colSpan = colonne.length;
      th.scope = "colgroup";
      th.append(el("span", senzaMarkdown(p.fonte)), el("span", p.data || "", "etichetta"));
      gruppo.append(th);
      corpo.append(gruppo);
    }
    const tr = el("tr");
    const apri = () => apriFonte(p.file, p.riga, null, null, "passaggi");
    for (const [k] of colonne) {
      const td = el("td");
      if (k === "pagina" || k === "fonte") {        // il pulsante porta la riga anche alla tastiera
        const etichetta = k === "fonte" ? senzaMarkdown(p.fonte) : p.pagina ? `p. ${p.pagina}` : `riga ${p.riga}`;
        const b = el("button", etichetta, "apri-passaggio");
        b.type = "button";
        b.addEventListener("click", (e) => { e.stopPropagation(); apri(); });
        td.append(b);
      } else if (k === "traduzione") {              // quattro righe; il testo intero al passaggio del mouse
        td.className = "traduzione";
        td.append(el("div", p[k] || "", "taglia"));
        td.title = p[k] || "";
      } else if (k === "letto_da") {                // l'ultimo pezzo dell'identificativo; quello intero nel titolo
        td.textContent = (p[k] || "").split("/").pop();
        td.title = p[k] || "";
        td.className = "letto-da";
      } else {
        td.textContent = p[k] || "";
      }
      tr.append(td);
    }
    if (ricerca && p.pertinente !== "sì") tr.classList.add("no");
    tr.dataset.cerca = Object.values(p).join(" ").toLowerCase();
    tr.dataset.file = p.file;
    tr.addEventListener("click", apri);
    corpo.append(tr);
  });
  const intestazione = document.createElement("thead");
  intestazione.append(testa);
  t.replaceChildren(intestazione, corpo);
  filtraPassaggi();
}

function filtraPassaggi() {
  const f = $("passaggi-filtro").value.trim().toLowerCase();
  const solo = $("passaggi-pertinenti").checked && !!(stato.doc && stato.doc.ricerca);
  const visibili = new Set();
  $("passaggi-tabella").querySelectorAll("tbody tr:not(.gruppo)").forEach((tr) => {
    tr.hidden = (!!f && !tr.dataset.cerca.includes(f)) || (solo && tr.classList.contains("no"));
    if (!tr.hidden) visibili.add(tr.dataset.file);
  });
  $("passaggi-tabella").querySelectorAll("tbody tr.gruppo").forEach((g) => { g.hidden = !visibili.has(g.dataset.file); });
}

async function caricaGlossario() {
  if (stato.glossario) return;
  let r;
  try { r = await api("/api/glossario"); } catch (e) { avviso(e.message, true); return; }
  stato.glossario = r;
  const voci = (box, elenco) => {
    box.replaceChildren();
    for (const v of elenco) {
      const d = el("details", null, "voce-glossario");
      d.append(el("summary", v.nome));
      const dl = el("dl");
      for (const [k, val] of Object.entries(v.campi)) {
        if (!String(val).trim()) continue;
        dl.append(el("dt", k), el("dd", val));
      }
      d.append(dl);
      d.dataset.cerca = (v.nome + " " + Object.values(v.campi).join(" ")).toLowerCase();
      box.append(d);
    }
    if (!elenco.length) box.append(el("p", "Nessuna.", "nota"));
  };
  voci($("gl-schede"), r.schede);
  voci($("gl-serie"), r.serie);
  $("gl-n-schede").textContent = `(${r.schede.length})`;
  $("gl-n-serie").textContent = `(${r.serie.length})`;
  filtraGlossario();
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
  sel.append(new Option("Nuovo progetto…", NUOVO));
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
}

function apriNuovoProgetto() {
  $("np-nome").value = "";
  $("np-descrizione").value = "";
  $("d-progetto").showModal();
}

const NUOVO = "__nuovo__";      // voce «Nuovo progetto…» del menu dei progetti

// i progetti nella sezione Generale delle Impostazioni: il cambio è un'azione esplicita, con conferma se c'è una
// ricerca aperta (la conversazione resta tra i Recenti del progetto di prima)
function disegnaProgetti() {
  const ul = $("cfg-progetti");
  const parti = (stato.progetti || []).map((p) => {
    const li = el("li", null, "modello-voce progetto-voce" + (p.in_uso ? " in-uso" : ""));
    const testa = el("div", null, "testa");
    testa.append(el("span", p.nome, "nome"));
    if (p.descrizione) testa.append(el("span", p.descrizione, "profilo"));
    li.append(testa, el("span", p.cartella, "cartella"));
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
  if (scelto === NUOVO) {
    apriNuovoProgetto();
    return;
  }
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
  if (!nome) return;
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
  li.append(el("span", misura ? "misurato su queste fonti" : "non misurato", "misura" + (misura ? " si" : "")));
  const azione = el("div", null, "azione");
  const occupato = Boolean(stato.esitoModello && stato.esitoModello.attesa);
  if (conInterruttori) {
    azione.append(interruttore(`Modello ${p.modello || p.nome} acceso`, !p.spento,
      (acceso) => cambiaInterruttore("profilo", p.nome, acceso, p.modello || p.nome)));
  }
  if (p.nome === unico) {
    li.classList.add("in-uso");
    azione.append(el("span", "in uso", "segno ok"));
  } else {
    const b = pulsante("Usa", () => usaModello(p.nome));
    const f = (stato.fornitori || []).find((x) => x.id === p.fornitore.id);
    b.disabled = occupato || Boolean(p.bloccato) || Boolean(f && f.pronto === false);   // fallirebbe comunque
    if (p.bloccato) b.title = "Non si può usare: " + p.bloccato;
    if (f && f.pronto === false) b.title = `${f.nome} non risponde`;
    b.setAttribute("aria-label", `Usa ${p.modello || p.nome} (${p.fornitore.nome})`);
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
    if (f.pronto === false) r.append(el("p", SE_SPENTO[f.id] || `${f.nome} non risponde: i suoi modelli non funzionano finché ` +
      "non torna raggiungibile.", "nota attenzione-testo"));
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
  ridisegna($("cfg-remoti"), tutti.filter((f) => !f.locale).sort((a, b) => a.nome.localeCompare(b.nome)).map(voce));
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
  if (f.chiave === "presente" || f.chiave_spenta) {
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
const IMPOSTAZIONI_MODELLI = "__impostazioni__";

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
      const doppio = profili.filter((x) => x.modello === p.modello).length > 1;
      const o = new Option(doppio ? `${p.modello} (${p.nome})` : p.modello || p.nome, p.nome, false, p.nome === unico);
      o.title = `${f.nome}: ${p.modello}` + (p.misurato && p.misurato !== "no" ? " · misurato su queste fonti" : "");
      og.append(o);
    }
    sel.append(og);
  }
  const altro = el("optgroup");
  altro.label = "—";
  altro.append(new Option("Fornitori e modelli…", IMPOSTAZIONI_MODELLI));
  sel.append(altro);
  sel.dataset.attuale = sel.value;
  sel.title = unico ? nomeModello(unico) : "";
}

// dal menu: «Usa» come nelle Impostazioni (prova di collegamento prima); se non riesce il menu torna alla scelta vera
async function sceltaModello() {
  const sel = $("modello");
  const scelto = sel.value;
  sel.value = sel.dataset.attuale;
  if (scelto === IMPOSTAZIONI_MODELLI) {
    apriImpostazioni("modelli");
    return;
  }
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

// ------------------------------------------------------------------ impostazioni (lavoro 39, poi pagina)
// Una pagina con le sezioni a sinistra (generale, modelli, chat, lingue OCR, ambiente) e i fornitori dei modelli,
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
  if (nome === "generale" || nome === "chat") caricaAvvio();
  else if (nome === "modelli") disegnaModelli();
  else if (nome === "fornitore") disegnaFornitore();
  else if (nome === "ocr") caricaLingue();
  else if (nome === "ambiente") caricaAmbiente();
}

// dalla barra e da Ctrl+,: l'ultima sezione vista (un fornitore solo se c'è ancora)
function apriImpostazioniRicordate() {
  const r = ricordato("sezione");
  const sezioni = ["generale", "modelli", "chat", "ocr", "ambiente"];
  if (r.startsWith("fornitore:") && (stato.fornitori || []).some((f) => f.id === r.slice(10))) {
    apriImpostazioni("fornitore", r.slice(10));
  } else {
    apriImpostazioni(sezioni.includes(r) ? r : "generale");
  }
}

// dopo un passo fatto da un dialogo (progetto, modello, chat) la pagina mostra lo stato nuovo
function aggiornaAvvio() {
  if (!$("vista-impostazioni").hidden && (stato.sezione === "generale" || stato.sezione === "chat")) caricaAvvio();
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
    progetto: (p) => [pulsante("Nuovo progetto…", apriNuovoProgetto, !p.fatto)],
    modello: (p) => [pulsante(p.fatto ? "Cambia…" : "Scegli…", () => mostraSezione("modelli"), !p.fatto)],
    fonti: () => [pulsante("Importa…", () => mostraVista("importazioni"))],
    chat: () => [pulsante("Collega…", () => mostraSezione("chat"))],
  };
  const progettoFatto = r.passi.find((p) => p.id === "progetto").fatto;
  ridisegna($("av-passi"), r.passi.map((p) => {
    const li = el("li");
    const segno = p.fatto ? "ok" : p.facoltativo ? "facoltativo" : "manca";
    li.append(el("span", p.fatto ? "✓" : p.facoltativo ? "○" : "●", "segno " + segno),
      el("span", p.titolo + (p.facoltativo ? " (facoltativo)" : ""), "titolo"));
    const a = el("div", null, "azioni");
    // il modello e le fonti appartengono a un progetto: senza progetto si comincia da quello
    if (progettoFatto || p.id === "progetto" || p.id === "chat") a.append(...azioni[p.id](p));
    li.append(a, el("span", p.dettaglio, "dettaglio"));
    return li;
  }));
  ridisegna($("cfg-client"), r.chat.map((c) => {
    const stato_ = c.collegato ? el("span", "collegato ✓", "segno ok") :
      c.da_aggiornare ? "Voce da aggiornare: un'altra copia del programma o altre impostazioni." :
      !c.presente ? "Non trovato su questo computer." : "Non collegato.";
    const azione = c.presente || c.collegato ? pulsante(c.collegato ? "Controlla…" : "Collega…", () => apriClient(c.id)) :
      null;
    if (azione) azione.setAttribute("aria-label", (c.collegato ? "Controlla " : "Collega ") + c.nome);
    return impostazione(c.nome, stato_, azione);
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

let clientAperto = "";
async function apriClient(nome) {
  clientAperto = nome;
  const m = $("cl-messaggi");
  m.hidden = true;
  $("cl-modifiche").replaceChildren();
  $("cl-scrivi").hidden = true;
  $("d-client").showModal();
  let c;
  try {
    c = await api("/api/client?nome=" + encodeURIComponent(nome));
  } catch (e) {
    m.textContent = e.message;
    m.hidden = false;
    return;
  }
  $("cl-titolo").textContent = `Collega ${c.nome}`;
  $("cl-file").textContent = `File di configurazione: ${c.file}` + (c.esiste ? "" : " (non esiste ancora: lo creo)");
  $("cl-modifiche").replaceChildren(...c.modifiche.map((x) => el("li", x)),
    el("li", `Il programma di chat avvierà: ${c.avvia}`, "nota"));
  if (c.errore) {
    m.textContent = c.errore;
    m.hidden = false;
    return;
  }
  if (c.aperto && !c.gia) {
    m.textContent = `${c.nome} è aperto: chiudilo (anche dall'icona accanto all'orologio), poi riapri questa finestra.`;
    m.hidden = false;
    return;
  }
  $("cl-scrivi").textContent = c.gia ? "Prova il collegamento" : "Scrivi le modifiche";
  $("cl-scrivi").hidden = false;
}

async function collegaClient(evento) {
  evento.preventDefault();
  const m = $("cl-messaggi");
  m.hidden = false;
  m.textContent = "Scrivo la configurazione e provo il server come lo avvierà il programma di chat…";
  $("cl-scrivi").disabled = true;
  try {
    const r = await api("/api/client", { nome: clientAperto });
    m.textContent = r.messaggi.join("\n") + (r.prova ? "" : "\nLa prova del server non è riuscita: vedi sopra.");
    $("cl-scrivi").hidden = true;
    aggiornaAvvio();
  } catch (e) {
    m.textContent = e.message;
  } finally {
    $("cl-scrivi").disabled = false;
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
function riassumiFiltri() {
  const f = filtriScelti();
  const parti = [];
  if (f.dal || f.al) parti.push(`${f.dal || "…"}–${f.al || "…"}`);
  if (f.fonti.length) parti.push(f.fonti.length === 1 ? f.fonti[0] : `${f.fonti.length} serie`);
  if (f.evoluzione) parti.push("evoluzione");
  $("filtri-riassunto").textContent = parti.join(" · ");
  if (stato.aggiornaRiepilogo) stato.aggiornaRiepilogo();     // il riepilogo della scheda aperta segue i filtri
}

function alternaFiltri() {
  const aperto = $("filtri").hidden;
  mostra("filtri", aperto);
  $("b-filtri").setAttribute("aria-expanded", String(aperto));
  if (aperto) $("dal").focus();
}

// riepilogo prima di avviare: cosa cerca, dove, con quale modello; la ricerca chiama il modello per ogni passaggio
// le forme si vedono già sopra (etichette o caselle): qui la domanda e il resto
function riepilogo(domanda, righe) {
  const f = filtriScelti();
  const dl = el("dl", null, "riepilogo");
  const voci = [
    ...(domanda ? [["Domanda", domanda]] : []),
    ["Periodo", f.dal || f.al ? `${f.dal || "…"}–${f.al || "…"}` : "tutto"],
    ["Serie", f.fonti.length ? f.fonti.join("; ") : "tutte"],
    ["Modello", modelloUnico() ? nomeModello(modelloUnico()) : "modelli diversi per ruolo"],
  ];
  if (f.evoluzione) voci.push(["Modo", "evoluzione anno per anno"]);
  if (righe) voci.push(["Nelle fonti", `${righe} righe con queste forme`]);
  for (const [k, v] of voci) dl.append(el("dt", k), el("dd", v));
  const box = el("div", null, "riepilogo-box");
  box.append(dl, el("p", "Il modello legge ogni passaggio trovato: con molti passaggi la ricerca dura a lungo e, " +
    "con un servizio a pagamento, ha un costo.", "nota"));
  return box;
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
    scelte.append(pulsanteMsg(nome, () => { chiudiScheda(m); stato.attesaChi = null; formeDelNome(nome, testo); }, "chip"));
  }
  const libera = pulsanteMsg("Fai la domanda al modello, senza ricerca guidata", () => {
    chiudiScheda(m);
    stato.attesaChi = null;
    seguito(testo, true);
  }, "discreto");
  m.append(scelte, libera);
  stato.attesaChi = (nome) => { chiudiScheda(m); return formeDelNome(nome, testo); };
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
    messaggio("assistente errore", el("p", e.message));
    return;
  }
  if (!r.schede.length) return esploraForme(entita, domanda);
  const m = messaggio("assistente scheda");
  const scelta = { scheda: r.schede[0] };
  const sommario = el("div");
  const forme = el("div", null, "chip-riga");
  const aggiorna = () => {
    forme.replaceChildren(...scelta.scheda.varianti.map((v) => el("span", v, "chip statico")));
    sommario.replaceChildren(riepilogo(domanda));
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
  const avvia = pulsanteMsg("Avvia la ricerca", () => { chiudiScheda(m); avviaRicerca(scelta.scheda.nome, domanda); }, "primario");
  m.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.target.type === "radio") avvia.click(); });
  const altra = pulsanteMsg("Non è questa: cerca le forme", () => { chiudiScheda(m); esploraForme(entita, domanda); }, "discreto");
  aggiorna();
  stato.aggiornaRiepilogo = () => { if (!m.classList.contains("decisa")) aggiorna(); };
  const azioni = el("div", null, "riga");
  azioni.append(avvia, altra);
  m.append(forme, sommario, azioni);
  annuncia("Forme del nome pronte: controlla il riepilogo e avvia la ricerca.");
  scorriInFondo();
}

function esploraForme(entita, domanda) {
  const m = messaggio("assistente scheda");
  m.append(el("p", `Non c'è ancora una scheda per «${entita}»: cerco nelle fonti le forme attestate.`));
  const campo = (etichetta, segnaposto) => {
    const l = el("label", etichetta);
    const i = document.createElement("input");
    i.type = "text";
    i.placeholder = segnaposto;
    l.append(i);
    return [l, i];
  };
  const [li, indizi] = campo("Indizi (facoltativi)", "paese, partito… separati da ;");
  const [lc, candidate] = campo("Altre forme da verificare (facoltative)", "per esempio una trascrizione; separate da ;");
  const esito = el("div");
  const cerca = pulsanteMsg("Cerca le forme nelle fonti", async () => {
    cerca.disabled = true;
    esito.replaceChildren(el("p", "Cerco le forme nelle fonti…", "nota"));
    try {
      const r = await api("/api/esplora", { nome: entita, indizi: indizi.value, candidate: candidate.value });
      mostraFormeTrovate(m, esito, r, entita, domanda);
    } catch (e) {
      esito.replaceChildren(el("p", e.message, "attenzione"));
    } finally {
      cerca.disabled = false;
      scorriInFondo();
    }
  }, "primario");
  m.append(li, lc, cerca, esito);
  indizi.focus();
}

function mostraFormeTrovate(m, box, r, entita, domanda) {
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
  box.append(el("p", "Spunta le forme che indicano davvero questa entità. «Ambigua»: può indicare anche altro; " +
    "quei passaggi li controlla sempre il modello.", "nota"));
  for (const f of r.forme) box.append(rigaForma(f));
  if (r.non_attestate.length) box.append(el("p", `Non attestate (non entrano nella scheda): ${r.non_attestate.join("; ")}`, "nota"));
  const sommario = el("div");
  const scelte = () => [...box.querySelectorAll("input.sceglie:checked")].map((c) => c.value);
  const aggiorna = () => {
    const righe = r.forme.filter((f) => scelte().includes(f.forma)).reduce((n, f) => n + (f.totale || 0), 0);
    sommario.replaceChildren(riepilogo(domanda, righe));
  };
  box.addEventListener("change", (e) => { if (e.target.classList.contains("sceglie")) aggiorna(); });
  const tipo = document.createElement("select");
  for (const t of ["persona", "organizzazione", "testata", "stato", "altro"]) tipo.append(new Option(t, t));
  const lt = el("label", "Tipo ");
  lt.append(tipo);
  const crea = pulsanteMsg("Crea la scheda e avvia la ricerca", async () => {
    const varianti = scelte();
    const ambigue = [...box.querySelectorAll("input.ambigua:checked")].map((c) => c.value).filter((f) => varianti.includes(f));
    if (!varianti.length) { avviso("Spunta almeno una forma del nome.", true); return; }
    try {
      const s = await api("/api/scheda", { nome: entita, varianti, forme_ambigue: ambigue, tipo: tipo.value,
        contesto: r.contesto });
      if (s.avviso) avviso(s.avviso);
      stato.glossario = null;                      // la scheda nuova entra nel glossario
      chiudiScheda(m);
      await avviaRicerca(s.scheda || entita, domanda);
    } catch (e) {
      avviso(e.message, true);
    }
  }, "primario");
  aggiorna();
  stato.aggiornaRiepilogo = () => { if (!m.classList.contains("decisa")) aggiorna(); };
  box.append(lt, sommario, crea);
  annuncia(`${r.forme.length} forme trovate: spunta quelle giuste.`);
}

function rigaForma(f) {
  const d = el("div", null, "forma");
  const testa = el("div", null, "testa");
  const l = el("label", null, "casella");
  const c = document.createElement("input");
  c.type = "checkbox";
  c.className = "sceglie";
  c.value = f.forma;
  c.checked = f.proposta;
  l.append(c, el("strong", f.forma));
  const la = el("label", null, "casella");
  const a = document.createElement("input");
  a.type = "checkbox";
  a.className = "ambigua";
  a.value = f.forma;
  a.checked = f.ambigua;
  a.setAttribute("aria-label", `${f.forma}: ambigua`);
  la.append(a, document.createTextNode("ambigua"));
  testa.append(l, el("span", `${f.totale} righe`, "conto"), la);
  if (f.origine && f.origine !== "nelle fonti") testa.append(el("span", f.origine, "conto"));
  d.append(testa);
  if (f.attenzione) d.append(el("div", f.attenzione, "attenzione"));
  const serie = Object.entries(f.per_serie_e_anno || {}).map(([s, anni]) =>
    `${s}: ${Object.entries(anni).map(([a, n]) => `${a} (${n})`).join(", ")}`);
  if (serie.length) d.append(el("div", serie.join("; "), "nota"));
  for (const e of f.esempi) {
    const q = el("blockquote", e.testo);
    q.title = e.riferimento;
    d.append(q);
  }
  return d;
}

// --------------------------------------------- la ricerca e la risposta
async function avviaRicerca(entita, domanda) {
  const f = filtriScelti();
  try {
    const r = await api("/api/ricerca/avvia", { entita, domanda: domanda || "", dal: f.dal, al: f.al, fonti: f.fonti,
      evoluzione: f.evoluzione });
    if (r.gia_in_corso) avviso("Questa ricerca era già in corso: ne seguo l'avanzamento.");
    else avviso("");
    const filo = Object.assign(filoCorrente(), { entita, domanda, avviata: true });
    filo.titolo = domanda || entita;
    registra(filo, { tipo: "ricerca", entita, domanda: domanda || "" });
    stato.filoRicerca = filo;
    stato.ultimaRisposta = "";
    stato.tappaAnnunciata = "";
    messaggioRicerca(domanda || entita);
    annuncia(`Ricerca avviata: ${entita}.`);
    inCorso(true);
    segui();
  } catch (e) {
    messaggio("assistente errore", el("p", e.message));
  }
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
  const m = messaggio("assistente ricerca", el("p", titolo, "titolo-ricerca"), barra,
    el("p", "In partenza…", "nota stato-ricerca"),
    el("p", "Continua anche se chiudi questa pagina.", "nota"));
  stato.ricercaEl = m;
  return m;
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
  const letti = r.letti ? `${r.letti.letti}/${r.letti.estratti} passaggi letti` : "";
  const parti = [r.stato, r.fase, letti || r.avanzamento, r.minuti ? `${r.minuti} min` : ""].filter(Boolean);
  if (r.prossimo_tentativo) parti.push(`nuovo tentativo: ${r.prossimo_tentativo}`);
  if (r.ultimo_messaggio && !(r.fase && r.ultimo_messaggio.includes(r.fase))) parti.push(r.ultimo_messaggio);
  m.querySelector(".stato-ricerca").textContent = parti.join(" · ");
  // la barra segue le tre fasi (estrazione, lettura, risposta) e, dentro la lettura, i passaggi letti
  const barra = m.querySelector(".barra");
  const f = /(\d)\s*\/\s*3/.exec(r.fase || "");
  const n = /(\d+)\s*\/\s*(\d+)/.exec(r.avanzamento || "");
  const segna = (p) => {
    const v = Math.round(Math.min(100, Math.max(0, p)));
    barra.setAttribute("aria-valuenow", String(v));
    barra.firstChild.style.width = v + "%";
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
    if (!allAvvio) annuncia(r.finito ? `Ricerca ${r.stato}.` : `Ricerca: ${r.fase}.`);
  }
  inCorso(!r.finito);
  if (!r.finito) { segui(); return; }
  segna(100);
  if (r.ultimi_messaggi && r.ultimi_messaggi.length) {
    avviso(`Ricerca ${r.stato}: ${r.ultimi_messaggi.slice(-2).join(" ")}`, true);
  }
  if (r.avviso) avviso(r.avviso, true);
  const p = r.risposta_pronta;
  stato.ricercaEl = null;
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
    m.querySelector(".stato-ricerca").textContent = `Ricerca ${r.stato}.`;
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
  azioni.append(pulsanteMsg("Fonti di questa risposta", () => { stato.doc = doc; apriLaterale("passaggi"); }, "discreto"));
  const a = el("a", "Apri il documento completo");
  a.href = url;
  a.target = "_blank";
  a.rel = "noopener";
  azioni.append(a);
  if (pertinenti !== null && pertinenti !== undefined) azioni.append(el("span", `${pertinenti} documenti pertinenti`, "etichetta"));
  const m = messaggio("assistente risposta", corpo, azioni);
  (async () => {
    try {
      const r = await api("/api/documento?" + new URLSearchParams(doc));
      corpo.replaceChildren();
      const pref = inserisciDocumento(corpo, r.corpo);
      await arricchisciDocumento(corpo, doc, pref);
    } catch (e) {
      corpo.replaceChildren(el("p", e.message, "attenzione"));
    }
  })();
  annuncia("Risposta pronta.");
  return m;
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
      dettaglio: f.entita })),
    ...[...s.risposte, ...s.ricerche].filter((r) => !nei.has(r.documento)).map((r) => ({ vecchia: r,
      titolo: r.domanda || r.entita || r.cartella || r.file, quando: quando(r.data), dettaglio: r.entita })),
  ].sort((a, b) => b.quando.localeCompare(a.quando));
  stato.recenti = voci;
  const corrente = stato.thread && stato.thread.id;
  ul.replaceChildren(...voci.map((v) => {
    const li = el("li");
    const b = el("button", v.titolo, "voce-recente");
    b.type = "button";
    b.title = [v.dettaglio, v.quando.replace("T", " ").slice(0, 16)].filter(Boolean).join(" · ");
    if (v.filo) {
      b.dataset.id = v.filo.id;
      if (v.filo.id === corrente) b.setAttribute("aria-current", "true");
      b.addEventListener("click", () => apriFilo(v.filo.id));
    } else {
      b.dataset.documento = v.vecchia.documento;
      b.addEventListener("click", () => apriDalloStorico(v.vecchia));
    }
    li.append(b);
    return li;
  }));
  if (!voci.length) ul.append(el("li", "Ancora nessuna ricerca.", "nota"));
  suggerimenti();
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
  box.replaceChildren(...nomi.map((n) => pulsanteMsg(n, () => { $("testo").value = n; invia(); }, "chip")));
}

// ------------------------------------------------------------------ importazione (lavoro 37)
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
    if (a) $("imp-barra").style.width = avanzamento("imp-avanzamento", (a.fatto / Math.max(1, a.totale)) * 100);
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
  for (const id of ["imp-carica", "imp-salva", "imp-prova", "imp-applica"]) $(id).disabled = !conTabella;
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

// ------------------------------------------------------------------ conversazione sulle fonti (lavoro 38)
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
  box.replaceChildren(...parti);
  box.hidden = false;
  const r = a.getBoundingClientRect();
  const larga = box.offsetWidth;
  const alta = box.offsetHeight;
  box.style.left = Math.max(8, Math.min(r.left, innerWidth - larga - 8)) + "px";
  box.style.top = (r.top - alta - 8 > 8 ? r.top - alta - 8 : r.bottom + 8) + "px";
  a.setAttribute("aria-describedby", "anteprima");
}

function nascondiAnteprima() {
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
  let f;
  try { f = await api("/api/filo?id=" + encodeURIComponent(id)); } catch (e) { avviso(e.message, true); return; }
  nuovoThread();
  segnaCorrente((b) => b.dataset.id === id);
  stato.thread = f;
  for (const m of f.messaggi) {
    if (m.tipo === "utente") messaggio("utente", el("p", m.testo));
    else if (m.tipo === "risposta") { messaggioRisposta(m.documento, m.pertinenti); f.risposta = m.documento; }
    else if (m.tipo === "conversazione") messaggio("assistente").replaceWith(rispostaConversazione(m.voce));
  }
  scorriInFondo();
  return f;
}

function segnaCorrente(prova) {
  document.querySelectorAll("#storico button").forEach((b) => {
    if (prova(b)) b.setAttribute("aria-current", "true");
    else b.removeAttribute("aria-current");
  });
}

// ------------------------------------------------------------------ avvio
document.addEventListener("DOMContentLoaded", () => {
  if (ricordato("barra") === "chiusa") barraLaterale(false);
  $("b-barra").addEventListener("click", () => barraLaterale($("app").classList.contains("barra-chiusa")));
  $("progetto").addEventListener("change", sceltaProgetto);
  $("cfg-nuovo-progetto").addEventListener("click", apriNuovoProgetto);
  $("modello").addEventListener("change", sceltaModello);
  $("np-crea").addEventListener("click", creaProgetto);
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
    b.addEventListener("click", () => apriLaterale(b.dataset.pannelloApri)));
  $("b-chiudi-laterale").addEventListener("click", chiudiLaterale);
  document.addEventListener("keydown", tastiFinestra);
  $("imp-sfoglia").addEventListener("click", sfogliaCartella);
  $("imp-cartella").value = ricordato("cartella");
  $("imp-sovrascrivi").addEventListener("change", etichettaImporta);
  $("imp-dubbi").addEventListener("change", () => stato.tabella && mostraTabella(stato.tabella));
  $("passaggi-pertinenti").addEventListener("change", filtraPassaggi);
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
  $("fonte-trascrizione").addEventListener("toggle", () => { stato.fonteAperta = $("fonte-trascrizione").open; });
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
  $("cl-scrivi").addEventListener("click", collegaClient);
  stato.convNuova = true;
  $("testo").focus();
  // al primo avvio (o se manca il progetto o il modello) la preparazione si apre da sé
  caricaTutto().then(() => api("/api/avvio")).then((r) => { if (!r.completo) apriImpostazioni("generale"); })
    .catch(() => {});
});

// Interfaccia di AIrchivist (lavoro 35): menu Progetto e Modello, percorso guidato della ricerca.
// Tutto passa dalle API di app.py; i testi delle fonti si inseriscono sempre come testo, mai come HTML.
"use strict";

const $ = (id) => document.getElementById(id);
const NUOVO = "__nuovo__";
const stato = { schede: [], nome: "", attesa: null, attesaImporta: null, ultimaRisposta: "",
  doc: null, passaggi: null, glossario: null, fonte: null };

async function api(percorso, dati) {
  const opzioni = { credentials: "same-origin" };
  if (dati !== undefined) {
    opzioni.method = "POST";
    opzioni.headers = { "Content-Type": "application/json", "X-AIrchivist": "1" };
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
  a.textContent = testo || "";
  a.hidden = !testo;
  a.classList.toggle("errore", errore);
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

// ------------------------------------------------------------------ schede del pannello sinistro
function apriScheda(nome) {
  document.querySelectorAll(".schede button").forEach((b) => b.classList.toggle("attiva", b.dataset.scheda === nome));
  document.querySelectorAll(".pannello").forEach((p) => { p.hidden = p.dataset.pannello !== nome; });
  if (nome === "storico") caricaStorico();
  if (nome === "passaggi") caricaPassaggi();
  if (nome === "glossario") caricaGlossario();
}

function apriDocumento(url) {
  if (!url) return;
  const f = $("documento");
  // il documento aperto decide i passaggi della scheda «Passaggi» e i collegamenti alla fonte
  const q = new URL(url, location.href).searchParams;
  stato.doc = q.get("risposta") ? { risposta: q.get("risposta") } : q.get("ricerca") ? { ricerca: q.get("ricerca") } : null;
  stato.passaggi = null;
  f.onload = arricchisciDocumento;
  f.src = url;
  f.hidden = false;
  mostra("risposta-vuota", false);
  apriScheda("risposta");
}

// ------------------------------------------------------------------ fonte, passaggi, glossario (lavoro 36)
async function datiPassaggi() {
  if (!stato.doc) return null;
  if (!stato.passaggi) stato.passaggi = await api("/api/passaggi?" + new URLSearchParams(stato.doc));
  return stato.passaggi;
}

// nel documento della risposta (stessa origine): «Apri la fonte» accanto a ogni passaggio [n] e ai suoi dati tecnici
async function arricchisciDocumento() {
  const d = $("documento").contentDocument;
  if (!d || !d.body) return;
  let r;
  try { r = await datiPassaggi(); } catch (e) { return; }
  if (!r || !Object.keys(r.rimandi).length) return;
  const stile = d.createElement("style");
  stile.textContent = ".apri-fonte { font: .8rem system-ui, sans-serif; margin-left: .5rem; padding: .05rem .45rem; " +
    "border: 1px solid currentColor; border-radius: 4px; background: none; color: inherit; cursor: pointer; " +
    "vertical-align: middle; opacity: .75; } .apri-fonte:hover { opacity: 1; } @media print { .apri-fonte { display: none; } }";
  d.head.append(stile);
  const pulsante = (x, v) => {
    if (x.querySelector(".apri-fonte")) return;
    const b = d.createElement("button");
    b.type = "button";
    b.className = "apri-fonte";
    b.textContent = v.pagina ? `Apri la fonte, p. ${v.pagina}` : "Apri la fonte";
    b.title = `${v.file}, riga ${v.riga}`;
    b.addEventListener("click", () => apriFonte(v.file, v.riga));
    x.append(b);
  };
  d.querySelectorAll("h3, li").forEach((x) => {
    const m = /^\[(\d+)\]/.exec(x.textContent.trim());
    const v = m && r.rimandi[m[1]];
    if (!v) return;
    pulsante(x, v);
    // la citazione sotto il passaggio («— ..., p. 13.»): anche lei apre la pagina
    for (let s = x.nextElementSibling; x.tagName === "H3" && s && !/^H[1-3]$/.test(s.tagName); s = s.nextElementSibling) {
      if (s.tagName === "P" && s.textContent.trim().startsWith("—")) pulsante(s, v);
    }
  });
}

async function apriFonte(file, riga, pagina) {
  const q = { file };
  if (riga) q.riga = riga;
  if (pagina) q.pagina = pagina;
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
  mostra("fonte-immagine-l", !!r.immagine);
  mostraImmagine();
  const box = $("fonte-testo");
  box.replaceChildren();
  let evidenziata = null;
  for (const x of r.righe) {
    const riga_ = el("div", null, "riga-fonte");
    if (/^\s*\[\[.*\]\]\s*$/.test(x.testo)) riga_.classList.add("marcatore");
    riga_.append(el("span", String(x.n), "n"), el("span", x.testo, "t"));
    if (x.n === r.evidenzia) {
      riga_.classList.add("evidenziata");
      evidenziata = riga_;
    }
    box.append(riga_);
  }
  apriScheda("fonte");
  (evidenziata || $("fonte")).scrollIntoView({ block: evidenziata ? "center" : "start" });
}

function mostraImmagine() {
  const r = stato.fonte;
  const si = !!(r && r.immagine && $("fonte-immagine").checked);
  const img = $("fonte-img");
  if (si && img.getAttribute("src") !== r.immagine) img.src = r.immagine;
  img.hidden = !si;
}

function sfoglia(passo) {
  const r = stato.fonte;
  if (r) apriFonte(r.file, null, r.pagina + passo);
}

async function caricaPassaggi() {
  const t = $("passaggi-tabella");
  if (!stato.doc) {
    t.replaceChildren();
    mostra("passaggi-filtro", false);
    $("passaggi-nota").textContent = "Apri una risposta o una ricerca (scheda «Storico»): qui compaiono i suoi " +
      "passaggi, e un clic apre la pagina della fonte.";
    return;
  }
  let r;
  try { r = await datiPassaggi(); } catch (e) { $("passaggi-nota").textContent = e.message; return; }
  const ricerca = !!stato.doc.ricerca;
  $("passaggi-nota").textContent = ricerca
    ? `${r.passaggi.length} passaggi letti in questa ricerca. Un clic apre la pagina della fonte.`
    : `${r.passaggi.length} passaggi citati nella risposta. Un clic apre la pagina della fonte.`;
  mostra("passaggi-filtro", r.passaggi.length > 0);
  const colonne = ricerca
    ? [["data", "Data"], ["fonte", "Fonte"], ["pagina", "p."], ["pertinente", "Pertinente"], ["letto_da", "Letto da"],
       ["traduzione", "Traduzione"]]
    : [["n", "n."], ["fonte", "Fonte"]];
  const testa = el("tr");
  for (const [, nome] of colonne) testa.append(el("th", nome));
  const corpo = document.createElement("tbody");
  for (const p of r.passaggi) {
    const tr = el("tr");
    for (const [k] of colonne) {
      const td = el("td", k === "fonte" ? senzaMarkdown(p[k]) : k === "traduzione" ? null : p[k] || "");
      if (k === "traduzione") {                     // quattro righe; il testo intero al passaggio del mouse
        td.className = "traduzione";
        td.append(el("div", p[k] || "", "taglia"));
        td.title = p[k] || "";
      }
      tr.append(td);
    }
    if (p.pertinente === "no") tr.classList.add("no");
    tr.dataset.cerca = Object.values(p).join(" ").toLowerCase();
    tr.title = `${p.file}, riga ${p.riga}`;
    tr.addEventListener("click", () => apriFonte(p.file, p.riga));
    corpo.append(tr);
  }
  const intestazione = document.createElement("thead");
  intestazione.append(testa);
  t.replaceChildren(intestazione, corpo);
  filtraPassaggi();
}

function filtraPassaggi() {
  const f = $("passaggi-filtro").value.trim().toLowerCase();
  $("passaggi-tabella").querySelectorAll("tbody tr").forEach((tr) => { tr.hidden = !!f && !tr.dataset.cerca.includes(f); });
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

// al cambio di progetto: documento, passaggi, fonte e glossario erano del progetto di prima
function dimenticaProgetto() {
  stato.doc = null;
  stato.passaggi = null;
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
  const sel = $("progetto");
  sel.replaceChildren();
  if (!s.progetto) sel.append(new Option("— nessun progetto —", "", true, true));
  for (const p of s.progetti) {
    const o = new Option(p.nome, p.cartella, p.in_uso, p.in_uso);
    o.title = p.cartella;
    sel.append(o);
  }
  sel.append(new Option("Nuovo progetto…", NUOVO));
  sel.dataset.attuale = s.progetto ? s.progetto.cartella : "";
  $("np-dove").textContent = `La cartella si crea in ${s.cartella_progetti}.`;
  if (!s.progetto) {
    avviso("Nessun progetto in uso: scegline uno dal menu «Progetto» o creane uno nuovo.");
  } else if (!s.progetto.documenti) {
    avviso(`Il progetto «${s.progetto.nome}» non ha ancora documenti: usa «Importa».`);
  } else {
    avviso("");
  }
  await Promise.all([caricaModelli(), caricaFonti()]);
  mostraRicerca(s.ricerca, true);
}

function apriNuovoProgetto() {
  $("np-nome").value = "";
  $("np-descrizione").value = "";
  $("d-progetto").showModal();
}

async function cambiaProgetto() {
  const sel = $("progetto");
  if (sel.value === NUOVO) {
    sel.value = sel.dataset.attuale;
    apriNuovoProgetto();
    return;
  }
  try {
    await api("/api/progetto", { cartella: sel.value });
    nuova();
    dimenticaProgetto();
    $("documento").hidden = true;
    mostra("risposta-vuota", true);
    await caricaTutto();
  } catch (e) {
    sel.value = sel.dataset.attuale;           // il progetto non cambia
    avviso(e.message, true);
  }
}

async function creaProgetto(evento) {
  evento.preventDefault();
  const nome = $("np-nome").value.trim();
  if (!nome) return;
  try {
    await api("/api/progetto/nuovo", { nome, descrizione: $("np-descrizione").value.trim() });
    $("d-progetto").close();
    nuova();
    await caricaTutto();
    aggiornaAvvio();
  } catch (e) {
    avviso(e.message, true);
    $("d-progetto").close();
  }
}

// ------------------------------------------------------------------ modello
async function caricaModelli() {
  const sel = $("modello");
  sel.replaceChildren();
  let m;
  try {
    m = await api("/api/modelli");
  } catch (e) {
    avviso(e.message, true);
    return;
  }
  const inUso = new Set(Object.values(m.in_uso || {}));
  if (inUso.size !== 1) sel.append(new Option(inUso.size ? "scelte diverse per ruolo" : "— nessun modello —", "",
    true, true));
  for (const p of m.profili || []) {
    const misura = p.misurato && p.misurato !== "no" ? "misurato" : "non misurato";
    const o = new Option(`${p.nome} · ${misura}`, p.nome);
    o.title = `${p.servizio}: ${p.modello}; chiave ${p.chiave}; misurato su queste fonti: ${p.misurato}`;
    if (inUso.size === 1 && inUso.has(p.nome)) o.selected = true;
    sel.append(o);
  }
  sel.append(new Option("Aggiungi modello…", NUOVO));
  sel.dataset.attuale = sel.value;
  if (m.errore) avviso(m.errore, true);
  aggiornaPallino();
  if ($("conversazione").open) caricaConversazione(false);     // progetto o modello cambiati: si ricomincia
}

async function aggiornaPallino() {
  const p = $("pallino");
  const nome = $("modello").value;
  p.className = "pallino";
  p.title = "Stato del collegamento";
  if (!nome || nome === NUOVO) return;
  p.classList.add("attesa");
  try {
    const c = await api("/api/collegamento?nome=" + encodeURIComponent(nome));
    p.className = "pallino " + (c.ok ? "ok" : "male");
    p.title = c.dettaglio || (c.ok ? "collegato" : "non raggiungibile");
  } catch (e) {
    p.className = "pallino male";
    p.title = e.message;
  }
}

async function cambiaModello() {
  const sel = $("modello");
  if (sel.value === NUOVO) {
    sel.value = sel.dataset.attuale;
    apriAggiungiModello();
    return;
  }
  if (!sel.value) return;
  const p = $("pallino");
  p.className = "pallino attesa";
  p.title = "Prova di collegamento in corso…";
  avviso(`Prova di collegamento con «${sel.value}»…`);
  try {
    const r = await api("/api/modello/usa", { nome: sel.value });
    if (r.cambiato) {
      avviso(`Modello in uso: ${sel.value}.` + (r.ricerca_in_corso ? " " + r.ricerca_in_corso : ""));
    } else {
      avviso("Il modello non è cambiato: " + (r.messaggi || []).join(" "), true);
    }
  } catch (e) {
    avviso(e.message, true);
  }
  const messaggio = $("avviso").textContent;
  const errore = $("avviso").classList.contains("errore");
  await caricaModelli();                       // il menu mostra la scelta vera, anche se la prova è fallita
  avviso(messaggio, errore);
}

let servizi = [];
async function apriAggiungiModello() {
  if (!servizi.length) {
    try { servizi = (await api("/api/servizi")).servizi; } catch (e) { avviso(e.message, true); return; }
    const s = $("am-servizio");
    for (const x of servizi) s.append(new Option(x.etichetta, x.id));
  }
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

// ------------------------------------------------------------------ preparazione (lavoro 39)
const SEGNI = { ok: "✓", manca: "✗", facoltativo: "–", info: "" };

function pulsante(testo, azione, primario) {
  const b = el("button", testo, primario ? "primario" : "");
  b.type = "button";
  b.addEventListener("click", azione);
  return b;
}

async function apriAvvio() {
  if (!$("d-avvio").open) $("d-avvio").showModal();
  $("av-ambiente").open = false;
  await caricaAvvio();
}

// dopo un passo fatto da un altro dialogo (progetto, modello, chat) la preparazione mostra lo stato nuovo
function aggiornaAvvio() { if ($("d-avvio").open) caricaAvvio(); }

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
    modello: (p) => [pulsante("Aggiungi modello…", apriAggiungiModello, !p.fatto)],
    fonti: () => [pulsante("Importa…", () => { $("d-avvio").close(); apriScheda("importazioni"); })],
    chat: () => [],
  };
  const progettoFatto = r.passi.find((p) => p.id === "progetto").fatto;
  $("av-passi").replaceChildren(...r.passi.map((p) => {
    const li = el("li");
    const stato = p.fatto ? "ok" : p.facoltativo ? "facoltativo" : "manca";
    li.append(el("span", p.fatto ? "✓" : p.facoltativo ? "○" : "●", "segno " + stato),
      el("span", p.titolo + (p.facoltativo ? " (facoltativo)" : ""), "titolo"));
    const a = el("div", null, "azioni");
    // il modello e le fonti appartengono a un progetto: senza progetto si comincia da quello
    if (progettoFatto || p.id === "progetto" || p.id === "chat") a.append(...azioni[p.id](p));
    li.append(a, el("span", p.dettaglio, "dettaglio"));
    if (p.id === "chat") {
      for (const c of r.chat) {
        const riga = el("div", null, "client");
        riga.append(el("span", c.nome));
        if (c.collegato) riga.append(el("span", "collegato ✓", "segno ok"));
        else if (c.da_aggiornare) riga.append(el("span", "voce da aggiornare (un'altra copia o impostazioni)", "nota"));
        else if (!c.presente) riga.append(el("span", "non trovato su questo computer", "nota"));
        riga.append(pulsante(c.collegato ? "Controlla…" : "Collega…", () => apriClient(c.id)));
        li.append(riga);
      }
    }
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
      if (v.azione === "modello") riga.append(pulsante("Aggiungi modello…", apriAggiungiModello));
      parti.push(riga);
    }
  }
  parti.unshift(el("p", r.mancano.length ? "Manca: " + r.mancano.join(", ") + "." :
    "Niente di necessario manca. I segni «–» indicano parti facoltative.", "nota"));
  d.replaceChildren(...parti);
  $("av-posizioni").textContent = r.posizioni.join(" · ");
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

// ------------------------------------------------------------------ percorso della ricerca
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
}

function nuova() {
  clearTimeout(stato.attesa);
  for (const id of ["nome", "domanda", "dal", "al", "indizi", "candidate"]) $(id).value = "";
  $("evoluzione").checked = false;
  $("fonti").querySelectorAll("input").forEach((c) => { c.checked = false; });
  for (const id of ["passo-forme", "passo-ricerca", "passo-risposta"]) mostra(id, false);
  mostra("passo-domanda", true);
  $("b-continua").disabled = false;
  $("nome").focus();
}

async function continua() {
  const nome = $("nome").value.trim();
  if (!nome) { $("nome").focus(); return; }
  stato.nome = nome;
  try {
    const r = await api("/api/entita", { nome });
    stato.schede = r.schede;
    const box = $("forme-scheda");
    box.replaceChildren();
    mostra("passo-forme", true);
    $("forme-trovate").replaceChildren();
    if (r.schede.length) {
      mostra("forme-esplora", false);
      box.append(el("p", r.schede.length > 1 ? "Ci sono più schede che corrispondono: scegli quella giusta."
        : "C'è già una scheda: la ricerca cerca queste forme del nome."));
      r.schede.forEach((s, i) => {
        const l = el("label", null, "casella");
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = "scheda";
        radio.value = s.nome;
        radio.checked = i === 0;
        l.append(radio, document.createTextNode(`${s.nome}${s.tipo ? " (" + s.tipo + ")" : ""}: ${s.varianti.join("; ")}`));
        box.append(l, el("br"));
      });
      const b = el("button", "Avvia la ricerca", "primario");
      b.type = "button";
      b.addEventListener("click", () => {
        const scelta = box.querySelector("input[name=scheda]:checked");
        avviaRicerca(scelta ? scelta.value : r.schede[0].nome);
      });
      const altra = el("button", "Non è questa: cerca le forme");
      altra.type = "button";
      altra.addEventListener("click", () => mostra("forme-esplora", true));
      box.append(b, document.createTextNode(" "), altra);
    } else {
      mostra("forme-esplora", true);
      $("indizi").focus();
    }
  } catch (e) {
    avviso(e.message, true);
  }
}

async function esplora() {
  const box = $("forme-trovate");
  box.replaceChildren(el("p", "Cerco le forme nelle fonti…", "nota"));
  $("b-esplora").disabled = true;
  try {
    const r = await api("/api/esplora", { nome: stato.nome, indizi: $("indizi").value, candidate: $("candidate").value });
    box.replaceChildren();
    if (r.errore) {
      box.append(el("p", r.errore + (r.avanzamento ? ` (${r.avanzamento})` : ""), "attenzione"));
      return;
    }
    if (r.avviso_indice) box.append(el("p", r.avviso_indice, "nota"));
    if (!r.forme.length) {
      box.append(el("p", `Nessuna forma di «${stato.nome}» compare nelle fonti.` +
        (r.non_attestate.length ? ` Non attestate: ${r.non_attestate.join("; ")}.` : ""), "nota"));
      return;
    }
    box.append(el("p", "Spunta le forme che indicano davvero questa entità. «Ambigua»: può indicare anche altro; " +
      "quei passaggi li controlla sempre il modello.", "nota"));
    for (const f of r.forme) box.append(rigaForma(f));
    if (r.non_attestate.length) box.append(el("p", `Non attestate (non entrano nella scheda): ${r.non_attestate.join("; ")}`, "nota"));
    const tipo = document.createElement("select");
    tipo.id = "tipo-scheda";
    for (const t of ["persona", "organizzazione", "testata", "stato", "altro"]) tipo.append(new Option(t, t));
    const lt = el("label", "Tipo ");
    lt.append(tipo);
    const b = el("button", "Crea la scheda e avvia la ricerca", "primario");
    b.type = "button";
    b.addEventListener("click", () => creaSchedaEAvvia(r.contesto));
    box.append(lt, b);
  } catch (e) {
    box.replaceChildren(el("p", e.message, "attenzione"));
  } finally {
    $("b-esplora").disabled = false;
  }
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

async function creaSchedaEAvvia(contesto) {
  const box = $("forme-trovate");
  const varianti = [...box.querySelectorAll("input.sceglie:checked")].map((c) => c.value);
  const ambigue = [...box.querySelectorAll("input.ambigua:checked")].map((c) => c.value).filter((f) => varianti.includes(f));
  if (!varianti.length) { avviso("Spunta almeno una forma del nome.", true); return; }
  try {
    const r = await api("/api/scheda", { nome: stato.nome, varianti, forme_ambigue: ambigue,
      tipo: $("tipo-scheda").value, contesto });
    if (r.avviso) avviso(r.avviso);
    await avviaRicerca(r.scheda || stato.nome);
  } catch (e) {
    avviso(e.message, true);
  }
}

async function avviaRicerca(entita) {
  const fonti = [...$("fonti").querySelectorAll("input:checked")].map((c) => c.value);
  try {
    const r = await api("/api/ricerca/avvia", { entita, domanda: $("domanda").value.trim(), dal: $("dal").value,
      al: $("al").value, fonti, evoluzione: $("evoluzione").checked });
    if (r.gia_in_corso) avviso("Questa ricerca era già in corso: ne seguo l'avanzamento.");
    else avviso("");
    stato.ultimaRisposta = "";
    mostra("passo-domanda", false);
    mostra("passo-forme", false);
    mostra("passo-risposta", false);
    mostra("passo-ricerca", true);
    $("ricerca-titolo").textContent = entita;
    $("ricerca-stato").textContent = "In partenza…";
    $("ricerca-barra").style.width = "0";
    segui();
  } catch (e) {
    avviso(e.message, true);
  }
}

function segui() {
  clearTimeout(stato.attesa);
  stato.attesa = setTimeout(async () => {
    try {
      mostraRicerca(await api("/api/ricerca"), false);
    } catch (e) {
      avviso(e.message, true);
      segui();
    }
  }, 2500);
}

function mostraRicerca(r, allAvvio) {
  if (!r || r.nessuna) return;
  if (allAvvio && r.finito) return;          // all'apertura: si segue solo una ricerca in corso
  mostra("passo-ricerca", true);
  if (allAvvio) {
    mostra("passo-domanda", false);
    mostra("passo-forme", false);
  }
  $("ricerca-titolo").textContent = r.domanda || r.entita;
  const letti = r.letti ? `${r.letti.letti}/${r.letti.estratti} passaggi letti` : "";
  const parti = [r.stato, r.fase, letti || r.avanzamento, r.minuti ? `${r.minuti} min` : ""].filter(Boolean);
  if (r.prossimo_tentativo) parti.push(`nuovo tentativo: ${r.prossimo_tentativo}`);
  if (r.ultimo_messaggio && !(r.fase && r.ultimo_messaggio.includes(r.fase))) parti.push(r.ultimo_messaggio);
  $("ricerca-stato").textContent = parti.join(" · ");
  // la barra segue le tre fasi (estrazione, lettura, risposta) e, dentro la lettura, i passaggi letti
  const f = /(\d)\s*\/\s*3/.exec(r.fase || "");
  const m = /(\d+)\s*\/\s*(\d+)/.exec(r.avanzamento || "");
  if (f) {
    const fase = +f[1];
    const dentro = fase !== 2 ? 0 : r.letti && r.letti.estratti ? r.letti.letti / r.letti.estratti
      : m && +m[2] ? m[1] / m[2] : 0;
    $("ricerca-barra").style.width = `${Math.min(100, ((fase - 1 + dentro) / 3) * 100)}%`;
  }
  $("b-ferma").disabled = !!r.finito;
  if (!r.finito) { segui(); return; }
  $("ricerca-barra").style.width = "100%";
  if (r.ultimi_messaggi && r.ultimi_messaggi.length) {
    avviso(`Ricerca ${r.stato}: ${r.ultimi_messaggi.slice(-2).join(" ")}`, true);
  }
  if (r.avviso) avviso(r.avviso, true);
  const p = r.risposta_pronta;
  if (p && stato.ultimaRisposta !== r.documento) {
    stato.ultimaRisposta = r.documento;
    mostra("passo-risposta", true);
    $("risposta-documenti").textContent = p.documenti_pertinenti !== null && p.documenti_pertinenti !== undefined
      ? `Documenti pertinenti: ${p.documenti_pertinenti}` : "";
    $("risposta-testo").textContent = senzaMarkdown(p.risposta);
    const lim = $("risposta-limiti");
    lim.replaceChildren();
    if (p.limiti && p.limiti.length) {
      lim.append(el("h2", "Limiti (i primi)"));
      const ul = el("ul");
      for (const x of p.limiti) ul.append(el("li", senzaMarkdown(x)));
      lim.append(ul);
    }
    $("risposta-apri").href = r.documento;
    apriDocumento(r.documento);
  }
}

async function ferma() {
  try {
    const r = await api("/api/ricerca/ferma", {});
    avviso(r.nota || "");
  } catch (e) {
    avviso(e.message, true);
  }
}

// ------------------------------------------------------------------ storico
async function caricaStorico() {
  const ur = $("storico-risposte");
  const ui = $("storico-ricerche");
  ur.replaceChildren();
  ui.replaceChildren();
  try {
    const s = await api("/api/storico");
    const voce = (ul, testo, data, url) => {
      const li = el("li");
      const a = el("a", testo);
      a.href = url;
      a.addEventListener("click", (e) => { e.preventDefault(); apriDocumento(url); });
      li.append(a, el("span", "  " + data, "nota"));
      ul.append(li);
    };
    for (const r of s.risposte) voce(ur, r.domanda, r.data, r.documento);
    for (const r of s.ricerche) voce(ui, r.cartella, r.data, r.documento);
    if (!s.risposte.length) ur.append(el("li", "Nessuna risposta salvata.", "nota"));
    if (!s.ricerche.length) ui.append(el("li", "Nessuna ricerca.", "nota"));
  } catch (e) {
    ur.append(el("li", e.message, "nota"));
  }
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
    if (a) $("imp-barra").style.width = `${Math.min(100, (a.fatto / Math.max(1, a.totale)) * 100)}%`;
    $("imp-stato").textContent = [r.finita ? "" : (a ? a.testo : "Lavoro in corso…"), importaEsito(r)]
      .filter(Boolean).join(" ");
    const esiti = (r.ultime || []).join("\n");
    $("imp-esiti").textContent = esiti;
    $("imp-esiti").hidden = !esiti;
    if (r.pronta && r.tabella && (!stato.tabella || stato.tabella.tabella !== r.tabella)) caricaTabella(r.tabella);
    if (!r.finita) { seguiImporta(id); return; }
    if (r.finita) caricaTutto();                       // i documenti nuovi entrano fra le fonti
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

function mostraTabella(t) {
  const box = $("imp-tabella");
  box.replaceChildren();
  if (!t) {
    box.hidden = true;
    $("imp-tabella-nome").textContent = "nessuna: il punto 1 non è ancora finito";
    for (const id of ["imp-carica", "imp-salva", "imp-prova", "imp-applica"]) $(id).disabled = true;
    return;
  }
  $("imp-tabella-nome").textContent = `${t.file} — ${t.righe.length} righe` +
    (t.tipo === "revisione" ? ", documenti già importati" : "");
  for (const id of ["imp-carica", "imp-salva", "imp-prova", "imp-applica"]) $(id).disabled = false;
  const colonne = t.colonne.filter((c) => $("imp-avanzate").checked || !COLONNE_AVANZATE.includes(c));
  const tab = el("table", null, "revisione");
  const intestazione = el("tr");
  for (const c of colonne) intestazione.append(el("th", c));
  tab.append(intestazione);
  t.righe.forEach((riga, n) => {
    const tr = el("tr");
    if ((riga.da_controllare || "").trim()) tr.className = "dubbio";
    for (const c of colonne) {
      const td = el("td");
      const i = document.createElement("input");
      i.type = "text";
      i.value = riga[c] || "";
      i.dataset.colonna = c;
      i.dataset.riga = n;
      if (["file", "file_dati", "percorso", "da_controllare"].includes(c)) i.readOnly = true;
      td.append(i);
      tr.append(td);
    }
    tab.append(tr);
  });
  const scroll = el("div", null, "scorrimento");
  scroll.append(tab);
  box.append(el("p", "Le righe con qualcosa da controllare sono in rosso; la colonna «importa» accetta sì o no.",
    "nota"), scroll);
  box.hidden = false;
}

async function salvaTabella() {
  const t = stato.tabella;
  if (!t) return;
  const celle = [...$("imp-tabella").querySelectorAll("input")];
  const righe = t.righe.map((riga, n) => {
    const r = {};
    for (const c of t.colonne) r[c] = riga[c] || "";       // le colonne nascoste restano come sono
    for (const i of celle) if (+i.dataset.riga === n) r[i.dataset.colonna] = i.value.trim();
    return r;
  });
  try {
    const s = await api("/api/tabella", { percorso: t.tabella, righe });
    const nome = s.tabella !== t.tabella ? ` in ${s.tabella} (il file Excel resta com'era)` : "";
    $("imp-stato").textContent =
      `Tabella salvata${nome} (${s.righe} righe): «Controlla senza scrivere», poi «Importa».`;
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

async function caricaConversazione(riprova) {
  const s = $("conv-stato");
  s.textContent = riprova ? "Verifico se il modello sa usare gli strumenti…" : "Un momento…";
  let r;
  try {
    r = await api("/api/conversazione" + (riprova ? "?riprova=1" : ""));
  } catch (e) {
    s.textContent = e.message;
    return;
  }
  mostraConversazione(r);
}

function mostraConversazione(r) {
  const attiva = !!r.attiva;
  $("conv-stato").textContent = attiva
    ? `Modello: ${r.profilo}${r.modello && r.modello !== r.profilo ? " (" + r.modello + ")" : ""}.`
    : (r.motivo || "Conversazione non disponibile.");
  $("conv-stato").classList.toggle("attenzione-testo", !attiva && !r.occupata);
  $("conv-testo").disabled = !attiva;
  $("conv-invia").disabled = !attiva;
  $("conv-riprova").hidden = !r.riprova;
  const box = $("conv-messaggi");
  box.replaceChildren();
  for (const m of r.messaggi || []) box.append(messaggioConversazione(m));
}

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
      span.title += " — clic per il passaggio";
      const apri = () => mostraPassaggio(voce, c);
      span.addEventListener("click", apri);
      span.addEventListener("keydown", (e) => { if (e.key === "Enter") apri(); });
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
  if (stesso) return;
  const q = el("blockquote", null, "conv-passaggio");
  q.dataset.inizio = String(c.inizio);
  q.append(el("p", c.riferimento));
  if (c.passaggio.originale) q.append(el("p", c.passaggio.originale));
  if (c.passaggio.traduzione) q.append(el("p", "Traduzione: " + c.passaggio.traduzione));
  if (c.passaggio.data_documento) q.append(el("p", "Data del documento: " + c.passaggio.data_documento, "nota"));
  voce.append(q);
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

async function inviaConversazione() {
  const testo = $("conv-testo").value.trim();
  if (!testo) { $("conv-testo").focus(); return; }
  const box = $("conv-messaggi");
  box.append(messaggioConversazione({ ruolo: "utente", testo }));
  const attesa = el("div", "Il modello sta consultando le fonti con gli strumenti…", "nota");
  box.append(attesa);
  $("conv-invia").disabled = true;
  $("conv-testo").disabled = true;
  try {
    const voce = await api("/api/conversazione", { testo });
    attesa.replaceWith(messaggioConversazione(voce));
    $("conv-testo").value = "";
    // una ricerca avviata dalla conversazione si segue nel riquadro della ricerca (se è già finita, lì compaiono
    // il riassunto e il documento)
    if ((voce.strumenti || []).some((s) => s.nome === "ricerca" && s.azione === "avvia")) {
      mostraRicerca(await api("/api/ricerca"), false);
    }
  } catch (e) {
    attesa.remove();
    box.lastElementChild.remove();                // la domanda non è rimasta nella conversazione
    avviso(e.message, true);
  } finally {
    $("conv-invia").disabled = false;
    $("conv-testo").disabled = false;
    $("conv-testo").focus();
  }
}

async function nuovaConversazione() {
  try {
    mostraConversazione(await api("/api/conversazione/nuova", {}));
  } catch (e) {
    avviso(e.message, true);
  }
}

// ------------------------------------------------------------------ avvio
document.addEventListener("DOMContentLoaded", () => {
  $("progetto").addEventListener("change", cambiaProgetto);
  $("modello").addEventListener("change", cambiaModello);
  $("np-crea").addEventListener("click", creaProgetto);
  $("am-servizio").addEventListener("change", scegliServizio);
  $("am-elenca").addEventListener("click", elencaModelli);
  $("am-aggiungi").addEventListener("click", aggiungiModello);
  $("b-continua").addEventListener("click", continua);
  $("nome").addEventListener("keydown", (e) => { if (e.key === "Enter") continua(); });
  $("b-esplora").addEventListener("click", esplora);
  $("b-ferma").addEventListener("click", ferma);
  $("b-nuova").addEventListener("click", () => { avviso(""); nuova(); });
  $("b-storico").addEventListener("click", () => apriScheda("storico"));
  $("b-importa").addEventListener("click", () => apriScheda("importazioni"));
  $("imp-proponi").addEventListener("click", () => avviaImporta("proponi", $("imp-cartella").value.trim()));
  $("imp-rivedi").addEventListener("click", () => avviaImporta("rivedi", ""));
  $("imp-carica").addEventListener("click", () => stato.tabella && caricaTabella(stato.tabella.tabella));
  $("imp-salva").addEventListener("click", salvaTabella);
  $("imp-avanzate").addEventListener("change", () => stato.tabella && mostraTabella(stato.tabella));
  $("imp-prova").addEventListener("click", () => stato.tabella && avviaImporta("applica", stato.tabella.tabella, true));
  $("imp-applica").addEventListener("click", () => stato.tabella && avviaImporta("applica", stato.tabella.tabella));
  document.querySelectorAll(".schede button").forEach((b) => b.addEventListener("click", () => apriScheda(b.dataset.scheda)));
  $("fonte-prima").addEventListener("click", () => sfoglia(-1));
  $("fonte-dopo").addEventListener("click", () => sfoglia(1));
  $("fonte-pagine").addEventListener("change", () => stato.fonte && apriFonte(stato.fonte.file, null, $("fonte-pagine").value));
  $("fonte-immagine").addEventListener("change", mostraImmagine);
  $("passaggi-filtro").addEventListener("input", filtraPassaggi);
  $("gl-filtro").addEventListener("input", filtraGlossario);
  // la verifica del modello costa una richiesta al servizio: si fa solo quando la conversazione si apre
  $("conversazione").addEventListener("toggle", () => { if ($("conversazione").open) caricaConversazione(false); });
  $("conv-invia").addEventListener("click", inviaConversazione);
  $("conv-testo").addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) inviaConversazione(); });
  $("conv-nuova").addEventListener("click", nuovaConversazione);
  $("conv-riprova").addEventListener("click", () => caricaConversazione(true));
  $("b-preparazione").addEventListener("click", apriAvvio);
  $("av-ambiente").addEventListener("toggle", () => { if ($("av-ambiente").open) caricaAmbiente(); });
  $("cl-scrivi").addEventListener("click", collegaClient);
  // al primo avvio (o se manca il progetto o il modello) la preparazione si apre da sé
  caricaTutto().then(() => api("/api/avvio")).then((r) => { if (!r.completo) apriAvvio(); }).catch(() => {});
});

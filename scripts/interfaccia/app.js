// Interfaccia di AIrchivist (lavoro 35): menu Progetto e Modello, percorso guidato della ricerca.
// Tutto passa dalle API di app.py; i testi delle fonti si inseriscono sempre come testo, mai come HTML.
"use strict";

const $ = (id) => document.getElementById(id);
const NUOVO = "__nuovo__";
const stato = { schede: [], nome: "", attesa: null, attesaImporta: null, ultimaRisposta: "" };

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
}

function apriDocumento(url) {
  if (!url) return;
  const f = $("documento");
  f.src = url;
  f.hidden = false;
  mostra("risposta-vuota", false);
  apriScheda("risposta");
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

async function cambiaProgetto() {
  const sel = $("progetto");
  if (sel.value === NUOVO) {
    sel.value = sel.dataset.attuale;
    $("np-nome").value = "";
    $("np-descrizione").value = "";
    $("d-progetto").showModal();
    return;
  }
  try {
    await api("/api/progetto", { cartella: sel.value });
    nuova();
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
  } catch (e) {
    m.textContent = e.message;
  } finally {
    $("am-aggiungi").disabled = false;
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
  const parti = [r.stato, r.fase, r.avanzamento, r.minuti ? `${r.minuti} min` : ""].filter(Boolean);
  if (r.prossimo_tentativo) parti.push(`nuovo tentativo: ${r.prossimo_tentativo}`);
  $("ricerca-stato").textContent = parti.join(" · ");
  // la barra segue le tre fasi (estrazione, lettura, risposta) e, dentro la lettura, i passaggi letti
  const f = /(\d)\s*\/\s*3/.exec(r.fase || "");
  const m = /(\d+)\s*\/\s*(\d+)/.exec(r.avanzamento || "");
  if (f) {
    const fase = +f[1];
    const dentro = fase === 2 && m && +m[2] ? m[1] / m[2] : 0;
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

// ------------------------------------------------------------------ importazione
async function importa(azione, prova) {
  const percorso = azione === "proponi" ? $("imp-cartella").value.trim() : $("imp-tabella").value.trim();
  if (!percorso) return;
  const reg = $("imp-registro");
  reg.hidden = false;
  reg.textContent = "Avviata…";
  try {
    const r = await api("/api/importa", { azione, percorso, prova });
    seguiImporta(r.id);
  } catch (e) {
    reg.textContent = e.message;
  }
}

function seguiImporta(id) {
  clearTimeout(stato.attesaImporta);
  stato.attesaImporta = setTimeout(async () => {
    try {
      const r = await api("/api/importa?id=" + encodeURIComponent(id));
      $("imp-registro").textContent = r.registro || r.errore || "…";
      if (r.tabella) $("imp-tabella").value = r.tabella;
      if (!r.finita) seguiImporta(id);
      else { caricaTutto(); }
    } catch (e) {
      $("imp-registro").textContent = e.message;
    }
  }, 2000);
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
  $("imp-proponi").addEventListener("click", () => importa("proponi", false));
  $("imp-prova").addEventListener("click", () => importa("applica", true));
  $("imp-applica").addEventListener("click", () => importa("applica", false));
  document.querySelectorAll(".schede button").forEach((b) => b.addEventListener("click", () => apriScheda(b.dataset.scheda)));
  caricaTutto();
});

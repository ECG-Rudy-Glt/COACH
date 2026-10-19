"use strict";

const app = document.getElementById("app");
const DOMAINS = {
  goals: "Objectifs et corps", health: "Santé", constraints: "Contraintes", history: "Parcours",
  multisport: "Multisport", running: "Course à pied", trail: "Trail", strength: "Musculation",
  hybrid: "Hyrox et CrossFit", cycling: "Vélo", mobility: "Mobilité", project: "Votre projet",
};
const OTHER = "autre";
const ICONS = {
  check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
  back: '<path d="M15 5l-7 7 7 7"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  trash: '<path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12"/>',
  next: '<path d="M9 5l7 7-7 7"/>',
  home: '<path d="M4 11l8-7 8 7v8a1 1 0 01-1 1h-4v-6H9v6H5a1 1 0 01-1-1z"/>',
  plan: '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M9 3v4M15 3v4"/>',
  goals: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3.5"/>',
  lib: '<path d="M3 10v4M6 8v8M18 8v8M21 10v4M6 12h12"/>',
  food: '<path d="M7 3v8M5 3v5a2 2 0 004 0V3M7 11v10M17 3c-2 2-3 4.5-3 7 0 1.5 1 2.5 3 3v8"/>',
  chat: '<path d="M5 6h14a1 1 0 011 1v8a1 1 0 01-1 1h-7l-4 3v-3H5a1 1 0 01-1-1V7a1 1 0 011-1z"/>',
  user: '<circle cx="12" cy="8.5" r="3.5"/><path d="M5 20c1-4 4-5.5 7-5.5s6 1.5 7 5.5"/>',
};

const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* stockage indisponible */ } },
  del(k) { try { localStorage.removeItem(k); } catch { /* idem */ } },
};

let bank = [];
let byId = new Map();
let userId = null;
let userName = "";

// ---------- utilitaires ----------
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === false || v == null) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "pressed") el.setAttribute("aria-pressed", String(v));
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.innerHTML = ICONS[name]; // constantes internes uniquement
  return svg;
}

function tabbar(active) {
  const tabs = [["home", "Accueil", () => home()], ["plan", "Plan", () => planScreen()], ["food", "Nutrition", () => nutritionScreen()], ["goals", "Objectifs", () => goalsScreen()],
    ["chat", "Coach", () => coachChat()], ["user", "Profil", () => profile()]];
  return h("div", { class: "tabbar" }, h("nav", { "aria-label": "Navigation" }, tabs.map(([k, name, fn]) =>
    h("button", { type: "button", "aria-current": k === active ? "page" : false, onclick: fn }, icon(k), name))));
}

let flushActive = null; // enregistrement en attente de l'écran affiché (séance en cours de saisie)
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden" && flushActive) flushActive(true); });
addEventListener("pagehide", () => { if (flushActive) flushActive(true); });
// clavier ouvert : les barres fixes flottent au milieu de l'écran sur iPhone, on les masque pendant la saisie
const typing = (el) => el && el.matches && el.matches('textarea, input:not([type="checkbox"]):not([type="radio"]):not([type="button"])');
if (window.visualViewport) {
  const vv = window.visualViewport;
  const check = () => document.body.classList.toggle("kb", innerHeight - vv.height > 160 && typing(document.activeElement));
  vv.addEventListener("resize", check);
  vv.addEventListener("scroll", check);
  document.addEventListener("focusout", () => setTimeout(check, 50));
}

const scrollMemo = {}; // position de défilement à retrouver quand on revient d'un écran de détail
function show(...nodes) {
  flushActive = null;
  document.body.classList.remove("kb");
  const list = nodes.flat().filter((n) => n && n.nodeType);
  app.className = list.some((n) => n.classList.contains("tabbar")) ? "tabs" : "";
  app.replaceChildren(...list);
  window.scrollTo(0, 0);
}

function toast(msg) {
  const t = h("div", { class: "toast", role: "status" }, msg);
  document.body.append(t);
  setTimeout(() => t.remove(), 2200);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: opts.body ? { "Content-Type": "application/json" } : undefined,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    keepalive: opts.keepalive || undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* corps vide */ }
  if (!res.ok) {
    const msg = Array.isArray(data?.detail) ? data.detail.map((d) => d.msg).filter(Boolean).join(" ; ") : data?.detail;
    const err = new Error(typeof msg === "string" && msg ? msg : `Erreur ${res.status}`);
    err.status = res.status;
    if (res.status === 401 && !path.startsWith("/auth/")) { userId = null; authScreen(); err.handled = true; }
    throw err;
  }
  return data;
}

function fmtDuration(min) {
  const hh = Math.floor(min / 60), m = Math.round(min % 60);
  return hh ? `${hh} h${m ? " " + String(m).padStart(2, "0") : ""}` : `${m} min`;
}

function label(q, o) { return o === OTHER ? "Autre…" : (q.option_labels && q.option_labels[o]) || o; }

function fmtEntry(q, e) {
  const parts = (q.fields || []).filter((f) => e[f.id] != null && e[f.id] !== "")
    .map((f) => ({ f, v: e[f.id] }));
  const first = parts.shift();
  const rest = parts.map(({ f, v }) => `${f.label.replace(/ \(.*\)$/, "")} ${v}${f.unit ? " " + f.unit : ""}`).join(" · ");
  return { title: first ? String(first.v) : "", sub: rest };
}

function fmtValue(q, facts) {
  const v = facts[q.fact_key];
  const other = facts[q.fact_key + ".other"];
  if (q.type === "entries") return Array.isArray(v) && v.length ? `${v.length} ${v.length > 1 ? "entrées" : "entrée"}` : "Rien à signaler";
  if (Array.isArray(v)) return v.map((x) => (x === OTHER && other ? other : label(q, x))).join(", ");
  if (v === OTHER && other) return other;
  if (q.type === "single") return label(q, v);
  if (q.type === "duration") return fmtDuration(v);
  if (q.type === "date") return new Date(v).toLocaleDateString("fr-FR");
  if (q.type === "number" && q.unit) return `${v} ${q.unit}`;
  if (q.type === "scale") return `${v} sur 5`;
  return String(v);
}

function fail(err) {
  if (err.handled) return;
  show(h("div", { class: "card stack" }, h("h3", null, "Connexion impossible"),
    h("p", { class: "muted" }, err.message || "Vérifiez votre connexion (VPN actif ?)."),
    h("button", { class: "btn primary", onclick: start }, "Réessayer")));
}

// ---------- thème (clair, sombre, éco : comme le portfolio) ----------
const THEMES = [["light", "☀", "Clair"], ["dark", "☾", "Sombre"], ["eco", "◐", "Éco (noir et blanc)"]];
const THEME_COLORS = { light: "#ece6d9", dark: "#14100c", eco: "#f7f5f1" };

function currentTheme() {
  const stored = store.get("theme");
  if (THEMES.some(([v]) => v === stored)) return stored;
  return window.matchMedia && matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme) {
  document.documentElement.className = theme;
  store.set("theme", theme);
  document.querySelectorAll('meta[name="theme-color"]').forEach((m) => { m.removeAttribute("media"); m.setAttribute("content", THEME_COLORS[theme]); });
}

function themeToggle() {
  const box = h("div", { class: "themes", role: "group", "aria-label": "Thème" });
  const draw = () => box.replaceChildren(...THEMES.map(([v, glyph, name]) =>
    h("button", { type: "button", "aria-label": name, title: name, pressed: currentTheme() === v,
      onclick: () => { applyTheme(v); draw(); } }, glyph)));
  draw();
  return box;
}

function actionBar(...nodes) { return h("div", { class: "bar" }, h("div", null, ...nodes)); }

function segments(done, remaining) {
  const total = done + remaining || 1;
  const on = Math.round((done / total) * 24);
  return h("div", { class: "seg", role: "progressbar", "aria-valuenow": Math.round((done / total) * 100), "aria-valuemin": 0, "aria-valuemax": 100 },
    Array.from({ length: 24 }, (_, i) => h("i", { class: i < on ? "on" : i === on ? "cur" : "" })));
}

// ---------- accueil ----------
function authScreen(mode = "login") {
  const reg = mode === "register";
  const err = h("p", { class: "error", role: "alert" });
  const f = (id, labelText, attrs) => h("div", { class: "field" }, h("label", { for: id }, labelText), h("input", { id, ...attrs }));
  const name = f("name", "Prénom", { type: "text", autocomplete: "given-name" });
  const email = f("email", "Email", { type: "email", autocomplete: "email", inputmode: "email" });
  const pw = f("pw", reg ? "Mot de passe (10 caractères minimum)" : "Mot de passe",
    { type: "password", autocomplete: reg ? "new-password" : "current-password" });
  const adopt = h("select", { id: "adopt" });
  const adoptBox = h("div", { class: "field", hidden: true }, h("label", { for: "adopt" }, "Reprendre un profil existant"), adopt);
  if (reg) {
    api("/auth/status").then((st) => {
      if (st.registration !== "open") { err.textContent = "Les inscriptions sont fermées."; return; }
      if (st.legacy.length) {
        adopt.replaceChildren(h("option", { value: "" }, "Non, nouveau profil"),
          ...st.legacy.map((u) => h("option", { value: u.id }, `${u.name} (${u.answers} réponses)`)));
        adoptBox.hidden = false;
      }
    }).catch(() => {});
  }
  const go = async () => {
    err.textContent = "";
    const body = { email: email.querySelector("input").value, password: pw.querySelector("input").value };
    if (reg) { body.name = name.querySelector("input").value; if (adopt.value) body.adopt_user_id = Number(adopt.value); }
    try {
      const r = await api(reg ? "/auth/register" : "/auth/login", { method: "POST", body });
      userId = String(r.id); userName = r.name;
      home();
    } catch (e) { err.textContent = e.message; }
  };
  app.onkeydown = (e) => { if (e.key === "Enter" && e.target.tagName === "INPUT") go(); };
  show(
    h("div", { class: "head" }, h("span", { class: "eyebrow" }, "Sport Coach"), themeToggle()),
    h("h1", null, reg ? "Créer votre compte" : "Content de vous revoir."),
    h("p", { class: "muted" }, reg
      ? "Vos données restent sur votre serveur. Un compte protège votre profil et votre historique."
      : "Connectez-vous pour retrouver votre profil et votre historique."),
    h("div", { class: "card stack" }, reg ? name : null, email, pw, reg ? adoptBox : null, err),
    h("button", { class: "link", onclick: () => authScreen(reg ? "login" : "register") },
      reg ? "J'ai déjà un compte" : "Créer un compte"),
    actionBar(h("button", { class: "btn primary", onclick: go }, reg ? "Créer mon compte" : "Se connecter")),
  );
}

function passwordScreen() {
  const err = h("p", { class: "error", role: "alert" });
  const f = (id, text, ac) => h("div", { class: "field" }, h("label", { for: id }, text), h("input", { id, type: "password", autocomplete: ac }));
  const cur = f("pw-cur", "Mot de passe actuel", "current-password");
  const nw = f("pw-new", "Nouveau mot de passe (10 caractères minimum)", "new-password");
  const go = async () => {
    err.textContent = "";
    try {
      await api("/auth/change-password", { method: "POST", body: { current: cur.querySelector("input").value, new: nw.querySelector("input").value } });
      toast("Mot de passe modifié"); home();
    } catch (e) { err.textContent = e.message; }
  };
  show(
    h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: home }, icon("back")), h("span", { class: "grow" })),
    h("h1", null, "Changer mon mot de passe"),
    h("p", { class: "muted" }, "Vos autres appareils seront déconnectés."),
    h("div", { class: "card stack" }, cur, nw, err),
    actionBar(h("button", { class: "btn primary", onclick: go }, "Enregistrer")),
  );
}

async function logout() {
  try { await api("/auth/logout", { method: "POST" }); } catch { /* déjà déconnecté */ }
  userId = null; userName = "";
  authScreen();
}

async function home() {
  let prof, bench, goalsData;
  try {
    [prof, bench, goalsData] = await Promise.all([api(`/users/${userId}/profile`), api(`/users/${userId}/benchmarks`),
      api(`/users/${userId}/goals?status=active`)]);
  } catch (e) {
    return fail(e);
  }
  const total = prof.answered + prof.remaining_visible;
  const pct = total ? Math.round((prof.answered / total) * 100) : 0;
  const C = 2 * Math.PI * 46;
  const ring = h("div", { class: "ring" },
    (() => {
      const s = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      s.setAttribute("viewBox", "0 0 112 112");
      s.innerHTML = `<circle class="t" cx="56" cy="56" r="46"/><circle class="v" cx="56" cy="56" r="46" stroke-dasharray="${C}" stroke-dashoffset="${C * (1 - pct / 100)}"/>`;
      return s;
    })(),
    h("b", null, `${pct}%`));
  const finished = prof.remaining_visible === 0;
  const domainRows = Object.entries(prof.domains || {}).map(([d, st]) => {
    const t = st.answered + st.remaining;
    return h("button", { class: "dom", disabled: !st.remaining, onclick: () => nextQuestion(d) },
      h("span", { class: "grow" }, DOMAINS[d] || d),
      h("span", { class: "mini" }, h("i", { style: `width:${t ? (st.answered / t) * 100 : 0}%` })),
      h("span", { class: "count num" }, `${st.answered}/${t}`),
      st.remaining ? icon("next") : null);
  });
  show(
    h("div", { class: "head" }, h("span", { class: "eyebrow" }, userName ? `Bonjour ${userName}` : "Bonjour"), themeToggle()),
    h("div", { class: "hero" }, ring,
      h("div", { class: "stack grow" },
        h("h1", null, finished ? "Profil complet" : "Votre profil"),
        h("p", { class: "muted" }, finished ? "Il s'enrichira avec vos séances." : `${prof.remaining_visible} questions pour l'instant. Elles s'adaptent à vos réponses.`))),
    finished ? null : h("button", { class: "btn primary", onclick: () => nextQuestion() }, prof.answered ? "Continuer le questionnaire" : "Commencer le questionnaire"),
    goalsCard(goalsData),
    planCard(),
    bench.novice
      ? h("div", { class: "card" }, h("h3", null, "Vos repères"), h("p", { class: "muted" }, "Pas de record à saisir pour l'instant : vos premières séances serviront de référence, et le coach en déduira vos charges."))
      : bench.total
      ? h("div", { class: "card row" },
        h("div", { class: "grow stack" }, h("h3", null, "Mes performances"),
          h("p", { class: "muted" }, `Record et niveau actuel par exercice. ${bench.filled} sur ${bench.total} renseignés.`)),
        h("button", { class: "btn sm", onclick: benchmarks }, "Remplir"))
      : prof.answered
        ? h("div", { class: "card" }, h("p", { class: "muted" }, "Choisissez vos sports dans le questionnaire : la page des performances apparaîtra ensuite."))
        : null,
    domainRows.length ? h("div", { class: "card" }, h("h3", null, "Par thème"), h("div", { style: "margin-top:8px" }, domainRows)) : null,
    tabbar("home"),
  );
}

// ---------- questions ----------
async function nextQuestion(domain) {
  let r;
  try { r = await api(`/users/${userId}/questions/next?n=1${domain ? `&domain=${domain}` : ""}`); } catch (e) { return fail(e); }
  if (!r.questions.length) return home();
  questionView(r.questions[0], { progress: r, domain, onDone: () => nextQuestion(domain), onBack: home });
}

function questionView(q, { progress, prefill, onDone, onBack, editing }) {
  const bq = byId.get(q.id) || q;
  const st = {
    value: prefill?.value ?? null, other: prefill?.other ?? "", hours: "", minutes: "",
    entries: Array.isArray(prefill?.value) && bq.type === "entries" ? [...prefill.value] : [], draft: {},
  };
  if (bq.type === "duration" && typeof st.value === "number") { st.hours = Math.floor(st.value / 60); st.minutes = st.value % 60; }
  const errBox = h("p", { class: "error", role: "alert" });
  const body = h("div", { class: "stack" });
  const submit = h("button", { class: "btn primary", onclick: () => send() }, editing ? "Enregistrer" : "Valider");

  const hasOther = () => (bq.type === "single" ? st.value === OTHER : Array.isArray(st.value) && st.value.includes(OTHER));
  const valid = () => {
    switch (bq.type) {
      case "single": return st.value != null && (st.value !== OTHER || st.other.trim());
      case "multi": return Array.isArray(st.value) && st.value.length > 0 && (!st.value.includes(OTHER) || st.other.trim());
      case "number": return typeof st.value === "number" && st.value >= 0;
      case "duration": return (st.hours !== "" || st.minutes !== "") && Number(st.hours || 0) * 60 + Number(st.minutes || 0) >= 0;
      case "scale": return Number.isInteger(st.value);
      case "date": return !!st.value;
      case "entries": return st.entries.length > 0;
      default: return typeof st.value === "string" && st.value.trim() !== "";
    }
  };
  const refresh = () => { submit.disabled = !valid(); };

  async function send(forced) {
    let v = st.value;
    if (bq.type === "duration") v = Number(st.hours || 0) * 60 + Number(st.minutes || 0);
    if (bq.type === "entries") v = forced ?? st.entries;
    if (forced === undefined && !valid()) return;
    submit.disabled = true;
    try {
      await api(`/users/${userId}/answers`, {
        method: "POST",
        body: { question_id: bq.id, value: v, other_text: hasOther() ? st.other.trim() : null },
      });
      onDone();
    } catch (e) { errBox.textContent = e.message; submit.disabled = false; }
  }

  async function skip() {
    try { await api(`/users/${userId}/skip`, { method: "POST", body: { question_id: bq.id } }); onDone(); }
    catch (e) { errBox.textContent = e.message; }
  }

  function drawEntries() {
    const nodes = st.entries.map((e, i) => {
      const { title, sub } = fmtEntry(bq, e);
      return h("div", { class: "entry" },
        h("div", { class: "grow" }, title, sub && h("span", { class: "sub" }, sub)),
        h("button", { class: "iconbtn", "aria-label": "Retirer cette ligne", onclick: () => { st.entries.splice(i, 1); draw(); refresh(); } }, icon("trash")));
    });
    const inputs = [];
    const fieldsEl = bq.fields.map((f) => {
      const id = `f-${bq.id}-${f.id}`.replace(/[^\w-]/g, "_");
      let ctl;
      if (f.type === "single") {
        ctl = h("select", { id }, h("option", { value: "" }, "Choisir…"), f.options.map((o) => h("option", { value: o }, o)));
        ctl.value = st.draft[f.id] ?? "";
      } else {
        ctl = h("input", {
          id, type: f.type === "text" ? "text" : f.type === "date" ? "date" : "number",
          inputmode: f.type === "text" || f.type === "date" ? "text" : "decimal",
          step: f.type === "year" ? "1" : "any", min: "0",
          placeholder: f.type === "year" ? "2019" : "", autocomplete: "off",
        });
        ctl.value = st.draft[f.id] ?? "";
      }
      ctl.addEventListener("input", () => { st.draft[f.id] = ctl.value; check(); });
      inputs.push({ f, ctl });
      return h("div", { class: "field" }, h("label", { for: id }, f.label + (f.optional ? " (facultatif)" : "")), ctl);
    });
    const add = h("button", { class: "btn sm", type: "button", onclick: () => {
      const e = {};
      for (const { f, ctl } of inputs) {
        const raw = ctl.value.trim();
        if (raw === "") continue;
        e[f.id] = ["single", "text", "date"].includes(f.type) ? raw : Number(raw);
      }
      st.entries.push(e); st.draft = {}; draw(); refresh();
    } }, icon("plus"), "Ajouter cette ligne");
    function check() {
      add.disabled = !inputs.every(({ f, ctl }) => f.optional || ctl.value.trim() !== "");
    }
    check();
    nodes.push(h("div", { class: "form" }, fieldsEl, add));
    return nodes;
  }

  function draw() {
    const nodes = [];
    const opts = [...(bq.options || []), ...(bq.allow_other ? [OTHER] : [])];
    if (bq.type === "single" || bq.type === "multi") {
      const multi = bq.type === "multi";
      const two = opts.length >= 4 && opts.every((o) => label(bq, o).length <= 18);
      nodes.push(h("div", { class: "opts" + (two ? " two" : "") }, opts.map((o) => {
        const on = multi ? Array.isArray(st.value) && st.value.includes(o) : st.value === o;
        return h("button", {
          class: "opt" + (multi ? "" : " radio"), pressed: on, type: "button",
          onclick: () => {
            if (multi) {
              const set = new Set(Array.isArray(st.value) ? st.value : []);
              set.has(o) ? set.delete(o) : set.add(o);
              st.value = [...set];
            } else {
              st.value = o;
              if (o !== OTHER && !editing) { draw(); refresh(); return send(); }
            }
            draw(); refresh();
          },
        }, h("span", { class: "tick" }, icon("check")), label(bq, o));
      })));
      if (hasOther()) {
        nodes.push(h("input", { type: "text", id: "autre", placeholder: "Précisez", value: st.other, "aria-label": "Précisez",
          oninput: (e) => { st.other = e.target.value; refresh(); } }));
      }
    } else if (bq.type === "number") {
      nodes.push(h("div", { class: "stack" },
        h("input", { class: "big", type: "number", id: "num", inputmode: "decimal", step: "any", min: "0", value: st.value ?? "", placeholder: "0", "aria-label": bq.text,
          oninput: (e) => { st.value = e.target.value === "" ? null : Number(e.target.value); refresh(); } }),
        bq.unit && h("p", { class: "unit", style: "text-align:center" }, bq.unit)));
    } else if (bq.type === "duration") {
      nodes.push(h("div", { class: "grid2" },
        h("div", { class: "field" }, h("label", { for: "dur-h" }, "Heures"),
          h("input", { class: "big", id: "dur-h", type: "number", inputmode: "numeric", min: "0", placeholder: "0", value: st.hours,
            oninput: (e) => { st.hours = e.target.value; refresh(); } })),
        h("div", { class: "field" }, h("label", { for: "dur-m" }, "Minutes"),
          h("input", { class: "big", id: "dur-m", type: "number", inputmode: "numeric", min: "0", max: "59", placeholder: "00", value: st.minutes,
            oninput: (e) => { st.minutes = e.target.value; refresh(); } }))));
    } else if (bq.type === "scale") {
      nodes.push(h("div", { class: "scale" }, [1, 2, 3, 4, 5].map((n) =>
        h("button", { class: "opt radio", type: "button", pressed: st.value === n, onclick: () => { st.value = n; draw(); refresh(); } }, n))));
      nodes.push(h("div", { class: "row between muted" }, h("span", null, "Faible"), h("span", null, "Élevé")));
    } else if (bq.type === "date") {
      nodes.push(h("input", { type: "date", id: "date", value: st.value ?? "", "aria-label": bq.text, oninput: (e) => { st.value = e.target.value; refresh(); } }));
    } else if (bq.type === "entries") {
      nodes.push(...drawEntries());
    } else {
      nodes.push(h("textarea", { id: "txt", "aria-label": bq.text, oninput: (e) => { st.value = e.target.value; refresh(); } }, st.value ?? ""));
    }
    body.replaceChildren(...nodes);
  }

  draw(); refresh();
  const canSkip = !bq.blocking && !editing;
  show(
    h("div", { class: "top" },
      h("button", { class: "iconbtn", "aria-label": "Retour", onclick: onBack }, icon("back")),
      progress ? segments(progress.answered, progress.remaining_visible) : h("span", { class: "grow" })),
    h("span", { class: "eyebrow" }, DOMAINS[bq.domain] || bq.domain),
    h("h2", { class: "q" }, bq.text),
    bq.type === "multi" && h("p", { class: "muted" }, "Plusieurs réponses possibles."),
    bq.help && h("p", { class: "muted" }, bq.help),
    body,
    errBox,
    bq.required && canSkip && h("p", { class: "muted" }, "Cette réponse aide à personnaliser votre plan, mais vous pouvez la passer."),
    actionBar(
      submit,
      h("div", { class: "links" },
        bq.type === "entries" && !editing && h("button", { class: "link", onclick: () => send([]) }, "Rien à signaler"),
        canSkip && h("button", { class: "link", onclick: skip }, "Préférer ne pas répondre")),
    ),
  );
}

// ---------- performances ----------
async function benchmarks() {
  let page;
  try { page = await api(`/users/${userId}/benchmarks`); } catch (e) { return fail(e); }
  const vals = JSON.parse(JSON.stringify(page.values || {}));
  const dirty = new Set();
  const save = h("button", { class: "btn primary", disabled: true }, "Enregistrer");
  const mark = (id) => { dirty.add(id); save.disabled = false; save.textContent = `Enregistrer (${dirty.size})`; };

  const cell = (it, side, title) => {
    vals[it.id] = vals[it.id] || {};
    const cur = vals[it.id][side] || {};
    const set = (k, v) => {
      vals[it.id][side] = vals[it.id][side] || {};
      if (v === "") delete vals[it.id][side][k]; else vals[it.id][side][k] = it.kind === "time" ? v : Number(v);
      mark(it.id);
    };
    const num = (k, ph, unit) => h("input", { type: "number", inputmode: "decimal", step: "any", min: "0", placeholder: ph,
      value: cur[k] ?? "", "aria-label": `${it.label}, ${title.toLowerCase()}, ${unit}`, oninput: (e) => set(k, e.target.value) });
    let inputs;
    if (it.kind === "weight_reps") inputs = h("div", { class: "pair" }, num("weight", "kg", "kg"), h("span", { class: "x" }, "×"), num("reps", "reps", "répétitions"));
    else if (it.kind === "reps") inputs = num("reps", "reps", "répétitions");
    else if (it.kind === "rounds") inputs = num("reps", "tours", "tours");
    else if (it.kind === "watts") inputs = num("watts", "W", "watts");
    else inputs = h("input", { type: "text", inputmode: "numeric", placeholder: "mm:ss", value: cur.time ?? "", "aria-label": `${it.label}, ${title.toLowerCase()}, temps`, oninput: (e) => set("time", e.target.value.trim()) });
    return h("div", { class: "cell" }, h("span", null, title), inputs);
  };

  const sections = page.sections.map((s) => h("div", { class: "card" }, h("h3", null, s.title),
    h("div", { style: "margin-top:6px" }, s.items.map((it) =>
      h("div", { class: "bench" }, h("strong", null, it.label),
        h("div", { class: "cols" }, cell(it, "pr", "Record"), cell(it, "now", "Actuel")))))));

  save.addEventListener("click", async () => {
    const items = {};
    for (const id of dirty) items[id] = vals[id];
    save.disabled = true;
    try {
      await api(`/users/${userId}/benchmarks`, { method: "PUT", body: { items } });
      dirty.clear(); save.textContent = "Enregistrer"; toast("Performances enregistrées");
    } catch (e) { save.disabled = false; toast(e.message); }
  });

  show(
    h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: home }, icon("back")), h("span", { class: "grow" })),
    h("span", { class: "eyebrow" }, "Performances"),
    h("h1", null, "Record et niveau actuel"),
    h("p", { class: "muted" }, "Renseignez ce que vous connaissez. Une estimation suffit pour le niveau actuel. Les lignes vides sont ignorées. Temps au format mm:ss ou h:mm:ss."),
    sections.length ? sections : h("p", { class: "muted" }, "Choisissez d'abord vos sports dans le questionnaire."),
    actionBar(save),
  );
}

// ---------- profil ----------
async function profile() {
  let prof;
  try { prof = await api(`/users/${userId}/profile`); } catch (e) { return fail(e); }
  const facts = prof.facts;
  const groups = new Map();
  for (const q of bank) {
    if (facts[q.fact_key] == null) continue;
    if (!groups.has(q.domain)) groups.set(q.domain, []);
    groups.get(q.domain).push(q);
  }
  const sections = Object.keys(DOMAINS).filter((d) => groups.has(d)).map((d) =>
    h("div", { class: "card" }, h("span", { class: "eyebrow" }, DOMAINS[d]),
      h("div", { style: "margin-top:6px" }, groups.get(d).sort((a, b) => a.order - b.order).map((q) =>
        h("button", { class: "item", onclick: () => edit(q, facts) },
          h("span", { class: "l" }, q.text), h("span", { class: "v" }, fmtValue(q, facts)))))));
  show(
    h("div", { class: "top" }, h("span", { class: "grow" }), h("span", { class: "muted" }, `${prof.answered} réponses`)),
    h("h1", null, "Profil"),
    sections.length ? sections : h("p", { class: "muted" }, "Rien pour l'instant."),
    h("div", { class: "card row" },
      h("div", { class: "grow stack" }, h("h3", null, "Garmin"), h("p", { class: "muted" }, "Importez vos activités pour ajuster le plan.")),
      h("button", { class: "btn sm", onclick: garminScreen }, "Ouvrir")),
    h("div", { class: "card row" },
      h("div", { class: "grow stack" }, h("h3", null, "Bibliothèque d'exercices"), h("p", { class: "muted" }, "Plus de 1 700 exercices avec schémas, illustrations et vidéos.")),
      h("button", { class: "btn sm", onclick: () => library() }, "Explorer")),
    h("div", { class: "card row" },
      h("div", { class: "grow stack" }, h("h3", null, "Sources scientifiques"), h("p", { class: "muted" }, "Les publications qui fondent le plan, la nutrition et le coach.")),
      h("button", { class: "btn sm", onclick: () => evidenceScreen() }, "Consulter")),
    h("div", { class: "card stack" }, h("h3", null, "Compte"),
      h("button", { class: "link", style: "text-align:left", onclick: passwordScreen }, "Changer mon mot de passe"),
      h("button", { class: "link", style: "text-align:left", onclick: logout }, "Se déconnecter")),
    tabbar("user"),
  );
}

function edit(q, facts) {
  questionView(q, {
    editing: true,
    prefill: { value: facts[q.fact_key], other: facts[q.fact_key + ".other"] || "" },
    onDone: profile,
    onBack: profile,
  });
}

// ---------- objectifs (à tout moment) ----------
const KINDS = { event: "Course ou événement", performance: "Performance", body: "Corps et poids", health: "Santé", habit: "Habitude", other: "Autre" };
const PRIORITIES = ["principal", "important", "si possible"];

function countdown(iso) {
  if (!iso) return "Sans échéance";
  const days = Math.round((new Date(iso) - new Date(new Date().toDateString())) / 86400000);
  if (days < 0) return `Échéance dépassée de ${-days} j`;
  if (days === 0) return "Aujourd'hui";
  return days < 14 ? `Dans ${days} jours` : `Dans ${Math.round(days / 7)} semaines`;
}

function goalsCard(data) {
  const next = data.goals[0];
  return h("div", { class: "card row" },
    h("div", { class: "grow stack" }, h("h3", null, "Mes objectifs"),
      h("p", { class: "muted" }, next
        ? `${data.goals.length} actif${data.goals.length > 1 ? "s" : ""}. Prochain : ${next.title}, ${countdown(next.target_date).toLowerCase()}.`
        : "Ajoutez ce que vous voulez accomplir. Vous pouvez en ajouter ou en changer à tout moment.")),
    h("button", { class: "btn sm", onclick: goalsScreen }, next ? "Gérer" : "Ajouter"));
}

async function goalsScreen() {
  let all;
  try { all = await api(`/users/${userId}/goals`); } catch (e) { return fail(e); }
  const active = all.goals.filter((g) => g.status === "active");
  const closed = all.goals.filter((g) => g.status !== "active");
  const row = (g) => h("button", { class: "item", onclick: () => goalForm(g) },
    h("span", { class: "l" }, h("strong", null, g.title),
      h("span", { class: "sub", style: "display:block;font-weight:400;color:var(--muted);font-size:.9rem" },
        `${KINDS[g.kind] || g.kind} · ${g.priority}`)),
    h("span", { class: "v" }, g.status === "active" ? countdown(g.target_date) : g.status === "done" ? "Terminé" : "Abandonné"));
  show(
    h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: home }, icon("back")), h("span", { class: "grow" })),
    h("span", { class: "eyebrow" }, "Projet"),
    h("h1", null, "Mes objectifs"),
    h("p", { class: "muted" }, "Ajoutez, modifiez ou clôturez vos objectifs quand vous voulez. Le plan s'ajuste à partir de la semaine suivante."),
    all.conflicts.length ? h("div", { class: "card" }, h("p", null, "Deux événements sont à moins de six semaines l'un de l'autre. Le plan devra faire un choix : gardez-en un comme principal.")) : null,
    active.length ? h("div", { class: "card" }, active.map(row)) : h("p", { class: "muted" }, "Aucun objectif actif pour l'instant."),
    closed.length ? h("div", { class: "card" }, h("h3", null, "Historique"), h("div", { style: "margin-top:6px" }, closed.map(row))) : null,
    h("button", { class: "btn primary", onclick: () => goalForm() }, "Ajouter un objectif"),
    tabbar("goals"),
  );
}

function goalForm(g) {
  const isNew = !g;
  g = g || { title: "", kind: "event", target_date: null, priority: "important", success: "", details: {}, status: "active" };
  const err = h("p", { class: "error", role: "alert" });
  const field = (id, text, ctl) => h("div", { class: "field" }, h("label", { for: id }, text), ctl);
  const title = h("input", { id: "g-title", type: "text", value: g.title, maxlength: 160, placeholder: "Ex. Trail de 50 km en juin" });
  const kind = h("select", { id: "g-kind" }, Object.entries(KINDS).map(([k, v]) => h("option", { value: k }, v)));
  kind.value = g.kind;
  const date = h("input", { id: "g-date", type: "date", value: g.target_date || "" });
  const prio = h("select", { id: "g-prio" }, PRIORITIES.map((p) => h("option", { value: p }, p)));
  prio.value = g.priority;
  const success = h("input", { id: "g-success", type: "text", value: g.success || "", maxlength: 300, placeholder: "Comment saurez-vous que c'est réussi ?" });
  const dist = h("input", { id: "g-dist", type: "number", inputmode: "decimal", min: "0", value: g.details.distance_km ?? "" });
  const elev = h("input", { id: "g-elev", type: "number", inputmode: "decimal", min: "0", value: g.details.elevation_m ?? "" });
  const detailsBox = h("div", { class: "grid2" }, field("g-dist", "Distance (km)", dist), field("g-elev", "Dénivelé positif (m)", elev));
  const syncDetails = () => { detailsBox.hidden = kind.value !== "event"; };
  kind.addEventListener("change", syncDetails); syncDetails();

  async function save() {
    err.textContent = "";
    const details = {};
    if (kind.value === "event") { if (dist.value) details.distance_km = Number(dist.value); if (elev.value) details.elevation_m = Number(elev.value); }
    const body = { title: title.value.trim(), kind: kind.value, priority: prio.value, success: success.value.trim() || null, details };
    if (date.value) body.target_date = date.value; else if (!isNew) body.clear_date = true;
    if (!body.title) { err.textContent = "Donnez un nom à cet objectif."; return; }
    try {
      await api(isNew ? `/users/${userId}/goals` : `/users/${userId}/goals/${g.id}`, { method: isNew ? "POST" : "PATCH", body });
      toast(isNew ? "Objectif ajouté" : "Objectif enregistré"); goalsScreen();
    } catch (e) { err.textContent = e.message; }
  }
  const setStatus = async (status, msg) => {
    try { await api(`/users/${userId}/goals/${g.id}`, { method: "PATCH", body: { status } }); toast(msg); goalsScreen(); }
    catch (e) { err.textContent = e.message; }
  };
  let armed = false;
  const del = h("button", { class: "link", onclick: async () => {
    if (!armed) { armed = true; del.textContent = "Confirmer la suppression définitive"; return; }
    try { await api(`/users/${userId}/goals/${g.id}`, { method: "DELETE" }); goalsScreen(); } catch (e) { err.textContent = e.message; }
  } }, "Supprimer");
  show(
    h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: goalsScreen }, icon("back")), h("span", { class: "grow" })),
    h("span", { class: "eyebrow" }, isNew ? "Nouvel objectif" : "Objectif"),
    h("h1", null, isNew ? "Que voulez-vous accomplir ?" : g.title),
    h("div", { class: "card stack" }, field("g-title", "Objectif", title), field("g-kind", "Type", kind), detailsBox,
      field("g-date", "Échéance (facultatif)", date), field("g-prio", "Priorité", prio), field("g-success", "Réussite (facultatif)", success), err),
    isNew ? null : h("div", { class: "row", style: "flex-wrap:wrap" },
      g.status === "active"
        ? [h("button", { class: "btn sm", onclick: () => setStatus("done", "Objectif terminé") }, "Marquer comme terminé"),
          h("button", { class: "btn sm", onclick: () => setStatus("dropped", "Objectif abandonné") }, "Abandonner")]
        : h("button", { class: "btn sm", onclick: () => setStatus("active", "Objectif réactivé") }, "Réactiver"), del),
    actionBar(h("button", { class: "btn primary", onclick: save }, isNew ? "Ajouter" : "Enregistrer")),
  );
}

// ---------- Garmin (par utilisateur) ----------
const SPORT_FR = { run: "Course", bike: "Vélo", strength: "Musculation", swim: "Natation", walk: "Marche", other: "Autre" };

async function garminScreen() {
  let st;
  try { st = await api(`/users/${userId}/garmin`); } catch (e) { return fail(e); }
  const err = h("p", { class: "error", role: "alert" });
  const back = h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: profile }, icon("back"), "Profil"), h("span", { class: "grow" }));
  if (!st.configured) {
    return show(back, h("h1", null, "Garmin"), h("div", { class: "card stack" }, h("p", null, "La connexion Garmin n'est pas activée sur ce serveur."),
      h("p", { class: "muted" }, "L'administrateur doit configurer la clé de chiffrement (SECRETS_KEY).")));
  }
  if (st.connected) {
    const run = async (btn, path, method, msg) => {
      btn.disabled = true; err.textContent = "";
      try { const r = await api(path, { method }); toast(typeof msg === "function" ? msg(r) : msg); garminScreen(); }
      catch (e) { err.textContent = e.message; btn.disabled = false; }
    };
    const sync = h("button", { class: "btn primary" }, "Synchroniser maintenant");
    sync.addEventListener("click", () => run(sync, `/users/${userId}/garmin/sync`, "POST", (r) => `${r.added} nouvelle${r.added > 1 ? "s" : ""} activité${r.added > 1 ? "s" : ""}`));
    let armed = false;
    const off = h("button", { class: "link", style: "text-align:left" }, "Déconnecter Garmin");
    off.addEventListener("click", () => {
      if (!armed) { armed = true; off.textContent = "Confirmer : supprimer le jeton et mes activités importées"; return; }
      run(off, `/users/${userId}/garmin?purge=true`, "DELETE", "Garmin déconnecté");
    });
    return show(back, h("span", { class: "eyebrow" }, "Garmin"), h("h1", null, "Garmin connecté"),
      h("div", { class: "card stack" }, h("p", null, st.email),
        h("p", { class: "muted" }, st.last_sync_at ? `Dernière synchronisation : ${new Date(st.last_sync_at).toLocaleString("fr-FR", { dateStyle: "medium", timeStyle: "short" })}` : "Pas encore synchronisé."),
        st.last_error ? h("p", { class: "error" }, st.last_error) : null, sync, err),
      st.recent.length ? h("div", { class: "card" }, h("h3", null, "Dernières activités"), h("div", { style: "margin-top:6px" }, st.recent.map((a) =>
        h("div", { class: "item" }, h("span", { class: "l" }, h("strong", null, a.name || SPORT_FR[a.sport] || "Activité"),
          h("span", { class: "sub" }, `${new Date(a.day + "T12:00:00").toLocaleDateString("fr-FR", { weekday: "short", day: "numeric", month: "short" })} · ${SPORT_FR[a.sport] || "Autre"}`)),
          h("span", { class: "v" }, [a.duration_s ? `${Math.round(a.duration_s / 60)} min` : null, a.distance_m ? `${(a.distance_m / 1000).toFixed(1)} km` : null].filter(Boolean).join(" · ")))))) : null,
      h("div", { class: "card stack" }, h("p", { class: "muted" }, "Vos séances planifiées sont marquées comme faites quand une activité Garmin correspond. Le volume de course mesuré remplace votre estimation."), off));
  }
  const f = (id, text, attrs) => h("div", { class: "field" }, h("label", { for: id }, text), h("input", { id, ...attrs }));
  const email = f("gm-email", "Email Garmin Connect", { type: "email", autocomplete: "username", inputmode: "email" });
  const pw = f("gm-pw", "Mot de passe Garmin", { type: "password", autocomplete: "current-password" });
  email.querySelector("input").value = st.email || "";
  const code = f("gm-code", "Code de vérification Garmin", { type: "text", inputmode: "numeric", autocomplete: "one-time-code" });
  const codeBox = h("div", { class: "stack", hidden: true }, h("p", { class: "muted" }, "Garmin vous a envoyé un code (email ou application). Saisissez-le ci-dessous."), code);
  const go = h("button", { class: "btn primary" }, "Connecter");
  let mfa = false;
  go.addEventListener("click", async () => {
    err.textContent = ""; go.disabled = true;
    try {
      const r = mfa
        ? await api(`/users/${userId}/garmin/mfa`, { method: "POST", body: { code: code.querySelector("input").value } })
        : await api(`/users/${userId}/garmin/connect`, { method: "POST", body: { email: email.querySelector("input").value, password: pw.querySelector("input").value } });
      if (r.status === "mfa_required") { mfa = true; codeBox.hidden = false; go.textContent = "Valider le code"; go.disabled = false; return; }
      toast("Garmin connecté"); garminScreen();
    } catch (e) { err.textContent = e.message; go.disabled = false; }
  });
  show(back, h("span", { class: "eyebrow" }, "Garmin"), h("h1", null, "Connecter Garmin"),
    h("p", { class: "muted" }, "Pour importer vos activités et ajuster votre plan à ce que vous faites vraiment."),
    h("div", { class: "card stack" }, email, pw, codeBox, err),
    h("div", { class: "card stack" }, h("h3", null, "Vos identifiants"),
      h("p", { class: "muted" }, "Votre mot de passe sert une seule fois à vous connecter à Garmin. Il n'est jamais enregistré : seul un jeton, chiffré sur le serveur, est conservé. Vous pouvez déconnecter Garmin à tout moment."),
      h("p", { class: "muted" }, "La connexion utilise une bibliothèque non officielle : Garmin peut la bloquer ou demander de se reconnecter.")),
    actionBar(go));
}

// ---------- discussion avec le coach ----------
function bubble(m) {
  const mine = m.role === "user";
  return h("div", { class: "msg " + (mine ? "mine" : "coach") },
    ...m.body.split("\n").map((l, i) => h("p", { style: i ? "margin-top:6px" : "" }, l)),
    h("span", { class: "when" }, new Date(m.created_at).toLocaleString("fr-FR", { weekday: "short", hour: "2-digit", minute: "2-digit" })));
}

async function coachChat() {
  let d;
  try { d = await api(`/users/${userId}/coach/chat`); } catch (e) { return fail(e); }
  const list = h("div", { class: "chat", "aria-live": "polite" }, d.messages.map(bubble));
  const empty = h("p", { class: "muted" }, "Posez une question, racontez vos sensations ou répondez aux questions du coach : il connaît votre plan, vos séances, votre montre et votre cycle.");
  const err = h("p", { class: "error", role: "alert" });
  const input = h("textarea", { rows: 3, maxlength: 1500, placeholder: "Écrivez au coach…", "aria-label": "Message au coach" });
  const send = h("button", { class: "btn primary" }, "Envoyer");
  const draftKey = `sc-chat-${userId}`;
  input.value = store.get(draftKey) || "";
  input.addEventListener("input", () => store.set(draftKey, input.value));
  const toBottom = () => window.scrollTo(0, document.body.scrollHeight);
  send.addEventListener("click", async () => {
    const text = input.value.trim();
    if (!text) return;
    err.textContent = ""; send.disabled = true; send.textContent = "Le coach réfléchit…";
    const mine = bubble({ role: "user", body: text, created_at: new Date().toISOString() });
    list.append(mine); empty.hidden = true; toBottom();
    try {
      const r = await api(`/users/${userId}/coach/chat`, { method: "POST", body: { message: text } });
      input.value = ""; store.del(draftKey);
      list.append(bubble(r.messages[1]));
    } catch (e) { err.textContent = e.message; }
    send.disabled = false; send.textContent = "Envoyer"; toBottom();
  });
  if (!d.configured) err.textContent = "Le coach IA n'est pas encore configuré sur ce serveur.";
  show(h("div", { class: "head" }, h("span", { class: "eyebrow" }, "Coach"), themeToggle()), h("h1", null, "Discussion"),
    d.messages.length ? null : empty, list,
    h("div", { class: "card stack" }, input, err, send,
      h("button", { class: "link", onclick: notifScreen }, "Notifications et conseils par mail")),
    tabbar("chat"));
  toBottom();
}

async function notifScreen() {
  let p;
  try { p = await api(`/users/${userId}/coach/notifications`); } catch (e) { return fail(e); }
  const err = h("p", { class: "error", role: "alert" });
  const supports = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
  const standalone = (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) || navigator.standalone === true;
  const b64 = (v) => Uint8Array.from(atob((v + "=".repeat((4 - v.length % 4) % 4)).replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));
  let here = null; // abonnement de cet appareil, s'il existe
  if (supports) { try { const reg = await Promise.race([navigator.serviceWorker.ready, new Promise((_, no) => setTimeout(no, 1500))]); here = await reg.pushManager.getSubscription(); } catch { /* service worker indisponible */ } }
  const native = h("button", { class: here ? "btn sm" : "btn primary" }, here ? "Désactiver sur cet appareil" : "Activer sur cet appareil");
  native.addEventListener("click", async () => {
    err.textContent = ""; native.disabled = true;
    try {
      const reg = await navigator.serviceWorker.ready;
      if (here) {
        await api(`/users/${userId}/coach/push/unsubscribe`, { method: "POST", body: { endpoint: here.endpoint } });
        await here.unsubscribe();
      } else {
        if (await Notification.requestPermission() !== "granted") throw new Error("Autorisation refusée : réglages de l'iPhone, Notifications, Coach.");
        const { key } = await api(`/users/${userId}/coach/push/key`);
        if (!key) throw new Error("Les notifications natives ne sont pas encore configurées sur le serveur.");
        const sub = await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64(key) });
        await api(`/users/${userId}/coach/push/subscribe`, { method: "POST", body: sub.toJSON() });
      }
      toast(here ? "Notifications désactivées ici" : "Notifications activées"); notifScreen();
    } catch (e) { err.textContent = e.message; native.disabled = false; }
  });
  const f = (id, text, attrs) => h("div", { class: "field" }, h("label", { for: id }, text), h("input", { id, ...attrs }));
  const topic = f("nt-topic", "Sujet ntfy (votre canal privé)", { type: "text", autocomplete: "off", autocapitalize: "off" });
  topic.querySelector("input").value = p.ntfy_topic || "";
  const mail = f("nt-mail", "Adresse mail", { type: "email", autocomplete: "email", inputmode: "email" });
  mail.querySelector("input").value = p.email || "";
  const check = (id, label, on) => { const i = h("input", { type: "checkbox", id, checked: on }); return [h("label", { class: "row", for: id }, i, h("span", { class: "grow" }, label)), i]; };
  const [pushRow, push] = check("nt-push", "Alertes sur le téléphone (baisse de forme ou de motivation)", p.push_enabled);
  const [mailRow, mailOn] = check("nt-mailon", "Mail de conseils par discipline (le dimanche)", p.email_enabled);
  const body = () => ({ ntfy_topic: topic.querySelector("input").value, email: mail.querySelector("input").value, push_enabled: push.checked, email_enabled: mailOn.checked });
  const save = h("button", { class: "btn primary" }, "Enregistrer");
  save.addEventListener("click", async () => {
    err.textContent = "";
    try { await api(`/users/${userId}/coach/notifications`, { method: "PUT", body: body() }); toast("Notifications enregistrées"); } catch (e) { err.textContent = e.message; }
  });
  const test = (ch) => h("button", { class: "btn sm", onclick: async () => {
    err.textContent = "";
    try { await api(`/users/${userId}/coach/notifications`, { method: "PUT", body: body() }); await api(`/users/${userId}/coach/notifications/test/${ch}`, { method: "POST" }); toast("Test envoyé"); }
    catch (e) { err.textContent = e.message; }
  } }, ch === "push" ? "Tester le téléphone" : "Tester le mail");
  show(h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: coachChat }, icon("back"), "Coach"), h("span", { class: "grow" })),
    h("span", { class: "eyebrow" }, "Coach"), h("h1", null, "Notifications"),
    h("p", { class: "muted" }, "Le coach vous prévient quand il voit des séances manquées, une fatigue forte, une douleur signalée ou une baisse de motivation. Jamais plus d'une alerte tous les 3 jours."),
    h("div", { class: "card stack" }, h("h3", null, "Notifications sur ce téléphone"),
      !p.server.webpush ? h("p", { class: "muted" }, "Les notifications natives ne sont pas encore activées sur le serveur.")
        : !supports ? h("p", { class: "muted" }, "Ce navigateur ne gère pas les notifications. Sur iPhone, ouvrez l'application depuis l'écran d'accueil.")
          : !standalone ? h("p", { class: "muted" }, "Sur iPhone, ajoutez d'abord l'application à l'écran d'accueil (Partager, puis Sur l'écran d'accueil), ouvrez-la depuis l'icône, puis revenez ici.")
            : [h("p", { class: "muted" }, `Alertes natives comme n'importe quelle application. Appareils abonnés : ${p.devices}.`), native],
      pushRow, test("push")),
    h("details", { class: "card" }, h("summary", { style: "font-weight:600;cursor:pointer" }, "Option : application ntfy"),
      h("p", { class: "muted", style: "margin:8px 0" }, p.server.push
        ? `Alternative : installez l'application ntfy, ajoutez le serveur ${p.ntfy_url || ""} puis abonnez-vous à un sujet de 8 à 64 caractères (lettres, chiffres, - et _), commençant par coach-.`
        : "Le canal ntfy n'est pas activé sur le serveur."), topic),
    h("div", { class: "card stack" }, h("h3", null, "Par mail"),
      h("p", { class: "muted" }, p.server.email ? "Chaque dimanche : quelques conseils pour chaque sport que vous pratiquez." : "L'envoi de mails n'est pas encore activé sur le serveur."),
      mail, mailRow, test("email")),
    err, actionBar(save), tabbar("chat"));
}

// ---------- coach ----------
function coachCard(c) {
  if (!c.configured) return null;
  const latest = c.latest;
  const d = latest ? latest.data : null;
  const act = (p) => p.action === "reduce" ? `Raccourcir « ${p.session_title} » de ${p.duration_min} à ${p.new_duration_min} min`
    : p.action === "swap_easy" ? `Remplacer « ${p.session_title} » par un footing facile`
      : `Déplacer « ${p.session_title} » au ${new Date(p.to_day + "T12:00:00").toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })}`;
  const decide = async (i, kind) => {
    try { await api(`/users/${userId}/coach/proposals/${latest.id}/${i}/${kind}`, { method: "POST" }); toast(kind === "apply" ? "Ajustement appliqué" : "Proposition ignorée"); planScreen(true); }
    catch (e) { toast(e.message); }
  };
  const btn = h("button", { class: latest ? "btn sm" : "btn primary", disabled: !c.budget.available }, latest ? "Nouveau bilan" : "Faire le bilan de la semaine");
  btn.addEventListener("click", async () => {
    btn.disabled = true; btn.textContent = "Le coach analyse votre semaine…";
    try { await api(`/users/${userId}/coach/review`, { method: "POST" }); planScreen(true); }
    catch (e) { toast(e.message); btn.disabled = !c.budget.available; btn.textContent = latest ? "Nouveau bilan" : "Faire le bilan de la semaine"; }
  });
  return h("div", { class: "card stack" },
    h("h3", null, "Bilan du coach"),
    latest ? h("p", { class: "muted" }, new Date(latest.created_at).toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })) : h("p", { class: "muted" }, "Le coach relit vos séances et vos activités Garmin, puis propose des ajustements que vous validez."),
    latest && latest.summary ? h("p", null, latest.summary) : null,
    d && d.adherence ? h("p", { class: "muted" }, d.adherence) : null,
    d && d.proposals.length ? h("div", { class: "stack" }, d.proposals.map((p, i) => h("div", { class: "form" },
      h("strong", null, act(p)), h("span", { class: "muted" }, p.reason),
      h("div", { class: "chips" }, p.rule_ids.map((r) => h("span", { class: "chip" }, r)), (p.source_ids || []).map((r) => h("button", { class: "chip", style: "border:0;cursor:pointer", onclick: () => evidenceScreen(r) }, r))),
      p.status === "proposed"
        ? h("div", { class: "row" }, h("button", { class: "btn sm primary", onclick: () => decide(i, "apply") }, "Appliquer"), h("button", { class: "btn sm", onclick: () => decide(i, "dismiss") }, "Ignorer"))
        : h("span", { class: "muted" }, p.status === "applied" ? "Appliqué" : "Ignoré")))) : (latest ? h("p", { class: "muted" }, "Aucun ajustement proposé : le plan reste tel quel.") : null),
    d && d.questions.length ? h("div", { class: "stack" }, h("strong", null, "Questions du coach"), d.questions.map((q) => h("p", { class: "muted" }, "• " + q)),
      h("button", { class: "btn sm", style: "align-self:flex-start", onclick: () => coachChat() }, "Répondre au coach")) : null,
    btn,
    h("button", { class: "link", onclick: () => coachChat() }, "Parler au coach"),
    h("p", { class: "muted" }, `Budget IA ce mois : ${c.budget.spent_eur.toFixed(2)} € sur ${c.budget.limit_eur} €.`));
}

// ---------- plan ----------
const KIND_LABEL = { run_easy: "Course facile", run_long: "Sortie longue", run_quality: "Qualité", strength_upper: "Haut du corps",
  strength_lower: "Jambes", strength_full: "Musculation", strength_crossfit: "CrossFit" };
const DAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"];
const isRun = (k) => k.startsWith("run_");

function fmtDay(iso, today) {
  const d = new Date(iso + "T12:00:00");
  const t = new Date(today + "T12:00:00");
  const diff = Math.round((d - t) / 86400000);
  const name = `${DAYS_FR[(d.getDay() + 6) % 7]} ${d.getDate()}/${String(d.getMonth() + 1).padStart(2, "0")}`;
  return diff === 0 ? `Aujourd'hui · ${name}` : diff === 1 ? `Demain · ${name}` : name;
}

function outlookCard(o) {
  if (!o) return null;
  return h("div", { class: "card stack" }, h("h3", null, o.ok ? `Objectif : ${o.event}` : "Objectif ambitieux"),
    h("p", { class: o.ok ? "muted" : "" }, o.message),
    h("p", { class: "muted" }, `Dans ${o.weeks_to_event} semaines · volume projeté ${o.projected_peak_km} km par semaine (repère : ${o.needed_peak_km} km).`));
}

function cycleCard(c) {
  if (!c) return null;
  const cur = c.current;
  const dayFr = (iso) => new Date(iso + "T12:00:00").toLocaleDateString("fr-FR", { day: "numeric", month: "long" });
  const strip = h("div", { class: "weeks", role: "img", "aria-label": "Prochaines semaines" }, c.upcoming.map((u) =>
    h("span", { class: "wk" + (u.allegee ? " light" : "") + (u.semaine === c.upcoming[0].semaine ? " now" : ""), title: `Semaine du ${dayFr(u.semaine)} : ${u.phase}${u.allegee ? ", allégée" : ""}` })));
  return h("div", { class: "card stack" },
    h("span", { class: "eyebrow" }, "Cycle d'entraînement"),
    h("h3", null, `${cur.macro_label} · ${cur.label}`),
    h("p", { class: "muted" }, cur.macro_text),
    strip,
    h("p", { class: "muted" }, [c.next_deload ? `Prochaine semaine allégée : semaine du ${dayFr(c.next_deload)}.` : null,
      cur.weeks_to_event != null ? `Objectif dans ${cur.weeks_to_event} semaine${cur.weeks_to_event > 1 ? "s" : ""}.` : null].filter(Boolean).join(" ")));
}

function planCard() {
  return h("div", { class: "card row" },
    h("div", { class: "grow stack" }, h("h3", null, "Mon plan"),
      h("p", { class: "muted" }, "Vos séances de la semaine, adaptées à votre profil et à vos objectifs.")),
    h("button", { class: "btn sm", onclick: () => planScreen() }, "Voir"));
}

const planView = { week: null };
const mondayOf = (iso) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return isoDay(d); };

async function planScreen(restore = false) {
  let data, coach;
  try { [data, coach] = await Promise.all([api(`/users/${userId}/plan?weeks=2`), api(`/users/${userId}/coach`)]); } catch (e) { return fail(e); }
  const gen = async (btn) => {
    btn.disabled = true;
    try {
      const r = await api(`/users/${userId}/plan/generate`, { method: "POST", body: { weeks: 1 } });
      toast(r.created ? "Semaine générée" : r.reason || "Aucune séance générée");
      if (r.created && coach.configured && coach.budget.available) { // le coach relit vos retours et ajuste la nouvelle semaine
        btn.textContent = "Le coach relit vos retours…";
        try { await api(`/users/${userId}/coach/review`, { method: "POST" }); } catch { /* le bilan reste disponible à la main */ }
      }
      planScreen();
    } catch (e) { btn.disabled = false; toast(e.message); }
  };
  if (!data.sessions.length) {
    const b = h("button", { class: "btn primary" }, "Générer mon plan");
    b.addEventListener("click", () => gen(b));
    return show(h("div", { class: "head" }, h("span", { class: "eyebrow" }, "Plan"), themeToggle()), h("h1", null, "Mon plan"),
      h("div", { class: "card stack" }, h("p", null, "Aucun plan pour l'instant."),
        h("p", { class: "muted" }, "Le plan est calculé à partir de votre profil, de votre matériel, de vos disponibilités et de vos objectifs. Vous pourrez l'ajuster à tout moment."), b),
      tabbar("plan"));
  }
  const thisMonday0 = mondayOf(data.today);
  let viewWeek = planView.week || thisMonday0;
  const hasLeft = data.sessions.some((x) => mondayOf(x.day) === thisMonday0 && x.day >= data.today);
  if (!planView.week && !hasLeft && data.sessions.some((x) => mondayOf(x.day) > thisMonday0)) viewWeek = shiftDay(thisMonday0, 7);  // semaine terminée : on montre la suivante
  let weekData;
  try { weekData = await api(`/users/${userId}/plan?week=${viewWeek}`); } catch (e) { return fail(e); }
  const viewSessions = weekData.sessions;
  const bounds = weekData.bounds || data.bounds || {};
  const firstW = bounds.first ? mondayOf(bounds.first) : thisMonday0, lastW = bounds.last ? mondayOf(bounds.last) : thisMonday0;
  const labelOf = (w) => w === thisMonday0 ? "Cette semaine" : w === shiftDay(thisMonday0, 7) ? "Semaine prochaine" : w === shiftDay(thisMonday0, -7) ? "Semaine dernière"
    : `Semaine du ${new Date(w + "T12:00:00").toLocaleDateString("fr-FR", { day: "numeric", month: "long" })}`;
  const goWeek = (w) => { planView.week = w === thisMonday0 ? null : w; scrollMemo.plan = null; planScreen(); };
  const weekNav = h("div", { class: "row between" },
    h("button", { class: "iconbtn", "aria-label": "Semaine précédente", disabled: viewWeek <= firstW, onclick: () => goWeek(shiftDay(viewWeek, -7)) }, icon("back")),
    h("strong", null, labelOf(viewWeek)),
    h("button", { class: "iconbtn", "aria-label": "Semaine suivante", disabled: viewWeek >= lastW, onclick: () => goWeek(shiftDay(viewWeek, 7)) }, icon("next")));
  const present = viewWeek >= thisMonday0;
  const SPORT_LBL = { run: "Course", bike: "Vélo", strength: "Musculation", swim: "Natation", walk: "Marche", other: "Autre" };
  const actsCard = (weekData.activities || []).length ? h("div", { class: "card" }, h("h3", null, "Activités Garmin hors plan"), h("div", { style: "margin-top:6px" }, weekData.activities.map((a) =>
    h("div", { class: "item" }, h("span", { class: "l" }, h("strong", null, a.name || SPORT_LBL[a.sport] || "Activité"),
      h("span", { class: "sub" }, `${new Date(a.day + "T12:00:00").toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" })} · ${SPORT_LBL[a.sport] || "Autre"}`)),
      h("span", { class: "v" }, [a.duration_s ? `${Math.round(a.duration_s / 60)} min` : null, a.distance_m ? `${(a.distance_m / 1000).toFixed(1)} km` : null].filter(Boolean).join(" · ")))))) : null;
  const emptyWeek = (viewSessions.length || actsCard) ? null : h("div", { class: "card" }, h("p", { class: "muted" }, "Aucune séance prévue cette semaine."));
  const byDay = new Map();
  for (const s of viewSessions) { if (!byDay.has(s.day)) byDay.set(s.day, []); byDay.get(s.day).push(s); }
  const weekOf = (iso) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return d.toISOString().slice(0, 10); };
  const nodes = [];
  let curWeek = "";
  for (const [day, list] of byDay) {
    const wk = weekOf(day);
    if (wk !== curWeek) {
      curWeek = wk;
      const n = [...byDay.keys()].filter((k) => weekOf(k) === wk).length;
      const wc = list[0].details.cycle;
      nodes.push(h("p", { class: "muted", style: "margin-top:-12px" }, `${n} jour${n > 1 ? "s" : ""} d'entraînement` + (wc ? ` · ${wc.macro_label} · ${wc.label}` : "")));
    }
    nodes.push(h("div", { class: "dayhead" + (day === data.today ? " today" : "") }, fmtDay(day, data.today)));
    nodes.push(h("div", { class: "card", style: "padding:0;overflow:hidden" }, list.map((s) => {
      const sub = [`${s.duration_min} min`, s.details.zone, s.details.format].filter(Boolean).join(" · ");
      return h("button", { class: `sess ${s.status}`, onclick: () => { scrollMemo.plan = window.scrollY; sessionScreen(s, data.today); } },
        h("span", { class: "dot" }, s.status === "done" ? icon("check") : isRun(s.kind) ? "C" : "M"),
        h("span", { class: "grow" }, h("strong", null, s.title), h("span", { class: "sub" }, sub)),
        icon("next"));
    })));
  }
  const thisMonday = weekOf(data.today);
  const current = data.sessions.filter((x) => weekOf(x.day) === thisMonday);
  const upcomingWeek = data.sessions.filter((x) => weekOf(x.day) > thisMonday);
  const finished = current.length > 0 && current.every((x) => x.status !== "planned" || x.day < data.today);
  const regen = h("button", { class: "link" }, "Recalculer la semaine prochaine");
  regen.addEventListener("click", () => gen(regen));
  const nextBtn = h("button", { class: "btn primary" }, "Générer la semaine suivante");
  nextBtn.addEventListener("click", () => gen(nextBtn));
  const nextCard = finished && !upcomingWeek.length
    ? h("div", { class: "card stack" }, h("h3", null, "Semaine terminée"),
      h("p", { class: "muted" }, "Le plan avance une semaine à la fois : le coach lit d'abord vos retours, puis ajuste la semaine suivante."), nextBtn) : null;
  show(h("div", { class: "head" }, h("span", { class: "eyebrow" }, "Plan"), themeToggle()), h("h1", null, "Mon plan"), weekNav, emptyWeek, ...(present ? [cycleCard(data.cycle), outlookCard(data.outlook), ...(data.advice || []).map((a) => h("div", { class: "card" }, h("p", { class: "muted" }, a))), coachCard(coach), nextCard] : []), ...nodes, actsCard,
    h("p", { class: "muted" }, "La semaine en cours n'est jamais modifiée sans votre accord."), upcomingWeek.length ? regen : null, tabbar("plan"));
  if (restore && scrollMemo.plan != null) window.scrollTo(0, scrollMemo.plan);
}

function sessionScreen(s, today) {
  const done = s.status === "done";
  const logged = s.logged || {};
  const draftKey = `sc-draft-${userId}-${s.id}`;
  const draft = (() => { try { return JSON.parse(store.get(draftKey)); } catch { return null; } })(); // saisie non enregistrée (app fermée, réseau coupé)
  const src = draft || logged;
  const st = { rpe: src.rpe ?? "", minutes: src.minutes ?? "", note: src.note ?? "", adaptation: src.adaptation ?? "", changes: [...(src.changes || [])], sets: [] };
  const prevSets = (name) => ((src.exercises || []).find((x) => x.name === name) || {}).sets || [];
  const err = h("p", { class: "error", role: "alert" });
  const saved = h("p", { class: "muted", role: "status" });
  // enregistrement automatique : brouillon local immédiat, serveur après une courte pause, et à la sortie de l'écran ou de l'app
  const collect = () => ({ adaptation: st.adaptation || null, changes: st.changes, rpe: st.rpe || null, minutes: st.minutes || null, note: st.note || null,
    exercises: st.sets.filter((x) => x.sets.some((y) => y.kg != null || y.reps != null)) });
  let dirty = false, timer = null, inflight = Promise.resolve();
  const persist = (keepalive) => {
    clearTimeout(timer);
    if (!dirty) return inflight;
    dirty = false;
    const mine = { ...(s.logged || {}), ...collect() };
    saved.textContent = "Enregistrement…";
    inflight = inflight.then(() => api(`/users/${userId}/plan/sessions/${s.id}`, { method: "PATCH", body: { status: s.status, logged: mine }, keepalive }))
      .then(() => { s.logged = mine; if (!dirty) { store.del(draftKey); saved.textContent = "Enregistré"; err.textContent = ""; } })
      .catch((e) => { dirty = true; saved.textContent = "Pas encore enregistré (le brouillon est gardé sur cet appareil)"; if (!e.handled) err.textContent = e.message; });
    return inflight;
  };
  const touch = () => {
    dirty = true;
    store.set(draftKey, JSON.stringify(collect()));
    saved.textContent = "Modification en cours…";
    clearTimeout(timer);
    timer = setTimeout(() => persist(false), 700);
  };
  const num = (v, set, ph, label) => h("input", { type: "number", inputmode: "decimal", step: "any", min: "0", placeholder: ph, value: v ?? "", "aria-label": label,
    oninput: (e) => { set(e.target.value === "" ? null : Number(e.target.value)); touch(); } });

  const slots = (s.details.slots || []).map((slot, i) => {
    const key = slot.exercise?.name || slot.pattern;
    st.sets[i] = { name: key, sets: JSON.parse(JSON.stringify(prevSets(key))) };
    const n = parseInt(String(slot.sets).split("-").pop(), 10) || 3;
    const name = slot.exercise?.name || `${slot.pattern} (${slot.muscle})`;
    const lastTxt = slot.last ? slot.last.sets.filter((x) => x.reps).map((x) => `${x.kg != null ? x.kg + " kg × " : ""}${x.reps}`).join(" · ") : "";
    return h("div", { class: "card exbox" },
      h("div", { class: "row" }, slot.exercise?.thumb ? h("img", { src: `/media/${slot.exercise.thumb}`, alt: "", loading: "lazy" }) : null,
        h("div", { class: "grow stack", style: "gap:2px" }, h("strong", null, name),
          h("span", { class: "muted" }, slot.role === "core" ? `${slot.sets} séries · ${slot.reps} · repos ${slot.rest}`
            : `${slot.sets} séries · ${slot.reps} reps · RIR ${slot.rir} (RPE ${slot.rpe}) · repos ${slot.rest}`),
          slot.last ? h("span", { class: "muted" }, `Dernière fois (${new Date(slot.last.day + "T12:00:00").toLocaleDateString("fr-FR", { day: "numeric", month: "short" })}) : ${lastTxt}`) : null,
          slot.target ? h("span", { class: "chip", style: "align-self:flex-start;margin-top:4px" }, slot.target.text)
            : slot.suggested_kg ? h("span", { class: "chip", style: "align-self:flex-start;margin-top:4px" }, `Charge de départ conseillée : ${slot.suggested_kg} kg`) : null),
        slot.exercise ? h("button", { class: "link", onclick: () => exerciseDetail(slot.exercise.id) }, "Fiche") : null),
      slot.cue ? h("p", { class: "muted" }, slot.cue) : null,
      slot.why ? h("p", { class: "muted", style: "font-style:italic" }, `Pourquoi : ${slot.why}`) : null,
      h("div", { class: "sets" }, h("span", null, ""), h("span", null, "kg"), h("span", null, "reps"),
        Array.from({ length: n }, (_, k) => {
          st.sets[i].sets[k] = st.sets[i].sets[k] || {};
          return [h("span", null, k + 1), num(st.sets[i].sets[k].kg, (v) => { st.sets[i].sets[k].kg = v; }, "kg", `${name}, série ${k + 1}, kg`),
            num(st.sets[i].sets[k].reps, (v) => { st.sets[i].sets[k].reps = v; }, "reps", `${name}, série ${k + 1}, répétitions`)];
        })));
  });

  const CHANGES_FR = ["plus léger", "plus court", "plus long", "exercice remplacé", "séries en moins", "séries en plus", "douleur", "trop facile", "trop dur", "matériel manquant"];
  const chipsBox = h("div", { class: "chips" });
  const drawChips = () => chipsBox.replaceChildren(...CHANGES_FR.map((c) => h("button", { type: "button", class: "chip", style: `border:0;cursor:pointer;opacity:${st.changes.includes(c) ? 1 : 0.5};${st.changes.includes(c) ? "outline:2px solid var(--accent)" : ""}`,
    "aria-pressed": st.changes.includes(c), onclick: () => { st.changes = st.changes.includes(c) ? st.changes.filter((x) => x !== c) : [...st.changes, c]; drawChips(); touch(); } }, c)));
  drawChips();
  const adapt = h("textarea", { id: "adapt", "aria-label": "Ce que j'ai adapté", placeholder: "Ex. : squat remplacé par la presse à cuisses (genou sensible), 3 séries au lieu de 4, charge réduite de 10 %…",
    oninput: (e) => { st.adaptation = e.target.value; touch(); } }, st.adaptation);
  const saveAdapt = async () => { dirty = true; await persist(false); if (!dirty) toast("Adaptation enregistrée : le coach la prendra en compte"); };
  const rpe = h("select", { id: "rpe", "aria-label": "Effort ressenti" }, h("option", { value: "" }, "Effort ressenti"),
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => h("option", { value: n }, `${n} sur 10`)));
  rpe.value = st.rpe; rpe.addEventListener("change", () => { st.rpe = rpe.value === "" ? "" : Number(rpe.value); touch(); });
  const save = async (status) => {
    err.textContent = "";
    clearTimeout(timer); await inflight;
    const body = { status, logged: { ...(s.logged || {}), ...collect() } }; // la saisie est toujours conservée, quel que soit le statut
    try { await api(`/users/${userId}/plan/sessions/${s.id}`, { method: "PATCH", body }); dirty = false; store.del(draftKey); flushActive = null; toast(status === "done" ? "Séance enregistrée" : status === "skipped" ? "Séance passée" : "Séance rouverte"); planScreen(true); }
    catch (e) { err.textContent = e.message; }
  };
  show(
    h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: async () => { await persist(false); if (!dirty) planScreen(true); } }, icon("back"), "Plan"), h("span", { class: "grow" })),
    h("span", { class: "eyebrow" }, fmtDay(s.day, today)),
    h("h1", null, s.title),
    h("div", { class: "chips" }, s.details.cycle ? h("span", { class: "chip" }, `${s.details.cycle.macro_label} · ${s.details.cycle.label}`) : null, h("span", { class: "chip" }, `${s.duration_min} min`), s.details.zone ? h("span", { class: "chip" }, s.details.zone) : null,
      s.details.format ? h("span", { class: "chip" }, s.details.format) : null, s.details.vert_m ? h("span", { class: "chip" }, `≈ ${s.details.vert_m} m D+`) : null),
    s.notes.length ? h("div", { class: "card" }, s.notes.map((n) => h("p", { class: "muted" }, n))) : null,
    logged.garmin_id ? h("div", { class: "card stack" }, h("h3", null, "Mesuré par la montre"),
      h("div", { class: "chips" }, [logged.minutes ? `${logged.minutes} min` : null, logged.distance_km ? `${logged.distance_km} km` : null, logged.avg_hr ? `FC moy ${logged.avg_hr}` : null,
        logged.max_hr ? `FC max ${logged.max_hr}` : null, logged.calories ? `${logged.calories} kcal` : null, logged.training_load ? `charge ${logged.training_load}` : null]
        .filter(Boolean).map((t) => h("span", { class: "chip" }, t)))) : null,
    ...slots,
    ...(s.details.blocks || []).map((b) => h("div", { class: "card stack" },
      h("div", { class: "row" }, h("h3", { class: "grow" }, b.title), h("span", { class: "chip" }, `${b.minutes} min`)),
      h("ul", { class: "plain" }, b.items.map((it) => h("li", null, it))),
      b.effort ? h("p", { class: "muted" }, `Effort visé : ${b.effort}`) : null)),
    slots.length ? h("details", { class: "card" }, h("summary", { style: "font-weight:600;cursor:pointer" }, "Comment doser l'effort (RIR et RPE)"),
      h("p", { class: "muted", style: "margin-top:8px" }, "RIR = répétitions en réserve : combien de répétitions vous pourriez encore faire à la fin de la série. RIR 2 signifie qu'il vous en restait 2 (RPE 8 sur 10). RIR 4 : très facile, RPE 6."),
      h("p", { class: "muted", style: "margin-top:6px" }, "Au fil des semaines, on se rapproche de l'échec (RIR 2-3, puis 2, puis 1-2), et la semaine allégée repart très facile. Quand vous atteignez le haut de la fourchette de répétitions sur toutes les séries, augmentez la charge.")) : null,
    h("div", { class: "card stack" }, h("h3", null, "Ce que j'ai adapté"),
      h("p", { class: "muted" }, "Dites au coach ce que vous avez changé ou adapté dans cette séance. Il en tiendra compte pour la suite."),
      chipsBox, adapt, h("button", { class: "btn sm", style: "align-self:flex-start", onclick: saveAdapt }, "Enregistrer mon adaptation")),
    h("div", { class: "card stack" }, h("h3", null, "Après la séance"),
      isRun(s.kind) || s.details.blocks ? h("div", { class: "field" }, h("label", { for: "mins" }, "Durée réelle (min)"),
        num(st.minutes, (v) => { st.minutes = v; }, String(s.duration_min), "Durée réelle en minutes")) : null,
      rpe, h("div", { class: "field" }, h("label", { for: "note" }, "Remarque"),
        h("input", { id: "note", type: "text", value: st.note, maxlength: 600, placeholder: "Sensations, douleurs…", oninput: (e) => { st.note = e.target.value; touch(); } })), saved, err),
    h("p", { class: "muted" }, `Règles appliquées : ${s.rules.join(", ")}.`),
    actionBar(done ? h("button", { class: "btn", onclick: () => save("planned") }, "Rouvrir la séance")
      : h("button", { class: "btn primary", onclick: () => save("done") }, "Terminer la séance"),
      h("div", { class: "links" }, !done && s.status !== "skipped" ? h("button", { class: "link", onclick: () => save("skipped") }, "Passer cette séance") : null)),
  );
  flushActive = (keepalive) => persist(keepalive);
  if (draft) { dirty = true; saved.textContent = "Saisie reprise, enregistrement…"; timer = setTimeout(() => persist(false), 300); }
}

// ---------- bibliothèque d'exercices ----------
const libState = { q: "", muscle: "", equipment: "", kind: "" };
let libMeta = null;

let libKeep = 0;
async function library(restore = false) {
  try { libMeta = libMeta || await api("/exercises/meta"); } catch (e) { return fail(e); }
  const list = h("div", { class: "stack" });
  const more = h("button", { class: "btn sm", hidden: true }, "Voir plus");
  const count = h("p", { class: "muted", role: "status" });
  let offset = 0;

  const select = (key, title, dict) => {
    const el = h("select", { "aria-label": title }, h("option", { value: "" }, title),
      Object.entries(dict).map(([k, v]) => h("option", { value: k }, v)));
    el.value = libState[key];
    el.addEventListener("change", () => { libState[key] = el.value; load(true); });
    return el;
  };
  const search = h("input", { type: "search", id: "lib-q", placeholder: "Rechercher un exercice", value: libState.q,
    "aria-label": "Rechercher un exercice", autocomplete: "off" });
  let timer;
  search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { libState.q = search.value.trim(); load(true); }, 250); });

  async function load(reset) {
    if (reset) { offset = 0; list.replaceChildren(); }
    const p = new URLSearchParams({ limit: "24", offset: String(offset) });
    for (const [k, v] of Object.entries(libState)) if (v) p.set(k, v);
    let r;
    try { r = await api(`/exercises?${p}`); } catch (e) { count.textContent = e.message; return; }
    count.textContent = `${r.total} exercice${r.total > 1 ? "s" : ""}`;
    list.append(...r.items.map((x) => h("button", { class: "ex", onclick: () => { scrollMemo.lib = window.scrollY; libKeep = offset; exerciseDetail(x.id); } },
      x.thumb ? h("img", { src: `/media/${x.thumb}`, alt: "", loading: "lazy", width: 64, height: 64 }) : h("span", { class: "noimg" }, "Aa"),
      h("span", { class: "grow" }, h("strong", null, x.name),
        h("span", { class: "sub" }, [libMeta.kinds[x.kind] || x.kind, ...x.muscles_primary.map((m) => libMeta.muscles[m] || m)].filter(Boolean).join(" · "))),
      icon("next"))));
    offset += r.items.length;
    more.hidden = offset >= r.total;
  }
  more.addEventListener("click", () => load(false));

  show(
    h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: home }, icon("back")), h("span", { class: "grow" })),
    h("span", { class: "eyebrow" }, "Bibliothèque"),
    h("h1", null, "Exercices"),
    search,
    h("div", { class: "grid2" }, select("muscle", "Muscle", libMeta.muscles), select("equipment", "Matériel", libMeta.equipment)),
    select("kind", "Type", libMeta.kinds),
    count, list, more,
    tabbar("user"),
  );
  await load(true);
  if (restore) { // revenir à l'endroit de la liste que vous consultiez
    while (offset < libKeep && !more.hidden) await load(false);
    window.scrollTo(0, scrollMemo.lib || 0);
  }
}

async function exerciseDetail(id) {
  let e;
  try { e = await api(`/exercises/${id}`); } catch (err) { return fail(err); }
  const meta = libMeta || { muscles: {}, equipment: {}, kinds: {} };
  const images = e.media.filter((m) => m.kind === "image");
  const videos = e.media.filter((m) => m.kind === "video");
  const chips = (arr, dict) => arr.map((k) => h("span", { class: "chip" }, dict[k] || k));
  const credit = (m, what) => h("li", null, `${what} : ${m.author || "auteur non indiqué"}, `,
    m.license_url ? h("a", { href: m.license_url, target: "_blank", rel: "noopener noreferrer" }, m.license) : m.license);
  show(
    h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: () => library(true) }, icon("back")), h("span", { class: "grow" })),
    h("span", { class: "eyebrow" }, meta.kinds[e.kind] || e.kind),
    h("h1", null, e.name),
    e.name_en && e.name_en !== e.name ? h("p", { class: "muted" }, e.name_en) : null,
    images.length ? h("div", { class: "gallery" }, images.map((m) => h("img", { src: `/media/${m.id}`, alt: `Illustration : ${e.name}`, loading: "lazy" }))) : null,
    h("div", { class: "chips" }, chips(e.muscles_primary, meta.muscles), chips(e.equipment, meta.equipment)),
    e.muscles_secondary.length ? h("p", { class: "muted" }, "Muscles secondaires : " + e.muscles_secondary.map((m) => meta.muscles[m] || m).join(", ")) : null,
    e.instructions ? h("div", { class: "card stack" }, h("h3", null, "Exécution"),
      h("p", { class: "prose" }, e.instructions),
      e.instructions_lang === "en" ? h("p", { class: "muted" }, "Texte en anglais (source).") : null) : null,
    videos.length ? h("div", { class: "stack" }, videos.map((m) => h("a", { class: "btn sm", href: m.video_url, target: "_blank", rel: "noopener noreferrer" }, "Voir la vidéo"))) : null,
    h("div", { class: "card" }, h("h3", null, "Sources et licences"),
      h("ul", { class: "credits" }, h("li", null, `Fiche : ${e.author || "auteur non indiqué"}, `,
        e.license_url ? h("a", { href: e.license_url, target: "_blank", rel: "noopener noreferrer" }, e.license) : e.license),
      images.map((m) => credit(m, "Image")), videos.map((m) => credit(m, "Vidéo")))),
  );
}

// ---------- nutrition ----------
const SLOTS = ["petit-déjeuner", "déjeuner", "dîner", "collation"];
const nutDay = { value: null };

function isoDay(d) { const x = new Date(d); return new Date(x.getTime() - x.getTimezoneOffset() * 60000).toISOString().slice(0, 10); }
function shiftDay(iso, n) { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() + n); return isoDay(d); }
function dayLabel(iso, today) {
  if (iso === today) return "Aujourd'hui";
  if (iso === shiftDay(today, -1)) return "Hier";
  return new Date(iso + "T12:00:00").toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
}

async function fileToJpegB64(file, max = 1280, q = 0.72) {
  const bmp = await createImageBitmap(file);
  const k = Math.min(1, max / Math.max(bmp.width, bmp.height));
  const c = document.createElement("canvas");
  c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
  c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
  return c.toDataURL("image/jpeg", q).split(",")[1];
}

function bar(label, val, target, unit) {
  const pct = target ? Math.min(100, Math.round((val / target) * 100)) : 0;
  return h("div", { class: "stack", style: "gap:4px" },
    h("div", { class: "row between" }, h("span", null, label), h("span", { class: "muted num" }, `≈ ${val} / ${target} ${unit}`)),
    h("div", { class: "mini", style: "width:100%;height:6px;background:var(--line);border-radius:3px;overflow:hidden" }, h("i", { style: `display:block;height:100%;width:${pct}%;background:var(--accent)` })));
}

function weightChart(w, targetKg) {
  if (!w.length) return null;
  const W = 320, H = 110, P = 8;
  const kgs = w.map((x) => x.kg).concat(targetKg ? [targetKg] : []);
  const lo = Math.min(...kgs) - 0.5, hi = Math.max(...kgs) + 0.5;
  const x = (i) => P + (w.length === 1 ? (W - 2 * P) / 2 : (i * (W - 2 * P)) / (w.length - 1));
  const y = (kg) => H - P - ((kg - lo) / (hi - lo)) * (H - 2 * P);
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("role", "img"); svg.setAttribute("aria-label", "Courbe de poids");
  svg.style.cssText = "width:100%;height:auto;stroke-width:2";
  const pts = w.map((p, i) => `${x(i)},${y(p.avg ?? p.kg)}`).join(" ");
  svg.innerHTML = (targetKg ? `<line x1="${P}" x2="${W - P}" y1="${y(targetKg)}" y2="${y(targetKg)}" stroke="var(--mark)" stroke-dasharray="4 4"/>` : "")
    + `<polyline fill="none" stroke="var(--accent)" stroke-linejoin="round" stroke-linecap="round" points="${pts}"/>`
    + w.map((p, i) => `<circle cx="${x(i)}" cy="${y(p.kg)}" r="2.5" fill="var(--muted)" stroke="none"/>`).join("");
  return svg;
}

async function nutritionScreen(day) {
  nutDay.value = day || nutDay.value;
  let d, prog;
  try { d = await api(`/users/${userId}/nutrition/day${nutDay.value ? `?day=${nutDay.value}` : ""}`); prog = await api(`/users/${userId}/nutrition/progress`); }
  catch (e) { return fail(e); }
  nutDay.value = d.day;
  const t = d.targets, tot = d.totals;
  const del = (m) => { let armed = false; const b = h("button", { class: "link" }, "Supprimer");
    b.addEventListener("click", async () => { if (!armed) { armed = true; b.textContent = "Confirmer la suppression"; return; }
      try { await api(`/users/${userId}/nutrition/meals/${m.id}`, { method: "DELETE" }); nutritionScreen(d.day); } catch (e) { toast(e.message); } });
    return b; };
  const mealCard = (m) => {
    const a = m.analysis;
    const est = h("button", { class: "btn sm" }, "Estimer avec l'IA");
    est.addEventListener("click", async () => { est.disabled = true; est.textContent = "Estimation en cours…";
      try { await api(`/users/${userId}/nutrition/meals/${m.id}/estimate`, { method: "POST" }); nutritionScreen(d.day); } catch (e) { toast(e.message); est.disabled = false; est.textContent = "Estimer avec l'IA"; } });
    return h("div", { class: "card stack" },
      h("div", { class: "row between" }, h("span", { class: "chip" }, m.slot), del(m)),
      m.has_photo ? h("img", { src: `/users/${userId}/nutrition/meals/${m.id}/photo`, alt: `Photo : ${m.description || m.slot}`, loading: "lazy", style: "width:100%;max-height:220px;object-fit:cover;border-radius:12px" }) : null,
      m.description ? h("p", null, m.description) : null,
      a ? h("div", { class: "stack", style: "gap:6px" },
        h("div", { class: "chips" }, h("span", { class: "chip" }, `≈ ${a.kcal} kcal (${a.kcal_min}-${a.kcal_max})`), h("span", { class: "chip" }, `P ${a.protein_g} g`), h("span", { class: "chip" }, `G ${a.carbs_g} g`), h("span", { class: "chip" }, `L ${a.fat_g} g`)),
        a.feedback ? h("p", { class: "muted" }, a.feedback) : null, ...(a.tips || []).map((x) => h("p", { class: "muted" }, "• " + x)),
        h("p", { class: "muted", style: "font-size:.8125rem" }, `Estimation (confiance ${a.confidence}). ${a.assumptions || ""}`))
        : est);
  };
  const dayNav = h("div", { class: "row between" },
    h("button", { class: "iconbtn", "aria-label": "Jour précédent", onclick: () => nutritionScreen(shiftDay(d.day, -1)) }, icon("back")),
    h("strong", null, dayLabel(d.day, d.today)),
    h("button", { class: "iconbtn", "aria-label": "Jour suivant", disabled: d.day >= d.today, onclick: () => nutritionScreen(shiftDay(d.day, 1)) }, icon("next")));
  const wInput = h("input", { id: "w-kg", type: "number", inputmode: "decimal", step: "0.1", min: "30", max: "250", placeholder: "Poids (kg)", "aria-label": "Poids en kilogrammes" });
  const wWaist = h("input", { id: "w-waist", type: "number", inputmode: "decimal", step: "0.5", placeholder: "Tour de taille (cm), facultatif", "aria-label": "Tour de taille en centimètres" });
  const wBtn = h("button", { class: "btn sm", style: "align-self:flex-start" }, "Enregistrer le poids");
  wBtn.addEventListener("click", async () => {
    if (!wInput.value) return;
    try { await api(`/users/${userId}/nutrition/weight`, { method: "POST", body: { kg: Number(wInput.value), waist_cm: wWaist.value ? Number(wWaist.value) : null } }); toast("Poids enregistré"); nutritionScreen(d.day); }
    catch (e) { toast(e.message); }
  });
  const pr = prog.profile, tr = prog.trend;
  show(
    h("div", { class: "head" }, h("span", { class: "eyebrow" }, "Nutrition"), themeToggle()),
    h("h1", null, "Nutrition"),
    dayNav,
    h("div", { class: "card stack" },
      h("div", { class: "row between" }, h("h3", null, "Objectif du jour"), h("span", { class: "chip" }, t.day_load === "training" ? "Jour d'entraînement" : "Jour de repos")),
      h("p", null, h("span", { class: "num", style: "font-size:1.9rem" }, `≈ ${t.kcal}`), " kcal"),
      bar("Énergie", tot.kcal, t.kcal, "kcal"), bar("Protéines", tot.protein_g, t.protein_g, "g"), bar("Glucides", tot.carbs_g, t.carbs_g, "g"), bar("Lipides", tot.fat_g, t.fat_g, "g"),
      tot.meals > tot.estimated_meals ? h("p", { class: "muted" }, `${tot.meals - tot.estimated_meals} repas sans estimation : ils ne sont pas comptés.`) : null,
      t.notice ? h("p", { class: "muted" }, t.notice) : null,
      h("p", { class: "muted", style: "font-size:.8125rem" }, `Dépense estimée ${t.tdee} kcal, déficit ${t.deficit_kcal} kcal (${t.rate_pct_per_week} % du poids par semaine). Règles ${t.rules.join(", ")}.`)),
    h("button", { class: "btn primary", onclick: () => mealForm(d.day) }, "Ajouter un repas"),
    ...d.meals.map(mealCard),
    d.meals.length ? null : h("div", { class: "card" }, h("p", { class: "muted" }, "Aucun repas enregistré ce jour. Décrivez ce que vous avez mangé, avec ou sans photo : l'IA estime calories et macros (ordres de grandeur).")),
    h("div", { class: "card stack" }, h("h3", null, "Suivi du poids"),
      h("p", { class: "muted" }, `Taille ${pr.height_cm} cm · IMC ${pr.bmi}${pr.target_kg ? ` · objectif ${pr.target_kg} kg` : ""}`),
      weightChart(tr.series.slice(-30), pr.target_kg),
      tr.current ? h("p", null, `Tendance (moyenne sur 7 jours) : ${tr.current} kg`, tr.rate_pct_per_week != null ? h("span", { class: "muted" }, ` · ${tr.rate_pct_per_week > 0 ? "+" : ""}${tr.rate_pct_per_week} % par semaine`) : null) : h("p", { class: "muted" }, "Aucune pesée pour l'instant."),
      ...prog.advice.map((a) => h("p", { class: "muted" }, a)),
      h("div", { class: "grid2" }, wInput, wWaist), wBtn,
      h("p", { class: "muted", style: "font-size:.8125rem" }, prog.disclaimer)),
    tabbar("food"),
  );
}

function mealForm(day) {
  const hr = new Date().getHours();
  let slot = hr < 10 ? "petit-déjeuner" : hr < 15 ? "déjeuner" : hr < 18 ? "collation" : "dîner";
  let file = null;
  const err = h("p", { class: "error", role: "alert" });
  const slotsBox = h("div", { class: "chips" });
  const drawSlots = () => slotsBox.replaceChildren(...SLOTS.map((s) => h("button", { type: "button", class: "chip", "aria-pressed": slot === s,
    style: `border:0;cursor:pointer;opacity:${slot === s ? 1 : 0.5};${slot === s ? "outline:2px solid var(--accent)" : ""}`, onclick: () => { slot = s; drawSlots(); } }, s)));
  drawSlots();
  const desc = h("textarea", { id: "meal-desc", placeholder: "Ex. : 150 g de poulet, riz (1 assiette), brocolis, un peu d'huile d'olive…", "aria-label": "Description du repas" });
  const preview = h("img", { alt: "Aperçu de la photo", hidden: true, style: "width:100%;max-height:220px;object-fit:cover;border-radius:12px" });
  const pick = h("input", { type: "file", accept: "image/*", id: "meal-photo", "aria-label": "Ajouter une photo" });
  pick.addEventListener("change", () => { file = pick.files[0] || null; if (file) { preview.src = URL.createObjectURL(file); preview.hidden = false; } else preview.hidden = true; });
  const est = h("input", { type: "checkbox", id: "meal-est", checked: true });
  const go = h("button", { class: "btn primary" }, "Enregistrer");
  go.addEventListener("click", async () => {
    err.textContent = "";
    if (!desc.value.trim() && !file) { err.textContent = "Décrivez votre repas ou ajoutez une photo."; return; }
    go.disabled = true; go.textContent = est.checked ? "Estimation en cours…" : "Enregistrement…";
    try {
      const body = { day, slot, description: desc.value.trim(), estimate: est.checked };
      if (file) body.photo_b64 = await fileToJpegB64(file);
      const r = await api(`/users/${userId}/nutrition/meals`, { method: "POST", body });
      if (r.analysis_error) toast("Repas enregistré. Estimation indisponible : " + r.analysis_error);
      nutritionScreen(day);
    } catch (e) { err.textContent = e.message; go.disabled = false; go.textContent = "Enregistrer"; }
  });
  show(
    h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: () => nutritionScreen(day) }, icon("back"), "Nutrition"), h("span", { class: "grow" })),
    h("span", { class: "eyebrow" }, dayLabel(day, isoDay(new Date()))),
    h("h1", null, "Ajouter un repas"),
    h("div", { class: "card stack" }, slotsBox, desc, h("div", { class: "field" }, h("label", { for: "meal-photo" }, "Photo (facultatif)"), pick), preview,
      h("label", { class: "row", for: "meal-est" }, est, h("span", null, "Estimer calories et macros avec l'IA")),
      h("p", { class: "muted", style: "font-size:.8125rem" }, "La photo est redimensionnée sur votre téléphone, stockée sur votre serveur et envoyée à l'IA uniquement pour l'estimation. Les chiffres sont des ordres de grandeur, souvent sous-estimés : suivez la tendance de la semaine, pas un repas isolé."), err),
    actionBar(go),
  );
}

// ---------- sources scientifiques ----------
const evState = { topic: "", q: "" };

async function evidenceScreen(focusId) {
  let data;
  try { data = await api("/evidence"); } catch (e) { return fail(e); }
  const list = h("div", { class: "stack" });
  const count = h("p", { class: "muted", role: "status" });
  const chips = h("div", { class: "chips" });
  const search = h("input", { type: "search", id: "ev-q", placeholder: "Rechercher une publication", value: evState.q, "aria-label": "Rechercher une publication", autocomplete: "off" });
  const CONF = { "élevée": "Preuve solide", moyenne: "Preuve moyenne", faible: "Preuve faible" };
  const draw = () => {
    chips.replaceChildren(...[["", "Tout", data.total], ...Object.entries(data.topics).map(([k, v]) => [k, v.label, v.count])].map(([k, label, n]) =>
      h("button", { type: "button", class: "chip", "aria-pressed": evState.topic === k, style: `border:0;cursor:pointer;opacity:${evState.topic === k ? 1 : 0.55}`,
        onclick: () => { evState.topic = k; draw(); } }, `${label} (${n})`)));
    const q = evState.q.toLowerCase();
    const items = data.items.filter((e) => (!evState.topic || e.topic === evState.topic) && (!q || (e.citation + e.finding_fr).toLowerCase().includes(q)))
      .sort((a, b) => (a.id === focusId ? -1 : b.id === focusId ? 1 : 0));
    count.textContent = `${items.length} publication${items.length > 1 ? "s" : ""}`;
    list.replaceChildren(...items.map((e) => h("div", { class: "card stack", id: e.id, style: e.id === focusId ? "outline:2px solid var(--accent)" : "" },
      h("div", { class: "row between" }, h("strong", null, e.id), h("span", { class: "chip" }, CONF[e.confidence] || e.confidence)),
      h("p", null, e.citation), h("p", { class: "muted" }, `${e.design}`),
      h("p", null, e.finding_fr), h("p", { class: "muted" }, `Limites : ${e.limits_fr}`),
      e.applies_to.length ? h("div", { class: "chips" }, e.applies_to.map((r) => h("span", { class: "chip" }, `Règle ${r}`))) : null,
      h("a", { class: "btn sm", style: "align-self:flex-start", href: e.url, target: "_blank", rel: "noopener noreferrer" }, "Voir la publication"))));
  };
  let timer;
  search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { evState.q = search.value.trim(); draw(); }, 200); });
  show(
    h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: profile }, icon("back"), "Profil"), h("span", { class: "grow" })),
    h("span", { class: "eyebrow" }, "Sources"), h("h1", null, "Sources scientifiques"),
    h("p", { class: "muted" }, "Les publications vérifiées sur lesquelles s'appuient le plan, la nutrition et le coach. Chaque conseil cite ses règles et, quand elle existe, sa source. Le niveau de preuve est indiqué honnêtement, avec les limites."),
    search, chips, count, data.total ? list : h("div", { class: "card" }, h("p", { class: "muted" }, "La base de publications est en cours de constitution.")),
    tabbar("user"));
  draw();
}

// ---------- démarrage ----------
async function start() {
  try {
    bank = await api("/bank");
    byId = new Map(bank.map((q) => [q.id, q]));
  } catch (e) { return fail(e); }
  try {
    const me = await api("/auth/me");
    userId = String(me.id); userName = me.name;
    home();
  } catch (e) { if (e.status === 401) authScreen(); else if (!e.handled) fail(e); }
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => { /* hors HTTPS ou refusé : sans impact */ });
}
start();

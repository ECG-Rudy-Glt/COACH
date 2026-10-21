"use strict";

// Traduction : voir i18n.js. Le français est la langue source ; __("texte {nom}", { nom }) traduit puis remplit les trous.
const __ = (s, vars) => I18N.t(s, vars);
const TR_ATTRS = new Set(["aria-label", "placeholder", "title", "alt"]);
const langTag = () => I18N.tag();

const app = document.getElementById("app");
const DOMAINS = {
  goals: "Objectifs et corps", health: "Santé", constraints: "Contraintes", history: "Parcours",
  multisport: "Multisport", running: "Course à pied", trail: "Trail", strength: "Musculation",
  hybrid: "Hyrox et CrossFit", cycling: "Vélo", mobility: "Mobilité", project: "Votre projet",
};
const OTHER = "autre";
const ICONS = {
  check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
  up: '<path d="M12 19V5M5.5 11.5L12 5l6.5 6.5"/>',
  back: '<path d="M15 5l-7 7 7 7"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  camera: '<path d="M4 8h3l1.5-2h7L17 8h3a1 1 0 011 1v9a1 1 0 01-1 1H4a1 1 0 01-1-1V9a1 1 0 011-1z"/><circle cx="12" cy="13" r="3.5"/>',
  image: '<rect x="3.5" y="5" width="17" height="14" rx="2"/><circle cx="9" cy="10" r="1.5"/><path d="M4 17l5-4 4 3 3-2 4 3"/>',
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
  watch: '<rect x="7" y="6" width="10" height="12" rx="3"/><path d="M9 6l.7-3h4.6L15 6M9 18l.7 3h4.6L15 18M12 10v2.5l1.5 1"/>',
  lock: '<rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 018 0v3"/>',
  spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM18.5 15l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8z"/>',
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
    else el.setAttribute(k, v === true ? "" : TR_ATTRS.has(k) && typeof v === "string" ? __(v) : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(typeof kid === "string" ? __(kid) : String(kid)));
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

// Carte dépliante : titre et résumé toujours visibles, détail à la demande ; l'état (ouvert ou fermé) est mémorisé par carte sur cet appareil.
function fold(id, eyebrow, title, summary, body, open = false) {
  const key = `sc-fold-${id}`;
  const saved = store.get(key);
  const d = h("details", { class: "card fold", open: saved == null ? open : saved === "1" },
    h("summary", null, h("span", { class: "grow stack" }, h("span", { class: "eyebrow" }, eyebrow), h("strong", null, title), summary ? h("span", { class: "muted" }, summary) : null)),
    h("div", { class: "stack fold-body" }, body));
  d.addEventListener("toggle", () => store.set(key, d.open ? "1" : "0"));
  return d;
}

// Feuille qui monte du bas (iPhone comme Android) : fermée par un toucher à côté, la touche Échap ou le bouton.
function sheet(title, ...nodes) {
  const prev = document.activeElement;
  const close = () => { back.remove(); document.removeEventListener("keydown", onKey); if (prev && prev.focus) prev.focus(); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  const panel = h("div", { class: "sheet", role: "dialog", "aria-modal": "true", "aria-label": title },
    h("div", { class: "row between" }, h("h3", null, title), h("button", { class: "iconbtn", "aria-label": "Fermer", onclick: close }, icon("close"))), ...nodes);
  const back = h("div", { class: "sheet-back", onclick: (e) => { if (e.target === back) close(); } }, panel);
  document.body.append(back);
  document.addEventListener("keydown", onKey);
  panel.querySelector("button, input, select")?.focus();
  return close;
}

const longDay = (iso) => new Date(iso + "T12:00:00").toLocaleDateString(langTag(), { weekday: "long", day: "numeric", month: "long" });

async function moveSession(s, day) {
  try {
    const r = await api(`/users/${userId}/plan/sessions/${s.id}/move`, { method: "PATCH", body: { day } });
    toast(r.warnings.length ? r.warnings[0] : "Séance déplacée");
    return true;
  } catch (e) { toast(e.message); return false; }
}

// Appui long puis glisser : la séance suit le doigt (ou la souris) au-dessus d'une barre de jours ; lâcher sur un jour la déplace.
// Touch Events pour le tactile (iPhone Safari, Android Chrome) : preventDefault une fois l'appui long reconnu empêche le défilement ;
// événements souris pour l'ordinateur. L'alternative sans geste est le bouton « Changer de jour » de la séance.
function attachLongPress(el, days, onDrop, board = null) {
  const HOLD = 420, SLOP = 10;
  let timer = null, active = false, sx = 0, sy = 0, ghost = null, tray = null, over = null, dx = 0, dy = 0, scroller = null, lastX = 0;
  const point = (e) => (e.touches && e.touches[0]) || (e.changedTouches && e.changedTouches[0]) || e;
  const hit = (x, y) => document.elementFromPoint(x, y)?.closest("[data-day]");
  const cancel = () => { clearTimeout(timer); timer = null; };
  const begin = (x, y) => {
    active = true; over = null;
    const r = el.getBoundingClientRect();
    dx = x - r.left; dy = y - r.top;
    ghost = el.cloneNode(true);
    ghost.classList.add("ghost");
    Object.assign(ghost.style, { width: r.width + "px", left: "0", top: "0", transform: `translate(${r.left}px, ${r.top}px) scale(1.03)` });
    el.classList.add("lifted");
    if (board) {  // tableau : les colonnes sont déjà à l'écran, on les marque et on fait défiler sur les bords
      for (const col of board.querySelectorAll("[data-day]")) { const ok = days.find((d) => d.iso === col.dataset.day)?.ok; col.dataset.ok = ok ? "1" : "0"; col.classList.toggle("off", !ok); }
      board.classList.add("dragging");
      document.body.append(ghost);
      lastX = x;
      scroller = setInterval(() => {
        const b = board.getBoundingClientRect(), edge = 56;
        if (lastX < b.left + edge) board.scrollLeft -= 14; else if (lastX > b.right - edge) board.scrollLeft += 14;
      }, 16);
    } else {
      tray = h("div", { class: "daytray", role: "group", "aria-label": "Déposer sur un jour" },
        days.map((d) => h("div", { class: "daychip" + (d.ok ? "" : " off"), "data-day": d.iso, "data-ok": d.ok ? "1" : "0" }, h("span", null, I18N.weekday((new Date(d.iso + "T12:00:00").getDay() + 6) % 7, "narrow")), h("strong", null, String(Number(d.iso.slice(8)))))));
      document.body.append(ghost, tray);
    }
    if (navigator.vibrate) navigator.vibrate(18);
  };
  const track = (x, y) => {
    lastX = x;
    ghost.style.transform = `translate(${x - dx}px, ${y - dy}px) scale(1.03)`;
    const c = hit(x, y);
    if (c !== over) { over?.classList.remove("over"); over = c && c.dataset.ok === "1" ? c : null; over?.classList.add("over"); }
  };
  const finish = (drop) => {
    cancel();
    if (!active) return;
    active = false;
    const target = drop && over ? over.dataset.day : null;
    ghost.remove(); tray?.remove(); el.classList.remove("lifted");
    if (board) { clearInterval(scroller); board.classList.remove("dragging"); for (const col of board.querySelectorAll("[data-day]")) col.classList.remove("over", "off"); }
    swallow = true; setTimeout(() => { swallow = false; }, 400);  // le relâchement ne doit pas ouvrir la séance
    if (target) onDrop(target);
  };
  let swallow = false;
  el.addEventListener("click", (e) => { if (swallow) { e.stopImmediatePropagation(); e.preventDefault(); } }, true);
  el.addEventListener("contextmenu", (e) => { if (timer || active) e.preventDefault(); });  // menu contextuel d'Android à l'appui long
  // tactile
  el.addEventListener("touchstart", (e) => {
    if (e.touches.length !== 1) return cancel();
    const t = point(e); sx = t.clientX; sy = t.clientY;
    cancel(); timer = setTimeout(() => begin(sx, sy), HOLD);
  }, { passive: true });
  el.addEventListener("touchmove", (e) => {
    const t = point(e);
    if (!active) { if (Math.hypot(t.clientX - sx, t.clientY - sy) > SLOP) cancel(); return; }
    e.preventDefault(); track(t.clientX, t.clientY);
  }, { passive: false });
  el.addEventListener("touchend", () => finish(true));
  el.addEventListener("touchcancel", () => finish(false));
  // souris
  el.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return;
    sx = e.clientX; sy = e.clientY; cancel(); timer = setTimeout(() => begin(sx, sy), 300);
    const move = (m) => { if (!active) { if (Math.hypot(m.clientX - sx, m.clientY - sy) > SLOP) cancel(); } else track(m.clientX, m.clientY); };
    const up = () => { document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); finish(true); };
    document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
  });
}

function toast(msg) {
  const t = h("div", { class: "toast", role: "status" }, msg);
  document.body.append(t);
  setTimeout(() => t.remove(), 2200);
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    method: opts.method || "GET",
    headers: { "X-Lang": I18N.locale(), ...(opts.body ? { "Content-Type": "application/json" } : {}) },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    keepalive: opts.keepalive || undefined,
  });
  let data = null;
  try { data = await res.json(); } catch { /* corps vide */ }
  if (!res.ok) {
    const msg = Array.isArray(data?.detail) ? data.detail.map((d) => d.msg).filter(Boolean).join(" ; ") : data?.detail;
    const err = new Error(typeof msg === "string" && msg ? msg : __("Erreur {status}", { status: res.status }));
    err.status = res.status;
    if (res.status === 401 && !path.startsWith("/auth/")) { userId = null; authScreen(); err.handled = true; }
    throw err;
  }
  return data;
}

function fmtDuration(min) {
  const hh = Math.floor(min / 60), m = Math.round(min % 60);
  return hh ? `${hh} h${m ? " " + String(m).padStart(2, "0") : ""}` : __("{m} min", { m });
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
  if (q.type === "entries") return Array.isArray(v) && v.length ? __(v.length > 1 ? "{n} entrées" : "{n} entrée", { n: v.length }) : "Rien à signaler";
  if (Array.isArray(v)) return v.map((x) => (x === OTHER && other ? other : label(q, x))).join(", ");
  if (v === OTHER && other) return other;
  if (q.type === "single") return label(q, v);
  if (q.type === "duration") return fmtDuration(v);
  if (q.type === "date") return new Date(v).toLocaleDateString(langTag());
  if (q.type === "number" && q.unit) return `${v} ${q.unit}`;
  if (q.type === "scale") return __("{v} sur 5", { v });
  return String(v);
}

function fail(err) {
  if (err.handled) return;
  show(h("div", { class: "card stack" }, h("h3", null, "Connexion impossible"),
    h("p", { class: "muted" }, err.message || "Vérifiez votre connexion (VPN actif ?)."),
    h("button", { class: "btn primary", onclick: start }, "Réessayer")));
}

// ---------- thème (clair, sombre, éco) ----------
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

// ---------- langue ----------
// Choix mémorisé sur l'appareil (localStorage) et sur le compte (les notifications et les mails du coach suivent) ; le changement recharge l'écran.
async function chooseLanguage(lang) {
  store.set("lang", lang);
  if (userId) { try { await api("/auth/language", { method: "PUT", body: { lang } }); } catch { /* le choix de l'appareil suffit pour l'affichage */ } }
  location.reload();
}

function langSwitch() {
  return h("div", { class: "themes", role: "group", "aria-label": "Langue" }, Object.entries(I18N.LOCALES).map(([code, info]) =>
    h("button", { type: "button", lang: code, "aria-label": info.name, title: info.name, pressed: I18N.locale() === code,
      onclick: () => { if (I18N.locale() !== code) chooseLanguage(code); } }, code.toUpperCase())));
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
      if (st.registration !== "open") { err.textContent = __("Les inscriptions sont fermées."); return; }
      if (st.legacy.length) {
        adopt.replaceChildren(h("option", { value: "" }, "Non, nouveau profil"),
          ...st.legacy.map((u) => h("option", { value: u.id }, __("{name} ({answers} réponses)", { name: u.name, answers: u.answers }))));
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
      if (r.lang && r.lang !== I18N.locale() && !store.get("lang")) { store.set("lang", r.lang); location.reload(); return; }  // nouvel appareil : la langue du compte
      if (r.lang !== I18N.locale()) api("/auth/language", { method: "PUT", body: { lang: I18N.locale() } }).catch(() => {});
      route();
    } catch (e) { err.textContent = __(e.message); }
  };
  app.onkeydown = (e) => { if (e.key === "Enter" && e.target.tagName === "INPUT") go(); };
  show(
    h("div", { class: "head" }, h("span", { class: "eyebrow" }, "Sport Coach"), h("div", { class: "row" }, langSwitch(), themeToggle())),
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
    } catch (e) { err.textContent = __(e.message); }
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
    h("div", { class: "head" }, h("span", { class: "eyebrow" }, userName ? __("Bonjour {userName}", { userName }) : "Bonjour"), themeToggle()),
    h("div", { class: "hero" }, ring,
      h("div", { class: "stack grow" },
        h("h1", null, finished ? "Profil complet" : "Votre profil"),
        h("p", { class: "muted" }, finished ? "Il s'enrichira avec vos séances." : __("{remaining_visible} questions pour l'instant. Elles s'adaptent à vos réponses.", { remaining_visible: prof.remaining_visible })))),
    finished ? null : h("button", { class: "btn primary", onclick: () => nextQuestion() }, prof.answered ? "Continuer le questionnaire" : "Commencer le questionnaire"),
    goalsCard(goalsData),
    planCard(),
    typeof statsCard === "function" ? statsCard() : null,
    bench.novice
      ? h("div", { class: "card" }, h("h3", null, "Vos repères"), h("p", { class: "muted" }, "Pas de record à saisir pour l'instant : vos premières séances serviront de référence, et le coach en déduira vos charges."))
      : bench.total
      ? h("div", { class: "card row" },
        h("div", { class: "grow stack" }, h("h3", null, "Mes performances"),
          h("p", { class: "muted" }, __("Record et niveau actuel par exercice. {filled} sur {total} renseignés.", { filled: bench.filled, total: bench.total }))),
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

function questionView(q, { progress, prefill, onDone, onBack, editing, note, eyebrow }) {
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
    } catch (e) { errBox.textContent = __(e.message); submit.disabled = false; }
  }

  async function skip() {
    try { await api(`/users/${userId}/skip`, { method: "POST", body: { question_id: bq.id } }); onDone(); }
    catch (e) { errBox.textContent = __(e.message); }
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
      onBack ? h("button", { class: "iconbtn", "aria-label": "Retour", onclick: onBack }, icon("back")) : null,
      progress ? segments(progress.answered, progress.remaining_visible) : h("span", { class: "grow" })),
    h("span", { class: "eyebrow" }, eyebrow || DOMAINS[bq.domain] || bq.domain),
    h("h2", { class: "q" }, bq.text),
    note && h("p", { class: "coachnote" }, icon("spark"), h("span", null, note)),
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
function estimateLine(e) { // C15 : estimation tirée des séances saisies, jamais une saisie de l'utilisateur
  const day = new Date(e.day + "T12:00:00").toLocaleDateString(langTag(), { day: "numeric", month: "long" });
  return __("Niveau actuel estimé d'après vos séances : ≈ {e1rm} kg sur une répétition ({kg} kg × {reps}, {day}). Estimation : saisissez votre niveau actuel pour la remplacer.", { e1rm: e.e1rm, kg: e.kg, reps: e.reps, day });
}

async function benchmarks() {
  let page;
  try { page = await api(`/users/${userId}/benchmarks`); } catch (e) { return fail(e); }
  const vals = JSON.parse(JSON.stringify(page.values || {}));
  const dirty = new Set();
  const save = h("button", { class: "btn primary", disabled: true }, "Enregistrer");
  const mark = (id) => { dirty.add(id); save.disabled = false; save.textContent = __("Enregistrer ({size})", { size: dirty.size }); };

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
    else inputs = h("input", { type: "text", inputmode: "numeric", placeholder: "mm:ss", value: cur.time ?? "", "aria-label": __("{label}, {toLowerCase}, temps", { label: it.label, toLowerCase: title.toLowerCase() }), oninput: (e) => set("time", e.target.value.trim()) });
    return h("div", { class: "cell" }, h("span", null, title), inputs);
  };

  const sections = page.sections.map((s) => h("div", { class: "card" }, h("h3", null, s.title),
    h("div", { style: "margin-top:6px" }, s.items.map((it) =>
      h("div", { class: "bench" }, h("strong", null, it.label),
        h("div", { class: "cols" }, cell(it, "pr", "Record"), cell(it, "now", "Actuel")),
        (page.estimates || {})[it.id] ? h("p", { class: "muted" }, estimateLine(page.estimates[it.id])) : null)))));

  save.addEventListener("click", async () => {
    const items = {};
    for (const id of dirty) items[id] = vals[id];
    save.disabled = true;
    try {
      await api(`/users/${userId}/benchmarks`, { method: "PUT", body: { items } });
      dirty.clear(); save.textContent = __("Enregistrer"); toast("Performances enregistrées");
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
// Vue d'ensemble : rubriques repliées. Les réponses au questionnaire (longue liste) sont sur un écran à part.
async function profile() {
  let prof, goalsData;
  try { [prof, goalsData] = await Promise.all([api(`/users/${userId}/profile`), api(`/users/${userId}/goals?status=active`)]); } catch (e) { return fail(e); }
  const facts = prof.facts, total = prof.answered + prof.remaining_visible, pct = total ? Math.round((prof.answered / total) * 100) : 0;
  const sports = [].concat(facts["sports.practiced"] || []).join(", ");
  const link = (label, fn) => h("button", { class: "item", onclick: fn }, h("span", { class: "l" }, label), icon("next"));
  const goalsSummary = goalsData.goals.length ? __("{n} objectif(s) actif(s)", { n: goalsData.goals.length }) : "Aucun objectif actif";
  show(
    h("div", { class: "top" }, h("span", { class: "grow" }), h("span", { class: "muted" }, __("{answered} réponses", { answered: prof.answered }))),
    h("h1", null, "Profil"),
    typeof radarProfileCard === "function" ? radarProfileCard() : null,
    fold("profile-identity", "Identité", userName || "Mon compte", null, [
      h("div", { class: "stack" }, h("h3", null, "Langue"), langSwitch(), h("p", { class: "muted" }, "Langue de l'application, du coach IA et des mails.")),
      h("div", { class: "stack" }, h("h3", null, "Thème"), themeToggle())]),
    fold("profile-sports", "Sports et objectifs", sports || "Sports non renseignés", goalsSummary, [
      goalsCard(goalsData), link("Mes performances", benchmarks)]),
    fold("profile-prefs", "Préférences", "Statistiques, Garmin, import, bibliothèque", null, [
      typeof statsPrefCard === "function" ? statsPrefCard() : null,
      link("Garmin : importer mes activités", garminScreen), link("Importer des fichiers FIT, TCX, GPX", importScreen), link("Bibliothèque d'exercices", () => library()), link("Sources scientifiques", () => evidenceScreen())]),
    fold("profile-account", "Compte et sécurité", "Mot de passe et déconnexion", null, [
      link("Changer mon mot de passe", passwordScreen),
      h("button", { class: "link", style: "text-align:left", onclick: logout }, "Se déconnecter")]),
    h("div", { class: "card row" },
      h("div", { class: "grow stack" }, h("span", { class: "eyebrow" }, "Questionnaire"), h("h3", null, __("{pct} % complété", { pct })),
        h("div", { class: "st-meter", role: "img", "aria-label": __("Questionnaire complété à {pct} %", { pct }) }, h("i", { style: `width:${pct}%` }))),
      h("button", { class: "btn sm", onclick: questionnaireScreen }, "Ouvrir")),
    tabbar("user"),
  );
}

// Les domaines de questions et les réponses déjà données (édition d'une réponse, reprise du questionnaire).
async function questionnaireScreen() {
  let prof;
  try { prof = await api(`/users/${userId}/profile`); } catch (e) { return fail(e); }
  const facts = prof.facts;
  const groups = new Map();
  for (const q of bank) {
    if (facts[q.fact_key] == null) continue;
    if (!groups.has(q.domain)) groups.set(q.domain, []);
    groups.get(q.domain).push(q);
  }
  const sections = Object.keys(DOMAINS).filter((d) => groups.has(d)).map((d) => {
    const qs = groups.get(d).sort((x, y) => x.order - y.order);
    return fold(`profile-${d}`, qs.length > 1 ? __("{n} réponses", { n: qs.length }) : __("{n} réponse", { n: qs.length }), DOMAINS[d], null,
      qs.map((q) => h("button", { class: "item", onclick: () => edit(q, facts) }, h("span", { class: "l" }, q.text), h("span", { class: "v" }, fmtValue(q, facts)))));
  });
  show(
    h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: profile }, icon("back")), h("span", { class: "grow" }),
      h("span", { class: "muted" }, __("{answered} réponses", { answered: prof.answered }))),
    h("h1", null, "Questionnaire"),
    prof.remaining_visible ? h("button", { class: "btn primary", onclick: () => nextQuestion() }, prof.answered ? "Continuer le questionnaire" : "Commencer le questionnaire") : h("p", { class: "muted" }, "Questionnaire complet."),
    sections.length ? sections : h("p", { class: "muted" }, "Rien pour l'instant."),
    tabbar("user"),
  );
}

function edit(q, facts) {
  questionView(q, {
    editing: true,
    prefill: { value: facts[q.fact_key], other: facts[q.fact_key + ".other"] || "" },
    onDone: questionnaireScreen,
    onBack: questionnaireScreen,
  });
}

// ---------- objectifs (à tout moment) ----------
const KINDS = { event: "Course ou événement", performance: "Performance", body: "Corps et poids", health: "Santé", habit: "Habitude", other: "Autre" };
const PRIORITIES = ["principal", "important", "si possible"];

function countdown(iso) {
  if (!iso) return "Sans échéance";
  const days = Math.round((new Date(iso) - new Date(new Date().toDateString())) / 86400000);
  if (days < 0) return __("Échéance dépassée de {v} j", { v: -days });
  if (days === 0) return "Aujourd'hui";
  return days < 14 ? __("Dans {days} jours", { days }) : __("Dans {round} semaines", { round: Math.round(days / 7) });
}

function goalsCard(data) {
  const next = data.goals[0];
  return h("div", { class: "card row" },
    h("div", { class: "grow stack" }, h("h3", null, "Mes objectifs"),
      h("p", { class: "muted" }, next
        ? __("{length} actif{v}. Prochain : {title}, {toLowerCase}.", { length: data.goals.length, v: data.goals.length > 1 ? "s" : "", title: next.title, toLowerCase: countdown(next.target_date).toLowerCase() })
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
    if (!body.title) { err.textContent = __("Donnez un nom à cet objectif."); return; }
    try {
      await api(isNew ? `/users/${userId}/goals` : `/users/${userId}/goals/${g.id}`, { method: isNew ? "POST" : "PATCH", body });
      toast(isNew ? "Objectif ajouté" : "Objectif enregistré"); goalsScreen();
    } catch (e) { err.textContent = __(e.message); }
  }
  const setStatus = async (status, msg) => {
    try { await api(`/users/${userId}/goals/${g.id}`, { method: "PATCH", body: { status } }); toast(msg); goalsScreen(); }
    catch (e) { err.textContent = __(e.message); }
  };
  let armed = false;
  const del = h("button", { class: "link", onclick: async () => {
    if (!armed) { armed = true; del.textContent = __("Confirmer la suppression définitive"); return; }
    try { await api(`/users/${userId}/goals/${g.id}`, { method: "DELETE" }); goalsScreen(); } catch (e) { err.textContent = __(e.message); }
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

// ---------- Import de fichiers FIT / TCX / GPX ----------
const IMPORT_MAX_FILES = 20, IMPORT_MAX_BYTES = 10 * 1024 * 1024;
const readB64 = (file) => new Promise((resolve, reject) => {
  const r = new FileReader();
  r.onload = () => resolve(String(r.result).split(",", 2)[1] || "");
  r.onerror = () => reject(new Error("Fichier illisible."));
  r.readAsDataURL(file);
});

function importScreen() {
  const back = h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: profile }, icon("back"), "Profil"), h("span", { class: "grow" }));
  const input = h("input", { type: "file", id: "imp-files", accept: ".fit,.tcx,.gpx", multiple: true, hidden: true, "aria-label": "Choisir des fichiers d'activité" });
  const list = h("div", { class: "stack", "aria-live": "polite" });
  const err = h("p", { class: "error", role: "alert" });
  const planBtn = h("button", { class: "btn", hidden: true, onclick: () => planScreen() }, "Voir le plan");
  const pick = h("button", { class: "btn primary", onclick: () => input.click() }, "Choisir des fichiers");
  const LABEL = { imported: "Importée", duplicate: "Doublon", rejected: "Illisible" };
  const line = (name) => {
    const state = h("span", { class: "v" }, "…"), sub = h("span", { class: "sub" });
    const el = h("div", { class: "item" }, h("span", { class: "l" }, h("strong", null, name), sub), state);
    list.append(el);
    return (status, msg, act) => {
      state.textContent = __(LABEL[status] || status);
      state.className = status === "rejected" ? "v error" : "v";
      const bits = act ? [SPORT_FR[act.sport] || "Autre", act.day, act.duration_s ? __("{round} min", { round: Math.round(act.duration_s / 60) }) : null, act.distance_m ? `${(act.distance_m / 1000).toFixed(1)} km` : null] : [];
      sub.textContent = [msg ? __(msg) : null, ...bits.map((b) => (b ? __(b) : null))].filter(Boolean).join(" · ");
    };
  };
  input.addEventListener("change", async () => {
    const chosen = [...input.files]; input.value = "";
    if (!chosen.length) return;
    err.textContent = ""; list.replaceChildren(); planBtn.hidden = true; pick.disabled = true;
    if (chosen.length > IMPORT_MAX_FILES) err.textContent = __("{max} fichiers maximum par envoi : les suivants sont ignorés.", { max: IMPORT_MAX_FILES });
    let imported = 0, completed = 0;
    for (const f of chosen.slice(0, IMPORT_MAX_FILES)) {
      const set = line(f.name);
      if (f.size > IMPORT_MAX_BYTES) { set("rejected", "Fichier trop volumineux (10 Mo maximum)."); continue; }
      try {
        const data = await readB64(f);
        const r = await api(`/users/${userId}/activities/import`, { method: "POST", body: { files: [{ name: f.name, data }], tz: Intl.DateTimeFormat().resolvedOptions().timeZone } });
        const x = r.results[0];
        set(x.status, x.message, x.activity); imported += r.imported; completed += r.sessions_completed;
      } catch (e) { set("rejected", e.message || "Fichier illisible."); }
    }
    pick.disabled = false;
    if (imported) { toast(imported > 1 ? __("{n} activités importées", { n: imported }) : __("{n} activité importée", { n: imported })); planBtn.hidden = false; planView.matchedAt = 0; }
    if (completed) list.append(h("p", { class: "muted" }, completed > 1 ? __("{n} séances du plan marquées comme faites.", { n: completed }) : __("{n} séance du plan marquée comme faite.", { n: completed })));
  });
  show(back, h("span", { class: "eyebrow" }, "Import"), h("h1", null, "Importer des activités"),
    h("div", { class: "card stack" },
      h("p", null, "Envoyez des fichiers FIT, TCX ou GPX exportés de votre montre ou de votre application (Coros, Suunto, Polar, Wahoo, Apple Santé, Garmin hors ligne…)."),
      h("p", { class: "muted" }, "Jusqu'à 20 fichiers de 10 Mo. Les séances du plan du même jour et du même sport sont marquées comme faites ; un fichier déjà importé ou déjà reçu de Garmin n'est jamais compté deux fois."),
      h("p", { class: "muted" }, "Vos fichiers restent sur votre serveur : seuls les totaux de la séance (durée, distance, dénivelé, fréquence cardiaque) sont conservés, la trace GPS ne l'est pas."),
      input, pick, err, list, planBtn));
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
      catch (e) { err.textContent = __(e.message); btn.disabled = false; }
    };
    const sync = h("button", { class: "btn primary" }, "Synchroniser maintenant");
    sync.addEventListener("click", () => run(sync, `/users/${userId}/garmin/sync`, "POST", (r) => r.added > 1 ? __("{added} nouvelles activités", { added: r.added }) : __("{added} nouvelle activité", { added: r.added })));
    let armed = false;
    const off = h("button", { class: "link", style: "text-align:left" }, "Déconnecter Garmin");
    off.addEventListener("click", () => {
      if (!armed) { armed = true; off.textContent = __("Confirmer : supprimer le jeton et mes activités importées"); return; }
      run(off, `/users/${userId}/garmin?purge=true`, "DELETE", "Garmin déconnecté");
    });
    return show(back, h("span", { class: "eyebrow" }, "Garmin"), h("h1", null, "Garmin connecté"),
      h("div", { class: "card stack" }, h("p", null, st.email),
        h("p", { class: "muted" }, st.last_sync_at ? __("Dernière synchronisation : {toLocaleString}", { toLocaleString: new Date(st.last_sync_at).toLocaleString(langTag(), { dateStyle: "medium", timeStyle: "short" }) }) : "Pas encore synchronisé."),
        st.last_error ? h("p", { class: "error" }, st.last_error) : null, sync, err),
      st.recent.length ? h("div", { class: "card" }, h("h3", null, "Dernières activités"), h("div", { style: "margin-top:6px" }, st.recent.map((a) =>
        h("div", { class: "item" }, h("span", { class: "l" }, h("strong", null, a.name || SPORT_FR[a.sport] || "Activité"),
          h("span", { class: "sub" }, `${new Date(a.day + "T12:00:00").toLocaleDateString(langTag(), { weekday: "short", day: "numeric", month: "short" })} · ${SPORT_FR[a.sport] || "Autre"}`)),
          h("span", { class: "v" }, [a.duration_s ? __("{round} min", { round: Math.round(a.duration_s / 60) }) : null, a.distance_m ? `${(a.distance_m / 1000).toFixed(1)} km` : null].filter(Boolean).join(" · ")))))) : null,
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
      if (r.status === "mfa_required") { mfa = true; codeBox.hidden = false; go.textContent = __("Valider le code"); go.disabled = false; return; }
      toast("Garmin connecté"); garminScreen();
    } catch (e) { err.textContent = __(e.message); go.disabled = false; }
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
    h("span", { class: "when" }, new Date(m.created_at).toLocaleString(langTag(), { weekday: "short", hour: "2-digit", minute: "2-digit" })));
}

const SUGGESTIONS = ["Fais le point sur ma semaine", "Je suis fatigué : j'allège ?", "Explique-moi ma prochaine séance"];
const reducedMotion = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const coarsePointer = () => window.matchMedia && window.matchMedia("(pointer: coarse)").matches;

async function coachChat() {
  let d;
  try { d = await api(`/users/${userId}/coach/chat`); } catch (e) { return fail(e); }
  const list = h("div", { class: "chat", "aria-live": "polite" }, d.messages.map(bubble));
  const empty = h("p", { class: "muted" }, "Posez une question, racontez vos sensations ou répondez aux questions du coach : il connaît votre plan, vos séances, votre montre et votre cycle.");
  const input = h("textarea", { rows: 1, maxlength: 1500, placeholder: "Écrivez au coach…", "aria-label": "Message au coach", enterkeyhint: "send" });
  const send = h("button", { class: "send", "aria-label": "Envoyer", disabled: true }, icon("up"));
  const chips = h("div", { class: "suggest", role: "group", "aria-label": "Suggestions" }, SUGGESTIONS.map((t) => h("button", { class: "chip", onclick: () => go(t) }, t)));
  const draftKey = `sc-chat-${userId}`;
  const toBottom = () => requestAnimationFrame(() => (composer.scrollIntoView ? composer.scrollIntoView({ block: "end", behavior: reducedMotion() ? "auto" : "smooth" }) : window.scrollTo(0, document.body.scrollHeight)));
  const grow = () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; };
  const refresh = () => { send.disabled = !input.value.trim() || busy; chips.hidden = !!input.value.trim() || busy; };
  let busy = false;
  const typing = () => h("div", { class: "msg coach typing", "aria-label": "Le coach écrit" }, h("i"), h("i"), h("i"));

  async function go(text, retryOf) {
    text = text.trim();
    if (!text || busy) return;
    busy = true; input.value = ""; store.del(draftKey); grow(); refresh(); empty.hidden = true;
    if (retryOf) retryOf.remove(); else list.append(Object.assign(bubble({ role: "user", body: text, created_at: new Date().toISOString() }), { className: "msg mine new" }));
    const wait = typing();
    list.append(wait); toBottom();
    try {
      const r = await api(`/users/${userId}/coach/chat`, { method: "POST", body: { message: text } });
      wait.remove();
      list.append(Object.assign(bubble(r.messages[1]), { className: "msg coach new" }));
    } catch (e) {
      wait.remove();
      const retry = h("button", { class: "link" }, "Réessayer");
      const box = h("div", { class: "msg coach err", role: "alert" }, h("p", null, e.message || "Le coach n'a pas pu répondre."), retry);
      retry.addEventListener("click", () => go(text, box));
      list.append(box);
    }
    busy = false; refresh(); toBottom();
  }

  input.value = store.get(draftKey) || "";
  input.addEventListener("input", () => { store.set(draftKey, input.value); grow(); refresh(); });
  input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing && !coarsePointer()) { e.preventDefault(); go(input.value); } });  // Entrée envoie sur ordinateur ; sur téléphone elle va à la ligne
  send.addEventListener("click", () => go(input.value));
  const composer = h("div", { class: "composer" }, chips, h("div", { class: "field-row" }, input, send),
    d.configured ? null : h("p", { class: "error", role: "alert" }, "Le coach IA n'est pas encore configuré sur ce serveur."));
  show(h("div", { class: "head" }, h("span", { class: "eyebrow" }, "Coach"), themeToggle()), h("h1", null, "Discussion"),
    d.messages.length ? null : empty, list, composer,
    h("button", { class: "link", onclick: notifScreen }, "Notifications et conseils par mail"),
    tabbar("chat"));
  grow(); refresh(); window.scrollTo(0, document.body.scrollHeight);
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
    } catch (e) { err.textContent = __(e.message); native.disabled = false; }
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
    try { await api(`/users/${userId}/coach/notifications`, { method: "PUT", body: body() }); toast("Notifications enregistrées"); } catch (e) { err.textContent = __(e.message); }
  });
  const test = (ch) => h("button", { class: "btn sm", onclick: async () => {
    err.textContent = "";
    try { await api(`/users/${userId}/coach/notifications`, { method: "PUT", body: body() }); await api(`/users/${userId}/coach/notifications/test/${ch}`, { method: "POST" }); toast("Test envoyé"); }
    catch (e) { err.textContent = __(e.message); }
  } }, ch === "push" ? "Tester le téléphone" : "Tester le mail");
  show(h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: coachChat }, icon("back"), "Coach"), h("span", { class: "grow" })),
    h("span", { class: "eyebrow" }, "Coach"), h("h1", null, "Notifications"),
    h("p", { class: "muted" }, "Le coach vous prévient quand il voit des séances manquées, une fatigue forte, une douleur signalée ou une baisse de motivation. Jamais plus d'une alerte tous les 3 jours."),
    h("div", { class: "card stack" }, h("h3", null, "Notifications sur ce téléphone"),
      !p.server.webpush ? h("p", { class: "muted" }, "Les notifications natives ne sont pas encore activées sur le serveur.")
        : !supports ? h("p", { class: "muted" }, "Ce navigateur ne gère pas les notifications. Sur iPhone, ouvrez l'application depuis l'écran d'accueil.")
          : !standalone ? h("p", { class: "muted" }, "Sur iPhone, ajoutez d'abord l'application à l'écran d'accueil (Partager, puis Sur l'écran d'accueil), ouvrez-la depuis l'icône, puis revenez ici.")
            : [h("p", { class: "muted" }, __("Alertes natives comme n'importe quelle application. Appareils abonnés : {devices}.", { devices: p.devices })), native],
      pushRow, test("push")),
    h("details", { class: "card" }, h("summary", { style: "font-weight:600;cursor:pointer" }, "Option : application ntfy"),
      h("p", { class: "muted", style: "margin:8px 0" }, p.server.push
        ? __("Alternative : installez l'application ntfy, ajoutez le serveur {v} puis abonnez-vous à un sujet de 8 à 64 caractères (lettres, chiffres, - et _), commençant par coach-.", { v: p.ntfy_url || "" })
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
  const act = (p) => p.action === "reduce" ? __("Raccourcir « {session_title} » de {duration_min} à {new_duration_min} min", { session_title: p.session_title, duration_min: p.duration_min, new_duration_min: p.new_duration_min })
    : p.action === "swap_easy" ? __("Remplacer « {session_title} » par un footing facile", { session_title: p.session_title })
      : __("Déplacer « {session_title} » au {toLocaleDateString}", { session_title: p.session_title, toLocaleDateString: new Date(p.to_day + "T12:00:00").toLocaleDateString(langTag(), { weekday: "long", day: "numeric", month: "long" }) });
  const decide = async (i, kind) => {
    try { await api(`/users/${userId}/coach/proposals/${latest.id}/${i}/${kind}`, { method: "POST" }); toast(kind === "apply" ? "Ajustement appliqué" : "Proposition ignorée"); planScreen(true); }
    catch (e) { toast(e.message); }
  };
  const btn = h("button", { class: latest ? "btn sm" : "btn primary", disabled: !c.budget.available }, latest ? "Nouveau bilan" : "Faire le bilan de la semaine");
  btn.addEventListener("click", async () => {
    btn.disabled = true; btn.textContent = __("Le coach analyse votre semaine…");
    try { await api(`/users/${userId}/coach/review`, { method: "POST" }); planScreen(true); }
    catch (e) { toast(e.message); btn.disabled = !c.budget.available; btn.textContent = latest ? "Nouveau bilan" : "Faire le bilan de la semaine"; }
  });
  const pending = !!d && (d.proposals.some((p) => p.status === "proposed") || d.questions.length > 0);  // il y a quelque chose à décider ou à répondre : ouvert par défaut
  const when = latest ? new Date(latest.created_at).toLocaleDateString(langTag(), { weekday: "long", day: "numeric", month: "long" }) : null;
  const note = pending ? __("{length} proposition(s), {length2} question(s)", { length: d.proposals.filter((p) => p.status === "proposed").length, length2: d.questions.length }) : (latest && latest.summary ? latest.summary.slice(0, 90) + (latest.summary.length > 90 ? "…" : "") : "Le coach relit vos séances et propose des ajustements");
  return fold("coach", "Bilan du coach", when || "Pas encore de bilan", note, [
    latest && latest.summary ? h("p", null, latest.summary) : h("p", { class: "muted" }, "Le coach relit vos séances et vos activités Garmin, puis propose des ajustements que vous validez."),
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
    h("p", { class: "muted" }, __("Budget IA ce mois : {toFixed} € sur {limit_eur} €.", { toFixed: c.budget.spent_eur.toFixed(2), limit_eur: c.budget.limit_eur }))], pending);
}

// ---------- plan ----------
const KIND_LABEL = { run_easy: "Course facile", run_long: "Sortie longue", run_quality: "Qualité", strength_upper: "Haut du corps",
  strength_lower: "Jambes", strength_full: "Musculation", strength_crossfit: "CrossFit" };
const isRun = (k) => k.startsWith("run_");

function fmtDay(iso, today) {
  const d = new Date(iso + "T12:00:00");
  const t = new Date(today + "T12:00:00");
  const diff = Math.round((d - t) / 86400000);
  const name = `${I18N.weekday((d.getDay() + 6) % 7)} ${d.getDate()}/${String(d.getMonth() + 1).padStart(2, "0")}`;
  return diff === 0 ? __("Aujourd'hui · {name}", { name }) : diff === 1 ? __("Demain · {name}", { name }) : name;
}

function outlookCard(o) {
  if (!o) return null;
  return fold("outlook", o.ok ? "Objectif" : "Objectif ambitieux", o.event, __("Dans {weeks_to_event} semaines · {v}", { weeks_to_event: o.weeks_to_event, v: o.ok ? __("cohérent avec votre préparation") : __("à reconsidérer") }), [
    h("p", { class: o.ok ? "muted" : "" }, o.message),
    h("p", { class: "muted" }, __("Volume projeté {projected_peak_km} km par semaine (repère : {needed_peak_km} km).", { projected_peak_km: o.projected_peak_km, needed_peak_km: o.needed_peak_km }))]);
}

function trajectoryCard(t) {
  if (!t) return null;
  const dayFr = (iso) => new Date(iso + "T12:00:00").toLocaleDateString(langTag(), { month: "long", year: "numeric" });
  const fullFr = (iso) => new Date(iso + "T12:00:00").toLocaleDateString(langTag(), { day: "numeric", month: "long", year: "numeric" });
  const lv = t.level;
  const level = lv && lv.source_kind === "garmin"
    ? (lv.bound
      ? __("Niveau actuel borné par votre montre : vous courez au moins aussi vite que {time} sur cette distance ({source}). Votre niveau réel est probablement plus rapide : renseignez un temps récent dans Mes performances pour un plan plus juste.", { time: lv.time, source: lv.source })
      : __("Niveau actuel estimé d'après votre montre : {time} ({source}).", { time: lv.time, source: lv.source }))
    : t.level ? (t.level.record_only
    ? __("Point de départ : votre record, {time} ({source}). Votre niveau du moment est probablement plus lent : renseignez un temps récent dans Mes performances pour un plan plus juste.", { time: t.level.time, source: t.level.source })
    : __("Niveau actuel estimé : {time} ({source}).", { time: t.level.time, source: t.level.source })) : "Ajoutez un record 5 km ou 10 km dans Mes performances pour situer votre niveau.";
  const gap = t.level ? __(" Écart à combler : {gap_pct} % ({per_month_pct} % par mois), jugé {verdict}.", { gap_pct: t.gap_pct, per_month_pct: t.per_month_pct, verdict: t.verdict }) : "";
  const phases = h("ol", { class: "traj" }, t.phases.filter((p) => p.macro !== "race").map((p, i) =>
    h("li", { class: i === 0 ? "now" : "" }, h("strong", null, p.label), __(" · {dayFr} → {dayFr2} · {weeks} sem.", { dayFr: dayFr(p.start), dayFr2: dayFr(p.end), weeks: p.weeks }))));
  const tests = t.milestones.length ? h("p", { class: "muted" }, "Tests de contrôle : " + t.milestones.map((m) => `${fullFr(m.date)} (${m.label} en ${m.target_time})`).join(", ") + ".") : null;
  const head = t.level ? __("{time} → {time2} · écart {gap_pct} % ({verdict})", { time: t.level.time, time2: t.target.time, gap_pct: t.gap_pct, verdict: t.verdict }) : __("Objectif {time}", { time: t.target.time });
  return fold("trajectory", "Trajectoire", `${t.target.title} · ${fullFr(t.target.date)}`, head, [
    h("p", { class: "muted" }, __("{level}{gap} Volume visé : environ {weekly_km_target} km par semaine.", { level, gap, weekly_km_target: t.weekly_km_target })),
    phases, tests,
    ...t.warnings.map((w) => h("p", null, w))], t.warnings.length > 0);
}

function cycleCard(c) {
  if (!c) return null;
  const cur = c.current;
  const dayFr = (iso) => new Date(iso + "T12:00:00").toLocaleDateString(langTag(), { day: "numeric", month: "long" });
  const strip = h("div", { class: "weeks", role: "img", "aria-label": "Prochaines semaines" }, c.upcoming.map((u) =>
    h("span", { class: "wk" + (u.allegee ? " light" : "") + (u.semaine === c.upcoming[0].semaine ? " now" : ""), title: __("Semaine du {dayFr} : {phase}{v}", { dayFr: dayFr(u.semaine), phase: u.phase, v: u.allegee ? __(", allégée") : "" }) })));
  const note = [c.next_deload ? __("Prochaine semaine allégée : semaine du {dayFr}.", { dayFr: dayFr(c.next_deload) }) : null,
    cur.weeks_to_event != null ? __("Objectif dans {weeks_to_event} semaine{v}.", { weeks_to_event: cur.weeks_to_event, v: cur.weeks_to_event > 1 ? "s" : "" }) : null].filter(Boolean).join(" ");
  return fold("cycle", "Cycle d'entraînement", `${cur.macro_label} · ${cur.label}`, cur.macro_text, [strip, note ? h("p", { class: "muted" }, note) : null]);
}

function planCard() {
  return h("div", { class: "card row" },
    h("div", { class: "grow stack" }, h("h3", null, "Mon plan"),
      h("p", { class: "muted" }, "Vos séances de la semaine, adaptées à votre profil et à vos objectifs.")),
    h("button", { class: "btn sm", onclick: () => planScreen() }, "Voir"));
}

const planView = { week: null, matchedAt: 0 };
const mondayOf = (iso) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return isoDay(d); };

async function planScreen(restore = false) {
  let data, coach;
  if (!planView.matchedAt || Date.now() - planView.matchedAt > 60000) {  // activités Garmin déjà reçues : on les rapproche des séances avant d'afficher
    planView.matchedAt = Date.now();
    try { await api(`/users/${userId}/plan/match`, { method: "POST" }); } catch { /* le plan s'affiche quand même */ }
  }
  try { [data, coach] = await Promise.all([api(`/users/${userId}/plan?weeks=2`), api(`/users/${userId}/coach`)]); } catch (e) { return fail(e); }
  const gen = async (btn) => {
    btn.disabled = true;
    try {
      const r = await api(`/users/${userId}/plan/generate`, { method: "POST", body: { weeks: 1 } });
      toast(r.created ? "Semaine générée" : r.reason || "Aucune séance générée");
      if (r.created && coach.configured && coach.budget.available) { // le coach relit vos retours et ajuste la nouvelle semaine
        btn.textContent = __("Le coach relit vos retours…");
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
    : __("Semaine du {toLocaleDateString}", { toLocaleDateString: new Date(w + "T12:00:00").toLocaleDateString(langTag(), { day: "numeric", month: "long" }) });
  const goWeek = (w) => { planView.week = w === thisMonday0 ? null : w; scrollMemo.plan = null; planScreen(); };
  const weekNav = h("div", { class: "row between" },
    h("button", { class: "iconbtn", "aria-label": "Semaine précédente", disabled: viewWeek <= firstW, onclick: () => goWeek(shiftDay(viewWeek, -7)) }, icon("back")),
    h("strong", null, labelOf(viewWeek)),
    h("button", { class: "iconbtn", "aria-label": "Semaine suivante", disabled: viewWeek >= lastW, onclick: () => goWeek(shiftDay(viewWeek, 7)) }, icon("next")));
  const present = viewWeek >= thisMonday0;
  const SPORT_LBL = { run: "Course", bike: "Vélo", strength: "Musculation", swim: "Natation", walk: "Marche", other: "Autre" };
  const reload = () => { planScreen(true); };
  const linkSheet = (a) => {
    const unlinked = viewSessions.filter((x) => !(x.logged || {}).garmin_id && x.status !== "skipped");
    const options = a.suggestions.length ? a.suggestions : unlinked.map((x) => ({ id: x.id, title: x.title, day: x.day, status: x.status, duration_min: x.duration_min }));
    let close = () => {};
    const pick = async (o) => {
      const later = o.day !== a.day;
      try {
        await api(`/users/${userId}/plan/sessions/${o.id}/link`, { method: "POST", body: { garmin_id: a.garmin_id, move: later } });
        close(); toast(later ? __("Séance reliée et placée au {longDay}", { longDay: longDay(a.day) }) : "Activité reliée à la séance"); reload();
      } catch (e) { toast(e.message); }
    };
    close = sheet("Rapprocher d'une séance",
      h("p", { class: "muted" }, `${a.name || SPORT_LBL[a.sport] || "Activité"} · ${longDay(a.day)} · ${a.duration_s ? __("{round} min", { round: Math.round(a.duration_s / 60) }) : ""}`),
      options.length ? h("div", { class: "stack" }, options.map((o) => h("button", { class: "opt", onclick: () => pick(o) },
        h("strong", null, o.title), h("span", { class: "muted" }, __("{longDay} · {duration_min} min{v}", { longDay: longDay(o.day), duration_min: o.duration_min, v: o.day !== a.day ? __(" · sera placée au jour de l'activité") : "" })))))
        : h("p", { class: "muted" }, "Aucune séance de la semaine à rapprocher. Générez ou ajoutez une séance, ou laissez cette activité hors plan."));
  };
  const actsCard = (weekData.activities || []).length ? h("div", { class: "card" }, h("h3", null, "Activités Garmin hors plan"), h("div", { style: "margin-top:6px" }, weekData.activities.map((a) =>
    h("div", null, h("div", { class: "item" }, h("span", { class: "l" }, h("strong", null, a.name || SPORT_LBL[a.sport] || "Activité"),
      h("span", { class: "sub" }, `${longDay(a.day)} · ${SPORT_LBL[a.sport] || "Autre"}`)),
      h("span", { class: "v" }, [a.duration_s ? __("{round} min", { round: Math.round(a.duration_s / 60) }) : null, a.distance_m ? `${(a.distance_m / 1000).toFixed(1)} km` : null].filter(Boolean).join(" · "))),
      h("button", { class: "link", style: "padding:2px 4px 10px", onclick: () => linkSheet(a) }, a.suggestions.length ? "Rapprocher d'une séance" : "Choisir une séance…"))))) : null;
  const emptyWeek = (viewSessions.length || actsCard) ? null : h("div", { class: "card" }, h("p", { class: "muted" }, "Aucune séance prévue cette semaine."));
  const byDay = new Map();
  for (const s of viewSessions) { if (!byDay.has(s.day)) byDay.set(s.day, []); byDay.get(s.day).push(s); }
  const weekOf = (iso) => { const d = new Date(iso + "T12:00:00"); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return d.toISOString().slice(0, 10); };
  const weekDays = (s) => Array.from({ length: 7 }, (_, i) => shiftDay(mondayOf(s.day), i)).map((iso) => ({ iso, ok: s.status === "done" ? iso <= data.today : iso >= data.today }));
  // tableau façon kanban : une colonne par jour, appui long sur une carte puis glisser vers un autre jour
  const planMode = store.get("sc-plan-mode") === "board" ? "board" : "list";
  const modeSwitch = h("div", { class: "seg2", role: "group", "aria-label": "Affichage de la semaine" }, [["list", "Liste"], ["board", "Tableau"]].map(([m, t]) =>
    h("button", { class: "seg2-btn", pressed: planMode === m, onclick: () => { store.set("sc-plan-mode", m); planScreen(true); } }, t)));
  const buildBoard = () => {
    const wrap = h("div", { class: "board", role: "group", "aria-label": "Semaine par jour" });
    for (const iso of Array.from({ length: 7 }, (_, i) => shiftDay(viewWeek, i))) {
      const list = byDay.get(iso) || [];
      wrap.append(h("div", { class: "bcol" + (iso === data.today ? " today" : ""), "data-day": iso, "data-ok": "1", "aria-label": longDay(iso) },
        h("div", { class: "bhead" }, h("span", null, I18N.weekday((new Date(iso + "T12:00:00").getDay() + 6) % 7).slice(0, 3)), h("strong", null, String(Number(iso.slice(8))))),
        ...list.map((s) => {
          const card = h("button", { class: `bcard ${s.status} ${isRun(s.kind) ? "k-run" : "k-str"}`, onclick: () => { scrollMemo.plan = window.scrollY; sessionScreen(s, data.today); } },
            h("span", { class: "bt" }, s.title), h("span", { class: "bm" }, __("{duration_min} min{v}", { duration_min: s.duration_min, v: s.details.moved_from ? __(" · déplacée") : "" })),
            s.status === "done" ? h("span", { class: "bdone" }, icon("check")) : null);
          if (s.status !== "skipped") attachLongPress(card, weekDays(s), async (d) => { if (d !== s.day && await moveSession(s, d)) reload(); }, wrap);
          return card;
        }),
        list.length ? null : h("div", { class: "bempty" }, "Repos")));
    }
    return wrap;
  };
  const nodes = [];
  let curWeek = "";
  for (const [day, list] of byDay) {
    const wk = weekOf(day);
    if (wk !== curWeek) {
      curWeek = wk;
      const n = [...byDay.keys()].filter((k) => weekOf(k) === wk).length;
      const wc = list[0].details.cycle;
      nodes.push(h("p", { class: "muted", style: "margin-top:-12px" }, __("{n} jour{v} d'entraînement", { n, v: n > 1 ? "s" : "" }) + (wc ? ` · ${wc.macro_label} · ${wc.label}` : "")));
    }
    nodes.push(h("div", { class: "dayhead" + (day === data.today ? " today" : "") }, fmtDay(day, data.today)));
    nodes.push(h("div", { class: "card", style: "padding:0;overflow:hidden" }, list.map((s) => {
      const sub = [__("{duration_min} min", { duration_min: s.duration_min }), s.details.zone, s.details.format, s.details.moved_from ? "déplacée" : null].filter(Boolean).join(" · ");
      const row = h("button", { class: `sess ${s.status}`, onclick: () => { scrollMemo.plan = window.scrollY; sessionScreen(s, data.today); } },
        h("span", { class: "dot" }, s.status === "done" ? icon("check") : isRun(s.kind) ? "C" : "M"),
        h("span", { class: "grow" }, h("strong", null, s.title), h("span", { class: "sub" }, sub)),
        icon("next"));
      if (s.status !== "skipped") attachLongPress(row, weekDays(s), async (d) => { if (d !== s.day && await moveSession(s, d)) reload(); });
      return row;
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
  show(h("div", { class: "head" }, h("span", { class: "eyebrow" }, "Plan"), themeToggle()), h("h1", null, "Mon plan"), weekNav, modeSwitch, emptyWeek, ...(present ? [cycleCard(data.cycle), outlookCard(data.outlook), trajectoryCard(data.trajectory), ...(data.advice || []).map((a) => h("div", { class: "card" }, h("p", { class: "muted" }, a))), coachCard(coach), nextCard] : []), ...(planMode === "board" ? [buildBoard()] : nodes), actsCard,
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
    saved.textContent = __("Enregistrement…");
    inflight = inflight.then(() => api(`/users/${userId}/plan/sessions/${s.id}`, { method: "PATCH", body: { status: s.status, logged: mine }, keepalive }))
      .then(() => { s.logged = mine; if (!dirty) { store.del(draftKey); saved.textContent = __("Enregistré"); err.textContent = ""; } })
      .catch((e) => { dirty = true; saved.textContent = __("Pas encore enregistré (le brouillon est gardé sur cet appareil)"); if (!e.handled) err.textContent = __(e.message); });
    return inflight;
  };
  const touch = () => {
    dirty = true;
    store.set(draftKey, JSON.stringify(collect()));
    saved.textContent = __("Modification en cours…");
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
          h("span", { class: "muted" }, slot.role === "core" ? __("{sets} séries · {reps} · repos {rest}", { sets: slot.sets, reps: slot.reps, rest: slot.rest })
            : __("{sets} séries · {reps} reps · RIR {rir} (RPE {rpe}) · repos {rest}", { sets: slot.sets, reps: slot.reps, rir: slot.rir, rpe: slot.rpe, rest: slot.rest })),
          slot.last ? h("span", { class: "muted" }, __("Dernière fois ({toLocaleDateString}) : {lastTxt}", { toLocaleDateString: new Date(slot.last.day + "T12:00:00").toLocaleDateString(langTag(), { day: "numeric", month: "short" }), lastTxt })) : null,
          slot.target ? h("span", { class: "chip", style: "align-self:flex-start;margin-top:4px" }, slot.target.text)
            : slot.suggested_kg ? h("span", { class: "chip", style: "align-self:flex-start;margin-top:4px" }, __("Charge de départ conseillée : {suggested_kg} kg", { suggested_kg: slot.suggested_kg })) : null),
        slot.exercise ? h("button", { class: "link", onclick: () => exerciseDetail(slot.exercise.id) }, "Fiche") : null),
      slot.cue ? h("p", { class: "muted" }, slot.cue) : null,
      slot.why ? h("p", { class: "muted", style: "font-style:italic" }, __("Pourquoi : {why}", { why: slot.why })) : null,
      h("div", { class: "sets" }, h("span", null, ""), h("span", null, "kg"), h("span", null, "reps"),
        Array.from({ length: n }, (_, k) => {
          st.sets[i].sets[k] = st.sets[i].sets[k] || {};
          return [h("span", null, k + 1), num(st.sets[i].sets[k].kg, (v) => { st.sets[i].sets[k].kg = v; }, "kg", __("{name}, série {v}, kg", { name, v: k + 1 })),
            num(st.sets[i].sets[k].reps, (v) => { st.sets[i].sets[k].reps = v; }, "reps", __("{name}, série {v}, répétitions", { name, v: k + 1 }))];
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
    [1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map((n) => h("option", { value: n }, __("{n} sur 10", { n }))));
  rpe.value = st.rpe; rpe.addEventListener("change", () => { st.rpe = rpe.value === "" ? "" : Number(rpe.value); touch(); });
  const save = async (status) => {
    err.textContent = "";
    clearTimeout(timer); await inflight;
    const body = { status, logged: { ...(s.logged || {}), ...collect() } }; // la saisie est toujours conservée, quel que soit le statut
    try { await api(`/users/${userId}/plan/sessions/${s.id}`, { method: "PATCH", body }); dirty = false; store.del(draftKey); flushActive = null; toast(status === "done" ? "Séance enregistrée" : status === "skipped" ? "Séance passée" : "Séance rouverte"); planScreen(true); }
    catch (e) { err.textContent = __(e.message); }
  };
  const moveDialog = () => {
    const ahead = s.status !== "done";
    const days = Array.from({ length: 14 }, (_, i) => shiftDay(today, ahead ? i : -i));
    if (!ahead) days.reverse();
    const dateInput = h("input", { type: "date", min: shiftDay(today, ahead ? 0 : -56), max: shiftDay(today, ahead ? 120 : 0), value: s.day, "aria-label": "Autre date" });
    let close = () => {};
    const go = async (d) => { if (d && d !== s.day && await moveSession(s, d)) { close(); await persist(false); planScreen(true); } else if (d === s.day) close(); };
    dateInput.addEventListener("change", () => go(dateInput.value));
    close = sheet(ahead ? "Reprogrammer la séance" : "Séance faite un autre jour",
      h("p", { class: "muted" }, ahead ? "Choisissez le jour où vous la ferez." : "Choisissez le jour où vous l'avez réellement faite."),
      h("div", { class: "daygrid" }, days.map((d) => h("button", { class: "daychip" + (d === s.day ? " cur" : ""), onclick: () => go(d), "aria-label": longDay(d) },
        h("span", null, I18N.weekday((new Date(d + "T12:00:00").getDay() + 6) % 7, "narrow")), h("strong", null, String(Number(d.slice(8))))))),
      h("div", { class: "field" }, h("label", null, "Autre date"), dateInput));
  };
  const unlink = async () => {
    try { await api(`/users/${userId}/plan/sessions/${s.id}/link`, { method: "DELETE" }); toast("Activité dissociée"); planScreen(true); } catch (e) { toast(e.message); }
  };
  show(
    h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: async () => { await persist(false); if (!dirty) planScreen(true); } }, icon("back"), "Plan"), h("span", { class: "grow" })),
    h("span", { class: "eyebrow" }, fmtDay(s.day, today)),
    h("h1", null, s.title),
    h("div", { class: "chips" }, s.details.cycle ? h("span", { class: "chip" }, `${s.details.cycle.macro_label} · ${s.details.cycle.label}`) : null, h("span", { class: "chip" }, __("{duration_min} min", { duration_min: s.duration_min })), s.details.zone ? h("span", { class: "chip" }, s.details.zone) : null,
      s.details.format ? h("span", { class: "chip" }, s.details.format) : null, s.details.vert_m ? h("span", { class: "chip" }, `≈ ${s.details.vert_m} m D+`) : null),
    s.notes.length ? h("div", { class: "card" }, s.notes.map((n) => h("p", { class: "muted" }, n))) : null,
    s.status === "skipped" ? null : h("div", { class: "card row" }, h("div", { class: "grow stack", style: "gap:2px" }, h("strong", null, "Jour de la séance"),
      h("span", { class: "muted" }, longDay(s.day) + (s.details.moved_from ? __(" · prévue le {longDay}", { longDay: longDay(s.details.moved_from) }) : ""))),
      h("button", { class: "btn sm", onclick: moveDialog }, "Changer de jour")),
    logged.garmin_id ? h("div", { class: "card stack" }, h("h3", null, "Mesuré par la montre"),
      h("div", { class: "chips" }, [logged.minutes ? __("{minutes} min", { minutes: logged.minutes }) : null, logged.distance_km ? `${logged.distance_km} km` : null, logged.avg_hr ? __("FC moy {avg_hr}", { avg_hr: logged.avg_hr }) : null,
        logged.max_hr ? __("FC max {max_hr}", { max_hr: logged.max_hr }) : null, logged.calories ? __("{calories} kcal", { calories: logged.calories }) : null, logged.training_load ? __("charge {training_load}", { training_load: logged.training_load }) : null]
        .filter(Boolean).map((t) => h("span", { class: "chip" }, t))),
      h("button", { class: "link", style: "align-self:flex-start;padding:2px 0", onclick: unlink }, "Dissocier de cette activité")) : null,
    ...slots,
    ...(s.details.blocks || []).map((b) => h("div", { class: "card stack" },
      h("div", { class: "row" }, h("h3", { class: "grow" }, b.title), h("span", { class: "chip" }, __("{minutes} min", { minutes: b.minutes }))),
      h("ul", { class: "plain" }, b.items.map((it) => h("li", null, it))),
      b.effort ? h("p", { class: "muted" }, __("Effort visé : {effort}", { effort: b.effort })) : null)),
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
    h("p", { class: "muted" }, __("Règles appliquées : {join}.", { join: s.rules.join(", ") })),
    actionBar(done ? h("button", { class: "btn", onclick: () => save("planned") }, "Rouvrir la séance")
      : h("button", { class: "btn primary", onclick: () => save("done") }, "Terminer la séance"),
      h("div", { class: "links" }, !done && s.status !== "skipped" ? h("button", { class: "link", onclick: () => save("skipped") }, "Passer cette séance") : null)),
  );
  flushActive = (keepalive) => persist(keepalive);
  if (draft) { dirty = true; saved.textContent = __("Saisie reprise, enregistrement…"); timer = setTimeout(() => persist(false), 300); }
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
    try { r = await api(`/exercises?${p}`); } catch (e) { count.textContent = __(e.message); return; }
    count.textContent = __("{total} exercice{v}", { total: r.total, v: r.total > 1 ? "s" : "" });
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
    images.length ? h("div", { class: "gallery" }, images.map((m) => h("img", { src: `/media/${m.id}`, alt: __("Illustration : {name}", { name: e.name }), loading: "lazy" }))) : null,
    h("div", { class: "chips" }, chips(e.muscles_primary, meta.muscles), chips(e.equipment, meta.equipment)),
    e.muscles_secondary.length ? h("p", { class: "muted" }, __("Muscles secondaires : {join}", { join: e.muscles_secondary.map((m) => meta.muscles[m] || m).join(", ") })) : null,
    e.instructions ? h("div", { class: "card stack" }, h("h3", null, "Exécution"),
      h("p", { class: "prose" }, e.instructions),
      e.instructions_lang === "en" ? h("p", { class: "muted" }, "Texte en anglais (source).") : null) : null,
    videos.length ? h("div", { class: "stack" }, videos.map((m) => h("a", { class: "btn sm", href: m.video_url, target: "_blank", rel: "noopener noreferrer" }, "Voir la vidéo"))) : null,
    h("div", { class: "card" }, h("h3", null, "Sources et licences"),
      h("ul", { class: "credits" }, h("li", null, __("Fiche : {v}, ", { v: e.author || __("auteur non indiqué") }),
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
  if (iso === shiftDay(today, 1)) return "Demain";
  return new Date(iso + "T12:00:00").toLocaleDateString(langTag(), { weekday: "long", day: "numeric", month: "long" });
}

async function fileToJpegB64(file, max = 1280, q = 0.72) {
  const bmp = await createImageBitmap(file);
  const k = Math.min(1, max / Math.max(bmp.width, bmp.height));
  const c = document.createElement("canvas");
  c.width = Math.round(bmp.width * k); c.height = Math.round(bmp.height * k);
  c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
  return c.toDataURL("image/jpeg", q).split(",")[1];
}

// Le chiffre principal est la moyenne des jours estimés (N6, N10) : un repas ou un jour isolé n'est qu'un repère.
function weekCard(w) {
  if (!w) return h("div", { class: "card stack" }, h("h3", null, "Moyenne des 7 derniers jours"), h("p", { class: "muted" }, "Estimez quelques repas : la moyenne de la semaine apparaît ici. C'est elle qu'il faut suivre, pas un repas isolé."));
  const gap = w.kcal - w.target_kcal;
  return h("div", { class: "card stack" }, h("h3", null, "Moyenne des 7 derniers jours"),
    h("p", { class: "num", style: "font-size:1.9rem" }, __("≈ {kcal} kcal par jour", { kcal: w.kcal })),
    bar("Énergie", w.kcal, w.target_kcal, "kcal"), bar("Protéines", w.protein_g, w.target_protein_g, "g"),
    h("p", { class: "muted", style: "font-size:.8125rem" }, __(w.days > 1 ? "Sur {days} jours estimés : {sign}{gap} kcal par rapport à l'objectif." : "Sur {days} jour estimé : {sign}{gap} kcal par rapport à l'objectif.",
      { days: w.days, sign: gap >= 0 ? "+" : "−", gap: Math.abs(gap) }), " ", __("Les estimations sont souvent sous-évaluées : regardez surtout la tendance de poids.")));
}

function bar(label, val, target, unit) {
  const pct = target ? Math.min(100, Math.round((val / target) * 100)) : 0;
  return h("div", { class: "stack", style: "gap:4px" },
    h("div", { class: "row between" }, h("span", null, label), h("span", { class: "muted num" }, `≈ ${val} / ${target} ${unit}`)),
    h("div", { class: "mini", style: "width:100%;height:6px;background:var(--line);border-radius:3px;overflow:hidden" }, h("i", { style: `display:block;height:100%;width:${pct}%;background:var(--accent)` })));
}

// Courbe de poids sur la période choisie : axe du temps réel, courbe lissée (le lissage de 7 jours reste interne), pesées en points, objectif en pointillés.
function weightChart(w, targetKg, months) {
  if (!w.length) return null;
  const W = 320, H = 140, PL = 34, PR = 8, PT = 8, PB = 20;
  const day = (iso) => new Date(iso + "T12:00:00").getTime();
  const end = Date.now(), start = end - ({ 1: 30, 3: 91, 6: 182, 12: 365 }[months] || 91) * 86400000;
  const kgs = w.map((x) => x.kg).concat(w.map((x) => x.avg)).concat(targetKg ? [targetKg] : []);
  const lo = Math.floor(Math.min(...kgs) - 0.5), hi = Math.ceil(Math.max(...kgs) + 0.5);
  const x = (iso) => PL + ((day(iso) - start) / (end - start)) * (W - PL - PR);
  const y = (kg) => H - PB - ((kg - lo) / (hi - lo)) * (H - PT - PB);
  const fmt = (t) => new Date(t).toLocaleDateString(langTag(), { day: "numeric", month: "short" });
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", __("Courbe de poids sur {n} mois, de {lo} à {hi} kg.", { n: months, lo: Math.min(...w.map((p) => p.kg)), hi: Math.max(...w.map((p) => p.kg)) }));
  svg.style.cssText = "width:100%;height:auto;stroke-width:2";
  const txt = "fill=\"var(--muted)\" stroke=\"none\" font-size=\"10\"";
  svg.innerHTML = `<line x1="${PL}" x2="${W - PR}" y1="${H - PB}" y2="${H - PB}" stroke="var(--line)" stroke-width="1"/>`
    + `<text x="${PL - 4}" y="${y(hi) + 8}" text-anchor="end" ${txt}>${hi}</text><text x="${PL - 4}" y="${y(lo)}" text-anchor="end" ${txt}>${lo}</text>`
    + `<text x="${PL}" y="${H - 5}" ${txt}>${fmt(start)}</text><text x="${W - PR}" y="${H - 5}" text-anchor="end" ${txt}>${fmt(end)}</text>`
    + (targetKg && targetKg >= lo && targetKg <= hi ? `<line x1="${PL}" x2="${W - PR}" y1="${y(targetKg)}" y2="${y(targetKg)}" stroke="var(--mark)" stroke-dasharray="4 4"/>` : "")
    + w.map((p) => `<circle cx="${x(p.day)}" cy="${y(p.kg)}" r="2" fill="var(--muted)" stroke="none"/>`).join("")
    + `<polyline fill="none" stroke="var(--accent)" stroke-linejoin="round" stroke-linecap="round" points="${w.map((p) => `${x(p.day)},${y(p.avg)}`).join(" ")}"/>`;
  return svg;
}

const WEIGHT_PERIODS = [1, 3, 6, 12];
const weightMonths = () => { const v = Number(store.get("sc-weight-months")); return WEIGHT_PERIODS.includes(v) ? v : 3; };

function weightTrendLines(wt) {
  const sg = (v) => `${v > 0 ? "+" : ""}${String(v).replace(".", I18N.locale() === "fr" ? "," : ".")}`;
  const lines = [];
  lines.push(wt.kg_per_month != null
    ? h("p", null, h("strong", null, __("Tendance : {kg} kg par mois ({pct} % par mois)", { kg: sg(wt.kg_per_month), pct: sg(wt.pct_per_month) })), h("span", { class: "muted" }, __(" sur {n} mois", { n: wt.months })))
    : h("p", { class: "muted" }, "Tendance non calculée : il faut au moins 3 pesées sur les 14 derniers jours."));
  if (wt.target_kg && wt.remaining_kg != null) {
    lines.push(h("p", null, __("Écart à l'objectif ({target} kg) : {gap} kg", { target: wt.target_kg, gap: Math.abs(wt.remaining_kg) })));
    if (wt.eta_date) lines.push(h("p", { class: "muted" }, __("Objectif atteint vers le {date} (estimation, si le rythme se maintient).", { date: new Date(wt.eta_date + "T12:00:00").toLocaleDateString(langTag(), { day: "numeric", month: "long", year: "numeric" }) })));
    else if (wt.kg_per_month != null && Math.abs(wt.remaining_kg) > 0.2) lines.push(h("p", { class: "muted" }, "Date d'atteinte non estimée : la tendance actuelle ne mène pas à l'objectif dans les trois ans."));
  }
  return lines;
}

function weightPeriodPicker(d) {
  const cur = weightMonths();
  return h("div", { class: "chips", role: "group", "aria-label": "Période" }, WEIGHT_PERIODS.map((m) =>
    h("button", { type: "button", class: "chip", pressed: cur === m, style: chipStyle(cur === m), onclick: () => { store.set("sc-weight-months", String(m)); nutritionScreen(d.day); } },
      __("{n} mois", { n: m }))));
}

const chipStyle = (on) => `border:0;cursor:pointer;opacity:${on ? 1 : 0.55};${on ? "outline:2px solid var(--accent)" : ""}`;

function slotPicker() {
  const hr = new Date().getHours();
  let slot = hr < 10 ? "petit-déjeuner" : hr < 15 ? "déjeuner" : hr < 18 ? "collation" : "dîner";
  const box = h("div", { class: "chips" });
  const draw = () => box.replaceChildren(...SLOTS.map((x) => h("button", { type: "button", class: "chip", "aria-pressed": slot === x, style: chipStyle(slot === x), onclick: () => { slot = x; draw(); } }, x)));
  draw();
  return { el: box, get: () => slot };
}

// Questions de clarification (N9) : réponses rapides ou libres, toujours possible de passer.
function clarifyBlock(m, reload) {
  const qs = m.analysis.questions;
  const picked = qs.map(() => "");
  const inputs = qs.map((q, i) => h("input", { type: "text", maxlength: "200", id: `q-${m.id}-${i}`, placeholder: "Ou précisez en quelques mots", "aria-label": q.text }));
  const rows = qs.map((q, i) => {
    const chips = h("div", { class: "chips" });
    const draw = () => chips.replaceChildren(...(q.choices || []).map((c) => h("button", { type: "button", class: "chip", "aria-pressed": picked[i] === c, style: chipStyle(picked[i] === c),
      onclick: () => { picked[i] = picked[i] === c ? "" : c; inputs[i].value = ""; draw(); } }, c)));
    inputs[i].addEventListener("input", () => { picked[i] = ""; draw(); });
    draw();
    return h("fieldset", { class: "stack", style: "gap:6px;border:0;padding:0;margin:0" }, h("legend", { style: "font-weight:600;padding:0" }, q.text), chips, inputs[i]);
  });
  const send = async (body, btns) => {
    btns.forEach((b) => { b.disabled = true; });
    try { await api(`/users/${userId}/nutrition/meals/${m.id}/estimate`, { method: "POST", body }); reload(); } catch (e) { toast(e.message); btns.forEach((b) => { b.disabled = false; }); }
  };
  const ok = h("button", { class: "btn sm primary" }, "Affiner l'estimation");
  const skip = h("button", { class: "btn sm" }, "Passer");
  ok.addEventListener("click", () => {
    const answers = qs.map((q, i) => ({ question: q.text, answer: inputs[i].value.trim() || picked[i] })).filter((a) => a.answer);
    if (!answers.length) { toast("Répondez à au moins une question, ou passez."); return; }
    ok.textContent = __("Estimation en cours…"); send({ answers }, [ok, skip]);
  });
  skip.addEventListener("click", () => send({ skip: true }, [ok, skip]));
  return h("div", { class: "stack", role: "group", "aria-label": "Questions pour affiner l'estimation", style: "gap:10px;border-top:.5px solid var(--line);padding-top:10px" },
    h("p", { class: "muted" }, "Pour affiner (facultatif) :"), ...rows, h("div", { class: "row", style: "gap:8px" }, ok, skip));
}

// Correction de l'utilisateur : son chiffre fait foi et sert d'exemple aux estimations suivantes (N10).
function correctionBlock(m, reload) {
  const a = m.analysis || {};
  const field = (id, label, val) => h("label", { class: "stack", for: id, style: "gap:4px" }, h("span", { class: "muted", style: "font-size:.8125rem" }, label),
    h("input", { id, type: "number", inputmode: "decimal", min: "0", step: "1", value: val ?? "" }));
  const k = field(`c-k-${m.id}`, "Calories (kcal)", a.kcal), p = field(`c-p-${m.id}`, "Protéines (g)", a.protein_g), g = field(`c-g-${m.id}`, "Glucides (g)", a.carbs_g), l = field(`c-l-${m.id}`, "Lipides (g)", a.fat_g);
  let touched = false;
  for (const f of [p, g, l]) f.querySelector("input").addEventListener("input", () => { touched = true; });
  const save = h("button", { class: "btn sm primary" }, "Enregistrer la correction");
  const err = h("p", { class: "error", role: "alert" });
  save.addEventListener("click", async () => {
    err.textContent = "";
    const raw = k.querySelector("input").value;
    const kcal = Math.round(Number(raw));
    if (!raw || !Number.isFinite(kcal) || kcal < 0) { err.textContent = __("Indiquez les calories."); return; }
    const body = { kcal };
    if (touched) { const n = (f) => Number(f.querySelector("input").value) || 0; body.protein_g = n(p); body.carbs_g = n(g); body.fat_g = n(l); }
    save.disabled = true;
    try { await api(`/users/${userId}/nutrition/meals/${m.id}/correction`, { method: "PUT", body }); toast("Correction enregistrée"); reload(); } catch (e) { err.textContent = e.message; save.disabled = false; }
  });
  const form = h("div", { class: "stack", hidden: true, style: "gap:8px" }, h("div", { class: "grid2" }, k, p, g, l),
    h("p", { class: "muted", style: "font-size:.8125rem" }, "Vos chiffres remplacent l'estimation et servent d'exemple aux prochaines estimations de repas semblables."), err, save);
  const open = h("button", { class: "link", "aria-expanded": "false" }, "Corriger les chiffres");
  open.addEventListener("click", () => { form.hidden = !form.hidden; open.setAttribute("aria-expanded", String(!form.hidden)); });
  return h("div", { class: "stack", style: "gap:8px" }, open, form);
}

async function nutritionScreen(day) {
  nutDay.value = day || nutDay.value;
  let d, prog;
  try { d = await api(`/users/${userId}/nutrition/day${nutDay.value ? `?day=${nutDay.value}` : ""}`); prog = await api(`/users/${userId}/nutrition/progress?months=${weightMonths()}`); }
  catch (e) { return fail(e); }
  nutDay.value = d.day;
  const t = d.targets, tot = d.totals;
  const del = (m) => { let armed = false; const b = h("button", { class: "link" }, "Supprimer");
    b.addEventListener("click", async () => { if (!armed) { armed = true; b.textContent = __("Confirmer la suppression"); return; }
      try { await api(`/users/${userId}/nutrition/meals/${m.id}`, { method: "DELETE" }); nutritionScreen(d.day); } catch (e) { toast(e.message); } });
    return b; };
  const mealCard = (m) => {
    const a = m.analysis;
    const est = h("button", { class: "btn sm" }, "Estimer avec l'IA");
    est.addEventListener("click", async () => { est.disabled = true; est.textContent = __("Estimation en cours…");
      try { await api(`/users/${userId}/nutrition/meals/${m.id}/estimate`, { method: "POST" }); nutritionScreen(d.day); } catch (e) { toast(e.message); est.disabled = false; est.textContent = __("Estimer avec l'IA"); } });
    return h("div", { class: "card stack" },
      h("div", { class: "row between" }, h("span", { class: "chip" }, m.slot), del(m)),
      m.has_photo ? h("img", { src: `/users/${userId}/nutrition/meals/${m.id}/photo`, alt: __("Photo : {v}", { v: m.description || m.slot }), loading: "lazy", style: "width:100%;max-height:220px;object-fit:cover;border-radius:12px" }) : null,
      m.description ? h("p", null, m.description) : null,
      a ? h("div", { class: "stack", style: "gap:6px" },
        h("div", { class: "chips" }, h("span", { class: "chip" }, __("≈ {kcal} kcal ({kcal_min}-{kcal_max})", { kcal: a.kcal, kcal_min: a.kcal_min, kcal_max: a.kcal_max })), h("span", { class: "chip" }, `P ${a.protein_g} g`), h("span", { class: "chip" }, `G ${a.carbs_g} g`), h("span", { class: "chip" }, `L ${a.fat_g} g`)),
        a.feedback ? h("p", { class: "muted" }, a.feedback) : null, ...(a.tips || []).map((x) => h("p", { class: "muted" }, "• " + x)),
        h("p", { class: "muted", style: "font-size:.8125rem" }, a.corrected ? (a.original ? __("Chiffres corrigés par vous (estimation initiale : {kcal} kcal).", { kcal: a.original.kcal }) : "Chiffres corrigés par vous.")
          : a.source === "openfoodfacts" ? __("Valeurs de l'emballage (Open Food Facts). {v}", { v: a.assumptions || "" }) : __("Estimation (confiance {confidence}). {v}", { confidence: a.confidence, v: a.assumptions || "" })),
        (a.questions || []).length ? clarifyBlock(m, () => nutritionScreen(d.day)) : null,
        correctionBlock(m, () => nutritionScreen(d.day)))
        : est);
  };
  const dayNav = h("div", { class: "row between" },
    h("button", { class: "iconbtn", "aria-label": "Jour précédent", onclick: () => nutritionScreen(shiftDay(d.day, -1)) }, icon("back")),
    h("strong", null, dayLabel(d.day, d.today)),
    h("button", { class: "iconbtn", "aria-label": "Jour suivant", disabled: d.day > d.today, onclick: () => nutritionScreen(shiftDay(d.day, 1)) }, icon("next")));
  const wInput = h("input", { id: "w-kg", type: "number", inputmode: "decimal", step: "0.1", min: "30", max: "250", placeholder: "Poids (kg)", "aria-label": "Poids en kilogrammes" });
  const wWaist = h("input", { id: "w-waist", type: "number", inputmode: "decimal", step: "0.5", placeholder: "Tour de taille (cm), facultatif", "aria-label": "Tour de taille en centimètres" });
  const wDate = h("input", { id: "w-day", type: "date", max: new Date().toISOString().slice(0, 10), min: new Date(Date.now() - 730 * 86400000).toISOString().slice(0, 10), "aria-label": "Date de la pesée (par défaut aujourd'hui)" });
  const wBtn = h("button", { class: "btn sm", style: "align-self:flex-start" }, "Enregistrer le poids");
  wBtn.addEventListener("click", async () => {
    if (!wInput.value) return;
    try { await api(`/users/${userId}/nutrition/weight`, { method: "POST", body: { kg: Number(wInput.value), day: wDate.value || undefined, waist_cm: wWaist.value ? Number(wWaist.value) : null } }); toast("Poids enregistré"); nutritionScreen(d.day); }
    catch (e) { toast(e.message); }
  });
  const pr = prog.profile;
  show(
    h("div", { class: "head" }, h("span", { class: "eyebrow" }, "Nutrition"), themeToggle()),
    h("h1", null, "Nutrition"),
    dayNav,
    weekCard(prog.week_average),
    h("div", { class: "card stack" },
      h("div", { class: "row between" }, h("h3", null, "Ce jour"), h("span", { class: "chip" }, t.day_load === "training" ? "Jour d'entraînement" : "Jour de repos")),
      h("p", { class: "num", style: "font-size:1.25rem" }, __("≈ {kcal} / {target} kcal (objectif du jour)", { kcal: tot.kcal, target: t.kcal })),
      bar("Énergie", tot.kcal, t.kcal, "kcal"), bar("Protéines", tot.protein_g, t.protein_g, "g"), bar("Glucides", tot.carbs_g, t.carbs_g, "g"), bar("Lipides", tot.fat_g, t.fat_g, "g"),
      tot.meals > tot.estimated_meals ? h("p", { class: "muted" }, __("{v} repas sans estimation : ils ne sont pas comptés.", { v: tot.meals - tot.estimated_meals })) : null,
      t.notice ? h("p", { class: "muted" }, t.notice) : null,
      h("p", { class: "muted", style: "font-size:.8125rem" }, __("Dépense estimée {tdee} kcal, déficit {deficit_kcal} kcal ({rate_pct_per_week} % du poids par semaine). Règles {join}.", { tdee: t.tdee, deficit_kcal: t.deficit_kcal, rate_pct_per_week: t.rate_pct_per_week, join: t.rules.join(", ") }))),
    h("div", { class: "grid2" }, h("button", { class: "btn primary", onclick: () => mealForm(d.day) }, "Ajouter un repas"),
      d.barcode ? h("button", { class: "btn", onclick: () => barcodeForm(d.day) }, "Produit emballé") : null),
    ...d.meals.map(mealCard),
    d.meals.length ? null : h("div", { class: "card" }, h("p", { class: "muted" }, "Aucun repas enregistré ce jour. Décrivez ce que vous avez mangé, avec ou sans photo : l'IA estime calories et macros (ordres de grandeur).")),
    h("div", { class: "card stack" }, h("h3", null, "Suivi du poids"),
      h("p", { class: "muted" }, __("Taille {height_cm} cm · IMC {bmi}{v}", { height_cm: pr.height_cm, bmi: pr.bmi, v: pr.target_kg ? __(" · objectif {target_kg} kg", { target_kg: pr.target_kg }) : "" })),
      weightPeriodPicker(d),
      weightChart(prog.weight.series, pr.target_kg, prog.weight.months),
      prog.weight.current ? h("p", null, __("Poids actuel (lissé) : {current} kg", { current: prog.weight.current })) : null,
      ...weightTrendLines(prog.weight),
      ...prog.advice.map((a) => h("p", { class: "muted" }, a)),
      h("div", { class: "grid2" }, wInput, wWaist), h("label", { class: "muted", for: "w-day" }, "Date de la pesée (facultatif, jusqu'à 2 ans en arrière)"), wDate, wBtn,
      h("p", { class: "muted", style: "font-size:.8125rem" }, prog.disclaimer)),
    tabbar("food"),
  );
}

function mealForm(day) {
  const sp = slotPicker();
  let file = null;
  const err = h("p", { class: "error", role: "alert" });
  const desc = h("textarea", { id: "meal-desc", placeholder: "Ex. : 150 g de poulet, riz (1 assiette), brocolis, un peu d'huile d'olive…", "aria-label": "Description du repas" });
  const preview = h("img", { alt: "Aperçu de la photo", style: "width:100%;max-height:260px;object-fit:cover;border-radius:14px;display:block" });
  const cam = h("input", { type: "file", accept: "image/*", capture: "environment", hidden: true, "aria-label": "Prendre une photo" });  // ouvre directement l'appareil photo (iPhone, Android)
  const lib = h("input", { type: "file", accept: "image/*", hidden: true, "aria-label": "Choisir une photo" });
  const photoBtns = h("div", { class: "photo-actions" },
    h("button", { type: "button", class: "photo-btn primary", onclick: () => cam.click() }, icon("camera"), h("span", null, "Prendre une photo")),
    h("button", { type: "button", class: "photo-btn", onclick: () => lib.click() }, icon("image"), h("span", null, "Photothèque")));
  const previewBox = h("div", { class: "photo-preview", hidden: true }, preview,
    h("button", { type: "button", class: "iconbtn photo-x", "aria-label": "Retirer la photo", onclick: () => setPhoto(null) }, icon("close")));
  const setPhoto = (f) => {
    if (preview.src.startsWith("blob:")) URL.revokeObjectURL(preview.src);
    file = f || null;
    if (file) preview.src = URL.createObjectURL(file);
    previewBox.hidden = !file; photoBtns.hidden = !!file;
  };
  for (const input of [cam, lib]) input.addEventListener("change", () => { setPhoto(input.files[0]); input.value = ""; });
  const canTomorrow = day <= isoDay(new Date());  // la gamelle se compte le lendemain : impossible au-delà de demain
  const box = h("input", { type: "checkbox", id: "meal-box" });
  const boxRow = canTomorrow ? h("label", { class: "row", for: "meal-box" }, box, h("span", null, "Gamelle pour demain midi (comptée demain)")) : null;
  const est = h("input", { type: "checkbox", id: "meal-est", checked: true });
  const go = h("button", { class: "btn primary" }, "Enregistrer");
  go.addEventListener("click", async () => {
    err.textContent = "";
    if (!desc.value.trim() && !file) { err.textContent = __("Décrivez votre repas ou ajoutez une photo."); return; }
    go.disabled = true; go.textContent = est.checked ? "Estimation en cours…" : "Enregistrement…";
    try {
      const body = { day, slot: sp.get(), description: desc.value.trim(), estimate: est.checked, for_tomorrow: canTomorrow && box.checked };
      if (file) body.photo_b64 = await fileToJpegB64(file);
      const r = await api(`/users/${userId}/nutrition/meals`, { method: "POST", body });
      if (r.analysis_error) toast(__("Repas enregistré. Estimation indisponible : {analysis_error}", { analysis_error: r.analysis_error }));
      nutritionScreen(body.for_tomorrow ? shiftDay(day, 1) : day);
    } catch (e) { err.textContent = __(e.message); go.disabled = false; go.textContent = __("Enregistrer"); }
  });
  show(
    h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: () => nutritionScreen(day) }, icon("back"), "Nutrition"), h("span", { class: "grow" })),
    h("span", { class: "eyebrow" }, dayLabel(day, isoDay(new Date()))),
    h("h1", null, "Ajouter un repas"),
    h("div", { class: "card stack" }, sp.el, desc, boxRow, h("div", { class: "stack", style: "gap:8px" }, h("strong", null, "Photo (facultatif)"), cam, lib, photoBtns, previewBox,
      h("p", { class: "muted", style: "font-size:.8125rem" }, "Pour une meilleure estimation : photo de dessus, bien éclairée, assiette entière visible ; précisez dans la description les quantités, l'huile et les sauces (ce qu'on ne voit pas).")),
      h("label", { class: "row", for: "meal-est" }, est, h("span", null, "Estimer calories et macros avec l'IA")),
      err,
      h("p", { class: "muted", style: "font-size:.8125rem" }, "La photo est redimensionnée sur votre téléphone, stockée sur votre serveur et envoyée à l'IA uniquement pour l'estimation. Les chiffres sont des ordres de grandeur, souvent sous-estimés : suivez la tendance de la semaine, pas un repas isolé."), err),
    actionBar(go),
  );
}

// Produit emballé (N10) : code saisi ou lu sur une photo (BarcodeDetector si le navigateur l'a), valeurs pour 100 g × quantité, sans IA.
async function readBarcode(file) {
  const det = new BarcodeDetector({ formats: ["ean_13", "ean_8", "upc_a", "upc_e"] });
  const bmp = await createImageBitmap(file);
  const found = await det.detect(bmp);
  return found.length ? found[0].rawValue : null;
}

function barcodeForm(day) {
  const sp = slotPicker();
  let product = null;
  const err = h("p", { class: "error", role: "alert" });
  const code = h("input", { id: "bc-code", type: "text", inputmode: "numeric", maxlength: "14", autocomplete: "off", placeholder: "Code-barres (8 à 14 chiffres)", "aria-label": "Code-barres" });
  const grams = h("input", { id: "bc-grams", type: "number", inputmode: "decimal", min: "1", max: "5000", step: "1", placeholder: "Quantité mangée (g)", "aria-label": "Quantité mangée en grammes" });
  const info = h("div", { class: "stack", hidden: true, "aria-live": "polite" });
  const go = h("button", { class: "btn primary", disabled: true }, "Enregistrer");
  const find = h("button", { class: "btn sm" }, "Chercher");
  const per = (g) => (product ? Math.round((product.kcal_100g * g) / 100) : 0);
  const refresh = () => {
    const g = Number(grams.value);
    go.disabled = !product || !(g > 0);
    const out = info.querySelector("[data-out]");
    if (out) out.textContent = g > 0 ? __("≈ {kcal} kcal pour {g} g", { kcal: per(g), g }) : __("Indiquez la quantité mangée.");
  };
  const lookup = async () => {
    err.textContent = ""; product = null; info.hidden = true; go.disabled = true;
    const c = code.value.replace(/\s/g, "");
    if (!c) { err.textContent = __("Saisissez ou scannez un code-barres."); return; }
    find.disabled = true; find.textContent = __("Recherche…");
    try {
      product = await api(`/users/${userId}/nutrition/barcode/${encodeURIComponent(c)}`);
      if (product.serving_g && !grams.value) grams.value = product.serving_g;
      info.replaceChildren(h("strong", null, product.name + (product.brand ? ` · ${product.brand}` : "")),
        h("p", { class: "muted" }, __("Pour 100 g : {kcal} kcal · P {p} g · G {c} g · L {f} g", { kcal: product.kcal_100g, p: product.protein_100g, c: product.carbs_100g, f: product.fat_100g })),
        h("p", { "data-out": "" }));
      info.hidden = false; refresh();
    } catch (e) { err.textContent = e.message; }
    find.disabled = false; find.textContent = __("Chercher");
  };
  find.addEventListener("click", lookup);
  code.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); lookup(); } });
  grams.addEventListener("input", refresh);
  let scan = null;
  if (window.BarcodeDetector) {
    const cam = h("input", { type: "file", accept: "image/*", capture: "environment", hidden: true, "aria-label": "Photographier le code-barres" });
    cam.addEventListener("change", async () => {
      const f = cam.files[0]; cam.value = ""; err.textContent = "";
      if (!f) return;
      try { const v = await readBarcode(f); if (v) { code.value = v; lookup(); } else err.textContent = __("Code non lu : cadrez-le de près, bien éclairé, ou saisissez les chiffres."); }
      catch { err.textContent = __("Lecture impossible sur cet appareil : saisissez les chiffres."); }
    });
    scan = h("div", null, cam, h("button", { type: "button", class: "photo-btn primary", onclick: () => cam.click() }, icon("camera"), h("span", null, "Scanner le code-barres")));
  }
  go.addEventListener("click", async () => {
    go.disabled = true; go.textContent = "Enregistrement…";
    try {
      await api(`/users/${userId}/nutrition/meals`, { method: "POST", body: { day, slot: sp.get(), barcode: product.code, grams: Number(grams.value) } });
      nutritionScreen(day);
    } catch (e) { err.textContent = e.message; go.disabled = false; go.textContent = "Enregistrer"; }
  });
  show(
    h("div", { class: "top" }, h("button", { class: "iconbtn", "aria-label": "Retour", onclick: () => nutritionScreen(day) }, icon("back"), "Nutrition"), h("span", { class: "grow" })),
    h("span", { class: "eyebrow" }, dayLabel(day, isoDay(new Date()))),
    h("h1", null, "Produit emballé"),
    h("div", { class: "card stack" }, sp.el, scan, h("div", { class: "row", style: "gap:8px" }, code, find), info, grams,
      h("p", { class: "muted", style: "font-size:.8125rem" }, "Valeurs de l'emballage (Open Food Facts, base collaborative : elles peuvent être inexactes, corrigez-les au besoin). Seul le code-barres est envoyé ; aucune IA n'intervient."), err),
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
    count.textContent = __("{length} publication{v}", { length: items.length, v: items.length > 1 ? "s" : "" });
    list.replaceChildren(...items.map((e) => h("div", { class: "card stack", id: e.id, style: e.id === focusId ? "outline:2px solid var(--accent)" : "" },
      h("div", { class: "row between" }, h("strong", null, e.id), h("span", { class: "chip" }, CONF[e.confidence] || e.confidence)),
      h("p", null, e.citation), h("p", { class: "muted" }, `${e.design}`),
      h("p", null, e.finding_fr), h("p", { class: "muted" }, __("Limites : {limits_fr}", { limits_fr: e.limits_fr })),
      e.applies_to.length ? h("div", { class: "chips" }, e.applies_to.map((r) => h("span", { class: "chip" }, __("Règle {r}", { r })))) : null,
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
// ---------- accueil : intro, questions essentielles, analyse du coach ----------
// Nouvel utilisateur : bienvenue, une douzaine de questions essentielles, puis une page de chargement pendant que le coach IA relit le profil.
// Sans question manquante on arrive sur l'application ; sinon sur « Quelques précisions ». L'indicateur est local : un utilisateur existant n'est jamais renvoyé ici.
const onboardKey = () => `sc-onboarding-${userId}`;

async function route() {
  let prof;
  try { prof = await api(`/users/${userId}/profile`); } catch (e) { return fail(e); }
  if (prof.answered === 0 && !prof.intake_done) return welcomeScreen();
  if (store.get(onboardKey()) === "1") return prof.essential.remaining > 0 ? onboardingNext() : intakeScreen();
  home();
}

function welcomeScreen() {
  store.set(onboardKey(), "1");
  const rows = [["plan", "Un plan à votre mesure", "Course, trail, musculation… selon vos objectifs, votre matériel et votre emploi du temps."],
    ["watch", "Il suit ce que vous faites vraiment", "Relié à votre montre, il compare le prévu et le réel, puis ajuste la semaine suivante."],
    ["lock", "Vos données restent chez vous", "Elles sont hébergées sur votre serveur. Rien n'est vendu ni partagé."]];
  show(h("div", { class: "welcome" },
    h("div", { class: "welcome-logo" }, h("img", { src: "/icons/icon-192.png", alt: "", width: 84, height: 84 })),
    h("h1", null, userName ? __("Bienvenue, {userName}", { userName }) : "Bienvenue"),
    h("p", { class: "lead" }, "Votre coach sportif construit un plan pour vous, puis l'adapte chaque semaine."),
    h("ul", { class: "benefits" }, rows.map(([ic, t, d]) => h("li", null, h("span", { class: "bicon" }, icon(ic)), h("div", { class: "stack", style: "gap:2px" }, h("strong", null, t), h("span", { class: "muted" }, d)))))),
    actionBar(h("button", { class: "btn primary", onclick: onboardingNext }, "Commencer"), h("p", { class: "muted", style: "text-align:center;font-size:.875rem" }, "Environ 3 minutes · vous pouvez passer ce que vous ne savez pas")));
}

async function onboardingNext() {
  let r;
  try { r = await api(`/users/${userId}/questions/next?n=1&tier=essential`); } catch (e) { return fail(e); }
  if (!r.questions.length) return intakeScreen();
  const total = r.essential.answered + r.essential.remaining;
  questionView(r.questions[0], { progress: { answered: r.essential.answered, remaining_visible: r.essential.remaining }, eyebrow: __("Question {v} sur {total}", { v: r.essential.answered + 1, total }),
    onDone: onboardingNext, onBack: r.essential.answered ? undefined : welcomeScreen });
}

async function intakeScreen() {
  const steps = [["Profil enregistré", "done"], ["Analyse par votre coach IA", "wait"], ["Préparation de votre plan", "idle"]];
  const list = h("ul", { class: "steps" }, steps.map(([t, st], i) => h("li", { class: st, "data-i": i }, h("span", { class: "tick" }, icon("check")), h("span", null, t))));
  const mark = (i, st) => { const li = list.children[i]; li.className = st; };
  show(h("div", { class: "loading" },
    h("div", { class: "orb", "aria-hidden": "true" }, icon("spark")),
    h("h1", null, "Vos informations sont transmises à votre coach IA"),
    h("p", { class: "lead" }, "Il relit votre profil pour construire un plan sur mesure."), list));
  const pause = (ms) => new Promise((ok) => setTimeout(ok, reducedMotion() ? Math.min(ms, 400) : ms));
  let res = null, failed = false;
  const [r] = await Promise.all([api(`/users/${userId}/coach/intake`, { method: "POST" }).catch(() => { failed = true; return null; }), pause(2400)]);
  res = r;
  mark(1, "done");
  if (res && res.status === "questions") return intakeQuestions(res);
  finishOnboarding(list, failed);
}

async function finishOnboarding(list, failed) {
  const li = list ? list.children[2] : null;
  if (li) li.className = "wait";
  try {
    const plan = await api(`/users/${userId}/plan`);
    if (!plan.sessions.length) await api(`/users/${userId}/plan/generate`, { method: "POST", body: { weeks: 1 } });
  } catch { /* le plan se génère aussi depuis l'écran Plan */ }
  if (li) { li.className = "done"; await new Promise((ok) => setTimeout(ok, reducedMotion() ? 0 : 600)); }
  store.del(onboardKey());
  home();
}

function intakeQuestions(res) {
  const queue = [...res.questions.map((q) => ({ q })), ...res.clarifications.map((c) => ({ c }))];
  const total = queue.length;
  const step = () => {
    const item = queue.shift();
    if (!item) return finishOnboarding(null, false);
    const n = total - queue.length;
    if (item.q) return questionView(item.q, { progress: { answered: n - 1, remaining_visible: total - n + 1 }, eyebrow: "Votre coach demande", note: item.q.reason || res.message, onDone: step, onBack: undefined });
    clarification(item.c, n, total, step);
  };
  step();
}

function clarification(c, n, total, onDone) {
  const txt = h("textarea", { "aria-label": c.question, maxlength: 600, placeholder: "Votre réponse…" });
  const err = h("p", { class: "error", role: "alert" });
  const go = h("button", { class: "btn primary", disabled: true }, "Valider");
  txt.addEventListener("input", () => { go.disabled = !txt.value.trim(); });
  go.addEventListener("click", async () => {
    go.disabled = true;
    try { await api(`/users/${userId}/coach/intake/clarification`, { method: "POST", body: { index: c.index, answer: txt.value.trim() } }); onDone(); }
    catch (e) { err.textContent = __(e.message); go.disabled = false; }
  });
  show(h("div", { class: "top" }, h("span", { class: "grow" }), segments(n - 1, total - n + 1)),
    h("span", { class: "eyebrow" }, "Votre coach demande"), h("h2", { class: "q" }, c.question),
    c.reason && h("p", { class: "coachnote" }, icon("spark"), h("span", null, c.reason)), txt, err,
    actionBar(go, h("div", { class: "links" }, h("button", { class: "link", onclick: onDone }, "Préférer ne pas répondre"))));
}

// Langue de l'interface : choix mémorisé sur l'appareil, sinon langue du compte, sinon langue du navigateur (anglais pour une langue non gérée).
async function setupLocale(me) {
  const stored = store.get("lang");
  const locale = await I18N.load(I18N.detect(stored && I18N.LOCALES[stored] ? stored : me && me.lang, navigator.languages));
  document.documentElement.lang = locale;
  return locale;
}

async function start() {
  let me = null;
  try { me = await api("/auth/me"); } catch (e) { if (e.status !== 401) return fail(e); }
  const locale = await setupLocale(me);
  try {
    bank = await api(`/bank?lang=${locale}`);
    byId = new Map(bank.map((q) => [q.id, q]));
  } catch (e) { return fail(e); }
  if (!me) return authScreen();
  userId = String(me.id); userName = me.name;
  if (me.lang !== locale) api("/auth/language", { method: "PUT", body: { lang: locale } }).catch(() => {});  // le compte suit l'appareil (notifications, mails)
  route();
}

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => { /* hors HTTPS ou refusé : sans impact */ });
}
start();

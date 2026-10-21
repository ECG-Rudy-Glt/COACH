"use strict";
// Écran « Statistiques » : graphiques SVG sans dépendance. Tout vient du moteur (GET /users/{id}/stats/…), rien n'est calculé ni inventé ici.
// Chaque graphique a son alternative texte (aria-label + tableau des valeurs) ; les couleurs viennent des variables CSS des trois thèmes.
// Dépend de app.js (h, api, show, tabbar, themeToggle, store, userId, SPORT_FR, fmtDuration, __, langTag), chargé avant ce fichier. Les textes restent en français :
// h() traduit ses enfants et attributs ; tout texte hors de h() (aria-label SVG, gabarits à variables) passe par __().

const SVG_NS = "http://www.w3.org/2000/svg";
const stFmt = (n, digits = 0) => (n == null ? "–" : Number(n).toLocaleString(langTag(), { maximumFractionDigits: digits, minimumFractionDigits: digits }));
const stDay = (iso, opts) => new Date(iso + "T12:00:00").toLocaleDateString(langTag(), opts);
const stPace = (m) => { if (m == null) return null; const s = Math.round(m * 60); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };

function svgEl(tag, attrs, text) {
  const el = document.createElementNS(SVG_NS, tag);
  for (const [k, v] of Object.entries(attrs || {})) if (v != null && v !== false) el.setAttribute(k, v);
  if (text != null) el.textContent = text;
  return el;
}

function svgRoot(W, H, label) {
  return svgEl("svg", { viewBox: `0 0 ${W} ${H}`, class: "st-chart", role: "img", "aria-label": label });
}

// Alternative texte d'un graphique : le même contenu sous forme de tableau, replié par défaut.
function valuesTable(caption, head, rows) {
  return h("details", { class: "st-table" }, h("summary", null, "Voir les valeurs"),
    h("table", null, h("caption", null, caption),
      h("thead", null, h("tr", null, head.map((c) => h("th", { scope: "col" }, c)))),
      h("tbody", null, rows.map((r) => h("tr", null, r.map((c, i) => (i === 0 ? h("th", { scope: "row" }, c) : h("td", null, c))))))));
}

// Barres par jour (7 jours) avec, si connue, la cible du jour en trait pointillé. Une valeur absente reste vide (« – »), jamais une barre à zéro.
function barChart({ days, values, targets, today, format, label }) {
  const W = 320, H = 150, PX = 6, PT = 16, PB = 24;
  const known = values.filter((v) => v != null).concat((targets || []).filter((v) => v != null));
  const max = Math.max(...known, 1) * 1.08;
  const slot = (W - 2 * PX) / values.length, bw = slot * 0.58;
  const y = (v) => PT + (H - PT - PB) * (1 - v / max);
  const svg = svgRoot(W, H, label);
  svg.append(svgEl("line", { class: "st-base", x1: PX, x2: W - PX, y1: H - PB, y2: H - PB }));
  values.forEach((v, i) => {
    const cx = PX + slot * i + slot / 2;
    if (v != null) {
      const top = y(v);
      svg.append(svgEl("rect", { class: `st-bar${days[i] === today ? " today" : ""}`, x: cx - bw / 2, y: top, width: bw, height: Math.max(H - PB - top, 1), rx: 3 }));
      svg.append(svgEl("text", { class: "st-val", x: cx, y: top - 3, "text-anchor": "middle" }, format(v)));
    } else {
      svg.append(svgEl("text", { class: "st-text", x: cx, y: H - PB - 6, "text-anchor": "middle" }, "–"));
    }
    if (targets && targets[i] != null) svg.append(svgEl("line", { class: "st-target", x1: cx - slot / 2 + 3, x2: cx + slot / 2 - 3, y1: y(targets[i]), y2: y(targets[i]) }));
    svg.append(svgEl("text", { class: `st-text${days[i] === today ? " strong" : ""}`, x: cx, y: H - 7, "text-anchor": "middle" },
      stDay(days[i], { weekday: "short" }).replace(".", "").slice(0, 3)));
  });
  return svg;
}

// Courbe dans le temps (axe horizontal proportionnel aux dates) : points = valeurs brutes, trait = moyenne glissante, pointillé = objectif.
function lineChart({ series, target, label }) {
  const W = 320, H = 150, PL = 34, PR = 8, PT = 12, PB = 22;
  const t = (iso) => new Date(iso + "T12:00:00").getTime();
  const t0 = t(series[0].day), t1 = t(series[series.length - 1].day);
  const vals = series.flatMap((p) => [p.kg, p.avg]).concat(target ? [target] : []);
  const lo = Math.floor(Math.min(...vals) - 0.5), hi = Math.ceil(Math.max(...vals) + 0.5);
  const x = (iso) => PL + (t1 === t0 ? (W - PL - PR) / 2 : ((t(iso) - t0) / (t1 - t0)) * (W - PL - PR));
  const y = (v) => PT + (H - PT - PB) * (1 - (v - lo) / (hi - lo));
  const svg = svgRoot(W, H, label);
  svg.append(svgEl("line", { class: "st-base", x1: PL, x2: W - PR, y1: H - PB, y2: H - PB }));
  svg.append(svgEl("text", { class: "st-text", x: PL - 4, y: y(hi) + 3, "text-anchor": "end" }, stFmt(hi)));
  svg.append(svgEl("text", { class: "st-text", x: PL - 4, y: y(lo) + 3, "text-anchor": "end" }, stFmt(lo)));
  svg.append(svgEl("text", { class: "st-text", x: PL, y: H - 6 }, stDay(series[0].day, { day: "numeric", month: "short" })));
  svg.append(svgEl("text", { class: "st-text", x: W - PR, y: H - 6, "text-anchor": "end" }, stDay(series[series.length - 1].day, { day: "numeric", month: "short" })));
  if (target) svg.append(svgEl("line", { class: "st-target", x1: PL, x2: W - PR, y1: y(target), y2: y(target) }));
  svg.append(...series.map((p) => svgEl("circle", { class: "st-dot", cx: x(p.day), cy: y(p.kg), r: 2.4 })));
  if (series.length > 1) svg.append(svgEl("polyline", { class: "st-line", points: series.map((p) => `${x(p.day)},${y(p.avg)}`).join(" ") }));
  else svg.append(svgEl("circle", { class: "st-bar", cx: x(series[0].day), cy: y(series[0].avg), r: 4 }));
  return svg;
}

const stLegend = (...items) => h("div", { class: "st-legend" }, items.map(([cls, text]) => h("span", null, h("i", { class: cls }), text)));
const stCard = (title, ...kids) => h("section", { class: "card stack", "aria-label": title }, h("h3", null, title), ...kids);
const stEmpty = (title, text, action) => stCard(title, h("p", { class: "muted" }, text), action || null);

// ---------- section « Quotidien » ----------

function stepsCard(s) {
  if (!s.connected) return stEmpty("Pas par jour", "Connectez votre montre Garmin (Profil, puis Garmin) pour suivre vos pas. Sans montre, cette courbe reste vide plutôt que d'afficher des zéros.");
  if (!s.days_measured && s.days.every((d) => d.steps == null)) return stEmpty("Pas par jour", "Aucun relevé de pas pour l'instant. La prochaine synchronisation Garmin les récupère.");
  const today = s.days[s.days.length - 1].day;
  const label = s.average != null ? __("Pas par jour sur 7 jours, moyenne {average} pas.", { average: stFmt(s.average) }) : __("Pas par jour sur 7 jours.");
  return stCard("Pas par jour",
    s.average != null ? h("p", null, h("span", { class: "st-big" }, stFmt(s.average)), h("span", { class: "st-unit" }, "pas par jour en moyenne")) : null,
    barChart({ days: s.days.map((d) => d.day), values: s.days.map((d) => d.steps), today, label, format: (v) => (v >= 1000 ? `${stFmt(v / 1000, 1)}k` : stFmt(v)) }),
    h("p", { class: "st-note" }, "Relevés de la montre. Aujourd'hui est en cours : il est grisé et ne compte pas dans la moyenne. « – » : pas de relevé."),
    valuesTable("Pas par jour", ["Jour", "Pas"], s.days.map((d) => [stDay(d.day, { weekday: "long", day: "numeric", month: "short" }), d.steps == null ? "pas de relevé" : stFmt(d.steps)])));
}

function mealsCard(n) {
  const est = n.days.filter((d) => d.kcal != null);
  if (!est.length) return stEmpty("Repas des 7 derniers jours", "Aucun repas estimé cette semaine. Ajoutez vos repas dans Nutrition : les moyennes de la semaine apparaîtront ici.",
    h("button", { class: "btn sm", style: "align-self:flex-start", onclick: () => nutritionScreen() }, "Ouvrir Nutrition"));
  const a = n.average, today = n.days[n.days.length - 1].day, days = n.days.map((d) => d.day);
  const listed = (key) => est.map((d) => `${stDay(d.day, { weekday: "long" })} ≈ ${stFmt(d[key])}`).join(", ");
  const chart = (key, tkey, name, label) => h("div", { class: "stack", style: "gap:6px" }, h("strong", null, name),
    barChart({ days, today, values: n.days.map((d) => d[key]), targets: n.days.map((d) => d[tkey]), format: (v) => stFmt(v), label }));
  return stCard("Repas des 7 derniers jours",
    h("p", null, h("span", { class: "st-big" }, `≈ ${stFmt(a.kcal)}`), h("span", { class: "st-unit" }, "kcal par jour en moyenne"),
      a.target_kcal != null ? h("span", { class: "muted" }, " ", __("(cible ≈ {target})", { target: stFmt(a.target_kcal) })) : null),
    h("p", { class: "muted" }, __("Protéines ≈ {protein} g par jour.", { protein: stFmt(a.protein_g) }), a.target_protein_g != null ? [" ", __("Cible ≈ {target} g.", { target: stFmt(a.target_protein_g) })] : null, " ",
      __("Moyenne calculée sur {days} jour{v} avec repas estimés, sur 7.", { days: a.days, v: a.days > 1 ? "s" : "" })),
    chart("kcal", "target_kcal", "Énergie", __("Énergie estimée par jour sur 7 jours, en kcal : {values}.", { values: listed("kcal") })),
    chart("protein_g", "target_protein_g", "Protéines", __("Protéines estimées par jour sur 7 jours, en g : {values}.", { values: listed("protein_g") })),
    n.has_target ? stLegend(["", "estimé"], ["target", "cible du jour"]) : h("p", { class: "muted" }, "Pas de cible affichée : renseignez votre taille, votre année de naissance et votre poids dans le profil."),
    h("p", { class: "st-note" }, "Estimations par texte ou photo : ordres de grandeur, souvent sous-évalués. Lisez la moyenne de la semaine plutôt qu'un jour isolé. Un jour sans repas estimé reste vide, il n'est pas compté comme zéro."),
    valuesTable("Repas estimés par jour", ["Jour", "Énergie (≈ kcal)", "Cible", "Protéines (≈ g)", "Cible"],
      n.days.map((d) => [stDay(d.day, { weekday: "long", day: "numeric", month: "short" }), d.kcal == null ? (d.meals ? "non estimé" : "aucun repas") : stFmt(d.kcal),
        stFmt(d.target_kcal), d.protein_g == null ? "–" : stFmt(d.protein_g), stFmt(d.target_protein_g)])));
}

function weightCard(w) {
  if (!w.series.length) return stEmpty("Poids", "Aucune pesée enregistrée. Deux pesées par semaine, le matin, suffisent : on suit la tendance, pas le chiffre d'un jour.",
    h("button", { class: "btn sm", style: "align-self:flex-start", onclick: () => nutritionScreen() }, "Saisir mon poids"));
  const rate = w.rate_pct_per_week;
  const label = w.target_kg ? __("Courbe de poids sur 60 jours : tendance sur 7 jours {current} kg, objectif {target} kg.", { current: stFmt(w.current, 1), target: stFmt(w.target_kg, 1) })
    : __("Courbe de poids sur 60 jours : tendance sur 7 jours {current} kg.", { current: stFmt(w.current, 1) });
  return stCard("Poids",
    h("p", null, h("span", { class: "st-big" }, stFmt(w.current, 1)), h("span", { class: "st-unit" }, "kg"), h("span", { class: "muted" }, "(tendance sur 7 jours)")),
    rate != null ? h("p", { class: "muted" }, __("Rythme : {rate} % par semaine.", { rate: `${rate > 0 ? "+" : ""}${stFmt(rate, 2)}` })) : h("p", { class: "muted" }, "Rythme non calculé : il faut au moins 3 pesées réparties sur 7 jours."),
    lineChart({ series: w.series, target: w.target_kg, label }),
    stLegend(["", "tendance 7 jours"], ["dot", "pesée"], ...(w.target_kg ? [["target", __("objectif {target} kg", { target: stFmt(w.target_kg, 1) })]] : [])),
    valuesTable("Pesées et tendance", ["Jour", "Pesée (kg)", "Tendance (kg)"], w.series.slice().reverse().map((p) => [stDay(p.day, { day: "numeric", month: "short", year: "2-digit" }), stFmt(p.kg, 1), stFmt(p.avg, 1)])));
}

function weekCard(wk) {
  const pct = wk.planned ? Math.min(100, Math.round((wk.done / wk.planned) * 100)) : 0;
  return stCard("Cette semaine",
    wk.planned ? h("p", null, h("span", { class: "st-big" }, `${wk.done} / ${wk.planned}`), " ", wk.planned > 1 ? "séances faites" : "séance faite") : h("p", { class: "muted" }, "Pas de séance prévue cette semaine."),
    wk.planned ? h("div", { class: "st-meter", role: "img", "aria-label": __("{done} séances faites sur {planned} prévues", { done: wk.done, planned: wk.planned }) }, h("i", { style: `width:${pct}%` })) : null,
    h("p", { class: "muted" }, wk.minutes || wk.run_km ? [wk.minutes ? __("{duration} d'activité", { duration: fmtDuration(wk.minutes) }) : null, wk.minutes && wk.run_km ? " · " : null,
      wk.run_km ? __("{km} km de course", { km: stFmt(wk.run_km, 1) }) : null] : "Aucune activité enregistrée depuis lundi."));
}

function recentCard(items) {
  if (!items.length) return stEmpty("Activités récentes", "Aucune activité sur les 14 derniers jours. Elles apparaissent ici quand la montre les synchronise ou quand vous validez une séance.");
  const sport = (s) => (typeof SPORT_FR !== "undefined" && SPORT_FR[s]) || "Autre";
  return stCard("Activités récentes", h("div", null, items.map((a) => h("div", { class: "item" },
    h("span", { class: "l" }, h("strong", null, a.title), h("span", { class: "sub" }, stDay(a.day, { weekday: "short", day: "numeric", month: "short" }), " · ", sport(a.sport), a.source === "saisie" ? [" · ", "saisie à la main"] : null)),
    h("span", { class: "v" }, [a.minutes ? __("{m} min", { m: a.minutes }) : null, a.distance_km ? `${stFmt(a.distance_km, 1)} km` : null, a.pace_min_km ? `${stPace(a.pace_min_km)} /km` : null,
      a.avg_hr ? __("FC {hr}", { hr: a.avg_hr }) : null].filter(Boolean).join(" · "))))));
}

async function renderDaily(box) {
  const d = await api(`/users/${userId}/stats/daily`);
  box.replaceChildren(weekCard(d.week), stepsCard(d.steps), mealsCard(d.nutrition), weightCard(d.weight), recentCard(d.recent));
}

// ---------- écran ----------

// Sections de l'écran : [id, libellé, rendu]. Chaque lot en ajoute une.
const STATS_SECTIONS = [["daily", "Quotidien", renderDaily]];

async function statsScreen(section) {
  const cur = STATS_SECTIONS.find((s) => s[0] === (section || store.get("sc-stats-section"))) || STATS_SECTIONS[0];
  store.set("sc-stats-section", cur[0]);
  const box = h("div", { class: "stack", "aria-live": "polite" }, h("p", { class: "muted" }, "Chargement…"));
  const nav = STATS_SECTIONS.length > 1 ? h("div", { class: "st-seg", role: "group", "aria-label": "Section" }, STATS_SECTIONS.map(([id, name]) =>
    h("button", { type: "button", class: "chip", style: `border:0;cursor:pointer;opacity:${id === cur[0] ? 1 : 0.6};${id === cur[0] ? "outline:2px solid var(--accent)" : ""}`,
      "aria-pressed": id === cur[0], onclick: () => statsScreen(id) }, name))) : null;
  show(h("div", { class: "head" }, h("span", { class: "eyebrow" }, "Statistiques"), themeToggle()), h("h1", null, "Statistiques"), nav, box,
    h("p", { class: "st-note" }, "Chiffres calculés par le moteur à partir de vos données, jamais par une IA. Ce suivi ne remplace pas un avis médical."), tabbar("home"));
  try { await cur[2](box); } catch (e) { if (!e.handled) box.replaceChildren(h("p", { class: "error", role: "alert" }, e.message || "Statistiques indisponibles.")); }
}

function statsCard() {
  return h("div", { class: "card row" },
    h("div", { class: "grow stack" }, h("h3", null, "Statistiques"), h("p", { class: "muted" }, "Pas, repas, poids et séances en graphiques, calculés à partir de vos données.")),
    h("button", { class: "btn sm", onclick: () => statsScreen() }, "Voir"));
}

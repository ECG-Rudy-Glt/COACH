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
function barChart({ days, values, targets, today, format, label, tick }) {
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
      tick ? tick(days[i]) : stDay(days[i], { weekday: "short" }).replace(".", "").slice(0, 3)));
  });
  return svg;
}

// Courbe dans le temps (axe horizontal proportionnel aux dates) : points = valeurs brutes, trait = tendance ou repère, pointillé = objectif.
// `invert` : les petites valeurs (temps, allure) sont en haut, car plus bas veut dire plus rapide. `snap` : bornes entières (poids).
function plotChart({ dots = [], line = [], target, fmt = stFmt, snap = false, invert = false, label }) {
  const W = 320, H = 150, PL = 40, PR = 8, PT = 12, PB = 22;
  const all = [...dots, ...line];
  const t = (iso) => new Date(iso + "T12:00:00").getTime();
  const times = all.map((p) => t(p.day)), t0 = Math.min(...times), t1 = Math.max(...times);
  const vals = all.map((p) => p.y).concat(target ? [target] : []);
  const vmin = Math.min(...vals), vmax = Math.max(...vals), pad = Math.max((vmax - vmin) * 0.1, vmax * 0.01);
  const lo = snap ? Math.floor(vmin - 0.5) : vmin - pad, hi = snap ? Math.ceil(vmax + 0.5) : vmax + pad;
  const x = (iso) => PL + (t1 === t0 ? (W - PL - PR) / 2 : ((t(iso) - t0) / (t1 - t0)) * (W - PL - PR));
  const y = (v) => PT + (H - PT - PB) * (invert ? (v - lo) / (hi - lo) : 1 - (v - lo) / (hi - lo));
  const svg = svgRoot(W, H, label);
  svg.append(svgEl("line", { class: "st-base", x1: PL, x2: W - PR, y1: H - PB, y2: H - PB }));
  svg.append(svgEl("text", { class: "st-text", x: PL - 4, y: y(hi) + 3, "text-anchor": "end" }, fmt(hi)));
  svg.append(svgEl("text", { class: "st-text", x: PL - 4, y: y(lo) + 3, "text-anchor": "end" }, fmt(lo)));
  svg.append(svgEl("text", { class: "st-text", x: PL, y: H - 6 }, stDay(new Date(t0).toISOString().slice(0, 10), { day: "numeric", month: "short", year: t1 - t0 > 300 * 864e5 ? "2-digit" : undefined })));
  svg.append(svgEl("text", { class: "st-text", x: W - PR, y: H - 6, "text-anchor": "end" }, stDay(new Date(t1).toISOString().slice(0, 10), { day: "numeric", month: "short", year: t1 - t0 > 300 * 864e5 ? "2-digit" : undefined })));
  if (target) svg.append(svgEl("line", { class: "st-target", x1: PL, x2: W - PR, y1: y(target), y2: y(target) }));
  if (line.length > 1) svg.append(svgEl("polyline", { class: "st-line", points: line.map((p) => `${x(p.day)},${y(p.y)}`).join(" ") }));
  svg.append(...dots.map((p) => svgEl("circle", { class: "st-dot", cx: x(p.day), cy: y(p.y), r: 2.6 })));
  if (line.length === 1 && !dots.length) svg.append(svgEl("circle", { class: "st-bar", cx: x(line[0].day), cy: y(line[0].y), r: 4 }));
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
    plotChart({ dots: w.series.map((p) => ({ day: p.day, y: p.kg })), line: w.series.map((p) => ({ day: p.day, y: p.avg })), target: w.target_kg, snap: true, label }),
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

// ---------- section « Progression » ----------

const stTime = (min) => { if (min == null) return "–"; const s = Math.round(min * 60); return s >= 3600 ? `${Math.floor(s / 3600)}:${String(Math.floor(s % 3600 / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
const stN = (n) => stFmt(n, Number.isInteger(n) ? 0 : 1); // 110 kg, 77,5 kg : pas de « ,0 » inutile
const stShort = (iso) => stDay(iso, { day: "numeric", month: "short" });
// Ligne « libellé, source / valeur » (même mise en page que les listes de l'application).
const stItem = (title, sub, value) => h("div", { class: "item" }, h("span", { class: "l" }, h("strong", null, title), sub ? h("span", { class: "sub" }, sub) : null), h("span", { class: "v" }, value));

function runRecordsCard(rows) {
  const blocks = rows.map((r) => {
    const items = [];
    if (r.declared.pr) items.push(stItem("Record déclaré", r.declared.pr.year ? __("année {year}", { year: r.declared.pr.year }) : "", r.declared.pr.time));
    if (r.declared.now) items.push(stItem("Niveau actuel déclaré", "", r.declared.now.time));
    if (r.measured) items.push(stItem(__("Meilleure allure mesurée sur une sortie d'au moins {km} km", { km: r.distance_km }),
      __("{km} km en {minutes} min, {day}", { km: stN(r.measured.km), minutes: r.measured.minutes, day: stShort(r.measured.day) }), `${r.measured.pace} /km`));
    if (r.watch) items.push(stItem("Estimation de la montre", stShort(r.watch.day), r.watch.time));
    return h("div", null, h("h4", null, r.label), items.length ? items : h("p", { class: "muted" }, "Aucun record ni sortie assez longue pour l'instant."));
  });
  return stCard("Records de course", ...blocks,
    h("p", { class: "st-note" }, "Trois sources distinctes, jamais mélangées : ce que vous avez déclaré, la meilleure allure réellement mesurée sur une sortie assez longue (ce n'est pas un temps de course), et l'estimation de la montre."));
}

function liftRecordsCard(lifts, declared) {
  if (!lifts.length && !declared.length) return stEmpty("Records de charges", "Saisissez vos charges et répétitions dans les séances de musculation, ou renseignez vos records dans Mes performances : ils apparaissent ici.");
  const kg = (v) => `${stN(v)} kg`;
  return stCard("Records de charges",
    lifts.length ? h("div", null, h("h4", null, "Saisis dans les séances"), lifts.map((l) => stItem(l.name,
      l.e1rm != null ? __("meilleur e1RM ≈ {e1rm} kg, {day}", { e1rm: stN(l.e1rm), day: stShort(l.e1rm_day) }) : stShort(l.day), `${kg(l.kg)} × ${stFmt(l.reps)}`))) : null,
    declared.length ? h("div", null, h("h4", null, "Déclarés dans Mes performances"), declared.map((d) => stItem(d.label,
      d.now ? __("niveau actuel {kg} kg × {reps}", { kg: stN(d.now.kg), reps: d.now.reps }) : "", d.pr ? `${kg(d.pr.kg)} × ${d.pr.reps}${d.pr.e1rm ? ` (≈ ${stN(d.pr.e1rm)})` : ""}` : "–"))) : null,
    h("p", { class: "st-note" }, "e1RM : maximum théorique sur une répétition, estimé par la formule d'Epley (charge × (1 + répétitions / 30)). Calculé seulement pour 1 à 10 répétitions : c'est une estimation, pas un test."));
}

function stTrajectoryCard(t) {
  if (!t) return stEmpty("Trajectoire vers l'objectif", "Pas d'objectif de performance daté. Ajoutez-en un dans Objectifs (par exemple « 10 km en moins de 40 min » dans deux ans) : les étapes et le repère de progression apparaissent ici.",
    h("button", { class: "btn sm", style: "align-self:flex-start", onclick: () => goalsScreen() }, "Ouvrir Objectifs"));
  const g = t.target;
  const verdict = { atteint: "Objectif atteint", réaliste: "Rythme réaliste", ambitieux: "Rythme ambitieux", "très ambitieux": "Rythme très ambitieux", inconnu: "Niveau actuel inconnu" }[t.verdict] || t.verdict;
  const hasChart = t.reference.length || t.measured.length;
  const label = __("Trajectoire : objectif {time} sur {km} km le {date}.", { time: g.time, km: stN(g.distance_km), date: stDay(g.date, { day: "numeric", month: "long", year: "numeric" }) });
  return stCard("Trajectoire vers l'objectif",
    h("p", null, h("span", { class: "st-big" }, g.time), h("span", { class: "st-unit" }, __("sur {km} km, soit {pace} /km", { km: stN(g.distance_km), pace: g.pace }))),
    h("p", { class: "muted" }, g.title, " · ", stDay(g.date, { day: "numeric", month: "long", year: "numeric" })),
    t.level ? h("p", null, __("Niveau actuel équivalent : {time}", { time: t.level.time }), " ", h("span", { class: "muted" }, `(${t.level.source})`)) : h("p", { class: "muted" }, "Niveau actuel inconnu : renseignez un record de 5 km ou de 10 km dans Mes performances."),
    t.level ? h("p", { class: "muted" }, `${verdict}. `, t.verdict === "atteint" ? "" : __("Écart à combler : {gap} % en {weeks} semaines.", { gap: stN(t.gap_pct), weeks: t.weeks_left })) : null,
    hasChart ? plotChart({ dots: t.measured.map((m) => ({ day: m.day, y: m.minutes })), line: t.reference.map((r) => ({ day: r.day, y: r.minutes })), target: t.goal_minutes, fmt: stTime, invert: true, label }) : null,
    hasChart ? stLegend(...(t.measured.length ? [["dot", "estimation de la montre"]] : []), ...(t.reference.length ? [["", "repère de progression"]] : []), ["target", "objectif"]) : null,
    h("p", { class: "st-note" }, "Le repère relie votre niveau actuel à l'objectif en ligne droite : c'est une référence, pas une prévision. Plus haut sur le graphique = plus rapide."),
    ...t.warnings.map((w) => h("p", { class: "muted" }, w)),
    t.phases.length ? h("div", null, h("h4", null, "Phases"), t.phases.map((p) => stItem(p.label, p.text, __("{weeks} sem. · {start}", { weeks: p.weeks, start: stShort(p.start) })))) : null,
    t.milestones.length ? valuesTable("Jalons : un test chronométré tous les trois mois", ["Date", "Épreuve", "Temps visé"], t.milestones.map((m) => [stDay(m.date, { day: "numeric", month: "long", year: "numeric" }), m.label, m.target_time])) : null,
    h("p", { class: "st-note" }, __("Règles C10 à C12. Volume de course visé : {km} km par semaine.", { km: t.weekly_km_target })));
}

function curvesCard(curves) {
  if (!curves.length) return stEmpty("Courbes par exercice", "Saisissez les charges et les répétitions dans vos séances de musculation : une courbe apparaît pour chaque exercice dès la deuxième séance.");
  const body = h("div", { class: "stack" });
  const pick = h("select", { "aria-label": "Exercice" }, curves.map((c, i) => h("option", { value: i }, c.name)));
  const draw = () => {
    const c = curves[Number(pick.value)], weighted = c.mode === "e1rm";
    const unit = weighted ? "kg" : "";
    const name = weighted ? "e1RM estimé (≈ kg)" : "meilleure série (répétitions)";
    const pts = c.points.map((p) => ({ day: p.day, y: p.value }));
    const label = __("{name} : {n} séances, de {first} à {last}.", { name: c.name, n: c.sessions, first: stN(pts[0].y), last: stN(pts[pts.length - 1].y) });
    body.replaceChildren(
      h("p", { class: "muted" }, name, c.change ? [" · ", __("{delta} depuis la première séance", { delta: `${c.change.abs > 0 ? "+" : ""}${stN(c.change.abs)} ${unit}`.trim() + (c.change.pct != null ? ` (${c.change.pct > 0 ? "+" : ""}${stN(c.change.pct)} %)` : "") })] : null),
      pts.length > 1 ? plotChart({ dots: pts, line: pts, fmt: (v) => stFmt(v, weighted ? 0 : 0), label }) : h("p", { class: "muted" }, "Un seul point pour l'instant : la courbe apparaît à la prochaine séance."),
      valuesTable(c.name, ["Jour", "Charge max (kg)", "Répétitions max", "Séries", weighted ? "e1RM (≈ kg)" : "Répétitions"],
        c.points.slice().reverse().map((p) => [stDay(p.day, { day: "numeric", month: "short", year: "2-digit" }), p.kg == null ? "–" : stN(p.kg), stFmt(p.reps), p.sets, stN(p.value)])));
  };
  pick.addEventListener("change", draw);
  draw();
  return stCard("Courbes par exercice", pick, body, h("p", { class: "st-note" }, "Séances faites des 16 dernières semaines, un point par jour. Avec des charges : e1RM estimé (Epley, 1 à 10 répétitions) ; sans charge : meilleure série en répétitions."));
}

function volumeCard(v) {
  const weeks = v.weeks, days = weeks.map((w) => w.monday), cur = weeks.find((w) => w.current);
  if (weeks.every((w) => !w.minutes && !w.run_km && !w.strength_sets)) return stEmpty("Volume par semaine", "Aucune activité sur les 12 dernières semaines.");
  const tick = (iso) => stDay(iso, { day: "numeric" });
  const km = weeks.map((w) => w.run_km), mins = weeks.map((w) => w.minutes);
  const kmLabel = __("Kilomètres de course par semaine sur 12 semaines, la semaine en cours est incomplète : {values}.", { values: weeks.map((w) => `${stShort(w.monday)} ${stN(w.run_km)}`).join(", ") });
  const minLabel = __("Minutes d'activité par semaine sur 12 semaines, la semaine en cours est incomplète : {values}.", { values: weeks.map((w) => `${stShort(w.monday)} ${stFmt(w.minutes)}`).join(", ") });
  return stCard("Volume par semaine",
    h("strong", null, "Course (km)"),
    barChart({ days, values: km.map((x) => (x || null)), targets: v.weekly_km_target ? km.map(() => v.weekly_km_target) : null, today: cur && cur.monday, tick, format: (x) => stN(x), label: kmLabel }),
    h("strong", null, "Temps d'activité (min)"),
    barChart({ days, values: mins.map((x) => (x || null)), today: cur && cur.monday, tick, format: (x) => stFmt(x), label: minLabel }),
    stLegend(["", "semaine (lundi au dimanche)"], ...(v.weekly_km_target ? [["target", __("repère du plan : {km} km", { km: v.weekly_km_target })]] : [])),
    h("p", { class: "st-note" }, "La semaine en cours (en clair) est incomplète. Les kilomètres viennent de la montre ; le temps inclut aussi les séances saisies à la main. Une semaine vide reste vide (« – »)."),
    valuesTable("Volume par semaine", ["Semaine du", "Course (km)", "Minutes", "Séries de muscu", "Tonnage (kg)"],
      weeks.slice().reverse().map((w) => [stDay(w.monday, { day: "numeric", month: "short" }) + (w.current ? " *" : ""), stN(w.run_km), stFmt(w.minutes), stFmt(w.strength_sets), stFmt(w.tonnage_kg)])));
}

function paceCard(p) {
  if (!p.outings.length) return stEmpty("Allure par sortie", "Aucune sortie de course sur les 4 derniers mois. Elles apparaissent ici après la synchronisation de la montre.");
  const dots = p.outings.map((o) => ({ day: o.day, y: o.pace }));
  const rec = p.recent, bef = p.before;
  const diff = p.change_s_per_km;
  const label = __("Allure de {n} sorties de course sur 4 mois, de {first} à {last} par km.", { n: p.outings.length, first: p.outings[0].pace_label, last: p.outings[p.outings.length - 1].pace_label });
  return stCard("Allure par sortie",
    rec ? h("p", null, h("span", { class: "st-big" }, rec.pace_label), h("span", { class: "st-unit" }, __("/km sur les 28 derniers jours ({n} sorties d'au moins 3 km)", { n: rec.outings }))) : h("p", { class: "muted" }, "Pas assez de sorties d'au moins 3 km sur 28 jours pour une allure moyenne."),
    diff != null ? h("p", { class: "muted" }, diff === 0 ? __("Identique aux 28 jours précédents ({pace} /km).", { pace: bef.pace_label })
      : diff < 0 ? __("{s} s/km plus rapide que les 28 jours précédents ({pace} /km).", { s: Math.abs(diff), pace: bef.pace_label })
        : __("{s} s/km plus lent que les 28 jours précédents ({pace} /km).", { s: diff, pace: bef.pace_label })) : null,
    plotChart({ dots, fmt: stPace, invert: true, label }),
    h("p", { class: "st-note" }, "Chaque point est une sortie, sans les relier : un footing, une sortie longue et une séance de vitesse n'ont pas la même allure. Plus haut = plus rapide."),
    valuesTable("Sorties de course", ["Jour", "Distance (km)", "Durée (min)", "Allure (/km)", "FC moyenne"],
      p.outings.slice().reverse().map((o) => [stDay(o.day, { day: "numeric", month: "short", year: "2-digit" }), stN(o.km), o.minutes, o.pace_label, o.avg_hr == null ? "–" : o.avg_hr])));
}

async function renderProgress(box) {
  const d = await api(`/users/${userId}/stats/progress`);
  box.replaceChildren(runRecordsCard(d.records.running), liftRecordsCard(d.records.lifts, d.records.declared_lifts), stTrajectoryCard(d.trajectory), curvesCard(d.curves), volumeCard(d.volume), paceCard(d.pace));
}

// ---------- écran ----------

// Sections de l'écran : [id, libellé, rendu]. Chaque lot en ajoute une.
const STATS_SECTIONS = [["daily", "Quotidien", renderDaily], ["progress", "Progression", renderProgress]];

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

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
  const sg = (v) => `${v > 0 ? "+" : ""}${stFmt(v, 2)}`;
  const label = w.target_kg ? __("Courbe de poids sur 60 jours : poids lissé {current} kg, objectif {target} kg.", { current: stFmt(w.current, 1), target: stFmt(w.target_kg, 1) })
    : __("Courbe de poids sur 60 jours : poids lissé {current} kg.", { current: stFmt(w.current, 1) });
  return stCard("Poids",
    h("p", null, h("span", { class: "st-big" }, stFmt(w.current, 1)), h("span", { class: "st-unit" }, "kg"), h("span", { class: "muted" }, "(poids lissé)")),
    w.kg_per_month != null ? h("p", { class: "muted" }, __("Tendance : {kg} kg par mois ({pct} % par mois).", { kg: sg(w.kg_per_month), pct: sg(w.pct_per_month) }))
      : h("p", { class: "muted" }, "Tendance non calculée : il faut au moins 3 pesées sur les 14 derniers jours."),
    plotChart({ dots: w.series.map((p) => ({ day: p.day, y: p.kg })), line: w.series.map((p) => ({ day: p.day, y: p.avg })), target: w.target_kg, snap: true, label }),
    stLegend(["", "courbe lissée"], ["dot", "pesée"], ...(w.target_kg ? [["target", __("objectif {target} kg", { target: stFmt(w.target_kg, 1) })]] : [])),
    valuesTable("Pesées et courbe lissée", ["Jour", "Pesée (kg)", "Lissé (kg)"], w.series.slice().reverse().map((p) => [stDay(p.day, { day: "numeric", month: "short", year: "2-digit" }), stFmt(p.kg, 1), stFmt(p.avg, 1)])));
}

function statsWeekCard(wk) {
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
  box.replaceChildren(statsWeekCard(d.week), stepsCard(d.steps), mealsCard(d.nutrition), weightCard(d.weight), recentCard(d.recent));
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

// ---------- section « Régularité » ----------
// Sans pression : pas de badge, pas de rappel, une séance passée volontairement n'est pas un échec, une semaine vide garde la série. Désactivable (Profil).

function goalCard(g) {
  if (!g.planned) return stCard("Objectif de la semaine", h("p", { class: "muted" }, "Pas de séance prévue cette semaine."));
  const pct = Math.min(100, Math.round((g.done / g.planned) * 100));
  return stCard("Objectif de la semaine",
    h("p", null, h("span", { class: "st-big" }, `${g.done} / ${g.planned}`), " ", g.planned > 1 ? "séances faites" : "séance faite"),
    h("div", { class: "st-meter", role: "img", "aria-label": __("{done} séances faites sur {planned} prévues", { done: g.done, planned: g.planned }) }, h("i", { style: `width:${pct}%` })),
    h("p", { class: "muted" }, g.met ? "Semaine tenue : la suite est un bonus." : __("La semaine compte comme tenue à partir de {needed} séances faites sur {planned}.", { needed: g.needed, planned: g.planned })),
    h("p", { class: "st-note" }, g.skipped > 1 ? __("{n} séances passées volontairement : elles ne comptent pas contre vous.", { n: g.skipped }) : g.skipped ? "1 séance passée volontairement : elle ne compte pas contre vous." : "Les séances prévues sont celles du plan : rien n'est ajouté ici."));
}

function streakCard(st, summary) {
  return stCard("Série de semaines",
    st.current ? h("p", null, h("span", { class: "st-big" }, st.current), h("span", { class: "st-unit" }, st.current > 1 ? "semaines tenues de suite" : "semaine tenue"))
      : h("p", { class: "muted" }, "Pas de série en cours : une prochaine semaine tenue en démarre une. Rien n'est perdu, vos semaines passées restent comptées ci-dessous."),
    st.best ? h("p", { class: "muted" }, st.best > 1 ? __("Meilleure série sur un an : {n} semaines.", { n: st.best }) : "Meilleure série sur un an : 1 semaine.") : null,
    summary.weeks_judged ? h("p", null, __("{met} semaines tenues sur {judged} terminées (12 dernières semaines).", { met: summary.weeks_met, judged: summary.weeks_judged })) : null,
    h("p", { class: "st-note" }, "Une semaine est tenue quand au moins 75 % des séances prévues sont faites. Une semaine sans séance prévue, ou une séance passée volontairement, ne casse jamais la série ; la semaine en cours non plus."));
}

function weeksCard(weeks, summary) {
  const cur = weeks.find((w) => w.current);
  const label = __("Séances faites par semaine sur 12 semaines : {values}.", { values: weeks.map((w) => `${stShort(w.monday)} ${w.done} / ${w.planned}`).join(", ") });
  return stCard("12 dernières semaines",
    barChart({ days: weeks.map((w) => w.monday), values: weeks.map((w) => (w.planned || w.done ? w.done : null)), targets: weeks.map((w) => (w.planned ? w.planned : null)), today: cur && cur.monday,
      tick: (iso) => stDay(iso, { day: "numeric" }), format: (v) => stFmt(v), label }),
    stLegend(["", "séances faites"], ["target", "séances prévues"]),
    h("p", { class: "st-note" }, __("{done} séances faites sur {planned} prévues en 12 semaines. La semaine en cours (en clair) n'est pas terminée.", { done: summary.sessions_done, planned: summary.sessions_planned })),
    valuesTable("Séances par semaine", ["Semaine du", "Faites", "Prévues", "Passées volontairement", "Semaine"],
      weeks.slice().reverse().map((w) => [stDay(w.monday, { day: "numeric", month: "short" }), w.done, w.planned, w.skipped,
        w.current ? "en cours" : w.met === true ? "tenue" : w.met === false ? "non tenue" : "sans séance prévue"])));
}

async function renderRegularity(box) {
  const d = await api(`/users/${userId}/stats/regularity`);
  if (!d.enabled) return box.replaceChildren(stEmpty("Régularité", "Cette section est masquée. Vous pouvez la réactiver dans Profil, rubrique Statistiques."));
  const off = h("button", { class: "link", style: "text-align:left", onclick: async () => {
    try { await api(`/users/${userId}/stats/preferences`, { method: "PUT", body: { regularity: false } }); statsScreen("daily"); } catch (e) { toast(e.message); } } }, "Masquer cette section");
  box.replaceChildren(goalCard(d.goal), streakCard(d.streak, d.summary), weeksCard(d.weeks, d.summary),
    h("div", { class: "card stack" }, h("p", { class: "muted" }, "Pas de badge, pas de rappel : cette page ne vous écrit jamais et ne sert qu'à vous situer. Vous pouvez la masquer quand vous voulez."), off));
}

// Réglage du profil : afficher ou non la régularité.
function statsPrefCard() {
  const body = h("div", { class: "stack" }, h("p", { class: "muted" }, "Chargement…"));
  api(`/users/${userId}/stats/preferences`).then((p) => {
    const box = h("input", { type: "checkbox", id: "st-pref-reg", checked: p.regularity });
    box.addEventListener("change", async () => {
      try { await api(`/users/${userId}/stats/preferences`, { method: "PUT", body: { regularity: box.checked } }); toast(box.checked ? "Régularité affichée" : "Régularité masquée"); }
      catch (e) { box.checked = !box.checked; toast(e.message); }
    });
    body.replaceChildren(h("label", { class: "row", for: "st-pref-reg" }, box, h("span", { class: "grow" }, "Afficher la régularité (séries de semaines, objectif de la semaine)")),
      h("p", { class: "muted" }, "Sans badge ni rappel. Décochée, la section disparaît de l'écran Statistiques et n'est plus calculée."));
  }).catch(() => body.replaceChildren(h("p", { class: "muted" }, "Réglage indisponible pour l'instant.")));
  return h("div", { class: "card stack" }, h("h3", null, "Statistiques"), body);
}

// ---------- section « Forme » (araignée) ----------
// Seulement des axes qu'une donnée mesure (ST14). Chaque axe : un pourcentage de TA propre référence, plafonné à 100 (ST15), avec sa définition, sa source,
// sa période, sa référence et sa valeur brute en texte. Pas de score global, pas de comparaison avec d'autres personnes.

const RADAR_TEXT = {
  volume: { name: "Volume", def: "Moyenne par semaine des 4 dernières semaines terminées, en kilomètres de course (en minutes d'activité si vous ne courez pas), face à votre référence.",
    source: "Source : sorties mesurées par la montre et séances saisies à la main.", range: "0 % = aucune activité ; 100 % = la référence atteinte ou dépassée." },
  regularity: { name: "Régularité", def: "Part des séances prévues par le plan qui sont faites, sur les 12 dernières semaines terminées. Les séances passées volontairement ne comptent pas.",
    source: "Source : séances du plan et leur état.", range: "0 % = aucune séance faite ; 100 % = toutes les séances prévues faites." },
  endurance: { name: "Endurance", def: "Meilleur effort de course des 8 dernières semaines mesuré par la montre, converti en temps équivalent sur la distance de l'objectif (10 km sans objectif), face à votre référence. Les temps saisis à la main et les records ne servent pas ici.",
    source: "Source : sorties de course de la montre (niveau actuel du plan).", range: "Pourcentage = temps de référence ÷ votre temps équivalent ; 100 % = référence atteinte ou battue." },
  strength: { name: "Force", def: "Maximum théorique sur une répétition (formule d'Epley, séries de 1 à 10 répétitions) des 12 dernières semaines, par exercice de référence, face aux 12 semaines précédentes. Moyenne des exercices présents dans les deux périodes.",
    source: "Source : séries chargées saisies dans vos séances.", range: "0 % = aucune charge ; 100 % = au moins aussi fort que la période précédente." },
};

const RADAR_REASONS = {
  short_history: "Pas assez d'historique : il faut au moins 3 semaines avec de l'activité parmi les 12 semaines qui précèdent la période, ou un objectif de course daté.",
  few_planned: "Pas assez de séances prévues : il en faut au moins 8, réparties sur 4 semaines, parmi les 12 dernières semaines terminées.",
  off: "Régularité masquée dans votre profil : rien n'est calculé. Vous pouvez la réactiver dans Profil, rubrique Statistiques.",
  no_run: "Aucune sortie de course exploitable ces 8 dernières semaines (au moins 3 km, allure plausible, peu de dénivelé, pas un simple footing).",
  no_reference: "Pas de référence : ajoutez un objectif de performance daté, ou courez de nouveau assez longtemps pour qu'une estimation plus ancienne existe.",
  few_lifts: "Il faut au moins 2 exercices de référence (développé couché, squat, rowing…) avec des séries chargées de 1 à 10 répétitions dans chacune des deux périodes de 12 semaines.",
};

const stSigned = (n) => (n > 0 ? `+${n}` : n < 0 ? `−${Math.abs(n)}` : "0");
const stDot = (iso) => stShort(iso).replace(/\.$/, "");  // « 18 oct. » : le point de l'abréviation ne doit pas doubler celui de la phrase
const stPeriod = (n) => (n && n.from ? __("Période : du {from} au {to}.", { from: stDot(n.from), to: stDot(n.to) }) : null);

// Valeur brute, référence et période d'un axe sous forme de texte (utilisés par la carte de l'axe et par le tableau).
function radarFacts(a, n) {
  if (a.id === "volume") {
    const u = a.unit;
    return { value: __("{value} {u} par semaine en moyenne ({weeks}).", { value: stN(n.value), u, weeks: n.weeks.map((x) => stN(x)).join(" / ") }),
      reference: n.reference_kind === "goal" ? __("{value} {u} par semaine : repère de volume du plan pour votre objectif.", { value: stN(n.reference), u })
        : __("{value} {u} : votre meilleure semaine des 12 semaines précédentes.", { value: stN(n.reference), u }), period: stPeriod(n) };
  }
  if (a.id === "regularity") {
    return { value: __("{done} séances faites sur {planned} prévues.", { done: n.done, planned: n.planned }), reference: "Toutes les séances prévues faites.", period: stPeriod(n) };
  }
  if (a.id === "endurance") {
    const src = { time: n.time, km: stN(n.to_km), from_km: stN(n.from_km), from_time: n.from_time, day: stDot(n.day) };
    return { value: n.kind === "estimate" ? __("Temps équivalent {time} sur {km} km, d'après {from_km} km en {from_time} le {day}.", src)
      : __("Au plus {time} sur {km} km, d'après {from_km} km en {from_time} le {day} (sans fréquence cardiaque, la sortie prouve seulement que vous courez au moins à cette allure).", src),
    reference: n.reference_kind === "goal" ? __("Votre objectif : {time} sur {km} km.", { time: n.reference_time, km: stN(n.to_km) })
      : __("Votre meilleure estimation antérieure : {time} sur {km} km, le {day}.", { time: n.reference_time, km: stN(n.to_km), day: stDot(n.reference_day) }),
    period: "Période : les 8 dernières semaines." };
  }
  return { value: n.lifts.map((x) => __("{label} : ≈ {now} kg", { label: x.label, now: stN(x.e1rm) })).join(" ; "),
    reference: n.lifts.map((x) => __("{label} : ≈ {ref} kg ({score} %)", { label: x.label, ref: stN(x.reference), score: x.score })).join(" ; "), period: "Période : les 12 dernières semaines contre les 12 précédentes." };
}

// Ce qu'il faut saisir, axe par axe, pour que l'araignée apparaisse (moins de 3 axes mesurés).
const RADAR_TODO = {
  volume: "Volume : synchronisez votre montre Garmin ou saisissez vos sorties pendant au moins 3 semaines, ou ajoutez un objectif de course daté.",
  regularity: "Régularité : générez un plan et marquez vos séances comme faites (8 séances prévues sur 4 semaines au minimum).",
  endurance: "Endurance : une sortie de course d'au moins 3 km mesurée par la montre, et un objectif de performance daté comme référence.",
  strength: "Force : saisissez les charges et répétitions (1 à 10) d'au moins 2 exercices dans vos séances de musculation, sur deux périodes de 12 semaines.",
};

function radarHowTo(axes, n) {
  const todo = axes.filter((a) => a.status !== "ok" && RADAR_TODO[a.id]);
  return h("div", { class: "stack" },
    h("p", null, __("Il faut au moins 3 axes mesurés pour tracer la forme ; {n} pour l'instant.", { n })),
    h("p", { class: "st-note" }, "Pour faire apparaître l'araignée, complétez :"),
    h("ul", { class: "st-note" }, todo.map((a) => h("li", null, __(RADAR_TODO[a.id])))));
}

function radarChart(drawn, compare, label) {
  const W = 320, H = 290, cx = 160, cy = 145, R = 80, n = drawn.length;
  const ang = (i) => -Math.PI / 2 + (2 * Math.PI * i) / n;
  const pt = (i, pct, extra = 0) => [cx + Math.cos(ang(i)) * (R * pct / 100 + extra), cy + Math.sin(ang(i)) * (R * pct / 100 + extra)];
  const poly = (vals) => vals.map((v, i) => pt(i, v).map((x) => x.toFixed(1)).join(",")).join(" ");
  const svg = svgRoot(W, H, label);
  for (const p of [25, 50, 75, 100]) svg.append(svgEl("polygon", { class: "st-ring", points: poly(drawn.map(() => p)) }));
  drawn.forEach((_, i) => { const [x, y] = pt(i, 100); svg.append(svgEl("line", { class: "st-spoke", x1: cx, y1: cy, x2: x, y2: y })); });
  svg.append(svgEl("text", { class: "st-text", x: cx + 3, y: cy - R / 2 - 2 }, "50 %"), svgEl("text", { class: "st-text", x: cx + 3, y: cy - R - 2 }, "100 %"));
  if (compare) svg.append(svgEl("polygon", { class: "st-area-before", points: poly(drawn.map((a) => a.before.score)) }));
  svg.append(svgEl("polygon", { class: "st-area", points: poly(drawn.map((a) => a.now.score)) }));
  drawn.forEach((a, i) => {
    const [x, y] = pt(i, a.now.score);
    svg.append(svgEl("circle", { class: "st-point", cx: x, cy: y, r: 3.5 }));
    const [lx, ly] = pt(i, 100, 14), c = Math.cos(ang(i)), s = Math.sin(ang(i));
    const anchor = c > 0.3 ? "start" : c < -0.3 ? "end" : "middle", ny = ly + (s < -0.5 ? -11 : s > 0.5 ? 8 : -1);
    svg.append(svgEl("text", { class: "st-text strong", x: lx, y: ny, "text-anchor": anchor }, __(RADAR_TEXT[a.id].name)),
      svgEl("text", { class: "st-val", x: lx, y: ny + 11, "text-anchor": anchor }, `${a.now.score} %`));
  });
  return svg;
}

function radarAxisCard(a, weeks) {
  const t = RADAR_TEXT[a.id], name = __(t.name);
  const info = [h("p", { class: "st-note" }, t.def), h("p", { class: "st-note" }, t.source), h("p", { class: "st-note" }, t.range)];
  if (a.status !== "ok") return stCard(name, h("p", { class: "muted" }, __("Axe non tracé. {reason}", { reason: __(RADAR_REASONS[a.reason]) })), ...info);
  const f = radarFacts(a, a.now), s = a.now.score;
  const before = a.before ? [__("Il y a {n} semaines : {score} %.", { n: weeks, score: a.before.score }), a.delta === 0 ? __("Aucun écart avec maintenant.") : __("Écart avec maintenant : {d} points.", { d: stSigned(a.delta) })].join(" ")
    : __("Il y a {n} semaines : pas assez de données pour cet axe.", { n: weeks });
  return stCard(name,
    h("p", null, h("span", { class: "st-big" }, `${s} %`), h("span", { class: "st-unit" }, "de votre référence")),
    h("div", { class: "st-meter", role: "img", "aria-label": __("{name} : {score} % de la référence", { name, score: s }) }, h("i", { style: `width:${s}%` })),
    h("p", null, h("strong", null, "Valeur : "), f.value), h("p", null, h("strong", null, "Référence : "), f.reference), f.period ? h("p", { class: "muted" }, f.period) : null,
    h("p", { class: "muted" }, before), ...info);
}

function radarTableRows(axes, weeks) {
  return axes.map((a) => {
    const name = __(RADAR_TEXT[a.id].name);
    if (a.status !== "ok") return [name, "–", "–", __("Non tracé : {reason}", { reason: __(RADAR_REASONS[a.reason]) }), "–"];
    const f = radarFacts(a, a.now);
    return [name, `${a.now.score} %`, a.before ? `${a.before.score} %` : "–", f.value, f.reference];
  });
}

function radarLabel(d, drawn) {
  const weeks = d.compare_weeks;
  return __("Forme sur {n} axes, en pourcentage de votre référence : {values}.", { n: drawn.length,
    values: drawn.map((a) => `${__(RADAR_TEXT[a.id].name)} ${a.now.score} %${d.compare ? __(" (il y a {n} semaines : {score} %)", { n: weeks, score: a.before.score }) : ""}`).join(", ") });
}

// Rubrique « Ma forme » de l'écran Profil : même rendu que la section Forme des Statistiques, avec un lien vers le détail.
function radarProfileCard() {
  const box = h("div", { class: "stack" }, h("p", { class: "muted" }, "Chargement…"));
  api(`/users/${userId}/stats/radar`).then((d) => {
    const drawn = d.axes.filter((a) => a.status === "ok");
    box.replaceChildren(d.chart ? radarChart(drawn, d.compare, radarLabel(d, drawn)) : radarHowTo(d.axes, drawn.length),
      ...(d.chart ? [stLegend(["", "maintenant"], ...(d.compare ? [["before", __("il y a {n} semaines", { n: d.compare_weeks })]] : []))] : []),
      h("button", { class: "btn sm", onclick: () => statsScreen("radar") }, "Voir le détail dans Statistiques"));
  }).catch(() => box.replaceChildren(h("p", { class: "muted" }, "Forme indisponible pour l'instant.")));
  return fold("profile-radar", "Statistiques", "Ma forme", null, box, true);
}

async function renderRadar(box) {
  const d = await api(`/users/${userId}/stats/radar`);
  const drawn = d.axes.filter((a) => a.status === "ok"), weeks = d.compare_weeks;
  const label = radarLabel(d, drawn);
  const head = ["Axe", "Maintenant", __("Il y a {n} semaines", { n: weeks }), "Valeur", "Référence"];
  const intro = stCard("Forme",
    h("p", { class: "muted" }, "Chaque axe compare une mesure à votre propre référence : 100 % veut dire référence atteinte ou dépassée. Aucune comparaison avec d'autres personnes, aucun score global."),
    d.chart ? radarChart(drawn, d.compare, label) : radarHowTo(d.axes, drawn.length),
    d.chart ? stLegend(["", "maintenant"], ...(d.compare ? [["before", __("il y a {n} semaines", { n: weeks })]] : [])) : null,
    d.chart && !d.compare ? h("p", { class: "st-note" }, __("La forme d'il y a {n} semaines n'est pas tracée : tous les axes n'ont pas de valeur à cette date. Les écarts sont donnés axe par axe.", { n: weeks })) : null,
    valuesTable("Axes de la forme", head, radarTableRows(d.axes, weeks)));
  const missing = stCard("Vitesse et récupération : non tracées",
    h("p", null, "Aucune mesure validée ne représente la vitesse ni la récupération aujourd'hui. La fréquence cardiaque au repos et l'état d'entraînement de la montre n'ont pas de correspondance publiée avec une échelle."),
    h("p", { class: "st-note" }, "Elles s'ajouteront quand une définition publiée existera : un axe tracé sans mesure serait une invention."));
  box.replaceChildren(intro, ...d.axes.map((a) => radarAxisCard(a, weeks)), missing);
}


// ---------- section « Muscles » et schéma d'une séance (règles ST21 à ST24) ----------

// Silhouette dessinée pour ce projet (aucune image tierce). Chaque tracé décrit la moitié gauche de l'image ; l'autre moitié est son miroir autour de x = 50.
const BODY = {
  front: { traps: ["M50 27 L50 37 L38 39 Q40 32 47 28 Z"], chest: ["M50 38 L50 62 Q40 66 31 58 Q28 48 33 40 Q42 36 50 38 Z"],
    shoulders: ["M33 39 Q25 35 20 43 Q17 50 20 57 L28 58 Q30 48 33 39 Z"], biceps: ["M20 59 L28 60 L27 78 L19 77 Q17 68 20 59 Z"],
    forearms: ["M19 80 L27 81 L24 106 L16 104 Q16 91 19 80 Z"], abs: ["M50 64 L50 96 Q42 97 39 94 Q37 80 38 66 Q44 68 50 64 Z"],
    quadriceps: ["M36 106 L45 112 Q46 130 47 149 L41 153 Q35 150 33 138 Q32 118 36 106 Z"], adductors: ["M45 112 L50 106 L50 138 L47 149 Q46 130 45 112 Z"],
    calves: ["M36 157 L45 157 Q47 174 43 192 L38 192 Q34 174 36 157 Z"] },
  back: { traps: ["M50 27 Q42 32 33 40 Q38 50 50 58 Z"], shoulders: ["M33 39 Q25 35 20 43 Q17 50 20 57 L28 58 Q30 48 33 39 Z"],
    triceps: ["M20 59 L28 60 L27 78 L19 77 Q17 68 20 59 Z"], forearms: ["M19 80 L27 81 L24 106 L16 104 Q16 91 19 80 Z"],
    lats: ["M33 48 Q31 66 38 86 L50 88 L50 74 Q40 72 36 62 Q35 54 33 48 Z"], middle_back: ["M50 56 L50 76 Q43 74 39 66 Q40 60 50 56 Z"],
    lower_back: ["M50 88 L50 104 Q42 104 38 100 Q38 92 41 88 Z"], glutes: ["M50 104 Q40 100 34 106 Q31 118 36 124 Q46 126 50 120 Z"],
    hamstrings: ["M35 126 Q32 138 34 150 L47 150 Q49 138 48 126 Q42 128 35 126 Z"], calves: ["M36 156 Q33 168 37 184 L44 190 Q47 172 46 156 Z"] },
};
const BODY_FILL = "M33 40 L28 60 L33 96 L36 106 L50 106 L50 38 Z"; // tronc : fond neutre derrière les muscles
const MU_LEVEL = { 0: "", 1: "mu-2nd", 2: "mu-main" };

function muscleFigure(rows, label) {
  const level = Object.fromEntries(rows.map((r) => [r.group, r.level]));
  const svg = svgEl("svg", { viewBox: "0 0 232 206", class: "mu-fig", role: "img", "aria-label": label });
  [["front", 0, "Face"], ["back", 124, "Dos"]].forEach(([side, dx, name]) => {
    const g = svgEl("g", { transform: `translate(${dx} 0)` });
    const half = (fn) => { fn(g, ""); fn(g, "translate(100 0) scale(-1 1)"); };
    half((root, tf) => { const p = svgEl("path", { class: "mu-body", d: BODY_FILL, transform: tf || null }); root.append(p);
      root.append(svgEl("ellipse", { class: "mu-body", cx: 20, cy: 108, rx: 4, ry: 6, transform: tf || null })); });
    g.append(svgEl("circle", { class: "mu-body", cx: 50, cy: 14, r: 10 }));
    for (const [grp, paths] of Object.entries(BODY[side])) {
      half((root, tf) => paths.forEach((d) => root.append(svgEl("path", { class: `mu ${MU_LEVEL[level[grp] || 0]}`.trim(), d, transform: tf || null, "data-group": grp }))));
    }
    g.append(svgEl("text", { class: "st-text", x: 50, y: 204, "text-anchor": "middle" }, __(name)));
    svg.append(g);
  });
  return svg;
}

const MU_FLAGS = { push_heavy: "Beaucoup plus de poussée que de tirage : à surveiller (pensez aux tirages et à l'arrière des épaules).",
  pull_heavy: "Beaucoup plus de tirage que de poussée : à surveiller.", legs_low: "Peu de travail des jambes par rapport au reste : à surveiller.",
  core_low: "Peu de travail du tronc (abdominaux, bas du dos) : à surveiller." };

function muscleLabel(d) {
  const names = (lvl) => d.rows.filter((r) => r.level === lvl).map((r) => r.label).join(", ");
  const main = names(2), second = names(1);
  return __("Schéma des muscles, face et dos. Principaux : {main}. Secondaires : {second}.", { main: main || __("aucun"), second: second || __("aucun") });
}

function muscleBody(d) {
  const family = (f) => stFmt(d.balance.families[f], 1);
  return [
    h("div", { class: "mu-wrap" }, muscleFigure(d.rows, muscleLabel(d))),
    h("div", { class: "st-legend" }, h("span", null, h("i", { class: "mu-key mu-main" }), "principal (fort)"), h("span", null, h("i", { class: "mu-key mu-2nd" }), "secondaire (clair)"),
      h("span", null, h("i", { class: "mu-key" }), "non sollicité")),
    h("p", { class: "muted" }, __("Séries pondérées : poussée {push}, tirage {pull}, jambes {legs}, tronc {core}.", { push: family("push"), pull: family("pull"), legs: family("legs"), core: family("core") })),
    d.balance.flags.length ? h("ul", { class: "plain" }, d.balance.flags.map((f) => h("li", null, MU_FLAGS[f]))) : null,
    d.unknown.length ? h("p", { class: "muted" }, __("Sans muscle connu dans la bibliothèque (non comptés) : {names}.", { names: d.unknown.join(", ") })) : null,
    valuesTable("Séries pondérées par groupe musculaire", ["Groupe", "Séries pondérées", "Séries principales", "Niveau"],
      d.rows.map((r) => [r.label, stFmt(r.sets, 1), stFmt(r.primary_sets, 1), ["non sollicité", "secondaire", "principal"][r.level]])),
    h("p", { class: "st-note" }, "Convention de comptage : une série vaut 1 pour chaque muscle principal de l'exercice et 0,5 pour chaque muscle secondaire. Ce n'est pas une mesure physiologique, seulement un repère de ce que vous avez saisi. Les repères d'équilibre sont indicatifs, jamais un avis médical.")];
}

// Carte de la fiche d'une séance faite : schéma pour la force, message clair pour le reste. `refresh()` relit le serveur après chaque enregistrement de la saisie.
function muscleSessionCard(s) {
  const head = () => h("h3", null, "Muscles travaillés");
  const box = h("div", { class: "card stack", "aria-live": "polite" }, head(), h("p", { class: "muted" }, "Chargement…"));
  box.refresh = () => api(`/users/${userId}/plan/sessions/${s.id}/muscles`).then((d) => {
    if (!d.supported) box.replaceChildren(head(), h("p", { class: "muted" }, "Pas de schéma musculaire pour la course, le vélo, la natation, la marche ni le CrossFit : seule la musculation avec exercices saisis est détaillée."));
    else if (!d.sets_counted) box.replaceChildren(head(), h("p", { class: "muted" }, d.unknown.length ? __("Aucun exercice saisi n'a de muscle connu dans la bibliothèque : {names}.", { names: d.unknown.join(", ") })
      : "Saisissez des séries (répétitions) pour voir les muscles travaillés."));
    else box.replaceChildren(head(), ...muscleBody(d));
  }).catch((e) => { if (!e.handled) box.replaceChildren(head(), h("p", { class: "muted" }, e.message || "Indisponible.")); });
  box.refresh();
  return box;
}

let muscleWeek = null;
async function renderMuscles(box) {
  const d = await api(`/users/${userId}/stats/muscles${muscleWeek ? `?week=${muscleWeek}` : ""}`);
  const shift = (days) => { const t = new Date(d.week_start + "T12:00:00"); t.setDate(t.getDate() + days); muscleWeek = t.toISOString().slice(0, 10); return renderMuscles(box); };
  const range = `${stShort(d.week_start)} – ${stShort(d.week_end)}`;
  const nav = h("div", { class: "row" }, h("button", { type: "button", class: "btn sm", onclick: () => shift(-7) }, "Semaine précédente"), h("strong", { class: "grow", style: "text-align:center" }, range),
    h("button", { type: "button", class: "btn sm", disabled: d.current, onclick: () => shift(7) }, "Semaine suivante"));
  const body = !d.sessions ? h("p", { class: "muted" }, "Aucune séance de musculation faite cette semaine-là : rien à afficher.")
    : [d.current ? h("p", { class: "muted" }, "Semaine en cours, incomplète.") : null, ...muscleBody(d)];
  box.replaceChildren(stCard("Muscles de la semaine", nav, body));
}


// ---------- courbes d'une séance reliée à une activité (règles ST25 à ST28) ----------

const cvClock = (s) => { const m = Math.floor(s / 60), h = Math.floor(m / 60); return h ? `${h}:${String(m % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}` : `${m}:${String(s % 60).padStart(2, "0")}`; };
const cvPercentile = (vals, p) => { const a = vals.slice().sort((x, y) => x - y); return a[Math.min(a.length - 1, Math.max(0, Math.round(p * (a.length - 1))))]; };

// Courbe d'une série mesurée au fil du temps : un trou d'enregistrement (pause) coupe le trait au lieu d'être comblé ; `bands` = bandes de zones de FC.
function curveChart({ t, y, label, fmt, bands, invert, area }) {
  const W = 320, H = 124, PL = 36, PR = 6, PT = 8, PB = 20;
  const vals = y.filter((v) => v != null);
  const clip = invert || area ? [cvPercentile(vals, invert ? 0.03 : 0), cvPercentile(vals, invert ? 0.97 : 1)] : [Math.min(...vals), Math.max(...vals)];
  let lo = clip[0], hi = clip[1];
  if (bands) { lo = Math.min(lo, bands.edges[0]); hi = Math.max(hi, bands.edges[3]); }
  const pad = (hi - lo || 1) * 0.06;
  lo -= pad; hi += pad;
  const end = t[t.length - 1] || 1;
  const x = (s) => PL + (W - PL - PR) * (s / end);
  const yy = (v) => { const c = Math.min(hi, Math.max(lo, v)), r = (c - lo) / (hi - lo); return PT + (H - PT - PB) * (invert ? r : 1 - r); };
  const svg = svgRoot(W, H, label);
  if (bands) {
    const edges = [lo, ...bands.edges, hi].map((v) => Math.min(hi, Math.max(lo, v)));
    for (let i = 0; i < 5; i++) {
      const a = yy(edges[i + 1]), b = yy(edges[i]);
      if (b - a > 0.5) svg.append(svgEl("rect", { class: `cv-band cv-z${i}`, x: PL, y: a, width: W - PL - PR, height: b - a }), svgEl("text", { class: "st-text cv-zl", x: PL + 3, y: a + 9, "text-anchor": "start" }, `Z${i + 1}`));
    }
  }
  svg.append(svgEl("line", { class: "st-base", x1: PL, x2: W - PR, y1: H - PB, y2: H - PB }));
  [lo + pad, (lo + hi) / 2, hi - pad].forEach((v) => svg.append(svgEl("text", { class: "st-text", x: PL - 4, y: yy(v) + 3, "text-anchor": "end" }, fmt(v))));
  [0, 0.5, 1].forEach((f, i) => svg.append(svgEl("text", { class: "st-text", x: x(end * f), y: H - 6, "text-anchor": i === 0 ? "start" : i === 2 ? "end" : "middle" }, cvClock(Math.round(end * f)))));
  const steps = t.slice(1).map((v, i) => v - t[i]).sort((a, b) => a - b), gap = Math.max(30, (steps[Math.floor(steps.length / 2)] || 1) * 2.5);
  let d = "", prev = null;
  t.forEach((s, i) => {
    if (y[i] == null) { prev = null; return; }
    d += `${prev == null || s - prev > gap ? "M" : "L"}${x(s).toFixed(1)} ${yy(y[i]).toFixed(1)} `;
    prev = s;
  });
  if (area) svg.append(svgEl("path", { class: "cv-area", d: `${d} L${x(t[t.length - 1]).toFixed(1)} ${H - PB} L${x(t[0]).toFixed(1)} ${H - PB} Z` }));
  svg.append(svgEl("path", { class: "st-line", d: d.trim() }));
  return svg;
}

// Le tableau reprend la courbe en une vingtaine de lignes régulières : l'alternative texte du graphique.
function curveTable(caption, head, t, y, fmt) {
  const idx = Array.from({ length: Math.min(20, t.length) }, (_, i) => Math.round((i * (t.length - 1)) / Math.max(1, Math.min(20, t.length) - 1)));
  return valuesTable(caption, head, idx.map((i) => [cvClock(t[i]), y[i] == null ? "–" : fmt(y[i])]));
}

const cvSeries = (d) => {
  const run = d.sport === "run" || d.sport === "walk";
  const out = [];
  if (d.hr) out.push({ key: "hr", title: "Fréquence cardiaque", unit: "bpm", y: d.hr, fmt: (v) => String(Math.round(v)), bands: d.zones });
  if (d.speed) {
    out.push(run ? { key: "pace", title: "Allure", unit: "/km", y: d.speed.map((v) => (v != null && v > 0.3 ? 1000 / v / 60 : null)), fmt: (v) => stPace(v), invert: true }
      : { key: "speed", title: "Vitesse", unit: "km/h", y: d.speed.map((v) => (v == null ? null : v * 3.6)), fmt: (v) => stFmt(v, 1) });
  }
  if (d.alt) out.push({ key: "alt", title: "Altitude", unit: "m", y: d.alt, fmt: (v) => stFmt(v, 0), area: true });
  if (d.cad) out.push({ key: "cad", title: "Cadence", unit: run ? "pas/min" : "tr/min", y: d.cad, fmt: (v) => String(Math.round(v)) });
  if (d.power) out.push({ key: "power", title: "Puissance", unit: "W", y: d.power, fmt: (v) => String(Math.round(v)) });
  return out;
};

function zonesBlock(z) {
  if (!z) return h("p", { class: "muted" }, "Pas de bandes de zones : indiquez votre FC max dans votre profil (ou faites quelques sorties mesurées par la montre).");
  const total = z.seconds.reduce((a, b) => a + b, 0) || 1;
  const rows = z.names.map((n, i) => [n, [`${i ? z.edges[i - 1] : 0}`, i < 4 ? `${z.edges[i]}` : "+"].join("–").replace("–+", "+"), cvClock(z.seconds[i]), `${Math.round((z.seconds[i] / total) * 100)} %`]);
  return h("div", { class: "stack" }, h("div", { class: "cv-zbar", role: "img", "aria-label": __("Temps par zone de FC : {list}.", { list: rows.map((r) => `${r[0]} ${r[3]}`).join(", ") }) },
    z.seconds.map((s, i) => h("i", { class: `cv-z${i}`, style: `flex:${s || 0}` }))),
  valuesTable("Temps par zone de fréquence cardiaque", ["Zone", "bpm", "Temps", "Part"], rows),
  h("p", { class: "st-note" }, z.basis === "declared" ? __("Zones calculées sur votre FC max déclarée ({hr} bpm) : 60-75 % et 85-92 % comme dans votre plan, les autres bornes sont une convention.", { hr: z.hr_max })
    : __("Zones calculées sur la plus haute FC mesurée par votre montre ({hr} bpm, estimation) : 60-75 % et 85-92 % comme dans votre plan, les autres bornes sont une convention.", { hr: z.hr_max })));
}

function splitsBlock(d) {
  const run = d.sport === "run" || d.sport === "walk";
  const sp = d.splits.laps.length >= 2 ? [["Tours de la montre", d.splits.laps]] : [];
  if (d.splits.km.length) sp.push(["Kilomètres", d.splits.km]);
  return sp.map(([title, rows]) => h("details", { class: "st-table", open: title === "Kilomètres" || null }, h("summary", null, title),
    h("table", null, h("caption", null, title === "Kilomètres" ? "Temps et FC par kilomètre" : "Temps et FC par tour"),
      h("thead", null, h("tr", null, ["N°", "Distance", "Durée", run ? "Allure" : "Vitesse", "FC"].map((c) => h("th", { scope: "col" }, c)))),
      h("tbody", null, rows.map((r) => h("tr", null, h("th", { scope: "row" }, String(r.i)), h("td", null, r.dist_m ? `${stFmt(r.dist_m / 1000, 2)} km` : "–"), h("td", null, cvClock(r.dur_s)),
        h("td", null, r.dist_m && r.dur_s ? (run ? `${stPace(r.dur_s / (r.dist_m / 1000) / 60)} /km` : `${stFmt((r.dist_m / r.dur_s) * 3.6, 1)} km/h`) : "–"), h("td", null, r.hr ? String(r.hr) : "–")))))));
}

function summaryBlock(s) {
  const pl = s.planned, dn = s.done, num = (v, unit) => (v == null ? "–" : `${stFmt(v, Number.isInteger(v) ? 0 : 1)}${unit}`);
  const rows = [["Durée", pl ? num(pl.minutes, " min") : "–", num(dn.minutes, " min")], ["Distance", pl ? num(pl.distance_km, " km") : "–", num(dn.distance_km, " km")],
    ["Allure moyenne", "–", dn.pace_s_km ? `${stPace(dn.pace_s_km / 60)} /km` : "–"], ["FC moyenne", "–", num(dn.avg_hr, " bpm")], ["FC max", "–", num(dn.max_hr, " bpm")], ["Dénivelé positif", "–", num(dn.elevation_m, " m")]]
    .filter((r) => r[1] !== "–" || r[2] !== "–");
  return h("div", { class: "stack" }, h("table", { class: "cv-sum" }, h("caption", null, s.manual ? "Fait (séance ajoutée hors plan : rien n'était prévu)" : "Prévu et fait"),
    h("thead", null, h("tr", null, ["", "Prévu", "Fait"].map((c) => h("th", { scope: "col" }, c)))), h("tbody", null, rows.map((r) => h("tr", null, h("th", { scope: "row" }, r[0]), h("td", null, r[1]), h("td", null, r[2]))))),
  s.gap_minutes == null ? null : h("p", { class: "muted" }, s.gap_minutes === 0 ? "Durée identique à la prévision." : __("Écart de durée : {sign}{m} min par rapport au prévu.", { sign: s.gap_minutes > 0 ? "+" : "−", m: Math.abs(s.gap_minutes) })));
}

function curvesBody(d) {
  const charts = cvSeries(d).map((c) => {
    const label = __("{title} au fil de la séance, de {lo} à {hi} {unit}", { title: __(c.title), lo: c.fmt(Math.min(...c.y.filter((v) => v != null))), hi: c.fmt(Math.max(...c.y.filter((v) => v != null))), unit: __(c.unit) });
    return h("section", { class: "stack cv-chart", "aria-label": c.title }, h("h4", null, c.title, " ", h("span", { class: "muted" }, `(${__(c.unit)})`)),
      curveChart({ t: d.t, y: c.y, label, fmt: c.fmt, bands: c.bands, invert: c.invert, area: c.area }), curveTable(c.title, ["Temps", `${c.title} (${__(c.unit)})`], d.t, c.y, c.fmt));
  });
  return [summaryBlock(d.summary), ...charts, d.hr ? h("section", { class: "stack", "aria-label": "Zones de fréquence cardiaque" }, h("h4", null, "Zones de fréquence cardiaque"), zonesBlock(d.zones)) : null, ...splitsBlock(d),
    h("p", { class: "st-note" }, "Courbes simplifiées (une moyenne tous les quelques instants, 400 points au plus) : aucune position GPS n'est conservée ni affichée. Une mesure absente reste vide, une pause reste un trou. Repères indicatifs, jamais un avis médical.")];
}

// Carte « Courbes de la séance » de la fiche d'une séance reliée à une activité de la montre ou à un fichier importé.
function curvesSessionCard(s) {
  const head = () => h("h3", null, "Courbes de la séance");
  const box = h("div", { class: "card stack", "aria-live": "polite" }, head(), h("p", { class: "muted" }, "Chargement…"));
  const show = (d) => {
    if (d.available) { box.replaceChildren(head(), ...curvesBody(d)); return; }
    const kids = [head()];
    if (d.summary) kids.push(summaryBlock(d.summary));
    if (d.reason === "no_streams") {
      kids.push(h("p", { class: "muted" }, d.can_fetch ? "Cette activité n'a pas encore de courbes : elles se téléchargent à la demande depuis Garmin (fréquence cardiaque, allure, altitude…), sans position GPS."
        : "Pas de courbes pour cette activité : le fichier importé ne contient pas de mesures au fil du temps, ou l'activité vient d'une source qui n'en fournit pas."));
      if (d.can_fetch) {
        const err = h("p", { class: "error", role: "alert" });
        const btn = h("button", { class: "btn sm", style: "align-self:flex-start", onclick: async () => {
          btn.disabled = true; err.textContent = "";
          try { show(await api(`/users/${userId}/plan/sessions/${s.id}/curves/fetch`, { method: "POST" })); } catch (e) { btn.disabled = false; if (!e.handled) err.textContent = __(e.message); }
        } }, "Afficher les courbes");
        kids.push(btn, err);
      }
    }
    box.replaceChildren(...kids);
  };
  api(`/users/${userId}/plan/sessions/${s.id}/curves`).then(show).catch((e) => { if (!e.handled) box.replaceChildren(head(), h("p", { class: "muted" }, e.message || "Indisponible.")); });
  return box;
}

// ---------- écran ----------

// Sections de l'écran : [id, libellé, rendu, préférence]. Chaque lot en ajoute une ; une section à préférence disparaît quand l'utilisateur la désactive.
const STATS_SECTIONS = [["daily", "Quotidien", renderDaily], ["progress", "Progression", renderProgress], ["regularity", "Régularité", renderRegularity, "regularity"], ["radar", "Forme", renderRadar], ["muscles", "Muscles", renderMuscles]];

async function statsScreen(section) {
  let prefs = {};
  try { prefs = await api(`/users/${userId}/stats/preferences`); } catch (e) { if (e.handled) return; }  // sans réponse : tout reste affiché
  const sections = STATS_SECTIONS.filter((s) => !s[3] || prefs[s[3]] !== false);
  const cur = sections.find((s) => s[0] === (section || store.get("sc-stats-section"))) || sections[0];
  store.set("sc-stats-section", cur[0]);
  const box = h("div", { class: "stack", "aria-live": "polite" }, h("p", { class: "muted" }, "Chargement…"));
  const nav = sections.length > 1 ? h("div", { class: "st-seg", role: "group", "aria-label": "Section" }, sections.map(([id, name]) =>
    h("button", { type: "button", class: "chip", style: `border:0;cursor:pointer;opacity:${id === cur[0] ? 1 : 0.6};${id === cur[0] ? "outline:2px solid var(--accent)" : ""}`,
      pressed: id === cur[0], onclick: () => statsScreen(id) }, name))) : null;
  show(h("div", { class: "head" }, h("span", { class: "eyebrow" }, "Statistiques"), themeToggle()), h("h1", null, "Statistiques"), nav, box,
    h("p", { class: "st-note" }, "Chiffres calculés par le moteur à partir de vos données, jamais par une IA. Ce suivi ne remplace pas un avis médical."), tabbar("home"));
  try { await cur[2](box); } catch (e) { if (!e.handled) box.replaceChildren(h("p", { class: "error", role: "alert" }, e.message || "Statistiques indisponibles.")); }
}

function statsCard() {
  return h("div", { class: "card row" },
    h("div", { class: "grow stack" }, h("h3", null, "Statistiques"), h("p", { class: "muted" }, "Pas, repas, poids et séances en graphiques, calculés à partir de vos données.")),
    h("button", { class: "btn sm", onclick: () => statsScreen() }, "Voir"));
}

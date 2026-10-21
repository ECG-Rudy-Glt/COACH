"use strict";
/* Traduction de l'interface, sans framework ni étape de build.

   Les textes du code restent en français : le français est la langue source et sert de clé. Pour une autre langue, `t()` cherche la clé exacte
   dans le dictionnaire (`/i18n/<langue>.json`), puis les modèles à trous (« Dans {n} semaines ») ; un texte sans traduction reste en français.
   `h()`, `toast()` et les attributs d'accessibilité passent par `t()` : les tables de libellés et les textes venus du serveur sont donc traduits
   sans avoir à réécrire chaque appel. En français, `t()` rend le texte inchangé (sortie identique octet pour octet).
   Voir docs/i18n.md. */
(function (root) {
  const LOCALES = { fr: { tag: "fr-FR", name: "Français" }, en: { tag: "en-GB", name: "English" } };
  const state = { locale: "fr", exact: new Map(), patterns: [], cache: new Map() };

  function compile(dict) {
    state.exact = new Map();
    state.patterns = [];
    state.cache = new Map();
    for (const [fr, tr] of Object.entries(dict || {})) {
      if (typeof tr !== "string") continue;
      state.exact.set(fr, tr);
      if (!/\{\w+\}/.test(fr)) continue;
      const names = [];
      const src = fr.replace(/[.*+?^$()|[\]\\]/g, "\\$&").replace(/\{(\w+)\}/g, (_, n) => { names.push(n); return n === "v" ? "([\\s\\S]*?)" : /^num\d*$/.test(n) ? "(\\d+(?:[.,]\\d+)?)" : "([\\s\\S]+?)"; });  // {v} : suffixe facultatif (« s » du pluriel) ; {num}, {num2}… : un nombre seulement
      state.patterns.push({ re: new RegExp("^" + src + "$"), names, tr, size: fr.replace(/\{\w+\}/g, "").length });
    }
    state.patterns.sort((a, b) => b.size - a.size);  // le modèle le plus précis d'abord
  }

  function pattern(s) {
    for (const p of state.patterns) {
      const m = p.re.exec(s);
      if (m) return p.tr.replace(/\{(\w+)\}/g, (_, n) => { const i = p.names.indexOf(n); return i < 0 ? "" : lookup(m[i + 1]); });
    }
    return null;
  }

  /** Texte composé de plusieurs phrases ou segments (« a. b · c ») : chaque morceau connu est traduit, le reste reste tel quel. */
  function bySentence(s) {
    const parts = s.split(/([.!?;]\s+|\s·\s|\s—\s|\n+|,\s+|\s\+\s)/);
    if (parts.length < 3) return s;
    let out = "", changed = false;
    for (let i = 0; i < parts.length; i += 2) {
      const seg = parts[i], sep = parts[i + 1] || "";
      const punct = /^[.!?;]/.test(sep) ? sep[0] : "";
      let tr = state.exact.get(seg + punct) ?? pattern(seg + punct);
      if (tr == null) { tr = state.exact.get(seg) ?? pattern(seg); if (tr != null) tr += punct; }
      if (tr != null) changed = true;
      out += (tr != null ? tr : seg + punct) + sep.slice(punct.length);
    }
    return changed ? out : s;
  }

  function lookup(s) {
    const hit = state.exact.get(s);
    if (hit !== undefined) return hit;
    const cached = state.cache.get(s);
    if (cached !== undefined) return cached;
    const out = pattern(s) ?? bySentence(s);
    state.cache.set(s, out);
    return out;
  }

  const fill = (s, vars) => s.replace(/\{(\w+)\}/g, (all, n) => (vars[n] === undefined ? all : String(vars[n])));

  function t(s, vars) {
    if (typeof s !== "string" || s === "") return s;
    const out = state.locale === "fr" ? s : lookup(s);
    return vars ? fill(out, vars) : out;
  }

  function detect(stored, navigatorLanguages) {
    if (stored && LOCALES[stored]) return stored;
    for (const l of navigatorLanguages || []) {
      const short = String(l).toLowerCase().slice(0, 2);
      if (LOCALES[short]) return short;
    }
    return "en";  // langue de repli pour tout autre navigateur
  }

  /** Charge le dictionnaire d'une langue (`/i18n/<langue>.json`) ; en cas d'échec (hors ligne, fichier absent) l'interface reste en français. */
  async function load(locale) {
    if (!LOCALES[locale] || locale === "fr") return setLocale("fr");
    try {
      const res = await fetch(`/i18n/${locale}.json`);
      if (!res.ok) throw new Error(String(res.status));
      return setLocale(locale, await res.json());
    } catch { return setLocale("fr"); }
  }

  function setLocale(locale, dict) {
    state.locale = LOCALES[locale] ? locale : "fr";
    compile(state.locale === "fr" ? {} : dict);
    return state.locale;
  }

  const api = {
    LOCALES, t, detect, setLocale, compile, load,
    locale: () => state.locale,
    tag: () => LOCALES[state.locale].tag,
    /** Nom d'un jour de la semaine (0 = lundi) dans la langue courante : « lundi » / « Monday », ou la lettre seule (« L » / « M »). */
    weekday: (index, style = "long") => new Date(Date.UTC(2024, 0, 1 + index)).toLocaleDateString(LOCALES[state.locale].tag, { weekday: style, timeZone: "UTC" }),
  };
  root.I18N = api;
  root.t = t;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);

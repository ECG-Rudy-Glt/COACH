"""Historique Garmin au service du coach : repères compacts envoyés à chaque appel, et recherches à la demande (outils du chat).

Le LLM ne reçoit jamais la base : les repères sont calculés ici, et les outils ne rendent que des résultats bornés et validés.
"""
from datetime import date, timedelta
from typing import Any

from app.repo import Repo

MAIN = {"run", "bike", "strength"}
SERIES = {  # mesure -> (libellé, unité)
    "resting_hr": ("FC au repos", "bpm"), "vo2max": ("VO2max", "ml/kg/min"), "vo2max_cycling": ("VO2max vélo", "ml/kg/min"),
    "race_5k": ("Temps estimé 5 km", "s"), "race_10k": ("Temps estimé 10 km", "s"), "race_half": ("Temps estimé semi", "s"),
    "race_marathon": ("Temps estimé marathon", "s"), "acwr": ("Ratio charge aiguë/chronique", ""), "load_acute": ("Charge aiguë", ""),
    "load_chronic": ("Charge chronique", ""),
}
RACES = {"race_5k": "5 km", "race_10k": "10 km", "race_half": "semi", "race_marathon": "marathon"}
MAX_ROWS = 40


def fmt_time(s: float) -> str:
    s = int(round(s))
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def _at(rows: list[dict[str, Any]], target: date) -> dict[str, Any] | None:
    """Mesure la plus proche de `target` (à 20 jours près)."""
    near = min(rows, key=lambda r: abs((r["day"] - target).days), default=None)
    return near if near and abs((near["day"] - target).days) <= 20 else None


def _val(r: dict[str, Any] | None) -> dict[str, Any] | None:
    return {"valeur": round(r["value"], 1), "date": r["day"].isoformat()} if r else None


def fitness_digest(repo: Repo, user_id: int, today: date) -> dict[str, Any]:
    """Forme physique mesurée par la montre : VO2max, FC au repos, temps estimés, statut d'entraînement, FC max des sorties."""
    rows = repo.list_metrics(user_id, None, today - timedelta(days=760))
    by: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        if r["value"] is not None:
            by.setdefault(r["metric"], []).append(r)
    out: dict[str, Any] = {}
    if "vo2max" in by:
        v = by["vo2max"]
        out["vo2max"] = {"actuelle": _val(v[-1]), "il_y_a_6_mois": _val(_at(v, today - timedelta(days=182))), "il_y_a_12_mois": _val(_at(v, today - timedelta(days=365))),
                         "max_12_mois": _val(max((r for r in v if r["day"] >= today - timedelta(days=365)), key=lambda r: r["value"], default=None))}
    if "resting_hr" in by:
        h = by["resting_hr"]
        last12 = [r for r in h if r["day"] >= today - timedelta(days=365)]
        last6 = [r for r in h if r["day"] >= today - timedelta(days=182)]
        last30 = [r["value"] for r in h if r["day"] >= today - timedelta(days=30)]
        months: dict[str, list[float]] = {}
        for r in last12:
            months.setdefault(r["day"].strftime("%Y-%m"), []).append(r["value"])
        out["fc_repos"] = {"derniere": _val(h[-1]), "moyenne_30_jours": round(sum(last30) / len(last30)) if last30 else None,
                           "plus_bas_6_mois": _val(min(last6, key=lambda r: r["value"], default=None)),
                           "plus_bas_12_mois": _val(min(last12, key=lambda r: r["value"], default=None)),
                           "plus_haut_12_mois": _val(max(last12, key=lambda r: r["value"], default=None)),
                           "moyenne_par_mois": {m: round(sum(x) / len(x)) for m, x in sorted(months.items())}}
    pred = {name: by[key] for key, name in RACES.items() if key in by}
    if pred:
        def at(day: date) -> dict[str, str] | None:
            got = {n: _at(v, day) for n, v in pred.items()}
            return {n: fmt_time(r["value"]) for n, r in got.items() if r} or None
        out["temps_estimes_par_la_montre"] = {"actuels": {n: fmt_time(v[-1]["value"]) for n, v in pred.items()}, "il_y_a_6_mois": at(today - timedelta(days=182)),
                                              "il_y_a_12_mois": at(today - timedelta(days=365))}
    status = [r for r in rows if r["metric"] == "training_status"]
    if status:
        last_day = status[-1]["day"]
        cur = {r["metric"]: r for r in rows if r["day"] == last_day}
        out["statut_entrainement"] = {"jour": last_day.isoformat(), "statut": status[-1]["text"],
                                      "ratio_charge_aigue_chronique": round(cur["acwr"]["value"], 2) if "acwr" in cur else None,
                                      "charge_aigue": round(cur["load_acute"]["value"]) if "load_acute" in cur else None,
                                      "charge_chronique": round(cur["load_chronic"]["value"]) if "load_chronic" in cur else None,
                                      "equilibre_charge": (cur.get("load_balance") or {}).get("text")}
    acts = repo.list_activities(user_id, today - timedelta(days=365), 5000)
    hr = [a for a in acts if a.get("max_hr")]
    if hr:
        top6 = max((a for a in hr if a["day"] >= today - timedelta(days=182)), key=lambda a: a["max_hr"], default=None)
        top12 = max(hr, key=lambda a: a["max_hr"])
        out["fc_max_en_sortie"] = {"6_mois": {"bpm": top6["max_hr"], "date": top6["day"].isoformat()} if top6 else None,
                                   "12_mois": {"bpm": top12["max_hr"], "date": top12["day"].isoformat()}}
    return out


def _place(name: str | None) -> str | None:
    if not name:
        return None
    for tail in (" Randonnée", " Hiking", " Marche", " Course à pied", " Escalade", " Alpinisme", " Trail"):
        name = name.removesuffix(tail)
    return name.strip() or None


def episodes(acts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Périodes marquantes hors course/vélo/musculation (randonnée en altitude, alpinisme, escalade, camps…), regroupées par écarts de 3 jours."""
    other = sorted((a for a in acts if a["sport"] not in MAIN and not (a.get("type_key") or "").startswith("indoor")
                    and (a.get("type_key") or "") not in ("soccer", "pilates", "yoga", "multi_sport")), key=lambda a: a["day"])
    groups: list[list[dict[str, Any]]] = []
    for a in other:
        if groups and (a["day"] - groups[-1][-1]["day"]).days <= 3:
            groups[-1].append(a)
        else:
            groups.append([a])
    out = []
    for g in groups:
        dplus = sum(a["elevation_m"] or 0 for a in g)
        hours = sum(a["duration_s"] or 0 for a in g) / 3600
        if dplus < 400 and hours < 4:
            continue
        types: dict[str, int] = {}
        for a in g:
            types[a.get("type_key") or a["sport"]] = types.get(a.get("type_key") or a["sport"], 0) + 1
        places = list(dict.fromkeys(p for a in g if (p := _place(a.get("name")))))[:5]
        out.append({"periode": f'{g[0]["day"].isoformat()} → {g[-1]["day"].isoformat()}', "activites": len(g), "types": types, "heures": round(hours, 1),
                    "km": round(sum(a["distance_m"] or 0 for a in g) / 1000), "d_plus_m": round(dplus),
                    "fc_max": max((a["max_hr"] for a in g if a.get("max_hr")), default=None), "lieux": places})
    return sorted(out, key=lambda e: (e["d_plus_m"], e["heures"]), reverse=True)[:6]


def records(acts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Plus grosses sorties par sport : durée, distance, dénivelé."""
    out = []
    for sport in ("run", "bike", "walk"):
        sub = [a for a in acts if a["sport"] == sport]
        for key, label in (("duration_s", "plus longue"), ("distance_m", "plus longue distance"), ("elevation_m", "plus gros dénivelé")):
            best = max((a for a in sub if a.get(key)), key=lambda a: a[key], default=None)
            if best:
                out.append({"sport": sport, "record": label, "jour": best["day"].isoformat(), "min": round((best["duration_s"] or 0) / 60),
                            "km": round((best["distance_m"] or 0) / 1000, 1), "d_plus_m": round(best["elevation_m"] or 0), "nom": _place(best.get("name"))})
    return out


def past_digest(repo: Repo, user_id: int, today: date) -> dict[str, Any]:
    acts = repo.list_activities(user_id, today - timedelta(days=730), 5000)
    return {"forme": fitness_digest(repo, user_id, today), "episodes_marquants": episodes(acts), "plus_grosses_sorties": records(acts)} if acts else {}


# ---------- outils du chat : recherches bornées ----------
TOOLS = [
    {"name": "historique_mesure", "description": "Série d'une mesure de la montre sur une période (FC au repos, VO2max, temps estimés, charges). Rend min, max, moyenne par jour, semaine ou mois.",
     "input_schema": {"type": "object", "properties": {
         "mesure": {"type": "string", "enum": sorted(SERIES)}, "depuis": {"type": "string", "description": "AAAA-MM-JJ"},
         "jusqua": {"type": "string", "description": "AAAA-MM-JJ, par défaut aujourd'hui"}, "par": {"type": "string", "enum": ["jour", "semaine", "mois"]}},
         "required": ["mesure", "depuis"]}},
    {"name": "historique_activites", "description": "Recherche dans les activités de la montre (2 ans) : filtre par sport, type ou nom, tri par durée, distance, dénivelé, FC max ou date.",
     "input_schema": {"type": "object", "properties": {
         "sport": {"type": "string", "enum": ["run", "bike", "strength", "walk", "swim", "other"]}, "type_garmin": {"type": "string"},
         "nom_contient": {"type": "string"}, "depuis": {"type": "string"}, "jusqua": {"type": "string"},
         "tri": {"type": "string", "enum": ["duree", "distance", "d_plus", "fc_max", "date"]}, "limite": {"type": "integer", "minimum": 1, "maximum": 15}},
         "required": []}},
]


def _d(v: Any, default: date | None) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else default
    except ValueError:
        return default


def run_tool(repo: Repo, user_id: int, name: str, args: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    today = today or date.today()
    if name == "historique_mesure":
        metric = str(args.get("mesure"))
        if metric not in SERIES:
            return {"erreur": "mesure inconnue", "mesures": sorted(SERIES)}
        since = max(_d(args.get("depuis"), today - timedelta(days=365)) or today, today - timedelta(days=760))
        until = _d(args.get("jusqua"), today)
        rows = [r for r in repo.list_metrics(user_id, metric, since, until) if r["value"] is not None]
        if not rows:
            return {"mesure": SERIES[metric][0], "points": [], "note": "aucune donnée sur cette période"}
        step = args.get("par") if args.get("par") in ("jour", "semaine", "mois") else ("jour" if len(rows) <= 31 else "semaine" if len(rows) <= 180 else "mois")
        key = {"jour": lambda d: d.isoformat(), "semaine": lambda d: (d - timedelta(days=d.weekday())).isoformat(), "mois": lambda d: d.strftime("%Y-%m")}[step]
        buckets: dict[str, list[float]] = {}
        for r in rows:
            buckets.setdefault(key(r["day"]), []).append(r["value"])
        pts = [{"periode": k, "min": round(min(v), 1), "max": round(max(v), 1), "moy": round(sum(v) / len(v), 1), "n": len(v)} for k, v in sorted(buckets.items())]
        lo, hi = min(rows, key=lambda r: r["value"]), max(rows, key=lambda r: r["value"])
        return {"mesure": SERIES[metric][0], "unite": SERIES[metric][1], "par": step, "points": pts[-MAX_ROWS:], "plus_bas": _val(lo), "plus_haut": _val(hi),
                "moyenne": round(sum(r["value"] for r in rows) / len(rows), 1), "derniere": _val(rows[-1])}
    if name == "historique_activites":
        since = max(_d(args.get("depuis"), today - timedelta(days=730)) or today, today - timedelta(days=730))
        until = _d(args.get("jusqua"), today)
        acts = [a for a in repo.list_activities(user_id, since, 5000) if until is None or a["day"] <= until]
        if args.get("sport"):
            acts = [a for a in acts if a["sport"] == args["sport"]]
        if args.get("type_garmin"):
            acts = [a for a in acts if (a.get("type_key") or "") == str(args["type_garmin"]).lower()]
        if args.get("nom_contient"):
            q = str(args["nom_contient"]).lower()
            acts = [a for a in acts if q in (a.get("name") or "").lower()]
        sort = {"duree": "duration_s", "distance": "distance_m", "d_plus": "elevation_m", "fc_max": "max_hr"}.get(str(args.get("tri")))
        acts = sorted(acts, key=(lambda a: a.get(sort) or 0), reverse=True) if sort else sorted(acts, key=lambda a: a["day"], reverse=True)
        limit = max(1, min(int(args.get("limite") or 8), 15))
        return {"total": len(acts), "activites": [{"jour": a["day"].isoformat(), "sport": a["sport"], "type": a.get("type_key"), "nom": a.get("name"),
                                                  "min": round((a["duration_s"] or 0) / 60), "km": round((a["distance_m"] or 0) / 1000, 1), "d_plus_m": round(a["elevation_m"] or 0),
                                                  "fc_moy": a.get("avg_hr"), "fc_max": a.get("max_hr")} for a in acts[:limit]]}
    return {"erreur": "outil inconnu"}

from datetime import date, datetime, timedelta

from app.coach import history
from app.garmin.client import parse_predictions, parse_rhr, parse_status, parse_vo2
from app.repo import MemoryRepo

TODAY = date(2026, 10, 12)


def act(i, day, sport="run", type_key="running", name="Sortie", minutes=45, km=8.0, dplus=50.0, max_hr=170):
    return {"garmin_id": str(i), "day": day, "started_at": datetime(day.year, day.month, day.day, 8), "sport": sport, "type_key": type_key, "name": name,
            "duration_s": minutes * 60, "distance_m": km * 1000, "elevation_m": dplus, "avg_hr": 140, "max_hr": max_hr, "calories": 500, "training_load": 80.0}


def seeded():
    repo = MemoryRepo()
    uid = repo.create_user("r")
    mountain = [act(100 + i, date(2025, 7, 18) + timedelta(days=i), "walk", "hiking", "Vallouise-Pelvoux Randonnée", 280, 7.0, 1000, 160) for i in (0, 1, 2)]
    repo.upsert_activities(uid, [act(1, TODAY - timedelta(days=3), max_hr=190), act(2, TODAY - timedelta(days=300), minutes=95, km=17, max_hr=185),
                                 act(3, date(2025, 8, 1), "walk", "hiking", "Balade", 30, 2, 20), *mountain])
    rows = [{"day": TODAY - timedelta(days=d), "metric": "resting_hr", "value": 40.0 + (d % 9)} for d in range(0, 360, 3)]
    rows += [{"day": date(2025, 10, 12), "metric": "vo2max", "value": 57.5}, {"day": TODAY, "metric": "vo2max", "value": 51.6},
             {"day": date(2025, 10, 31), "metric": "race_5k", "value": 1237}, {"day": TODAY, "metric": "race_5k", "value": 1300},
             {"day": TODAY, "metric": "training_status", "value": 2, "text": "UNPRODUCTIVE_5"}, {"day": TODAY, "metric": "acwr", "value": 0.9}]
    repo.upsert_metrics(uid, rows)
    return repo, uid


def test_digest_gives_past_landmarks_the_llm_can_quote():
    repo, uid = seeded()
    d = history.past_digest(repo, uid, TODAY)
    f = d["forme"]
    assert f["vo2max"]["actuelle"]["valeur"] == 51.6 and f["vo2max"]["il_y_a_12_mois"]["valeur"] == 57.5
    assert f["fc_repos"]["plus_bas_12_mois"]["valeur"] == 40.0 and f["fc_repos"]["moyenne_par_mois"]
    assert f["fc_max_en_sortie"]["6_mois"]["bpm"] == 190
    assert f["temps_estimes_par_la_montre"]["actuels"]["5 km"] == "21:40" and f["temps_estimes_par_la_montre"]["il_y_a_12_mois"]["5 km"] == "20:37"
    assert f["statut_entrainement"]["statut"] == "UNPRODUCTIVE_5"
    ep = d["episodes_marquants"]
    assert len(ep) == 1 and ep[0]["d_plus_m"] == 3000 and ep[0]["lieux"] == ["Vallouise-Pelvoux"] and ep[0]["periode"].startswith("2025-07-18")  # la balade n'est pas un épisode
    assert any(r["sport"] == "run" and r["record"] == "plus longue" and r["km"] == 17.0 for r in d["plus_grosses_sorties"])


def test_tools_are_bounded_and_answer_with_dates():
    repo, uid = seeded()
    r = history.run_tool(repo, uid, "historique_mesure", {"mesure": "resting_hr", "depuis": "2026-04-12", "par": "mois"}, TODAY)
    assert r["plus_bas"]["valeur"] == 40.0 and r["points"] and len(r["points"]) <= history.MAX_ROWS and r["unite"] == "bpm"
    assert history.run_tool(repo, uid, "historique_mesure", {"mesure": "n_importe_quoi", "depuis": "2026-01-01"}, TODAY)["erreur"]
    a = history.run_tool(repo, uid, "historique_activites", {"sport": "walk", "tri": "d_plus", "limite": 99}, TODAY)
    assert a["total"] == 4 and a["activites"][0]["d_plus_m"] == 1000 and len(a["activites"]) <= 15
    assert history.run_tool(repo, uid, "historique_activites", {"nom_contient": "vallouise"}, TODAY)["total"] == 3
    assert history.run_tool(repo, uid, "supprimer_tout", {}, TODAY)["erreur"]


def test_garmin_payload_parsers_and_metric_pruning():
    rhr = parse_rhr({"allMetrics": {"metricsMap": {"WELLNESS_RESTING_HEART_RATE": [{"calendarDate": "2026-01-27", "value": 38.0}, {"calendarDate": "2026-01-28", "value": None}]}}})
    assert rhr == [{"day": date(2026, 1, 27), "metric": "resting_hr", "value": 38.0}]
    assert parse_vo2([{"generic": {"calendarDate": "2026-10-12", "vo2MaxPreciseValue": 51.6}, "cycling": None}])[0]["value"] == 51.6
    assert {r["metric"] for r in parse_predictions([{"calendarDate": "2026-10-12", "time5K": 1237, "time10K": 2685}])} == {"race_5k", "race_10k"}
    st = parse_status({"mostRecentTrainingStatus": {"latestTrainingStatusData": {"1": {"trainingStatusFeedbackPhrase": "PRODUCTIVE_1", "trainingStatus": 4,
                                                                                         "acuteTrainingLoadDTO": {"dailyAcuteChronicWorkloadRatio": 1.1}}}}}, TODAY)
    assert {r["metric"] for r in st} == {"training_status", "acwr"}
    repo, uid = seeded()
    repo.prune_activities(uid, TODAY - timedelta(days=100))
    assert all(m["day"] >= TODAY - timedelta(days=100) for m in repo.list_metrics(uid, None, date(2024, 1, 1)))  # la base ne grossit pas sans limite

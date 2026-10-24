"""Adaptateur Garmin (bibliothèque non officielle `garminconnect`). Isolé pour pouvoir être remplacé ou simulé."""
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

SPORTS = {
    "running": "run", "trail_running": "run", "treadmill_running": "run", "track_running": "run", "virtual_run": "run",
    "cycling": "bike", "road_biking": "bike", "mountain_biking": "bike", "gravel_cycling": "bike", "indoor_cycling": "bike",
    "strength_training": "strength", "fitness_equipment": "strength", "hiit": "strength", "cross_training": "strength", "crossfit": "strength", "indoor_cardio": "other",
    "lap_swimming": "swim", "open_water_swimming": "swim", "hiking": "walk", "walking": "walk",
}


class GarminAuthError(Exception):
    pass


class GarminRateLimited(Exception):
    pass


class GarminUnavailable(Exception):
    pass


@dataclass
class LoginResult:
    tokens: str | None = None  # jeton à chiffrer si la connexion est terminée
    mfa_handle: Any = None  # objet à conserver côté serveur pour reprendre après le code


def normalize(a: dict[str, Any]) -> dict[str, Any] | None:
    """Activité Garmin -> ligne compacte. Retourne None si inutilisable."""
    try:
        started = datetime.fromisoformat(str(a["startTimeLocal"]).replace(" ", "T")[:19])
    except (KeyError, ValueError):
        return None
    key = ((a.get("activityType") or {}).get("typeKey") or "").lower()

    def num(k: str, cast: Any = float) -> Any:
        v = a.get(k)
        return cast(v) if isinstance(v, int | float) and not isinstance(v, bool) else None

    return {
        "garmin_id": str(a.get("activityId")), "day": started.date(), "started_at": started,
        "sport": SPORTS.get(key, "other"), "type_key": key or None, "name": (a.get("activityName") or "")[:120] or None,
        "duration_s": num("duration", int), "distance_m": num("distance"), "elevation_m": num("elevationGain"),
        "avg_hr": num("averageHR", int), "max_hr": num("maxHR", int), "calories": num("calories", int),
        "training_load": num("activityTrainingLoad"),
    }


def _day(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _num(v: Any) -> float | None:
    return float(v) if isinstance(v, int | float) and not isinstance(v, bool) else None


def parse_rhr(resp: dict[str, Any]) -> list[dict[str, Any]]:
    pts = ((resp or {}).get("allMetrics") or {}).get("metricsMap", {}).get("WELLNESS_RESTING_HEART_RATE") or []
    return [{"day": d, "metric": "resting_hr", "value": v} for p in pts if (d := _day(p.get("calendarDate"))) and (v := _num(p.get("value")))]


def parse_steps(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pas par jour. Un total à 0 signifie presque toujours « montre non portée » : ce n'est pas enregistré (donnée absente plutôt que fausse)."""
    return [{"day": d, "metric": "steps", "value": v} for it in items or [] if isinstance(it, dict) and (d := _day(it.get("calendarDate"))) and (v := _num(it.get("totalSteps")))]


def fetch_steps(client: Any, start: date, end: date, errors: tuple[type[Exception], ...]) -> list[dict[str, Any]]:
    """Pas par tranches de 28 jours (limite de Garmin) ; une tranche en erreur n'efface pas celles déjà reçues."""
    rows: list[dict[str, Any]] = []
    cur = start
    while cur <= end:
        stop = min(cur + timedelta(days=27), end)
        try:
            rows += parse_steps(client.get_daily_steps(cur.isoformat(), stop.isoformat()))
        except errors:
            break
        cur = stop + timedelta(days=1)
        if cur <= end:
            time.sleep(0.5)
    return rows


def parse_vo2(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for it in items or []:
        for key, name in (("generic", "vo2max"), ("cycling", "vo2max_cycling")):
            blk = it.get(key) or {}
            d, v = _day(blk.get("calendarDate")), _num(blk.get("vo2MaxPreciseValue") or blk.get("vo2MaxValue"))
            if d and v:
                out.append({"day": d, "metric": name, "value": v})
    return out


def parse_predictions(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keys = {"time5K": "race_5k", "time10K": "race_10k", "timeHalfMarathon": "race_half", "timeMarathon": "race_marathon"}
    return [{"day": d, "metric": name, "value": v} for it in items or [] if (d := _day(it.get("calendarDate")))
            for k, name in keys.items() if (v := _num(it.get(k)))]


def parse_status(resp: dict[str, Any], day: date) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    latest = ((resp or {}).get("mostRecentTrainingStatus") or {}).get("latestTrainingStatusData") or {}
    st = next(iter(latest.values()), {}) if latest else {}
    if st.get("trainingStatusFeedbackPhrase"):
        out.append({"day": day, "metric": "training_status", "value": _num(st.get("trainingStatus")), "text": str(st["trainingStatusFeedbackPhrase"])[:40]})
    acute = st.get("acuteTrainingLoadDTO") or {}
    for key, name in (("dailyAcuteChronicWorkloadRatio", "acwr"), ("dailyTrainingLoadAcute", "load_acute"), ("dailyTrainingLoadChronic", "load_chronic")):
        if (v := _num(acute.get(key))) is not None:
            out.append({"day": day, "metric": name, "value": v})
    bal = next(iter(((resp or {}).get("mostRecentTrainingLoadBalance") or {}).get("metricsTrainingLoadBalanceDTOMap", {}).values()), {})
    for key, name in (("monthlyLoadAerobicLow", "load_aerobic_low"), ("monthlyLoadAerobicHigh", "load_aerobic_high"), ("monthlyLoadAnaerobic", "load_anaerobic")):
        if (v := _num(bal.get(key))) is not None:
            out.append({"day": day, "metric": name, "value": v})
    if bal.get("trainingBalanceFeedbackPhrase"):
        out.append({"day": day, "metric": "load_balance", "value": None, "text": str(bal["trainingBalanceFeedbackPhrase"])[:40]})
    return out


class GarminGateway:
    """Appels réels. Chaque méthode traduit les erreurs de la bibliothèque en erreurs métier."""

    def _lib(self) -> Any:
        import garminconnect as g
        return g

    def start_login(self, email: str, password: str) -> LoginResult:
        g = self._lib()
        client = g.Garmin(email, password, return_on_mfa=True)
        try:
            status, state = client.login()
        except g.GarminConnectAuthenticationError as e:
            raise GarminAuthError(str(e)) from e
        except g.GarminConnectTooManyRequestsError as e:
            raise GarminRateLimited(str(e)) from e
        except g.GarminConnectConnectionError as e:
            raise GarminUnavailable(str(e)) from e
        if status == "needs_mfa":
            return LoginResult(mfa_handle=(client, state))
        return LoginResult(tokens=client.client.dumps())

    def finish_mfa(self, handle: Any, code: str) -> LoginResult:
        g = self._lib()
        client, state = handle
        try:
            client.resume_login(state, code.strip())
        except g.GarminConnectAuthenticationError as e:
            raise GarminAuthError(str(e)) from e
        except g.GarminConnectTooManyRequestsError as e:
            raise GarminRateLimited(str(e)) from e
        except g.GarminConnectConnectionError as e:
            raise GarminUnavailable(str(e)) from e
        return LoginResult(tokens=client.client.dumps())

    def fetch_metrics(self, tokens: str, start: date, end: date, monthly_predictions: bool) -> tuple[list[dict[str, Any]], str]:
        """Mesures quotidiennes (FC au repos, pas, VO2max, temps estimés, statut d'entraînement). Une section en erreur n'empêche pas les autres."""
        g = self._lib()
        client = g.Garmin()
        rows: list[dict[str, Any]] = []
        try:
            client.login(tokenstore=tokens)
            name = client._require_display_name()
            cur = start
            while cur <= end:
                stop = min(cur + timedelta(days=364), end)
                a, b = cur.isoformat(), stop.isoformat()
                steps = (
                    lambda a=a, b=b: parse_rhr(client.connectapi(f"{client.garmin_connect_rhr_url}/{name}", params={"fromDate": a, "untilDate": b, "metricId": 60})),
                    lambda a=a, b=b: parse_vo2(client.connectapi(f"{client.garmin_connect_metrics_url}/{a}/{b}")),
                    lambda a=a, b=b: parse_predictions(client.get_race_predictions(a, b, "monthly" if monthly_predictions else "daily")),
                    lambda cur=cur, stop=stop: fetch_steps(client, cur, stop, (g.GarminConnectConnectionError, g.GarminConnectTooManyRequestsError, KeyError, ValueError, TypeError)),
                )
                for step in steps:
                    try:
                        rows += step()
                    except (g.GarminConnectConnectionError, g.GarminConnectTooManyRequestsError, KeyError, ValueError, TypeError):
                        continue
                    time.sleep(0.5)
                cur = stop + timedelta(days=1)
            try:
                rows += parse_status(client.get_training_status(end.isoformat()), end)
            except (g.GarminConnectConnectionError, g.GarminConnectTooManyRequestsError, KeyError, ValueError, TypeError):
                pass
        except g.GarminConnectAuthenticationError as e:
            raise GarminAuthError(str(e)) from e
        return rows, client.client.dumps()

    def download_activity_tcx(self, tokens: str, garmin_id: str) -> tuple[bytes, str]:
        """Fichier TCX d'une activité (détail à la demande) : l'appelant en extrait les courbes et n'en garde ni les positions ni le fichier."""
        g = self._lib()
        client = g.Garmin()
        try:
            client.login(tokenstore=tokens)
            raw = client.download_activity(garmin_id, dl_fmt=g.Garmin.ActivityDownloadFormat.TCX)
        except g.GarminConnectAuthenticationError as e:
            raise GarminAuthError(str(e)) from e
        except g.GarminConnectTooManyRequestsError as e:
            raise GarminRateLimited(str(e)) from e
        except g.GarminConnectConnectionError as e:
            raise GarminUnavailable(str(e)) from e
        return bytes(raw), client.client.dumps()

    def fetch_activities(self, tokens: str, start: date, end: date) -> tuple[list[dict[str, Any]], str]:
        """Retourne (activités normalisées, jeton éventuellement rafraîchi)."""
        g = self._lib()
        client = g.Garmin()
        try:
            client.login(tokenstore=tokens)
            raw: list[dict[str, Any]] = []
            seen: set[Any] = set()
            cur = start
            while cur <= end:  # tranches de 180 jours : requêtes raisonnables, pause entre deux tranches
                stop = min(cur + timedelta(days=179), end)
                for a in client.get_activities_by_date(cur.isoformat(), stop.isoformat()):
                    if a.get("activityId") not in seen:
                        seen.add(a.get("activityId"))
                        raw.append(a)
                cur = stop + timedelta(days=1)
                if cur <= end:
                    time.sleep(1.0)
        except g.GarminConnectAuthenticationError as e:
            raise GarminAuthError(str(e)) from e
        except g.GarminConnectTooManyRequestsError as e:
            raise GarminRateLimited(str(e)) from e
        except g.GarminConnectConnectionError as e:
            raise GarminUnavailable(str(e)) from e
        rows = [r for r in (normalize(a) for a in raw) if r]
        return rows, client.client.dumps()

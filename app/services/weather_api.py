from datetime import datetime, timezone
import requests


def _weather_score_for_pitcher(weather: dict, pitcher_profile: dict) -> float:
    if not weather.get("available"):
        return 50.0

    temp = weather.get("temperature_f") or 70
    humidity = weather.get("humidity") or 50
    wind = weather.get("wind_speed_mph") or 0
    pressure = weather.get("pressure_hpa") or 1013

    score = 50.0

    if temp >= 85:
        score -= 5
    elif temp <= 55:
        score += 4

    if humidity >= 70:
        score -= 2
    elif humidity <= 35:
        score += 1

    if wind >= 12:
        score -= 4
    elif wind <= 5:
        score += 1

    if pressure < 1008:
        score -= 2
    elif pressure > 1020:
        score += 2

    hr9 = pitcher_profile.get("raw", {}).get("traditional", {}).get("HR/9", 1.0)
    if hr9 >= 1.4 and score < 50:
        score -= 3

    return round(max(20, min(80, score)), 1)


def _closest_hour_index(times: list[str], game_datetime: str | None) -> int:
    if not times:
        return 0

    if not game_datetime:
        return 0

    try:
        # MLB dates are usually UTC ISO strings ending in Z.
        target = datetime.fromisoformat(game_datetime.replace("Z", "+00:00"))
    except ValueError:
        return 0

    best_idx = 0
    best_delta = None

    for idx, item in enumerate(times):
        try:
            # Open-Meteo returns local naive time strings. Treat them as naive for nearest-hour selection.
            point = datetime.fromisoformat(item)
            target_compare = target.replace(tzinfo=None)
            delta = abs((point - target_compare).total_seconds())
        except ValueError:
            continue

        if best_delta is None or delta < best_delta:
            best_delta = delta
            best_idx = idx

    return best_idx


def get_weather_context(venue_context: dict, pitcher_profile: dict | None = None, game_datetime: str | None = None) -> dict:
    roof = venue_context.get("roof")
    if roof == "dome":
        return {
            "available": True,
            "weather_score": 50.0,
            "summary": "Indoor dome. Weather impact treated as neutral.",
            "roof": roof,
        }

    lat = venue_context.get("lat")
    lon = venue_context.get("lon")

    if lat is None or lon is None:
        return {
            "available": False,
            "weather_score": 50.0,
            "summary": "Weather unavailable for unmapped venue.",
            "roof": roof or "unknown",
        }

    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,relative_humidity_2m,wind_speed_10m,surface_pressure,precipitation_probability",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "auto",
        "forecast_days": 1,
    }

    try:
        response = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=8)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return {
            "available": False,
            "weather_score": 50.0,
            "summary": "Weather API unavailable.",
            "roof": roof or "unknown",
        }

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])

    if not times:
        return {
            "available": False,
            "weather_score": 50.0,
            "summary": "Weather forecast missing hourly data.",
            "roof": roof or "unknown",
        }

    idx = _closest_hour_index(times, game_datetime)

    def pick(key, default=None):
        values = hourly.get(key, [])
        if idx < len(values):
            return values[idx]
        return default

    weather = {
        "available": True,
        "temperature_f": pick("temperature_2m"),
        "humidity": pick("relative_humidity_2m"),
        "wind_speed_mph": pick("wind_speed_10m"),
        "pressure_hpa": pick("surface_pressure"),
        "precipitation_probability": pick("precipitation_probability"),
        "roof": roof or "open",
    }

    weather["weather_score"] = _weather_score_for_pitcher(weather, pitcher_profile or {})

    roof_note = ""
    if roof == "retractable":
        roof_note = " Retractable roof; actual roof status is not modeled yet."

    weather["summary"] = (
        f"{weather.get('temperature_f')}°F, "
        f"{weather.get('humidity')}% humidity, "
        f"{weather.get('wind_speed_mph')} mph wind, "
        f"{weather.get('pressure_hpa')} hPa pressure."
        f"{roof_note}"
    )

    return weather

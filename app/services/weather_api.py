from datetime import datetime, timezone
import requests


def _weather_score_for_pitcher(weather: dict, pitcher_profile: dict) -> float:
    """Score weather from a pitcher's perspective.

    Hot weather, wind out, and low pressure generally increase carry/contact risk.
    This is intentionally simple but real-data-ready.
    """
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

    # Penalize fly-ball / HR-prone profiles more heavily in bad carry environments.
    hr9 = pitcher_profile.get("raw", {}).get("traditional", {}).get("HR/9", 1.0)
    if hr9 >= 1.4 and score < 50:
        score -= 3

    return round(max(20, min(80, score)), 1)


def get_weather_context(venue_context: dict, pitcher_profile: dict | None = None) -> dict:
    lat = venue_context.get("lat")
    lon = venue_context.get("lon")

    if lat is None or lon is None:
        return {
            "available": False,
            "weather_score": 50.0,
            "summary": "Weather unavailable for unmapped venue.",
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
        }

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])

    if not times:
        return {
            "available": False,
            "weather_score": 50.0,
            "summary": "Weather forecast missing hourly data.",
        }

    # MVP: use the current/first available hourly point.
    idx = 0

    weather = {
        "available": True,
        "temperature_f": hourly.get("temperature_2m", [None])[idx],
        "humidity": hourly.get("relative_humidity_2m", [None])[idx],
        "wind_speed_mph": hourly.get("wind_speed_10m", [None])[idx],
        "pressure_hpa": hourly.get("surface_pressure", [None])[idx],
        "precipitation_probability": hourly.get("precipitation_probability", [None])[idx],
    }

    weather["weather_score"] = _weather_score_for_pitcher(weather, pitcher_profile or {})
    weather["summary"] = (
        f"{weather.get('temperature_f')}°F, "
        f"{weather.get('humidity')}% humidity, "
        f"{weather.get('wind_speed_mph')} mph wind, "
        f"{weather.get('pressure_hpa')} hPa pressure"
    )

    return weather

from app.services.advanced_stats import get_pitcher_profile
from app.services.venue_context import get_venue_context
from app.services.weather_api import get_weather_context
from app.services.lineup_context import get_lineup_matchup_context


WEIGHTS = {
    "Season Performance": 0.20,
    "Recent Form": 0.25,
    "Statcast Quality": 0.20,
    "Command / Whiff": 0.15,
    "Lineup Matchup": 0.10,
    "Weather Impact": 0.05,
    "Park Context": 0.05,
}


def _weighted_pitchiq_score(profile: dict, home_bonus: float = 0.0) -> float:
    scores = profile.get("component_scores", {})
    total = 0

    for label, weight in WEIGHTS.items():
        total += scores.get(label, 50) * weight

    return round(total + home_bonus, 1)


def _probability_from_scores(away_score: float, home_score: float) -> tuple[float, float]:
    gap = home_score - away_score
    home = 50 + (gap * 0.65)
    home = max(32, min(68, home))
    away = 100 - home
    return round(away, 1), round(home, 1)


def _raw(profile: dict, group: str, key: str, default):
    return profile.get("raw", {}).get(group, {}).get(key, default)


def _expected_innings(profile: dict) -> float:
    avg_ip = _raw(profile, "recent_form", "Avg IP", 5.3)
    pitch_count = _raw(profile, "recent_form", "Avg Pitch Count", 85)
    command = profile.get("component_scores", {}).get("Command / Whiff", 50)
    weather = profile.get("component_scores", {}).get("Weather Impact", 50)
    park = profile.get("component_scores", {}).get("Park Context", 50)

    innings = avg_ip
    innings += ((command - 50) / 100)
    innings += ((pitch_count - 85) / 60)
    innings += ((weather - 50) / 120)
    innings += ((park - 50) / 140)

    return round(max(4.0, min(7.4, innings)), 1)


def _strikeout_projection(profile: dict, expected_ip: float) -> float:
    k9 = _raw(profile, "traditional", "K/9", 8.0)
    whiff = _raw(profile, "plate_discipline", "Whiff%", 24)
    lineup = profile.get("component_scores", {}).get("Lineup Matchup", 50)

    projection = (k9 / 9) * expected_ip
    projection += (whiff - 24) / 9
    projection += (lineup - 50) / 25

    return round(max(2.0, min(11.5, projection)), 1)


def _quality_start_probability(profile: dict, expected_ip: float) -> int:
    scores = profile.get("component_scores", {})
    statcast = scores.get("Statcast Quality", 50)
    recent = scores.get("Recent Form", 50)
    season = scores.get("Season Performance", 50)
    weather = scores.get("Weather Impact", 50)
    park = scores.get("Park Context", 50)

    probability = 18 + (expected_ip - 5.0) * 12
    probability += (statcast - 50) * .25
    probability += (recent - 50) * .18
    probability += (season - 50) * .12
    probability += (weather - 50) * .10
    probability += (park - 50) * .08

    return int(round(max(8, min(72, probability))))


def _explanation_rows(away_profile: dict, home_profile: dict) -> list[dict]:
    rows = []

    for label, weight in WEIGHTS.items():
        away_value = away_profile.get("component_scores", {}).get(label, 50)
        home_value = home_profile.get("component_scores", {}).get(label, 50)

        edge = round(home_value - away_value, 1)

        rows.append(
            {
                "label": label,
                "weight": f"{int(weight * 100)}%",
                "away": away_value,
                "home": home_value,
                "edge": edge,
                "meter": max(0, min(100, 50 + edge)),
            }
        )

    return rows


def _apply_context_scores(profile: dict, weather: dict, park: dict, lineup: dict) -> None:
    profile["component_scores"]["Weather Impact"] = weather.get("weather_score", 50.0)
    profile["component_scores"]["Park Context"] = park.get("park_score", 50.0)
    profile["component_scores"]["Lineup Matchup"] = lineup.get("lineup_score", 50.0)


def build_matchup_prediction(game: dict) -> dict:
    away_profile = get_pitcher_profile(game.get("away_pitcher_id"), game.get("away_pitcher") or "TBD")
    home_profile = get_pitcher_profile(game.get("home_pitcher_id"), game.get("home_pitcher") or "TBD")

    venue_context = get_venue_context(game.get("venue", ""))

    away_weather = get_weather_context(venue_context, away_profile)
    home_weather = get_weather_context(venue_context, home_profile)

    away_lineup = get_lineup_matchup_context(
        pitcher_id=game.get("away_pitcher_id"),
        opposing_team_id=game.get("home", {}).get("id"),
        game_id=game.get("game_id"),
        opposing_side="home",
    )

    home_lineup = get_lineup_matchup_context(
        pitcher_id=game.get("home_pitcher_id"),
        opposing_team_id=game.get("away", {}).get("id"),
        game_id=game.get("game_id"),
        opposing_side="away",
    )

    _apply_context_scores(away_profile, away_weather, venue_context, away_lineup)
    _apply_context_scores(home_profile, home_weather, venue_context, home_lineup)

    away_score = _weighted_pitchiq_score(away_profile)
    home_score = _weighted_pitchiq_score(home_profile, home_bonus=2.0)

    away_win_probability, home_win_probability = _probability_from_scores(away_score, home_score)

    away_ip = _expected_innings(away_profile)
    home_ip = _expected_innings(home_profile)

    away_ks = _strikeout_projection(away_profile, away_ip)
    home_ks = _strikeout_projection(home_profile, home_ip)

    away_qs = _quality_start_probability(away_profile, away_ip)
    home_qs = _quality_start_probability(home_profile, home_ip)

    if home_score > away_score:
        pitcher_advantage = game.get("home_team", "Home Team")
        edge_amount = round(home_score - away_score, 1)
    elif away_score > home_score:
        pitcher_advantage = game.get("away_team", "Away Team")
        edge_amount = round(away_score - home_score, 1)
    else:
        pitcher_advantage = "Even"
        edge_amount = 0

    confidence = "Medium - model includes pitcher profile, weather, park context, and lineup/BvP scaffold"
    if abs(home_score - away_score) < 3:
        confidence = "Low - matchup grades are very close"
    elif abs(home_score - away_score) >= 10:
        confidence = "Medium-High - meaningful profile separation"

    return {
        "pitcher_advantage": pitcher_advantage,
        "edge_amount": edge_amount,
        "away_pitchiq_score": away_score,
        "home_pitchiq_score": home_score,
        "away_win_probability": away_win_probability,
        "home_win_probability": home_win_probability,
        "expected_away_pitcher_innings": away_ip,
        "expected_home_pitcher_innings": home_ip,
        "away_strikeout_projection": away_ks,
        "home_strikeout_projection": home_ks,
        "away_quality_start_probability": away_qs,
        "home_quality_start_probability": home_qs,
        "confidence": confidence,
        "away_profile": away_profile,
        "home_profile": home_profile,
        "venue_context": venue_context,
        "away_weather": away_weather,
        "home_weather": home_weather,
        "away_lineup": away_lineup,
        "home_lineup": home_lineup,
        "score_breakdown": _explanation_rows(away_profile, home_profile),
    }

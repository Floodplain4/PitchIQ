from app.services.advanced_stats import get_pitcher_profile
from app.services.venue_context import get_venue_context
from app.services.weather_api import get_weather_context
from app.services.lineup_context import get_lineup_matchup_context


WEIGHTS = {
    "Season Performance": 0.20,
    "Recent Form": 0.22,
    "Statcast Quality": 0.20,
    "Command / Whiff": 0.18,
    "Lineup Matchup": 0.10,
    "Weather Impact": 0.05,
    "Park Context": 0.05,
}

LEAGUE_AVERAGE_K_RATE = 0.225
LEAGUE_AVERAGE_BATTERS_PER_INNING = 4.25


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _weighted_pitchiq_score(profile: dict, home_bonus: float = 0.0) -> float:
    scores = profile.get("component_scores", {})
    total = 0.0

    for label, weight in WEIGHTS.items():
        total += scores.get(label, 50) * weight

    return round(_clamp(total + home_bonus, 20, 80), 1)


def _probability_from_scores(away_score: float, home_score: float) -> tuple[float, float]:
    """Conservative pitcher-focused probability from PitchIQ score gap."""
    gap = home_score - away_score
    home = 50 + (gap * 0.55)
    home = _clamp(home, 35, 65)
    away = 100 - home
    return round(away, 1), round(home, 1)


def _raw(profile: dict, group: str, key: str, default):
    return profile.get("raw", {}).get(group, {}).get(key, default)


def _expected_innings(profile: dict) -> float:
    """Estimate starter workload conservatively."""
    avg_ip = float(_raw(profile, "recent_form", "Avg IP", 5.2))
    pitch_count = float(_raw(profile, "recent_form", "Avg Pitch Count", 84))
    recent_score = profile.get("component_scores", {}).get("Recent Form", 50)
    command_score = profile.get("component_scores", {}).get("Command / Whiff", 50)
    weather_score = profile.get("component_scores", {}).get("Weather Impact", 50)
    park_score = profile.get("component_scores", {}).get("Park Context", 50)

    innings = avg_ip
    innings += (pitch_count - 84) / 95
    innings += (recent_score - 50) / 180
    innings += (command_score - 50) / 220
    innings += (weather_score - 50) / 250
    innings += (park_score - 50) / 250

    return round(_clamp(innings, 3.5, 6.2), 1)


def _expected_batters_faced(profile: dict, expected_ip: float) -> float:
    season_score = profile.get("component_scores", {}).get("Season Performance", 50)
    statcast_score = profile.get("component_scores", {}).get("Statcast Quality", 50)
    command_score = profile.get("component_scores", {}).get("Command / Whiff", 50)

    whip = float(_raw(profile, "traditional", "WHIP", 1.30))
    bb9 = float(_raw(profile, "traditional", "BB/9", 3.0))
    hr9 = float(_raw(profile, "traditional", "HR/9", 1.1))

    batters_per_inning = LEAGUE_AVERAGE_BATTERS_PER_INNING
    batters_per_inning += (whip - 1.25) * 0.55
    batters_per_inning += (bb9 - 3.0) * 0.08
    batters_per_inning += (hr9 - 1.1) * 0.08

    quality_score = (season_score * 0.40) + (statcast_score * 0.35) + (command_score * 0.25)
    batters_per_inning -= (quality_score - 50) / 220

    batters_per_inning = _clamp(batters_per_inning, 3.85, 4.75)
    return round(expected_ip * batters_per_inning, 1)


def _adjusted_k_rate(profile: dict) -> float:
    """Estimate strikeout rate before multiplying by expected batters faced."""
    k_pct = float(_raw(profile, "plate_discipline", "K%", LEAGUE_AVERAGE_K_RATE * 100)) / 100
    k9 = float(_raw(profile, "traditional", "K/9", 8.2))
    whiff = float(_raw(profile, "plate_discipline", "Whiff%", 24))
    chase = float(_raw(profile, "plate_discipline", "Chase%", 30))
    lineup_score = profile.get("component_scores", {}).get("Lineup Matchup", 50)

    k9_rate = (k9 / 9) / LEAGUE_AVERAGE_BATTERS_PER_INNING

    rate = (k_pct * 0.62) + (k9_rate * 0.28) + (LEAGUE_AVERAGE_K_RATE * 0.10)
    rate += (whiff - 24) * 0.0022
    rate += (chase - 30) * 0.0012
    rate += (lineup_score - 50) * 0.0009

    rate = (rate * 0.82) + (LEAGUE_AVERAGE_K_RATE * 0.18)
    return _clamp(rate, 0.145, 0.335)


def _strikeout_projection(profile: dict, expected_ip: float) -> float:
    """Projected Ks = expected batters faced x adjusted K%, with only a tiny recent-form nudge."""
    expected_bf = _expected_batters_faced(profile, expected_ip)
    adjusted_k_rate = _adjusted_k_rate(profile)

    projection = expected_bf * adjusted_k_rate

    last_3_k = float(_raw(profile, "recent_form", "Last 3 K", 15))
    recent_k_per_start = last_3_k / 3

    if recent_k_per_start >= 7:
        projection += 0.25
    elif recent_k_per_start <= 3:
        projection -= 0.25

    return round(_clamp(projection, 1.5, 7.2), 1)


def _quality_start_probability(profile: dict, expected_ip: float) -> int:
    scores = profile.get("component_scores", {})
    statcast = scores.get("Statcast Quality", 50)
    recent = scores.get("Recent Form", 50)
    season = scores.get("Season Performance", 50)
    command = scores.get("Command / Whiff", 50)
    weather = scores.get("Weather Impact", 50)
    park = scores.get("Park Context", 50)

    era = float(_raw(profile, "traditional", "ERA", 4.10))
    whip = float(_raw(profile, "traditional", "WHIP", 1.28))
    hr9 = float(_raw(profile, "traditional", "HR/9", 1.10))

    probability = 22
    probability += (expected_ip - 5.2) * 13
    probability += (season - 50) * 0.16
    probability += (recent - 50) * 0.15
    probability += (statcast - 50) * 0.16
    probability += (command - 50) * 0.08
    probability += (weather - 50) * 0.07
    probability += (park - 50) * 0.07

    probability -= max(0, era - 4.20) * 3.0
    probability -= max(0, whip - 1.30) * 12
    probability -= max(0, hr9 - 1.20) * 5

    return int(round(_clamp(probability, 6, 62)))


def _run_prevention_projection(profile: dict) -> dict:
    era = float(_raw(profile, "traditional", "ERA", 4.10))
    fip = float(_raw(profile, "traditional", "FIP", 4.10))
    xwoba = float(_raw(profile, "statcast", "xwOBA", 0.320))
    hard_hit = float(_raw(profile, "statcast", "HardHit%", 39.0))
    barrel = float(_raw(profile, "statcast", "Barrel%", 8.0))

    projected_era = (era * 0.38) + (fip * 0.34) + (((xwoba - 0.320) * 12) + 4.10) * 0.18
    projected_era += (hard_hit - 39) * 0.025
    projected_era += (barrel - 8) * 0.045

    return {
        "projected_era_context": round(_clamp(projected_era, 2.50, 6.20), 2),
        "contact_risk": round(_clamp(50 + (hard_hit - 39) * 1.4 + (barrel - 8) * 2.1, 15, 85), 1),
    }


def _matchup_lean(away_score: float, home_score: float, game: dict) -> dict:
    diff = round(home_score - away_score, 1)

    if abs(diff) < 2:
        return {
            "side": "even",
            "team": "No clear pitching edge",
            "abbr": "EVEN",
            "score_edge": round(abs(diff), 1),
            "strength": "No",
            "logo": "",
            "color": "#64748b",
            "summary": "No clear pitching edge",
        }

    if diff > 0:
        team = game.get("home_team", "Home Team")
        team_block = game.get("home", {}) or {}
        strength = "Slight" if diff < 6 else "Clear"
        edge = diff
        side = "home"
    else:
        team = game.get("away_team", "Away Team")
        team_block = game.get("away", {}) or {}
        strength = "Slight" if abs(diff) < 6 else "Clear"
        edge = abs(diff)
        side = "away"

    return {
        "side": side,
        "team": team,
        "abbr": team_block.get("abbr", team[:3].upper()),
        "score_edge": round(edge, 1),
        "strength": strength,
        "logo": team_block.get("logo", ""),
        "color": team_block.get("primary", "#2563eb"),
        "summary": f"{strength} lean: {team} by {round(edge, 1)} PitchIQ points",
    }


def _stat_tooltips() -> dict:
    return {
        "Pitcher Advantage": "The starting pitcher with the stronger PitchIQ matchup grade after season performance, recent form, Statcast quality, command/whiff skill, lineup, weather, and park context are applied.",
        "PitchIQ": "A 20-80 style pitcher matchup score. It blends season performance, recent form, Statcast quality, command/whiff skill, lineup matchup, weather, and park context. Higher is better for the pitcher.",
        "PitchIQ Score": "A 20-80 style pitcher matchup score. It blends season performance, recent form, Statcast quality, command/whiff skill, lineup matchup, weather, and park context. Higher is better for the pitcher.",
        "Win Probability": "A conservative pitcher-focused probability derived from the PitchIQ score gap. It is not a sportsbook line and does not fully model offense, bullpen, defense, injuries, or market odds.",
        "Expected IP": "Estimated starter workload. It starts with recent average innings, then adjusts modestly for pitch count, command, recent form, weather, and park context.",
        "K Projection": "Projected strikeouts. Calculated as expected batters faced multiplied by adjusted strikeout rate, with only a small recent-form nudge.",
        "Quality Start": "Estimated chance of 6+ innings and 3 or fewer earned runs. Workload, run prevention, command, park, and weather all influence it.",
        "Model Role": "Whether this pitcher is being evaluated as the away starter or home starter for the matchup.",
        "Season Performance": "Season-level pitcher quality score using ERA, WHIP, FIP, and strikeout skill.",
        "Recent Form": "Recent-start score using recent ERA, WHIP, strikeouts, average innings, pitch count, and velocity trend.",
        "Statcast Quality": "Contact-quality score using expected stats and batted-ball damage allowed, such as xwOBA, xBA, xSLG, hard-hit rate, barrel rate, and average exit velocity.",
        "Command / Whiff": "Pitcher dominance and command score using K%, BB%, chase rate, and whiff rate.",
        "Lineup Matchup": "Pitcher-facing score for the opposing lineup. When official lineups are unavailable, this currently falls back to a deterministic placeholder.",
        "Weather Impact": "Pitcher-facing weather score. Heat, humidity, wind, pressure, and HR-prone profiles can move this up or down.",
        "Park Context": "Pitcher-facing ballpark score based on run factor and home-run factor. Pitcher-friendly parks score higher.",
        "ERA": "Earned Run Average: earned runs allowed per nine innings. Lower is better for pitchers.",
        "WHIP": "Walks plus hits per inning pitched. Lower means fewer baserunners.",
        "FIP": "Fielding Independent Pitching. Estimates pitcher run prevention from strikeouts, walks/HBP, and home runs while reducing defense effects.",
        "K/9": "Strikeouts per nine innings. Useful, but less direct than K% for strikeout projections because it depends on innings.",
        "BB/9": "Walks per nine innings. Lower is better.",
        "HR/9": "Home runs allowed per nine innings. Lower is better, especially in hitter-friendly parks.",
        "Last 3 ERA": "ERA over the recent-start sample.",
        "Last 3 WHIP": "WHIP over the recent-start sample.",
        "Last 3 K": "Total strikeouts over the recent-start sample. Used only lightly so one hot stretch does not dominate projections.",
        "Avg IP": "Average innings per start over the recent-start sample.",
        "Avg Pitch Count": "Average recent pitch count. Higher pitch counts can support more expected innings.",
        "Velocity Trend": "Estimated recent velocity movement compared with baseline. Positive is generally better.",
        "xwOBA": "Expected weighted on-base average allowed based on contact quality and plate appearance outcomes. Lower is better for pitchers.",
        "xBA": "Expected batting average allowed. Lower is better.",
        "xSLG": "Expected slugging allowed. Lower is better.",
        "HardHit%": "Percentage of batted balls hit 95+ mph. Lower is better for pitchers.",
        "Barrel%": "Percentage of batted balls with ideal exit velocity and launch angle. Lower is better.",
        "Avg EV": "Average exit velocity allowed. Lower is better.",
        "GB%": "Ground-ball percentage. More ground balls can reduce extra-base damage.",
        "FB%": "Fly-ball percentage. Context dependent; high fly-ball rates can be risky in homer-friendly parks.",
        "LD%": "Line-drive percentage. Lower is usually better for pitchers.",
        "Pull%": "Pulled-contact percentage. High pull contact can indicate damage risk depending on hitter and park.",
        "Oppo%": "Opposite-field contact percentage.",
        "Zone%": "Percentage of pitches thrown in the strike zone.",
        "Chase%": "Percentage of out-of-zone pitches that batters swing at. Higher is better for pitchers.",
        "Whiff%": "Swing-and-miss rate. Higher usually supports stronger strikeout projection.",
        "1stPitchS%": "First-pitch strike percentage. Getting ahead early generally improves pitcher outcomes.",
        "BB%": "Walk rate per plate appearance. Lower is better.",
        "K%": "Strikeout rate per plate appearance. This is one of the best anchors for strikeout projections because it is tied to batters faced.",
    }

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
    home_score = _weighted_pitchiq_score(home_profile, home_bonus=1.5)

    away_win_probability, home_win_probability = _probability_from_scores(away_score, home_score)

    away_ip = _expected_innings(away_profile)
    home_ip = _expected_innings(home_profile)

    away_bf = _expected_batters_faced(away_profile, away_ip)
    home_bf = _expected_batters_faced(home_profile, home_ip)

    away_k_rate = _adjusted_k_rate(away_profile)
    home_k_rate = _adjusted_k_rate(home_profile)

    away_ks = _strikeout_projection(away_profile, away_ip)
    home_ks = _strikeout_projection(home_profile, home_ip)

    away_qs = _quality_start_probability(away_profile, away_ip)
    home_qs = _quality_start_probability(home_profile, home_ip)

    away_run_context = _run_prevention_projection(away_profile)
    home_run_context = _run_prevention_projection(home_profile)

    lean = _matchup_lean(away_score, home_score, game)

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
        "matchup_lean": lean,
        "away_pitchiq_score": away_score,
        "home_pitchiq_score": home_score,
        "away_win_probability": away_win_probability,
        "home_win_probability": home_win_probability,
        "expected_away_pitcher_innings": away_ip,
        "expected_home_pitcher_innings": home_ip,
        "away_expected_batters_faced": away_bf,
        "home_expected_batters_faced": home_bf,
        "away_adjusted_k_rate": round(away_k_rate * 100, 1),
        "home_adjusted_k_rate": round(home_k_rate * 100, 1),
        "away_strikeout_projection": away_ks,
        "home_strikeout_projection": home_ks,
        "away_quality_start_probability": away_qs,
        "home_quality_start_probability": home_qs,
        "away_run_context": away_run_context,
        "home_run_context": home_run_context,
        "confidence": confidence,
        "stat_tooltips": _stat_tooltips(),
        "away_profile": away_profile,
        "home_profile": home_profile,
        "venue_context": venue_context,
        "away_weather": away_weather,
        "home_weather": home_weather,
        "away_lineup": away_lineup,
        "home_lineup": home_lineup,
        "score_breakdown": _explanation_rows(away_profile, home_profile),
    }

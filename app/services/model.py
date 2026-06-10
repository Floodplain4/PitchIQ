import re

from app.services.advanced_stats import get_pitcher_profile
from app.services.venue_context import get_venue_context
from app.services.weather_api import get_weather_context
from app.services.lineup_context import get_lineup_matchup_context


# Keep PitchIQ pitcher-focused, but do not let small Statcast samples or short workloads
# create market-looking blowouts. Team context is added separately to win probability.
WEIGHTS = {
    # Keep the model pitcher-first. Statcast and command should drive the
    # PitchIQ score more than placeholder lineup/BvP context.
    "Season Performance": 0.18,
    "Recent Form": 0.10,
    "Statcast Quality": 0.28,
    "Command / Whiff": 0.20,
    "Lineup Matchup": 0.10,
    "Weather Impact": 0.04,
    "Park Context": 0.04,
}

LEAGUE_AVERAGE_K_RATE = 0.225
LEAGUE_AVERAGE_BATTERS_PER_INNING = 4.25


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _extract_sample_pitches(profile: dict) -> int:
    """Best-effort sample-size detector.

    Different profile versions have stored sample size in slightly different
    places, so this checks several locations and then falls back to parsing
    the data_quality text, e.g. "Real Statcast profile · 175 pitches sampled".
    """
    candidates = [
        profile.get("sample_pitches"),
        profile.get("raw", {}).get("sample_pitches"),
        profile.get("raw", {}).get("statcast", {}).get("sample_pitches"),
    ]

    for value in candidates:
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            pass

    text = str(profile.get("data_quality", ""))
    match = re.search(r"(\d+)\s+pitches", text, re.IGNORECASE)
    if match:
        return int(match.group(1))

    # Deterministic/placeholder profiles should be treated as low confidence.
    return 0


def _profile_reliability(profile: dict) -> float:
    """Regress small samples toward league average.

    Public projection systems generally avoid treating tiny samples as truth.
    This gives very small samples limited influence and lets 1200+ pitches
    behave close to fully reliable.
    """
    sample_pitches = _extract_sample_pitches(profile)

    if sample_pitches <= 0:
        return 0.40

    # 175 pitches should be around 0.45 reliable, 600 around 0.67, 1200+ near 1.0.
    return _clamp(0.35 + (sample_pitches / 1200) * 0.65, 0.35, 1.00)


def _weighted_pitchiq_score(profile: dict, expected_ip: float | None = None, home_bonus: float = 0.0) -> float:
    """Pitcher-focused 20-80 grade with sample-size and workload regression.

    This is where the final PitchIQ number is calculated. The old version used
    component scores almost directly, which let small Statcast samples create
    huge edges. This version pulls uncertain/short-workload pitchers back toward
    average.
    """
    scores = profile.get("component_scores", {})
    raw_total = 0.0

    for label, weight in WEIGHTS.items():
        raw_total += scores.get(label, 50) * weight

    # Normalize to a 20-80 style center even if weights change later.
    weight_sum = sum(WEIGHTS.values()) or 1
    raw_score = raw_total / weight_sum

    reliability = _profile_reliability(profile)

    workload_factor = 1.0
    if expected_ip is not None:
        # A pitcher projected for only 3.5 IP should not be able to create a
        # massive matchup edge by himself.
        workload_factor = _clamp(expected_ip / 5.6, 0.55, 1.05)

    regressed = 50 + ((raw_score - 50) * reliability * workload_factor)
    return round(_clamp(regressed + home_bonus, 30, 70), 1)


def _record_pct(record: str) -> float | None:
    if not record:
        return None

    match = re.search(r"(\d+)\s*-\s*(\d+)", record)
    if not match:
        return None

    wins = int(match.group(1))
    losses = int(match.group(2))
    total = wins + losses

    if total <= 0:
        return None

    return wins / total


def _probability_from_context(away_score: float, home_score: float, game: dict) -> tuple[float, float]:
    """Conservative game probability, not just pitcher edge.

    Sportsbooks/projection systems include team quality, offense, bullpen,
    defense, and market info. We do not have all of that yet, so this uses
    pitcher score gap + record strength + a small home-field bump.
    """
    pitcher_gap = home_score - away_score

    away_record = _record_pct(game.get("away", {}).get("record", ""))
    home_record = _record_pct(game.get("home", {}).get("record", ""))

    record_gap = 0.0
    if away_record is not None and home_record is not None:
        record_gap = home_record - away_record

    home = 50
    home += pitcher_gap * 0.25
    home += record_gap * 18
    home += 1.5  # home field

    # Conservative until real offense/bullpen inputs are added.
    home = _clamp(home, 38, 62)
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

    reliability = _profile_reliability(profile)

    innings = avg_ip
    innings += (pitch_count - 84) / 95
    innings += (recent_score - 50) / 220
    innings += (command_score - 50) / 260
    innings += (weather_score - 50) / 300
    innings += (park_score - 50) / 300

    # Regress low-sample or uncertain pitchers toward a conservative starter/bulk role.
    innings = (innings * reliability) + (4.7 * (1 - reliability))

    return round(_clamp(innings, 3.2, 6.3), 1)


def _expected_batters_faced(profile: dict, expected_ip: float) -> float:
    season_score = profile.get("component_scores", {}).get("Season Performance", 50)
    statcast_score = profile.get("component_scores", {}).get("Statcast Quality", 50)
    command_score = profile.get("component_scores", {}).get("Command / Whiff", 50)

    whip = float(_raw(profile, "traditional", "WHIP", 1.30))
    bb9 = float(_raw(profile, "traditional", "BB/9", 3.0))
    hr9 = float(_raw(profile, "traditional", "HR/9", 1.1))

    batters_per_inning = LEAGUE_AVERAGE_BATTERS_PER_INNING
    batters_per_inning += (whip - 1.25) * 0.45
    batters_per_inning += (bb9 - 3.0) * 0.06
    batters_per_inning += (hr9 - 1.1) * 0.05

    quality_score = (season_score * 0.25) + (statcast_score * 0.45) + (command_score * 0.30)
    batters_per_inning -= (quality_score - 50) / 260

    batters_per_inning = _clamp(batters_per_inning, 3.95, 4.65)
    return round(expected_ip * batters_per_inning, 1)


def _adjusted_k_rate(profile: dict) -> float:
    """Estimate strikeout rate before multiplying by expected batters faced."""
    k_pct = float(_raw(profile, "plate_discipline", "K%", LEAGUE_AVERAGE_K_RATE * 100)) / 100
    k9 = float(_raw(profile, "traditional", "K/9", 8.2))
    whiff = float(_raw(profile, "plate_discipline", "Whiff%", 24))
    chase = float(_raw(profile, "plate_discipline", "Chase%", 30))
    lineup_score = profile.get("component_scores", {}).get("Lineup Matchup", 50)

    k9_rate = (k9 / 9) / LEAGUE_AVERAGE_BATTERS_PER_INNING

    rate = (k_pct * 0.60) + (k9_rate * 0.22) + (LEAGUE_AVERAGE_K_RATE * 0.18)
    rate += (whiff - 24) * 0.0015
    rate += (chase - 30) * 0.0008
    rate += (lineup_score - 50) * 0.0006

    reliability = _profile_reliability(profile)

    # Small samples get heavily regressed toward league average.
    rate = (rate * reliability) + (LEAGUE_AVERAGE_K_RATE * (1 - reliability))
    rate = (rate * 0.88) + (LEAGUE_AVERAGE_K_RATE * 0.12)

    return _clamp(rate, 0.155, 0.315)


def _strikeout_projection(profile: dict, expected_ip: float) -> float:
    """Projected Ks = expected batters faced x adjusted K%."""
    expected_bf = _expected_batters_faced(profile, expected_ip)
    adjusted_k_rate = _adjusted_k_rate(profile)

    projection = expected_bf * adjusted_k_rate

    last_3_k = float(_raw(profile, "recent_form", "Last 3 K", 15))
    recent_k_per_start = last_3_k / 3

    # Tiny form nudge only.
    if recent_k_per_start >= 7:
        projection += 0.15
    elif recent_k_per_start <= 3:
        projection -= 0.15

    return round(_clamp(projection, 1.5, 7.0), 1)


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

    reliability = _profile_reliability(profile)

    probability = 18
    probability += (expected_ip - 5.2) * 12
    probability += (season - 50) * 0.08
    probability += (recent - 50) * 0.06
    probability += (statcast - 50) * 0.14
    probability += (command - 50) * 0.06
    probability += (weather - 50) * 0.05
    probability += (park - 50) * 0.05

    probability -= max(0, era - 4.20) * 2.5
    probability -= max(0, whip - 1.30) * 10
    probability -= max(0, hr9 - 1.20) * 4

    # Low samples should not produce high QS confidence.
    probability = (probability * reliability) + (18 * (1 - reliability))

    return int(round(_clamp(probability, 4, 58)))


def _run_prevention_projection(profile: dict) -> dict:
    era = float(_raw(profile, "traditional", "ERA", 4.10))
    fip = float(_raw(profile, "traditional", "FIP", 4.10))
    xwoba = float(_raw(profile, "statcast", "xwOBA", 0.320))
    hard_hit = float(_raw(profile, "statcast", "HardHit%", 39.0))
    barrel = float(_raw(profile, "statcast", "Barrel%", 8.0))

    reliability = _profile_reliability(profile)

    # Make the run-prevention context more forward-looking. ERA/FIP still
    # matter, but xwOBA and contact damage should move the projection more.
    projected_era = (era * 0.24) + (fip * 0.26) + (((xwoba - 0.320) * 12) + 4.10) * 0.34
    projected_era += (hard_hit - 39) * 0.024
    projected_era += (barrel - 8) * 0.055

    # Regress projected run prevention for small samples.
    projected_era = (projected_era * reliability) + (4.10 * (1 - reliability))

    return {
        "projected_era_context": round(_clamp(projected_era, 2.70, 5.80), 2),
        "contact_risk": round(_clamp(50 + (hard_hit - 39) * 1.0 + (barrel - 8) * 1.5, 20, 80), 1),
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
        "Pitcher Advantage": "The starting pitcher with the stronger regressed PitchIQ matchup grade. Small samples and short expected workloads are pulled toward average.",
        "PitchIQ": "A regressed 20-80 style pitcher matchup score. It blends season performance, recent form, Statcast quality, command/whiff skill, lineup matchup, weather, and park context. Small samples and short workloads are reduced.",
        "PitchIQ Score": "A regressed 20-80 style pitcher matchup score. It blends season performance, recent form, Statcast quality, command/whiff skill, lineup matchup, weather, and park context.",
        "Win Probability": "A conservative game probability using PitchIQ gap, team record strength, and home field. It is not a sportsbook line and does not fully model offense, bullpen, defense, injuries, or market odds.",
        "Expected IP": "Estimated starter workload. It starts with recent average innings, then adjusts modestly for pitch count, command, recent form, weather, park context, and sample reliability.",
        "K Projection": "Projected strikeouts. Calculated as expected batters faced multiplied by adjusted strikeout rate, with small-sample regression.",
        "Quality Start": "Estimated chance of 6+ innings and 3 or fewer earned runs. Workload, run prevention, command, park, weather, and sample reliability all influence it.",
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

    away_weather = get_weather_context(venue_context, away_profile, game_datetime=game.get("game_date"))
    home_weather = get_weather_context(venue_context, home_profile, game_datetime=game.get("game_date"))

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

    away_ip = _expected_innings(away_profile)
    home_ip = _expected_innings(home_profile)

    away_score = _weighted_pitchiq_score(away_profile, expected_ip=away_ip)
    home_score = _weighted_pitchiq_score(home_profile, expected_ip=home_ip, home_bonus=0.8)

    away_win_probability, home_win_probability = _probability_from_context(away_score, home_score, game)

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
    if min(_profile_reliability(away_profile), _profile_reliability(home_profile)) < 0.55:
        confidence = "Low-Medium - one or both pitchers have limited Statcast sample"
    elif abs(home_score - away_score) < 3:
        confidence = "Low - matchup grades are very close"
    elif abs(home_score - away_score) >= 10:
        confidence = "Medium - meaningful profile separation after regression"

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
        "away_profile_reliability": round(_profile_reliability(away_profile), 2),
        "home_profile_reliability": round(_profile_reliability(home_profile), 2),
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

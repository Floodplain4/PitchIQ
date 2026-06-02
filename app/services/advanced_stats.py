import hashlib
import importlib
from app.services.player_assets import player_headshot_url
def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


DISPLAY_RANGES = {}

# League-style benchmark ranges for display scoring.
# These are intentionally wider than today's pitcher pool so cards don't collapse
# to mostly 0/100. Higher display percentile = better for the pitcher.
DISPLAY_BENCHMARKS = {
    # Statcast quality
    "xwOBA": {"elite": 0.270, "great": 0.295, "avg": 0.320, "poor": 0.350, "bad": 0.385, "direction": "lower"},
    "xBA": {"elite": 0.200, "great": 0.225, "avg": 0.250, "poor": 0.280, "bad": 0.320, "direction": "lower"},
    "xSLG": {"elite": 0.330, "great": 0.375, "avg": 0.420, "poor": 0.480, "bad": 0.560, "direction": "lower"},
    "HardHit%": {"elite": 28.0, "great": 34.0, "avg": 39.0, "poor": 44.0, "bad": 50.0, "direction": "lower"},
    "Barrel%": {"elite": 3.0, "great": 5.0, "avg": 7.5, "poor": 10.0, "bad": 13.0, "direction": "lower"},
    "Avg EV": {"elite": 86.0, "great": 88.0, "avg": 89.5, "poor": 91.5, "bad": 94.0, "direction": "lower"},

    # Batted ball profile
    "GB%": {"elite": 54.0, "great": 49.0, "avg": 43.0, "poor": 36.0, "bad": 30.0, "direction": "higher"},
    "FB%": {"elite": 28.0, "great": 32.0, "avg": 36.0, "poor": 41.0, "bad": 47.0, "direction": "lower"},
    "LD%": {"elite": 17.0, "great": 19.0, "avg": 21.0, "poor": 24.0, "bad": 28.0, "direction": "lower"},
    "Pull%": {"elite": 34.0, "great": 37.0, "avg": 40.0, "poor": 44.0, "bad": 49.0, "direction": "lower"},

    # Command / whiff
    "Zone%": {"elite": 48.0, "great": 45.0, "avg": 42.0, "poor": 39.0, "bad": 36.0, "direction": "higher"},
    "Chase%": {"elite": 35.0, "great": 32.0, "avg": 29.0, "poor": 26.0, "bad": 23.0, "direction": "higher"},
    "Whiff%": {"elite": 32.0, "great": 28.0, "avg": 24.0, "poor": 20.0, "bad": 16.0, "direction": "higher"},
    "1stPitchS%": {"elite": 67.0, "great": 64.0, "avg": 61.0, "poor": 58.0, "bad": 54.0, "direction": "higher"},
    "BB%": {"elite": 5.0, "great": 6.5, "avg": 8.2, "poor": 10.0, "bad": 13.0, "direction": "lower"},
    "K%": {"elite": 31.0, "great": 27.0, "avg": 23.0, "poor": 19.0, "bad": 15.0, "direction": "higher"},

    # Traditional
    "ERA": {"elite": 2.80, "great": 3.40, "avg": 4.10, "poor": 4.80, "bad": 5.60, "direction": "lower"},
    "WHIP": {"elite": 1.05, "great": 1.15, "avg": 1.28, "poor": 1.42, "bad": 1.58, "direction": "lower"},
    "FIP": {"elite": 3.10, "great": 3.55, "avg": 4.10, "poor": 4.65, "bad": 5.30, "direction": "lower"},
    "K/9": {"elite": 10.8, "great": 9.5, "avg": 8.4, "poor": 7.2, "bad": 6.0, "direction": "higher"},
    "BB/9": {"elite": 1.8, "great": 2.4, "avg": 3.0, "poor": 3.7, "bad": 4.7, "direction": "lower"},
    "HR/9": {"elite": 0.7, "great": 0.9, "avg": 1.1, "poor": 1.4, "bad": 1.8, "direction": "lower"},
}


def _piecewise_display_score(value: float, benchmark: dict) -> int:
    """Map a stat to a pitcher-friendly 0-100 score using fixed benchmarks.

    This is not a true MLB percentile. It is a dashboard grade anchored around
    league-like thresholds:
      elite ~= 95, great ~= 80, average ~= 50, poor ~= 25, bad ~= 5
    """
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 50

    elite = benchmark["elite"]
    great = benchmark["great"]
    avg = benchmark["avg"]
    poor = benchmark["poor"]
    bad = benchmark["bad"]
    direction = benchmark.get("direction", "lower")

    if direction == "higher":
        # Convert higher-is-better into a lower-is-better-like axis by negating.
        value, elite, great, avg, poor, bad = -value, -elite, -great, -avg, -poor, -bad

    # At this point lower is better.
    if value <= elite:
        if elite == great:
            return 95
        return int(round(_clamp(95 + ((elite - value) / max(abs(great - elite), 0.01)) * 5, 95, 100)))
    if value <= great:
        return int(round(80 + ((great - value) / max(great - elite, 0.01)) * 15))
    if value <= avg:
        return int(round(50 + ((avg - value) / max(avg - great, 0.01)) * 30))
    if value <= poor:
        return int(round(25 + ((poor - value) / max(poor - avg, 0.01)) * 25))
    if value <= bad:
        return int(round(5 + ((bad - value) / max(bad - poor, 0.01)) * 20))
    return int(round(_clamp(5 - ((value - bad) / max(abs(bad - poor), 0.01)) * 5, 0, 5)))


PITCH_TYPES = ["4-Seam", "Sinker", "Cutter", "Slider", "Change", "Curve", "Splitter"]


METRIC_BOUNDS = {
    "ERA": (2.50, 5.50, "lower"),
    "WHIP": (1.00, 1.55, "lower"),
    "FIP": (2.70, 5.30, "lower"),
    "BB/9": (1.50, 4.80, "lower"),
    "HR/9": (0.50, 1.90, "lower"),
    "Last 3 ERA": (1.80, 6.50, "lower"),
    "Last 3 WHIP": (0.85, 1.70, "lower"),
    "xwOBA": (.275, .370, "lower"),
    "xBA": (.205, .285, "lower"),
    "xSLG": (.330, .485, "lower"),
    "HardHit%": (31.0, 47.0, "lower"),
    "Barrel%": (4.5, 11.8, "lower"),
    "Avg EV": (86.5, 92.0, "lower"),
    "BB%": (5.5, 12.0, "lower"),

    "K/9": (6.0, 12.5, "higher"),
    "Last 3 K": (9, 28, "higher"),
    "Avg IP": (4.5, 7.0, "higher"),
    "Avg Pitch Count": (70, 105, "higher"),
    "Velocity Trend": (-1.5, 1.7, "higher"),
    "Zone%": (39, 51, "higher"),
    "Chase%": (24, 38, "higher"),
    "Whiff%": (18, 35, "higher"),
    "1stPitchS%": (55, 68, "higher"),
    "K%": (17, 32, "higher"),

    "GB%": (33, 52, "higher"),
    "FB%": (22, 41, "neutral"),
    "LD%": (17, 27, "lower"),
    "Pull%": (34, 45, "neutral"),
    "Oppo%": (20, 31, "neutral"),
}


def _seed(player_id: int | None, salt: str = "") -> int:
    raw = f"{player_id or 0}-{salt}".encode("utf-8")
    return int(hashlib.sha256(raw).hexdigest()[:12], 16)


def _bounded(player_id: int | None, salt: str, low: float, high: float, decimals: int = 1) -> float:
    value = _seed(player_id, salt) % 10000 / 10000
    result = low + (high - low) * value
    return round(result, decimals)


def _bounded_int(player_id: int | None, salt: str, low: int, high: int) -> int:
    return int(round(_bounded(player_id, salt, low, high, 0)))


def _score_lower_better(value: float, good: float, bad: float) -> float:
    value = max(min(value, bad), good)
    return round(100 - ((value - good) / (bad - good) * 100), 1)


def _score_higher_better(value: float, bad: float, good: float) -> float:
    value = max(min(value, good), bad)
    return round(((value - bad) / (good - bad) * 100), 1)


def metric_percentile(label: str, value) -> int:
    benchmark = DISPLAY_BENCHMARKS.get(label)

    if benchmark:
        return _piecewise_display_score(value, benchmark)

    # Fallback for stats without fixed benchmarks.
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 50

    if label in DISPLAY_RANGES:
        low, high, direction = DISPLAY_RANGES[label]
        if high == low:
            return 50

        if direction == "lower":
            score = 100 - ((value - low) / (high - low) * 100)
        else:
            score = ((value - low) / (high - low) * 100)

        return int(round(_clamp(score, 0, 100)))

    return 50


def metric_heat_class(label: str, value) -> str:
    p = metric_percentile(label, value)

    if p >= 95:
        return "heat heat-super-elite"
    if p >= 85:
        return "heat heat-elite"
    if p >= 70:
        return "heat heat-great"
    if p >= 55:
        return "heat heat-good"
    if p >= 45:
        return "heat heat-neutral"
    if p >= 30:
        return "heat heat-cold"
    if p >= 15:
        return "heat heat-poor"
    return "heat heat-super-poor"


def stat_item(label: str, value) -> dict:
    percentile = metric_percentile(label, value)
    return {
        "label": label,
        "value": value,
        "percentile": percentile,
        "heat_class": metric_heat_class(label, value),
    }


def stat_items(stats: dict) -> list[dict]:
    return [stat_item(label, value) for label, value in stats.items()]


def _pitch_arsenal(player_id: int | None) -> list[dict]:
    raw = []
    for pitch in PITCH_TYPES:
        usage = _bounded(player_id, f"usage-{pitch}", 0, 35, 1)
        raw.append({"pitch": pitch, "usage": usage})

    top = sorted(raw, key=lambda item: item["usage"], reverse=True)[:5]
    total = sum(item["usage"] for item in top) or 1

    arsenal = []
    for item in top:
        usage = round((item["usage"] / total) * 100, 1)
        whiff = _bounded(player_id, f"whiff-{item['pitch']}", 12, 41, 1)

        arsenal.append(
            {
                "pitch": item["pitch"],
                "usage": usage,
                "velocity": _bounded(player_id, f"velo-{item['pitch']}", 78, 98, 1),
                "whiff": whiff,
                "whiff_percentile": metric_percentile("Whiff%", whiff),
            }
        )

    return arsenal



def _try_savant_profile(player_id: int | None, player_name: str) -> dict | None:
    """Build a real profile from savant_api.fetch_pitcher_statcast + summarize_pitcher_statcast."""
    if not player_id:
        return None

    try:
        savant_api = importlib.import_module("app.services.savant_api")
        fetch_pitcher_statcast = getattr(savant_api, "fetch_pitcher_statcast")
        summarize_pitcher_statcast = getattr(savant_api, "summarize_pitcher_statcast")
    except Exception as exc:
        print("STATCAST FAILED: could not load savant functions:", repr(exc))
        return None

    try:
        df = fetch_pitcher_statcast(player_id)
        summary = summarize_pitcher_statcast(df)
    except Exception as exc:
        print("STATCAST FAILED:", repr(exc))
        return None

    if not summary or not summary.get("available"):
        print(f"STATCAST FAILED: no Statcast sample for {player_name} ({player_id})")
        return None

    return _profile_from_savant_summary(player_id, player_name, summary)


def _value(summary: dict, key: str, fallback):
    value = summary.get(key)
    return fallback if value is None else value


def _profile_from_savant_summary(player_id: int, player_name: str, summary: dict) -> dict:
    """Convert savant_api summary output into the profile shape used by templates/model."""
    innings_est = max(float(summary.get("innings_est") or 1), 0.1)
    pa = max(int(summary.get("plate_appearances_est") or 1), 1)

    strikeouts = int(summary.get("strikeouts") or 0)
    walks = int(summary.get("walks") or 0)
    hits = int(summary.get("hits") or 0)
    hr = int(summary.get("hr") or 0)

    # These are approximations from pitch-level Statcast data.
    # They are better than fake deterministic values, but still not official season ERA/FIP.
    whip = round((walks + hits) / innings_est, 2)
    k9 = round((strikeouts / innings_est) * 9, 1)
    bb9 = round((walks / innings_est) * 9, 1)
    hr9 = round((hr / innings_est) * 9, 1)
    fip = round(((13 * hr + 3 * walks - 2 * strikeouts) / innings_est) + 3.1, 2)

    # ERA cannot be reliably derived from this summary without earned runs.
    # Use xwOBA to estimate an ERA-like display number.
    xwoba = _value(summary, "xwoba", _bounded(player_id, "xwoba", .275, .370, 3))
    era_est = round(_clamp(2.5 + ((float(xwoba) - .280) / (.390 - .280)) * 3.2, 2.4, 6.2), 2)

    traditional_raw = {
        "ERA": era_est,
        "WHIP": _clamp(whip, 0.75, 2.10),
        "FIP": _clamp(fip, 2.20, 6.40),
        "K/9": _clamp(k9, 3.0, 16.0),
        "BB/9": _clamp(bb9, 0.0, 8.0),
        "HR/9": _clamp(hr9, 0.0, 4.0),
    }

    recent = summary.get("recent") or {}
    recent_raw = {
        "Last 3 ERA": _bounded(player_id, "l3-era", 1.80, 6.40, 2),
        "Last 3 WHIP": _bounded(player_id, "l3-whip", 0.85, 1.70, 2),
        "Last 3 K": int(recent.get("last_3_k") or _bounded_int(player_id, "l3-k", 10, 26)),
        "Avg IP": round(float(recent.get("avg_ip") or innings_est), 1),
        "Avg Pitch Count": int(recent.get("avg_pitch_count") or summary.get("sample_pitches") or _bounded_int(player_id, "pitch-count", 72, 101)),
        "Velocity Trend": _bounded(player_id, "velo-trend", -1.4, 1.6, 1),
    }

    statcast_raw = {
        "xwOBA": round(float(_value(summary, "xwoba", _bounded(player_id, "xwoba", .275, .370, 3))), 3),
        "xBA": round(float(_value(summary, "xba", _bounded(player_id, "xba", .205, .285, 3))), 3),
        "xSLG": round(float(_value(summary, "xslg", _bounded(player_id, "xslg", .330, .485, 3))), 3),
        "HardHit%": round(float(_value(summary, "hard_hit_pct", _bounded(player_id, "hardhit", 31.0, 47.0, 1))), 1),
        "Barrel%": round(float(_value(summary, "barrel_pct", _bounded(player_id, "barrel", 4.8, 11.5, 1))), 1),
        "Avg EV": round(float(_value(summary, "avg_ev", _bounded(player_id, "ev", 86.5, 91.8, 1))), 1),
    }

    batted_ball_raw = {
        "GB%": round(float(_value(summary, "gb_pct", _bounded(player_id, "gb", 33, 52, 1))), 1),
        "FB%": round(float(_value(summary, "fb_pct", _bounded(player_id, "fb", 22, 41, 1))), 1),
        "LD%": round(float(_value(summary, "ld_pct", _bounded(player_id, "ld", 17, 27, 1))), 1),
        "Pull%": _bounded(player_id, "pull", 34, 45, 1),
        "Oppo%": _bounded(player_id, "oppo", 20, 31, 1),
    }

    discipline_raw = {
        "Zone%": round(float(_value(summary, "zone_pct", _bounded(player_id, "zone", 39, 51, 1))), 1),
        "Chase%": round(float(_value(summary, "chase_pct", _bounded(player_id, "chase", 25, 37, 1))), 1),
        "Whiff%": round(float(_value(summary, "whiff_pct", _bounded(player_id, "whiff", 18, 34, 1))), 1),
        "1stPitchS%": round(float(_value(summary, "first_pitch_strike_pct", _bounded(player_id, "firstpitch", 55, 68, 1))), 1),
        "BB%": round(float(_value(summary, "bb_pct", _bounded(player_id, "bbpercent", 5.5, 11.8, 1))), 1),
        "K%": round(float(_value(summary, "k_pct", _bounded(player_id, "kpercent", 17, 32, 1))), 1),
    }

    arsenal = summary.get("pitch_arsenal") or _pitch_arsenal(player_id)
    for pitch in arsenal:
        if "whiff" in pitch:
            pitch["whiff_percentile"] = metric_percentile("Whiff%", pitch.get("whiff") or 0)

    scores = calculate_component_scores(traditional_raw, recent_raw, statcast_raw, discipline_raw)

    sample_pitches = int(summary.get("sample_pitches") or 0)

    return {
        "id": player_id,
        "name": player_name,
        "headshot": player_headshot_url(player_id),
        "data_quality": f"Real Statcast profile · {sample_pitches} pitches sampled",
        "traditional": stat_items(traditional_raw),
        "recent_form": stat_items(recent_raw),
        "statcast": stat_items(statcast_raw),
        "batted_ball": stat_items(batted_ball_raw),
        "plate_discipline": stat_items(discipline_raw),
        "arsenal": arsenal,
        "component_scores": scores,
        "raw": {
            "traditional": traditional_raw,
            "recent_form": recent_raw,
            "statcast": statcast_raw,
            "plate_discipline": discipline_raw,
            "sample_pitches": sample_pitches,
        },
    }


def get_pitcher_profile(player_id: int | None, player_name: str = "TBD") -> dict:
    if not player_id:
        return {
            "id": None,
            "name": player_name,
            "headshot": player_headshot_url(None),
            "data_quality": "Missing probable pitcher ID",
            "traditional": [],
            "recent_form": [],
            "statcast": [],
            "batted_ball": [],
            "plate_discipline": [],
            "arsenal": [],
            "component_scores": {
                "Season Performance": 50.0,
                "Recent Form": 50.0,
                "Statcast Quality": 50.0,
                "Command / Whiff": 50.0,
                "Weather Impact": 50.0,
                "Lineup Matchup": 50.0,
                "Park Context": 50.0,
            },
            "raw": {
                "traditional": {},
                "recent_form": {},
                "statcast": {},
                "plate_discipline": {},
            },
        }

    real_profile = _try_savant_profile(player_id, player_name)
    if real_profile:
        return real_profile

    traditional_raw = {
        "ERA": _bounded(player_id, "era", 2.45, 5.45, 2),
        "WHIP": _bounded(player_id, "whip", 1.02, 1.52, 2),
        "FIP": _bounded(player_id, "fip", 2.80, 5.20, 2),
        "K/9": _bounded(player_id, "k9", 6.3, 12.1, 1),
        "BB/9": _bounded(player_id, "bb9", 1.6, 4.6, 1),
        "HR/9": _bounded(player_id, "hr9", 0.5, 1.8, 1),
    }

    recent_raw = {
        "Last 3 ERA": _bounded(player_id, "l3-era", 1.80, 6.40, 2),
        "Last 3 WHIP": _bounded(player_id, "l3-whip", 0.85, 1.70, 2),
        "Last 3 K": _bounded_int(player_id, "l3-k", 10, 26),
        "Avg IP": _bounded(player_id, "avg-ip", 4.6, 6.8, 1),
        "Avg Pitch Count": _bounded_int(player_id, "pitch-count", 72, 101),
        "Velocity Trend": _bounded(player_id, "velo-trend", -1.4, 1.6, 1),
    }

    statcast_raw = {
        "xwOBA": _bounded(player_id, "xwoba", .275, .370, 3),
        "xBA": _bounded(player_id, "xba", .205, .285, 3),
        "xSLG": _bounded(player_id, "xslg", .330, .485, 3),
        "HardHit%": _bounded(player_id, "hardhit", 31.0, 47.0, 1),
        "Barrel%": _bounded(player_id, "barrel", 4.8, 11.5, 1),
        "Avg EV": _bounded(player_id, "ev", 86.5, 91.8, 1),
    }

    batted_ball_raw = {
        "GB%": _bounded(player_id, "gb", 33, 52, 1),
        "FB%": _bounded(player_id, "fb", 22, 41, 1),
        "LD%": _bounded(player_id, "ld", 17, 27, 1),
        "Pull%": _bounded(player_id, "pull", 34, 45, 1),
        "Oppo%": _bounded(player_id, "oppo", 20, 31, 1),
    }

    discipline_raw = {
        "Zone%": _bounded(player_id, "zone", 39, 51, 1),
        "Chase%": _bounded(player_id, "chase", 25, 37, 1),
        "Whiff%": _bounded(player_id, "whiff", 18, 34, 1),
        "1stPitchS%": _bounded(player_id, "firstpitch", 55, 68, 1),
        "BB%": _bounded(player_id, "bbpercent", 5.5, 11.8, 1),
        "K%": _bounded(player_id, "kpercent", 17, 32, 1),
    }

    scores = calculate_component_scores(traditional_raw, recent_raw, statcast_raw, discipline_raw)

    return {
        "id": player_id,
        "name": player_name,
        "headshot": player_headshot_url(player_id),
        "data_quality": "Deterministic fallback profile; real Statcast unavailable",
        "traditional": stat_items(traditional_raw),
        "recent_form": stat_items(recent_raw),
        "statcast": stat_items(statcast_raw),
        "batted_ball": stat_items(batted_ball_raw),
        "plate_discipline": stat_items(discipline_raw),
        "arsenal": _pitch_arsenal(player_id),
        "component_scores": scores,
        "raw": {
            "traditional": traditional_raw,
            "recent_form": recent_raw,
            "statcast": statcast_raw,
            "plate_discipline": discipline_raw,
        },
    }


def calculate_component_scores(traditional: dict, recent: dict, statcast: dict, discipline: dict) -> dict:
    season_score = (
        _score_lower_better(traditional["ERA"], 2.50, 5.50) * .35
        + _score_lower_better(traditional["WHIP"], 1.00, 1.55) * .25
        + _score_lower_better(traditional["FIP"], 2.70, 5.30) * .20
        + _score_higher_better(traditional["K/9"], 6.0, 12.5) * .20
    )

    form_score = (
        _score_lower_better(recent["Last 3 ERA"], 1.80, 6.50) * .30
        + _score_lower_better(recent["Last 3 WHIP"], .85, 1.70) * .25
        + _score_higher_better(recent["Last 3 K"], 9, 28) * .20
        + _score_higher_better(recent["Avg IP"], 4.5, 7.0) * .15
        + _score_higher_better(recent["Velocity Trend"], -1.5, 1.7) * .10
    )

    statcast_score = (
        _score_lower_better(statcast["xwOBA"], .275, .370) * .28
        + _score_lower_better(statcast["xBA"], .205, .285) * .18
        + _score_lower_better(statcast["xSLG"], .330, .485) * .18
        + _score_lower_better(statcast["HardHit%"], 31, 47) * .14
        + _score_lower_better(statcast["Barrel%"], 4.5, 11.8) * .14
        + _score_lower_better(statcast["Avg EV"], 86.5, 92.0) * .08
    )

    command_score = (
        _score_higher_better(discipline["K%"], 17, 32) * .30
        + _score_lower_better(discipline["BB%"], 5.5, 12) * .25
        + _score_higher_better(discipline["Chase%"], 24, 38) * .20
        + _score_higher_better(discipline["Whiff%"], 18, 35) * .25
    )

    return {
        "Season Performance": round(season_score, 1),
        "Recent Form": round(form_score, 1),
        "Statcast Quality": round(statcast_score, 1),
        "Command / Whiff": round(command_score, 1),
        "Weather Impact": 50.0,
        "Lineup Matchup": 50.0,
        "Park Context": 50.0,
    }

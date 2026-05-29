import hashlib
from app.services.player_assets import player_headshot_url


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
    try:
        value = float(value)
    except (TypeError, ValueError):
        return 50

    low, high, direction = METRIC_BOUNDS.get(label, (0, 100, "neutral"))

    if direction == "lower":
        score = _score_lower_better(value, low, high)
    elif direction == "higher":
        score = _score_higher_better(value, low, high)
    else:
        midpoint = (low + high) / 2
        spread = (high - low) / 2
        distance = abs(value - midpoint) / spread if spread else 0
        score = 50 + min(distance * 20, 20)

    return int(round(max(0, min(100, score))))


def metric_heat_class(label: str, value) -> str:
    p = metric_percentile(label, value)

    if p >= 90:
        return "heat heat-elite"
    if p >= 75:
        return "heat heat-great"
    if p >= 60:
        return "heat heat-good"
    if p >= 45:
        return "heat heat-neutral"
    if p >= 30:
        return "heat heat-cold"
    return "heat heat-poor"


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
        "data_quality": "MVP deterministic profile; real Statcast pipeline planned",
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

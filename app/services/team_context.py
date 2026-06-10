from __future__ import annotations

from datetime import date
import hashlib
import requests

from app.services.cache import read_json_cache, write_json_cache
from app.services.lineup_context import get_official_lineup


MLB_TEAM_STATS_URL = "https://statsapi.mlb.com/api/v1/teams/{team_id}/stats"
MLB_PEOPLE_URL = "https://statsapi.mlb.com/api/v1/people/{player_id}"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _stable_neutral_score(*parts) -> float:
    """Small deterministic nudge around average.

    Used only when the public endpoint does not provide the needed split.
    Keeps missing data from producing fake high-confidence edges.
    """
    raw = "-".join(str(part) for part in parts).encode("utf-8")
    value = int(hashlib.sha256(raw).hexdigest()[:8], 16) % 10000 / 10000
    return round(48 + (value * 4), 1)


def _safe_float(value, default: float | None = None) -> float | None:
    try:
        if value in (None, "", "-"):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _fetch_team_stats(team_id: int | None, group: str, ttl_hours: int = 6) -> dict:
    if not team_id:
        return {}

    cache_name = f"team_stats_{team_id}_{group}_{date.today().isoformat()}.json"
    cached = read_json_cache(cache_name, ttl_hours=ttl_hours)
    if cached is not None:
        return cached

    try:
        response = requests.get(
            MLB_TEAM_STATS_URL.format(team_id=team_id),
            params={"stats": "season", "group": group},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        write_json_cache(cache_name, data)
        return data
    except requests.RequestException:
        return {}


def _first_split_stat(data: dict) -> dict:
    try:
        return data.get("stats", [])[0].get("splits", [])[0].get("stat", {}) or {}
    except (IndexError, AttributeError):
        return {}


def _fetch_pitcher_hand(player_id: int | None, ttl_hours: int = 72) -> str | None:
    if not player_id:
        return None

    cache_name = f"pitcher_hand_{player_id}.json"
    cached = read_json_cache(cache_name, ttl_hours=ttl_hours)
    if cached is not None:
        return cached.get("pitch_hand")

    try:
        response = requests.get(MLB_PEOPLE_URL.format(player_id=player_id), timeout=8)
        response.raise_for_status()
        person = (response.json().get("people") or [{}])[0]
        hand = (person.get("pitchHand") or {}).get("code")
        data = {"pitch_hand": hand}
        write_json_cache(cache_name, data)
        return hand
    except requests.RequestException:
        return None


def get_bullpen_context(team_id: int | None, team_name: str = "Team") -> dict:
    """Return a pitcher-friendly bullpen/support score.

    MLB's public team season endpoint does not cleanly expose bullpen-only
    splits here, so this uses team pitching indicators as a conservative proxy.
    The summary calls this out instead of pretending it is a full bullpen model.
    """
    data = _fetch_team_stats(team_id, "pitching", ttl_hours=6)
    stat = _first_split_stat(data)

    era = _safe_float(stat.get("era"), 4.10)
    whip = _safe_float(stat.get("whip"), 1.28)
    k9 = _safe_float(stat.get("strikeoutsPer9Inn"), 8.4)
    bb9 = _safe_float(stat.get("walksPer9Inn"), 3.2)
    hr9 = _safe_float(stat.get("homeRunsPer9"), 1.1)

    if not stat:
        score = _stable_neutral_score(team_id, "bullpen")
        return {
            "available": False,
            "team": team_name,
            "bullpen_score": score,
            "summary": "Bullpen proxy unavailable; neutral team-support score used.",
            "metrics": {},
        }

    score = 50.0
    score += (4.10 - era) * 5.2
    score += (1.28 - whip) * 18.0
    score += (k9 - 8.4) * 1.5
    score += (3.2 - bb9) * 1.4
    score += (1.10 - hr9) * 5.0

    return {
        "available": True,
        "team": team_name,
        "bullpen_score": round(_clamp(score, 30, 70), 1),
        "summary": "Team pitching proxy used for bullpen/support context.",
        "metrics": {
            "ERA": era,
            "WHIP": whip,
            "K/9": k9,
            "BB/9": bb9,
            "HR/9": hr9,
        },
    }


def get_team_offense_vs_pitcher_hand_context(
    team_id: int | None,
    team_name: str = "Team",
    opposing_pitcher_id: int | None = None,
) -> dict:
    """Return offense support score against the opposing starter's hand.

    The current implementation uses live team hitting indicators and records
    the opposing pitcher's throwing hand when available. True L/R batting splits
    can be added later without changing the model contract.
    """
    hand = _fetch_pitcher_hand(opposing_pitcher_id)
    data = _fetch_team_stats(team_id, "hitting", ttl_hours=6)
    stat = _first_split_stat(data)

    avg = _safe_float(stat.get("avg"), 0.245)
    obp = _safe_float(stat.get("obp"), 0.315)
    slg = _safe_float(stat.get("slg"), 0.405)
    ops = _safe_float(stat.get("ops"), 0.720)
    runs = _safe_float(stat.get("runs"), None)
    games = _safe_float(stat.get("gamesPlayed"), None)

    if not stat:
        score = _stable_neutral_score(team_id, opposing_pitcher_id, "offense")
        return {
            "available": False,
            "team": team_name,
            "pitcher_hand": hand or "unknown",
            "offense_score": score,
            "summary": "Offense data unavailable; neutral run-support score used.",
            "metrics": {},
        }

    runs_per_game = (runs / games) if runs is not None and games else 4.4

    score = 50.0
    score += (ops - 0.720) * 80
    score += (obp - 0.315) * 65
    score += (slg - 0.405) * 45
    score += (avg - 0.245) * 35
    score += (runs_per_game - 4.4) * 2.2

    return {
        "available": True,
        "team": team_name,
        "pitcher_hand": hand or "unknown",
        "offense_score": round(_clamp(score, 30, 70), 1),
        "summary": f"Team offense context vs opposing starter hand: {hand or 'unknown'}.",
        "metrics": {
            "AVG": avg,
            "OBP": obp,
            "SLG": slg,
            "OPS": ops,
            "R/G": round(runs_per_game, 2),
        },
    }


def get_confirmed_lineup_strength_context(
    game_id: int | None,
    side: str,
    team_id: int | None = None,
    team_name: str = "Team",
) -> dict:
    """Score confirmed lineup availability conservatively.

    If no official lineup is posted, the model stays neutral. This prevents
    pregame unknowns from turning into fake confidence.
    """
    lineup = get_official_lineup(game_id, side) if game_id else []

    if not lineup:
        return {
            "available": False,
            "team": team_name,
            "lineup_strength_score": 50.0,
            "summary": "Official lineup not posted; neutral lineup score used.",
            "batters_confirmed": 0,
            "batters": [],
        }

    count = len(lineup)
    completeness = _clamp(count / 9, 0, 1)

    # Until individual hitter projections are added, a complete confirmed lineup
    # should improve confidence more than it changes the score.
    score = 48 + (completeness * 4)

    return {
        "available": True,
        "team": team_name,
        "lineup_strength_score": round(_clamp(score, 46, 54), 1),
        "summary": f"{count} confirmed hitters available from official boxscore.",
        "batters_confirmed": count,
        "batters": lineup[:9],
    }

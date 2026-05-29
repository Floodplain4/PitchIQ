from __future__ import annotations

import hashlib
import requests

from app.services.cache import read_json_cache, write_json_cache
from app.services.savant_api import fetch_batter_vs_pitcher, summarize_batter_vs_pitcher


MLB_BOXSCORE_URL = "https://statsapi.mlb.com/api/v1/game/{game_id}/boxscore"


def _stable_score(*parts) -> float:
    raw = "-".join(str(p) for p in parts).encode("utf-8")
    value = int(hashlib.sha256(raw).hexdigest()[:8], 16) % 10000 / 10000
    return round(42 + (value * 16), 1)


def get_official_lineup(game_id: int | None, side: str) -> list[dict]:
    """Return official batting order when MLB boxscore has it.

    side must be "home" or "away".
    Pregame lineups are often unavailable; this safely returns [].
    """
    if not game_id:
        return []

    cache_name = f"boxscore_{game_id}.json"
    data = read_json_cache(cache_name, ttl_hours=2)

    if data is None:
        try:
            response = requests.get(MLB_BOXSCORE_URL.format(game_id=game_id), timeout=10)
            response.raise_for_status()
            data = response.json()
            write_json_cache(cache_name, data)
        except requests.RequestException:
            return []

    team_data = data.get("teams", {}).get(side, {})
    players = team_data.get("players", {}) or {}
    batting_order = team_data.get("battingOrder", []) or []

    lineup = []

    for player_key in batting_order:
        player = players.get(f"ID{player_key}") or players.get(str(player_key)) or {}
        person = player.get("person", {}) or {}

        lineup.append(
            {
                "id": person.get("id") or player_key,
                "name": person.get("fullName", "Unknown Batter"),
                "position": player.get("position", {}).get("abbreviation", ""),
                "batting_order": player.get("battingOrder", ""),
            }
        )

    return lineup


def _score_bvp_summary(summary: dict) -> float:
    """Score from pitcher's perspective."""
    if not summary.get("available") or summary.get("pa", 0) < 3:
        return 50.0

    pa = max(summary.get("pa", 1), 1)
    k_rate = summary.get("strikeouts", 0) / pa
    bb_rate = summary.get("walks", 0) / pa
    hr_rate = summary.get("hr", 0) / pa
    hit_rate = summary.get("hits", 0) / pa
    xwoba = summary.get("xwoba")

    score = 50.0
    score += (k_rate - 0.22) * 35
    score -= (bb_rate - 0.08) * 30
    score -= (hr_rate) * 45
    score -= (hit_rate - 0.24) * 25

    if xwoba:
        score -= (xwoba - 0.320) * 80

    return round(max(20, min(80, score)), 1)


def get_lineup_matchup_context(
    pitcher_id: int | None,
    opposing_team_id: int | None,
    game_id: int | None = None,
    opposing_side: str | None = None,
) -> dict:
    if not pitcher_id or not opposing_team_id:
        return {
            "available": False,
            "lineup_score": 50.0,
            "summary": "Lineup matchup unavailable until pitcher/team IDs are available.",
            "sample_note": "Neutral placeholder.",
            "batters": [],
        }

    lineup = get_official_lineup(game_id, opposing_side) if game_id and opposing_side else []

    if not lineup:
        return {
            "available": False,
            "lineup_score": _stable_score(pitcher_id, opposing_team_id),
            "summary": "Official lineup not available yet. Using deterministic team matchup placeholder.",
            "sample_note": "Once lineups post, this will evaluate batter-vs-pitcher Statcast history.",
            "batters": [],
        }

    batter_rows = []
    scores = []

    for batter in lineup[:9]:
        df = fetch_batter_vs_pitcher(pitcher_id, batter.get("id"))
        summary = summarize_batter_vs_pitcher(df)
        score = _score_bvp_summary(summary)

        batter_rows.append(
            {
                "id": batter.get("id"),
                "name": batter.get("name"),
                "position": batter.get("position"),
                "score": score,
                **summary,
            }
        )

        scores.append(score)

    lineup_score = round(sum(scores) / len(scores), 1) if scores else 50.0
    available_count = sum(1 for row in batter_rows if row.get("available"))

    return {
        "available": available_count > 0,
        "lineup_score": lineup_score,
        "summary": f"Evaluated {len(batter_rows)} lineup spots; {available_count} had direct BvP Statcast samples.",
        "sample_note": "Small samples are weighted cautiously.",
        "batters": batter_rows,
    }

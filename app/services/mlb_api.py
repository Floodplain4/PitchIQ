from datetime import date
import requests

from app.services.team_assets import team_asset

MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"


def _record(team_block: dict) -> str:
    league_record = team_block.get("leagueRecord") or {}
    wins = league_record.get("wins")
    losses = league_record.get("losses")
    if wins is None or losses is None:
        return ""
    return f"{wins} - {losses}"


def _team_payload(team_block: dict) -> dict:
    team = team_block.get("team", {}) or {}
    team_id = team.get("id")
    asset = team_asset(team_id)

    return {
        "id": team_id,
        "name": team.get("name", "Unknown Team"),
        "abbr": asset["abbr"],
        "record": _record(team_block),
        "logo": asset["logo"],
        "primary": asset["primary"],
        "secondary": asset["secondary"],
        "probable_pitcher": team_block.get("probablePitcher", {}).get("fullName", "TBD"),
        "probable_pitcher_id": team_block.get("probablePitcher", {}).get("id"),
    }


def _game_payload(game: dict) -> dict:
    teams = game.get("teams", {})
    away = _team_payload(teams.get("away", {}))
    home = _team_payload(teams.get("home", {}))

    return {
        "game_id": game.get("gamePk"),
        "game_date": game.get("gameDate"),
        "status": game.get("status", {}).get("detailedState", "Unknown"),
        "venue": game.get("venue", {}).get("name", "Unknown Venue"),
        "away": away,
        "home": home,

        # Backward-compatible fields used by the current model/template.
        "away_team": away["name"],
        "home_team": home["name"],
        "away_pitcher": away["probable_pitcher"],
        "home_pitcher": home["probable_pitcher"],
        "away_pitcher_id": away["probable_pitcher_id"],
        "home_pitcher_id": home["probable_pitcher_id"],
    }


def get_todays_games() -> list[dict]:
    today = date.today().isoformat()

    params = {
        "sportId": 1,
        "date": today,
        "hydrate": "probablePitcher,team,venue",
    }

    try:
        response = requests.get(MLB_SCHEDULE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return []

    games = []

    for day in data.get("dates", []):
        for game in day.get("games", []):
            games.append(_game_payload(game))

    return games


def get_game_detail(game_id: int) -> dict:
    params = {
        "sportId": 1,
        "gamePk": game_id,
        "hydrate": "probablePitcher,team,venue",
    }

    try:
        response = requests.get(MLB_SCHEDULE_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return {"game_id": game_id, "error": "Could not load game detail."}

    for day in data.get("dates", []):
        for game in day.get("games", []):
            return _game_payload(game)

    return {"game_id": game_id, "error": "Game not found."}



MLB_LIVE_FEED_URL = "https://statsapi.mlb.com/api/v1.1/game/{game_id}/feed/live"


def get_live_game_state(game_id: int) -> dict:
    """Return a compact live-game payload for polling pages.

    This uses MLB's public live feed endpoint. It is intentionally defensive because
    live feed shape can vary by game state (pregame, in-progress, final).
    """
    try:
        response = requests.get(MLB_LIVE_FEED_URL.format(game_id=game_id), timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return {"game_id": game_id, "error": "Could not load live game feed."}

    game_data = data.get("gameData", {}) or {}
    live_data = data.get("liveData", {}) or {}
    linescore = live_data.get("linescore", {}) or {}
    plays = live_data.get("plays", {}) or {}
    current_play = plays.get("currentPlay", {}) or {}
    all_plays = plays.get("allPlays", []) or []

    teams = game_data.get("teams", {}) or {}
    away_team = teams.get("away", {}) or {}
    home_team = teams.get("home", {}) or {}

    away_asset = team_asset(away_team.get("id"))
    home_asset = team_asset(home_team.get("id"))

    offense = linescore.get("offense", {}) or {}
    defense = linescore.get("defense", {}) or {}

    current_count = current_play.get("count", {}) or {}
    result = current_play.get("result", {}) or {}
    matchup = current_play.get("matchup", {}) or {}

    recent_plays = []
    for play in list(reversed(all_plays))[:8]:
        play_result = play.get("result", {}) or {}
        play_about = play.get("about", {}) or {}
        play_matchup = play.get("matchup", {}) or {}
        recent_plays.append(
            {
                "inning": play_about.get("inning"),
                "half": play_about.get("halfInning"),
                "description": play_result.get("description") or play_result.get("event") or "",
                "batter": (play_matchup.get("batter") or {}).get("fullName", ""),
                "pitcher": (play_matchup.get("pitcher") or {}).get("fullName", ""),
            }
        )

    return {
        "game_id": game_id,
        "status": (game_data.get("status") or {}).get("detailedState", "Unknown"),
        "abstract_state": (game_data.get("status") or {}).get("abstractGameState", "Unknown"),
        "venue": (game_data.get("venue") or {}).get("name", ""),
        "away": {
            "id": away_team.get("id"),
            "name": away_team.get("name", "Away"),
            "abbr": away_asset["abbr"],
            "logo": away_asset["logo"],
            "primary": away_asset["primary"],
            "runs": (linescore.get("teams", {}).get("away", {}) or {}).get("runs", 0),
            "hits": (linescore.get("teams", {}).get("away", {}) or {}).get("hits", 0),
            "errors": (linescore.get("teams", {}).get("away", {}) or {}).get("errors", 0),
        },
        "home": {
            "id": home_team.get("id"),
            "name": home_team.get("name", "Home"),
            "abbr": home_asset["abbr"],
            "logo": home_asset["logo"],
            "primary": home_asset["primary"],
            "runs": (linescore.get("teams", {}).get("home", {}) or {}).get("runs", 0),
            "hits": (linescore.get("teams", {}).get("home", {}) or {}).get("hits", 0),
            "errors": (linescore.get("teams", {}).get("home", {}) or {}).get("errors", 0),
        },
        "inning": linescore.get("currentInning"),
        "inning_ordinal": linescore.get("currentInningOrdinal"),
        "half_inning": linescore.get("inningHalf"),
        "outs": linescore.get("outs", 0),
        "balls": current_count.get("balls", 0),
        "strikes": current_count.get("strikes", 0),
        "current_batter": (matchup.get("batter") or {}).get("fullName", ""),
        "current_pitcher": (matchup.get("pitcher") or {}).get("fullName", ""),
        "last_event": result.get("event", ""),
        "last_description": result.get("description", ""),
        "on_first": bool(offense.get("first")),
        "on_second": bool(offense.get("second")),
        "on_third": bool(offense.get("third")),
        "defense_pitcher": (defense.get("pitcher") or {}).get("fullName", ""),
        "recent_plays": recent_plays,
    }

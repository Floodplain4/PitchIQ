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

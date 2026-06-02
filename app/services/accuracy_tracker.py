from __future__ import annotations

import csv
from datetime import datetime, date
from pathlib import Path
from typing import Any

import requests

TRACKING_DIR = Path("data")
TRACKING_DIR.mkdir(exist_ok=True)

PREDICTIONS_FILE = TRACKING_DIR / "prediction_log.csv"
MLB_SCHEDULE_URL = "https://statsapi.mlb.com/api/v1/schedule"

FIELDNAMES = [
    "timestamp",
    "game_id",
    "game_date",
    "away_team",
    "home_team",
    "away_score",
    "home_score",
    "predicted_side",
    "predicted_team",
    "edge_amount",
    "away_pitchiq",
    "home_pitchiq",
    "away_win_probability",
    "home_win_probability",
    "actual_away_runs",
    "actual_home_runs",
    "actual_winner",
    "correct_winner",
    "graded_at",
]


def _ensure_file() -> None:
    if PREDICTIONS_FILE.exists():
        return

    with PREDICTIONS_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()


def _read_rows() -> list[dict[str, str]]:
    _ensure_file()
    with PREDICTIONS_FILE.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_rows(rows: list[dict[str, Any]]) -> None:
    _ensure_file()
    with PREDICTIONS_FILE.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})


def _prediction_side(prediction: dict) -> tuple[str, str]:
    away_score = float(prediction.get("away_pitchiq_score", 50))
    home_score = float(prediction.get("home_pitchiq_score", 50))

    if abs(home_score - away_score) < 2:
        return "even", "No clear pitching edge"

    if home_score > away_score:
        return "home", prediction.get("matchup_lean", {}).get("team", "Home Team")

    return "away", prediction.get("matchup_lean", {}).get("team", "Away Team")


def record_prediction(game: dict, prediction: dict) -> None:
    """Log one pregame prediction if the game has not already been logged."""
    if not game or not prediction:
        return

    game_id = str(game.get("game_id", ""))
    if not game_id:
        return

    rows = _read_rows()
    if any(row.get("game_id") == game_id for row in rows):
        return

    side, team = _prediction_side(prediction)

    rows.append(
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "game_id": game_id,
            "game_date": game.get("game_date", ""),
            "away_team": game.get("away", {}).get("name", game.get("away_team", "")),
            "home_team": game.get("home", {}).get("name", game.get("home_team", "")),
            "away_score": "",
            "home_score": "",
            "predicted_side": side,
            "predicted_team": team,
            "edge_amount": prediction.get("edge_amount", ""),
            "away_pitchiq": prediction.get("away_pitchiq_score", ""),
            "home_pitchiq": prediction.get("home_pitchiq_score", ""),
            "away_win_probability": prediction.get("away_win_probability", ""),
            "home_win_probability": prediction.get("home_win_probability", ""),
            "actual_away_runs": "",
            "actual_home_runs": "",
            "actual_winner": "",
            "correct_winner": "",
            "graded_at": "",
        }
    )

    _write_rows(rows)


def _fetch_final_score(game_id: str) -> dict | None:
    try:
        response = requests.get(
            MLB_SCHEDULE_URL,
            params={"sportId": 1, "gamePk": game_id},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException:
        return None

    for day in data.get("dates", []):
        for game in day.get("games", []):
            status = (game.get("status", {}) or {}).get("detailedState", "")
            coded_state = (game.get("status", {}) or {}).get("codedGameState", "")
            if status != "Final" and coded_state != "F":
                return None

            teams = game.get("teams", {})
            away = teams.get("away", {})
            home = teams.get("home", {})

            return {
                "away_runs": away.get("score"),
                "home_runs": home.get("score"),
            }

    return None


def grade_predictions() -> dict:
    """Update ungraded logged predictions with final scores when available."""
    rows = _read_rows()
    graded_now = 0

    for row in rows:
        if row.get("graded_at"):
            continue

        final_score = _fetch_final_score(row.get("game_id", ""))
        if not final_score:
            continue

        away_runs = final_score.get("away_runs")
        home_runs = final_score.get("home_runs")
        if away_runs is None or home_runs is None:
            continue

        actual_winner = "away" if int(away_runs) > int(home_runs) else "home"
        predicted_side = row.get("predicted_side", "")

        row["actual_away_runs"] = away_runs
        row["actual_home_runs"] = home_runs
        row["actual_winner"] = actual_winner
        row["correct_winner"] = (
            "" if predicted_side == "even" else str(predicted_side == actual_winner)
        )
        row["graded_at"] = datetime.now().isoformat(timespec="seconds")
        graded_now += 1

    _write_rows(rows)
    return summary_stats(extra={"graded_now": graded_now})


def summary_stats(extra: dict | None = None) -> dict:
    rows = _read_rows()

    graded = [r for r in rows if r.get("graded_at")]
    actionable = [r for r in graded if r.get("predicted_side") in {"away", "home"}]
    correct = [r for r in actionable if r.get("correct_winner") == "True"]

    by_bucket = {
        "slight": {"games": 0, "correct": 0},
        "clear": {"games": 0, "correct": 0},
    }

    for row in actionable:
        try:
            edge = float(row.get("edge_amount") or 0)
        except ValueError:
            edge = 0

        bucket = "clear" if edge >= 6 else "slight"
        by_bucket[bucket]["games"] += 1
        if row.get("correct_winner") == "True":
            by_bucket[bucket]["correct"] += 1

    stats = {
        "total_logged": len(rows),
        "graded_games": len(graded),
        "actionable_games": len(actionable),
        "correct": len(correct),
        "accuracy": round((len(correct) / len(actionable)) * 100, 1) if actionable else None,
        "by_bucket": by_bucket,
        "recent_rows": list(reversed(rows[-25:])),
    }

    if extra:
        stats.update(extra)

    return stats

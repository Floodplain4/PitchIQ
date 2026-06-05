from __future__ import annotations

from datetime import datetime, timedelta
import gc

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app.services.mlb_api import get_todays_games, get_game_detail
from app.services.model import build_matchup_prediction
from app.services.ai_explanations import generate_matchup_explanation
from app.services.accuracy_tracker import record_prediction, grade_predictions, summary_stats

app = FastAPI(title="PitchIQ - MLB Pitching Matchup Analyzer")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

_HOME_CACHE = {"expires": datetime.min, "games": []}
HOME_CACHE_SECONDS = 900
MAX_HOMEPAGE_GAMES = 20


def _compact_home_prediction(prediction: dict | None) -> dict | None:
    if not prediction:
        return None

    lean = prediction.get("matchup_lean") or {}

    return {
        "matchup_lean": {
            "side": lean.get("side", "even"),
            "team": lean.get("team", "No clear pitching edge"),
            "abbr": lean.get("abbr", "EVEN"),
            "score_edge": lean.get("score_edge", 0),
            "strength": lean.get("strength", "No"),
            "logo": lean.get("logo", ""),
            "color": lean.get("color", "#64748b"),
            "summary": lean.get("summary", "No clear pitching edge"),
        },
        "away_pitchiq_score": prediction.get("away_pitchiq_score", 50),
        "home_pitchiq_score": prediction.get("home_pitchiq_score", 50),
    }


def _safe_home_prediction(game: dict) -> dict | None:
    try:
        full_prediction = build_matchup_prediction(game)
        compact = _compact_home_prediction(full_prediction)
        del full_prediction
        gc.collect()
        return compact
    except Exception as exc:
        print("=" * 80)
        print("PitchIQ homepage prediction failed")
        print("Game:", game.get("away_team"), "@", game.get("home_team"))
        print("Game ID:", game.get("game_id"))
        print("Error:", repr(exc))
        print("=" * 80)
        gc.collect()
        return None


def _build_home_games() -> list[dict]:
    games = get_todays_games()[:MAX_HOMEPAGE_GAMES]
    enriched_games = []

    for game in games:
        game["prediction"] = _safe_home_prediction(game)
        enriched_games.append(game)

    gc.collect()
    return enriched_games

@app.head("/")
def health_check():
    return None

@app.get("/")
def home(request: Request):
    now = datetime.now()

    if now >= _HOME_CACHE["expires"]:
        _HOME_CACHE["games"] = _build_home_games()
        _HOME_CACHE["expires"] = now + timedelta(seconds=HOME_CACHE_SECONDS)

    return templates.TemplateResponse(
        request,
        "index.html",
        {"games": _HOME_CACHE["games"]},
    )


@app.get("/matchup/{game_id}")
def matchup_detail(request: Request, game_id: int):
    game = get_game_detail(game_id)
    prediction = build_matchup_prediction(game)
    record_prediction(game, prediction)
    ai_summary = generate_matchup_explanation(game, prediction)

    return templates.TemplateResponse(
        request,
        "matchup.html",
        {"game": game, "prediction": prediction, "ai_summary": ai_summary},
    )


@app.get("/about-model")
def about_model(request: Request):
    return templates.TemplateResponse(request, "about_model.html", {})


@app.get("/accuracy")
def accuracy_page(request: Request):
    return templates.TemplateResponse(
        request,
        "accuracy.html",
        {"stats": summary_stats()},
    )


@app.post("/accuracy/grade")
def accuracy_grade(request: Request):
    stats = grade_predictions()
    return templates.TemplateResponse(
        request,
        "accuracy.html",
        {"stats": stats},
    )

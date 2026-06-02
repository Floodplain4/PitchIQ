from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app.services.mlb_api import get_todays_games, get_game_detail
from app.services.model import build_matchup_prediction
from app.services.ai_explanations import generate_matchup_explanation


app = FastAPI(title="PitchIQ - MLB Pitching Matchup Analyzer")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# Render free tier has a 512MB memory limit. The homepage gets expensive if it
# builds full Statcast/weather/lineup predictions for every MLB game at once.
# Keep a small in-process cache and limit homepage prediction work. Full detail
# is still calculated when someone opens one matchup page.
_HOME_CACHE = {
    "expires": datetime.min,
    "games": [],
}

HOME_CACHE_SECONDS = 900
MAX_HOMEPAGE_PREDICTIONS = 8


def _safe_prediction(game: dict) -> dict | None:
    try:
        return build_matchup_prediction(game)
    except Exception:
        return None


def _build_home_games() -> list[dict]:
    games = get_todays_games()
    enriched_games = []

    for index, game in enumerate(games):
        if index < MAX_HOMEPAGE_PREDICTIONS:
            game["prediction"] = _safe_prediction(game)
        else:
            game["prediction"] = None

        enriched_games.append(game)

    return enriched_games


@app.get("/")
def home(request: Request):
    now = datetime.now()

    if now >= _HOME_CACHE["expires"]:
        _HOME_CACHE["games"] = _build_home_games()
        _HOME_CACHE["expires"] = now + timedelta(seconds=HOME_CACHE_SECONDS)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "games": _HOME_CACHE["games"],
            "homepage_prediction_limit": MAX_HOMEPAGE_PREDICTIONS,
        },
    )


@app.get("/matchup/{game_id}")
def matchup_detail(request: Request, game_id: int):
    game = get_game_detail(game_id)

    if game.get("error"):
        return templates.TemplateResponse(
            request,
            "matchup.html",
            {"game": game, "prediction": None, "ai_summary": None},
        )

    prediction = build_matchup_prediction(game)
    ai_summary = generate_matchup_explanation(game, prediction)

    return templates.TemplateResponse(
        request,
        "matchup.html",
        {"game": game, "prediction": prediction, "ai_summary": ai_summary},
    )


@app.get("/about-model")
def about_model(request: Request):
    return templates.TemplateResponse(request, "about_model.html", {})

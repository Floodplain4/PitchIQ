from __future__ import annotations

from datetime import datetime, timedelta
import gc

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app.services.mlb_api import get_todays_games, get_game_detail
from app.services.model import build_matchup_prediction
from app.services.ai_explanations import generate_matchup_explanation
from app.services.accuracy_tracker import record_prediction, grade_predictions, summary_stats
from app.services.cache import read_json_cache, write_json_cache

app = FastAPI(title="PitchIQ - MLB Pitching Matchup Analyzer")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

_HOME_CACHE = {"expires": datetime.min, "games": []}
HOME_CACHE_SECONDS = 1800
HOME_STALE_CACHE_HOURS = 12
HOME_CACHE_FILE = "home_games_predictions.json"
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
    """Build the expensive prediction payload for the homepage.

    This calls Statcast/weather/lineup helpers through build_matchup_prediction,
    so it should never block a first page render when the cache is cold.
    """
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

def _build_home_game_shells() -> list[dict]:
    """Fast fallback: show today's games immediately without predictions."""
    games = get_todays_games()[:MAX_HOMEPAGE_GAMES]
    for game in games:
        game.setdefault("prediction", None)
    return games


def _refresh_home_cache() -> None:
    """Refresh both memory and disk cache after the response is sent."""
    try:
        games = _build_home_games()
        _HOME_CACHE["games"] = games
        _HOME_CACHE["expires"] = datetime.now() + timedelta(seconds=HOME_CACHE_SECONDS)
        write_json_cache(HOME_CACHE_FILE, games)
    except Exception as exc:
        print("PitchIQ home cache refresh failed:", repr(exc))
    finally:
        gc.collect()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/")
def home(request: Request, background_tasks: BackgroundTasks):
    now = datetime.now()

    # Fast path: warm in-memory cache.
    if _HOME_CACHE["games"] and now < _HOME_CACHE["expires"]:
        return templates.TemplateResponse(request, "index.html", {"games": _HOME_CACHE["games"]})

    # Render restarts clear memory. Use disk cache so the first request after a
    # restart is still fast, then refresh in the background.
    disk_games = read_json_cache(HOME_CACHE_FILE, ttl_hours=HOME_STALE_CACHE_HOURS)
    if disk_games:
        _HOME_CACHE["games"] = disk_games
        _HOME_CACHE["expires"] = now + timedelta(seconds=HOME_CACHE_SECONDS)
        background_tasks.add_task(_refresh_home_cache)
        return templates.TemplateResponse(request, "index.html", {"games": disk_games})

    # Last resort: render the page quickly with schedule-only cards and build
    # predictions after the response. This avoids 20+ second homepage loads.
    games = _build_home_game_shells()
    background_tasks.add_task(_refresh_home_cache)
    return templates.TemplateResponse(request, "index.html", {"games": games})


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

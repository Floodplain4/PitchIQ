from __future__ import annotations

from datetime import datetime, timedelta, date
import gc
import json
import threading
import traceback
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app.services.mlb_api import get_todays_games, get_game_detail
from app.services.model import build_matchup_prediction
from app.services.ai_explanations import generate_matchup_explanation
from app.services.accuracy_tracker import record_prediction, grade_predictions, summary_stats

app = FastAPI(title="PitchIQ - MLB Pitching Matchup Analyzer")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

# Homepage strategy:
# - Never block the first page render on Statcast/weather/model calls.
# - Show schedule cards immediately.
# - Read previously calculated previews from disk.
# - Warm missing previews in a background thread and save after every game.
# This makes PitchIQ feel fast while still supporting a richer 10-12 game preview board.
CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)
HOMEPAGE_PREVIEW_CACHE = CACHE_DIR / "homepage_predictions.json"
HOMEPAGE_PREVIEW_LIMIT = 12
HOMEPAGE_CACHE_TTL_SECONDS = 60 * 30
HOMEPAGE_REFRESH_BATCH_SIZE = 4

_REFRESH_LOCK = threading.Lock()
_REFRESHING = False
_REFRESH_STARTED_AT: str | None = None
_LAST_REFRESH_ERROR: str | None = None


def _today_key() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _read_preview_cache() -> dict:
    if not HOMEPAGE_PREVIEW_CACHE.exists():
        return {"date": _today_key(), "updated_at": "", "predictions": {}}

    try:
        data = json.loads(HOMEPAGE_PREVIEW_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {"date": _today_key(), "updated_at": "", "predictions": {}}

    if data.get("date") != _today_key():
        return {"date": _today_key(), "updated_at": "", "predictions": {}}

    data.setdefault("predictions", {})
    return data


def _write_preview_cache(data: dict) -> None:
    data["date"] = _today_key()
    data["updated_at"] = _now_iso()
    data.setdefault("predictions", {})

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=str(CACHE_DIR), suffix=".tmp") as tmp:
        json.dump(data, tmp, indent=2)
        tmp_path = Path(tmp.name)
    tmp_path.replace(HOMEPAGE_PREVIEW_CACHE)


def _cache_is_fresh(cache_data: dict) -> bool:
    updated_at = cache_data.get("updated_at")
    if not updated_at:
        return False
    try:
        updated = datetime.fromisoformat(updated_at)
    except ValueError:
        return False
    return datetime.now() - updated < timedelta(seconds=HOMEPAGE_CACHE_TTL_SECONDS)


def _game_key(game: dict) -> str:
    return str(game.get("game_id") or "")


def _component_edge(prediction: dict, label: str) -> dict:
    lean = prediction.get("matchup_lean") or {}
    for row in prediction.get("score_breakdown", []) or []:
        if row.get("label") == label:
            edge = float(row.get("edge") or 0)
            if abs(edge) < 0.1:
                return {"label": label, "team": "Even", "abbr": "EVEN", "edge": 0}
            if edge > 0:
                # score_breakdown edge is home - away
                return {
                    "label": label,
                    "team": prediction.get("home_profile", {}).get("team", "Home"),
                    "abbr": lean.get("abbr") if lean.get("side") == "home" else "HOME",
                    "edge": round(abs(edge), 1),
                }
            return {
                "label": label,
                "team": prediction.get("away_profile", {}).get("team", "Away"),
                "abbr": lean.get("abbr") if lean.get("side") == "away" else "AWAY",
                "edge": round(abs(edge), 1),
            }
    return {"label": label, "team": "Even", "abbr": "EVEN", "edge": 0}


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
        "away_win_probability": prediction.get("away_win_probability", 50),
        "home_win_probability": prediction.get("home_win_probability", 50),
        "expected_away_pitcher_innings": prediction.get("expected_away_pitcher_innings"),
        "expected_home_pitcher_innings": prediction.get("expected_home_pitcher_innings"),
        "away_strikeout_projection": prediction.get("away_strikeout_projection"),
        "home_strikeout_projection": prediction.get("home_strikeout_projection"),
        "away_quality_start_probability": prediction.get("away_quality_start_probability"),
        "home_quality_start_probability": prediction.get("home_quality_start_probability"),
        "confidence": prediction.get("confidence", ""),
        "statcast_edge": _component_edge(prediction, "Statcast Quality"),
        "command_edge": _component_edge(prediction, "Command / Whiff"),
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
        traceback.print_exc()
        print("=" * 80)
        gc.collect()
        return None


def _refresh_homepage_predictions_worker(games: list[dict]) -> None:
    global _REFRESHING, _REFRESH_STARTED_AT, _LAST_REFRESH_ERROR

    try:
        cache_data = _read_preview_cache()
        predictions = cache_data.setdefault("predictions", {})

        for idx, game in enumerate(games[:HOMEPAGE_PREVIEW_LIMIT], start=1):
            key = _game_key(game)
            if not key:
                continue

            # Keep existing fresh prediction entries so a refresh does not make the page look empty.
            if predictions.get(key) and _cache_is_fresh(cache_data):
                continue

            prediction = _safe_home_prediction(dict(game))
            if prediction:
                predictions[key] = prediction
                _write_preview_cache(cache_data)

            if idx % HOMEPAGE_REFRESH_BATCH_SIZE == 0:
                gc.collect()

        _write_preview_cache(cache_data)
        _LAST_REFRESH_ERROR = None
    except Exception as exc:
        _LAST_REFRESH_ERROR = repr(exc)
        print("Homepage prediction refresh failed:", repr(exc))
        traceback.print_exc()
    finally:
        with _REFRESH_LOCK:
            _REFRESHING = False
            _REFRESH_STARTED_AT = None
        gc.collect()


def _start_refresh_if_needed(games: list[dict], cache_data: dict, force: bool = False) -> None:
    global _REFRESHING, _REFRESH_STARTED_AT

    preview_games = games[:HOMEPAGE_PREVIEW_LIMIT]
    predictions = cache_data.get("predictions", {}) or {}
    required_ids = [_game_key(game) for game in preview_games if _game_key(game)]
    ready_count = sum(1 for game_id in required_ids if predictions.get(game_id))
    stale = not _cache_is_fresh(cache_data)
    missing = ready_count < len(required_ids)

    if not force and not stale and not missing:
        return

    with _REFRESH_LOCK:
        if _REFRESHING:
            return
        _REFRESHING = True
        _REFRESH_STARTED_AT = _now_iso()

    thread = threading.Thread(
        target=_refresh_homepage_predictions_worker,
        args=([dict(game) for game in preview_games],),
        daemon=True,
    )
    thread.start()


def _merge_home_games(games: list[dict], cache_data: dict) -> list[dict]:
    predictions = cache_data.get("predictions", {}) or {}
    enriched = []

    for idx, game in enumerate(games):
        item = dict(game)
        key = _game_key(item)
        item["prediction"] = predictions.get(key)
        item["preview_state"] = "ready" if item["prediction"] else ("warming" if idx < HOMEPAGE_PREVIEW_LIMIT else "detail_only")
        enriched.append(item)

    return enriched


def _cache_meta(games: list[dict], cache_data: dict) -> dict:
    preview_games = games[:HOMEPAGE_PREVIEW_LIMIT]
    predictions = cache_data.get("predictions", {}) or {}
    required_ids = [_game_key(game) for game in preview_games if _game_key(game)]
    ready_count = sum(1 for game_id in required_ids if predictions.get(game_id))

    return {
        "updated_at": cache_data.get("updated_at", ""),
        "is_fresh": _cache_is_fresh(cache_data),
        "refreshing": _REFRESHING,
        "refresh_started_at": _REFRESH_STARTED_AT,
        "last_error": _LAST_REFRESH_ERROR,
        "preview_limit": HOMEPAGE_PREVIEW_LIMIT,
        "ready_count": ready_count,
        "total_preview_count": len(required_ids),
    }


@app.get("/")
def home(request: Request):
    games = get_todays_games()
    cache_data = _read_preview_cache()
    _start_refresh_if_needed(games, cache_data)
    enriched_games = _merge_home_games(games, cache_data)

    return templates.TemplateResponse(
        request,
        "index.html",
        {"games": enriched_games, "cache_meta": _cache_meta(games, cache_data)},
    )


@app.get("/api/homepage-status")
def homepage_status():
    games = get_todays_games()
    cache_data = _read_preview_cache()
    return JSONResponse(_cache_meta(games, cache_data))


@app.post("/refresh-homepage")
def refresh_homepage():
    games = get_todays_games()
    cache_data = _read_preview_cache()
    _start_refresh_if_needed(games, cache_data, force=True)
    return RedirectResponse("/", status_code=303)


@app.get("/health")
def health():
    return {"status": "ok"}


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

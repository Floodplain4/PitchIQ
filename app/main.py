from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app.services.mlb_api import get_todays_games, get_game_detail, get_live_game_state
from app.services.model import build_matchup_prediction
from app.services.ai_explanations import generate_matchup_explanation

app = FastAPI(title="PitchIQ - MLB Pitching Matchup Analyzer")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/")
def home(request: Request):
    games = get_todays_games()
    enriched_games = []
    for game in games:
        try:
            game["prediction"] = build_matchup_prediction(game)
        except Exception:
            game["prediction"] = None
        enriched_games.append(game)
    return templates.TemplateResponse(request, "index.html", {"games": enriched_games})


@app.get("/matchup/{game_id}")
def matchup_detail(request: Request, game_id: int):
    game = get_game_detail(game_id)
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



@app.get("/live/{game_id}")
def live_game(request: Request, game_id: int):
    game = get_game_detail(game_id)
    live = get_live_game_state(game_id)
    prediction = build_matchup_prediction(game)
    return templates.TemplateResponse(
        request,
        "live_game.html",
        {"game": game, "live": live, "prediction": prediction},
    )


@app.get("/api/live/{game_id}")
def live_game_api(game_id: int):
    return get_live_game_state(game_id)

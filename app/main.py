from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from app.services.mlb_api import get_todays_games, get_game_detail
from app.services.model import build_matchup_prediction

app = FastAPI(title="PitchIQ - MLB Pitching Matchup Analyzer")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


@app.get("/")
def home(request: Request):
    games = get_todays_games()
    return templates.TemplateResponse(request, "index.html", {"games": games})


@app.get("/matchup/{game_id}")
def matchup_detail(request: Request, game_id: int):
    game = get_game_detail(game_id)
    prediction = build_matchup_prediction(game)
    return templates.TemplateResponse(
        request,
        "matchup.html",
        {"game": game, "prediction": prediction},
    )


@app.get("/about-model")
def about_model(request: Request):
    return templates.TemplateResponse(request, "about_model.html", {})

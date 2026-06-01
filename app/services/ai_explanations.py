from __future__ import annotations

import json
import os
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


API_VERSIONS = ["v1beta", "v1"]
PREFERRED_MODEL_KEYWORDS = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "flash",
    "pro",
]


def _get_gemini_api_key() -> str | None:
    return (
        os.getenv("GEMINI_API_KEY")
        or os.getenv("GOOGLE_API_KEY")
        or os.getenv("GOOGLE_GENAI_API_KEY")
    )


def _list_models(api_key: str) -> list[tuple[str, str]]:
    """Return [(api_version, model_name)] for models that support generateContent."""
    usable = []

    for version in API_VERSIONS:
        url = f"https://generativelanguage.googleapis.com/{version}/models"
        try:
            response = requests.get(url, params={"key": api_key}, timeout=10)
            response.raise_for_status()
            data = response.json()
        except Exception:
            continue

        for model in data.get("models", []):
            name = model.get("name", "")
            methods = model.get("supportedGenerationMethods", []) or []
            if name and "generateContent" in methods:
                usable.append((version, name))

    def rank(item: tuple[str, str]) -> int:
        _, name = item
        lower = name.lower()
        for i, keyword in enumerate(PREFERRED_MODEL_KEYWORDS):
            if keyword in lower:
                return i
        return 99

    return sorted(usable, key=rank)


def _fallback_model_candidates() -> list[tuple[str, str]]:
    return [
        ("v1beta", "models/gemini-2.5-flash"),
        ("v1beta", "models/gemini-2.0-flash"),
        ("v1", "models/gemini-2.5-flash"),
        ("v1", "models/gemini-2.0-flash"),
        ("v1beta", "models/gemini-1.5-flash"),
        ("v1", "models/gemini-1.5-flash"),
    ]


def _generate_url(api_version: str, model_name: str) -> str:
    if not model_name.startswith("models/"):
        model_name = f"models/{model_name}"
    return f"https://generativelanguage.googleapis.com/{api_version}/{model_name}:generateContent"


def build_ai_context(game: dict, prediction: dict) -> dict:
    away = game.get("away", {}) or {}
    home = game.get("home", {}) or {}

    return {
        "game": {
            "away_team": away.get("name"),
            "home_team": home.get("name"),
            "away_record": away.get("record"),
            "home_record": home.get("record"),
            "venue": game.get("venue"),
            "status": game.get("status"),
        },
        "pitchers": {
            "away": {
                "name": game.get("away_pitcher"),
                "pitchiq": prediction.get("away_pitchiq_score"),
                "win_probability": prediction.get("away_win_probability"),
                "expected_ip": prediction.get("expected_away_pitcher_innings"),
                "k_projection": prediction.get("away_strikeout_projection"),
                "quality_start_probability": prediction.get("away_quality_start_probability"),
                "profile_reliability": prediction.get("away_profile_reliability"),
                "data_quality": prediction.get("away_profile", {}).get("data_quality"),
            },
            "home": {
                "name": game.get("home_pitcher"),
                "pitchiq": prediction.get("home_pitchiq_score"),
                "win_probability": prediction.get("home_win_probability"),
                "expected_ip": prediction.get("expected_home_pitcher_innings"),
                "k_projection": prediction.get("home_strikeout_projection"),
                "quality_start_probability": prediction.get("home_quality_start_probability"),
                "profile_reliability": prediction.get("home_profile_reliability"),
                "data_quality": prediction.get("home_profile", {}).get("data_quality"),
            },
        },
        "matchup": {
            "pitcher_advantage": prediction.get("pitcher_advantage"),
            "edge_amount": prediction.get("edge_amount"),
            "confidence": prediction.get("confidence"),
            "lean": prediction.get("matchup_lean", {}),
        },
        "context": {
            "park": prediction.get("venue_context", {}),
            "away_weather": prediction.get("away_weather", {}),
            "home_weather": prediction.get("home_weather", {}),
            "away_lineup": prediction.get("away_lineup", {}),
            "home_lineup": prediction.get("home_lineup", {}),
        },
        "score_breakdown": prediction.get("score_breakdown", []),
    }


def fallback_explanation(game: dict, prediction: dict, reason: str = "") -> dict:
    lean = prediction.get("matchup_lean", {}) or {}
    away = game.get("away", {}) or {}
    home = game.get("home", {}) or {}

    warnings = []
    away_rel = prediction.get("away_profile_reliability")
    home_rel = prediction.get("home_profile_reliability")

    if away_rel is not None and away_rel < 0.55:
        warnings.append(f"{game.get('away_pitcher', 'Away pitcher')} has a limited Statcast sample.")
    if home_rel is not None and home_rel < 0.55:
        warnings.append(f"{game.get('home_pitcher', 'Home pitcher')} has a limited Statcast sample.")

    if prediction.get("expected_away_pitcher_innings", 5) < 4.2:
        warnings.append(f"{game.get('away_pitcher', 'Away pitcher')} projects for a short workload.")
    if prediction.get("expected_home_pitcher_innings", 5) < 4.2:
        warnings.append(f"{game.get('home_pitcher', 'Home pitcher')} projects for a short workload.")

    if not warnings:
        warnings.append("No major model warnings detected, but PitchIQ is still pitcher-focused and not a sportsbook line.")

    return {
        "available": False,
        "headline": lean.get("summary") or f"{prediction.get('pitcher_advantage', 'No clear edge')} has the current PitchIQ edge.",
        "summary": (
            f"PitchIQ gives {prediction.get('pitcher_advantage', 'the matchup')} a "
            f"{prediction.get('edge_amount', 0)} point pitcher advantage. "
            f"The game probability remains conservative because the model does not fully include offense, bullpen, defense, injuries, or betting market data."
        ),
        "key_factors": [
            f"{away.get('abbr', 'Away')} PitchIQ: {prediction.get('away_pitchiq_score')}",
            f"{home.get('abbr', 'Home')} PitchIQ: {prediction.get('home_pitchiq_score')}",
            f"Confidence: {prediction.get('confidence')}",
        ],
        "warnings": warnings,
        "reason": reason,
    }


def generate_matchup_explanation(game: dict, prediction: dict) -> dict:
    api_key = _get_gemini_api_key()

    if not api_key:
        return fallback_explanation(
            game,
            prediction,
            "No Gemini key found. Set GEMINI_API_KEY, GOOGLE_API_KEY, or GOOGLE_GENAI_API_KEY.",
        )

    context = build_ai_context(game, prediction)

    prompt = f"""
You are the explanation layer for PitchIQ, a baseball pitching matchup analytics web app.

Rules:
- Do NOT invent betting odds.
- Do NOT claim this is gambling advice.
- Do NOT override the deterministic model.
- Explain the model result in plain English.
- Flag possible issues/outliers such as small Statcast samples, reliever/bulk pitcher usage, short expected IP, model/market disagreement, or weather/park uncertainty.
- Keep it concise for a dashboard card.

Return ONLY valid JSON with this exact shape:
{{
  "headline": "short headline",
  "summary": "2-4 sentence explanation",
  "key_factors": ["factor 1", "factor 2", "factor 3"],
  "warnings": ["warning 1", "warning 2"]
}}

Data:
{json.dumps(context, indent=2)}
""".strip()

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.25,
            "maxOutputTokens": 650,
            "responseMimeType": "application/json",
        },
    }

    candidates = _list_models(api_key) or _fallback_model_candidates()
    errors = []

    for api_version, model_name in candidates:
        try:
            response = requests.post(
                _generate_url(api_version, model_name),
                params={"key": api_key},
                json=payload,
                timeout=12,
            )
            response.raise_for_status()
            data = response.json()
            text = (
                data.get("candidates", [{}])[0]
                .get("content", {})
                .get("parts", [{}])[0]
                .get("text", "")
            )
            parsed = json.loads(text)

            return {
                "available": True,
                "headline": parsed.get("headline", "AI Matchup Summary"),
                "summary": parsed.get("summary", ""),
                "key_factors": parsed.get("key_factors", []),
                "warnings": parsed.get("warnings", []),
                "reason": f"Generated with {api_version}/{model_name}.",
            }

        except Exception as exc:
            errors.append(f"{api_version}/{model_name}: {exc}")

    return fallback_explanation(
        game,
        prediction,
        "Gemini failed for all discovered models. "
        + " | ".join(errors[-2:])
    )

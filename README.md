# ⚾ PitchIQ

PitchIQ is a FastAPI web application for analyzing MLB pitching matchups using public data.

The goal is to compare starting pitchers using recent form, venue context, lineup matchup data, weather conditions, and transparent prediction outputs such as expected innings, strikeout projection, quality start probability, and pitcher advantage.

## Current MVP

- Today's MLB games
- Probable starting pitchers
- Basic matchup scoring
- Transparent model explanation
- FastAPI + Jinja2 web interface

## Planned Features

- Pitcher recent-form analysis
- Stadium-specific pitching history
- Batter-vs-pitcher matchup summaries
- Weather impact modeling
- Expected innings projection
- Strikeout projection
- Quality start probability
- Win probability estimate
- Model explanation page

## Run Locally

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open:

```text
http://127.0.0.1:8000
```

## Disclaimer

PitchIQ is a sports analytics and software portfolio project. It is not gambling advice.

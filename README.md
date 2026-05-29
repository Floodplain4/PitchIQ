⚾ PitchIQ
MLB Pitching Matchup Intelligence

PitchIQ is a FastAPI-based baseball analytics application that evaluates MLB pitching matchups using public baseball data, weather conditions, ballpark context, recent pitcher performance, and advanced metrics.

The goal is to provide transparent, explainable pitching projections rather than black-box predictions.

🚀 Live Demo
🌐 Application

https://pitchiq-f0p6.onrender.com/

Screenshot

Features
Matchup Analysis
Daily MLB schedule
Probable starting pitchers
Team matchup previews
Home/away context
Pitcher Evaluation
PitchIQ Rating
Win Probability
Expected Innings Pitched
Strikeout Projection
Quality Start Probability
Advanced Metrics
ERA
WHIP
FIP
K/9
BB/9
HR/9
xwOBA
xBA
xSLG
Hard Hit %
Barrel %
Average Exit Velocity
Contextual Factors
Recent Form Analysis
Weather Effects
Ballpark Effects
Lineup Matchup Analysis
Pitch Arsenal Profiles
Explainable Model

Every prediction includes a factor-by-factor breakdown showing:

Season Performance
Recent Form
Statcast Quality
Command / Whiff Ability
Weather Impact
Park Context
Lineup Matchup
Architecture
MLB Stats API
        │
        ▼
Game Schedule
Probable Pitchers
Venue Information
        │
        ▼
PitchIQ Analytics Engine
        │
 ┌──────┼──────┐
 ▼      ▼      ▼
Weather  Park  Matchup
Context  Data  Factors
        │
        ▼
Prediction Model
        │
        ▼
FastAPI Web Application
Built With
Backend
FastAPI
Python
Jinja2
Requests
Data Sources
MLB Stats API
Baseball Savant
Open-Meteo
Deployment
Render
Current Status

PitchIQ is currently an active portfolio project.

Implemented:

Live MLB schedule integration
Probable pitcher tracking
Weather context
Ballpark context
Pitcher comparison engine
Public cloud deployment

In Progress:

Expanded Statcast integration
Historical prediction tracking
Model accuracy reporting
Batter-vs-pitcher analysis
PostgreSQL persistence layer
Why This Project Exists

Most publicly available betting and fantasy tools provide predictions without showing how those predictions were generated.

PitchIQ focuses on transparency and explainability by exposing the individual factors that influence each projection.

Author

Tyler Ledbetter

IT Professional | Python Developer | Cloud & Infrastructure Enthusiast

GitHub:
https://github.com/Floodplain4
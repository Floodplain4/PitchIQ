BALLPARK_CONTEXT = {
    "Great American Ball Park": {
        "city": "Cincinnati",
        "lat": 39.0979,
        "lon": -84.5082,
        "run_factor": 1.08,
        "hr_factor": 1.18,
        "notes": "Hitter-friendly park with elevated home run risk.",
    },
    "Truist Park": {
        "city": "Atlanta",
        "lat": 33.8908,
        "lon": -84.4678,
        "run_factor": 1.01,
        "hr_factor": 1.04,
        "notes": "Generally neutral to slightly hitter-friendly.",
    },
    "Yankee Stadium": {
        "city": "New York",
        "lat": 40.8296,
        "lon": -73.9262,
        "run_factor": 1.03,
        "hr_factor": 1.13,
        "notes": "Short right field can boost left-handed power.",
    },
    "Coors Field": {
        "city": "Denver",
        "lat": 39.7559,
        "lon": -104.9942,
        "run_factor": 1.25,
        "hr_factor": 1.18,
        "notes": "Extreme run environment due to altitude.",
    },
    "Petco Park": {
        "city": "San Diego",
        "lat": 32.7073,
        "lon": -117.1566,
        "run_factor": 0.94,
        "hr_factor": 0.92,
        "notes": "Pitcher-friendly environment.",
    },
    "T-Mobile Park": {
        "city": "Seattle",
        "lat": 47.5914,
        "lon": -122.3325,
        "run_factor": 0.92,
        "hr_factor": 0.88,
        "notes": "Pitcher-friendly park.",
    },
    "Oracle Park": {
        "city": "San Francisco",
        "lat": 37.7786,
        "lon": -122.3893,
        "run_factor": 0.91,
        "hr_factor": 0.82,
        "notes": "Strong pitcher-friendly park, especially for home runs.",
    },
    "Dodger Stadium": {
        "city": "Los Angeles",
        "lat": 34.0739,
        "lon": -118.2400,
        "run_factor": 0.98,
        "hr_factor": 1.02,
        "notes": "Mostly neutral run environment.",
    },
}


def get_venue_context(venue_name: str) -> dict:
    context = BALLPARK_CONTEXT.get(venue_name)

    if not context:
        return {
            "venue": venue_name,
            "city": "",
            "lat": None,
            "lon": None,
            "run_factor": 1.00,
            "hr_factor": 1.00,
            "park_score": 50.0,
            "notes": "Neutral fallback. Venue-specific park factors not mapped yet.",
        }

    run_factor = context["run_factor"]
    hr_factor = context["hr_factor"]

    # Pitcher score: lower run/HR factor is better for pitchers.
    park_score = 50
    park_score -= (run_factor - 1.00) * 130
    park_score -= (hr_factor - 1.00) * 90
    park_score = round(max(15, min(85, park_score)), 1)

    return {
        "venue": venue_name,
        **context,
        "park_score": park_score,
    }

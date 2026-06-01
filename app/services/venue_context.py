BALLPARK_CONTEXT = {
    "Angel Stadium": {"city": "Anaheim", "lat": 33.8003, "lon": -117.8827, "run_factor": 1.00, "hr_factor": 1.02, "roof": "open", "notes": "Mostly neutral run environment."},
    "Busch Stadium": {"city": "St. Louis", "lat": 38.6226, "lon": -90.1928, "run_factor": 0.97, "hr_factor": 0.93, "roof": "open", "notes": "Slightly pitcher-friendly park."},
    "Chase Field": {"city": "Phoenix", "lat": 33.4455, "lon": -112.0667, "run_factor": 1.03, "hr_factor": 1.02, "roof": "retractable", "notes": "Retractable-roof park; neutral to slightly hitter-friendly."},
    "Citi Field": {"city": "New York", "lat": 40.7571, "lon": -73.8458, "run_factor": 0.97, "hr_factor": 0.96, "roof": "open", "notes": "Generally pitcher-friendly."},
    "Citizens Bank Park": {"city": "Philadelphia", "lat": 39.9057, "lon": -75.1665, "run_factor": 1.03, "hr_factor": 1.12, "roof": "open", "notes": "Hitter-friendly home-run environment."},
    "Comerica Park": {"city": "Detroit", "lat": 42.3390, "lon": -83.0485, "run_factor": 0.98, "hr_factor": 0.92, "roof": "open", "notes": "Slightly pitcher-friendly, especially for home runs."},
    "Coors Field": {"city": "Denver", "lat": 39.7559, "lon": -104.9942, "run_factor": 1.25, "hr_factor": 1.18, "roof": "open", "notes": "Extreme run environment due to altitude."},
    "Daikin Park": {"city": "Houston", "lat": 29.7573, "lon": -95.3555, "run_factor": 1.00, "hr_factor": 1.05, "roof": "retractable", "notes": "Retractable-roof park; mostly neutral with some home-run boost."},
    "Minute Maid Park": {"city": "Houston", "lat": 29.7573, "lon": -95.3555, "run_factor": 1.00, "hr_factor": 1.05, "roof": "retractable", "notes": "Retractable-roof park; mostly neutral with some home-run boost."},
    "Dodger Stadium": {"city": "Los Angeles", "lat": 34.0739, "lon": -118.2400, "run_factor": 0.98, "hr_factor": 1.02, "roof": "open", "notes": "Mostly neutral run environment."},
    "Fenway Park": {"city": "Boston", "lat": 42.3467, "lon": -71.0972, "run_factor": 1.05, "hr_factor": 0.98, "roof": "open", "notes": "Hitter-friendly for run scoring, less extreme for home runs."},
    "George M. Steinbrenner Field": {"city": "Tampa", "lat": 27.9803, "lon": -82.5067, "run_factor": 1.00, "hr_factor": 1.00, "roof": "open", "notes": "Neutral fallback for temporary Rays home venue."},
    "Globe Life Field": {"city": "Arlington", "lat": 32.7473, "lon": -97.0842, "run_factor": 0.98, "hr_factor": 1.00, "roof": "retractable", "notes": "Retractable-roof park; mostly neutral."},
    "Great American Ball Park": {"city": "Cincinnati", "lat": 39.0979, "lon": -84.5082, "run_factor": 1.08, "hr_factor": 1.18, "roof": "open", "notes": "Hitter-friendly park with elevated home run risk."},
    "Guaranteed Rate Field": {"city": "Chicago", "lat": 41.8300, "lon": -87.6339, "run_factor": 1.01, "hr_factor": 1.08, "roof": "open", "notes": "Slightly hitter-friendly, especially for home runs."},
    "Rate Field": {"city": "Chicago", "lat": 41.8300, "lon": -87.6339, "run_factor": 1.01, "hr_factor": 1.08, "roof": "open", "notes": "Slightly hitter-friendly, especially for home runs."},
    "Kauffman Stadium": {"city": "Kansas City", "lat": 39.0517, "lon": -94.4803, "run_factor": 0.99, "hr_factor": 0.88, "roof": "open", "notes": "Suppresses home runs, generally pitcher-friendly for power."},
    "LoanDepot Park": {"city": "Miami", "lat": 25.7781, "lon": -80.2197, "run_factor": 0.93, "hr_factor": 0.88, "roof": "retractable", "notes": "Pitcher-friendly retractable-roof park."},
    "loanDepot park": {"city": "Miami", "lat": 25.7781, "lon": -80.2197, "run_factor": 0.93, "hr_factor": 0.88, "roof": "retractable", "notes": "Pitcher-friendly retractable-roof park."},
    "American Family Field": {"city": "Milwaukee", "lat": 43.0280, "lon": -87.9712, "run_factor": 1.00, "hr_factor": 1.06, "roof": "retractable", "notes": "Retractable-roof park with mild home-run boost."},
    "Nationals Park": {"city": "Washington", "lat": 38.8730, "lon": -77.0074, "run_factor": 1.01, "hr_factor": 1.03, "roof": "open", "notes": "Mostly neutral to slightly hitter-friendly."},
    "Oakland Coliseum": {"city": "Oakland", "lat": 37.7516, "lon": -122.2005, "run_factor": 0.94, "hr_factor": 0.86, "roof": "open", "notes": "Pitcher-friendly park."},
    "Sutter Health Park": {"city": "West Sacramento", "lat": 38.5803, "lon": -121.5133, "run_factor": 1.00, "hr_factor": 1.00, "roof": "open", "notes": "Neutral fallback for current Athletics home venue."},
    "Oracle Park": {"city": "San Francisco", "lat": 37.7786, "lon": -122.3893, "run_factor": 0.91, "hr_factor": 0.82, "roof": "open", "notes": "Strong pitcher-friendly park, especially for home runs."},
    "Oriole Park at Camden Yards": {"city": "Baltimore", "lat": 39.2839, "lon": -76.6217, "run_factor": 0.98, "hr_factor": 0.93, "roof": "open", "notes": "More pitcher-friendly after left-field dimension changes."},
    "Petco Park": {"city": "San Diego", "lat": 32.7073, "lon": -117.1566, "run_factor": 0.94, "hr_factor": 0.92, "roof": "open", "notes": "Pitcher-friendly environment."},
    "PNC Park": {"city": "Pittsburgh", "lat": 40.4469, "lon": -80.0057, "run_factor": 0.97, "hr_factor": 0.90, "roof": "open", "notes": "Pitcher-friendly, suppresses home runs."},
    "Progressive Field": {"city": "Cleveland", "lat": 41.4962, "lon": -81.6852, "run_factor": 0.99, "hr_factor": 0.98, "roof": "open", "notes": "Mostly neutral to slightly pitcher-friendly."},
    "Rogers Centre": {"city": "Toronto", "lat": 43.6414, "lon": -79.3894, "run_factor": 1.02, "hr_factor": 1.08, "roof": "retractable", "notes": "Retractable-roof park with some home-run boost."},
    "T-Mobile Park": {"city": "Seattle", "lat": 47.5914, "lon": -122.3325, "run_factor": 0.92, "hr_factor": 0.88, "roof": "retractable", "notes": "Pitcher-friendly park."},
    "Target Field": {"city": "Minneapolis", "lat": 44.9817, "lon": -93.2776, "run_factor": 0.99, "hr_factor": 0.97, "roof": "open", "notes": "Mostly neutral to slightly pitcher-friendly."},
    "Truist Park": {"city": "Atlanta", "lat": 33.8908, "lon": -84.4678, "run_factor": 1.01, "hr_factor": 1.04, "roof": "open", "notes": "Generally neutral to slightly hitter-friendly."},
    "Wrigley Field": {"city": "Chicago", "lat": 41.9484, "lon": -87.6553, "run_factor": 1.02, "hr_factor": 1.04, "roof": "open", "notes": "Weather-sensitive park; wind can swing the run environment significantly."},
    "Yankee Stadium": {"city": "New York", "lat": 40.8296, "lon": -73.9262, "run_factor": 1.03, "hr_factor": 1.13, "roof": "open", "notes": "Short right field can boost left-handed power."},
    "Tropicana Field": {"city": "St. Petersburg", "lat": 27.7682, "lon": -82.6534, "run_factor": 0.96, "hr_factor": 0.95, "roof": "dome", "notes": "Indoor dome; weather is neutralized."},
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
            "roof": "unknown",
            "park_score": 50.0,
            "notes": "Neutral fallback. Venue-specific park factors not mapped yet.",
        }

    run_factor = context["run_factor"]
    hr_factor = context["hr_factor"]

    park_score = 50
    park_score -= (run_factor - 1.00) * 130
    park_score -= (hr_factor - 1.00) * 90
    park_score = round(max(15, min(85, park_score)), 1)

    return {
        "venue": venue_name,
        **context,
        "park_score": park_score,
    }

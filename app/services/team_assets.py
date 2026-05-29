TEAM_ASSETS = {
    144: {"abbr": "ATL", "primary": "#CE1141", "secondary": "#13274F"},
    113: {"abbr": "CIN", "primary": "#C6011F", "secondary": "#000000"},
    135: {"abbr": "SD", "primary": "#2F241D", "secondary": "#FFC425"},
    120: {"abbr": "WSH", "primary": "#AB0003", "secondary": "#14225A"},
    142: {"abbr": "MIN", "primary": "#002B5C", "secondary": "#D31145"},
    134: {"abbr": "PIT", "primary": "#FDB827", "secondary": "#27251F"},
    141: {"abbr": "TOR", "primary": "#134A8E", "secondary": "#E8291C"},
    110: {"abbr": "BAL", "primary": "#DF4601", "secondary": "#000000"},
    111: {"abbr": "BOS", "primary": "#BD3039", "secondary": "#0C2340"},
    114: {"abbr": "CLE", "primary": "#E31937", "secondary": "#0C2340"},
    108: {"abbr": "LAA", "primary": "#BA0021", "secondary": "#003263"},
    139: {"abbr": "TB", "primary": "#092C5C", "secondary": "#8FBCE6"},
    146: {"abbr": "MIA", "primary": "#00A3E0", "secondary": "#EF3340"},
    121: {"abbr": "NYM", "primary": "#002D72", "secondary": "#FF5910"},
    112: {"abbr": "CHC", "primary": "#0E3386", "secondary": "#CC3433"},
    138: {"abbr": "STL", "primary": "#C41E3A", "secondary": "#0C2340"},
    116: {"abbr": "DET", "primary": "#0C2340", "secondary": "#FA4616"},
    145: {"abbr": "CWS", "primary": "#27251F", "secondary": "#C4CED4"},
    118: {"abbr": "KC", "primary": "#004687", "secondary": "#BD9B60"},
    140: {"abbr": "TEX", "primary": "#003278", "secondary": "#C0111F"},
    158: {"abbr": "MIL", "primary": "#12284B", "secondary": "#FFC52F"},
    117: {"abbr": "HOU", "primary": "#002D62", "secondary": "#EB6E1F"},
    119: {"abbr": "LAD", "primary": "#005A9C", "secondary": "#EF3E42"},
    109: {"abbr": "ARI", "primary": "#A71930", "secondary": "#E3D4AD"},
    115: {"abbr": "COL", "primary": "#33006F", "secondary": "#C4CED4"},
    137: {"abbr": "SF", "primary": "#FD5A1E", "secondary": "#27251F"},
    147: {"abbr": "NYY", "primary": "#0C2340", "secondary": "#C4CED4"},
    143: {"abbr": "PHI", "primary": "#E81828", "secondary": "#002D72"},
    133: {"abbr": "ATH", "primary": "#003831", "secondary": "#EFB21E"},
    136: {"abbr": "SEA", "primary": "#0C2C56", "secondary": "#005C5C"},
}


def team_logo_url(team_id: int | None) -> str:
    if not team_id:
        return ""
    return f"https://www.mlbstatic.com/team-logos/{team_id}.svg"


def team_asset(team_id: int | None) -> dict:
    asset = TEAM_ASSETS.get(team_id or 0, {})
    return {
        "abbr": asset.get("abbr", "MLB"),
        "primary": asset.get("primary", "#1f2937"),
        "secondary": asset.get("secondary", "#60a5fa"),
        "logo": team_logo_url(team_id),
    }

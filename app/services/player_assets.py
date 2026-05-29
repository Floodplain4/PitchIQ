def player_headshot_url(player_id: int | None) -> str:
    """Return MLB's public player headshot URL.

    Falls back to MLB's generic silhouette when an ID is missing.
    """
    if not player_id:
        return "https://img.mlbstatic.com/mlb-photos/image/upload/w_213,d_people:generic:headshot:silo:current.png,q_auto:best,f_auto/v1/people/generic/headshot/67/current"

    return (
        "https://img.mlbstatic.com/mlb-photos/image/upload/"
        "w_213,d_people:generic:headshot:silo:current.png,q_auto:best,f_auto/"
        f"v1/people/{player_id}/headshot/67/current"
    )

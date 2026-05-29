from __future__ import annotations

from datetime import date
from io import StringIO
import hashlib

import pandas as pd
import requests

from app.services.cache import cache_path, is_fresh


SAVANT_CSV_URL = "https://baseballsavant.mlb.com/statcast_search/csv"


def _safe_read_csv(text: str) -> pd.DataFrame:
    if not text or text.strip().startswith("<"):
        return pd.DataFrame()

    try:
        return pd.read_csv(StringIO(text))
    except Exception:
        return pd.DataFrame()


def _csv_cache_name(prefix: str, params: dict) -> str:
    raw = repr(sorted(params.items())).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:16]
    return f"{prefix}_{digest}.csv"


def _fetch_savant_csv(prefix: str, params: dict, ttl_hours: int = 24) -> pd.DataFrame:
    cache_file = cache_path(_csv_cache_name(prefix, params))

    if is_fresh(cache_file, ttl_hours=ttl_hours):
        try:
            return pd.read_csv(cache_file)
        except Exception:
            pass

    try:
        response = requests.get(SAVANT_CSV_URL, params=params, timeout=20)
        response.raise_for_status()
    except requests.RequestException:
        return pd.DataFrame()

    df = _safe_read_csv(response.text)

    if not df.empty:
        df.to_csv(cache_file, index=False)

    return df


def current_season_dates() -> tuple[str, str]:
    year = date.today().year
    return f"{year}-03-01", date.today().isoformat()


def fetch_pitcher_statcast(pitcher_id: int | None, ttl_hours: int = 24) -> pd.DataFrame:
    if not pitcher_id:
        return pd.DataFrame()

    start_date, end_date = current_season_dates()

    params = {
        "all": "true",
        "hfPT": "",
        "hfAB": "",
        "hfGT": "R|",
        "hfPR": "",
        "hfZ": "",
        "stadium": "",
        "hfBBL": "",
        "hfNewZones": "",
        "hfPull": "",
        "hfC": "",
        "hfSea": str(date.today().year) + "|",
        "hfSit": "",
        "player_type": "pitcher",
        "hfOuts": "",
        "opponent": "",
        "pitcher_throws": "",
        "batter_stands": "",
        "hfSA": "",
        "game_date_gt": start_date,
        "game_date_lt": end_date,
        "pitchers_lookup[]": str(pitcher_id),
        "group_by": "name",
        "min_pitches": "0",
        "min_results": "0",
        "type": "details",
    }

    return _fetch_savant_csv(f"pitcher_{pitcher_id}", params, ttl_hours=ttl_hours)


def fetch_batter_vs_pitcher(pitcher_id: int | None, batter_id: int | None, ttl_hours: int = 72) -> pd.DataFrame:
    if not pitcher_id or not batter_id:
        return pd.DataFrame()

    start_date = f"{date.today().year - 5}-03-01"
    end_date = date.today().isoformat()

    params = {
        "all": "true",
        "hfPT": "",
        "hfAB": "",
        "hfGT": "R|",
        "hfPR": "",
        "hfZ": "",
        "stadium": "",
        "hfBBL": "",
        "hfNewZones": "",
        "hfPull": "",
        "hfC": "",
        "hfSea": "",
        "hfSit": "",
        "player_type": "pitcher",
        "hfOuts": "",
        "opponent": "",
        "pitcher_throws": "",
        "batter_stands": "",
        "hfSA": "",
        "game_date_gt": start_date,
        "game_date_lt": end_date,
        "pitchers_lookup[]": str(pitcher_id),
        "batters_lookup[]": str(batter_id),
        "group_by": "name",
        "min_pitches": "0",
        "min_results": "0",
        "type": "details",
    }

    return _fetch_savant_csv(f"bvp_{pitcher_id}_{batter_id}", params, ttl_hours=ttl_hours)


def _safe_mean(df: pd.DataFrame, column: str):
    if column not in df.columns:
        return None
    series = pd.to_numeric(df[column], errors="coerce").dropna()
    if series.empty:
        return None
    return float(series.mean())


def _event_count(df: pd.DataFrame, events: set[str]) -> int:
    if "events" not in df.columns:
        return 0
    return int(df["events"].isin(events).sum())


def summarize_pitcher_statcast(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"available": False, "sample_pitches": 0}

    pitches = len(df)
    batted = df[df.get("launch_speed", pd.Series(dtype=float)).notna()] if "launch_speed" in df.columns else pd.DataFrame()

    whiffs = 0
    if "description" in df.columns:
        whiffs = int(df["description"].isin({"swinging_strike", "swinging_strike_blocked", "foul_tip"}).sum())

    swings = 0
    if "description" in df.columns:
        swings = int(df["description"].isin({
            "swinging_strike",
            "swinging_strike_blocked",
            "foul",
            "foul_tip",
            "hit_into_play",
            "hit_into_play_no_out",
            "hit_into_play_score",
        }).sum())

    strikeouts = _event_count(df, {"strikeout", "strikeout_double_play"})
    walks = _event_count(df, {"walk", "intent_walk"})
    hr = _event_count(df, {"home_run"})

    hard_hit = 0
    barrels = 0

    if not batted.empty and "launch_speed" in batted.columns:
        hard_hit = int((pd.to_numeric(batted["launch_speed"], errors="coerce") >= 95).sum())

    if not batted.empty and "launch_speed" in batted.columns and "launch_angle" in batted.columns:
        ev = pd.to_numeric(batted["launch_speed"], errors="coerce")
        la = pd.to_numeric(batted["launch_angle"], errors="coerce")
        barrels = int(((ev >= 98) & (la >= 26) & (la <= 30)).sum())

    pa_events = df[df.get("events", pd.Series(dtype=str)).notna()] if "events" in df.columns else pd.DataFrame()
    pa = len(pa_events) or max(1, int(pitches / 4))

    summary = {
        "available": True,
        "sample_pitches": pitches,
        "plate_appearances_est": pa,
        "avg_ev": round(_safe_mean(batted, "launch_speed") or 0, 1) if not batted.empty else None,
        "hard_hit_pct": round((hard_hit / len(batted)) * 100, 1) if not batted.empty else None,
        "barrel_pct": round((barrels / len(batted)) * 100, 1) if not batted.empty else None,
        "whiff_pct": round((whiffs / swings) * 100, 1) if swings else None,
        "k_pct": round((strikeouts / pa) * 100, 1) if pa else None,
        "bb_pct": round((walks / pa) * 100, 1) if pa else None,
        "hr": hr,
        "xwoba": round(_safe_mean(df, "estimated_woba_using_speedangle") or 0, 3) if "estimated_woba_using_speedangle" in df.columns else None,
    }

    return summary


def summarize_batter_vs_pitcher(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "available": False,
            "pa": 0,
            "summary": "No batter-vs-pitcher Statcast sample found.",
        }

    pa_events = df[df.get("events", pd.Series(dtype=str)).notna()] if "events" in df.columns else pd.DataFrame()
    pa = len(pa_events)

    strikeouts = _event_count(df, {"strikeout", "strikeout_double_play"})
    walks = _event_count(df, {"walk", "intent_walk"})
    hits = _event_count(df, {"single", "double", "triple", "home_run"})
    hr = _event_count(df, {"home_run"})

    xwoba = _safe_mean(df, "estimated_woba_using_speedangle")
    avg_ev = _safe_mean(df, "launch_speed")

    return {
        "available": True,
        "pa": pa,
        "hits": hits,
        "strikeouts": strikeouts,
        "walks": walks,
        "hr": hr,
        "xwoba": round(xwoba, 3) if xwoba else None,
        "avg_ev": round(avg_ev, 1) if avg_ev else None,
        "summary": f"{pa} PA, {hits} H, {strikeouts} K, {walks} BB, {hr} HR",
    }

from __future__ import annotations

from datetime import date
from io import StringIO
import hashlib

import pandas as pd
import requests

from app.services.cache import cache_path, is_fresh


SAVANT_CSV_URL = "https://baseballsavant.mlb.com/statcast_search/csv"


SWING_DESCRIPTIONS = {
    "swinging_strike",
    "swinging_strike_blocked",
    "foul",
    "foul_tip",
    "hit_into_play",
    "hit_into_play_no_out",
    "hit_into_play_score",
}

WHIFF_DESCRIPTIONS = {"swinging_strike", "swinging_strike_blocked", "foul_tip"}
STRIKEOUT_EVENTS = {"strikeout", "strikeout_double_play"}
WALK_EVENTS = {"walk", "intent_walk"}
HIT_EVENTS = {"single", "double", "triple", "home_run"}
HR_EVENTS = {"home_run"}


PITCH_NAME_MAP = {
    "FF": "4-Seam",
    "FA": "4-Seam",
    "SI": "Sinker",
    "FT": "Sinker",
    "FC": "Cutter",
    "SL": "Slider",
    "ST": "Sweeper",
    "CH": "Change",
    "CU": "Curve",
    "KC": "Curve",
    "FS": "Splitter",
    "FO": "Splitter",
    "KN": "Knuckle",
}


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


def fetch_pitcher_statcast(pitcher_id: int | None, ttl_hours: int = 12) -> pd.DataFrame:
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


def _pa_rows(df: pd.DataFrame) -> pd.DataFrame:
    if "events" not in df.columns:
        return pd.DataFrame()
    return df[df["events"].notna() & (df["events"].astype(str) != "")]


def _estimate_ip_from_pa(pa: int) -> float:
    return max(0.1, pa / 4.25)


def _safe_pct(num: int | float, den: int | float):
    if not den:
        return None
    return round((num / den) * 100, 1)


def _batted_ball_summary(df: pd.DataFrame) -> dict:
    if "launch_speed" not in df.columns:
        return {}

    batted = df[pd.to_numeric(df["launch_speed"], errors="coerce").notna()].copy()
    if batted.empty:
        return {}

    ev = pd.to_numeric(batted["launch_speed"], errors="coerce")
    la = pd.to_numeric(batted.get("launch_angle", pd.Series(dtype=float)), errors="coerce")

    hard_hit = int((ev >= 95).sum())
    barrels = int(((ev >= 98) & (la >= 26) & (la <= 30)).sum()) if not la.empty else 0

    gb = int((la < 10).sum()) if not la.empty else 0
    ld = int(((la >= 10) & (la <= 25)).sum()) if not la.empty else 0
    fb = int((la > 25).sum()) if not la.empty else 0
    bbe = len(batted)

    return {
        "avg_ev": round(float(ev.dropna().mean()), 1) if not ev.dropna().empty else None,
        "hard_hit_pct": _safe_pct(hard_hit, bbe),
        "barrel_pct": _safe_pct(barrels, bbe),
        "gb_pct": _safe_pct(gb, bbe),
        "ld_pct": _safe_pct(ld, bbe),
        "fb_pct": _safe_pct(fb, bbe),
        "batted_balls": bbe,
    }


def _discipline_summary(df: pd.DataFrame) -> dict:
    desc = df["description"].astype(str) if "description" in df.columns else pd.Series(dtype=str)
    swings = int(desc.isin(SWING_DESCRIPTIONS).sum()) if not desc.empty else 0
    whiffs = int(desc.isin(WHIFF_DESCRIPTIONS).sum()) if not desc.empty else 0

    zone = None
    chase = None
    if "zone" in df.columns:
        z = pd.to_numeric(df["zone"], errors="coerce")
        zone_mask = z.between(1, 9)
        zone = _safe_pct(int(zone_mask.sum()), len(df))

        if swings and not desc.empty:
            chase = _safe_pct(int((~zone_mask & desc.isin(SWING_DESCRIPTIONS)).sum()), int((~zone_mask).sum()))

    first_pitch_strikes = None
    if "pitch_number" in df.columns and "type" in df.columns:
        first = df[pd.to_numeric(df["pitch_number"], errors="coerce") == 1]
        if not first.empty:
            first_pitch_strikes = _safe_pct(int(first["type"].astype(str).isin({"S", "X"}).sum()), len(first))

    return {
        "swings": swings,
        "whiffs": whiffs,
        "whiff_pct": _safe_pct(whiffs, swings),
        "zone_pct": zone,
        "chase_pct": chase,
        "first_pitch_strike_pct": first_pitch_strikes,
    }


def _expected_stats_summary(df: pd.DataFrame) -> dict:
    # Baseball Savant sometimes exposes xBA/xSLG columns with different names.
    xwoba = _safe_mean(df, "estimated_woba_using_speedangle")
    xba = _safe_mean(df, "estimated_ba_using_speedangle")
    xslg = _safe_mean(df, "estimated_slg_using_speedangle")

    return {
        "xwoba": round(xwoba, 3) if xwoba else None,
        "xba": round(xba, 3) if xba else None,
        "xslg": round(xslg, 3) if xslg else None,
    }


def _recent_summary(df: pd.DataFrame) -> dict:
    if "game_date" not in df.columns:
        return {}

    work = df.copy()
    work["game_date"] = pd.to_datetime(work["game_date"], errors="coerce")
    work = work.dropna(subset=["game_date"])
    if work.empty:
        return {}

    game_groups = []
    for game_date, g in work.groupby("game_date"):
        pa = len(_pa_rows(g)) or max(1, int(len(g) / 4))
        k = _event_count(g, STRIKEOUT_EVENTS)
        pitches = len(g)
        game_groups.append(
            {
                "date": game_date,
                "pa": pa,
                "k": k,
                "ip_est": _estimate_ip_from_pa(pa),
                "pitch_count": pitches,
            }
        )

    recent = sorted(game_groups, key=lambda row: row["date"], reverse=True)[:3]
    if not recent:
        return {}

    return {
        "last_3_k": int(sum(row["k"] for row in recent)),
        "avg_ip": round(sum(row["ip_est"] for row in recent) / len(recent), 1),
        "avg_pitch_count": round(sum(row["pitch_count"] for row in recent) / len(recent), 0),
    }


def _pitch_arsenal_summary(df: pd.DataFrame) -> list[dict]:
    if "pitch_type" not in df.columns:
        return []

    rows = []
    total = len(df)
    if total == 0:
        return []

    for pitch_type, g in df.groupby("pitch_type"):
        if not isinstance(pitch_type, str) or not pitch_type:
            continue
        usage = round((len(g) / total) * 100, 1)
        if usage < 1:
            continue

        desc = g["description"].astype(str) if "description" in g.columns else pd.Series(dtype=str)
        swings = int(desc.isin(SWING_DESCRIPTIONS).sum()) if not desc.empty else 0
        whiffs = int(desc.isin(WHIFF_DESCRIPTIONS).sum()) if not desc.empty else 0

        velo = _safe_mean(g, "release_speed")
        pitch_name = PITCH_NAME_MAP.get(pitch_type, pitch_type)

        rows.append(
            {
                "pitch": pitch_name,
                "usage": usage,
                "velocity": round(velo, 1) if velo else None,
                "whiff": _safe_pct(whiffs, swings) or 0,
                "whiff_percentile": 50,
            }
        )

    return sorted(rows, key=lambda row: row["usage"], reverse=True)[:5]


def summarize_pitcher_statcast(df: pd.DataFrame) -> dict:
    if df.empty:
        return {"available": False, "sample_pitches": 0}

    pitches = len(df)
    pa_events = _pa_rows(df)
    pa = len(pa_events) or max(1, int(pitches / 4))
    innings_est = _estimate_ip_from_pa(pa)

    strikeouts = _event_count(df, STRIKEOUT_EVENTS)
    walks = _event_count(df, WALK_EVENTS)
    hits = _event_count(df, HIT_EVENTS)
    hr = _event_count(df, HR_EVENTS)

    summary = {
        "available": True,
        "sample_pitches": pitches,
        "plate_appearances_est": pa,
        "innings_est": round(innings_est, 1),
        "strikeouts": strikeouts,
        "walks": walks,
        "hits": hits,
        "hr": hr,
        "k_pct": _safe_pct(strikeouts, pa),
        "bb_pct": _safe_pct(walks, pa),
    }

    summary.update(_batted_ball_summary(df))
    summary.update(_discipline_summary(df))
    summary.update(_expected_stats_summary(df))
    summary["recent"] = _recent_summary(df)
    summary["pitch_arsenal"] = _pitch_arsenal_summary(df)

    return summary


def summarize_batter_vs_pitcher(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "available": False,
            "pa": 0,
            "summary": "No batter-vs-pitcher Statcast sample found.",
        }

    pa_events = _pa_rows(df)
    pa = len(pa_events)

    strikeouts = _event_count(df, STRIKEOUT_EVENTS)
    walks = _event_count(df, WALK_EVENTS)
    hits = _event_count(df, HIT_EVENTS)
    hr = _event_count(df, HR_EVENTS)

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

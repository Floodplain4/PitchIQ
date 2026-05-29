from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import json


CACHE_DIR = Path("data/cache")
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def cache_path(name: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_", ".") else "_" for ch in name)
    return CACHE_DIR / safe


def is_fresh(path: Path, ttl_hours: int = 12) -> bool:
    if not path.exists():
        return False

    modified = datetime.fromtimestamp(path.stat().st_mtime)
    return datetime.now() - modified < timedelta(hours=ttl_hours)


def read_json_cache(name: str, ttl_hours: int = 12):
    path = cache_path(name)

    if not is_fresh(path, ttl_hours=ttl_hours):
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def write_json_cache(name: str, data) -> None:
    path = cache_path(name)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")

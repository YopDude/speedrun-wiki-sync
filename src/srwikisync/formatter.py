from datetime import datetime
from .speedrun_api import api_get_json

def format_time(primary_t_seconds: float) -> str:
    # Convert seconds -> "3h 4m 49s" (include ms only if non-zero)
    total_ms = int(round(primary_t_seconds * 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60

    parts = []
    if h:
        parts.append(f"{h}h")
    if h or m:
        parts.append(f"{m}m")
    parts.append(f"{s}s")
    if ms:
        parts.append(f"{ms}ms")
    return " ".join(parts)

def format_date(date_str: str | None) -> str:
    # speedrun.com: typically "YYYY-MM-DD". Return "Month D, YYYY".
    if not date_str:
        return ""
    d = datetime.fromisoformat(date_str).date()
    # Linux supports %-d
    return d.strftime("%B %-d, %Y")


import requests

def extract_runner_display(run: dict, api_base: str, user_agent: str, user_cache: dict[str, str]) -> str:
    players = run.get("players", [])
    names: list[str] = []

    for p in players:
        rel = p.get("rel")
        if rel == "guest":
            names.append(p.get("name", "Unknown"))
        elif rel == "user":
            uid = p.get("id")
            if not uid:
                names.append("Unknown")
                continue
            if uid in user_cache:
                names.append(user_cache[uid])
                continue

            u = api_get_json(api_base, f"/users/{uid}", user_agent)
            uname = u["data"]["names"]["international"]
            user_cache[uid] = uname
            names.append(uname)
        else:
            names.append("Unknown")

    return ", ".join([n for n in names if n]) or "Unknown"

def run_path_from_run(run: dict, game_slug: str) -> str:
    """
    Return wiki-style run path, e.g.:
    tlozph/runs/y4lpopkz
    """
    rid = run.get("id")
    return f"{game_slug}/runs/{rid}" if rid else ""

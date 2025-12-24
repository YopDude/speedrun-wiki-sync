import time
import random
import re
from urllib.parse import urlparse, urljoin

import requests

DEFAULT_TIMEOUT = 20


_META_REFRESH_RE = re.compile(r'''content=["']?[^"']*url=([^"'>\s]+)''', re.IGNORECASE)

def _extract_meta_refresh_url(html: str) -> str | None:
    """Return the URL from a meta-refresh HTML page, if present."""
    m = _META_REFRESH_RE.search(html or "")
    if not m:
        return None
    return m.group(1).strip()

def _absolute_from_api_base(api_base: str, target: str) -> str:
    """Convert a meta-refresh target (often a relative /api/v1/... path) into an absolute URL."""
    if not target:
        return api_base
    if target.startswith("http://") or target.startswith("https://"):
        return target
    parsed = urlparse(api_base)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if target.startswith("/"):
        return origin + target
    return urljoin(api_base, target)

def _sleep_backoff(attempt: int) -> None:
    # exponential backoff with jitter
    base = 0.8 * (2 ** attempt)
    jitter = random.uniform(0, 0.4)
    time.sleep(min(10.0, base + jitter))

def api_get_json(api_base: str, path: str, user_agent: str, params: dict | None = None, timeout: int = DEFAULT_TIMEOUT) -> dict:
    """
    GET JSON with retry, backoff, and basic rate-limit handling.
    Retries on:
      - 429 Too Many Requests
      - 5xx
      - timeouts / transient connection errors
    """
    url = f"{api_base}{path}"
    headers = {"User-Agent": user_agent, "Accept": "application/json"}

    last_exc = None
    for attempt in range(5):
        try:
            r = requests.get(url, params=params or {}, headers=headers, timeout=timeout)

            # Rate limit
            if r.status_code == 429:
                retry_after = r.headers.get("Retry-After")
                if retry_after:
                    try:
                        time.sleep(float(retry_after))
                    except ValueError:
                        _sleep_backoff(attempt)
                else:
                    _sleep_backoff(attempt)
                continue

            # Transient server errors
            if 500 <= r.status_code < 600:
                _sleep_backoff(attempt)
                continue

            r.raise_for_status()

            # speedrun.com sometimes returns an HTML meta-refresh redirect when a slug is used
            # (e.g. /games/<abbrev> -> /games/<id>). If we see HTML, follow it once.
            content_type = (r.headers.get("Content-Type") or "").lower()
            body = r.text or ""
            if "text/html" in content_type or body.lstrip().startswith("<!DOCTYPE html"):
                target = _extract_meta_refresh_url(body)
                if target:
                    url2 = _absolute_from_api_base(api_base, target)
                    r2 = requests.get(url2, params=params or {}, headers=headers, timeout=timeout)
                    r2.raise_for_status()
                    return r2.json()

            # Normal JSON response
            return r.json()

        except (requests.Timeout, requests.ConnectionError) as e:
            last_exc = e
            _sleep_backoff(attempt)
            continue
        except requests.HTTPError as e:
            # Non-retryable 4xx
            raise

    # If we got here, retries exhausted
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Failed to GET {url} after retries")

def get_leaderboard_top1(api_base: str, user_agent: str, game: str, category_id: str, variables: dict, level_id: str | None = None) -> dict | None:
    params = {"top": 1}
    for var_id, value_id in (variables or {}).items():
        params[f"var-{var_id}"] = value_id

    if level_id:
        path = f"/leaderboards/{game}/level/{level_id}/{category_id}"
    else:
        path = f"/leaderboards/{game}/category/{category_id}"

    data = api_get_json(api_base, path, user_agent, params=params)
    runs = data["data"].get("runs", [])
    if not runs:
        return None
    return runs[0]["run"]


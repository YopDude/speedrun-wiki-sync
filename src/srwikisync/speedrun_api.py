import time
import random
import requests

DEFAULT_TIMEOUT = 20

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
    headers = {"User-Agent": user_agent}

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

def get_leaderboard_top1(api_base: str, user_agent: str, game: str, category_id: str, variables: dict) -> dict | None:
    params = {"top": 1}
    for var_id, value_id in (variables or {}).items():
        params[f"var-{var_id}"] = value_id

    data = api_get_json(api_base, f"/leaderboards/{game}/category/{category_id}", user_agent, params=params)
    runs = data["data"].get("runs", [])
    if not runs:
        return None
    return runs[0]["run"]


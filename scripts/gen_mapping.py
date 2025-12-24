#!/usr/bin/env python3
"""
scripts/gen_mapping.py

Mapping generator for srwikisync.

Key rules:
- Uses ONLY approved substitutions from configs/zeldawiki_wikiterms.json
- Substitutions are:
  - substring-based
  - CASE-SENSITIVE
  - longest-match-first
- Applied to BOTH base category text and subcategory value labels
- NEVER rewrite inside existing [[links]] or {{templates}}
- ALSO: never re-match inside substitutions inserted during this run (prevents nesting)

Optional per-game exceptions:
- mappings/zeldawiki/curation/<mapping>.json
  - deny substrings: "contains": [...]
  - scoped allow overrides: "contains_exceptions": [...]
    * allow phrases override ONLY the deny terms they contain.
    * other deny matches still cause exclusion.

Debug:
- Set env EXCEPTIONS_DEBUG=1 to print why specific entries are excluded/kept.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import re
from pathlib import Path
from typing import Any, Iterable, Tuple

import requests

DEFAULT_API_BASE = "https://www.speedrun.com/api/v1"
DEFAULT_UA = "SpeedrunWikiSync/0.3 (mapping generator)"

_WIKI_PROTECTED_RE = re.compile(r"(\[\[.*?\]\]|\{\{.*?\}\})", flags=re.DOTALL)
_TOKEN_PREFIX = "\u0007WIKITERM_TOKEN_"
_TOKEN_SUFFIX = "\u0007"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def api_get(api_base: str, path: str, ua: str, params: dict | None = None) -> dict:
    r = requests.get(
        api_base + path,
        params=params or {},
        headers={"User-Agent": ua},
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def load_wikiterms(section_id: str | None) -> list[tuple[str, str]]:
    """
    Load substitutions from configs/zeldawiki_wikiterms.json.

    Supported formats (backwards compatible):

    1) Flat mapping:
       { "Any%": "[[Any%]]", ... }

    2) Scoped mapping:
       {
         "Master Quest": {
           "default": "[[Master Quest]]",
           "sections": { "HW": "[[Master Quest Map]]" }
         }
       }

    For scoped entries:
    - If section_id matches a key in "sections", that value is used
    - Else if "default" is provided, that is used
    - Else the entry is ignored
    """
    path = repo_root() / "configs" / "zeldawiki_wikiterms.json"
    if not path.exists():
        return []

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"Expected dict in {path}")

    terms: list[tuple[str, str]] = []

    for k, v in data.items():
        if not isinstance(k, str) or not k:
            continue

        # Simple flat mapping
        if isinstance(v, str):
            terms.append((k, v))
            continue

        # Scoped mapping
        if isinstance(v, dict):
            chosen: str | None = None

            # section override
            if section_id and isinstance(v.get("sections"), dict):
                sv = v["sections"].get(section_id)
                if isinstance(sv, str) and sv:
                    chosen = sv

            # default fallback
            if chosen is None:
                dv = v.get("default")
                if isinstance(dv, str) and dv:
                    chosen = dv

            if chosen is not None:
                terms.append((k, chosen))
            continue

    # Longest-first avoids partial replacements breaking longer ones
    terms.sort(key=lambda kv: len(kv[0]), reverse=True)
    return terms


def load_exceptions_for_mapping(mapping: str) -> tuple[list[str], list[str], list[str], list[str], list[str], list[str]]:
    """
    Load optional per-mapping curation rules.

    File: mappings/zeldawiki/curation/<mapping>.json

    Backwards compatible formats:

    1) List[str]
       Interpreted as legacy deny list (same as {"contains": [...]})

    2) Dict with:
       - "contains": list[str]            (deny substrings, case-insensitive)
       - "contains_exceptions": list[str] (scoped allow overrides, case-insensitive)

    New (optional) label filtering for subcategory variables:
       - "label_vars_keep": list[str]  (speedrun.com variable IDs to INCLUDE in the wiki label)
       - "label_vars_drop": list[str]  (speedrun.com variable IDs to EXCLUDE from the wiki label)

    Note: label filtering only affects the displayed wiki_category_wikitext. It does NOT change
    which variable combinations are generated or stored in sr.variables.
    """
    path = repo_root() / "mappings" / "zeldawiki" / "curation" / f"{mapping}.json"
    if not path.exists():
        return ([], [], [], [], [], [])

    data = json.loads(path.read_text(encoding="utf-8"))

    def norm_list_lc(v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        return [x.strip().lower() for x in v if isinstance(x, str) and x.strip()]

    def norm_list_raw(v: object) -> list[str]:
        if not isinstance(v, list):
            return []
        return [x.strip() for x in v if isinstance(x, str) and x.strip()]

    # Legacy: list means deny-only
    if isinstance(data, list):
        return (norm_list_lc(data), [], [], [], [], [])

    if isinstance(data, dict):
        deny = norm_list_lc(data.get("contains"))
        allow = norm_list_lc(data.get("contains_exceptions"))

        label_keep = norm_list_raw(data.get("label_vars_keep"))
        label_drop = norm_list_raw(data.get("label_vars_drop"))

        # NEW (optional): filter variables used in the API query (sr.variables)
        query_keep = norm_list_raw(data.get("query_vars_keep"))
        query_drop = norm_list_raw(data.get("query_vars_drop"))

        return (deny, allow, label_keep, label_drop, query_keep, query_drop)

    raise SystemExit(f"Invalid exceptions format in {path}")


def should_exclude_wikitext(wiki_cat: str, deny: list[str], allow: list[str]) -> bool:
    """
    Scoped override semantics (case-insensitive):

    - If no deny matches => keep
    - If deny matches and no allow matches => exclude
    - If both match:
        allow phrases ONLY override the deny terms they contain.
        Any other deny term still triggers exclusion.
    """
    if not deny:
        return False

    lc = wiki_cat.lower()
    matched_denies = [d for d in deny if d and d in lc]
    if not matched_denies:
        return False

    matched_allows = [a for a in allow if a and a in lc] if allow else []
    if not matched_allows:
        return True

    overridden: set[str] = set()
    for a in matched_allows:
        for d in matched_denies:
            if d in a:
                overridden.add(d)

    # Exclude if any matched deny is NOT overridden
    return any(d not in overridden for d in matched_denies)


def _protect_wiki_segments(text: str) -> tuple[str, list[str]]:
    protected: list[str] = []

    def repl(m: re.Match) -> str:
        protected.append(m.group(0))
        return f"{_TOKEN_PREFIX}PROT_{len(protected)-1}{_TOKEN_SUFFIX}"

    return _WIKI_PROTECTED_RE.sub(repl, text), protected


def _restore_wiki_segments(text: str, protected: list[str]) -> str:
    for i, seg in enumerate(protected):
        text = text.replace(f"{_TOKEN_PREFIX}PROT_{i}{_TOKEN_SUFFIX}", seg)
    return text


def apply_wikiterms(text: str, terms: list[tuple[str, str]]) -> str:
    if not text or not terms:
        return text

    working, protected = _protect_wiki_segments(text)

    inserted: list[str] = []
    for term, repl in terms:
        if term and term in working:
            token = f"{_TOKEN_PREFIX}INS_{len(inserted)}{_TOKEN_SUFFIX}"
            inserted.append(repl)
            working = working.replace(term, token)

    for i, repl in enumerate(inserted):
        working = working.replace(f"{_TOKEN_PREFIX}INS_{i}{_TOKEN_SUFFIX}", repl)

    return _restore_wiki_segments(working, protected)


def get_game_categories(api_base: str, ua: str, game_slug: str) -> list[dict]:
    return api_get(api_base, f"/games/{game_slug}/categories", ua, params={"embed": "variables"})["data"]


def extract_subcategory_variables(cat_obj: dict) -> list[dict]:
    vars_ = cat_obj.get("variables", {}).get("data", [])
    return [v for v in vars_ if v.get("is-subcategory")] if isinstance(vars_, list) else []


def iter_value_labels(var_obj: dict) -> list[Tuple[str, str]]:
    values = var_obj.get("values", {}).get("values", {})
    out: list[Tuple[str, str]] = []
    if isinstance(values, dict):
        for value_id, meta in values.items():
            label = meta.get("label")
            if label:
                out.append((value_id, label))
    out.sort(key=lambda x: x[1])
    return out


def cartesian_var_assignments(sub_vars: list[dict]) -> Iterable[Tuple[dict[str, str], list[Tuple[str, str]]]]:
    """
    Yield all combinations of subcategory variable assignments.

    Returns:
      - variables: {var_id: value_id} (used for API queries)
      - labels:    [(var_id, label)] (used for building the wiki row label; can be filtered)
    """
    if not sub_vars:
        yield ({}, [])
        return

    var_vals: list[Tuple[str, list[Tuple[str, str]]]] = []
    for v in sub_vars:
        var_id = v.get("id")
        vals = iter_value_labels(v)
        if var_id and vals:
            var_vals.append((var_id, vals))

    if not var_vals:
        yield ({}, [])
        return

    for combo in itertools.product(*(vals for _, vals in var_vals)):
        variables: dict[str, str] = {}
        labels: list[Tuple[str, str]] = []
        for (var_id, _), (value_id, label) in zip(var_vals, combo):
            variables[var_id] = value_id
            labels.append((var_id, label))
        yield (variables, labels)


def format_wiki_category_wikitext(
    cat_name: str,
    sub_labels: list[Tuple[str, str]],
    terms: list[tuple[str, str]],
    *,
    label_vars_keep: list[str] | None = None,
    label_vars_drop: list[str] | None = None,
) -> str:
    """
    Build the wiki row label.

    sub_labels is [(var_id, label)].

    If label_vars_keep is provided and non-empty, only those var_ids are included in the label.
    If label_vars_drop is provided and non-empty, those var_ids are excluded from the label.

    This only affects the display label; sr.variables still contains the full assignment.
    """
    base = apply_wikiterms(cat_name, terms)

    label_vars_keep = [v for v in (label_vars_keep or []) if v]
    label_vars_drop = [v for v in (label_vars_drop or []) if v]

    filtered: list[str] = []
    for var_id, lbl in sub_labels:
        if label_vars_keep and var_id not in label_vars_keep:
            continue
        if label_vars_drop and var_id in label_vars_drop:
            continue
        filtered.append(lbl)

    if not filtered:
        return base

    joined = " / ".join(apply_wikiterms(lbl, terms) for lbl in filtered)
    return f"{base} {{{{Small|({joined})}}}}"


def pick_categories_by_names(all_cats: list[dict], wanted_names: list[str]) -> list[dict]:
    picked: list[dict] = []
    for name in wanted_names:
        matches = [c for c in all_cats if c.get("name") == name]
        if len(matches) == 1:
            picked.append(matches[0])
        elif not matches:
            raise RuntimeError(f'Category not found: "{name}"')
        else:
            raise RuntimeError(f'Ambiguous category name "{name}"')
    return picked


def generate_per_game_entries(
    section: str,
    game_slug: str,
    api_base: str,
    ua: str,
    include_misc: bool,
    wanted_category_names: list[str] | None,
    all_categories: bool,
    terms: list[tuple[str, str]],
    deny: list[str],
    allow: list[str],
    label_vars_keep: list[str],
    label_vars_drop: list[str],
    query_vars_keep: list[str],
    query_vars_drop: list[str],
) -> list[dict[str, Any]]:
    cats = get_game_categories(api_base, ua, game_slug)
    cats = [c for c in cats if c.get("type") == "per-game"]
    if not include_misc:
        cats = [c for c in cats if not c.get("misc")]

    chosen = cats if all_categories else pick_categories_by_names(cats, wanted_category_names or [])

    debug = os.environ.get("EXCEPTIONS_DEBUG", "").strip() == "1"

    out: list[dict[str, Any]] = []
    seen_keys: set[tuple] = set()
    for c in chosen:
        cat_id = c["id"]
        cat_name = c["name"]
        sub_vars = extract_subcategory_variables(c)

        for variables_dict, labels in cartesian_var_assignments(sub_vars):
            # Optional: filter variables used in the leaderboard query (sr.variables)
            # This does NOT affect label rendering unless label_vars_* are also provided.
            if query_vars_keep:
                variables_dict = {k: v for k, v in variables_dict.items() if k in query_vars_keep}
            if query_vars_drop:
                variables_dict = {k: v for k, v in variables_dict.items() if k not in query_vars_drop}
            wiki_cat = format_wiki_category_wikitext(cat_name, labels, terms, label_vars_keep=label_vars_keep, label_vars_drop=label_vars_drop)

            excluded = should_exclude_wikitext(wiki_cat, deny, allow)
            if debug and (excluded or any(d in wiki_cat.lower() for d in deny)):
                lc = wiki_cat.lower()
                md = [d for d in deny if d in lc]
                ma = [a for a in allow if a in lc]
                print(f"[exceptions] {'EXCLUDE' if excluded else 'KEEP'}: {wiki_cat}")
                print(f"            matched_denies={md}")
                print(f"            matched_allows={ma}")

            if excluded:
                continue

            # De-duplicate identical mapping entries (can happen when query_vars_drop removes a differentiator)

            dedupe_key = (

                section,

                wiki_cat,

                game_slug,

                cat_id,

                tuple(sorted((variables_dict or {}).items())),

            )

            if dedupe_key in seen_keys:

                continue

            seen_keys.add(dedupe_key)


            out.append(
                {
                    "section": section,
                    "wiki_category_wikitext": wiki_cat,
                    "sr": {
                        "game": game_slug,
                        "category_id": cat_id,
                        "variables": variables_dict,
                        "kind": "full-game",
                        "category_name": cat_name,
                        "misc": bool(c.get("misc")),
                    },
                }
            )

    out.sort(key=lambda e: e["wiki_category_wikitext"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--all",
        action="store_true",
        help=(
            "Regenerate mappings for every *.json file in --out-dir. "
            "Each file provides its own section id + game slug."
        ),
    )
    ap.add_argument(
        "--out-dir",
        default="mappings/zeldawiki",
        help=(
            "Directory containing mapping JSON files for --all (default: mappings/zeldawiki). "
            "In single mode, this is ignored."
        ),
    )
    ap.add_argument(
        "--exclude",
        action="append",
        default=[],
        help=(
            "Exclude games/sections when using --all. Can be repeated, and can be comma-separated. "
            "Matches mapping filename stem, section id, or speedrun.com game slug exactly."
        ),
    )

    ap.add_argument("--section", help="Section id (single mapping mode)")
    ap.add_argument("--game", help="Speedrun.com game slug (single mapping mode)")
    ap.add_argument("--out", help="Output mapping JSON path (single mapping mode)")
    ap.add_argument("--categories", nargs="*", default=None)
    ap.add_argument("--all-categories", action="store_true")
    ap.add_argument("--no-misc", action="store_true")
    ap.add_argument("--api-base", default=DEFAULT_API_BASE)
    ap.add_argument("--user-agent", default=DEFAULT_UA)

    args = ap.parse_args()

    def split_excludes(values: list[str] | None) -> set[str]:
        out: set[str] = set()
        for v in values or []:
            if not v:
                continue
            for part in v.split(","):
                part = part.strip()
                if part:
                    out.add(part)
        return out

    excludes = split_excludes(args.exclude)

    if args.all:
        import glob

        out_dir = Path(args.out_dir)
        paths = sorted(glob.glob(str(out_dir / "*.json")))
        if not paths:
            raise SystemExit(f"No mapping JSON files found in {out_dir}")

        total = 0
        for path in paths:
            p = Path(path)
            stem = p.stem

            try:
                with open(path, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception as e:
                print(f"[SKIP] {path}: could not read JSON ({e})")
                continue

            if not isinstance(existing, list) or not existing:
                print(f"[SKIP] {path}: empty or invalid mapping (expected non-empty list)")
                continue

            section = existing[0].get("section")
            sr = existing[0].get("sr") or {}
            game = sr.get("game")

            candidates = {stem}
            if section:
                candidates.add(section)
            if game:
                candidates.add(game)

            if any(c in excludes for c in candidates):
                print(f"[SKIP] {path}")
                continue

            if not section or not game:
                print(f"[SKIP] {path}: couldn't infer section/game from mapping")
                continue

            # Section-scoped wikiterms
            terms = load_wikiterms(section)

            deny, allow, label_keep, label_drop, query_keep, query_drop = load_exceptions_for_mapping(stem)

            entries = generate_per_game_entries(
                section=section,
                game_slug=game,
                api_base=args.api_base,
                ua=args.user_agent,
                include_misc=not args.no_misc,
                wanted_category_names=args.categories,
                all_categories=args.all_categories,
                terms=terms,
                deny=deny,
                allow=allow,
                label_vars_keep=label_keep,
                label_vars_drop=label_drop,
                query_vars_keep=query_keep,
                query_vars_drop=query_drop,
            )

            with open(path, "w", encoding="utf-8") as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)

            print(f"[OK  ] {path}: wrote {len(entries)} entries")
            total += len(entries)

        print(f"Done. Wrote {total} total entries across {len(paths)} files.")
        return

    # Single mapping mode.
    if not args.section or not args.game or not args.out:
        raise SystemExit("Single mode requires --section, --game, and --out (or use --all)")
    # Section-scoped wikiterms
    terms = load_wikiterms(args.section)

    deny, allow, label_keep, label_drop, query_keep, query_drop = load_exceptions_for_mapping(Path(args.out).stem)
    entries = generate_per_game_entries(
        section=args.section,
        game_slug=args.game,
        api_base=args.api_base,
        ua=args.user_agent,
        include_misc=not args.no_misc,
        wanted_category_names=args.categories,
        all_categories=args.all_categories,
        terms=terms,
        deny=deny,
        allow=allow,
                label_vars_keep=label_keep,
                label_vars_drop=label_drop,
                query_vars_keep=query_keep,
                query_vars_drop=query_drop,
    )

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(entries)} entries to {args.out}")


if __name__ == "__main__":
    main()
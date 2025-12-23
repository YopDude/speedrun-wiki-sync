from __future__ import annotations

import difflib
import json
from typing import Any

import pywikibot
import yaml

from .speedrun_api import get_leaderboard_top1
from .formatter import (
    format_time,
    format_date,
    run_path_from_run,
    extract_runner_display,
)
from .wiki import (
    extract_section,
    replace_speedrun_record_row,
    remove_speedrun_record_row,
    MissingWikiRowError,
    scaffold_rows,
)


def load_yaml(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_mapping(path: str) -> list[dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def unified_diff(old: str, new: str, fromfile: str = "wiki_old", tofile: str = "wiki_new") -> str:
    lines = difflib.unified_diff(
        old.splitlines(True),
        new.splitlines(True),
        fromfile=fromfile,
        tofile=tofile,
        lineterm="",
    )
    return "\n".join(lines)


def build_section_block(full_text: str, section_name: str) -> str:
    """
    Return exactly the <section begin="X"/> ... <section end="X"/> block
    from a full page text.
    """
    prefix, body, suffix = extract_section(full_text, section_name)

    begin_tag = f'<section begin="{section_name}"/>'
    end_tag = f'<section end="{section_name}"/>'

    # prefix ends after the begin tag (per our extract_section impl),
    # but to be robust, find the last occurrence of begin_tag in prefix.
    begin_idx = prefix.rfind(begin_tag)
    if begin_idx == -1:
        # Fallback (shouldn't happen): emit tags + body
        return begin_tag + body + end_tag

    # suffix begins with the end tag (per our extract_section impl),
    # but to be robust, locate the first end tag.
    end_idx = suffix.find(end_tag)
    if end_idx == -1:
        # Fallback: emit from begin through the end of suffix
        return prefix[begin_idx:] + body + suffix

    return prefix[begin_idx:] + body + suffix[: end_idx + len(end_tag)]


def update_section_for_mapping(
    page_text: str,
    section_name: str,
    mapping_entries: list[dict[str, Any]],
    api_base: str,
    user_agent: str,
    no_blanks: bool = False,
) -> tuple[str, bool]:
    """
    Update only the named <section begin="X"/>...<section end="X"/> block,
    replacing only those Speedrun Record rows whose first parameter matches
    mapping 'wiki_category_wikitext' exactly.

    Returns (new_text, changed).
    """
    prefix, body, suffix = extract_section(page_text, section_name)
    if not isinstance(body, str):
        raise RuntimeError(f"Section body is not a string (got {type(body)}). Check section extraction.")

    new_body = body
    user_cache: dict[str, str] = {}

    for entry in mapping_entries:
        if entry.get("section") != section_name:
            continue

        wiki_cat = entry["wiki_category_wikitext"]
        sr = entry["sr"]
        run = get_leaderboard_top1(
            api_base=api_base,
            user_agent=user_agent,
            game=sr["game"],
            category_id=sr["category_id"],
            variables=sr.get("variables", {}),
            level_id=sr.get("level_id"),
        )

        if run is None:
            # No verified run found for this filter.
            # If --no-blanks is enabled, prune any existing placeholder row.
            if no_blanks:
                new_body = remove_speedrun_record_row(new_body, wiki_category_wikitext=wiki_cat)
            continue

        runner = extract_runner_display(run, api_base, user_agent, user_cache)
        time_str = format_time(run["times"]["primary_t"])
        date_str = format_date(run.get("date"))

        game_slug = sr["game"]  # e.g. "tlozph"
        run_path = run_path_from_run(run, game_slug)

        new_body = replace_speedrun_record_row(
            new_body,
            wiki_category_wikitext=wiki_cat,
            runner=runner,
            time_str=time_str,
            date_str=date_str,
            run_path=run_path,
        )

        if not isinstance(new_body, str):
            raise RuntimeError(
                f"Row replacement returned non-string (got {type(new_body)}). "
                f"Check replace_speedrun_record_row() returns the updated body."
            )

    new_text = prefix + new_body + suffix
    return new_text, (new_text != page_text)


def infer_section_from_mapping(mapping_entries):
    secs = {e.get('section') for e in mapping_entries if e.get('section')}
    if len(secs) == 1:
        return next(iter(secs))
    raise RuntimeError("Mapping contains multiple sections; specify --section explicitly")


def run_update(
    config_path: str,
    mapping_path: str,
    dry_run: bool,
    write: bool,
    emit: bool = False,
    section_override: str | None = None,
    no_blanks: bool = False,
) -> int:
    """
    Main entrypoint used by CLI.

    - dry_run=True prints a unified diff and does not save
    - write=True saves (one atomic edit) if changes exist
    - emit=True prints the updated section block and does not save
    """
    cfg = load_yaml(config_path)

    family = cfg["wiki"]["family"]
    lang = cfg["wiki"]["lang"]
    page_title = cfg["wiki"]["page_title"]

    api_base = cfg["speedrun"]["api_base"]
    user_agent = cfg["speedrun"]["user_agent"]

    mapping_entries = load_mapping(mapping_path)

    section_name = (
        section_override
        or cfg.get("behavior", {}).get("section_name")
        or infer_section_from_mapping(mapping_entries)
    )

    site = pywikibot.Site(code=lang, fam=family)
    site.login()
    if not site.username():
        raise RuntimeError("Not logged in. Check PYWIKIBOT_DIR and credentials.")

    page = pywikibot.Page(site, page_title)
    old_text = page.text

    try:
        new_text, changed = update_section_for_mapping(
            page_text=old_text,
            section_name=section_name,
            mapping_entries=mapping_entries,
            api_base=api_base,
            user_agent=user_agent,
            no_blanks=no_blanks,
        )
    except MissingWikiRowError as e:
        print(f"ABORT: The wiki section is missing at least one expected row: {e.missing_category_wikitext}")
        print("\nPaste these rows into the section (order as you like), then re-run:\n")
        if no_blanks:
            # In --no-blanks mode, mappings may include hundreds of potential permutations.
            # Scaffolding *everything* is not helpful; scaffold just the missing row.
            print(f"{{{{Speedrun Record|{e.missing_category_wikitext}|N/A|N/A|N/A|N/A}}}}\n")
        else:
            print(scaffold_rows(mapping_entries, section_name))
        return 3

    # Emit mode: print the updated section block and exit (no save).
    if emit:
        print(build_section_block(new_text, section_name))
        return 0

    if not changed:
        print("No changes.")
        return 0

    # Dry run: show diff only
    diff = unified_diff(old_text, new_text, fromfile=page_title, tofile=page_title)
    print(diff)

    if dry_run or not write:
        # signal that changes exist (cron-friendly)
        return 2

    # Write mode: one atomic edit
    try:
        page.text = new_text
        page.save(summary=f"Update speedrun.com WRs for {section_name} (automated)")
        print("Saved.")
        return 0
    except pywikibot.exceptions.PageSaveRelatedError:
        print("SAVE FAILED: Page save blocked (often CAPTCHA / AbuseFilter / permissions).")
        print("Try --emit to paste into a sandbox, or use an account exempt from CAPTCHA.")
        raise
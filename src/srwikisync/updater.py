import json
import difflib

import pywikibot
import yaml
import time

from .speedrun_api import get_leaderboard_top1
from .formatter import format_time, format_date, run_path_from_run, extract_runner_display
from .wiki import extract_section, replace_speedrun_record_row, MissingWikiRowError, scaffold_rows
from .wikiterms import load_wikiterms

def load_yaml(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def load_mapping(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def unified_diff(old: str, new: str, fromfile: str = "wiki_old", tofile: str = "wiki_new") -> str:
    lines = difflib.unified_diff(
        old.splitlines(True),
        new.splitlines(True),
        fromfile=fromfile,
        tofile=tofile,
        lineterm=""
    )
    return "\n".join(lines)

def update_section_for_mapping(
    page_text: str,
    section_name: str,
    mapping_entries: list[dict],
    api_base: str,
    user_agent: str,
) -> tuple[str, bool]:
    prefix, body, suffix = extract_section(page_text, section_name)
    new_body = body

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
        )
        if run is None:
            # If no run exists, skip; later you may want to report this.
            continue

        user_cache = {}
        runner = extract_runner_display(run, api_base, user_agent, user_cache)
        time.sleep(0.15)    # pause between API calls
        time_str = format_time(run["times"]["primary_t"])
        date_str = format_date(run.get("date"))

        game_slug = sr["game"]  # e.g. "tlozph"
        run_path = run_path_from_run(run, game_slug)

        if not isinstance(new_body, str):
            raise RuntimeError(f"Section body is not a string (got {type(new_body)}). Check section extraction.")

        new_body = replace_speedrun_record_row(
            new_body,
            wiki_category_wikitext=wiki_cat,
            runner=runner,
            time_str=time_str,
            date_str=date_str,
            run_path=run_path,
        )

    new_text = prefix + new_body + suffix
    changed = (new_text != page_text)
    return new_text, changed

def run_update(
    config_path: str,
    mapping_path: str,
    dry_run: bool,
    write: bool,
) -> int:
    cfg = load_yaml(config_path)
    wikiterms_path = cfg.get("wiki", {}).get("wikiterms_file")
    wikiterms = load_wikiterms(wikiterms_path)
    family = cfg["wiki"]["family"]
    lang = cfg["wiki"]["lang"]
    page_title = cfg["wiki"]["page_title"]
    section_name = cfg["behavior"]["section_name"]
    api_base = cfg["speedrun"]["api_base"]
    user_agent = cfg["speedrun"]["user_agent"]

    mapping_entries = load_mapping(mapping_path)

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
        )
    except MissingWikiRowError as e:
        print(f"ABORT: The wiki section is missing at least one expected row: {e.missing_category_wikitext}")
        print("\nPaste these rows into the section (order as you like), then re-run:\n")
        print(scaffold_rows(mapping_entries, section_name, wikiterms=wikiterms))
        return 3


    if not changed:
        print("No changes.")
        return 0

    diff = unified_diff(old_text, new_text, fromfile=page_title, tofile=page_title)
    print(diff)

    if write and not dry_run:
        page.text = new_text
        page.save(summary=f"Update speedrun.com WRs for {section_name} (automated)")
        print("Saved.")
        return 0

    # dry-run: signal “changes exist”
    return 2

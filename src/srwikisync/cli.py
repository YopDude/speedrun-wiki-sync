import argparse
import os
import sys
import glob
from pathlib import Path

from .updater import run_update, load_yaml


def _split_excludes(values: list[str] | None) -> list[str]:
    """Allow --exclude a,b,c and repeated --exclude flags."""
    out: list[str] = []
    for v in values or []:
        if not v:
            continue
        for part in v.split(","):
            part = part.strip()
            if part:
                out.append(part)
    return out


def _should_exclude(mapping_path: str, mapping_entries, excludes: set[str]) -> bool:
    if not excludes:
        return False

    p = Path(mapping_path)
    stem = p.stem

    # Try to infer game + section from mapping itself.
    section = None
    game = None
    if isinstance(mapping_entries, list) and mapping_entries:
        section = mapping_entries[0].get("section")
        sr = mapping_entries[0].get("sr") or {}
        game = sr.get("game")

    candidates = {stem}
    if section:
        candidates.add(section)
    if game:
        candidates.add(game)

    # Exact match only (case-sensitive) to avoid surprises.
    return any(c in excludes for c in candidates)

def main():
    ap = argparse.ArgumentParser(prog="srwikisync")
    ap.add_argument("--config", required=True, help="Path to wiki config YAML")
    ap.add_argument("--mapping", help="Path to mapping JSON (single-game mode)")
    ap.add_argument(
        "--all",
        action="store_true",
        help=(
            "Process all mapping JSON files in a directory (batch mode). "
            "Uses each file's embedded section id."
        ),
    )
    ap.add_argument(
        "--mapping-dir",
        default="mappings/zeldawiki",
        help=(
            "Directory containing mapping JSON files for --all (default: mappings/zeldawiki). "
            "All *.json files in this directory will be processed."
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
    ap.add_argument("--section", help="Wiki section id override (optional)")
    ap.add_argument("--dry-run", action="store_true", help="Print diff, do not save")
    ap.add_argument("--write", action="store_true", help="Save changes to the wiki (ignored if --dry-run)")
    ap.add_argument("--emit", action="store_true", help="Print updated section wikitext (no save)")
    ap.add_argument(
        "--no-blanks",
        action="store_true",
        help=(
            "Remove placeholder rows for mapping entries that have no verified run. "
            "In --emit/--write mode, this will prune rows that would otherwise remain N/A."
        ),
    )
    args = ap.parse_args()
    print("srwikisync: starting")

    if args.all and args.section:
        ap.error("--section override can't be used with --all (each mapping file provides its own section)")

    if not args.all and not args.mapping:
        ap.error("--mapping is required unless --all is used")

    cfg = load_yaml(args.config)
    pywikibot_dir = cfg["wiki"].get("pywikibot_dir")
    if pywikibot_dir:
        os.environ["PYWIKIBOT_DIR"] = pywikibot_dir

    # If not writing, default to dry-run unless --emit is used
    if args.emit:
        args.dry_run = True
        args.write = False
    elif not args.write:
        args.dry_run = True



    excludes = set(_split_excludes(args.exclude))

    # Batch mode: run once per mapping file.
    if args.all:
        mapping_dir = Path(args.mapping_dir)
        paths = sorted(glob.glob(str(mapping_dir / "*.json")))
        if not paths:
            print(f"No mapping JSON files found in {mapping_dir}")
            sys.exit(1)

        any_fail = False
        any_changed = False

        # Lazy import to avoid changing updater's public surface.
        from .updater import load_mapping

        for mp in paths:
            try:
                mapping_entries = load_mapping(mp)
                if _should_exclude(mp, mapping_entries, excludes):
                    print(f"[SKIP] {mp}")
                    continue

                print(f"[RUN ] {mp}")
                code = run_update(
                    section_override=None,
                    config_path=args.config,
                    mapping_path=mp,
                    dry_run=args.dry_run,
                    write=args.write,
                    emit=args.emit,
                    no_blanks=args.no_blanks,
                )
                if code not in (0, 2):
                    any_fail = True
                if code == 2:
                    any_changed = True
            except Exception as e:
                any_fail = True
                print(f"[FAIL] {mp}: {e}")

        # Exit codes:
        # - 0: all ok, no changes
        # - 2: at least one mapping would change (cron-friendly)
        # - 1: failures occurred
        if any_fail:
            sys.exit(1)
        if any_changed and (args.dry_run or not args.write):
            sys.exit(2)
        sys.exit(0)

    # Single mapping mode.
    code = run_update(
        section_override=args.section,
        config_path=args.config,
        mapping_path=args.mapping,
        dry_run=args.dry_run,
        write=args.write,
        emit=args.emit,
        no_blanks=args.no_blanks,
    )
    sys.exit(code)

if __name__ == "__main__":
    main()

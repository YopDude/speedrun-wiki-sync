import argparse
import os
import sys

from .updater import run_update, load_yaml

def main():
    ap = argparse.ArgumentParser(prog="srwikisync")
    ap.add_argument("--config", required=True, help="Path to wiki config YAML")
    ap.add_argument("--mapping", required=True, help="Path to mapping JSON")
    ap.add_argument("--dry-run", action="store_true", help="Print diff, do not save")
    ap.add_argument("--write", action="store_true", help="Save changes to the wiki (ignored if --dry-run)")
    args = ap.parse_args()
    print("srwikisync: starting")
    cfg = load_yaml(args.config)
    pywikibot_dir = cfg["wiki"].get("pywikibot_dir")
    if pywikibot_dir:
        os.environ["PYWIKIBOT_DIR"] = pywikibot_dir

    # Safety: require explicit --write to save
    if not args.write:
        args.dry_run = True

    code = run_update(
        config_path=args.config,
        mapping_path=args.mapping,
        dry_run=args.dry_run,
        write=args.write,
    )
    sys.exit(code)

if __name__ == "__main__":
    main()

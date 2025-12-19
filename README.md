# speedrun-wiki-sync

Sync speedrun.com world record times into MediaWiki pages (via Pywikibot) using a config-driven mapping.

This repo is designed to be reusable across different communities/wikis:
- You define **what rows exist** on the wiki (mapping JSON).
- The bot **updates only those rows** (no auto-creation of new categories/rows).
- Dry-run mode prints a unified diff.
- Write mode performs a single atomic edit.

## Current status (Zelda Wiki)
✅ Phantom Hourglass pipeline working end-to-end in dry-run  
⚠️ Writing is currently blocked by a site CAPTCHA (ConfirmEdit) for bot/API edits.

## Repository structure

    speedrun-wiki-sync/
    ├── configs/
    ├── mappings/
    ├── scripts/
    └── src/
        └── srwikisync/

## Requirements

- Python 3.10+
- A working Pywikibot setup (family file + bot login)
- Network access to speedrun.com and your wiki

Dependencies (installed via pip):
- pywikibot
- requests
- PyYAML

## Setup

### 1) Create venv and install deps

From repo root:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install --upgrade pip setuptools wheel
    python -m pip install -e .

> If you are not using editable installs yet, you can also run with:
> `PYTHONPATH=src python -m srwikisync.cli ...`

### 2) Point to your Pywikibot config directory

This project expects Pywikibot to read your existing `user-config.py` / cookies via `PYWIKIBOT_DIR`.

Example:

    export PYWIKIBOT_DIR="/home/mint/pwb"

## Configuration

### configs/<wiki>.yaml

Example configs/zeldawiki.yaml:

    wiki:
      family: zw
      lang: en
      page_title: Speedrun_Records
      pywikibot_dir: /home/mint/pwb

    speedrun:
      api_base: https://www.speedrun.com/api/v1
      user_agent: "SpeedrunWikiSync/0.1 (zeldawiki; maintainer: BotDude)"

    behavior:
      section_name: PH

### mappings/<wiki>/<game>.json

Mappings define the exact rows on-wiki the bot is allowed to update.
Each entry describes:
- the target <section begin="..."/> block
- the exact category wikitext (first template parameter)
- speedrun.com category + variable IDs to query

The bot will **abort** and print scaffold rows if the expected rows are missing.

## Usage

### Dry-run (prints diff, makes no edits)

    export PYWIKIBOT_DIR="/home/mint/pwb"
    PYTHONPATH=src python -m srwikisync.cli \
      --config configs/zeldawiki.yaml \
      --mapping mappings/zeldawiki/phantom_hourglass.json \
      --dry-run

### Write mode (performs one atomic edit)

    export PYWIKIBOT_DIR="/home/mint/pwb"
    PYTHONPATH=src python -m srwikisync.cli \
      --config configs/zeldawiki.yaml \
      --mapping mappings/zeldawiki/phantom_hourglass.json \
      --write

## Safety model

- Updates only inside a named `<section begin="X"/> ... <section end="X"/>`
- Updates only rows matching the exact `{{Speedrun Record|<category>|<player>|<time>|<date>}}`
- Does **not** auto-add new categories/rows
- Writes at most **one edit per run**
- Skips save when no changes

## CAPTCHA / ConfirmEdit note (important)

Some wikis enforce a CAPTCHA for API-based edits (ConfirmEdit). If enabled, Pywikibot saves will fail with a CAPTCHA error.

Recommended fix:
- Ask an admin to exempt the bot account (or the bot group) from CAPTCHA / ConfirmEdit for edits.

This is an admin-side configuration; the bot does not attempt to solve CAPTCHAs.

## License
This project is licensed under the Creative Commons Attribution-NonCommercial 4.0 International License.

You are free to use, modify, and share this project for non-commercial purposes only.

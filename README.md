# speedrun-wiki-sync

A small, config‑driven tool that keeps **speedrun.com world record data** in sync with **MediaWiki pages**.

In plain terms:

* You tell it *which wiki pages exist*
* You tell it *which speedrun.com categories belong in which rows*
* The tool fetches the latest records and updates only those rows

It **does not guess**, **does not create new rows**, and **does not restructure pages**. Everything the bot touches is explicitly defined by you.

For any queries, feel free to contact me on:
DaYopDude@proton.me
yopDude on Discord

---

## Project status

✅ **Functionality is essentially finished**

The main workflow works end‑to‑end:

1. Fetch runs from speedrun.com
2. Match them against your mappings
3. Generate updated wikitext
4. Show you what would change, or apply it
---

## Things to do

- Run the sync script as an automated job with proper logging
- Add a monthly summary email (changes applied, failures, new records)
- Add case-by-case notification emails when new mappings or manual action is required

## What this tool actually does

At a high level, the tool:

* Pulls verified world‑record runs from the speedrun.com API
* Normalizes category names, variables, and labels
* Matches runs to *pre‑defined wiki rows*
* Regenerates the affected wiki text
* Either:

  * shows you a diff (preview), or
  * writes the changes to the wiki

Important boundaries:

* If a run is **not mapped**, it is ignored
* If a wiki row is **not declared**, it is never touched
* The bot never invents new structure

This makes it safe to run repeatedly.

---

## Project Pipeline

1. **Mappings** describe *what belongs where*
2. **Wiki terms** help translate naming differences
3. The **API layer** fetches and cleans run data
4. The **renderer** updates only mapped rows
5. The **CLI** decides whether to preview, save, or export

---

## Folder and file structure

Here is how the repository is organised and how each part is used:

### `mapping/`

* Each `.json` file usually represents **one game**
* Each file lists:

  * which wiki page(s) are involved
  * which rows already exist on that page
  * which speedrun.com categories feed those rows

Only data described here will ever be used.

---

### `wikiterms/`

Speedrun.com names and wiki names often do not match exactly.

This folder contains dictionaries that say:

> “When the API says *this*, the wiki means *that*.”

They are used during matching so mappings stay readable and stable.

Examples of what goes here:

* Category name variants
* Variable label differences
* Region / platform wording differences

---

### `wikiterms/curations/`

This folder is for **exceptions**.

Use curations when:

* One game breaks otherwise global rules
* A category is intentionally named differently on the wiki
* The API is inconsistent for a specific title

Curations override normal wiki terms and only apply where needed.

---

### Other folders

* `api/` – talks to speedrun.com and normalizes run data
* `wiki/` – builds new wiki text and generates diffs
* `sync.py` – main entry point and command‑line handling

---

## Running the tool

This project is typically used in two phases:

1. **Generate or update mapping files** (one-time or occasional)
2. **Run the sync tool** to preview or apply updates

---

### Generating mappings (helper script)

This step helps you *create* mapping files by inspecting speedrun.com categories and laying out a starting structure.

```bash
python scripts/gen_mapping.py \
  --section "Linked Oracles" \
  --game "oracle" \
  --out ./mappings/zeldawiki/oracle_linked.json \
  --all-categories
```

What this does:

* `--section "OoT"`
  The name of the section as it already exists on the wiki page.

* `--game "oot"`
  The speedrun.com game slug to pull categories from.

* `--out ./mappings/zeldawiki/ocarina.json`
  Where the generated mapping file will be written.

* `--all-categories`
  Includes all categories found for the game, giving you a complete starting point to edit and refine.

The output file is **not meant to be final**. You are expected to edit it by hand to match real wiki rows.

---

## Previewing changes (recommended)

```bash
PYTHONPATH=src python -m srwikisync.cli \
  --config configs/zeldawiki.yaml \
  --mapping ./mappings/zeldawiki/ocarina.json \
  --dry-run
```

This is the safest mode and the default.

What each argument means:

* `--config configs/zeldawiki.yaml`
  Points to your main configuration file. This usually contains:

  * wiki connection details
  * bot username
  * site-specific settings

* `--mapping ./mappings/zeldawiki/ocarina.json`
  Tells the tool exactly which mapping file to use. Only the pages and rows defined in this file will be touched.

* `--dry-run`
  Runs the full pipeline but **does not save anything**.

What happens when you run this:

* Runs are fetched from speedrun.com
* Wiki terms and curations are applied
* Rows defined in the mapping are updated
* A readable diff is printed showing what *would* change

No wiki edits are made.

Use this as often as you want.

---

## Writing changes to the wiki

```bash
PYTHONPATH=src python -m srwikisync.cli \
  --config configs/zeldawiki.yaml \
  --mapping ./mappings/zeldawiki/ocarina.json \
  --write
```

This command uses the same inputs as a dry run, but actually applies the changes.

Arguments explained:

* `--config configs/zeldawiki.yaml`
  Same config file as before. Nothing about your setup changes between dry-run and write.

* `--mapping ./mappings/zeldawiki/ocarina.json`
  The specific game / page mapping to apply.

* `--write`
  Enables saving the updated wiki text.

What happens when you run this:

* All changes are prepared in memory first
* The page is saved once with the full update
* No partial or incremental edits are made

If saving fails, it is usually due to wiki-side restrictions (see CAPTCHA note below).

---

## Exporting wiki text to a file

```bash
PYTHONPATH=src python -m srwikisync.cli \
  --config configs/zeldawiki.yaml \
  --mapping ./mappings/zeldawiki/ocarina.json \
  --emit output.txt
```

This mode generates wiki text without touching the wiki.

Arguments explained:

* `--emit output.txt`
  Writes the generated wiki text to the given file path.

What happens when you run this:

* Runs are fetched and mapped as usual
* Updated wiki text is rendered
* The result is written to `output.txt`

Useful for:

* Reviewing output
* Manual posting
* Debugging mappings

---

## Running everything at once (`--all`)

```bash
PYTHONPATH=src python -m srwikisync.cli \
  --config configs/zeldawiki.yaml \
  --all \
  --dry-run
```

The `--all` flag tells the tool to ignore `--mapping` and instead:

* Find **every `.json` file** in the mappings folder
* Run each mapping one after another

Arguments explained:

* `--all`
  Enables batch mode across all mapping files.

* `--dry-run` / `--write` / `--emit`
  Apply the chosen action to **every mapping**.

Examples:

```bash
--all --write
```

Applies changes for all games to the wiki.

```bash
--all --emit out/
```

Writes one output file per mapping into the `out/` directory.

This is most useful when maintaining many games or doing routine updates.

---

## CAPTCHA / ConfirmEdit warning

Some wikis block automated edits using CAPTCHA (ConfirmEdit).

If this is enabled:

* `--write` will fail
* `--dry-run` and `--emit` still work

The fix is wiki‑side:

* Ask an admin to exempt the bot account from ConfirmEdit

The tool does not attempt to bypass CAPTCHA.

---

## Curations (advanced mapping control)

Curations let you handle edge cases where speedrun.com’s data model does not map cleanly to how the wiki presents categories.
They are **optional**, per-game overrides and are only applied when a curation file exists.

Curations live in:

```
mappings/zeldawiki/curation/
```

Each file is named after the **mapping filename stem**.

Example:
```
mappings/zeldawiki/hyrule_warriors_age_of_imprisonment.json
→ mappings/zeldawiki/curation/hyrule_warriors_age_of_imprisonment.json
```

If no curation file exists for a mapping, default behaviour is used.

---

### Existing curation rules (backwards compatible)

- `contains`  
  Substrings that exclude categories if matched.

- `contains_exceptions`  
  Overrides for specific allowed cases.

Legacy list-only curations are still supported and treated as a deny list.

---

### New curation rules (label + query control)

#### `label_vars_drop`

Removes speedrun.com **variable IDs** from the displayed wiki label only.

```json
{
  "label_vars_drop": ["j84pqgw8"]
}
```

---

#### `query_vars_drop`

Removes speedrun.com **variable IDs** from leaderboard API queries.

This is required when a variable exists on speedrun.com but querying with it returns no runs.

```json
{
  "label_vars_drop": ["j84pqgw8"],
  "query_vars_drop": ["j84pqgw8"]
}
```

---

### Automatic de-duplication

When dropped query variables cause multiple combinations to collapse into the same category,
duplicate mapping entries are automatically skipped.

Two entries are considered identical if they share:
- section
- wiki category label
- game
- category ID
- query variables

## License

Creative Commons Attribution–NonCommercial 4.0 International (CC BY‑NC 4.0)

Free for non‑commercial use, modification, and sharing.

---
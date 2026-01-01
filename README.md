# speedrun-wiki-sync

A small, config-driven tool for keeping **speedrun.com world record data** in sync with **MediaWiki pages**.

In short:

- You define which wiki pages exist
- You define which speedrun.com categories map to which rows
- The tool fetches records and updates *only* those rows

It does not guess, invent structure, or modify anything that hasn’t been explicitly defined.

---

## Project status

**Completed. External adoption declined. (Not in use)**

The full workflow works end-to-end:

1. Fetch runs from speedrun.com  
2. Match them against explicit mappings  
3. Generate updated wikitext  
4. Either preview the changes or apply them  

---

## Possible future work (not planned)

- Run as a scheduled job with logging  
- Periodic summary emails (records changed, failures, unmapped categories)  
- Optional notifications when manual intervention is needed  

These were considered but not implemented.

---

## What the tool actually does

At a high level, the tool:

- Pulls verified world-record runs from the speedrun.com API
- Normalizes category names, variables, and labels
- Matches runs to **pre-declared wiki rows only**
- Regenerates the affected wiki text

It then either:

- prints a readable diff, or
- writes the updated text to the wiki

Important boundaries:

- If a run is **not mapped**, it is ignored
- If a wiki row is **not declared**, it is never touched
- No new rows or sections are created

This makes it safe to run repeatedly.

---

## Pipeline overview

1. **Mappings** define what belongs where
2. **Wiki terms** translate naming differences
3. The **API layer** fetches and cleans run data
4. The **renderer** updates mapped rows only
5. The **CLI** controls preview vs write behavior

---

## Repository structure

### `mapping/`

- Each `.json` file usually represents one game
- Each file lists:
  - the target wiki page(s)
  - the rows that already exist
  - the speedrun.com categories that feed those rows

Only data defined here is ever used.

---

### `wikiterms/`

Speedrun.com naming does not always match wiki naming.

This folder contains translation dictionaries used during matching, for example:

- category name variants
- variable label differences
- platform / region wording

These keep mappings readable and stable.

---

### `wikiterms/curations/`

Curations handle exceptions.

Use these when:

- a game breaks otherwise global rules
- a category is intentionally named differently
- the API behaves inconsistently for a specific title

Curations override normal wiki terms and apply only where present.

---

### Other directories

- `api/` – speedrun.com API access and normalization
- `wiki/` – wikitext generation and diffing
- `sync.py` – main entry point and CLI handling

---

## Typical usage

The project is usually used in two phases:

1. Generate or update mapping files (occasional)
2. Run the sync tool to preview or apply updates

---

## Generating mappings (helper script)

This script inspects speedrun.com categories and produces a starting mapping file.

```bash
python scripts/gen_mapping.py \
  --section "Linked Oracles" \
  --game "oracle" \
  --out ./mappings/zeldawiki/oracle_linked.json \
  --all-categories
```

This generates a **starting point only**.  
The output is expected to be edited by hand to match real wiki rows.

---

## Previewing changes (recommended)

```bash
PYTHONPATH=src python -m srwikisync.cli \
  --config configs/zeldawiki.yaml \
  --mapping ./mappings/zeldawiki/ocarina.json \
  --dry-run
```

This runs the full pipeline without saving anything.

What happens:

- Runs are fetched
- Wiki terms and curations are applied
- Only mapped rows are updated
- A readable diff is printed

No wiki edits are made.

---

## Writing changes to the wiki

```bash
PYTHONPATH=src python -m srwikisync.cli \
  --config configs/zeldawiki.yaml \
  --mapping ./mappings/zeldawiki/ocarina.json \
  --write
```

Behavior is identical to `--dry-run`, except the page is saved once with the full update.

If saving fails, it is usually due to wiki-side restrictions (see CAPTCHA note).

---

## Exporting wiki text to a file

```bash
PYTHONPATH=src python -m srwikisync.cli \
  --config configs/zeldawiki.yaml \
  --mapping ./mappings/zeldawiki/ocarina.json \
  --emit output.txt
```

This renders updated wiki text to a file without touching the wiki.

Useful for review, debugging, or manual posting.

---

## Batch mode (`--all`)

```bash
PYTHONPATH=src python -m srwikisync.cli \
  --config configs/zeldawiki.yaml \
  --all \
  --dry-run
```

The `--all` flag runs the chosen action across every mapping file.

Examples:

```bash
--all --write
```

Apply updates for all games.

```bash
--all --emit out/
```

Write one output file per mapping.

---

## CAPTCHA / ConfirmEdit note

Some wikis block automated edits via CAPTCHA.

If enabled:

- `--write` will fail
- `--dry-run` and `--emit` still work

The fix is wiki-side: exempt the bot account from ConfirmEdit.

The tool does not attempt to bypass CAPTCHA.

---

## Curations (advanced)

Curations handle cases where the speedrun.com data model doesn’t line up cleanly with wiki presentation.

They are optional, per-game overrides and only apply when present.

Location:

```
mappings/zeldawiki/curation/
```

Filename must match the mapping filename.

---

### Supported rules

- `contains` – exclude categories by substring
- `contains_exceptions` – allow specific exceptions

Legacy list-only curations are still supported.

---

### Variable handling

#### `label_vars_drop`

Drops variable IDs from displayed wiki labels.

```json
{
  "label_vars_drop": ["j84pqgw8"]
}
```

---

#### `query_vars_drop`

Drops variable IDs from leaderboard API queries.

Required when querying with a variable returns no runs.

```json
{
  "label_vars_drop": ["j84pqgw8"],
  "query_vars_drop": ["j84pqgw8"]
}
```

---

### Automatic de-duplication

If dropping query variables causes multiple mappings to collapse into the same category,
duplicates are automatically skipped.

Entries are considered identical if they share:

- section
- wiki label
- game
- category ID
- query variables

---

## License

Creative Commons Attribution–NonCommercial 4.0 International (CC BY-NC 4.0)

Free for non-commercial use, modification, and sharing.

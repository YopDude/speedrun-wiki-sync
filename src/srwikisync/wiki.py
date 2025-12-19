import re

def extract_section(text: str, name: str) -> tuple[str, str, str]:
    """
    Tolerant parser for:
      <section begin="NAME"/>   (with optional whitespace)
      <section end="NAME"/>     (with optional whitespace)

    Returns (prefix_including_begin_tag, body_between_tags, suffix_including_end_tag_and_rest).
    """
    pattern = re.compile(
        rf'(?P<prefix>.*?<section\s+begin="{re.escape(name)}"\s*/>\s*)'
        rf'(?P<body>.*?)'
        rf'(?P<suffix>\s*<section\s+end="{re.escape(name)}"\s*/>.*)',
        re.DOTALL
    )
    m = pattern.match(text)
    if not m:
        raise RuntimeError(
            f'Section "{name}" not found. Expected tags like <section begin="{name}"/> and <section end="{name}"/> '
            f'(whitespace is OK).'
        )
    return m.group("prefix"), m.group("body"), m.group("suffix")



def replace_speedrun_record_row(section_body: str, wiki_category_wikitext: str, runner: str, time_str: str, date_str: str, run_path: str) -> str:
    """
    Replaces exactly one row of the form:
    {{Speedrun Record|<wiki_category_wikitext>|...|...|...|...}}
    matched by the first parameter.
    """
    # Match row starting with the exact wikitext category parameter.
    # Non-greedy match until the end of the template instance.
    row_re = re.compile(
        r"(\{\{Speedrun Record\|)"
        + re.escape(wiki_category_wikitext)
        + r"\|.*?\}\}",
        re.DOTALL
    )

    replacement = f"{{{{Speedrun Record|{wiki_category_wikitext}|{runner}|{time_str}|{date_str}|{run_path}}}}}"
    new_body, n = row_re.subn(replacement, section_body, count=1)
    if n == 0:
        raise MissingWikiRowError(wiki_category_wikitext)
    return new_body


class MissingWikiRowError(RuntimeError):
    def __init__(self, missing_category_wikitext: str):
        super().__init__(f"Missing wiki row for category wikitext: {missing_category_wikitext!r}")
        self.missing_category_wikitext = missing_category_wikitext


def scaffold_rows(mapping_entries: list[dict], section_name: str, wikiterms: dict | None = None) -> str:
    rows = []
    for entry in mapping_entries:
        if entry.get("section") != section_name:
            continue
        cat = entry["wiki_category_wikitext"]
        if wikiterms:
            from srwikisync.wikiterms import apply_wikiterms_outside_links
            cat = apply_wikiterms_outside_links(cat, wikiterms)
        rows.append(f"{{{{Speedrun Record|{cat}|<player>|<time>|<date>|<run_path>}}}}")
    return "\n".join(rows) + "\n"

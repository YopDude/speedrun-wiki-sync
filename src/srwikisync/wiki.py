import re

def extract_section(text: str, name: str) -> tuple[str, str, str]:
    pattern = re.compile(
        rf'(?P<prefix>.*?<section\s+begin="{re.escape(name)}"\s*/>\s*)'
        rf'(?P<body>.*?)'
        rf'(?P<suffix>\s*<section\s+end="{re.escape(name)}"\s*/>.*)',
        re.DOTALL
    )
    m = pattern.match(text)
    if not m:
        raise RuntimeError(
            f'Section "{name}" not found.'
        )
    return m.group("prefix"), m.group("body"), m.group("suffix")


def normalize_category_wikitext(s: str) -> str:
    s = re.sub(r"\{\{Small\|\((.*?)\)\}\}", r"\1", s, flags=re.DOTALL)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _split_template_params(body: str) -> list[str]:
    params: list[str] = []
    buf: list[str] = []
    i = 0
    depth_tpl = 0
    depth_link = 0

    while i < len(body):
        if body.startswith("[[", i):
            depth_link += 1
            buf.append("[[")
            i += 2
            continue
        if body.startswith("]]", i) and depth_link > 0:
            depth_link -= 1
            buf.append("]]")
            i += 2
            continue
        if body.startswith("{{", i):
            depth_tpl += 1
            buf.append("{{")
            i += 2
            continue
        if body.startswith("}}", i) and depth_tpl > 0:
            depth_tpl -= 1
            buf.append("}}")
            i += 2
            continue

        ch = body[i]
        if ch == "|" and depth_tpl == 0 and depth_link == 0:
            params.append("".join(buf))
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    params.append("".join(buf))
    return params



def normalize_category_wikitext(s: str) -> str:
    """Normalize category wikitext for matching purposes.

    - Strips {{Small|(...)}} wrappers
    - Removes presentational parentheses
    - Collapses whitespace
    """
    s = re.sub(r"\{\{Small\|\((.*?)\)\}\}", r"\1", s, flags=re.DOTALL)
    s = s.replace("(", "").replace(")", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _split_template_params(body: str) -> list[str]:
    """Split template params by top-level '|' (not inside [[...]] or {{...}})."""
    params: list[str] = []
    buf: list[str] = []
    i = 0
    depth_tpl = 0
    depth_link = 0

    while i < len(body):
        if body.startswith("[[", i):
            depth_link += 1
            buf.append("[[")
            i += 2
            continue
        if body.startswith("]]", i) and depth_link > 0:
            depth_link -= 1
            buf.append("]]")
            i += 2
            continue

        if body.startswith("{{", i):
            depth_tpl += 1
            buf.append("{{")
            i += 2
            continue
        if body.startswith("}}", i) and depth_tpl > 0:
            depth_tpl -= 1
            buf.append("}}")
            i += 2
            continue

        ch = body[i]
        if ch == "|" and depth_tpl == 0 and depth_link == 0:
            params.append("".join(buf))
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    params.append("".join(buf))
    return params


def _iter_template_invocations(text: str, template_name: str):
    """Yield (start, end, full_text) for each {{template_name|...}} invocation.

    Uses a brace-depth scanner so nested templates like {{Small|(...)}} are safe.
    """
    needle = "{{" + template_name + "|"
    i = 0
    n = len(text)
    while True:
        start = text.find(needle, i)
        if start == -1:
            return
        j = start
        depth = 0
        while j < n:
            if text.startswith("{{", j):
                depth += 1
                j += 2
                continue
            if text.startswith("}}", j):
                depth -= 1
                j += 2
                if depth == 0:
                    end = j
                    yield start, end, text[start:end]
                    i = end
                    break
                continue
            j += 1
        else:
            return


def replace_speedrun_record_row(
    section_body: str,
    wiki_category_wikitext: str,
    runner: str,
    time_str: str,
    date_str: str,
    run_path: str,
) -> str:
    """Replace exactly one {{Speedrun Record|...}} row, matched by its first parameter.

    Matching is tolerant of {{Small|(...)}} wrappers and presentational parentheses in the existing wiki row.
    When replacing, we preserve the existing category parameter formatting to avoid churn.
    """
    expected_norm = normalize_category_wikitext(wiki_category_wikitext)

    for start, end, full in _iter_template_invocations(section_body, "Speedrun Record"):
        inner = full[len("{{Speedrun Record|"):-2]
        params = _split_template_params(inner)
        if not params:
            continue
        existing_cat = params[0]
        if normalize_category_wikitext(existing_cat) != expected_norm:
            continue

        replacement = f"{{{{Speedrun Record|{existing_cat}|{runner}|{time_str}|{date_str}|{run_path}}}}}"
        return section_body[:start] + replacement + section_body[end:]

    raise MissingWikiRowError(wiki_category_wikitext)


def remove_speedrun_record_row(section_body: str, wiki_category_wikitext: str) -> str:
    """Remove a {{Speedrun Record|...}} row matched by its first parameter.

    Matching uses the same normalization as replace_speedrun_record_row().
    If no matching row exists, returns the body unchanged.

    This is used by the updater when --no-blanks is enabled to prune scaffolded
    N/A rows for mapping entries that have no verified run.
    """
    expected_norm = normalize_category_wikitext(wiki_category_wikitext)

    for start, end, full in _iter_template_invocations(section_body, "Speedrun Record"):
        inner = full[len("{{Speedrun Record|"):-2]
        params = _split_template_params(inner)
        if not params:
            continue
        existing_cat = params[0]
        if normalize_category_wikitext(existing_cat) != expected_norm:
            continue

        # Remove the invocation and a single surrounding newline if present.
        before = section_body[:start]
        after = section_body[end:]
        if after.startswith("\n"):
            after = after[1:]
        elif before.endswith("\n"):
            before = before[:-1]
        return before + after

    return section_body


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
        rows.append(f"{{{{Speedrun Record|{cat}|N/A|N/A|N/A|N/A}}}}")
    return "\n".join(rows) + "\n"

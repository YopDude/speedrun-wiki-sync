import json
import re
from typing import Dict

LINK_RE = re.compile(r"\[\[.*?\]\]")  # minimal wiki-link matcher

def load_wikiterms(path: str | None) -> Dict[str, str]:
    if not path:
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def apply_wikiterms_outside_links(text: str, terms: Dict[str, str]) -> str:
    """
    Replace phrases only in segments that are NOT inside [[...]].
    Sort longer keys first to avoid partial replacements.
    """
    if not terms:
        return text

    # Split into alternating [outside, link, outside, link...]
    parts = []
    last = 0
    for m in LINK_RE.finditer(text):
        parts.append(("outside", text[last:m.start()]))
        parts.append(("link", m.group(0)))
        last = m.end()
    parts.append(("outside", text[last:]))

    keys = sorted(terms.keys(), key=len, reverse=True)

    out = []
    for kind, seg in parts:
        if kind == "outside":
            for k in keys:
                seg = seg.replace(k, terms[k])
        out.append(seg)
    return "".join(out)

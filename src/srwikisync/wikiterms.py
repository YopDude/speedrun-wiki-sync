import json
import re
from typing import Dict, Any

LINK_RE = re.compile(r"\[\[.*?\]\]")  # minimal wiki-link matcher


def load_wikiterms(path: str | None, section_id: str | None = None) -> Dict[str, str]:
    """
    Load substitutions from a wikiterms JSON file.

    Supported formats (backwards compatible):

    1) Flat mapping:
       { "Any%": "[[Any%]]", ... }

    2) Scoped mapping:
       {
         "Master Quest": {
           "default": "[[Master Quest]]",
           "sections": { "HW": "[[Master Quest Map]]" }
         }
       }

    For scoped entries:
    - If section_id matches a key in "sections", that value is used
    - Else if "default" is provided, that is used
    - Else the entry is ignored
    """
    if not path:
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data: Any = json.load(f)

    if not isinstance(data, dict):
        return {}

    out: Dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(k, str) or not k:
            continue

        if isinstance(v, str):
            out[k] = v
            continue

        if isinstance(v, dict):
            chosen: str | None = None

            if section_id and isinstance(v.get("sections"), dict):
                sv = v["sections"].get(section_id)
                if isinstance(sv, str) and sv:
                    chosen = sv

            if chosen is None:
                dv = v.get("default")
                if isinstance(dv, str) and dv:
                    chosen = dv

            if chosen is not None:
                out[k] = chosen

    return out


def apply_wikiterms_outside_links(text: str, terms: Dict[str, str]) -> str:
    """
    Replace phrases only in segments that are NOT inside [[...]].

    This prevents turning already-linked terms into nested links.
    """
    if not text or not terms:
        return text

    parts: list[tuple[str, str]] = []
    last = 0
    for m in LINK_RE.finditer(text):
        parts.append(("outside", text[last : m.start()]))
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

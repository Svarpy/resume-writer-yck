"""Date ranges as written on resumes ("June 2026 – Present", "2019 – 2021", "05/2020 - 08/2021")."""

from __future__ import annotations

import re
from typing import Optional

_MONTH = (r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|"
          r"Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
_POINT = rf"(?:{_MONTH}\s+\d{{4}}|\d{{1,2}}/\d{{4}}|\d{{4}})"
_END = rf"(?:{_POINT}|Present|Current|Now|Ongoing|Till\s+Date|To\s+Date)"
DATE_RANGE = re.compile(rf"\b{_POINT}\s*(?:-|–|—|to)\s*{_END}\b", re.IGNORECASE)
DATE_SINGLE = re.compile(rf"^\s*(?:{_MONTH}\s+\d{{4}}|\d{{4}})\s*$", re.IGNORECASE)


def find_date(text: str) -> Optional[tuple[int, int]]:
    match = DATE_RANGE.search(text)
    if match:
        return match.start(), match.end()
    if DATE_SINGLE.match(text):
        stripped = text.strip()
        start = text.index(stripped)
        return start, start + len(stripped)
    return None

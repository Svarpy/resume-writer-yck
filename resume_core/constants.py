"""Application-wide constants (version, theme palettes, date patterns).

User-specific values (name, output folder, fonts, education, ...) are settings stored by the
server, see ``resume_core.settings``.
"""

from __future__ import annotations

import re

APP_VERSION = "v3.0.0Beta3"

# Every released version, oldest first, with its release date when known. The server records these in
# its `system` collection; add a line here whenever APP_VERSION is bumped (new versions are also
# registered automatically the first time a server of that version starts).
VERSION_HISTORY: tuple[tuple[str, str], ...] = (
    ("v1.0", "2026-07-14"),
    ("v1.1", "2026-07-14"),
    ("v2.0", "2026-08-27"),
    ("v2.1", "2026-09-17"),
    ("v3.0.0Beta2", "2026-09-23"),
)

MONTH_PATTERN = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
DATE_RANGE_RE = re.compile(
    rf"\b(?:{MONTH_PATTERN})\s+\d{{4}}\s*(?:-|–|—|to)\s*(?:Present|Current|(?:{MONTH_PATTERN})\s+\d{{4}})\b",
    re.IGNORECASE,
)

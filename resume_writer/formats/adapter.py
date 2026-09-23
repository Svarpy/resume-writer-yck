"""Adapter bridging format store specs to the writer."""

from __future__ import annotations

from typing import Optional

from resume_writer.formats.models import ResumeFormatSpec, default_format_spec
from resume_writer.formats.store import get_primary_format

def get_format_for_writer(username: Optional[str] = None) -> ResumeFormatSpec:
    """Resolve the format the writer should use.

    - Signed-in user → primary format (fallback to default if missing)
    - No user → protected default application format
    """
    if not username:
        return default_format_spec()
    try:
        return get_primary_format(username)
    except Exception:
        return default_format_spec()

"""TLS helpers for updater HTTPS calls.

macOS python.org builds often ship without a usable system CA store, which
causes ``CERTIFICATE_VERIFY_FAILED`` against GitHub. Prefer certifi's Mozilla
CA bundle when available; fall back to the default SSL context.
"""

from __future__ import annotations

import ssl


def create_ssl_context() -> ssl.SSLContext:
    """Return an SSL context that can verify public HTTPS endpoints."""
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())

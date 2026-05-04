"""
Shared ChromaDB client factory.

ChromaDB 0.6.x calls PostHog with the pre-7.x capture signature. Some local
environments resolve PostHog 7.x, which raises noisy telemetry errors even when
anonymized telemetry is disabled. This module disables telemetry before any
PersistentClient is created.
"""

from __future__ import annotations

import logging

import chromadb
from chromadb.config import Settings


def _disable_chromadb_telemetry() -> None:
    """Disable Chroma/PostHog telemetry and tolerate PostHog API changes."""
    try:
        import posthog

        posthog.disabled = True

        def _noop_capture(*args, **kwargs):
            return None

        posthog.capture = _noop_capture
    except Exception:
        # Telemetry should never block local retrieval or evaluation.
        pass

    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)


def get_chroma_client(path: str = "data/chroma") -> chromadb.PersistentClient:
    """
    Create a Chroma PersistentClient with telemetry disabled.

    Args:
        path: Local Chroma persistence directory.

    Returns:
        Configured ChromaDB PersistentClient.
    """
    _disable_chromadb_telemetry()
    return chromadb.PersistentClient(
        path=path,
        settings=Settings(anonymized_telemetry=False),
    )

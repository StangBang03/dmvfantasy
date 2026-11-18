#!/usr/bin/env python3
"""Retired legacy normalizer.

This script generated public ESPN member identifiers and wrote a schema that
no longer matches the production datasets. It is intentionally disabled to
prevent accidental re-publication or destructive replacement of normalized
history. Use the maintained refresh pipeline and its private
ESPN_OWNER_MAP_JSON secret instead.
"""

raise SystemExit(
    "scripts/normalize_espn.py is retired and intentionally disabled. "
    "It must not be used to regenerate production datasets."
)

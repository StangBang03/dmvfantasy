"""Backward-compatible entry point for the canonical records engine.

The original file was malformed and duplicated the v3 implementation.
Keep this entry point as a thin wrapper so existing manual invocations
continue to work while all logic remains in build_records_engine_v3.py.
"""

from build_records_engine_v3 import main


if __name__ == "__main__":
    main()

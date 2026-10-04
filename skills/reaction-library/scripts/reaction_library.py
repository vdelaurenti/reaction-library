#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["Pillow>=10", "jsonschema>=4.18"]
# ///
"""reaction-library CLI. Run with: uv run reaction_library.py <command> [args]
(or ./reaction_library.py <command> on macOS and Linux)."""

import sys

from reaction_lib.cli import configure_utf8, main

if __name__ == "__main__":
    configure_utf8()
    sys.exit(main())

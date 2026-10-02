# /// script
# requires-python = ">=3.11"
# dependencies = ["Pillow>=10", "jsonschema>=4.18"]
# ///
"""reaction-library CLI. Run with: uv run reaction_library.py <command> [args]"""

import sys

from reaction_lib.cli import configure_utf8, main

if __name__ == "__main__":
    configure_utf8()
    sys.exit(main())

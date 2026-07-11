"""CLI entrypoint for the P0-T21 source-bound spec and fixture generator."""

from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from validation.tools._zero_start_call_continue_slice_generator.cli import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())

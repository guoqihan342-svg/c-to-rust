from __future__ import annotations

import argparse
import json
from pathlib import Path

from .common import stable_json_bytes
from .constants import DEFAULT_FIXTURE, DEFAULT_INPUT, DEFAULT_SPEC, SLICE_ID
from .fixture import build_documents
from .source_binding import load_generator_input, validate_source_checkout


def write_or_check(path: Path, content: bytes, *, check: bool) -> None:
    if check:
        if not path.is_file() or path.read_bytes() != content:
            raise SystemExit(f"generated output drift: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--spec-out", type=Path, default=DEFAULT_SPEC)
    parser.add_argument("--fixture-out", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    generator_input = load_generator_input(args.input)
    if args.source_root is not None:
        validate_source_checkout(args.source_root, generator_input)
    spec, fixture = build_documents(generator_input)
    write_or_check(args.fixture_out, stable_json_bytes(fixture), check=args.check)
    write_or_check(args.spec_out, stable_json_bytes(spec), check=args.check)
    print(
        json.dumps(
            {
                "status": "checked" if args.check else "generated",
                "slice_id": SLICE_ID,
                "source_fragment_sha256": generator_input["source"]["fragment"]["sha256"],
                "fixture_sha256": spec["fixture_hash"],
            },
            sort_keys=True,
        )
    )
    return 0

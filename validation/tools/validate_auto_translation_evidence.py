#!/usr/bin/env python3
"""Validate bounded auto-translation evidence against committed schemas."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import jsonschema


REPO_ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-id", required=True)
    parser.add_argument("--slice-id", required=True)
    parser.add_argument("--slice-spec", type=Path)
    parser.add_argument("--evidence-root", default=REPO_ROOT / "validation" / "evidence", type=Path)
    args = parser.parse_args()

    evidence_dir = args.evidence_root / args.target_id / "auto-translation" / args.slice_id
    prefix = f"l3-{args.slice_id}"
    slice_spec = args.slice_spec or resolve_slice_spec(args.target_id, args.slice_id)
    checks = [
        ("validation/slice-spec-template/slice-spec.schema.json", slice_spec),
        ("validation/type-map-template/type-map.schema.json", evidence_dir / f"{prefix}-type-map.json"),
        ("validation/cfg-template/cfg.schema.json", evidence_dir / f"{prefix}-cfg.json"),
        ("validation/pointer-graph-template/pointer-graph.schema.json", evidence_dir / f"{prefix}-pointer-graph.json"),
        ("validation/test-translation-template/test-translation.schema.json", evidence_dir / f"{prefix}-test-translation-generated.json"),
        ("validation/l3-template/evidence-manifest.schema.json", evidence_dir / f"{prefix}-evidence-manifest.json"),
        ("validation/auto-translation-template/auto-translation-plan.schema.json", evidence_dir / f"{prefix}-auto-translation-plan.json"),
        ("validation/auto-translation-template/ai-candidate-manifest.schema.json", evidence_dir / f"{prefix}-ai-candidate-manifest.json"),
        ("validation/auto-translation-template/blocked-repairs.schema.json", evidence_dir / f"{prefix}-self-healing-blocked-repairs.json"),
    ]

    validated = []
    for schema_path, data_path in checks:
        validate_json(REPO_ROOT / schema_path, data_path)
        validated.append(rel(data_path))

    patch_schema = load_json(REPO_ROOT / "validation/auto-translation-template/patch-event.schema.json")
    patch_path = evidence_dir / f"{prefix}-patch-events.jsonl"
    patch_count = 0
    if patch_path.exists():
        for line in patch_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                jsonschema.validate(json.loads(line), patch_schema)
                patch_count += 1
    validated.append(rel(patch_path))

    event_schema = load_json(REPO_ROOT / "validation/auto-translation-template/auto-translation-event.schema.json")
    event_path = evidence_dir / f"{prefix}-auto-translation-events.jsonl"
    event_count = 0
    for line in event_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            jsonschema.validate(json.loads(line), event_schema)
            event_count += 1
    validated.append(rel(event_path))

    print(
        json.dumps(
            {
                "status": "passed",
                "target_id": args.target_id,
                "slice_id": args.slice_id,
                "validated": validated,
                "patch_event_count": patch_count,
                "auto_translation_event_count": event_count,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def validate_json(schema_path: Path, data_path: Path) -> None:
    jsonschema.validate(load_json(data_path), load_json(schema_path))


def resolve_slice_spec(target_id: str, slice_id: str) -> Path:
    spec_dir = REPO_ROOT / "validation" / "slice-specs"
    candidates = [
        spec_dir / f"{target_id}-{slice_id}.json",
        spec_dir / f"{target_id.split('-')[0]}-{slice_id}.json",
    ]
    candidates.extend(spec_dir.glob(f"*-{slice_id}.json"))
    candidates.extend(spec_dir.glob(f"*{slice_id}*.json"))
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise SystemExit(
        f"no slice spec found for target_id={target_id!r}, slice_id={slice_id!r}; pass --slice-spec explicitly"
    )


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())

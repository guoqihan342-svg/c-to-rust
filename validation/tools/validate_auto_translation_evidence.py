#!/usr/bin/env python3
"""Validate bounded auto-translation evidence against committed schemas."""

from __future__ import annotations

import argparse
import hashlib
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
    parser.add_argument(
        "--require-semantic-pass",
        action="store_true",
        help="Require accepted C oracle/Rust replay/diff/negative/unsafe/final verification evidence, not just schema validity.",
    )
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

    semantic = (
        validate_semantic_pass(evidence_dir, prefix, slice_spec)
        if args.require_semantic_pass
        else {"semantic_pass": False, "status": "not_required"}
    )

    print(
        json.dumps(
            {
                "status": "passed",
                "schema_status": "passed",
                "semantic_pass": bool(semantic.get("semantic_pass")),
                "semantic": semantic,
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


def validate_semantic_pass(evidence_dir: Path, prefix: str, slice_spec_path: Path) -> dict[str, Any]:
    slice_spec = load_json(slice_spec_path)
    manifest_path = evidence_dir / f"{prefix}-evidence-manifest.json"
    manifest = load_json(manifest_path)
    if manifest.get("status") != "passed":
        raise SystemExit(f"semantic pass requires manifest.status=passed: {manifest_path}")

    evidence = manifest.get("evidence", {})
    reports = {
        "c_oracle": load_ref(evidence, "c_oracle"),
        "rust_report": load_ref(evidence, "rust_report"),
        "schema_diff": load_ref(evidence, "schema_diff"),
        "negative_diff": load_ref(evidence, "negative_diff"),
        "unsafe_scan": load_ref(evidence, "unsafe_scan"),
        "unsafe_ledger": load_ref(evidence, "unsafe_ledger"),
        "final_verification": load_ref(evidence, "final_verification"),
        "version_or_config_binding": load_ref(evidence, "version_or_config_binding"),
    }

    require_status(reports["c_oracle"], "c_oracle", {"C_ORACLE_GENERATED", "passed"})
    if reports["c_oracle"].get("toolchain_status") != "C_ORACLE_GENERATED":
        raise SystemExit("semantic pass requires c_oracle.toolchain_status=C_ORACLE_GENERATED")
    require_status(reports["rust_report"], "rust_report", {"passed"})
    require_status(reports["schema_diff"], "schema_diff", {"passed"})
    if reports["schema_diff"].get("first_mismatch") is not None:
        raise SystemExit("semantic pass requires schema_diff.first_mismatch=null")
    if not mutation_detected(reports["negative_diff"]):
        raise SystemExit("semantic pass requires negative_diff mutation_detected/detected=true")
    require_status(reports["unsafe_scan"], "unsafe_scan", {"passed"})
    require_status(reports["unsafe_ledger"], "unsafe_ledger", {"passed"})
    require_status(reports["final_verification"], "final_verification", {"passed"})
    if not reports["final_verification"].get("semantic_pass"):
        raise SystemExit("semantic pass requires final_verification.semantic_pass=true")
    require_status(reports["version_or_config_binding"], "version_or_config_binding", {"recorded", "passed"})

    expected_commit = source_commit(slice_spec)
    for label, report in reports.items():
        report_commit = report.get("source_commit")
        if report_commit and report_commit != expected_commit:
            raise SystemExit(f"semantic pass source_commit mismatch in {label}: {report_commit} != {expected_commit}")

    fixture = reports["final_verification"].get("fixture", {})
    fixture_path = fixture.get("path") or fixture_path_from_spec(slice_spec)
    fixture_file = REPO_ROOT / fixture_path
    if fixture_file.exists() and fixture.get("sha256"):
        actual = sha256(fixture_file)
        if fixture["sha256"] != actual:
            raise SystemExit(f"semantic pass fixture sha256 mismatch: {fixture['sha256']} != {actual}")

    return {
        "status": "passed",
        "semantic_pass": True,
        "manifest": rel(manifest_path),
        "source_commit": expected_commit,
        "fixture_path": fixture_path,
        "fixture_sha256": fixture.get("sha256"),
        "checked": sorted(reports),
    }


def load_ref(evidence: dict[str, Any], key: str) -> dict[str, Any]:
    ref = evidence.get(key, {})
    path = ref.get("path")
    if not path:
        raise SystemExit(f"semantic pass requires manifest evidence.{key}.path")
    resolved = REPO_ROOT / path
    if not resolved.exists():
        raise SystemExit(f"semantic pass requires existing evidence.{key}: {resolved}")
    return load_json(resolved)


def require_status(report: dict[str, Any], label: str, allowed: set[str]) -> None:
    status = str(report.get("status", ""))
    if status not in allowed:
        raise SystemExit(f"semantic pass requires {label}.status in {sorted(allowed)}, got {status!r}")


def mutation_detected(report: dict[str, Any]) -> bool:
    return bool(report.get("mutation_detected") or report.get("detected"))


def source_commit(slice_spec: dict[str, Any]) -> str:
    return slice_spec.get("source_commit") or slice_spec.get("source", {}).get("source_commit") or "UNKNOWN0"


def fixture_path_from_spec(slice_spec: dict[str, Any]) -> str:
    fixture = slice_spec.get("fixture_contract", {})
    return fixture.get("path") or fixture.get("input") or "unknown-fixture"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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

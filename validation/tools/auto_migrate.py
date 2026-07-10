#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path as _C2RPartPath

_C2R_PARTS_DIR = _C2RPartPath(__file__).with_name("_auto_migrate_parts")
for _C2R_PART_NAME in (
    "part_00.py",
    "part_01.py",
    "part_02.py",
    "part_03.py",
    "part_04.py",
    "part_05.py",
    "part_06.py",
    "part_07.py",
):
    _C2R_PART_PATH = _C2R_PARTS_DIR / _C2R_PART_NAME
    exec(
        compile(
            _C2R_PART_PATH.read_text(encoding="utf-8"),
            str(_C2R_PART_PATH),
            "exec",
        ),
        globals(),
    )
for _C2R_PART_TEMP_NAME in (
    "_C2RPartPath",
    "_C2R_PARTS_DIR",
    "_C2R_PART_NAME",
    "_C2R_PART_PATH",
):
    globals().pop(_C2R_PART_TEMP_NAME, None)
del _C2R_PART_TEMP_NAME


def c2rust_crc32_safety_candidate_from_manifest(
    baseline_manifest: dict[str, Any],
    *,
    manifest_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    from validation.tools.flashdb_l3_self_healing import (
        extract_c2rust_function_baseline,
        transform_c2rust_crc32_baseline,
    )

    manifest_path = manifest_path.resolve()
    repo_root = repo_root.resolve()
    try:
        manifest_relative_path = manifest_path.relative_to(repo_root).as_posix()
    except ValueError as exc:
        raise ValueError("C2Rust baseline manifest path escapes repository root") from exc
    if not manifest_path.is_file():
        raise ValueError("C2Rust baseline manifest does not exist")
    if baseline_manifest.get("target_id") != "flashdb" or baseline_manifest.get("slice_id") != "real-fdb-calc-crc32":
        raise ValueError("C2Rust safety candidate requires the real-fdb-calc-crc32 manifest")
    if baseline_manifest.get("status") != "generated":
        raise ValueError("C2Rust safety candidate requires a generated baseline manifest")
    if baseline_manifest.get("correctness_role") != "candidate_context_only":
        raise ValueError("C2Rust baseline correctness role drifted")
    output = baseline_manifest.get("output")
    if not isinstance(output, dict) or output.get("status") != "generated":
        raise ValueError("C2Rust baseline output is not generated")
    output_path_value = output.get("path")
    expected_sha256 = output.get("sha256")
    if not isinstance(output_path_value, str) or not output_path_value:
        raise ValueError("C2Rust baseline output path is missing")
    if not isinstance(expected_sha256, str) or len(expected_sha256) != 64:
        raise ValueError("C2Rust baseline output sha256 is missing")
    output_path = Path(output_path_value)
    if output_path.is_absolute():
        raise ValueError("C2Rust baseline output path must be repository-relative")
    output_path = (repo_root / output_path).resolve()
    try:
        output_path.relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError("C2Rust baseline output path escapes repository root") from exc
    actual_sha256 = sha256(output_path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"C2Rust baseline output sha256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )
    if read_json(manifest_path) != baseline_manifest:
        raise ValueError("C2Rust baseline manifest payload does not match the bound file")

    extraction = extract_c2rust_function_baseline(
        output_path,
        function_name="fdb_calc_crc32",
        readonly_static="crc32_table",
        repo_root=repo_root,
    )
    transformed = transform_c2rust_crc32_baseline(extraction)
    baseline_unsafe = extraction["unsafe_scan"]["first_party_non_test_unsafe_count"]
    current_unsafe = transformed["unsafe_scan"]["first_party_non_test_unsafe_count"]
    return {
        "schema_version": 1,
        "candidate_source": "c2rust-function-level-baseline",
        "semantic_pass": False,
        "baseline_manifest": {
            "path": manifest_relative_path,
            "sha256": sha256(manifest_path),
            "status": baseline_manifest.get("status"),
        },
        "baseline_output": {**output, "verified_sha256": True},
        "extraction": extraction,
        "transformed": transformed,
        "repair_round": dict(transformed["repair_round"]),
        "unsafe_reduction": {
            "status": "function_level_scan_only",
            "baseline_total_unsafe": baseline_unsafe,
            "current_total_unsafe": current_unsafe,
            "reduced_by": baseline_unsafe - current_unsafe,
        },
        "claim_boundary": {
            "compile_verified": False,
            "fixture_replay_verified": False,
            "schema_diff_verified": False,
            "semantic_pass": False,
            "translation_coverage_numerator": 0,
        },
    }

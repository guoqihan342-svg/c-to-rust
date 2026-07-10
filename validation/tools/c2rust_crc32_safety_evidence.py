#!/usr/bin/env python3
from __future__ import annotations

import argparse
import difflib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from validation.tools import validate_judge_entrypoints as judge_validator
from validation.tools.c2rust_crc32_c_oracle import execute_verified_c_oracle


PREFIX = "l3-real-fdb-calc-crc32-c2rust-safety"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify the bounded C2Rust CRC32 safety transform")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(
            "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/"
            "l3-real-fdb-calc-crc32-c2rust-baseline-manifest.json"
        ),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32"),
    )
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    manifest_path = args.manifest if args.manifest.is_absolute() else repo_root / args.manifest
    out_dir = args.out_dir if args.out_dir.is_absolute() else repo_root / args.out_dir

    from validation.tools import auto_migrate

    report = auto_migrate.emit_c2rust_crc32_safety_evidence(
        _read_json(manifest_path),
        manifest_path=manifest_path,
        repo_root=repo_root,
        out_dir=out_dir,
    )
    print(
        json.dumps(
            {
                "status": report["status"],
                "semantic_pass": report["semantic_pass"],
                "verification": report["verification"],
            },
            sort_keys=True,
        )
    )
    return 0


def emit_evidence(
    candidate: dict[str, Any],
    *,
    repo_root: Path,
    out_dir: Path,
    c_oracle_path: Path | None = None,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    out_dir = out_dir.resolve()
    _require_inside_repo(out_dir, repo_root, "evidence output directory")
    c_oracle_path = (
        c_oracle_path.resolve()
        if c_oracle_path is not None
        else repo_root / "validation/evidence/flashdb/l3-real-fdb-calc-crc32-c-oracle.json"
    )
    _require_inside_repo(c_oracle_path, repo_root, "C oracle")

    extraction = _required_dict(candidate, "extraction")
    transformed = _required_dict(candidate, "transformed")
    baseline_rust = _required_string(extraction, "rust")
    candidate_rust = _required_string(transformed, "rust")
    if candidate.get("semantic_pass") is not False:
        raise ValueError("unverified C2Rust safety candidate must enter evidence emission as semantic_pass=false")

    c_oracle = _read_json(c_oracle_path)
    _validate_c_oracle(c_oracle)
    fixture_path = (repo_root / _required_string(c_oracle, "fixture")).resolve()
    _require_inside_repo(fixture_path, repo_root, "CRC32 fixture")
    fixture = _read_json(fixture_path)
    expected_cases = _validated_cases(fixture, c_oracle)

    out_dir.mkdir(parents=True, exist_ok=True)
    baseline_path = out_dir / f"{PREFIX}-baseline.rs"
    candidate_path = out_dir / f"{PREFIX}-candidate.rs"
    replay_path = out_dir / f"{PREFIX}-replay.rs"
    patch_path = out_dir / f"{PREFIX}-accepted.patch"
    stdout_path = out_dir / f"{PREFIX}-replay.stdout.log"
    stderr_path = out_dir / f"{PREFIX}-replay.stderr.log"
    repair_history_path = out_dir / f"{PREFIX}-repair-history.jsonl"
    verification_path = out_dir / f"{PREFIX}-verification.json"

    c_oracle_execution = execute_verified_c_oracle(
        repo_root=repo_root,
        out_dir=out_dir,
        c_oracle=c_oracle,
    )

    _write_text(baseline_path, baseline_rust)
    _write_text(candidate_path, candidate_rust)
    replay_rust = _render_replay(candidate_rust, expected_cases)
    _write_text(replay_path, replay_rust)
    patch_text = "".join(
        difflib.unified_diff(
            baseline_rust.splitlines(keepends=True),
            candidate_rust.splitlines(keepends=True),
            fromfile=_repo_relative(baseline_path, repo_root),
            tofile=_repo_relative(candidate_path, repo_root),
            n=0,
        )
    )
    if not patch_text:
        raise ValueError("C2Rust safety transform produced an empty patch")
    _write_text(patch_path, patch_text)

    rustc = shutil.which("rustc")
    if rustc is None:
        raise ValueError("rustc is required to verify the C2Rust safety candidate")
    version = subprocess.run([rustc, "--version"], text=True, capture_output=True, timeout=30)
    if version.returncode != 0:
        raise ValueError("rustc --version failed for the C2Rust safety candidate")

    with tempfile.TemporaryDirectory(prefix="c2rust-crc32-safety-") as tmp:
        tmp_dir = Path(tmp)
        baseline_compile = _compile_rust(
            rustc,
            baseline_path,
            tmp_dir / "baseline.rlib",
            crate_type="lib",
        )
        candidate_compile = _compile_rust(
            rustc,
            candidate_path,
            tmp_dir / "candidate.rlib",
            crate_type="lib",
        )
        replay_compile = _compile_rust(
            rustc,
            replay_path,
            tmp_dir / ("replay.exe" if shutil.which("rustc.exe") else "replay"),
            crate_type="bin",
        )
        if baseline_compile["returncode"] != 0:
            raise ValueError(f"C2Rust function baseline failed rustc: {baseline_compile['stderr']}")
        if candidate_compile["returncode"] != 0:
            raise ValueError(f"C2Rust safety candidate failed rustc: {candidate_compile['stderr']}")
        if replay_compile["returncode"] != 0:
            raise ValueError(f"C2Rust safety replay failed rustc: {replay_compile['stderr']}")
        replay_binary = Path(replay_compile["output_path"])
        replay_run = subprocess.run(
            [str(replay_binary)],
            text=True,
            capture_output=True,
            timeout=120,
        )

    _write_text(stdout_path, replay_run.stdout)
    _write_text(stderr_path, replay_run.stderr)
    if replay_run.returncode != 0:
        raise ValueError(f"C2Rust safety replay execution failed: {replay_run.stderr}")
    observed_cases = _parse_replay(replay_run.stdout, expected_cases)
    diff = _compare_cases(expected_cases, observed_cases)
    if diff["status"] != "passed":
        raise ValueError(f"C2Rust safety replay disagrees with accepted C oracle: {diff['first_mismatch']}")
    negative_diff = _negative_diff(expected_cases, observed_cases)
    if not negative_diff["mutation_detected"]:
        raise ValueError("C2Rust safety negative diff did not detect the injected mutation")

    unsafe_reduction = _required_dict(candidate, "unsafe_reduction")
    if unsafe_reduction != {
        "status": "function_level_scan_only",
        "baseline_total_unsafe": 2,
        "current_total_unsafe": 0,
        "reduced_by": 2,
    }:
        raise ValueError("C2Rust safety candidate unsafe reduction contract drifted")
    accepted_unsafe_reduction = dict(unsafe_reduction)
    accepted_unsafe_reduction["status"] = "measured"
    accepted_unsafe_reduction["ratio"] = 0.0

    artifact_refs = {
        "baseline": _ref(baseline_path, repo_root, "compiled"),
        "candidate": _ref(candidate_path, repo_root, "passed"),
        "accepted_patch": _ref(patch_path, repo_root, "verified"),
        "replay_source": _ref(replay_path, repo_root, "compiled"),
        "replay_stdout": _ref(stdout_path, repo_root, "passed"),
        "replay_stderr": _ref(stderr_path, repo_root, "captured"),
        "c_oracle": _ref(c_oracle_path, repo_root, "passed"),
        "fixture": _ref(fixture_path, repo_root, "bound"),
    }
    artifact_refs.update(c_oracle_execution["artifacts"])
    repair_row = {
        "schema_version": 1,
        "round": 1,
        "status": "verified",
        "candidate_source": "c2rust-function-level-safety-transform",
        "baseline": artifact_refs["baseline"],
        "final": artifact_refs["candidate"],
        "accepted_patch": artifact_refs["accepted_patch"],
        "oracle_evidence": artifact_refs["c_oracle"],
        "unsafe_reduction": accepted_unsafe_reduction,
        "verified_gates": [
            "baseline_rustc",
            "candidate_rustc",
            "accepted_c_oracle_bound",
            "candidate_replay",
            "schema_diff",
            "negative_diff",
            "unsafe_reduction",
        ],
        "semantic_pass": True,
        "generated_draft_semantic_pass": False,
    }
    _write_text(repair_history_path, json.dumps(repair_row, sort_keys=True) + "\n")
    artifact_refs["repair_history"] = _ref(repair_history_path, repo_root, "verified")

    report = {
        "schema_version": 1,
        "report_kind": "c2rust-crc32-safety-verification",
        "target_id": "flashdb",
        "slice_id": "real-fdb-calc-crc32",
        "function": "fdb_calc_crc32",
        "status": "passed",
        "semantic_pass": True,
        "semantic_claim_source": "c2rust_safety_transform_replay_with_accepted_c_oracle",
        "candidate_source": "c2rust-function-level-safety-transform",
        "baseline_manifest": candidate["baseline_manifest"],
        "baseline_output": candidate["baseline_output"],
        "c_oracle_execution": c_oracle_execution,
        "artifacts": artifact_refs,
        "rustc": {
            "version": version.stdout.strip(),
            "baseline_compile": _compile_report(baseline_compile),
            "candidate_compile": _compile_report(candidate_compile),
            "replay_compile": _compile_report(replay_compile),
        },
        "replay": {
            "status": "passed",
            "returncode": replay_run.returncode,
            "case_count": len(observed_cases),
            "cases": observed_cases,
        },
        "schema_diff": diff,
        "negative_diff": negative_diff,
        "unsafe_reduction": accepted_unsafe_reduction,
        "repair_round": transformed["repair_round"],
        "claim_boundary": {
            "scope": "function_level_c2rust_plus_repair_candidate",
            "generated_draft_semantic_pass": False,
            "translation_coverage_numerator": 0,
            "whole_project_migration": False,
            "must_not_claim": [
                "translator-generated semantic pass",
                "whole-project FlashDB migration",
                "general C2Rust safety transform coverage",
            ],
        },
    }
    _write_json(verification_path, report)
    return report | {"verification": _ref(verification_path, repo_root, "passed")}


def _compile_rust(
    rustc: str,
    source_path: Path,
    output_path: Path,
    *,
    crate_type: str,
) -> dict[str, Any]:
    result = subprocess.run(
        [
            rustc,
            "--edition=2021",
            f"--crate-type={crate_type}",
            "--crate-name=c2rust_crc32_safety",
            "-Awarnings",
            str(source_path),
            "-o",
            str(output_path),
        ],
        text=True,
        capture_output=True,
        timeout=120,
    )
    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "output_path": str(output_path),
        "crate_type": crate_type,
    }


def _compile_report(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "passed" if result["returncode"] == 0 else "failed",
        "returncode": result["returncode"],
        "crate_type": result["crate_type"],
        "stdout_sha256": _sha256_text(result["stdout"]),
        "stderr_sha256": _sha256_text(result["stderr"]),
    }


def _render_replay(candidate_rust: str, cases: list[dict[str, Any]]) -> str:
    lines = [candidate_rust.rstrip(), "", "fn main() {"]
    for index, case in enumerate(cases):
        case_id = json.dumps(case["id"])
        buf = ", ".join(str(value) for value in case["buf"])
        lines.append(
            f"    let result_{index} = fdb_calc_crc32({case['crc']}u32, &[{buf}]);"
        )
        lines.append(f'    println!("{{}}\\t{{}}", {case_id}, result_{index});')
    lines.extend(["}", ""])
    return "\n".join(lines)


def _parse_replay(stdout: str, expected_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    expected_ids = {case["id"] for case in expected_cases}
    observed: list[dict[str, Any]] = []
    for line in stdout.splitlines():
        parts = line.split("\t")
        if len(parts) != 2 or parts[0] not in expected_ids:
            raise ValueError(f"unexpected C2Rust safety replay output: {line!r}")
        try:
            return_code = int(parts[1])
        except ValueError as exc:
            raise ValueError(f"invalid C2Rust safety replay return code: {line!r}") from exc
        observed.append({"id": parts[0], "return_code": return_code, "status": "passed"})
    if len(observed) != len(expected_cases) or len({case["id"] for case in observed}) != len(observed):
        raise ValueError("C2Rust safety replay case count or identity drifted")
    return observed


def _validated_cases(fixture: dict[str, Any], c_oracle: dict[str, Any]) -> list[dict[str, Any]]:
    fixture_cases = fixture.get("cases")
    oracle_cases = c_oracle.get("cases")
    if not isinstance(fixture_cases, list) or not isinstance(oracle_cases, list):
        raise ValueError("CRC32 fixture and C oracle cases are required")
    oracle_by_id = {case.get("id"): case for case in oracle_cases if isinstance(case, dict)}
    result: list[dict[str, Any]] = []
    for case in fixture_cases:
        if not isinstance(case, dict):
            raise ValueError("CRC32 fixture case must be an object")
        case_id = case.get("id")
        buf = case.get("buf")
        crc = case.get("crc")
        expected = case.get("return_code")
        oracle_case = oracle_by_id.get(case_id)
        if (
            not isinstance(case_id, str)
            or not case_id
            or "\t" in case_id
            or "\n" in case_id
            or not isinstance(buf, list)
            or not all(isinstance(value, int) and 0 <= value <= 255 for value in buf)
            or not isinstance(crc, int)
            or not isinstance(expected, int)
            or not isinstance(oracle_case, dict)
            or oracle_case.get("return_code") != expected
        ):
            raise ValueError(f"CRC32 fixture/C oracle case drifted: {case_id!r}")
        result.append({"id": case_id, "buf": buf, "crc": crc, "return_code": expected})
    if len(result) != c_oracle.get("case_count") or len(result) != fixture.get("case_count"):
        raise ValueError("CRC32 fixture/C oracle case count drifted")
    return result


def _compare_cases(expected: list[dict[str, Any]], observed: list[dict[str, Any]]) -> dict[str, Any]:
    observed_by_id = {case["id"]: case for case in observed}
    first_mismatch: dict[str, Any] | None = None
    for case in expected:
        actual = observed_by_id.get(case["id"], {}).get("return_code")
        if actual != case["return_code"]:
            first_mismatch = {
                "id": case["id"],
                "field": "return_code",
                "expected": case["return_code"],
                "actual": actual,
            }
            break
    return {
        "status": "passed" if first_mismatch is None else "failed",
        "case_count": len(expected),
        "compared_fields": ["return_code"],
        "first_mismatch": first_mismatch,
    }


def _negative_diff(expected: list[dict[str, Any]], observed: list[dict[str, Any]]) -> dict[str, Any]:
    mutated = [dict(case) for case in observed]
    mutated[0]["return_code"] ^= 1
    diff = _compare_cases(expected, mutated)
    return {
        "status": "expected_failed" if diff["status"] == "failed" else "failed",
        "expected_failure": True,
        "mutation": "xor_first_return_code_with_1",
        "mutation_detected": diff["status"] == "failed",
        "first_mismatch": diff["first_mismatch"],
    }


def _validate_c_oracle(c_oracle: dict[str, Any]) -> None:
    if (
        c_oracle.get("target_id") != "flashdb"
        or c_oracle.get("slice_id") != "real-fdb-calc-crc32"
        or c_oracle.get("status") != "passed"
        or c_oracle.get("semantic_pass") is not True
        or c_oracle.get("toolchain_status") != "C_ORACLE_GENERATED"
    ):
        raise ValueError("accepted real-fdb-calc-crc32 C oracle contract is not passed")


def _required_dict(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"required object is missing: {key}")
    return value


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"required string is missing: {key}")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON artifact must be an object: {path}")
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def _sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _ref(path: Path, repo_root: Path, status: str) -> dict[str, Any]:
    return {
        "path": _repo_relative(path, repo_root),
        "sha256": judge_validator.sha256_file(path),
        "status": status,
    }


def _repo_relative(path: Path, repo_root: Path) -> str:
    _require_inside_repo(path, repo_root, "artifact")
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _require_inside_repo(path: Path, repo_root: Path, label: str) -> None:
    try:
        path.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"{label} escapes repository root: {path}") from exc


if __name__ == "__main__":
    raise SystemExit(main())

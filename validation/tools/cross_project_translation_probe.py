"""Run a small, deterministic route-stability probe against c2r-translator."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURES = REPO_ROOT / "validation" / "fixtures" / "cross_project_translation_probe" / "cases.json"
MAX_CASES = 20
CASE_ID = re.compile(r"^[a-z][a-z0-9-]*$")
REQUIRED_CASE_FIELDS = {
    "id",
    "project",
    "syntax_family",
    "naming_variant",
    "function_name",
    "c_source",
    "clang_ast_fixture",
    "expected_classification",
}
Runner = Callable[[Sequence[str], Path], subprocess.CompletedProcess[str]]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_cases(path: Path, repo_root: Path = REPO_ROOT) -> tuple[dict[str, Any], list[dict[str, str]]]:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1:
        raise ValueError("fixture catalog schema_version must be 1")
    source_file = catalog.get("source_file")
    cases = catalog.get("cases")
    if not isinstance(source_file, str) or not source_file:
        raise ValueError("fixture catalog requires source_file")
    if not isinstance(cases, list) or not 1 <= len(cases) <= MAX_CASES:
        raise ValueError(f"fixture catalog must contain 1 to {MAX_CASES} cases")
    source_path = Path(source_file)
    if source_path.is_absolute() or ".." in source_path.parts or not (repo_root / source_path).is_file():
        raise ValueError(f"fixture source file does not exist: {source_file}")

    seen_ids: set[str] = set()
    normalized_cases: list[dict[str, str]] = []
    for case in cases:
        if not isinstance(case, dict) or REQUIRED_CASE_FIELDS - case.keys():
            raise ValueError("each fixture case must define all required fields")
        if not all(isinstance(case[field], str) and case[field] for field in REQUIRED_CASE_FIELDS):
            raise ValueError("fixture case fields must be non-empty strings")
        case_id = case["id"]
        if not CASE_ID.fullmatch(case_id) or case_id in seen_ids:
            raise ValueError(f"fixture case id must be unique and URL-safe: {case_id}")
        if case["expected_classification"] not in {"success", "refusal"}:
            raise ValueError("expected_classification must be success or refusal")
        ast_fixture = Path(case["clang_ast_fixture"])
        if ast_fixture.is_absolute() or ".." in ast_fixture.parts or not (repo_root / ast_fixture).is_file():
            raise ValueError(f"clang AST fixture does not exist: {case['clang_ast_fixture']}")
        seen_ids.add(case_id)
        normalized_cases.append({field: case[field] for field in REQUIRED_CASE_FIELDS})
    return catalog, normalized_cases


def build_slice_spec(case: dict[str, str], source_file: str, source_hash: str) -> dict[str, Any]:
    return {
        "target_id": f"probe-{case['project']}",
        "slice_id": case["id"],
        "source_commit": "cross-project-translation-probe-v1",
        "function_name": case["function_name"],
        "c_source": case["c_source"],
        "fixture_hash": f"{case['id']}-fixture",
        "source_root": ".",
        "source_file": source_file,
        "source_file_hashes": {source_file: source_hash},
        "c_boundary": {},
        "build_profile": {
            "compiler_command_source": "fixture-replay",
            "include_paths": [],
            "defines": [],
            "clang_available": True,
            "clang_ast_fixture": case["clang_ast_fixture"],
            "target": {
                "triple_or_abi": "x86_64-unknown-linux-gnu",
                "int_width": 32,
                "long_width": 64,
                "pointer_width": 64,
            },
        },
    }


def default_runner(argv: Sequence[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, cwd=cwd, text=True, capture_output=True, check=False)


def translator_argv(repo_root: Path, spec_path: Path, case_dir: Path) -> list[str]:
    return [
        "cargo",
        "run",
        "--quiet",
        "--manifest-path",
        str(repo_root / "crates" / "c2r-translator" / "Cargo.toml"),
        "--features",
        "clang-lowering-report",
        "--bin",
        "c2r_translate",
        "--",
        "--slice-spec",
        str(spec_path),
        "--out-dir",
        str(case_dir),
    ]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def portable_path(path: Path, repo_root: Path) -> str:
    try:
        return path.relative_to(repo_root).as_posix()
    except ValueError:
        return path.as_posix()


def refusal_codes(route: Any, blocked_repairs: dict[str, Any]) -> list[str]:
    codes: list[str] = []
    if isinstance(route, dict):
        for reason in route.get("reasons", []):
            if isinstance(reason, dict) and isinstance(reason.get("code"), str):
                codes.append(reason["code"])
    for blocked in blocked_repairs.get("blocked", []):
        if isinstance(blocked, dict) and isinstance(blocked.get("kind"), str):
            codes.append(blocked["kind"])
    return list(dict.fromkeys(codes))


def classify_case(
    case: dict[str, str], case_dir: Path, completed: subprocess.CompletedProcess[str], repo_root: Path
) -> dict[str, Any]:
    base = {
        "id": case["id"],
        "project": case["project"],
        "syntax_family": case["syntax_family"],
        "naming_variant": case["naming_variant"],
        "expected_classification": case["expected_classification"],
        "route": None,
        "success": False,
        "refusal": None,
        "process_returncode": completed.returncode,
    }
    if completed.returncode != 0:
        base.update(
            {
                "classification": "execution_failure",
                "refusal": {"codes": ["translator_process_failed"]},
                "matches_expected": False,
                "stderr": completed.stderr.strip(),
            }
        )
        return base

    prefix = f"l3-{case['id']}"
    plan = load_json(case_dir / f"{prefix}-auto-translation-plan.json")
    lowering = load_json(case_dir / f"{prefix}-clang-lowering-report.json")
    blocked_repairs = load_json(case_dir / f"{prefix}-blocked-repairs.json")
    candidate = lowering.get("typed_ir_candidate", {})
    if not isinstance(candidate, dict):
        candidate = {}
    route = candidate.get("candidate_route")
    route_id = route.get("route_id") if isinstance(route, dict) else None
    generated = (
        plan.get("status") == "generated"
        and candidate.get("rust_draft_generated") is True
        and isinstance(route_id, str)
        and bool(route_id)
    )
    classification = "success" if generated else "refusal"
    base.update(
        {
            "classification": classification,
            "route": route_id,
            "success": generated,
            "refusal": None if generated else {"codes": refusal_codes(route, blocked_repairs)},
            "matches_expected": classification == case["expected_classification"],
            "artifacts": {
                "translation_plan": portable_path(
                    case_dir / f"{prefix}-auto-translation-plan.json", repo_root
                ),
                "clang_lowering_report": portable_path(
                    case_dir / f"{prefix}-clang-lowering-report.json", repo_root
                ),
            },
        }
    )
    return base


def prepare_case_dir(output_root: Path, case_id: str) -> Path:
    output_root = output_root.resolve()
    case_dir = (output_root / case_id).resolve()
    if output_root not in case_dir.parents:
        raise ValueError("case output must remain under out_dir")
    if case_dir.exists():
        shutil.rmtree(case_dir)
    case_dir.mkdir(parents=True)
    return case_dir


def run_probe(
    repo_root: Path,
    fixtures_path: Path,
    output_root: Path,
    runner: Runner = default_runner,
) -> dict[str, Any]:
    catalog, cases = load_cases(fixtures_path, repo_root)
    source_file = catalog["source_file"]
    source_hash = sha256_file(repo_root / source_file)
    output_root.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for case in cases:
        case_dir = prepare_case_dir(output_root, case["id"])
        spec_path = case_dir / "slice-spec.json"
        spec_path.write_text(
            json.dumps(build_slice_spec(case, source_file, source_hash), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        completed = runner(translator_argv(repo_root, spec_path, case_dir), repo_root)
        results.append(classify_case(case, case_dir, completed, repo_root))

    outcome_counts = {
        name: sum(result["classification"] == name for result in results)
        for name in ("success", "refusal", "execution_failure")
    }
    mismatches = [result["id"] for result in results if not result["matches_expected"]]
    return {
        "schema_version": 1,
        "status": "passed" if not mismatches else "failed",
        "claim_boundary": {
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
            "note": "This probe records candidate route stability only; it does not establish semantic equivalence.",
        },
        "fixture_catalog": portable_path(fixtures_path, repo_root),
        "case_count": len(results),
        "outcome_counts": outcome_counts,
        "mismatches": mismatches,
        "cases": results,
    }


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=REPO_ROOT / "target" / "cross-project-translation-probe",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_probe(REPO_ROOT, args.fixtures.resolve(), args.out_dir.resolve())
    report_path = args.out_dir / "cross-project-translation-probe-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

from .artifacts import checked_relative_path, content_sha256, write_json_artifact
from .held_out_integrity import (
    IntegrityError,
    bound_file,
    compile_database,
    confined_path,
    file_sha256,
    repository_tree_sha256,
    source_shape,
)
from .held_out_ledger import HeldOutLedgerError, verify_completed_project
from .identity_guard import scan_identity_dispatch
MAX_CASES = 20
MIN_PROJECTS = 5
MIN_CONSTRUCT_FAMILIES = 12
MIN_HELD_OUT_PROJECTS = 2
ID_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,95}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40,64}$")
GENERIC_IDENTITIES = {"case", "held-out", "project", "repo", "repository", "source", "test"}
PlanRunner = Callable[[list[str]], dict[str, Any]]
HeldOutContractError = IntegrityError
def validate_manifest(
    manifest: Mapping[str, Any], *, manifest_dir: Path, harness_root: Path, mode: str,
) -> dict[str, Any]:
    _require(mode in {"offline-contract", "real-projects"}, "mode must be explicit")
    _require(manifest.get("schema_version") == 1, "schema_version must be 1")
    suite_id = _identifier(manifest.get("suite_id"), "suite_id")
    harness = harness_root.resolve(strict=True)
    entrypoint = bound_file(manifest.get("generic_plan_entrypoint"), harness, "generic_plan_entrypoint")
    cases = manifest.get("cases")
    _require(isinstance(cases, list), "cases must be a list")
    _require(MIN_PROJECTS <= len(cases) <= MAX_CASES, "cases must contain 5 to 20 projects")

    normalized: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    seen_project_ids: set[str] = set()
    seen_paths: set[Path] = set()
    seen_trees: dict[str, str] = {}
    source_shapes: list[tuple[str, set[str], str]] = []
    families: set[str] = set()
    identities: set[str] = set()
    held_out = 0
    for raw in cases:
        _require(isinstance(raw, Mapping), "each case must be an object")
        forbidden = {
            "plan_entrypoint", "adapter", "translator", "prompt", "dispatch",
            "translation_evidence",
        } & set(raw)
        _require(not forbidden, f"case-level identity dispatch fields are forbidden: {sorted(forbidden)}")
        case_id = _identifier(raw.get("case_id"), "case_id")
        project_id = _identifier(raw.get("project_id"), "project_id")
        _require(case_id not in seen_case_ids, "case ids must be unique")
        _require(project_id not in seen_project_ids, "project ids must be unique")
        seen_case_ids.add(case_id)
        seen_project_ids.add(project_id)
        participated = raw.get("participated_in_rule_development")
        _require(isinstance(participated, bool), "participated_in_rule_development must be boolean")
        held_out += int(not participated)
        declared = raw.get("construct_families")
        _require(isinstance(declared, list) and declared, "construct_families must be non-empty")
        case_families = {_identifier(item, "construct_family") for item in declared}
        _require(len(case_families) == len(declared), "construct_families must be unique per case")
        families.update(case_families)

        repository = raw.get("repository")
        _require(isinstance(repository, Mapping), "repository must be an object")
        repo = _resolve_path(repository.get("path"), manifest_dir, "repository.path")
        _require(repo.is_dir(), f"repository does not exist: {repo}")
        commit = repository.get("source_commit")
        _require(isinstance(commit, str) and COMMIT_RE.fullmatch(commit) is not None, "source_commit must be a full commit hash")
        tree_sha = repository_tree_sha256(repo)
        _match_sha(repository.get("tree_sha256"), tree_sha, "repository.tree_sha256")
        _require(repo not in seen_paths, "duplicate repository path")
        _require(tree_sha not in seen_trees, f"duplicate project content: {seen_trees.get(tree_sha, '')}")
        seen_paths.add(repo)
        seen_trees[tree_sha] = case_id

        compile_db, compile_sha, sources = compile_database(raw.get("compile_database"), repo)
        shape, shape_sha = source_shape(sources)
        for prior_id, prior_shape, prior_sha in source_shapes:
            _require(shape_sha != prior_sha, f"duplicate normalized project: {prior_id}/{case_id}")
            union = shape | prior_shape
            similarity = len(shape & prior_shape) / len(union) if union else 1.0
            _require(not (min(len(shape), len(prior_shape)) >= 12 and similarity >= 0.78),
                     f"near-duplicate projects: {prior_id}/{case_id}")
        source_shapes.append((case_id, shape, shape_sha))
        if mode == "real-projects":
            _require(_git_head(repo) == commit.lower(), f"source_commit mismatch: {case_id}")
        for identity in (project_id.casefold(), repo.name.casefold()):
            identities.add(identity)
            identities.update(re.findall(r"[a-z0-9]{4,}", identity))
        normalized.append({
            "case_id": case_id, "project_id": project_id, "repo": repo,
            "source_commit": commit.lower(), "tree_sha256": tree_sha,
            "compile_database": compile_db, "compile_database_sha256": compile_sha,
            "participated_in_rule_development": participated,
            "construct_families": sorted(case_families),
        })

    _require(len(families) >= MIN_CONSTRUCT_FAMILIES, "suite must cover at least 12 construct families")
    _require(held_out >= MIN_HELD_OUT_PROJECTS, "suite must include at least two true held-out projects")
    scan_ids = sorted(value for value in identities if len(value) >= 4 and value not in GENERIC_IDENTITIES)
    identity_scan = scan_identity_dispatch(_production_paths(entrypoint, harness), scan_ids)
    _require(identity_scan["status"] == "passed", "generic plan entrypoint contains identity dispatch")
    return {
        "schema_version": 1, "suite_id": suite_id, "mode": mode,
        "generic_plan_entrypoint": entrypoint, "cases": normalized,
        "project_count": len(normalized), "construct_families": sorted(families),
        "held_out_project_count": held_out, "identity_scan": identity_scan,
    }
def run_acceptance_suite(
    manifest: Mapping[str, Any], *, manifest_dir: Path, harness_root: Path,
    mode: str, out_root: str, plan_runner: PlanRunner | None = None,
) -> dict[str, Any]:
    harness = harness_root.resolve(strict=True)
    out_rel = checked_relative_path(out_root.rstrip("/"))
    out_path = PurePosixPath(out_rel)
    _require(
        len(out_path.parts) > 1 and out_path.parts[0] == "target",
        "out_root must stay under the harness target directory",
    )
    output = confined_path(
        harness, out_rel, "held-out output root", must_exist=False,
    )
    validated = validate_manifest(
        manifest, manifest_dir=manifest_dir,
        harness_root=harness, mode=mode,
    )
    runner = plan_runner or _subprocess_runner(validated["generic_plan_entrypoint"], harness)
    refs: list[dict[str, Any]] = []
    accepted = 0
    planned = 0
    for case in validated["cases"]:
        case_out = f"{out_rel}/plans/{validated['suite_id']}/{case['case_id']}"
        argv = [
            "plan", "--repo-root", str(case["repo"]), "--compile-database", str(case["compile_database"]),
            "--out-root", case_out, "--run-id", f"heldout-{case['case_id']}",
            "--source-commit", case["source_commit"],
        ]
        plan = runner(argv)
        plan_ok = plan.get("status") in {"planned", "ready", "ready_with_boundaries"}
        _require(isinstance(plan.get("plan_sha256"), str) and SHA_RE.fullmatch(plan["plan_sha256"]) is not None,
                 "plan_sha256 must be sha256")
        boundary = plan.get("claim_boundary", {})
        _require(boundary.get("semantic_gate") is False, "planning must not claim semantic success")
        _require(boundary.get("translation_coverage_numerator") == 0, "planning must not increase translation coverage")
        planned += int(plan_ok)
        translation = _translation_result(
            case, plan, harness, mode, case_out=case_out
        )
        accepted += int(translation["status"] == "accepted")
        evidence = {
            "schema_version": 1, "case_id": case["case_id"], "project_id": case["project_id"],
            "mode": mode, "input_binding": _json_case(case),
            "plan": {"status": plan.get("status"), "plan_sha256": plan.get("plan_sha256"),
                     "payload_sha256": content_sha256(plan)},
            "planning_status": "passed" if plan_ok else "failed", "translation": translation,
            "claim_boundary": {"semantic_gate": translation["status"] == "accepted",
                               "translation_coverage_numerator": translation.get("translation_coverage_numerator", 0)},
        }
        refs.append(write_json_artifact(output, f"evidence/sha256/{content_sha256(evidence)}.json", evidence))
    planning_failed = planned != len(refs)
    status = "failed" if planning_failed else "contract_passed"
    if mode == "real-projects":
        status = "acceptance_passed" if accepted == len(refs) else ("failed" if planning_failed else "incomplete")
    summary = {
        "schema_version": 1, "status": status, "suite_id": validated["suite_id"], "mode": mode,
        "project_count": validated["project_count"], "case_count": len(refs),
        "construct_family_count": len(validated["construct_families"]),
        "held_out_project_count": validated["held_out_project_count"],
        "planned_projects": planned, "accepted_projects": accepted,
        "case_evidence": refs,
        "claim_boundary": {"semantic_gate": status == "acceptance_passed",
                           "translation_coverage_numerator": accepted},
    }
    summary_ref = write_json_artifact(output, f"evidence/sha256/{content_sha256(summary)}.json", summary)
    return {**summary, "summary_evidence": summary_ref}
def _translation_result(
    case: Mapping[str, Any], plan: Mapping[str, Any], harness: Path,
    mode: str, *, case_out: str,
) -> dict[str, Any]:
    if mode != "real-projects":
        return {"status": "not_evaluated", "reason": "offline_contract_is_planning_only", "translation_coverage_numerator": 0}
    ledger = plan.get("ledger")
    ledger_path = ledger.get("path") if isinstance(ledger, Mapping) else None
    expected = f"{case_out}/state/project-migration.sqlite3"
    if ledger_path != expected:
        return _not_accepted("authoritative_ledger_binding_missing")
    try:
        path = confined_path(harness, expected, "project ledger", must_exist=True)
        result = verify_completed_project(
            ledger_path=path,
            harness_root=harness,
            run_id=f"heldout-{case['case_id']}",
            plan_sha256=str(plan.get("plan_sha256", "")),
            repo_root=case["repo"],
            source_commit=case["source_commit"],
            repository_tree_sha256_expected=case["tree_sha256"],
            compile_database=case["compile_database"],
            compile_database_sha256=case["compile_database_sha256"],
        )
    except (HeldOutLedgerError, IntegrityError, OSError, ValueError):
        return _not_accepted("authoritative_ledger_not_complete")
    return result


def _not_accepted(reason: str) -> dict[str, Any]:
    return {
        "status": "not_accepted", "reason": reason,
        "translation_coverage_numerator": 0, "semantic_gate": False,
    }


def _resolve_path(value: Any, base: Path, label: str) -> Path:
    _require(isinstance(value, str) and value, f"{label} must be explicit")
    path = Path(value)
    return (path if path.is_absolute() else base / path).resolve(strict=True)


def _identifier(value: Any, label: str) -> str:
    _require(isinstance(value, str) and ID_RE.fullmatch(value) is not None, f"{label} must be portable lowercase")
    return value


def _match_sha(actual: Any, expected: str, label: str) -> None:
    _require(isinstance(actual, str) and SHA_RE.fullmatch(actual) is not None, f"{label} must be sha256")
    _require(actual == expected, f"{label} mismatch")


def _production_paths(entrypoint: Path, harness: Path) -> list[Path]:
    package = entrypoint.parent / "_project_migration_harness"
    paths = [entrypoint, *(package.rglob("*.py") if package.is_dir() else [])]
    agent = harness / ".opencode" / "agents" / "c2rust-candidate.md"
    if agent.is_file():
        paths.append(agent)
    return paths


def _git_head(repo: Path) -> str:
    result = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10)
    _require(result.returncode == 0, f"real project is not a readable git checkout: {repo}")
    return result.stdout.strip().lower()


def _subprocess_runner(entrypoint: Path, harness: Path) -> PlanRunner:
    def run(argv: list[str]) -> dict[str, Any]:
        env = {**os.environ, "PYTHONPATH": f"{harness}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}
        result = subprocess.run([sys.executable, "-B", str(entrypoint), *argv], cwd=harness,
                                capture_output=True, text=True, timeout=300, env=env)
        _require(result.returncode in {0, 1}, f"generic plan entrypoint failed: {result.stderr.strip()}")
        payload = json.loads(result.stdout)
        _require(isinstance(payload, dict), "generic plan output must be an object")
        return payload
    return run


def _json_case(case: Mapping[str, Any]) -> dict[str, Any]:
    return {"repository_path": str(case["repo"]), "repository_tree_sha256": case["tree_sha256"],
            "source_commit": case["source_commit"], "compile_database_path": str(case["compile_database"]),
            "compile_database_sha256": case["compile_database_sha256"],
            "participated_in_rule_development": case["participated_in_rule_development"],
            "construct_families": case["construct_families"]}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise HeldOutContractError(message)


__all__ = ["HeldOutContractError", "file_sha256", "repository_tree_sha256", "run_acceptance_suite", "validate_manifest"]

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from .build_facts import json_sha256, resolve_repository_path
from .candidate_admission import apply_candidate_admission
from .closure_paths import (
    bind_repository_artifact,
    path_error_blocker,
    verify_repository_artifact,
)
from .link_closure import discover_link_closure
from .meson_introspection import verify_meson_introspection


MAX_GENERATED_INCLUDE_ROOTS = 256
MAX_COMPILE_OUTPUTS = 10_000


def materialize_build_ir_stage(
    repo_root: Path,
    output: Path,
    discovery: dict[str, Any],
    artifacts: dict[str, dict[str, Any]],
    profile: str = "development",
) -> dict[str, Any]:
    from .generated_closure_materialize import materialize_generated_build_ir_stage
    return materialize_generated_build_ir_stage(
        repo_root, output, discovery, artifacts, profile,
    )


def discover_generated_build_closure(
    repo_root: Path,
    compile_database_path: Path,
    generated_facts: dict[str, Any],
    translation_units: list[dict[str, Any]],
) -> dict[str, Any]:
    root = repo_root.resolve()
    blockers: list[dict[str, Any]] = [
        {"kind": reason}
        for reason in generated_facts.get("blockers", [])
        if isinstance(reason, str) and reason
    ]
    try:
        compile_database = bind_repository_artifact(
            root, compile_database_path, kind="file"
        )
    except (OSError, ValueError) as error:
        compile_database = None
        blockers.append(path_error_blocker(
            error, role="compile_database", path="<compile-database>"
        ))
    generated_roots = _generated_include_roots(
        root, compile_database_path, translation_units, blockers
    )
    compile_outputs = _compile_outputs(root, translation_units, blockers)
    link = discover_link_closure(root, compile_database_path, generated_facts)
    blockers.extend(link["blockers"])
    if link["status"] == "ready":
        linked_paths = {
            item["path"]
            for target in link["targets"]
            for item in target["inputs"]
        }
        for output in compile_outputs:
            if output["path"] not in linked_paths:
                blockers.append({
                    "kind": "compile_output_unlinked",
                    "path": output["path"],
                })
    blockers = _unique_blockers(blockers)
    return {
        "schema_version": 1,
        "status": "ready" if not blockers else "blocked",
        "compile_database": compile_database,
        "generated_stage_facts": generated_facts,
        "generated_include_roots": generated_roots,
        "compile_outputs": compile_outputs,
        "target_link_closure": link,
        "blockers": blockers,
        "claim_boundary": {
            "role": "generated_build_input_closure_only",
            "parameters_guessed": False,
            "commands_executed": False,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }


def verify_generated_build_closure(
    repo_root: str | Path, closure: dict[str, Any]
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    bindings: list[dict[str, Any]] = []
    blockers: list[dict[str, Any]] = []
    closure_status = closure.get("status")
    closure_blockers = closure.get("blockers")
    if (
        closure_status not in {"ready", "blocked"}
        or not isinstance(closure_blockers, list)
        or closure_status == "ready" and closure_blockers
        or closure_status == "blocked" and not closure_blockers
    ):
        blockers.append({"kind": "generated_closure_status_mismatch"})
    compile_database = closure.get("compile_database")
    if isinstance(compile_database, dict):
        bindings.append(compile_database)
    else:
        blockers.append({"kind": "compile_database_replay_binding_missing"})
    bindings.extend(_binding_list(closure.get("generated_include_roots")))
    bindings.extend(_binding_list(closure.get("compile_outputs")))
    generated = closure.get("generated_stage_facts")
    if isinstance(generated, dict):
        bindings.extend(_binding_list(generated.get("link_command_files")))
        bindings.extend(_binding_list(generated.get("metadata_files")))
        meson = generated.get("meson_introspection")
        if isinstance(meson, dict):
            bindings.extend(_binding_list(meson.get("snapshot_files")))
            bindings.extend(_binding_list(meson.get("referenced_artifacts")))
            database_path = compile_database.get("path") if isinstance(
                compile_database, dict
            ) else None
            if isinstance(database_path, str):
                blockers.extend(verify_meson_introspection(
                    root, root / Path(*PurePosixPath(database_path).parts), meson
                ))
    else:
        blockers.append({"kind": "generated_stage_facts_replay_missing"})
    link = closure.get("target_link_closure")
    if isinstance(link, dict):
        if closure_status == "ready" and link.get("status") != "ready":
            blockers.append({"kind": "generated_closure_status_mismatch"})
        database_path = compile_database.get("path") if isinstance(
            compile_database, dict
        ) else None
        if isinstance(database_path, str) and isinstance(generated, dict):
            try:
                current_link = discover_link_closure(
                    root, resolve_repository_path(root, database_path), generated,
                )
                if current_link != link:
                    blockers.append({"kind": "target_link_closure_drift"})
            except (OSError, TypeError, ValueError):
                blockers.append({"kind": "target_link_closure_reopen_failed"})
        for target in link.get("targets", []):
            if not isinstance(target, dict):
                continue
            for key in ("fact_file", "output"):
                value = target.get(key)
                if isinstance(value, dict):
                    bindings.append(value)
            for key in ("inputs", "search_roots", "response_files"):
                bindings.extend(_binding_list(target.get(key)))
        bindings.extend(_binding_list(link.get("support_files")))
    else:
        blockers.append({"kind": "target_link_closure_replay_missing"})
    seen: set[tuple[str, str]] = set()
    for binding in bindings:
        identity = (str(binding.get("path")), str(binding.get("kind")))
        if identity in seen:
            continue
        seen.add(identity)
        blocker = verify_repository_artifact(root, binding)
        if blocker is not None:
            blockers.append(blocker)
    blockers = _unique_blockers(blockers)
    return {
        "schema_version": 1,
        "status": "verified" if not blockers else "blocked",
        "verified_binding_count": len(seen),
        "blockers": blockers,
    }


def apply_generated_closure_admission(
    portfolio: dict[str, Any], *, admission_evidence: dict[str, Any],
) -> dict[str, Any]:
    return apply_candidate_admission(portfolio, admission_evidence)


def _generated_include_roots(
    root: Path,
    database_path: Path,
    units: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    build_root = database_path.parent.resolve()
    candidates: set[str] = set()
    for unit in units:
        for include in unit.get("includes", []):
            if not isinstance(include, dict):
                continue
            path = include.get("path")
            if include.get("scope") != "repository":
                blockers.append({
                    "kind": "external_include_path",
                    "unit_id": unit.get("unit_id"),
                })
                continue
            if include.get("kind") in {"forced", "macros"} or not isinstance(path, str):
                continue
            try:
                candidate = resolve_repository_path(root, Path(*PurePosixPath(path).parts))
                candidate.relative_to(build_root)
            except (OSError, ValueError):
                continue
            if build_root != root:
                candidates.add(path)
    if len(candidates) > MAX_GENERATED_INCLUDE_ROOTS:
        blockers.append({"kind": "generated_include_root_limit_exceeded"})
        candidates = set(sorted(candidates)[:MAX_GENERATED_INCLUDE_ROOTS])
    result = []
    for path in sorted(candidates):
        try:
            result.append(bind_repository_artifact(root, path, kind="directory"))
        except (OSError, ValueError) as error:
            blockers.append(path_error_blocker(
                error, role="generated_include", path=path
            ))
    return result


def _compile_outputs(
    root: Path,
    units: list[dict[str, Any]],
    blockers: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    paths = sorted({
        str(unit.get("output")) for unit in units if isinstance(unit.get("output"), str)
    })
    if len(paths) > MAX_COMPILE_OUTPUTS:
        blockers.append({"kind": "compile_output_limit_exceeded"})
        paths = paths[:MAX_COMPILE_OUTPUTS]
    result = []
    for path in paths:
        try:
            result.append(bind_repository_artifact(root, path, kind="file"))
        except (OSError, ValueError) as error:
            blockers.append(path_error_blocker(error, role="compile_output", path=path))
    return result


def _binding_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _unique_blockers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    keyed = {json_sha256(item): item for item in items}
    return [keyed[key] for key in sorted(keyed)]


__all__ = [
    "discover_generated_build_closure",
    "apply_generated_closure_admission",
    "materialize_build_ir_stage",
    "verify_generated_build_closure",
]

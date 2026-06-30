#!/usr/bin/env python3
"""Validate judge-facing harness entrypoint indexes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO_ROOT / "config" / "competition-env" / "judge-entrypoints" / "flashdb-harness.json"
LOCAL_ABSOLUTE_PATH = re.compile(r"(?:^|[^A-Za-z0-9_])(?:[A-Za-z]:[\\/]|/mnt/[A-Za-z]/)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--require-local-artifacts",
        action="store_true",
        help="Fail when expected target artifacts listed by the entrypoint index are not present locally.",
    )
    args = parser.parse_args()

    result = validate_config(
        args.config,
        require_local_artifacts=args.require_local_artifacts,
        repo_root=REPO_ROOT,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def repo_relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def repo_path(path_text: str, *, repo_root: Path) -> Path:
    assert_repo_relative_posix(path_text)
    return repo_root / Path(*PurePosixPath(path_text).parts)


def assert_repo_relative_posix(path_text: str) -> None:
    if not isinstance(path_text, str) or not path_text:
        raise ValueError("path must be a non-empty string")
    path = PurePosixPath(path_text)
    if "\\" in path_text or path.is_absolute() or path_text.startswith("~"):
        raise ValueError(f"path must be repo-relative POSIX: {path_text}")
    if len(path_text) >= 2 and path_text[1] == ":":
        raise ValueError(f"path must not use a drive prefix: {path_text}")
    if ".." in path.parts:
        raise ValueError(f"path must not contain parent traversal: {path_text}")


def assert_no_local_absolute_path(text: str) -> None:
    if not isinstance(text, str):
        raise ValueError("command/text must be a string")
    if LOCAL_ABSOLUTE_PATH.search(text):
        raise ValueError(f"text contains local absolute path: {text}")


def validate_ref(ref: dict[str, Any], *, repo_root: Path) -> dict[str, Any]:
    path_text = ref.get("path")
    expected_sha = ref.get("sha256")
    if not isinstance(path_text, str) or not isinstance(expected_sha, str):
        raise ValueError("artifact ref must include path and sha256 strings")
    path = repo_path(path_text, repo_root=repo_root)
    if not path.is_file():
        raise ValueError(f"artifact ref path does not exist: {path_text}")
    actual_sha = sha256_file(path)
    if expected_sha != actual_sha:
        raise ValueError(f"artifact ref sha256 mismatch for {path_text}: {expected_sha} != {actual_sha}")
    return {"path": path_text, "sha256": actual_sha, "status": "present"}


def validate_expected_artifacts(
    artifacts: dict[str, Any],
    *,
    require_local_artifacts: bool,
    repo_root: Path,
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    if not isinstance(artifacts, dict):
        raise ValueError("expected_artifacts must be an object")
    for name, path_text in sorted(artifacts.items()):
        if not isinstance(path_text, str):
            raise ValueError(f"expected artifact path must be a string: {name}")
        path = repo_path(path_text, repo_root=repo_root)
        artifact = {"path": path_text, "status": "present" if path.is_file() else "missing"}
        if path.is_file():
            artifact["sha256"] = sha256_file(path)
        elif require_local_artifacts:
            raise ValueError(f"expected artifact is missing: {path_text}")
        result[str(name)] = artifact
    return result


def validate_claim_boundary(config: dict[str, Any]) -> dict[str, Any]:
    boundary = config.get("claim_boundary")
    if not isinstance(boundary, dict):
        raise ValueError("claim_boundary must be an object")
    if boundary.get("semantic_claim_source") != "accepted_evidence_binding":
        raise ValueError("claim_boundary.semantic_claim_source must be accepted_evidence_binding")
    if boundary.get("generated_draft_semantic_pass") is not False:
        raise ValueError("claim_boundary.generated_draft_semantic_pass must be false")
    if boundary.get("translation_coverage_numerator") != 0:
        raise ValueError("claim_boundary.translation_coverage_numerator must be 0")
    return {
        "semantic_claim_source": boundary["semantic_claim_source"],
        "generated_draft_semantic_pass": boundary["generated_draft_semantic_pass"],
        "translation_coverage_numerator": boundary["translation_coverage_numerator"],
    }


def validate_config(
    config_path: Path,
    *,
    require_local_artifacts: bool = False,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    config_path = config_path if config_path.is_absolute() else repo_root / config_path
    config = load_json(config_path)
    errors: list[str] = []
    entrypoint_results: list[dict[str, Any]] = []

    try:
        if config.get("schema_version") != 1:
            raise ValueError("schema_version must be 1")
        if config.get("manifest_kind") != "judge-entrypoints":
            raise ValueError("manifest_kind must be judge-entrypoints")
        if config.get("status") != "active":
            raise ValueError("status must be active")
        claim_boundary = validate_claim_boundary(config)
        validate_ref(config["environment_profile"], repo_root=repo_root)
        assert_no_local_absolute_path(str(config.get("source_pin", {}).get("checkout_command", "")))
    except (KeyError, ValueError) as error:
        errors.append(str(error))
        claim_boundary = {}

    entrypoints = config.get("entrypoints")
    if not isinstance(entrypoints, list) or not entrypoints:
        errors.append("entrypoints must be a non-empty list")
        entrypoints = []

    for entry in entrypoints:
        try:
            if not isinstance(entry, dict):
                raise ValueError("entrypoint must be an object")
            command = entry.get("command")
            if not isinstance(command, str) or "python -B" not in command:
                raise ValueError(f"entrypoint command must use python -B: {entry.get('id')}")
            assert_no_local_absolute_path(command)
            for command_text in entry.get("verification_commands", []):
                assert_no_local_absolute_path(str(command_text))
            audit_command = entry.get("audit_command")
            if isinstance(audit_command, str):
                assert_no_local_absolute_path(audit_command)
            entrypoint_results.append(
                {
                    "id": entry.get("id"),
                    "status": "passed",
                    "purpose": entry.get("purpose"),
                    "profile": validate_ref(entry["profile"], repo_root=repo_root),
                    "tracked_manifest": validate_ref(entry["tracked_manifest"], repo_root=repo_root),
                    "expected_artifacts": validate_expected_artifacts(
                        entry.get("expected_artifacts", {}),
                        require_local_artifacts=require_local_artifacts,
                        repo_root=repo_root,
                    ),
                }
            )
        except (KeyError, ValueError) as error:
            entrypoint_results.append({"id": entry.get("id") if isinstance(entry, dict) else None, "status": "failed"})
            errors.append(str(error))

    return {
        "status": "failed" if errors else "passed",
        "config": {"path": repo_relative(config_path, repo_root), "sha256": sha256_file(config_path)},
        "entrypoint_count": len(entrypoint_results),
        "entrypoints": entrypoint_results,
        "claim_boundary": claim_boundary,
        "require_local_artifacts": require_local_artifacts,
        "errors": errors,
    }


if __name__ == "__main__":
    raise SystemExit(main())

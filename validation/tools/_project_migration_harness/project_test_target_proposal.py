from __future__ import annotations

import hashlib
import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import canonical_json_bytes, content_sha256
from .build_facts import is_linklike
from .build_ir import is_sha256


MAX_PROPOSAL_BYTES = 64 * 1024
_MAKE_TARGET_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_./@+-]{0,127}\Z", re.ASCII)
_LABEL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/+-]{0,255}\Z", re.ASCII)
_CLAIM_BOUNDARY = {
    "semantic_gate": False,
    "translation_coverage_numerator": 0,
}


@dataclass(frozen=True, slots=True)
class ProjectTestTargetProposalSelection:
    path: Path
    sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.path, Path)
            or not is_sha256(self.sha256)
            or isinstance(self.size_bytes, bool)
            or not isinstance(self.size_bytes, int)
            or not 0 < self.size_bytes <= MAX_PROPOSAL_BYTES
        ):
            raise ValueError("project_test_target_proposal_selection_invalid")


def resolve_project_test_target_proposal_selection(
    selection: ProjectTestTargetProposalSelection | None,
    *, harness_root: Path,
) -> ProjectTestTargetProposalSelection | None:
    if selection is None:
        return None
    if not isinstance(selection, ProjectTestTargetProposalSelection):
        raise ValueError("project_test_target_proposal_selection_invalid")
    root = Path(harness_root).resolve(strict=True)
    candidate = selection.path
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        lexical = Path(os.path.abspath(candidate))
        if _path_has_link_component(lexical):
            raise ValueError("linked proposal input")
        resolved = lexical.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as error:
        raise ValueError("project_test_target_proposal_path_invalid") from error
    return ProjectTestTargetProposalSelection(
        resolved, selection.sha256, selection.size_bytes,
    )


def load_project_test_target_proposal(
    selection: ProjectTestTargetProposalSelection,
) -> dict[str, Any]:
    if not isinstance(selection, ProjectTestTargetProposalSelection):
        raise ValueError("project_test_target_proposal_selection_invalid")
    try:
        lexical = Path(os.path.abspath(selection.path))
        if _path_has_link_component(lexical):
            raise ValueError("linked proposal input")
        path = lexical.resolve(strict=True)
        if not path.is_file():
            raise ValueError("proposal input is not a file")
        observed_size = path.stat().st_size
        data = path.read_bytes()
    except (OSError, ValueError) as error:
        raise ValueError("project_test_target_proposal_input_invalid") from error
    if (
        observed_size != selection.size_bytes
        or len(data) != selection.size_bytes
        or hashlib.sha256(data).hexdigest() != selection.sha256
    ):
        raise ValueError("project_test_target_proposal_input_drifted")
    payload = _strict_json(data)
    validate_project_test_target_proposal(payload)
    return {
        "proposal": payload,
        "input_sha256": selection.sha256,
        "input_size_bytes": selection.size_bytes,
        "binding_sha256": content_sha256({
            "proposal": payload,
            "input_sha256": selection.sha256,
            "input_size_bytes": selection.size_bytes,
        }),
    }


def build_project_test_target_proposal(
    *, target: str, provider: str, model: str,
    prompt_sha256: str, response_sha256: str,
) -> dict[str, Any]:
    return validate_project_test_target_proposal({
        "schema_version": 1,
        "artifact_kind": "project-test-target-proposal-v1",
        "build_system": "make",
        "target": target,
        "producer": {
            "kind": "ai-candidate", "provider": provider, "model": model,
            "prompt_sha256": prompt_sha256,
            "response_sha256": response_sha256,
        },
        "claim_boundary": dict(_CLAIM_BOUNDARY),
    })


def validate_project_test_target_proposal(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "schema_version", "artifact_kind", "build_system", "target",
        "producer", "claim_boundary",
    }:
        raise ValueError("project_test_target_proposal_schema_invalid")
    producer = value.get("producer")
    if (
        value.get("schema_version") != 1
        or value.get("artifact_kind") != "project-test-target-proposal-v1"
        or value.get("build_system") != "make"
        or not valid_make_target(value.get("target"))
        or value.get("claim_boundary") != _CLAIM_BOUNDARY
        or not isinstance(producer, Mapping)
        or set(producer) != {
            "kind", "provider", "model", "prompt_sha256", "response_sha256",
        }
        or producer.get("kind") != "ai-candidate"
        or not _valid_label(producer.get("provider"))
        or not _valid_label(producer.get("model"))
        or not is_sha256(producer.get("prompt_sha256"))
        or not is_sha256(producer.get("response_sha256"))
    ):
        raise ValueError("project_test_target_proposal_schema_invalid")
    return dict(value)


def validate_bound_project_test_target_proposal(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != {
        "proposal", "input_sha256", "input_size_bytes", "binding_sha256",
    }:
        raise ValueError("project_test_target_proposal_binding_invalid")
    proposal = validate_project_test_target_proposal(value.get("proposal"))
    size = value.get("input_size_bytes")
    proposal_bytes = canonical_json_bytes(proposal)
    core = {
        "proposal": proposal,
        "input_sha256": value.get("input_sha256"),
        "input_size_bytes": size,
    }
    if (
        not is_sha256(value.get("input_sha256"))
        or isinstance(size, bool) or not isinstance(size, int)
        or not 0 < size <= MAX_PROPOSAL_BYTES
        or size != len(proposal_bytes)
        or value.get("input_sha256")
        != hashlib.sha256(proposal_bytes).hexdigest()
        or value.get("binding_sha256") != content_sha256(core)
    ):
        raise ValueError("project_test_target_proposal_binding_invalid")
    return {**core, "binding_sha256": value["binding_sha256"]}


def valid_make_target(value: Any) -> bool:
    return (
        isinstance(value, str)
        and _MAKE_TARGET_RE.fullmatch(value) is not None
        and not any(part in {"", ".", ".."} for part in value.split("/"))
    )


def _strict_json(data: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in items:
            if key in result:
                raise ValueError("duplicate proposal key")
            result[key] = item
        return result

    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("project_test_target_proposal_json_invalid") from error
    if not isinstance(value, dict) or canonical_json_bytes(value) != data:
        raise ValueError("project_test_target_proposal_json_not_canonical")
    return value


def _valid_label(value: Any) -> bool:
    return isinstance(value, str) and _LABEL_RE.fullmatch(value) is not None


def _path_has_link_component(path: Path) -> bool:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.exists() and is_linklike(current):
            return True
    return False


__all__ = [
    "MAX_PROPOSAL_BYTES", "ProjectTestTargetProposalSelection",
    "build_project_test_target_proposal",
    "load_project_test_target_proposal", "valid_make_target",
    "resolve_project_test_target_proposal_selection",
    "validate_bound_project_test_target_proposal",
    "validate_project_test_target_proposal",
]

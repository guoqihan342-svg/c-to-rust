from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path, PurePosixPath
import re
from typing import Any

from .artifacts import content_sha256
from .native_link_actual_paths import (
    inspect_mapped_native_artifact,
    normalize_native_guest_roots,
)
from .native_link_context import validate_native_link_context
from .native_link_model import validate_native_link_candidate
from .native_link_trace import validate_cargo_linker_trace


NATIVE_LINK_ACTUAL_RESOLUTION_SCHEMA_VERSION = 1
_SHARED_NAME = re.compile(
    r"lib(?P<stem>[A-Za-z0-9][A-Za-z0-9_+.-]*)\.so(?P<version>(?:\.[0-9]+)*)\Z",
    re.ASCII,
)
_STATIC_NAME = re.compile(
    r"lib(?P<stem>[A-Za-z0-9][A-Za-z0-9_+.-]*)\.a\Z",
    re.ASCII,
)
_RUST_LINK_STEM = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_+.-]{0,126}\Z", re.ASCII,
)


def resolve_traced_native_artifacts(
    trace: Mapping[str, Any],
    context: Mapping[str, Any],
    candidate: Mapping[str, Any],
    *,
    guest_roots: Mapping[str, Path] | None = None,
) -> dict[str, Any]:
    """Observe unique traced Linux library objects without resolving semantics."""
    normalized_trace = validate_cargo_linker_trace(trace)
    validate_native_link_context(context)
    validate_native_link_candidate(candidate, context)
    roots = normalize_native_guest_roots(guest_roots)
    proposals = {
        item["requirement_id"]: item for item in candidate["proposals"]
    }
    requirements = [
        _resolve_requirement(
            requirement,
            proposals[requirement["requirement_id"]],
            normalized_trace,
            roots,
        )
        for requirement in sorted(
            context["requirements"], key=lambda item: item["requirement_id"],
        )
    ]
    payload = {
        "schema_version": NATIVE_LINK_ACTUAL_RESOLUTION_SCHEMA_VERSION,
        "context_sha256": context["context_sha256"],
        "candidate_sha256": candidate["candidate_sha256"],
        "trace_entry_set_sha256": normalized_trace["entry_set_sha256"],
        "status": (
            "observed"
            if requirements
            and all(item["status"] == "passed" for item in requirements)
            else "blocked"
        ),
        "requirements": requirements,
        "unverified_gates": ["symbols", "target-triple"],
        "semantic_gate": False,
        "resolution_gate": False,
    }
    payload["artifact_sha256"] = content_sha256(payload)
    return payload


def _resolve_requirement(
    requirement: Mapping[str, Any],
    proposal: Mapping[str, Any],
    trace: Mapping[str, Any],
    roots: Mapping[str, Path],
) -> dict[str, Any]:
    trace_sha256 = str(trace["entry_set_sha256"])
    if proposal["strategy"] != "rustc-link-lib":
        return _item(
            requirement, trace_sha256,
            "native_link_strategy_not_rustc_link_lib",
        )
    library_format = str(requirement["library_format"])
    if library_format == "import-or-static-library":
        return _item(
            requirement, trace_sha256,
            "native_link_linux_format_unsupported",
        )
    stem = _link_stem(str(requirement["portable_name"]), library_format)
    if stem is None:
        return _item(
            requirement, trace_sha256,
            "native_link_portable_name_unsupported",
        )
    if proposal["rustc_link_name"] != stem:
        return _item(
            requirement, trace_sha256,
            "native_link_proposal_name_mismatch",
        )
    expected_kind = "dylib" if library_format == "shared-library" else "static"
    if proposal["rustc_link_kind"] != expected_kind:
        return _item(
            requirement, trace_sha256,
            "native_link_proposal_kind_mismatch",
        )
    matches = [
        entry for entry in trace["entries"]
        if _matches_file_name(
            PurePosixPath(entry["path"]).name, library_format, stem,
            str(requirement["portable_name"]),
        )
    ]
    ordinals = [int(entry["ordinal"]) for entry in matches]
    paths = {str(entry["path"]) for entry in matches}
    if not paths:
        return _item(
            requirement, trace_sha256, "native_link_trace_match_missing",
            ordinals=ordinals,
        )
    if len(paths) != 1:
        return _item(
            requirement, trace_sha256, "native_link_trace_match_ambiguous",
            ordinals=ordinals,
        )
    guest_path = next(iter(paths))
    file_name = PurePosixPath(guest_path).name
    reason_code, inspection = inspect_mapped_native_artifact(
        guest_path, library_format, roots,
    )
    return _item(
        requirement,
        trace_sha256,
        reason_code,
        file_name=file_name,
        ordinals=ordinals,
        inspection=inspection,
        passed=reason_code == "native_link_actual_artifact_observed",
    )


def _link_stem(portable_name: str, library_format: str) -> str | None:
    pattern = _SHARED_NAME if library_format == "shared-library" else _STATIC_NAME
    matched = pattern.fullmatch(portable_name)
    if matched is None:
        return None
    stem = matched.group("stem")
    valid = _RUST_LINK_STEM.fullmatch(stem) is not None and ".." not in stem
    return stem if valid else None


def _matches_file_name(
    name: str, library_format: str, stem: str, portable_name: str,
) -> bool:
    if library_format == "static-archive":
        return name == f"lib{stem}.a"
    matched = _SHARED_NAME.fullmatch(name)
    required = _SHARED_NAME.fullmatch(portable_name)
    if matched is None or required is None or matched.group("stem") != stem:
        return False
    version = matched.group("version")
    required_version = required.group("version")
    same_family = version == required_version or version.startswith(
        required_version + ".",
    )
    return not version or not required_version or same_family


def _item(
    requirement: Mapping[str, Any],
    trace_sha256: str,
    reason_code: str,
    *,
    file_name: str | None = None,
    ordinals: list[int] | None = None,
    inspection: dict[str, Any] | None = None,
    passed: bool = False,
) -> dict[str, Any]:
    return {
        "requirement_id": requirement["requirement_id"],
        "status": "passed" if passed else "blocked",
        "reason_code": reason_code,
        "file_name": file_name,
        "trace_ordinals": [] if ordinals is None else ordinals,
        "trace_entry_set_sha256": trace_sha256,
        "inspection": inspection,
    }


__all__ = [
    "NATIVE_LINK_ACTUAL_RESOLUTION_SCHEMA_VERSION",
    "resolve_traced_native_artifacts",
]

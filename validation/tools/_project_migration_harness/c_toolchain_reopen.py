from __future__ import annotations

from collections.abc import Mapping, Sequence
import copy
from pathlib import Path, PureWindowsPath
import re
from typing import Any

from .artifacts import content_sha256
from .c_toolchain_environment import (
    environment_binding, environment_values, host_binding,
)
from .c_toolchain_probe import ProbeExecution, probe_plans, run_tool_probes
from .c_toolchain_schema import (
    C_TOOLCHAIN_ARTIFACT_KIND, C_TOOLCHAIN_PROFILES, C_TOOLCHAIN_RAW_ROLE,
    tool_records_by_token, validate_c_toolchain_evidence,
)
from .host_tool_binding import (
    MAX_TOOL_RECORDS, HostToolBindingError, Resolver, classify_tool_basename,
    reopen_profile_binding, resolve_host_tool, validate_requests,
)


def collect_c_toolchain_evidence(
    requests: Sequence[Mapping[str, Any]], *, profile: str = "competition",
    environment: Mapping[str, str] | None = None, resolver: Resolver | None = None,
    runner: Any = None, profile_binding: Mapping[str, Any] | None = None,
) -> dict:
    normalized = validate_requests(requests)
    if profile not in C_TOOLCHAIN_PROFILES:
        raise ValueError("c_toolchain_profile_invalid")
    if profile == "competition" and profile_binding is None:
        raise ValueError("c_toolchain_competition_profile_binding_required")
    bound_profile = None
    profile_facts = None
    if profile_binding is not None:
        bound_profile, profile_facts = reopen_profile_binding(profile_binding)
    values = environment_values(environment)
    env_evidence = environment_binding(values)
    host = host_binding(values)
    path_sha256 = env_evidence["path_snapshot"]["fingerprint"]
    effective_runner = runner
    if profile == "competition" and host["system"] != "linux" and runner is None:
        effective_runner = _not_started_runner
    records: dict[str, dict[str, Any]] = {}
    for request in normalized:
        records[request["token"]] = _collect_tool(
            request["token"], request["roles"], requested=True,
            derived_from_tokens=[], profile=profile, environment=values,
            path_sha256=path_sha256, resolver=resolver, runner=effective_runner,
        )
    _collect_derived_linkers(
        records, normalized, profile=profile, environment=values,
        path_sha256=path_sha256, resolver=resolver, runner=effective_runner,
    )
    blockers: list[str] = []
    if profile == "competition":
        if host["system"] != "linux":
            blockers.append("competition_host_os_family_mismatch")
        if profile_facts is None:
            raise ValueError("c_toolchain_competition_profile_binding_required")
        expected_os = profile_facts["os_name"].strip().lower()
        if ("linux" if expected_os in {"ubuntu", "linux"} else expected_os) != host["system"]:
            blockers.append("competition_host_os_family_mismatch")
        _apply_gcc_profile_version(records, profile_facts["gcc_version"])
    for token, record in records.items():
        blockers.extend(f"{token}:{code}" for code in record["blockers"])
    blockers = sorted(set(blockers))
    core = {
        "schema_version": 1,
        "artifact_kind": C_TOOLCHAIN_ARTIFACT_KIND,
        "raw_fact_role": C_TOOLCHAIN_RAW_ROLE,
        "profile": profile,
        "profile_binding": bound_profile,
        "status": "blocked" if blockers else "ready",
        "requests": normalized,
        "host": host,
        "environment": env_evidence,
        "tools": [records[token] for token in sorted(records)],
        "blockers": blockers,
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    }
    payload = {**core, "evidence_sha256": content_sha256(core)}
    validate_c_toolchain_evidence(payload)
    return payload


def reopen_c_toolchain_evidence(
    stored: Any, *, environment: Mapping[str, str] | None = None,
    resolver: Resolver | None = None, runner: Any = None,
    profile_binding: Mapping[str, Any] | None = None,
) -> dict:
    validate_c_toolchain_evidence(stored)
    expected_profile = stored["profile_binding"]
    if profile_binding is not None and dict(profile_binding) != expected_profile:
        raise ValueError("c_toolchain_profile_binding_drift")
    current = collect_c_toolchain_evidence(
        copy.deepcopy(stored["requests"]), profile=stored["profile"],
        environment=environment, resolver=resolver, runner=runner,
        profile_binding=expected_profile,
    )
    if current != stored:
        raise ValueError("c_toolchain_evidence_drift")
    return current


def _collect_tool(
    token: str, roles: list[str], *, requested: bool,
    derived_from_tokens: list[str], profile: str,
    environment: Mapping[str, str], path_sha256: str,
    resolver: Resolver | None, runner: Any,
) -> dict[str, Any]:
    family, basename = classify_tool_basename(_basename(token))
    mode = "absolute" if _absolute_token(token) else "path-search"
    base = {
        "token": token,
        "roles": list(roles),
        "requested": requested,
        "derived_from_tokens": sorted(set(derived_from_tokens)),
        "family": family,
        "basename": basename,
        "resolution": {"mode": mode, "path_snapshot_sha256": path_sha256},
    }
    try:
        binding = resolve_host_tool(
            token, roles, environment=environment, resolver=resolver,
        )
    except HostToolBindingError as error:
        blockers = [error.code]
        return {
            **base, "status": "blocked", "resolved_path": None,
            "binary": None, "probe_policy": "not-started", "probes": [],
            "blockers": blockers,
        }
    probes = run_tool_probes(
        binding.resolved_path, binding.family, roles,
        environment=environment, runner=runner,
    )
    blockers = []
    if profile == "competition" and family == "compiler-wrapper" and basename in {"distcc", "icecc"}:
        blockers.append("competition_distributed_wrapper_rejected")
    for probe, plan in zip(probes, probe_plans(family, roles), strict=True):
        if plan.applicable and probe["status"] not in {"reported", "reported-empty/default"}:
            blockers.append(f"probe_{probe['kind']}_{probe['status']}")
    return {
        **base,
        "status": "blocked" if blockers else "ready",
        "resolved_path": binding.resolved_path,
        "binary": binding.binary,
        "probe_policy": (
            "hash-only-wrapper" if family == "compiler-wrapper" else "fixed-probes"
        ),
        "probes": probes,
        "blockers": sorted(set(blockers)),
    }


def _collect_derived_linkers(
    records: dict[str, dict[str, Any]], requests: list[dict[str, Any]], *,
    profile: str, environment: Mapping[str, str], path_sha256: str,
    resolver: Resolver | None, runner: Any,
) -> None:
    for request in requests:
        if "linker-driver" not in request["roles"]:
            continue
        parent = records[request["token"]]
        probe = next(
            (item for item in parent["probes"] if item["kind"] == "linker-path"),
            None,
        )
        if probe is None or probe["status"] != "reported":
            _add_blocker(parent, "derived_linker_missing")
            continue
        token = probe["value"]
        if token not in records and len(records) >= MAX_TOOL_RECORDS:
            _add_blocker(parent, "tool_record_limit_exceeded")
            continue
        try:
            derived = _collect_tool(
                token, ["linker"], requested=token in {item["token"] for item in requests},
                derived_from_tokens=[request["token"]], profile=profile,
                environment=environment, path_sha256=path_sha256,
                resolver=resolver, runner=runner,
            )
        except (TypeError, ValueError):
            _add_blocker(parent, "derived_linker_token_invalid")
            continue
        existing = records.get(token)
        if existing is None:
            records[token] = derived
        elif not _equivalent_tool_binding(existing, derived):
            _add_blocker(parent, "derived_linker_binding_conflict")
        else:
            existing["derived_from_tokens"] = sorted(set(
                [*existing["derived_from_tokens"], request["token"]]
            ))
        selected = records.get(token)
        if selected is None or selected["status"] != "ready":
            _add_blocker(parent, "derived_linker_unavailable")


def _equivalent_tool_binding(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    ignored = {"requested", "derived_from_tokens"}
    return (
        left.get("roles") == right.get("roles")
        and {key: value for key, value in left.items() if key not in ignored}
        == {key: value for key, value in right.items() if key not in ignored}
    )


def _apply_gcc_profile_version(
    records: dict[str, dict[str, Any]], expected: str,
) -> None:
    pattern = re.compile(rf"(?<![0-9.]){re.escape(expected)}(?![0-9.])")
    for record in records.values():
        if record["family"] != "gnu-compiler" or "compiler-driver" not in record["roles"]:
            continue
        version = next(
            (item for item in record["probes"] if item["kind"] == "version"),
            None,
        )
        if version is None or version["status"] != "reported" or pattern.search(version["value"]) is None:
            _add_blocker(record, "competition_gcc_version_mismatch")


def _add_blocker(record: dict[str, Any], code: str) -> None:
    record["blockers"] = sorted(set([*record["blockers"], code]))
    record["status"] = "blocked"


def _not_started_runner(argv: list[str], **_: Any) -> ProbeExecution:
    return ProbeExecution(None, b"", b"", started=False)


def _basename(value: str) -> str:
    return value.replace("\\", "/").rsplit("/", 1)[-1]


def _absolute_token(value: str) -> bool:
    return Path(value).is_absolute() or PureWindowsPath(value).is_absolute()


__all__ = [
    "C_TOOLCHAIN_RAW_ROLE", "collect_c_toolchain_evidence",
    "reopen_c_toolchain_evidence", "tool_records_by_token",
    "validate_c_toolchain_evidence",
]

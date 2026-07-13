from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping
from typing import Any

from .compiler_diagnostics import validated_compiler_diagnostic_details
from validation.tools.replay_assertion_inventory import (
    validated_runtime_localization,
)
from .context_security import redact_metadata_text, sanitize_value
from .repair_contract import normalize_validation_result


MAX_FAILURE_FACTS = 32
MAX_FAILURES_PER_GATE = 2
MAX_GATE_BYTES = 64
MAX_KIND_BYTES = 128
MAX_MESSAGE_BYTES = 1_024
MAX_DETAIL_TEXT_BYTES = 1_024
MAX_DETAILS_BYTES = 1_024
MAX_DETAIL_ITEMS = 32
MAX_DETAIL_DEPTH = 5

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_GATES = (
    "rustc",
    "generated_replay",
    "schema_diff",
    "negative_mutation",
    "unsafe_scan",
    "unsafe_ledger",
    "alias_contract",
    "abi_contract",
    "oracle_contract",
    "final_verification",
)


def extract_gate_failure_facts(
    gate_payloads: Mapping[str, Any] | Any,
    *,
    selected_candidate_sha256: str,
) -> dict[str, Any]:
    """Normalize validator-owned common-gate results for the repair loop.

    Every required payload must directly bind ``candidate_sha256`` to the
    selected Rust candidate. A ``passed`` result only means that no repair fact
    was found; this repair-contract payload never grants semantic acceptance.
    """
    selected_sha = str(selected_candidate_sha256).lower()
    if not SHA256_PATTERN.fullmatch(selected_sha):
        return _result(
            [_fact("candidate_binding", "invalid_sha256", "Selected candidate SHA-256 is invalid.")]
        )
    if not isinstance(gate_payloads, Mapping):
        return _result(
            [_fact("common_gates", "malformed_payloads", "Common gate payloads must be an object.")]
        )

    failures: list[dict[str, Any]] = []
    unknown = sorted(str(key) for key in gate_payloads if key not in REQUIRED_GATES)
    if unknown:
        failures.append(
            _fact(
                "common_gates",
                "unsupported_gate",
                "Common gate payloads contain unsupported gate names.",
                details={"gates": unknown},
            )
        )

    for gate in REQUIRED_GATES:
        if len(failures) >= MAX_FAILURE_FACTS:
            break
        payload = gate_payloads.get(gate)
        failures.extend(_gate_failures(gate, payload, selected_sha))

    return _result(failures[:MAX_FAILURE_FACTS])


def _gate_failures(gate: str, payload: Any, selected_sha: str) -> list[dict[str, Any]]:
    if payload is None:
        return [_fact(gate, "artifact_missing", f"Required {gate} artifact is missing.")]
    if not isinstance(payload, Mapping):
        return [_fact(gate, "malformed_payload", f"{gate} payload must be an object.")]

    bound_sha = payload.get("candidate_sha256")
    if not isinstance(bound_sha, str) or not SHA256_PATTERN.fullmatch(bound_sha.lower()):
        return [_fact(gate, "candidate_binding_missing", f"{gate} payload has no valid candidate SHA-256 binding.")]
    if bound_sha.lower() != selected_sha:
        return [
            _fact(
                gate,
                "candidate_sha256_mismatch",
                f"{gate} payload is bound to a different candidate.",
                details={"expected": selected_sha, "actual": bound_sha.lower()},
            )
        ]

    status = payload.get("status")
    allowed = {"passed", "expected_failed"} if gate == "negative_mutation" else {"passed"}
    embedded = payload.get("failures")
    if status in allowed and isinstance(embedded, list) and embedded:
        return [
            _fact(
                gate,
                "contradictory_payload",
                f"{gate} reports a passing status together with failure entries.",
            )
        ]
    if status not in allowed:
        facts = _embedded_failures(gate, payload)
        if facts:
            return facts
        return [
            _fact(
                gate,
                "gate_not_passed",
                f"{gate} did not report an accepted passing status.",
                details={"status": status if isinstance(status, str) else "missing"},
            )
        ]

    invariant_failure = _passing_invariant_failure(gate, payload)
    return [invariant_failure] if invariant_failure else []


def _passing_invariant_failure(gate: str, payload: Mapping[str, Any]) -> dict[str, Any] | None:
    if gate == "rustc" and "returncode" in payload and payload.get("returncode") != 0:
        return _fact(gate, "nonzero_returncode", "rustc reported passed with a nonzero return code.")
    if gate == "generated_replay":
        execution = payload.get("replay_execution")
        if payload.get("generated_draft_replay_pass") is not True:
            return _fact(gate, "replay_not_proven", "Generated replay did not prove the selected candidate passed.")
        if not isinstance(execution, Mapping) or execution.get("status") != "passed":
            return _fact(gate, "execution_not_passed", "Generated replay execution is missing or not passed.")
    if gate == "schema_diff":
        if "first_mismatch" not in payload:
            return _fact(gate, "comparison_missing", "Schema diff does not contain first_mismatch evidence.")
        if payload.get("first_mismatch") is not None:
            return _fact(
                gate,
                "value_mismatch",
                "Schema diff contains a mismatch.",
                details={"first_mismatch": payload.get("first_mismatch")},
            )
    if gate == "negative_mutation" and not (
        payload.get("mutation_detected") is True or payload.get("detected") is True
    ):
        return _fact(gate, "mutation_not_detected", "Negative mutation was not detected by the diff gate.")
    if gate == "final_verification" and payload.get("semantic_pass") is not True:
        return _fact(
            gate,
            "semantic_acceptance_missing",
            "Final verification did not grant validator-owned semantic acceptance.",
        )
    return None


def _embedded_failures(gate: str, payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    entries: Any = payload.get("failures")
    if not isinstance(entries, list) or not entries:
        entries = payload.get("errors")
    if not isinstance(entries, list) or not entries:
        reason = payload.get("reason") or payload.get("error")
        if reason is None:
            blocked = payload.get("blocked_reasons")
            entries = blocked if isinstance(blocked, list) else []
        else:
            entries = [reason]

    facts: list[dict[str, Any]] = []
    for entry in entries[:MAX_FAILURES_PER_GATE]:
        if isinstance(entry, Mapping):
            kind = entry.get("kind") or entry.get("code") or "gate_failure"
            if isinstance(kind, Mapping):
                kind = kind.get("code") or "gate_failure"
            message = entry.get("message") or entry.get("reason") or "Validator reported a gate failure."
            details = entry.get("details")
            if not isinstance(details, Mapping):
                details = {
                    str(key): value
                    for key, value in entry.items()
                    if key not in {"gate", "kind", "code", "message", "reason", "details"}
                }
            compiler_details = (
                validated_compiler_diagnostic_details(details)
                if gate in {"rustc", "generated_replay"}
                else None
            )
            runtime_details = (
                validated_runtime_localization(details)
                if gate == "generated_replay"
                and str(kind) == "runtime_assertion_failed"
                else None
            )
            safe_details = compiler_details or runtime_details or details
            facts.append(
                _fact(
                    gate,
                    str(kind),
                    str(message),
                    details=safe_details,
                    compiler_owned=compiler_details is not None,
                    oracle_safe=runtime_details is not None,
                )
            )
        else:
            facts.append(_fact(gate, "gate_failure", str(entry)))
    return facts


def _fact(
    gate: str,
    kind: str,
    message: str,
    *,
    details: Mapping[str, Any] | None = None,
    compiler_owned: bool = False,
    oracle_safe: bool = False,
) -> dict[str, Any]:
    oracle_sensitive = not compiler_owned and not oracle_safe and gate in {
        "generated_replay",
        "schema_diff",
        "negative_mutation",
        "oracle_contract",
        "final_verification",
    }
    if oracle_sensitive:
        message = "Semantic gate failed; concrete oracle values are withheld from repair input."
        details = _redact_oracle_details(details) if details else details
    fact: dict[str, Any] = {
        "gate": _bounded_text(gate, "unknown_gate", max_bytes=MAX_GATE_BYTES),
        "kind": _bounded_text(kind, "gate_failure", max_bytes=MAX_KIND_BYTES),
        "message": _bounded_text(
            message,
            "Validator reported a gate failure.",
            max_bytes=MAX_MESSAGE_BYTES,
        ),
    }
    if details:
        fact["details"] = _bounded_details(details)
    return fact


def _redact_oracle_details(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "oracle_values": "withheld",
        "detail_keys": sorted(str(key) for key in value)[:32],
    }


def _bounded_text(value: str, fallback: str, *, max_bytes: int) -> str:
    text = redact_metadata_text(value).strip() or fallback
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    suffix = b"..."
    return encoded[: max_bytes - len(suffix)].decode("utf-8", errors="ignore").rstrip() + "..."


def _bounded_details(value: Mapping[str, Any]) -> dict[str, Any]:
    sanitized = sanitize_value(dict(value))
    bounded = _bound_value(sanitized, depth=0)
    if not isinstance(bounded, dict):
        return {"summary": "Validator details were not an object."}
    encoded = json.dumps(bounded, sort_keys=True, ensure_ascii=False).encode("utf-8")
    if len(encoded) > MAX_DETAILS_BYTES:
        return {"summary": "Validator details exceeded the bounded repair context."}
    return bounded


def _bound_value(value: Any, *, depth: int) -> Any:
    if depth >= MAX_DETAIL_DEPTH:
        return "<depth-limit>"
    if isinstance(value, str):
        return _bounded_text(value, "<empty>", max_bytes=MAX_DETAIL_TEXT_BYTES)
    if isinstance(value, float) and not math.isfinite(value):
        return "<non-finite-number>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, list):
        return [_bound_value(item, depth=depth + 1) for item in value[:MAX_DETAIL_ITEMS]]
    if isinstance(value, Mapping):
        return {
            _bounded_text(str(key), "field", max_bytes=MAX_KIND_BYTES): _bound_value(
                item, depth=depth + 1
            )
            for key, item in list(value.items())[:MAX_DETAIL_ITEMS]
        }
    return _bounded_text(str(value), "<unsupported>", max_bytes=MAX_DETAIL_TEXT_BYTES)


def _result(failures: list[dict[str, Any]]) -> dict[str, Any]:
    return normalize_validation_result(
        {
            "schema_version": 1,
            "status": "failed" if failures else "passed",
            "failures": failures,
        }
    )

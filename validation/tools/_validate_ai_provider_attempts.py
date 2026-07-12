from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from validation.tools._ai_candidate_harness_parts.provider_runtime import (
    is_retryable_empty_completion,
)


ArtifactResolver = Callable[..., Path | None]
HashBindingValidator = Callable[..., bool]
JsonLoader = Callable[[Path], Any]
ReceiptValidator = Callable[..., list[str]]


def validate_ai_provider_attempts(
    manifest: dict[str, Any],
    *,
    bindings: dict[str, Any] | None,
    provider_invocations: int,
    manifest_path: Path,
    summary_path: Path,
    repo_root: Path,
    policy: dict[str, Any],
    nested_ref_is_hash_bound: HashBindingValidator,
    resolve_artifact: ArtifactResolver,
    load_json: JsonLoader,
    validate_receipt: ReceiptValidator,
) -> tuple[list[str], bool]:
    reasons: list[str] = []
    schema_version = manifest.get("schema_version")
    if not isinstance(schema_version, int) or isinstance(schema_version, bool):
        return ["ai_manifest_provider_attempts_schema_invalid"], False
    if schema_version < 9:
        return (
            ["ai_manifest_retry_requires_schema_version_9"]
            if provider_invocations == 2
            else [],
            provider_invocations <= 1,
        )
    attempts = manifest.get("provider_attempts")
    if not isinstance(attempts, list) or len(attempts) != provider_invocations:
        return ["ai_manifest_provider_attempts_invalid"], False

    expected_reasons = ["initial", "provider_empty_completion_retry"]
    prompt_ref = bindings.get("prompt") if isinstance(bindings, dict) else None
    for index, attempt in enumerate(attempts):
        if (
            not isinstance(attempt, dict)
            or attempt.get("attempt_index") != index + 1
            or attempt.get("reason") != expected_reasons[index]
        ):
            reasons.append("ai_manifest_provider_attempt_identity_invalid")
            continue
        response_ref = attempt.get("raw_response")
        receipt_ref = attempt.get("invocation_receipt")
        if not nested_ref_is_hash_bound(
            response_ref,
            owner_path=manifest_path,
            summary_path=summary_path,
            repo_root=repo_root,
        ):
            reasons.append("ai_manifest_provider_attempt_response_binding_invalid")
        if not nested_ref_is_hash_bound(
            receipt_ref,
            owner_path=manifest_path,
            summary_path=summary_path,
            repo_root=repo_root,
        ):
            reasons.append("ai_manifest_provider_attempt_receipt_binding_invalid")
            continue
        reasons.extend(
            validate_receipt(
                receipt_ref,
                bindings={"prompt": prompt_ref, "raw_response": response_ref},
                manifest_path=manifest_path,
                summary_path=summary_path,
                repo_root=repo_root,
                policy=policy,
            )
        )
        receipt_path = resolve_artifact(
            receipt_ref.get("path"),
            owner_path=manifest_path,
            summary_path=summary_path,
            repo_root=repo_root,
        )
        try:
            receipt = load_json(receipt_path) if receipt_path is not None else None
        except (OSError, UnicodeError, json.JSONDecodeError):
            receipt = None
        expected_session_ref = (
            receipt.get("session_export_identity") if isinstance(receipt, dict) else None
        )
        if attempt.get("session_export_identity") != expected_session_ref:
            reasons.append("ai_manifest_provider_attempt_session_binding_invalid")

    if attempts:
        final_attempt = attempts[-1]
        if isinstance(final_attempt, dict) and isinstance(bindings, dict):
            if (
                bindings.get("raw_response") != final_attempt.get("raw_response")
                or bindings.get("invocation_receipt")
                != final_attempt.get("invocation_receipt")
            ):
                reasons.append("ai_manifest_provider_attempt_final_binding_mismatch")

    retry = manifest.get("provider_retry")
    if provider_invocations in {0, 1}:
        if retry is not None:
            reasons.append("ai_manifest_provider_retry_unexpected")
    elif provider_invocations == 2:
        expected_retry = {
            "schema_version": 1,
            "trigger": "provider_empty_completion",
            "max_retries": 1,
            "initial_attempt": 1,
            "retry_attempt": 2,
            "result": manifest.get("status"),
            "semantic_gate": False,
        }
        if retry != expected_retry:
            reasons.append("ai_manifest_provider_retry_invalid")
        first_attempt = attempts[0] if attempts and isinstance(attempts[0], dict) else None
        first_response_ref = first_attempt.get("raw_response") if first_attempt is not None else None
        first_response_path = (
            resolve_artifact(
                first_response_ref.get("path"),
                owner_path=manifest_path,
                summary_path=summary_path,
                repo_root=repo_root,
            )
            if isinstance(first_response_ref, dict)
            and isinstance(first_response_ref.get("path"), str)
            else None
        )
        try:
            first_response = (
                first_response_path.read_text(encoding="utf-8")
                if first_response_path is not None
                else ""
            )
        except (OSError, UnicodeError):
            first_response = ""
        if not is_retryable_empty_completion(first_response):
            reasons.append("ai_manifest_provider_retry_trigger_invalid")
    return sorted(set(reasons)), not reasons


__all__ = ["validate_ai_provider_attempts"]

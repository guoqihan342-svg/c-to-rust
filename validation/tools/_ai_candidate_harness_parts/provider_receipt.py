from __future__ import annotations

from pathlib import Path
from typing import Any

from .context import atomic_write_json, sha256_path
from .prompt_transport import prompt_transport_contract
from .provider_response import session_ids_from_jsonl
from .provider_runtime import ProviderExecution


def write_invocation_receipt(
    execution: ProviderExecution,
    *,
    resolved_model: str,
    agent: str,
    variant: str,
    persisted_response: str,
    prompt_path: Path,
    response_path: Path,
    receipt_path: Path,
    session_identity_path: Path,
) -> None:
    identity = dict(
        execution.identity_receipt
        or expected_runner_identity_receipt(
            resolved_model=resolved_model,
            agent=agent,
            variant=variant,
            stdout=persisted_response,
        )
    )
    session_export_sha256 = identity.pop("session_export_sha256", None)
    session_identity_ref = None
    if identity["source"] == "opencode-session-export":
        session_identity = {
            "schema_version": 1,
            "source": "opencode-session-export-identity-projection",
            "session_export_sha256": session_export_sha256,
            "full_export_persisted": False,
            "identity": {
                key: identity[key]
                for key in (
                    "session_id",
                    "provider_id",
                    "model_id",
                    "agent",
                    "variant",
                    "opencode_version",
                )
            },
        }
        atomic_write_json(session_identity_path, session_identity)
        session_identity_ref = {
            "path": session_identity_path.name,
            "sha256": sha256_path(session_identity_path),
        }
    receipt = {
        "schema_version": 1,
        **identity,
        "resolved_model": resolved_model,
        "prompt_sha256": sha256_path(prompt_path),
        "raw_response_sha256": sha256_path(response_path),
        "session_ids": session_ids_from_jsonl(persisted_response),
        "prompt_transport": prompt_transport_contract(),
        "invocation_contract": invocation_contract(
            resolved_model=resolved_model,
            agent=agent,
            variant=variant,
        ),
    }
    if session_identity_ref is not None:
        receipt["session_export_identity"] = session_identity_ref
    atomic_write_json(receipt_path, receipt)


def expected_runner_identity_receipt(
    *,
    resolved_model: str,
    agent: str,
    variant: str,
    stdout: str,
) -> dict[str, str]:
    provider_id, model_id = resolved_model.split("/", 1)
    session_ids = session_ids_from_jsonl(stdout)
    return {
        "source": "runner-contract",
        "session_id": session_ids[0] if len(session_ids) == 1 else "unavailable",
        "provider_id": provider_id,
        "model_id": model_id,
        "agent": agent,
        "variant": variant,
        "opencode_version": "unattested",
    }


def invocation_contract(
    *,
    resolved_model: str,
    agent: str,
    variant: str,
) -> dict[str, Any]:
    return {
        "tool": "opencode",
        "subcommand": "run",
        "pure": True,
        "format": "json",
        "print_logs": True,
        "log_level": "ERROR",
        "resolved_model": resolved_model,
        "agent": agent,
        "variant": variant,
        "prompt_transport": prompt_transport_contract(),
    }


__all__ = [
    "expected_runner_identity_receipt",
    "invocation_contract",
    "write_invocation_receipt",
]

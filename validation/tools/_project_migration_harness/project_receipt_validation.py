from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any

from validation.tools._ai_candidate_harness_parts.prompt_transport import (
    prompt_transport_contract,
)
from validation.tools._ai_candidate_harness_parts.provider_receipt import (
    invocation_contract,
)
from validation.tools._ai_candidate_harness_parts.provider_response import (
    session_ids_from_jsonl,
)

from .ledger_security import assert_no_secrets


SHA256 = re.compile(r"^[0-9a-f]{64}$")
MAX_RECEIPT_BYTES = 128_000
BASE_KEYS = {
    "schema_version", "source", "session_id", "provider_id", "model_id",
    "agent", "variant", "opencode_version", "resolved_model", "prompt_sha256",
    "raw_response_sha256", "session_ids", "prompt_transport", "invocation_contract",
}


def validate_project_invocation_receipt(
    receipt_path: Path, *, prompt_path: Path, response_path: Path,
    resolved_model: str, agent: str, variant: str, require_export: bool,
) -> dict[str, Any]:
    receipt = _json_file(receipt_path, "OpenCode invocation receipt")
    assert_no_secrets(receipt, "invocation_receipt")
    provider_id, model_id = resolved_model.split("/", 1)
    source = receipt.get("source")
    expected_keys = BASE_KEYS | (
        {"session_export_identity"} if source == "opencode-session-export" else set()
    )
    response = _read_file(response_path, MAX_RECEIPT_BYTES * 16)
    try:
        response_text = response.decode("utf-8")
    except UnicodeError as error:
        raise ValueError("OpenCode response is not UTF-8") from error
    session_ids = session_ids_from_jsonl(response_text)
    checks = (
        set(receipt) == expected_keys,
        receipt.get("schema_version") == 1,
        source in {"opencode-session-export", "runner-contract"},
        receipt.get("resolved_model") == resolved_model,
        receipt.get("provider_id") == provider_id,
        receipt.get("model_id") == model_id,
        receipt.get("agent") == agent,
        receipt.get("variant") == variant,
        isinstance(receipt.get("opencode_version"), str),
        bool(receipt.get("opencode_version")),
        len(str(receipt.get("opencode_version"))) <= 128,
        len(session_ids) == 1,
        receipt.get("session_id") == session_ids[0] if len(session_ids) == 1 else False,
        receipt.get("session_ids") == session_ids,
        receipt.get("prompt_sha256") == _sha256(prompt_path),
        receipt.get("raw_response_sha256") == hashlib.sha256(response).hexdigest(),
        receipt.get("prompt_transport") == prompt_transport_contract(),
        receipt.get("invocation_contract") == invocation_contract(
            resolved_model=resolved_model, agent=agent, variant=variant
        ),
    )
    if not all(checks):
        raise ValueError("OpenCode invocation receipt contract is invalid")
    if require_export and source != "opencode-session-export":
        raise ValueError("competition worker requires live session-export identity")
    session_reference = None
    if source == "opencode-session-export":
        session_reference = _validate_session_projection(
            receipt_path, receipt["session_export_identity"], receipt
        )
    return {
        "status": "verified" if source == "opencode-session-export" else "auxiliary-unattested",
        "source": source,
        "resolved_model": resolved_model,
        "session_identity": session_reference,
    }


def _validate_session_projection(
    receipt_path: Path, reference: Any, receipt: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(reference, dict) or set(reference) != {"path", "sha256"}:
        raise ValueError("OpenCode session identity reference is invalid")
    name = reference.get("path")
    digest = reference.get("sha256")
    if (
        not isinstance(name, str)
        or Path(name).name != name
        or not isinstance(digest, str)
        or SHA256.fullmatch(digest) is None
    ):
        raise ValueError("OpenCode session identity reference is unsafe")
    path = receipt_path.parent / name
    data = _read_file(path, MAX_RECEIPT_BYTES)
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("OpenCode session identity projection hash drifted")
    try:
        projection = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("OpenCode session identity projection is invalid") from error
    identity = projection.get("identity") if isinstance(projection, dict) else None
    fields = (
        "session_id", "provider_id", "model_id", "agent", "variant", "opencode_version",
    )
    if (
        not isinstance(projection, dict)
        or set(projection) != {
            "schema_version", "source", "session_export_sha256",
            "full_export_persisted", "identity",
        }
        or projection.get("schema_version") != 1
        or projection.get("source") != "opencode-session-export-identity-projection"
        or projection.get("full_export_persisted") is not False
        or not isinstance(projection.get("session_export_sha256"), str)
        or SHA256.fullmatch(projection["session_export_sha256"]) is None
        or not isinstance(identity, dict)
        or set(identity) != set(fields)
        or any(identity.get(field) != receipt.get(field) for field in fields)
    ):
        raise ValueError("OpenCode session identity projection does not match the receipt")
    assert_no_secrets(projection, "session_identity_projection")
    return {"path": path.name, "sha256": digest, "size_bytes": len(data)}


def _json_file(path: Path, label: str) -> dict[str, Any]:
    data = _read_file(path, MAX_RECEIPT_BYTES)
    try:
        payload = json.loads(data.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is invalid") from error
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be an object")
    return payload


def _read_file(path: Path, limit: int) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise ValueError("OpenCode evidence file is unavailable or unbounded")
    data = path.read_bytes()
    if len(data) > limit:
        raise ValueError("OpenCode evidence file exceeds its bound")
    return data


def _sha256(path: Path) -> str:
    return hashlib.sha256(_read_file(path, MAX_RECEIPT_BYTES * 16)).hexdigest()


__all__ = ["validate_project_invocation_receipt"]

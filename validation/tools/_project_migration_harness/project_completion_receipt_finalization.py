from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .artifacts import content_sha256
from .ledger_security import LedgerError


_KEYS = {
    "completion_epoch", "cohort_sha256", "generation_sha256",
    "gate_bundle_sha256", "invariant",
}


def finalization_payload(value: Mapping[str, Any]) -> dict[str, Any]:
    result = {key: value.get(key) for key in _KEYS}
    _validate(result)
    return result


def validate_receipt_finalization(
    receipt: Mapping[str, Any], expected: Mapping[str, Any] | None,
) -> None:
    value = receipt.get("finalization")
    _validate(value)
    if expected is not None and value != finalization_payload(expected):
        raise LedgerError("project completion receipt finalization binding drifted")


def _validate(value: Any) -> None:
    if not isinstance(value, Mapping) or set(value) != _KEYS:
        raise LedgerError("project completion finalization schema is invalid")
    epoch = value.get("completion_epoch")
    invariant = value.get("invariant")
    if (
        isinstance(epoch, bool) or not isinstance(epoch, int) or epoch < 1
        or not all(_sha(value.get(key)) for key in (
            "cohort_sha256", "generation_sha256", "gate_bundle_sha256",
        ))
        or not isinstance(invariant, Mapping)
        or set(invariant) != {"payload", "sha256"}
        or not isinstance(invariant.get("payload"), Mapping)
        or not _sha(invariant.get("sha256"))
        or content_sha256(invariant["payload"]) != invariant["sha256"]
    ):
        raise LedgerError("project completion finalization binding is invalid")


def _sha(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


__all__ = ["finalization_payload", "validate_receipt_finalization"]

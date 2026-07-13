from __future__ import annotations

import hashlib
import json

from .ledger_security import contains_secret_text
from .runtime_security import reject_forbidden_tool_events


def provider_response_for_persistence(
    stdout: str, *, max_bytes: int,
) -> tuple[str, str | None]:
    root_cause = None
    if len(stdout.encode("utf-8")) > max_bytes:
        root_cause = "provider_output_too_large"
    elif contains_secret_text(stdout):
        root_cause = "provider_secret_output"
    else:
        try:
            reject_forbidden_tool_events(stdout)
        except ValueError:
            root_cause = "provider_forbidden_tool_event"
    if root_cause is None:
        return stdout, None
    digest = hashlib.sha256(stdout.encode("utf-8")).hexdigest()
    redacted = json.dumps({
        "type": "error",
        "error": "provider_output_redacted",
        "root_cause_key": root_cause,
        "response_sha256": digest,
    }, sort_keys=True, separators=(",", ":")) + "\n"
    return redacted, root_cause


__all__ = ["provider_response_for_persistence"]

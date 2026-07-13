from __future__ import annotations

from collections.abc import Mapping
import hashlib
import json
from pathlib import Path
import subprocess

from .provider_response import session_ids_from_jsonl


def export_session_identity(
    argv: list[str], stdout: str, *,
    environment: Mapping[str, str] | None = None, cwd: Path | None = None,
) -> dict[str, str] | None:
    session_ids = session_ids_from_jsonl(stdout)
    if len(session_ids) != 1 or "run" not in argv:
        return None
    prefix = argv[: argv.index("run")]
    if not prefix:
        return None
    try:
        completed = subprocess.run(
            [*prefix, "export", session_ids[0]],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            env=dict(environment) if environment is not None else None,
            cwd=str(cwd) if cwd is not None else None,
        )
        payload = json.loads(completed.stdout) if completed.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    fields = parse_session_identity_export(payload, session_ids[0])
    if fields is None:
        return None
    return {
        **fields,
        "source": "opencode-session-export",
        "session_export_sha256": hashlib.sha256(
            completed.stdout.encode("utf-8")
        ).hexdigest(),
    }


def parse_session_identity_export(
    payload: object,
    expected_session_id: str,
) -> dict[str, str] | None:
    info = payload.get("info") if isinstance(payload, dict) else None
    model = info.get("model") if isinstance(info, dict) else None
    if (
        not isinstance(info, dict)
        or info.get("id") != expected_session_id
        or not isinstance(model, dict)
    ):
        return None
    fields = {
        "session_id": expected_session_id,
        "provider_id": model.get("providerID"),
        "model_id": model.get("id"),
        "agent": info.get("agent"),
        "variant": model.get("variant"),
        "opencode_version": info.get("version"),
    }
    return (
        fields
        if all(isinstance(value, str) and value for value in fields.values())
        else None
    )


__all__ = ["export_session_identity", "parse_session_identity_export"]

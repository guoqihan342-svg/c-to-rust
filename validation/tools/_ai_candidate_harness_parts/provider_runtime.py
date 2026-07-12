from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess

from .provider_response import contains_tool_event, text_fragments


MAX_PROVIDER_STDOUT_BYTES = 2_000_000
MAX_PROVIDER_STDERR_BYTES = 256_000
OPENCODE_LOG_PATH_ENV = "OPENCODE_LOG_PATH"
PROVIDER_BALANCE_SENTINEL = "provider_error=insufficient_balance"
PROVIDER_AUTH_SENTINEL = "provider_error=authentication_failed"
PROVIDER_INVOCATION_SENTINEL = "provider_error=invocation_failed"
EMPTY_COMPLETION_FAILURE_KIND = "provider_empty_completion"


@dataclass(frozen=True)
class ProviderExecution:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    identity_receipt: dict[str, str] | None = None


def classify_provider_failure(execution: ProviderExecution) -> dict[str, str] | None:
    combined = f"{execution.stderr}\n{execution.stdout}".lower()
    if (
        len(execution.stdout.encode("utf-8")) > MAX_PROVIDER_STDOUT_BYTES
        or len(execution.stderr.encode("utf-8")) > MAX_PROVIDER_STDERR_BYTES
    ):
        return {
            "kind": "provider_output_too_large",
            "message": "OpenCode output exceeded the bounded harness capture limit",
        }
    if (
        PROVIDER_BALANCE_SENTINEL in combined
        or "insufficient balance" in combined
        or "no resource package" in combined
    ):
        return {
            "kind": "provider_insufficient_balance",
            "message": "OpenCode provider balance or resource package is unavailable",
        }
    if (
        PROVIDER_AUTH_SENTINEL in combined
        or "unauthorized" in combined
        or "invalid api key" in combined
        or "authentication" in combined
    ):
        return {
            "kind": "provider_authentication_failed",
            "message": "OpenCode provider authentication failed",
        }
    if PROVIDER_INVOCATION_SENTINEL in combined:
        return {
            "kind": "provider_invocation_failed",
            "message": "OpenCode provider process could not be started",
        }
    if execution.timed_out:
        return {"kind": "provider_timeout", "message": "OpenCode candidate generation timed out"}
    if execution.returncode != 0:
        return {
            "kind": "opencode_failed",
            "message": f"OpenCode exited with code {execution.returncode}",
        }
    if is_retryable_empty_completion(execution.stdout):
        return {
            "kind": EMPTY_COMPLETION_FAILURE_KIND,
            "message": "OpenCode returned a terminal zero-token completion without assistant text",
        }
    return None


def is_retryable_empty_completion(stdout: str) -> bool:
    events: list[dict[str, object]] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            return False
        if not isinstance(event, dict):
            return False
        if contains_tool_event(event) or text_fragments(event):
            return False
        events.append(event)
    if not events:
        return False
    terminal = events[-1]
    part = terminal.get("part")
    if (
        terminal.get("type") != "step_finish"
        or not isinstance(part, dict)
        or part.get("type") != "step-finish"
    ):
        return False
    tokens = part.get("tokens")
    return bool(
        isinstance(tokens, dict)
        and _is_zero_token_count(tokens.get("output"))
        and _is_zero_token_count(tokens.get("reasoning"))
    )


def _is_zero_token_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 0


def subprocess_runner(argv: list[str], timeout_seconds: int) -> ProviderExecution:
    log_snapshot = snapshot_opencode_log(argv)
    try:
        completed = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except OSError:
        return ProviderExecution(
            returncode=127,
            stdout="",
            stderr=PROVIDER_INVOCATION_SENTINEL,
        )
    except subprocess.TimeoutExpired as error:
        stderr = append_provider_log_diagnostic(
            decode_timeout_output(error.stderr),
            log_snapshot,
        )
        return ProviderExecution(
            returncode=124,
            stdout=decode_timeout_output(error.stdout),
            stderr=stderr,
            timed_out=True,
        )
    stderr = completed.stderr
    if completed.returncode != 0:
        stderr = append_provider_log_diagnostic(stderr, log_snapshot)
    identity_receipt = (
        export_session_identity(argv, completed.stdout)
        if completed.returncode == 0
        else None
    )
    return ProviderExecution(
        completed.returncode,
        completed.stdout,
        stderr,
        identity_receipt=identity_receipt,
    )


def export_session_identity(argv: list[str], stdout: str) -> dict[str, str] | None:
    from .provider_response import session_ids_from_jsonl

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


def snapshot_opencode_log(argv: list[str]) -> tuple[Path, int, str, str, str] | None:
    try:
        model = argv[argv.index("--model") + 1]
        agent = argv[argv.index("--agent") + 1]
    except (ValueError, IndexError):
        return None
    if "/" not in model:
        return None
    provider_id, model_id = model.rsplit("/", 1)
    candidates = opencode_log_candidates()
    if not candidates:
        return None
    path = candidates[0]
    try:
        offset = path.stat().st_size
    except FileNotFoundError:
        offset = 0
    except OSError:
        return None
    return path, offset, provider_id, model_id, agent


def opencode_log_candidates() -> list[Path]:
    candidates: list[Path] = []
    override = os.environ.get(OPENCODE_LOG_PATH_ENV)
    if override:
        candidates.append(Path(override))
    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        candidates.append(Path(xdg_data_home) / "opencode" / "log" / "opencode.log")
    candidates.append(Path.home() / ".local" / "share" / "opencode" / "log" / "opencode.log")
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.append(Path(local_app_data) / "opencode" / "log" / "opencode.log")
    return candidates


def appended_provider_log_diagnostic(
    snapshot: tuple[Path, int, str, str, str] | None,
) -> str:
    if snapshot is None:
        return ""
    path, offset, provider_id, model_id, agent = snapshot
    try:
        with path.open("rb") as handle:
            if handle.seek(0, os.SEEK_END) < offset:
                return ""
            handle.seek(offset)
            appended = handle.read(MAX_PROVIDER_STDERR_BYTES)
    except OSError:
        return ""
    text = appended.decode("utf-8", errors="replace")
    matching = "\n".join(
        line
        for line in text.splitlines()
        if f"providerID={provider_id}" in line
        and f"modelID={model_id}" in line
        and f"agent={agent}" in line
    ).lower()
    if "insufficient balance" in matching or "no resource package" in matching:
        return PROVIDER_BALANCE_SENTINEL
    if (
        "unauthorized" in matching
        or "invalid api key" in matching
        or "authentication" in matching
    ):
        return PROVIDER_AUTH_SENTINEL
    return ""


def append_provider_log_diagnostic(
    stderr: str,
    snapshot: tuple[Path, int, str, str, str] | None,
) -> str:
    diagnostic = appended_provider_log_diagnostic(snapshot)
    if not diagnostic or diagnostic in stderr:
        return stderr
    return "\n".join(part for part in (stderr, diagnostic) if part)


def decode_timeout_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value


__all__ = [
    "MAX_PROVIDER_STDERR_BYTES",
    "MAX_PROVIDER_STDOUT_BYTES",
    "OPENCODE_LOG_PATH_ENV",
    "PROVIDER_AUTH_SENTINEL",
    "PROVIDER_BALANCE_SENTINEL",
    "PROVIDER_INVOCATION_SENTINEL",
    "EMPTY_COMPLETION_FAILURE_KIND",
    "ProviderExecution",
    "append_provider_log_diagnostic",
    "appended_provider_log_diagnostic",
    "classify_provider_failure",
    "decode_timeout_output",
    "export_session_identity",
    "is_retryable_empty_completion",
    "opencode_log_candidates",
    "parse_session_identity_export",
    "snapshot_opencode_log",
    "subprocess",
    "subprocess_runner",
]

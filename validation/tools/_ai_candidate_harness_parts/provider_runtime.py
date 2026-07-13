from __future__ import annotations

import json

from .provider_process import (
    MAX_PROVIDER_STDERR_BYTES,
    MAX_PROVIDER_STDOUT_BYTES,
    OPENCODE_LOG_PATH_ENV,
    PROVIDER_AUTH_SENTINEL,
    PROVIDER_BALANCE_SENTINEL,
    PROVIDER_INVOCATION_SENTINEL,
    ProviderExecution,
    append_provider_log_diagnostic,
    appended_provider_log_diagnostic,
    decode_timeout_output,
    export_session_identity,
    opencode_log_candidates,
    parse_session_identity_export,
    snapshot_opencode_log,
    subprocess,
    subprocess_runner,
    subprocess_runner_with_environment,
)
from .provider_response import contains_tool_event, text_fragments


EMPTY_COMPLETION_FAILURE_KIND = "provider_empty_completion"


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
    "subprocess_runner_with_environment",
]

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .context import atomic_write_bytes, sha256_path
from .provider_receipt import write_invocation_receipt
from .provider_runtime import (
    EMPTY_COMPLETION_FAILURE_KIND,
    MAX_PROVIDER_STDOUT_BYTES,
    ProviderExecution,
    classify_provider_failure,
)


EMPTY_COMPLETION_RETRY_REASON = "provider_empty_completion_retry"
Runner = Callable[[list[str], int], ProviderExecution]


@dataclass(frozen=True)
class ProviderAttempt:
    attempt_index: int
    reason: str
    execution: ProviderExecution
    response_path: Path
    receipt_path: Path
    session_identity_path: Path

    def binding(self) -> dict[str, object]:
        binding: dict[str, object] = {
            "attempt_index": self.attempt_index,
            "reason": self.reason,
            "raw_response": {
                "path": self.response_path.name,
                "sha256": sha256_path(self.response_path),
            },
            "invocation_receipt": {
                "path": self.receipt_path.name,
                "sha256": sha256_path(self.receipt_path),
            },
        }
        if self.session_identity_path.is_file():
            binding["session_export_identity"] = {
                "path": self.session_identity_path.name,
                "sha256": sha256_path(self.session_identity_path),
            }
        return binding


@dataclass(frozen=True)
class ProviderRetryResult:
    attempts: tuple[ProviderAttempt, ...]

    @property
    def final_attempt(self) -> ProviderAttempt:
        return self.attempts[-1]

    @property
    def provider_invocations(self) -> int:
        return len(self.attempts)

    def attempt_bindings(self) -> list[dict[str, object]]:
        return [attempt.binding() for attempt in self.attempts]

    def retry_record(self, *, result: str) -> dict[str, object] | None:
        if len(self.attempts) != 2:
            return None
        return {
            "schema_version": 1,
            "trigger": EMPTY_COMPLETION_FAILURE_KIND,
            "max_retries": 1,
            "initial_attempt": 1,
            "retry_attempt": 2,
            "result": result,
            "semantic_gate": False,
        }


def has_retryable_empty_completion_fingerprint(execution: ProviderExecution) -> bool:
    failure = classify_provider_failure(execution)
    return bool(
        isinstance(failure, dict)
        and failure.get("kind") == EMPTY_COMPLETION_FAILURE_KIND
    )


def run_with_empty_completion_retry(
    argv: list[str],
    timeout_seconds: int,
    runner: Runner,
    *,
    resolved_model: str,
    agent: str,
    variant: str,
    prompt_path: Path,
    response_path: Path,
    receipt_path: Path,
    session_identity_path: Path,
) -> ProviderRetryResult:
    stable_argv = tuple(argv)
    first_execution = runner(list(stable_argv), timeout_seconds)
    first = _persist_attempt(
        1,
        "initial",
        first_execution,
        resolved_model=resolved_model,
        agent=agent,
        variant=variant,
        prompt_path=prompt_path,
        response_path=response_path,
        receipt_path=receipt_path,
        session_identity_path=session_identity_path,
    )
    if not has_retryable_empty_completion_fingerprint(first_execution):
        return ProviderRetryResult((first,))

    second_execution = runner(list(stable_argv), timeout_seconds)
    second = _persist_attempt(
        2,
        EMPTY_COMPLETION_RETRY_REASON,
        second_execution,
        resolved_model=resolved_model,
        agent=agent,
        variant=variant,
        prompt_path=prompt_path,
        response_path=response_path.with_name(
            f"{response_path.stem}-retry-1{response_path.suffix}"
        ),
        receipt_path=receipt_path.with_name(
            f"{receipt_path.stem}-retry-1{receipt_path.suffix}"
        ),
        session_identity_path=session_identity_path.with_name(
            f"{session_identity_path.stem}-retry-1{session_identity_path.suffix}"
        ),
    )
    return ProviderRetryResult((first, second))


def _persist_attempt(
    attempt_index: int,
    reason: str,
    execution: ProviderExecution,
    *,
    resolved_model: str,
    agent: str,
    variant: str,
    prompt_path: Path,
    response_path: Path,
    receipt_path: Path,
    session_identity_path: Path,
) -> ProviderAttempt:
    response_bytes = execution.stdout.encode("utf-8")
    atomic_write_bytes(response_path, response_bytes[:MAX_PROVIDER_STDOUT_BYTES])
    persisted_response = response_path.read_text(encoding="utf-8", errors="replace")
    write_invocation_receipt(
        execution,
        resolved_model=resolved_model,
        agent=agent,
        variant=variant,
        persisted_response=persisted_response,
        prompt_path=prompt_path,
        response_path=response_path,
        receipt_path=receipt_path,
        session_identity_path=session_identity_path,
    )
    return ProviderAttempt(
        attempt_index,
        reason,
        execution,
        response_path,
        receipt_path,
        session_identity_path,
    )


__all__ = [
    "EMPTY_COMPLETION_FAILURE_KIND",
    "EMPTY_COMPLETION_RETRY_REASON",
    "ProviderAttempt",
    "ProviderRetryResult",
    "has_retryable_empty_completion_fingerprint",
    "run_with_empty_completion_retry",
]

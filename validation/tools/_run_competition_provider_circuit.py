from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


DEFAULT_SHARED_FAILURE_KINDS = frozenset(
    {
        "provider_invocation_failed",
        "provider_timeout",
        "provider_unavailable",
    }
)


class ProviderCircuit:
    """Track consecutive provider-wide failures across competition units."""

    def __init__(
        self,
        *,
        threshold: int = 2,
        shared_failure_kinds: Iterable[str] = DEFAULT_SHARED_FAILURE_KINDS,
    ) -> None:
        if isinstance(threshold, bool) or not isinstance(threshold, int) or threshold < 1:
            raise ValueError("threshold must be a positive integer")
        kinds = frozenset(shared_failure_kinds)
        if not kinds or not all(isinstance(kind, str) and kind for kind in kinds):
            raise ValueError("shared_failure_kinds must contain non-empty strings")

        self._threshold = threshold
        self._shared_failure_kinds = kinds
        self._status = "closed"
        self._failure_kind: str | None = None
        self._observations: list[dict[str, str]] = []
        self._requested_slice_specs = 0
        self._attempted_slice_specs = 0
        self._skipped_slice_specs = 0

    @property
    def is_open(self) -> bool:
        return self._status == "open"

    def request(self, unit_id: str) -> bool:
        """Register a requested unit and return whether its provider call may run."""
        self._validate_unit_id(unit_id)
        self._requested_slice_specs += 1
        if self.is_open:
            self._skipped_slice_specs += 1
            return False
        self._attempted_slice_specs += 1
        return True

    def observe_manifest(self, unit_id: str, manifest_path: str | Path) -> None:
        """Update the circuit from one attempted unit's AI candidate manifest."""
        self._validate_unit_id(unit_id)
        if self.is_open:
            return

        failure_kind = self._blocked_failure_kind(Path(manifest_path))
        if failure_kind not in self._shared_failure_kinds:
            self._reset_consecutive_failures()
            return

        self._observations.append(
            {
                "unit_id": unit_id,
                "failure_kind": failure_kind,
            }
        )
        if len(self._observations) >= self._threshold:
            self._status = "open"
            self._failure_kind = failure_kind

    def summary(self) -> dict[str, Any]:
        """Return a stable, JSON-serializable circuit summary."""
        return {
            "status": self._status,
            "threshold": self._threshold,
            "consecutive_failures": len(self._observations),
            "failure_kind": self._failure_kind if self.is_open else None,
            "requested_slice_specs": self._requested_slice_specs,
            "attempted_slice_specs": self._attempted_slice_specs,
            "skipped_slice_specs": self._skipped_slice_specs,
            "observations": [dict(item) for item in self._observations],
        }

    def _reset_consecutive_failures(self) -> None:
        self._observations.clear()
        self._failure_kind = None

    @staticmethod
    def _blocked_failure_kind(manifest_path: Path) -> str | None:
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if not isinstance(manifest, dict) or manifest.get("status") != "blocked":
            return None
        failure = manifest.get("failure")
        if not isinstance(failure, dict):
            return None
        kind = failure.get("kind")
        return kind if isinstance(kind, str) and kind else None

    @staticmethod
    def _validate_unit_id(unit_id: str) -> None:
        if not isinstance(unit_id, str) or not unit_id:
            raise ValueError("unit_id must be a non-empty string")

from __future__ import annotations

import hashlib
from pathlib import Path
import sys
from typing import Any

from .ledger_security import LedgerError
from .sandbox_contract import canonical_sha256


SEMANTIC_FAMILIES = frozenset({
    "oracle-replay-diff", "negative", "unsafe-alias", "abi-layout",
})
FIXED_TIMEOUT_SECONDS = 300
MAX_ADAPTER_OUTPUT_BYTES = 1024 * 1024
MAX_OBSERVATION_COUNT = 1_000_000
FIXED_RESOURCE_LIMITS = {
    "cpu_seconds": 300,
    "address_space_bytes": 2 * 1024 * 1024 * 1024,
    "file_size_bytes": 512 * 1024 * 1024,
    "process_count": 64,
    "open_files": 128,
}
_ADAPTER_SOURCES = (
    "candidate_semantic_backend.py",
    "candidate_semantic_backend_contract.py",
    "candidate_semantic_backend_inputs.py",
    "candidate_semantic_backend_project.py",
    "candidate_semantic_backend_sandbox.py",
    "candidate_semantic_stimuli.py",
    "candidate_semantic_plan.py",
    "candidate_semantic_runners.py",
)


def fixed_adapter_plan(gate_family: str) -> dict[str, Any]:
    require_semantic_family(gate_family)
    launcher = Path(sys.executable).resolve(strict=True)
    command = [
        launcher.name, "-E", "-s", "-B", "-m",
        "validation.tools._project_migration_harness.candidate_semantic_runners",
        "--adapter-worker", gate_family,
    ]
    launcher_argv = [str(launcher), *command[1:]]
    return {
        "schema_version": 1,
        "adapter_id": f"host.candidate.semantic.{gate_family}.v1",
        "protocol": "candidate-semantic-raw-json-v1",
        "gate_family": gate_family,
        "command": command,
        "command_sha256": canonical_sha256(command),
        "launcher_argv_sha256": canonical_sha256(launcher_argv),
        "adapter_source_sha256": _adapter_source_sha256(),
        "launcher_sha256": _file_sha256(launcher),
        "timeout_seconds": FIXED_TIMEOUT_SECONDS,
        "resource_limits": dict(FIXED_RESOURCE_LIMITS),
        "max_stdout_bytes": MAX_ADAPTER_OUTPUT_BYTES,
        "max_stderr_bytes": MAX_ADAPTER_OUTPUT_BYTES,
        "shell": False,
    }


def require_semantic_family(value: str) -> None:
    if value not in SEMANTIC_FAMILIES:
        raise LedgerError("candidate semantic gate family is invalid")


def _adapter_source_sha256() -> str:
    root = Path(__file__).resolve(strict=True).parent
    bindings = []
    for name in _ADAPTER_SOURCES:
        path = root / name
        bindings.append({"path": name, "sha256": _file_sha256(path)})
    return canonical_sha256(bindings)


def _file_sha256(path: Path) -> str:
    if not path.is_file() or path.stat().st_size > 64 * 1024 * 1024:
        raise LedgerError("candidate semantic adapter executable is invalid")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "FIXED_RESOURCE_LIMITS", "FIXED_TIMEOUT_SECONDS",
    "MAX_ADAPTER_OUTPUT_BYTES", "MAX_OBSERVATION_COUNT",
    "SEMANTIC_FAMILIES", "fixed_adapter_plan", "require_semantic_family",
]

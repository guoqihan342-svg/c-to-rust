from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess

from validation.tools._project_migration_harness import integration
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract,
    SandboxRunResult,
    canonical_sha256,
)


class BoundBackend:
    def __init__(self, *, tamper_contract: bool = False) -> None:
        self.contract = SandboxContract(
            backend="bubblewrap-v1",
            launcher_sha256="1" * 64,
            toolchain_sha256="2" * 64,
            cpu_seconds=60,
        )
        self.tamper_contract = tamper_contract
        self.calls: list[dict[str, object]] = []

    def execute(
        self,
        cargo_binary: Path,
        cargo_args: list[str],
        *,
        project_root: Path,
        runtime_root: Path,
        timeout_seconds: int,
    ) -> SandboxRunResult:
        command = ["cargo", *cargo_args]
        self.calls.append({
            "cargo_binary": cargo_binary,
            "cargo_args": list(cargo_args),
            "project_root": project_root,
            "runtime_root": runtime_root,
            "timeout_seconds": timeout_seconds,
        })
        return SandboxRunResult(
            completed=subprocess.CompletedProcess(command, 0, "", ""),
            contract_sha256=(
                "0" * 64 if self.tamper_contract else self.contract.sha256
            ),
            command_sha256=canonical_sha256(command),
            command_started=True,
            launcher_argv_sha256="3" * 64,
        )


def managed_project(root: Path) -> tuple[Path, Path]:
    candidates = root / "candidates"
    candidates.mkdir()
    source = b"pub fn bounded_value() -> i32 { 7 }\n"
    source_path = candidates / "unit.rs"
    source_path.write_bytes(source)
    descriptor = {
        "group_id": "bounded-unit",
        "status": "accepted",
        "source_path": "unit.rs",
        "sha256": hashlib.sha256(source).hexdigest(),
        "public_symbols": ["bounded_value"],
        "required_symbols": [],
        "unsafe_count": 0,
    }
    project = root / "project"
    result = integration.integrate_candidates(
        {"dag": {"bounded-unit": []}}, [descriptor], candidates, project,
    )
    if result["status"] != "integrated":
        raise AssertionError(result)
    tools = root / "tools"
    tools.mkdir()
    cargo = tools / "cargo"
    cargo.write_bytes(b"host-owned-test-cargo")
    return project, cargo


def triples(values: list[str]) -> list[list[str]]:
    return [values[index:index + 3] for index in range(len(values) - 2)]


def executable(path: Path, content: bytes) -> Path:
    path.write_bytes(content)
    path.chmod(0o755)
    return path


def toolchain(root: Path, version: str) -> dict[str, Path]:
    binary_root = root / "bin"
    binary_root.mkdir(parents=True)
    library_root = root / "lib"
    library_root.mkdir()
    (library_root / "libstd.rlib").write_bytes(
        f"{version}-library".encode("ascii")
    )
    return {
        name: executable(binary_root / name, f"{version}-{name}".encode("ascii"))
        for name in ("cargo", "rustc", "rustdoc")
    }


__all__ = ["BoundBackend", "executable", "managed_project", "toolchain", "triples"]

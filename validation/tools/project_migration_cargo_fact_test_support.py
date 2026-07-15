from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxRunResult,
)
from validation.tools._project_migration_harness.sandbox_requirements import (
    SandboxVerificationPlan,
)
from validation.tools.project_migration_sandbox_test_support import BoundBackend


PACKAGE_ID = "path+file:///workspace#fixture@0.1.0"


def cargo_metadata_stdout() -> bytes:
    payload = {
        "packages": [{
            "id": PACKAGE_ID,
            "name": "fixture",
            "version": "0.1.0",
            "features": {"default": []},
            "targets": [{
                "name": "fixture",
                "kind": ["lib"],
                "crate_types": ["lib"],
                "required-features": [],
            }],
        }],
        "workspace_members": [PACKAGE_ID],
        "workspace_default_members": [PACKAGE_ID],
        "resolve": None,
        "target_directory": "/runtime/target",
        "build_directory": "/runtime/target/build",
        "version": 1,
        "workspace_root": "/workspace",
        "metadata": None,
    }
    return json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def cargo_check_stdout() -> bytes:
    artifact = {
        "reason": "compiler-artifact",
        "package_id": PACKAGE_ID,
        "manifest_path": "/workspace/Cargo.toml",
        "target": {
            "kind": ["lib"],
            "crate_types": ["lib"],
            "name": "fixture",
            "src_path": "/workspace/src/lib.rs",
            "edition": "2021",
            "doc": True,
            "doctest": True,
            "test": True,
        },
        "profile": {
            "opt_level": "0",
            "debuginfo": 2,
            "debug_assertions": True,
            "overflow_checks": True,
            "test": False,
        },
        "features": [],
        "filenames": ["/runtime/target/debug/deps/libfixture.rmeta"],
        "executable": None,
        "fresh": False,
    }
    finished = {"reason": "build-finished", "success": True}
    return (
        json.dumps(artifact, sort_keys=True, separators=(",", ":"))
        + "\n"
        + json.dumps(finished, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


class CargoFactBackend(BoundBackend):
    def __init__(self, *, fail_stage: str | None = None) -> None:
        super().__init__()
        self.fail_stage = fail_stage

    def execute(
        self, cargo_binary: Path, cargo_args: list[str], *,
        project_root: Path, runtime_root: Path,
        verification_plan: SandboxVerificationPlan, probe_receipt: object,
    ) -> SandboxRunResult:
        result = super().execute(
            cargo_binary, cargo_args,
            project_root=project_root,
            runtime_root=runtime_root,
            verification_plan=verification_plan,
            probe_receipt=probe_receipt,
        )
        stage = cargo_args[0]
        stdout = (
            cargo_metadata_stdout()
            if stage == "metadata" else cargo_check_stdout()
        )
        returncode = 1 if stage == self.fail_stage else 0
        if returncode:
            stdout = b""
        completed = subprocess.CompletedProcess(
            ["cargo", *cargo_args], returncode, stdout,
            b"fixture compile failure\n" if returncode else b"",
        )
        return replace(result, completed=completed)


__all__ = [
    "CargoFactBackend", "PACKAGE_ID", "cargo_check_stdout",
    "cargo_metadata_stdout",
]

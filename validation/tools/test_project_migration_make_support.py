from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes, content_sha256,
)
from validation.tools._project_migration_harness.build_facts import file_binding
from validation.tools._project_migration_harness.make_build_ir_adapter import (
    MakeReportSelection,
)
from validation.tools._project_migration_harness.make_dry_run_contract import (
    canonical_make_dry_run_report_bytes, create_make_dry_run_report,
)
from validation.tools._project_migration_harness.make_dry_run_host_evidence import (
    MAKE_REQUIRED_CAPABILITIES, canonical_make_host_preflight_bytes,
)
from validation.tools._project_migration_harness.make_dry_run_runner import (
    MakeDryRunExecution, MakeDryRunPreflight,
    canonical_make_dry_run_plan_bytes, create_make_dry_run_plan,
    run_make_dry_run,
)
from validation.tools._project_migration_harness.project_test_target_proposal import (
    ProjectTestTargetProposalSelection,
)


class ControlledMakeBackend:
    def __init__(
        self, preflight: MakeDryRunPreflight, execution: MakeDryRunExecution,
    ) -> None:
        self.preflight_value = preflight
        self.execution_value = execution

    def preflight(self, plan, *, project_root, runtime_root):
        return self.preflight_value

    def execute(
        self, make_binary, make_args, *, project_root, runtime_root,
        plan, preflight,
    ):
        return self.execution_value


class ControlledCollectorBackend:
    def __init__(self, toolchain_sha256: str, stdout: bytes) -> None:
        self.toolchain_sha256 = toolchain_sha256
        self.stdout = stdout
        self.preflight_calls = 0
        self.execute_calls = 0

    def preflight(self, plan, *, project_root, runtime_root):
        self.preflight_calls += 1
        return MakeDryRunPreflight(
            backend="controlled-collector-backend",
            backend_version="test-1",
            plan_sha256=plan["plan_sha256"],
            toolchain_sha256=self.toolchain_sha256,
            launcher_sha256="1" * 64,
            make_sha256="2" * 64,
            probe_observation_sha256="3" * 64,
            capability_results=tuple(
                (name, True) for name in MAKE_REQUIRED_CAPABILITIES
            ),
            cleanup_ready=True,
        )

    def execute(
        self, make_binary, make_args, *, project_root, runtime_root,
        plan, preflight,
    ):
        self.execute_calls += 1
        return MakeDryRunExecution(
            stdout=self.stdout,
            stderr=b"",
            returncode=0,
            timed_out=False,
            command_started=True,
            cleanup_verified=True,
            plan_sha256=plan["plan_sha256"],
            command_sha256=content_sha256(plan["command"]),
        )


def artifact_ref(path: str, data: bytes) -> dict[str, Any]:
    return {
        "path": path,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def controlled_success(
    plan: dict[str, Any], toolchain_ref: dict[str, Any], stdout: bytes,
    stderr: bytes, *, sandbox_path: str,
) -> tuple[Any, dict[str, Any], bytes]:
    preflight = MakeDryRunPreflight(
        backend="controlled-test-backend",
        backend_version="test-1",
        plan_sha256=plan["plan_sha256"],
        toolchain_sha256=toolchain_ref["sha256"],
        launcher_sha256="1" * 64,
        make_sha256="2" * 64,
        probe_observation_sha256="3" * 64,
        capability_results=tuple(
            (name, True) for name in MAKE_REQUIRED_CAPABILITIES
        ),
        cleanup_ready=True,
    )
    sandbox_bytes = canonical_make_host_preflight_bytes(preflight.payload())
    sandbox_ref = artifact_ref(sandbox_path, sandbox_bytes)
    execution = MakeDryRunExecution(
        stdout=stdout,
        stderr=stderr,
        returncode=0,
        timed_out=False,
        command_started=True,
        cleanup_verified=True,
        plan_sha256=plan["plan_sha256"],
        command_sha256=content_sha256(plan["command"]),
    )
    outcome = run_make_dry_run(
        plan,
        project_root=Path("."),
        runtime_root=Path("target/test-make-runtime"),
        make_binary=Path("make"),
        toolchain_ref=toolchain_ref,
        sandbox_ref=sandbox_ref,
        backend=ControlledMakeBackend(preflight, execution),
    )
    if outcome.status != "ready":
        raise AssertionError(outcome)
    return outcome, sandbox_ref, sandbox_bytes


class MakeBundleFactory:
    def __init__(self, base: Path) -> None:
        self.base = base

    def build(self, name: str, *, compile_database: bool = False) -> dict[str, Any]:
        root = self.base / name / "project"
        harness = self.base / name / "harness"
        root.mkdir(parents=True)
        harness.mkdir()
        self.write(root, "src/unit.c", "int unit(void) { return 7; }\n")
        self.write_bytes(root, "vendor/prebuilt.a", b"bounded-test-input\n")
        self.write(root, "Makefile", self.makefile())
        toolchain_payload = {
            "schema_version": 1,
            "artifact_kind": "project-migration-make-toolchain-evidence",
            "status": "recorded",
            "tools": ["clang", "llvm-ar", "llvm-ranlib"],
            "claim_boundary": {
                "identity": "hash-bound-evidence-only",
                "version_verified": False,
                "target_verified": False,
                "sysroot_verified": False,
            },
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        }
        self.write_bytes(
            root, "evidence/toolchain.json", canonical_json_bytes(toolchain_payload),
        )
        stdout = self.stdout()
        stderr = b""
        stdout_relative = (
            "evidence/cas/raw-stdout/"
            f"{hashlib.sha256(stdout).hexdigest()}.bin"
        )
        stderr_relative = (
            "evidence/cas/raw-stderr/"
            f"{hashlib.sha256(stderr).hexdigest()}.bin"
        )
        self.write_bytes(root, stdout_relative, stdout)
        self.write_bytes(root, stderr_relative, stderr)
        makefile = file_binding(root, root / "Makefile")
        source = file_binding(root, root / "src/unit.c")
        prebuilt = file_binding(root, root / "vendor/prebuilt.a")
        toolchain = file_binding(root, root / "evidence/toolchain.json")
        plan = create_make_dry_run_plan(
            makefile_ref=makefile, input_refs=[source, prebuilt],
            toolchain_ref=toolchain,
            targets=["all"], timeout_seconds=30,
        )
        plan_path = self.write_bytes(
            root, "evidence/make-plan.json", canonical_make_dry_run_plan_bytes(plan),
        )
        outcome, expected_sandbox, sandbox_bytes = controlled_success(
            plan, toolchain, stdout, stderr, sandbox_path="evidence/sandbox.json",
        )
        sandbox_path = self.write_bytes(
            root, "evidence/sandbox.json", sandbox_bytes,
        )
        sandbox = file_binding(root, sandbox_path)
        if sandbox != expected_sandbox:
            raise AssertionError("controlled sandbox binding drift")
        report = create_make_dry_run_report(
            outcome=outcome,
            raw_stdout_ref=file_binding(root, root / stdout_relative),
            raw_stderr_ref=file_binding(root, root / stderr_relative),
            makefile_ref=makefile, source_refs=[source],
            input_refs=[source, prebuilt],
            toolchain_ref=toolchain, sandbox_ref=sandbox,
            execution_plan_ref=file_binding(root, plan_path), targets=["all"],
        )
        report_path = self.write_bytes(
            root, "evidence/make-report.json",
            canonical_make_dry_run_report_bytes(report),
        )
        report_ref = file_binding(root, report_path)
        if compile_database:
            self.write(root, "compile_commands.json", json.dumps([{
                "directory": ".", "file": "src/unit.c",
                "arguments": [
                    "clang", "-std=c11", "-c", "src/unit.c",
                    "-o", "build/unit.o",
                ],
                "output": "build/unit.o",
            }]) + "\n")
        return {
            "root": root, "harness": harness,
            "stdout_relative": stdout_relative,
            "stderr_relative": stderr_relative,
            "selection": MakeReportSelection(
                report_path, report_ref["sha256"], report_ref["size_bytes"],
            ),
        }

    @staticmethod
    def stdout() -> bytes:
        return "\n".join((
            "clang -std=c11 -c src/unit.c -o build/unit.o",
            "llvm-ar rcs build/libunit.a build/unit.o",
            "llvm-ranlib build/libunit.a",
            "clang build/unit.o vendor/prebuilt.a -Lbuild -lunit -o build/program",
            "",
        )).encode("utf-8")

    @staticmethod
    def makefile() -> str:
        return (
            "all: build/program\n\n"
            "build/unit.o: src/unit.c\n"
            "\tclang -std=c11 -c src/unit.c -o build/unit.o\n\n"
            "build/libunit.a: build/unit.o\n"
            "\tllvm-ar rcs build/libunit.a build/unit.o\n"
            "\tllvm-ranlib build/libunit.a\n\n"
            "build/program: build/unit.o build/libunit.a vendor/prebuilt.a\n"
            "\tclang build/unit.o vendor/prebuilt.a -Lbuild -lunit -o build/program\n"
        )

    @staticmethod
    def write(root: Path, relative: str, content: str) -> Path:
        return MakeBundleFactory.write_bytes(root, relative, content.encode("utf-8"))

    @staticmethod
    def write_bytes(root: Path, relative: str, content: bytes) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path


def make_test_target_proposal(
    harness_root: Path, target: str = "all",
) -> ProjectTestTargetProposalSelection:
    payload = {
        "schema_version": 1,
        "artifact_kind": "project-test-target-proposal-v1",
        "build_system": "make", "target": target,
        "producer": {
            "kind": "ai-candidate", "provider": "test-provider",
            "model": "test-model", "prompt_sha256": "a" * 64,
            "response_sha256": "b" * 64,
        },
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    }
    data = canonical_json_bytes(payload)
    path = MakeBundleFactory.write_bytes(
        harness_root, "evidence/project-test-target-proposal.json", data,
    )
    return ProjectTestTargetProposalSelection(
        path, hashlib.sha256(data).hexdigest(), len(data),
    )


__all__ = [
    "ControlledCollectorBackend", "MakeBundleFactory", "artifact_ref",
    "controlled_success", "make_test_target_proposal",
]

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from typing import Any

from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes,
    content_sha256,
)
from validation.tools._project_migration_harness.build_ir_host_toolchains import (
    HostToolchainProjection,
)
from validation.tools._project_migration_harness.build_ir_projection import (
    project_build_ir,
)
from validation.tools._project_migration_harness.link_closure_schema import (
    LINK_CLOSURE_SCHEMA_VERSION,
)
from validation.tools._project_migration_harness.c_toolchain_probe import (
    ProbeExecution,
)
from validation.tools._project_migration_harness.c_toolchain_reopen import (
    C_TOOLCHAIN_RAW_ROLE,
    collect_c_toolchain_evidence,
)
from validation.tools._project_migration_harness.c_toolchain_test_support import (
    FakeToolchain,
)


class ContractToolchain(FakeToolchain):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        suffix = ".exe" if os.name == "nt" else ""
        self.paths["ranlib"] = self._executable(
            root / "ranlib" / f"ranlib{suffix}", b"ranlib",
        )

    def runner(
        self, argv: list[str], **kwargs: object,
    ) -> subprocess.CompletedProcess[bytes] | ProbeExecution:
        if Path(argv[0]).stem.lower() == "ranlib":
            self.calls.append(list(argv))
            return subprocess.CompletedProcess(
                argv, 0, b"GNU ranlib 2.42\n", b"",
            )
        return super().runner(argv, **kwargs)


def binding(path: str, data: bytes) -> dict[str, Any]:
    return {
        "path": path,
        "kind": "file",
        "materialized": True,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
    }


def artifact_reference(path: str, payload: Any) -> dict[str, Any]:
    encoded = canonical_json_bytes(payload)
    return {
        "path": path,
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "size_bytes": len(encoded),
    }


def command(
    ordinal: int,
    kind: str,
    argv: list[str],
    inputs: list[str],
    outputs: list[str],
) -> dict[str, Any]:
    return {
        "ordinal": ordinal,
        "kind": kind,
        "tool": argv[0],
        "argv": argv,
        "argv_sha256": content_sha256(argv),
        "inputs": inputs,
        "outputs": outputs,
    }


class BuildIRHostBindingTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="build-ir-host-binding-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project_root = self.root / "project"
        (self.project_root / "src").mkdir(parents=True)
        self.source_bytes = b"int unit(void) { return 0; }\n"
        (self.project_root / "src" / "unit.c").write_bytes(self.source_bytes)
        self.makefile_bytes = b"all:\n\t@true\n"
        (self.project_root / "Makefile").write_bytes(self.makefile_bytes)
        self.fake = ContractToolchain(self.root / "tools")
        self.environment = {"PATH": str(self.root / "path"), "LC_ALL": "C"}

    def collect(
        self,
        requests: list[dict[str, Any]],
        fake: ContractToolchain | None = None,
    ) -> dict[str, Any]:
        selected = fake or self.fake
        return collect_c_toolchain_evidence(
            requests,
            profile="development",
            environment=self.environment,
            resolver=selected.resolver,
            runner=selected.runner,
        )

    def full_evidence(self) -> dict[str, Any]:
        return self.collect([
            {"token": "ar", "roles": ["archiver"]},
            {"token": "distcc", "roles": ["compiler-wrapper"]},
            {
                "token": "gcc",
                "roles": ["compiler-driver", "linker-driver"],
            },
            {"token": "ranlib", "roles": ["ranlib"]},
        ])

    @staticmethod
    def _exercise_projection(
        projector: HostToolchainProjection,
    ) -> dict[str, str]:
        return {
            "compile": projector.compile("gcc", ["distcc"], "c"),
            "linker-driver": projector.command("gcc", "linker-driver"),
            "linker": projector.command("ld", "linker"),
            "archiver": projector.command("ar", "archiver"),
            "ranlib": projector.command("ranlib", "ranlib"),
        }

    @staticmethod
    def _target_tool(
        target: dict[str, Any], records: dict[str, dict[str, Any]],
    ) -> tuple[str, str]:
        record = records[target["toolchain_id"]]
        return record["driver"], record["role"]

    @staticmethod
    def _claim_boundary(build_ir: dict[str, Any]) -> tuple[Any, ...]:
        boundary = build_ir["claim_boundary"]
        return (
            boundary["host_toolchain_bound"],
            boundary["toolchain_profile"],
            boundary["semantic_gate"],
            boundary["translation_coverage_numerator"],
        )

    def standard_build_ir(self) -> dict[str, Any]:
        source = binding("src/unit.c", self.source_bytes)
        object_output = binding("build/unit.o", b"object")
        archive_output = binding("build/libunit.a", b"archive")
        link_output = binding("build/program", b"program")
        closure = {
            "status": "ready",
            "compile_outputs": [object_output],
            "target_link_closure": {
                "schema_version": LINK_CLOSURE_SCHEMA_VERSION,
                "targets": [
                    {
                        "output": archive_output,
                        "inputs": [object_output],
                        "search_roots": [],
                        "driver": "ar",
                        "archive_operation": "create",
                        "ranlib_drivers": ["ranlib"],
                        "ordered_system_link_args": [],
                        "ordered_link_occurrences": [{
                            "ordinal": 0, "argument_index": 1,
                            "argument_count": 1, "kind": "input",
                            "reference_ordinal": 0,
                        }],
                    },
                    {
                        "output": link_output,
                        "inputs": [object_output],
                        "search_roots": [],
                        "driver": "gcc",
                        "ordered_system_link_args": ["-lm"],
                        "ordered_link_occurrences": [
                            {
                                "ordinal": 0, "argument_index": 0,
                                "argument_count": 1, "kind": "input",
                                "reference_ordinal": 0,
                            },
                            {
                                "ordinal": 1, "argument_index": 1,
                                "argument_count": 1,
                                "kind": "system-argument",
                                "reference_ordinal": 0,
                            },
                        ],
                    },
                ],
            },
            "generated_include_roots": [],
            "generated_stage_facts": {},
            "blockers": [],
        }
        discovery = {
            "status": "ready",
            "compile_database": binding(
                "facts/compile-commands.json", b"compile database",
            ),
            "translation_units": [{
                "unit_id": "unit-contract",
                "variant_index": 0,
                "variant_count": 1,
                "source": source,
                "working_directory": ".",
                "compiler": "gcc",
                "compiler_wrappers": ["distcc"],
                "language": "c",
                "includes": [],
                "defines": [],
                "redacted_define_count": 0,
                "semantic_flags": ["-std=c11", "-m64"],
                "expanded_argv_sha256": content_sha256([
                    "distcc", "gcc", "-std=c11", "-m64", "-c",
                    "src/unit.c", "-o", "build/unit.o",
                ]),
                "response_files": [],
                "output": "build/unit.o",
                "entry": {"index": 0, "sha256": content_sha256("entry")},
            }],
            "generated_build_closure": closure,
        }
        verification = {"status": "verified", "blockers": []}
        evidence = self.full_evidence()
        refs = [
            {"role": "discovery", **artifact_reference("facts/discovery.json", discovery)},
            {
                "role": "generated-build-closure",
                **artifact_reference("facts/generated-closure.json", closure),
            },
            {
                "role": "generated-build-closure-verification",
                **artifact_reference("facts/generated-closure-verification.json", verification),
            },
            {
                "role": C_TOOLCHAIN_RAW_ROLE,
                **artifact_reference("facts/c-toolchain.json", evidence),
            },
        ]
        return project_build_ir(
            discovery, closure, verification, refs, evidence,
        )

    def make_report(self) -> dict[str, Any]:
        return {
            "commands": [
                command(
                    0, "compile",
                    ["gcc", "-std=c11", "-c", "src/unit.c", "-o", "build/unit.o"],
                    ["src/unit.c"], ["build/unit.o"],
                ),
                command(
                    1, "archive",
                    ["ar", "rcs", "build/libunit.a", "build/unit.o"],
                    ["build/unit.o"], ["build/libunit.a"],
                ),
                command(
                    2, "ranlib", ["ranlib", "build/libunit.a"],
                    ["build/libunit.a"], ["build/libunit.a"],
                ),
                command(
                    3, "link", ["ld", "build/unit.o", "-o", "build/program"],
                    ["build/unit.o"], ["build/program"],
                ),
            ],
            "input_refs": [binding("src/unit.c", self.source_bytes)],
            "makefile_ref": binding("Makefile", self.makefile_bytes),
            "toolchain_ref": binding("facts/legacy-toolchain.json", b"legacy"),
        }


__all__ = [
    "BuildIRHostBindingTestCase",
    "ContractToolchain",
    "artifact_reference",
]

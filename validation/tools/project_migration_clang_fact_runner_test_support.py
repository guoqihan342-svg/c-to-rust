from __future__ import annotations

from contextlib import ExitStack, contextmanager
import hashlib
import json
from collections.abc import Iterator

from unittest import mock

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.build_ir_projection import project_build_ir
from validation.tools._project_migration_harness.c_toolchain_probe import ProbeExecution
from validation.tools._project_migration_harness.c_toolchain_schema import C_TOOLCHAIN_RAW_ROLE
from validation.tools._project_migration_harness.clang_fact_commands import build_clang_fact_plans
from validation.tools._project_migration_harness.clang_fact_runner_paths import (
    ClangHostBindings,
)
from validation.tools._project_migration_harness.clang_fact_runner_process import (
    ClangProcessResult,
)
from validation.tools._project_migration_harness.clang_toolchain_binding import (
    persist_clang_toolchain_binding,
)
from validation.tools._project_migration_harness.sandbox_contract import SandboxContract
from validation.tools._project_migration_harness.sandbox_probe import make_probe_receipt
from validation.tools._project_migration_harness.sandbox_requirements import (
    REQUIRED_CAPABILITIES,
)
from validation.tools._project_migration_harness import clang_fact_runner as subject
from validation.tools._project_migration_harness import (
    clang_fact_runner_reopen as reopen_subject,
)
from validation.tools.project_migration_build_ir_host_test_support import (
    BuildIRHostBindingTestCase, artifact_reference, binding,
)


class ClangFactRunnerTestCase(BuildIRHostBindingTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.source_bytes = b"struct Packet { int value; };\n"
        (self.project_root / "src" / "unit.c").write_bytes(self.source_bytes)
        self.other_bytes = b"int other(void) { return 1; }\n"
        (self.project_root / "src" / "other.c").write_bytes(self.other_bytes)
        self.out_root = self.root / "target" / "run"
        self.ledger = self.out_root / "state" / "project-migration.sqlite3"
        self.ledger.parent.mkdir(parents=True)
        self.ledger.touch()
        self.runtime_parent = self.root / "runtime"
        self.resource_dir = self.root / "clang-resource"
        self.resource_dir.mkdir()
        self.fake.special[("--no-default-config", "-print-resource-dir")] = ProbeExecution(
            0, (str(self.resource_dir) + "\n").encode(), b"",
        )
        self.toolchain_receipt = persist_clang_toolchain_binding(
            self.out_root, profile="development", environment=self.environment,
            resolver=self.fake.resolver, runner=self.fake.runner,
        )
        portable = self.toolchain_receipt["portable_binding"]
        self.host = ClangHostBindings(
            portable, self.toolchain_receipt, (
                (self.fake.paths["clang"].resolve(), "/toolchain/bin/clang"),
                (self.resource_dir.resolve(), "/toolchain/resource"),
            ),
        )
        self.launcher = self.root / "bwrap"
        self.launcher.write_bytes(b"bubblewrap")
        self.launcher.chmod(0o755)
        self.contract = SandboxContract(
            backend="bubblewrap-v1",
            launcher_sha256=hashlib.sha256(self.launcher.read_bytes()).hexdigest(),
            toolchain_sha256=portable["binding_sha256"],
        )
        self.probe = make_probe_receipt(
            contract=self.contract, backend_version="0.11.0",
            capability_results={name: True for name in REQUIRED_CAPABILITIES},
            raw_observation={"status": "passed"}, cleanup_verified=True,
        )
        self.build_ir = self._build_ir()
        self.plans = build_clang_fact_plans(self.build_ir, portable)

    def plan(self, unit_id: str, gate: str) -> dict:
        return next(item for item in self.plans
                    if item["unit_id"] == unit_id and item["gate"] == gate)

    def kwargs(self, plan: dict, *, build_ir: dict | None = None) -> dict:
        return {
            "ledger_path": self.ledger, "out_root_rel": "target/run",
            "c_repo_root": self.project_root, "runtime_parent": self.runtime_parent,
            "bubblewrap_launcher": self.launcher, "sandbox_contract": self.contract,
            "sandbox_probe": self.probe, "build_ir": build_ir or self.build_ir,
            "toolchain_receipt": self.toolchain_receipt, "plan": plan,
        }

    def reopen_kwargs(self, plan: dict) -> dict:
        return {
            "ledger_path": self.ledger, "c_repo_root": self.project_root,
            "plan": plan, "build_ir": self.build_ir,
            "toolchain_receipt": self.toolchain_receipt,
            "sandbox_contract": self.contract, "sandbox_probe": self.probe,
        }

    @contextmanager
    def host_patches(self, *, verify: bool = True) -> Iterator[None]:
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                subject, "load_clang_host_bindings", return_value=self.host,
            ))
            stack.enter_context(mock.patch.object(
                reopen_subject, "load_clang_host_bindings", return_value=self.host,
            ))
            if verify:
                stack.enter_context(mock.patch.object(
                    subject, "verify_clang_host_binding_current", return_value=None,
                ))
            stack.enter_context(mock.patch.object(
                reopen_subject, "verify_clang_host_binding_current", return_value=None,
            ))
            yield

    def _build_ir(self) -> dict:
        outputs = [binding("build/unit.o", b"unit"), binding("build/other.o", b"other")]
        closure = {
            "status": "ready", "compile_outputs": outputs,
            "target_link_closure": {"targets": []}, "generated_include_roots": [],
            "generated_stage_facts": {}, "blockers": [],
        }
        units = [
            self._unit("unit-a", "src/unit.c", self.source_bytes, "build/unit.o", 0),
            self._unit("unit-b", "src/other.c", self.other_bytes, "build/other.o", 1),
        ]
        discovery = {
            "status": "ready",
            "compile_database": binding("facts/compile-commands.json", b"db"),
            "translation_units": units, "generated_build_closure": closure,
        }
        verification = {"status": "verified", "blockers": []}
        evidence = self.collect([{"token": "gcc", "roles": ["compiler-driver"]}])
        refs = [
            {"role": "discovery", **artifact_reference("facts/discovery.json", discovery)},
            {"role": "generated-build-closure",
             **artifact_reference("facts/closure.json", closure)},
            {"role": "generated-build-closure-verification",
             **artifact_reference("facts/verification.json", verification)},
            {"role": C_TOOLCHAIN_RAW_ROLE,
             **artifact_reference("facts/c-toolchain.json", evidence)},
        ]
        return project_build_ir(discovery, closure, verification, refs, evidence)

    @staticmethod
    def _unit(unit_id: str, path: str, data: bytes, output: str, index: int) -> dict:
        flags = ["-std=c11", "-m64", "-nostdinc"]
        return {
            "unit_id": unit_id, "variant_index": 0, "variant_count": 1,
            "source": binding(path, data), "working_directory": ".",
            "compiler": "gcc", "compiler_wrappers": [], "language": "c",
            "includes": [], "defines": [], "redacted_define_count": 0,
            "semantic_flags": flags,
            "expanded_argv_sha256": content_sha256(["gcc", *flags, "-c", path]),
            "response_files": [], "output": output,
            "entry": {"index": index, "sha256": content_sha256(f"entry-{index}")},
        }


def invocation(
    stdout: bytes, *, returncode: int = 0, timed_out: bool = False,
    flooded: bool = False,
):
    def invoke(argv: list[str], **_: object) -> ClangProcessResult:
        return ClangProcessResult(
            True, returncode, stdout, b"", timed_out=timed_out,
            output_limit_exceeded=flooded,
            launcher_argv_sha256=content_sha256(argv),
        )
    return invoke


def ast_bytes() -> bytes:
    record = {
        "kind": "RecordDecl", "name": "Packet", "tagUsed": "struct",
        "completeDefinition": True,
        "loc": {"file": "src/unit.c", "offset": 0, "tokLen": 6},
        "range": {
            "begin": {"offset": 0, "tokLen": 6},
            "end": {"offset": 27, "tokLen": 1},
        },
        "inner": [{
            "kind": "FieldDecl", "name": "value",
            "type": {"qualType": "int"}, "isBitfield": False,
        }],
    }
    return json.dumps(
        {"kind": "TranslationUnitDecl", "inner": [record]},
        separators=(",", ":"),
    ).encode()


def layout_bytes() -> bytes:
    def block(name: str) -> str:
        return "\n".join([
            "*** Dumping AST Record Layout", f"         0 | struct {name}",
            "         0 |   int value", "           | [sizeof=8, align=8]", "",
        ])
    return (block("SystemNoise") + block("Packet")).encode()


def triples(values: list[str]) -> list[list[str]]:
    return [values[index:index + 3] for index in range(len(values) - 2)]


__all__ = [
    "ClangFactRunnerTestCase", "ast_bytes", "invocation", "layout_bytes",
    "triples",
]

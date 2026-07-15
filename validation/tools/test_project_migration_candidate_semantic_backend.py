from __future__ import annotations

import hashlib
import platform
from pathlib import Path
import shutil
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes,
    content_sha256,
)
from validation.tools._project_migration_harness.candidate_semantic_backend_contract import (
    SemanticBackendError,
    parse_scalar_function,
)
from validation.tools._project_migration_harness.candidate_semantic_stimuli import (
    HELD_OUT_CASE_COUNT,
    held_out_scalar_cases,
    rust_negative_source,
)
from validation.tools._project_migration_harness.candidate_semantic_schema import (
    CONTEXT_KEYS,
    fixed_adapter_plan,
    parse_adapter_observation,
)
from validation.tools._project_migration_harness import candidate_semantic_runners as runners
from validation.tools._project_migration_harness.sandbox_linux import (
    discover_sandbox_backend,
)


FAMILIES = (
    "oracle-replay-diff", "negative", "unsafe-alias", "abi-layout",
)


def digest(value: bytes | str) -> str:
    data = value if isinstance(value, bytes) else value.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class CandidateSemanticBackendContractTests(unittest.TestCase):
    def test_held_out_cases_are_nonce_bound_and_render_an_executed_mutant(self) -> None:
        function = parse_scalar_function(
            "scalar_probe", "int scalar_probe(int value) { return value + 1; }",
        )
        first = held_out_scalar_cases(function, b"a" * 32)
        second = held_out_scalar_cases(function, b"b" * 32)
        self.assertEqual(HELD_OUT_CASE_COUNT, len(first))
        self.assertEqual(HELD_OUT_CASE_COUNT, len(set(first)))
        self.assertNotEqual(first, second)
        self.assertTrue(any(row[0] not in {-3, -1, 0, 1, 3, 7} for row in first))
        mutant = rust_negative_source(function, first)
        self.assertEqual(1, mutant.count("wrapping_add"))
        self.assertIn("candidate::scalar_probe", mutant)

    def test_scalar_contract_is_identity_independent_and_rejects_pointers(self) -> None:
        first = parse_scalar_function(
            "alpha_value", "int alpha_value(int input) { return input + 1; }",
        )
        second = parse_scalar_function(
            "beta_value", "int beta_value(int input) { return input + 1; }",
        )
        self.assertEqual(first.result, second.result)
        self.assertEqual(first.parameters, second.parameters)
        with self.assertRaisesRegex(SemanticBackendError, "signature_unsupported"):
            parse_scalar_function(
                "alpha_value", "int alpha_value(const int *input) { return *input; }",
            )

    @unittest.skipUnless(platform.system() == "Linux", "requires Linux bubblewrap")
    def test_fixed_worker_executes_all_real_scalar_adapters(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        cargo_value = shutil.which("cargo")
        if cargo_value is None:
            self.skipTest("Cargo is unavailable")
        discovery = discover_sandbox_backend(Path(cargo_value), repository)
        if discovery.backend is None:
            self.skipTest(discovery.reason_code or "sandbox unavailable")
        target = repository / "target"
        target.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="candidate-semantic-live-", dir=target,
        ) as temporary:
            fixture = Path(temporary)
            requests = self._requests(
                repository, fixture, discovery.backend.contract.payload(),
            )
            observations = {}
            for family in FAMILIES:
                plan = fixed_adapter_plan(family)
                execution = runners._invoke_fixed_adapter(
                    plan, canonical_json_bytes(requests[family]), repository,
                )
                self.assertIsNone(
                    runners._execution_blocker(execution),
                    execution.stderr.decode("utf-8", errors="replace"),
                )
                observations[family] = parse_adapter_observation(
                    execution.stdout, family,
                )
        self.assertGreater(observations["oracle-replay-diff"]["case_count"], 0)
        self.assertEqual(0, observations["oracle-replay-diff"]["mismatch_count"])
        self.assertEqual(0, observations["oracle-replay-diff"]["crash_count"])
        self.assertEqual(0, observations["negative"]["unexpected_accept_count"])
        self.assertEqual(0, observations["unsafe-alias"]["unsafe_site_count"])
        self.assertEqual(0, observations["unsafe-alias"]["unproven_alias_count"])
        self.assertGreater(observations["abi-layout"]["check_count"], 0)
        self.assertEqual(0, observations["abi-layout"]["mismatch_count"])

    @unittest.skipUnless(platform.system() == "Linux", "requires Linux bubblewrap")
    def test_old_fixed_sample_lookup_candidate_is_rejected(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        cargo_value = shutil.which("cargo")
        if cargo_value is None:
            self.skipTest("Cargo is unavailable")
        discovery = discover_sandbox_backend(Path(cargo_value), repository)
        if discovery.backend is None:
            self.skipTest(discovery.reason_code or "sandbox unavailable")
        target = repository / "target"
        target.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="candidate-semantic-hardcode-", dir=target,
        ) as temporary:
            fixture = Path(temporary)
            hardcoded = b"""pub fn scalar_probe(value: i32) -> i32 {
    match value {
        -3 => -8, -1 => -2, 0 => 1, 1 => 4, 3 => 10, 7 => 22,
        _ => 0,
    }
}
"""
            request = self._requests(
                repository, fixture, discovery.backend.contract.payload(),
                rust_source=hardcoded,
            )["oracle-replay-diff"]
            plan = fixed_adapter_plan("oracle-replay-diff")
            execution = runners._invoke_fixed_adapter(
                plan, canonical_json_bytes(request), repository,
            )
            self.assertIsNone(runners._execution_blocker(execution))
            observation = parse_adapter_observation(
                execution.stdout, "oracle-replay-diff",
            )
            self.assertGreater(observation["mismatch_count"], 0)

    def _requests(
        self, repository: Path, fixture: Path, sandbox_contract: dict,
        *, rust_source: bytes | None = None,
    ) -> dict[str, dict]:
        symbol = "scalar_probe"
        c_source = (
            f"int {symbol}(int value) {{ return value * 3 + 1; }}\n"
        ).encode("utf-8")
        rust_source = rust_source or (
            f"pub fn {symbol}(value: i32) -> i32 {{ value * 3 + 1 }}\n"
        ).encode("utf-8")
        source_ref = self._write(repository, fixture / "source/unit.c", c_source)
        candidate_ref = self._write(
            repository, fixture / "candidate.rs", rust_source,
        )
        node_id = "node-" + digest(symbol)[:16]
        compiler = sandbox_contract["native_linker"]["driver"]
        compiler_size = Path("/usr/bin/cc").resolve(strict=True).stat().st_size
        facts = [
            self._fact("function", {
                "node_id": node_id, "unit_id": "unit", "node_kind": "function",
                "symbol": symbol, "linkage": "external",
            }),
            self._fact("source_binding", {
                "node_id": node_id,
                "source": {
                    "path": source_ref["path"], "sha256": source_ref["sha256"],
                    "encoding": "utf-8",
                    "span": {
                        "byte_start": 0, "byte_end": len(c_source),
                        "sha256": digest(c_source),
                    },
                },
            }),
            self._fact("function_source", {
                "node_id": node_id, "chunk_index": 0, "chunk_count": 1,
                "content": c_source.decode("utf-8"),
            }),
            self._fact("compile_unit", {
                "unit_id": "unit", "compiler": "cc", "language": "c",
                "working_directory": ".", "redacted_define_count": 0,
            }),
            self._fact("compiler_fact_binding", {
                "unit_id": "unit", "status": "syntax_passed",
                "reason_code": None, "source_sha256": source_ref["sha256"],
                "expanded_argv_sha256": digest("argv"),
                "toolchain_id": "toolchain", "toolchain_binding_sha256": digest("toolchain"),
                "compile_context_sha256": digest("compile-context"),
                "plan_sha256": digest("compiler-plan"),
                "receipt_sha256": digest("compiler-receipt"),
                "command_started": True, "syntax_passed": True,
                "diagnostics_sha256": digest("compiler-diagnostics"),
                "diagnostic_bytes": 0,
                "compiler_basename": compiler["basename"],
                "compiler_binary_sha256": compiler["sha256"],
                "compiler_binary_size_bytes": compiler_size,
                "evidence_scope": "exact_original_compiler_syntax_only",
                "semantic_gate": False, "translation_coverage_numerator": 0,
            }),
        ]
        page_ref = self._write_json(repository, fixture / "context/page.json", {
            "schema_version": 1, "facts": facts,
        })
        worker_base = {
            "schema_version": 1, "request_kind": "project_migration_worker",
            "run_id": "run", "worker_id": "worker", "role": "translator",
            "group_id": "group", "unit_id": "unit",
            "context": {"pages": [{
                "page_id": "page-live", "path": page_ref["path"],
                "sha256": page_ref["sha256"],
                "byte_count": page_ref["size_bytes"],
                "token_count": page_ref["size_bytes"],
            }]},
        }
        worker = {
            **worker_base, "effective_input_sha256": content_sha256(worker_base),
        }
        worker_ref = self._write_json(
            repository, fixture / "worker-request.json", worker,
        )
        candidate_set = digest("candidate-set")
        compile_raw = {
            "run_id": "run", "unit_id": "unit",
            "candidate_artifact_id": "candidate",
            "candidate_sha256": candidate_ref["sha256"],
            "candidate_set_sha256": candidate_set,
            "sandbox": {"contract": sandbox_contract},
        }
        compile_ref = self._write_json(
            repository, fixture / "compile-observation.json", compile_raw,
        )
        bindings = {
            "run_id": "run", "group_id": "group", "unit_id": "unit",
            "candidate_artifact_id": "candidate",
            "candidate_sha256": candidate_ref["sha256"],
            "candidate_set_sha256": candidate_set,
            "candidate_source": candidate_ref,
            "run_context_sha256": digest("run-context"),
            "compile_verdict": compile_ref,
            "compile_observation": compile_ref,
            "generation_sha256": digest("generation"),
            "toolchain_sha256": sandbox_contract["toolchain_sha256"],
            "worker_request": worker_ref,
        }
        self.assertEqual(CONTEXT_KEYS, set(bindings))
        return {
            family: {
                "schema_version": 1,
                "artifact_kind": "candidate-semantic-adapter-request",
                "bindings": bindings,
                "verification_plan": fixed_adapter_plan(family),
            }
            for family in FAMILIES
        }

    @staticmethod
    def _fact(kind: str, payload: dict) -> dict:
        value = {"kind": kind, "payload": payload}
        return {"sha256": content_sha256(value), **value}

    @staticmethod
    def _write(repository: Path, path: Path, data: bytes) -> dict:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return {
            "path": path.relative_to(repository).as_posix(),
            "sha256": digest(data), "size_bytes": len(data),
        }

    @classmethod
    def _write_json(cls, repository: Path, path: Path, value: dict) -> dict:
        return cls._write(repository, path, canonical_json_bytes(value))


if __name__ == "__main__":
    unittest.main()

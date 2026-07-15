from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.c_compilation_fact_bundle import (
    C_COMPILATION_FACT_BUNDLE_KIND,
)
from validation.tools._project_migration_harness.c_compilation_fact_validation import (
    validate_c_compilation_fact_bundle,
)
from validation.tools._project_migration_harness.c_compilation_fact_runtime import (
    _required_compiler_records,
)
from validation.tools._project_migration_harness.c_index import index_translation_units
from validation.tools._project_migration_harness.context_pages import build_context_pages
from validation.tools._project_migration_harness.host_tool_binding import (
    classify_tool_basename,
)
from validation.tools._project_migration_harness.migration_graph import build_migration_graph
from validation.tools._project_migration_harness.sandbox_contract import SandboxContract
from validation.tools._project_migration_harness.sandbox_probe import make_probe_receipt
from validation.tools._project_migration_harness.sandbox_requirements import (
    REQUIRED_CAPABILITIES,
)


def valid_compilation_bundle(unit: dict, build_ir_sha256: str) -> dict:
    unit_id = str(unit["unit_id"])
    compiler = str(unit.get("compiler", "clang")).replace("\\", "/").rsplit("/", 1)[-1]
    family, basename = classify_tool_basename(compiler)
    arguments = unit.get("compile_arguments", {})
    argv_sha256 = unit.get(
        "expanded_argv_sha256", arguments.get("expanded_argv_sha256"),
    )
    empty_sha256 = hashlib.sha256(b"").hexdigest()
    probe_value = {
        "status": "reported", "value": "test-value",
        "stdout_sha256": empty_sha256, "stderr_sha256": empty_sha256,
    }
    toolchain_core = {
        "schema_version": 1, "artifact_kind": "c-compiler-portable-binding",
        "toolchain_id": unit["toolchain_id"], "family": family,
        "basename": basename,
        "binary": {"sha256": "1" * 64, "size_bytes": 1},
        "target": dict(probe_value), "version": dict(probe_value),
    }
    toolchain = {
        **toolchain_core, "binding_sha256": content_sha256(toolchain_core),
    }
    contract = SandboxContract(
        backend="bubblewrap-v1", launcher_sha256="2" * 64,
        toolchain_sha256=content_sha256([toolchain]),
    )
    probe = make_probe_receipt(
        contract=contract, backend_version="1.0",
        capability_results={name: True for name in REQUIRED_CAPABILITIES},
        raw_observation={"status": "verified"}, cleanup_verified=True,
    )
    plan_sha256 = "e" * 64
    unit_sha256 = hashlib.sha256(unit_id.encode("utf-8")).hexdigest()
    raw = {
        "schema_version": 1, "unit_id": unit_id,
        "unit_id_sha256": unit_sha256, "plan_sha256": plan_sha256,
    }
    for stream in ("stdout", "stderr"):
        raw[f"{stream}_sha256"] = empty_sha256
        raw[f"{stream}_ref"] = {
            "path": "verification/raw-output/c-compilation/"
            f"{plan_sha256}/{unit_sha256}/{stream}/{empty_sha256}.bin",
            "sha256": empty_sha256, "size_bytes": 0,
        }
    receipt_core = {
        "schema_version": 1, "artifact_kind": "c-compilation-syntax-receipt",
        "unit_id": unit_id, "source_sha256": unit["source"]["sha256"],
        "expanded_argv_sha256": argv_sha256,
        "toolchain_id": unit["toolchain_id"],
        "toolchain_binding_sha256": toolchain["binding_sha256"],
        "compile_context_sha256": "d" * 64, "plan_sha256": plan_sha256,
        "sandbox_probe_sha256": probe.sha256, "status": "syntax_passed",
        "reason_code": None, "command_started": True, "returncode": 0,
        "timed_out": False, "output_limit_exceeded": False,
        "diagnostics_sha256": empty_sha256, "diagnostic_bytes": 0,
        "raw_outputs": raw, "semantic_gate": False,
        "translation_coverage_numerator": 0,
    }
    receipt = {**receipt_core, "receipt_sha256": content_sha256(receipt_core)}
    core = {
        "schema_version": 1, "artifact_kind": C_COMPILATION_FACT_BUNDLE_KIND,
        "status": "ready", "profile": "competition",
        "build_ir_semantic_sha256": build_ir_sha256,
        "sandbox": {
            "contract": contract.payload(), "contract_sha256": contract.sha256,
            "probe": probe.payload(), "probe_sha256": probe.sha256,
        },
        "toolchains": [toolchain], "units": [receipt],
        "summary": {"total": 1, "observed": 1, "passed": 1,
                    "blocked": 0, "unavailable_reason": None},
        "claim_boundary": {"semantic_gate": False,
                           "translation_coverage_numerator": 0,
                           "scope": "compiler_syntax_witness_only"},
    }
    return {**core, "bundle_sha256": content_sha256(core)}


def _rehash_bundle(bundle: dict) -> None:
    bundle["bundle_sha256"] = content_sha256({
        key: value for key, value in bundle.items() if key != "bundle_sha256"
    })


def _mutate_receipt(bundle: dict, **changes: object) -> None:
    receipt = bundle["units"][0]
    receipt.update(changes)
    receipt["receipt_sha256"] = content_sha256({
        key: value for key, value in receipt.items() if key != "receipt_sha256"
    })
    _rehash_bundle(bundle)


class ProjectMigrationCCompilationFactTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="c-compilation-facts-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        raw = b"#if FEATURE\nint selected(void) { return 1; }\n#endif\n"
        path = self.root / "src/unit.c"
        path.parent.mkdir(parents=True)
        path.write_bytes(raw)
        self.source_sha256 = hashlib.sha256(raw).hexdigest()
        self.argv_sha256 = "a" * 64
        self.build_ir_sha256 = "b" * 64
        self.unit = {
            "unit_id": "unit-a",
            "source": {"path": "src/unit.c", "sha256": self.source_sha256},
            "toolchain_id": "toolchain-a",
            "compiler": "clang",
            "expanded_argv_sha256": self.argv_sha256,
        }

    def test_exact_syntax_witness_reaches_context_without_erasing_boundary(self) -> None:
        bundle = self.bundle()

        index = index_translation_units(
            self.root,
            [self.unit],
            compilation_fact_bundle=bundle,
            build_ir_semantic_sha256=self.build_ir_sha256,
        )

        fact = index["unit_contexts"][0]["compiler_fact"]
        self.assertTrue(fact["syntax_passed"])
        self.assertFalse(fact["semantic_gate"])
        self.assertEqual("ready_with_boundaries", index["status"])
        pages = build_context_pages(index, build_migration_graph(index))
        compiler_facts = [
            value["payload"] for value in pages["shared_facts"].values()
            if value["kind"] == "compiler_fact_binding"
        ]
        self.assertEqual(1, len(compiler_facts))
        self.assertEqual("exact_original_compiler_syntax_only",
                         compiler_facts[0]["evidence_scope"])
        self.assertEqual("clang", compiler_facts[0]["compiler_basename"])
        self.assertEqual("1" * 64, compiler_facts[0]["compiler_binary_sha256"])
        self.assertEqual(1, compiler_facts[0]["compiler_binary_size_bytes"])
        self.assertEqual(
            bundle["toolchains"][0]["binding_sha256"],
            compiler_facts[0]["toolchain_binding_sha256"],
        )

    def test_source_argument_or_toolchain_drift_is_rejected(self) -> None:
        for field, value in (
            ("expanded_argv_sha256", "c" * 64),
            ("toolchain_id", "toolchain-b"),
            ("compiler", "gcc"),
        ):
            with self.subTest(field=field):
                unit = {**self.unit, field: value}
                with self.assertRaisesRegex(ValueError, "translation_unit_drifted"):
                    index_translation_units(
                        self.root,
                        [unit],
                        compilation_fact_bundle=self.bundle(),
                        build_ir_semantic_sha256=self.build_ir_sha256,
                    )

    def test_runtime_selects_only_translation_unit_compilers(self) -> None:
        compiler = {
            "toolchain_id": "toolchain-a", "role": "compiler-driver",
        }
        linker = {
            "toolchain_id": "toolchain-link", "role": "linker-driver",
        }

        selected = _required_compiler_records({
            "translation_units": [{"toolchain_id": "toolchain-a"}],
            "toolchains": [linker, compiler],
        })

        self.assertEqual([compiler], selected)

    def test_runtime_rejects_missing_or_duplicate_required_toolchain(self) -> None:
        unit = {"toolchain_id": "toolchain-a"}
        with self.assertRaisesRegex(ValueError, "toolchain_binding_missing"):
            _required_compiler_records({
                "translation_units": [unit],
                "toolchains": [{"toolchain_id": "toolchain-link"}],
            })
        with self.assertRaisesRegex(ValueError, "toolchain_duplicate"):
            _required_compiler_records({
                "translation_units": [unit],
                "toolchains": [
                    {"toolchain_id": "toolchain-a"},
                    {"toolchain_id": "toolchain-a"},
                ],
            })

    def test_forged_toolchain_and_sandbox_are_rejected(self) -> None:
        forged = deepcopy(self.bundle())
        forged["toolchains"] = [{}]
        _rehash_bundle(forged)
        with self.assertRaisesRegex(ValueError, "toolchain"):
            validate_c_compilation_fact_bundle(forged)

        forged = deepcopy(self.bundle())
        forged["sandbox"]["probe_sha256"] = "0" * 64
        _rehash_bundle(forged)
        with self.assertRaisesRegex(ValueError, "sandbox_binding"):
            validate_c_compilation_fact_bundle(forged)

    def test_passed_receipt_requires_real_execution_and_raw_refs(self) -> None:
        for changes in (
            {"raw_outputs": {}},
            {"command_started": False},
            {"toolchain_binding_sha256": "9" * 64},
        ):
            with self.subTest(changes=changes):
                forged = deepcopy(self.bundle())
                _mutate_receipt(forged, **changes)
                with self.assertRaises(ValueError):
                    validate_c_compilation_fact_bundle(forged)

    def test_blocked_receipt_execution_shape_is_strict(self) -> None:
        blocked = deepcopy(self.bundle())
        _mutate_receipt(
            blocked, status="blocked", reason_code="compiler_nonzero_exit",
            returncode=7,
        )
        blocked["status"] = "ready_with_boundaries"
        blocked["summary"].update({"passed": 0, "blocked": 1})
        _rehash_bundle(blocked)
        validate_c_compilation_fact_bundle(blocked)

        forged = deepcopy(blocked)
        _mutate_receipt(
            forged, reason_code="compiler_runtime_cleanup_failed",
        )
        with self.assertRaisesRegex(ValueError, "execution_invalid"):
            validate_c_compilation_fact_bundle(forged)

    def test_status_and_summary_are_rederived(self) -> None:
        for mutation in ("status", "summary"):
            with self.subTest(mutation=mutation):
                forged = deepcopy(self.bundle())
                if mutation == "status":
                    forged["status"] = "ready_with_boundaries"
                else:
                    forged["summary"]["passed"] = 0
                _rehash_bundle(forged)
                with self.assertRaisesRegex(ValueError, "summary"):
                    validate_c_compilation_fact_bundle(forged)

    def bundle(self) -> dict:
        return valid_compilation_bundle(self.unit, self.build_ir_sha256)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.native_link_abi_evidence import (
    build_native_link_abi_evidence,
)
from validation.tools._project_migration_harness.native_link_actual_resolution import (
    resolve_traced_native_artifacts,
)
from validation.tools._project_migration_harness.native_link_order import (
    build_native_link_order_evidence,
)
from validation.tools._project_migration_harness.native_link_settlement import (
    build_native_link_settlement,
    validate_native_link_settlement,
)
from validation.tools._project_migration_harness.native_link_symbol_evidence import (
    build_native_link_symbol_evidence,
)
from validation.tools._project_migration_harness.project_cargo_evidence import (
    CARGO_COMMANDS, project_cargo_observation,
)
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract, canonical_sha256,
)
from validation.tools._project_migration_harness.sandbox_native_linker_contract import (
    NativeLinkerContract,
)
from validation.tools._project_migration_harness.sandbox_probe import (
    make_probe_receipt,
)
from validation.tools._project_migration_harness.sandbox_requirements import (
    cargo_verification_plan,
)
from validation.tools.project_migration_native_link_actual_test_support import (
    NativeLinkActualTestCase,
    candidate,
    context,
    elf,
    trace,
)


INPUT_SHA256 = "a" * 64


class NativeLinkSettlementTests(NativeLinkActualTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.context = context((f"lib{self.shared_stem}.so", "shared-library"))
        self.candidate = candidate(self.context)
        guest = f"/usr/lib/lib{self.shared_stem}.so.1"
        self._write_guest(guest, elf(object_type=3, machine=62))
        self.link_trace = trace(guest)
        self.actual = resolve_traced_native_artifacts(
            self.link_trace, self.context, self.candidate,
            guest_roots=self.roots,
        )
        self.contract = _linker_contract("x86_64-unknown-linux-gnu")
        self.order = build_native_link_order_evidence(
            self.link_trace, self.context, self.candidate, self.actual,
        )
        self.abi = build_native_link_abi_evidence(
            self.contract.payload(), self.link_trace, self.context,
            self.candidate, self.actual,
        )
        self.symbol_context = _no_symbol_context(self.context, self.candidate)
        self.symbols = build_native_link_symbol_evidence(
            self.link_trace, self.context, self.candidate, self.actual,
            self.symbol_context, None, {},
        )
        self.cargo = _cargo_observation(self.contract, passed=True)

    def inputs(self) -> dict:
        return {
            "cargo_test_observation": self.cargo,
            "linker_contract": self.contract.payload(),
            "trace": self.link_trace,
            "context": self.context,
            "candidate": self.candidate,
            "actual_resolution": self.actual,
            "order_evidence": self.order,
            "abi_evidence": self.abi,
            "symbol_context": self.symbol_context,
            "symbol_candidate": None,
            "symbol_reports": {},
            "symbol_evidence": self.symbols,
        }

    def test_all_native_resolution_gates_issue_reopenable_receipt(self) -> None:
        values = self.inputs()
        receipt = build_native_link_settlement(**values)
        self.assertEqual("resolved", receipt["status"])
        self.assertTrue(receipt["resolution_gate"])
        self.assertEqual([], receipt["blockers"])
        self.assertTrue(all(receipt["gates"].values()))
        self.assertFalse(receipt["semantic_gate"])
        self.assertEqual(0, receipt["translation_coverage_numerator"])
        self.assertEqual(
            receipt, validate_native_link_settlement(receipt, **values),
        )

    def test_failed_cargo_or_mismatched_abi_cannot_aggregate_to_resolved(self) -> None:
        failed_cargo = self.inputs()
        failed_cargo["cargo_test_observation"] = _cargo_observation(
            self.contract, passed=False,
        )
        receipt = build_native_link_settlement(**failed_cargo)
        self.assertEqual("blocked", receipt["status"])
        self.assertEqual(["cargo-test"], receipt["blockers"])

        other = _linker_contract("aarch64-unknown-linux-gnu")
        mismatched = self.inputs()
        mismatched["linker_contract"] = other.payload()
        mismatched["abi_evidence"] = build_native_link_abi_evidence(
            other.payload(), self.link_trace, self.context,
            self.candidate, self.actual,
        )
        mismatched["cargo_test_observation"] = _cargo_observation(
            other, passed=True,
        )
        receipt = build_native_link_settlement(**mismatched)
        self.assertEqual(["target-abi"], receipt["blockers"])
        self.assertFalse(receipt["resolution_gate"])

    def test_receipt_or_bound_evidence_tamper_fails_validation(self) -> None:
        values = self.inputs()
        receipt = build_native_link_settlement(**values)
        tampered = copy.deepcopy(receipt)
        tampered["resolution_gate"] = False
        with self.assertRaisesRegex(ValueError, "settlement_invalid"):
            validate_native_link_settlement(tampered, **values)

        evidence_tamper = self.inputs()
        evidence_tamper["order_evidence"] = copy.deepcopy(self.order)
        evidence_tamper["order_evidence"]["order_gate"] = False
        with self.assertRaisesRegex(ValueError, "order_evidence_invalid"):
            build_native_link_settlement(**evidence_tamper)


def _linker_contract(target: str) -> NativeLinkerContract:
    binding = {
        "driver": {
            "basename": "cc", "family": "gnu-compiler", "sha256": "1" * 64,
        },
        "linker": {
            "basename": "ld", "family": "linker", "sha256": "2" * 64,
        },
        "target_triple": target,
    }
    return NativeLinkerContract(
        driver_basename="cc", driver_sha256="1" * 64,
        linker_basename="ld", linker_sha256="2" * 64,
        target_triple=target, binding_sha256=content_sha256(binding),
    )


def _no_symbol_context(link_context: dict, link_candidate: dict) -> dict:
    proposals = {
        item["requirement_id"]: item for item in link_candidate["proposals"]
    }
    result = {
        "schema_version": 1,
        "artifact_kind": "native-symbol-model-context",
        "status": "not-required",
        "profile": link_context["profile"],
        "bindings": {
            "rust_project_ir_sha256": content_sha256("rust-project-ir"),
            "native_link_context_sha256": link_context["context_sha256"],
            "native_link_candidate_sha256": link_candidate["candidate_sha256"],
        },
        "symbols": [], "symbol_count": 0,
        "providers": [{
            "requirement_id": item["requirement_id"],
            "portable_name": item["portable_name"],
            "library_format": item["library_format"],
            "strategy": proposals[item["requirement_id"]]["strategy"],
            "rustc_link_name": proposals[item["requirement_id"]]["rustc_link_name"],
            "rustc_link_kind": proposals[item["requirement_id"]]["rustc_link_kind"],
        } for item in link_context["requirements"]],
        "provider_count": len(link_context["requirements"]),
        "model_policy": {
            "input_scope": "grouped-rust-ffi-imports-and-native-requirements",
            "allowed_provider_kinds": ["defer", "native-requirement", "runtime"],
            "exact_symbol_coverage_required": True,
            "invented_symbols_allowed": False,
            "model_may_claim_resolved": False,
        },
        "claim_boundary": {
            "artifact_role": "native-symbol-planning-context",
            "symbol_assignments_resolved": False,
            "native_exports_verified": False,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }
    result["context_sha256"] = content_sha256(result)
    return result


def _cargo_observation(
    native_linker: NativeLinkerContract, *, passed: bool,
) -> dict:
    contract = SandboxContract(
        backend="bubblewrap-v1", launcher_sha256="3" * 64,
        toolchain_sha256="4" * 64, native_linker=native_linker,
    )
    probe = make_probe_receipt(
        contract=contract, backend_version="test-only",
        capability_results={name: True for name in contract.requirements.capabilities},
        raw_observation={"fixture": "bounded"}, cleanup_verified=True,
    )
    command = [*CARGO_COMMANDS["cargo-test"], "--jobs", "1"]
    plan = cargo_verification_plan(
        "cargo-test", tuple(command), INPUT_SHA256,
        requirements=contract.requirements, native_link_trace=True,
    )
    status, returncode = ("passed", 0) if passed else ("failed", 1)
    check = {
        "command": command, "status": status, "cargo_executed": True,
        "returncode": returncode, "timed_out": False,
        "stdout_sha256": "5" * 64, "stderr_sha256": "6" * 64,
        "stdout_ref": _raw_ref("stdout", "5" * 64),
        "stderr_ref": _raw_ref("stderr", "6" * 64),
        "sandbox_contract_sha256": contract.sha256,
        "sandbox_command_sha256": canonical_sha256(command),
        "sandbox_command_started": True,
        "sandbox_launcher_argv_sha256": "7" * 64,
        "sandbox_requirements_sha256": contract.requirements.sha256,
        "sandbox_verification_plan": plan.payload(),
        "sandbox_verification_plan_sha256": plan.sha256,
        "sandbox_probe_receipt_sha256": probe.sha256,
    }
    sandbox = {
        "contract": contract.payload(), "contract_sha256": contract.sha256,
        "probe_receipt": probe.payload(), "probe_receipt_sha256": probe.sha256,
        "cleanup_verified": True,
    }
    execution = {
        "project_input_sha256": INPUT_SHA256,
        "project_state_before": INPUT_SHA256,
        "project_state_after": INPUT_SHA256,
        "project_state_unchanged": True,
        "sandbox": sandbox, "checks": [check],
    }
    return project_cargo_observation(
        execution, check, gate_kind="cargo-test",
        expected_input_sha256=INPUT_SHA256,
    )


def _raw_ref(stream: str, digest: str) -> dict:
    return {
        "path": (
            "target/run/verification/raw-output/cargo-test/"
            f"{stream}/{digest}.bin"
        ),
        "sha256": digest, "size_bytes": 1,
    }


if __name__ == "__main__":
    unittest.main()

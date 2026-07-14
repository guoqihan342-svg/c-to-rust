from __future__ import annotations

from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.host_verifier_contract import (
    HOST_VERIFIER_GATE_KINDS, HOST_VERIFIER_ISSUER,
    HostVerifierEnvelopeBindings,
)
from validation.tools._project_migration_harness.host_verifier_raw_evidence import (
    write_host_verifier_raw_evidence,
)
from validation.tools._project_migration_harness.host_verifier_receipt import (
    build_host_verifier_receipt, host_verifier_receipt_sha256,
    reopen_and_validate_host_verifier_receipt,
    validate_host_verifier_receipt, validate_host_verifier_receipt_schema,
)
from validation.tools._project_migration_harness.sandbox_requirements import (
    SandboxVerificationPlan, strict_sandbox_requirements,
)


class ProjectMigrationHostVerifierReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="host-verifier-receipt-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.evidence_root = "target/host-verifier-run"

    def test_three_distinct_gate_kinds_build_non_authoritative_receipts(self) -> None:
        self.assertEqual(3, len(HOST_VERIFIER_GATE_KINDS))
        self.assertEqual(3, len(set(HOST_VERIFIER_GATE_KINDS)))
        self.assertEqual({
            "project-initialization", "project-feature-cfg", "project-abi",
        }, set(HOST_VERIFIER_GATE_KINDS))
        for gate_kind in HOST_VERIFIER_GATE_KINDS:
            with self.subTest(gate_kind=gate_kind):
                bindings, receipt = self._case(gate_kind)
                reopened = reopen_and_validate_host_verifier_receipt(
                    self.root, receipt, bindings,
                )
                self.assertEqual("failed", reopened["status"])
                self.assertEqual(HOST_VERIFIER_ISSUER, reopened["issuer"])
                self.assertFalse(reopened["semantic_gate"])
                self.assertEqual(0, reopened["translation_coverage_numerator"])
                self.assertNotIn("nonce_consumed", reopened)
                self.assertNotIn("caller_authority", reopened)

    def test_blocked_receipt_has_no_exit_code_or_pass_authority(self) -> None:
        bindings, _receipt = self._case("project-initialization")
        stdout, stderr = self._raw_pair(bindings.gate_kind)
        for termination in ("not-started", "timed-out", "signaled"):
            with self.subTest(termination=termination):
                receipt = build_host_verifier_receipt(
                    bindings, stdout_ref=stdout, stderr_ref=stderr,
                    exit_code=None, termination=termination, status="blocked",
                )
                self.assertEqual(
                    "blocked",
                    reopen_and_validate_host_verifier_receipt(
                        self.root, receipt, bindings,
                    )["status"],
                )

    def test_pass_unknown_field_caller_authority_and_claims_are_rejected(self) -> None:
        bindings, receipt = self._case("project-feature-cfg")
        mutations = (
            ({**receipt, "status": "passed", "exit_code": 0}, "claim boundary"),
            ({**receipt, "caller_authority": True}, "fields"),
            ({**receipt, "issuer": "caller"}, "identity"),
            ({**receipt, "semantic_gate": True}, "claim boundary"),
            ({**receipt, "translation_coverage_numerator": 1}, "claim boundary"),
            ({**receipt, "nonce_consumed": True}, "fields"),
        )
        for mutated, message in mutations:
            with self.subTest(message=message):
                self._refresh(mutated)
                with self.assertRaisesRegex(ValueError, message):
                    validate_host_verifier_receipt_schema(mutated)

    def test_replay_shape_and_stale_capability_nonce_context_are_rejected(self) -> None:
        bindings, receipt = self._case("project-abi")
        replay_shaped = {**receipt, "nonce": {"value": receipt["nonce"]}}
        self._refresh(replay_shaped)
        with self.assertRaisesRegex(ValueError, "nonce"):
            validate_host_verifier_receipt_schema(replay_shaped)
        stale_bindings = replace(bindings, nonce=self._sha("next-nonce"))
        with self.assertRaisesRegex(ValueError, "stale binding: nonce"):
            validate_host_verifier_receipt(receipt, stale_bindings)
        fields = (
            "run_capability_sha256", "run_id", "cohort_sha256",
            "rust_project_ir_sha256", "rust_project_interface_sha256",
            "toolchain_sha256",
        )
        for field in fields:
            mutated = {**receipt, field: (
                "run-stale" if field == "run_id" else self._sha(field + "-stale")
            )}
            self._refresh(mutated)
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError, "stale binding"):
                    validate_host_verifier_receipt(mutated, bindings)

    def test_plan_argv_exit_and_termination_are_fixed(self) -> None:
        _bindings, receipt = self._case("project-initialization")
        mutations = (
            ({**receipt, "argv": [*receipt["argv"], "--extra"]}, "fixed argv"),
            ({**receipt, "exit_code": True}, "status/termination/exit code"),
            ({**receipt, "termination": "completed"}, "termination"),
        )
        for mutated, message in mutations:
            self._refresh(mutated)
            with self.subTest(message=message):
                with self.assertRaisesRegex(ValueError, message):
                    validate_host_verifier_receipt_schema(mutated)

    def test_status_termination_and_exit_code_are_consistent(self) -> None:
        _bindings, receipt = self._case("project-initialization")
        mutations = (
            {**receipt, "exit_code": 0},
            {**receipt, "exit_code": None, "termination": "not-started"},
            {**receipt, "exit_code": None, "termination": "timed-out"},
            {**receipt, "exit_code": None, "termination": "signaled"},
            {**receipt, "status": "blocked"},
        )
        for mutated in mutations:
            self._refresh(mutated)
            with self.subTest(
                status=mutated["status"], termination=mutated["termination"],
                exit_code=mutated["exit_code"],
            ):
                with self.assertRaisesRegex(
                    ValueError, "status/termination/exit code",
                ):
                    validate_host_verifier_receipt_schema(mutated)

    def test_receipt_hash_and_raw_content_tamper_are_rejected(self) -> None:
        bindings, receipt = self._case("project-abi")
        changed = {**receipt, "exit_code": 9}
        with self.assertRaisesRegex(ValueError, "content binding"):
            validate_host_verifier_receipt(changed, bindings)
        raw_path = self.root.joinpath(*Path(receipt["stdout_ref"]["path"]).parts)
        raw_path.write_bytes(b"changed-stdout")
        with self.assertRaisesRegex(ValueError, "content binding"):
            reopen_and_validate_host_verifier_receipt(
                self.root, receipt, bindings,
            )

    def test_sandbox_reference_shape_and_file_tamper_are_rejected(self) -> None:
        bindings, receipt = self._case("project-feature-cfg")
        sandbox = receipt["sandbox_receipt"]
        mutations = (
            {**sandbox, "path": "../" + sandbox["path"]},
            {**sandbox, "sha256": "not-a-sha"},
            {**sandbox, "size_bytes": True},
            {**sandbox, "unknown": False},
        )
        for reference in mutations:
            mutated = {**receipt, "sandbox_receipt": reference}
            self._refresh(mutated)
            with self.subTest(reference=reference):
                with self.assertRaises(ValueError):
                    validate_host_verifier_receipt_schema(mutated)
        sandbox_path = self.root.joinpath(*Path(sandbox["path"]).parts)
        data = sandbox_path.read_bytes()
        sandbox_path.write_bytes(b"X" + data[1:])
        with self.assertRaisesRegex(ValueError, "content binding"):
            reopen_and_validate_host_verifier_receipt(
                self.root, receipt, bindings,
            )

    def _case(
        self, gate_kind: str,
    ) -> tuple[HostVerifierEnvelopeBindings, dict[str, object]]:
        bindings = self._bindings(gate_kind)
        stdout, stderr = self._raw_pair(gate_kind)
        receipt = build_host_verifier_receipt(
            bindings, stdout_ref=stdout, stderr_ref=stderr,
            exit_code=7, termination="exited", status="failed",
        )
        return bindings, receipt

    def _bindings(self, gate_kind: str) -> HostVerifierEnvelopeBindings:
        generation = self._sha(f"generation:{gate_kind}")
        requirements = strict_sandbox_requirements()
        plan = SandboxVerificationPlan(
            purpose=gate_kind,
            command=("project-host-verifier", "--gate", gate_kind),
            input_sha256=generation,
            timeout_seconds=300,
            requirements_sha256=requirements.sha256,
            requirements=requirements,
        )
        out_root = self.root.joinpath(*Path(self.evidence_root).parts)
        local = write_content_addressed_json(
            out_root, "host-verifier/sandbox-receipt",
            {"schema_version": 1, "status": "recorded", "gate_kind": gate_kind},
        )
        sandbox = {**local, "path": f"{self.evidence_root}/{local['path']}"}
        return HostVerifierEnvelopeBindings(
            gate_kind=gate_kind,
            run_capability_sha256=self._sha("run-capability"),
            nonce=self._sha("one-time-nonce"),
            run_id="run-host-verifier",
            cohort_sha256=self._sha("cohort"),
            generation_sha256=generation,
            rust_project_ir_sha256=self._sha("rust-project-ir"),
            rust_project_interface_sha256=self._sha("rust-project-interface"),
            verification_plan=plan,
            toolchain_sha256=self._sha("toolchain"),
            sandbox_receipt=sandbox,
            evidence_root=self.evidence_root,
        )

    def _raw_pair(self, gate_kind: str) -> tuple[dict, dict]:
        return tuple(  # type: ignore[return-value]
            write_host_verifier_raw_evidence(
                self.root, self.evidence_root, gate_kind=gate_kind,
                stream=stream, data=f"{gate_kind}:{stream}".encode("ascii"),
            )
            for stream in ("stdout", "stderr")
        )

    @staticmethod
    def _sha(value: str) -> str:
        return hashlib.sha256(value.encode("ascii")).hexdigest()

    @staticmethod
    def _refresh(receipt: dict) -> None:
        receipt["receipt_sha256"] = host_verifier_receipt_sha256(receipt)


if __name__ == "__main__":
    unittest.main()

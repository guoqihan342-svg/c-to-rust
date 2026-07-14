from __future__ import annotations

from copy import deepcopy
import unittest

from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness.project_cargo_evidence import (
    CARGO_COMMANDS, derive_project_cargo_status, project_cargo_observation,
)
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract, canonical_sha256,
)
from validation.tools._project_migration_harness.sandbox_execution_schema import (
    validate_sandbox_execution_evidence,
)
from validation.tools._project_migration_harness.sandbox_probe import (
    make_probe_receipt,
)
from validation.tools._project_migration_harness.sandbox_requirements import (
    cargo_verification_plan,
)


INPUT_SHA256 = "a" * 64


class SandboxExecutionSchemaTests(unittest.TestCase):
    def test_complete_execution_and_project_observation_pass(self) -> None:
        sandbox, check = evidence()
        verified = validate_sandbox_execution_evidence(
            sandbox, check,
            expected_command=CARGO_COMMANDS["cargo-check"],
            expected_input_sha256=INPUT_SHA256,
            expected_purpose="cargo-check",
        )
        self.assertEqual("passed", verified.status)

        observation = project_cargo_observation(
            execution(sandbox, check), check,
            gate_kind="cargo-check",
            expected_input_sha256=INPUT_SHA256,
        )
        self.assertEqual(
            "passed", derive_project_cargo_status("cargo-check", observation),
        )

    def test_old_four_field_observation_cannot_grant_pass(self) -> None:
        with self.assertRaisesRegex(LedgerError, "schema"):
            derive_project_cargo_status("cargo-check", {
                "executed": True,
                "returncode": 0,
                "timed_out": False,
                "sandbox_profile": "os-isolated-v1",
            })

    def test_plan_probe_start_and_cleanup_drift_fail_closed(self) -> None:
        for label, mutate in (
            ("plan", drift_plan),
            ("probe", fail_probe),
            ("start", lambda sandbox, check: check.update(
                sandbox_command_started=False,
            )),
            ("returncode-type", lambda sandbox, check: check.update(
                returncode=False,
            )),
            ("cleanup", lambda sandbox, check: sandbox.update(
                cleanup_verified=False,
            )),
        ):
            with self.subTest(label=label):
                sandbox, check = evidence()
                mutate(sandbox, check)
                with self.assertRaises(ValueError):
                    validate_sandbox_execution_evidence(
                        sandbox, check,
                        expected_command=CARGO_COMMANDS["cargo-check"],
                        expected_input_sha256=INPUT_SHA256,
                        expected_purpose="cargo-check",
                    )

    def test_project_input_drift_cannot_pass(self) -> None:
        sandbox, check = evidence()
        current = execution(sandbox, check)
        current["project_state_after"] = "b" * 64
        observation = project_cargo_observation(
            current, check, gate_kind="cargo-check",
            expected_input_sha256=INPUT_SHA256,
        )
        self.assertEqual("executed", observation["outcome"])
        self.assertEqual(
            "failed", derive_project_cargo_status("cargo-check", observation),
        )

    def test_malformed_execution_becomes_explicit_blocker(self) -> None:
        sandbox, check = evidence()
        check["sandbox_verification_plan_sha256"] = "0" * 64
        observation = project_cargo_observation(
            execution(sandbox, check), check,
            gate_kind="cargo-check",
            expected_input_sha256=INPUT_SHA256,
        )
        self.assertEqual("blocked", observation["outcome"])
        self.assertEqual(
            "failed", derive_project_cargo_status("cargo-check", observation),
        )


def evidence() -> tuple[dict, dict]:
    contract = SandboxContract(
        backend="bubblewrap-v1",
        launcher_sha256="1" * 64,
        toolchain_sha256="2" * 64,
    )
    probe = passing_probe(contract)
    command = CARGO_COMMANDS["cargo-check"]
    plan = cargo_verification_plan(
        "cargo-check", tuple(command), INPUT_SHA256,
        requirements=contract.requirements,
    )
    sandbox = {
        "contract": contract.payload(),
        "contract_sha256": contract.sha256,
        "probe_receipt": probe.payload(),
        "probe_receipt_sha256": probe.sha256,
        "cleanup_verified": True,
    }
    check = {
        "command": command,
        "status": "passed",
        "cargo_executed": True,
        "returncode": 0,
        "timed_out": False,
        "stdout_sha256": "3" * 64,
        "stderr_sha256": "4" * 64,
        "stdout_ref": _raw_ref("cargo-check", "stdout", "3" * 64),
        "stderr_ref": _raw_ref("cargo-check", "stderr", "4" * 64),
        "sandbox_contract_sha256": contract.sha256,
        "sandbox_command_sha256": canonical_sha256(command),
        "sandbox_command_started": True,
        "sandbox_launcher_argv_sha256": "5" * 64,
        "sandbox_requirements_sha256": contract.requirements.sha256,
        "sandbox_verification_plan": plan.payload(),
        "sandbox_verification_plan_sha256": plan.sha256,
        "sandbox_probe_receipt_sha256": probe.sha256,
    }
    return sandbox, check


def _raw_ref(gate: str, stream: str, digest: str) -> dict:
    return {
        "path": (
            f"target/run/verification/raw-output/{gate}/{stream}/{digest}.bin"
        ),
        "sha256": digest,
        "size_bytes": 1,
    }


def execution(sandbox: dict, check: dict) -> dict:
    return {
        "project_input_sha256": INPUT_SHA256,
        "project_state_before": INPUT_SHA256,
        "project_state_after": INPUT_SHA256,
        "project_state_unchanged": True,
        "sandbox": deepcopy(sandbox),
        "checks": [deepcopy(check)],
    }


def passing_probe(contract: SandboxContract):
    return make_probe_receipt(
        contract=contract,
        backend_version="test-only",
        capability_results={name: True for name in contract.requirements.capabilities},
        raw_observation={"fixture": "bounded"},
        cleanup_verified=True,
    )


def drift_plan(_sandbox: dict, check: dict) -> None:
    payload = check["sandbox_verification_plan"]
    payload["input_sha256"] = "b" * 64
    check["sandbox_verification_plan_sha256"] = canonical_sha256(payload)


def fail_probe(sandbox: dict, _check: dict) -> None:
    contract_payload = sandbox["contract"]
    contract = SandboxContract(
        backend=contract_payload["backend"],
        launcher_sha256=contract_payload["launcher_sha256"],
        toolchain_sha256=contract_payload["toolchain_sha256"],
    )
    results = {name: True for name in contract.requirements.capabilities}
    results["network-isolation"] = False
    receipt = make_probe_receipt(
        contract=contract, backend_version="test-only",
        capability_results=results, raw_observation={"fixture": "failed"},
        cleanup_verified=True,
    )
    sandbox["probe_receipt"] = receipt.payload()
    sandbox["probe_receipt_sha256"] = receipt.sha256


if __name__ == "__main__":
    unittest.main()

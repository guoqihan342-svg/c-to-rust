from __future__ import annotations

from dataclasses import replace
import unittest

from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract,
)
from validation.tools._project_migration_harness.sandbox_probe import (
    make_probe_receipt,
    probe_receipt_from_payload,
    validate_probe_receipt,
)
from validation.tools._project_migration_harness.sandbox_requirements import (
    REQUIRED_CAPABILITIES,
    strict_sandbox_requirements,
)


def contract() -> SandboxContract:
    return SandboxContract(
        backend="bubblewrap-v1",
        launcher_sha256="1" * 64,
        toolchain_sha256="2" * 64,
    )


def passing_results() -> dict[str, bool]:
    return {name: True for name in REQUIRED_CAPABILITIES}


class ProjectMigrationSandboxProbeTests(unittest.TestCase):
    def test_receipt_is_deterministic_canonical_and_reopenable(self) -> None:
        selected = contract()
        first = make_probe_receipt(
            contract=selected,
            backend_version="0.11.0",
            capability_results=passing_results(),
            raw_observation={"probe": "bounded", "returncode": 0},
            cleanup_verified=True,
        )
        second = probe_receipt_from_payload(first.payload())

        self.assertEqual(first, second)
        self.assertEqual(first.sha256, second.sha256)
        validate_probe_receipt(second, selected, selected.requirements)

    def test_missing_or_false_capability_fails_closed(self) -> None:
        selected = contract()
        missing = passing_results()
        missing.pop("network-isolation")
        with self.assertRaisesRegex(ValueError, "capability results"):
            make_probe_receipt(
                contract=selected, backend_version="1.0.0",
                capability_results=missing, raw_observation={},
                cleanup_verified=True,
            )
        failed = passing_results()
        failed["network-isolation"] = False
        receipt = make_probe_receipt(
            contract=selected, backend_version="1.0.0",
            capability_results=failed, raw_observation={},
            cleanup_verified=True,
        )
        with self.assertRaisesRegex(ValueError, "did not satisfy"):
            validate_probe_receipt(receipt, selected, selected.requirements)

    def test_contract_and_requirements_drift_are_rejected(self) -> None:
        selected = contract()
        receipt = make_probe_receipt(
            contract=selected, backend_version="1.2.3",
            capability_results=passing_results(), raw_observation={},
            cleanup_verified=True,
        )
        drifted_contract = replace(selected, launcher_sha256="3" * 64)
        with self.assertRaisesRegex(ValueError, "did not satisfy"):
            validate_probe_receipt(
                receipt, drifted_contract, drifted_contract.requirements,
            )
        drifted_requirements = strict_sandbox_requirements(cpu_seconds=60)
        with self.assertRaisesRegex(ValueError, "did not satisfy"):
            validate_probe_receipt(receipt, selected, drifted_requirements)

    def test_cleanup_failure_cannot_produce_a_valid_probe(self) -> None:
        selected = contract()
        receipt = make_probe_receipt(
            contract=selected, backend_version="1.0.0",
            capability_results=passing_results(), raw_observation={},
            cleanup_verified=False,
        )
        with self.assertRaisesRegex(ValueError, "did not satisfy"):
            validate_probe_receipt(receipt, selected, selected.requirements)

    def test_payload_tampering_is_rejected(self) -> None:
        selected = contract()
        receipt = make_probe_receipt(
            contract=selected, backend_version="1.0.0",
            capability_results=passing_results(), raw_observation={},
            cleanup_verified=True,
        )
        payload = receipt.payload()
        payload["backend_version"] = "bad version"
        with self.assertRaises(ValueError):
            probe_receipt_from_payload(payload)


if __name__ == "__main__":
    unittest.main()

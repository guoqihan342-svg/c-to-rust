from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from validation.tools._run_competition_provider_circuit import (
    DEFAULT_SHARED_FAILURE_KINDS,
    ProviderCircuit,
)


class ProviderCircuitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temporary_directory = tempfile.TemporaryDirectory(prefix="provider-circuit-")
        self.root = Path(self._temporary_directory.name)

    def tearDown(self) -> None:
        self._temporary_directory.cleanup()

    def write_manifest(
        self,
        name: str,
        *,
        status: str,
        failure_kind: str | None = None,
    ) -> Path:
        manifest: dict[str, object] = {"status": status}
        if failure_kind is not None:
            manifest["failure"] = {"kind": failure_kind, "message": "test failure"}
        path = self.root / name
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    def attempt(self, circuit: ProviderCircuit, unit_id: str, manifest: Path) -> None:
        self.assertTrue(circuit.request(unit_id))
        circuit.observe_manifest(unit_id, manifest)

    def test_default_shared_failures_include_required_provider_kinds(self) -> None:
        self.assertTrue(
            {
                "provider_timeout",
                "provider_unavailable",
                "provider_invocation_failed",
            }.issubset(DEFAULT_SHARED_FAILURE_KINDS)
        )

    def test_two_consecutive_shared_failures_open_circuit(self) -> None:
        circuit = ProviderCircuit()
        timeout = self.write_manifest(
            "timeout.json", status="blocked", failure_kind="provider_timeout"
        )
        unavailable = self.write_manifest(
            "unavailable.json", status="blocked", failure_kind="provider_unavailable"
        )

        self.attempt(circuit, "unit-a", timeout)
        self.assertFalse(circuit.is_open)
        self.attempt(circuit, "unit-b", unavailable)

        self.assertTrue(circuit.is_open)
        self.assertEqual(
            circuit.summary(),
            {
                "status": "open",
                "threshold": 2,
                "consecutive_failures": 2,
                "failure_kind": "provider_unavailable",
                "requested_slice_specs": 2,
                "attempted_slice_specs": 2,
                "skipped_slice_specs": 0,
                "observations": [
                    {"unit_id": "unit-a", "failure_kind": "provider_timeout"},
                    {"unit_id": "unit-b", "failure_kind": "provider_unavailable"},
                ],
            },
        )

    def test_success_resets_consecutive_failures(self) -> None:
        circuit = ProviderCircuit()
        timeout = self.write_manifest(
            "timeout.json", status="blocked", failure_kind="provider_timeout"
        )
        generated = self.write_manifest("generated.json", status="generated")

        self.attempt(circuit, "unit-a", timeout)
        self.attempt(circuit, "unit-b", generated)
        self.attempt(circuit, "unit-c", timeout)

        summary = circuit.summary()
        self.assertEqual(summary["status"], "closed")
        self.assertEqual(summary["failure_kind"], None)
        self.assertEqual(summary["consecutive_failures"], 1)
        self.assertEqual(
            summary["observations"],
            [{"unit_id": "unit-c", "failure_kind": "provider_timeout"}],
        )

    def test_non_shared_failure_resets_consecutive_failures(self) -> None:
        circuit = ProviderCircuit()
        timeout = self.write_manifest(
            "timeout.json", status="blocked", failure_kind="provider_timeout"
        )
        candidate_failure = self.write_manifest(
            "candidate.json", status="blocked", failure_kind="candidate_invalid"
        )

        self.attempt(circuit, "unit-a", timeout)
        self.attempt(circuit, "unit-b", candidate_failure)
        self.attempt(circuit, "unit-c", timeout)

        self.assertEqual(circuit.summary()["status"], "closed")
        self.assertEqual(circuit.summary()["consecutive_failures"], 1)

    def test_missing_and_malformed_manifests_do_not_open_circuit(self) -> None:
        malformed_paths = {
            "missing": self.root / "missing.json",
            "invalid-json": self.root / "invalid.json",
            "non-object": self.root / "list.json",
            "missing-failure": self.root / "missing-failure.json",
            "invalid-kind": self.root / "invalid-kind.json",
        }
        malformed_paths["invalid-json"].write_text("{", encoding="utf-8")
        malformed_paths["non-object"].write_text("[]", encoding="utf-8")
        malformed_paths["missing-failure"].write_text(
            json.dumps({"status": "blocked"}), encoding="utf-8"
        )
        malformed_paths["invalid-kind"].write_text(
            json.dumps({"status": "blocked", "failure": {"kind": 42}}),
            encoding="utf-8",
        )

        for label, path in malformed_paths.items():
            with self.subTest(label=label):
                circuit = ProviderCircuit(threshold=1)
                self.attempt(circuit, label, path)
                self.assertEqual(circuit.summary()["status"], "closed")
                self.assertEqual(circuit.summary()["consecutive_failures"], 0)

    def test_open_circuit_counts_requested_attempted_and_skipped_units(self) -> None:
        circuit = ProviderCircuit()
        failed = self.write_manifest(
            "failed.json", status="blocked", failure_kind="provider_invocation_failed"
        )

        self.attempt(circuit, "unit-a", failed)
        self.attempt(circuit, "unit-b", failed)
        self.assertFalse(circuit.request("unit-c"))
        self.assertFalse(circuit.request("unit-d"))

        summary = circuit.summary()
        self.assertEqual(summary["requested_slice_specs"], 4)
        self.assertEqual(summary["attempted_slice_specs"], 2)
        self.assertEqual(summary["skipped_slice_specs"], 2)

    def test_summary_is_json_serializable_and_returns_detached_observations(self) -> None:
        circuit = ProviderCircuit()
        failed = self.write_manifest(
            "failed.json", status="blocked", failure_kind="provider_timeout"
        )
        self.attempt(circuit, "unit-a", failed)

        summary = circuit.summary()
        json.dumps(summary)
        summary["observations"].clear()

        self.assertEqual(circuit.summary()["consecutive_failures"], 1)
        self.assertEqual(len(circuit.summary()["observations"]), 1)

    def test_custom_threshold_and_shared_failure_kind_are_supported(self) -> None:
        circuit = ProviderCircuit(
            threshold=3,
            shared_failure_kinds={"provider_rate_limited"},
        )
        failed = self.write_manifest(
            "failed.json", status="blocked", failure_kind="provider_rate_limited"
        )

        for index in range(3):
            self.attempt(circuit, f"unit-{index}", failed)

        self.assertEqual(circuit.summary()["status"], "open")
        self.assertEqual(circuit.summary()["threshold"], 3)


if __name__ == "__main__":
    unittest.main()

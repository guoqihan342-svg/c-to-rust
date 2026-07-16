from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest import mock

from validation.tools._project_migration_harness.project_cargo_evidence import (
    CARGO_COMMANDS,
)
from validation.tools._project_migration_harness.project_cargo_verifier import (
    verify_project_cargo,
)


MODULE = "validation.tools._project_migration_harness.project_cargo_verifier"


class ProjectCargoTopologyGateTests(unittest.TestCase):
    def test_v3_requires_structure_capture_and_ready_topology(self) -> None:
        result, cargo_runner, topology = self._verify("blocked")

        self.assertEqual("blocked", result["status"])
        self.assertTrue(cargo_runner.call_args.kwargs["capture_cargo_facts"])
        self.assertTrue(cargo_runner.call_args.kwargs["capture_cargo_structure"])
        topology.assert_called_once()

    def test_ready_v3_topology_preserves_passed_cargo_gates(self) -> None:
        result, _cargo_runner, _topology = self._verify("ready")

        self.assertEqual("passed", result["status"])
        self.assertEqual(
            ["passed", "passed"],
            [item["gate_status"] for item in result["records"]],
        )

    def _verify(self, topology_status: str):
        temporary = tempfile.TemporaryDirectory(prefix="topology-gate-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        database = root / "state" / "project-migration.sqlite3"
        database.parent.mkdir()
        database.touch()
        ledger = mock.MagicMock(path=database)
        ledger.bind_current_candidate_set.return_value = "c" * 64
        context = {
            "project_input_sha256": "d" * 64,
            "rust_project_ir": {
                "schema_version": 3, "ir_sha256": "e" * 64,
                "interface_sha256": "f" * 64,
                "native_link_requirements": [],
            },
        }
        checks = [{
            "command": CARGO_COMMANDS[f"cargo-{stage}"],
            "status": "passed", "diagnostics": [],
        } for stage in ("check", "test")]
        execution = {"status": "passed", "checks": checks}
        cargo_runner = mock.Mock(return_value=execution)
        topology = mock.Mock(return_value={
            "status": topology_status,
            **({"reference": {"path": "verification/x", "sha256": "1" * 64,
                                "size_bytes": 1}} if topology_status == "ready" else {}),
        })
        identity = lambda value, **_kwargs: value
        with (
            mock.patch(f"{MODULE}.current_candidate_members", return_value=[{
                "unit_id": "unit", "artifact_id": "candidate",
                "content_sha256": "a" * 64,
            }]),
            mock.patch(f"{MODULE}.load_migration_contract", return_value=({}, {})),
            mock.patch(f"{MODULE}.load_managed_project_context", return_value=context),
            mock.patch(f"{MODULE}.run_cargo_project_gates", cargo_runner),
            mock.patch(f"{MODULE}.persist_captured_rust_products", side_effect=identity),
            mock.patch(f"{MODULE}.persist_captured_native_link_trace", side_effect=identity),
            mock.patch(f"{MODULE}.persist_captured_cargo_outputs", side_effect=identity),
            mock.patch(f"{MODULE}.materialize_project_rust_cargo_topology", topology),
            mock.patch(f"{MODULE}.project_cargo_observation", return_value={
                "outcome": "executed",
            }),
            mock.patch(f"{MODULE}.record_host_project_observation", side_effect=(
                lambda **values: {
                    "gate_status": "passed", "record_id": values["gate_kind"],
                }
            )),
            mock.patch(f"{MODULE}.settle_cargo_native_links", return_value={
                "status": "not-required",
            }),
        ):
            result = verify_project_cargo(
                ledger=ledger, run_id="run", project_root=root / "project",
                runtime_root=root / "runtime", out_root=root,
                out_root_rel="target/run",
            )
        return result, cargo_runner, topology


if __name__ == "__main__":
    unittest.main()

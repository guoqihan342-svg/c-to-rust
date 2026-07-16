from __future__ import annotations

import copy
from pathlib import Path
import tempfile
import unittest

from validation.tools._project_migration_harness.cargo_fact_commands import (
    CARGO_BUILD_COMMAND, CARGO_METADATA_COMMAND,
)
from validation.tools._project_migration_harness.cargo_raw_output_evidence import (
    write_cargo_raw_output,
)
from validation.tools._project_migration_harness.project_rust_cargo_topology import (
    materialize_project_rust_cargo_topology,
    reopen_project_rust_cargo_topology,
)
from validation.tools._project_migration_harness.rust_cargo_topology_ir import (
    derive_rust_cargo_topology_expectation,
)
from validation.tools._project_migration_harness.rust_product_evidence import (
    persist_captured_rust_products,
)
from validation.tools._project_migration_harness.rustc_dep_info_evidence import (
    persist_captured_rustc_dep_info,
)
from validation.tools.project_migration_rust_cargo_topology_test_support import (
    captured_dep_info as _captured_dep_info,
    captured_products as _captured_products,
    check as _check,
    compiler_raw as _compiler_raw,
    metadata_raw as _metadata_raw,
)
from validation.tools.project_migration_rust_project_cargo_v3_test_support import (
    direct_two_package_ir,
)


class ProjectRustCargoTopologyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="project-topology-")
        self.addCleanup(self.temporary.cleanup)
        self.harness = Path(self.temporary.name)
        self.out_root = self.harness / "target" / "run"
        self.database = self.out_root / "state" / "project-migration.sqlite3"
        self.database.parent.mkdir(parents=True)
        self.database.touch()
        self.ir, _sources = direct_two_package_ir()
        self.expectation = derive_rust_cargo_topology_expectation(self.ir)
        self.project_input = "d" * 64
        self.candidate_set = "c" * 64

    def test_materialized_topology_reopens_from_bound_raw_outputs(self) -> None:
        result = self._materialize()

        self.assertEqual("ready", result["status"])
        self.assertTrue(
            result["receipt"]["coverage"]["rust_project_ir_alignment_complete"],
        )
        reopened = reopen_project_rust_cargo_topology(
            ledger_path=self.database, reference=result["reference"],
            run_id="run", candidate_set_sha256=self.candidate_set,
            project_input_sha256=self.project_input,
            rust_project_ir=self.ir,
        )
        self.assertEqual(result["receipt"], reopened)

    def test_metadata_target_drift_blocks_even_when_compiler_agrees(self) -> None:
        facts = copy.deepcopy(self.expectation["facts"])
        facts["packages"][0]["targets"][0]["name"] = "forged-target"
        facts["workspace_members"] = copy.deepcopy(facts["packages"])
        facts["default_members"] = [copy.deepcopy(facts["packages"][0])]

        result = self._materialize(facts=facts)

        self.assertEqual("blocked", result["status"])
        self.assertIn(
            "rust_cargo_ir_package_target_set_mismatch",
            {item["code"] for item in result["receipt"]["blockers"]},
        )

    def test_fresh_compiler_artifact_cannot_satisfy_clean_build_witness(self) -> None:
        result = self._materialize(fresh=True)

        self.assertEqual("blocked", result["status"])
        self.assertIn(
            "rust_cargo_compiler_artifact_fresh",
            {item["code"] for item in result["receipt"]["blockers"]},
        )

    def test_raw_output_drift_breaks_topology_reopen(self) -> None:
        result = self._materialize()
        raw = result["receipt"]["raw_sources"]["cargo_build_stdout"]
        target = self.harness.joinpath(*raw["path"].split("/"))
        with target.open("ab") as handle:
            handle.write(b"\n")

        with self.assertRaisesRegex(Exception, "Cargo raw output"):
            reopen_project_rust_cargo_topology(
                ledger_path=self.database, reference=result["reference"],
                run_id="run", candidate_set_sha256=self.candidate_set,
                project_input_sha256=self.project_input,
            )

    def _materialize(
        self, *, facts: dict | None = None, fresh: bool = False,
    ) -> dict:
        selected = facts or self.expectation["facts"]
        metadata_raw = _metadata_raw(selected)
        compiler_raw = _compiler_raw(selected, self.ir, fresh=fresh)
        metadata_ref = write_cargo_raw_output(
            self.out_root, "target/run", gate_kind="cargo-metadata",
            stream="stdout", data=metadata_raw,
        )
        check_ref = write_cargo_raw_output(
            self.out_root, "target/run", gate_kind="cargo-build",
            stream="stdout", data=compiler_raw,
        )
        execution = {
            "status": "passed",
            "project_input_sha256": self.project_input,
            "project_state_unchanged": True,
            "fact_probes": {"cargo-metadata": _check(
                list(CARGO_METADATA_COMMAND), metadata_raw, metadata_ref,
            )},
            "structure_probes": {"cargo-build": _check(
                list(CARGO_BUILD_COMMAND), compiler_raw, check_ref,
            )},
            "_captured_rust_products": _captured_products(selected, self.ir),
            "_captured_rustc_dep_info": _captured_dep_info(selected, self.ir),
        }
        execution = persist_captured_rust_products(
            execution, out_root=self.out_root, required=True,
        )
        execution = persist_captured_rustc_dep_info(
            execution, out_root=self.out_root, required=True,
        )
        return materialize_project_rust_cargo_topology(
            ledger_path=self.database, out_root=self.out_root,
            run_id="run", candidate_set_sha256=self.candidate_set,
            context={
                "project_input_sha256": self.project_input,
                "rust_project_ir": self.ir,
            },
            execution=execution,
        )

if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile
import unittest

from validation.tools._project_migration_harness.cargo_raw_output_evidence import (
    persist_captured_cargo_outputs,
)
from validation.tools._project_migration_harness.project_rust_cargo_topology import (
    materialize_project_rust_cargo_topology,
)
from validation.tools._project_migration_harness.project_verification import (
    run_cargo_generation_gates,
)
from validation.tools._project_migration_harness.rust_link_product_inspection import (
    inspect_rust_link_product,
)
from validation.tools._project_migration_harness.rust_project_cargo import (
    reconstruct_cargo_project_from_ir,
)
from validation.tools._project_migration_harness.rust_product_evidence import (
    persist_captured_rust_products,
)
from validation.tools.project_migration_rust_project_cargo_v3_test_support import (
    V3CargoFixture,
)


LIVE_SANDBOX = (
    os.name == "posix" and shutil.which("cargo") is not None
    and shutil.which("bwrap") is not None
)


@unittest.skipUnless(LIVE_SANDBOX, "Linux Cargo+bwrap sandbox is unavailable")
class RustProjectCargoV3StructureLiveTests(unittest.TestCase):
    def test_static_library_build_product_is_captured_before_cleanup(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargo-v3-structure-") as temporary:
            root = Path(temporary)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            fixture = V3CargoFixture(artifacts)
            self.addCleanup(fixture.close)
            ir = fixture.build("pub fn value() -> i32 { 7 }\n")
            plan = reconstruct_cargo_project_from_ir(ir, artifacts)
            project = root / "project"
            _materialize(project, plan.files)

            result = run_cargo_generation_gates(
                project, runtime_root=root / "runtime", timeout_seconds=120,
                capture_raw_output=True, capture_cargo_facts=True,
                capture_cargo_structure=True,
            )

            out_root = root / "target" / "run"
            database = out_root / "state" / "project-migration.sqlite3"
            database.parent.mkdir(parents=True)
            database.touch()
            persisted = persist_captured_cargo_outputs(
                persist_captured_rust_products(
                    result, out_root=out_root, required=True,
                ),
                out_root=out_root, out_root_rel="target/run",
            )
            topology = materialize_project_rust_cargo_topology(
                ledger_path=database, out_root=out_root,
                run_id="run", candidate_set_sha256="c" * 64,
                context={
                    "project_input_sha256": result["project_input_sha256"],
                    "rust_project_ir": ir,
                },
                execution=persisted,
            )

        self.assertEqual("passed", result["status"], result["diagnostics"])
        self.assertEqual("ready", topology["status"], topology["receipt"]["blockers"])
        self.assertEqual(
            2, topology["receipt"]["coverage"]["inspected_product_count"],
        )
        self.assertEqual(
            "build", result["structure_probes"]["cargo-build"]["command"][1],
        )
        products = result["_captured_rust_products"]
        self.assertEqual(
            ["rlib", "staticlib"],
            [item["product_kind"] for item in products],
        )
        for product in products:
            inspection = inspect_rust_link_product(
                product["data"], product["product_kind"],
            )
            self.assertEqual("unix-ar", inspection["object_format"])
        self.assertEqual([], list((root / "runtime").glob("cargo-sandbox-*")))

    def test_binary_link_trace_is_target_bound_and_reopened(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cargo-v3-link-") as temporary:
            root = Path(temporary)
            artifacts = root / "artifacts"
            artifacts.mkdir()
            fixture = V3CargoFixture(artifacts)
            self.addCleanup(fixture.close)
            ir = fixture.build("fn main() {}\n", product="link")
            plan = reconstruct_cargo_project_from_ir(ir, artifacts)
            project = root / "project"
            _materialize(project, plan.files)

            result = run_cargo_generation_gates(
                project, runtime_root=root / "runtime", timeout_seconds=120,
                capture_raw_output=True, capture_cargo_facts=True,
                capture_cargo_structure=True,
            )
            out_root = root / "target" / "run"
            database = out_root / "state" / "project-migration.sqlite3"
            database.parent.mkdir(parents=True)
            database.touch()
            persisted = persist_captured_cargo_outputs(
                persist_captured_rust_products(
                    result, out_root=out_root, required=True,
                ),
                out_root=out_root, out_root_rel="target/run",
            )
            topology = materialize_project_rust_cargo_topology(
                ledger_path=database, out_root=out_root,
                run_id="run", candidate_set_sha256="c" * 64,
                context={
                    "project_input_sha256": result["project_input_sha256"],
                    "rust_project_ir": ir,
                },
                execution=persisted,
            )

        self.assertEqual("passed", result["status"], result["diagnostics"])
        self.assertEqual("ready", topology["status"], topology["receipt"]["blockers"])
        link = topology["receipt"]["link_order_witness"]
        self.assertEqual("required", link["mode"])
        self.assertEqual(1, link["coverage"]["expected_link_target_count"])
        self.assertEqual(1, link["coverage"]["observed_link_target_count"])
        self.assertEqual(
            ["bin"], [item["product_kind"]
                      for item in result["_captured_rust_products"]],
        )
        self.assertEqual([], list((root / "runtime").glob("cargo-sandbox-*")))


def _materialize(root: Path, files) -> None:
    for relative, data in files.items():
        target = root.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


if __name__ == "__main__":
    unittest.main()

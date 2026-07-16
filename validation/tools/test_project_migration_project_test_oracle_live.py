from __future__ import annotations

import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.project_test_mapping import (
    derive_project_test_mapping,
)
from validation.tools._project_migration_harness.project_test_oracle_runner import (
    run_project_test_oracle,
)
from validation.tools.project_migration_rust_project_cargo_v3_test_support import (
    direct_two_package_ir,
)


LIVE = os.environ.get("C2R_LIVE_PROJECT_ORACLE") == "1"


@unittest.skipUnless(
    LIVE and os.name == "posix" and shutil.which("cc"),
    "explicit Linux project-oracle live gate",
)
class ProjectTestOracleLiveTests(unittest.TestCase):
    def test_same_input_c_and_rust_programs_match_in_bubblewrap(self) -> None:
        with tempfile.TemporaryDirectory(prefix="project-oracle-live-") as temporary:
            root = Path(temporary)
            source = root / "source"
            generation = root / "generation"
            runtime = root / "runtime"
            binary = source / "build" / "suite"
            binary.parent.mkdir(parents=True)
            c_source = source / "suite.c"
            c_source.write_text(
                '#include <stdio.h>\nint main(void) { puts("logic-ok"); return 0; }\n',
                encoding="ascii",
            )
            completed = subprocess.run(
                [shutil.which("cc"), str(c_source), "-o", str(binary)],
                capture_output=True, check=False, timeout=30,
            )
            self.assertEqual(0, completed.returncode, completed.stderr.decode())
            ir, _sources = direct_two_package_ir()
            _write_generation(generation)
            inventory = _inventory(source, binary)
            mapping = derive_project_test_mapping(inventory, ir)
            self.assertEqual("ready", mapping["status"])

            result = run_project_test_oracle(
                repo_root=source, generation_root=generation,
                runtime_root=runtime, rust_project_ir=ir,
                inventory=inventory, mapping=mapping, timeout_seconds=120,
            )

            self.assertEqual("passed", result["status"], result)
            self.assertTrue(result["cleanup_verified"])
            self.assertEqual({
                "case_count": 1, "mismatch_count": 0, "crash_count": 0,
            }, {
                key: result["observation"][key]
                for key in ("case_count", "mismatch_count", "crash_count")
            })

    def test_compiling_rust_with_wrong_logic_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="project-oracle-mismatch-") as temporary:
            root = Path(temporary)
            source = root / "source"
            generation = root / "generation"
            runtime = root / "runtime"
            binary = source / "build" / "suite"
            binary.parent.mkdir(parents=True)
            c_source = source / "suite.c"
            c_source.write_text(
                '#include <stdio.h>\nint main(void) { puts("logic-ok"); return 0; }\n',
                encoding="ascii",
            )
            completed = subprocess.run(
                [shutil.which("cc"), str(c_source), "-o", str(binary)],
                capture_output=True, check=False, timeout=30,
            )
            self.assertEqual(0, completed.returncode, completed.stderr.decode())
            ir, _sources = direct_two_package_ir()
            _write_generation(generation, binary_output="wrong-logic")
            inventory = _inventory(source, binary)
            mapping = derive_project_test_mapping(inventory, ir)
            self.assertEqual("ready", mapping["status"])

            result = run_project_test_oracle(
                repo_root=source, generation_root=generation,
                runtime_root=runtime, rust_project_ir=ir,
                inventory=inventory, mapping=mapping, timeout_seconds=120,
            )

            self.assertEqual("failed", result["status"], result)
            self.assertTrue(result["cleanup_verified"])
            self.assertEqual(1, result["observation"]["case_count"])
            self.assertEqual(1, result["observation"]["mismatch_count"])
            self.assertEqual(0, result["observation"]["crash_count"])
            self.assertEqual("test-live", result["evidence"]["failure_details"][0]["test_id"])

    def test_matching_nonzero_failures_cannot_pass_as_equivalent(self) -> None:
        with tempfile.TemporaryDirectory(prefix="project-oracle-baseline-fail-") as temporary:
            root = Path(temporary)
            source = root / "source"
            generation = root / "generation"
            runtime = root / "runtime"
            binary = source / "build" / "suite"
            binary.parent.mkdir(parents=True)
            c_source = source / "suite.c"
            c_source.write_text("int main(void) { return 7; }\n", encoding="ascii")
            completed = subprocess.run(
                [shutil.which("cc"), str(c_source), "-o", str(binary)],
                capture_output=True, check=False, timeout=30,
            )
            self.assertEqual(0, completed.returncode, completed.stderr.decode())
            ir, _sources = direct_two_package_ir()
            _write_generation(generation, binary_source="fn main() { std::process::exit(7); }\n")
            inventory = _inventory(source, binary)
            mapping = derive_project_test_mapping(inventory, ir)

            result = run_project_test_oracle(
                repo_root=source, generation_root=generation,
                runtime_root=runtime, rust_project_ir=ir,
                inventory=inventory, mapping=mapping, timeout_seconds=120,
            )

            self.assertEqual("blocked", result["status"], result)
            self.assertEqual("project_test_oracle_baseline_failed", result["reason_code"])
            self.assertEqual(7, result["process"]["exit_code"])

    def test_rust_candidate_cannot_forward_hidden_c_oracle_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="project-oracle-isolation-") as temporary:
            root = Path(temporary)
            source = root / "source"
            generation = root / "generation"
            runtime = root / "runtime"
            binary = source / "build" / "suite"
            binary.parent.mkdir(parents=True)
            c_source = source / "suite.c"
            c_source.write_text(
                '#include <stdio.h>\nint main(void) { puts("logic-ok"); return 0; }\n',
                encoding="ascii",
            )
            completed = subprocess.run(
                [shutil.which("cc"), str(c_source), "-o", str(binary)],
                capture_output=True, check=False, timeout=30,
            )
            self.assertEqual(0, completed.returncode, completed.stderr.decode())
            ir, _sources = direct_two_package_ir()
            _write_generation(
                generation,
                binary_source=(
                    'use std::process::Command;\nfn main() {\n'
                    '  let output = Command::new("/runtime/oracle-source/build/suite")\n'
                    '      .output().expect("oracle should be hidden");\n'
                    '  print!("{}", String::from_utf8_lossy(&output.stdout));\n}\n'
                ),
            )
            inventory = _inventory(source, binary)
            mapping = derive_project_test_mapping(inventory, ir)

            result = run_project_test_oracle(
                repo_root=source, generation_root=generation,
                runtime_root=runtime, rust_project_ir=ir,
                inventory=inventory, mapping=mapping, timeout_seconds=120,
            )

            self.assertEqual("failed", result["status"], result)
            self.assertEqual(1, result["observation"]["mismatch_count"])
            self.assertFalse(result["isolation"]["source_executable_visible_to_replay"])


def _write_generation(
    root: Path, *, binary_output: str = "logic-ok", binary_source: str | None = None,
) -> None:
    binary = root / "packages" / "package-bin"
    library = root / "packages" / "package-lib"
    (binary / "src").mkdir(parents=True)
    (library / "src").mkdir(parents=True)
    (binary / "Cargo.toml").write_text(
        '[package]\nname = "package_bin"\nversion = "0.0.0"\n'
        'edition = "2021"\nautobins = false\n\n'
        '[[bin]]\nname = "target_bin"\npath = "src/main.rs"\n',
        encoding="ascii",
    )
    (binary / "src" / "main.rs").write_text(
        binary_source or f'fn main() {{ println!("{binary_output}"); }}\n',
        encoding="ascii",
    )
    (library / "Cargo.toml").write_text(
        '[package]\nname = "package_lib"\nversion = "0.0.0"\n'
        'edition = "2021"\n\n[lib]\nname = "target_lib"\npath = "src/lib.rs"\n',
        encoding="ascii",
    )
    (library / "src" / "lib.rs").write_text(
        "pub fn value() -> i32 { 7 }\n", encoding="ascii",
    )


def _inventory(root: Path, binary: Path) -> dict:
    data = binary.read_bytes()
    test = {
        "source_index": 0, "name": "suite",
        "source_target_id": "build-target-bin",
        "source_executable": {
            "path": binary.relative_to(root).as_posix(), "kind": "file",
            "materialized": True, "sha256": hashlib.sha256(data).hexdigest(),
            "size_bytes": len(data),
        },
        "arguments": [], "working_directory": "build", "environment": {},
        "timeout_seconds": 30, "test_id": "test-live",
    }
    value = {
        "schema_version": 1, "artifact_kind": "project-test-inventory",
        "status": "ready", "adapter": "ctest-json-v1",
        "source_observation": {
            "path": "plan/ctest.json", "sha256": "b" * 64,
            "size_bytes": 1,
        },
        "build_directory": "build", "tests": [test], "blockers": [],
        "claim_boundary": {
            "semantic_gate": False, "translation_coverage_numerator": 0,
        },
    }
    value["inventory_sha256"] = content_sha256(value)
    return value


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import hashlib
import json
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
from validation.tools.project_migration_rust_project_cargo_v3_test_support import (
    direct_two_package_ir,
)
from validation.tools.project_migration_rust_link_product_test_support import (
    ET_DYN, ET_EXEC, ar_member, archive, elf_product, relocatable_elf,
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
        compiler_raw = _compiler_raw(selected, fresh=fresh)
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
            "_captured_rust_products": _captured_products(selected),
        }
        execution = persist_captured_rust_products(
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


def _check(command: list[str], raw: bytes, reference: dict) -> dict:
    return {
        "command": list(command), "status": "passed",
        "stdout_sha256": hashlib.sha256(raw).hexdigest(),
        "stdout_ref": reference,
    }


def _metadata_raw(facts: dict) -> bytes:
    packages = []
    identities = []
    for package in facts["packages"]:
        identity = _package_id(package["name"])
        identities.append(identity)
        packages.append({
            "id": identity, "name": package["name"],
            "version": package["version"], "features": {},
            "targets": [{
                "name": target["name"], "kind": target["kind"],
                "crate_types": target["crate_types"],
                "required-features": target["required_features"],
            } for target in package["targets"]],
        })
    defaults = {
        (item["name"], item["version"]) for item in facts["default_members"]
    }
    root = {
        "metadata": None, "packages": packages, "resolve": None,
        "target_directory": "/workspace/target", "version": 1,
        "workspace_default_members": [
            identity for identity, package in zip(identities, packages, strict=True)
            if (package["name"], package["version"]) in defaults
        ],
        "workspace_members": identities, "workspace_root": "/workspace",
    }
    return _json(root)


def _compiler_raw(facts: dict, *, fresh: bool) -> bytes:
    events = []
    for package in facts["packages"]:
        for target in package["targets"]:
            filename = f"/workspace/target/debug/{target['name']}.rmeta"
            compiler_target = {
                "kind": target["kind"], "crate_types": target["crate_types"],
                "name": target["name"],
                "src_path": f"/workspace/{package['name']}/src/root.rs",
                "edition": "2021", "doc": True,
                "doctest": True, "test": True,
            }
            artifact = {
                "reason": "compiler-artifact",
                "package_id": _package_id(package["name"]),
                "manifest_path": f"/workspace/{package['name']}/Cargo.toml",
                "target": compiler_target,
                "profile": {
                    "opt_level": "0", "debuginfo": 2,
                    "debug_assertions": True, "overflow_checks": True,
                    "test": False,
                },
                "features": [], "filenames": [filename],
                "executable": None, "fresh": fresh,
            }
            events.append(artifact)
            if set(target["kind"]) & {"bin", "cdylib"}:
                events.append({
                    "reason": "compiler-message",
                    "package_id": artifact["package_id"],
                    "manifest_path": artifact["manifest_path"],
                    "target": compiler_target,
                    "message": {
                        "level": "warning", "code": {"code": "linker_messages"},
                        "message": "linker stdout: /usr/lib/crt1.o\n",
                    },
                })
    events.append({"reason": "build-finished", "success": True})
    return b"".join(_json(event) + b"\n" for event in events)


def _captured_products(facts: dict) -> list[dict]:
    result = []
    for package in facts["packages"]:
        for target in package["targets"]:
            compiler_target = {
                "kind": target["kind"], "crate_types": target["crate_types"],
                "name": target["name"],
                "src_path": f"/workspace/{package['name']}/src/root.rs",
                "edition": "2021", "doc": True,
                "doctest": True, "test": True,
            }
            kinds = set(target["crate_types"]) & {
                "bin", "cdylib", "rlib", "staticlib",
            }
            if "lib" in target["crate_types"] and "rlib" not in kinds:
                kinds.add("rlib")
            for kind in sorted(kinds):
                guest = f"/runtime/target/debug/{package['name']}-{kind}"
                result.append({
                    "package_id": _package_id(package["name"]),
                    "target": compiler_target, "product_kind": kind,
                    "guest_path_sha256": hashlib.sha256(
                        guest.encode("utf-8"),
                    ).hexdigest(),
                    "data": _product_bytes(kind),
                })
    return result


def _product_bytes(kind: str) -> bytes:
    relocatable = relocatable_elf()
    if kind == "staticlib":
        return archive(ar_member("unit.o/", relocatable))
    if kind == "rlib":
        return archive(
            ar_member("lib.rmeta/", relocatable),
            ar_member("unit.o/", relocatable + b"code"),
        )
    if kind == "cdylib":
        return elf_product(ET_DYN, executable_entry=False)
    return elf_product(ET_EXEC)


def _package_id(name: str) -> str:
    return f"path+file:///workspace/{name}#{name}@0.0.0"


def _json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


if __name__ == "__main__":
    unittest.main()

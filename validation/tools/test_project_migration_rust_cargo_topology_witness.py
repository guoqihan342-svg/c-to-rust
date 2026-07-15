from __future__ import annotations

import copy
import json
import unittest

from validation.tools._project_migration_harness.cargo_compiler_artifact_evidence import (
    parse_cargo_compiler_artifact_evidence,
)
from validation.tools._project_migration_harness.cargo_metadata_fact_evidence import (
    parse_cargo_metadata_fact_evidence,
)
from validation.tools._project_migration_harness.rust_cargo_topology_witness import (
    build_rust_cargo_topology_witness,
    validate_rust_cargo_topology_witness,
)


class RustCargoTopologyWitnessTests(unittest.TestCase):
    def test_featureless_workspace_target_matrix_is_ready_and_portable(self) -> None:
        metadata = _metadata()
        compiler = _compiler(_artifact())
        witness = build_rust_cargo_topology_witness(metadata, compiler)

        self.assertEqual("ready", witness["status"])
        self.assertTrue(witness["coverage"]["module_target_ownership_complete"])
        self.assertTrue(witness["coverage"]["feature_matrix_complete"])
        self.assertEqual("neutral-package", witness["packages"][0]["package"]["name"])
        self.assertEqual(1, witness["packages"][0]["targets"][0]["artifact_count"])
        serialized = json.dumps(witness, sort_keys=True)
        self.assertNotIn("/workspace", serialized)
        self.assertNotIn("C:/", serialized)
        self.assertFalse(witness["claim_boundary"]["section_closure"])
        self.assertEqual(
            witness,
            validate_rust_cargo_topology_witness(witness, metadata, compiler),
        )

    def test_featureful_workspace_requires_more_than_all_features_lane(self) -> None:
        features = {"default": ["fast"], "fast": []}
        metadata = _metadata(features=features)
        compiler = _compiler(_artifact(features=["default", "fast"]))
        witness = build_rust_cargo_topology_witness(metadata, compiler)

        self.assertEqual("blocked", witness["status"])
        self.assertFalse(witness["coverage"]["feature_matrix_complete"])
        self.assertIn(
            "rust_cargo_feature_matrix_lanes_missing",
            {item["code"] for item in witness["blockers"]},
        )

    def test_missing_extra_and_ambiguous_workspace_targets_block(self) -> None:
        metadata = _metadata(extra_target=True)
        wrong = _artifact(name="undeclared", kind=["bin"], crate_types=["bin"])
        duplicate_identity = _artifact(package_id=(
            "registry+https://example.invalid/index#neutral-package@0.1.0"
        ))
        witness = build_rust_cargo_topology_witness(
            metadata,
            _compiler(wrong, duplicate_identity),
        )
        codes = {item["code"] for item in witness["blockers"]}
        self.assertEqual("blocked", witness["status"])
        self.assertIn("rust_cargo_package_identity_ambiguous", codes)
        self.assertIn("rust_cargo_target_artifact_missing", codes)
        self.assertIn("rust_cargo_workspace_target_undeclared", codes)

    def test_all_features_mismatch_and_unparseable_package_id_block(self) -> None:
        metadata = _metadata(features={"fast": []})
        witness = build_rust_cargo_topology_witness(
            metadata,
            _compiler(
                _artifact(features=[]),
                _artifact(package_id="opaque-package-id", name="dependency"),
            ),
        )
        codes = {item["code"] for item in witness["blockers"]}
        self.assertIn("rust_cargo_all_features_observation_mismatch", codes)
        self.assertIn("rust_cargo_compiler_package_id_unparseable", codes)
        self.assertFalse(witness["coverage"]["feature_matrix_complete"])
        details = [
            item["detail"] for item in witness["blockers"]
            if item["code"] == "rust_cargo_compiler_package_id_unparseable"
        ]
        self.assertEqual(64, len(details[0]))
        self.assertNotIn("opaque", json.dumps(witness))

    def test_duplicate_declared_target_identity_blocks_without_silent_collapse(self) -> None:
        witness = build_rust_cargo_topology_witness(
            _metadata(duplicate_target=True), _compiler(_artifact()),
        )
        self.assertIn(
            "rust_cargo_declared_target_duplicate",
            {item["code"] for item in witness["blockers"]},
        )
        self.assertFalse(witness["coverage"]["module_target_ownership_complete"])

    def test_recomputed_witness_rejects_self_consistent_tamper(self) -> None:
        metadata = _metadata()
        compiler = _compiler(_artifact())
        witness = build_rust_cargo_topology_witness(metadata, compiler)
        forged = copy.deepcopy(witness)
        forged["packages"][0]["targets"][0]["artifact_count"] = 2
        with self.assertRaisesRegex(ValueError, "source_drifted"):
            validate_rust_cargo_topology_witness(forged, metadata, compiler)


def _metadata(
    *, features: dict[str, list[str]] | None = None,
    extra_target: bool = False, duplicate_target: bool = False,
) -> dict:
    targets = [_metadata_target()]
    if duplicate_target:
        targets.append(_metadata_target())
    if extra_target:
        targets.append(_metadata_target(
            name="tool", kind=["bin"], crate_types=["bin"],
        ))
    package_id = "path+file:///workspace/pkg#neutral-package@0.1.0"
    root = {
        "metadata": None,
        "packages": [{
            "id": package_id,
            "name": "neutral-package",
            "version": "0.1.0",
            "features": features or {},
            "targets": targets,
        }],
        "resolve": None,
        "target_directory": "/workspace/target",
        "version": 1,
        "workspace_default_members": [package_id],
        "workspace_members": [package_id],
        "workspace_root": "/workspace",
    }
    return parse_cargo_metadata_fact_evidence(_json(root))


def _metadata_target(
    *, name: str = "neutral", kind: list[str] | None = None,
    crate_types: list[str] | None = None,
) -> dict:
    return {
        "name": name,
        "kind": kind or ["lib"],
        "crate_types": crate_types or ["lib"],
        "required-features": [],
    }


def _artifact(
    *, package_id: str | None = None, name: str = "neutral",
    kind: list[str] | None = None, crate_types: list[str] | None = None,
    features: list[str] | None = None,
) -> dict:
    filename = f"/workspace/target/debug/{name}.rmeta"
    return {
        "reason": "compiler-artifact",
        "package_id": package_id or (
            "path+file:///workspace/pkg#neutral-package@0.1.0"
        ),
        "manifest_path": "/workspace/pkg/Cargo.toml",
        "target": {
            "kind": kind or ["lib"],
            "crate_types": crate_types or ["lib"],
            "name": name,
            "src_path": f"/workspace/pkg/src/{name}.rs",
            "edition": "2021",
            "doc": True,
            "doctest": True,
            "test": True,
        },
        "profile": {
            "opt_level": "0",
            "debuginfo": 2,
            "debug_assertions": True,
            "overflow_checks": True,
            "test": False,
        },
        "features": features or [],
        "filenames": [filename],
        "executable": None,
        "fresh": False,
    }


def _compiler(*artifacts: dict) -> dict:
    return parse_cargo_compiler_artifact_evidence(_events(
        *artifacts,
        {"reason": "build-finished", "success": True},
    ))


def _events(*values: dict) -> bytes:
    return b"".join(_json(value) + b"\n" for value in values)


def _json(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


if __name__ == "__main__":
    unittest.main()

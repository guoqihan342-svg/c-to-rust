from __future__ import annotations

import copy
import hashlib
import json
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.cargo_metadata_fact_evidence import (
    CargoMetadataFactEvidenceError,
    parse_cargo_metadata_fact_evidence,
    validate_cargo_metadata_fact_evidence,
)


class ProjectMigrationCargoMetadataFactEvidenceTests(unittest.TestCase):
    def test_normalizes_minimal_multi_target_workspace_without_identities(self) -> None:
        payload = _metadata()
        data = _encoded(payload)

        result = parse_cargo_metadata_fact_evidence(data)

        self.assertEqual("ready", result["status"])
        self.assertEqual([], result["blockers"])
        package = result["facts"]["packages"][0]
        self.assertEqual("neutral-package", package["name"])
        self.assertEqual("0.1.0", package["version"])
        self.assertEqual(
            [
                {"name": "cli", "enables": []},
                {"name": "default", "enables": ["cli"]},
            ],
            package["features"],
        )
        self.assertEqual(
            [
                {
                    "name": "command", "kind": ["bin"], "crate_types": ["bin"],
                    "required_features": ["cli"],
                },
                {
                    "name": "library", "kind": ["lib"],
                    "crate_types": ["lib", "rlib"],
                    "required_features": [],
                },
            ],
            package["targets"],
        )
        self.assertEqual(
            result["facts"]["packages"], result["facts"]["workspace_members"],
        )
        self.assertEqual(
            result["facts"]["packages"], result["facts"]["default_members"],
        )
        self.assertEqual(content_sha256(result["facts"]), result["facts_sha256"])
        self.assertEqual(hashlib.sha256(data).hexdigest(), result["raw_sha256"])
        self.assertEqual(
            {"semantic_gate": False, "translation_coverage_numerator": 0},
            result["claim_boundary"],
        )
        self.assertNotIn("interface_closure", result)
        projection = json.dumps(result["facts"], sort_keys=True)
        for forbidden in ("/workspace/one", "C:\\work", "Cargo.toml", "src/"):
            self.assertNotIn(forbidden, projection)
        self.assertEqual(
            result, validate_cargo_metadata_fact_evidence(result, data),
        )

    def test_target_and_feature_input_order_is_not_semantic(self) -> None:
        first = _metadata()
        second = copy.deepcopy(first)
        second["packages"][0]["targets"].reverse()
        second["packages"][0]["features"] = {
            "default": ["cli", "cli"], "cli": [],
        }

        first_result = parse_cargo_metadata_fact_evidence(_encoded(first))
        second_result = parse_cargo_metadata_fact_evidence(_encoded(second))

        self.assertEqual(first_result["facts"], second_result["facts"])
        self.assertEqual(first_result["facts_sha256"], second_result["facts_sha256"])

    def test_explicit_library_crate_types_are_valid_target_kinds(self) -> None:
        payload = _metadata()
        library = payload["packages"][0]["targets"][0]
        library["kind"] = ["staticlib", "rlib"]
        library["crate_types"] = ["staticlib", "rlib"]

        result = parse_cargo_metadata_fact_evidence(_encoded(payload))

        self.assertEqual("ready", result["status"])
        self.assertEqual(
            ["rlib", "staticlib"],
            result["facts"]["packages"][0]["targets"][1]["kind"],
        )

    def test_feature_drift_changes_facts_sha256(self) -> None:
        baseline = _metadata()
        changed = copy.deepcopy(baseline)
        changed["packages"][0]["features"]["default"] = []

        before = parse_cargo_metadata_fact_evidence(_encoded(baseline))
        after = parse_cargo_metadata_fact_evidence(_encoded(changed))

        self.assertEqual("ready", after["status"])
        self.assertNotEqual(before["facts"], after["facts"])
        self.assertNotEqual(before["facts_sha256"], after["facts_sha256"])

    def test_rejects_duplicate_keys_and_nonstandard_numbers(self) -> None:
        invalid = (
            b'{"version":1,"version":1}',
            b'{"version":NaN}',
            b'{"version":Infinity}',
            b'{"version":-Infinity}',
        )
        for data in invalid:
            with self.subTest(data=data):
                with self.assertRaisesRegex(
                    CargoMetadataFactEvidenceError, "cargo_metadata_json_invalid",
                ):
                    parse_cargo_metadata_fact_evidence(data)

    def test_rejects_invalid_utf8_trailing_content_and_unknown_top_level(self) -> None:
        unknown = _metadata()
        unknown["future_topology"] = {}
        invalid = (b"\xff", _encoded(_metadata()) + b"{}", _encoded(unknown))
        for data in invalid:
            with self.subTest(data=data[:40]):
                with self.assertRaises(CargoMetadataFactEvidenceError):
                    parse_cargo_metadata_fact_evidence(data)

    def test_unknown_workspace_member_is_blocked(self) -> None:
        payload = _metadata()
        payload["workspace_members"] = ["unknown-member"]
        payload["workspace_default_members"] = []

        result = parse_cargo_metadata_fact_evidence(_encoded(payload))

        self.assertEqual("blocked", result["status"])
        self.assertIn("cargo_metadata_workspace_member_unknown", result["blockers"])
        self.assertFalse(result["claim_boundary"]["semantic_gate"])

    def test_missing_fields_and_unsupported_target_kind_are_blocked(self) -> None:
        missing = _metadata()
        del missing["packages"][0]["features"]
        unsupported = _metadata()
        unsupported["packages"][0]["targets"][0]["kind"] = ["future-kind"]
        unsupported["packages"][0]["targets"][0]["crate_types"] = ["future-crate"]

        missing_result = parse_cargo_metadata_fact_evidence(_encoded(missing))
        unsupported_result = parse_cargo_metadata_fact_evidence(
            _encoded(unsupported)
        )

        self.assertEqual("blocked", missing_result["status"])
        self.assertIn(
            "cargo_metadata_package_features_invalid", missing_result["blockers"],
        )
        self.assertEqual("blocked", unsupported_result["status"])
        self.assertIn(
            "cargo_metadata_target_kind_unsupported",
            unsupported_result["blockers"],
        )
        self.assertIn(
            "cargo_metadata_target_crate_type_unsupported",
            unsupported_result["blockers"],
        )

    def test_host_paths_must_be_absolute_but_are_not_semantic(self) -> None:
        payload = _metadata()
        payload["target_directory"] = "relative/target"
        result = parse_cargo_metadata_fact_evidence(_encoded(payload))
        self.assertEqual("blocked", result["status"])
        self.assertIn("cargo_metadata_host_path_shape_invalid", result["blockers"])

    def test_host_path_and_path_package_id_changes_do_not_change_facts_sha256(self) -> None:
        windows = _metadata(host=r"C:\work\one")
        linux = _metadata(host="/srv/build/two")

        first = parse_cargo_metadata_fact_evidence(_encoded(windows))
        second = parse_cargo_metadata_fact_evidence(_encoded(linux))

        self.assertEqual("ready", first["status"])
        self.assertEqual("ready", second["status"])
        self.assertNotEqual(first["raw_sha256"], second["raw_sha256"])
        self.assertEqual(first["facts"], second["facts"])
        self.assertEqual(first["facts_sha256"], second["facts_sha256"])


def _metadata(host: str = "/workspace/one") -> dict:
    package_id = f"path+file://{host}/pkg#neutral-package@0.1.0"
    return {
        "packages": [{
            "name": "neutral-package", "version": "0.1.0", "id": package_id,
            "manifest_path": f"{host}/pkg/Cargo.toml",
            "targets": [
                {
                    "name": "library", "kind": ["lib"],
                    "crate_types": ["rlib", "lib", "rlib"],
                    "src_path": f"{host}/pkg/src/lib.rs", "edition": "2021",
                    "doc": True, "doctest": True, "test": True,
                },
                {
                    "name": "command", "kind": ["bin"],
                    "crate_types": ["bin"],
                    "required-features": ["cli", "cli"],
                    "src_path": f"{host}/pkg/src/main.rs", "edition": "2021",
                    "doc": True, "doctest": False, "test": True,
                },
            ],
            "features": {"cli": [], "default": ["cli", "cli"]},
        }],
        "workspace_members": [package_id],
        "workspace_default_members": [package_id],
        "resolve": None,
        "target_directory": f"{host}/pkg/target",
        "build_directory": f"{host}/pkg/target",
        "version": 1,
        "workspace_root": f"{host}/pkg",
        "metadata": None,
    }


def _encoded(value: dict) -> bytes:
    return (
        json.dumps(value, ensure_ascii=True, sort_keys=False, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


if __name__ == "__main__":
    unittest.main()

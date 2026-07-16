from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.rust_cargo_product_witness import (
    build_rust_cargo_product_witness,
    reopen_rust_cargo_product_witness,
    validate_rust_cargo_product_witness,
)
from validation.tools.project_migration_rust_link_product_test_support import (
    ar_member, archive, relocatable_elf,
)


MODULE = (
    "validation.tools._project_migration_harness.rust_cargo_product_witness"
)


class RustCargoProductWitnessTests(unittest.TestCase):
    def test_witness_binds_reopenable_archive_members(self) -> None:
        data, product, compiler, expectation = _inputs()
        with _dependencies(data, compiler, expectation):
            witness = build_rust_cargo_product_witness(
                Path("unused"), [product], {}, {},
            )
            self.assertEqual("ready", witness["status"])
            self.assertEqual(2, witness["schema_version"])
            binding = witness["inspections"][0]
            inspection = binding["inspection"]
            self.assertEqual(
                inspection["inspection_sha256"], binding["inspection_sha256"],
            )
            self.assertEqual(2, len(inspection["members"]))
            self.assertEqual(
                content_sha256(witness["inspections"]),
                witness["inspection_set_sha256"],
            )
            self.assertEqual(witness, validate_rust_cargo_product_witness(witness))
            self.assertEqual(
                witness,
                reopen_rust_cargo_product_witness(Path("unused"), witness, {}, {}),
            )
        serialized = json.dumps(witness, sort_keys=True)
        self.assertNotIn("private.o", serialized)
        self.assertNotRegex(serialized, r"[A-Za-z]:\\|/(?:home|root|tmp)/")

    def test_self_consistent_member_forgery_is_rejected_on_reopen(self) -> None:
        data, product, compiler, expectation = _inputs()
        with _dependencies(data, compiler, expectation):
            witness = build_rust_cargo_product_witness(
                Path("unused"), [product], {}, {},
            )
            forged = copy.deepcopy(witness)
            inspection = forged["inspections"][0]["inspection"]
            inspection["members"][0]["payload_sha256"] = "0" * 64
            _reseal_inspection(inspection)
            _reseal_witness(forged)
            self.assertEqual(forged, validate_rust_cargo_product_witness(forged))
            with self.assertRaisesRegex(ValueError, "reopen_drift"):
                reopen_rust_cargo_product_witness(
                    Path("unused"), forged, {}, {},
                )

    def test_witness_and_member_schemas_are_strict(self) -> None:
        data, product, compiler, expectation = _inputs()
        with _dependencies(data, compiler, expectation):
            witness = build_rust_cargo_product_witness(
                Path("unused"), [product], {}, {},
            )
            unexpected = copy.deepcopy(witness)
            unexpected["inspections"][0]["inspection"]["members"][0][
                "member_name"
            ] = "private.o"
            _reseal_witness(unexpected)
            with self.assertRaisesRegex(ValueError, "report_invalid"):
                validate_rust_cargo_product_witness(unexpected)

            binding_drift = copy.deepcopy(witness)
            binding_drift["inspections"][0]["inspection_sha256"] = "0" * 64
            _reseal_witness(binding_drift, refresh_bindings=False)
            with self.assertRaisesRegex(ValueError, "inspection_invalid"):
                validate_rust_cargo_product_witness(binding_drift)

            unhashable_binding = copy.deepcopy(witness)
            unhashable_binding["inspections"][0]["product_sha256"] = []
            _reseal_witness(unhashable_binding)
            with self.assertRaisesRegex(ValueError, "inspection_invalid"):
                validate_rust_cargo_product_witness(unhashable_binding)


def _dependencies(data: bytes, compiler: dict, expectation: dict):
    return _Patches(data, compiler, expectation)


class _Patches:
    def __init__(self, data: bytes, compiler: dict, expectation: dict) -> None:
        self._patches = (
            patch(f"{MODULE}.validate_cargo_compiler_artifact_evidence",
                  return_value=compiler),
            patch(f"{MODULE}.validate_rust_cargo_topology_expectation",
                  return_value=expectation),
            patch(f"{MODULE}.read_rust_product", return_value=data),
        )

    def __enter__(self):
        for item in self._patches:
            item.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        for item in reversed(self._patches):
            item.stop()


def _inputs() -> tuple[bytes, dict, dict, dict]:
    package_id = "neutral@1.0.0"
    payload = relocatable_elf()
    data = archive(
        ar_member("private.o/", payload),
        ar_member("private.o/", payload + b"duplicate"),
    )
    digest = hashlib.sha256(data).hexdigest()
    product_core = {
        "schema_version": 1,
        "package": {
            "name": "neutral", "version": "1.0.0",
            "package_id_sha256": hashlib.sha256(package_id.encode()).hexdigest(),
        },
        "target": {
            "name": "neutral", "kind": ["staticlib"],
            "crate_types": ["staticlib"],
        },
        "product_kind": "staticlib",
        "guest_path_sha256": "b" * 64,
        "file": {
            "path": f"verification/rust-products/{digest}.bin",
            "sha256": digest, "size_bytes": len(data),
        },
    }
    product = {
        **product_core, "product_sha256": content_sha256(product_core),
    }
    compiler = {
        "artifacts": [{"package_id": package_id, "target": {"name": "neutral"}}],
    }
    expectation = {
        "facts": {"packages": [{
            "name": "neutral", "version": "1.0.0",
            "targets": [{"name": "neutral", "crate_types": ["staticlib"]}],
        }]},
    }
    return data, product, compiler, expectation


def _reseal_inspection(inspection: dict) -> None:
    inspection["member_identity_sha256"] = content_sha256(inspection["members"])
    core = {key: value for key, value in inspection.items()
            if key != "inspection_sha256"}
    inspection["inspection_sha256"] = content_sha256(core)


def _reseal_witness(witness: dict, *, refresh_bindings: bool = True) -> None:
    if refresh_bindings:
        for binding in witness["inspections"]:
            binding["inspection_sha256"] = binding["inspection"]["inspection_sha256"]
    witness["inspection_set_sha256"] = content_sha256(witness["inspections"])
    core = {key: value for key, value in witness.items() if key != "witness_sha256"}
    witness["witness_sha256"] = content_sha256(core)


if __name__ == "__main__":
    unittest.main()

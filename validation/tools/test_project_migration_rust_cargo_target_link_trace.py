from __future__ import annotations

import copy
import hashlib
import json
import unittest

from validation.tools._project_migration_harness.rust_cargo_target_link_trace import (
    parse_rust_cargo_target_link_trace,
    validate_rust_cargo_target_link_trace,
)
from validation.tools.project_migration_rust_cargo_link_order_test_support import (
    cargo_stream,
    package_id,
    package_name,
    path_sha256,
    target_name,
)


class RustCargoTargetLinkTraceTests(unittest.TestCase):
    def test_attributes_diagnostics_and_preserves_per_target_path_order(self) -> None:
        raw = cargo_stream(diagnostics=(
            ("gamma", ("gamma",)),
            ("app", ("alpha", "beta", "alpha")),
        ))

        result = parse_rust_cargo_target_link_trace(raw)

        self.assertEqual(2, result["diagnostic_count"])
        by_target = {
            item["target"]["name"]: item for item in result["diagnostics"]
        }
        app = by_target[target_name("app")]
        self.assertEqual(package_name("app"), app["package"]["name"])
        self.assertEqual(
            hashlib.sha256(package_id("app").encode("utf-8")).hexdigest(),
            app["package"]["package_id_sha256"],
        )
        self.assertEqual([0, 1, 2], [
            entry["link_ordinal"] for entry in app["entries"]
        ])
        self.assertEqual(
            [path_sha256("alpha"), path_sha256("beta"), path_sha256("alpha")],
            [entry["guest_path_sha256"] for entry in app["entries"]],
        )
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(), result["source_sha256"],
        )
        self.assertNotIn("/runtime/target", json.dumps(result, sort_keys=True))

    def test_validation_reparses_source_and_rejects_nested_tamper(self) -> None:
        raw = cargo_stream()
        trace = parse_rust_cargo_target_link_trace(raw)

        self.assertEqual(
            trace, validate_rust_cargo_target_link_trace(trace, raw),
        )
        tampered = copy.deepcopy(trace)
        tampered["diagnostics"][0]["entries"][0]["guest_path_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "entry_hash_drifted"):
            validate_rust_cargo_target_link_trace(tampered)

        changed_source = cargo_stream(noise="source changed after capture")
        with self.assertRaisesRegex(ValueError, "source_reparse_drift"):
            validate_rust_cargo_target_link_trace(trace, changed_source)

    def test_duplicate_trace_for_one_target_is_rejected(self) -> None:
        raw = cargo_stream(diagnostics=(
            ("app", ("alpha", "beta")),
            ("app", ("alpha", "beta")),
        ))

        with self.assertRaisesRegex(ValueError, "target_duplicate"):
            parse_rust_cargo_target_link_trace(raw)


if __name__ == "__main__":
    unittest.main()

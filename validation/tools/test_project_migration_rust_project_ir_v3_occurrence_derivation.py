from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools.test_project_migration_rust_project_ir_v3_topology import (
    _build, _candidate, _derive, _product, _unit,
)


class RustProjectIRV3OccurrenceDerivationTests(unittest.TestCase):
    def test_scc_object_occurrences_are_contiguous_and_source_ordered(self) -> None:
        units = [_unit("left"), _unit("right")]
        product = _product("product", "archive", ["obj-left", "obj-right"], [])
        scope = _multi_scope(["left", "right"], ["product"])

        topology = _derive([_build(units, [product])], {"group": scope},
                           [_candidate("group")])

        occurrences = topology["targets"][0]["input_occurrences"]
        self.assertEqual(["left", "right"], [item["source_unit_id"]
                                               for item in occurrences])
        self.assertEqual(1, len({item["module_id"] for item in occurrences}))
        module = topology["modules"][0]
        self.assertEqual(module["module_id"], occurrences[0]["module_id"])
        self.assertEqual(["left", "right"], module["source_unit_ids"])

    def test_object_input_ambiguities_fail_closed(self) -> None:
        cases = [
            ("duplicate", ["obj-unit", "obj-unit"], [_unit("unit")],
             "object_occurrence_duplicate"),
            ("reverse-scc", ["obj-right", "obj-left"],
             [_unit("left"), _unit("right")], "object_occurrence_order_invalid"),
            ("missing", [], [_unit("unit")], "object_occurrence_closure_drift"),
            ("unknown", ["obj-missing"], [_unit("unit")],
             "input_dependency_unknown"),
            ("unowned", ["obj-extra"], [_unit("unit"), _unit("extra")],
             "object_input_unowned"),
            ("native", [None], [_unit("unit")], "native_input_unsupported"),
        ]
        for label, inputs, units, error in cases:
            with self.subTest(label=label):
                source_ids = [item["unit_id"] for item in units]
                owned = source_ids if label == "reverse-scc" else ["unit"]
                scope = _multi_scope(owned, ["product"])
                product = _product("product", "archive", inputs, [])
                with self.assertRaisesRegex(ValueError, error):
                    _derive([_build(units, [product])], {"group": scope},
                            [_candidate("group")])


def _multi_scope(unit_ids, reachable):
    records = [{
        "unit_id": unit_id,
        "variant": {"key": unit_id, "index": 0, "count": 1},
        "object_owner_target_id": f"obj-{unit_id}",
        "reachable_target_ids": sorted(reachable),
        "terminal_target_ids": sorted(reachable),
    } for unit_id in sorted(unit_ids)]
    payload = {
        "schema_version": 1, "scope_kind": "scc-build-target-scope",
        "source_unit_ids": sorted(unit_ids), "unit_scopes": records,
        "object_target_ids": sorted(item["object_owner_target_id"] for item in records),
        "reachable_target_ids": sorted(reachable),
        "terminal_target_ids": sorted(reachable),
        "shared_reachable_target_ids": sorted(reachable),
        "domain_status": "target-bound" if len(records) == 1 else "shared-target-domain",
    }
    return {**payload, "scope_sha256": content_sha256(payload)}


if __name__ == "__main__":
    unittest.main()

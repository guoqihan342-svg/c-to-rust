from __future__ import annotations

import json
import unittest

from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes, content_sha256,
)
from validation.tools._project_migration_harness.c2rust_project_baseline_target_exports import (
    CONFLICT_CODE, project_target_scoped_exports,
)


class TargetScopedExportTests(unittest.TestCase):
    def test_equal_exports_in_disjoint_terminal_targets_coexist(self) -> None:
        plan = _plan([
            ("terminal-a", [("unit-a", [0])]),
            ("terminal-b", [("unit-b", [0])]),
        ])
        source = b'#[no_mangle]\npub unsafe extern "C" fn shared() {}\n'
        trees = {
            "unit-b": {"generated/b.rs": source},
            "unit-a": {
                "generated/a.rs": source,
                "README.txt": b"#[no_mangle] is documentation, not Rust",
            },
        }
        identities = {
            "unit-b": "key-b",
            "unit-a": {"unit_id": "unit-a", "unit_key": "key-a"},
        }

        result = project_target_scoped_exports(plan, trees, identities)

        self.assertEqual("passed", result["status"])
        self.assertEqual([], result["blockers"])
        self.assertEqual(0, result["refusal_count"])
        self.assertEqual(
            [("terminal-a", "shared"), ("terminal-b", "shared")],
            [
                (target["terminal_target_id"], target["exports"][0]["symbol"])
                for target in result["terminal_targets"]
            ],
        )
        self.assertTrue(all(
            target["status"] == "passed" and target["conflict_count"] == 0
            for target in result["terminal_targets"]
        ))
        core = {key: value for key, value in result.items()
                if key != "report_sha256"}
        self.assertEqual(content_sha256(core), result["report_sha256"])
        self.assertEqual(result, json.loads(canonical_json_bytes(result)))

    def test_same_target_cross_unit_export_refuses_without_winner(self) -> None:
        plan = _plan([("terminal", [
            ("unit-a", [0]), ("unit-b", [1]),
        ])])
        trees = {
            "unit-a": {"z.rs": (
                '#[no_mangle]\npub unsafe extern "C" fn collision() {}\n'
            )},
            "unit-b": {"a.rs": (
                "#[no_mangle]\npub static mut collision: i32 = 0;\n"
                "#[no_mangle]\npub fn unique() {}\n"
            )},
        }
        identities = {
            "unit-a": {"unit_id": "unit-a", "variant": 0},
            "unit-b": {"unit_id": "unit-b", "variant": 1},
        }

        result = project_target_scoped_exports(plan, trees, identities)

        self.assertEqual("refused", result["status"])
        self.assertEqual([CONFLICT_CODE], result["blockers"])
        self.assertEqual(1, result["refusal_count"])
        target = result["terminal_targets"][0]
        conflict = target["conflicts"][0]
        self.assertEqual("refused", target["status"])
        self.assertEqual("collision", conflict["symbol"])
        self.assertEqual(["unit-a", "unit-b"], conflict["unit_ids"])
        collision = [item for item in target["exports"]
                     if item["symbol"] == "collision"]
        self.assertEqual(
            {"function", "static"},
            {item["definition_kind"] for item in collision},
        )
        self.assertEqual({"a.rs", "z.rs"},
                         {item["generated_path"] for item in collision})
        self.assertNotIn("winner", json.dumps(result, sort_keys=True))
        self.assertEqual(
            result,
            project_target_scoped_exports(
                plan, dict(reversed(list(trees.items()))),
                dict(reversed(list(identities.items()))),
            ),
        )

    def test_repeated_unit_occurrences_do_not_create_a_conflict(self) -> None:
        plan = _plan([("terminal", [
            ("unit", [0, 0]), ("unit", [0, 2]),
        ])])
        source = (
            'const TEXT: &str = "#[no_mangle]"; // #[no_mangle]\n'
            "/* #[no_mangle] pub fn fake() {} */\n"
            "#[no_mangle]\npub unsafe extern \"C\" fn actual() {}\n"
        )

        result = project_target_scoped_exports(
            plan,
            {"unit": {"lib.rs": source, "notes.txt": "#[no_mangle]"}},
            {"unit": {"unit_id": "unit", "snapshot": "bound"}},
        )

        self.assertEqual("passed", result["status"])
        target = result["terminal_targets"][0]
        self.assertEqual(1, target["export_count"])
        self.assertEqual("actual", target["exports"][0]["symbol"])
        self.assertEqual(
            [[0, 0], [0, 2]], target["exports"][0]["target_occurrence_paths"],
        )
        self.assertEqual([], target["conflicts"])

    def test_same_unit_duplicate_export_also_refuses(self) -> None:
        plan = _plan([("terminal", [("unit", [0])])])
        result = project_target_scoped_exports(
            plan,
            {"unit": {
                "a.rs": "#[no_mangle]\npub fn duplicate() {}\n",
                "b.rs": "#[no_mangle]\npub static duplicate: i32 = 0;\n",
            }},
            {"unit": {"unit_id": "unit"}},
        )

        self.assertEqual("refused", result["status"])
        conflict = result["terminal_targets"][0]["conflicts"][0]
        self.assertEqual("duplicate", conflict["symbol"])
        self.assertEqual(2, conflict["definition_count"])
        self.assertEqual(["unit"], conflict["unit_ids"])

    def test_tree_and_identity_coverage_fail_closed(self) -> None:
        plan = _plan([("terminal", [("unit", [0])])])
        tree = {"unit": {"lib.rs": "pub fn internal() {}\n"}}
        identity = {"unit": {"unit_id": "unit"}}
        with self.assertRaisesRegex(ValueError, "unit_coverage_invalid"):
            project_target_scoped_exports(plan, {}, identity)
        with self.assertRaisesRegex(ValueError, "unit_identity_invalid"):
            project_target_scoped_exports(
                plan, tree, {"unit": {"unit_id": "different"}},
            )
        with self.assertRaisesRegex(ValueError, "generated_path_invalid"):
            project_target_scoped_exports(
                plan, {"unit": {"../escape.rs": ""}}, identity,
            )


def _plan(
    targets: list[tuple[str, list[tuple[str, list[int]]]]],
) -> dict:
    return {
        "schema_version": 1,
        "terminal_target_ids": [target_id for target_id, _items in targets],
        "terminal_targets": [
            {
                "terminal_target_id": target_id,
                "unit_occurrences": [
                    {"unit_id": unit_id, "target_occurrence_path": path}
                    for unit_id, path in items
                ],
            }
            for target_id, items in targets
        ],
        "unit_fan_out": [],
    }


if __name__ == "__main__":
    unittest.main()

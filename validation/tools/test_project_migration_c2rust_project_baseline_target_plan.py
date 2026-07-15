from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.c2rust_project_baseline_target_plan import (
    project_terminal_target_plan,
)


class TerminalTargetPlanTests(unittest.TestCase):
    def test_same_source_variants_remain_in_exact_terminal_closures(self) -> None:
        debug = _unit("unit-debug", "src/shared.c", "build/debug/shared.o", 0, 2)
        release = _unit(
            "unit-release", "src/shared.c", "build/release/shared.o", 1, 2,
        )
        targets = []
        for label, unit in (("debug", debug), ("release", release)):
            object_id = f"object-{label}"
            archive_id = f"archive-{label}"
            targets.extend([
                _object(object_id, unit),
                _target(
                    archive_id, "archive", f"build/{label}/libshared.a",
                    [(object_id, unit["output"]["path"])],
                ),
                _target(
                    f"link-{label}", "link", f"build/{label}/app",
                    [(archive_id, f"build/{label}/libshared.a")],
                    link_arguments=[f"-Wl,--build-id={label}"],
                ),
            ])

        plan = project_terminal_target_plan(_build_ir([debug, release], targets))

        self.assertEqual(["link-debug", "link-release"], plan["terminal_target_ids"])
        by_terminal = {
            item["terminal_target_id"]: item for item in plan["terminal_targets"]
        }
        self.assertEqual(
            [("unit-debug", 0, 2)],
            [
                (item["unit_id"], item["variant_index"], item["variant_count"])
                for item in by_terminal["link-debug"]["unit_occurrences"]
            ],
        )
        self.assertEqual(
            ["unit-release"],
            [
                item["unit_id"]
                for item in by_terminal["link-release"]["unit_occurrences"]
            ],
        )

    def test_one_unit_fans_out_to_each_terminal_occurrence(self) -> None:
        unit = _unit("unit", "src/unit.c", "build/unit.o")
        targets = [_object("object", unit)]
        targets.extend(
            _target(link_id, "link", f"build/{link_id}", [("object", "build/unit.o")])
            for link_id in ("link-a", "link-b")
        )

        plan = project_terminal_target_plan(_build_ir([unit], targets))

        fan_out = plan["unit_fan_out"][0]
        self.assertEqual(2, fan_out["occurrence_count"])
        self.assertEqual(
            [
                ("link-a", [0]),
                ("link-b", [0]),
            ],
            [
                (item["terminal_target_id"], item["target_occurrence_path"])
                for item in fan_out["occurrences"]
            ],
        )

    def test_archive_order_duplicates_and_target_boundaries_are_preserved(self) -> None:
        first = _unit("unit-a", "src/a.c", "build/a.o")
        second = _unit("unit-b", "src/b.c", "build/b.o")
        archive = _target(
            "archive", "archive", "build/libmix.a",
            [
                ("object-b", "build/b.o"),
                ("object-a", "build/a.o"),
                ("object-b", "build/b.o"),
            ],
            archive_semantics={"operation": "rcs", "ranlib_passes": 2},
        )
        link_arguments = ["build/libmix.a", "-lm", "vendor/libnative.a"]
        link = _target(
            "link", "link", "build/app",
            [("archive", "build/libmix.a"), (None, "vendor/libnative.a")],
            link_arguments=link_arguments,
        )
        build_ir = _build_ir(
            [first, second], [_object("object-a", first), _object("object-b", second), archive, link],
            external=[{
                "dependency_id": "native", "kind": "unresolved-native-library",
                "name": "vendor/libnative.a", "consumer_target_ids": ["link"],
                "ordinal": 2,
            }],
            boundaries=[{
                "kind": "native_link_config_unresolved", "dependency_id": "native",
            }],
        )

        terminal = project_terminal_target_plan(build_ir)["terminal_targets"][0]

        self.assertEqual(
            ["link", "archive", "object-b", "object-a", "object-b"],
            [item["target_id"] for item in terminal["target_occurrences"]],
        )
        self.assertEqual(
            [[], [0], [0, 0], [0, 1], [0, 2]],
            [item["target_occurrence_path"] for item in terminal["target_occurrences"]],
        )
        self.assertEqual(
            ["unit-b", "unit-a", "unit-b"],
            [item["unit_id"] for item in terminal["unit_occurrences"]],
        )
        self.assertEqual(
            {"operation": "rcs", "ranlib_passes": 2},
            terminal["target_occurrences"][1]["archive_semantics"],
        )
        self.assertEqual(
            link_arguments, terminal["target_occurrences"][0]["ordered_link_arguments"],
        )
        boundaries = terminal["target_owned_boundaries"]
        self.assertEqual(
            ["external-dependency", "ordered-input"],
            [item["boundary_kind"] for item in boundaries],
        )
        self.assertEqual(
            "native_link_config_unresolved",
            boundaries[0]["build_ir_boundaries"][0]["kind"],
        )

    def test_object_only_terminal_is_compile_only(self) -> None:
        unit = _unit("unit", "src/unit.c", "build/unit.o")

        terminal = project_terminal_target_plan(
            _build_ir([unit], [_object("object", unit)])
        )["terminal_targets"][0]

        self.assertEqual("object", terminal["terminal_target_id"])
        self.assertEqual("compile_only", terminal["execution_mode"])
        self.assertEqual(["unit"], [item["unit_id"] for item in terminal["unit_occurrences"]])

    def test_unknown_dependency_and_cycle_fail_closed(self) -> None:
        unit = _unit("unit", "src/unit.c", "build/unit.o")
        unknown = _target(
            "link", "link", "build/app", [("missing", "build/missing.o")],
        )
        with self.assertRaisesRegex(ValueError, "unknown_dependency"):
            project_terminal_target_plan(_build_ir([unit], [_object("object", unit), unknown]))

        archive = _target("archive", "archive", "build/lib.a", [("link", "build/app")])
        link = _target("link", "link", "build/app", [("archive", "build/lib.a")])
        with self.assertRaisesRegex(ValueError, "cycle"):
            project_terminal_target_plan(
                _build_ir([unit], [_object("object", unit), archive, link])
            )

    def test_owner_input_and_output_conflicts_fail_closed(self) -> None:
        unit = _unit("unit", "src/unit.c", "build/unit.o")
        duplicate_output = _target("link", "link", "build/app", [])
        duplicate_output["outputs"].append({"path": "build/app"})
        cases = [
            (
                "object_owner_missing",
                [_object("object", {**unit, "output": {"path": "build/other.o"}})],
            ),
            (
                "ordered_input_unrepresentable",
                [
                    _object("object", unit),
                    _target("link", "link", "build/app", [("object", "build/wrong.o")]),
                ],
            ),
            (
                "output_conflict",
                [_object("object", unit), duplicate_output],
            ),
            (
                "output_conflict",
                [
                    _object("object", unit),
                    _target("link", "link", "build/unit.o", []),
                ],
            ),
        ]
        for reason, targets in cases:
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                project_terminal_target_plan(_build_ir([unit], targets))


def _unit(
    unit_id: str, source: str, output: str, variant_index: int = 0,
    variant_count: int = 1,
) -> dict:
    return {
        "unit_id": unit_id, "variant_index": variant_index,
        "variant_count": variant_count, "source": {"path": source},
        "output": {"path": output},
    }


def _object(target_id: str, unit: dict) -> dict:
    target = _target(
        target_id, "object", unit["output"]["path"],
        [(None, unit["source"]["path"])],
    )
    target["ordered_inputs"][0]["role"] = "source"
    target["provenance"] = {"unit_id": unit["unit_id"]}
    return target


def _target(
    target_id: str, kind: str, output: str,
    inputs: list[tuple[str | None, str]], *,
    link_arguments: list[str] | None = None,
    archive_semantics: dict | None = None,
) -> dict:
    dependencies = list(dict.fromkeys(
        dependency for dependency, _path in inputs if dependency is not None
    ))
    result = {
        "target_id": target_id, "name": output, "kind": kind,
        "outputs": [{"path": output}],
        "ordered_inputs": [
            {
                "ordinal": ordinal, "role": "link-input", "binding": {"path": path},
                "dependency_target_id": dependency,
            }
            for ordinal, (dependency, path) in enumerate(inputs)
        ],
        "dependency_target_ids": dependencies,
        "ordered_link_arguments": list(link_arguments or []),
        "provenance": {},
    }
    if kind == "archive":
        result["archive_semantics"] = archive_semantics or {
            "operation": "rcs", "ranlib_passes": 0,
        }
    return result


def _build_ir(
    units: list[dict], targets: list[dict], *, external: list[dict] | None = None,
    boundaries: list[dict] | None = None,
) -> dict:
    return {
        "translation_units": units, "targets": targets,
        "external_dependencies": list(external or []),
        "boundaries": list(boundaries or []),
    }


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.build_ir_external_dependencies import NATIVE_DEPENDENCY_KIND, ORDERED_LINK_ARGUMENT_KIND
from validation.tools._project_migration_harness.native_link_requirement_projection import native_link_requirement_id, project_native_link_requirements
from validation.tools._project_migration_harness.rust_project_ir_v3_link_expectation import project_layered_link_expectation
from validation.tools._project_migration_harness.rust_project_ir_v3_link_validation import validate_link_target_closure, validate_target_occurrences
from validation.tools._project_migration_harness.rust_project_ir_v3_topology_products import input_occurrence_id


BUILD_SHA = "a" * 64
SOURCE_TARGET = "build-consumer"
RUST_TARGET = "target-consumer"


class RustProjectIRV3LinkExpectationTests(unittest.TestCase):
    def test_distinct_native_requirements_keep_distinct_identities(self) -> None:
        requirements = project_native_link_requirements([{
            "semantic_sha256": "f" * 64,
            "external_dependencies": [
                _dependency("native-a", NATIVE_DEPENDENCY_KIND, "libalpha.so", 0),
                _dependency("native-b", NATIVE_DEPENDENCY_KIND, "libbeta.a", 1,
                            library_format="static-archive"),
            ],
        }])

        self.assertEqual(2, len({item["requirement_id"] for item in requirements}))
        self.assertEqual({
            native_link_requirement_id("libalpha.so", "shared-library"),
            native_link_requirement_id("libbeta.a", "static-archive"),
        }, {item["requirement_id"] for item in requirements})

    def test_cross_class_order_and_duplicates_are_preserved(self) -> None:
        build_ir, source_target, products, inputs = _interleaved_fixture()

        expectation = project_layered_link_expectation(
            build_ir, source_target, products, inputs,
            rust_target_id=RUST_TARGET,
            build_ir_artifact_sha256=BUILD_SHA,
        )

        rows = expectation["occurrences"]
        self.assertEqual([
            "module-dep-info-commitment", "system-link-argument",
            "cargo-package-product", "native-link-input",
            "system-link-argument", "native-link-input",
        ], [item["representation_layer"] for item in rows])
        self.assertEqual(["-pthread", "-pthread"], [
            item["system_argument"] for item in rows
            if item["representation_layer"] == "system-link-argument"
        ])
        native_rows = [item for item in rows
                       if item["representation_layer"] == "native-link-input"]
        self.assertEqual(1, len({item["native_requirement_id"]
                                for item in native_rows}))
        self.assertEqual(2, len({item["external_dependency_id"]
                                for item in native_rows}))
        target = _target(expectation, inputs)
        requirement_id = native_link_requirement_id(
            "libportable.so", "shared-library",
        )
        validate_target_occurrences(target, {requirement_id})
        validate_link_target_closure(target, {
            RUST_TARGET: target,
            "target-library": {"package_id": "package-library"},
        }, {
            "module-consumer": {
                "target_id": RUST_TARGET, "source_unit_ids": ["source-object"],
            },
        })

    def test_consumer_package_and_requirement_drift_fail_closed(self) -> None:
        build_ir, source_target, products, inputs = _interleaved_fixture()
        expectation = project_layered_link_expectation(
            build_ir, source_target, products, inputs,
            rust_target_id=RUST_TARGET,
            build_ir_artifact_sha256=BUILD_SHA,
        )
        requirement_id = native_link_requirement_id(
            "libportable.so", "shared-library",
        )
        for label, mutate, requirement_ids, error in (
            (
                "consumer",
                lambda value: value["occurrences"][0].update({
                    "consumer_target_id": "target-forged",
                }),
                {requirement_id}, "link occurrence order",
            ),
            (
                "package",
                lambda value: value["occurrences"][2].update({
                    "package_id": "package-forged",
                }),
                {requirement_id}, "link package mapping",
            ),
            ("requirement", lambda _value: None, set(), "native link mapping"),
        ):
            with self.subTest(label=label):
                target = _target(copy.deepcopy(expectation), inputs)
                mutate(target["link_expectation"])
                _rehash_expectation(target["link_expectation"])
                if label == "package":
                    validate_target_occurrences(target, requirement_ids)
                    with self.assertRaisesRegex(ValueError, "link package closure"):
                        validate_link_target_closure(target, {
                            RUST_TARGET: target,
                            "target-library": {"package_id": "package-library"},
                        }, {"module-consumer": {
                            "target_id": RUST_TARGET,
                            "source_unit_ids": ["source-object"],
                        }})
                    continue
                with self.assertRaisesRegex(ValueError, error):
                    validate_target_occurrences(target, requirement_ids)

    def test_non_unique_controls_and_search_roots_fail_closed(self) -> None:
        controls = (
            "-Wl,--as-needed", "-Wl,--start-group", "-Wl,--whole-archive",
            "-Wl,@arguments.rsp", "/WHOLEARCHIVE:portable.lib",
            "-Wl,--rpath,<repository>/lib", "-Wl,unknown", "-O2",
        )
        for argument in controls:
            with self.subTest(argument=argument):
                build_ir, target = _system_fixture(argument)
                with self.assertRaisesRegex(ValueError, "system_control_unsupported"):
                    project_layered_link_expectation(
                        build_ir, target, {}, [], rust_target_id=RUST_TARGET,
                        build_ir_artifact_sha256=BUILD_SHA,
                    )
        build_ir, target = _system_fixture("-pthread")
        target["ordered_link_search_roots"] = [{
            "ordinal": 0, "binding_sha256": "b" * 64,
        }]
        with self.assertRaisesRegex(ValueError, "search_root_unsupported"):
            project_layered_link_expectation(
                build_ir, target, {}, [], rust_target_id=RUST_TARGET,
                build_ir_artifact_sha256=BUILD_SHA,
            )
        build_ir, target = _system_fixture("-pthread")
        target["link_response_files"] = [{
            "ordinal": 0, "binding_sha256": "c" * 64,
        }]
        with self.assertRaisesRegex(ValueError, "response_file_unsupported"):
            project_layered_link_expectation(
                build_ir, target, {}, [], rust_target_id=RUST_TARGET,
                build_ir_artifact_sha256=BUILD_SHA,
            )

    def test_unmapped_positional_input_fails_closed(self) -> None:
        source = {
            "target_id": SOURCE_TARGET, "kind": "link",
            "ordered_link_arguments": [], "ordered_link_search_roots": [],
            "link_response_files": [],
            "ordered_link_occurrences": [_source_row(
                0, "input", input_ordinal=0, binding_sha256="b" * 64,
                dependency_target_id=None,
            )],
        }
        projected = [{
            "ordinal": 0,
            "occurrence_id": input_occurrence_id(BUILD_SHA, SOURCE_TARGET, 0),
            "role": "link-input", "dependency_target_id": None,
            "object_target_id": None, "source_unit_id": None, "module_id": None,
            "binding_sha256": "b" * 64,
        }]
        with self.assertRaisesRegex(ValueError, "object_mapping_invalid"):
            project_layered_link_expectation(
                {"external_dependencies": []}, source, {}, projected,
                rust_target_id=RUST_TARGET,
                build_ir_artifact_sha256=BUILD_SHA,
            )

    def test_repeated_package_product_without_physical_strategy_is_blocked(self) -> None:
        build_ir, source, products, inputs = _interleaved_fixture()
        repeated = copy.deepcopy(inputs[1])
        repeated["ordinal"] = 2
        repeated["occurrence_id"] = input_occurrence_id(
            BUILD_SHA, SOURCE_TARGET, 2,
        )
        inputs.append(repeated)
        source["ordered_link_occurrences"].append(_source_row(
            6, "input", input_ordinal=2, binding_sha256="c" * 64,
            dependency_target_id="build-library",
        ))

        with self.assertRaisesRegex(ValueError, "package_repeat_unsupported"):
            project_layered_link_expectation(
                build_ir, source, products, inputs,
                rust_target_id=RUST_TARGET,
                build_ir_artifact_sha256=BUILD_SHA,
            )


def _interleaved_fixture():
    inputs = [
        {
            "ordinal": 0,
            "occurrence_id": input_occurrence_id(BUILD_SHA, SOURCE_TARGET, 0),
            "role": "link-input", "dependency_target_id": None,
            "object_target_id": "build-object", "source_unit_id": "source-object",
            "module_id": "module-consumer", "binding_sha256": "b" * 64,
        },
        {
            "ordinal": 1,
            "occurrence_id": input_occurrence_id(BUILD_SHA, SOURCE_TARGET, 1),
            "role": "link-input", "dependency_target_id": "target-library",
            "object_target_id": None, "source_unit_id": None, "module_id": None,
            "binding_sha256": "c" * 64,
        },
    ]
    dependencies = [
        _dependency("system-0", ORDERED_LINK_ARGUMENT_KIND, "-pthread", 0),
        _dependency("native-0", NATIVE_DEPENDENCY_KIND, "libportable.so", 3),
        _dependency("system-1", ORDERED_LINK_ARGUMENT_KIND, "-pthread", 1),
        _dependency("native-1", NATIVE_DEPENDENCY_KIND, "libportable.so", 5),
    ]
    source = {
        "target_id": SOURCE_TARGET, "kind": "link",
        "ordered_link_arguments": ["-pthread", "-pthread"],
        "ordered_link_search_roots": [], "link_response_files": [],
        "ordered_link_occurrences": [
            _source_row(0, "input", input_ordinal=0,
                        binding_sha256="b" * 64,
                        dependency_target_id="build-object"),
            _source_row(1, "system-argument", external_dependency_id="system-0"),
            _source_row(2, "input", input_ordinal=1,
                        binding_sha256="c" * 64,
                        dependency_target_id="build-library"),
            _source_row(3, "external-native-library",
                        external_dependency_id="native-0"),
            _source_row(4, "system-argument", external_dependency_id="system-1"),
            _source_row(5, "external-native-library",
                        external_dependency_id="native-1"),
        ],
    }
    products = {"build-library": {
        "package_id": "package-library", "target_id": "target-library",
    }}
    return {"external_dependencies": dependencies}, source, products, inputs


def _system_fixture(argument: str):
    dependency = _dependency(
        "system-only", ORDERED_LINK_ARGUMENT_KIND, argument, 0,
    )
    target = {
        "target_id": SOURCE_TARGET, "kind": "link",
        "ordered_link_arguments": [argument], "ordered_link_search_roots": [],
        "link_response_files": [],
        "ordered_link_occurrences": [_source_row(
            0, "system-argument", external_dependency_id="system-only",
        )],
    }
    return {"external_dependencies": [dependency]}, target


def _source_row(ordinal, kind, **changes):
    row = {
        "ordinal": ordinal, "argument_index": ordinal, "argument_count": 1,
        "kind": kind, "input_ordinal": None, "binding_sha256": None,
        "dependency_target_id": None, "external_dependency_id": None,
    }
    row.update(changes)
    return row


def _dependency(
    dependency_id, kind, name, ordinal, *, library_format="shared-library",
):
    value = {
        "dependency_id": dependency_id, "kind": kind, "name": name,
        "consumer_target_ids": [SOURCE_TARGET], "ordinal": ordinal,
    }
    if kind == NATIVE_DEPENDENCY_KIND:
        value["format"] = library_format
    return value


def _target(expectation, inputs):
    return {
        "target_id": RUST_TARGET, "build_ir_target_id": SOURCE_TARGET,
        "module_ids": ["module-consumer"], "input_occurrences": copy.deepcopy(inputs),
        "ordered_link_arguments": ["-pthread", "-pthread"],
        "link_expectation": expectation,
        "evidence": {"build_ir_sha256s": [BUILD_SHA]},
    }


def _rehash_expectation(value):
    core = {key: item for key, item in value.items()
            if key != "expectation_sha256"}
    value["expectation_sha256"] = content_sha256(core)


if __name__ == "__main__":
    unittest.main()

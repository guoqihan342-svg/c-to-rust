from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.rust_project_ir_v3 import (
    build_rust_project_ir_v3,
)
from validation.tools._project_migration_harness.rust_project_ir_v3_topology import (
    derive_rust_project_ir_v3_topology,
)
from validation.tools._project_migration_harness.rust_project_ir_v3_topology_products import (
    input_occurrence_id,
)
from validation.tools._project_migration_harness.rust_project_ir_v3_validation import (
    module_id_for_target_candidate,
)


SEMANTIC = "1" * 64
ARTIFACT = "a" * 64


class RustProjectIRV3TopologyTests(unittest.TestCase):
    def test_archive_executable_dependency_and_object_mapping(self) -> None:
        archive = _product("archive", "archive", ["obj-lib"], [])
        binary = _product(
            "application", "link", ["archive", "obj-main"],
            ["-Wl,--as-needed"], name="lib-misleading.so",
        )
        build = _build([_unit("lib"), _unit("main")], [archive, binary])
        scopes = {
            "group-lib": _scope("lib", ["archive", "application"], ["application"]),
            "group-main": _scope("main", ["application"], ["application"]),
        }
        candidates = [_candidate("group-main"), _candidate("group-lib")]

        topology = _derive([build], scopes, candidates)

        self.assertEqual(
            {"workspace", "packages", "targets", "modules",
             "topology_status", "topology_blockers"},
            set(topology),
        )
        self.assertEqual("ready", topology["topology_status"])
        packages = {item["build_ir_target_id"]: item for item in topology["packages"]}
        targets = {item["build_ir_target_id"]: item for item in topology["targets"]}
        self.assertEqual("static-library", packages["archive"]["product_kind"])
        self.assertEqual("executable", packages["application"]["product_kind"])
        self.assertEqual(
            [packages["archive"]["package_id"]],
            packages["application"]["dependency_package_ids"],
        )
        self.assertEqual([0], [
            item["ordinal"] for item in targets["archive"]["input_occurrences"]
        ])
        archive_input = targets["archive"]["input_occurrences"][0]
        self.assertEqual("obj-lib", archive_input["object_target_id"])
        self.assertEqual("lib", archive_input["source_unit_id"])
        self.assertIsNone(archive_input["dependency_target_id"])
        self.assertEqual(
            input_occurrence_id(ARTIFACT, "archive", 0),
            archive_input["occurrence_id"],
        )
        application_inputs = targets["application"]["input_occurrences"]
        self.assertEqual([
            input_occurrence_id(ARTIFACT, "application", ordinal)
            for ordinal in range(2)
        ], [item["occurrence_id"] for item in application_inputs])
        self.assertEqual(targets["archive"]["target_id"],
                         application_inputs[0]["dependency_target_id"])
        self.assertTrue(all(application_inputs[0][key] is None for key in (
            "object_target_id", "source_unit_id", "module_id",
        )))
        self.assertEqual("obj-main", application_inputs[1]["object_target_id"])
        self.assertEqual(
            ["-Wl,--as-needed"], targets["application"]["ordered_link_arguments"],
        )
        module = next(item for item in topology["modules"]
                      if item["unit_id"] == "group-lib")
        self.assertEqual(module["module_id"], module_id_for_target_candidate(
            module["target_namespace_id"], module["unit_id"],
            module["candidate_sha256"], module["source_unit_ids"],
        ))
        for owner in [topology["workspace"], *topology["packages"],
                      *topology["targets"], *topology["modules"]]:
            self.assertEqual([ARTIFACT], owner["evidence"]["build_ir_sha256s"])
            self.assertNotIn(SEMANTIC, owner["evidence"]["build_ir_sha256s"])
        ir = build_rust_project_ir_v3(
            migration_dag_ref=_ref("dag.json", "b" * 64),
            migration_graph_ref=_ref("graph.json", "c" * 64),
            build_ir_refs=[_ref("build.json", ARTIFACT)],
            candidate_refs=candidates,
            workspace=topology["workspace"], packages=topology["packages"],
            targets=topology["targets"], modules=topology["modules"],
            topology_blockers=topology["topology_blockers"],
        )
        self.assertEqual(3, ir["schema_version"])
        self.assertEqual(topology, _derive([build], dict(reversed(list(scopes.items()))),
                                           list(reversed(candidates))))

    def test_shared_and_executable_classification_ignore_names(self) -> None:
        cases = [
            ("--shared", "program.exe", "shared-library", "cdylib"),
            ("/DLL", "archive-looking.a", "shared-library", "cdylib"),
            ("-Wl,--gc-sections", "lib-fake.so", "executable", "bin"),
        ]
        for argument, name, product_kind, rust_kind in cases:
            with self.subTest(argument=argument):
                product = _product("product", "link", ["obj-unit"], [argument], name=name)
                build = _build([_unit("unit")], [product])
                topology = _derive(
                    [build], {"group": _scope("unit", ["product"], ["product"])},
                    [_candidate("group")],
                )
                self.assertEqual(product_kind, topology["packages"][0]["product_kind"])
                self.assertEqual(rust_kind, topology["targets"][0]["kind"])

    def test_candidate_is_duplicated_across_proven_namespaces(self) -> None:
        products = [
            _product("left", "link", ["obj-unit"], ["-Wl,left"]),
            _product("right", "link", ["obj-unit"], ["-Wl,right"]),
        ]
        build = _build([_unit("unit")], products)
        topology = _derive(
            [build], {"group": _scope("unit", ["left", "right"], ["left", "right"])},
            [_candidate("group")],
        )

        self.assertEqual("ready", topology["topology_status"])
        self.assertEqual(2, len(topology["modules"]))
        self.assertEqual(2, len({item["module_id"] for item in topology["modules"]}))
        self.assertEqual(2, len({item["target_namespace_id"]
                                for item in topology["modules"]}))

    def test_same_source_debug_release_variants_stay_isolated(self) -> None:
        shared_source = {"path": "src/unit.c", "sha256": "d" * 64}
        units = [
            _unit("debug", source=shared_source, index=0, count=2),
            _unit("release", source=shared_source, index=1, count=2),
        ]
        build = _build(units, [
            _product("debug-lib", "archive", ["obj-debug"], []),
            _product("release-lib", "archive", ["obj-release"], []),
        ])
        candidates = [_candidate("group-debug", "e" * 64),
                      _candidate("group-release", "e" * 64)]
        topology = _derive([build], {
            "group-debug": _scope("debug", ["debug-lib"], ["debug-lib"], 0, 2),
            "group-release": _scope(
                "release", ["release-lib"], ["release-lib"], 1, 2,
            ),
        }, candidates)

        self.assertEqual("ready", topology["topology_status"])
        self.assertEqual({("debug",), ("release",)}, {
            tuple(item["source_unit_ids"]) for item in topology["modules"]
        })
        self.assertEqual(2, len({item["module_id"] for item in topology["modules"]}))

    def test_defined_ambiguities_block_without_guessing(self) -> None:
        cases = [
            ("object-only", _build([_unit("unit")], []),
             _scope("unit", [], []), "build_ir_object_only", True),
            ("relocatable", _build([_unit("unit")], [
                _product("product", "link", ["obj-unit"], ["-r"]),
            ]), _scope("unit", ["product"], ["product"]),
             "build_ir_relocatable_product_unsupported", True),
            ("unknown-product", _build([_unit("unit")], [
                _product("product", "link", ["obj-unit"], ["-Wl,x"]),
            ], driver=False), _scope("unit", ["product"], ["product"]),
             "build_ir_product_kind_unknown", True),
            ("missing-scope", _build([_unit("unit")], [
                _product("product", "archive", ["obj-unit"], []),
            ]), None, "candidate_target_scope_missing", False),
        ]
        for label, build, scope, code, include_scope in cases:
            with self.subTest(label=label):
                scopes = {"group": scope} if include_scope else {}
                if label == "missing-scope":
                    with self.assertRaisesRegex(ValueError, "object_input_unowned"):
                        _derive([build], scopes, [_candidate("group")])
                    continue
                topology = _derive([build], scopes, [_candidate("group")])
                self.assertEqual("blocked", topology["topology_status"])
                self.assertIn(code, _codes(topology))
                if label == "object-only":
                    self.assertIn("candidate_common_consumer_missing", _codes(topology))

    def test_target_namespace_collision_blocks(self) -> None:
        first = _build([_unit("left")], [
            _product("same-product", "archive", ["obj-left"], []),
        ])
        second = _build([_unit("right")], [
            _product("same-product", "archive", ["obj-right"], []),
        ], semantic="2" * 64)
        topology = derive_rust_project_ir_v3_topology(
            [first, second],
            {"group": _scope("left", ["same-product"], ["same-product"])},
            [_candidate("group")],
            build_ir_binding_sha256s={SEMANTIC: ARTIFACT, "2" * 64: "b" * 64},
        )
        self.assertIn("build_ir_target_namespace_collision", _codes(topology))

    def test_build_binding_mapping_must_be_complete_and_one_to_one(self) -> None:
        build = _build([_unit("unit")], [
            _product("product", "archive", ["obj-unit"], []),
        ])
        args = ([build], {"group": _scope("unit", ["product"], ["product"])},
                [_candidate("group")])
        bad_values = [
            {}, {"2" * 64: ARTIFACT}, {SEMANTIC: "bad"},
        ]
        for value in bad_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "build_binding_sha256s_invalid"):
                    derive_rust_project_ir_v3_topology(
                        *args, build_ir_binding_sha256s=value,
                    )
        second = _build([_unit("other")], [], semantic="2" * 64)
        with self.assertRaisesRegex(ValueError, "build_binding_sha256s_invalid"):
            derive_rust_project_ir_v3_topology(
                [build, second], args[1], args[2],
                build_ir_binding_sha256s={SEMANTIC: ARTIFACT, "2" * 64: ARTIFACT},
            )


def _derive(builds, scopes, candidates):
    return derive_rust_project_ir_v3_topology(
        builds, scopes, candidates,
        build_ir_binding_sha256s={item["semantic_sha256"]: ARTIFACT for item in builds},
    )


def _unit(unit_id, *, source=None, index=0, count=1):
    source = source or {"path": f"src/{unit_id}.c", "sha256": content_sha256(unit_id)}
    return {"unit_id": unit_id, "variant_index": index, "variant_count": count,
            "source": dict(source)}


def _product(target_id, kind, inputs, arguments, *, name=None):
    occurrences = [{
        "ordinal": index, "role": "link-input", "dependency_target_id": dependency,
        "binding": {"path": f"build/{dependency}", "kind": "file",
                    "materialized": True, "sha256": content_sha256(dependency),
                    "size_bytes": 1},
    } for index, dependency in enumerate(inputs)]
    return {
        "target_id": target_id, "name": name or target_id, "kind": kind,
        "dependency_target_ids": list(dict.fromkeys(inputs)),
        "ordered_inputs": occurrences, "ordered_link_arguments": list(arguments),
        "toolchain_id": "link-driver" if kind == "link" else "archiver",
    }


def _build(units, products, *, semantic=SEMANTIC, driver=True):
    objects = [{"target_id": f"obj-{item['unit_id']}", "name": item["unit_id"],
                "kind": "object", "dependency_target_ids": [],
                "ordered_inputs": [], "ordered_link_arguments": []}
               for item in units]
    toolchains = ([{"toolchain_id": "link-driver", "role": "linker-driver"}]
                  if driver else [])
    return {"semantic_sha256": semantic, "translation_units": units,
            "targets": [*objects, *products], "toolchains": toolchains}


def _scope(unit_id, reachable, terminal, index=0, count=1):
    record = {"unit_id": unit_id, "variant": {"key": unit_id, "index": index,
                                               "count": count},
              "object_owner_target_id": f"obj-{unit_id}",
              "reachable_target_ids": sorted(reachable),
              "terminal_target_ids": sorted(terminal)}
    status = "object-only-conservative" if not reachable else "target-bound"
    payload = {"schema_version": 1, "scope_kind": "scc-build-target-scope",
               "source_unit_ids": [unit_id], "unit_scopes": [record],
               "object_target_ids": [f"obj-{unit_id}"],
               "reachable_target_ids": sorted(reachable),
               "terminal_target_ids": sorted(terminal),
               "shared_reachable_target_ids": sorted(reachable),
               "domain_status": status}
    return {**payload, "scope_sha256": content_sha256(payload)}


def _candidate(unit_id, sha=None):
    sha = sha or content_sha256({"candidate": unit_id})
    return {"unit_id": unit_id, "artifact_id": f"candidate-{unit_id}",
            "source": _ref(f"candidates/{unit_id}.rs", sha)}


def _ref(path, sha):
    return {"path": path, "sha256": sha, "size_bytes": 1}


def _codes(topology):
    return {item["code"] for item in topology["topology_blockers"]}


if __name__ == "__main__":
    unittest.main()

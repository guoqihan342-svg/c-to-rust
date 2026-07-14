from __future__ import annotations

import unittest

from validation.tools._project_migration_harness.build_ir_toolchains import (
    MAX_LINK_TARGETS,
    MAX_MAKE_COMMANDS,
    MAX_TOKEN_BYTES,
    MAX_TOOL_REQUESTS,
    MAX_WRAPPERS_PER_UNIT,
    make_tool_requests,
    merge_tool_requests,
    standard_tool_requests,
)


class ProjectMigrationBuildIRToolchainTests(unittest.TestCase):
    def test_standard_roles_are_derived_from_generic_fact_fields(self) -> None:
        discovery = {
            "project_name": "renamed-project",
            "translation_units": [{
                "source": {"path": "renamed/source.c"},
                "function_name": "renamed_function",
                "compiler": "renamed-compiler",
                "compiler_wrappers": ["renamed-cache"],
            }],
        }
        closure = {
            "project_identity": "another-renamed-project",
            "target_link_closure": {"targets": [
                {"driver": "renamed-archiver", "archive_operation": "rcs",
                 "ranlib_drivers": ["renamed-ranlib"],
                 "output": {"path": "renamed/lib.a"}},
                {"driver": "renamed-linker",
                 "output": {"path": "renamed/program"}},
            ]},
        }

        self.assertEqual(
            [
                {"token": "renamed-compiler", "role": "compiler-driver"},
                {"token": "renamed-cache", "role": "compiler-wrapper"},
                {"token": "renamed-archiver", "role": "archiver"},
                {"token": "renamed-ranlib", "role": "ranlib"},
                {"token": "renamed-linker", "role": "linker-driver"},
            ],
            standard_tool_requests(discovery, closure),
        )

        discovery["project_name"] = "unrelated-identity"
        discovery["translation_units"][0]["source"]["path"] = "other/tree.c"
        discovery["translation_units"][0]["function_name"] = "other_function"
        closure["project_identity"] = "unrelated-closure"
        closure["target_link_closure"]["targets"][0]["output"]["path"] = "other/lib.a"
        self.assertEqual(
            [
                {"token": "renamed-compiler", "role": "compiler-driver"},
                {"token": "renamed-cache", "role": "compiler-wrapper"},
                {"token": "renamed-archiver", "role": "archiver"},
                {"token": "renamed-ranlib", "role": "ranlib"},
                {"token": "renamed-linker", "role": "linker-driver"},
            ],
            standard_tool_requests(discovery, closure),
        )

    def test_make_roles_cover_compile_archive_ranlib_and_link(self) -> None:
        requests = make_tool_requests({"commands": [
            {"kind": "compile", "tool": "vendor-cc"},
            {"kind": "archive", "tool": "vendor-ar"},
            {"kind": "ranlib", "tool": "vendor-ranlib"},
            {"kind": "link", "tool": "vendor-cc"},
        ]})

        self.assertEqual(
            [
                {"token": "vendor-cc", "role": "compiler-driver"},
                {"token": "vendor-ar", "role": "archiver"},
                {"token": "vendor-ranlib", "role": "ranlib"},
                {"token": "vendor-cc", "role": "linker-driver"},
            ],
            requests,
        )
        self.assertEqual(
            [
                {"token": "vendor-ar", "roles": ["archiver"]},
                {"token": "vendor-cc", "roles": [
                    "compiler-driver", "linker-driver",
                ]},
                {"token": "vendor-ranlib", "roles": ["ranlib"]},
            ],
            merge_tool_requests(requests),
        )

    def test_merge_is_stable_and_deduplicates_roles(self) -> None:
        self.assertEqual(
            [
                {"token": "a-tool", "roles": [
                    "compiler-driver", "compiler-wrapper", "linker-driver",
                ]},
                {"token": "z-tool", "roles": ["archiver"]},
            ],
            merge_tool_requests([
                {"token": "z-tool", "role": "archiver"},
                {"token": "a-tool", "role": "linker-driver"},
                {"token": "a-tool", "role": "compiler-driver"},
                {"token": "a-tool", "role": "linker-driver"},
                {"token": "a-tool", "role": "compiler-wrapper"},
            ]),
        )

    def test_missing_unknown_and_malformed_facts_fail_closed(self) -> None:
        valid_discovery = {"translation_units": [{
            "compiler": "cc", "compiler_wrappers": [],
        }]}
        valid_closure = {"target_link_closure": {"targets": []}}
        invalid_calls = {
            "discovery_type": lambda: standard_tool_requests([], valid_closure),
            "missing_units": lambda: standard_tool_requests({}, valid_closure),
            "unit_type": lambda: standard_tool_requests(
                {"translation_units": ["unit"]}, valid_closure,
            ),
            "missing_compiler": lambda: standard_tool_requests(
                {"translation_units": [{"compiler_wrappers": []}]}, valid_closure,
            ),
            "wrapper_type": lambda: standard_tool_requests(
                {"translation_units": [{"compiler": "cc", "compiler_wrappers": "cache"}]},
                valid_closure,
            ),
            "missing_link_closure": lambda: standard_tool_requests(valid_discovery, {}),
            "target_type": lambda: standard_tool_requests(
                valid_discovery, {"target_link_closure": {"targets": ["target"]}},
            ),
            "missing_driver": lambda: standard_tool_requests(
                valid_discovery, {"target_link_closure": {"targets": [{}]}},
            ),
            "archive_operation_type": lambda: standard_tool_requests(
                valid_discovery,
                {"target_link_closure": {"targets": [
                    {"driver": "ar", "archive_operation": None},
                ]}},
            ),
            "missing_commands": lambda: make_tool_requests({}),
            "command_type": lambda: make_tool_requests({"commands": ["cc"]}),
            "missing_kind": lambda: make_tool_requests({"commands": [{"tool": "cc"}]}),
            "unknown_kind": lambda: make_tool_requests({"commands": [
                {"kind": "configure", "tool": "cc"},
            ]}),
            "missing_tool": lambda: make_tool_requests({"commands": [
                {"kind": "compile"},
            ]}),
            "path_token": lambda: make_tool_requests({"commands": [
                {"kind": "compile", "tool": "../cc"},
            ]}),
            "missing_token": lambda: merge_tool_requests([
                {"role": "compiler-driver"},
            ]),
            "unknown_role": lambda: merge_tool_requests([
                {"token": "cc", "role": "project-specific-driver"},
            ]),
            "unknown_request_field": lambda: merge_tool_requests([
                {"token": "cc", "role": "compiler-driver", "path": "src/a.c"},
            ]),
        }
        for label, call in invalid_calls.items():
            with self.subTest(label=label), self.assertRaises(ValueError):
                call()

    def test_all_collection_and_token_limits_fail_closed(self) -> None:
        valid_discovery = {"translation_units": [{
            "compiler": "cc", "compiler_wrappers": [],
        }]}
        with self.assertRaises(ValueError):
            standard_tool_requests(
                {"translation_units": [{
                    "compiler": "cc",
                    "compiler_wrappers": ["cache"] * (MAX_WRAPPERS_PER_UNIT + 1),
                }]},
                {"target_link_closure": {"targets": []}},
            )
        with self.assertRaises(ValueError):
            standard_tool_requests(
                valid_discovery,
                {"target_link_closure": {
                    "targets": [{"driver": "ld"}] * (MAX_LINK_TARGETS + 1),
                }},
            )
        with self.assertRaises(ValueError):
            make_tool_requests({
                "commands": [{"kind": "compile", "tool": "cc"}]
                * (MAX_MAKE_COMMANDS + 1),
            })
        with self.assertRaises(ValueError):
            merge_tool_requests([
                {"token": f"tool-{index}", "role": "compiler-driver"}
                for index in range(MAX_TOOL_REQUESTS + 1)
            ])
        with self.assertRaises(ValueError):
            merge_tool_requests([{
                "token": "x" * (MAX_TOKEN_BYTES + 1),
                "role": "compiler-driver",
            }])


if __name__ == "__main__":
    unittest.main()

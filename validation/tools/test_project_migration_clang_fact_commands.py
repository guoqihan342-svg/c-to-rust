from __future__ import annotations

import copy
import json

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.build_ir import (
    finalize_build_ir,
    stable_build_id,
)
from validation.tools._project_migration_harness.build_ir_host_toolchains import (
    HostToolchainProjection,
)
from validation.tools._project_migration_harness.build_ir_projection import (
    project_build_ir,
)
from validation.tools._project_migration_harness.build_ir_validation import (
    validate_build_ir,
)
from validation.tools._project_migration_harness.c_toolchain_schema import (
    C_TOOLCHAIN_RAW_ROLE,
)
from validation.tools._project_migration_harness.clang_fact_commands import (
    CLANG_TOOLCHAIN_BINDING_KIND,
    build_clang_fact_plans,
    validate_clang_fact_plan,
)
from validation.tools.project_migration_build_ir_host_test_support import (
    BuildIRHostBindingTestCase,
    artifact_reference,
    binding,
)


class ClangFactCommandTests(BuildIRHostBindingTestCase):
    def build_ir(self) -> dict:
        output = binding("build/unit.o", b"object")
        closure = {
            "status": "ready",
            "compile_outputs": [output],
            "target_link_closure": {"targets": []},
            "generated_include_roots": [],
            "generated_stage_facts": {},
            "blockers": [],
        }
        discovery = {
            "status": "ready",
            "compile_database": binding("facts/compile-commands.json", b"compile-db"),
            "translation_units": [{
                "unit_id": "unit-contract",
                "variant_index": 0,
                "variant_count": 1,
                "source": binding("src/unit.c", self.source_bytes),
                "working_directory": ".",
                "compiler": "gcc",
                "compiler_wrappers": [],
                "language": "c",
                "includes": [
                    {"kind": "user", "path": "include", "scope": "repository"},
                    {"kind": "system", "path": "sys", "scope": "repository"},
                    {"kind": "quote", "path": "quote", "scope": "repository"},
                    {"kind": "after", "path": "after", "scope": "repository"},
                    {"kind": "forced", "path": "config.h", "scope": "repository"},
                    {"kind": "macros", "path": "macros.h", "scope": "repository"},
                ],
                "defines": [{"name": "FEATURE", "value": "1"},
                            {"name": "WIDTH", "value": "32"}],
                "redacted_define_count": 0,
                "semantic_flags": ["-std=c11", "-m64", "-pthread"],
                "expanded_argv_sha256": content_sha256([
                    "gcc", "-std=c11", "-m64", "-pthread", "-c", "src/unit.c",
                ]),
                "response_files": [],
                "output": "build/unit.o",
                "entry": {"index": 0, "sha256": content_sha256("entry")},
            }],
            "generated_build_closure": closure,
        }
        verification = {"status": "verified", "blockers": []}
        evidence = self.collect([{"token": "gcc", "roles": ["compiler-driver"]}])
        refs = [
            {"role": "discovery", **artifact_reference("facts/discovery.json", discovery)},
            {"role": "generated-build-closure",
             **artifact_reference("facts/generated-closure.json", closure)},
            {"role": "generated-build-closure-verification",
             **artifact_reference("facts/generated-verification.json", verification)},
            {"role": C_TOOLCHAIN_RAW_ROLE,
             **artifact_reference("facts/c-toolchain.json", evidence)},
        ]
        result = project_build_ir(discovery, closure, verification, refs, evidence)
        validate_build_ir(result)
        return result

    def clang_binding(self, target: str = "x86_64-linux-gnu") -> dict:
        evidence = self.collect([{"token": "clang", "roles": ["compiler-driver"]}])
        record = HostToolchainProjection(evidence).records()[0]
        driver = next(item for item in record["tools"] if item["relation"] == "driver")
        target_probe = dict(driver["target"])
        target_probe["value"] = target
        core = {
            "schema_version": 1,
            "artifact_kind": CLANG_TOOLCHAIN_BINDING_KIND,
            "status": "ready",
            "family": driver["family"],
            "basename": driver["basename"],
            "binary": dict(driver["binary"]),
            "version": dict(driver["version"]),
            "target": target_probe,
            "resource_dir": self.path_probe(driver["resource_dir"]),
            "sysroot": self.path_probe(driver["sysroot"]),
        }
        return {**core, "binding_sha256": content_sha256(core)}

    @staticmethod
    def path_probe(value: dict) -> dict:
        return {key: value[key] for key in ("status", "stdout_sha256", "stderr_sha256")}

    @staticmethod
    def resign(value: dict) -> dict:
        value = copy.deepcopy(value)
        return finalize_build_ir(value)

    @staticmethod
    def resign_binding(value: dict) -> dict:
        value = copy.deepcopy(value)
        core = {key: item for key, item in value.items() if key != "binding_sha256"}
        value["binding_sha256"] = content_sha256(core)
        return value

    def replace_host_target(self, build_ir: dict, *, status: str,
                            value: str | None) -> dict:
        changed = copy.deepcopy(build_ir)
        record = changed["toolchains"][0]
        old_id = record["toolchain_id"]
        driver = next(item for item in record["tools"] if item["relation"] == "driver")
        driver["target"]["status"], driver["target"]["value"] = status, value
        core = {key: item for key, item in record.items()
                if key not in {"toolchain_id", "provenance"}}
        new_id = stable_build_id("toolchain", core)
        record["toolchain_id"] = new_id
        for collection in (changed["translation_units"], changed["abi_facts"],
                           changed["targets"]):
            for item in collection:
                if item.get("toolchain_id") == old_id:
                    item["toolchain_id"] = new_id
        return finalize_build_ir(changed)

    def test_exact_fixed_argv_uses_independent_clang_binding(self) -> None:
        build_ir, clang = self.build_ir(), self.clang_binding()
        ast, layout = build_clang_fact_plans(build_ir, clang)
        common = [
            "clang", "--no-default-config", "--target=x86_64-linux-gnu",
            "-resource-dir", "/toolchain/resource",
            "-std=c11", "-m64", "-pthread",
            "-I", "/workspace/include", "-isystem", "/workspace/sys",
            "-iquote", "/workspace/quote", "-idirafter", "/workspace/after",
            "-include", "/workspace/config.h", "-imacros", "/workspace/macros.h",
            "-DFEATURE=1", "-DWIDTH=32", "-fsyntax-only", "-Xclang",
        ]
        self.assertEqual([*common, "-ast-dump=json", "--", "src/unit.c"],
                         ast["argv"])
        self.assertEqual([*common, "-fdump-record-layouts-complete", "--",
                          "src/unit.c"], layout["argv"])
        self.assertEqual("gcc", build_ir["translation_units"][0]["compiler"])
        for plan in (ast, layout):
            self.assertIs(False, plan["semantic_gate"])
            self.assertEqual(0, plan["translation_coverage_numerator"])
            self.assertEqual(plan, validate_clang_fact_plan(plan, build_ir, clang))
            encoded = json.dumps(plan)
            self.assertNotIn(str(self.root), encoded)
            self.assertNotIn("resolved_path", encoded)
            self.assertNotIn("value\": \"/opt/llvm", encoded)

    def test_gates_have_isolated_argv_input_limits_and_plan_identity(self) -> None:
        ast, layout = build_clang_fact_plans(self.build_ir(), self.clang_binding())
        for field in ("argv_sha256", "input_sha256", "plan_sha256",
                      "max_stdout_bytes", "max_combined_bytes"):
            self.assertNotEqual(ast[field], layout[field])
        for field in ("compile_context_sha256", "target_context_sha256",
                      "toolchain_portable_sha256"):
            self.assertEqual(ast[field], layout[field])

    def test_target_toolchain_argv_and_plan_drift_fail_closed(self) -> None:
        build_ir, clang = self.build_ir(), self.clang_binding()
        plan = build_clang_fact_plans(build_ir, clang)[0]
        incompatible = self.clang_binding("aarch64-unknown-linux-gnu")
        with self.assertRaises(ValueError):
            build_clang_fact_plans(build_ir, incompatible)
        changed_tool = copy.deepcopy(clang)
        changed_tool["binary"]["sha256"] = "a" * 64
        changed_tool = self.resign_binding(changed_tool)
        with self.assertRaises(ValueError):
            validate_clang_fact_plan(plan, build_ir, changed_tool)
        changed_argv = copy.deepcopy(plan)
        changed_argv["argv"][2] = "-std=c17"
        changed_argv["argv_sha256"] = content_sha256(changed_argv["argv"])
        changed_argv["plan_sha256"] = content_sha256({
            key: value for key, value in changed_argv.items() if key != "plan_sha256"
        })
        with self.assertRaises(ValueError):
            validate_clang_fact_plan(changed_argv, build_ir, clang)
        changed_plan = copy.deepcopy(plan)
        changed_plan["max_stdout_bytes"] -= 1
        changed_plan["plan_sha256"] = content_sha256({
            key: value for key, value in changed_plan.items() if key != "plan_sha256"
        })
        with self.assertRaises(ValueError):
            validate_clang_fact_plan(changed_plan, build_ir, clang)
        bad_sha = copy.deepcopy(plan)
        bad_sha["plan_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "plan_sha256"):
            validate_clang_fact_plan(bad_sha, build_ir, clang)

    def test_missing_or_drifted_build_ir_target_and_abi_fail_closed(self) -> None:
        build_ir, clang = self.build_ir(), self.clang_binding()
        missing = self.replace_host_target(build_ir, status="failed", value=None)
        validate_build_ir(missing)
        with self.assertRaisesRegex(ValueError, "host_target_missing"):
            build_clang_fact_plans(missing, clang)
        drifted = self.replace_host_target(
            build_ir, status="reported", value="aarch64-unknown-linux-gnu",
        )
        validate_build_ir(drifted)
        with self.assertRaisesRegex(ValueError, "target_incompatible"):
            build_clang_fact_plans(drifted, clang)
        abi = copy.deepcopy(build_ir)
        abi["abi_facts"][0]["target_flags"] = ["-m32"]
        abi = finalize_build_ir(abi)
        with self.assertRaisesRegex(ValueError, "abi_target_drifted"):
            build_clang_fact_plans(abi, clang)

    def test_rejects_replay_redaction_external_paths_and_path_escape(self) -> None:
        base, clang = self.build_ir(), self.clang_binding()
        mutations = []
        wrappers = copy.deepcopy(base)
        wrappers["translation_units"][0]["compiler_wrappers"] = ["distcc"]
        mutations.append(wrappers)
        response = copy.deepcopy(base)
        response["translation_units"][0]["compile_arguments"]["response_files"] = [
            binding("facts/args.rsp", b"-DATTACK=1")
        ]
        mutations.append(response)
        redacted = copy.deepcopy(base)
        redacted["translation_units"][0]["redacted_define_count"] = 1
        mutations.append(redacted)
        external = copy.deepcopy(base)
        external["translation_units"][0]["includes"][0] = {
            "kind": "user", "path": "<external-path>", "scope": "external",
        }
        mutations.append(external)
        parent = copy.deepcopy(base)
        parent["translation_units"][0]["includes"][0]["path"] = "../include"
        mutations.append(parent)
        absolute = copy.deepcopy(base)
        absolute["translation_units"][0]["working_directory"] = "/host/project"
        mutations.append(absolute)
        source = copy.deepcopy(base)
        source["translation_units"][0]["source"]["path"] = "/host/unit.c"
        mutations.append(source)
        for value in mutations:
            with self.subTest(value=value["translation_units"][0]), self.assertRaises(ValueError):
                build_clang_fact_plans(finalize_build_ir(value), clang)

    def test_rejects_parameter_and_define_injection_without_silent_deletion(self) -> None:
        base, clang = self.build_ir(), self.clang_binding()
        dangerous = [
            ["@args.rsp"], ["-Xclang", "-load"], ["-cc1"],
            ["-fplugin=evil.so"], ["-o", "out.o"], ["-MF"], ["-shared"],
            ["-I", "include"], ["-mllvm", "-evil"], ["--sysroot=/tmp"],
            ["-Wl,-rpath,/tmp"], ["-std=c11;touch"],
        ]
        for flags in dangerous:
            changed = copy.deepcopy(base)
            changed["translation_units"][0]["compile_arguments"]["semantic_flags"] = flags
            changed["abi_facts"][0]["target_flags"] = [
                item for item in flags if item.startswith(("-m", "-target", "--target"))
            ]
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                build_clang_fact_plans(finalize_build_ir(changed), clang)
        define = copy.deepcopy(base)
        define["translation_units"][0]["defines"][0]["value"] = "1;touch"
        with self.assertRaisesRegex(ValueError, "define_injection"):
            build_clang_fact_plans(finalize_build_ir(define), clang)

    def test_repository_rename_does_not_change_plans(self) -> None:
        before_ir, clang = self.build_ir(), self.clang_binding()
        before = build_clang_fact_plans(before_ir, clang)
        self.project_root.rename(self.root / "renamed-project")
        after_ir = self.build_ir()
        self.assertEqual(before_ir, after_ir)
        self.assertEqual(before, build_clang_fact_plans(after_ir, clang))


if __name__ == "__main__":
    import unittest
    unittest.main()

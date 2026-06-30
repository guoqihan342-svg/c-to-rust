import json
import tomllib
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_DIR = REPO_ROOT / "config" / "competition-env"
COMPAT_PROFILE_DIR = (
    REPO_ROOT
    / "validation"
    / "environment-profiles"
    / "huawei-competition-ubuntu-24.04"
)
OLD_FLASHDB_SOURCE_COMMIT = "93d175549da579b8abac07bd175ce4c3f9dde829"
RUST_MANIFESTS = [
    REPO_ROOT / "crates" / "c2r-translator" / "Cargo.toml",
    REPO_ROOT / "validation" / "l2_slices" / "Cargo.toml",
    REPO_ROOT / "flashDB_rust" / "Cargo.toml",
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def direct_rust_dependencies(manifest: Path) -> set[str]:
    cargo_toml = tomllib.loads(manifest.read_text(encoding="utf-8"))
    return set(cargo_toml.get("dependencies", {}))


class CompetitionEnvironmentProfileTests(unittest.TestCase):
    def test_default_profile_matches_competition_baseline(self) -> None:
        profile = load_json(PROFILE_DIR / "environment.json")

        self.assertEqual(profile["profile_id"], "huawei-competition-ubuntu-24.04")
        self.assertEqual(profile["canonical_path"], "config/competition-env/environment.json")
        self.assertNotIn("compatibility_paths", profile)
        self.assertEqual(
            profile["os"],
            {
                "name": "Ubuntu",
                "version": "24.04.4 LTS",
                "codename": "noble",
                "marketing_name": "Noble Numbat",
                "kernel": "5.10.0-182.0.0.95.r194_123.hce2.x86_64",
            },
        )
        self.assertEqual(
            profile["package_mirrors"],
            {
                "apt": "http://mirrors.tools.huawei.com/ubuntu",
                "pypi": "https://mirrors.tools.huawei.com/pypi/simple",
                "npm": "https://mirrors.tools.huawei.com/npm/",
                "cargo_crates_io": "sparse+http://rust.inhuawei.com/crates.io-index/",
            },
        )

        toolchain = profile["toolchain"]
        self.assertEqual(toolchain["python"], "3.12.3")
        self.assertEqual(toolchain["pip"], "24.0")
        self.assertEqual(toolchain["node"], "v24.13.0")
        self.assertEqual(toolchain["npm"], "11.6.2")
        self.assertEqual(toolchain["java"]["distribution"], "OpenJDK")
        self.assertEqual(toolchain["java"]["version"], "21.0.10")
        self.assertEqual(toolchain["java"]["vendor"], "bisheng_jdk_enterprise")
        self.assertEqual(toolchain["maven"]["version"], "3.9.11")
        self.assertEqual(toolchain["maven"]["maven_home"], "/usr/local/maven3")
        self.assertEqual(toolchain["rustc"], "1.96.0")
        self.assertEqual(toolchain["cargo"], "1.96.0")
        self.assertEqual(toolchain["gcc"], "13.3.0")
        self.assertEqual(toolchain["g++"], "13.3.0")
        self.assertNotIn("gpp", toolchain)
        self.assertEqual(toolchain["make"], "4.3")
        self.assertEqual(profile["unavailable_tools"]["go"], "not_installed")
        self.assertEqual(profile["unavailable_tools"]["cmake"], "not_found")
        self.assertEqual(profile["optional_tools"]["clang"]["default_required"], False)
        self.assertEqual(profile["optional_tools"]["clang"]["env_var"], "CLANG_PATH")
        self.assertEqual(
            profile["optional_tools"]["clang"]["command"],
            "clang -Xclang -ast-dump=json -fsyntax-only",
        )
        self.assertEqual(
            profile["optional_tools"]["clang"]["required_for"],
            ["auto_migrate.py --competition-clang-lane"],
        )
        self.assertEqual(profile["optional_tools"]["clang"]["missing_status"], "missing_clang_path")

    def test_competition_environment_profile_records_clang_lane_identity(self) -> None:
        profile = load_json(PROFILE_DIR / "environment.json")
        lane = profile["optional_lanes"]["competition_clang"]

        self.assertEqual(lane["default_enabled"], False)
        self.assertEqual(lane["auto_migrate_flag"], "--competition-clang-lane")
        self.assertEqual(lane["feature"], "clang-lowering-report")
        self.assertEqual(lane["requires_env"], ["CLANG_PATH"])
        self.assertEqual(lane["accepted_env"], ["CLANG_PATH"])
        self.assertEqual(lane["required_source"], "CLANG_PATH or project-local vendored clang")
        self.assertTrue(lane["local_fallback"]["enabled"])
        self.assertEqual(lane["ignored_env_for_ast_dump"], ["LIBCLANG_PATH"])
        self.assertEqual(lane["missing_status"], "missing_clang_path")
        self.assertEqual(
            lane["local_fallback"]["search_paths"],
            [
                "tools/llvm/bin/clang-18",
                "tools/llvm/bin/clang",
                "tools/clang/bin/clang",
            ],
        )

        validation = lane["clang_validation"]
        self.assertEqual(validation["resource_dir_command"], "clang -print-resource-dir")
        self.assertEqual(validation["minimum_tu_headers"], ["stdint.h", "stddef.h"])
        self.assertIn("-Xclang -ast-dump=json", validation["minimum_tu_command"])
        self.assertIn("resource_dir", validation["required_evidence"])
        self.assertIn("minimum_tu_ast_dump", validation["required_evidence"])

    def test_competition_profile_records_flashdb_source_pin(self) -> None:
        profile = load_json(PROFILE_DIR / "environment.json")
        flashdb = profile["source_pins"]["flashdb"]

        self.assertEqual(flashdb["repository"], "https://gitcode.com/xwxf/FlashDB.git")
        self.assertEqual(flashdb["branch"], "competition")
        self.assertEqual(flashdb["commit"], "f9d0421315c564fb890a1b14eee77b290e0d7bbe")
        self.assertEqual(
            flashdb["checkout_command"],
            "git checkout -b competition f9d0421315c564fb890a1b14eee77b290e0d7bbe",
        )
        self.assertIn("--source-repository", flashdb["runner_required_flags"])
        self.assertIn("--source-branch", flashdb["runner_required_flags"])
        self.assertIn("--require-source-commit", flashdb["runner_required_flags"])

    def test_flashdb_planned_batch_profile_follows_competition_source_pin(self) -> None:
        profile = load_json(PROFILE_DIR / "environment.json")
        flashdb = profile["source_pins"]["flashdb"]
        commit = flashdb["commit"]
        batch_profile_path = PROFILE_DIR / "planned-batches" / "flashdb-fdb-utils-accepted-evidence.json"
        batch = load_json(batch_profile_path)

        self.assertEqual(batch["schema_version"], 1)
        self.assertEqual(batch["profile_id"], "flashdb-fdb-utils-accepted-evidence")
        self.assertEqual(batch["proof_class"], "local-simulation")
        self.assertEqual(batch["target_id"], "flashdb")
        self.assertEqual(batch["source_repo_root"], "sources/FlashDB")
        self.assertEqual(batch["source_repository"], flashdb["repository"])
        self.assertEqual(batch["source_branch"], flashdb["branch"])
        self.assertEqual(batch["source_file"], "src/fdb_utils.c")
        self.assertEqual(batch["source_commit"], commit)
        self.assertEqual(batch["require_source_commit"], commit)
        self.assertEqual(batch["functions"], ["fdb_calc_crc32"])
        self.assertEqual(batch["slice_specs"], ["validation/slice-specs/flashdb-real-fdb-calc-crc32.json"])
        self.assertTrue(batch["reuse_accepted_evidence"])
        self.assertEqual(batch["accepted_evidence_root"], "validation/evidence")
        self.assertEqual(batch["mode"], "deterministic")
        self.assertTrue(batch["execute_merge"])
        self.assertEqual(
            batch["acceptance_boundary"],
            {
                "semantic_claim_source": "accepted_evidence_binding",
                "generated_draft_semantic_pass": False,
            },
        )
        self.assertNotIn(OLD_FLASHDB_SOURCE_COMMIT, json.dumps(batch, sort_keys=True))

        for path_value in [
            batch["source_repo_root"],
            batch["accepted_evidence_root"],
            *batch["slice_specs"],
        ]:
            with self.subTest(path_value=path_value):
                self.assertNotIn("\\", path_value)
                self.assertFalse(path_value.startswith("/"))
                self.assertNotIn("..", Path(path_value).parts)
                self.assertTrue((REPO_ROOT / path_value).exists())

        slice_spec = load_json(REPO_ROOT / batch["slice_specs"][0])
        self.assertEqual(slice_spec["target_id"], batch["target_id"])
        self.assertEqual(slice_spec["function_name"], "fdb_calc_crc32")
        self.assertEqual(slice_spec["source_commit"], commit)

    def test_flashdb_quickstart_examples_follow_competition_source_pin(self) -> None:
        profile = load_json(PROFILE_DIR / "environment.json")
        flashdb = profile["source_pins"]["flashdb"]
        commit = flashdb["commit"]

        quickstarts = [
            REPO_ROOT / "docs" / "c2rust-migration-agent" / "quickstart.md",
            REPO_ROOT / "docs" / "c2rust-migration-agent" / "quickstart.en.md",
        ]
        for quickstart in quickstarts:
            text = quickstart.read_text(encoding="utf-8")
            with self.subTest(quickstart=quickstart.relative_to(REPO_ROOT).as_posix()):
                self.assertNotIn(OLD_FLASHDB_SOURCE_COMMIT, text)
                self.assertIn(f"--source-commit {commit}", text)
                self.assertIn(f"--source-repository {flashdb['repository']}", text)
                self.assertIn(f"--source-branch {flashdb['branch']}", text)
                self.assertIn(f"--require-source-commit {commit}", text)
                for required_flag in flashdb["runner_required_flags"]:
                    self.assertIn(required_flag, text)

        readmes = [
            REPO_ROOT / "docs" / "c2rust-migration-agent" / "README.md",
            REPO_ROOT / "docs" / "c2rust-migration-agent" / "README.en.md",
        ]
        for readme in readmes:
            text = readme.read_text(encoding="utf-8")
            with self.subTest(readme=readme.relative_to(REPO_ROOT).as_posix()):
                self.assertNotIn(OLD_FLASHDB_SOURCE_COMMIT, text)
                self.assertIn(commit, text)

    def test_flashdb_kv_set_slice_and_evidence_follow_competition_source_pin(self) -> None:
        profile = load_json(PROFILE_DIR / "environment.json")
        flashdb = profile["source_pins"]["flashdb"]
        commit = flashdb["commit"]

        slice_spec = load_json(REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-kv-set.json")
        self.assertEqual(slice_spec["source_commit"], commit)
        self.assertEqual(slice_spec["source"]["source_commit"], commit)
        self.assertEqual(slice_spec["source"]["source_root"], "sources/FlashDB")
        self.assertNotIn(OLD_FLASHDB_SOURCE_COMMIT, json.dumps(slice_spec, sort_keys=True))

        evidence_dir = (
            REPO_ROOT
            / "validation"
            / "evidence"
            / "flashdb"
            / "auto-translation"
            / "real-fdb-kv-set"
        )
        evidence_files = [
            evidence_dir / "l3-real-fdb-kv-set-translator-input.json",
            evidence_dir / "l3-real-fdb-kv-set-clang-lowering-report.json",
            evidence_dir / "l3-real-fdb-kv-set-route-decision.json",
            evidence_dir / "l3-real-fdb-kv-set-validation-profile.json",
            evidence_dir / "l3-real-fdb-kv-set-capability-delta.json",
        ]
        for evidence_file in evidence_files:
            payload = load_json(evidence_file)
            with self.subTest(evidence_file=evidence_file.relative_to(REPO_ROOT).as_posix()):
                serialized = json.dumps(payload, sort_keys=True)
                self.assertIn(commit, serialized)
                self.assertNotIn(OLD_FLASHDB_SOURCE_COMMIT, serialized)

    def test_quickstart_runbook_documents_competition_commands_and_outputs(self) -> None:
        quickstarts = [
            REPO_ROOT / "docs" / "c2rust-migration-agent" / "quickstart.md",
            REPO_ROOT / "docs" / "c2rust-migration-agent" / "quickstart.en.md",
        ]
        required_terms = [
            "config/competition-env/environment.json",
            "config/competition-env/opencode-single-interaction.md",
            "source config/competition-env/env.sh",
            "bash config/competition-env/toolchain-check.sh",
            "validation/tools/run_competition.py",
            "python validation/tools/run_competition_smoke.py --proof-class ci-approximation",
            "python validation/tools/run_competition_smoke.py --proof-class wsl-local-simulation",
            "python validation/tools/run_competition_smoke.py --proof-class competition-exact --confirm-competition-exact",
            "competition-run-summary.json",
            "target/competition-smoke/summary/competition-smoke-summary.json",
            "target/competition-out/summary/competition-run-summary.json",
            "target/competition-out/slice-specs/flashdb-real-fdb-calc-crc32.json",
            "target/competition-out/evidence/flashdb/auto-translation/real-fdb-calc-crc32",
            "l3-real-fdb-calc-crc32-diff.json",
            "l3-real-fdb-calc-crc32-negative-diff.json",
            "l3-real-fdb-calc-crc32-final-verification.json",
            "target/competition-out/logs/commands.jsonl",
            "python -m validation.tools.opencode_agent_harness run-worker",
            "--mode opencode",
            "--opencode-variant max",
            '"run_id"',
            '"schema_version"',
            '"proof_class"',
            '"profile_id"',
            '"profile_sha256"',
            '"clang_source"',
            '"cargo_mirror_activation"',
            '"config_file"',
            '"elapsed_seconds"',
            '"translator_version"',
            '"slices"',
            '"unsafe_budget"',
            '"artifact_roots"',
            '"final_gate"',
            '"validator"',
            "--source-repo-root sources/FlashDB",
            "--source-repository https://gitcode.com/xwxf/FlashDB.git",
            "--source-branch competition",
            "--source-file src/fdb_utils.c",
            "fdb_calc_crc32",
            "--target-id flashdb",
            "--slice-id real-fdb-calc-crc32",
            "validate_auto_translation_evidence.py",
            "--evidence-root target/competition-out/evidence",
            "--require-semantic-pass",
            "workers/<worker-id>",
            "target/competition-out/workers/worker-a",
            "ci-approximation",
            "wsl-local-simulation",
            "local-simulation",
            "competition-exact",
        ]
        forbidden_terms = [
            "--reuse-accepted-evidence",
            "--accepted-evidence-root validation/evidence",
        ]
        for quickstart in quickstarts:
            text = quickstart.read_text(encoding="utf-8")
            with self.subTest(quickstart=quickstart.relative_to(REPO_ROOT).as_posix()):
                self.assertNotIn("CONTEXT.md", text)
                for term in forbidden_terms:
                    self.assertNotIn(term, text)
                for term in required_terms:
                    self.assertIn(term, text)

    def test_competition_shell_entrypoints_use_repo_root_and_activate_cargo_mirror(self) -> None:
        profile = load_json(PROFILE_DIR / "environment.json")
        activation = profile["cargo_mirror_activation"]
        self.assertEqual(activation["method"], "CARGO_HOME")
        self.assertEqual(activation["env_var"], "CARGO_HOME")
        self.assertEqual(activation["path"], "config/competition-env/cargo")
        self.assertEqual(activation["config_file"], "config/competition-env/cargo/config.toml")

        expected_clang_paths = [
            '"${repo_root}/tools/llvm/bin/clang-18"',
            '"${repo_root}/tools/llvm/bin/clang"',
            '"${repo_root}/tools/clang/bin/clang"',
        ]
        for script_path in [
            PROFILE_DIR / "env.sh",
            PROFILE_DIR / "toolchain-check.sh",
        ]:
            script = script_path.read_text(encoding="utf-8")
            with self.subTest(script=script_path.relative_to(REPO_ROOT).as_posix()):
                self.assertIn("find_repo_root()", script)
                self.assertIn('repo_root="$(find_repo_root)"', script)
                for expected_path in expected_clang_paths:
                    self.assertIn(expected_path, script)
                self.assertNotIn('"tools/llvm/bin/clang"', script)
                self.assertNotIn('"${script_dir}/../tools/llvm/bin/clang"', script)

        default_env = (PROFILE_DIR / "env.sh").read_text(encoding="utf-8")
        self.assertIn('export CARGO_HOME="${script_dir}/cargo"', default_env)

        toolchain_check = (PROFILE_DIR / "toolchain-check.sh").read_text(encoding="utf-8")
        self.assertIn("check_optional_clang_smoke()", toolchain_check)
        self.assertIn("-print-resource-dir", toolchain_check)
        self.assertIn("#include <stdint.h>", toolchain_check)
        self.assertIn("#include <stddef.h>", toolchain_check)

    def test_competition_smoke_shell_entrypoint_uses_profile_env_and_smoke_runner(self) -> None:
        smoke_script = (PROFILE_DIR / "smoke.sh").read_text(encoding="utf-8")

        self.assertIn("find_repo_root()", smoke_script)
        self.assertIn('repo_root="$(find_repo_root)"', smoke_script)
        self.assertIn('source "${script_dir}/env.sh"', smoke_script)
        self.assertIn("validation/tools/run_competition_smoke.py", smoke_script)
        self.assertIn("--proof-class", smoke_script)
        self.assertIn("--out-root", smoke_script)

    def test_dependency_admission_policy_governs_current_direct_dependencies(self) -> None:
        profile = load_json(PROFILE_DIR / "environment.json")
        policy = profile["dependency_admission_policy"]

        self.assertEqual(policy["schema_version"], 1)
        self.assertEqual(policy["status"], "enforced")
        self.assertEqual(policy["source_of_truth"], "config/competition-env/environment.json")
        self.assertEqual(
            policy["applies_to"]["manifest_paths"],
            [
                "crates/c2r-translator/Cargo.toml",
                "validation/l2_slices/Cargo.toml",
                "flashDB_rust/Cargo.toml",
            ],
        )
        self.assertEqual(
            policy["applies_to"]["default_paths_must_not_require"],
            ["go", "cmake", "clang"],
        )
        self.assertIn("semantic_risk", policy["admission_rule"]["required_risk_basis"])
        self.assertIn("generation_quality_risk", policy["admission_rule"]["required_risk_basis"])
        self.assertIn("maintainability_risk", policy["admission_rule"]["required_risk_basis"])
        self.assertIn("compatible_with_rust_1_96", policy["admission_rule"]["required_environment_fit"])
        self.assertIn("does_not_require_unavailable_tool", policy["admission_rule"]["required_environment_fit"])

        approved_rust = policy["approved_direct_dependencies"]["rust"]
        self.assertEqual(sorted(approved_rust), ["serde", "serde_json", "sha2"])
        for dependency_name, admission in approved_rust.items():
            with self.subTest(dependency_name=dependency_name):
                self.assertEqual(admission["admission"], "approved")
                self.assertTrue(admission["risk_basis"])
                self.assertTrue(admission["environment_fit"])
                self.assertIn("rust_1_96_compatible", admission["environment_fit"])

        for manifest in RUST_MANIFESTS:
            with self.subTest(manifest=manifest.relative_to(REPO_ROOT).as_posix()):
                self.assertLessEqual(direct_rust_dependencies(manifest), set(approved_rust))

        candidates = policy["candidate_dependencies"]
        for dependency_name in ["libclang", "bindgen", "syn", "quote", "tracing", "anyhow"]:
            with self.subTest(dependency_name=dependency_name):
                self.assertEqual(candidates[dependency_name]["admission"], "not_approved")
                self.assertTrue(candidates[dependency_name]["required_before_use"])

    def test_core_validation_ci_runs_competition_environment_profile_tests(self) -> None:
        workflow = (REPO_ROOT / ".github" / "workflows" / "core-translator-validation-ci.yml").read_text(
            encoding="utf-8"
        )

        self.assertIn("validation.tools.test_competition_environment_profile", workflow)
        self.assertIn("config/competition-env/**", workflow)
        self.assertNotIn("validation/environment-profiles/**", workflow)

    def test_legacy_validation_profile_is_readme_only_redirect(self) -> None:
        self.assertTrue(COMPAT_PROFILE_DIR.exists())
        files = sorted(
            path.relative_to(COMPAT_PROFILE_DIR).as_posix()
            for path in COMPAT_PROFILE_DIR.rglob("*")
            if path.is_file()
        )
        self.assertEqual(files, ["README.en.md", "README.md"])

        forbidden_runtime_files = [
            "environment.json",
            "env.sh",
            "smoke.sh",
            "toolchain-check.sh",
            "apt/sources.list",
            "pip/pip.conf",
            "npm/.npmrc",
            "cargo/config.toml",
            "rust/rust-toolchain.toml",
        ]
        for relative_path in forbidden_runtime_files:
            with self.subTest(relative_path=relative_path):
                self.assertFalse((COMPAT_PROFILE_DIR / relative_path).exists())

        for readme_name in ["README.md", "README.en.md"]:
            readme = (COMPAT_PROFILE_DIR / readme_name).read_text(encoding="utf-8")
            with self.subTest(readme=readme_name):
                self.assertIn("config/competition-env/", readme)
                self.assertIn("README-only", readme)


if __name__ == "__main__":
    unittest.main()

import hashlib
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
RUST_MANIFESTS = [
    REPO_ROOT / "crates" / "c2r-translator" / "Cargo.toml",
    REPO_ROOT / "validation" / "l2_slices" / "Cargo.toml",
    REPO_ROOT / "flashDB_rust" / "Cargo.toml",
]


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def direct_rust_dependencies(manifest: Path) -> set[str]:
    cargo_toml = tomllib.loads(manifest.read_text(encoding="utf-8"))
    return set(cargo_toml.get("dependencies", {}))


class CompetitionEnvironmentProfileTests(unittest.TestCase):
    def test_default_profile_matches_competition_baseline(self) -> None:
        profile = load_json(PROFILE_DIR / "environment.json")

        self.assertEqual(profile["profile_id"], "huawei-competition-ubuntu-24.04")
        self.assertEqual(profile["canonical_path"], "config/competition-env/environment.json")
        self.assertEqual(
            profile["compatibility_paths"],
            ["validation/environment-profiles/huawei-competition-ubuntu-24.04/environment.json"],
        )
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
            COMPAT_PROFILE_DIR / "env.sh",
            COMPAT_PROFILE_DIR / "toolchain-check.sh",
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
        self.assertEqual(sorted(approved_rust), ["serde", "serde_json"])
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

    def test_compatibility_profile_stays_synchronized_with_default_profile(self) -> None:
        synchronized_files = [
            "environment.json",
            "toolchain-check.sh",
            "apt/sources.list",
            "pip/pip.conf",
            "npm/.npmrc",
            "cargo/config.toml",
            "rust/rust-toolchain.toml",
        ]
        for relative_path in synchronized_files:
            with self.subTest(relative_path=relative_path):
                self.assertEqual(
                    sha256(PROFILE_DIR / relative_path),
                    sha256(COMPAT_PROFILE_DIR / relative_path),
                )


if __name__ == "__main__":
    unittest.main()

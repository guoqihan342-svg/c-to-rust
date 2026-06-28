import hashlib
import json
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


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        self.assertEqual(lane["ignored_env_for_ast_dump"], ["LIBCLANG_PATH"])
        self.assertEqual(lane["missing_status"], "missing_clang_path")

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

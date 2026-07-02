import hashlib
import json
import re
import tempfile
import tomllib
import unittest
from pathlib import Path, PurePosixPath

from validation.tools import validate_judge_entrypoints as judge_validator


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


def sha256_file(path: Path) -> str:
    return judge_validator.sha256_file(path)


def assert_repo_relative_posix(testcase: unittest.TestCase, path_text: str) -> None:
    testcase.assertIsInstance(path_text, str)
    testcase.assertTrue(path_text)
    testcase.assertNotIn("\\", path_text)
    testcase.assertFalse(path_text.startswith("/"))
    testcase.assertFalse(path_text.startswith("~"))
    testcase.assertFalse(len(path_text) >= 2 and path_text[1] == ":")
    testcase.assertNotIn("..", PurePosixPath(path_text).parts)


def assert_no_local_absolute_path(testcase: unittest.TestCase, text: str) -> None:
    testcase.assertIsInstance(text, str)
    testcase.assertNotRegex(text, re.compile(r"(?:^|[^A-Za-z0-9_])(?:[A-Za-z]:[\\/]|/mnt/[A-Za-z]/)"))


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

    def test_judge_artifact_hash_is_lf_stable_for_text_files_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            json_artifact = tmp_path / "artifact.json"
            json_artifact.write_bytes(b'{"status":"passed"}\r\n')
            expected_text_sha = hashlib.sha256(b'{"status":"passed"}\n').hexdigest()

            self.assertEqual(judge_validator.sha256_file(json_artifact), expected_text_sha)

            rust_artifact = tmp_path / "candidate.rs"
            rust_artifact.write_bytes(b"fn main() {}\r\n")
            expected_rust_sha = hashlib.sha256(b"fn main() {}\n").hexdigest()

            self.assertEqual(judge_validator.sha256_file(rust_artifact), expected_rust_sha)

            c_artifact = tmp_path / "source.c"
            c_artifact.write_bytes(b"int main(void) { return 0; }\r\n")
            expected_c_sha = hashlib.sha256(b"int main(void) { return 0; }\n").hexdigest()

            self.assertEqual(judge_validator.sha256_file(c_artifact), expected_c_sha)

            binary_artifact = tmp_path / "artifact.rlib"
            binary_artifact.write_bytes(b"\x00\r\n\xff")
            expected_binary_sha = hashlib.sha256(b"\x00\r\n\xff").hexdigest()

            self.assertEqual(judge_validator.sha256_file(binary_artifact), expected_binary_sha)

    def test_competition_config_hash_is_lf_stable_for_extensionless_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            for relative in [
                "config/competition-env/apt/sources.list",
                "config/competition-env/npm/.npmrc",
                "config/competition-env/pip/pip.conf",
            ]:
                config_path = tmp_path / relative
                config_path.parent.mkdir(parents=True, exist_ok=True)
                config_path.write_bytes(b"line1\r\nline2\r\n")
                self.assertEqual(
                    judge_validator.sha256_file(config_path),
                    hashlib.sha256(b"line1\nline2\n").hexdigest(),
                    relative,
                )

    def test_repo_attributes_keep_judge_text_paths_lf_stable(self) -> None:
        attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")

        for required in [
            "*.json text eol=lf",
            "*.jsonl text eol=lf",
            "*.md text eol=lf",
            "*.py text eol=lf",
            "*.rs text eol=lf",
            "*.c text eol=lf",
            "*.h text eol=lf",
            "*.toml text eol=lf",
            "*.conf text eol=lf",
            "*.yml text eol=lf",
            "*.yaml text eol=lf",
            "*.sh text eol=lf",
            "config/competition-env/apt/sources.list text eol=lf",
            "config/competition-env/npm/.npmrc text eol=lf",
            "validation/evidence/**/*.rlib binary -eol",
        ]:
            with self.subTest(required=required):
                self.assertIn(required, attributes)

    def test_competition_bootstrap_files_are_judge_replayable(self) -> None:
        requirements = REPO_ROOT / "requirements.txt"
        bootstrap = REPO_ROOT / "scripts" / "bootstrap_flashdb_sources.sh"
        smoke = PROFILE_DIR / "smoke.sh"

        self.assertTrue(requirements.exists())
        self.assertIn("jsonschema", requirements.read_text(encoding="utf-8"))
        self.assertTrue(bootstrap.exists())
        bootstrap_text = bootstrap.read_text(encoding="utf-8")
        self.assertIn("https://gitcode.com/xwxf/FlashDB.git", bootstrap_text)
        self.assertIn("f9d0421315c564fb890a1b14eee77b290e0d7bbe", bootstrap_text)

        smoke_text = smoke.read_text(encoding="utf-8")
        self.assertIn("python3 -B validation/tools/run_competition_smoke.py", smoke_text)
        self.assertNotIn("\npython validation/tools/run_competition_smoke.py", smoke_text)

        opencode_config = load_json(REPO_ROOT / "opencode.json")
        self.assertEqual(opencode_config.get("plugin"), [])

    def test_flashdb_bootstrap_avoids_noisy_missing_branch_fetch_fallback(self) -> None:
        bootstrap = (REPO_ROOT / "scripts" / "bootstrap_flashdb_sources.sh").read_text(encoding="utf-8")

        self.assertIn('git ls-remote --exit-code --heads origin "${FLASHDB_BRANCH}"', bootstrap)
        self.assertNotIn('git fetch --tags origin "${FLASHDB_BRANCH}" || git fetch --tags origin', bootstrap)

    def test_competition_opencode_docs_pin_glm_model(self) -> None:
        docs = [
            REPO_ROOT / "docs" / "c2rust-migration-agent" / "quickstart.md",
            REPO_ROOT / "docs" / "c2rust-migration-agent" / "quickstart.en.md",
            REPO_ROOT / "config" / "competition-env" / "opencode-single-interaction.md",
            REPO_ROOT / "config" / "competition-env" / "opencode-single-interaction.en.md",
            REPO_ROOT / "docs" / "c2rust-migration-agent" / "opencode-agent-harness-design.md",
            REPO_ROOT / "docs" / "c2rust-migration-agent" / "opencode-agent-harness-design.en.md",
        ]

        for doc in docs:
            with self.subTest(doc=doc.relative_to(REPO_ROOT).as_posix()):
                text = doc.read_text(encoding="utf-8")
                self.assertNotIn("DeepSeek", text)
                for block in re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL):
                    if "opencode-preflight" in block or "--mode opencode" in block:
                        self.assertIn("--opencode-model GLM-5.1", block)

    def test_competition_readme_records_glm_preflight_availability_boundary(self) -> None:
        stale_status_phrases = [
            "now passes the runner and `--require-local-artifacts` deep validation under local `local-simulation`",
            "\u5df2\u5728\u672c\u673a `local-simulation` \u4e0b\u901a\u8fc7 runner \u4e0e `--require-local-artifacts` \u6df1\u6821\u9a8c",
        ]
        for readme_path in [PROFILE_DIR / "README.md", PROFILE_DIR / "README.en.md"]:
            text = readme_path.read_text(encoding="utf-8")
            with self.subTest(readme=readme_path.relative_to(REPO_ROOT).as_posix()):
                self.assertIn("GLM-5.1", text)
                self.assertIn("opencode_model_unavailable", text)
                self.assertIn("required_model_not_listed", text)
                self.assertIn("local-simulation OpenCode pass does not close P0-H9", text)
                for stale_phrase in stale_status_phrases:
                    self.assertNotIn(stale_phrase, text)

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
        self.assertTrue(batch["auto_retry"])
        self.assertEqual(batch["max_workers"], 4)
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

    def test_demo_before_after_public_judge_profile_contract(self) -> None:
        batch = load_json(PROFILE_DIR / "planned-batches" / "demo-store-add-one-before-after.json")

        self.assertEqual(batch["schema_version"], 1)
        self.assertEqual(batch["profile_id"], "demo-store-add-one-before-after")
        self.assertEqual(batch["proof_class"], "local-simulation")
        self.assertEqual(batch["mode"], "deterministic")
        self.assertTrue(batch["execute_merge"])
        self.assertTrue(batch["auto_retry"])
        self.assertEqual(batch["max_workers"], 4)
        self.assertTrue(batch["emit_before_after_exhibit_report"])
        self.assertTrue(batch["emit_route_governance_metrics_report"])
        self.assertEqual(batch["acceptance_boundary"]["semantic_claim_source"], "accepted_evidence_binding")
        self.assertIs(batch["acceptance_boundary"]["generated_draft_semantic_pass"], False)
        self.assertEqual(
            batch["acceptance_boundary"]["translation_before_after"],
            "validation/evidence/demo/auto-translation/store-add-one/l3-store-add-one-translation-before-after.json",
        )

        for readme_path in [PROFILE_DIR / "README.md", PROFILE_DIR / "README.en.md"]:
            text = readme_path.read_text(encoding="utf-8")
            with self.subTest(readme=readme_path.relative_to(REPO_ROOT).as_posix()):
                self.assertIn("demo-store-add-one-before-after.json", text)
                self.assertIn("python3 -B -m validation.tools.opencode_agent_harness run-batch-profile", text)
                self.assertIn("python3 -B validation/tools/validate_competition_run_summary.py", text)
                self.assertIn("target/competition-out-demo-before-after-exhibit/summary/before-after-exhibit.json", text)
                self.assertIn("generated_draft_semantic_pass=false", text)
                self.assertIn("auto_retry=true", text)
                self.assertIn("translation_coverage_numerator", text)

        before_after = load_json(REPO_ROOT / batch["acceptance_boundary"]["translation_before_after"])
        self.assertEqual(before_after["status"], "bound")
        self.assertEqual(before_after["unsafe_reduction"]["status"], "measured")
        self.assertEqual(before_after["unsafe_reduction"]["baseline_total_unsafe"], 3)
        self.assertEqual(before_after["unsafe_reduction"]["current_total_unsafe"], 0)
        self.assertEqual(before_after["unsafe_reduction"]["reduced_by"], 3)
        for key in [
            "baseline",
            "final",
            "oracle_evidence",
            "accepted_patch",
            "patch_log",
            "unsafe_scan_evidence",
        ]:
            artifact = before_after[key]
            artifact_path = REPO_ROOT / artifact["path"]
            with self.subTest(artifact=key):
                self.assertTrue(artifact_path.exists())
                self.assertEqual(artifact["sha256"], sha256_file(artifact_path))

    def test_opencode_single_interaction_documents_auto_retry_contract(self) -> None:
        for runbook_path in [
            PROFILE_DIR / "opencode-single-interaction.md",
            PROFILE_DIR / "opencode-single-interaction.en.md",
        ]:
            text = runbook_path.read_text(encoding="utf-8")
            with self.subTest(runbook=runbook_path.relative_to(REPO_ROOT).as_posix()):
                self.assertIn("--auto-retry", text)
                self.assertIn("--max-workers", text)
                self.assertIn("repair", text)
                self.assertIn("5", text)
                self.assertIn("validator", text)
                self.assertIn("opencode_runtime_env", text)
                self.assertIn("opencode-runtime", text)

    def test_flashdb_real_before_after_profile_contract(self) -> None:
        profile = load_json(PROFILE_DIR / "environment.json")
        flashdb = profile["source_pins"]["flashdb"]
        commit = flashdb["commit"]
        batch = load_json(PROFILE_DIR / "planned-batches" / "flashdb-fdb-utils-before-after.json")

        self.assertEqual(batch["schema_version"], 1)
        self.assertEqual(batch["profile_id"], "flashdb-fdb-utils-before-after")
        self.assertEqual(batch["proof_class"], "local-simulation")
        self.assertEqual(batch["target_id"], "flashdb")
        self.assertEqual(batch["source_repo_root"], "sources/FlashDB")
        self.assertEqual(batch["source_file"], "src/fdb_utils.c")
        self.assertEqual(batch["source_commit"], commit)
        self.assertEqual(batch["require_source_commit"], commit)
        self.assertEqual(batch["functions"], ["fdb_calc_crc32"])
        self.assertEqual(batch["slice_specs"], ["validation/slice-specs/flashdb-real-fdb-calc-crc32.json"])
        self.assertTrue(batch["reuse_accepted_evidence"])
        self.assertTrue(batch["execute_merge"])
        self.assertTrue(batch["auto_retry"])
        self.assertEqual(batch["max_workers"], 4)
        self.assertTrue(batch["emit_route_governance_metrics_report"])
        self.assertTrue(batch["emit_before_after_exhibit_report"])
        self.assertEqual(batch["acceptance_boundary"]["semantic_claim_source"], "accepted_evidence_binding")
        self.assertIs(batch["acceptance_boundary"]["generated_draft_semantic_pass"], False)
        self.assertEqual(
            batch["acceptance_boundary"]["translation_before_after"],
            "validation/evidence/flashdb/auto-translation/real-fdb-calc-crc32/"
            "l3-real-fdb-calc-crc32-translation-before-after.json",
        )
        self.assertIn("real FlashDB", batch["acceptance_boundary"]["claim"])

        before_after = load_json(REPO_ROOT / batch["acceptance_boundary"]["translation_before_after"])
        self.assertEqual(before_after["status"], "bound")
        self.assertEqual(before_after["target_id"], "flashdb")
        self.assertEqual(before_after["slice_id"], "real-fdb-calc-crc32")
        self.assertEqual(before_after["claim_boundary"]["source_commit"], commit)
        self.assertIn("baseline_verification", before_after["claim_boundary"]["boundary"])
        verified_ref = batch["attempt_evidence_policy"]["baseline_attempt"]["verified_unsafe_baseline"]
        self.assertEqual(verified_ref, before_after["baseline_verification"])
        verified_payload = load_json(REPO_ROOT / verified_ref["path"])
        self.assertEqual(verified_payload["status"], "passed")
        self.assertIs(verified_payload["semantic_pass"], True)
        self.assertEqual(verified_payload["semantic_claim_source"], "verified_unsafe_baseline_gates")
        self.assertEqual(before_after["unsafe_reduction"]["status"], "measured")
        self.assertGreater(before_after["unsafe_reduction"]["baseline_total_unsafe"], 0)
        self.assertEqual(before_after["unsafe_reduction"]["current_total_unsafe"], 0)
        self.assertEqual(
            before_after["unsafe_reduction"]["reduced_by"],
            before_after["unsafe_reduction"]["baseline_total_unsafe"],
        )
        for key in [
            "baseline",
            "final",
            "oracle_evidence",
            "accepted_patch",
            "patch_log",
            "baseline_verification",
            "unsafe_scan_evidence",
        ]:
            artifact = before_after[key]
            artifact_path = REPO_ROOT / artifact["path"]
            with self.subTest(artifact=key):
                self.assertTrue(artifact_path.exists())
                self.assertEqual(artifact["sha256"], sha256_file(artifact_path))

    def test_flashdb_judge_entrypoints_contract(self) -> None:
        profile = load_json(PROFILE_DIR / "environment.json")
        flashdb = profile["source_pins"]["flashdb"]
        config_path = PROFILE_DIR / "judge-entrypoints" / "flashdb-harness.json"
        config = load_json(config_path)

        self.assertEqual(config["schema_version"], 1)
        self.assertEqual(config["manifest_kind"], "judge-entrypoints")
        self.assertEqual(config["profile_id"], "flashdb-harness-judge-entrypoint")
        self.assertEqual(config["entrypoint_id"], "flashdb-harness")
        self.assertEqual(config["entrypoint_type"], "judge_one_click")
        self.assertEqual(config["target_id"], "flashdb")
        self.assertEqual(config["status"], "active")
        self.assertEqual(config["proof_class_default"], "local-simulation")
        self.assertIn("competition-exact", config["allowed_proof_classes"])

        environment_ref = config["environment_profile"]
        assert_repo_relative_posix(self, environment_ref["path"])
        self.assertEqual(environment_ref["path"], "config/competition-env/environment.json")
        self.assertEqual(environment_ref["profile_id"], "huawei-competition-ubuntu-24.04")
        self.assertEqual(environment_ref["sha256"], sha256_file(REPO_ROOT / environment_ref["path"]))
        self.assertEqual(config["source_pin"]["repository"], flashdb["repository"])
        self.assertEqual(config["source_pin"]["branch"], flashdb["branch"])
        self.assertEqual(config["source_pin"]["commit"], flashdb["commit"])
        self.assertEqual(config["source_pin"]["checkout_command"], flashdb["checkout_command"])
        assert_no_local_absolute_path(self, config["source_pin"]["checkout_command"])
        source_pin_policy = config["source_pin_policy"]
        self.assertEqual(source_pin_policy["canonical_commit"], flashdb["commit"])
        self.assertTrue(source_pin_policy["new_extraction_requires_canonical_commit"])
        historical_commits = {
            item["commit"]
            for item in source_pin_policy["allowed_historical_evidence_commits"]
        }
        self.assertEqual(historical_commits, {"93d175549da579b8abac07bd175ce4c3f9dde829"})

        claim_boundary = config["claim_boundary"]
        self.assertEqual(claim_boundary["semantic_claim_source"], "accepted_evidence_binding")
        self.assertFalse(claim_boundary["generated_draft_semantic_pass"])
        self.assertEqual(claim_boundary["translation_coverage_numerator"], 0)
        self.assertIn("not a semantic gate", claim_boundary["boundary"])
        self.assertIn("translator-generated semantic pass", claim_boundary["non_goals"])
        self.assertIn("whole-project FlashDB migration", claim_boundary["non_goals"])
        self.assertIn("translator-generated semantic pass", claim_boundary["forbidden_claims"])
        self.assertIn("whole-project FlashDB automatic C-to-Rust translation", claim_boundary["forbidden_claims"])
        self.assertIn("unsafe 2 -> 0", " ".join(claim_boundary["allowed_claims"]))
        self.assertEqual(
            set(config["harness_features_demonstrated"]),
            {
                "h1_evaluate_one_click",
                "h2_multi_worker_fanout",
                "h3_precise_repair_self_heal",
                "h4_before_after_exhibit",
                "h5_context_management",
                "h6_judge_reports",
            },
        )
        self.assertTrue(all(config["harness_features_demonstrated"].values()))

        entrypoints = {entry["id"]: entry for entry in config["entrypoints"]}
        self.assertEqual(
            set(entrypoints),
            {
                "competition_environment_smoke",
                "before_after_judge_demo",
                "multi_worker_evaluate_profile",
                "opencode_multi_worker_evaluate_profile",
            },
        )
        contract = config["test_contract"]
        self.assertEqual(set(contract["required_entrypoint_ids"]), set(entrypoints))
        self.assertTrue(contract["paths_must_be_repo_relative_posix"])
        self.assertTrue(contract["commands_must_use_portable_python3_b"])
        self.assertEqual(
            set(contract["required_harness_features"]),
            {
                "h1_evaluate_one_click",
                "h2_multi_worker_fanout",
                "h3_precise_repair_self_heal",
                "h4_before_after_exhibit",
                "h5_context_management",
                "h6_judge_reports",
            },
        )
        self.assertEqual(
            contract["required_context_pipeline_stages"],
            ["plan", "translate", "verify", "repair"],
        )
        self.assertEqual(
            set(contract["required_agent_roles"]),
            {"planner", "worker", "repairer", "verifier", "reporter"},
        )
        self.assertEqual(contract["repair_round_cap"], 5)
        self.assertFalse(contract["context_pack_contract"]["chat_output_is_evidence"])
        self.assertFalse(contract["context_pack_contract"]["semantic_gate"])
        self.assertEqual(contract["context_pack_contract"]["checkpoint_backend"], "sqlite")
        self.assertFalse(contract["agent_index_contract"]["chat_output_is_evidence"])
        self.assertFalse(contract["agent_index_contract"]["semantic_gate"])
        self.assertEqual(contract["agent_index_contract"]["worker_isolation"], "per-worker out_root")
        self.assertEqual(contract["semantic_claim_source"], "accepted_evidence_binding")
        self.assertFalse(contract["generated_draft_semantic_pass"])
        self.assertEqual(contract["translation_coverage_numerator"], 0)

        smoke = entrypoints["competition_environment_smoke"]
        self.assertEqual(smoke["priority"], 0)
        self.assertEqual(smoke["entrypoint_type"], "competition_environment_smoke")
        self.assertEqual(smoke["purpose"], "competition-environment-smoke")
        self.assertIn("validation/tools/run_competition_smoke.py", smoke["command"])
        self.assertIn("--proof-class local-simulation", smoke["command"])
        self.assertIn("--run-id competition-flashdb-environment-smoke-20260701", smoke["command"])
        self.assertIn("--out-root target/competition-smoke-flashdb-judge-entrypoint", smoke["command"])
        self.assertFalse(smoke["smoke_contract"]["semantic_gate"])
        self.assertFalse(smoke["smoke_contract"]["generated_draft_semantic_pass"])
        self.assertEqual(smoke["smoke_contract"]["translation_coverage_numerator"], 0)
        for artifact in [
            "competition_smoke_summary",
            "vendored_clang_verification",
            "evidence_governance_report",
            "translator_coverage_matrix",
            "milestone_release_report",
            "command_log",
        ]:
            self.assertIn(artifact, smoke["expected_artifacts"])

        before_after = entrypoints["before_after_judge_demo"]
        self.assertEqual(before_after["priority"], 1)
        self.assertEqual(before_after["purpose"], "core-translation-before-after-exhibit")
        self.assertIn("validation.tools.judge_demo", before_after["command"])
        self.assertIn("--profile config/competition-env/planned-batches/flashdb-fdb-utils-before-after.json", before_after["command"])
        self.assertIn("--run-id competition-flashdb-before-after-exhibit", before_after["command"])
        self.assertIn("--out-root target/competition-out-flashdb-before-after-exhibit", before_after["command"])
        self.assertIn(
            "--review-checklist config/competition-env/review-checklists/flashdb-harness-internal-review.json",
            before_after["command"],
        )
        review_checklist = before_after["review_checklist"]
        self.assertEqual(
            review_checklist["path"],
            "config/competition-env/review-checklists/flashdb-harness-internal-review.json",
        )
        self.assertEqual(review_checklist["report_kind"], "milestone-review-checklist")
        review_checklist_path = REPO_ROOT / review_checklist["path"]
        self.assertTrue(review_checklist_path.exists(), review_checklist["path"])
        self.assertEqual(review_checklist["sha256"], sha256_file(review_checklist_path))
        self.assertIn("validate_competition_run_summary.py", " ".join(before_after["verification_commands"]))
        for artifact in [
            "competition_summary",
            "workflow_metrics",
            "judge_demo_report",
            "before_after_exhibit",
            "milestone_release_report",
            "context_pack",
            "agent_index",
        ]:
            self.assertIn(artifact, before_after["expected_artifacts"])

        multi_worker = entrypoints["multi_worker_evaluate_profile"]
        self.assertEqual(multi_worker["priority"], 2)
        self.assertEqual(multi_worker["purpose"], "harness-architecture-multi-worker-evaluate")
        self.assertIn("validation.tools.opencode_agent_harness evaluate", multi_worker["command"])
        self.assertIn("--profile config/competition-env/planned-batches/flashdb-fdb-utils-explicit-workers.json", multi_worker["command"])
        self.assertIn("--run-id harness-flashdb-explicit-workers-evaluate-profile-20260701", multi_worker["command"])
        self.assertIn(
            "--out-root target/competition-out-flashdb-explicit-workers-evaluate-profile-20260701",
            multi_worker["command"],
        )
        for artifact in [
            "competition_summary",
            "workflow_metrics",
            "route_governance_metrics_report",
            "evaluate_report",
            "judge_evidence_index",
            "batch_profile_report",
            "context_pack",
            "agent_index",
            "run_plan_report",
            "merge_plan",
            "worker_plan",
        ]:
            self.assertIn(artifact, multi_worker["expected_artifacts"])

        opencode_multi_worker = entrypoints["opencode_multi_worker_evaluate_profile"]
        self.assertEqual(opencode_multi_worker["priority"], 3)
        self.assertEqual(opencode_multi_worker["purpose"], "harness-architecture-opencode-multi-worker-evaluate")
        self.assertIn("validation.tools.opencode_agent_harness evaluate", opencode_multi_worker["command"])
        self.assertIn(
            "--profile config/competition-env/planned-batches/flashdb-fdb-utils-opencode-explicit-workers.json",
            opencode_multi_worker["command"],
        )
        self.assertIn("--run-id harness-flashdb-opencode-explicit-workers-evaluate-profile-20260701", opencode_multi_worker["command"])
        self.assertIn(
            "--out-root target/competition-out-flashdb-opencode-explicit-workers-evaluate-profile-20260701",
            opencode_multi_worker["command"],
        )
        for artifact in [
            "competition_summary",
            "workflow_metrics",
            "route_governance_metrics_report",
            "evaluate_report",
            "judge_evidence_index",
            "batch_profile_report",
            "context_pack",
            "agent_index",
            "run_plan_report",
            "merge_plan",
            "worker_plan",
            "opencode_safety_transform_attempt",
        ]:
            self.assertIn(artifact, opencode_multi_worker["expected_artifacts"])
        self.assertEqual(
            opencode_multi_worker["expected_artifacts"]["opencode_safety_transform_attempt"],
            "target/competition-out-flashdb-opencode-explicit-workers-evaluate-profile-20260701/"
            "workers/flashdb-opencode-worker-001-fdb-calc-crc32/harness/"
            "opencode-safety-transform-attempt-1.json",
        )
        self.assertIn("opencode preflight", " ".join(opencode_multi_worker["judge_focus"]))
        self.assertIn("runtime contract", " ".join(opencode_multi_worker["judge_focus"]))
        opencode_profile = load_json(
            PROFILE_DIR / "planned-batches" / "flashdb-fdb-utils-opencode-explicit-workers.json"
        )
        self.assertEqual(opencode_profile["mode"], "opencode")
        self.assertEqual(opencode_profile["opencode_command"], "opencode")
        self.assertEqual(opencode_profile["opencode_model"], "GLM-5.1")
        self.assertEqual(opencode_profile["opencode_variant"], "max")
        self.assertTrue(opencode_profile["opencode_skip_permissions"])
        self.assertTrue(opencode_profile["auto_retry"])
        self.assertEqual(opencode_profile["max_workers"], 2)
        opencode_config = load_json(REPO_ROOT / "opencode.json")
        self.assertEqual(opencode_config.get("plugin"), [])

        for entry in config["entrypoints"]:
            self.assertEqual(entry["proof_class"], "local-simulation")
            self.assertTrue(entry["command"].startswith("python3 -B "), entry["id"])
            for ref_name in ["profile", "tracked_manifest"]:
                if ref_name not in entry:
                    continue
                ref = entry[ref_name]
                assert_repo_relative_posix(self, ref["path"])
                path = REPO_ROOT / ref["path"]
                self.assertTrue(path.exists(), ref["path"])
                self.assertEqual(ref["sha256"], sha256_file(path), ref["path"])
            for artifact_path in entry["expected_artifacts"].values():
                assert_repo_relative_posix(self, artifact_path)
            for command in [entry["command"], entry.get("audit_command", ""), *entry["verification_commands"]]:
                assert_no_local_absolute_path(self, command)

    def test_judge_validator_rejects_preflight_without_glm_model_availability_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo_root = Path(tmp)
            preflight_path = repo_root / "target" / "harness" / "opencode-preflight-report.json"
            preflight_path.parent.mkdir(parents=True)
            launch_policy = {
                "opencode_command": "opencode",
                "opencode_model": "GLM-5.1",
                "opencode_agent": None,
                "opencode_variant": "max",
                "opencode_skip_permissions": True,
            }
            launch_policy_sha = judge_validator.sha256_text(json.dumps(launch_policy, sort_keys=True))
            preflight_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "run_id": "preflight-run",
                        "status": "passed",
                        "marker_exists": True,
                        "launch_policy": launch_policy,
                        "launch_policy_sha256": launch_policy_sha,
                        "contract_verification": {
                            "status": "executed",
                            "first_shell_command_matches_worker_command": True,
                            "worker_command_seen": True,
                            "summary_exists": True,
                            "tools_before_first_shell": [],
                        },
                    },
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            binding = {
                "path": "target/harness/opencode-preflight-report.json",
                "sha256": sha256_file(preflight_path),
                "status": "passed",
                "contract_status": "executed",
                "run_id": "preflight-run",
                "launch_policy": launch_policy,
                "launch_policy_sha256": launch_policy_sha,
            }

            with self.assertRaisesRegex(ValueError, "opencode_model_availability is required"):
                judge_validator.validate_opencode_preflight_binding(
                    binding,
                    "opencode_agent_runtime.opencode_preflight_report",
                    repo_root=repo_root,
                )

    def test_judge_validator_rejects_resume_replay_with_non_glm_preflight_model(self) -> None:
        worker = {
            "worker_id": "worker-001",
            "opencode_preflight_report": {
                "path": "target/harness/opencode-preflight-report.json",
                "launch_policy": {
                    "opencode_command": "opencode",
                    "opencode_model": None,
                    "opencode_agent": None,
                    "opencode_variant": "max",
                    "opencode_skip_permissions": True,
                },
            },
        }
        argv = [
            "python3",
            "-B",
            "-m",
            "validation.tools.opencode_agent_harness",
            "run-worker",
            "--db",
            "target/state/opencode-agent-harness.sqlite3",
            "--run-id",
            "run-resume",
            "--worker-id",
            "worker-001",
            "--mode",
            "opencode",
            "--opencode-preflight-report",
            "target/harness/opencode-preflight-report.json",
        ]

        with self.assertRaisesRegex(ValueError, "--opencode-model must be GLM-5.1"):
            judge_validator.validate_resume_manifest_replay_command(
                {
                    "argv": argv,
                    "command": " ".join(argv),
                    "replay_safety": {"status": "ready"},
                },
                label="resume_manifest.workers[0].replay_commands.run_worker",
                expected_subcommand="run-worker",
                worker=worker,
                worker_id="worker-001",
                run_id="run-resume",
                ledger_path="target/state/opencode-agent-harness.sqlite3",
                require_hint=False,
            )

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
            "python3 -B validation/tools/run_competition_smoke.py --proof-class ci-approximation",
            "python3 -B validation/tools/run_competition_smoke.py --proof-class wsl-local-simulation",
            "python3 -B validation/tools/run_competition_smoke.py --proof-class competition-exact --confirm-competition-exact",
            "competition-run-summary.json",
            "target/competition-smoke/summary/competition-smoke-summary.json",
            "target/competition-out/summary/competition-run-summary.json",
            "target/competition-out/slice-specs/flashdb-real-fdb-calc-crc32.json",
            "target/competition-out/evidence/flashdb/auto-translation/real-fdb-calc-crc32",
            "l3-real-fdb-calc-crc32-diff.json",
            "l3-real-fdb-calc-crc32-negative-diff.json",
            "l3-real-fdb-calc-crc32-final-verification.json",
            "target/competition-out/logs/commands.jsonl",
            "python3 -B -m validation.tools.opencode_agent_harness run-worker",
            "--mode opencode",
            "--opencode-variant max",
            "opencode_runtime_env",
            "opencode-runtime",
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
        self.assertIn("validation.tools.test_resync_sha_bindings", workflow)
        self.assertIn("validation.tools.test_opencode_agent_harness", workflow)
        self.assertIn("bash scripts/bootstrap_flashdb_sources.sh", workflow)
        self.assertIn("git ls-files --eol", workflow)
        self.assertIn("[iw]/(crlf|mixed)", workflow)
        self.assertIn("validation.tools.resync_sha_bindings --scan-root config/competition-env --dry-run --check", workflow)
        self.assertIn("validation.tools.resync_sha_bindings --scope judge-chain --dry-run --check", workflow)
        self.assertIn("config/competition-env/**", workflow)
        self.assertIn("validation/evidence/**", workflow)
        self.assertIn("validation/slice-specs/**", workflow)
        self.assertIn("requirements.txt", workflow)
        self.assertIn(".gitattributes", workflow)
        self.assertIn("scripts/bootstrap_flashdb_sources.sh", workflow)
        self.assertIn("opencode.json", workflow)
        self.assertNotIn("validation/environment-profiles/**", workflow)

    def test_repo_owned_c2rust_skill_tracks_competition_harness_gates(self) -> None:
        skill_path = REPO_ROOT / ".codex" / "skills" / "c2rust-migration" / "SKILL.md"
        self.assertTrue(skill_path.is_file())
        skill = skill_path.read_text(encoding="utf-8")

        self.assertIn("python3 -B", skill)
        self.assertNotIn("python -B", skill)
        self.assertIn("git clone -c core.autocrlf=false --no-local", skill)
        self.assertIn("validation.tools.resync_sha_bindings --scan-root config/competition-env --dry-run --check", skill)
        self.assertIn("validation.tools.resync_sha_bindings --scope judge-chain --dry-run --check", skill)
        self.assertIn("validation.tools.validate_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json", skill)
        self.assertIn("validation.tools.run_judge_entrypoints --config config/competition-env/judge-entrypoints/flashdb-harness.json --dry-run", skill)
        self.assertIn("--require-local-artifacts", skill)
        self.assertIn("opencode-preflight", skill)
        self.assertIn("marker_exists=true", skill)
        self.assertIn("GLM-5.1", skill)
        self.assertIn("opencode_model_availability", skill)
        self.assertIn("opencode_model_unavailable", skill)
        self.assertIn("local-simulation OpenCode pass does not close P0-H9", skill)

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

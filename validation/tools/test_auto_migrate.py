import json
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"


def load_auto_migrate_module():
    spec = importlib.util.spec_from_file_location("auto_migrate_under_test", AUTO_MIGRATE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load auto_migrate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AutoMigrateTests(unittest.TestCase):
    def test_generates_candidate_without_claiming_semantic_pass(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            out_root = Path(tmp) / "evidence"
            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
            self.assertEqual(manifest["source_commit"], "d40f29fd42ed9158e3eb3e221dca50e4b627f7a8")
            self.assertEqual(manifest["fixture"]["hash"], "zlib-adler32-fixture")
            self.assertEqual(manifest["oracle"]["status"], "SKIPPED_LOCAL_NO_C_TOOLCHAIN")
            self.assertEqual(manifest["oracle"]["fixture"], "validation/l2_slices/fixtures/zlib-adler32-c-oracle.json")
            self.assertEqual(manifest["replay"]["fixture"], "validation/l2_slices/fixtures/zlib-adler32-c-oracle.json")
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertTrue(
                (out_root / "zlib-ng" / "auto-translation" / "adler32-step" / "l3-adler32-step-type-map.json").exists()
            )

    def test_compile_failure_records_blocked_patch_evidence(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "bad-syntax",
            "source_commit": "1234567",
            "function_name": "bad_syntax",
            "c_source": "int bad_syntax(int value) { return value + ; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "bad-syntax.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["rust_check"]["status"], "failed")
            self.assertEqual(manifest["patch"]["status"], "blocked")
            blocked_path = out_root / "demo" / "auto-translation" / "bad-syntax" / "l3-bad-syntax-self-healing-blocked-repairs.json"
            blocked = json.loads(blocked_path.read_text(encoding="utf-8"))
            self.assertEqual(blocked["status"], "recorded")
            self.assertEqual(blocked["blocked_repairs"][0]["candidate_patch_id"], "patch-blocked-1")
            self.assertTrue(blocked["blocked_repairs"][0]["human_action_required"])

    def test_keyword_identifier_compile_failure_is_self_healed(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "keyword-param",
            "source_commit": "1234567",
            "function_name": "keyword_param",
            "c_source": "int keyword_param(int match) { return match + 1; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "keyword-param.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertEqual(manifest["patch"]["status"], "recorded")
            patch_events = (
                out_root
                / "demo"
                / "auto-translation"
                / "keyword-param"
                / "l3-keyword-param-patch-events.jsonl"
            ).read_text(encoding="utf-8")
            self.assertIn('"status": "verified"', patch_events)
            draft = (
                out_root
                / "demo"
                / "auto-translation"
                / "keyword-param"
                / "l3-keyword-param-rust-draft.rs"
            ).read_text(encoding="utf-8")
            self.assertIn("r#match", draft)

    def test_cache_drift_invalidates_reusable_translation_artifacts(self) -> None:
        auto_migrate = load_auto_migrate_module()
        previous = {
            "source_commit": "source-a",
            "source_file_hashes": {"src/file.c": "hash-a"},
            "slice_spec_sha256": "slice-a",
            "fixture_hash": "fixture-a",
            "build_profile_hash": "profile-a",
            "cargo_lock_hash": "lock-a",
            "tool_versions": {"rustc": "rustc-a"},
            "schema_versions": {"cfg": 1},
            "translator_version": "0.1.0",
            "translator_manifest_sha256": "manifest-a",
            "command_arguments": ["auto_migrate.py", "--slice-spec", "slice.json"],
        }

        reusable = auto_migrate.cache_drift_report(previous, dict(previous))

        self.assertEqual(reusable["status"], "reusable")
        self.assertTrue(reusable["reuse_allowed"])
        self.assertEqual(reusable["invalidated_artifacts"], [])

        current = dict(previous)
        current["source_commit"] = "source-b"
        current["build_profile_hash"] = "profile-b"
        current["fixture_hash"] = "fixture-b"
        current["source_file_hashes"] = {"src/file.c": "hash-b"}

        drifted = auto_migrate.cache_drift_report(previous, current)

        self.assertEqual(drifted["status"], "drift_detected")
        self.assertFalse(drifted["reuse_allowed"])
        self.assertIn("source_commit", drifted["drifted_keys"])
        self.assertIn("source_file_hashes", drifted["drifted_keys"])
        self.assertIn("fixture_hash", drifted["drifted_keys"])
        self.assertIn("build_profile_hash", drifted["drifted_keys"])
        for artifact in [
            "context_pack",
            "type_map",
            "cfg",
            "pointer_graph",
            "rust_draft",
            "patch_plan",
            "c_oracle",
            "diff",
            "summary",
        ]:
            self.assertIn(artifact, drifted["invalidated_artifacts"])


if __name__ == "__main__":
    unittest.main()

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from validation.tools import validate_judge_entrypoints as judge_validator
from validation.tools import resync_sha_bindings


class ResyncShaBindingsTest(unittest.TestCase):
    def test_resync_updates_lf_stable_text_refs_and_cascading_parent_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaf = root / "leaf.json"
            child = root / "child.json"
            parent = root / "parent.json"
            binary = root / "artifact.rlib"

            leaf.write_bytes(b'{"status":"passed"}\r\n')
            binary.write_bytes(b"\x00\r\n\xff")
            write_json(
                child,
                {
                    "leaf": {
                        "path": "leaf.json",
                        "sha256": hashlib.sha256(leaf.read_bytes()).hexdigest(),
                    },
                    "binary": {
                        "path": "artifact.rlib",
                        "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                    },
                },
            )
            write_json(
                parent,
                {
                    "child": {
                        "path": "child.json",
                        "sha256": "0" * 64,
                    },
                },
            )

            result = resync_sha_bindings.resync_roots(repo_root=root, scan_roots=[root], max_passes=5)

            self.assertEqual(result["status"], "updated")
            self.assertGreaterEqual(result["updated_ref_count"], 2)

            child_payload = load_json(child)
            self.assertEqual(child_payload["leaf"]["sha256"], judge_validator.sha256_file(leaf))
            self.assertEqual(child_payload["binary"]["sha256"], hashlib.sha256(binary.read_bytes()).hexdigest())

            parent_payload = load_json(parent)
            self.assertEqual(parent_payload["child"]["sha256"], judge_validator.sha256_file(child))

    def test_dry_run_check_simulates_cascading_parent_hash_updates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaf = root / "leaf.json"
            child = root / "child.json"
            parent = root / "parent.json"

            leaf.write_bytes(b'{"status":"passed"}\r\n')
            write_json(
                child,
                {
                    "leaf": {
                        "path": "leaf.json",
                        "sha256": hashlib.sha256(leaf.read_bytes()).hexdigest(),
                    },
                },
            )
            write_json(
                parent,
                {
                    "child": {
                        "path": "child.json",
                        "sha256": judge_validator.sha256_file(child),
                    },
                },
            )
            before_parent = parent.read_text(encoding="utf-8")

            result = resync_sha_bindings.resync_roots(repo_root=root, scan_roots=[root], max_passes=5, dry_run=True)

            self.assertEqual(result["status"], "would_update")
            self.assertGreaterEqual(result["updated_ref_count"], 2)
            self.assertEqual(result["changed_files"], ["child.json", "parent.json"])
            self.assertEqual(resync_sha_bindings.exit_code_for_result(result, check=True), 1)
            self.assertEqual(parent.read_text(encoding="utf-8"), before_parent)

    def test_check_mode_exit_code_fails_on_drift_and_missing_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            leaf = root / "leaf.json"
            stale = root / "stale.json"
            missing = root / "missing.json"

            leaf.write_text('{"status":"passed"}\n', encoding="utf-8", newline="\n")
            write_json(stale, {"leaf": {"path": "leaf.json", "sha256": "0" * 64}})
            write_json(missing, {"artifact": {"path": "absent.json", "sha256": "0" * 64}})

            drift = resync_sha_bindings.resync_roots(repo_root=root, scan_roots=[stale], dry_run=True)
            self.assertEqual(drift["status"], "would_update")
            self.assertEqual(resync_sha_bindings.exit_code_for_result(drift, check=True), 1)
            self.assertEqual(resync_sha_bindings.exit_code_for_result(drift, check=False), 0)

            missing_ref = resync_sha_bindings.resync_roots(repo_root=root, scan_roots=[missing], dry_run=True)
            self.assertEqual(missing_ref["status"], "unchanged")
            self.assertEqual(missing_ref["missing_refs"], ["absent.json"])
            self.assertEqual(resync_sha_bindings.exit_code_for_result(missing_ref, check=True), 1)

            clean = resync_sha_bindings.resync_roots(repo_root=root, scan_roots=[leaf], dry_run=True)
            self.assertEqual(clean["status"], "unchanged")
            self.assertEqual(resync_sha_bindings.exit_code_for_result(clean, check=True), 0)

    def test_check_mode_fails_on_self_refs_and_json_cycles_without_rewriting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self_ref = root / "self.json"
            cycle_a = root / "cycle-a.json"
            cycle_b = root / "cycle-b.json"

            write_json(self_ref, {"self": {"path": "self.json", "sha256": "0" * 64}})
            write_json(cycle_a, {"b": {"path": "cycle-b.json", "sha256": "0" * 64}})
            write_json(cycle_b, {"a": {"path": "cycle-a.json", "sha256": "0" * 64}})
            before = {path: path.read_text(encoding="utf-8") for path in [self_ref, cycle_a, cycle_b]}

            result = resync_sha_bindings.resync_roots(repo_root=root, scan_roots=[root], dry_run=True)

            self.assertEqual(result["status"], "unchanged")
            self.assertEqual(result["self_refs"], ["self.json"])
            self.assertEqual(sorted(result["cycle_refs"]), ["cycle-a.json", "cycle-b.json"])
            self.assertEqual(resync_sha_bindings.exit_code_for_result(result, check=True), 1)
            self.assertEqual(before, {path: path.read_text(encoding="utf-8") for path in [self_ref, cycle_a, cycle_b]})

    def test_judge_chain_scope_follows_hash_bound_json_refs_and_skips_unrelated_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "config" / "competition-env" / "judge-entrypoints" / "flashdb-harness.json"
            profile = root / "config" / "competition-env" / "planned-batches" / "release-profile.json"
            artifact = root / "validation" / "evidence" / "flashdb" / "release-artifact.json"
            leaf = root / "validation" / "evidence" / "flashdb" / "release-leaf.json"
            unrelated = root / "validation" / "evidence" / "demo" / "historical.json"
            unrelated_leaf = root / "validation" / "evidence" / "demo" / "historical-leaf.json"

            leaf.parent.mkdir(parents=True)
            unrelated_leaf.parent.mkdir(parents=True)
            leaf.write_text('{"status":"passed"}\n', encoding="utf-8", newline="\n")
            unrelated_leaf.write_text('{"status":"stale"}\n', encoding="utf-8", newline="\n")
            write_json(artifact, {"leaf": {"path": rel(root, leaf), "sha256": "0" * 64}})
            write_json(profile, {"artifact": {"path": rel(root, artifact), "sha256": judge_validator.sha256_file(artifact)}})
            write_json(seed, {"profile": {"path": rel(root, profile), "sha256": judge_validator.sha256_file(profile)}})
            write_json(unrelated, {"leaf": {"path": rel(root, unrelated_leaf), "sha256": "0" * 64}})

            result = resync_sha_bindings.resync_judge_chain(
                repo_root=root,
                seeds=[seed],
                max_passes=6,
                dry_run=True,
            )

            self.assertEqual(result["status"], "would_update")
            self.assertEqual(result["scan_scope"], "judge-chain")
            self.assertEqual(
                result["scanned_json_files"],
                sorted([rel(root, seed), rel(root, profile), rel(root, artifact), rel(root, leaf)]),
            )
            self.assertEqual(result["changed_files"], sorted([rel(root, seed), rel(root, profile), rel(root, artifact)]))
            self.assertNotIn(rel(root, unrelated), result["changed_files"])
            self.assertEqual(resync_sha_bindings.exit_code_for_result(result, check=True), 1)

    def test_judge_chain_scope_can_pass_after_resync_without_touching_unrelated_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "config" / "competition-env" / "judge-entrypoints" / "flashdb-harness.json"
            profile = root / "config" / "competition-env" / "planned-batches" / "release-profile.json"
            artifact = root / "validation" / "evidence" / "flashdb" / "release-artifact.json"
            leaf = root / "validation" / "evidence" / "flashdb" / "release-leaf.json"
            unrelated = root / "validation" / "evidence" / "demo" / "historical.json"
            unrelated_leaf = root / "validation" / "evidence" / "demo" / "historical-leaf.json"

            leaf.parent.mkdir(parents=True)
            unrelated_leaf.parent.mkdir(parents=True)
            leaf.write_text('{"status":"passed"}\n', encoding="utf-8", newline="\n")
            unrelated_leaf.write_text('{"status":"stale"}\n', encoding="utf-8", newline="\n")
            write_json(artifact, {"leaf": {"path": rel(root, leaf), "sha256": "0" * 64}})
            write_json(profile, {"artifact": {"path": rel(root, artifact), "sha256": judge_validator.sha256_file(artifact)}})
            write_json(seed, {"profile": {"path": rel(root, profile), "sha256": judge_validator.sha256_file(profile)}})
            write_json(unrelated, {"leaf": {"path": rel(root, unrelated_leaf), "sha256": "0" * 64}})
            unrelated_before = unrelated.read_text(encoding="utf-8")

            update_result = resync_sha_bindings.resync_judge_chain(
                repo_root=root,
                seeds=[seed],
                max_passes=6,
            )
            check_result = resync_sha_bindings.resync_judge_chain(
                repo_root=root,
                seeds=[seed],
                max_passes=6,
                dry_run=True,
            )

            self.assertEqual(update_result["status"], "updated")
            self.assertEqual(check_result["status"], "unchanged")
            self.assertEqual(resync_sha_bindings.exit_code_for_result(check_result, check=True), 0)
            self.assertEqual(unrelated.read_text(encoding="utf-8"), unrelated_before)

    def test_judge_chain_scope_ignores_uncommitted_runtime_and_bootstrap_source_refs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "config" / "competition-env" / "judge-entrypoints" / "flashdb-harness.json"
            manifest = root / "validation" / "evidence" / "flashdb" / "harness" / "release-manifest.json"
            runtime_artifact = root / "target" / "competition-out" / "summary" / "competition-run-summary.json"
            runtime_artifact.parent.mkdir(parents=True)
            runtime_artifact.write_text('{"status":"passed"}\n', encoding="utf-8", newline="\n")

            write_json(
                manifest,
                {
                    "runtime": {"path": rel(root, runtime_artifact), "sha256": "0" * 64},
                    "source": {"path": "sources/FlashDB/src/fdb_utils.c", "sha256": "0" * 64},
                },
            )
            write_json(seed, {"manifest": {"path": rel(root, manifest), "sha256": judge_validator.sha256_file(manifest)}})

            result = resync_sha_bindings.resync_judge_chain(
                repo_root=root,
                seeds=[seed],
                max_passes=4,
                dry_run=True,
            )

            self.assertEqual(result["status"], "unchanged")
            self.assertEqual(result["missing_refs"], [])
            self.assertEqual(sorted(result["skipped_refs"]), ["sources/FlashDB/src/fdb_utils.c", rel(root, runtime_artifact)])
            self.assertEqual(result["changed_files"], [])
            self.assertEqual(result["scanned_json_files"], sorted([rel(root, seed), rel(root, manifest)]))
            self.assertEqual(resync_sha_bindings.exit_code_for_result(result, check=True), 0)

    def test_judge_chain_seeds_active_entrypoint_refs_but_bundle_files_are_terminal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            judge_config = root / "config" / "competition-env" / "judge-entrypoints" / "flashdb-harness.json"
            bundle = root / "config" / "competition-env" / "bundle-manifest.json"
            env = root / "config" / "competition-env" / "environment.json"
            active_profile = root / "config" / "competition-env" / "planned-batches" / "active.json"
            demo_profile = root / "config" / "competition-env" / "planned-batches" / "demo.json"
            review = root / "config" / "competition-env" / "review-checklists" / "review.json"
            manifest = root / "validation" / "evidence" / "flashdb" / "harness" / "active-manifest.json"

            write_json(env, {"profile_id": "test"})
            write_json(active_profile, {"profile_id": "active"})
            write_json(demo_profile, {"profile_id": "demo"})
            write_json(review, {"review": "recorded"})
            write_json(manifest, {"status": "passed"})
            write_json(
                bundle,
                {
                    "files": [
                        {"path": rel(root, active_profile), "sha256": judge_validator.sha256_file(active_profile)},
                        {"path": rel(root, demo_profile), "sha256": "0" * 64},
                    ]
                },
            )
            write_json(
                judge_config,
                {
                    "manifest_kind": "judge-entrypoints",
                    "environment_profile": {"path": rel(root, env), "sha256": judge_validator.sha256_file(env)},
                    "entrypoints": [
                        {
                            "id": "active",
                            "profile": {"path": rel(root, active_profile), "sha256": judge_validator.sha256_file(active_profile)},
                            "tracked_manifest": {"path": rel(root, manifest), "sha256": judge_validator.sha256_file(manifest)},
                            "review_checklist": {"path": rel(root, review), "sha256": judge_validator.sha256_file(review)},
                        }
                    ],
                },
            )

            result = resync_sha_bindings.resync_judge_chain(
                repo_root=root,
                max_passes=4,
                dry_run=True,
            )

            self.assertEqual(result["status"], "would_update")
            self.assertEqual(result["changed_files"], [rel(root, bundle)])
            self.assertEqual(
                result["scanned_json_files"],
                sorted([rel(root, judge_config), rel(root, bundle), rel(root, env), rel(root, active_profile), rel(root, review), rel(root, manifest)]),
            )
            self.assertNotIn(rel(root, demo_profile), result["scanned_json_files"])

    def test_judge_chain_self_and_cycle_refs_are_skipped_without_check_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "config" / "competition-env" / "judge-entrypoints" / "flashdb-harness.json"
            self_ref = root / "validation" / "evidence" / "flashdb" / "self.json"
            cycle_a = root / "validation" / "evidence" / "flashdb" / "cycle-a.json"
            cycle_b = root / "validation" / "evidence" / "flashdb" / "cycle-b.json"

            write_json(self_ref, {"self": {"path": rel(root, self_ref), "sha256": "0" * 64}})
            write_json(cycle_a, {"b": {"path": rel(root, cycle_b), "sha256": "0" * 64}})
            write_json(cycle_b, {"a": {"path": rel(root, cycle_a), "sha256": "0" * 64}})
            write_json(
                seed,
                {
                    "self_ref": {"path": rel(root, self_ref), "sha256": judge_validator.sha256_file(self_ref)},
                    "cycle": {"path": rel(root, cycle_a), "sha256": judge_validator.sha256_file(cycle_a)},
                },
            )

            result = resync_sha_bindings.resync_judge_chain(
                repo_root=root,
                seeds=[seed],
                max_passes=4,
                dry_run=True,
            )

            self.assertEqual(result["status"], "unchanged")
            self.assertEqual(result["self_refs"], [])
            self.assertEqual(result["cycle_refs"], [])
            self.assertEqual(result["skipped_self_refs"], [rel(root, self_ref)])
            self.assertEqual(sorted(result["skipped_cycle_refs"]), [rel(root, cycle_a), rel(root, cycle_b)])
            self.assertEqual(resync_sha_bindings.exit_code_for_result(result, check=True), 0)

    def test_judge_chain_keeps_entire_cycle_members_immutable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "config" / "competition-env" / "judge-entrypoints" / "flashdb-harness.json"
            cycle_a = root / "validation" / "evidence" / "flashdb" / "cycle-a.json"
            cycle_b = root / "validation" / "evidence" / "flashdb" / "cycle-b.json"
            leaf = root / "validation" / "evidence" / "flashdb" / "leaf.json"

            write_json(leaf, {"status": "stable"})
            write_json(
                cycle_a,
                {
                    "b": {"path": rel(root, cycle_b), "sha256": "0" * 64},
                    "leaf": {"path": rel(root, leaf), "sha256": "1" * 64},
                },
            )
            write_json(cycle_b, {"a": {"path": rel(root, cycle_a), "sha256": "0" * 64}})
            write_json(seed, {"cycle": {"path": rel(root, cycle_a), "sha256": judge_validator.sha256_file(cycle_a)}})
            before = {path: load_text(path) for path in (cycle_a, cycle_b)}

            result = resync_sha_bindings.resync_judge_chain(
                repo_root=root,
                seeds=[seed],
                max_passes=4,
            )

            self.assertEqual(result["status"], "unchanged")
            self.assertEqual(sorted(result["skipped_cycle_refs"]), [rel(root, cycle_a), rel(root, cycle_b)])
            self.assertEqual(before, {path: load_text(path) for path in (cycle_a, cycle_b)})

    def test_plain_path_back_reference_is_not_a_hash_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "config" / "competition-env" / "judge-entrypoints" / "flashdb-harness.json"
            target = root / "validation" / "evidence" / "flashdb" / "target.json"

            write_json(target, {"source": {"path": rel(root, seed)}})
            write_json(seed, {"target": {"path": rel(root, target), "sha256": "0" * 64}})

            result = resync_sha_bindings.resync_judge_chain(
                repo_root=root,
                seeds=[seed],
                max_passes=4,
            )

            self.assertEqual(result["status"], "updated")
            self.assertEqual(result["skipped_cycle_refs"], [])
            self.assertEqual(load_json(seed)["target"]["sha256"], judge_validator.sha256_file(target))

    def test_judge_chain_does_not_rewrite_semantic_evidence_sources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed = root / "config" / "competition-env" / "judge-entrypoints" / "flashdb-harness.json"
            tracked = root / "validation" / "evidence" / "sample" / "auto-translation" / "slice-a" / "tracked.json"
            leaf = tracked.parent / "leaf.txt"

            leaf.parent.mkdir(parents=True, exist_ok=True)
            leaf.write_text("stable\n", encoding="utf-8", newline="\n")
            write_json(tracked, {"leaf": {"path": rel(root, leaf), "sha256": "0" * 64}})
            write_json(seed, {"tracked": {"path": rel(root, tracked), "sha256": judge_validator.sha256_file(tracked)}})
            before = load_text(tracked)

            result = resync_sha_bindings.resync_judge_chain(
                repo_root=root,
                seeds=[seed],
                max_passes=4,
            )

            self.assertEqual(result["status"], "unchanged")
            self.assertIn(rel(root, tracked), result["skipped_immutable_sources"])
            self.assertEqual(load_text(tracked), before)


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


if __name__ == "__main__":
    unittest.main()

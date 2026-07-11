from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from validation.tools.validate_ai_finite_cross_project_suite import (
    DEFAULT_SUITE,
    SuiteContractError,
    validate_suite,
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _git(checkout: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(checkout), *args],
        capture_output=True,
        check=True,
        encoding="utf-8",
        errors="replace",
        timeout=5,
    )
    return completed.stdout.strip()


class AiFiniteCrossProjectSuiteTests(unittest.TestCase):
    TEST_REPOSITORY = "https://example.invalid/upstream"

    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]
        self.suite = json.loads((self.repo_root / DEFAULT_SUITE).read_text(encoding="utf-8"))
        if "project_sources" not in self.suite:
            self.suite["project_sources"] = {
                project_id: {
                    "repository": f"https://example.invalid/{project_id}",
                    "root": next(
                        item["source_binding"]["root"]
                        for item in self.suite["items"]
                        if item["project_id"] == project_id and item["source_binding"]["root"] is not None
                    ),
                    "commit": next(
                        item["source_binding"]["source_commit"]
                        for item in self.suite["items"]
                        if item["project_id"] == project_id and item["source_binding"]["source_commit"] is not None
                    ),
                }
                for project_id in ("flashdb", "zlib-ng", "libuv")
            }

    def _write_suite(self, root: Path, suite: dict) -> Path:
        path = root / "validation" / "suite.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(suite), encoding="utf-8")
        return path

    def _minimal_repo(
        self,
        declared_source: bytes | None = None,
        checkout_source: bytes | None = None,
    ) -> tuple[tempfile.TemporaryDirectory[str], Path, dict]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        source_root = root / "sources" / "upstream"
        source_root.mkdir(parents=True)
        source = source_root / "src" / "unit.c"
        source.parent.mkdir()
        span_raw = b"int unit(int value) { return value + 1; }"
        if declared_source is None:
            declared_source = b"static int seed = 1;\n" + span_raw + b"\n"
        source.write_bytes(declared_source if checkout_source is None else checkout_source)
        _git(source_root, "init")
        _git(source_root, "config", "core.autocrlf", "false")
        _git(source_root, "config", "user.name", "Suite Test")
        _git(source_root, "config", "user.email", "suite-test@example.invalid")
        _git(source_root, "remote", "add", "origin", f"{self.TEST_REPOSITORY}.git/")
        _git(source_root, "add", "src/unit.c")
        _git(source_root, "commit", "-m", "fixture source")
        source_commit = _git(source_root, "rev-parse", "HEAD")
        fixture = root / "validation" / "fixtures" / "unit.json"
        fixture.parent.mkdir(parents=True)
        fixture.write_text('{"cases": []}\n', encoding="utf-8")
        byte_start = declared_source.index(span_raw)
        byte_end = byte_start + len(span_raw)
        span_hash = _sha256_bytes(span_raw)
        file_hash = _sha256_bytes(declared_source)
        spec = {
            "target_id": "flashdb",
            "slice_id": "unit",
            "source": {
                "source_root": "sources/upstream",
                "source_commit": source_commit,
                "source_file_hashes": {"src/unit.c": file_hash},
            },
            "c_boundary": {
                "files": [{"path": "src/unit.c", "role": "source", "sha256": file_hash}],
                "signatures": [
                    {
                        "function": "unit",
                        "source_span": {
                            "file": "src/unit.c",
                            "line_start": 2,
                            "line_end": 2,
                            "byte_start": byte_start,
                            "byte_end": byte_end,
                            "sha256": span_hash,
                        },
                    }
                ],
            },
            "fixture_contract": {"path": "validation/fixtures/unit.json"},
        }
        spec_path = root / "validation" / "slice-specs" / "unit.json"
        spec_path.parent.mkdir(parents=True)
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        item = {
            "id": "flashdb-unit",
            "project_id": "flashdb",
            "slice_id": "unit",
            "provenance_kind": "real_upstream_source_slice",
            "construct_family": "scalar-arithmetic",
            "slice_spec": {"path": "validation/slice-specs/unit.json", "sha256": _sha256(spec_path)},
            "source_binding": {
                "root": "sources/upstream",
                "path": "src/unit.c",
                "source_commit": source_commit,
                "file_sha256": file_hash,
                "span": {
                    "line_start": 2,
                    "line_end": 2,
                    "byte_start": byte_start,
                    "byte_end": byte_end,
                    "sha256": span_hash,
                },
            },
            "fixture": {"path": "validation/fixtures/unit.json", "sha256": _sha256(fixture)},
            "fresh_executable": True,
        }
        return temp, root, item

    def _suite_with_ten_ready_items(self, root: Path, item: dict) -> dict:
        suite = copy.deepcopy(self.suite)
        suite["items"] = []
        suite["project_sources"] = {
            project_id: {
                "repository": self.TEST_REPOSITORY,
                "root": item["source_binding"]["root"],
                "commit": item["source_binding"]["source_commit"],
            }
            for project_id in ("flashdb", "zlib-ng", "libuv")
        }
        projects = ("flashdb", "zlib-ng", "libuv")
        for index in range(10):
            clone = copy.deepcopy(item)
            clone["id"] = f"real-unit-{index}"
            clone["project_id"] = projects[index % len(projects)]
            clone["construct_family"] = f"family-{index}"
            spec_path = root / "validation" / "slice-specs" / f"unit-{index}.json"
            spec = json.loads((root / item["slice_spec"]["path"]).read_text(encoding="utf-8"))
            spec["target_id"] = clone["project_id"]
            spec["slice_id"] = f"unit-{index}"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            clone["slice_id"] = spec["slice_id"]
            clone["slice_spec"] = {
                "path": f"validation/slice-specs/unit-{index}.json",
                "sha256": _sha256(spec_path),
            }
            suite["items"].append(clone)
        return suite

    def _bind_fragment_spec(
        self,
        root: Path,
        item: dict,
        *,
        file: str = "src/unit.c",
        hash_mode: str = "normalized_line_span_with_newline",
        sha256: str | None = None,
    ) -> None:
        item["provenance_kind"] = "real_upstream_source_fragment"
        span = item["source_binding"]["span"]
        source = (root / "sources/upstream/src/unit.c").read_bytes()
        span["byte_end"] += 1
        span["sha256"] = _sha256_bytes(source[span["byte_start"] : span["byte_end"]])
        spec_path = root / item["slice_spec"]["path"]
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        spec["c_boundary"]["signatures"] = []
        spec["translation_carrier"] = {
            "real_source": {
                "file": file,
                "fragment": {
                    "line_start": span["line_start"],
                    "line_end": span["line_end"],
                    "sha256": span["sha256"] if sha256 is None else sha256,
                    "hash_mode": hash_mode,
                },
            }
        }
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        item["slice_spec"]["sha256"] = _sha256(spec_path)

    def test_repository_contract_is_bounded_and_retains_blocked_items(self) -> None:
        repository_suite = json.loads((self.repo_root / DEFAULT_SUITE).read_text(encoding="utf-8"))
        if "project_sources" not in repository_suite:
            with self.assertRaisesRegex(SuiteContractError, "project_sources"):
                validate_suite(DEFAULT_SUITE, self.repo_root)
            return
        report = validate_suite(DEFAULT_SUITE, self.repo_root)
        self.assertEqual("passed", report["contract_status"])
        self.assertEqual(12, report["summary"]["items_total"])
        self.assertEqual(12, report["summary"]["construct_families"])
        self.assertGreaterEqual(report["summary"]["real_projects"], 3)
        self.assertEqual(12, report["summary"]["ready"] + report["summary"]["blocked"])
        self.assertEqual(0, report["summary"]["model_invocations"])
        self.assertEqual(4, report["summary"]["provenance_counts"]["real_project_synthetic_carrier"])
        self.assertEqual(1, report["summary"]["provenance_counts"]["real_project_unbound_slice"])

    def test_ready_item_reopens_source_span_and_fixture(self) -> None:
        temp, root, item = self._minimal_repo()
        self.addCleanup(temp.cleanup)
        suite = self._suite_with_ten_ready_items(root, item)
        path = self._write_suite(root, suite)
        report = validate_suite(path, root)
        self.assertEqual(10, report["summary"]["ready"])
        self.assertEqual("ready", report["status"])

    def test_lf_declaration_accepts_crlf_checkout(self) -> None:
        lf_source = b"static int seed = 1;\nint unit(int value) { return value + 1; }\n"
        crlf_source = lf_source.replace(b"\n", b"\r\n")
        temp, root, item = self._minimal_repo(lf_source, crlf_source)
        self.addCleanup(temp.cleanup)

        report = validate_suite(self._write_suite(root, self._suite_with_ten_ready_items(root, item)), root)

        self.assertEqual(10, report["summary"]["ready"])
        self.assertEqual("ready", report["status"])

    def test_crlf_declaration_accepts_lf_checkout(self) -> None:
        crlf_source = b"static int seed = 1;\r\nint unit(int value) { return value + 1; }\r\n"
        lf_source = crlf_source.replace(b"\r\n", b"\n")
        temp, root, item = self._minimal_repo(crlf_source, lf_source)
        self.addCleanup(temp.cleanup)

        report = validate_suite(self._write_suite(root, self._suite_with_ten_ready_items(root, item)), root)

        self.assertEqual(10, report["summary"]["ready"])
        self.assertEqual("ready", report["status"])

    def test_real_upstream_fragment_uses_translation_carrier_span(self) -> None:
        temp, root, item = self._minimal_repo()
        self.addCleanup(temp.cleanup)
        self._bind_fragment_spec(root, item)

        report = validate_suite(self._write_suite(root, self._suite_with_ten_ready_items(root, item)), root)

        self.assertEqual(10, report["summary"]["ready"])
        self.assertEqual("ready", report["status"])
        self.assertEqual(
            10,
            report["summary"]["provenance_counts"]["real_upstream_source_fragment"],
        )

    def test_real_upstream_fragment_rejects_invalid_spec_binding(self) -> None:
        cases = {
            "source file": {"file": "src/other.c"},
            "fragment sha": {"sha256": "0" * 64},
            "hash mode": {"hash_mode": "trimmed_normalized_span"},
        }
        for label, overrides in cases.items():
            with self.subTest(label=label):
                temp, root, item = self._minimal_repo()
                self.addCleanup(temp.cleanup)
                self._bind_fragment_spec(root, item, **overrides)

                report = validate_suite(
                    self._write_suite(root, self._suite_with_ten_ready_items(root, item)),
                    root,
                )

                self.assertEqual(0, report["summary"]["ready"])
                self.assertTrue(
                    all("source_span_binding_mismatch" in result["blocked_reasons"] for result in report["items"])
                )

    def test_real_upstream_fragment_recomputes_suite_byte_span(self) -> None:
        temp, root, item = self._minimal_repo()
        self.addCleanup(temp.cleanup)
        self._bind_fragment_spec(root, item)
        item["source_binding"]["span"]["byte_start"] += 1
        item["source_binding"]["span"]["byte_end"] += 1

        report = validate_suite(self._write_suite(root, self._suite_with_ten_ready_items(root, item)), root)

        self.assertEqual(0, report["summary"]["ready"])
        self.assertTrue(
            all("source_span_line_range_mismatch" in result["blocked_reasons"] for result in report["items"])
        )
        self.assertTrue(
            all("source_span_binding_mismatch" not in result["blocked_reasons"] for result in report["items"])
        )

    def test_real_upstream_fragment_rejects_suite_and_spec_wrong_lines(self) -> None:
        temp, root, item = self._minimal_repo()
        self.addCleanup(temp.cleanup)
        self._bind_fragment_spec(root, item)
        span = item["source_binding"]["span"]
        span["line_start"] = 1
        span["line_end"] = 1
        spec_path = root / item["slice_spec"]["path"]
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        fragment = spec["translation_carrier"]["real_source"]["fragment"]
        fragment["line_start"] = 1
        fragment["line_end"] = 1
        spec_path.write_text(json.dumps(spec), encoding="utf-8")
        item["slice_spec"]["sha256"] = _sha256(spec_path)

        report = validate_suite(self._write_suite(root, self._suite_with_ten_ready_items(root, item)), root)

        self.assertEqual(0, report["summary"]["ready"])
        self.assertTrue(
            all("source_span_line_range_mismatch" in result["blocked_reasons"] for result in report["items"])
        )
        self.assertTrue(
            all("source_span_binding_mismatch" not in result["blocked_reasons"] for result in report["items"])
        )

    def test_synthetic_carrier_is_not_ready(self) -> None:
        temp, root, item = self._minimal_repo()
        self.addCleanup(temp.cleanup)
        item["provenance_kind"] = "real_project_synthetic_carrier"
        item["fresh_executable"] = False

        report = validate_suite(self._write_suite(root, self._suite_with_ten_ready_items(root, item)), root)

        self.assertEqual(0, report["summary"]["ready"])
        self.assertTrue(
            all("fresh_execution_not_declared" in result["blocked_reasons"] for result in report["items"])
        )

    def test_fake_project_label_is_blocked(self) -> None:
        temp, root, item = self._minimal_repo()
        self.addCleanup(temp.cleanup)
        suite = self._suite_with_ten_ready_items(root, item)
        suite["items"][0]["project_id"] = "fake-project"

        report = validate_suite(self._write_suite(root, suite), root)

        first = next(result for result in report["items"] if result["id"] == "real-unit-0")
        self.assertIn("project_source_registry_missing", first["blocked_reasons"])

    def test_item_root_and_commit_must_match_project_registry(self) -> None:
        temp, root, item = self._minimal_repo()
        self.addCleanup(temp.cleanup)
        suite = self._suite_with_ten_ready_items(root, item)
        suite["items"][0]["source_binding"]["root"] = "sources/other"
        suite["items"][1]["source_binding"]["source_commit"] = "b" * 40

        report = validate_suite(self._write_suite(root, suite), root)

        first = next(result for result in report["items"] if result["id"] == "real-unit-0")
        second = next(result for result in report["items"] if result["id"] == "real-unit-1")
        self.assertIn("project_source_root_binding_mismatch", first["blocked_reasons"])
        self.assertIn("project_source_commit_binding_mismatch", second["blocked_reasons"])

    def test_project_registry_rejects_wrong_checkout_head(self) -> None:
        temp, root, item = self._minimal_repo()
        self.addCleanup(temp.cleanup)
        suite = self._suite_with_ten_ready_items(root, item)
        checkout = root / "sources/upstream"
        marker = checkout / "tracked-marker.txt"
        marker.write_text("new commit\n", encoding="utf-8")
        _git(checkout, "add", "tracked-marker.txt")
        _git(checkout, "commit", "-m", "move head")

        report = validate_suite(self._write_suite(root, suite), root)

        self.assertTrue(
            all("project_source_head_mismatch" in result["blocked_reasons"] for result in report["items"])
        )

    def test_project_registry_rejects_wrong_remote(self) -> None:
        temp, root, item = self._minimal_repo()
        self.addCleanup(temp.cleanup)
        suite = self._suite_with_ten_ready_items(root, item)
        _git(root / "sources/upstream", "remote", "set-url", "origin", "https://example.invalid/wrong.git")

        report = validate_suite(self._write_suite(root, suite), root)

        self.assertTrue(
            all("project_source_repository_mismatch" in result["blocked_reasons"] for result in report["items"])
        )

    def test_project_registry_rejects_dirty_tracked_file(self) -> None:
        temp, root, item = self._minimal_repo()
        self.addCleanup(temp.cleanup)
        suite = self._suite_with_ten_ready_items(root, item)
        (root / "sources/upstream/src/unit.c").write_bytes(
            b"static int seed = 1;\nint unit(int value) { return value + 2; }\n"
        )

        report = validate_suite(self._write_suite(root, suite), root)

        self.assertTrue(
            all("project_source_tracked_dirty" in result["blocked_reasons"] for result in report["items"])
        )

    def test_missing_pinned_root_and_hash_are_blocked_not_dropped(self) -> None:
        suite = copy.deepcopy(self.suite)
        suite["items"][0]["source_binding"]["root"] = None
        suite["items"][0]["source_binding"]["file_sha256"] = None
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for item in suite["items"]:
                source_spec = self.repo_root / item["slice_spec"]["path"]
                target_spec = root / item["slice_spec"]["path"]
                target_spec.parent.mkdir(parents=True, exist_ok=True)
                target_spec.write_bytes(source_spec.read_bytes())
                source_fixture = self.repo_root / item["fixture"]["path"]
                target_fixture = root / item["fixture"]["path"]
                target_fixture.parent.mkdir(parents=True, exist_ok=True)
                target_fixture.write_bytes(source_fixture.read_bytes())
            path = self._write_suite(root, suite)
            report = validate_suite(path, root)
        first = next(item for item in report["items"] if item["id"] == suite["items"][0]["id"])
        self.assertEqual("blocked", first["status"])
        self.assertIn("source_root_not_pinned", first["blocked_reasons"])
        self.assertIn("source_file_hash_missing", first["blocked_reasons"])
        self.assertEqual(12, report["summary"]["items_total"])

    def test_source_hash_drift_blocks_ready_item(self) -> None:
        temp, root, item = self._minimal_repo()
        self.addCleanup(temp.cleanup)
        suite = self._suite_with_ten_ready_items(root, item)
        (root / "sources/upstream/src/unit.c").write_bytes(
            b"static int seed = 1;\nint unit(int value) { return value + 2; }\n"
        )
        report = validate_suite(self._write_suite(root, suite), root)
        self.assertEqual(0, report["summary"]["ready"])
        self.assertTrue(all("source_file_sha256_mismatch" in item["blocked_reasons"] for item in report["items"]))
        self.assertTrue(all("source_span_sha256_mismatch" in item["blocked_reasons"] for item in report["items"]))

    def test_duplicate_construct_family_is_rejected(self) -> None:
        suite = copy.deepcopy(self.suite)
        suite["items"][1]["construct_family"] = suite["items"][0]["construct_family"]
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(SuiteContractError, "duplicate families"):
                validate_suite(self._write_suite(Path(temp), suite), temp)

    def test_demo_cannot_masquerade_as_real_project(self) -> None:
        suite = copy.deepcopy(self.suite)
        suite["items"][0]["slice_spec"]["path"] = "validation/slice-specs/demo-add-one.json"
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(SuiteContractError, "demo"):
                validate_suite(self._write_suite(Path(temp), suite), temp)

    def test_project_name_cannot_become_routing_input(self) -> None:
        suite = copy.deepcopy(self.suite)
        suite["translation_policy"]["project_name_is_routing_input"] = True
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(SuiteContractError, "project names"):
                validate_suite(self._write_suite(Path(temp), suite), temp)

    def test_more_than_twenty_items_is_rejected(self) -> None:
        suite = copy.deepcopy(self.suite)
        suite["items"] = [copy.deepcopy(suite["items"][0]) for _ in range(21)]
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(SuiteContractError, "1..20"):
                validate_suite(self._write_suite(Path(temp), suite), temp)

    def test_path_traversal_is_rejected(self) -> None:
        suite = copy.deepcopy(self.suite)
        suite["items"][0]["slice_spec"]["path"] = "../outside.json"
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(SuiteContractError, "slice-spec catalogue|safe POSIX"):
                validate_suite(self._write_suite(Path(temp), suite), temp)


if __name__ == "__main__":
    unittest.main()

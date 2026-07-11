from __future__ import annotations

import copy
import hashlib
import json
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


class AiFiniteCrossProjectSuiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repo_root = Path(__file__).resolve().parents[2]
        self.suite = json.loads((self.repo_root / DEFAULT_SUITE).read_text(encoding="utf-8"))

    def _write_suite(self, root: Path, suite: dict) -> Path:
        path = root / "validation" / "suite.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(suite), encoding="utf-8")
        return path

    def _minimal_repo(self) -> tuple[tempfile.TemporaryDirectory[str], Path, dict]:
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        source_root = root / "sources" / "upstream"
        source_root.mkdir(parents=True)
        source = source_root / "src" / "unit.c"
        source.parent.mkdir()
        source.write_bytes(b"int unit(int value) { return value + 1; }\n")
        fixture = root / "validation" / "fixtures" / "unit.json"
        fixture.parent.mkdir(parents=True)
        fixture.write_text('{"cases": []}\n', encoding="utf-8")
        span_raw = source.read_bytes()[:-1]
        span_hash = hashlib.sha256(span_raw).hexdigest()
        file_hash = _sha256(source)
        spec = {
            "target_id": "flashdb",
            "slice_id": "unit",
            "source": {
                "source_root": "sources/upstream",
                "source_commit": "a" * 40,
                "source_file_hashes": {"src/unit.c": file_hash},
            },
            "c_boundary": {
                "files": [{"path": "src/unit.c", "role": "source", "sha256": file_hash}],
                "signatures": [
                    {
                        "function": "unit",
                        "source_span": {
                            "file": "src/unit.c",
                            "line_start": 1,
                            "line_end": 1,
                            "byte_start": 0,
                            "byte_end": len(span_raw),
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
                "source_commit": "a" * 40,
                "file_sha256": file_hash,
                "span": {
                    "line_start": 1,
                    "line_end": 1,
                    "byte_start": 0,
                    "byte_end": len(span_raw),
                    "sha256": span_hash,
                },
            },
            "fixture": {"path": "validation/fixtures/unit.json", "sha256": _sha256(fixture)},
            "fresh_executable": True,
        }
        return temp, root, item

    def test_repository_contract_is_bounded_and_retains_blocked_items(self) -> None:
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
        suite = copy.deepcopy(self.suite)
        suite["items"] = []
        projects = ["flashdb", "zlib-ng", "libuv"]
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
        path = self._write_suite(root, suite)
        report = validate_suite(path, root)
        self.assertEqual(10, report["summary"]["ready"])
        self.assertEqual("ready", report["status"])

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
        suite = copy.deepcopy(self.suite)
        suite["items"] = []
        for index in range(10):
            clone = copy.deepcopy(item)
            clone["id"] = f"real-unit-{index}"
            clone["construct_family"] = f"family-{index}"
            clone["project_id"] = ("flashdb", "zlib-ng", "libuv")[index % 3]
            spec_path = root / "validation" / "slice-specs" / f"unit-{index}.json"
            spec = json.loads((root / item["slice_spec"]["path"]).read_text(encoding="utf-8"))
            spec["target_id"] = clone["project_id"]
            spec["slice_id"] = f"unit-{index}"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            clone["slice_id"] = spec["slice_id"]
            clone["slice_spec"] = {"path": f"validation/slice-specs/unit-{index}.json", "sha256": _sha256(spec_path)}
            suite["items"].append(clone)
        (root / "sources/upstream/src/unit.c").write_text("changed\n", encoding="utf-8")
        report = validate_suite(self._write_suite(root, suite), root)
        self.assertEqual(0, report["summary"]["ready"])
        self.assertTrue(all("source_file_sha256_mismatch" in item["blocked_reasons"] for item in report["items"]))

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

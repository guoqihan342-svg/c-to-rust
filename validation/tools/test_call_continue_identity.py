from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, Callable

from validation.tools import auto_migrate
from validation.tools._translation_carrier_reporter.call_continue_contract import KIND
from validation.tools._translation_carrier_reporter.call_continue_reports import mutation_manifest


REPO_ROOT = Path(__file__).resolve().parents[2]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class CallContinueIdentityTests(unittest.TestCase):
    def test_all_identity_bindings_accept_when_recomputed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="call-identity-", dir=REPO_ROOT / "target") as tmp:
            spec, spec_path, reports = evidence_set(Path(tmp))
            write_reports(spec, reports)
            accepted = auto_migrate.resolve_accepted_evidence(spec, spec_path)
        self.assertEqual(accepted["status"], "accepted")

    def test_each_identity_binding_drift_fails_closed(self) -> None:
        binding_keys = (
            "slice_spec_sha256", "fixture_sha256", "real_source_sha256",
            "source_fragment_sha256", "source_fragment_line_start", "source_fragment_line_end",
            "carrier_source_sha256", "c_oracle_harness_sha256",
            "generated_rust_draft_sha256", "generated_replay_test_sha256",
            "negative_mutation_manifest_sha256",
        )
        for key in binding_keys:
            with self.subTest(key=key), tempfile.TemporaryDirectory(
                prefix="call-identity-", dir=REPO_ROOT / "target"
            ) as tmp:
                spec, spec_path, reports = evidence_set(Path(tmp))
                replacement: Any = 99 if key.endswith("line_start") or key.endswith("line_end") else "f" * 64
                for label in ("c_oracle", "rust_report", "diff", "negative_diff"):
                    reports[label]["evidence_identity"]["bindings"][key] = replacement
                    resign(reports[label]["evidence_identity"])
                write_reports(spec, reports)
                with self.assertRaisesRegex(SystemExit, "mismatch"):
                    auto_migrate.resolve_accepted_evidence(spec, spec_path)

    def test_cross_report_and_mutation_artifact_drift_fail_closed(self) -> None:
        mutations: tuple[tuple[str, Callable[[dict[str, Any], dict[str, Any]], None]], ...] = (
            (
                "cross-report",
                lambda _spec, reports: mutate_one_identity(reports["diff"]),
            ),
            (
                "manifest-report",
                lambda _spec, reports: reports["negative_diff"]["mutation_manifest"].update(sha256="e" * 64),
            ),
            (
                "mutated-artifact",
                lambda _spec, reports: Path(
                    reports["negative_diff"]["actual_mutation_execution"]["scenarios"][1]["mutation"]["mutated_draft"]["path"]
                ).write_text("artifact drift\n", encoding="utf-8"),
            ),
        )
        for label, mutate in mutations:
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix="call-identity-", dir=REPO_ROOT / "target"
            ) as tmp:
                spec, spec_path, reports = evidence_set(Path(tmp))
                mutate(spec, reports)
                write_reports(spec, reports)
                with self.assertRaisesRegex(SystemExit, "mismatch"):
                    auto_migrate.resolve_accepted_evidence(spec, spec_path)


def evidence_set(root: Path) -> tuple[dict[str, Any], Path, dict[str, Any]]:
    source = root / "source.c"
    source.write_text("before();\nfragment();\nafter();\n", encoding="utf-8", newline="\n")
    fixture = root / "fixture.json"
    fixture_cases = [
        {"id": "hit", "inputs": {"scripted": 9}, "expected_outputs": {"returned": True}},
        {"id": "wrap-hit", "inputs": {"scripted": 9}, "expected_outputs": {"returned": True}},
        {"id": "zero", "inputs": {"scripted": 0}, "expected_outputs": {"returned": False}},
        {"id": "ordinary", "inputs": {"scripted": 4}, "expected_outputs": {"returned": False}},
    ]
    fixture.write_text(json.dumps({"cases": fixture_cases}), encoding="utf-8", newline="\n")
    harness = root / "harness.c"
    harness.write_text("int main(void) { return 0; }\n", encoding="utf-8", newline="\n")
    draft = root / "draft.rs"
    draft.write_text("fn translated(v: u32) -> bool { if v == 9 { continue_probe(); continue; } false }\nfn continue_probe() {}\n", encoding="utf-8", newline="\n")
    replay = root / "replay.rs"
    replay.write_text("#[test] fn replay() {}\n", encoding="utf-8", newline="\n")
    original = draft.read_bytes()
    scenarios = []
    for scenario_id, before, after, case_ids in (
        ("comparison-equality-flip", b"==", b"!=", ["hit", "wrap-hit", "zero", "ordinary"]),
        ("continue-noop", b"continue;", b"/*noop*/;", ["hit", "wrap-hit"]),
    ):
        offset = original.index(before)
        mutated = original[:offset] + after + original[offset + len(before):]
        path = root / f"mutated-{scenario_id}.rs"
        path.write_bytes(mutated)
        passed_ids = [
            case_id for case_id in ["hit", "wrap-hit", "zero", "ordinary"]
            if case_id not in case_ids
        ]
        scenarios.append({
            "scenario_id": scenario_id,
            "mutation": {
                "operator_from": before.decode("ascii"), "operator_to": after.decode("ascii"),
                "mutation_count": 1, "byte_offset": offset,
                "original_draft": {"path": str(draft), "sha256": sha(draft)},
                "mutated_draft": {"path": str(path), "sha256": sha(path)},
            },
            "expected_detected_case_ids": case_ids,
            "partition_replay": {
                "detected_case_ids": case_ids,
                "passed_case_ids": passed_ids,
            },
        })
    execution = {"scenarios": scenarios}
    manifest = mutation_manifest(execution)
    c_source = "static void carrier(void) { fragment(); }\n"
    spec = {
        "target_id": "renamed-target", "slice_id": "renamed-call-continue",
        "source_commit": "a" * 40, "source_root": str(root), "source_file": source.name,
        "source_file_hashes": {source.name: sha(source)}, "c_source": c_source,
        "fixture_hash": sha(fixture),
        "replay_contract": {
            "kind": KIND,
            "external_callee": {"return_fixture_field": "scripted"},
            "comparison": {"sentinel": 9},
            "return": {"fixture_field": "returned"},
        },
        "translation_carrier": {
            "carrier_source_sha256": text_sha(c_source),
            "real_source": {"fragment": {"line_start": 2, "line_end": 2, "sha256": text_sha("fragment();\n")}},
        },
        "fixture_contract": {
            "path": str(fixture), "hash": sha(fixture),
            **{name: str(root / f"{name}.json") for name in (
                "c_oracle", "rust_report", "diff", "negative_diff", "unsafe_scan", "unsafe_ledger"
            )},
        },
    }
    spec_path = root / "slice-spec.json"
    spec_path.write_text(json.dumps(spec, sort_keys=True), encoding="utf-8", newline="\n")
    bindings = {
        "slice_spec_sha256": sha(spec_path), "fixture_sha256": sha(fixture),
        "real_source_sha256": sha(source), "source_fragment_sha256": text_sha("fragment();\n"),
        "source_fragment_line_start": 2, "source_fragment_line_end": 2,
        "carrier_source_sha256": text_sha(c_source), "c_oracle_harness_sha256": sha(harness),
        "generated_rust_draft_sha256": sha(draft), "generated_replay_test_sha256": sha(replay),
        "negative_mutation_manifest_sha256": manifest["sha256"],
    }
    identity = {
        "schema_version": 2, "target_id": spec["target_id"], "slice_id": spec["slice_id"],
        "source_commit": spec["source_commit"], "replay_contract_kind": KIND, "bindings": bindings,
    }
    resign(identity)
    common = {
        "target_id": spec["target_id"], "slice_id": spec["slice_id"],
        "source_commit": spec["source_commit"], "evidence_identity": identity,
    }
    refs = {
        "c_oracle_harness": {"path": str(harness), "sha256": sha(harness)},
        "generated_rust_draft": {"path": str(draft), "sha256": sha(draft)},
        "generated_replay_test": {"path": str(replay), "sha256": sha(replay)},
    }
    reports = {
        "c_oracle": {**copy.deepcopy(common), "status": "passed", "toolchain_status": "C_ORACLE_GENERATED", "provenance": {"evidence_refs": refs}},
        "rust_report": {**copy.deepcopy(common), "status": "passed"},
        "diff": {**copy.deepcopy(common), "status": "passed", "first_mismatch": None},
        "negative_diff": {
            **copy.deepcopy(common), "status": "expected_failed", "mutation_detected": True,
            "mutation_manifest": manifest, "actual_mutation_execution": execution,
            "partition_detection": {
                "comparison-equality-flip": {"detected_case_ids": ["hit", "wrap-hit", "zero", "ordinary"], "passed_case_ids": []},
                "continue-noop": {"detected_case_ids": ["hit", "wrap-hit"], "passed_case_ids": ["zero", "ordinary"]},
            },
        },
        "unsafe_scan": {"status": "passed", "source_commit": spec["source_commit"]},
        "unsafe_ledger": {"status": "recorded"},
    }
    return spec, spec_path, reports


def resign(identity: dict[str, Any]) -> None:
    material = {key: value for key, value in identity.items() if key not in {"identity_sha256", "recomputed"}}
    identity["identity_sha256"] = text_sha(json.dumps(material, sort_keys=True, separators=(",", ":")))
    identity["recomputed"] = True


def mutate_one_identity(report: dict[str, Any]) -> None:
    report["evidence_identity"]["bindings"]["carrier_source_sha256"] = "d" * 64
    resign(report["evidence_identity"])


def write_reports(spec: dict[str, Any], reports: dict[str, Any]) -> None:
    for name, report in reports.items():
        Path(spec["fixture_contract"][name]).write_text(
            json.dumps(report), encoding="utf-8", newline="\n"
        )


if __name__ == "__main__":
    unittest.main()

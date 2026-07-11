import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from validation.tools import auto_migrate


REPO_ROOT = Path(__file__).resolve().parents[2]
KIND = "record_interior_projection_u32_reset_add_while_continue_state"


def raw_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def text_sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class AcceptedEvidenceIdentityTests(unittest.TestCase):
    def test_matching_identity_is_accepted(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="accepted-identity-", dir=REPO_ROOT / "target"
        ) as tmp:
            spec, reports = self._evidence_set(Path(tmp))
            self._write_reports(spec, reports)

            accepted = auto_migrate.resolve_accepted_evidence(spec)

            self.assertEqual(accepted["status"], "accepted")

    def test_identity_substitutions_fail_closed(self) -> None:
        mutations = {
            "slice-id": lambda reports: reports["c_oracle"].update(slice_id="other-slice"),
            "fragment-hash": lambda reports: reports["diff"]["evidence_identity"]["bindings"].update(
                source_fragment_sha256="1" * 64
            ),
            "carrier-hash": lambda reports: reports["rust_report"]["evidence_identity"]["bindings"].update(
                carrier_source_sha256="2" * 64
            ),
            "draft-hash": lambda reports: reports["c_oracle"]["evidence_identity"]["bindings"].update(
                generated_rust_draft_sha256="3" * 64
            ),
            "mutation-original-hash": lambda reports: reports["negative_diff"][
                "actual_mutation_execution"
            ]["mutation"]["original_draft"].update(sha256="4" * 64),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix="accepted-identity-", dir=REPO_ROOT / "target"
            ) as tmp:
                spec, reports = self._evidence_set(Path(tmp))
                mutate(reports)
                self._write_reports(spec, reports)
                with self.assertRaisesRegex(SystemExit, "mismatch"):
                    auto_migrate.resolve_accepted_evidence(spec)

    def test_adjacent_legacy_replay_does_not_require_identity(self) -> None:
        spec = {
            "target_id": "fixture-target",
            "slice_id": "legacy-slice",
            "source_commit": "a" * 40,
            "replay_contract": {"kind": "record_interior_projection_u32_state"},
        }
        report = {
            "target_id": "fixture-target",
            "slice_id": "legacy-slice",
            "source_commit": "a" * 40,
            "status": "passed",
            "toolchain_status": "C_ORACLE_GENERATED",
        }
        auto_migrate.require_accepted_report(spec, "c_oracle", report, require_toolchain=True)

    def _evidence_set(self, root: Path) -> tuple[dict, dict]:
        source = root / "source.c"
        source.write_text("before();\nchanged();\nafter();\n", encoding="utf-8", newline="\n")
        fixture = root / "fixture.json"
        fixture.write_text('{"cases": []}\n', encoding="utf-8", newline="\n")
        draft = root / "draft.rs"
        draft.write_text("pub fn translated() {}\n", encoding="utf-8", newline="\n")
        c_source = "static void carrier(void) {\nchanged();\n}\n"
        fragment_sha = text_sha("changed();\n")
        draft_ref = {"path": str(draft), "sha256": raw_sha(draft)}
        spec = {
            "target_id": "fixture-target",
            "slice_id": "identity-slice",
            "source_commit": "a" * 40,
            "source_root": str(root),
            "source_file": source.name,
            "c_source": c_source,
            "fixture_hash": raw_sha(fixture),
            "replay_contract": {"kind": KIND},
            "translation_carrier": {
                "carrier_source_sha256": text_sha(c_source),
                "real_source": {
                    "fragment": {
                        "line_start": 2,
                        "line_end": 2,
                        "sha256": fragment_sha,
                    }
                },
            },
            "fixture_contract": {
                "path": str(fixture),
                "hash": raw_sha(fixture),
                **{
                    name: str(root / f"{name}.json")
                    for name in (
                        "c_oracle",
                        "rust_report",
                        "diff",
                        "negative_diff",
                        "unsafe_scan",
                        "unsafe_ledger",
                    )
                },
            },
        }
        identity = self._identity(spec, fragment_sha, raw_sha(draft))
        common = {
            "target_id": spec["target_id"],
            "slice_id": spec["slice_id"],
            "source_commit": spec["source_commit"],
        }
        reports = {
            "c_oracle": {
                **common,
                "evidence_identity": copy.deepcopy(identity),
                "status": "passed",
                "toolchain_status": "C_ORACLE_GENERATED",
                "provenance": {
                    "evidence_refs": {"generated_rust_draft": copy.deepcopy(draft_ref)}
                },
            },
            "rust_report": {
                **common,
                "evidence_identity": copy.deepcopy(identity),
                "status": "passed",
                "provenance": {"refs": {"generated_rust_draft": copy.deepcopy(draft_ref)}},
            },
            "diff": {
                **common,
                "evidence_identity": copy.deepcopy(identity),
                "status": "passed",
                "first_mismatch": None,
            },
            "negative_diff": {
                **common,
                "evidence_identity": copy.deepcopy(identity),
                "status": "expected_failed",
                "mutation_detected": True,
                "actual_mutation_execution": {
                    "mutation": {"original_draft": copy.deepcopy(draft_ref)}
                },
            },
            "unsafe_scan": {"status": "passed", "source_commit": spec["source_commit"]},
            "unsafe_ledger": {"status": "recorded"},
        }
        return spec, copy.deepcopy(reports)

    def _identity(self, spec: dict, fragment_sha: str, draft_sha: str) -> dict:
        material = {
            "schema_version": 1,
            "target_id": spec["target_id"],
            "slice_id": spec["slice_id"],
            "source_commit": spec["source_commit"],
            "replay_contract_kind": KIND,
            "bindings": {
                "slice_spec_sha256": "5" * 64,
                "fixture_sha256": spec["fixture_hash"],
                "real_source_sha256": "6" * 64,
                "source_fragment_sha256": fragment_sha,
                "source_fragment_line_start": 2,
                "source_fragment_line_end": 2,
                "carrier_source_sha256": spec["translation_carrier"]["carrier_source_sha256"],
                "c_oracle_harness_sha256": "7" * 64,
                "generated_rust_draft_sha256": draft_sha,
                "generated_replay_test_sha256": "8" * 64,
            },
        }
        digest = text_sha(json.dumps(material, sort_keys=True, separators=(",", ":")))
        return {**material, "identity_sha256": digest, "recomputed": True}

    def _write_reports(self, spec: dict, reports: dict) -> None:
        for name, report in reports.items():
            path = Path(spec["fixture_contract"][name])
            path.write_text(json.dumps(report), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    unittest.main()

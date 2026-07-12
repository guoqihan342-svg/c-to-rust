from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

from validation.tools import run_ai_auxiliary_cross_project_suite as module


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def ready_preflight(total: int) -> dict[str, object]:
    return {
        "contract_status": "passed",
        "status": "ready",
        "summary": {
            "items_total": total,
            "ready": total,
            "blocked": 0,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }


class AuxiliaryCrossProjectSuiteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="ai-aux-suite-")
        self.root = Path(self.temporary.name)
        self.suite_path = self.root / "validation" / "suite.json"
        self.items = [
            {
                "id": "project-a-one",
                "project_id": "project-a",
                "slice_id": "one",
                "construct_family": "loop",
                "slice_spec": {"path": "validation/one.json", "sha256": "a" * 64},
            },
            {
                "id": "project-b-two",
                "project_id": "project-b",
                "slice_id": "two",
                "construct_family": "record",
                "slice_spec": {"path": "validation/two.json", "sha256": "b" * 64},
            },
        ]
        write_json(
            self.suite_path,
            {"schema_version": 1, "suite_id": "aux-test", "items": self.items},
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_auxiliary_results_are_separate_from_competition_numerators(self) -> None:
        calls: list[dict[str, object]] = []

        def fake_unit_runner(**kwargs: object) -> dict[str, object]:
            calls.append(kwargs)
            item = kwargs["item"]
            index = kwargs["index"]
            passed = index == 0
            return {
                "index": index,
                "item_id": item["id"],
                "project_id": item["project_id"],
                "construct_family": item["construct_family"],
                "target_id": item["project_id"],
                "slice_id": item["slice_id"],
                "status": "exact_pass" if passed else "exact_failed",
                "returncode": 0,
                "duration_ms": 5,
                "provider_invocations": 1,
                "repair_rounds": 0,
                "auxiliary_exact_pass": passed,
                "reason": None if passed else "common_exact_gates_failed",
                "artifacts": {},
                "_candidate_manifest_path": None,
            }

        with mock.patch.object(module, "validate_suite", return_value=ready_preflight(2)):
            exit_code, report, report_path = module.run_suite(
                suite=self.suite_path,
                out_root=self.root / "target" / "out",
                repo_root=self.root,
                unit_runner=fake_unit_runner,
                max_workers=2,
            )

        self.assertEqual(0, exit_code)
        self.assertEqual("completed", report["status"])
        self.assertEqual(2, len(calls))
        self.assertEqual(2, report["execution"]["max_workers"])
        self.assertEqual([0, 1], [unit["index"] for unit in report["units"]])
        self.assertEqual(2, report["summary"]["provider_invocations"])
        self.assertEqual(1, report["summary"]["auxiliary_exact_pass"])
        self.assertEqual(0, report["claim_boundary"]["competition_success_numerator"])
        self.assertEqual(0, report["claim_boundary"]["translation_coverage_numerator"])
        self.assertFalse(report["claim_boundary"]["closes_p0_a10"])
        self.assertFalse(report["model"]["competition_eligible"])
        self.assertEqual("auxiliary-local-validation", report["model"]["evaluation_scope"])
        self.assertEqual(report, json.loads(report_path.read_text(encoding="utf-8")))

    def test_competition_model_is_rejected_before_preflight(self) -> None:
        with mock.patch.object(module, "validate_suite") as preflight:
            with self.assertRaisesRegex(ValueError, "noncompetition resolved model"):
                module.run_suite(
                    suite=self.suite_path,
                    out_root=self.root / "target" / "out",
                    model="zai/glm-5.1",
                    repo_root=self.root,
                )
        preflight.assert_not_called()

    def test_blocked_preflight_writes_zero_unit_report(self) -> None:
        blocked = {
            "contract_status": "passed",
            "status": "blocked",
            "summary": {"items_total": 2, "ready": 1, "blocked": 1},
        }
        with mock.patch.object(module, "validate_suite", return_value=blocked):
            exit_code, report, report_path = module.run_suite(
                suite=self.suite_path,
                out_root=self.root / "target" / "blocked",
                repo_root=self.root,
            )

        self.assertEqual(2, exit_code)
        self.assertEqual("blocked", report["status"])
        self.assertEqual([], report["units"])
        self.assertEqual(0, report["summary"]["provider_invocations"])
        self.assertEqual(report, json.loads(report_path.read_text(encoding="utf-8")))

    def test_run_unit_forces_ai_only_finite_execution(self) -> None:
        spec_path = self.root / "validation" / "one.json"
        write_json(spec_path, {"target_id": "project-a", "slice_id": "one"})
        self.items[0]["slice_spec"]["sha256"] = module.sha256_path(spec_path)
        commands: list[list[str]] = []
        environments: list[dict[str, str]] = []

        def fake_command(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            commands.append(command)
            environments.append(kwargs["env"])
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="failed")

        unit = module.run_unit(
            item=self.items[0],
            index=0,
            repo_root=self.root,
            evidence_root=self.root / "target" / "evidence",
            logs_root=self.root / "target" / "logs",
            report_path=self.root / "target" / "summary" / "report.json",
            model=module.DEFAULT_MODEL,
            agent=module.DEFAULT_AGENT,
            variant=module.DEFAULT_VARIANT,
            timeout_seconds=30,
            repair_rounds=1,
            opencode_command="opencode",
            command_runner=fake_command,
        )

        self.assertEqual("execution_failed", unit["status"])
        self.assertEqual("ai_candidate_manifest_missing", unit["reason"])
        command = commands[0]
        self.assertIn("--ai-first-candidate", command)
        self.assertEqual("off", command[command.index("--ai-deterministic-fallback") + 1])
        self.assertEqual(module.DEFAULT_MODEL, command[command.index("--ai-model") + 1])
        self.assertNotIn("--accept-existing-evidence", command)
        self.assertTrue(Path(environments[0]["XDG_DATA_HOME"]).is_absolute())
        self.assertNotEqual(environments[0]["XDG_DATA_HOME"], str(Path.home() / ".local" / "share"))

    def test_output_path_escape_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "path escapes repository"):
            module.run_suite(
                suite=self.suite_path,
                out_root=Path("..") / "escape",
                repo_root=self.root,
            )

    def test_nonempty_output_root_is_rejected_before_preflight(self) -> None:
        output_root = self.root / "target" / "stale"
        write_json(output_root / "evidence" / "old.json", {"status": "stale"})
        with mock.patch.object(module, "validate_suite") as preflight:
            with self.assertRaisesRegex(ValueError, "stale evidence reuse"):
                module.run_suite(
                    suite=self.suite_path,
                    out_root=output_root,
                    repo_root=self.root,
                )
        preflight.assert_not_called()

    def test_output_root_reservation_is_atomic_and_precedes_preflight(self) -> None:
        output_root = self.root / "target" / "reserved"

        def blocked_preflight(_suite: Path, _root: Path) -> dict[str, object]:
            self.assertTrue((output_root / ".ai-auxiliary-run-reservation").is_file())
            return {
                "contract_status": "passed",
                "status": "blocked",
                "summary": {"items_total": 2, "ready": 0, "blocked": 2},
            }

        with mock.patch.object(module, "validate_suite", side_effect=blocked_preflight):
            exit_code, _, _ = module.run_suite(
                suite=self.suite_path,
                out_root=output_root,
                repo_root=self.root,
            )
        self.assertEqual(2, exit_code)
        with self.assertRaisesRegex(ValueError, "stale evidence reuse|already reserved"):
            module.reserve_output_root(output_root)

    def test_path_unsafe_and_duplicate_unit_identities_are_rejected_before_preflight(self) -> None:
        unsafe = json.loads(json.dumps(self.items))
        unsafe[0]["slice_id"] = "one/../../escape"
        duplicate = json.loads(json.dumps(self.items))
        duplicate[1]["project_id"] = duplicate[0]["project_id"]
        duplicate[1]["slice_id"] = duplicate[0]["slice_id"]
        for items, message in (
            (unsafe, "path-safe identifier"),
            (duplicate, "pairs must be unique"),
        ):
            with self.subTest(message=message):
                write_json(self.suite_path, {"schema_version": 1, "suite_id": "aux-test", "items": items})
                with mock.patch.object(module, "validate_suite") as preflight:
                    with self.assertRaisesRegex(ValueError, message):
                        module.run_suite(
                            suite=self.suite_path,
                            out_root=self.root / "target" / message.replace(" ", "-"),
                            repo_root=self.root,
                        )
                preflight.assert_not_called()

    def test_slice_spec_hash_drift_is_rejected_before_and_after_execution(self) -> None:
        spec_path = self.root / "validation" / "one.json"
        write_json(spec_path, {"target_id": "project-a", "slice_id": "one"})
        expected_sha = module.sha256_path(spec_path)
        item = json.loads(json.dumps(self.items[0]))
        item["slice_spec"]["sha256"] = "0" * 64
        before = module.run_unit(
            item=item,
            index=0,
            repo_root=self.root,
            evidence_root=self.root / "target" / "before" / "evidence",
            logs_root=self.root / "target" / "before" / "logs",
            report_path=self.root / "target" / "before" / "summary" / "report.json",
            model=module.DEFAULT_MODEL,
            agent=module.DEFAULT_AGENT,
            variant=module.DEFAULT_VARIANT,
            timeout_seconds=30,
            repair_rounds=0,
            opencode_command="opencode",
        )
        self.assertEqual("slice_spec_sha256_mismatch_before_launch", before["reason"])

        item["slice_spec"]["sha256"] = expected_sha

        def mutate_spec(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            write_json(spec_path, {"target_id": "project-a", "slice_id": "changed"})
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="changed")

        after = module.run_unit(
            item=item,
            index=0,
            repo_root=self.root,
            evidence_root=self.root / "target" / "after" / "evidence",
            logs_root=self.root / "target" / "after" / "logs",
            report_path=self.root / "target" / "after" / "summary" / "report.json",
            model=module.DEFAULT_MODEL,
            agent=module.DEFAULT_AGENT,
            variant=module.DEFAULT_VARIANT,
            timeout_seconds=30,
            repair_rounds=0,
            opencode_command="opencode",
            command_runner=mutate_spec,
        )
        self.assertEqual("contract_failed", after["status"])
        self.assertEqual("slice_spec_sha256_changed_during_execution", after["reason"])


if __name__ == "__main__":
    unittest.main()

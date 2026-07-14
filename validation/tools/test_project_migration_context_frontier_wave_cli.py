from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import unittest
from unittest import mock

import validation.tools.project_migration_harness as entrypoint
from validation.tools._project_migration_harness.artifacts import canonical_json_bytes
from validation.tools._project_migration_harness.project_migration_cli import (
    parse_args,
)
from validation.tools.project_migration_controller_test_support import (
    ProjectMigrationControllerCase,
)


SOURCE = (
    "int alpha(int value) { return value + 1; }\n"
    "int beta(int value) { return alpha(value); }\n"
)


class ProjectMigrationContextFrontierWaveCliTests(
    ProjectMigrationControllerCase,
):
    def test_real_two_wave_cli_refreshes_next_wave_without_launch(self) -> None:
        plan, argv = self.command()
        dag = self.load(_artifact_path(plan, "portfolio_dag"))
        previous = dag["waves"][0]["group_ids"]
        following = dag["waves"][1]["group_ids"]
        _mark_last_good(self.ledger(), plan["run_id"], previous)
        before = self.runtime_counts(plan["run_id"])

        code, output = self.invoke(argv)

        result = json.loads(output)
        self.assertEqual(0, code)
        self.assertEqual(canonical_json_bytes(result).decode("utf-8"), output)
        self.assertEqual("ready", result["status"])
        self.assertEqual(following, [
            item["unit_id"] for item in result["selection_directives"]
        ])
        frontiers = {
            item["unit_id"]: item
            for item in self.ledger().context_frontier_states(plan["run_id"])
        }
        self.assertTrue(all(
            frontiers[unit_id]["status"] == "ready"
            and frontiers[unit_id]["state_version"] == 2
            and frontiers[unit_id]["head"]["query_epoch"] == 1
            for unit_id in following
        ))
        after = self.runtime_counts(plan["run_id"])
        self.assertEqual((0, 0), (after[0] - before[0], after[1] - before[1]))
        self.assertEqual((0, 0), self.active_runtime_counts(plan["run_id"]))

    def test_cli_exposes_no_caller_owned_authority_or_plan_refs(self) -> None:
        _plan, argv = self.command()
        parsed = parse_args(argv)
        for field in (
            "run_id", "unit_id", "db", "status", "verdict",
            "portfolio_path", "context_path",
        ):
            self.assertFalse(hasattr(parsed, field))
        for option in (
            "--run-id", "--unit-id", "--db", "--status", "--verdict",
            "--portfolio-path", "--context-path",
        ):
            with (
                self.subTest(option=option),
                redirect_stderr(io.StringIO()),
                self.assertRaises(SystemExit),
            ):
                parse_args([*argv, option, "caller-owned"])

    def test_all_input_paths_fail_closed_outside_repository_target(self) -> None:
        plan, argv = self.command()
        for option, value in (
            ("--plan", "source/project-migration-plan.json"),
            ("--latest-dag-path", "source/portfolio-dag.json"),
            ("--failure-evidence", "source/failure-evidence.json"),
            ("--expansion-queries", "../expansion-queries.json"),
        ):
            with self.subTest(option=option):
                with self.assertRaisesRegex(SystemExit, "target directory"):
                    self.invoke(_replace(argv, option, value))
        self.assertEqual(0, self.frontier_event_count(plan["run_id"]))

    def test_plan_owned_portfolio_and_context_paths_cannot_escape_output_root(self) -> None:
        plan, argv = self.command()
        plan_path = self.out_root / "project-migration-plan.json"
        for name in ("portfolio", "context_pages"):
            original = plan["artifacts"][name]["path"]
            plan["artifacts"][name]["path"] = "../outside.json"
            plan_path.write_text(json.dumps(plan), encoding="utf-8")
            with self.subTest(name=name):
                with self.assertRaisesRegex(SystemExit, "artifact binding is invalid"):
                    self.invoke(argv)
            plan["artifacts"][name]["path"] = original
        self.assertEqual(0, self.frontier_event_count(plan["run_id"]))

    def test_latest_dag_sha_and_size_fail_closed_before_frontier_event(self) -> None:
        plan, argv = self.command()
        cases = (
            ("--latest-dag-sha256", "0" * 64),
            ("--latest-dag-size-bytes", "1"),
        )
        for option, value in cases:
            with self.subTest(option=option), self.assertRaises(ValueError):
                self.invoke(_replace(argv, option, value))
            self.assertEqual(0, self.frontier_event_count(plan["run_id"]))

    def test_failure_and_query_inputs_must_be_explicit_json_arrays(self) -> None:
        plan, argv = self.command()
        for option, filename in (
            ("--failure-evidence", "failure-evidence.json"),
            ("--expansion-queries", "expansion-queries.json"),
        ):
            path = self.out_root / "cli-inputs" / filename
            path.write_text("{}", encoding="utf-8")
            with self.subTest(option=option):
                with self.assertRaisesRegex(SystemExit, "expected JSON array"):
                    self.invoke(argv)
            path.write_text("[]", encoding="utf-8")
        self.assertEqual(0, self.frontier_event_count(plan["run_id"]))

    def command(self) -> tuple[dict, list[str]]:
        plan = self.plan(SOURCE)
        inputs = self.out_root / "cli-inputs"
        inputs.mkdir(parents=True, exist_ok=True)
        for name in ("failure-evidence.json", "expansion-queries.json"):
            (inputs / name).write_text("[]", encoding="utf-8")
        dag = plan["artifacts"]["portfolio_dag"]
        return plan, [
            "prepare-next-context-frontier-wave",
            "--plan", "target/run/project-migration-plan.json",
            "--latest-dag-path", _artifact_path(plan, "portfolio_dag"),
            "--latest-dag-sha256", dag["sha256"],
            "--latest-dag-size-bytes", str(dag["size_bytes"]),
            "--completed-wave-index", "0",
            "--failure-evidence", "target/run/cli-inputs/failure-evidence.json",
            "--expansion-queries", "target/run/cli-inputs/expansion-queries.json",
        ]

    def invoke(self, argv: list[str]) -> tuple[int, str]:
        output = io.StringIO()
        with (
            mock.patch.object(entrypoint, "REPO_ROOT", self.harness),
            redirect_stdout(output),
        ):
            code = entrypoint.main(argv)
        return code, output.getvalue()

    def runtime_counts(self, run_id: str) -> tuple[int, int]:
        with self.ledger().connect() as connection:
            attempts = connection.execute(
                "select count(*) from attempts where run_id=?", (run_id,),
            ).fetchone()[0]
            leases = connection.execute(
                "select count(*) from leases where run_id=?", (run_id,),
            ).fetchone()[0]
        return int(attempts), int(leases)

    def frontier_event_count(self, run_id: str) -> int:
        with self.ledger().connect() as connection:
            return int(connection.execute(
                "select count(*) from context_frontier_events where run_id=?",
                (run_id,),
            ).fetchone()[0])

    def active_runtime_counts(self, run_id: str) -> tuple[int, int]:
        with self.ledger().connect() as connection:
            running = connection.execute(
                "select count(*) from attempts where run_id=? and status='running'",
                (run_id,),
            ).fetchone()[0]
            active = connection.execute(
                "select count(*) from leases where run_id=? and status='active'",
                (run_id,),
            ).fetchone()[0]
        return int(running), int(active)


def _mark_last_good(ledger: object, run_id: str, unit_ids: list[str]) -> None:
    with ledger.connect() as connection:
        for unit_id in unit_ids:
            assignment = connection.execute(
                """select worker_id,role from assignments
                   where run_id=? and unit_id=? order by role limit 1""",
                (run_id, unit_id),
            ).fetchone()
            worker_id, role = str(assignment["worker_id"]), str(assignment["role"])
            attempt_id, artifact_id = (
                f"test-attempt-{unit_id}", f"test-last-good-{unit_id}",
            )
            connection.execute(
                """insert into attempts(attempt_id,run_id,unit_id,role,ordinal,
                   worker_id,status,fencing_token,input_sha256,output_sha256,
                   error_key,started_at,finished_at,metadata_json)
                   values(?,?,?,?,1,?,'completed',1,?,?,null,?,?, '{}')""",
                (attempt_id, run_id, unit_id, role, worker_id,
                 "a" * 64, "b" * 64, "2026-07-14T00:00:00Z",
                 "2026-07-14T00:00:01Z"),
            )
            connection.execute(
                """insert into artifacts(run_id,artifact_id,unit_id,attempt_id,
                   worker_id,fencing_token,kind,repo_rel_path,content_sha256,
                   status,created_at,metadata_json)
                   values(?,?,?,?,?,1,'candidate-rust',?,?,'candidate',?, '{}')""",
                (run_id, artifact_id, unit_id, attempt_id, worker_id,
                 f"target/run/test/{unit_id}.rs", "c" * 64,
                 "2026-07-14T00:00:01Z"),
            )
            connection.execute(
                """update migration_units set status='resume-ready',
                   resumable_status='last_good',last_good_artifact_id=?
                   where run_id=? and unit_id=?""",
                (artifact_id, run_id, unit_id),
            )
        connection.commit()


def _artifact_path(plan: dict, name: str) -> str:
    return f"target/run/{plan['artifacts'][name]['path']}"


def _replace(argv: list[str], option: str, value: str) -> list[str]:
    result = list(argv)
    result[result.index(option) + 1] = value
    return result


if __name__ == "__main__":
    unittest.main()

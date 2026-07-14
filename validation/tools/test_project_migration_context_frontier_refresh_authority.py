from __future__ import annotations

import ast
from copy import deepcopy
from pathlib import Path, PurePosixPath
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from validation.tools._project_migration_harness import controller_dispatch
from validation.tools._project_migration_harness.artifacts import (
    canonical_json_bytes,
    content_sha256,
)
from validation.tools._project_migration_harness.context_frontier_cas import (
    write_frontier_cas_json,
)
from validation.tools._project_migration_harness.context_frontier_overlay import (
    build_context_frontier_overlay,
    resolve_effective_context,
    validate_context_frontier_overlay,
)
from validation.tools._project_migration_harness.ledger import ProjectLedger


HARNESS = Path(__file__).parent / "_project_migration_harness"
COMMAND_BASENAME = "ContextFrontierCommand"
HOST_COMMAND_OWNER = "ledger_context_frontier.py"


class ProjectMigrationContextFrontierRefreshAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="frontier-refresh-authority-")
        self.addCleanup(temporary.cleanup)
        self.harness_root = Path(temporary.name)

    def test_project_ledger_does_not_expose_raw_frontier_apply(self) -> None:
        offenders: list[str] = []
        for path, tree in _production_trees():
            for node in ast.walk(tree):
                if (
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == "apply_context_frontier"
                ):
                    offenders.append(f"{path.name}:{node.lineno}")

        self.assertFalse(
            hasattr(ProjectLedger, "apply_context_frontier"),
            "ProjectLedger must expose only the host refresh transaction",
        )
        self.assertEqual(
            [], offenders,
            "production code must not expose apply_context_frontier",
        )

    def test_low_level_frontier_command_is_private_and_host_owned(self) -> None:
        public_definitions: list[str] = []
        external_imports: list[str] = []
        external_constructors: list[str] = []
        exported_symbols: list[str] = []
        for path, tree in _production_trees():
            for node in ast.walk(tree):
                if (
                    isinstance(node, ast.ClassDef)
                    and _command_basename(node.name) == COMMAND_BASENAME
                    and not node.name.startswith("_")
                ):
                    public_definitions.append(f"{path.name}:{node.lineno}")
                if isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        if (
                            _command_basename(alias.name) == COMMAND_BASENAME
                            and path.name != HOST_COMMAND_OWNER
                        ):
                            external_imports.append(f"{path.name}:{node.lineno}")
                if isinstance(node, ast.Call):
                    name = _call_name(node.func)
                    if (
                        name is not None
                        and _command_basename(name) == COMMAND_BASENAME
                        and path.name != HOST_COMMAND_OWNER
                    ):
                        external_constructors.append(f"{path.name}:{node.lineno}")
            exported_symbols.extend(_command_exports(path, tree))

        self.assertEqual(
            [], public_definitions,
            "the low-level frontier command must be private",
        )
        self.assertEqual(
            [], external_imports,
            "only the host ledger commit adapter may import the low-level command",
        )
        self.assertEqual(
            [], external_constructors,
            "external production modules must not construct frontier commands",
        )
        self.assertEqual(
            [], exported_symbols,
            "the low-level frontier command must not be exported",
        )

    def test_ready_overlay_reference_binds_the_complete_content(self) -> None:
        assignment, context, overlay, reference, frontier = self.bound_overlay()

        self.assertEqual(
            context,
            resolve_effective_context(assignment, frontier, overlay),
        )

        changed = deepcopy(overlay)
        changed["effective_context"]["host_refresh_note"] = "changed"
        changed["context_sha256"] = content_sha256(changed["effective_context"])
        validate_context_frontier_overlay(changed)

        with self.assertRaisesRegex(ValueError, "reference identity drifted"):
            resolve_effective_context(assignment, frontier, changed)
        self.assertEqual(reference, frontier["context_overlay"])

    def test_overlay_drift_fails_before_materialization_lease_and_model(self) -> None:
        assignment, _context, overlay, reference, frontier = self.bound_overlay()
        changed = deepcopy(overlay)
        changed["effective_context"]["host_refresh_note"] = "tampered-on-disk"
        changed["context_sha256"] = content_sha256(changed["effective_context"])
        target = self.harness_root.joinpath(
            *PurePosixPath(reference["path"]).parts,
        )
        target.write_bytes(canonical_json_bytes(changed))

        schedule = {
            "status": "ready",
            "ready": [{
                "assignment": assignment,
                "context_frontier": frontier,
            }],
            "deferred": [],
            "schedule_sha256": _sha("schedule"),
        }
        ledger = Mock()
        ledger.require_portfolio_binding.return_value = {
            "plan_sha256": _sha("plan"),
            "dag_sha256": _sha("dag"),
        }
        ledger.recover_expired_attempts.return_value = []
        ledger.unit_states.return_value = []

        with (
            patch.object(controller_dispatch, "build_gate_facts", return_value={}),
            patch.object(controller_dispatch, "schedule_portfolio", return_value=schedule),
            patch.object(
                controller_dispatch, "materialize_scheduled_contexts",
            ) as materialize,
            patch.object(subprocess, "Popen") as model_process,
        ):
            with self.assertRaisesRegex(ValueError, "SHA-256 drifted"):
                controller_dispatch.dispatch_project_workers(
                    {"run_id": "refresh-authority-run"},
                    ledger=ledger,
                    harness_root=self.harness_root,
                    out_root=self.harness_root / "target/run",
                    out_root_rel="target/run",
                )

        materialize.assert_not_called()
        ledger.begin_worker_attempt.assert_not_called()
        model_process.assert_not_called()

    def bound_overlay(self) -> tuple[dict, dict, dict, dict, dict]:
        assignment = {
            "run_id": "refresh-authority-run",
            "unit_id": "unit-a",
            "group_id": "unit-a",
            "role": "translator",
            "worker_id": "worker-unit-a-translator",
            "immutable_input": {"source_sha256": _sha("source")},
        }
        outputs = {
            "selection_receipt_sha256": _sha("receipt"),
            "materialized_page_set_sha256": _sha("page-set"),
            "selection_materialization_sha256": _sha("materialization"),
        }
        catalog = _reference(
            "target/run/context/catalog-refreshed.json", "refreshed-catalog",
        )
        context = {
            "catalog": deepcopy(catalog),
            "retrieval": {"selection_status": "ready", **outputs},
            "pages": [{"page_id": "page-a", "sha256": _sha("page-a")}],
        }
        base = {
            "run_id": assignment["run_id"],
            "unit_id": assignment["unit_id"],
            "status": "pending_retrieval",
            "state_version": 3,
            "head_sha256": _sha("pending-head"),
            "query_epoch": 2,
            "catalog": _reference(
                "target/run/context/catalog-base.json", "base-catalog",
            ),
        }
        overlay = build_context_frontier_overlay(
            [assignment],
            base,
            plan_sha256=_sha("plan"),
            refresh_bundle=_reference(
                "target/run/context/refresh-input.json", "refresh-input",
            ),
            effective_context=context,
        )
        reference = write_frontier_cas_json(
            self.harness_root, "context-frontier-overlay", overlay,
        )
        frontier = {
            "status": "ready",
            "query_epoch": overlay["query_epoch"],
            "catalog": deepcopy(catalog),
            **outputs,
            "context_overlay": deepcopy(reference),
        }
        return assignment, context, overlay, reference, frontier


def _production_trees() -> list[tuple[Path, ast.Module]]:
    return [
        (path, ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))
        for path in sorted(HARNESS.glob("*.py"))
    ]


def _command_basename(value: str) -> str:
    return value.lstrip("_")


def _call_name(value: ast.expr) -> str | None:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        return value.attr
    return None


def _command_exports(path: Path, tree: ast.Module) -> list[str]:
    offenders: list[str] = []
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in targets
        ):
            continue
        value = node.value
        if not isinstance(value, (ast.List, ast.Tuple)):
            continue
        for item in value.elts:
            if (
                isinstance(item, ast.Constant)
                and isinstance(item.value, str)
                and _command_basename(item.value) == COMMAND_BASENAME
            ):
                offenders.append(f"{path.name}:{item.lineno}")
    return offenders


def _sha(label: str) -> str:
    return content_sha256({"label": label})


def _reference(path: str, label: str) -> dict:
    return {"path": path, "sha256": _sha(label), "size_bytes": len(label)}


if __name__ == "__main__":
    unittest.main()

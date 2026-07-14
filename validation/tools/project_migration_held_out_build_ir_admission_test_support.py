from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack
import json
from pathlib import Path, PurePosixPath
from unittest import mock
import uuid

from validation.tools._project_migration_harness import (
    build_ir_validation,
    orchestrator,
)


DOWNSTREAM_STAGES = (
    ("index_translation_units", "c_index"),
    ("build_migration_graph", "migration_graph"),
    ("build_context_pages", "context_pages"),
    ("build_context_portfolio", "context_portfolio"),
    ("ProjectLedger", "ledger"),
)


class HeldOutBuildIRAdmissionTestSupport:
    base: Path
    harness: Path

    def run_plan(
        self,
        source: Path,
        database: Path,
        *,
        identity: str,
        out_root: str,
        events: list[str],
        validator: mock.Mock,
    ) -> tuple[dict, dict[str, mock.Mock]]:
        stages: dict[str, mock.Mock] = {}
        with ExitStack() as stack:
            stack.enter_context(mock.patch.object(
                build_ir_validation, "verify_build_ir_artifact", validator,
            ))
            stack.enter_context(mock.patch.object(
                orchestrator, "verify_build_ir_artifact", validator,
            ))
            for attribute, label in DOWNSTREAM_STAGES:
                operation = getattr(orchestrator, attribute)
                stage = mock.Mock(
                    name=label,
                    side_effect=self.recording_call(events, label, operation),
                )
                stages[label] = stage
                stack.enter_context(mock.patch.object(orchestrator, attribute, stage))
            plan = orchestrator.plan_project(
                source,
                harness_root=self.harness,
                out_root=out_root,
                compile_database=database,
                run_id=f"heldout-{identity}",
                source_commit=(identity.encode("ascii").hex() + "0" * 40)[:40],
                max_concurrency=2,
            )
        return plan, stages

    def validator(
        self,
        events: list[str],
        *,
        drift_call: int | None = None,
        drift_path: Path | None = None,
    ) -> mock.Mock:
        canonical = build_ir_validation.verify_build_ir_artifact
        call_count = 0

        def verify(*args: object, **kwargs: object) -> dict:
            nonlocal call_count
            call_count += 1
            events.append(f"build_ir_validation[{call_count}]")
            if call_count == drift_call:
                if drift_path is None:
                    raise AssertionError("drift_path is required")
                drift_path.write_text(
                    drift_path.read_text(encoding="utf-8")
                    + f"/* admission-drift-{uuid.uuid4().hex} */\n",
                    encoding="utf-8",
                )
            return canonical(*args, **kwargs)

        return mock.Mock(name="canonical_build_ir_validator", side_effect=verify)

    @staticmethod
    def recording_call(
        events: list[str], label: str, operation: Callable[..., object],
    ) -> Callable[..., object]:
        def call(*args: object, **kwargs: object) -> object:
            events.append(label)
            return operation(*args, **kwargs)

        return call

    def assert_no_downstream_effects(
        self,
        plan: dict,
        stages: dict[str, mock.Mock],
        out_root: str,
    ) -> None:
        for stage in stages.values():
            stage.assert_not_called()
        for artifact in ("c_index", "migration_graph", "context_pages"):
            self.assertNotIn(artifact, plan["artifacts"])
        self.assert_no_dag_ledger_or_model(plan, out_root)

    def assert_no_dag_ledger_or_model(
        self,
        plan: dict,
        out_root: str,
    ) -> None:
        for artifact in (
            "context_materialization", "portfolio_dag", "portfolio",
            "integration_manifest", "initial_schedule",
        ):
            self.assertNotIn(artifact, plan["artifacts"])
        self.assertNotIn("ledger", plan)
        output = self.output(out_root)
        self.assertFalse((output / "plan/portfolio-dag.json").exists())
        self.assertFalse((output / "plan/portfolio.json").exists())
        self.assertFalse((output / "state/project-migration.sqlite3").exists())
        self.assertFalse((output / "harness/assignments").exists())
        self.assert_nonsemantic_plan(plan)

    def assert_nonsemantic_plan(self, plan: dict) -> None:
        self.assertFalse(plan["execution"]["model_launched"])
        self.assertFalse(plan["claim_boundary"]["semantic_gate"])
        self.assertEqual(
            0, plan["claim_boundary"]["translation_coverage_numerator"],
        )

    def write_project(self, ordinal: int) -> tuple[Path, Path, str, Path]:
        identity = f"case-{ordinal}-{uuid.uuid4().hex[:12]}"
        symbol = f"entry_{uuid.uuid4().hex[:12]}"
        target = f"program_{uuid.uuid4().hex[:12]}"
        root = self.base / f"repo-{uuid.uuid4().hex}"
        source_rel = f"src/unit_{uuid.uuid4().hex[:12]}.c"
        object_rel = f"build/{uuid.uuid4().hex[:12]}.o"
        binary_rel = f"build/{target}.bin"
        root.mkdir()
        self.write(root, "CMakeLists.txt", f"add_executable({target} {source_rel})\n")
        source_file = self.write(
            root,
            source_rel,
            "#include \"config.h\"\n"
            f"static int helper_{ordinal}(void) {{ return VALUE + {ordinal}; }}\n"
            f"int {symbol}(void) {{ return helper_{ordinal}(); }}\n",
        )
        self.write(root, "build/generated/config.h", "#define VALUE 7\n")
        self.write(root, object_rel, b"object-v1")
        self.write(root, binary_rel, b"program-v1")
        self.write(
            root,
            f"build/CMakeFiles/{target}.dir/link.txt",
            f"clang {Path(object_rel).name} -o {Path(binary_rel).name} -lm\n",
        )
        database = self.write(
            root,
            "build/compile_commands.json",
            json.dumps([{
                "directory": str(root),
                "file": source_rel,
                "arguments": [
                    "clang", "-std=c11", "-DVALUE=7", "-Ibuild/generated",
                    "-c", source_rel, "-o", object_rel,
                ],
                "output": object_rel,
            }]),
        )
        return root, database, identity, source_file

    @staticmethod
    def write(root: Path, relative: str, value: str | bytes) -> Path:
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(value, bytes):
            path.write_bytes(value)
        else:
            path.write_text(value, encoding="utf-8")
        return path

    def read_artifact(self, out_root: str, reference: dict) -> dict:
        relative = Path(*PurePosixPath(reference["path"]).parts)
        return json.loads(
            (self.output(out_root) / relative).read_text(encoding="utf-8")
        )

    def output(self, out_root: str) -> Path:
        return self.harness / Path(*PurePosixPath(out_root).parts)


__all__ = ["HeldOutBuildIRAdmissionTestSupport"]

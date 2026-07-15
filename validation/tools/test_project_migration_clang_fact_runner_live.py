from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import unittest

from validation.tools._project_migration_harness.clang_fact_commands import (
    build_clang_fact_plans,
)
from validation.tools._project_migration_harness.clang_fact_runner_derived import (
    read_clang_derived_evidence,
)
from validation.tools._project_migration_harness.clang_fact_runner_paths import (
    load_clang_host_bindings,
)
from validation.tools._project_migration_harness.clang_toolchain_binding import (
    persist_clang_toolchain_binding,
)
from validation.tools._project_migration_harness.clang_raw_output_evidence import (
    read_clang_raw_outputs,
)
from validation.tools._project_migration_harness.host_tool_binding import (
    competition_profile_binding,
)
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract,
)
from validation.tools._project_migration_harness.sandbox_bubblewrap_argv import (
    build_bubblewrap_argv,
    resource_limiter,
)
from validation.tools._project_migration_harness.sandbox_environment import (
    canonical_environment_items,
    cargo_guest_environment,
)
from validation.tools._project_migration_harness.sandbox_linux_probe import (
    bubblewrap_version,
    run_bubblewrap_probe,
)
from validation.tools._project_migration_harness.sandbox_toolchain import (
    file_sha256,
)
from validation.tools._project_migration_harness import clang_fact_runner
from validation.tools.project_migration_clang_fact_runner_test_support import (
    ClangFactRunnerTestCase,
)


LIVE = os.environ.get("C2R_RUN_LIVE_TOOLCHAIN_TESTS") == "1"


@unittest.skipUnless(LIVE and os.name == "posix", "explicit Linux live gate")
class ProjectMigrationLiveClangFactRunnerTests(ClangFactRunnerTestCase):
    def test_real_bubblewrap_ast_then_layout_reopens(self) -> None:
        missing = [name for name in ("bwrap", "clang") if shutil.which(name) is None]
        self.assertEqual([], missing, f"missing competition tools: {missing}")
        launcher = Path(shutil.which("bwrap") or "").resolve(strict=True)
        receipt = persist_clang_toolchain_binding(
            self.out_root,
            profile="competition",
            profile_binding=competition_profile_binding(),
        )
        portable = receipt["portable_binding"]
        contract = SandboxContract(
            backend="bubblewrap-v1",
            launcher_sha256=file_sha256(launcher),
            toolchain_sha256=portable["binding_sha256"],
        )
        probe = _live_probe(
            launcher=launcher,
            contract=contract,
            project_root=self.project_root,
            ledger_path=self.ledger,
            toolchain_receipt=receipt,
        )
        plans = build_clang_fact_plans(self.build_ir, portable)
        ast_plan = _plan(plans, "clang-ast")
        layout_plan = _plan(plans, "clang-record-layout")
        common = {
            "ledger_path": self.ledger,
            "out_root_rel": "target/run",
            "c_repo_root": self.project_root,
            "runtime_parent": self.runtime_parent,
            "bubblewrap_launcher": launcher,
            "sandbox_contract": contract,
            "sandbox_probe": probe,
            "build_ir": self.build_ir,
            "toolchain_receipt": receipt,
        }

        ast_receipt = clang_fact_runner.run_clang_fact_plan(
            **common, plan=ast_plan,
        )
        layout_receipt = clang_fact_runner.run_clang_fact_plan(
            **common, plan=layout_plan, ast_plan=ast_plan,
            ast_receipt=ast_receipt,
        )

        self.assertEqual("facts-ready", ast_receipt["status"], ast_receipt)
        derived = read_clang_derived_evidence(
            self.ledger,
            layout_receipt["derived_evidence"],
            plan_sha256=layout_plan["plan_sha256"],
        )
        raw = read_clang_raw_outputs(
            self.ledger,
            layout_receipt["raw_outputs"],
            gate_kind="clang-record-layout",
            plan_sha256=layout_plan["plan_sha256"],
            unit_id=layout_plan["unit_id"],
        )
        self.assertEqual(
            "facts-ready", layout_receipt["status"],
            {
                "receipt": layout_receipt,
                "derived": derived,
                "stdout": raw["stdout"].decode("utf-8", errors="replace"),
            },
        )
        self.assertEqual(["Packet"], [item["name"] for item in derived["records"]])
        self.assertEqual(
            layout_receipt,
            clang_fact_runner.reopen_clang_fact_run_receipt(
                value=layout_receipt,
                ledger_path=self.ledger,
                c_repo_root=self.project_root,
                plan=layout_plan,
                build_ir=self.build_ir,
                toolchain_receipt=receipt,
                sandbox_contract=contract,
                sandbox_probe=probe,
                ast_plan=ast_plan,
                ast_receipt=ast_receipt,
            ),
        )
        self.assertEqual([], list(self.runtime_parent.iterdir()))


def _plan(plans: list[dict], gate: str) -> dict:
    return next(
        item for item in plans
        if item["unit_id"] == "unit-a" and item["gate"] == gate
    )


def _live_probe(
    *, launcher: Path, contract: SandboxContract, project_root: Path,
    ledger_path: Path, toolchain_receipt: dict,
) -> object:
    host = load_clang_host_bindings(ledger_path, toolchain_receipt)
    clang_binary = next(
        path for path, guest in host.tool_bindings
        if guest == "/toolchain/bin/clang"
    )
    probe_bindings = (*host.tool_bindings, (clang_binary, "/toolchain/bin/cargo"))
    environment = canonical_environment_items(cargo_guest_environment())
    return run_bubblewrap_probe(
        contract=contract,
        backend_version=bubblewrap_version(launcher),
        project_root=project_root,
        argv_builder=lambda runtime, command: build_bubblewrap_argv(
            launcher=launcher,
            workspace=project_root,
            runtime=runtime,
            tool_bindings=probe_bindings,
            environment=environment,
            guest_command=tuple(command),
        ),
        executor=subprocess.run,
        preexec_fn=resource_limiter(contract),
    )


if __name__ == "__main__":
    unittest.main()

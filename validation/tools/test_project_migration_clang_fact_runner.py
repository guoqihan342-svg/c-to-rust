from __future__ import annotations

import copy
import json
from unittest import mock

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.build_ir import finalize_build_ir
from validation.tools._project_migration_harness.clang_fact_commands import (
    build_clang_fact_plans,
)
from validation.tools._project_migration_harness.clang_fact_runner_derived import (
    read_clang_derived_evidence,
)
from validation.tools._project_migration_harness.ledger_security import LedgerError
from validation.tools._project_migration_harness import clang_fact_runner as subject
from validation.tools._project_migration_harness import (
    clang_fact_runner_process as process_subject,
)
from validation.tools.project_migration_clang_fact_runner_test_support import (
    ClangFactRunnerTestCase, ast_bytes, invocation, layout_bytes, triples,
)


class ProjectMigrationClangFactRunnerTests(ClangFactRunnerTestCase):
    def test_process_command_allows_fixed_empty_environment_value(self) -> None:
        argv = ["/usr/bin/bwrap", "--setenv", "CARGO_ENCODED_RUSTFLAGS", ""]
        self.assertEqual(argv, process_subject._command(argv))
        for invalid in ([], ["/usr/bin/not-bwrap"], ["/usr/bin/bwrap", None]):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                process_subject._command(invalid)

    def test_ast_then_layout_is_shell_free_and_ast_selected(self) -> None:
        ast_plan = self.plan("unit-a", "clang-ast")
        layout_plan = self.plan("unit-a", "clang-record-layout")
        invocations = iter([invocation(ast_bytes()), invocation(layout_bytes())])
        def execute(*args, **kwargs):
            return next(invocations)(*args, **kwargs)
        with self.host_patches(), mock.patch.object(
            subject, "run_bounded_bubblewrap", side_effect=execute,
        ) as process:
            ast_receipt = subject.run_clang_fact_plan(**self.kwargs(ast_plan))
            layout_receipt = subject.run_clang_fact_plan(
                **self.kwargs(layout_plan), ast_plan=ast_plan,
                ast_receipt=ast_receipt,
            )

        self.assertEqual("facts-ready", ast_receipt["status"])
        self.assertEqual("facts-ready", layout_receipt["status"])
        derived = read_clang_derived_evidence(
            self.ledger, layout_receipt["derived_evidence"],
            plan_sha256=layout_plan["plan_sha256"],
        )
        self.assertEqual(["Packet"], [item["name"] for item in derived["records"]])
        self.assertEqual("ast-selected-record-layout", layout_receipt["derivation"]["kind"])
        self.assertEqual(ast_receipt["receipt_sha256"],
                         layout_receipt["derivation"]["ast_receipt_sha256"])
        for call in process.call_args_list:
            argv = call.args[0]
            self.assertNotIn("/bin/sh", argv)
            self.assertIn("/toolchain/bin/clang", argv)
            self.assertIn([
                "--ro-bind", str(self.project_root.resolve(strict=True)), "/workspace",
            ], triples(argv))
            self.assertTrue(any(
                item[0] == "--bind" and item[2] == "/runtime"
                for item in triples(argv)
            ))
        self.assertNotIn(str(self.root), json.dumps(layout_receipt, sort_keys=True))

    def test_started_failure_modes_keep_raw_and_do_not_publish_derived(self) -> None:
        plan = self.plan("unit-a", "clang-ast")
        cases = {
            "nonzero": (invocation(b"diagnostic", returncode=1), "clang_nonzero_exit"),
            "timeout": (invocation(b"partial", returncode=-9, timed_out=True),
                        "clang_execution_timeout"),
            "flood": (invocation(b"partial", returncode=-9, flooded=True),
                      "clang_output_limit_exceeded"),
            "parser": (invocation(b"not-json"), "clang_fact_parse_failed"),
        }
        for name, (process_result, reason) in cases.items():
            with self.subTest(name=name), self.host_patches(), mock.patch.object(
                subject, "run_bounded_bubblewrap", side_effect=process_result,
            ):
                receipt = subject.run_clang_fact_plan(**self.kwargs(plan))
            self.assertEqual(reason, receipt["reason_code"])
            self.assertIsNotNone(receipt["raw_outputs"])
            self.assertIsNone(receipt["derived_evidence"])

        with self.host_patches(), mock.patch.object(
            subject, "run_bounded_bubblewrap", side_effect=invocation(ast_bytes()),
        ), mock.patch.object(subject, "cleanup_runtime", return_value=False):
            receipt = subject.run_clang_fact_plan(**self.kwargs(plan))
        self.assertEqual("clang_runtime_cleanup_failed", receipt["reason_code"])
        self.assertIsNotNone(receipt["raw_outputs"])
        self.assertIsNone(receipt["derived_evidence"])

    def test_started_failure_receipts_reopen_from_raw_without_fact_derivation(self) -> None:
        plan = self.plan("unit-a", "clang-ast")
        for name, process_result in (
            ("nonzero", invocation(b"diagnostic", returncode=1)),
            ("timeout", invocation(b"partial", returncode=-9, timed_out=True)),
            ("flood", invocation(b"partial", returncode=-9, flooded=True)),
        ):
            with self.subTest(name=name), self.host_patches(), mock.patch.object(
                subject, "run_bounded_bubblewrap", side_effect=process_result,
            ):
                receipt = subject.run_clang_fact_plan(**self.kwargs(plan))
                self.assertEqual(
                    receipt,
                    subject.reopen_clang_fact_run_receipt(
                        value=receipt, **self.reopen_kwargs(plan),
                    ),
                )

        with self.host_patches(verify=False), mock.patch.object(
            subject, "run_bounded_bubblewrap", side_effect=invocation(ast_bytes()),
        ), mock.patch.object(
            subject, "verify_clang_host_binding_current",
            side_effect=LedgerError("drifted"),
        ):
            receipt = subject.run_clang_fact_plan(**self.kwargs(plan))
        with self.host_patches():
            reopened = subject.reopen_clang_fact_run_receipt(
                value=receipt, **self.reopen_kwargs(plan),
            )
        self.assertEqual("clang_toolchain_drifted", reopened["reason_code"])

    def test_raw_cas_failure_stops_before_parser(self) -> None:
        plan = self.plan("unit-a", "clang-ast")
        with self.host_patches(), mock.patch.object(
            subject, "run_bounded_bubblewrap", side_effect=invocation(ast_bytes()),
        ), mock.patch.object(
            subject, "write_clang_raw_outputs", side_effect=LedgerError("raw failed"),
        ), mock.patch.object(subject, "derive_clang_fact_evidence") as parser:
            with self.assertRaisesRegex(LedgerError, "raw failed"):
                subject.run_clang_fact_plan(**self.kwargs(plan))
        parser.assert_not_called()

    def test_plan_and_unit_exchange_are_rejected(self) -> None:
        first = self.plan("unit-a", "clang-ast")
        second = self.plan("unit-b", "clang-ast")
        with self.host_patches(), mock.patch.object(
            subject, "run_bounded_bubblewrap", side_effect=invocation(ast_bytes()),
        ):
            receipt = subject.run_clang_fact_plan(**self.kwargs(first))
        with self.assertRaises(ValueError):
            subject.validate_clang_fact_run_receipt(
                receipt, plan=second, build_ir=self.build_ir,
                toolchain_receipt=self.toolchain_receipt,
                sandbox_contract=self.contract, sandbox_probe=self.probe,
            )
        changed = copy.deepcopy(first)
        changed["argv"], changed["argv_sha256"] = second["argv"], second["argv_sha256"]
        changed["plan_sha256"] = content_sha256({
            key: value for key, value in changed.items() if key != "plan_sha256"
        })
        with self.host_patches(), mock.patch.object(
            subject, "run_bounded_bubblewrap",
        ) as process, self.assertRaises(ValueError):
            subject.run_clang_fact_plan(**self.kwargs(changed))
        process.assert_not_called()

    def test_post_start_toolchain_drift_keeps_raw_and_blocks(self) -> None:
        plan = self.plan("unit-a", "clang-ast")
        with self.host_patches(verify=False), mock.patch.object(
            subject, "run_bounded_bubblewrap", side_effect=invocation(ast_bytes()),
        ), mock.patch.object(
            subject, "verify_clang_host_binding_current",
            side_effect=LedgerError("drifted"),
        ):
            receipt = subject.run_clang_fact_plan(**self.kwargs(plan))
        self.assertEqual("clang_toolchain_drifted", receipt["reason_code"])
        self.assertIsNotNone(receipt["raw_outputs"])
        self.assertIsNone(receipt["derived_evidence"])

    def test_unbound_system_includes_run_but_never_claim_closure(self) -> None:
        changed = copy.deepcopy(self.build_ir)
        for unit in changed["translation_units"]:
            unit["compile_arguments"]["semantic_flags"].remove("-nostdinc")
        changed = finalize_build_ir(changed)
        plan = build_clang_fact_plans(
            changed, self.toolchain_receipt["portable_binding"],
        )[0]
        with self.host_patches(), mock.patch.object(
            subject, "run_bounded_bubblewrap", side_effect=invocation(ast_bytes()),
        ) as process:
            receipt = subject.run_clang_fact_plan(
                **self.kwargs(plan, build_ir=changed),
            )
        process.assert_called_once()
        boundary = receipt["toolchain"]["proof_boundary"]
        self.assertFalse(boundary["system_include_closure"])
        self.assertEqual("host-read-only-unbound", boundary["system_include_source"])
        self.assertFalse(receipt["section_closure"])


if __name__ == "__main__":
    import unittest
    unittest.main()

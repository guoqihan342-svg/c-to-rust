from __future__ import annotations

import copy
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from validation.tools import auto_migrate
from validation.tools._translation_carrier_reporter.call_continue_negative_execution import (
    run_call_continue_negative_execution,
)
from validation.tools._translation_carrier_reporter.contract import (
    ReporterError,
    behavior_fields,
    parse_contract,
    validate_cases,
)
from validation.tools._translation_carrier_reporter.call_continue_model import reference_outputs
from validation.tools._translation_carrier_reporter.state_replay_kinds import (
    is_state_replay_kind,
)
from validation.tools.call_continue_syntax import validate_rust_call_continue_draft
from validation.tools.call_continue_test_support import (
    REPO_ROOT,
    renamed_rust_draft,
    renamed_target_only_rust_draft,
    renamed_spec,
    replay_source,
)


class CallContinueHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec, self.cases = renamed_spec()

    def test_renamed_contract_auto_generators_and_syntax(self) -> None:
        contract = parse_contract(self.spec)
        self.assertFalse(is_state_replay_kind(contract))
        self.assertEqual(len(validate_cases(self.cases, contract)), 4)
        fixture = auto_migrate.oracle_fixture_binding(self.spec)
        self.assertTrue(auto_migrate.call_continue_state_replay_supported(self.spec, fixture))
        oracle = auto_migrate.oracle_fixture_execution_source(self.spec, fixture)
        self.assertIn("advance_window", oracle["statements"])
        self.assertIn("c2r_call_snapshot_2", oracle["statements"])
        for case in self.cases:
            for field in behavior_fields(contract):
                self.assertIn(
                    f"fixture case {case['id']} {field} matched",
                    oracle["statements"],
                )
        replay = auto_migrate.rust_replay_fixture_cases_source(self.spec, fixture)
        self.assertIn("advance_window(&mut actual_hit_plain_source", replay)
        self.assertIn("__c2r_scripted_external_call_args()", replay)
        safety = validate_rust_call_continue_draft(renamed_rust_draft(), contract)
        self.assertEqual(safety["argument_modes"], [
            "entry_root", "entry_local_copy", "owner_interior_alias"
        ])
        self.assertEqual(safety["pointer_root_count"], 2)
        self.assertEqual(safety["external_call_count"], 1)
        external = auto_migrate.external_direct_callee_context(self.spec, [])
        external["declared"] = external["declarations"]
        with tempfile.TemporaryDirectory(prefix="call-replay-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            draft = root / "draft.rs"
            draft.write_text(renamed_target_only_rust_draft(), encoding="utf-8", newline="\n")
            auto_migrate.inject_external_callee_stubs(draft, external, self.spec)
            combined = root / "combined.rs"
            combined.write_text(
                draft.read_text(encoding="utf-8")
                + "\n#[test]\nfn generated_replay() {\n"
                + replay
                + "}\n",
                encoding="utf-8",
                newline="\n",
            )
            executable = root / "replay.exe"
            rustc = shutil.which("rustc")
            self.assertIsNotNone(rustc)
            compiled = subprocess.run(
                [rustc, "--edition=2021", "--test", str(combined), "-o", str(executable)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run([str(executable)], capture_output=True, text=True, check=False)
            self.assertEqual(executed.returncode, 0, executed.stderr)

    def test_ordered_noalias_argument_and_shape_drift_fail_closed(self) -> None:
        mutations = (
            ("reversed-noalias", lambda spec: spec["replay_contract"].update(noalias_required=[["owner", "source"]]), "ordered db-to-owner"),
            ("boundary-noalias", lambda spec: spec["c_boundary"]["pointer_contract"].update(noalias_required=[["owner", "source"]]), "ordered db-to-owner"),
            ("alias-root", lambda spec: spec["replay_contract"]["external_callee"]["arguments"][2].update(entry_parameter="cursor"), "ordered argument binding"),
            ("mode-order", lambda spec: spec["replay_contract"]["external_callee"]["arguments"][1].update(mode="entry_root"), "ordered argument binding"),
            ("local-root", lambda spec: spec["replay_contract"]["entry_arguments"][1].update(pass_mode="mutable_ref"), "order or modes"),
            ("shape", lambda spec: spec["replay_contract"]["comparison"].update(extra=True), "comparison must"),
        )
        for label, mutate, message in mutations:
            bad = copy.deepcopy(self.spec)
            mutate(bad)
            with self.subTest(label=label), self.assertRaisesRegex(ReporterError, message):
                parse_contract(bad)

    def test_fixture_and_rust_shape_drift_fail_closed(self) -> None:
        contract = parse_contract(self.spec)
        missing_partition = copy.deepcopy(self.cases)
        missing_partition[-1]["inputs"]["scripted_return"] = 0
        missing_partition[-1]["expected_outputs"] = reference_outputs(
            missing_partition[-1], contract
        )
        with self.assertRaisesRegex(ReporterError, "zero miss, and nonzero miss"):
            validate_cases(missing_partition, contract)
        drafts = (
            ("comparison", renamed_rust_draft().replace(" == 2779096485u32", " != 2779096485u32"), "exact sentinel comparison"),
            ("continue", renamed_rust_draft().replace("continue;", "/*noop*/;"), "current-level continue"),
            ("alias", renamed_rust_draft().replace("cursor.meta.phase = 0u32;", "owner.active.meta.phase = 0u32;"), "hit alias reset"),
            ("call-order", renamed_rust_draft().replace("source, &mut window, cursor", "source, cursor, &mut window"), "external call assignment"),
        )
        for label, draft, message in drafts:
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, message):
                validate_rust_call_continue_draft(draft, contract)

    def test_actual_two_scenario_negative_execution_partitions(self) -> None:
        contract = parse_contract(self.spec)
        context = SimpleNamespace(
            repo_root=REPO_ROOT,
            spec={"slice_id": "renamed-call-continue", "function_name": "advance_window"},
            contract=contract,
            cases=self.cases,
        )
        with tempfile.TemporaryDirectory(prefix="call-continue-", dir=REPO_ROOT / "target") as tmp:
            root = Path(tmp)
            draft = root / "draft.rs"
            replay = root / "replay.rs"
            draft.write_text(renamed_rust_draft(), encoding="utf-8", newline="\n")
            replay.write_text(replay_source(self.cases), encoding="utf-8", newline="\n")
            result = run_call_continue_negative_execution(
                context, draft, replay, root / "out"
            )
        scenarios = {item["scenario_id"]: item for item in result["scenarios"]}
        self.assertEqual(len(scenarios["comparison-equality-flip"]["partition_replay"]["detected_case_ids"]), 4)
        self.assertEqual(scenarios["continue-noop"]["partition_replay"]["detected_case_ids"], ["hit-plain", "hit-wrap"])
        self.assertEqual(scenarios["continue-noop"]["partition_replay"]["passed_case_ids"], ["miss-zero", "miss-nonzero"])


if __name__ == "__main__":
    unittest.main()

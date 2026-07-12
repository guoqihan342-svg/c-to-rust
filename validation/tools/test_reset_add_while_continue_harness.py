from __future__ import annotations

import copy
from pathlib import Path
import re
import unittest
from types import SimpleNamespace

from validation.tools import auto_migrate
from validation.tools._translation_carrier_reporter.contract import (
    ReporterError,
    parse_contract,
    validate_cases,
)
from validation.tools._translation_carrier_reporter.reset_add_while_continue_reports import (
    evidence_identity,
)
from validation.tools._translation_carrier_reporter.state_replay_negative import mutation_spec
from validation.tools.reset_add_while_continue_syntax import (
    validate_rust_reset_add_while_continue_draft,
)
from validation.tools.replay_call_plan import (
    build_replay_call_plan,
    render_declarative_replay_cases,
)


class ResetAddWhileContinueHarnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec, self.cases = renamed_spec()

    def test_renamed_contract_oracle_replay_and_identity(self) -> None:
        fixture = auto_migrate.oracle_fixture_binding(self.spec)
        contract = auto_migrate.record_interior_projection_u32_reset_add_while_continue_state_replay_contract(
            self.spec, fixture
        )
        self.assertIsNotNone(contract)
        reporter_contract = parse_contract(self.spec)
        self.assertEqual([case["id"] for case in validate_cases(self.cases, reporter_contract)], ["plain", "wrap"])

        oracle = auto_migrate.oracle_fixture_execution_source(self.spec, fixture)
        self.assertIn("actual_plain_owner.current.meta.phase", oracle["statements"])
        self.assertIn("actual_plain_owner.total", oracle["statements"])
        plan = build_replay_call_plan(self.spec, Path.cwd())
        replay = render_declarative_replay_cases(self.spec, plan, Path.cwd())
        self.assertIn(
            "advance_window(&actual_plain_0_source, &mut actual_plain_0_owner)", replay
        )
        self.assertIn("actual_plain_0_owner.current.meta.phase", replay)
        self.assertIn("actual_plain_0_owner.total", replay)

        safety = validate_rust_reset_add_while_continue_draft(renamed_rust(), reporter_contract)
        self.assertEqual(safety["projection_mode"], "safe_mutable_reference")
        self.assertEqual(safety["continue_count"], 1)
        self.assertEqual(safety["unsafe_count"], 0)
        self.assertEqual(safety["raw_pointer_count"], 0)
        generated_shape = renamed_rust().replace(
            "let mut once = true;\n    while once {",
            "let mut once: bool = true;\n    while once != false {",
        )
        self.assertEqual(
            validate_rust_reset_add_while_continue_draft(
                generated_shape, reporter_contract
            )["status"],
            "passed",
        )

        pattern, before, after = mutation_spec(reporter_contract)
        self.assertEqual(before, b"continue;")
        self.assertEqual(after, b"/*noop*/;")
        self.assertEqual(len(before), len(after))
        self.assertEqual(len(pattern.findall(renamed_rust().encode())), 1)

        context = SimpleNamespace(
            spec={
                "target_id": "orbit-store",
                "slice_id": "advance-window",
                "source_commit": "renamed-source",
                "translation_carrier": {
                    "carrier_source_sha256": "1" * 64,
                    "real_source": {
                        "fragment": {
                            "sha256": "8" * 64,
                            "line_start": 17,
                            "line_end": 23,
                        }
                    },
                },
            },
            contract=reporter_contract,
            refs={
                "slice_spec": {"sha256": "2" * 64},
                "fixture": {"sha256": "3" * 64},
                "real_source": {
                    "sha256": "4" * 64,
                    "source_fragment_sha256": "8" * 64,
                },
            },
        )
        runtime = {"refs": {
            "c_oracle_harness": {"sha256": "5" * 64},
            "generated_rust_draft": {"sha256": "6" * 64},
            "generated_replay_test": {"sha256": "7" * 64},
        }}
        identity = evidence_identity(context, runtime)
        self.assertTrue(identity["recomputed"])
        self.assertRegex(identity["identity_sha256"], re.compile(r"^[0-9a-f]{64}$"))
        self.assertEqual(identity["bindings"]["source_fragment_sha256"], "8" * 64)
        self.assertEqual(identity["bindings"]["source_fragment_line_start"], 17)
        self.assertEqual(identity["bindings"]["source_fragment_line_end"], 23)

        for label, fragment_update, message in (
            ("sha-shape", {"sha256": "not-a-sha"}, "sha256 drifted"),
            ("sha-binding", {"sha256": "9" * 64}, "sha256 drifted"),
            ("line-type", {"line_start": True}, "line range drifted"),
            ("line-order", {"line_start": 24}, "line range drifted"),
        ):
            bad_context = copy.deepcopy(context)
            bad_context.spec["translation_carrier"]["real_source"]["fragment"].update(
                fragment_update
            )
            with self.subTest(label=label), self.assertRaisesRegex(ReporterError, message):
                evidence_identity(bad_context, runtime)

    def test_contract_and_generated_rust_drift_fail_closed(self) -> None:
        noalias = copy.deepcopy(self.spec)
        noalias["replay_contract"]["noalias_required"] = [["source", "cursor"]]
        with self.assertRaisesRegex(ReporterError, "exact source-owner pair"):
            parse_contract(noalias)

        control = copy.deepcopy(self.spec)
        control["replay_contract"]["control_flow"]["continue_target"] = "nested_while"
        with self.assertRaisesRegex(ReporterError, "control_flow semantics"):
            parse_contract(control)

        contract = parse_contract(self.spec)
        for label, draft, message in (
            ("direct-reset", renamed_rust().replace("cursor.meta.phase = 0u32;", "owner.current.meta.phase = 0u32;"), "projected alias reset"),
            ("raw", renamed_rust().replace("let cursor: &mut Node", "let cursor: *mut Node"), "raw_pointer"),
            ("add", renamed_rust().replace("wrapping_add", "wrapping_sub"), "owner wrapping_add"),
            ("continue", renamed_rust().replace("continue;", "/*noop*/;"), "current while continue"),
        ):
            with self.subTest(label=label), self.assertRaisesRegex(ValueError, message):
                validate_rust_reset_add_while_continue_draft(draft, contract)


def renamed_spec() -> tuple[dict[str, object], list[dict[str, object]]]:
    cases = [
        {"id": "plain", "inputs": {"source_step": 9, "phase_initial": 4, "total_initial": 11},
         "expected_outputs": {"did_advance": True, "phase_after": 0, "total_after": 20}},
        {"id": "wrap", "inputs": {"source_step": 5, "phase_initial": 0xFFFFFFFF, "total_initial": 0xFFFFFFFE},
         "expected_outputs": {"did_advance": True, "phase_after": 0, "total_after": 3}},
    ]
    source_init = {"record_type": "Metrics", "fields": [
        {"name": "step", "fixture_field": "source_step", "rust_type": "u32"}
    ]}
    owner_init = {"record_type": "Owner", "fields": [
        {"name": "current", "record": {"record_type": "Node", "fields": [
            {"name": "meta", "record": {"record_type": "Meta", "fields": [
                {"name": "phase", "fixture_field": "phase_initial", "rust_type": "u32"}
            ]}}
        ]}},
        {"name": "total", "fixture_field": "total_initial", "rust_type": "u32"},
    ]}
    contract = {
        "schema_version": 1, "kind": "record_interior_projection_u32_reset_add_while_continue_state",
        "entry_arguments": [
            {"parameter": "source", "c_type": "const struct Metrics *", "rust_type": "Metrics", "pass_mode": "mutable_ref", "direction": "input", "initializer": source_init},
            {"parameter": "owner", "c_type": "struct Owner *", "rust_type": "Owner", "pass_mode": "mutable_ref", "direction": "inout", "initializer": owner_init},
        ],
        "owner_parameter": "owner",
        "projection": {"path": ["current"], "alias_local": "cursor", "alias_c_pointer_type": "NodePtr", "alias_rust_type": "Node"},
        "reset_state": {"alias_field_path": ["meta", "phase"], "owner_field_path": ["current", "meta", "phase"], "fixture_field": "phase_after", "rust_type": "u32", "value": 0},
        "add_state": {"owner_field_path": ["total"], "fixture_field": "total_after", "rust_type": "u32", "operation": "wrapping_add", "rhs": {"mode": "direct_record_u32_field", "parameter": "source", "field_path": ["step"], "source_expression": "source_step(source)"}},
        "control_flow": {"kind": "single_iteration_while_continue", "sentinel_local": "once", "initial_value": True, "body_first_assignment": False, "continue_target": "current_while", "unreachable_return": False, "terminal_return": True},
        "return": {"fixture_field": "did_advance", "rust_type": "bool", "value": True},
        "noalias_required": [["source", "owner"]],
    }
    c_source = """#define source_step(source) ((source)->step)
struct Metrics { uint32_t step; };
struct Meta { uint32_t phase; };
struct Node { struct Meta meta; };
typedef struct Node *NodePtr;
struct Owner { struct Node current; uint32_t total; };
static bool advance_window(const struct Metrics *source, struct Owner *owner)
{
    NodePtr cursor = &(owner->current);
    bool once = true;
    while (once) {
        once = false;
        cursor->meta.phase = 0;
        owner->total += source_step(source);
        continue;
        return false;
    }
    return true;
}
"""
    return {
        "function_name": "advance_window", "c_source": c_source,
        "fixture_contract": {"cases": cases, "behavior_fields": ["did_advance", "phase_after", "total_after"], "observable_outputs": ["did_advance", "phase_after", "total_after"]},
        "replay_contract": contract,
        "c_boundary": {"signatures": [{"function": "advance_window", "return_type": "bool", "parameters": [
            {"name": "source", "c_type": "const struct Metrics *", "direction": "input"},
            {"name": "owner", "c_type": "struct Owner *", "direction": "inout"},
        ]}], "pointer_contract": {"aliasing_proven": True, "noalias_required": [["source", "owner"]]}},
        "rust_boundary": {"public_api": [{"name": "advance_window"}]},
    }, cases


def renamed_rust() -> str:
    return """pub struct Metrics { pub step: u32 }
pub struct Meta { pub phase: u32 }
pub struct Node { pub meta: Meta }
pub struct Owner { pub current: Node, pub total: u32 }
pub fn advance_window(source: &Metrics, owner: &mut Owner) -> bool {
    let cursor: &mut Node = &mut owner.current;
    let mut once = true;
    while once {
        once = false;
        cursor.meta.phase = 0u32;
        owner.total = owner.total.wrapping_add(source.step);
        continue;
        return false;
    }
    return true;
}
"""


if __name__ == "__main__":
    unittest.main()

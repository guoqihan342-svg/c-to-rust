from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from validation.tools._translation_carrier_reporter.errors import ReporterError
from validation.tools._translation_carrier_reporter.negative_execution import (
    run_negative_execution,
    suppress_body_call_statement,
)
from validation.tools._translation_carrier_reporter.reports import report_claim
from validation.tools._translation_carrier_reporter.sequence_contract import (
    behavior_fields,
    parse_contract,
)
from validation.tools._translation_carrier_reporter.sequence_contract_validation import (
    validate_noalias,
)
from validation.tools._translation_carrier_reporter.sequence_model import (
    negative_partition_probe_source,
    mutated_observable_outputs,
    reference_outputs,
    validate_cases,
)
from validation.tools.sequence_replay_test_support import build_interior_sequence_spec


BODY_EVENT = 11
TAIL_EVENT = 29
REPO_ROOT = Path(__file__).resolve().parents[2]


class TranslationCarrierSequenceBodyCalleeTests(unittest.TestCase):
    def test_recomputes_body_calls_arguments_and_shared_order(self) -> None:
        spec, fixture = build_body_sequence_spec()

        contract = parse_contract(spec)
        self.assertEqual(validate_cases(fixture["cases"], contract), fixture["cases"])
        self.assertEqual(
            behavior_fields(contract),
            [
                "completed",
                "selected_value",
                "body_count",
                "body_args",
                "probe_count",
                "probe_args",
                "call_order",
            ],
        )
        self.assertEqual(
            reference_outputs(fixture["cases"][1], contract),
            fixture["cases"][1]["expected_outputs"],
        )
        self.assertEqual(
            fixture["cases"][1]["expected_outputs"]["body_args"],
            [[7, 2], [7, 5], [7, 8]],
        )
        self.assertEqual(
            fixture["cases"][1]["expected_outputs"]["call_order"],
            [BODY_EVENT, TAIL_EVENT, BODY_EVENT, TAIL_EVENT, BODY_EVENT, TAIL_EVENT],
        )

    def test_callee_declaration_and_signature_order_do_not_matter(self) -> None:
        spec, _ = build_body_sequence_spec()
        spec["c_boundary"]["external_direct_callees"].reverse()
        spec["c_boundary"]["signatures"][1:] = reversed(
            spec["c_boundary"]["signatures"][1:]
        )

        contract = parse_contract(spec)

        self.assertEqual(contract["body_callee"]["name"], "observe_iteration")

    def test_rejects_body_shape_return_event_and_signature_drift(self) -> None:
        spec, _ = build_body_sequence_spec()
        missing = copy.deepcopy(spec)
        missing["replay_contract"]["body_callee"].pop("call_order_output")
        with self.assertRaisesRegex(ReporterError, "body_callee shape drifted"):
            parse_contract(missing)

        bool_return = copy.deepcopy(spec)
        bool_return["replay_contract"]["body_callee"]["return_value"] = True
        with self.assertRaisesRegex(ReporterError, "i32 integer"):
            parse_contract(bool_return)

        duplicate_event = copy.deepcopy(spec)
        duplicate_event["replay_contract"]["body_callee"]["tail_event_id"] = BODY_EVENT
        with self.assertRaisesRegex(ReporterError, "event ids must be unique"):
            parse_contract(duplicate_event)

        signature = copy.deepcopy(spec)
        signature["c_boundary"]["signatures"][2]["return_type"] = "uint32_t"
        with self.assertRaisesRegex(ReporterError, "body signature drifted"):
            parse_contract(signature)

    def test_rejects_body_on_legacy_schema_and_preserves_legacy_contract(self) -> None:
        legacy, _ = build_interior_sequence_spec()
        parse_contract(legacy)

        body_spec, _ = build_body_sequence_spec()
        body_spec["replay_contract"]["schema_version"] = 1
        with self.assertRaisesRegex(ReporterError, "requires schema_version 2"):
            parse_contract(body_spec)

    def test_noalias_includes_mutable_root_used_only_by_body_callee(self) -> None:
        contract = {
            "external_callee": {
                "arguments": [
                    {"mode": "record_ref", "entry_parameter": "ledger"},
                ]
            },
            "body_callee": {
                "arguments": [
                    {"mode": "record_ref", "entry_parameter": "audit"},
                ]
            },
            "state_output": {"parameter": "progress"},
            "noalias_required": [
                ["audit", "ledger"],
                ["audit", "progress"],
                ["ledger", "progress"],
            ],
        }
        spec = {
            "c_boundary": {
                "pointer_contract": {
                    "aliasing_proven": True,
                    "noalias_required": contract["noalias_required"],
                }
            }
        }
        entries = {
            "ledger": {"pass_mode": "mutable_ref"},
            "audit": {"pass_mode": "mutable_ref"},
            "progress": {"pass_mode": "mutable_ref"},
        }

        validate_noalias(spec, contract, entries)

        drift = copy.deepcopy(contract)
        drift["noalias_required"] = [["ledger", "progress"]]
        spec["c_boundary"]["pointer_contract"]["noalias_required"] = drift[
            "noalias_required"
        ]
        with self.assertRaisesRegex(ReporterError, "complete mutable root pair set"):
            validate_noalias(spec, drift, entries)

    def test_negative_probe_and_report_claim_include_body_observations(self) -> None:
        spec, fixture = build_body_sequence_spec()
        contract = parse_contract(spec)
        context = SimpleNamespace(
            contract=contract,
            cases=fixture["cases"],
            spec=spec,
            claim_boundary={"excluded_semantics": ["real callee semantics"]},
        )

        probe = negative_partition_probe_source(context)
        self.assertIn("__c2r_scripted_body_call_count()", probe)
        self.assertIn("__c2r_scripted_body_call_args()", probe)
        self.assertIn("__c2r_scripted_call_order()", probe)
        claim = report_claim(context)
        self.assertEqual(claim["body_callee"], "observe_iteration")
        self.assertEqual(
            claim["sequence_replay"]["body_call"]["shared_order_output"],
            "call_order",
        )
        self.assertFalse(claim["external_callee_semantics_verified"])

    def test_negative_mutation_suppresses_body_call_not_tail_comparison(self) -> None:
        spec, fixture = build_body_sequence_spec()
        contract = parse_contract(spec)
        source = b"""fn translated() {
    loop {
        let _ = observe_iteration(&mut ledger, cursor);
        cursor.selected = probe_following_window(&mut ledger, &mut window, cursor);
        if !(cursor.selected != 91u32) { break; }
    }
}
"""

        mutated, start, end = suppress_body_call_statement(
            source, contract["body_callee"]["name"]
        )

        self.assertEqual(len(mutated), len(source))
        self.assertNotIn(b"observe_iteration(", mutated)
        self.assertIn(b"cursor.selected != 91u32", mutated)
        self.assertTrue(mutated[start:end].startswith(b"//"))
        self.assertNotIn(b" ", mutated[start:end])
        suppressed = mutated_observable_outputs(fixture["cases"][1], contract)
        self.assertIsNotNone(suppressed)
        self.assertEqual(suppressed["body_count"], 0)
        self.assertEqual(suppressed["body_args"], [])
        self.assertEqual(suppressed["call_order"], [TAIL_EVENT, TAIL_EVENT, TAIL_EVENT])
        self.assertEqual(suppressed["probe_count"], 3)

    def test_negative_execution_detects_body_suppression_for_every_case(self) -> None:
        spec, fixture = build_body_sequence_spec()
        contract = parse_contract(spec)
        target = REPO_ROOT / "target"
        target.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="body-negative-", dir=target) as tmp:
            root = Path(tmp)
            draft = root / "draft.rs"
            replay = root / "replay.rs"
            output = root / "accepted"
            output.mkdir()
            draft.write_text(body_aware_rust_draft(), encoding="utf-8")
            replay.write_text(body_aware_positive_replay(), encoding="utf-8")
            context = SimpleNamespace(
                contract=contract,
                cases=fixture["cases"],
                spec=spec,
                repo_root=REPO_ROOT,
            )

            execution = run_negative_execution(context, draft, replay, output)

            self.assertEqual(execution["mutation"]["mutation_kind"], "body_call_suppression")
            self.assertEqual(execution["mutation"]["operator_from"], "body_call")
            self.assertEqual(execution["mutation"]["operator_to"], "suppressed")
            partition = execution["partition_replay"]
            self.assertEqual(
                partition["body_call_observable_mismatch_case_ids"],
                [case["id"] for case in fixture["cases"]],
            )
            self.assertEqual(partition["sequence_exhaustion_case_ids"], [])
            self.assertEqual(partition["observable_mismatch_case_ids"], [])
            mutated = next(
                content
                for path, content in execution["artifacts"].items()
                if path.name == "mutated-rust-draft.rs"
            )
            self.assertNotIn(b"let _ = observe_iteration(", mutated)
            self.assertIn(b"cursor.selected != 91u32", mutated)


def build_body_sequence_spec() -> tuple[dict[str, Any], dict[str, Any]]:
    spec, fixture = build_interior_sequence_spec()
    contract = spec["replay_contract"]
    contract["body_callee"] = {
        "name": "observe_iteration",
        "return_value": -7,
        "call_count_output": "body_count",
        "call_args_output": "body_args",
        "call_order_output": "call_order",
        "event_id": BODY_EVENT,
        "tail_event_id": TAIL_EVENT,
        "arguments": [
            {
                "parameter": "ledger_ref",
                "mode": "record_ref",
                "entry_parameter": "ledger",
                "field_path": ["stamp"],
            },
            {
                "parameter": "cursor_ref",
                "mode": "owner_interior_alias",
                "entry_parameter": "progress",
                "projection_path": ["current"],
                "alias_local": "cursor",
                "field_path": ["selected"],
            },
        ],
    }
    fields = [
        "completed",
        "selected_value",
        "body_count",
        "body_args",
        "probe_count",
        "probe_args",
        "call_order",
    ]
    spec["fixture_contract"]["behavior_fields"] = fields
    spec["fixture_contract"]["observable_outputs"] = fields
    fixture["compared_fields"] = fields
    body_signature = {
        "id": "sig-observe-iteration",
        "function": "observe_iteration",
        "return_type": "int",
        "parameters": [
            {"name": "ledger_ref", "c_type": "struct Ledger *", "direction": "input"},
            {"name": "cursor_ref", "c_type": "struct Cursor *", "direction": "inout"},
        ],
        "definition_status": "deterministic_fixture_stimulus",
    }
    spec["c_boundary"]["signatures"].append(body_signature)
    spec["c_boundary"]["external_direct_callees"].append(
        {
            "name": "observe_iteration",
            "signature_ref": body_signature["id"],
            "definition_status": "deterministic_fixture_stimulus",
            "stub_boundary": "fixed_fixture_only_no_real_callee_semantics",
        }
    )
    for case in fixture["cases"]:
        inputs = case["inputs"]
        expected = case["expected_outputs"]
        count = expected["probe_count"]
        current = inputs["selected_initial"]
        body_rows = []
        for scripted in inputs["probe_sequence"][:count]:
            body_rows.append([inputs["ledger_stamp"], current])
            current = scripted
        ordered = {
            "completed": expected["completed"],
            "selected_value": expected["selected_value"],
            "body_count": count,
            "body_args": body_rows,
            "probe_count": expected["probe_count"],
            "probe_args": expected["probe_args"],
            "call_order": [BODY_EVENT, TAIL_EVENT] * count,
        }
        expected.clear()
        expected.update(ordered)
    spec["fixture_contract"]["cases"] = fixture["cases"]
    return spec, fixture


def body_aware_rust_draft() -> str:
    return f"""#[derive(Clone, Copy)]
pub struct Ledger {{ pub stamp: u32 }}
#[derive(Clone, Copy)]
pub struct Window {{ pub page: u32 }}
#[derive(Clone, Copy)]
pub struct Cursor {{ pub selected: u32, pub tag: u32 }}
#[derive(Clone, Copy)]
pub struct Progress {{ pub walked: u32, pub current: Cursor }}

pub fn advance_window_tail(ledger: &mut Ledger, window_seed: Window, progress: &mut Progress) -> bool {{
    let cursor = &mut progress.current;
    let mut window = window_seed;
    loop {{
        let _ = observe_iteration(ledger, cursor);
        cursor.selected = probe_following_window(ledger, &mut window, cursor);
        if !(cursor.selected != 91u32) {{
            break;
        }}
    }}
    false
}}

std::thread_local! {{
    static SEQUENCE: std::cell::RefCell<Vec<u32>> = std::cell::RefCell::new(Vec::new());
    static INDEX: std::cell::Cell<usize> = std::cell::Cell::new(0);
    static EXTERNAL_COUNT: std::cell::Cell<usize> = std::cell::Cell::new(0);
    static EXTERNAL_ARGS: std::cell::RefCell<Vec<[u32; 3]>> = std::cell::RefCell::new(Vec::new());
    static BODY_COUNT: std::cell::Cell<usize> = std::cell::Cell::new(0);
    static BODY_ARGS: std::cell::RefCell<Vec<[u32; 2]>> = std::cell::RefCell::new(Vec::new());
    static CALL_ORDER: std::cell::RefCell<Vec<u32>> = std::cell::RefCell::new(Vec::new());
}}

fn __c2r_scripted_external_set_sequence(values: &[u32]) {{
    SEQUENCE.with(|slot| *slot.borrow_mut() = values.to_vec());
    INDEX.with(|slot| slot.set(0));
}}
fn __c2r_scripted_external_reset_calls() {{
    INDEX.with(|slot| slot.set(0));
    EXTERNAL_COUNT.with(|slot| slot.set(0));
    EXTERNAL_ARGS.with(|slot| slot.borrow_mut().clear());
    BODY_COUNT.with(|slot| slot.set(0));
    BODY_ARGS.with(|slot| slot.borrow_mut().clear());
    CALL_ORDER.with(|slot| slot.borrow_mut().clear());
}}
fn __c2r_scripted_external_call_count() -> usize {{ EXTERNAL_COUNT.with(std::cell::Cell::get) }}
fn __c2r_scripted_external_call_args() -> Vec<[u32; 3]> {{ EXTERNAL_ARGS.with(|slot| slot.borrow().clone()) }}
fn __c2r_scripted_body_call_count() -> usize {{ BODY_COUNT.with(std::cell::Cell::get) }}
fn __c2r_scripted_body_call_args() -> Vec<[u32; 2]> {{ BODY_ARGS.with(|slot| slot.borrow().clone()) }}
fn __c2r_scripted_call_order() -> Vec<u32> {{ CALL_ORDER.with(|slot| slot.borrow().clone()) }}

fn observe_iteration(ledger_ref: &mut Ledger, cursor_ref: &mut Cursor) -> i32 {{
    BODY_ARGS.with(|slot| slot.borrow_mut().push([ledger_ref.stamp, cursor_ref.selected]));
    BODY_COUNT.with(|slot| slot.set(slot.get() + 1));
    CALL_ORDER.with(|slot| slot.borrow_mut().push({BODY_EVENT}u32));
    -7i32
}}
fn probe_following_window(ledger_ref: &mut Ledger, window_ref: &mut Window, cursor_ref: &mut Cursor) -> u32 {{
    EXTERNAL_ARGS.with(|slot| slot.borrow_mut().push([ledger_ref.stamp, window_ref.page, cursor_ref.selected]));
    EXTERNAL_COUNT.with(|slot| slot.set(slot.get() + 1));
    CALL_ORDER.with(|slot| slot.borrow_mut().push({TAIL_EVENT}u32));
    let index = INDEX.with(std::cell::Cell::get);
    let value = SEQUENCE.with(|slot| *slot.borrow().get(index).expect("sequence exhausted"));
    INDEX.with(|slot| slot.set(index + 1));
    value
}}
"""


def body_aware_positive_replay() -> str:
    return f"""
#[test]
fn accepted_body_observations() {{
    __c2r_scripted_external_set_sequence(&[5u32, 8u32, 91u32]);
    __c2r_scripted_external_reset_calls();
    let mut ledger = Ledger {{ stamp: 7 }};
    let window = Window {{ page: 11 }};
    let mut progress = Progress {{ walked: 13, current: Cursor {{ selected: 2, tag: 119 }} }};
    assert!(!advance_window_tail(&mut ledger, window, &mut progress));
    assert_eq!(__c2r_scripted_external_call_count(), 3usize);
    assert_eq!(__c2r_scripted_body_call_count(), 3usize);
    assert_eq!(__c2r_scripted_body_call_args(), vec![[7u32, 2u32], [7u32, 5u32], [7u32, 8u32]]);
    assert_eq!(__c2r_scripted_call_order(), vec![{BODY_EVENT}u32, {TAIL_EVENT}u32, {BODY_EVENT}u32, {TAIL_EVENT}u32, {BODY_EVENT}u32, {TAIL_EVENT}u32]);
}}
"""


if __name__ == "__main__":
    unittest.main()

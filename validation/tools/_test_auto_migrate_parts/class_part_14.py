from validation.tools.sequence_replay_test_support import (
    build_interior_sequence_spec,
)


class _AutoMigrateTestsPart14:
    @staticmethod
    def _body_sequence_demo() -> tuple[dict[str, Any], str]:
        spec, _ = build_interior_sequence_spec()
        spec["fixture_hash"] = "synthetic-body-sequence-fixture"
        body = {
            "name": "inspect_window_step",
            "return_value": -3,
            "call_count_output": "body_count",
            "call_args_output": "body_args",
            "call_order_output": "call_order",
            "event_id": 7,
            "tail_event_id": 9,
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
                {
                    "parameter": "page_copy",
                    "mode": "scalar_field_value",
                    "entry_parameter": "window_seed",
                    "field_path": ["page"],
                },
            ],
        }
        spec["replay_contract"]["body_callee"] = body
        existing_fields = list(spec["fixture_contract"]["behavior_fields"])
        fields = [
            existing_fields[0],
            existing_fields[1],
            "body_count",
            "body_args",
            existing_fields[2],
            existing_fields[3],
            "call_order",
        ]
        spec["fixture_contract"]["behavior_fields"] = fields
        spec["fixture_contract"]["observable_outputs"] = list(fields)
        for case in spec["fixture_contract"]["cases"]:
            inputs = case["inputs"]
            sequence = inputs["probe_sequence"]
            count = sequence.index(91) + 1
            current = inputs["selected_initial"]
            body_rows = []
            order = []
            for scripted in sequence[:count]:
                body_rows.append(
                    [inputs["ledger_stamp"], current, inputs["window_page"]]
                )
                order.extend([7, 9])
                current = scripted
            case["expected_outputs"].update(
                {
                    "body_count": count,
                    "body_args": body_rows,
                    "call_order": order,
                }
            )
        spec["c_boundary"]["signatures"].append(
            {
                "id": "sig-inspect-window-step",
                "function": "inspect_window_step",
                "return_type": "int",
                "parameters": [
                    {
                        "name": "ledger_ref",
                        "c_type": "struct Ledger *",
                        "direction": "input",
                    },
                    {
                        "name": "cursor_ref",
                        "c_type": "struct Cursor *",
                        "direction": "input",
                    },
                    {
                        "name": "page_copy",
                        "c_type": "uint32_t",
                        "direction": "input",
                    },
                ],
                "definition_status": "deterministic_fixture_observer",
            }
        )
        spec["c_boundary"]["external_direct_callees"].append(
            {
                "name": "inspect_window_step",
                "signature_ref": "sig-inspect-window-step",
                "definition_status": "deterministic_fixture_observer",
                "stub_boundary": "scripted_fixture_only_no_real_callee_semantics",
            }
        )
        spec["c_boundary"]["direct_dependencies"].append(
            {
                "kind": "callee",
                "name": "inspect_window_step",
                "definition_status": "deterministic_fixture_observer_only",
            }
        )
        spec["c_source"] = """#define WINDOW_END 91u
struct Ledger { uint32_t stamp; };
struct Window { uint32_t page; };
struct Cursor { uint32_t selected; uint32_t tag; };
struct Progress { uint32_t walked; struct Cursor current; };
int inspect_window_step(struct Ledger *ledger_ref, struct Cursor *cursor_ref, uint32_t page_copy);
uint32_t probe_following_window(struct Ledger *ledger_ref, struct Window *window_ref, struct Cursor *cursor_ref);
static bool advance_window_tail(struct Ledger *ledger, struct Window window_seed, struct Progress *progress)
{
    struct Cursor *cursor = &progress->current;
    struct Window window = window_seed;
    do {
        (void)inspect_window_step(ledger, cursor, window.page);
        cursor->selected = probe_following_window(ledger, &window, cursor);
    } while (cursor->selected != WINDOW_END);
    return false;
}
"""
        rust_draft = """#[derive(Clone, Copy)]
pub struct Ledger { pub stamp: u32 }
#[derive(Clone, Copy)]
pub struct Window { pub page: u32 }
#[derive(Clone, Copy)]
pub struct Cursor { pub selected: u32, pub tag: u32 }
#[derive(Clone, Copy)]
pub struct Progress { pub walked: u32, pub current: Cursor }

pub fn advance_window_tail(ledger: &mut Ledger, window_seed: Window, progress: &mut Progress) -> bool {
    let cursor = &mut progress.current;
    let mut window = window_seed;
    loop {
        let page_copy = window.page;
        let _ = inspect_window_step(ledger, cursor, page_copy);
        cursor.selected = probe_following_window(ledger, &mut window, cursor);
        if cursor.selected == 91u32 {
            break;
        }
    }
    false
}
"""
        return spec, rust_draft

    @staticmethod
    def _parse_body_sequence(module: Any, spec: dict[str, Any]) -> dict[str, Any]:
        return module.scripted_external_record_u32_sequence_do_while_state_replay_contract(
            spec, module.oracle_fixture_binding(spec)
        )

    def test_body_sequence_demo_c_oracle_and_rust_replay(self) -> None:
        module = load_auto_migrate_module()
        spec, rust_draft = self._body_sequence_demo()
        fixture_binding = module.oracle_fixture_binding(spec)
        contract = self._parse_body_sequence(module, spec)
        self.assertEqual(
            [item["mode"] for item in contract["body_callee"]["arguments"]],
            ["record_ref", "owner_interior_alias", "scalar_field_value"],
        )
        self.assertEqual(
            spec["fixture_contract"]["cases"][1]["expected_outputs"]["call_order"],
            [7, 9, 7, 9, 7, 9],
        )
        oracle_source = module.oracle_fixture_execution_source(spec, fixture_binding)
        self.assertIn("int inspect_window_step(", oracle_source["definitions_after_target"])
        self.assertIn("c2r_scripted_call_order", oracle_source["definitions_after_target"])
        self.assertEqual(
            oracle_source["fixture_external_stub"]["callees"],
            ["probe_following_window", "inspect_window_step"],
        )
        context = module.external_direct_callee_context(
            spec,
            [
                {"callee": "inspect_window_step"},
                {"callee": "probe_following_window"},
            ],
        )
        boundaries = module.external_stub_boundaries(context)
        self.assertEqual(
            {item["callee"] for item in boundaries},
            {"inspect_window_step", "probe_following_window"},
        )
        self.assertTrue(all(item["fixture_only"] for item in boundaries))

        with tempfile.TemporaryDirectory(prefix="auto-migrate-body-sequence-") as tmp:
            evidence_dir = Path(tmp)
            spec_path = evidence_dir / "advance-window-tail.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            oracle = module.generate_oracle_harness_draft(spec, evidence_dir, False)
            self.assertEqual(
                oracle["compile_execution"]["harness_execution"]["status"],
                "exited_zero_not_oracle",
            )
            draft_path = evidence_dir / "l3-advance-window-tail-rust-draft.rs"
            draft_path.write_text(rust_draft, encoding="utf-8")
            plan_path = evidence_dir / "l3-advance-window-tail-auto-translation-plan.json"
            plan_path.write_text(
                json.dumps(
                    {
                        "translation_summary": {
                            "translation_rule_ids": ["clang-lowered-typed-ir"],
                            "call_expressions": [
                                {"callee": "inspect_window_step"},
                                {"callee": "probe_following_window"},
                            ],
                        }
                    }
                ),
                encoding="utf-8",
            )
            replay = module.generate_rust_replay_test_draft(
                spec, evidence_dir, spec_path
            )
            rust_check, _ = module.run_rust_check(evidence_dir, False, spec)
            self.assertEqual(rust_check["status"], "passed")
            bindings = rust_check["rust_check_harness_only_bindings"]["bindings"]
            self.assertEqual({item["name"] for item in bindings}, {
                "inspect_window_step",
                "probe_following_window",
            })
            self.assertTrue(all(item["fixture_only"] for item in bindings))
            replay = module.run_generated_rust_replay(
                spec, evidence_dir, replay, rust_check
            )
            self.assertEqual(replay["status"], "passed")

    def test_body_sequence_stub_injection_is_callee_order_independent(self) -> None:
        for reverse in (False, True):
            with self.subTest(reverse=reverse):
                module = load_auto_migrate_module()
                spec, rust_draft = self._body_sequence_demo()
                context = module.external_direct_callee_context(
                    spec,
                    [
                        {"callee": "inspect_window_step"},
                        {"callee": "probe_following_window"},
                    ],
                )
                if reverse:
                    context["declared"].reverse()
                with tempfile.TemporaryDirectory(
                    prefix="auto-migrate-body-stub-order-"
                ) as tmp:
                    draft_path = Path(tmp) / "draft.rs"
                    draft_path.write_text(rust_draft, encoding="utf-8")
                    self.assertTrue(
                        module.inject_external_callee_stubs(
                            draft_path, context, spec
                        )
                    )
                    checked = module.rust_check_once(draft_path)
                    self.assertEqual(checked["returncode"], 0, checked["stderr"])
                    text = draft_path.read_text(encoding="utf-8")
                    self.assertEqual(
                        text.count("fn __c2r_scripted_external_set_sequence("), 1
                    )
                    self.assertEqual(text.count("fn __c2r_scripted_call_order("), 1)
                    bindings = module.rust_check_external_binding_report(context)[
                        "bindings"
                    ]
                    self.assertEqual(len(bindings), 2)
                    self.assertTrue(all(item["fixture_only"] for item in bindings))

    def test_body_sequence_contract_and_fixture_drift_fail_closed(self) -> None:
        module = load_auto_migrate_module()
        invalid: list[tuple[str, dict[str, Any], str]] = []

        extra_contract, _ = self._body_sequence_demo()
        extra_contract["replay_contract"]["unexpected"] = True
        invalid.append(("contract-extra", extra_contract, "contract shape drifted"))

        extra_body, _ = self._body_sequence_demo()
        extra_body["replay_contract"]["body_callee"]["unexpected"] = True
        invalid.append(("body-extra", extra_body, "body_callee shape drifted"))

        redundant_external, _ = self._body_sequence_demo()
        redundant_external["replay_contract"]["external_callee"][
            "call_order_output"
        ] = "redundant_order"
        invalid.append(
            (
                "external-redundant-order",
                redundant_external,
                "external_callee shape drifted",
            )
        )

        invalid_return, _ = self._body_sequence_demo()
        invalid_return["replay_contract"]["body_callee"]["return_value"] = True
        invalid.append(("return-type", invalid_return, "return_value must be i32"))

        invalid_version, _ = self._body_sequence_demo()
        invalid_version["replay_contract"]["schema_version"] = 1
        invalid.append(
            ("schema-version", invalid_version, "requires schema_version 2")
        )

        invalid_event, _ = self._body_sequence_demo()
        invalid_event["replay_contract"]["body_callee"]["event_id"] = "body"
        invalid.append(("event-type", invalid_event, "event ids must be u32"))

        duplicate_event, _ = self._body_sequence_demo()
        duplicate_event["replay_contract"]["body_callee"]["tail_event_id"] = 7
        invalid.append(("event-duplicate", duplicate_event, "event ids must be unique"))

        same_name, _ = self._body_sequence_demo()
        same_name["replay_contract"]["body_callee"]["name"] = (
            same_name["replay_contract"]["external_callee"]["name"]
        )
        invalid.append(("same-name", same_name, "callees must differ"))

        undeclared, _ = self._body_sequence_demo()
        undeclared["c_boundary"]["external_direct_callees"] = [
            item
            for item in undeclared["c_boundary"]["external_direct_callees"]
            if item["name"] != "inspect_window_step"
        ]
        invalid.append(("undeclared", undeclared, "one declared body callee"))

        signature, _ = self._body_sequence_demo()
        signature["c_boundary"]["signatures"][-1]["return_type"] = "uint32_t"
        invalid.append(("signature", signature, "body signature binding drifted"))

        parameter, _ = self._body_sequence_demo()
        parameter["c_boundary"]["signatures"][-1]["parameters"][2][
            "c_type"
        ] = "size_t"
        invalid.append(("parameter", parameter, "body parameter types drifted"))

        order, _ = self._body_sequence_demo()
        order["fixture_contract"]["cases"][0]["expected_outputs"]["call_order"] = [
            9,
            7,
        ]
        invalid.append(("order", order, "expected outputs drifted"))

        missing_output, _ = self._body_sequence_demo()
        del missing_output["fixture_contract"]["cases"][0]["expected_outputs"][
            "body_args"
        ]
        invalid.append(
            ("fixture-field", missing_output, "expected output fields drifted")
        )

        invalid_output_type, _ = self._body_sequence_demo()
        invalid_output_type["fixture_contract"]["cases"][0]["expected_outputs"][
            "body_count"
        ] = True
        invalid.append(
            ("fixture-type", invalid_output_type, "call counts are invalid")
        )

        for label, spec, message in invalid:
            with self.subTest(label=label):
                with self.assertRaisesRegex(ValueError, message):
                    self._parse_body_sequence(module, spec)

    def test_sequence_contract_without_body_keeps_legacy_outputs(self) -> None:
        module = load_auto_migrate_module()
        spec, _ = build_interior_sequence_spec()
        spec["fixture_hash"] = "synthetic-legacy-sequence-fixture"
        fixture_binding = module.oracle_fixture_binding(spec)
        contract = (
            module.scripted_external_record_u32_sequence_do_while_state_replay_contract(
                spec, fixture_binding
            )
        )
        self.assertNotIn("body_callee", contract)
        self.assertEqual(
            module.scripted_sequence_behavior_fields(contract),
            ["completed", "selected_value", "probe_count", "probe_args"],
        )
        for case in spec["fixture_contract"]["cases"]:
            self.assertEqual(
                module.scripted_sequence_expected_outputs(case["inputs"], contract),
                case["expected_outputs"],
            )
        oracle = module.oracle_fixture_execution_source(spec, fixture_binding)
        self.assertEqual(
            oracle["fixture_external_stub"],
            {
                "kind": "scripted_external_record_u32_sequence_do_while_state",
                "scope": "fixture_only",
                "semantics_verified": False,
            },
        )
        self.assertNotIn("c2r_scripted_body", oracle["definitions_after_target"])

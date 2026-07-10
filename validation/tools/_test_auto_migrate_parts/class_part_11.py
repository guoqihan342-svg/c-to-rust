class _AutoMigrateTestsPart11:
    def _scripted_record_external_spec(self) -> dict[str, Any]:
        cases = [
            {
                "id": "sentinel",
                "inputs": {
                    "store_token": 41,
                    "cursor_offset": 73,
                    "entry_initial_value": 9,
                    "scripted_value": 0xFFFFFFFF,
                },
                "expected_outputs": {
                    "is_exhausted": True,
                    "entry_value": 0xFFFFFFFF,
                    "reserve_call_count": 1,
                    "reserve_call_args": [41, 73, 9],
                },
            },
            {
                "id": "available",
                "inputs": {
                    "store_token": 5,
                    "cursor_offset": 11,
                    "entry_initial_value": 17,
                    "scripted_value": 7001,
                },
                "expected_outputs": {
                    "is_exhausted": False,
                    "entry_value": 7001,
                    "reserve_call_count": 1,
                    "reserve_call_args": [5, 11, 17],
                },
            },
        ]
        initializer = lambda record_type, field: {
            "record_type": record_type,
            "fields": [field],
        }
        return {
            "schema_version": 1,
            "target_id": "independent-record-store",
            "slice_id": "classify-record-reservation",
            "level": "L3",
            "function_name": "classify_record_reservation",
            "source_commit": "synthetic-scripted-record-contract",
            "fixture_hash": "synthetic-scripted-record-fixture",
            "c_source": (
                "#define INVALID_VALUE ((uint32_t)-1)\n"
                "struct Store { uint32_t token; };\n"
                "struct Cursor { uint32_t offset; };\n"
                "struct Position { uint32_t value; };\n"
                "struct Entry { struct Position position; };\n"
                "uint32_t reserve_next(struct Store *store, struct Cursor *cursor, struct Entry *entry);\n"
                "static bool classify_record_reservation(struct Store *store, struct Cursor cursor_seed, struct Entry *entry)\n"
                "{\n"
                "    struct Cursor cursor = cursor_seed;\n"
                "    bool exhausted = false;\n"
                "    if ((entry->position.value = reserve_next(store, &cursor, entry)) == INVALID_VALUE) {\n"
                "        exhausted = true;\n"
                "    }\n"
                "    return exhausted;\n"
                "}\n"
            ),
            "fixture_contract": {
                "path": "inline-independent-record-store.json",
                "behavior_fields": [
                    "is_exhausted",
                    "entry_value",
                    "reserve_call_count",
                    "reserve_call_args",
                ],
                "observable_outputs": [
                    "is_exhausted",
                    "entry_value",
                    "reserve_call_count",
                    "reserve_call_args",
                ],
                "cases": cases,
            },
            "replay_contract": {
                "schema_version": 1,
                "kind": "scripted_external_record_u32_call_bool_state",
                "external_callee": {
                    "name": "reserve_next",
                    "return_fixture_field": "scripted_value",
                    "call_count_output": "reserve_call_count",
                    "call_args_output": "reserve_call_args",
                    "arguments": [
                        {
                            "parameter": "store",
                            "entry_parameter": "store",
                            "field_path": ["token"],
                        },
                        {
                            "parameter": "cursor",
                            "entry_parameter": "cursor_seed",
                            "field_path": ["offset"],
                        },
                        {
                            "parameter": "entry",
                            "entry_parameter": "entry",
                            "field_path": ["position", "value"],
                        },
                    ],
                },
                "entry_arguments": [
                    {
                        "parameter": "store",
                        "c_type": "struct Store *",
                        "rust_type": "Store",
                        "pass_mode": "mutable_ref",
                        "direction": "input",
                        "initializer": initializer(
                            "Store",
                            {
                                "name": "token",
                                "fixture_field": "store_token",
                                "rust_type": "u32",
                            },
                        ),
                    },
                    {
                        "parameter": "cursor_seed",
                        "c_type": "struct Cursor",
                        "rust_type": "Cursor",
                        "pass_mode": "value",
                        "direction": "input",
                        "initializer": initializer(
                            "Cursor",
                            {
                                "name": "offset",
                                "fixture_field": "cursor_offset",
                                "rust_type": "u32",
                            },
                        ),
                    },
                    {
                        "parameter": "entry",
                        "c_type": "struct Entry *",
                        "rust_type": "Entry",
                        "pass_mode": "mutable_ref",
                        "direction": "inout",
                        "initializer": initializer(
                            "Entry",
                            {
                                "name": "position",
                                "record": initializer(
                                    "Position",
                                    {
                                        "name": "value",
                                        "fixture_field": "entry_initial_value",
                                        "rust_type": "u32",
                                    },
                                ),
                            },
                        ),
                    },
                ],
                "state_output": {
                    "parameter": "entry",
                    "field_path": ["position", "value"],
                    "fixture_field": "entry_value",
                    "rust_type": "u32",
                },
                "return": {"fixture_field": "is_exhausted", "rust_type": "bool"},
                "noalias_required": [["store", "entry"]],
            },
            "c_boundary": {
                "oracle_source_mode": "embedded_slice_c_source",
                "signatures": [
                    {
                        "id": "sig-classify-record-reservation",
                        "function": "classify_record_reservation",
                        "return_type": "bool",
                        "parameters": [
                            {"name": "store", "c_type": "struct Store *", "direction": "input"},
                            {"name": "cursor_seed", "c_type": "struct Cursor", "direction": "input"},
                            {"name": "entry", "c_type": "struct Entry *", "direction": "inout"},
                        ],
                    },
                    {
                        "id": "sig-reserve-next",
                        "function": "reserve_next",
                        "return_type": "uint32_t",
                        "parameters": [
                            {"name": "store", "c_type": "struct Store *", "direction": "input"},
                            {"name": "cursor", "c_type": "struct Cursor *", "direction": "input"},
                            {"name": "entry", "c_type": "struct Entry *", "direction": "input"},
                        ],
                        "definition_status": "deterministic_fixture_stimulus",
                    },
                ],
                "external_direct_callees": [
                    {
                        "name": "reserve_next",
                        "signature_ref": "sig-reserve-next",
                        "definition_status": "deterministic_fixture_stimulus",
                        "stub_boundary": "scripted_fixture_only_no_real_callee_semantics",
                    }
                ],
                "direct_dependencies": [
                    {
                        "kind": "callee",
                        "name": "reserve_next",
                        "definition_status": "deterministic_fixture_stimulus_only",
                    }
                ],
                "pointer_contract": {
                    "input_buffers": [{"name": "store"}],
                    "output_pointers": [{"name": "entry"}],
                    "aliasing_proven": True,
                    "noalias_required": [["store", "entry"]],
                },
            },
            "build_profile": {
                "compiler": "cc",
                "include_paths": [],
                "defines": [],
                "oracle_harness_includes": [],
            },
        }

    def test_scripted_record_external_contract_is_project_independent_and_replays(self) -> None:
        module = load_auto_migrate_module()
        spec = self._scripted_record_external_spec()
        fixture_binding = module.oracle_fixture_binding(spec)

        contract = module.scripted_external_record_u32_call_bool_state_replay_contract(
            spec, fixture_binding
        )
        self.assertEqual(contract["external_callee"]["name"], "reserve_next")
        oracle = module.oracle_fixture_execution_source(spec, fixture_binding)
        self.assertEqual(oracle["declarations"], "")
        self.assertIn("uint32_t reserve_next(", oracle["definitions_after_target"])
        self.assertIn("struct Entry actual_sentinel_entry", oracle["statements"])

        draft = """\
#[derive(Clone, Copy)]
pub struct Store { pub token: u32 }
#[derive(Clone, Copy)]
pub struct Cursor { pub offset: u32 }
#[derive(Clone, Copy)]
pub struct Position { pub value: u32 }
#[derive(Clone, Copy)]
pub struct Entry { pub position: Position }

pub fn classify_record_reservation(store: &mut Store, cursor_seed: Cursor, entry: &mut Entry) -> bool {
    let mut cursor = cursor_seed;
    entry.position.value = reserve_next(store, &mut cursor, entry);
    entry.position.value == u32::MAX
}
"""
        with tempfile.TemporaryDirectory(prefix="auto-migrate-scripted-record-") as tmp:
            evidence_dir = Path(tmp)
            spec_path = evidence_dir / "classify-record-reservation.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            oracle_report = module.generate_oracle_harness_draft(spec, evidence_dir, False)
            self.assertEqual(
                oracle_report["compile_execution"]["harness_execution"]["status"],
                "exited_zero_not_oracle",
            )
            (evidence_dir / "l3-classify-record-reservation-rust-draft.rs").write_text(
                draft, encoding="utf-8"
            )
            (evidence_dir / "l3-classify-record-reservation-auto-translation-plan.json").write_text(
                json.dumps(
                    {
                        "translation_summary": {
                            "translation_rule_ids": ["clang-lowered-typed-ir"],
                            "call_expressions": [{"callee": "reserve_next"}],
                        }
                    }
                ),
                encoding="utf-8",
            )
            replay = module.generate_rust_replay_test_draft(spec, evidence_dir, spec_path)
            rust_check, _ = module.run_rust_check(evidence_dir, False, spec)
            self.assertEqual(rust_check["status"], "passed")
            replay = module.run_generated_rust_replay(
                spec, evidence_dir, replay, rust_check
            )
            self.assertEqual(replay["status"], "passed")
            self.assertEqual(
                replay["fixture_external_stub"]["kind"],
                "scripted_external_record_u32_call_bool_state",
            )

    def test_scripted_record_external_contract_rejects_noalias_drift(self) -> None:
        module = load_auto_migrate_module()
        spec = self._scripted_record_external_spec()
        spec["c_boundary"]["pointer_contract"]["noalias_required"] = []

        with self.assertRaisesRegex(ValueError, "noalias contract drifted"):
            module.scripted_external_record_u32_call_bool_state_replay_contract(
                spec,
                module.oracle_fixture_binding(spec),
            )

        spec["replay_contract"]["noalias_required"] = []
        with self.assertRaisesRegex(ValueError, "must cover all forwarded mutable record pairs"):
            module.scripted_external_record_u32_call_bool_state_replay_contract(
                spec,
                module.oracle_fixture_binding(spec),
            )

class _AutoMigrateTestsPart10:
    def test_translation_carrier_binds_input_plan_and_lowering_report(self) -> None:
        module = load_auto_migrate_module()
        carrier = {
            "kind": "exact_source_fragment_wrapper",
            "carrier_function": "identity_probe",
            "embedding_mode": "verbatim_once",
            "claim_boundary": {
                "scope": "source_fragment_only",
                "whole_function_semantics_verified": False,
                "external_callee_semantics_verified": False,
            },
        }
        base_spec = {
            "schema_version": 1,
            "target_id": "independent-carrier-target",
            "slice_id": "identity-carrier-binding",
            "level": "L3",
            "function_name": "identity_probe",
            "source_commit": "synthetic-carrier-binding",
            "fixture_hash": "synthetic-carrier-fixture",
            "c_source": "int identity_probe(int value) { return value; }",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "compiler_command_source": "unit-test",
                "clang_available": False,
            },
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-carrier-chain-") as tmp:
            root = Path(tmp)
            for label, include_carrier in (("with", True), ("without", False)):
                with self.subTest(label=label):
                    spec = json.loads(json.dumps(base_spec))
                    if include_carrier:
                        spec["translation_carrier"] = carrier
                    evidence_dir = root / label
                    evidence_dir.mkdir()
                    spec_path = evidence_dir / "slice.json"
                    spec_path.write_text(json.dumps(spec), encoding="utf-8")
                    translator_input_path = module.write_translator_spec(
                        spec,
                        spec_path,
                        evidence_dir,
                    )
                    module.run_translator(
                        translator_input_path,
                        evidence_dir,
                        emit_clang_lowering_report=True,
                    )
                    (
                        evidence_dir
                        / "l3-identity-carrier-binding-c-oracle-harness-draft.c"
                    ).write_text("int main(void) { return 0; }\n", encoding="utf-8")
                    (
                        evidence_dir
                        / "l3-identity-carrier-binding-rust-replay-test-draft.rs"
                    ).write_text("// replay placeholder\n", encoding="utf-8")
                    module.normalize_translation_artifacts(spec, spec_path, evidence_dir)
                    translator_input = json.loads(
                        translator_input_path.read_text(encoding="utf-8")
                    )
                    plan = json.loads(
                        (
                            evidence_dir
                            / "l3-identity-carrier-binding-auto-translation-plan.json"
                        ).read_text(encoding="utf-8")
                    )
                    lowering = json.loads(
                        (
                            evidence_dir
                            / "l3-identity-carrier-binding-clang-lowering-report.json"
                        ).read_text(encoding="utf-8")
                    )
                    if include_carrier:
                        self.assertEqual(translator_input["translation_carrier"], carrier)
                        self.assertEqual(plan["translation_carrier"], carrier)
                        self.assertEqual(lowering["translation_carrier"], carrier)
                        self.assertEqual(plan["fixture_hash"], base_spec["fixture_hash"])
                    else:
                        self.assertNotIn("translation_carrier", translator_input)
                        self.assertNotIn("translation_carrier", plan)
                        self.assertNotIn("translation_carrier", lowering)

    def _scripted_external_bool_out_spec(self) -> dict[str, Any]:
        cases = [
            {
                "id": "sentinel",
                "inputs": {
                    "owner_token": 41,
                    "partition": 73,
                    "units": 9,
                    "scripted_ticket": 0xFFFFFFFF,
                },
                "expected_outputs": {
                    "is_exhausted": True,
                    "ticket_value": 0xFFFFFFFF,
                    "reserve_call_count": 1,
                    "reserve_call_args": [41, 73, 9],
                },
            },
            {
                "id": "available",
                "inputs": {
                    "owner_token": 5,
                    "partition": 11,
                    "units": 2048,
                    "scripted_ticket": 7001,
                },
                "expected_outputs": {
                    "is_exhausted": False,
                    "ticket_value": 7001,
                    "reserve_call_count": 1,
                    "reserve_call_args": [5, 11, 2048],
                },
            },
        ]
        return {
            "schema_version": 1,
            "target_id": "independent-ticket-store",
            "slice_id": "classify-ticket-reservation",
            "level": "L3",
            "function_name": "classify_ticket",
            "source_commit": "synthetic-scripted-external-contract",
            "fixture_hash": "synthetic-scripted-external-fixture",
            "c_source": (
                "uint32_t reserve_ticket(uint32_t owner, uint32_t bucket, size_t amount);\n"
                "static bool classify_ticket(uint32_t owner, uint32_t bucket, size_t amount, "
                "uint32_t *ticket_out)\n"
                "{\n"
                "    uint32_t ticket = UINT32_MAX;\n"
                "    bool exhausted = false;\n"
                "    if ((ticket = reserve_ticket(owner, bucket, amount)) == UINT32_MAX) {\n"
                "        exhausted = true;\n"
                "    }\n"
                "    *ticket_out = ticket;\n"
                "    return exhausted;\n"
                "}\n"
            ),
            "fixture_contract": {
                "path": "inline-independent-ticket-store.json",
                "behavior_fields": [
                    "is_exhausted",
                    "ticket_value",
                    "reserve_call_count",
                    "reserve_call_args",
                ],
                "observable_outputs": [
                    "is_exhausted",
                    "ticket_value",
                    "reserve_call_count",
                    "reserve_call_args",
                ],
                "cases": cases,
            },
            "replay_contract": {
                "schema_version": 1,
                "kind": "scripted_external_u32_call_bool_out",
                "external_callee": {
                    "name": "reserve_ticket",
                    "return_fixture_field": "scripted_ticket",
                    "call_count_output": "reserve_call_count",
                    "call_args_output": "reserve_call_args",
                },
                "inputs": [
                    {"parameter": "owner", "fixture_field": "owner_token", "rust_type": "u32"},
                    {"parameter": "bucket", "fixture_field": "partition", "rust_type": "u32"},
                    {"parameter": "amount", "fixture_field": "units", "rust_type": "usize"},
                ],
                "output_pointer": {
                    "parameter": "ticket_out",
                    "fixture_field": "ticket_value",
                    "rust_type": "u32",
                },
                "return": {"fixture_field": "is_exhausted", "rust_type": "bool"},
            },
            "c_boundary": {
                "oracle_source_mode": "embedded_slice_c_source",
                "signatures": [
                    {
                        "id": "sig-classify-ticket",
                        "function": "classify_ticket",
                        "return_type": "bool",
                        "parameters": [
                            {"name": "owner", "c_type": "uint32_t", "direction": "input"},
                            {"name": "bucket", "c_type": "uint32_t", "direction": "input"},
                            {"name": "amount", "c_type": "size_t", "direction": "input"},
                            {"name": "ticket_out", "c_type": "uint32_t *", "direction": "output"},
                        ],
                    },
                    {
                        "id": "sig-reserve-ticket",
                        "function": "reserve_ticket",
                        "return_type": "uint32_t",
                        "parameters": [
                            {"name": "owner", "c_type": "uint32_t", "direction": "input"},
                            {"name": "bucket", "c_type": "uint32_t", "direction": "input"},
                            {"name": "amount", "c_type": "size_t", "direction": "input"},
                        ],
                        "definition_status": "deterministic_fixture_stimulus",
                    },
                ],
                "external_direct_callees": [
                    {
                        "name": "reserve_ticket",
                        "signature_ref": "sig-reserve-ticket",
                        "definition_status": "deterministic_fixture_stimulus",
                        "stub_boundary": "scripted_fixture_only_no_real_callee_semantics",
                    }
                ],
                "direct_dependencies": [
                    {
                        "kind": "callee",
                        "name": "reserve_ticket",
                        "definition_status": "deterministic_fixture_stimulus_only",
                    }
                ],
                "pointer_contract": {
                    "input_buffers": [],
                    "output_pointers": [
                        {
                            "name": "ticket_out",
                            "c_type": "uint32_t *",
                            "direction": "output",
                            "length_companion": "constant:1",
                            "mutability": "write_only",
                        }
                    ],
                    "aliasing_proven": True,
                    "noalias_required": [],
                },
            },
            "build_profile": {
                "compiler": "cc",
                "include_paths": [],
                "defines": [],
                "oracle_harness_includes": [],
            },
        }

    def test_scripted_external_contract_is_project_independent_and_replays(self) -> None:
        module = load_auto_migrate_module()
        spec = self._scripted_external_bool_out_spec()
        fixture_binding = module.oracle_fixture_binding(spec)

        self.assertIsNone(module.record_pointer_identity_return_replay_contract(spec, fixture_binding))
        self.assertIsNone(module.readonly_byte_slice_bool_return_replay_contract(spec, fixture_binding))
        contract = module.scripted_external_u32_call_bool_out_replay_contract(spec, fixture_binding)
        self.assertEqual(contract["external_callee"]["name"], "reserve_ticket")

        oracle = module.oracle_fixture_execution_source(spec, fixture_binding)
        self.assertIn("uint32_t reserve_ticket(", oracle["declarations"])
        self.assertIn("classify_ticket(", oracle["statements"])
        self.assertIn("c2r_scripted_external_call_count", oracle["statements"])
        self.assertIn("c2r_scripted_external_arg2", oracle["statements"])
        self.assertEqual(
            oracle["fixture_external_stub"],
            {
                "kind": "scripted_external_u32_call_bool_out",
                "scope": "fixture_only",
                "semantics_verified": False,
            },
        )

        draft = """\
pub fn classify_ticket(owner: u32, bucket: u32, amount: usize, ticket_out: &mut [u32]) -> bool {
    let ticket = reserve_ticket(owner, bucket, amount);
    let exhausted = ticket == u32::MAX;
    ticket_out[0] = ticket;
    exhausted
}
"""
        with tempfile.TemporaryDirectory(prefix="auto-migrate-scripted-external-") as tmp:
            evidence_dir = Path(tmp)
            spec_path = evidence_dir / "classify-ticket-reservation.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            oracle_report = module.generate_oracle_harness_draft(spec, evidence_dir, False)
            self.assertEqual(
                oracle_report["compile_execution"]["status"],
                "compile_succeeded_not_oracle",
            )
            self.assertEqual(
                oracle_report["compile_execution"]["harness_execution"]["status"],
                "exited_zero_not_oracle",
            )
            self.assertEqual(
                oracle_report["compile_execution"]["harness_execution"]["output_gate"]["status"],
                "matched_not_oracle",
            )
            self.assertFalse(
                oracle_report["harness_contract"]["fixture_external_stub"]["semantics_verified"]
            )
            draft_path = evidence_dir / "l3-classify-ticket-reservation-rust-draft.rs"
            draft_path.write_text(
                draft,
                encoding="utf-8",
            )
            original_draft = draft_path.read_bytes()
            (evidence_dir / "l3-classify-ticket-reservation-auto-translation-plan.json").write_text(
                json.dumps(
                    {
                        "translation_summary": {
                            "translation_rule_ids": ["clang-lowered-typed-ir"],
                            "call_expressions": [{"callee": "reserve_ticket"}],
                        }
                    }
                ),
                encoding="utf-8",
            )
            replay = module.generate_rust_replay_test_draft(spec, evidence_dir, spec_path)
            rust_check, _ = module.run_rust_check(evidence_dir, False, spec)
            self.assertEqual(rust_check["status"], "passed")
            bindings = rust_check["rust_check_harness_only_bindings"]
            self.assertFalse(bindings["semantics_verified"])
            self.assertEqual(bindings["allowed_use"], "fixture_bound_rust_replay_only")
            self.assertEqual(bindings["bindings"][0]["fixture_only"], True)
            self.assertFalse(bindings["bindings"][0]["semantics_verified"])

            checked_draft = draft_path.read_text(encoding="utf-8")
            self.assertEqual(original_draft, draft_path.read_bytes())
            self.assertNotIn("std::thread_local!", checked_draft)
            self.assertNotIn("unsafe", checked_draft)
            replay = module.run_generated_rust_replay(spec, evidence_dir, replay, rust_check)
            self.assertEqual(replay["status"], "passed")
            self.assertTrue(replay["generated_draft_replay_pass"])
            self.assertFalse(replay["generated_draft_semantic_pass"])
            self.assertEqual(replay["fixture_external_stub"]["scope"], "fixture_only")
            self.assertFalse(replay["fixture_external_stub"]["semantics_verified"])
            recorded_commands = (
                rust_check["command"],
                replay["replay_execution"]["compile_command"],
                replay["replay_execution"]["run_command"],
            )
            for command in recorded_commands:
                self.assertNotIn(str(evidence_dir), command)
                self.assertNotIn("/tmp/", command)
                self.assertNotRegex(command, r"^[A-Za-z]:[\\/]")
            self.assertIn("<draft>", rust_check["command"])
            self.assertIn("<generated-replay.rs>", replay["replay_execution"]["compile_command"])

    def test_scripted_external_contract_fails_closed_on_matching_kind_drift(self) -> None:
        module = load_auto_migrate_module()
        invalid_specs: list[tuple[str, dict[str, Any], str]] = []

        extra_contract_field = self._scripted_external_bool_out_spec()
        extra_contract_field["replay_contract"]["unexpected"] = True
        invalid_specs.append(("shape", extra_contract_field, "contract shape drifted"))

        missing_output_field = self._scripted_external_bool_out_spec()
        del missing_output_field["fixture_contract"]["cases"][0]["expected_outputs"]["ticket_value"]
        invalid_specs.append(("missing-field", missing_output_field, "expected output fields drifted"))

        wrong_fixture_type = self._scripted_external_bool_out_spec()
        wrong_fixture_type["fixture_contract"]["cases"][0]["inputs"]["owner_token"] = "41"
        invalid_specs.append(("fixture-type", wrong_fixture_type, "u32 fixture input type drifted"))

        wrong_output_type = self._scripted_external_bool_out_spec()
        wrong_output_type["fixture_contract"]["cases"][0]["expected_outputs"][
            "reserve_call_count"
        ] = "1"
        invalid_specs.append(("output-type", wrong_output_type, "call count must be usize"))

        wrong_declared_type = self._scripted_external_bool_out_spec()
        wrong_declared_type["c_boundary"]["signatures"][1]["parameters"][2]["c_type"] = "uint32_t"
        invalid_specs.append(("signature-type", wrong_declared_type, "external parameter types drifted"))

        for label, spec, message in invalid_specs:
            with self.subTest(label=label):
                fixture_binding = module.oracle_fixture_binding(spec)
                with self.assertRaisesRegex(ValueError, message):
                    module.scripted_external_u32_call_bool_out_replay_contract(
                        spec,
                        fixture_binding,
                    )

    def test_replay_contract_helpers_do_not_preempt_other_kinds(self) -> None:
        module = load_auto_migrate_module()
        spec = self._scripted_external_bool_out_spec()
        fixture_binding = module.oracle_fixture_binding(spec)
        self.assertIsNone(module.record_pointer_identity_return_replay_contract(spec, fixture_binding))
        self.assertIsNone(module.readonly_byte_slice_bool_return_replay_contract(spec, fixture_binding))

        other = self._scripted_external_bool_out_spec()
        other["replay_contract"] = {
            "schema_version": 1,
            "kind": "some_future_contract",
        }
        other_binding = module.oracle_fixture_binding(other)
        self.assertIsNone(
            module.scripted_external_u32_call_bool_out_replay_contract(other, other_binding)
        )
        self.assertIsNone(module.record_pointer_identity_return_replay_contract(other, other_binding))
        self.assertIsNone(module.readonly_byte_slice_bool_return_replay_contract(other, other_binding))

        malformed_record = self._scripted_external_bool_out_spec()
        malformed_record["replay_contract"] = {"kind": "record_pointer_identity_return"}
        with self.assertRaisesRegex(ValueError, "schema_version must be 1"):
            module.record_pointer_identity_return_replay_contract(
                malformed_record,
                module.oracle_fixture_binding(malformed_record),
            )

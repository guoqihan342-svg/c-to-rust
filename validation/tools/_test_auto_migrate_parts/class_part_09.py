class _AutoMigrateTestsPart09:
    def _readonly_byte_slice_bool_spec(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "target_id": "synthetic-bytes",
            "slice_id": "printable-prefix",
            "level": "L3",
            "function_name": "printable_prefix",
            "source_commit": "synthetic-readonly-byte-slice-contract",
            "fixture_hash": "synthetic-printable-prefix-fixture",
            "fixture_contract": {
                "path": "inline-synthetic-printable-prefix.json",
                "behavior_fields": ["return_value"],
                "observable_outputs": ["return_value"],
                "cases": [
                    {
                        "id": "printable",
                        "input_ref": "inline",
                        "expected_ref": "inline",
                        "inputs": {"value": [32, 65, 126], "len": 3},
                        "expected_outputs": {"return_value": True},
                    },
                    {
                        "id": "control-byte",
                        "input_ref": "inline",
                        "expected_ref": "inline",
                        "inputs": {"value": [65, 31], "len": 2},
                        "expected_outputs": {"return_value": False},
                    },
                    {
                        "id": "ignored-tail",
                        "input_ref": "inline",
                        "expected_ref": "inline",
                        "inputs": {"value": [65, 0], "len": 1},
                        "expected_outputs": {"return_value": True},
                    },
                    {
                        "id": "empty",
                        "input_ref": "inline",
                        "expected_ref": "inline",
                        "inputs": {"value": [], "len": 0},
                        "expected_outputs": {"return_value": True},
                    },
                ],
            },
            "c_boundary": {
                "signatures": [
                    {
                        "function": "printable_prefix",
                        "return_type": "bool",
                        "parameters": [
                            {"name": "value", "c_type": "uint8_t *", "direction": "input"},
                            {"name": "len", "c_type": "size_t", "direction": "input"},
                        ],
                    }
                ],
                "pointer_contract": {
                    "input_buffers": [
                        {
                            "name": "value",
                            "c_type": "uint8_t *",
                            "mutability": "read_only",
                            "length_companion": "len",
                        }
                    ],
                    "output_pointers": [],
                    "aliasing_proven": True,
                    "noalias_required": [],
                },
            },
            "replay_contract": {
                "schema_version": 1,
                "kind": "readonly_byte_slice_bool_return",
                "input": {
                    "parameter": "value",
                    "fixture_field": "value",
                    "fixture_encoding": "u8_array",
                    "fixture_scalar_type": "u8",
                    "length_parameter": "len",
                    "length_field": "len",
                },
                "output": {"fixture_field": "return_value", "rust_type": "bool"},
            },
            "rust_boundary": {
                "public_api": [{"name": "printable_prefix"}],
                "raw_pointer_policy": "internal_only",
            },
        }

    def test_readonly_byte_slice_bool_contract_generates_generic_oracle_and_replay(self) -> None:
        module = load_auto_migrate_module()
        spec = self._readonly_byte_slice_bool_spec()
        fixture_binding = module.oracle_fixture_binding(spec)
        oracle = module.oracle_fixture_execution_source(spec, fixture_binding)
        self.assertIn("printable_prefix(printable_value, (size_t)3)", oracle["statements"])
        self.assertIn("static uint8_t empty_value[] = { 0 };", oracle["declarations"])
        self.assertNotIn("fdb_", oracle["statements"])

        draft = """\
pub fn printable_prefix(value: &[u8], len: usize) -> bool {
    for byte in &value[..len] {
        if !(((*byte as u32).wrapping_sub(' ' as u32)) < (127u32 - ' ' as u32)) {
            return false;
        }
    }
    true
}
"""
        with tempfile.TemporaryDirectory(prefix="auto-migrate-readonly-byte-replay-") as tmp:
            evidence_dir = Path(tmp)
            spec_path = evidence_dir / "printable-prefix.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            (evidence_dir / "l3-printable-prefix-rust-draft.rs").write_text(draft, encoding="utf-8")
            (evidence_dir / "l3-printable-prefix-auto-translation-plan.json").write_text(
                json.dumps({"translation_summary": {"translation_rule_ids": ["clang-lowered-typed-ir"]}}),
                encoding="utf-8",
            )
            replay = module.generate_rust_replay_test_draft(spec, evidence_dir, spec_path)
            replay = module.run_generated_rust_replay(spec, evidence_dir, replay, {"status": "passed"})
            replay_source = (
                evidence_dir / "l3-printable-prefix-rust-replay-test-draft.rs"
            ).read_text(encoding="utf-8")
            self.assertIn("// ReplayCallPlan-SHA256:", replay_source)
            self.assertIn("printable_prefix(&[65u8, 0u8], 1usize)", replay_source)
            self.assertNotIn("fdb_", replay_source)
            self.assertEqual(replay["status"], "passed")
            self.assertTrue(replay["generated_draft_replay_pass"])

    def test_readonly_byte_slice_bool_contract_fails_closed(self) -> None:
        module = load_auto_migrate_module()
        invalid_specs: list[tuple[str, dict[str, Any], str]] = []

        excessive_length = self._readonly_byte_slice_bool_spec()
        excessive_length["fixture_contract"]["cases"][0]["inputs"]["len"] = 4
        invalid_specs.append(("length", excessive_length, "length exceeds"))

        mutable_pointer = self._readonly_byte_slice_bool_spec()
        mutable_pointer["c_boundary"]["pointer_contract"]["input_buffers"][0]["mutability"] = "read_write"
        invalid_specs.append(("mutability", mutable_pointer, "read_only"))

        integer_expected = self._readonly_byte_slice_bool_spec()
        integer_expected["fixture_contract"]["cases"][0]["expected_outputs"]["return_value"] = 1
        invalid_specs.append(("bool", integer_expected, "must be bool"))

        wrong_length_type = self._readonly_byte_slice_bool_spec()
        wrong_length_type["c_boundary"]["signatures"][0]["parameters"][1]["c_type"] = "uint32_t"
        invalid_specs.append(("size_t", wrong_length_type, "size_t"))

        for label, spec, message in invalid_specs:
            with self.subTest(label=label):
                fixture_binding = module.oracle_fixture_binding(spec)
                with self.assertRaisesRegex(ValueError, message):
                    module.readonly_byte_slice_bool_return_replay_contract(spec, fixture_binding)

    def test_readonly_byte_slice_bool_contract_supports_declared_hex_fixtures(self) -> None:
        module = load_auto_migrate_module()
        spec = self._readonly_byte_slice_bool_spec()
        for case in spec["fixture_contract"]["cases"]:
            values = case["inputs"].pop("value")
            case["inputs"]["value_hex"] = bytes(values).hex()
        input_contract = spec["replay_contract"]["input"]
        input_contract["fixture_field"] = "value_hex"
        input_contract["fixture_encoding"] = "hex"

        fixture_binding = module.oracle_fixture_binding(spec)
        oracle = module.oracle_fixture_execution_source(spec, fixture_binding)
        replay = module.rust_replay_fixture_cases_source(spec, fixture_binding)

        self.assertIn("static uint8_t printable_value[] = { 32u, 65u, 126u };", oracle["declarations"])
        self.assertIn("printable_prefix(&[32u8, 65u8, 126u8], 3usize)", replay)

        spec["fixture_contract"]["cases"][0]["inputs"]["value_hex"] = "0xz1"
        with self.assertRaisesRegex(ValueError, "non-hex"):
            module.readonly_byte_slice_bool_return_replay_contract(
                spec,
                module.oracle_fixture_binding(spec),
            )

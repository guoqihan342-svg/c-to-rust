from __future__ import annotations

import copy
import json
from pathlib import Path
import tempfile
import unittest

from validation.tools.replay_call_plan import (
    build_replay_call_plan,
    render_declarative_replay_cases,
    replay_call_plan_marker,
    validate_replay_call_plan,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class ReplayCallPlanTests(unittest.TestCase):
    def test_buffer_length_plan_is_ordered_hash_bound_and_renderable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="replay-plan-") as tmp:
            root = Path(tmp)
            self.write_json(root / "fixture.json", [{"data_hex": "0102", "expected": 3}])
            spec = self.buffer_spec()

            plan = build_replay_call_plan(spec, root)

            self.assertEqual("bound", plan["status"])
            self.assertEqual("source_checksum", plan["source_function_name"])
            self.assertEqual("checksum", plan["api_name"])
            self.assertEqual(["seed", "data", "len"], [item["name"] for item in plan["parameters"]])
            self.assertEqual(["len"], plan["length_parameters_retained"])
            self.assertIn(plan["plan_sha256"], replay_call_plan_marker(plan))
            source = render_declarative_replay_cases(spec, plan, root)
            self.assertIn("checksum(1u32, &[1u8, 2u8], 2usize)", source)
            self.assertIn("let actual_case_0_0: u32 = checksum", source)
            self.assertIn(
                "if observed_case_0_0_0 != 3u32 { panic!(\"C2R_REPLAY_ASSERT:",
                source,
            )
            self.assertNotIn("case-0 expected drifted", source)

    def test_output_pointer_can_be_declared_as_return_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="replay-report-") as tmp:
            root = Path(tmp)
            self.write_json(root / "input.json", {"cases": [{"ip": "127.0.0.1", "port": 80}]})
            self.write_json(root / "oracle.json", {"cases": [{"code": 0, "family": 2}]})
            spec = self.report_spec()

            plan = build_replay_call_plan(spec, root)

            self.assertEqual("bound", plan["status"])
            self.assertEqual(["addr"], plan["omitted_c_parameters"])
            source = render_declarative_replay_cases(spec, plan, root)
            self.assertIn('parse_addr("127.0.0.1", 80i32)', source)
            self.assertIn("actual_loopback_0.family", source)

    def test_function_rename_changes_data_not_adapter_selection(self) -> None:
        with tempfile.TemporaryDirectory(prefix="replay-rename-") as tmp:
            root = Path(tmp)
            self.write_json(root / "fixture.json", [{"data_hex": "", "expected": 1}])
            spec = self.buffer_spec()
            spec["function_name"] = "renamed_source"
            spec["c_boundary"]["signatures"][0]["function"] = "renamed_source"
            spec["rust_boundary"]["public_api"][0]["name"] = "renamed_api"

            plan = build_replay_call_plan(spec, root)

            self.assertEqual("bound", plan["status"])
            self.assertEqual("renamed_source", plan["source_function_name"])
            self.assertEqual("renamed_api", plan["api_name"])

    def test_unclosed_c_mapping_and_path_escape_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="replay-blocked-") as tmp:
            root = Path(tmp)
            self.write_json(root / "fixture.json", [{"data_hex": "", "expected": 1}])
            missing = self.buffer_spec()
            missing["replay_contract"]["rust_api"]["parameters"].pop()
            escaped = self.buffer_spec()
            escaped["fixture_contract"]["path"] = "../outside.json"

            self.assertEqual("blocked", build_replay_call_plan(missing, root)["status"])
            self.assertEqual("blocked", build_replay_call_plan(escaped, root)["status"])

    def test_plan_sha_and_assertion_path_tampering_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="replay-tamper-") as tmp:
            root = Path(tmp)
            self.write_json(root / "fixture.json", [{"data_hex": "", "expected": 1}])
            plan = build_replay_call_plan(self.buffer_spec(), root)
            tampered = copy.deepcopy(plan)
            tampered["api_name"] = "other"
            with self.assertRaisesRegex(ValueError, "sha256 drifted"):
                validate_replay_call_plan(tampered)
            mapping_drift = copy.deepcopy(plan)
            mapping_drift["c_parameter_mappings"][0]["rust_parameter"] = "other"
            with self.assertRaisesRegex(ValueError, "mappings drifted"):
                validate_replay_call_plan(mapping_drift)
            case_drift = copy.deepcopy(plan)
            case_drift["fixture"]["case_ids"] = []
            with self.assertRaisesRegex(ValueError, "case identities"):
                validate_replay_call_plan(case_drift)
            injected = self.buffer_spec()
            injected["replay_contract"]["assertions"][0]["actual"] = "return); panic!("
            self.assertEqual("blocked", build_replay_call_plan(injected, root)["status"])

    def test_zero_argument_api_is_supported(self) -> None:
        with tempfile.TemporaryDirectory(prefix="replay-zero-arg-") as tmp:
            root = Path(tmp)
            self.write_json(root / "fixture.json", [{"expected": 7}])
            spec = self.buffer_spec()
            spec["c_boundary"]["signatures"][0]["parameters"] = []
            spec["replay_contract"]["rust_api"]["parameters"] = []
            spec["fixture_contract"]["cases"][0]["inputs"] = {}
            spec["fixture_contract"]["cases"][0]["expected_outputs"] = {"expected": 7}

            plan = build_replay_call_plan(spec, root)

            self.assertEqual("bound", plan["status"])
            self.assertEqual([], plan["parameters"])
            source = render_declarative_replay_cases(spec, plan, root)
            self.assertIn("checksum()", source)

    def test_symbolic_fixture_reference_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="replay-symlink-") as tmp:
            root = Path(tmp)
            target = root / "fixture.json"
            link = root / "fixture-link.json"
            self.write_json(target, [{"data_hex": "", "expected": 1}])
            try:
                link.symlink_to(target)
            except OSError as exc:
                self.skipTest(f"symbolic links unavailable: {exc}")
            spec = self.buffer_spec()
            spec["fixture_contract"]["path"] = link.name

            plan = build_replay_call_plan(spec, root)

            self.assertEqual("blocked", plan["status"])
            self.assertIn("symbolic", plan["reason"])

    def test_readonly_byte_slice_semantic_contract_normalizes_without_name_dispatch(self) -> None:
        spec = self.load_repo_spec("flashdb-real-fdb-is-str.json")
        original = spec["function_name"]
        spec["function_name"] = "renamed_source"
        spec["c_boundary"]["signatures"][0]["function"] = "renamed_source"
        spec["rust_boundary"]["public_api"][0]["name"] = "renamed_api"

        plan = build_replay_call_plan(spec, REPO_ROOT)

        self.assertEqual("bound", plan["status"])
        self.assertEqual("renamed_source", plan["source_function_name"])
        self.assertEqual("renamed_api", plan["api_name"])
        self.assertEqual(["value", "len"], [item["name"] for item in plan["parameters"]])
        self.assertEqual(["len"], plan["length_parameters_retained"])
        source = render_declarative_replay_cases(spec, plan, REPO_ROOT)
        self.assertIn("renamed_api(&[], 0usize)", source)
        self.assertNotIn(original + "(", source)

    def test_crc32_declarative_contract_accepts_json_byte_array(self) -> None:
        spec = self.load_repo_spec("flashdb-real-fdb-calc-crc32.json")

        plan = build_replay_call_plan(spec, REPO_ROOT)

        self.assertEqual("bound", plan["status"])
        self.assertEqual(["crc", "buf", "size"], [item["name"] for item in plan["parameters"]])
        source = render_declarative_replay_cases(spec, plan, REPO_ROOT)
        self.assertIn("fdb_calc_crc32(0u32, &[], 0usize)", source)
        self.assertIn("49u8, 50u8, 51u8", source)
        self.assertIn("3421780262u32", source)

    @staticmethod
    def write_json(path: Path, value: object) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def load_repo_spec(filename: str) -> dict:
        return json.loads(
            (REPO_ROOT / "validation" / "slice-specs" / filename).read_text(
                encoding="utf-8"
            )
        )

    @staticmethod
    def buffer_spec() -> dict:
        return {
            "function_name": "source_checksum",
            "c_boundary": {
                "signatures": [
                    {
                        "function": "source_checksum",
                        "return_type": "uint32_t",
                        "parameters": [
                            {"name": "seed", "c_type": "uint32_t", "direction": "input"},
                            {"name": "data", "c_type": "const uint8_t *", "direction": "input"},
                            {"name": "len", "c_type": "size_t", "direction": "input"},
                        ],
                    }
                ]
            },
            "rust_boundary": {"public_api": [{"name": "checksum"}]},
            "fixture_contract": {
                "path": "fixture.json",
                "cases": [
                    {
                        "id": "case-0",
                        "input_ref": "cases[0]",
                        "inputs": {"seed": 1, "data_hex": "0102"},
                        "expected_outputs": {"expected": 3},
                    }
                ],
                "observable_outputs": ["expected"],
            },
            "replay_contract": {
                "schema_version": 3,
                "kind": "declarative_call_plan",
                "rust_api": {
                    "visibility": "pub",
                    "abi": "Rust",
                    "unsafe": False,
                    "parameters": [
                        {
                            "name": "seed",
                            "rust_type": "u32",
                            "c_parameter": "seed",
                            "length_retained": False,
                            "source": {"kind": "fixture_field", "field": "seed", "encoding": "u32"},
                        },
                        {
                            "name": "data",
                            "rust_type": "&[u8]",
                            "c_parameter": "data",
                            "length_retained": False,
                            "source": {"kind": "fixture_field", "field": "data_hex", "encoding": "hex_bytes"},
                        },
                        {
                            "name": "len",
                            "rust_type": "usize",
                            "c_parameter": "len",
                            "length_retained": True,
                            "source": {"kind": "encoded_length", "field": "data_hex", "encoding": "hex"},
                        },
                    ],
                    "return_type": "u32",
                    "supporting_types": [],
                },
                "omitted_c_parameters": [],
                "assertions": [
                    {"actual": "return", "fixture_field": "expected", "rust_type": "u32", "encoding": "u32"}
                ],
            },
        }

    @staticmethod
    def report_spec() -> dict:
        return {
            "function_name": "source_parse_addr",
            "c_boundary": {
                "signatures": [
                    {
                        "function": "source_parse_addr",
                        "return_type": "int",
                        "parameters": [
                            {"name": "ip", "c_type": "const char *", "direction": "input"},
                            {"name": "port", "c_type": "int", "direction": "input"},
                            {"name": "addr", "c_type": "struct addr *", "direction": "output"},
                        ],
                    }
                ]
            },
            "rust_boundary": {"public_api": [{"name": "parse_addr"}]},
            "fixture_contract": {
                "path": "input.json",
                "cases": [{"id": "loopback", "input_ref": "cases[0]", "expected_ref": "oracle.json"}],
                "observable_outputs": ["code", "family"],
            },
            "replay_contract": {
                "schema_version": 3,
                "kind": "declarative_call_plan",
                "rust_api": {
                    "visibility": "pub",
                    "abi": "Rust",
                    "unsafe": False,
                    "parameters": [
                        {"name": "ip", "rust_type": "&str", "c_parameter": "ip", "length_retained": False, "source": {"kind": "fixture_field", "field": "ip", "encoding": "string"}},
                        {"name": "port", "rust_type": "i32", "c_parameter": "port", "length_retained": False, "source": {"kind": "fixture_field", "field": "port", "encoding": "i32"}},
                    ],
                    "return_type": "AddrReport",
                    "supporting_types": [{"kind": "struct", "name": "AddrReport", "visibility": "pub", "fields": [{"name": "code", "rust_type": "i32"}, {"name": "family", "rust_type": "u16"}]}],
                },
                "omitted_c_parameters": ["addr"],
                "assertions": [
                    {"actual": "return.code", "fixture_field": "code", "rust_type": "i32", "encoding": "i32"},
                    {"actual": "return.family", "fixture_field": "family", "rust_type": "u16", "encoding": "u16"},
                ],
            },
        }


if __name__ == "__main__":
    unittest.main()

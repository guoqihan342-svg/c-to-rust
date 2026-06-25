import json
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"


def load_auto_migrate_module():
    spec = importlib.util.spec_from_file_location("auto_migrate_under_test", AUTO_MIGRATE)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load auto_migrate module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AutoMigrateTests(unittest.TestCase):
    def test_generates_candidate_without_claiming_semantic_pass(self) -> None:
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            out_root = Path(tmp) / "evidence"
            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(REPO_ROOT / "validation" / "slice-specs" / "zlib-adler32-step.json"),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
            self.assertEqual(manifest["source_commit"], "d40f29fd42ed9158e3eb3e221dca50e4b627f7a8")
            self.assertEqual(manifest["fixture"]["hash"], "zlib-adler32-fixture")
            self.assertEqual(manifest["oracle"]["status"], "SKIPPED_LOCAL_NO_C_TOOLCHAIN")
            self.assertEqual(manifest["oracle"]["fixture"], "validation/l2_slices/fixtures/zlib-adler32-c-oracle.json")
            self.assertEqual(manifest["replay"]["fixture"], "validation/l2_slices/fixtures/zlib-adler32-c-oracle.json")
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertTrue(
                (out_root / "zlib-ng" / "auto-translation" / "adler32-step" / "l3-adler32-step-type-map.json").exists()
            )

    def test_compound_and_increment_translation_flows_through_auto_migrate(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "compound-inc-dec",
            "source_commit": "1234567",
            "function_name": "compound_inc_dec",
            "c_source": "int compound_inc_dec(int value) { value += 1; value++; --value; return value; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "compound-inc-dec.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "compound-inc-dec"
            draft = (evidence_dir / "l3-compound-inc-dec-rust-draft.rs").read_text(encoding="utf-8")
            plan = json.loads(
                (evidence_dir / "l3-compound-inc-dec-auto-translation-plan.json").read_text(encoding="utf-8")
            )
            cfg = json.loads((evidence_dir / "l3-compound-inc-dec-cfg.json").read_text(encoding="utf-8"))
            statement_kinds = cfg["functions"][0]["basic_blocks"][0]["statement_kinds"]

            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertIn("value += 1;", draft)
            self.assertIn("value -= 1;", draft)
            self.assertIn("compound-assignment", plan["translation_summary"]["translation_rule_ids"])
            self.assertIn("increment-decrement", plan["translation_summary"]["translation_rule_ids"])
            self.assertIn("compound_assignment", statement_kinds)
            self.assertIn("inc_dec", statement_kinds)

    def test_call_expression_evidence_flows_through_auto_migrate(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "call-expression",
            "source_commit": "1234567",
            "function_name": "call_expression",
            "c_source": "int call_expression(int value) { int first = call_expression(value); value = call_expression(first); return call_expression(value); }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "call-expression.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "call-expression"
            plan = json.loads(
                (evidence_dir / "l3-call-expression-auto-translation-plan.json").read_text(
                    encoding="utf-8"
                )
            )
            cfg = json.loads((evidence_dir / "l3-call-expression-cfg.json").read_text(encoding="utf-8"))
            context_pack = json.loads(
                (evidence_dir / "l3-call-expression-context-pack.json").read_text(encoding="utf-8")
            )

            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertIn("call_expression", cfg["functions"][0]["basic_blocks"][0]["statement_kinds"])
            self.assertIn("bounded-call-expression", plan["translation_summary"]["translation_rule_ids"])
            self.assertEqual(len(plan["translation_summary"]["call_expressions"]), 3)
            self.assertEqual(plan["translation_summary"]["call_expressions"][0]["callee"], "call_expression")
            self.assertEqual(
                context_pack["direct_call_edges"][0],
                {
                    "callee": "call_expression",
                    "arguments": ["value"],
                    "source_expression": "call_expression(value)",
                    "statement_context": "declaration_initializer",
                },
            )

    def test_declared_external_callee_context_allows_helper_rust_check(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "external-callee",
            "source_commit": "1234567",
            "function_name": "call_helper_chain",
            "c_source": (
                "int call_helper_chain(int value) { "
                "int first = helper_add_one(value); "
                "value = helper_add_one(first); "
                "return helper_add_one(value); "
                "}"
            ),
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "c_boundary": {
                "files": [
                    {"path": "unit/caller.c", "role": "slice_entry", "sha256": "caller-sha"},
                    {"path": "unit/helper.c", "role": "external_direct_callee", "sha256": "helper-sha"},
                ],
                "signatures": [
                    {
                        "id": "sig-call-helper-chain",
                        "function": "call_helper_chain",
                        "return_type": "int",
                        "parameters": [{"name": "value", "c_type": "int"}],
                        "c_source": (
                            "int call_helper_chain(int value) { "
                            "int first = helper_add_one(value); "
                            "value = helper_add_one(first); "
                            "return helper_add_one(value); "
                            "}"
                        ),
                    },
                    {
                        "id": "sig-helper-add-one",
                        "role": "external_direct_callee",
                        "function": "helper_add_one",
                        "return_type": "int",
                        "parameters": [{"name": "value", "c_type": "int"}],
                        "source_ref": "unit/helper.c#helper_add_one",
                        "signature_sha256": "helper-signature-sha",
                        "definition_status": "real_source_bound",
                        "c_source": "int helper_add_one(int value) { return value + 1; }",
                    },
                ],
                "direct_dependencies": [
                    {"kind": "callee", "name": "helper_add_one", "source": "unit/helper.c#helper_add_one"}
                ],
                "external_direct_callees": [
                    {
                        "name": "helper_add_one",
                        "signature_ref": "sig-helper-add-one",
                        "source_files": [{"path": "unit/helper.c", "sha256": "helper-sha"}],
                        "definition_status": "real_source_bound",
                        "stub_boundary": "compile_only",
                    }
                ],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "external-callee.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "external-callee"
            draft = (evidence_dir / "l3-external-callee-rust-draft.rs").read_text(encoding="utf-8")
            plan = json.loads(
                (evidence_dir / "l3-external-callee-auto-translation-plan.json").read_text(encoding="utf-8")
            )
            context_pack = json.loads(
                (evidence_dir / "l3-external-callee-context-pack.json").read_text(encoding="utf-8")
            )

            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertIn("fn helper_add_one(value: i32) -> i32", draft)
            self.assertIn("external callee context stub: helper_add_one", draft)
            external_callee = plan["translation_summary"]["external_direct_callees"][0]
            self.assertEqual(external_callee["name"], "helper_add_one")
            self.assertEqual(external_callee["signature_ref"], "sig-helper-add-one")
            self.assertEqual(external_callee["stub_kind"], "compile_only")
            self.assertFalse(external_callee["semantics_verified"])
            self.assertEqual(len(plan["translation_summary"]["call_expressions"]), 3)
            self.assertEqual(
                plan["translation_summary"]["call_expressions"][0]["callee_signature_id"],
                "sig-helper-add-one",
            )
            self.assertEqual(plan["inputs"]["external_callee_context"]["status"], "recorded")
            self.assertEqual(plan["inputs"]["external_callee_context"]["declared_count"], 1)
            self.assertEqual(plan["inputs"]["external_callee_context"]["blocked_count"], 0)
            self.assertEqual(context_pack["external_direct_callees"][0]["name"], "helper_add_one")
            self.assertEqual(context_pack["external_direct_callees"][0]["stub_kind"], "compile_only")
            self.assertFalse(context_pack["external_direct_callees"][0]["semantics_verified"])
            self.assertEqual(context_pack["call_edge_to_callee_binding"][0]["callee"], "helper_add_one")
            self.assertEqual(
                manifest["claim_boundary"]["external_callee_scope"]["status"],
                "compile_context_only",
            )
            self.assertFalse(manifest["claim_boundary"]["generated_draft_semantic_pass"])

    def test_undeclared_external_callee_context_blocks_silent_stub_injection(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "missing-external-callee",
            "source_commit": "1234567",
            "function_name": "call_missing_helper",
            "c_source": (
                "int call_missing_helper(int value) { "
                "int first = helper_add_one(value); "
                "return helper_add_one(first); "
                "}"
            ),
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "missing-external-callee.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "missing-external-callee"
            draft = (evidence_dir / "l3-missing-external-callee-rust-draft.rs").read_text(encoding="utf-8")
            plan = json.loads(
                (evidence_dir / "l3-missing-external-callee-auto-translation-plan.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertEqual(manifest["rust_check"]["status"], "failed")
            self.assertNotIn("fn helper_add_one", draft)
            self.assertEqual(
                manifest["rust_check"]["external_callee_context"]["status"],
                "blocked",
            )
            self.assertEqual(
                manifest["rust_check"]["external_callee_context"]["blocked_callees"][0]["name"],
                "helper_add_one",
            )
            self.assertEqual(plan["inputs"]["external_callee_context"]["status"], "blocked")
            self.assertEqual(plan["inputs"]["external_callee_context"]["declared_count"], 0)
            self.assertEqual(plan["inputs"]["external_callee_context"]["blocked_count"], 1)
            self.assertEqual(
                plan["translation_summary"]["external_direct_callee_blocks"][0]["reason"],
                "missing_declared_external_direct_callee",
            )

    def test_pointer_index_lvalue_decision_flows_through_auto_migrate(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "fill-first",
            "source_commit": "1234567",
            "function_name": "fill_first",
            "c_source": "int fill_first(int* out, int value) { out[0] = value; return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "fill-first.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "fill-first"
            cfg = json.loads((evidence_dir / "l3-fill-first-cfg.json").read_text(encoding="utf-8"))
            pointer_graph = json.loads((evidence_dir / "l3-fill-first-pointer-graph.json").read_text(encoding="utf-8"))
            plan = json.loads((evidence_dir / "l3-fill-first-auto-translation-plan.json").read_text(encoding="utf-8"))
            block = cfg["functions"][0]["basic_blocks"][0]

            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertIn("bounded_pointer_index", block["lvalue_kinds"])
            self.assertTrue(
                any(decision["decision"] == "bounded_pointer_index" for decision in block["lvalue_decisions"])
            )
            self.assertTrue(
                any(
                    decision["decision"] == "bounded_pointer_index"
                    for decision in pointer_graph["pointer_decisions"]
                )
            )
            out_node = next(node for node in pointer_graph["pointer_nodes"] if node["id"] == "out")
            self.assertIn("out[0]", out_node["write_effects"])
            self.assertIn("bounded_pointer_index", out_node["boundary_decisions"])
            self.assertIn("bounded-pointer-index-write", plan["translation_summary"]["translation_rule_ids"])
            self.assertEqual(plan["translation_summary"]["lvalue_decision_counts"]["bounded_pointer_index"], 1)
            self.assertEqual(
                plan["translation_summary"]["pointer_boundary_decision_counts"]["bounded_pointer_index"], 1
            )

    def test_input_buffer_pointer_decision_flows_through_auto_migrate(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "sum-i32-buffer",
            "source_commit": "1234567",
            "function_name": "sum_i32_buffer",
            "c_source": "int sum_i32_buffer(const int* values, int len, int* out) { int total = 0; for (int i = 0; i < len; i++) { total = total + values[i]; } out[0] = total; return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["return_code", "status", "sum"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "sum-i32-buffer.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "sum-i32-buffer"
            cfg = json.loads((evidence_dir / "l3-sum-i32-buffer-cfg.json").read_text(encoding="utf-8"))
            pointer_graph = json.loads(
                (evidence_dir / "l3-sum-i32-buffer-pointer-graph.json").read_text(encoding="utf-8")
            )
            plan = json.loads(
                (evidence_dir / "l3-sum-i32-buffer-auto-translation-plan.json").read_text(encoding="utf-8")
            )
            block = cfg["functions"][0]["basic_blocks"][0]

            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertFalse(manifest["claim_boundary"]["semantic_pass"])
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertIn("bounded_input_buffer_read", block["statement_kinds"])
            self.assertTrue(
                any(decision["decision"] == "bounded_input_buffer" for decision in block["lvalue_decisions"])
            )
            self.assertTrue(
                any(
                    decision["decision"] == "bounded_input_buffer"
                    for decision in pointer_graph["pointer_decisions"]
                )
            )
            values_node = next(node for node in pointer_graph["pointer_nodes"] if node["id"] == "values")
            self.assertEqual(values_node["kind"], "buffer")
            self.assertEqual(values_node["buffer_role"], "input")
            self.assertEqual(values_node["length_companion"], "len")
            self.assertEqual(values_node["ownership_role"], "borrowed")
            self.assertEqual(values_node["mutability"], "read_only")
            self.assertIn("values[i]", values_node["read_effects"])
            self.assertIn("bounded_input_buffer", values_node["boundary_decisions"])
            out_node = next(node for node in pointer_graph["pointer_nodes"] if node["id"] == "out")
            self.assertIn("out[0]", out_node["write_effects"])
            self.assertIn("bounded-input-buffer-read", plan["translation_summary"]["translation_rule_ids"])
            self.assertEqual(plan["translation_summary"]["lvalue_decision_counts"]["bounded_input_buffer"], 1)
            self.assertEqual(
                plan["translation_summary"]["pointer_boundary_decision_counts"]["bounded_input_buffer"], 1
            )

    def test_pointer_arithmetic_input_read_flows_through_auto_migrate(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "sum-i32-ptr-arith",
            "source_commit": "1234567",
            "function_name": "sum_i32_ptr_arith",
            "c_source": "int sum_i32_ptr_arith(const int* values, int len, int* out) { int total = 0; for (int i = 0; i < len; i++) { total = total + *(values + i); } out[0] = total; return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["return_code", "status", "sum"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "sum-i32-ptr-arith.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "sum-i32-ptr-arith"
            cfg = json.loads((evidence_dir / "l3-sum-i32-ptr-arith-cfg.json").read_text(encoding="utf-8"))
            pointer_graph = json.loads(
                (evidence_dir / "l3-sum-i32-ptr-arith-pointer-graph.json").read_text(encoding="utf-8")
            )
            plan = json.loads(
                (evidence_dir / "l3-sum-i32-ptr-arith-auto-translation-plan.json").read_text(
                    encoding="utf-8"
                )
            )
            block = cfg["functions"][0]["basic_blocks"][0]

            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertIn("bounded_input_buffer_read", block["statement_kinds"])
            self.assertIn("bounded_pointer_arithmetic_input_read", block["statement_kinds"])
            self.assertIn("bounded_pointer_arithmetic_input_buffer", block["lvalue_kinds"])
            self.assertTrue(
                any(
                    decision["decision"] == "bounded_pointer_arithmetic_input_read"
                    and decision["translation_rule_id"] == "bounded-pointer-arithmetic-input-read"
                    for decision in block["lvalue_decisions"]
                )
            )
            self.assertTrue(
                any(
                    decision["decision"] == "bounded_pointer_arithmetic_input_read"
                    and decision["translation_rule_id"] == "bounded-pointer-arithmetic-input-read"
                    for decision in pointer_graph["pointer_decisions"]
                )
            )
            values_node = next(node for node in pointer_graph["pointer_nodes"] if node["id"] == "values")
            self.assertIn("values[i]", values_node["read_effects"])
            self.assertIn("*(values + i)", values_node["read_effects"])
            self.assertIn("bounded_input_buffer", values_node["boundary_decisions"])
            self.assertIn("bounded_pointer_arithmetic_input_read", values_node["boundary_decisions"])
            self.assertIn("bounded-input-buffer-read", plan["translation_summary"]["translation_rule_ids"])
            self.assertIn(
                "bounded-pointer-arithmetic-input-read",
                plan["translation_summary"]["translation_rule_ids"],
            )
            self.assertEqual(
                plan["translation_summary"]["lvalue_decision_counts"][
                    "bounded_pointer_arithmetic_input_read"
                ],
                1,
            )
            self.assertEqual(
                plan["translation_summary"]["pointer_boundary_decision_counts"][
                    "bounded_pointer_arithmetic_input_read"
                ],
                1,
            )

    def test_pointer_arithmetic_output_write_flows_through_auto_migrate(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "fill-i32-ptr-arith-out",
            "source_commit": "1234567",
            "function_name": "fill_i32_ptr_arith_out",
            "c_source": "int fill_i32_ptr_arith_out(int* out, int len, int value) { for (int i = 0; i < len; i++) { *(out + i) = value; } return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["return_code", "status", "out_values"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "fill-i32-ptr-arith-out.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "fill-i32-ptr-arith-out"
            cfg = json.loads((evidence_dir / "l3-fill-i32-ptr-arith-out-cfg.json").read_text(encoding="utf-8"))
            pointer_graph = json.loads(
                (evidence_dir / "l3-fill-i32-ptr-arith-out-pointer-graph.json").read_text(
                    encoding="utf-8"
                )
            )
            plan = json.loads(
                (
                    evidence_dir / "l3-fill-i32-ptr-arith-out-auto-translation-plan.json"
                ).read_text(encoding="utf-8")
            )
            rust_draft = (evidence_dir / "l3-fill-i32-ptr-arith-out-rust-draft.rs").read_text(
                encoding="utf-8"
            )
            block = cfg["functions"][0]["basic_blocks"][0]

            self.assertEqual(manifest["status"], "candidate_generated")
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertIn("out: &mut [i32]", rust_draft)
            self.assertIn("out[i as usize] = value;", rust_draft)
            self.assertIn("bounded_pointer_arithmetic_output_write", block["statement_kinds"])
            self.assertIn("bounded_pointer_arithmetic_output_buffer", block["lvalue_kinds"])
            self.assertTrue(
                any(
                    decision["decision"] == "bounded_pointer_arithmetic_output_write"
                    and decision["translation_rule_id"] == "bounded-pointer-arithmetic-output-write"
                    for decision in block["lvalue_decisions"]
                )
            )
            self.assertTrue(
                any(
                    decision["decision"] == "bounded_pointer_arithmetic_output_write"
                    and decision["translation_rule_id"] == "bounded-pointer-arithmetic-output-write"
                    for decision in pointer_graph["pointer_decisions"]
                )
            )
            out_node = next(node for node in pointer_graph["pointer_nodes"] if node["id"] == "out")
            self.assertEqual(out_node["kind"], "buffer")
            self.assertEqual(out_node["buffer_role"], "output")
            self.assertEqual(out_node["length_companion"], "len")
            self.assertEqual(out_node["ownership_role"], "out_param")
            self.assertEqual(out_node["mutability"], "write_only")
            self.assertIn("out[i]", out_node["write_effects"])
            self.assertIn("*(out + i)", out_node["write_effects"])
            self.assertIn("bounded_pointer_arithmetic_output_write", out_node["boundary_decisions"])
            self.assertIn(
                "bounded-pointer-arithmetic-output-write",
                plan["translation_summary"]["translation_rule_ids"],
            )
            self.assertEqual(
                plan["translation_summary"]["lvalue_decision_counts"][
                    "bounded_pointer_arithmetic_output_write"
                ],
                1,
            )
            self.assertEqual(
                plan["translation_summary"]["pointer_boundary_decision_counts"][
                    "bounded_pointer_arithmetic_output_write"
                ],
                1,
            )

    def test_alias_sensitive_read_write_pointer_gate_flows_through_auto_migrate(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "copy-i32-alias-gate",
            "source_commit": "1234567",
            "function_name": "copy_i32_alias_gate",
            "c_source": "int copy_i32_alias_gate(const int* values, int len, int* out) { for (int i = 0; i < len; i++) { *(out + i) = *(values + i); } return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "c_boundary": {
                "pointer_contract": {
                    "input_buffers": [
                        {
                            "name": "values",
                            "c_type": "const int*",
                            "length_companion": "len",
                            "read_effects": ["*(values + i)", "values[i]"],
                        }
                    ],
                    "output_pointers": [
                        {
                            "name": "out",
                            "c_type": "int*",
                            "length_companion": "len",
                            "write_effects": ["*(out + i)", "out[i]"],
                        }
                    ],
                    "aliasing_proven": False,
                }
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["return_code", "status", "out_values"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "copy-i32-alias-gate.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "copy-i32-alias-gate"
            pointer_graph = json.loads(
                (evidence_dir / "l3-copy-i32-alias-gate-pointer-graph.json").read_text(encoding="utf-8")
            )
            plan = json.loads(
                (evidence_dir / "l3-copy-i32-alias-gate-auto-translation-plan.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertIn("alias_sensitive_state", pointer_graph["applicability"]["triggers"])
            self.assertEqual(pointer_graph["alias_sets"][0]["id"], "alias-set-1")
            self.assertEqual(pointer_graph["alias_sets"][0]["members"], ["values", "out"])
            self.assertEqual(pointer_graph["alias_sets"][0]["relationship"], "unknown_overlap")
            self.assertEqual(
                pointer_graph["alias_sets"][0]["evidence"],
                "c_boundary.pointer_contract.aliasing_proven=false",
            )
            self.assertEqual(pointer_graph["alias_contract"]["decision"], "requires_noalias_contract")
            self.assertFalse(pointer_graph["alias_contract"]["proven"])
            self.assertTrue(pointer_graph["alias_contract"]["requires_noalias"])
            self.assertEqual(pointer_graph["alias_risks"][0]["risk_level"], "unknown_alias")
            self.assertEqual(pointer_graph["alias_risks"][0]["gate_decision"], "requires_noalias_contract")
            self.assertIn("values", pointer_graph["alias_risks"][0]["pointer_nodes"])
            self.assertIn("out", pointer_graph["alias_risks"][0]["pointer_nodes"])
            self.assertTrue(
                any(
                    item["kind"] == "noalias"
                    and item["applies_to"] == ["values", "out"]
                    and item["required"]
                    for item in pointer_graph["safe_boundary_preconditions"]
                )
            )
            self.assertEqual(
                plan["translation_summary"]["alias_gate"]["decision"],
                "requires_noalias_contract",
            )
            self.assertEqual(
                manifest["claim_boundary"]["alias_gate"]["decision"],
                "requires_noalias_contract",
            )
            self.assertFalse(manifest["claim_boundary"]["alias_gate"]["complete_alias_safety"])

    def test_output_only_pointer_write_does_not_trigger_input_output_alias_risk(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "fill-i32-output-only",
            "source_commit": "1234567",
            "function_name": "fill_i32_output_only",
            "c_source": "int fill_i32_output_only(int* out, int len, int value) { for (int i = 0; i < len; i++) { *(out + i) = value; } return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["return_code", "status", "out_values"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "fill-i32-output-only.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "fill-i32-output-only"
            pointer_graph = json.loads(
                (evidence_dir / "l3-fill-i32-output-only-pointer-graph.json").read_text(encoding="utf-8")
            )
            plan = json.loads(
                (evidence_dir / "l3-fill-i32-output-only-auto-translation-plan.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertNotIn("alias_sensitive_state", pointer_graph["applicability"]["triggers"])
            self.assertEqual(pointer_graph["alias_sets"], [])
            self.assertEqual(pointer_graph["alias_risks"], [])
            self.assertEqual(pointer_graph["alias_contract"]["decision"], "not_applicable")
            self.assertFalse(pointer_graph["alias_contract"]["requires_noalias"])
            self.assertEqual(plan["translation_summary"]["alias_gate"]["decision"], "not_applicable")
            self.assertEqual(manifest["claim_boundary"]["alias_gate"]["decision"], "not_applicable")

    def test_cache_identity_tracks_alias_gate_inputs(self) -> None:
        auto_migrate = load_auto_migrate_module()
        spec = {
            "target_id": "demo",
            "slice_id": "copy-i32-alias-cache",
            "source_commit": "1234567",
            "function_name": "copy_i32_alias_cache",
            "c_source": "int copy_i32_alias_cache(const int* values, int len, int* out) { for (int i = 0; i < len; i++) { *(out + i) = *(values + i); } return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {"target_triple": "x86_64-unknown-linux-gnu"},
            "c_boundary": {
                "pointer_contract": {
                    "input_buffers": [
                        {
                            "name": "values",
                            "c_type": "const int*",
                            "length_companion": "len",
                            "read_effects": ["*(values + i)", "values[i]"],
                        }
                    ],
                    "output_pointers": [
                        {
                            "name": "out",
                            "c_type": "int*",
                            "length_companion": "len",
                            "write_effects": ["*(out + i)", "out[i]"],
                        }
                    ],
                    "aliasing_proven": False,
                }
            },
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            spec_path = Path(tmp) / "copy-i32-alias-cache.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")

            identity = auto_migrate.cache_identity(spec, spec_path)

            self.assertIn("alias_gate_identity", identity)
            self.assertEqual(identity["alias_gate_identity"]["decision"], "requires_noalias_contract")
            self.assertEqual(identity["alias_gate_identity"]["risk_count"], 1)
            self.assertFalse(identity["alias_gate_identity"]["aliasing_proven"])
            self.assertTrue(identity["alias_gate_identity"]["requires_noalias"])

    def test_unsupported_lvalue_blocks_auto_migrate_candidate_generation(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "unbounded-index",
            "source_commit": "1234567",
            "function_name": "unbounded_index",
            "c_source": "int unbounded_index(int* out, int i, int value) { out[i] = value; return 0; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "unbounded-index.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            evidence_dir = out_root / "demo" / "auto-translation" / "unbounded-index"
            cfg = json.loads((evidence_dir / "l3-unbounded-index-cfg.json").read_text(encoding="utf-8"))
            plan = json.loads(
                (evidence_dir / "l3-unbounded-index-auto-translation-plan.json").read_text(encoding="utf-8")
            )
            block = cfg["functions"][0]["basic_blocks"][0]

            self.assertEqual(manifest["translator"]["status"], "blocked")
            self.assertEqual(plan["status"], "blocked")
            self.assertEqual(plan["translation_summary"]["unsupported_lvalue_count"], 1)
            self.assertIn("unsupported_lvalue", block["lvalue_kinds"])
            self.assertTrue(
                any(decision["decision"] == "unsupported_lvalue" for decision in block["lvalue_decisions"])
            )

    def test_compile_failure_records_blocked_patch_evidence(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "bad-syntax",
            "source_commit": "1234567",
            "function_name": "bad_syntax",
            "c_source": "int bad_syntax(int value) { return value + ; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "bad-syntax.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["rust_check"]["status"], "failed")
            self.assertEqual(manifest["patch"]["status"], "blocked")
            blocked_path = out_root / "demo" / "auto-translation" / "bad-syntax" / "l3-bad-syntax-self-healing-blocked-repairs.json"
            blocked = json.loads(blocked_path.read_text(encoding="utf-8"))
            self.assertEqual(blocked["status"], "recorded")
            self.assertEqual(blocked["blocked_repairs"][0]["candidate_patch_id"], "patch-blocked-1")
            self.assertTrue(blocked["blocked_repairs"][0]["human_action_required"])

    def test_keyword_identifier_compile_failure_is_self_healed(self) -> None:
        spec = {
            "target_id": "demo",
            "slice_id": "keyword-param",
            "source_commit": "1234567",
            "function_name": "keyword_param",
            "c_source": "int keyword_param(int match) { return match + 1; }",
            "fixture_hash": "fixture",
            "build_profile": {
                "include_paths": [],
                "defines": [],
                "target_triple": "x86_64-unknown-linux-gnu",
                "abi": "linux-gnu",
                "compiler_command_source": "unit-test",
                "clang_available": True,
            },
            "fixture_contract": {
                "input": "unit-test-fixture.json",
                "behavior_fields": ["value"],
            },
            "non_goals": ["unit test only"],
        }
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            tmp_path = Path(tmp)
            spec_path = tmp_path / "keyword-param.json"
            spec_path.write_text(json.dumps(spec), encoding="utf-8")
            out_root = tmp_path / "evidence"

            result = subprocess.run(
                [
                    "python",
                    str(AUTO_MIGRATE),
                    "--slice-spec",
                    str(spec_path),
                    "--out-root",
                    str(out_root),
                    "--skip-c-oracle",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=True,
            )

            manifest = json.loads(result.stdout)
            self.assertEqual(manifest["rust_check"]["status"], "passed")
            self.assertEqual(manifest["patch"]["status"], "recorded")
            patch_events = (
                out_root
                / "demo"
                / "auto-translation"
                / "keyword-param"
                / "l3-keyword-param-patch-events.jsonl"
            ).read_text(encoding="utf-8")
            self.assertIn('"status": "verified"', patch_events)
            draft = (
                out_root
                / "demo"
                / "auto-translation"
                / "keyword-param"
                / "l3-keyword-param-rust-draft.rs"
            ).read_text(encoding="utf-8")
            self.assertIn("r#match", draft)

    def test_cache_drift_invalidates_reusable_translation_artifacts(self) -> None:
        auto_migrate = load_auto_migrate_module()
        previous = {
            "source_commit": "source-a",
            "source_file_hashes": {"src/file.c": "hash-a"},
            "slice_spec_sha256": "slice-a",
            "fixture_hash": "fixture-a",
            "build_profile_hash": "profile-a",
            "cargo_lock_hash": "lock-a",
            "tool_versions": {"rustc": "rustc-a"},
            "schema_versions": {"cfg": 1},
            "translator_version": "0.1.0",
            "translator_manifest_sha256": "manifest-a",
            "command_arguments": ["auto_migrate.py", "--slice-spec", "slice.json"],
            "alias_gate_identity": {
                "decision": "not_applicable",
                "risk_count": 0,
                "aliasing_proven": False,
                "requires_noalias": False,
            },
        }

        reusable = auto_migrate.cache_drift_report(previous, dict(previous))

        self.assertEqual(reusable["status"], "reusable")
        self.assertTrue(reusable["reuse_allowed"])
        self.assertEqual(reusable["invalidated_artifacts"], [])

        current = dict(previous)
        current["source_commit"] = "source-b"
        current["build_profile_hash"] = "profile-b"
        current["fixture_hash"] = "fixture-b"
        current["source_file_hashes"] = {"src/file.c": "hash-b"}
        current["alias_gate_identity"] = {
            "decision": "requires_noalias_contract",
            "risk_count": 1,
            "aliasing_proven": False,
            "requires_noalias": True,
        }

        drifted = auto_migrate.cache_drift_report(previous, current)

        self.assertEqual(drifted["status"], "drift_detected")
        self.assertFalse(drifted["reuse_allowed"])
        self.assertIn("source_commit", drifted["drifted_keys"])
        self.assertIn("source_file_hashes", drifted["drifted_keys"])
        self.assertIn("fixture_hash", drifted["drifted_keys"])
        self.assertIn("build_profile_hash", drifted["drifted_keys"])
        self.assertIn("alias_gate_identity", drifted["drifted_keys"])
        for artifact in [
            "context_pack",
            "type_map",
            "cfg",
            "pointer_graph",
            "rust_draft",
            "patch_plan",
            "rust_replay",
            "c_oracle",
            "diff",
            "negative_diff",
            "unsafe_ledger",
            "final_verification",
            "summary",
        ]:
            self.assertIn(artifact, drifted["invalidated_artifacts"])

    def test_accept_existing_evidence_requires_c_oracle_marker(self) -> None:
        auto_migrate = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            spec = self._accepted_evidence_spec(Path(tmp), include_toolchain_marker=False)

            with self.assertRaises(SystemExit) as raised:
                auto_migrate.resolve_accepted_evidence(spec)

            self.assertIn("toolchain_status=C_ORACLE_GENERATED", str(raised.exception))

    def test_accept_existing_evidence_binding_keeps_generated_draft_candidate(self) -> None:
        auto_migrate = load_auto_migrate_module()
        with tempfile.TemporaryDirectory(prefix="auto-migrate-test-") as tmp:
            spec = self._accepted_evidence_spec(Path(tmp), include_toolchain_marker=True)

            accepted = auto_migrate.resolve_accepted_evidence(spec)
            summary = auto_migrate.accepted_binding_summary(accepted)

            self.assertEqual(accepted["status"], "accepted")
            self.assertEqual(accepted["toolchain_status"], "C_ORACLE_GENERATED")
            self.assertFalse(accepted["generated_draft_semantic_pass"])
            self.assertFalse(summary["generated_draft_semantic_pass"])
            self.assertEqual(summary["paths"]["c_oracle"], accepted["paths"]["c_oracle"])

    def _accepted_evidence_spec(self, root: Path, include_toolchain_marker: bool) -> dict:
        fixture = root / "fixture.json"
        c_oracle = root / "c-oracle.json"
        rust_report = root / "rust-report.json"
        diff = root / "diff.json"
        negative = root / "negative-diff.json"
        unsafe_scan = root / "unsafe-scan.json"
        unsafe_ledger = root / "unsafe-ledger.json"
        fixture.write_text("[]\n", encoding="utf-8")
        oracle_payload = {
            "status": "passed",
            "source_commit": "1234567",
            "case_count": 1,
            "slice_id": "demo-slice",
        }
        if include_toolchain_marker:
            oracle_payload["toolchain_status"] = "C_ORACLE_GENERATED"
        c_oracle.write_text(json.dumps(oracle_payload), encoding="utf-8")
        rust_report.write_text(
            json.dumps({"status": "passed", "source_commit": "1234567", "case_count": 1}),
            encoding="utf-8",
        )
        diff.write_text(
            json.dumps({"status": "passed", "source_commit": "1234567", "first_mismatch": None}),
            encoding="utf-8",
        )
        negative.write_text(
            json.dumps({"status": "expected_failed", "source_commit": "1234567", "mutation_detected": True}),
            encoding="utf-8",
        )
        unsafe_scan.write_text(
            json.dumps({"status": "passed", "source_commit": "1234567", "first_party_non_test_unsafe_count": 0}),
            encoding="utf-8",
        )
        unsafe_ledger.write_text(
            json.dumps({"status": "passed", "source_commit": "1234567", "first_party_non_test_unsafe_count": 0}),
            encoding="utf-8",
        )
        return {
            "target_id": "demo",
            "slice_id": "demo-slice",
            "source_commit": "1234567",
            "fixture_hash": "fixture-hash",
            "fixture_contract": {
                "path": str(fixture),
                "c_oracle": str(c_oracle),
                "rust_report": str(rust_report),
                "diff": str(diff),
                "negative_diff": str(negative),
                "unsafe_scan": str(unsafe_scan),
                "unsafe_ledger": str(unsafe_ledger),
                "behavior_fields": ["value"],
            },
        }


if __name__ == "__main__":
    unittest.main()

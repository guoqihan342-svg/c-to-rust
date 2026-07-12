from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import jsonschema

from validation.tools import ai_candidate_harness, auto_migrate
from validation.tools._ai_candidate_harness_parts.context_replay import (
    build_replay_api_contract,
    replay_contract_input_binding,
    validate_replay_api_contract_binding,
)
from validation.tools._ai_candidate_harness_parts.context_required_api import (
    build_required_candidate_api,
    validate_required_candidate_api,
)
from validation.tools._ai_candidate_harness_parts.provider_readiness import (
    replay_api_contract_status,
)
from validation.tools.replay_call_plan import (
    build_replay_call_plan,
    replay_call_plan_marker,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


class RequiredCandidateApiTests(unittest.TestCase):
    def test_record_identity_api_binds_return_lifetime_and_supporting_types(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-tsl-to-blob.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        plan = build_replay_call_plan(spec, REPO_ROOT)

        contract = build_required_candidate_api(plan)

        self.assertEqual("bound", contract["status"])
        self.assertEqual(plan["plan_sha256"], contract["plan_sha256"])
        self.assertEqual("blob", contract["return_lifetime_from"])
        self.assertEqual(
            "pub fn fdb_tsl_to_blob<'out>(tsl: &FdbTsl, blob: &'out mut FdbBlob) -> &'out mut FdbBlob",
            contract["signature"],
        )
        self.assertIn("pub struct FdbTslAddr", contract["supporting_types_source"])
        self.assertIn("pub log: u32", contract["supporting_types_source"])
        self.assertIn("pub struct FdbBlob", contract["supporting_types_source"])

    def test_generic_renamed_plan_has_no_project_or_function_dispatch(self) -> None:
        plan = {
            "api_name": "transfer_packet",
            "visibility": "pub(crate)",
            "abi": "Rust",
            "unsafe": False,
            "parameters": [
                {
                    "name": "source",
                    "rust_type": "&SourcePacket",
                    "source": {"kind": "binding_borrow", "binding": "source"},
                },
                {
                    "name": "target",
                    "rust_type": "&mut TargetPacket",
                    "source": {"kind": "binding_borrow_mut", "binding": "target"},
                },
            ],
            "return_type": "&mut TargetPacket",
            "identity_assertions": [
                {
                    "actual": "return",
                    "expected_binding": "target",
                    "mutability": "mutable",
                }
            ],
            "supporting_types": [
                {
                    "kind": "struct",
                    "name": "TargetPacket",
                    "visibility": "pub(crate)",
                    "fields": [{"name": "count", "rust_type": "usize"}],
                }
            ],
            "plan_sha256": "a" * 64,
        }

        contract = build_required_candidate_api(plan)

        self.assertEqual(
            "pub(crate) fn transfer_packet<'out>(source: &SourcePacket, target: &'out mut TargetPacket) -> &'out mut TargetPacket",
            contract["signature"],
        )
        self.assertNotIn("fdb", json.dumps(contract).lower())

    def test_c_abi_and_unsafe_are_explicit(self) -> None:
        plan = {
            "api_name": "translate_word",
            "visibility": "pub",
            "abi": "C",
            "unsafe": True,
            "parameters": [
                {
                    "name": "value",
                    "rust_type": "u32",
                    "source": {"kind": "fixture_field", "field": "value"},
                }
            ],
            "return_type": "u32",
            "supporting_types": [],
            "plan_sha256": "b" * 64,
        }

        contract = build_required_candidate_api(plan)

        self.assertEqual(
            'pub unsafe extern "C" fn translate_word(value: u32) -> u32',
            contract["signature"],
        )
        self.assertIsNone(contract["return_lifetime_from"])

    def test_reference_return_without_identity_fails_closed(self) -> None:
        plan = {
            "api_name": "ambiguous",
            "visibility": "pub",
            "abi": "Rust",
            "unsafe": False,
            "parameters": [
                {"name": "left", "rust_type": "&mut Item", "source": {"binding": "left"}},
                {"name": "right", "rust_type": "&mut Item", "source": {"binding": "right"}},
            ],
            "return_type": "&mut Item",
            "supporting_types": [],
            "plan_sha256": "c" * 64,
        }

        with self.assertRaisesRegex(ValueError, "identity assertion"):
            build_required_candidate_api(plan)

    def test_replay_contract_recomputes_required_api_binding(self) -> None:
        spec_path = REPO_ROOT / "validation" / "slice-specs" / "flashdb-real-fdb-kv-to-blob.json"
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        plan = build_replay_call_plan(spec, REPO_ROOT)
        with tempfile.TemporaryDirectory(prefix="required-candidate-api-") as tmp:
            root = Path(tmp)
            replay_path = root / "l3-generic-rust-replay-test-draft.rs"
            replay_path.write_text(
                replay_call_plan_marker(plan)
                + "fn replay(kv: &FdbKv, blob: &mut FdbBlob) { let _ = fdb_kv_to_blob(kv, blob); }\n",
                encoding="utf-8",
            )
            contract = build_replay_api_contract(
                replay_path,
                function_name="fdb_kv_to_blob",
                trusted_root=root,
                expected_filename=replay_path.name,
                call_plan=plan,
            )
            context = {
                "schema_version": 4,
                "slice_id": "generic",
                "function_name": "fdb_kv_to_blob",
                "replay_api_contract": contract,
                "bindings": {
                    "inputs": [replay_contract_input_binding(contract)],
                },
            }
            context_path = root / "ai-context-pack.json"

            self.assertEqual(3, contract["schema_version"])
            self.assertEqual("bound", validate_replay_api_contract_binding(context, context_path))
            self.assertEqual("bound", replay_api_contract_status(context))
            validate_required_candidate_api(plan, contract["required_candidate_api"])

            contract["required_candidate_api"]["signature"] += " /* drift */"
            self.assertEqual("invalid", replay_api_contract_status(context))
            self.assertEqual(
                "binding_mismatch",
                validate_replay_api_contract_binding(context, context_path),
            )

    def test_real_context_pack_schema_binds_compact_api(self) -> None:
        schema = json.loads(
            (
                REPO_ROOT
                / "validation"
                / "auto-translation-template"
                / "ai-context-pack.schema.json"
            ).read_text(encoding="utf-8")
        )
        source_root = REPO_ROOT / "sources" / "FlashDB"
        for filename, signature_fragment in (
            (
                "flashdb-real-fdb-tsl-to-blob.json",
                "blob: &'out mut FdbBlob) -> &'out mut FdbBlob",
            ),
            (
                "flashdb-real-fdb-kv-set.json",
                "db: &KvDbFixture, key: &str, value: Option<&str>) -> i32",
            ),
        ):
            with self.subTest(filename=filename):
                spec_path = REPO_ROOT / "validation" / "slice-specs" / filename
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
                with tempfile.TemporaryDirectory(prefix="required-api-context-") as tmp:
                    replay_root = Path(tmp)
                    replay_path = auto_migrate.write_rust_replay_test_draft_source(
                        spec,
                        replay_root,
                    )
                    context = ai_candidate_harness.build_context_pack(
                        spec_path,
                        source_root=source_root,
                        replay_test_path=replay_path,
                        replay_root=replay_root,
                    )

                jsonschema.Draft7Validator(schema).validate(context)
                replay_contract = context["replay_api_contract"]
                required_api = replay_contract["required_candidate_api"]
                self.assertEqual(3, replay_contract["schema_version"])
                self.assertIn(signature_fragment, required_api["signature"])
                self.assertEqual(
                    replay_contract["call_plan"]["plan_sha256"],
                    required_api["plan_sha256"],
                )


if __name__ == "__main__":
    unittest.main()

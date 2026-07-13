from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest

import jsonschema

from validation.tools import ai_candidate_harness
from validation.tools._ai_candidate_harness_parts.context_callees import (
    build_external_callee_source_context,
    callee_source_input_bindings,
)
from validation.tools._ai_candidate_harness_parts.context_compiler_headers import (
    is_compiler_header_candidate,
)
from validation.tools._ai_candidate_harness_parts.context_scope import (
    prompt_scope_for_context,
)
from validation.tools._ai_candidate_harness_parts.provider_readiness_callees import (
    external_callee_source_context_status,
)


def declaration_spec(
    name: str = "rotate_word",
    header: str = "machine/rotate.h",
    signature_id: str = "sig-rotate-word",
) -> dict[str, object]:
    source_ref = f"compiler-header:{header}#{name}"
    return {
        "c_boundary": {
            "signatures": [{
                "id": signature_id,
                "role": "external_direct_callee",
                "function": name,
                "definition_status": "declared_external_direct_callee",
                "source_ref": source_ref,
                "return_type": "unsigned int",
                "parameters": [{"name": "value", "c_type": "unsigned int"}],
            }],
            "external_direct_callees": [{
                "name": name,
                "signature_ref": signature_id,
                "definition_status": "declared_external_direct_callee",
                "source_ref": source_ref,
                "header_files": [header],
                "stub_boundary": "compile_only",
            }],
        },
    }


def build_context(spec: dict[str, object]) -> dict[str, object]:
    return build_external_callee_source_context(
        spec,
        source_root=None,
        known_roots=(),
    )


def readiness_pack(spec: dict[str, object], context: dict[str, object]) -> dict[str, object]:
    return {
        "c_boundary": {
            "required_callee_sections": ["external_direct_callees"],
            "payload": copy.deepcopy(spec["c_boundary"]),
        },
        "external_callee_source_context": context,
        "bindings": {"inputs": []},
    }


class AiCompilerHeaderDeclarationTests(unittest.TestCase):
    def test_repository_declaration_with_compile_only_boundary_is_not_reclassified(self) -> None:
        self.assertFalse(is_compiler_header_candidate({
            "definition_status": "declared_external_direct_callee",
            "source_ref": "src/helpers.c#rotate_word",
            "stub_boundary": "compile_only",
        }))

    def test_renamed_declarations_are_compile_context_only(self) -> None:
        identities = (
            ("rotate_word", "machine/rotate.h", "sig-rotate-word"),
            ("fold_octet", "vendor/bytes/fold.hpp", "sig-fold-octet"),
        )
        for name, header, signature_id in identities:
            with self.subTest(name=name):
                spec = declaration_spec(name, header, signature_id)
                context = build_context(spec)

                self.assertEqual("bound", context["status"])
                self.assertEqual([], context["blocks"])
                self.assertEqual([], context["blocked"])
                declaration = context["declarations"][0]
                self.assertEqual(name, declaration["callee"])
                self.assertEqual(header, declaration["header"])
                self.assertEqual("compile_context_only", declaration["allowed_use"])
                self.assertFalse(declaration["execution_allowed"])
                self.assertEqual([], callee_source_input_bindings(context))
                self.assertIn("compiler_header_declarations", prompt_scope_for_context({
                    "external_callee_source_context": context,
                }))
                self.assertEqual(
                    "ready",
                    external_callee_source_context_status(readiness_pack(spec, context)),
                )

    def test_namespace_header_symbol_signature_and_boundary_drift_fail_closed(self) -> None:
        mutations = {
            "compiler_header_definition_status_invalid": lambda c, s: c.update(
                definition_status="real_source_bound"
            ),
            "compiler_header_namespace_invalid": lambda c, s: c.update(
                source_ref=c["source_ref"].replace("compiler-header:", "Compiler-Header:")
            ),
            "compiler_header_source_ref_invalid": lambda c, s: c.update(
                source_ref=c["source_ref"] + "#extra"
            ),
            "compiler_header_path_invalid": lambda c, s: c.update(
                source_ref="compiler-header:../machine/rotate.h#rotate_word"
            ),
            "compiler_header_symbol_mismatch": lambda c, s: c.update(
                source_ref="compiler-header:machine/rotate.h#other_word"
            ),
            "compiler_header_inventory_missing": lambda c, s: c.pop("header_files"),
            "compiler_header_inventory_mismatch": lambda c, s: c.update(
                header_files=["machine/other.h"]
            ),
            "compiler_header_inventory_invalid": lambda c, s: c.update(
                header_files=["machine\\rotate.h"]
            ),
            "compiler_header_signature_ref_missing": lambda c, s: c.pop("signature_ref"),
            "compiler_header_signature_ref_ambiguous": lambda c, s: c.update(
                signature_ref="unknown-signature"
            ),
            "compiler_header_signature_mismatch": lambda c, s: s.update(function="other_word"),
            "compiler_header_stub_boundary_invalid": lambda c, s: c.update(
                stub_boundary="runtime_stub"
            ),
        }
        for reason, mutate in mutations.items():
            with self.subTest(reason=reason):
                spec = declaration_spec()
                callee = spec["c_boundary"]["external_direct_callees"][0]
                signature = spec["c_boundary"]["signatures"][0]
                mutate(callee, signature)

                context = build_context(spec)

                self.assertEqual([], context["declarations"])
                self.assertEqual(reason, context["blocked"][0]["reason"])
                self.assertNotEqual(
                    "ready",
                    external_callee_source_context_status(readiness_pack(spec, context)),
                )
                self.assertNotIn(
                    "repository_source_path_required",
                    {item["reason"] for item in context["blocked"]},
                )

    def test_readiness_recomputes_declaration_and_rejects_source_block(self) -> None:
        spec = declaration_spec()
        context = build_context(spec)
        for mutate in (
            lambda value: value["declarations"][0].update(declaration_sha256="0" * 64),
            lambda value: value.update(declarations=[]),
            lambda value: value["blocks"].append({"callee": "rotate_word"}),
        ):
            with self.subTest(mutate=mutate):
                drifted = copy.deepcopy(context)
                mutate(drifted)
                self.assertEqual(
                    "invalid",
                    external_callee_source_context_status(readiness_pack(spec, drifted)),
                )

    def test_real_mixed_context_has_declaration_and_repository_source_separately(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        spec_path = repo_root / "validation/slice-specs/libuv-ip4-addr.json"
        context_pack = ai_candidate_harness.build_context_pack(
            spec_path,
            source_root=repo_root / "sources/libuv",
        )
        context = context_pack["external_callee_source_context"]

        self.assertEqual(["__bswap_16"], [item["callee"] for item in context["declarations"]])
        self.assertEqual(["uv_inet_pton"], [item["callee"] for item in context["blocks"]])
        self.assertNotIn(
            "repository_source_path_required",
            {item["reason"] for item in context["blocked"]},
        )
        self.assertEqual("ready", external_callee_source_context_status(context_pack))
        source_binding_names = {
            item.get("name")
            for item in context_pack["bindings"]["inputs"]
            if item.get("kind") == "external_callee_source"
        }
        self.assertNotIn("__bswap_16", source_binding_names)

        schema = json.loads((
            repo_root / "validation/auto-translation-template/ai-context-pack.schema.json"
        ).read_text(encoding="utf-8"))
        jsonschema.Draft7Validator(
            schema["properties"]["external_callee_source_context"]
        ).validate(context)

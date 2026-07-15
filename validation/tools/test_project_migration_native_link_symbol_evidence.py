from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.build_ir import stable_build_id
from validation.tools._project_migration_harness.native_link_actual_resolution import (
    resolve_traced_native_artifacts,
)
from validation.tools._project_migration_harness.native_link_symbol_evidence import (
    build_native_link_symbol_evidence,
    validate_native_link_symbol_evidence,
)
from validation.tools._project_migration_harness.native_object_symbols import (
    extract_native_object_symbols,
)
from validation.tools._project_migration_harness.native_symbol_model import (
    build_native_symbol_candidate,
)
from validation.tools.project_migration_native_link_actual_test_support import (
    NativeLinkActualTestCase,
    trace,
)
from validation.tools.project_migration_native_object_archive_test_support import (
    ar_member, archive,
)
from validation.tools.project_migration_native_object_symbols_test_support import (
    Symbol, elf_object,
)


class NativeLinkSymbolEvidenceTests(NativeLinkActualTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.exports = {}
        self.reports = {}
        trace_values = []
        for index, requirement in enumerate(self.context["requirements"]):
            identifier = requirement["requirement_id"]
            exported = f"generic_export_{index}"
            self.exports[identifier] = exported
            if requirement["library_format"] == "shared-library":
                data = elf_object(
                    64, "little", object_type=3,
                    tables=[("dynsym", [Symbol(exported)])],
                )
                guest = f"/usr/lib/{requirement['portable_name']}.7"
                trace_value: str | tuple[str, str] = guest
            else:
                obj = elf_object(
                    64, "little", object_type=1,
                    tables=[("symtab", [Symbol(exported)])],
                )
                data = archive(ar_member("object.o/", obj))
                guest = f"/lib64/{requirement['portable_name']}"
                trace_value = (guest, "object.o")
            host = self._write_guest(guest, data)
            self.reports[identifier] = extract_native_object_symbols(host)
            trace_values.append(trace_value)
        self.link_trace = trace(*trace_values)
        self.actual = resolve_traced_native_artifacts(
            self.link_trace, self.context, self.candidate,
            guest_roots=self.roots,
        )
        self.symbol_context = _symbol_context(
            self.context, self.candidate, self.exports,
        )
        self.response = _symbol_response(self.symbol_context, self.exports)
        self.symbol_candidate = build_native_symbol_candidate(
            self.symbol_context, self.response,
        )

    def evidence(
        self, symbol_candidate: dict | None = None,
        reports: dict | None = None,
        symbol_context: dict | None = None,
    ) -> dict:
        return build_native_link_symbol_evidence(
            self.link_trace, self.context, self.candidate, self.actual,
            self.symbol_context if symbol_context is None else symbol_context,
            self.symbol_candidate if symbol_candidate is None else symbol_candidate,
            self.reports if reports is None else reports,
        )

    def test_exact_ai_assignment_and_real_exports_pass(self) -> None:
        result = self.evidence()
        self.assertEqual("passed", result["status"])
        self.assertTrue(result["symbol_gate"])
        self.assertTrue(all(item["status"] == "passed" for item in result["checks"]))
        self.assertEqual(
            result,
            validate_native_link_symbol_evidence(
                result, self.link_trace, self.context, self.candidate,
                self.actual, self.symbol_context, self.symbol_candidate,
                self.reports,
            ),
        )

    def test_wrong_native_assignment_runtime_and_defer_stay_blocked(self) -> None:
        requirement_ids = list(self.exports)
        wrong = copy.deepcopy(self.response)
        first_assignment = next(
            item for item in wrong["assignments"]
            if item["requirement_id"] == requirement_ids[0]
        )
        first_assignment["requirement_id"] = requirement_ids[1]
        wrong_candidate = build_native_symbol_candidate(
            self.symbol_context, wrong,
        )
        self.assertFalse(self.evidence(wrong_candidate)["symbol_gate"])

        for provider_kind in ("runtime", "defer"):
            response = copy.deepcopy(self.response)
            response["assignments"][0].update({
                "provider_kind": provider_kind, "requirement_id": None,
            })
            candidate = build_native_symbol_candidate(
                self.symbol_context, response,
            )
            with self.subTest(provider_kind=provider_kind):
                self.assertFalse(self.evidence(candidate)["symbol_gate"])

    def test_report_object_binding_and_evidence_tamper_fail_closed(self) -> None:
        identifiers = list(self.reports)
        swapped = dict(self.reports)
        swapped[identifiers[0]] = self.reports[identifiers[1]]
        with self.assertRaisesRegex(ValueError, "object_drift"):
            self.evidence(reports=swapped)

        valid = self.evidence()
        tampered = copy.deepcopy(valid)
        tampered["symbol_gate"] = False
        with self.assertRaisesRegex(ValueError, "evidence_invalid"):
            validate_native_link_symbol_evidence(
                tampered, self.link_trace, self.context, self.candidate,
                self.actual, self.symbol_context, self.symbol_candidate,
                self.reports,
            )

    def test_no_imported_symbols_is_explicitly_not_required(self) -> None:
        no_symbols = _symbol_context(self.context, self.candidate, {})
        result = build_native_link_symbol_evidence(
            self.link_trace, self.context, self.candidate, self.actual,
            no_symbols, None, {},
        )
        self.assertEqual("not-required", result["status"])
        self.assertTrue(result["symbol_gate"])
        self.assertEqual([], result["checks"])

    def test_missing_ai_symbol_candidate_is_explicitly_blocked(self) -> None:
        result = build_native_link_symbol_evidence(
            self.link_trace, self.context, self.candidate, self.actual,
            self.symbol_context, None, self.reports,
        )
        self.assertEqual("blocked", result["status"])
        self.assertFalse(result["symbol_gate"])
        self.assertTrue(result["checks"])
        self.assertEqual(
            {"native_symbol_candidate_missing"},
            {item["reason_code"] for item in result["checks"]},
        )


def _symbol_context(context: dict, candidate: dict, exports: dict[str, str]) -> dict:
    symbols = []
    for requirement_id, link_name in exports.items():
        identity = {"link_name": link_name, "abi": "C"}
        symbols.append({
            "symbol_id": stable_build_id("native-symbol", identity),
            **identity,
            "declaration_count": 1,
            "declaration_set_sha256": content_sha256([
                f"declaration:{requirement_id}",
            ]),
        })
    symbols.sort(key=lambda item: item["symbol_id"])
    proposals = {item["requirement_id"]: item for item in candidate["proposals"]}
    providers = [{
        "requirement_id": item["requirement_id"],
        "portable_name": item["portable_name"],
        "library_format": item["library_format"],
        "strategy": proposals[item["requirement_id"]]["strategy"],
        "rustc_link_name": proposals[item["requirement_id"]]["rustc_link_name"],
        "rustc_link_kind": proposals[item["requirement_id"]]["rustc_link_kind"],
    } for item in context["requirements"]]
    result = {
        "schema_version": 1,
        "artifact_kind": "native-symbol-model-context",
        "status": "planning-required" if symbols else "not-required",
        "profile": context["profile"],
        "bindings": {
            "rust_project_ir_sha256": content_sha256("rust-project-ir"),
            "native_link_context_sha256": context["context_sha256"],
            "native_link_candidate_sha256": candidate["candidate_sha256"],
        },
        "symbols": symbols,
        "symbol_count": len(symbols),
        "providers": providers,
        "provider_count": len(providers),
        "model_policy": {
            "input_scope": "grouped-rust-ffi-imports-and-native-requirements",
            "allowed_provider_kinds": ["defer", "native-requirement", "runtime"],
            "exact_symbol_coverage_required": True,
            "invented_symbols_allowed": False,
            "model_may_claim_resolved": False,
        },
        "claim_boundary": {
            "artifact_role": "native-symbol-planning-context",
            "symbol_assignments_resolved": False,
            "native_exports_verified": False,
            "semantic_gate": False,
            "translation_coverage_numerator": 0,
        },
    }
    result["context_sha256"] = content_sha256(result)
    return result


def _symbol_response(context: dict, exports: dict[str, str]) -> dict:
    by_name = {item["link_name"]: item["symbol_id"] for item in context["symbols"]}
    return {
        "schema_version": 1,
        "artifact_kind": "native-symbol-model-response",
        "context_sha256": context["context_sha256"],
        "assignments": [{
            "symbol_id": by_name[link_name],
            "provider_kind": "native-requirement",
            "requirement_id": requirement_id,
        } for requirement_id, link_name in exports.items()],
    }


if __name__ == "__main__":
    unittest.main()

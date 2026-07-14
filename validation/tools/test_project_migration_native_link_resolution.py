from __future__ import annotations

import copy
import unittest

from validation.tools._project_migration_harness.artifacts import content_sha256
from validation.tools._project_migration_harness.build_ir import stable_build_id
from validation.tools._project_migration_harness.native_link_model import (
    build_native_link_candidate,
)
from validation.tools._project_migration_harness.native_link_resolution import (
    NATIVE_LINK_HOST_EVIDENCE_KIND, NATIVE_LINK_RESOLUTION_ISSUER,
    build_native_link_resolution_receipt,
    native_link_resolution_receipt_sha256,
    reopen_native_link_resolution_receipt,
    validate_native_link_resolution_receipt,
)


class NativeLinkResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.context = self._context(("alpha", "shared-library"), ("beta", "static-archive"))
        response = {
            "schema_version": 1,
            "artifact_kind": "native-link-model-response",
            "context_sha256": self.context["context_sha256"],
            "proposals": [{
                "requirement_id": item["requirement_id"],
                "strategy": "rustc-link-lib",
                "rustc_link_name": item["portable_name"],
                "rustc_link_kind": (
                    "static" if item["library_format"] == "static-archive" else "dylib"
                ),
            } for item in self.context["requirements"]],
        }
        self.candidate = build_native_link_candidate(self.context, response)
        self.evidence = self._evidence()

    def test_resolved_receipt_round_trips_and_binds_every_input(self) -> None:
        receipt = build_native_link_resolution_receipt(
            self.context, self.candidate, self.evidence,
        )
        reopened = reopen_native_link_resolution_receipt(
            receipt, self.context, self.candidate, self.evidence,
        )
        self.assertEqual("resolved", reopened["status"])
        self.assertTrue(all(item["status"] == "resolved" for item in reopened["resolutions"]))
        self.assertEqual(self.context["context_sha256"], reopened["context_sha256"])
        self.assertEqual(self.candidate["candidate_sha256"], reopened["candidate_sha256"])
        self.assertEqual(self.evidence["project_input_sha256"], reopened["project_input_sha256"])
        self.assertEqual(content_sha256(self.evidence), reopened["host_evidence_sha256"])
        self.assertFalse(reopened["semantic_gate"])
        self.assertEqual(
            native_link_resolution_receipt_sha256(reopened), reopened["receipt_sha256"],
        )

    def test_missing_extra_and_duplicate_requirement_evidence_are_rejected(self) -> None:
        cases = []
        missing = copy.deepcopy(self.evidence)
        missing["requirements"].pop()
        cases.append(missing)
        extra = copy.deepcopy(self.evidence)
        extra["requirements"].append({
            **copy.deepcopy(extra["requirements"][0]),
            "requirement_id": "native-link-requirement-" + "f" * 24,
        })
        cases.append(extra)
        duplicate = copy.deepcopy(self.evidence)
        duplicate["requirements"][1] = copy.deepcopy(duplicate["requirements"][0])
        cases.append(duplicate)
        for evidence in cases:
            with self.subTest(count=len(evidence["requirements"])):
                with self.assertRaisesRegex(ValueError, "coverage"):
                    build_native_link_resolution_receipt(
                        self.context, self.candidate, evidence,
                    )

    def test_absolute_parent_and_windows_paths_are_rejected(self) -> None:
        paths = ("/host/lib/libalpha.so", "../escape/libalpha.so", "C:\\host\\alpha.lib")
        for path in paths:
            evidence = copy.deepcopy(self.evidence)
            evidence["requirements"][0]["actual_artifact"]["artifact"]["path"] = path
            with self.subTest(path=path):
                with self.assertRaisesRegex(ValueError, "reference"):
                    build_native_link_resolution_receipt(
                        self.context, self.candidate, evidence,
                    )

    def test_cargo_success_alone_cannot_resolve_any_requirement(self) -> None:
        gates = ("toolchain", "abi", "linker_trace", "actual_artifact")
        for gate in gates:
            evidence = copy.deepcopy(self.evidence)
            evidence["requirements"][0][gate]["status"] = "failed"
            if gate == "actual_artifact":
                evidence["requirements"][0][gate]["artifact"] = None
                evidence["requirements"][0][gate]["portable_metadata"] = None
            receipt = build_native_link_resolution_receipt(
                self.context, self.candidate, evidence,
            )
            with self.subTest(gate=gate):
                self.assertEqual("rejected", receipt["status"])
                self.assertEqual("rejected", receipt["resolutions"][0]["status"])
        blocked = copy.deepcopy(self.evidence)
        blocked["requirements"][0]["abi"]["status"] = "blocked"
        self.assertEqual(
            "blocked",
            build_native_link_resolution_receipt(
                self.context, self.candidate, blocked,
            )["status"],
        )

    def test_toolchain_abi_cargo_link_trace_and_artifact_sha_drift_fail_reopen(self) -> None:
        receipt = build_native_link_resolution_receipt(
            self.context, self.candidate, self.evidence,
        )
        mutations = (
            ("toolchain", lambda value: self._set_requirement_sha(value, "toolchain")),
            ("abi", lambda value: self._set_requirement_sha(value, "abi")),
            ("cargo", self._set_cargo_sha),
            ("linker", lambda value: self._set_requirement_sha(value, "linker_trace")),
            ("artifact", lambda value: self._set_requirement_sha(value, "actual_artifact")),
        )
        for name, mutate in mutations:
            evidence = copy.deepcopy(self.evidence)
            mutate(evidence)
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError, "recompute_drift"):
                    reopen_native_link_resolution_receipt(
                        receipt, self.context, self.candidate, evidence,
                    )
        changed_binding = copy.deepcopy(self.context)
        changed_binding["build_ir_binding"]["toolchain_abi_sha256"] = self._sha("drift")
        changed_binding["context_sha256"] = content_sha256({
            key: value for key, value in changed_binding.items() if key != "context_sha256"
        })
        with self.assertRaises(ValueError):
            reopen_native_link_resolution_receipt(
                receipt, changed_binding, self.candidate, self.evidence,
            )

    def test_candidate_and_evidence_cannot_self_report_resolution(self) -> None:
        candidate = copy.deepcopy(self.candidate)
        candidate["status"] = "resolved"
        candidate["claim_boundary"]["native_link_config_resolved"] = True
        candidate["candidate_sha256"] = content_sha256({
            key: value for key, value in candidate.items() if key != "candidate_sha256"
        })
        with self.assertRaisesRegex(ValueError, "candidate_summary"):
            build_native_link_resolution_receipt(
                self.context, candidate, self.evidence,
            )
        evidence = copy.deepcopy(self.evidence)
        evidence["requirements"][0]["linker_trace"]["status"] = "resolved"
        with self.assertRaisesRegex(ValueError, "linker_trace_status"):
            build_native_link_resolution_receipt(
                self.context, self.candidate, evidence,
            )
        receipt = build_native_link_resolution_receipt(
            self.context, self.candidate, self.evidence,
        )
        receipt["resolutions"][0]["status"] = "blocked"
        receipt["receipt_sha256"] = native_link_resolution_receipt_sha256(receipt)
        with self.assertRaisesRegex(ValueError, "status_not_host_derived"):
            validate_native_link_resolution_receipt(
                receipt, self.context, self.candidate,
            )

    def _evidence(self) -> dict:
        requirements = []
        for index, requirement in enumerate(self.context["requirements"]):
            references = {
                name: self._ref(f"evidence/{index}-{name}.json", f"{index}:{name}")
                for name in ("toolchain", "abi", "linker")
            }
            requirements.append({
                "requirement_id": requirement["requirement_id"],
                "toolchain": {"status": "passed", "artifact": references["toolchain"]},
                "abi": {"status": "passed", "artifact": references["abi"]},
                "linker_trace": {"status": "passed", "artifact": references["linker"]},
                "actual_artifact": {
                    "status": "passed",
                    "artifact": self._ref(
                        f"artifacts/{index}-{requirement['portable_name']}",
                        f"artifact:{index}",
                    ),
                    "portable_metadata": {
                        "portable_name": requirement["portable_name"],
                        "library_format": requirement["library_format"],
                        "file_name": requirement["portable_name"],
                        "target_triple": "x86_64-unknown-linux-gnu",
                    },
                },
            })
        return {
            "schema_version": 1,
            "artifact_kind": NATIVE_LINK_HOST_EVIDENCE_KIND,
            "issuer": NATIVE_LINK_RESOLUTION_ISSUER,
            "context_sha256": self.context["context_sha256"],
            "candidate_sha256": self.candidate["candidate_sha256"],
            "build_ir_semantic_sha256": self.context["build_ir_binding"]["semantic_sha256"],
            "toolchain_abi_sha256": self.context["build_ir_binding"]["toolchain_abi_sha256"],
            "project_input_sha256": self._sha("project-input"),
            "cargo": {
                "status": "passed", "exit_code": 0,
                "stdout": self._ref("cargo/stdout.raw", "cargo-stdout"),
                "stderr": self._ref("cargo/stderr.raw", "cargo-stderr"),
            },
            "requirements": requirements,
        }

    @staticmethod
    def _context(*identities: tuple[str, str]) -> dict:
        requirements = []
        for name, library_format in identities:
            identity = {"portable_name": name, "library_format": library_format}
            requirements.append({
                "requirement_id": stable_build_id("native-link-requirement", identity),
                **identity,
                "dependency_count": 1,
                "dependency_set_sha256": content_sha256([f"dep:{name}"]),
                "consumer_target_count": 1,
                "consumer_target_set_sha256": content_sha256([f"target:{name}"]),
            })
        requirements.sort(key=lambda item: item["requirement_id"])
        context = {
            "schema_version": 1,
            "artifact_kind": "native-link-model-context",
            "status": "planning-required",
            "profile": "competition",
            "build_ir_binding": {
                "artifact": NativeLinkResolutionTests._ref("facts/build-ir.json", "build-ir"),
                "semantic_sha256": NativeLinkResolutionTests._sha("build-ir-semantic"),
                "toolchain_abi_sha256": NativeLinkResolutionTests._sha("toolchain-abi"),
                "toolchain_record_count": 1,
                "abi_fact_count": 2,
            },
            "requirements": requirements,
            "requirement_count": len(requirements),
            "dependency_count": len(requirements),
            "model_policy": {
                "input_scope": "grouped-portable-native-identities",
                "allowed_strategies": ["defer", "ffi-boundary", "rustc-link-lib"],
                "absolute_paths_allowed": False,
                "model_may_claim_resolved": False,
            },
            "claim_boundary": {
                "artifact_role": "native-link-planning-context",
                "native_link_config_resolved": False,
                "cargo_executed": False,
                "semantic_gate": False,
                "translation_coverage_numerator": 0,
            },
        }
        context["context_sha256"] = content_sha256(context)
        return context

    @staticmethod
    def _ref(path: str, content: str) -> dict:
        return {"path": path, "sha256": NativeLinkResolutionTests._sha(content), "size_bytes": len(content)}

    @staticmethod
    def _sha(value: str) -> str:
        return content_sha256(value)

    @staticmethod
    def _set_requirement_sha(evidence: dict, gate: str) -> None:
        evidence["requirements"][0][gate]["artifact"]["sha256"] = "e" * 64

    @staticmethod
    def _set_cargo_sha(evidence: dict) -> None:
        evidence["cargo"]["stdout"]["sha256"] = "e" * 64


if __name__ == "__main__":
    unittest.main()

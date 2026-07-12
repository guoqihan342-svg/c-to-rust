from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from validation.tools._ai_candidate_harness_parts.prompt_transport import (
    prompt_transport_contract,
)
from validation.tools._ai_candidate_harness_parts.router import (
    route_candidates,
    selection_policy_sha256,
)
from validation.tools._validate_ai_exact_evidence_parts import validate_evidence
from validation.tools._validate_ai_exact_evidence_parts.io import EvidenceError, EvidenceStore
from validation.tools._validate_ai_exact_evidence_parts.repair import validate_c2rust_repair_audit


REPO_ROOT = Path(__file__).resolve().parents[2]
CLI = REPO_ROOT / "validation" / "tools" / "validate_ai_exact_evidence.py"
AUTO_MIGRATE = REPO_ROOT / "validation" / "tools" / "auto_migrate.py"
GATES = (
    "rustc", "generated_replay", "schema_diff", "negative_mutation",
    "unsafe_scan", "unsafe_ledger", "alias_contract", "abi_contract",
    "oracle_contract", "final_verification",
)
SOURCES = {
    "compile": ("rustc",),
    "oracle": ("oracle_contract",),
    "replay": ("generated_replay",),
    "schema_diff": ("schema_diff",),
    "negative_diff": ("negative_mutation",),
    "unsafe": ("unsafe_scan", "unsafe_ledger"),
    "alias_abi": ("alias_contract", "abi_contract"),
    "final_verification": ("final_verification",),
}


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode())


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def router_gates(gates: dict, candidate_sha: str) -> dict:
    output = {}
    for name, sources in SOURCES.items():
        passed = all(
            gates[source]["status"] == ("expected_failed" if source == "negative_mutation" else "passed")
            for source in sources
        )
        output[name] = {
            "status": "passed" if passed else "failed",
            "candidate_sha256": candidate_sha,
            "source_gates": list(sources),
        }
    return output


class Fixture:
    def __init__(
        self,
        root: Path,
        *,
        fallback: bool = False,
        repair: bool = False,
        no_selection: bool = False,
    ) -> None:
        self.root = root
        self.evidence_root = root / "evidence"
        self.directory = self.evidence_root / "demo" / "auto-translation" / "add-one"
        self.directory.mkdir(parents=True)
        ai = self.add_candidate(
            "ai", b"pub fn add_one(v: i32) -> i32 { v + 1 }\n",
            not fallback and not repair and not no_selection,
        )
        candidates = [{
            "candidate_id": "opencode-glm51-1",
            "source": "opencode-ai",
            "artifact_sha256": ai["sha"],
            "gate_results": ai["router_gates"],
            "provider": "zai",
            "logical_model": "GLM-5.1",
            "resolved_model": "zai/glm-5.1",
            "competition_eligible": True,
            "evaluation_scope": "competition-primary",
            "agent": "c2rust-migrator",
            "variant": "max",
        }]
        evidence = {"ai": ai["ref"]}
        selected_bytes = ai["bytes"]
        if fallback:
            typed = self.add_candidate("typed", b"pub fn add_one(v: i32) -> i32 { v.wrapping_add(1) }\n", True)
            candidates.append({
                "candidate_id": "typed-ir:clang-lowered",
                "source": "typed-ir",
                "artifact_sha256": typed["sha"],
                "gate_results": typed["router_gates"],
            })
            evidence["typed_ir"] = typed["ref"]
            selected_bytes = typed["bytes"]
        candidate_source_audit = None
        if repair:
            repaired = self.add_candidate(
                "c2rust-repair",
                b"pub fn add_one(v: i32) -> i32 { v.wrapping_add(1) }\n",
                True,
            )
            candidates.append({
                "candidate_id": "c2rust-repair:round-1",
                "source": "c2rust-repair",
                "artifact_sha256": repaired["sha"],
                "gate_results": repaired["router_gates"],
            })
            evidence["c2rust_repair"] = repaired["ref"]
            selected_bytes = repaired["bytes"]
            candidate_source_audit = self.add_repair_audit(repaired)
        self.canonical = self.directory / "l3-add-one-rust-draft.rs"
        self.canonical.write_bytes(selected_bytes)
        router = route_candidates(candidates, provider_invocations=1)
        router.update({
            "candidate_evidence": evidence,
            "repair_eligibility": {
                "opencode-ai": {
                    "status": "skipped" if ai["passed"] else "eligible",
                    "reason": (
                        "structured_candidate_failure_missing"
                        if ai["passed"]
                        else "fresh_oracle_and_target_contract_bound"
                    ),
                    "provider_invocations": 0,
                    "semantic_gate": False,
                },
                "c2rust-baseline": {
                    "status": "skipped",
                    "reason": "candidate_not_validated",
                    "provider_invocations": 0,
                    "semantic_gate": False,
                },
            },
            "canonical_draft_sha256": digest(self.canonical),
            "semantic_pass": router["selected_candidate_id"] is not None,
        })
        if candidate_source_audit is not None:
            router["candidate_source_audit"] = {"c2rust_repair": candidate_source_audit}
        self.router = self.directory / "l3-add-one-ai-router.json"
        write_json(self.router, router)
        self.manifest = self.directory / "l3-add-one-auto-translation-manifest.json"
        semantic_pass = router["selected_candidate_id"] is not None
        write_json(self.manifest, {
            "target_id": "demo",
            "slice_id": "add-one",
            "ai_exact_validation": {
                "path": self.router.name,
                "sha256": digest(self.router),
                "status": "passed" if semantic_pass else "failed",
                "semantic_pass": semantic_pass,
            },
        })

    def add_candidate(self, label: str, source: bytes, passed: bool) -> dict:
        attempt = self.directory / "ai-exact-attempts" / label
        attempt.mkdir(parents=True)
        candidate = attempt / "candidate.rs"
        candidate.write_bytes(source)
        candidate_sha = digest(candidate)
        gates = {}
        for index, name in enumerate(GATES, 1):
            status = "expected_failed" if name == "negative_mutation" else "passed"
            if not passed and name == "rustc":
                status = "failed"
            payload = {"candidate_sha256": candidate_sha, "status": status}
            if name == "oracle_contract":
                payload["target_contract_sha256"] = "a" * 64
            if name == "final_verification":
                payload.update({
                    "status": "passed" if passed else "failed",
                    "semantic_pass": passed,
                    "required_gates": list(GATES[:-1]),
                })
            gates[name] = payload
            write_json(attempt / f"{index:02d}-{name}.json", payload)
        index_payload = {
            "schema_version": 1,
            "candidate_sha256": candidate_sha,
            "gates": {
                name: {"path": f"{index:02d}-{name}.json", "sha256": digest(attempt / f"{index:02d}-{name}.json")}
                for index, name in enumerate(GATES, 1)
            },
        }
        gate_index = attempt / "gate-index.json"
        write_json(gate_index, index_payload)
        projected = router_gates(gates, candidate_sha)
        summary = {
            "schema_version": 1,
            "status": "passed" if passed else "failed",
            "candidate_sha256": candidate_sha,
            "semantic_pass": passed,
            "gate_index": {"path": gate_index.relative_to(self.directory).as_posix(), "sha256": digest(gate_index)},
            "gates": gates,
            "router_gate_results": projected,
        }
        summary_path = self.directory / f"l3-add-one-{label}-exact-validation.json"
        write_json(summary_path, summary)
        return {
            "bytes": source,
            "passed": passed,
            "sha": candidate_sha,
            "router_gates": projected,
            "ref": {"path": summary_path.name, "sha256": digest(summary_path), "status": summary["status"]},
        }

    def rebind_router(self) -> None:
        manifest = read_json(self.manifest)
        manifest["ai_exact_validation"]["sha256"] = digest(self.router)
        write_json(self.manifest, manifest)

    def rebind_summary(self, key: str = "ai") -> None:
        router = read_json(self.router)
        summary = self.directory / router["candidate_evidence"][key]["path"]
        router["candidate_evidence"][key]["sha256"] = digest(summary)
        write_json(self.router, router)
        self.rebind_router()

    def add_repair_audit(self, repaired: dict) -> dict:
        baseline = self.directory / "l3-add-one-c2rust-baseline.rs"
        baseline.write_bytes(b"pub fn add_one(v: i32) -> i32 { v + 1 }\n")
        failure = self.directory / "l3-add-one-c2rust-repair-01-failure-facts.json"
        prompt = self.directory / "l3-add-one-c2rust-repair-01-prompt.txt"
        response = self.directory / "l3-add-one-c2rust-repair-01-response.jsonl"
        patch = self.directory / "l3-add-one-c2rust-repair-01.patch"
        candidate = self.directory / "l3-add-one-c2rust-repair-01-candidate.rs"
        validation = self.directory / "l3-add-one-c2rust-repair-01-validation-result.json"
        write_json(failure, {"status": "failed", "failures": [{"kind": "rustc"}]})
        prompt.write_text("repair the c2rust baseline\n", encoding="utf-8")
        response.write_text('{"type":"text","text":"repair"}\n', encoding="utf-8")
        patch.write_text("candidate-only repair\n", encoding="utf-8")
        candidate.write_bytes(repaired["bytes"])
        write_json(validation, {"status": "passed", "failures": []})

        def ref(path: Path) -> dict:
            return {"path": path.name, "sha256": digest(path)}

        self.repair_prompt = prompt
        self.repair_report = self.directory / "l3-add-one-c2rust-repair-report.json"
        status = "candidate_ready_for_common_validation"
        write_json(self.repair_report, {
            "schema_version": 3,
            "artifact_label": "c2rust-repair",
            "input_source": "c2rust-baseline",
            "status": status,
            "generator": {
                "tool": "opencode",
                "provider": "zai",
                "logical_model": "GLM-5.1",
                "resolved_model": "zai/glm-5.1",
                "competition_eligible": True,
                "evaluation_scope": "competition-primary",
                "agent": "c2rust-migrator",
                "variant": "max",
                "prompt_transport": prompt_transport_contract(),
            },
            "initial_candidate": {"name": baseline.name, "sha256": digest(baseline)},
            "claim_boundary": {
                "semantic_gate": False,
                "semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
            "rounds": [{
                "round": 1,
                "semantic_pass": False,
                "bindings": {
                    "failure_facts": ref(failure),
                    "prompt": ref(prompt),
                    "raw_response": ref(response),
                    "repair_artifact": ref(patch),
                    "candidate": ref(candidate),
                    "validation_result": ref(validation),
                },
            }],
            "final_candidate": ref(candidate),
        })
        return {
            "source": "c2rust-repair",
            "status": "exact_gates_completed",
            "reason": "fresh_exact_gates_passed",
            "base_candidate_sha256": digest(baseline),
            "repair_report": {
                "path": self.repair_report.name,
                "sha256": digest(self.repair_report),
                "status": status,
                "semantic_pass": False,
            },
            "repair_rounds": 1,
            "final_candidate_sha256": repaired["sha"],
        }

    def rebind_repair_report(self) -> None:
        router = read_json(self.router)
        router["candidate_source_audit"]["c2rust_repair"]["repair_report"]["sha256"] = digest(
            self.repair_report
        )
        write_json(self.router, router)
        self.rebind_router()


class ValidateAiExactEvidenceTests(unittest.TestCase):
    def validate(self, fixture: Fixture, *, required: bool = True) -> dict:
        return validate_evidence(
            target_id="demo", slice_id="add-one", evidence_root=fixture.evidence_root,
            require_semantic_pass=required,
        )

    def test_ai_and_typed_fallback_positive_paths(self) -> None:
        for fallback in (False, True):
            with self.subTest(fallback=fallback), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp), fallback=fallback)
                report = self.validate(fixture)
                expected = "typed-ir:clang-lowered" if fallback else "opencode-glm51-1"
                self.assertEqual(report["selected_candidate_id"], expected)
                self.assertTrue(report["semantic_pass"])
                self.assertGreaterEqual(report["checked_artifacts"], 15)

    def test_cli_outputs_structured_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            result = subprocess.run([
                sys.executable, str(CLI), "--target-id", "demo", "--slice-id", "add-one",
                "--evidence-root", str(fixture.evidence_root), "--require-semantic-pass",
            ], cwd=REPO_ROOT, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "passed")

    def test_no_selected_candidate_remains_semantic_false(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp), no_selection=True)
            report = self.validate(fixture, required=False)
            self.assertIsNone(report["selected_candidate_id"])
            self.assertFalse(report["semantic_pass"])
            with self.assertRaisesRegex(EvidenceError, "semantic pass is required"):
                self.validate(fixture, required=True)

    def test_validator_accepts_real_auto_migrate_exact_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            provider = root / "provider.py"
            provider.write_text(
                "import json\n"
                "payload={'schema_version':1,'candidate':{'language':'rust',"
                "'source':'pub fn add_one(value: i32) -> i32 { value.wrapping_add(1) }\\n'},"
                "'assumptions':[]}\n"
                "print(json.dumps({'type':'message.part.updated','part':{'type':'text',"
                "'text':json.dumps(payload)}}))\n",
                encoding="utf-8",
            )
            out_root = root / "evidence"
            generated = subprocess.run([
                sys.executable, str(AUTO_MIGRATE), "--slice-spec",
                str(REPO_ROOT / "validation" / "slice-specs" / "demo-add-one.json"),
                "--out-root", str(out_root), "--emit-clang-lowering-report",
                "--ai-first-candidate", "--ai-opencode-command",
                f'"{sys.executable}" "{provider}"',
            ], cwd=REPO_ROOT, text=True, capture_output=True)
            self.assertEqual(generated.returncode, 0, generated.stderr)
            report = validate_evidence(
                target_id="demo", slice_id="add-one", evidence_root=out_root,
                require_semantic_pass=True,
            )
            self.assertTrue(report["semantic_pass"])
            self.assertEqual(report["selected_candidate_id"], "opencode-glm51-1")

    def test_missing_path_hash_and_manifest_hash_drift_are_rejected(self) -> None:
        cases = ("missing", "path_escape", "gate_hash", "manifest_hash")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                attempt = fixture.directory / "ai-exact-attempts" / "ai"
                if case == "missing":
                    (attempt / "01-rustc.json").unlink()
                elif case == "path_escape":
                    outside = fixture.root / "outside.json"
                    write_json(outside, {"status": "passed"})
                    index = read_json(attempt / "gate-index.json")
                    index["gates"]["rustc"] = {"path": str(outside), "sha256": digest(outside)}
                    write_json(attempt / "gate-index.json", index)
                    self._rebind_index(fixture)
                elif case == "gate_hash":
                    (attempt / "01-rustc.json").write_text("{}\n", encoding="utf-8")
                else:
                    router = read_json(fixture.router)
                    router["semantic_pass"] = False
                    write_json(fixture.router, router)
                with self.assertRaises(EvidenceError):
                    self.validate(fixture)

    def test_gate_policy_selected_and_accepted_proof_tampering_is_rejected(self) -> None:
        for case in ("gate", "policy", "selected", "accepted"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp))
                router = read_json(fixture.router)
                summary_path = fixture.directory / router["candidate_evidence"]["ai"]["path"]
                if case == "gate":
                    summary = read_json(summary_path)
                    summary["gates"]["rustc"]["status"] = "failed"
                    write_json(summary_path, summary)
                    fixture.rebind_summary()
                elif case == "policy":
                    router["selection_policy"]["stage"] = "tampered"
                    router["selection_policy_sha256"] = selection_policy_sha256(router["selection_policy"])
                    write_json(fixture.router, router)
                    fixture.rebind_router()
                elif case == "selected":
                    router["selected_candidate_id"] = None
                    router["semantic_pass"] = False
                    write_json(fixture.router, router)
                    fixture.rebind_router()
                else:
                    summary = read_json(summary_path)
                    summary["accepted_evidence_binding"] = {"status": "accepted"}
                    write_json(summary_path, summary)
                    fixture.rebind_summary()
                with self.assertRaises(EvidenceError):
                    self.validate(fixture)

    def test_repair_eligibility_tampering_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp))
            router = read_json(fixture.router)
            router["repair_eligibility"]["opencode-ai"]["status"] = "eligible"
            router["repair_eligibility"]["opencode-ai"]["reason"] = "tampered"
            write_json(fixture.router, router)
            fixture.rebind_router()
            with self.assertRaisesRegex(EvidenceError, "repair eligibility"):
                self.validate(fixture)

    def test_c2rust_repair_audit_is_reopened_and_fails_closed_on_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp), repair=True)
            report = self.validate(fixture)
            self.assertEqual(report["selected_candidate_id"], "c2rust-repair:round-1")
            self.assertTrue(report["semantic_pass"])

        for case in (
            "missing_audit",
            "report_sha",
            "round_binding",
            "path_escape",
            "semantic_pass",
            "prompt_transport",
            "generator_identity",
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                fixture = Fixture(Path(tmp), repair=True)
                if case == "missing_audit":
                    router = read_json(fixture.router)
                    del router["candidate_source_audit"]
                    write_json(fixture.router, router)
                    fixture.rebind_router()
                elif case == "report_sha":
                    fixture.repair_report.write_text(
                        fixture.repair_report.read_text(encoding="utf-8") + "\n",
                        encoding="utf-8",
                    )
                elif case == "round_binding":
                    fixture.repair_prompt.write_text("drifted prompt\n", encoding="utf-8")
                else:
                    repair_report = read_json(fixture.repair_report)
                    if case == "path_escape":
                        repair_report["rounds"][0]["bindings"]["prompt"]["path"] = "../prompt.txt"
                    elif case == "prompt_transport":
                        repair_report["generator"]["prompt_transport"]["message_sha256"] = "0" * 64
                    elif case == "generator_identity":
                        repair_report["generator"].update(
                            {
                                "provider": "opencode",
                                "logical_model": "DeepSeek-V4-Flash",
                                "resolved_model": "opencode/deepseek-v4-flash-free",
                                "competition_eligible": False,
                                "evaluation_scope": "auxiliary-local-validation",
                                "agent": "c2rust-candidate",
                            }
                        )
                    else:
                        repair_report["claim_boundary"]["semantic_pass"] = True
                    write_json(fixture.repair_report, repair_report)
                    fixture.rebind_repair_report()
                with self.assertRaises(EvidenceError):
                    self.validate(fixture)

    def test_c2rust_repair_duplicate_audit_is_reopened(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp), repair=True)
            router = read_json(fixture.router)
            repaired = next(
                item for item in router["candidate_set"] if item["source"] == "c2rust-repair"
            )
            router["candidate_set"].remove(repaired)
            duplicate = {
                **repaired,
                "decision": "duplicate",
                "duplicate_of": "opencode-glm51-1",
            }
            router["deduplicated_candidates"].append(duplicate)
            del router["candidate_evidence"]["c2rust_repair"]
            audit = router["candidate_source_audit"]["c2rust_repair"]
            audit.update(
                status="duplicate",
                reason="duplicate_exact_artifact_sha256",
                duplicate_of="opencode-glm51-1",
            )

            self.assertEqual(
                validate_c2rust_repair_audit(EvidenceStore(fixture.directory), router),
                1,
            )
            audit["duplicate_of"] = "typed-ir"
            with self.assertRaises(EvidenceError):
                validate_c2rust_repair_audit(EvidenceStore(fixture.directory), router)

    def test_c2rust_repair_without_candidate_audit_is_reopened(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fixture = Fixture(Path(tmp), repair=True)
            router = read_json(fixture.router)
            router["candidate_set"] = [
                item for item in router["candidate_set"] if item["source"] != "c2rust-repair"
            ]
            del router["candidate_evidence"]["c2rust_repair"]
            audit = router["candidate_source_audit"]["c2rust_repair"]
            audit.update(
                status="repair_completed_without_candidate",
                reason="repair_report_has_no_reopenable_candidate",
            )
            audit.pop("final_candidate_sha256")

            report = read_json(fixture.repair_report)
            report["status"] = "round_limit_reached"
            report.pop("final_candidate")
            del report["rounds"][0]["bindings"]["candidate"]
            write_json(fixture.repair_report, report)
            audit["repair_report"].update(
                sha256=digest(fixture.repair_report),
                status=report["status"],
            )

            self.assertEqual(
                validate_c2rust_repair_audit(EvidenceStore(fixture.directory), router),
                1,
            )
            report["rounds"][0]["bindings"]["candidate"] = {
                "path": "l3-add-one-c2rust-repair-01-candidate.rs",
                "sha256": digest(fixture.directory / "l3-add-one-c2rust-repair-01-candidate.rs"),
            }
            write_json(fixture.repair_report, report)
            audit["repair_report"]["sha256"] = digest(fixture.repair_report)
            with self.assertRaises(EvidenceError):
                validate_c2rust_repair_audit(EvidenceStore(fixture.directory), router)

    @staticmethod
    def _rebind_index(fixture: Fixture) -> None:
        router = read_json(fixture.router)
        summary_path = fixture.directory / router["candidate_evidence"]["ai"]["path"]
        summary = read_json(summary_path)
        index_path = fixture.directory / summary["gate_index"]["path"]
        summary["gate_index"]["sha256"] = digest(index_path)
        write_json(summary_path, summary)
        fixture.rebind_summary()


if __name__ == "__main__":
    unittest.main()

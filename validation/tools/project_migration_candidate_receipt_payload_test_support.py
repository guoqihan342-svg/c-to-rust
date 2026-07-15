from __future__ import annotations

import hashlib
from pathlib import Path

from validation.tools._project_migration_harness.candidate_cargo_fact_binding import (
    write_candidate_cargo_fact_binding,
)
from validation.tools._project_migration_harness.cargo_compiler_artifact_evidence import (
    parse_cargo_compiler_artifact_evidence,
)
from validation.tools._project_migration_harness.cargo_fact_commands import (
    CARGO_METADATA_COMMAND,
)
from validation.tools._project_migration_harness.cargo_metadata_fact_evidence import (
    parse_cargo_metadata_fact_evidence,
)
from validation.tools._project_migration_harness.cargo_raw_output_evidence import (
    write_cargo_raw_output,
)
from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.project_candidate_domain import (
    candidate_domain_context_sha256,
    candidate_verification_context,
)
from validation.tools._project_migration_harness.project_cargo_evidence import (
    CARGO_COMMANDS,
    project_cargo_observation,
)
from validation.tools._project_migration_harness.project_native_link_settlement_binding import (
    project_native_link_settlement_status,
)
from validation.tools._project_migration_harness.project_verification_execution import (
    environment_policy,
)
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract,
    canonical_sha256,
)
from validation.tools._project_migration_harness.sandbox_requirements import (
    cargo_verification_plan,
)
from validation.tools.project_migration_candidate_receipt_test_support import (
    materialize_test_quarantine,
)
from validation.tools.project_migration_cargo_fact_test_support import (
    cargo_check_stdout,
    cargo_metadata_stdout,
)
from validation.tools.project_migration_sandbox_test_support import (
    passing_probe_receipt,
)


class CandidateReceiptFixture:
    def __init__(self, repo: Path) -> None:
        self.repo = Path(repo)
        self.out_root = self.repo / "target/run"
        self.out_root.mkdir(parents=True)
        self.ledger_path = self.out_root / "state/project-migration.sqlite3"
        self.quarantine_root = self.repo / "quarantine"
        self.materialization = materialize_test_quarantine(self.quarantine_root)
        self.candidate_set_sha256 = self.materialization["candidate_set_sha256"]
        self.project_input_sha256 = self.materialization["generation"]["sha256"]

    def payload(self) -> dict:
        observations = self._observations()
        native = project_native_link_settlement_status("not-required")
        domain = {
            "run_id": "receipt-run",
            "run_context_sha256": "1" * 64,
            "dag_sha256": "2" * 64,
            "integration_manifest": {
                "path": "plan/integration-manifest.json",
                "sha256": "3" * 64,
                "size_bytes": 1,
            },
            "candidate_set_sha256": self.candidate_set_sha256,
            "candidate_set_manifest_sha256": "4" * 64,
            "rust_project_ir_sha256": "a" * 64,
            "rust_project_interface_sha256": "b" * 64,
            "rust_project_binding_sha256": "5" * 64,
        }
        domain["candidate_domain_context_sha256"] = (
            candidate_domain_context_sha256(domain)
        )
        build_ir = {"schema_version": 1, "status": "verified", "blockers": []}
        materialization = self._materialization()
        execution = self._execution(observations)
        cargo_facts = write_candidate_cargo_fact_binding(
            parsed={
                "cargo_metadata": parse_cargo_metadata_fact_evidence(
                    cargo_metadata_stdout()
                ),
                "compiler_artifacts": parse_cargo_compiler_artifact_evidence(
                    cargo_check_stdout()
                ),
            },
            execution=execution,
            observations=observations,
            out_root=self.out_root,
            out_root_rel="target/run",
        )
        payload = {
            "schema_version": 2,
            "artifact_kind": "candidate-project-verification",
            "status": "candidate-verified",
            **domain,
            "build_ir_verification": build_ir,
            "materialization": materialization,
            "execution": execution,
            "cargo_observations": observations,
            "cargo_statuses": {"cargo-check": "passed", "cargo-test": "passed"},
            "cargo_fact_evidence": cargo_facts,
            "native_link_settlement": native,
            "state_effects": {
                "final_current_updated": False,
                "project_gate_records_written": 0,
                "candidate_only": True,
            },
            "claim_boundary": {
                "candidate_project_gate": True,
                "final_project_gate": False,
                "updates_final_current": False,
                "writes_project_gate_records": False,
                "semantic_gate": False,
                "semantic_pass": False,
                "translation_coverage_numerator": 0,
            },
        }
        payload["verification_context_sha256"] = candidate_verification_context(
            domain, build_ir, materialization, execution, observations, native,
            cargo_facts,
        )
        return payload

    def write(self, payload: dict) -> dict:
        reference = write_content_addressed_json(
            self.out_root, "candidate-project-verification", payload,
        )
        return {**reference, "path": f"target/run/{reference['path']}"}

    def _materialization(self) -> dict:
        return {
            "schema_version": 1,
            "status": "materialized",
            "candidate_set": {
                "sha256": self.candidate_set_sha256, "member_count": 2,
            },
            "candidate_count": 2,
            "rust_project_ir_sha256": "a" * 64,
            "rust_project_interface_sha256": "b" * 64,
            "rust_project_ir_scope": "full-project",
            "generator": self.materialization["generator"],
            "generation": dict(self.materialization["generation"]),
            "manifest_ref": self.materialization["manifest_ref"],
            "generation_manifest_ref": self.materialization[
                "generation_manifest_ref"
            ],
            "immutable": True,
            "last_good_updated": False,
            "cargo_executed": False,
            "diagnostics": [],
        }

    def _execution(self, observations: dict[str, dict]) -> dict:
        return {
            "schema_version": 1,
            "status": "passed",
            "cargo_executed": True,
            "project_input_sha256": self.project_input_sha256,
            "project_state_before": self.project_input_sha256,
            "project_state_after": self.project_input_sha256,
            "project_state_unchanged": True,
            "sandbox": self.sandbox,
            "checks": [
                observations["cargo-check"]["check"],
                observations["cargo-test"]["check"],
            ],
            "fact_probes": {"cargo-metadata": self._metadata_probe()},
            "environment_policy": environment_policy(),
            "diagnostics": [],
            "semantic_gate": False,
            "proof_boundary": (
                "Sandboxed Cargo topology/compile/test facts only; "
                "oracle and final verification remain separate"
            ),
            "native_link_trace": {
                "schema_version": 1,
                "status": "not-required",
                "cargo_gate": None,
                "source_stdout_sha256": None,
                "native_linker_binding_sha256": None,
                "artifact": None,
                "entry_count": 0,
                "semantic_gate": False,
            },
        }

    def _observations(self) -> dict[str, dict]:
        self.contract = SandboxContract(
            backend="bubblewrap-v1",
            launcher_sha256="8" * 64,
            toolchain_sha256="9" * 64,
        )
        self.probe = passing_probe_receipt(self.contract)
        self.sandbox = {
            "contract": self.contract.payload(),
            "contract_sha256": self.contract.sha256,
            "probe_receipt": self.probe.payload(),
            "probe_receipt_sha256": self.probe.sha256,
            "cleanup_verified": True,
        }
        result = {}
        for gate in ("cargo-check", "cargo-test"):
            command = CARGO_COMMANDS[gate]
            stdout = cargo_check_stdout() if gate == "cargo-check" else b"tests passed\n"
            check = self._sandbox_check(command, gate, stdout, b"")
            execution = {
                "project_input_sha256": self.project_input_sha256,
                "project_state_before": self.project_input_sha256,
                "project_state_after": self.project_input_sha256,
                "project_state_unchanged": True,
                "sandbox": self.sandbox,
            }
            result[gate] = project_cargo_observation(
                execution, check, gate_kind=gate,
                expected_input_sha256=self.project_input_sha256,
            )
        return result

    def _metadata_probe(self) -> dict:
        return self._sandbox_check(
            list(CARGO_METADATA_COMMAND), "cargo-metadata",
            cargo_metadata_stdout(), b"",
        )

    def _sandbox_check(
        self, command: list[str], gate: str, stdout: bytes, stderr: bytes,
    ) -> dict:
        plan = cargo_verification_plan(
            gate, tuple(command), self.project_input_sha256,
            requirements=self.contract.requirements,
        )
        return {
            "command": command, "status": "passed", "cargo_executed": True,
            "returncode": 0, "timed_out": False,
            "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
            "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
            "stdout_ref": write_cargo_raw_output(
                self.out_root, "target/run", gate_kind=gate,
                stream="stdout", data=stdout,
            ),
            "stderr_ref": write_cargo_raw_output(
                self.out_root, "target/run", gate_kind=gate,
                stream="stderr", data=stderr,
            ),
            "sandbox_contract_sha256": self.contract.sha256,
            "sandbox_command_sha256": canonical_sha256(command),
            "sandbox_command_started": True,
            "sandbox_launcher_argv_sha256": "a" * 64,
            "sandbox_requirements_sha256": self.contract.requirements.sha256,
            "sandbox_verification_plan": plan.payload(),
            "sandbox_verification_plan_sha256": plan.sha256,
            "sandbox_probe_receipt_sha256": self.probe.sha256,
        }


__all__ = ["CandidateReceiptFixture"]

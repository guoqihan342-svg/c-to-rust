from __future__ import annotations

from validation.tools._project_migration_harness.gate_authority import (
    project_authority,
    project_summary_payload,
)
from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.project_cargo_evidence import (
    CARGO_COMMANDS,
)
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract, canonical_sha256,
)
from validation.tools._project_migration_harness.sandbox_requirements import (
    cargo_verification_plan,
)
from validation.tools.project_migration_gate_authority_candidate_test_support import (
    digest,
)
from validation.tools.project_migration_sandbox_test_support import (
    passing_probe_receipt,
)


class ProjectGateAuthoritySupportMixin:
    def record_project_host_gate(
        self, kind: str, status: str, record_id: str, candidate_set: str,
        sources: list[dict] | None = None,
    ) -> None:
        if kind != "final-verification" and sources is None:
            sources = [self.project_observation(kind, status, candidate_set)]
        payload = project_summary_payload(
            run_id="run",
            gate_kind=kind,
            status=status,
            candidate_set_sha256=candidate_set,
            source_evidence=sources or [],
        )
        reference = write_content_addressed_json(
            self.out_root, f"project/{kind}", payload,
        )
        self.ledger.record_project_gate(
            record_id=record_id,
            run_id="run",
            gate_kind=kind,
            status=status,
            candidate_set_sha256=candidate_set,
            verifier_id=project_authority(kind),
            evidence_path=f"target/run/{reference['path']}",
            evidence_sha256=str(reference["sha256"]),
        )

    def project_observation(
        self, kind: str, status: str, candidate_set: str,
    ) -> dict[str, object]:
        observation = self.project_observation_value(kind, status)
        payload = {
            "schema_version": 1,
            "artifact_kind": "host-project-gate-observation",
            "authority_id": project_authority(kind),
            "run_id": "run",
            "gate_kind": kind,
            "candidate_set_sha256": candidate_set,
            "observation": observation,
        }
        reference = write_content_addressed_json(
            self.out_root, f"raw/{kind}", payload,
        )
        return {**reference, "path": f"target/run/{reference['path']}"}

    def project_observation_value(
        self, kind: str, status: str,
    ) -> dict[str, object]:
        passed = status == "passed"
        if kind == "integration":
            observation = {
                "managed_project_unchanged": passed,
                "candidate_count": 1,
                "manifest_sha256": digest("manifest"),
                "project_sha256": digest("project"),
                "interface_complete": passed,
            }
        elif kind in {"cargo-check", "cargo-test"}:
            observation = _cargo_observation(kind, passed)
        elif kind == "oracle-replay":
            observation = {
                "case_count": 1,
                "mismatch_count": 0 if passed else 1,
                "crash_count": 0,
                "oracle_sha256": digest("oracle"),
                "candidate_sha256": digest("candidate-project"),
            }
        elif kind == "negative":
            observation = {
                "case_count": 1,
                "unexpected_accept_count": 0 if passed else 1,
            }
        elif kind == "unsafe-alias-abi":
            observation = {
                "check_count": 1,
                "violation_count": 0 if passed else 1,
            }
        else:
            raise ValueError("unsupported raw project observation")
        return observation

    def record_project_final(self, record_id: str, candidate_set: str) -> None:
        sources = self.ledger.project_gate_bundle_sources(
            run_id="run", candidate_set_sha256=candidate_set,
        )
        self.record_project_host_gate(
            "final-verification", "passed", record_id, candidate_set, sources,
        )


def _cargo_observation(kind: str, passed: bool) -> dict[str, object]:
    contract = SandboxContract(
        backend="bubblewrap-v1",
        launcher_sha256=digest("launcher"),
        toolchain_sha256=digest("toolchain"),
    )
    probe = passing_probe_receipt(contract)
    command = CARGO_COMMANDS[kind]
    input_sha256 = digest("manifest")
    plan = cargo_verification_plan(
        kind, tuple(command), input_sha256,
        requirements=contract.requirements,
    )
    return {
        "outcome": "executed",
        "project_input_sha256": input_sha256,
        "project_state_unchanged": True,
        "blocker_code": None,
        "sandbox": {
            "contract": contract.payload(),
            "contract_sha256": contract.sha256,
            "probe_receipt": probe.payload(),
            "probe_receipt_sha256": probe.sha256,
            "cleanup_verified": True,
        },
        "check": {
            "command": command,
            "status": "passed" if passed else "failed",
            "cargo_executed": True,
            "returncode": 0 if passed else 1,
            "timed_out": False,
            "stdout_sha256": digest("stdout"),
            "stderr_sha256": digest("stderr"),
            "sandbox_contract_sha256": contract.sha256,
            "sandbox_command_sha256": canonical_sha256(command),
            "sandbox_command_started": True,
            "sandbox_launcher_argv_sha256": digest("argv"),
            "sandbox_requirements_sha256": contract.requirements.sha256,
            "sandbox_verification_plan": plan.payload(),
            "sandbox_verification_plan_sha256": plan.sha256,
            "sandbox_probe_receipt_sha256": probe.sha256,
        },
    }


__all__ = ["ProjectGateAuthoritySupportMixin"]

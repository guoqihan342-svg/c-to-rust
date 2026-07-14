from __future__ import annotations

import json
from typing import Any

from validation.tools._project_migration_harness.integration import (
    integrate_rust_project_ir,
)
from validation.tools._project_migration_harness.gate_candidate_sets import (
    current_candidate_members,
)
from validation.tools._project_migration_harness.project_generation_context import (
    load_managed_project_context, managed_project_root,
)
from validation.tools._project_migration_harness.project_cargo_evidence import (
    CARGO_COMMANDS,
)
from validation.tools._project_migration_harness.project_diagnostic_shape import (
    build_project_diagnostic,
)
from validation.tools._project_migration_harness.project_host_gates import (
    record_host_project_observation,
)
from validation.tools._project_migration_harness.project_interface_coordinator import (
    coordinate_project_interfaces,
)
from validation.tools._project_migration_harness.project_repair_authoritative_ir import (
    persist_authoritative_project_ir,
)
from validation.tools._project_migration_harness.project_repair_coordinator import (
    resume_latest_project_repair,
)
from validation.tools._project_migration_harness.project_repair_dispatch_permit import (
    project_repair_dispatch_binding,
)
from validation.tools._project_migration_harness.project_repair_ingest import (
    ingest_project_repair_response,
)
from validation.tools._project_migration_harness.project_repair_worker_request import (
    materialize_project_repair_request, read_bound_rust_project_ir,
)
from validation.tools._project_migration_harness.sandbox_contract import SandboxContract
from validation.tools._project_migration_harness.sandbox_requirements import (
    cargo_verification_plan,
)
from validation.tools.project_migration_gate_authority_test_support import digest
from validation.tools.project_migration_cargo_receipt_test_support import (
    classified_cargo_observation, register_verifier_project_ir,
)
from validation.tools.project_migration_project_repair_test_support import (
    project_repair_test_dispatch_permit,
)
from validation.tools.project_migration_sandbox_test_support import (
    cargo_compiler_message,
)


class ProjectVerifierRepairFlowSupportMixin:
    def _prepare_verifier_case(self) -> None:
        self.promote_current_candidate()
        self.rust_project_ir = register_verifier_project_ir(
            self.ledger, self.out_root, "target/run",
        )
        self.candidate_set = self.ledger.bind_current_candidate_set(run_id="run")
        self._prepare_source_generation()
        self.reference = self._record_intake()
        self.wrappers = self.ledger.bound_project_diagnostic_intakes(
            run_id="run", references=[self.reference],
            rust_project_ir_sha256=self.rust_project_ir["ir_sha256"],
        )

    def _prepare_source_generation(self) -> None:
        integrate_rust_project_ir(
            self.rust_project_ir, self.out_root,
            managed_project_root(self.out_root),
        )
        with self.ledger.connect() as connection:
            members = current_candidate_members(connection, "run")
        context = load_managed_project_context(
            managed_project_root(self.out_root), members,
        )
        self.source_project_input = context["project_input_sha256"]

    def _candidate(self) -> tuple[dict, dict, dict, dict, dict]:
        receipt, request, _request_ref, base_ref, _preflight = (
            self._materialized_request()
        )
        result = ingest_project_repair_response(
            request, self._response(request), ledger=self.ledger,
            harness_root=self.harness, out_root=self.out_root,
            out_root_rel="target/run",
        )
        candidate = read_bound_rust_project_ir(
            self.harness,
            result["artifacts"]["rust_project_ir_authoritative"],
        )
        pending = resume_latest_project_repair(
            ledger=self.ledger, run_id="run", base_rust_project_ir=base_ref,
            harness_root=self.harness, out_root=self.out_root,
            out_root_rel="target/run",
        )
        return receipt, request, result, candidate, pending

    def _response(self, request: dict[str, Any]) -> dict[str, Any]:
        module = self.rust_project_ir["modules"][0]
        return {
            "schema_version": 1, "run_id": "run", "role": "project-repairer",
            "project_repair_queue_sha256": request[
                "project_repair_queue_sha256"
            ],
            "repair_id": request["repair_id"],
            "attempt_id": request["execution_binding"]["attempt_id"],
            "effective_input_sha256": request["effective_input_sha256"],
            "base_rust_project_ir_sha256": self.rust_project_ir["ir_sha256"],
            "context_sha256": request["project_repair_context"]["context_sha256"],
            "operations": [{
                "section": "modules", "action": "replace",
                "record_id": module["module_id"],
                "changes": {"visibility": "public"},
            }],
        }

    def _materialized_request(self) -> tuple[dict, dict, dict, dict, dict]:
        receipt = coordinate_project_interfaces(
            self.rust_project_ir, project_diagnostic_intakes=self.wrappers,
        )
        self.ledger.register_project_interface_receipt(
            run_id="run", receipt=receipt, rust_project_ir=self.rust_project_ir,
        )
        base_ref = persist_authoritative_project_ir(
            self.rust_project_ir, out_root=self.out_root,
            out_root_rel="target/run",
        )
        item = receipt["project_repair_queue"]["items"][0]
        permit = project_repair_test_dispatch_permit(
            self.harness, self.out_root, self.ledger, base_ref,
        )
        materialized = materialize_project_repair_request(
            ledger=self.ledger, run_id="run",
            queue_sha256=receipt["project_repair_queue"][
                "project_repair_queue_sha256"
            ],
            repair_id=item["repair_id"], worker_id="project-repairer-1",
            base_rust_project_ir=base_ref, harness_root=self.harness,
            out_root=self.out_root, out_root_rel="target/run",
            dispatch_permit=permit,
        )
        request_ref = materialized["request"]
        request = json.loads(
            (self.harness / request_ref["path"]).read_text(encoding="utf-8")
        )
        preflight = project_repair_dispatch_binding(permit)["preflight"]
        return receipt, request, request_ref, base_ref, preflight

    def _record_candidate_gate(
        self, candidate: dict[str, Any], status: str, input_label: str,
    ) -> dict[str, Any]:
        if input_label == "source-generation":
            project_input = self.source_project_input
        else:
            integrated = integrate_rust_project_ir(
                candidate, self.out_root, managed_project_root(self.out_root),
            )
            if integrated["status"] != "integrated":
                raise AssertionError("test candidate generation was not published")
            with self.ledger.connect() as connection:
                members = current_candidate_members(connection, "run")
            project_input = load_managed_project_context(
                managed_project_root(self.out_root), members,
            )["project_input_sha256"]
        observation, partition = self._classified_cargo_observation(
            status, project_input, candidate,
        )
        diagnostic_input = None
        if status == "failed":
            diagnostic_input = {
                "rust_project_ir_sha256": candidate["ir_sha256"],
                "rust_project_interface_sha256": candidate["interface_sha256"],
                "project_input_sha256": project_input,
                "diagnostics": partition.project_diagnostics,
            }
        return record_host_project_observation(
            ledger=self.ledger, out_root=self.out_root,
            out_root_rel="target/run", run_id="run", gate_kind="cargo-check",
            candidate_set_sha256=self.candidate_set, observation=observation,
            diagnostic_codes=[] if status == "passed" else ["e0425"],
            project_diagnostic_input=diagnostic_input,
        )

    def _cargo_observation(
        self, status: str, project_input: str,
    ) -> dict[str, Any]:
        observation = self.project_observation_value("cargo-check", status)
        contract = SandboxContract(
            backend="bubblewrap-v1", launcher_sha256=digest("launcher"),
            toolchain_sha256=digest("toolchain"),
        )
        plan = cargo_verification_plan(
            "cargo-check", tuple(CARGO_COMMANDS["cargo-check"]), project_input,
            requirements=contract.requirements,
        )
        observation["project_input_sha256"] = project_input
        observation["check"]["sandbox_verification_plan"] = plan.payload()
        observation["check"]["sandbox_verification_plan_sha256"] = plan.sha256
        return observation

    def _classified_cargo_observation(
        self, status: str, project_input: str, rust_project_ir: dict[str, Any],
    ) -> tuple[dict[str, Any], Any]:
        with self.ledger.connect() as connection:
            members = current_candidate_members(connection, "run")
        stdout = ""
        if status == "failed":
            stdout = "".join(
                cargo_compiler_message(
                    code=code.upper(),
                    message="unresolved import `shared_feature`",
                    file="src/project.rs",
                )
                for code in ("e0425", "e0432")
            )
        return classified_cargo_observation(
            out_root=self.out_root, out_root_rel="target/run", run_id="run",
            gate_kind="cargo-check",
            candidate_set_sha256=self.candidate_set,
            project_input_sha256=project_input, candidate_members=members,
            rust_project_ir=rust_project_ir,
            observation=self._cargo_observation(status, project_input),
            stdout=stdout,
        )

    def _cargo_result(self, status: str, record: dict[str, Any]) -> dict[str, Any]:
        return {
            "schema_version": 1, "status": status, "run_id": "run",
            "candidate_set_sha256": self.candidate_set, "records": [record],
            "project_diagnostic_intakes": [
                record["project_diagnostic_intake"]
            ] if "project_diagnostic_intake" in record else [],
        }

    def _record_intake(self) -> dict[str, Any]:
        observation, partition = self._classified_cargo_observation(
            "failed", self.source_project_input, self.rust_project_ir,
        )
        recorded = record_host_project_observation(
            ledger=self.ledger, out_root=self.out_root,
            out_root_rel="target/run", run_id="run", gate_kind="cargo-check",
            candidate_set_sha256=self.candidate_set,
            observation=observation,
            diagnostic_codes=["e0425", "e0432"],
            project_diagnostic_input={
                "rust_project_ir_sha256": self.rust_project_ir["ir_sha256"],
                "rust_project_interface_sha256": self.rust_project_ir[
                    "interface_sha256"
                ],
                "project_input_sha256": self.source_project_input,
                "diagnostics": partition.project_diagnostics,
            },
        )
        return recorded["project_diagnostic_intake"]


def project_verifier_diagnostic(
    module_id: str, source_code: str = "e0432",
) -> dict[str, Any]:
    return {
        "family": "compile", "source_code": source_code,
        "stage": "cargo-check", "message": "unresolved import `shared`",
        "location": {"file": "src/lib.rs", "line": 1, "column": 1},
        "project_diagnostic": build_project_diagnostic(
            code=f"project-verifier-{source_code}",
            entity_ids=[source_code, "file:src/lib.rs", module_id],
            affected_module_ids=[module_id],
        ),
    }


__all__ = [
    "ProjectVerifierRepairFlowSupportMixin", "project_verifier_diagnostic",
]

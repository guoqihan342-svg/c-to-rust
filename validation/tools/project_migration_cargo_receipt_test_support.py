from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from validation.tools._project_migration_harness.accepted_candidates import (
    accepted_candidate_descriptors,
)
from validation.tools._project_migration_harness.cargo_raw_output_evidence import (
    write_cargo_raw_output,
)
from validation.tools._project_migration_harness.project_cargo_classification_receipt import (
    write_cargo_classification_receipt,
)
from validation.tools._project_migration_harness.project_cargo_diagnostic_cohort import (
    decide_cargo_diagnostic_cohort,
)
from validation.tools._project_migration_harness.project_cargo_diagnostic_intake import (
    CargoDiagnosticPartition, partition_cargo_diagnostics,
)
from validation.tools._project_migration_harness.project_cargo_evidence import (
    bind_project_cargo_classification,
)
from validation.tools._project_migration_harness.ledger_run_contract import (
    load_migration_contract,
)
from validation.tools._project_migration_harness.project_interface_coordinator import (
    coordinate_project_interfaces,
)
from validation.tools._project_migration_harness.project_repair_authoritative_ir import (
    persist_authoritative_project_ir,
)
from validation.tools._project_migration_harness.project_rust_ir import (
    derive_bound_project_ir,
)
from validation.tools._project_migration_harness.sandbox_diagnostics import (
    cargo_check_diagnostics,
)
from validation.tools._project_migration_harness.rust_project_ir import (
    build_rust_project_ir,
)


def classified_cargo_observation(
    *, out_root: Path, out_root_rel: str, run_id: str, gate_kind: str,
    candidate_set_sha256: str, project_input_sha256: str,
    candidate_members: Sequence[Mapping[str, Any]],
    rust_project_ir: Mapping[str, Any], observation: Mapping[str, Any],
    stdout: str,
) -> tuple[dict[str, Any], CargoDiagnosticPartition]:
    result = json.loads(json.dumps(observation))
    result["schema_version"] = 2
    check = result["check"]
    for stream, data in (("stdout", stdout.encode("utf-8")), ("stderr", b"")):
        reference = write_cargo_raw_output(
            out_root, out_root_rel, gate_kind=gate_kind,
            stream=stream, data=data,
        )
        check[f"{stream}_sha256"] = reference["sha256"]
        check[f"{stream}_ref"] = reference
    status = str(check["status"])
    diagnostics = cargo_check_diagnostics(
        stdout, gate_kind.removeprefix("cargo-"), int(check["returncode"]),
    )
    partition = (
        partition_cargo_diagnostics(
            gate_kind=gate_kind, diagnostics=diagnostics,
            candidate_members=candidate_members,
            rust_project_ir=rust_project_ir,
        )
        if status == "failed" else CargoDiagnosticPartition({}, [], None)
    )
    source_check = {
        "status": status, "returncode": int(check["returncode"]),
        "stdout_ref": check["stdout_ref"], "stderr_ref": check["stderr_ref"],
        "diagnostics": diagnostics,
    }
    decision = decide_cargo_diagnostic_cohort(
        execution_status=status, checks={gate_kind: source_check},
        observations={gate_kind: {"outcome": "executed"}},
        partitions={gate_kind: partition},
        candidate_members=candidate_members,
    )
    receipt = write_cargo_classification_receipt(
        out_root, out_root_rel, run_id=run_id,
        candidate_set_sha256=candidate_set_sha256,
        project_input_sha256=project_input_sha256,
        rust_project_ir=rust_project_ir,
        candidate_members=candidate_members, checks={gate_kind: source_check},
        partitions={gate_kind: partition}, admission=decision.payload(),
    )
    return bind_project_cargo_classification(result, receipt), partition


def with_verifier_feature(value: dict[str, Any]) -> dict[str, Any]:
    module = value["modules"][0]
    return build_rust_project_ir(
        migration_dag_ref=value["bindings"]["migration_dag"],
        build_ir_refs=value["bindings"]["build_ir"],
        candidate_refs=value["bindings"]["candidates"],
        crate=value["crate"], modules=value["modules"],
        public_api=value["public_api"], shared_types=value["shared_types"],
        global_ownership=value["global_ownership"],
        initialization=value["initialization"],
        ffi_boundaries=value["ffi_boundaries"], cfgs=value["cfgs"],
        features=[*value["features"], {
            "feature_id": "project-verifier-feature", "name": "shared_feature",
            "default": False, "enables": [],
            "module_ids": [module["module_id"]], "evidence": module["evidence"],
        }],
        unsafe_obligations=value["unsafe_obligations"],
    )


def register_verifier_project_ir(
    ledger: Any, out_root: Path, out_root_rel: str,
) -> dict[str, Any]:
    with ledger.connect() as connection:
        contract, manifest = load_migration_contract(
            ledger.path, connection, "run",
        )
    descriptors = accepted_candidate_descriptors(
        ledger, run_id="run", out_root_rel=out_root_rel,
    )
    rust_project_ir = with_verifier_feature(derive_bound_project_ir(
        migration_contract=contract, migration_manifest=manifest,
        candidate_descriptors=descriptors, artifact_root=out_root,
    ))
    receipt = coordinate_project_interfaces(rust_project_ir)
    persist_authoritative_project_ir(
        rust_project_ir, out_root=out_root, out_root_rel=out_root_rel,
    )
    ledger.register_project_interface_receipt(
        run_id="run", receipt=receipt, rust_project_ir=rust_project_ir,
    )
    return rust_project_ir


__all__ = [
    "classified_cargo_observation", "register_verifier_project_ir",
    "with_verifier_feature",
]

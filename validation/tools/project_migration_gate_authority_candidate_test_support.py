from __future__ import annotations

import hashlib
import json
from pathlib import Path

from validation.tools._project_migration_harness.candidate_compile_evidence import (
    FIXED_CARGO_CHECK,
)
from validation.tools._project_migration_harness.gate_authority import (
    CANDIDATE_REQUIRED_GATES,
    candidate_authority,
    candidate_kind,
    candidate_verdict_payload,
)
from validation.tools._project_migration_harness.gate_evidence import (
    write_content_addressed_json,
)
from validation.tools._project_migration_harness.ledger_transition_authority import (
    TransitionAuthority, load_unit_projection,
)
from validation.tools._project_migration_harness.ledger_transition_commands import (
    attempt_finished_command, attempt_started_command,
)
from validation.tools._project_migration_harness.ledger_transition_policy import UnitState
from validation.tools._project_migration_harness.sandbox_contract import (
    SandboxContract,
    canonical_sha256,
)
from validation.tools._project_migration_harness.rust_candidate_facts import (
    derive_rust_metadata,
)
from validation.tools.project_migration_compile_test_support import (
    compile_observation_for_ledger,
)
from validation.tools.project_migration_semantic_test_support import (
    passed_strict_semantic_observation,
)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class CandidateGateAuthoritySupportMixin:
    def make_candidate(self, label: str) -> tuple[str, str]:
        candidate_sha = digest(label)
        candidate_id = label
        source_path = f"target/run/workers/translator/out/{label}.rs"
        target = self.harness.joinpath(*Path(source_path).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(label.encode("utf-8"))
        metadata = json.dumps(
            derive_rust_metadata(label), sort_keys=True, separators=(",", ":"),
        )
        with self.ledger.connect() as connection:
            ordinal = int(connection.execute(
                "select count(*)+1 from attempts where run_id='run' and unit_id='unit'"
            ).fetchone()[0])
            attempt = f"run:unit:translator:{ordinal}"
            now = f"2026-01-01T00:00:0{ordinal}Z"
            connection.execute(
                """insert into attempts(attempt_id,run_id,unit_id,role,ordinal,worker_id,
                   status,fencing_token,input_sha256,output_sha256,error_key,started_at,
                   finished_at,metadata_json)
                   values (?,?,?,?,?,?,'completed',?,?,?,null,?,?,?)""",
                (attempt, "run", "unit", "translator", ordinal, "translator", ordinal,
                 digest(f"input-{label}"), candidate_sha, now, now, "{}"),
            )
            connection.execute(
                """insert into artifacts(run_id,artifact_id,unit_id,attempt_id,worker_id,
                   fencing_token,kind,repo_rel_path,content_sha256,status,created_at,metadata_json)
                   values (?,?,?,?,?,?,?,?,?,'candidate',?,?)""",
                ("run", candidate_id, "unit", attempt, "translator", ordinal,
                 "rust-candidate", source_path, candidate_sha, now, metadata),
            )
            authority = TransitionAuthority(connection)
            authority.apply(
                attempt_started_command(
                    run_id="run", unit_id="unit", attempt_id=attempt,
                    fencing_token=ordinal,
                    expected=load_unit_projection(connection, "run", "unit"),
                    input_sha256=digest(f"input-{label}"),
                ),
                created_at=now,
            )
            authority.apply(
                attempt_finished_command(
                    run_id="run", unit_id="unit", attempt_id=attempt,
                    fencing_token=ordinal,
                    expected=load_unit_projection(connection, "run", "unit"),
                    target=UnitState("gate-pending", "awaiting_gate"),
                    reason="attempt_completed", evidence_sha256=candidate_sha,
                ),
                created_at=now,
            )
        return candidate_id, candidate_sha

    def record_candidate_host_gate(
        self, family: str, status: str, record_id: str,
    ) -> dict[str, str | int]:
        candidate_set = self.ledger.bind_verification_candidate_set(run_id="run")
        payload = candidate_verdict_payload(
            run_id="run",
            unit_id="unit",
            candidate_artifact_id=self.candidate_id,
            candidate_sha256=self.candidate_sha,
            gate_family=family,
            status=status,
            diagnostics=(
                [] if status == "passed"
                else [{"code": "host-failed", "stage": family}]
            ),
            candidate_set_sha256=candidate_set if status == "passed" else None,
            source_evidence=self.candidate_sources(
                family, status, candidate_set,
            ),
        )
        reference = write_content_addressed_json(
            self.out_root, f"candidate/{family}", payload,
        )
        full_path = f"target/run/{reference['path']}"
        self.ledger._record_derived_verification(
            record_id=record_id,
            run_id="run",
            unit_id="unit",
            candidate_artifact_id=self.candidate_id,
            kind=candidate_kind(family),
            status=status,
            verifier_id=candidate_authority(family),
            evidence_path=full_path,
            evidence_sha256=str(reference["sha256"]),
            gate_family=family,
        )
        return {**reference, "path": full_path}

    def candidate_sources(
        self, family: str, status: str, candidate_set: str,
        verification_scope: str = "wave-provisional",
    ) -> list[dict[str, str | int]]:
        if status != "passed":
            return []
        if family == "final-verification":
            return self._final_candidate_sources()
        if family == "compile":
            raw = compile_observation_for_ledger(
                self.ledger,
                self.harness,
                run_id="run",
                unit_id="unit",
                candidate_artifact_id=self.candidate_id,
                candidate_set_sha256=candidate_set,
                execution=_compile_execution(),
            )
        else:
            raw = passed_strict_semantic_observation(
                family, ledger=self.ledger,
                run_id="run",
                unit_id="unit",
                candidate_artifact_id=self.candidate_id,
                candidate_sha256=self.candidate_sha,
                candidate_set_sha256=candidate_set,
                verification_scope=verification_scope,
            )
        reference = write_content_addressed_json(
            self.out_root, f"raw/candidate/{family}", raw,
        )
        return [{**reference, "path": f"target/run/{reference['path']}"}]

    def _final_candidate_sources(self) -> list[dict[str, str | int]]:
        with self.ledger.connect() as connection:
            rows = connection.execute(
                """select evidence_path,evidence_sha256 from verifier_records v
                   where run_id='run' and unit_id='unit'
                     and candidate_artifact_id=? and gate_family!='final-verification'
                     and gate_epoch=(select max(newer.gate_epoch) from verifier_records newer
                       where newer.run_id=v.run_id and newer.unit_id=v.unit_id
                         and newer.candidate_artifact_id=v.candidate_artifact_id
                         and newer.gate_family=v.gate_family)
                   order by gate_family""",
                (self.candidate_id,),
            ).fetchall()
        return [{
            "path": str(row["evidence_path"]),
            "sha256": str(row["evidence_sha256"]),
            "size_bytes": self.harness.joinpath(
                *Path(str(row["evidence_path"])).parts
            ).stat().st_size,
        } for row in rows]

    def promote_current_candidate(self) -> None:
        records = {}
        ordered = ["compile", *sorted(CANDIDATE_REQUIRED_GATES - {"compile"})]
        for family in ordered:
            record_id = f"{self.candidate_id}-{family}"
            self.record_candidate_host_gate(family, "passed", record_id)
            records[family] = record_id
        final_id = f"{self.candidate_id}-final"
        self.record_candidate_host_gate("final-verification", "passed", final_id)
        self.ledger.promote_last_good_from_verification(
            run_id="run",
            unit_id="unit",
            candidate_artifact_id=self.candidate_id,
            verifier_record_id=records["compile"],
            gate_record_id=final_id,
        )


def _compile_execution() -> dict:
    sandbox_contract = SandboxContract(
        "bubblewrap-v1", digest("sandbox-launcher"), digest("toolchain"),
    )
    contract = sandbox_contract.sha256
    return {
        "project_state_unchanged": True,
        "checks": [{
            "command": list(FIXED_CARGO_CHECK),
            "status": "passed",
            "cargo_executed": True,
            "returncode": 0,
            "timed_out": False,
            "stdout_sha256": digest("stdout"),
            "stderr_sha256": digest("stderr"),
            "sandbox_contract_sha256": contract,
            "sandbox_command_sha256": canonical_sha256(FIXED_CARGO_CHECK),
            "sandbox_launcher_argv_sha256": digest("launcher-argv"),
        }],
        "sandbox": {
            "contract_sha256": contract,
            "contract": sandbox_contract.payload(),
        },
    }


__all__ = ["CandidateGateAuthoritySupportMixin", "digest"]

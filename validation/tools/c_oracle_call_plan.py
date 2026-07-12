from __future__ import annotations

from pathlib import Path
from typing import Any

from validation.tools.c_oracle_call_plan_direct import (
    render_direct_return_call_plan,
)
from validation.tools.c_oracle_call_plan_output import (
    render_output_binding_call_plan,
)


def render_c_oracle_call_plan(
    spec: dict[str, Any], repo_root: Path
) -> dict[str, Any]:
    if "c_oracle_contract" in spec:
        return render_output_binding_call_plan(spec, repo_root)
    return render_direct_return_call_plan(spec, repo_root)


def validate_c_oracle_call_plan_harness(
    spec: dict[str, Any],
    contract: Any,
    harness_text: str,
    repo_root: Path,
) -> None:
    if not isinstance(contract, dict):
        raise ValueError("C oracle call-plan contract is missing")
    rendered = render_c_oracle_call_plan(spec, repo_root)
    if contract.get("status") == "not_used":
        if rendered.get("status") == "generated":
            raise ValueError("generated C oracle call-plan contract is missing")
        return
    if contract.get("status") != "generated":
        raise ValueError("C oracle call-plan contract status is invalid")
    if rendered.get("status") != "generated":
        raise ValueError("C oracle call-plan contract cannot be regenerated")
    expected_contract = {
        "status": "generated",
        "replay_call_plan_sha256": rendered["replay_call_plan_sha256"],
        "case_count": rendered["case_count"],
        "compared_fields": rendered["compared_fields"],
        "output_protocol": rendered["output_protocol"],
        "protocol_record_count": len(rendered["protocol_records"]),
    }
    if "c_oracle_call_plan_sha256" in rendered:
        expected_contract["c_oracle_call_plan_sha256"] = rendered[
            "c_oracle_call_plan_sha256"
        ]
    if contract != expected_contract:
        raise ValueError("C oracle call-plan contract drifted")
    marker_sha = rendered.get(
        "c_oracle_call_plan_sha256", rendered["replay_call_plan_sha256"]
    )
    marker = f"COracleCallPlan-SHA256: {marker_sha}"
    if harness_text.count(marker) != 1:
        raise ValueError("C oracle call-plan marker is missing or duplicated")
    declarations = str(rendered["declarations"]).strip()
    statements = str(rendered["statements"])
    if declarations not in harness_text:
        raise ValueError("C oracle call-plan declarations drifted")
    if harness_text.count(statements) != 1:
        raise ValueError("C oracle call-plan target invocation or assertions drifted")


__all__ = [
    "render_c_oracle_call_plan",
    "validate_c_oracle_call_plan_harness",
]

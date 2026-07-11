from __future__ import annotations

import copy
from typing import Any

from validation.tools._translation_carrier_reporter.call_continue_contract import (
    behavior_fields,
    parse_contract,
)
from validation.tools._translation_carrier_reporter.call_continue_model import reference_outputs

from .common import sha256_bytes, stable_json_bytes
from .constants import SLICE_ID, TARGET_ID
from .contract import build_carrier_source, build_replay_contract
from .source_binding import validate_generator_input
from .spec import build_spec


def build_documents(
    generator_input: dict[str, Any],
    *,
    target_id: str = TARGET_ID,
    slice_id: str = SLICE_ID,
) -> tuple[dict[str, Any], dict[str, Any]]:
    validate_generator_input(generator_input)
    source = copy.deepcopy(generator_input["source"])
    c_source = build_carrier_source(source["fragment"]["text"])
    contract = build_replay_contract()
    outputs = behavior_fields(contract)
    fixture_path = f"validation/l2_slices/fixtures/{slice_id}.json"
    spec = build_spec(
        source=source,
        c_source=c_source,
        contract=contract,
        outputs=outputs,
        target_id=target_id,
        slice_id=slice_id,
        fixture_path=fixture_path,
    )
    parsed_contract = parse_contract(spec)
    cases = build_cases(generator_input["cases"], parsed_contract)
    fixture = {
        "schema_version": 2,
        "level": "L3",
        "target_id": target_id,
        "slice_id": slice_id,
        "source_commit": source["source_commit"],
        "source_boundary": {
            "files": [source["file"]],
            "functions": ["fdb_kv_iterate:zero-start-next-sector-advance-continue@1868-1874"],
        },
        "compared_fields": outputs,
        "case_count": len(cases),
        "cases": cases,
    }
    bind_fixture(spec, fixture, fixture_path)
    return spec, fixture


def build_cases(
    raw_cases: list[dict[str, Any]], contract: dict[str, Any]
) -> list[dict[str, Any]]:
    cases = []
    for raw_case in raw_cases:
        case = copy.deepcopy(raw_case)
        case["expected_outputs"] = reference_outputs(case, contract)
        cases.append(case)
    return cases


def bind_fixture(spec: dict[str, Any], fixture: dict[str, Any], fixture_path: str) -> None:
    fixture_hash = sha256_bytes(stable_json_bytes(fixture))
    spec["fixture_hash"] = fixture_hash
    spec["fixture_contract"]["hash"] = fixture_hash
    spec["fixture_contract"]["cases"] = [
        {
            "id": case["id"],
            "input_ref": f"cases[{index}]",
            "expected_ref": fixture_path,
            "expected_outputs": case["expected_outputs"],
        }
        for index, case in enumerate(fixture["cases"])
    ]

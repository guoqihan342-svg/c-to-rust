from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RUST_TYPE_RE = re.compile(r"^[A-Za-z0-9_&'\[\]<>:(), ]+$")
ACTUAL_RE = re.compile(r"^return(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
ALLOWED_ENCODINGS = {
    "u32",
    "u64",
    "i32",
    "usize",
    "u16",
    "bool",
    "string",
    "string_vec",
    "hex_bytes",
    "u8_array",
}
MAX_FIXTURE_BYTES = 4 * 1024 * 1024


def build_replay_call_plan(spec: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    contract = spec.get("replay_contract")
    if not isinstance(contract, dict):
        from validation.tools.replay_call_plan_scalar import build_implicit_scalar_contract

        contract = build_implicit_scalar_contract(spec)
    if not isinstance(contract, dict):
        from validation.tools.replay_call_plan_out import (
            build_implicit_i32_output_plan,
            supports_implicit_i32_output_plan,
        )

        if supports_implicit_i32_output_plan(spec):
            try:
                return build_implicit_i32_output_plan(
                    spec,
                    _fixture_binding(spec, repo_root.resolve()),
                )
            except ValueError as exc:
                return {"schema_version": 1, "status": "blocked", "reason": str(exc)}
            except (OSError, RuntimeError):
                return {
                    "schema_version": 1,
                    "status": "blocked",
                    "reason": "declarative replay fixture cannot be resolved",
                }
    if not isinstance(contract, dict):
        return {"schema_version": 1, "status": "unavailable"}
    contract_kind = contract.get("kind")
    if contract_kind not in {
        "declarative_call_plan",
        "readonly_byte_slice_bool_return",
        "record_u32_field_constant_state",
        "record_u32_field_wrapping_add_state",
        "record_u32_field_scalar_wrapping_add_state",
        "record_u32_field_postfix_increment_state",
        "record_pointer_identity_return",
        "record_buffer_length_identity_return",
        "opaque_context_return_code",
        "record_interior_projection_u32_constant_state",
        "record_owner_interior_stats_sequence_state",
        "record_owner_interior_guarded_stats_sequence_state",
        "record_owner_interior_u32_to_usize_wrapping_add_state",
        "record_interior_projection_u32_reset_add_while_continue_state",
        "scripted_external_u32_call_bool_out",
        "scripted_external_record_u32_call_bool_state",
        "scripted_external_record_u32_sequence_do_while_state",
        "scripted_external_u32_call_interior_reset_add_while_continue_state",
    }:
        return {"schema_version": 1, "status": "unavailable"}
    try:
        resolved_root = repo_root.resolve()
        if contract_kind == "record_pointer_identity_return":
            from validation.tools.replay_call_plan_record_identity import (
                build_record_pointer_identity_plan,
            )

            return build_record_pointer_identity_plan(
                spec,
                contract,
                _fixture_binding(spec, resolved_root),
            )
        if contract_kind == "record_buffer_length_identity_return":
            from validation.tools.replay_call_plan_record_buffer_identity import (
                build_record_buffer_identity_plan,
            )

            return build_record_buffer_identity_plan(
                spec,
                contract,
                _fixture_binding(spec, resolved_root),
            )
        if contract_kind == "opaque_context_return_code":
            from validation.tools.replay_call_plan_opaque_context import (
                build_opaque_context_plan,
            )

            return build_opaque_context_plan(
                spec,
                contract,
                _fixture_binding(spec, resolved_root),
            )
        if contract_kind in {
            "scripted_external_u32_call_bool_out",
            "scripted_external_record_u32_call_bool_state",
            "scripted_external_record_u32_sequence_do_while_state",
            "scripted_external_u32_call_interior_reset_add_while_continue_state",
        }:
            from validation.tools.replay_call_plan_v2 import build_scripted_external_plan

            return build_scripted_external_plan(
                spec,
                _validated_scripted_contract(spec, contract_kind),
                _fixture_binding(spec, resolved_root),
            )
        if contract_kind in {
            "record_u32_field_constant_state",
            "record_u32_field_wrapping_add_state",
            "record_u32_field_scalar_wrapping_add_state",
            "record_u32_field_postfix_increment_state",
        }:
            from validation.tools.replay_call_plan_v2 import (
                build_record_u32_constant_state_plan,
            )

            return build_record_u32_constant_state_plan(
                spec,
                contract,
                _fixture_binding(spec, resolved_root),
            )
        if contract_kind == "record_owner_interior_u32_to_usize_wrapping_add_state":
            from validation.tools.replay_call_plan_v2 import (
                build_record_owner_usize_wrapping_add_plan,
            )

            return build_record_owner_usize_wrapping_add_plan(
                spec,
                contract,
                _fixture_binding(spec, resolved_root),
            )
        if contract_kind == "record_interior_projection_u32_constant_state":
            from validation.tools.replay_call_plan_v2 import (
                build_record_interior_u32_constant_state_plan,
            )

            return build_record_interior_u32_constant_state_plan(
                spec,
                contract,
                _fixture_binding(spec, resolved_root),
            )
        if contract_kind == "record_interior_projection_u32_reset_add_while_continue_state":
            from validation.tools.replay_call_plan_v2 import (
                build_record_reset_add_while_continue_plan,
            )

            return build_record_reset_add_while_continue_plan(
                spec,
                contract,
                _fixture_binding(spec, resolved_root),
            )
        if contract_kind in {
            "record_owner_interior_stats_sequence_state",
            "record_owner_interior_guarded_stats_sequence_state",
        }:
            from validation.tools.replay_call_plan_v2 import (
                build_record_owner_stats_sequence_plan,
            )

            return build_record_owner_stats_sequence_plan(
                spec,
                contract,
                _fixture_binding(spec, resolved_root),
            )
        if contract_kind == "readonly_byte_slice_bool_return":
            contract = _readonly_byte_slice_bool_contract(contract)
        return _build_bound_plan(spec, contract, resolved_root)
    except ValueError as exc:
        return {
            "schema_version": 1,
            "status": "blocked",
            "reason": str(exc),
        }
    except (OSError, RuntimeError):
        return {
            "schema_version": 1,
            "status": "blocked",
            "reason": "declarative replay fixture cannot be resolved",
        }


def _build_bound_plan(
    spec: dict[str, Any],
    contract: dict[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    if contract.get("schema_version") != 3:
        raise ValueError("declarative replay contract schema_version must be 3")
    source_function_name = _identifier(spec.get("function_name"), "source function")
    signatures = spec.get("c_boundary", {}).get("signatures")
    matching_signatures = [
        item
        for item in signatures or []
        if isinstance(item, dict) and item.get("function") == source_function_name
    ]
    if len(matching_signatures) != 1:
        raise ValueError("declarative replay requires exactly one matching C signature")
    signature = matching_signatures[0]
    c_parameters = [item for item in signature.get("parameters", []) if isinstance(item, dict)]
    c_names = [_identifier(item.get("name"), "C parameter") for item in c_parameters]
    if len(c_names) != len(set(c_names)):
        raise ValueError("C signature parameter names must be unique")

    public_api = spec.get("rust_boundary", {}).get("public_api")
    api_entries = [item for item in public_api or [] if isinstance(item, dict)]
    if len(api_entries) != 1:
        raise ValueError("declarative replay requires exactly one Rust public API")
    api_name = _identifier(api_entries[0].get("name"), "Rust API")

    rust_api = contract.get("rust_api")
    if not isinstance(rust_api, dict):
        raise ValueError("declarative replay rust_api is required")
    visibility = rust_api.get("visibility")
    if visibility not in {"pub", "pub(crate)", "private"}:
        raise ValueError("Rust API visibility is unsupported")
    abi = rust_api.get("abi")
    if abi not in {"Rust", "C"}:
        raise ValueError("Rust API ABI is unsupported")
    unsafe = rust_api.get("unsafe")
    if not isinstance(unsafe, bool):
        raise ValueError("Rust API unsafe must be boolean")
    return_type = _rust_type(rust_api.get("return_type"), "return type")

    raw_parameters = rust_api.get("parameters")
    if not isinstance(raw_parameters, list):
        raise ValueError("Rust API parameters must be an array")
    normalized_parameters: list[dict[str, Any]] = []
    mapped_c_names: list[str] = []
    for position, raw_parameter in enumerate(raw_parameters):
        if not isinstance(raw_parameter, dict):
            raise ValueError("Rust API parameter must be an object")
        name = _identifier(raw_parameter.get("name"), "Rust parameter")
        c_parameter = _identifier(raw_parameter.get("c_parameter"), "C parameter mapping")
        if c_parameter not in c_names:
            raise ValueError(f"Rust parameter {name} maps unknown C parameter {c_parameter}")
        if c_parameter in mapped_c_names:
            raise ValueError(f"C parameter {c_parameter} is mapped more than once")
        source = _normalize_source(raw_parameter.get("source"))
        length_retained = raw_parameter.get("length_retained")
        if not isinstance(length_retained, bool):
            raise ValueError(f"Rust parameter {name} length_retained must be boolean")
        if source["kind"] == "encoded_length" and not length_retained:
            raise ValueError(f"derived length parameter {name} must be retained")
        normalized_parameters.append(
            {
                "position": position,
                "name": name,
                "rust_type": _rust_type(raw_parameter.get("rust_type"), "parameter type"),
                "c_parameter": c_parameter,
                "length_retained": length_retained,
                "source": source,
            }
        )
        mapped_c_names.append(c_parameter)
    rust_names = [item["name"] for item in normalized_parameters]
    if len(rust_names) != len(set(rust_names)):
        raise ValueError("Rust API parameter names must be unique")

    omitted = contract.get("omitted_c_parameters")
    if not isinstance(omitted, list):
        raise ValueError("omitted_c_parameters must be an array")
    omitted_names = [_identifier(item, "omitted C parameter") for item in omitted]
    if len(omitted_names) != len(set(omitted_names)):
        raise ValueError("omitted C parameters must be unique")
    if any(item not in c_names for item in omitted_names):
        raise ValueError("omitted_c_parameters contains an unknown C parameter")
    if set(mapped_c_names) & set(omitted_names):
        raise ValueError("a C parameter cannot be both mapped and omitted")
    if set(mapped_c_names) | set(omitted_names) != set(c_names):
        raise ValueError("C parameter mappings are not closed")

    assertions = _normalize_assertions(contract.get("assertions"))
    fixture_assertions = _normalize_fixture_assertions(
        contract.get("fixture_assertions", [])
    )
    observable_outputs = spec.get("fixture_contract", {}).get("observable_outputs")
    if not isinstance(observable_outputs, list) or not observable_outputs:
        raise ValueError("fixture observable_outputs are required")
    covered_outputs = {
        item["fixture_field"] for item in [*assertions, *fixture_assertions]
    }
    if covered_outputs != set(observable_outputs):
        raise ValueError("replay assertions must cover every observable output exactly")

    fixture = _fixture_binding(spec, repo_root)
    _validate_case_values(
        fixture["cases"], normalized_parameters, assertions, fixture_assertions
    )
    c_by_name = {item["name"]: item for item in c_parameters}
    plan: dict[str, Any] = {
        "schema_version": 1,
        "status": "bound",
        "source_function_name": source_function_name,
        "api_name": api_name,
        "visibility": visibility,
        "abi": abi,
        "unsafe": unsafe,
        "parameters": normalized_parameters,
        "c_parameter_mappings": [
            {
                "position": item["position"],
                "c_parameter": item["c_parameter"],
                "c_type": str(c_by_name[item["c_parameter"]].get("c_type") or ""),
                "direction": str(c_by_name[item["c_parameter"]].get("direction") or ""),
                "rust_parameter": item["name"],
                "rust_type": item["rust_type"],
            }
            for item in normalized_parameters
        ],
        "omitted_c_parameters": omitted_names,
        "length_parameters_retained": [
            item["name"] for item in normalized_parameters if item["length_retained"]
        ],
        "return_type": return_type,
        "supporting_types": _normalize_supporting_types(rust_api.get("supporting_types")),
        "call_args": [
            {
                "position": item["position"],
                "parameter": item["name"],
                "source": item["source"],
            }
            for item in normalized_parameters
        ],
        "assertions": assertions,
        "fixture": {
            "path": fixture["path"],
            "sha256": fixture["sha256"],
            "case_count": len(fixture["cases"]),
            "case_ids": [item["id"] for item in fixture["cases"]],
        },
    }
    if fixture_assertions:
        plan["fixture_assertions"] = fixture_assertions
    plan["plan_sha256"] = _plan_sha256(plan)
    validate_replay_call_plan(plan)
    return plan


def _validated_scripted_contract(spec: dict[str, Any], kind: str) -> dict[str, Any]:
    from validation.tools import auto_migrate

    validators = {
        "scripted_external_u32_call_bool_out":
            auto_migrate.scripted_external_u32_call_bool_out_replay_contract,
        "scripted_external_record_u32_call_bool_state":
            auto_migrate.scripted_external_record_u32_call_bool_state_replay_contract,
        "scripted_external_record_u32_sequence_do_while_state":
            auto_migrate.scripted_external_record_u32_sequence_do_while_state_replay_contract,
        "scripted_external_u32_call_interior_reset_add_while_continue_state":
            auto_migrate.call_continue_state_replay_contract,
    }
    validator = validators[kind]
    validated = validator(spec, auto_migrate.oracle_fixture_binding(spec))
    if not isinstance(validated, dict):
        raise ValueError("scripted external replay contract is unavailable")
    return validated


def render_declarative_replay_cases(
    spec: dict[str, Any],
    plan: dict[str, Any],
    repo_root: Path,
) -> str:
    validate_replay_call_plan(plan)
    fixture = _fixture_binding(spec, repo_root.resolve())
    if fixture["sha256"] != plan["fixture"]["sha256"]:
        raise ValueError("replay fixture binding drifted")
    if plan.get("schema_version") == 2:
        from validation.tools.replay_call_plan_v2 import render_replay_call_plan_v2

        return render_replay_call_plan_v2(plan, fixture["cases"])
    lines: list[str] = []
    for index, case in enumerate(fixture["cases"]):
        variable = f"actual_{_safe_ident(case['id'])}_{index}"
        arguments = [
            _source_literal(item["source"], case["inputs"])
            for item in plan["parameters"]
        ]
        lines.append(
            f"    let {variable}: {plan['return_type']} = "
            f"{plan['api_name']}({', '.join(arguments)});\n"
        )
        for assertion_index, assertion in enumerate(plan["assertions"]):
            actual = variable
            if assertion["actual"] != "return":
                actual += assertion["actual"][len("return") :]
            observed = f"observed_{_safe_ident(case['id'])}_{index}_{assertion_index}"
            expected = _encoded_literal(
                case["expected"][assertion["fixture_field"]],
                assertion["encoding"],
            )
            lines.append(
                f"    let {observed}: {assertion['rust_type']} = {actual};\n"
            )
            lines.append(
                f"    assert_eq!({observed}, {expected}, "
                f"{json.dumps(case['id'] + ' ' + assertion['fixture_field'] + ' drifted')});\n"
            )
        for assertion_index, assertion in enumerate(plan.get("fixture_assertions", [])):
            actual = _encoded_literal(
                case["expected"][assertion["fixture_field"]], assertion["encoding"]
            )
            expected = _encoded_literal(assertion["expected"], assertion["encoding"])
            lines.append(
                f"    assert_eq!({actual}, {expected}, "
                f"{json.dumps(case['id'] + ' ' + assertion['fixture_field'] + ' metadata drifted')});\n"
            )
    return "".join(lines)


def replay_call_plan_marker(plan: dict[str, Any]) -> str:
    validate_replay_call_plan(plan)
    return f"// ReplayCallPlan-SHA256: {plan['plan_sha256']}\n"


def validate_replay_call_plan(plan: dict[str, Any]) -> None:
    if isinstance(plan, dict) and plan.get("schema_version") == 2:
        from validation.tools.replay_call_plan_v2 import validate_replay_call_plan_v2

        validate_replay_call_plan_v2(plan)
        return
    if not isinstance(plan, dict) or plan.get("schema_version") != 1 or plan.get("status") != "bound":
        raise ValueError("ReplayCallPlan must be a bound schema v1 object")
    _identifier(plan.get("source_function_name"), "source function")
    _identifier(plan.get("api_name"), "Rust API")
    if plan.get("visibility") not in {"pub", "pub(crate)", "private"}:
        raise ValueError("ReplayCallPlan visibility is invalid")
    if plan.get("abi") not in {"Rust", "C"} or not isinstance(plan.get("unsafe"), bool):
        raise ValueError("ReplayCallPlan ABI or unsafe policy is invalid")
    _rust_type(plan.get("return_type"), "return type")
    parameters = plan.get("parameters")
    call_args = plan.get("call_args")
    if not isinstance(parameters, list) or not isinstance(call_args, list):
        raise ValueError("ReplayCallPlan parameters and call_args are required")
    if [item.get("position") for item in parameters if isinstance(item, dict)] != list(
        range(len(parameters))
    ):
        raise ValueError("ReplayCallPlan parameter order is invalid")
    normalized_parameters: list[dict[str, Any]] = []
    for item in parameters:
        if not isinstance(item, dict):
            raise ValueError("ReplayCallPlan parameter is invalid")
        normalized_parameters.append(
            {
                "position": item.get("position"),
                "name": _identifier(item.get("name"), "Rust parameter"),
                "rust_type": _rust_type(item.get("rust_type"), "parameter type"),
                "c_parameter": _identifier(item.get("c_parameter"), "C parameter mapping"),
                "length_retained": item.get("length_retained"),
                "source": _normalize_source(item.get("source")),
            }
        )
        if not isinstance(item.get("length_retained"), bool):
            raise ValueError("ReplayCallPlan length retention is invalid")
    if normalized_parameters != parameters:
        raise ValueError("ReplayCallPlan parameters are not canonical")
    names = [item["name"] for item in parameters]
    c_names = [item["c_parameter"] for item in parameters]
    if len(names) != len(set(names)) or len(c_names) != len(set(c_names)):
        raise ValueError("ReplayCallPlan parameter mappings are duplicated")
    c_parameter_mappings = plan.get("c_parameter_mappings")
    if not isinstance(c_parameter_mappings, list) or len(c_parameter_mappings) != len(parameters):
        raise ValueError("ReplayCallPlan C parameter mappings are invalid")
    for parameter, mapping in zip(parameters, c_parameter_mappings, strict=True):
        if (
            not isinstance(mapping, dict)
            or mapping.get("position") != parameter["position"]
            or mapping.get("c_parameter") != parameter["c_parameter"]
            or mapping.get("rust_parameter") != parameter["name"]
            or mapping.get("rust_type") != parameter["rust_type"]
            or not isinstance(mapping.get("c_type"), str)
            or not isinstance(mapping.get("direction"), str)
        ):
            raise ValueError("ReplayCallPlan C parameter mappings drifted")
    if call_args != [
        {"position": item["position"], "parameter": item["name"], "source": item["source"]}
        for item in parameters
    ]:
        raise ValueError("ReplayCallPlan call arguments drifted")
    if _normalize_assertions(plan.get("assertions")) != plan.get("assertions"):
        raise ValueError("ReplayCallPlan assertions are not canonical")
    if "fixture_assertions" in plan and _normalize_fixture_assertions(
        plan.get("fixture_assertions")
    ) != plan.get("fixture_assertions"):
        raise ValueError("ReplayCallPlan fixture assertions are not canonical")
    if _normalize_supporting_types(plan.get("supporting_types")) != plan.get("supporting_types"):
        raise ValueError("ReplayCallPlan supporting types are not canonical")
    omitted = plan.get("omitted_c_parameters")
    if not isinstance(omitted, list) or any(not isinstance(item, str) for item in omitted):
        raise ValueError("ReplayCallPlan omitted C parameters are invalid")
    omitted_names = [_identifier(item, "omitted C parameter") for item in omitted]
    if len(omitted_names) != len(set(omitted_names)) or set(omitted_names) & set(c_names):
        raise ValueError("ReplayCallPlan omitted C parameters are duplicated")
    expected_lengths = [item["name"] for item in parameters if item["length_retained"]]
    if plan.get("length_parameters_retained") != expected_lengths:
        raise ValueError("ReplayCallPlan retained length fields drifted")
    if any(
        item["source"]["kind"] == "encoded_length" and not item["length_retained"]
        for item in parameters
    ):
        raise ValueError("ReplayCallPlan derived length must be retained")
    fixture = plan.get("fixture")
    if (
        not isinstance(fixture, dict)
        or not isinstance(fixture.get("path"), str)
        or not re.fullmatch(r"[0-9a-f]{64}", str(fixture.get("sha256") or ""))
        or not isinstance(fixture.get("case_count"), int)
        or fixture["case_count"] < 1
    ):
        raise ValueError("ReplayCallPlan fixture binding is invalid")
    case_ids = fixture.get("case_ids")
    if (
        not isinstance(case_ids, list)
        or len(case_ids) != fixture["case_count"]
        or any(not isinstance(item, str) or not item for item in case_ids)
        or len(case_ids) != len(set(case_ids))
    ):
        raise ValueError("ReplayCallPlan fixture case identities are invalid")
    if not re.fullmatch(r"[0-9a-f]{64}", str(plan.get("plan_sha256") or "")):
        raise ValueError("ReplayCallPlan sha256 is invalid")
    if _plan_sha256(plan) != plan["plan_sha256"]:
        raise ValueError("ReplayCallPlan sha256 drifted")


def _fixture_binding(spec: dict[str, Any], repo_root: Path) -> dict[str, Any]:
    fixture_contract = spec.get("fixture_contract")
    if not isinstance(fixture_contract, dict):
        raise ValueError("fixture_contract is required")
    declared_cases = fixture_contract.get("cases")
    if not isinstance(declared_cases, list) or not declared_cases:
        raise ValueError("fixture_contract cases are required")
    explicit_cases = all(
        isinstance(item, dict)
        and isinstance(item.get("inputs"), dict)
        and isinstance(item.get("expected_outputs"), dict)
        for item in declared_cases
    )
    fixture_ref = fixture_contract.get("path") or fixture_contract.get("input")
    inline_cases = explicit_cases and (
        fixture_ref is None
        or all(item.get("input_ref") == "inline" for item in declared_cases)
    )
    if explicit_cases and not inline_cases:
        inline_cases = not _resolve_json_ref_path(fixture_ref, repo_root).is_file()
    if inline_cases:
        path = None
        payload = None
        data = json.dumps(
            {
                "cases": [
                    {
                        "id": item.get("id"),
                        "inputs": item["inputs"],
                        "expected_outputs": item["expected_outputs"],
                    }
                    for item in declared_cases
                ]
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    else:
        path, payload, data = _read_json_ref(fixture_ref, repo_root)
    cases: list[dict[str, Any]] = []
    for index, raw_case in enumerate(declared_cases):
        if not isinstance(raw_case, dict):
            raise ValueError("fixture case must be an object")
        case_id = str(raw_case.get("id") or f"case-{index}")
        input_ref = str(raw_case.get("input_ref") or f"cases[{index}]")
        case_index, input_section = (
            (index, None) if input_ref == "inline" else _case_ref_selector(input_ref)
        )
        input_payload = raw_case.get("inputs")
        if not isinstance(input_payload, dict):
            input_payload = _case_payload(payload, case_index, input_section)
        expected = raw_case.get("expected_outputs")
        if not isinstance(expected, dict) or not expected:
            expected_ref = raw_case.get("expected_ref") or fixture_ref
            _, expected_payload, _ = _read_json_ref(expected_ref, repo_root)
            expected = _case_payload(expected_payload, case_index)
            if isinstance(expected.get("expected_outputs"), dict):
                expected = expected["expected_outputs"]
        if not isinstance(input_payload, dict) or not isinstance(expected, dict):
            raise ValueError(f"fixture case {case_id} cannot be resolved")
        cases.append({"id": case_id, "inputs": input_payload, "expected": expected})
    return {
        "path": "inline" if path is None else path.relative_to(repo_root).as_posix(),
        "sha256": hashlib.sha256(data).hexdigest(),
        "cases": cases,
    }


def _read_json_ref(value: Any, repo_root: Path) -> tuple[Path, Any, bytes]:
    resolved = _resolve_json_ref_path(value, repo_root)
    if not resolved.is_file():
        raise ValueError("fixture reference is missing")
    data = resolved.read_bytes()
    if len(data) > MAX_FIXTURE_BYTES:
        raise ValueError("fixture reference is too large")
    try:
        return resolved, json.loads(data.decode("utf-8-sig")), data
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("fixture reference is not valid UTF-8 JSON") from exc


def _resolve_json_ref_path(value: Any, repo_root: Path) -> Path:
    if not isinstance(value, str) or not value or value == "inline":
        raise ValueError("fixture reference must be a repository-relative JSON path")
    path = Path(value.split("#", 1)[0])
    if path.is_absolute():
        raise ValueError("fixture reference must be repository-relative")
    unresolved = repo_root / path
    current = repo_root
    for part in path.parts:
        if part in {"", "."}:
            continue
        if part == "..":
            current = current.parent
            continue
        current = current / part
        is_junction = getattr(current, "is_junction", lambda: False)
        if current.is_symlink() or is_junction():
            raise ValueError("fixture reference must not traverse symbolic links")
    resolved = unresolved.resolve()
    try:
        resolved.relative_to(repo_root)
    except ValueError as exc:
        raise ValueError("fixture reference escapes repository root") from exc
    return resolved


def _case_ref_selector(value: str) -> tuple[int, str | None]:
    match = re.fullmatch(r"cases\[(\d+)\](?:\.(inputs|expected_outputs))?", value)
    if not match:
        raise ValueError("fixture input_ref must use cases[n] with an optional bounded section")
    return int(match.group(1)), match.group(2)


def _case_payload(payload: Any, index: int, section: str | None = None) -> dict[str, Any]:
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list) or index >= len(cases) or not isinstance(cases[index], dict):
        raise ValueError("fixture case reference is out of range")
    case = cases[index]
    if section is None:
        return case
    selected = case.get(section)
    if not isinstance(selected, dict):
        raise ValueError("fixture case section is missing")
    return selected


def _normalize_source(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("call argument source must be an object")
    kind = value.get("kind")
    field = _identifier(value.get("field"), "fixture source field")
    if kind == "fixture_field":
        encoding = value.get("encoding")
        if encoding not in ALLOWED_ENCODINGS:
            raise ValueError("fixture field encoding is unsupported")
        result = {"kind": kind, "field": field, "encoding": encoding}
        if "null_default" in value:
            result["null_default"] = value["null_default"]
        return result
    if kind == "encoded_length" and value.get("encoding") == "hex":
        return {"kind": kind, "field": field, "encoding": "hex"}
    raise ValueError("call argument source kind is unsupported")


def _readonly_byte_slice_bool_contract(contract: dict[str, Any]) -> dict[str, Any]:
    if contract.get("schema_version") != 1:
        raise ValueError("readonly byte-slice replay contract schema_version must be 1")
    input_contract = contract.get("input")
    output_contract = contract.get("output")
    if not isinstance(input_contract, dict) or not isinstance(output_contract, dict):
        raise ValueError("readonly byte-slice replay input and output are required")
    fixture_encoding = input_contract.get("fixture_encoding")
    if fixture_encoding not in {"hex", "hex_bytes", "u8_array"}:
        raise ValueError("readonly byte-slice replay encoding is unsupported")
    if input_contract.get("fixture_scalar_type") != "u8" or output_contract.get("rust_type") != "bool":
        raise ValueError("readonly byte-slice replay encoding is unsupported")
    value_parameter = _identifier(input_contract.get("parameter"), "byte-slice parameter")
    length_parameter = _identifier(input_contract.get("length_parameter"), "length parameter")
    value_field = _identifier(input_contract.get("fixture_field"), "byte-slice fixture field")
    length_field = _identifier(input_contract.get("length_field"), "length fixture field")
    output_field = _identifier(output_contract.get("fixture_field"), "output fixture field")
    return {
        "schema_version": 3,
        "kind": "declarative_call_plan",
        "rust_api": {
            "visibility": "pub",
            "abi": "Rust",
            "unsafe": False,
            "parameters": [
                {
                    "name": value_parameter,
                    "rust_type": "&[u8]",
                    "c_parameter": value_parameter,
                    "length_retained": False,
                    "source": {
                        "kind": "fixture_field",
                        "field": value_field,
                        "encoding": "u8_array" if fixture_encoding == "u8_array" else "hex_bytes",
                    },
                },
                {
                    "name": length_parameter,
                    "rust_type": "usize",
                    "c_parameter": length_parameter,
                    "length_retained": True,
                    "source": {
                        "kind": "fixture_field",
                        "field": length_field,
                        "encoding": "usize",
                    },
                },
            ],
            "return_type": "bool",
            "supporting_types": [],
        },
        "omitted_c_parameters": [],
        "assertions": [
            {
                "actual": "return",
                "fixture_field": output_field,
                "rust_type": "bool",
                "encoding": "bool",
            }
        ],
    }


def _normalize_assertions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError("replay assertions are required")
    result: list[dict[str, Any]] = []
    fields: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict) or not ACTUAL_RE.fullmatch(str(raw.get("actual") or "")):
            raise ValueError("replay assertion actual path is invalid")
        field = _identifier(raw.get("fixture_field"), "assertion fixture field")
        if field in fields:
            raise ValueError("replay assertion fixture fields must be unique")
        encoding = raw.get("encoding")
        if encoding not in ALLOWED_ENCODINGS - {"hex_bytes"}:
            raise ValueError("replay assertion encoding is unsupported")
        result.append(
            {
                "actual": raw["actual"],
                "fixture_field": field,
                "rust_type": _rust_type(raw.get("rust_type"), "assertion type"),
                "encoding": encoding,
            }
        )
        fields.add(field)
    return result


def _normalize_fixture_assertions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("fixture assertions must be an array")
    result: list[dict[str, Any]] = []
    fields: set[str] = set()
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("fixture assertion must be an object")
        field = _identifier(raw.get("fixture_field"), "fixture assertion field")
        encoding = raw.get("encoding")
        if field in fields or encoding not in {"u32", "u64", "i32", "usize", "bool", "string", "string_vec"}:
            raise ValueError("fixture assertion field or encoding is invalid")
        _encoded_literal(raw.get("expected"), encoding)
        result.append(
            {
                "fixture_field": field,
                "encoding": encoding,
                "expected": raw.get("expected"),
            }
        )
        fields.add(field)
    return result


def _normalize_supporting_types(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("supporting_types must be an array")
    result: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, dict) or raw.get("kind") != "struct":
            raise ValueError("only struct supporting types are supported")
        fields = raw.get("fields")
        if not isinstance(fields, list) or not fields:
            raise ValueError("supporting struct fields are required")
        visibility = raw.get("visibility")
        if visibility not in {"pub", "pub(crate)", "private"}:
            raise ValueError("supporting type visibility is unsupported")
        result.append(
            {
                "kind": "struct",
                "name": _identifier(raw.get("name"), "supporting type"),
                "visibility": visibility,
                "fields": [
                    {
                        "name": _identifier(field.get("name"), "supporting field"),
                        "rust_type": _rust_type(field.get("rust_type"), "supporting field type"),
                    }
                    for field in fields
                    if isinstance(field, dict)
                ],
            }
        )
        if len(result[-1]["fields"]) != len(fields):
            raise ValueError("supporting struct field must be an object")
        field_names = [field["name"] for field in result[-1]["fields"]]
        if len(field_names) != len(set(field_names)):
            raise ValueError("supporting struct fields must be unique")
    type_names = [item["name"] for item in result]
    if len(type_names) != len(set(type_names)):
        raise ValueError("supporting types must be unique")
    return result


def _validate_case_values(
    cases: list[dict[str, Any]],
    parameters: list[dict[str, Any]],
    assertions: list[dict[str, Any]],
    fixture_assertions: list[dict[str, Any]],
) -> None:
    for case in cases:
        for parameter in parameters:
            _source_literal(parameter["source"], case["inputs"])
        for assertion in assertions:
            field = assertion["fixture_field"]
            if field not in case["expected"]:
                raise ValueError(f"fixture case {case['id']} is missing expected field {field}")
            _encoded_literal(case["expected"][field], assertion["encoding"])
        for assertion in fixture_assertions:
            field = assertion["fixture_field"]
            if field not in case["expected"]:
                raise ValueError(f"fixture case {case['id']} is missing metadata field {field}")
            if case["expected"][field] != assertion["expected"]:
                raise ValueError(f"fixture case {case['id']} metadata field {field} drifted")
            _encoded_literal(case["expected"][field], assertion["encoding"])


def _source_literal(source: dict[str, Any], payload: dict[str, Any]) -> str:
    field = source["field"]
    if field not in payload:
        raise ValueError(f"fixture input field {field} is missing")
    value = payload[field]
    if value is None and "null_default" in source:
        value = source["null_default"]
    if source["kind"] == "encoded_length":
        return f"{len(_decode_hex(value))}usize"
    return _encoded_literal(value, source["encoding"])


def _encoded_literal(value: Any, encoding: str) -> str:
    if encoding == "u32":
        return f"{_integer(value, 0, 2**32 - 1, encoding)}u32"
    if encoding == "u64":
        return f"{_integer(value, 0, 2**64 - 1, encoding)}u64"
    if encoding == "i32":
        return f"{_integer(value, -(2**31), 2**31 - 1, encoding)}i32"
    if encoding == "usize":
        return f"{_integer(value, 0, 2**64 - 1, encoding)}usize"
    if encoding == "u16":
        return f"{_integer(value, 0, 2**16 - 1, encoding)}u16"
    if encoding == "bool" and isinstance(value, bool):
        return "true" if value else "false"
    if encoding == "string" and isinstance(value, str):
        return json.dumps(value, ensure_ascii=True)
    if encoding == "string_vec" and isinstance(value, list) and len(value) <= 64:
        if not all(isinstance(item, str) for item in value):
            raise ValueError("string_vec fixture field is invalid")
        return "&[" + ", ".join(json.dumps(item, ensure_ascii=True) for item in value) + "]"
    if encoding == "hex_bytes":
        return "&[" + ", ".join(f"{item}u8" for item in _decode_hex(value)) + "]"
    if encoding == "u8_array" and isinstance(value, list):
        items = [_integer(item, 0, 255, encoding) for item in value]
        return "&[" + ", ".join(f"{item}u8" for item in items) + "]"
    raise ValueError(f"value does not match replay encoding {encoding}")


def _decode_hex(value: Any) -> bytes:
    if not isinstance(value, str) or len(value) % 2 or not re.fullmatch(r"[0-9a-fA-F]*", value):
        raise ValueError("hex fixture field is invalid")
    return bytes.fromhex(value)


def _integer(value: Any, minimum: int, maximum: int, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"value does not match replay encoding {label}")
    return value


def _identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value):
        raise ValueError(f"{label} identifier is invalid")
    return value


def _rust_type(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or not RUST_TYPE_RE.fullmatch(value):
        raise ValueError(f"Rust {label} is invalid")
    return value


def _safe_ident(value: str) -> str:
    result = re.sub(r"[^A-Za-z0-9_]", "_", value)
    return result if result and not result[0].isdigit() else f"case_{result}"


def _plan_sha256(plan: dict[str, Any]) -> str:
    payload = {key: value for key, value in plan.items() if key != "plan_sha256"}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "build_replay_call_plan",
    "render_declarative_replay_cases",
    "replay_call_plan_marker",
    "validate_replay_call_plan",
]

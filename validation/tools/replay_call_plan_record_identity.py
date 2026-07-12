from __future__ import annotations

import re
from typing import Any

from validation.tools.replay_call_plan_v2 import _plan_sha256


__all__ = [
    "supports_record_pointer_identity_plan",
    "build_record_pointer_identity_plan",
]


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RUST_KEYWORDS = {
    "Self", "as", "async", "await", "break", "const", "continue", "crate",
    "dyn", "else", "enum", "extern", "false", "fn", "for", "if", "impl",
    "in", "let", "loop", "match", "mod", "move", "mut", "pub", "ref",
    "return", "self", "static", "struct", "super", "trait", "true", "type",
    "union", "unsafe", "use", "where", "while",
}
RECORD_KEYS = {"parameter", "fixture_root", "rust_type", "fields", "defaults"}
INPUT_FIELD_KEYS = {
    "fixture_path", "rust_field_path", "rust_type_path", "fixture_scalar_type",
    "rust_scalar_type", "conversion",
}
OUTPUT_FIELD_KEYS = {
    "initial_fixture_path", "expected_output", "rust_field_path", "rust_type_path",
    "fixture_scalar_type", "rust_scalar_type", "conversion",
}
DEFAULT_KEYS = {"rust_field_path", "rust_type_path", "rust_scalar_type", "value"}
POINTER_RUST_TYPES = {
    "raw_const_ptr": "*const core::ffi::c_void",
    "raw_mut_ptr": "*mut core::ffi::c_void",
}


def supports_record_pointer_identity_plan(spec: dict[str, Any]) -> bool:
    contract = spec.get("replay_contract") if isinstance(spec, dict) else None
    if not isinstance(contract, dict) or contract.get("kind") != "record_pointer_identity_return":
        return False
    try:
        _parse_contract(spec, contract)
    except ValueError:
        return False
    return True


def build_record_pointer_identity_plan(
    spec: dict[str, Any],
    contract: dict[str, Any],
    fixture: dict[str, Any],
) -> dict[str, Any]:
    if contract != spec.get("replay_contract"):
        raise ValueError("record identity replay contract drifted from the slice spec")
    model = _parse_contract(spec, contract)
    _validate_fixture(spec, fixture, model)

    supporting_types: dict[str, dict[str, Any]] = {}
    input_binding = _binding(model["input"], False, supporting_types)
    output_binding = _binding(model["output"], True, supporting_types)
    bindings = [input_binding, output_binding]
    binding_by_parameter = {item["name"]: item for item in bindings}

    parameters: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    for position, c_parameter in enumerate(model["signature_parameters"]):
        name = c_parameter["name"]
        binding = binding_by_parameter[name]
        is_output = name == model["output"]["parameter"]
        rust_type = f"&mut {binding['rust_type']}" if is_output else f"&{binding['rust_type']}"
        source = {
            "kind": "binding_borrow_mut" if is_output else "binding_borrow",
            "binding": name,
        }
        parameters.append(
            {
                "position": position,
                "name": name,
                "rust_type": rust_type,
                "c_parameter": name,
                "length_retained": False,
                "source": source,
            }
        )
        mappings.append(
            {
                "position": position,
                "c_parameter": name,
                "c_type": str(c_parameter.get("c_type") or ""),
                "direction": str(c_parameter.get("direction") or ""),
                "rust_parameter": name,
                "rust_type": rust_type,
            }
        )

    output_name = model["output"]["parameter"]
    assertions = [
        {
            "actual": f"binding.{output_name}." + ".".join(field["rust_field_path"]),
            "fixture_field": field["expected_output"],
            "rust_type": field["rust_scalar_type"],
            "encoding": field["rust_scalar_type"],
        }
        for field in model["output"]["fields"]
    ]
    identity_field = f"return_same_{output_name}"
    plan: dict[str, Any] = {
        "schema_version": 2,
        "status": "bound",
        "source_function_name": model["function_name"],
        "api_name": model["api_name"],
        "visibility": "pub",
        "abi": "Rust",
        "unsafe": False,
        "parameters": parameters,
        "c_parameter_mappings": mappings,
        "omitted_c_parameters": [],
        "length_parameters_retained": [],
        "return_type": f"&mut {model['output']['rust_type']}",
        "supporting_types": list(supporting_types.values()),
        "bindings": bindings,
        "distinct_mutable_bindings": [
            sorted([model["input"]["parameter"], output_name])
        ],
        "call_args": [
            {"position": item["position"], "parameter": item["name"], "source": item["source"]}
            for item in parameters
        ],
        "assertions": assertions,
        "identity_assertions": [
            {
                "kind": "reference_identity",
                "actual": "return",
                "expected_binding": output_name,
                "mutability": "mutable",
                "fixture_field": identity_field,
            }
        ],
        "fixture": {
            "path": fixture["path"],
            "sha256": fixture["sha256"],
            "case_count": len(fixture["cases"]),
            "case_ids": [item["id"] for item in fixture["cases"]],
        },
    }
    _validate_produced_plan(plan, model)
    plan["plan_sha256"] = _plan_sha256(plan)
    return plan


def _parse_contract(spec: dict[str, Any], contract: dict[str, Any]) -> dict[str, Any]:
    _exact_keys(
        contract,
        {"schema_version", "kind", "input", "output", "return", "noalias_refs"},
        "record identity contract",
    )
    if contract.get("schema_version") != 1:
        raise ValueError("record identity contract schema_version must be 1")
    if contract.get("kind") != "record_pointer_identity_return":
        raise ValueError("record identity contract kind is unsupported")
    if contract.get("return") != {"kind": "identity", "parameter_ref": "output"}:
        raise ValueError("record identity return must bind the output record")
    if contract.get("noalias_refs") != [["input", "output"]]:
        raise ValueError("record identity noalias refs must close input/output exactly")

    input_record = _record(contract.get("input"), "input")
    output_record = _record(contract.get("output"), "output")
    if input_record["parameter"] == output_record["parameter"]:
        raise ValueError("record identity parameters must be distinct")

    function_name = _ident(spec.get("function_name"), "source function")
    signature = _matching_signature(spec, function_name)
    raw_parameters = signature.get("parameters")
    if not isinstance(raw_parameters, list) or len(raw_parameters) != 2:
        raise ValueError("record identity signature must contain exactly two parameters")
    parameters = []
    for item in raw_parameters:
        if not isinstance(item, dict):
            raise ValueError("record identity C parameter must be an object")
        normalized = dict(item)
        normalized["name"] = _ident(item.get("name"), "C parameter")
        parameters.append(normalized)
    names = [item["name"] for item in parameters]
    expected_names = {input_record["parameter"], output_record["parameter"]}
    if len(set(names)) != 2 or set(names) != expected_names:
        raise ValueError("record identity contract parameters do not close the C signature")
    by_name = {item["name"]: item for item in parameters}
    if by_name[input_record["parameter"]].get("direction") != "input":
        raise ValueError("record identity input direction drifted")
    if by_name[output_record["parameter"]].get("direction") not in {"output", "inout"}:
        raise ValueError("record identity output direction drifted")
    if _c_type(signature.get("return_type")) != _c_type(
        by_name[output_record["parameter"]].get("c_type")
    ):
        raise ValueError("record identity return type does not match the output pointer type")
    _validate_identity_source(signature, output_record["parameter"])
    _validate_pointer_proof(spec, input_record["parameter"], output_record["parameter"])

    observable = spec.get("fixture_contract", {}).get("observable_outputs")
    expected_observable = {
        f"return_same_{output_record['parameter']}",
        *(item["expected_output"] for item in output_record["fields"]),
    }
    if not isinstance(observable, list) or len(observable) != len(set(observable)):
        raise ValueError("record identity observable outputs must be unique")
    if set(observable) != expected_observable:
        raise ValueError("record identity observable outputs are not closed")
    behavior = spec.get("fixture_contract", {}).get("behavior_fields")
    if behavior is not None and behavior != observable:
        raise ValueError("record identity behavior fields drifted from observable outputs")

    return {
        "function_name": function_name,
        "api_name": _public_api(spec),
        "signature_parameters": parameters,
        "input": input_record,
        "output": output_record,
        "observable": observable,
    }


def _record(value: Any, role: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"record identity {role} definition is required")
    _exact_keys(value, RECORD_KEYS, f"record identity {role} definition")
    result = {
        "parameter": _ident(value.get("parameter"), f"{role} parameter"),
        "fixture_root": _fixture_path(value.get("fixture_root"), f"{role} fixture root"),
        "rust_type": _ident(value.get("rust_type"), f"{role} Rust type"),
        "fields": _fields(value.get("fields"), role),
        "defaults": _defaults(value.get("defaults"), role),
    }
    _validate_record_topology(result, role)
    return result


def _fields(value: Any, role: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"record identity {role} fields are required")
    result: list[dict[str, Any]] = []
    fixture_key = "fixture_path" if role == "input" else "initial_fixture_path"
    required = INPUT_FIELD_KEYS if role == "input" else OUTPUT_FIELD_KEYS
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError(f"record identity {role} field must be an object")
        _exact_keys(raw, required, f"record identity {role} field")
        fixture_type = raw.get("fixture_scalar_type")
        rust_type = raw.get("rust_scalar_type")
        conversion = raw.get("conversion")
        _scalar_conversion(fixture_type, rust_type, conversion)
        item = {
            fixture_key: _fixture_path(raw.get(fixture_key), fixture_key),
            "rust_field_path": _rust_path(raw.get("rust_field_path"), "Rust field path"),
            "rust_type_path": _rust_type_path(raw.get("rust_type_path")),
            "fixture_scalar_type": fixture_type,
            "rust_scalar_type": rust_type,
            "conversion": conversion,
        }
        if role == "output":
            expected = raw.get("expected_output")
            if not isinstance(expected, str) or not expected:
                raise ValueError("record identity output expected field is required")
            item["expected_output"] = expected
        if len(item["rust_type_path"]) != len(item["rust_field_path"]) - 1:
            raise ValueError("record identity Rust type path length drifted")
        result.append(item)
    return result


def _defaults(value: Any, role: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"record identity {role} defaults must be an array")
    allowed = {
        "u32": "zero",
        "usize": "zero",
        "raw_const_ptr": "null",
        "raw_mut_ptr": "null_mut",
    }
    result = []
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError(f"record identity {role} default must be an object")
        _exact_keys(raw, DEFAULT_KEYS, f"record identity {role} default")
        scalar_type = raw.get("rust_scalar_type")
        default = raw.get("value")
        if scalar_type not in allowed or default != {"kind": allowed[scalar_type]}:
            raise ValueError("record identity default type/value pair is unsupported")
        rust_path = _rust_path(raw.get("rust_field_path"), "default Rust field path")
        type_path = _rust_type_path(raw.get("rust_type_path"))
        if len(type_path) != len(rust_path) - 1:
            raise ValueError("record identity default Rust type path length drifted")
        result.append(
            {
                "rust_field_path": rust_path,
                "rust_type_path": type_path,
                "rust_scalar_type": scalar_type,
                "value": dict(default),
            }
        )
    return result


def _validate_record_topology(record: dict[str, Any], role: str) -> None:
    fixture_key = "fixture_path" if role == "input" else "initial_fixture_path"
    fixture_paths = [tuple(item[fixture_key]) for item in record["fields"]]
    rust_paths = [
        tuple(item["rust_field_path"]) for item in [*record["fields"], *record["defaults"]]
    ]
    if len(set(fixture_paths)) != len(fixture_paths):
        raise ValueError(f"record identity duplicate {role} fixture path")
    if len(set(rust_paths)) != len(rust_paths):
        raise ValueError(f"record identity duplicate {role} Rust field path")
    if role == "output":
        expected = [item["expected_output"] for item in record["fields"]]
        if len(set(expected)) != len(expected):
            raise ValueError("record identity duplicate output observable")
    prefix_types: dict[tuple[str, ...], str] = {}
    for item in [*record["fields"], *record["defaults"]]:
        path = tuple(item["rust_field_path"])
        for other in rust_paths:
            if path != other and len(path) < len(other) and other[: len(path)] == path:
                raise ValueError("record identity Rust field path has a prefix conflict")
        for index, rust_type in enumerate(item["rust_type_path"]):
            prefix = path[: index + 1]
            if prefix in prefix_types and prefix_types[prefix] != rust_type:
                raise ValueError("record identity Rust type path is inconsistent")
            prefix_types[prefix] = rust_type


def _binding(
    record: dict[str, Any],
    mutable: bool,
    supporting_types: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    tree: dict[str, Any] = {"rust_type": record["rust_type"], "children": {}}
    fixture_key = "fixture_path" if mutable is False else "initial_fixture_path"
    for field in record["fields"]:
        source = {
            "kind": "fixture_field",
            "path": [*record["fixture_root"], *field[fixture_key]],
            "encoding": field["rust_scalar_type"],
        }
        _insert_tree(tree, field["rust_field_path"], field["rust_type_path"], source)
    for default in record["defaults"]:
        scalar_type = default["rust_scalar_type"]
        if scalar_type in {"u32", "usize"}:
            source = {
                "kind": "constant_scalar",
                "rust_type": scalar_type,
                "encoding": scalar_type,
                "value": 0,
            }
        else:
            source = {
                "kind": "null_pointer",
                "rust_type": POINTER_RUST_TYPES[scalar_type],
                "mutability": "mutable" if scalar_type == "raw_mut_ptr" else "shared",
            }
        _insert_tree(tree, default["rust_field_path"], default["rust_type_path"], source)
    initializer = _tree_initializer(tree, supporting_types)
    return {
        "name": record["parameter"],
        "rust_type": record["rust_type"],
        "mutable": mutable,
        "initializer": initializer,
    }


def _insert_tree(
    tree: dict[str, Any], path: list[str], type_path: list[str], source: dict[str, Any]
) -> None:
    node = tree
    for index, name in enumerate(path):
        children = node["children"]
        if index == len(path) - 1:
            if name in children:
                raise ValueError("record identity duplicate initializer path")
            children[name] = {"leaf": source, "rust_type": _source_rust_type(source)}
            return
        child_type = type_path[index]
        child = children.get(name)
        if child is None:
            child = {"rust_type": child_type, "children": {}}
            children[name] = child
        if child.get("rust_type") != child_type or "children" not in child:
            raise ValueError("record identity initializer type path drifted")
        node = child


def _tree_initializer(
    node: dict[str, Any], supporting_types: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    fields = []
    type_fields = []
    for name, child in node["children"].items():
        value = child["leaf"] if "leaf" in child else _tree_initializer(child, supporting_types)
        fields.append({"name": name, "value": value})
        type_fields.append({"name": name, "rust_type": child["rust_type"]})
    if not fields:
        raise ValueError("record identity initializer record is empty")
    definition = {
        "kind": "struct",
        "name": node["rust_type"],
        "visibility": "pub",
        "fields": type_fields,
    }
    previous = supporting_types.get(node["rust_type"])
    if previous is not None and previous != definition:
        raise ValueError("record identity supporting type definitions conflict")
    supporting_types[node["rust_type"]] = definition
    return {"kind": "struct", "rust_type": node["rust_type"], "fields": fields}


def _source_rust_type(source: dict[str, Any]) -> str:
    if source["kind"] == "fixture_field":
        return source["encoding"]
    return source["rust_type"]


def _validate_fixture(spec: dict[str, Any], fixture: dict[str, Any], model: dict[str, Any]) -> None:
    if not isinstance(fixture, dict):
        raise ValueError("record identity fixture binding is required")
    if not isinstance(fixture.get("path"), str) or not fixture["path"]:
        raise ValueError("record identity fixture path is invalid")
    if not SHA256_RE.fullmatch(str(fixture.get("sha256") or "")):
        raise ValueError("record identity fixture sha256 is invalid")
    cases = fixture.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("record identity fixture cases are required")
    ids = [item.get("id") if isinstance(item, dict) else None for item in cases]
    if any(not isinstance(item, str) or not item for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("record identity fixture case ids are invalid")
    declared = spec.get("fixture_contract", {}).get("cases")
    if not isinstance(declared, list) or [item.get("id") for item in declared] != ids:
        raise ValueError("record identity fixture case ids drifted")

    identity_field = f"return_same_{model['output']['parameter']}"
    expected_fields = {
        identity_field, *(item["expected_output"] for item in model["output"]["fields"])
    }
    for index, case in enumerate(cases):
        if set(case) != {"id", "inputs", "expected"}:
            raise ValueError("record identity fixture case binding shape drifted")
        inputs = case["inputs"]
        expected = case["expected"]
        if not isinstance(inputs, dict) or not isinstance(expected, dict):
            raise ValueError("record identity fixture case payload is incomplete")
        if set(expected) != expected_fields or expected.get(identity_field) is not True:
            raise ValueError("record identity expected outputs drifted")
        declared_expected = declared[index].get("expected_outputs")
        if not isinstance(declared_expected, dict) or declared_expected != expected:
            raise ValueError("record identity declared fixture outputs drifted")
        _validate_fixture_record(inputs, model["input"], "input")
        _validate_fixture_record(inputs, model["output"], "output")
        for field in model["output"]["fields"]:
            _scalar_value(expected[field["expected_output"]], field["fixture_scalar_type"])


def _validate_fixture_record(inputs: dict[str, Any], record: dict[str, Any], role: str) -> None:
    root = _value_at_path(inputs, record["fixture_root"])
    fixture_key = "fixture_path" if role == "input" else "initial_fixture_path"
    expected_paths = {tuple(item[fixture_key]) for item in record["fields"]}
    try:
        actual_paths = _leaf_paths(root)
    except ValueError as exc:
        raise ValueError(f"record identity {role} fixture shape drifted") from exc
    if actual_paths != expected_paths:
        raise ValueError(f"record identity {role} fixture shape drifted")
    for field in record["fields"]:
        _scalar_value(_value_at_path(root, field[fixture_key]), field["fixture_scalar_type"])


def _validate_produced_plan(plan: dict[str, Any], model: dict[str, Any]) -> None:
    parameter_names = [item["name"] for item in plan["parameters"]]
    signature_names = [item["name"] for item in model["signature_parameters"]]
    if parameter_names != signature_names:
        raise ValueError("record identity plan reordered C parameters")
    binding_names = [item["name"] for item in plan["bindings"]]
    if set(binding_names) != {model["input"]["parameter"], model["output"]["parameter"]}:
        raise ValueError("record identity plan binding closure drifted")
    covered = {item["fixture_field"] for item in plan["assertions"]}
    covered.update(item["fixture_field"] for item in plan["identity_assertions"])
    if covered != set(model["observable"]):
        raise ValueError("record identity plan does not cover every observable exactly")
    if len(covered) != len(plan["assertions"]) + len(plan["identity_assertions"]):
        raise ValueError("record identity plan observable coverage is duplicated")


def _validate_pointer_proof(spec: dict[str, Any], input_name: str, output_name: str) -> None:
    pointer = spec.get("c_boundary", {}).get("pointer_contract")
    if not isinstance(pointer, dict):
        raise ValueError("record identity pointer contract is required")
    required_pair = frozenset((input_name, output_name))
    pairs = pointer.get("noalias_required")
    if not isinstance(pairs, list) or len(pairs) != 1:
        raise ValueError("record identity pointer noalias proof is not closed")
    pair = pairs[0]
    if not isinstance(pair, list) or len(pair) != 2 or frozenset(pair) != required_pair:
        raise ValueError("record identity pointer noalias pair drifted")
    input_buffers = pointer.get("input_buffers")
    output_pointers = pointer.get("output_pointers")
    if (
        not isinstance(input_buffers, list)
        or not isinstance(output_pointers, list)
        or [item.get("name") for item in input_buffers if isinstance(item, dict)] != [input_name]
        or [item.get("name") for item in output_pointers if isinstance(item, dict)] != [output_name]
        or len(input_buffers) != 1
        or len(output_pointers) != 1
    ):
        raise ValueError("record identity pointer roles do not close the signature")
    alias = pointer.get("alias_contract")
    actual = pointer.get("actual_argument_noalias_proof")
    if (
        pointer.get("aliasing_proven") is not True
        or not isinstance(alias, dict)
        or alias.get("requires_noalias") is not True
        or alias.get("proven") is not True
        or not isinstance(actual, dict)
        or actual.get("proven") is not True
        or not isinstance(actual.get("parameter_pair"), list)
        or frozenset(actual["parameter_pair"]) != required_pair
    ):
        raise ValueError("record identity pointer noalias proof is incomplete")
    actual_args = actual.get("actual_arguments")
    if (
        not isinstance(actual_args, list)
        or len(actual_args) != 2
        or {item.get("parameter") for item in actual_args if isinstance(item, dict)}
        != {input_name, output_name}
    ):
        raise ValueError("record identity actual argument proof is not closed")


def _validate_identity_source(signature: dict[str, Any], output_name: str) -> None:
    source = signature.get("c_source")
    if source is None:
        return
    if not isinstance(source, str) or not source.strip():
        raise ValueError("record identity C source is invalid")
    returned = re.findall(r"\breturn\s+([A-Za-z_][A-Za-z0-9_]*)\s*;", source)
    if returned != [output_name]:
        raise ValueError("record identity C source does not return the output parameter")


def _matching_signature(spec: dict[str, Any], function_name: str) -> dict[str, Any]:
    signatures = spec.get("c_boundary", {}).get("signatures")
    matches = [
        item for item in signatures or []
        if isinstance(item, dict) and item.get("function") == function_name
    ]
    if len(matches) != 1:
        raise ValueError("record identity requires exactly one matching C signature")
    return matches[0]


def _public_api(spec: dict[str, Any]) -> str:
    entries = [
        item for item in spec.get("rust_boundary", {}).get("public_api") or []
        if isinstance(item, dict)
    ]
    if len(entries) != 1:
        raise ValueError("record identity requires exactly one Rust public API")
    return _ident(entries[0].get("name"), "Rust API")


def _scalar_conversion(fixture_type: Any, rust_type: Any, conversion: Any) -> None:
    if conversion == "identity" and fixture_type == rust_type and rust_type in {"u32", "usize"}:
        return
    if conversion == "u32_to_usize" and fixture_type == "u32" and rust_type == "usize":
        return
    raise ValueError("record identity scalar conversion is inconsistent")


def _scalar_value(value: Any, scalar_type: str) -> None:
    valid = isinstance(value, int) and not isinstance(value, bool) and value >= 0
    if scalar_type == "u32" and valid and value <= 0xFFFFFFFF:
        return
    if scalar_type == "usize" and valid and value <= 0xFFFFFFFFFFFFFFFF:
        return
    raise ValueError(f"record identity fixture scalar does not match {scalar_type}")


def _leaf_paths(value: Any, prefix: tuple[str, ...] = ()) -> set[tuple[str, ...]]:
    if not isinstance(value, dict) or not value:
        raise ValueError("record identity fixture record is missing or empty")
    result: set[tuple[str, ...]] = set()
    for key, child in value.items():
        if not isinstance(key, str) or not key:
            raise ValueError("record identity fixture field name is invalid")
        path = (*prefix, key)
        if isinstance(child, dict):
            result.update(_leaf_paths(child, path))
        else:
            result.add(path)
    return result


def _value_at_path(value: Any, path: list[str]) -> Any:
    current = value
    for part in path:
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"record identity fixture path is missing: {'.'.join(path)}")
        current = current[part]
    return current


def _fixture_path(value: Any, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item or "\x00" in item for item in value)
    ):
        raise ValueError(f"record identity {label} is invalid")
    return list(value)


def _rust_path(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"record identity {label} is required")
    return [_ident(item, label) for item in value]


def _rust_type_path(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("record identity Rust type path must be an array")
    return [_ident(item, "Rust type path") for item in value]


def _ident(value: Any, label: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER_RE.fullmatch(value) or value in RUST_KEYWORDS:
        raise ValueError(f"record identity {label} is not a safe identifier")
    return value


def _c_type(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} shape drifted")

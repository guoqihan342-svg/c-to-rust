from __future__ import annotations

import hashlib
import json
from typing import Any

from .context_typed_ir_extensions import (
    summarize_mutable_void_pointer_address,
    summarize_record_memset,
    validate_mutable_void_pointer_address,
    validate_record_memset,
)


MAX_SUMMARY_NODES = 512
MAX_SEQUENCE_ITEMS = 64


def typed_ir_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    budget = [MAX_SUMMARY_NODES]
    summary: dict[str, Any] = {
        key: value[key]
        for key in ("name",)
        if isinstance(value.get(key), str)
    }
    return_type = type_summary(value.get("return_type"))
    if return_type:
        summary["return_type"] = return_type
    params = value.get("params")
    if isinstance(params, list):
        summary["params"] = [
            {
                "name": item.get("name"),
                "type": type_summary(item.get("ty")),
            }
            for item in params[:32]
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
    body = value.get("body")
    if isinstance(body, list):
        summary["body"] = summarize_statements(body, budget=budget, depth=0)
        summary["statement_kinds"] = stable_unique(
            next(iter(item))
            for item in body
            if isinstance(item, dict) and len(item) == 1
        )
    facts = {"callees": [], "integer_literals": [], "operators": [], "members": []}
    collect_typed_ir_facts(value, facts)
    summary.update({key: items for key, items in facts.items() if items})
    issues = projection_issues(value.get("body"))
    summary["projection_status"] = "complete" if not issues and budget[0] > 0 else "incomplete"
    summary["unsupported_nodes"] = issues
    summary["truncated"] = budget[0] <= 0 or "sequence_limit_exceeded" in issues
    summary["semantics_verified"] = False
    summary["projection_sha256"] = projection_sha256(summary)
    return summary


def typed_ir_summary_is_valid(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and value.get("projection_status") == "complete"
        and value.get("truncated") is False
        and value.get("unsupported_nodes") == []
        and value.get("semantics_verified") is False
        and isinstance(value.get("body"), list)
        and bool(value["body"])
        and value.get("projection_sha256") == projection_sha256(value)
    )


def typed_ir_context_status(context_pack: Any) -> str:
    artifacts = context_pack.get("deterministic_artifacts") if isinstance(context_pack, dict) else None
    if not isinstance(artifacts, dict):
        return "not_present"
    summaries = []
    for name, artifact in artifacts.items():
        if not isinstance(name, str) or not name.endswith("-clang-lowering-report.json"):
            continue
        excerpt = artifact.get("context_excerpt") if isinstance(artifact, dict) else None
        lowering = excerpt.get("lowering_report") if isinstance(excerpt, dict) else None
        summary = lowering.get("function_ir_summary") if isinstance(lowering, dict) else None
        if summary is not None:
            summaries.append(summary)
    if not summaries:
        return "not_present"
    return "ready" if all(typed_ir_summary_is_valid(item) for item in summaries) else "invalid"


def projection_sha256(value: dict[str, Any]) -> str:
    payload = {key: item for key, item in value.items() if key != "projection_sha256"}
    encoded = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def projection_issues(body: Any) -> list[str]:
    issues: list[str] = []
    budget = [MAX_SUMMARY_NODES]
    validate_statements(body, issues, budget=budget, depth=0)
    if budget[0] <= 0:
        append_issue(issues, "node_limit_exceeded")
    return issues


def validate_statements(value: Any, issues: list[str], *, budget: list[int], depth: int) -> None:
    if not isinstance(value, list):
        append_issue(issues, "statement_list_missing")
        return
    if len(value) > MAX_SEQUENCE_ITEMS:
        append_issue(issues, "sequence_limit_exceeded")
    for item in value[:MAX_SEQUENCE_ITEMS]:
        if not consume(budget, depth) or not isinstance(item, dict) or len(item) != 1:
            append_issue(issues, "statement_shape_invalid")
            continue
        kind, payload = next(iter(item.items()))
        if kind in {"Continue", "Break"}:
            continue
        if not isinstance(payload, dict):
            append_issue(issues, f"statement_payload_invalid:{kind}")
            continue
        if kind == "Decl":
            validate_expression(payload.get("init"), issues, budget=budget, depth=depth + 1)
        elif kind in {"Assign", "CompoundAssign"}:
            validate_expression(payload.get("target"), issues, budget=budget, depth=depth + 1)
            validate_expression(payload.get("value"), issues, budget=budget, depth=depth + 1)
        elif kind == "Expr":
            validate_expression(payload.get("expr"), issues, budget=budget, depth=depth + 1)
        elif kind == "Return":
            validate_expression(payload.get("value"), issues, budget=budget, depth=depth + 1)
        elif kind == "If":
            validate_expression(payload.get("condition"), issues, budget=budget, depth=depth + 1)
            validate_statements(payload.get("then_body"), issues, budget=budget, depth=depth + 1)
            validate_statements(payload.get("else_body"), issues, budget=budget, depth=depth + 1)
        elif kind in {"While", "DoWhile"}:
            validate_expression(payload.get("condition"), issues, budget=budget, depth=depth + 1)
            validate_statements(payload.get("body"), issues, budget=budget, depth=depth + 1)
        elif kind == "RecordMemset":
            validate_record_memset(
                payload,
                issues,
                budget=budget,
                depth=depth,
                validate_expression=validate_expression,
                append_issue=append_issue,
            )
        else:
            append_issue(issues, f"statement_unsupported:{kind}")


def validate_expression(value: Any, issues: list[str], *, budget: list[int], depth: int) -> None:
    if value is None:
        return
    if not consume(budget, depth) or not isinstance(value, dict) or len(value) != 1:
        append_issue(issues, "expression_shape_invalid")
        return
    kind, payload = next(iter(value.items()))
    if kind in {"Var", "LitInt", "NullPtr"}:
        return
    if not isinstance(payload, dict):
        append_issue(issues, f"expression_payload_invalid:{kind}")
        return
    if kind in {"LValueToRValue", "Paren", "ImplicitCast"}:
        validate_expression(
            payload.get("expr", payload.get("operand")),
            issues,
            budget=budget,
            depth=depth + 1,
        )
    elif kind == "Member":
        validate_expression(payload.get("base"), issues, budget=budget, depth=depth + 1)
    elif kind == "Call":
        args = payload.get("args")
        if not isinstance(args, list):
            append_issue(issues, "call_args_invalid")
        else:
            if len(args) > MAX_SEQUENCE_ITEMS:
                append_issue(issues, "sequence_limit_exceeded")
            for item in args[:MAX_SEQUENCE_ITEMS]:
                validate_expression(item, issues, budget=budget, depth=depth + 1)
    elif kind in {"Binary", "Assign"}:
        validate_expression(
            payload.get("lhs", payload.get("target")),
            issues,
            budget=budget,
            depth=depth + 1,
        )
        validate_expression(
            payload.get("rhs", payload.get("value")),
            issues,
            budget=budget,
            depth=depth + 1,
        )
    elif kind in {"Unary", "AddrOf", "Deref"}:
        validate_expression(payload.get("operand"), issues, budget=budget, depth=depth + 1)
    elif kind == "Cast":
        validate_expression(payload.get("expr"), issues, budget=budget, depth=depth + 1)
    elif kind in {"Index", "Subscript"}:
        validate_expression(payload.get("base"), issues, budget=budget, depth=depth + 1)
        validate_expression(payload.get("index"), issues, budget=budget, depth=depth + 1)
    elif kind == "MutableVoidPointerAddress":
        validate_mutable_void_pointer_address(
            payload,
            issues,
            budget=budget,
            depth=depth,
            validate_expression=validate_expression,
            append_issue=append_issue,
        )
    else:
        append_issue(issues, f"expression_unsupported:{kind}")


def append_issue(issues: list[str], value: str) -> None:
    if value not in issues and len(issues) < 32:
        issues.append(value)


def summarize_statements(
    values: list[Any],
    *,
    budget: list[int],
    depth: int,
) -> list[dict[str, Any]]:
    return [
        summary
        for item in values[:MAX_SEQUENCE_ITEMS]
        if (summary := summarize_statement(item, budget=budget, depth=depth + 1))
    ]


def summarize_statement(
    value: Any,
    *,
    budget: list[int],
    depth: int,
) -> dict[str, Any] | None:
    if not consume(budget, depth) or not isinstance(value, dict) or len(value) != 1:
        return None
    kind, payload = next(iter(value.items()))
    if not isinstance(kind, str):
        return None
    result: dict[str, Any] = {"kind": kind}
    if not isinstance(payload, dict):
        return result
    if kind == "Decl":
        result["name"] = payload.get("name")
        result["type"] = type_summary(payload.get("ty"))
        result["initializer"] = summarize_expression(payload.get("init"), budget=budget, depth=depth + 1)
    elif kind in {"Assign", "CompoundAssign"}:
        result["target"] = summarize_expression(payload.get("target"), budget=budget, depth=depth + 1)
        result["value"] = summarize_expression(payload.get("value"), budget=budget, depth=depth + 1)
        if isinstance(payload.get("op"), str):
            result["operation"] = payload["op"]
    elif kind == "Expr":
        result["expression"] = summarize_expression(payload.get("expr"), budget=budget, depth=depth + 1)
    elif kind == "Return":
        result["value"] = summarize_expression(payload.get("value"), budget=budget, depth=depth + 1)
    elif kind == "If":
        result["condition"] = summarize_expression(payload.get("condition"), budget=budget, depth=depth + 1)
        result["then"] = summarize_statements(
            payload.get("then_body", []) if isinstance(payload.get("then_body"), list) else [],
            budget=budget,
            depth=depth + 1,
        )
        result["else"] = summarize_statements(
            payload.get("else_body", []) if isinstance(payload.get("else_body"), list) else [],
            budget=budget,
            depth=depth + 1,
        )
    elif kind in {"While", "DoWhile", "For"}:
        result["condition"] = summarize_expression(payload.get("condition"), budget=budget, depth=depth + 1)
        result["body"] = summarize_statements(
            payload.get("body", []) if isinstance(payload.get("body"), list) else [],
            budget=budget,
            depth=depth + 1,
        )
    elif kind == "RecordMemset":
        return summarize_record_memset(
            payload,
            budget=budget,
            depth=depth,
            summarize_expression=summarize_expression,
        )
    else:
        for key in ("name", "op", "value"):
            if isinstance(payload.get(key), (str, int, bool)):
                result[key] = payload[key]
    return {key: item for key, item in result.items() if item not in (None, {}, [])}


def summarize_expression(
    value: Any,
    *,
    budget: list[int],
    depth: int,
) -> Any:
    if not consume(budget, depth) or not isinstance(value, dict) or len(value) != 1:
        return None
    kind, payload = next(iter(value.items()))
    if not isinstance(kind, str):
        return None
    if kind in {"LValueToRValue", "Paren", "ImplicitCast"} and isinstance(payload, dict):
        return summarize_expression(
            payload.get("expr", payload.get("operand")),
            budget=budget,
            depth=depth + 1,
        )
    if kind == "Var" and isinstance(payload, dict):
        return {"kind": "var", "name": payload.get("name")}
    if kind == "Member" and isinstance(payload, dict):
        return {
            "kind": "member",
            "base": summarize_expression(payload.get("base"), budget=budget, depth=depth + 1),
            "field": payload.get("field"),
            "access": "arrow" if payload.get("is_arrow") is True else "dot",
        }
    if kind == "LitInt" and isinstance(payload, dict):
        result = {
            "kind": "integer",
            "value": payload.get("value"),
            "spelling": payload.get("spelling"),
        }
        ty = type_summary(payload.get("ty"))
        if ty:
            result["type"] = ty
        return result
    if kind == "Call" and isinstance(payload, dict):
        args = payload.get("args")
        return {
            "kind": "call",
            "callee": payload.get("callee"),
            "args": [
                summarize_expression(item, budget=budget, depth=depth + 1)
                for item in args[:MAX_SEQUENCE_ITEMS]
            ] if isinstance(args, list) else [],
        }
    if kind in {"Binary", "Assign"} and isinstance(payload, dict):
        result = {
            "kind": kind.lower(),
            "operation": payload.get("op"),
            "left": summarize_expression(payload.get("lhs", payload.get("target")), budget=budget, depth=depth + 1),
            "right": summarize_expression(payload.get("rhs", payload.get("value")), budget=budget, depth=depth + 1),
        }
        ty = type_summary(payload.get("ty"))
        if ty:
            result["type"] = ty
        if payload.get("op") in {"Add", "Sub", "Mul"} and ty.get("signed") is False:
            result["overflow"] = "wrapping"
        return result
    if kind == "Unary" and isinstance(payload, dict):
        return {
            "kind": "unary",
            "operation": payload.get("op"),
            "operand": summarize_expression(payload.get("operand"), budget=budget, depth=depth + 1),
        }
    if kind in {"AddrOf", "Deref"} and isinstance(payload, dict):
        return {
            "kind": kind.lower(),
            "operand": summarize_expression(payload.get("operand"), budget=budget, depth=depth + 1),
        }
    if kind == "Cast" and isinstance(payload, dict):
        target = type_summary(payload.get("target"))
        expression = summarize_expression(payload.get("expr"), budget=budget, depth=depth + 1)
        result = {
            "kind": "cast",
            "target_type": target,
            "expression": expression,
        }
        if (
            target.get("signed") is False
            and isinstance(expression, dict)
            and expression.get("kind") == "unary"
            and expression.get("operation") == "Neg"
            and isinstance(expression.get("operand"), dict)
            and expression["operand"].get("kind") == "integer"
            and expression["operand"].get("value") == 1
        ):
            result["semantic"] = "unsigned_all_ones_sentinel"
        return result
    if kind in {"Index", "Subscript"} and isinstance(payload, dict):
        return {
            "kind": "index",
            "base": summarize_expression(payload.get("base"), budget=budget, depth=depth + 1),
            "index": summarize_expression(payload.get("index"), budget=budget, depth=depth + 1),
        }
    if kind == "MutableVoidPointerAddress" and isinstance(payload, dict):
        return summarize_mutable_void_pointer_address(
            payload,
            budget=budget,
            depth=depth,
            summarize_expression=summarize_expression,
        )
    if kind == "NullPtr":
        return {"kind": "null_pointer"}
    return {"kind": kind}


def type_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    result = {
        key: value[key]
        for key in ("spelled", "canonical", "width_bits", "is_const")
        if isinstance(value.get(key), (str, int, bool))
    }
    kind = value.get("kind")
    integer = kind.get("Integer") if isinstance(kind, dict) else None
    if isinstance(integer, dict) and isinstance(integer.get("signed"), bool):
        result["signed"] = integer["signed"]
    return result


def collect_typed_ir_facts(value: Any, facts: dict[str, list[Any]], *, depth: int = 0) -> None:
    if depth > 48 or sum(len(items) for items in facts.values()) >= 128:
        return
    if isinstance(value, dict):
        call = value.get("Call")
        if isinstance(call, dict) and isinstance(call.get("callee"), str):
            append_unique(facts["callees"], call["callee"])
        literal = value.get("LitInt")
        if isinstance(literal, dict):
            projected = {
                key: literal[key]
                for key in ("spelling", "value")
                if isinstance(literal.get(key), (str, int)) and not isinstance(literal.get(key), bool)
            }
            if projected:
                append_unique(facts["integer_literals"], projected)
        for operator_kind in ("Binary", "Unary", "AssignOp"):
            operator = value.get(operator_kind)
            if isinstance(operator, dict) and isinstance(operator.get("op"), str):
                append_unique(facts["operators"], operator["op"])
        member = value.get("Member")
        if isinstance(member, dict) and isinstance(member.get("field"), str):
            append_unique(facts["members"], member["field"])
        for item in value.values():
            collect_typed_ir_facts(item, facts, depth=depth + 1)
    elif isinstance(value, list):
        for item in value[:256]:
            collect_typed_ir_facts(item, facts, depth=depth + 1)


def stable_unique(values: Any) -> list[Any]:
    result: list[Any] = []
    for value in values:
        append_unique(result, value)
    return result


def append_unique(values: list[Any], value: Any) -> None:
    if value not in values and len(values) < 32:
        values.append(value)


def consume(budget: list[int], depth: int) -> bool:
    if depth > 48 or budget[0] <= 0:
        budget[0] = 0
        return False
    budget[0] -= 1
    return True


__all__ = [
    "typed_ir_context_status",
    "typed_ir_summary",
    "typed_ir_summary_is_valid",
]

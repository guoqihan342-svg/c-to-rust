from __future__ import annotations

import json
from typing import Any


def render_boundary_contract(context_pack: dict[str, Any]) -> str:
    function_name = context_pack.get("function_name")
    c_payload = boundary_payload(context_pack.get("c_boundary"))
    rust_payload = boundary_payload(context_pack.get("rust_boundary"))
    signatures = c_payload.get("signatures")
    selected_signature = None
    if isinstance(signatures, list):
        selected_signature = next(
            (
                signature
                for signature in signatures
                if isinstance(signature, dict)
                and signature.get("function") == function_name
            ),
            None,
        )
    contract = {
        "function_name": function_name,
        "c_signature": selected_signature,
        "rust_public_api": rust_payload.get("public_api"),
        "raw_pointer_policy": rust_payload.get("raw_pointer_policy"),
        "unsafe_policy": rust_payload.get("unsafe_policy"),
    }
    return json.dumps(contract, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def boundary_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    payload = value.get("payload")
    return payload if isinstance(payload, dict) else value


__all__ = ["render_boundary_contract"]

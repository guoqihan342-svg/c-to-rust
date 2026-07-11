from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_ai_exact_router_status(
    evidence_root: Path,
    target_id: str,
    slice_id: str,
) -> dict[str, Any]:
    path = evidence_root / target_id / "auto-translation" / slice_id / f"l3-{slice_id}-ai-router.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _failed()
    if not isinstance(payload, dict) or not isinstance(payload.get("candidate_set"), list):
        return _failed()
    selected_id = payload.get("selected_candidate_id")
    selected = next(
        (
            item
            for item in payload["candidate_set"]
            if isinstance(item, dict) and item.get("candidate_id") == selected_id
        ),
        None,
    )
    if not isinstance(selected, dict):
        return _failed()
    accepted = selected.get("accepted_gates")
    return {
        "compiled": isinstance(accepted, list) and "compile" in accepted,
        "semantic_pass": payload.get("semantic_pass") is True and selected.get("decision") == "selected",
        "selected_candidate_id": selected_id,
        "selected_source": selected.get("source"),
    }


def _failed() -> dict[str, Any]:
    return {
        "compiled": False,
        "semantic_pass": False,
        "selected_candidate_id": None,
        "selected_source": None,
    }

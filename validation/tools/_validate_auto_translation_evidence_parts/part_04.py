def validate_translation_carrier_binding(
    evidence_dir: Path,
    prefix: str,
    slice_spec_path: Path,
    *,
    repo_root: Path | None = None,
) -> None:
    """Bind a synthetic translation carrier to an exact real-source fragment."""
    slice_spec = load_json(slice_spec_path)
    carrier = slice_spec.get("translation_carrier")
    if carrier is None:
        return
    if not isinstance(carrier, dict):
        raise SystemExit("translation_carrier must be an object")

    root = (repo_root or REPO_ROOT).resolve()
    if carrier.get("kind") != "exact_source_fragment_wrapper":
        raise SystemExit("translation_carrier.kind must be exact_source_fragment_wrapper")
    if carrier.get("embedding_mode") != "verbatim_once":
        raise SystemExit("translation_carrier.embedding_mode must be verbatim_once")
    if carrier.get("frontend_contract") != "live_clang_slice_source":
        raise SystemExit("translation_carrier.frontend_contract must be live_clang_slice_source")
    if carrier.get("source_text_normalization") != "utf8_universal_newlines":
        raise SystemExit(
            "translation_carrier.source_text_normalization must be utf8_universal_newlines"
        )
    if carrier.get("source_file_hash_mode") != "raw_bytes":
        raise SystemExit("translation_carrier.source_file_hash_mode must be raw_bytes")
    if carrier.get("artifact_source_hash_mode") != "lf_stable_text":
        raise SystemExit(
            "translation_carrier.artifact_source_hash_mode must be lf_stable_text"
        )

    carrier_function = str(carrier.get("carrier_function") or "")
    if not carrier_function or carrier_function != str(slice_spec.get("function_name") or ""):
        raise SystemExit("translation_carrier.carrier_function must match slice function_name")

    claim_boundary = carrier.get("claim_boundary")
    if not isinstance(claim_boundary, dict):
        raise SystemExit("translation_carrier.claim_boundary must be an object")
    if claim_boundary.get("scope") != "source_fragment_only":
        raise SystemExit("translation_carrier claim scope must be source_fragment_only")
    if claim_boundary.get("whole_function_semantics_verified") is not False:
        raise SystemExit("translation_carrier must keep whole_function_semantics_verified=false")
    if claim_boundary.get("external_callee_semantics_verified") is not False:
        raise SystemExit("translation_carrier must keep external_callee_semantics_verified=false")
    excluded_semantics = claim_boundary.get("excluded_semantics")
    if not isinstance(excluded_semantics, list) or not excluded_semantics or not all(
        isinstance(item, str) and item for item in excluded_semantics
    ):
        raise SystemExit("translation_carrier.claim_boundary.excluded_semantics must be non-empty")

    c_source = slice_spec.get("c_source")
    if not isinstance(c_source, str) or not c_source:
        raise SystemExit("translation_carrier requires non-empty slice c_source")
    carrier_sha = hashlib.sha256(c_source.encode("utf-8")).hexdigest()
    if carrier.get("carrier_source_sha256") != carrier_sha:
        raise SystemExit("translation_carrier.carrier_source_sha256 mismatch")

    real_source = carrier.get("real_source")
    if not isinstance(real_source, dict):
        raise SystemExit("translation_carrier.real_source must be an object")
    logical_source_file = str(real_source.get("file") or "")
    if not logical_source_file or logical_source_file != str(slice_spec.get("source_file") or ""):
        raise SystemExit("translation_carrier real source file must match slice source_file")
    source_root_text = str(
        slice_spec.get("source_root")
        or slice_spec.get("source", {}).get("source_root")
        or ""
    )
    source_root = translation_carrier_repo_path(root, source_root_text, "source_root")
    source_path = translation_carrier_child_path(source_root, logical_source_file, "real source file")
    if not source_path.is_file():
        raise SystemExit(f"translation_carrier real source file missing: {source_path}")
    source_bytes = source_path.read_bytes()
    source_text = source_path.read_text(encoding="utf-8-sig")

    source_hashes = slice_spec.get("source_file_hashes") or slice_spec.get("source", {}).get(
        "source_file_hashes", {}
    )
    expected_source_sha = source_hashes.get(logical_source_file) if isinstance(source_hashes, dict) else None
    actual_source_sha = hashlib.sha256(source_bytes).hexdigest()
    if not expected_source_sha or expected_source_sha != actual_source_sha:
        raise SystemExit("translation_carrier real source file sha256 mismatch")

    containing_function = real_source.get("containing_function")
    fragment = real_source.get("fragment")
    if not isinstance(containing_function, dict) or not isinstance(fragment, dict):
        raise SystemExit("translation_carrier real source spans are missing")
    function_start, function_end, function_bytes = translation_carrier_span(
        source_text, containing_function, "containing function", trim=True
    )
    fragment_start, fragment_end, fragment_bytes = translation_carrier_span(
        source_text, fragment, "source fragment", trim=False
    )
    if fragment_start < function_start or fragment_end > function_end:
        raise SystemExit("translation_carrier source fragment is outside containing function span")

    containing_name = str(containing_function.get("name") or "")
    declaration_text = str(containing_function.get("declaration_text") or "")
    if not containing_name or not declaration_text:
        raise SystemExit("translation_carrier containing function identity is missing")
    if not function_bytes.startswith(declaration_text.encode("utf-8")):
        raise SystemExit("translation_carrier containing function declaration_text mismatch")
    if re.search(rf"\b{re.escape(containing_name)}\s*\(", declaration_text) is None:
        raise SystemExit("translation_carrier containing function name is not bound to declaration_text")

    fragment_text = fragment.get("text")
    if not isinstance(fragment_text, str) or fragment_text.encode("utf-8") != fragment_bytes:
        raise SystemExit("translation_carrier source fragment text mismatch")
    if c_source.count(fragment_text) != 1:
        raise SystemExit("translation_carrier source fragment must be embedded verbatim exactly once")

    translator_input = load_json(evidence_dir / f"{prefix}-translator-input.json")
    plan = load_json(evidence_dir / f"{prefix}-auto-translation-plan.json")
    lowering_report = load_json(evidence_dir / f"{prefix}-clang-lowering-report.json")
    for label, artifact in [
        ("translator input", translator_input),
        ("auto-translation plan", plan),
        ("clang lowering report", lowering_report),
    ]:
        if artifact.get("translation_carrier") != carrier:
            raise SystemExit(f"translation_carrier binding drift in {label}")
        for identity_key in ("target_id", "slice_id", "source_commit"):
            if artifact.get(identity_key) != slice_spec.get(identity_key):
                raise SystemExit(
                    f"translation_carrier {identity_key} drift in {label}"
                )
    if translator_input.get("fixture_hash") != slice_spec.get("fixture_hash"):
        raise SystemExit("translation_carrier fixture_hash drift in translator input")
    if lowering_report.get("fixture_hash") != slice_spec.get("fixture_hash"):
        raise SystemExit("translation_carrier fixture_hash drift in clang lowering report")
    plan_fixture_key = f"fixture_hash={slice_spec.get('fixture_hash')}"
    if plan.get("fixture_hash") != slice_spec.get("fixture_hash") and plan_fixture_key not in plan.get(
        "cache_invalidation_keys", []
    ):
        raise SystemExit("translation_carrier fixture_hash drift in auto-translation plan")

    if translator_input.get("c_source") != c_source:
        raise SystemExit("translation_carrier c_source drift in translator input")
    if translator_input.get("function_name") != carrier_function:
        raise SystemExit("translation_carrier function drift in translator input")
    if translator_input.get("source_root") != source_root_text:
        raise SystemExit("translation_carrier source_root drift in translator input")
    if translator_input.get("source_file") != logical_source_file:
        raise SystemExit("translation_carrier source_file drift in translator input")
    artifact_source_hashes = translator_input.get("source_file_hashes")
    expected_artifact_source_sha = sha256(source_path)
    if (
        not isinstance(artifact_source_hashes, dict)
        or artifact_source_hashes.get(logical_source_file) != expected_artifact_source_sha
    ):
        raise SystemExit("translation_carrier source_file_hashes drift in translator input")
    input_profile = translator_input.get("build_profile", {})
    if input_profile.get("clang_ast_fixture"):
        raise SystemExit("translation_carrier live clang contract forbids clang_ast_fixture")
    if plan.get("status") not in {"generated", "draft_generated"}:
        raise SystemExit("translation_carrier requires generated auto-translation plan")
    if plan.get("translation_source", {}).get("selected") != "clang-lowered-typed-ir":
        raise SystemExit("translation_carrier requires clang-lowered-typed-ir plan source")
    if lowering_report.get("status") != "lowered":
        raise SystemExit("translation_carrier requires lowered clang report")
    if lowering_report.get("function_name") != carrier_function:
        raise SystemExit("translation_carrier function drift in clang lowering report")
    if lowering_report.get("lowering_report", {}).get("frontend") != "clang_slice_source":
        raise SystemExit("translation_carrier requires clang_slice_source lowering frontend")
    if lowering_report.get("metadata", {}).get("clang_ast_fixture"):
        raise SystemExit("translation_carrier lowering report must not bind clang_ast_fixture")
    report_metadata = lowering_report.get("metadata", {})
    if report_metadata.get("source_root") != source_root_text:
        raise SystemExit("translation_carrier source_root drift in clang lowering report")
    if report_metadata.get("logical_source_file") != logical_source_file:
        raise SystemExit("translation_carrier source_file drift in clang lowering report")
    if report_metadata.get("source_file_hashes") != artifact_source_hashes:
        raise SystemExit("translation_carrier source_file_hashes drift in clang lowering report")
    typed_ir_candidate = lowering_report.get("typed_ir_candidate", {})
    if (
        typed_ir_candidate.get("status") != "generated"
        or typed_ir_candidate.get("rust_draft_generated") is not True
        or typed_ir_candidate.get("semantic_pass") is not False
    ):
        raise SystemExit("translation_carrier typed-IR candidate binding is incomplete")


def translation_carrier_span(
    source_text: str,
    span: dict[str, Any],
    label: str,
    *,
    trim: bool,
) -> tuple[int, int, bytes]:
    line_start = span.get("line_start")
    line_end = span.get("line_end")
    if not isinstance(line_start, int) or not isinstance(line_end, int):
        raise SystemExit(f"translation_carrier {label} line range must be integers")
    lines = source_text.splitlines(keepends=True)
    if line_start < 1 or line_end < line_start or line_end > len(lines):
        raise SystemExit(f"translation_carrier {label} line range is invalid")
    span_text = "".join(lines[line_start - 1 : line_end])
    expected_hash_mode = (
        "trimmed_normalized_span" if trim else "normalized_line_span_with_newline"
    )
    if span.get("hash_mode") != expected_hash_mode:
        raise SystemExit(f"translation_carrier {label} hash_mode mismatch")
    if trim:
        span_text = span_text.strip()
    span_bytes = span_text.encode("utf-8")
    actual_sha = hashlib.sha256(span_bytes).hexdigest()
    if span.get("sha256") != actual_sha:
        raise SystemExit(f"translation_carrier {label} sha256 mismatch")
    return line_start, line_end, span_bytes


def translation_carrier_repo_path(root: Path, path_text: str, label: str) -> Path:
    if not path_text:
        raise SystemExit(f"translation_carrier {label} is missing")
    path = Path(path_text)
    if path.is_absolute():
        raise SystemExit(f"translation_carrier {label} must be repo-relative")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise SystemExit(f"translation_carrier {label} escapes repo root") from exc
    return resolved


def translation_carrier_child_path(root: Path, path_text: str, label: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        raise SystemExit(f"translation_carrier {label} must be relative")
    resolved = (root / path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise SystemExit(f"translation_carrier {label} escapes source root") from exc
    return resolved

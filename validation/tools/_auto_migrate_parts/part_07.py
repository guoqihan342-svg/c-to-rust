def source_file_hashes(spec: dict[str, Any]) -> dict[str, str]:
    declared_hashes = {
        str(path): str(value)
        for path, value in spec.get("source", {}).get("source_file_hashes", {}).items()
        if value
    }
    file_entries = [item for item in spec.get("c_boundary", {}).get("files", []) if item.get("path")]
    files = [item["path"] for item in file_entries]
    files.extend(str(item) for item in spec.get("source_files", []))
    result: dict[str, str] = {}
    source_root = spec.get("source", {}).get("source_root")
    for file_name in sorted(set(files)):
        matching_entry = next((item for item in file_entries if item.get("path") == file_name), {})
        explicit_hash = declared_hashes.get(file_name) or matching_entry.get("sha256")
        path = REPO_ROOT / file_name
        if path.exists() and path.is_file():
            result[file_name] = sha256(path)
            continue
        if source_root:
            source_path = Path(str(source_root)) / file_name
            if source_path.exists() and source_path.is_file():
                result[file_name] = sha256(source_path)
                continue
        result[file_name] = str(explicit_hash) if explicit_hash else "missing"
    return result


def tool_versions() -> dict[str, str]:
    return {
        "python": command_version([sys.executable, "--version"]),
        "rustc": command_version(["rustc", "--version"]),
        "cargo": command_version(["cargo", "--version"]),
    }


def command_version(cmd: list[str], fallback: list[str] | None = None) -> str:
    try:
        result = subprocess.run(
            cmd,
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        if fallback is None:
            return "unavailable"
        return command_version(fallback)
    text = (result.stdout or result.stderr).strip()
    if result.returncode != 0 and not text:
        return f"unavailable:{result.returncode}"
    return text.splitlines()[0] if text else "unknown"


def type_mapping_kind(c_type: str) -> str:
    if "*" in c_type:
        return "pointer"
    if c_type in {"int", "unsigned int", "uint32_t", "char", "unsigned char"}:
        return "primitive"
    if c_type.startswith("struct "):
        return "struct"
    return "unsupported"


def function_signature(spec: dict[str, Any]) -> str:
    signatures = spec.get("c_boundary", {}).get("signatures", [])
    if signatures:
        signature = signatures[0]
        params = ", ".join(
            f"{param.get('c_type')} {param.get('name')}" for param in signature.get("parameters", [])
        )
        return f"{signature.get('return_type')} {signature.get('function')}({params})"
    return spec.get("c_source", "").split("{", 1)[0].strip()


def extract_return_expression(statements: list[str]) -> str:
    for statement in statements:
        if statement.strip().startswith("return"):
            return statement.strip()[len("return") :].strip()
    return ""


def count_token(text: str, token: str) -> int:
    return len(re.findall(rf"\b{re.escape(token)}\b", text))


def source_boundary(spec: dict[str, Any]) -> dict[str, Any]:
    c_boundary = spec.get("c_boundary", {})
    files = [item["path"] for item in c_boundary.get("files", [])] or spec.get("source_files", [])
    functions = c_boundary.get("functions") or [spec.get("function_name", "unknown")]
    global_dependencies = global_dependency_requirements(spec)
    return {
        "files": files,
        "functions": functions,
        "structs": [dep.get("name") for dep in c_boundary.get("direct_dependencies", []) if dep.get("kind") == "type"],
        "globals": [item["name"] for item in global_dependencies],
        "direct_call_edges": [],
    }


def blocked_repairs_payload(spec: dict[str, Any], repairs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "target_id": spec.get("target_id"),
        "slice_id": spec.get("slice_id"),
        "status": "recorded" if repairs else "none",
        "blocked_repairs": repairs,
        "cache_invalidation_keys": [
            f"source_commit={source_commit(spec)}",
            f"fixture_hash={fixture_hash(spec)}",
            "patch_plan_schema=1",
        ],
    }


def rustc_error_code(error: dict[str, Any]) -> str:
    code = error.get("code")
    if isinstance(code, dict) and code.get("code"):
        return str(code["code"])
    return "rustc_error"


def required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise SystemExit(f"slice spec must include non-empty string `{key}`")
    return value


def safe_ident(text: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in text)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def write_log_text(path: Path, text: str) -> None:
    if text:
        write_text(path, text)
    elif path.exists():
        path.unlink()


def sha256(path: Path) -> str:
    """Delegates to the judge validator's suffix-gated LF-stable file hash so
    producer-recorded refs and validator-recomputed hashes always use one
    discipline. Text artifacts (.c/.h/.rs/.json/...) are newline-normalized —
    upstream checkouts whose text attributes produce CRLF on Windows and LF on
    Linux (e.g. the pinned FlashDB repository) yield one platform-independent
    hash — while binary artifacts (.rlib etc.) keep raw-byte hashing."""
    return judge_validator.sha256_file(path)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())

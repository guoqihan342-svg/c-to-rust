from __future__ import annotations

import ast
from pathlib import Path


PACKAGE = "validation.tools._project_migration_harness"


def module_name(name: str) -> str:
    return f"{PACKAGE}.{name}"


def _edges(*specs: tuple[str, str, str]) -> dict[tuple[str, str], frozenset[str]]:
    return {
        (module_name(source), module_name(target)): frozenset(symbols.split())
        for source, target, symbols in specs
    }


GENERIC_FACADES = {module_name("build_adapter"), module_name("build_ir_reopen")}
MAKE_MODULE_NAMES = (
    "make_build_ir_adapter",
    "make_build_ir_external",
    "make_build_ir_projection",
    "make_build_ir_reopen",
    "make_build_ir_toolchains",
    "make_dry_run_binding",
    "make_dry_run_contract",
    "make_dry_run_host_evidence",
    "make_dry_run_parser",
    "make_dry_run_report_io",
    "make_dry_run_result",
    "make_dry_run_runner",
    "make_dry_run_tools",
)
MAKE_MODULES = {module_name(name) for name in MAKE_MODULE_NAMES}
ADAPTER_ZONE = GENERIC_FACADES | MAKE_MODULES
FACADE_EXPORTS = {
    module_name("build_adapter"): frozenset(
        "BuildInputSelection BuildInputSelectionLike MAKE_REPORT_INPUT_KIND "
        "MAX_BUILD_INPUT_BYTES discover_selected_project "
        "materialize_selected_build_ir_stage normalize_build_input_selection".split()
    ),
    module_name("build_ir_reopen"): frozenset(
        "accepted_provenance_role accepted_raw_roles reproject_bound_build_ir".split()
    ),
}
FACADE_IMPORTS = _edges(
    ("discovery", "build_adapter",
     "BuildInputSelectionLike discover_selected_project"),
    ("orchestrator", "build_adapter",
     "BuildInputSelectionLike materialize_selected_build_ir_stage"),
    ("project_migration_cli", "build_adapter",
     "BuildInputSelection MAKE_REPORT_INPUT_KIND"),
    ("build_ir_validation", "build_ir_reopen",
     "accepted_provenance_role accepted_raw_roles reproject_bound_build_ir"),
)
PRIVATE_IMPORTS = _edges(
    ("build_adapter", "make_build_ir_adapter",
     "MAKE_INPUT_KIND MakeReportSelection discover_make_project materialize_make_build_ir_stage"),
    ("build_ir_reopen", "make_build_ir_reopen",
     "accepted_make_provenance_role accepted_make_raw_roles reproject_bound_make_build_ir"),
    ("make_build_ir_adapter", "make_build_ir_projection",
     "MAKE_RAW_ROLE normalize_make_translation_units project_make_build_ir"),
    ("make_build_ir_adapter", "make_dry_run_parser", "MAX_COMMANDS"),
    ("make_build_ir_adapter", "make_dry_run_report_io",
     "MAX_REPORT_BYTES reopen_make_dry_run_report verify_make_dry_run_report_inputs"),
    ("make_build_ir_projection", "make_build_ir_external",
     "MAKE_BUILD_BOUNDARIES project_make_external_dependencies"),
    ("make_build_ir_projection", "make_build_ir_toolchains",
     "abi_facts legacy_toolchain_id legacy_toolchains"),
    ("make_build_ir_reopen", "make_build_ir_adapter", "reproject_make_build_ir"),
    ("make_build_ir_reopen", "make_build_ir_projection", "MAKE_RAW_ROLE"),
    ("make_dry_run_contract", "make_dry_run_binding",
     "fixed_make_argv validated_targets"),
    ("make_dry_run_contract", "make_dry_run_parser",
     "MAX_STDOUT_BYTES PARSER_NAME PARSER_VERSION parse_make_dry_run_stdout validate_make_dry_run_commands"),
    ("make_dry_run_contract", "make_dry_run_result",
     "MakeDryRunOutcome validate_successful_make_outcome"),
    ("make_dry_run_parser", "make_dry_run_tools", "classify_make_tool"),
    ("make_dry_run_report_io", "make_dry_run_binding", "make_input_sha256"),
    ("make_dry_run_report_io", "make_dry_run_contract",
     "MAX_STDERR_BYTES canonical_make_dry_run_report_bytes validate_make_dry_run_report"),
    ("make_dry_run_report_io", "make_dry_run_host_evidence",
     "canonical_make_host_preflight_bytes validate_make_host_preflight"),
    ("make_dry_run_report_io", "make_dry_run_parser",
     "MAX_STDOUT_BYTES parse_make_dry_run_stdout"),
    ("make_dry_run_report_io", "make_dry_run_runner",
     "canonical_make_dry_run_plan_bytes validate_make_dry_run_plan"),
    ("make_dry_run_runner", "make_dry_run_host_evidence",
     "MAKE_REQUIRED_CAPABILITIES create_make_host_preflight validate_make_host_preflight"),
    ("make_dry_run_runner", "make_dry_run_binding",
     "fixed_make_argv make_input_sha256"),
    ("make_dry_run_runner", "make_dry_run_contract", "MAX_STDERR_BYTES"),
    ("make_dry_run_runner", "make_dry_run_parser", "MAX_STDOUT_BYTES"),
    ("make_dry_run_runner", "make_dry_run_result",
     "MakeDryRunExecution MakeDryRunOutcome"),
)
DYNAMIC_MODULES = {"builtins", "importlib", "marshal", "runpy", "zipimport"}
BUILTIN_SINKS = {"__import__", "compile", "eval", "exec"}
LOADER_SINKS = {
    "SourceFileLoader",
    "SourcelessFileLoader",
    "import_module",
    "module_from_spec",
    "run_module",
    "run_path",
    "spec_from_file_location",
    "zipimporter",
}
DYNAMIC_SINKS = BUILTIN_SINKS | LOADER_SINKS


def audit_source(module: str, source: str) -> list[str]:
    tree = ast.parse(source, filename=module)
    violations: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            violations.extend(_audit_import(module, node))
        elif isinstance(node, ast.Call):
            sink = dynamic_sink(node)
            if sink is not None:
                violations.append(_issue(node, "dynamic-loader-call", sink))
        if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
            reference = dynamic_reference(node)
            if reference is not None:
                violations.append(_issue(node, "dynamic-loader-reference", reference))
    return sorted(set(violations))


def _audit_import(module: str, node: ast.Import | ast.ImportFrom) -> list[str]:
    violations = []
    for target, symbol in import_records(module, node):
        if target.split(".", 1)[0] in DYNAMIC_MODULES:
            violations.append(_issue(node, "dynamic-loader-import", target))
        if is_private_make_module(target):
            allowed = PRIVATE_IMPORTS.get((module, target), frozenset())
            if symbol not in allowed:
                violations.append(_issue(node, "private-make-import", _label(target, symbol)))
        if target in GENERIC_FACADES:
            allowed = FACADE_IMPORTS.get((module, target), frozenset())
            if symbol is None:
                violations.append(_issue(node, "facade-module-import", target))
            elif symbol == "*":
                violations.append(_issue(node, "facade-star-import", target))
            else:
                if symbol not in FACADE_EXPORTS[target]:
                    violations.append(_issue(node, "facade-non-export", _label(target, symbol)))
                if symbol not in allowed:
                    violations.append(_issue(node, "facade-symbol-not-allowed", _label(target, symbol)))
    return violations


def import_records(
    module: str, node: ast.Import | ast.ImportFrom,
) -> list[tuple[str, str | None]]:
    if isinstance(node, ast.Import):
        return [(alias.name, None) for alias in node.names]
    base = _resolve_from(module, node.level, node.module)
    records = []
    for alias in node.names:
        candidate = f"{base}.{alias.name}" if base else alias.name
        if node.module is None or candidate in ADAPTER_ZONE or is_private_make_module(candidate):
            records.append((candidate, None))
        else:
            records.append((base, alias.name))
    return records


def is_private_make_module(target: str) -> bool:
    return (
        target.startswith(f"{PACKAGE}.make_")
        and target.count(".") == PACKAGE.count(".") + 1
    )


def dynamic_reference(node: ast.Name | ast.Attribute | ast.Subscript) -> str | None:
    if isinstance(node, ast.Name):
        if isinstance(node.ctx, ast.Load) and node.id in BUILTIN_SINKS:
            return node.id
        return None
    if not isinstance(node.ctx, ast.Load):
        return None
    if isinstance(node, ast.Attribute):
        dotted = _dotted_name(node)
        leaf = dotted.rsplit(".", 1)[-1] if dotted else None
        owner = dotted.rsplit(".", 1)[0] if dotted and "." in dotted else None
        if leaf in LOADER_SINKS or (
            leaf in BUILTIN_SINKS and owner in {"builtins", "__builtins__"}
        ):
            return str(dotted)
        return None
    key = node.slice
    owner = _dotted_name(node.value)
    if isinstance(key, ast.Constant) and key.value in DYNAMIC_SINKS and (
        owner in {"__builtins__", *DYNAMIC_MODULES}
    ):
        return str(key.value)
    return None


def dynamic_sink(call: ast.Call) -> str | None:
    dotted = _dotted_name(call.func)
    leaf = dotted.rsplit(".", 1)[-1] if dotted else None
    owner = dotted.rsplit(".", 1)[0] if dotted and "." in dotted else None
    if isinstance(call.func, ast.Name) and leaf in DYNAMIC_SINKS:
        return str(dotted)
    if leaf in LOADER_SINKS or (
        leaf in BUILTIN_SINKS and owner in {"builtins", "__builtins__"}
    ):
        return str(dotted)
    if isinstance(call.func, ast.Name) and call.func.id == "getattr":
        target = _dotted_name(call.args[0]) if call.args else None
        attribute = call.args[1] if len(call.args) > 1 else None
        if target in {"__builtins__", *DYNAMIC_MODULES} or (
            isinstance(attribute, ast.Constant) and attribute.value in DYNAMIC_SINKS
        ):
            return "getattr"
    if isinstance(call.func, ast.Subscript):
        return dynamic_reference(call.func)
    return None


def _dotted_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _resolve_from(module: str, level: int, imported: str | None) -> str:
    if level == 0:
        return imported or ""
    package = module.split(".")[:-1]
    keep = len(package) - level + 1
    parts = package[:keep] if keep >= 0 else []
    return ".".join([*parts, *(imported.split(".") if imported else [])])


def _label(target: str, symbol: str | None) -> str:
    return f"{target}:{symbol or '<module>'}"


def _issue(node: ast.AST, rule: str, detail: str) -> str:
    return f"{getattr(node, 'lineno', 0)}:{rule}:{detail}"


def declared_all(source: str) -> frozenset[str]:
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        ):
            if isinstance(node.value, (ast.List, ast.Tuple)) and all(
                isinstance(item, ast.Constant) and isinstance(item.value, str)
                for item in node.value.elts
            ):
                return frozenset(item.value for item in node.value.elts)
    raise AssertionError("facade __all__ must be a literal string sequence")


def repository_production_sources(root: Path) -> dict[str, str]:
    sources = {}
    package = root / "validation" / "tools" / "_project_migration_harness"
    entrypoint = root / "validation" / "tools" / "project_migration_harness.py"
    paths = [
        *(
            path for path in package.iterdir()
            if path.suffix in {".py", ".pyi"}
        ),
        entrypoint,
    ]
    for path in sorted(paths):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.is_file():
            raise AssertionError(f"production module is not regular: {relative}")
        source = path.read_bytes().decode("utf-8")
        ast.parse(source, filename=relative)
        module = path.relative_to(root).with_suffix("").as_posix().replace("/", ".")
        sources[module] = source
    return sources

from __future__ import annotations

import ast
from pathlib import Path

from validation.tools.project_migration_make_boundary_edges import (
    ENTRYPOINT_PRIVATE_IMPORTS, PRIVATE_IMPORT_SPECS,
)


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
    "make_build_ir_closure",
    "make_build_ir_closure_artifacts",
    "make_build_ir_closure_resolution",
    "make_build_ir_external",
    "make_build_ir_projection",
    "make_build_ir_reopen",
    "make_build_ir_toolchains",
    "make_dry_run_binding",
    "make_dry_run_cas",
    "make_dry_run_cli",
    "make_dry_run_collect",
    "make_dry_run_collect_io",
    "make_dry_run_contract",
    "make_dry_run_contract_refs",
    "make_dry_run_host_evidence",
    "make_dry_run_linux",
    "make_dry_run_parser",
    "make_dry_run_process",
    "make_dry_run_report_io",
    "make_dry_run_result",
    "make_dry_run_runner",
    "make_dry_run_sandbox",
    "make_dry_run_snapshot",
    "make_dry_run_snapshot_io",
    "make_dry_run_toolchain",
    "make_dry_run_tools",
)
MAKE_MODULES = {module_name(name) for name in MAKE_MODULE_NAMES}
ADAPTER_ZONE = GENERIC_FACADES | MAKE_MODULES
FACADE_EXPORTS = {
    module_name("build_adapter"): frozenset(
        "BuildInputSelection BuildInputSelectionLike MAKE_REPORT_INPUT_KIND "
        "MAKE_REPORT_RAW_ROLE "
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
    ("project_test_inventory_adapter", "build_adapter",
     "MAKE_REPORT_INPUT_KIND MAKE_REPORT_RAW_ROLE"),
    ("build_ir_validation", "build_ir_reopen",
     "accepted_provenance_role accepted_raw_roles reproject_bound_build_ir"),
)
PRIVATE_IMPORTS = _edges(*PRIVATE_IMPORT_SPECS)
PRIVATE_IMPORTS.update({
    (source, module_name(target)): symbols
    for (source, target), symbols in ENTRYPOINT_PRIVATE_IMPORTS.items()
})
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

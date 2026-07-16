from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping
import re
from typing import Any

from .artifacts import content_sha256
from .rust_project_cargo_v3_link_semantics import link_order_unproven
from .rust_project_cargo_v3_projection_validation import package_member_path


_CARGO_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")
_KIND_BY_PRODUCT = {
    "static-library": "lib", "shared-library": "cdylib", "executable": "bin",
}


def public_namespaces(ir, modules):
    required = defaultdict(set)
    providers = defaultdict(lambda: defaultdict(set))
    for record in ir["public_api"]:
        if record["visibility"] != "public":
            continue
        module_id, symbol = str(record["module_id"]), str(record["symbol"])
        target_id = str(modules[module_id]["target_id"])
        required[target_id].add(symbol)
        if symbol in modules[module_id]["top_level_names"]:
            providers[target_id][symbol].add(module_id)
    hashes = {}
    for target in ir["targets"]:
        target_id = str(target["target_id"])
        hashes[target_id] = content_sha256({
            "required_symbols": sorted(required[target_id]),
            "providers": [
                {"symbol": symbol, "module_id": module_id}
                for symbol in sorted(providers[target_id])
                for module_id in sorted(providers[target_id][symbol])
            ],
        })
    return required, providers, hashes


def entry_module(raw, owned, units, blockers):
    target_id, kind = str(raw["target_id"]), str(raw["kind"])
    entries = [item for item in owned if item["binary_entry_count"] == 1]
    counts = [item["binary_entry_count"] for item in owned]
    if kind != "bin":
        if any(counts):
            block(blockers, "library_main_present", "target", target_id)
        return None
    if not any(counts):
        block(blockers, "binary_main_missing", "target", target_id)
        return None
    if len(entries) != 1 or any(count not in {0, 1} for count in counts):
        block(blockers, "binary_main_multiple", "target", target_id)
        return None
    entry = entries[0]
    if units[entry["unit_id"]]["main_cfg_guarded"]:
        block(blockers, "binary_main_cfg_guarded", "target", target_id)
    return str(entry["module_id"])


def topology_blockers(
    ir, packages, targets, modules, blockers, *, required, providers,
) -> None:
    workspace_id = str(ir["workspace"]["workspace_id"])
    normalized_names = defaultdict(list)
    paths = []
    for package_id, package in packages.items():
        if len(package["target_ids"]) != 1:
            block(blockers, "package_target_cardinality_invalid", "package", package_id)
        if not _CARGO_NAME.fullmatch(package["name"]):
            block(blockers, "package_name_invalid", "package", package_id)
        normalized_names[package["name"].replace("-", "_").casefold()].append(package_id)
        paths.append(package["manifest_path"])
    if any(len(items) > 1 for items in normalized_names.values()):
        block(blockers, "package_name_collision", "workspace", workspace_id)
    if dependency_cycle(packages):
        block(blockers, "package_dependency_cycle", "workspace", workspace_id)
    paths.extend(item["root_path"] for item in targets.values())
    paths.extend(item["render_path"] for item in modules.values())
    if len(paths) != len({item.casefold() for item in paths}):
        block(blockers, "casefold_path_collision", "workspace", workspace_id)
    for target_id, target in targets.items():
        package = packages[target["package_id"]]
        owned = [modules[key] for key in target["module_ids"]]
        if not _CARGO_NAME.fullmatch(target["name"]):
            block(blockers, "target_name_invalid", "target", target_id)
        if _KIND_BY_PRODUCT.get(package["product_kind"]) != target["kind"]:
            block(blockers, "product_target_kind_mismatch", "target", target_id)
        names = [name for item in owned for name in item["top_level_names"]]
        identifiers = [item["identifier"] for item in owned]
        if any(count > 1 for count in Counter(names).values()):
            block(blockers, "target_top_level_name_collision", "target", target_id)
        if len(identifiers) != len(set(identifiers)) or set(identifiers) & set(names):
            block(blockers, "module_identifier_collision", "target", target_id)
        aliases = list(package["dependency_aliases"].values())
        namespace = {item.casefold() for item in [*identifiers, *names]}
        if len(aliases) != len({item.casefold() for item in aliases}) or (
            {item.casefold() for item in aliases} & namespace
        ):
            block(blockers, "dependency_alias_collision", "package", package["package_id"])
        closure_targets = {
            child_target
            for package_id in dependency_closure(package["package_id"], packages)
            for child_target in packages[package_id]["target_ids"]
        }
        symbols = set().union(*(required[key] for key in closure_targets))
        for symbol in symbols:
            found = set().union(*(providers[key][symbol] for key in closure_targets))
            if len(found) > 1:
                block(blockers, "public_provider_multiple", "target", target_id)
            elif not found:
                block(blockers, "required_symbol_provider_unproven", "target", target_id)


def dependency_closure(package_id, packages):
    pending, result = [package_id], set()
    while pending:
        current = pending.pop()
        if current in result:
            continue
        result.add(current)
        pending.extend(packages[current]["dependency_package_ids"])
    return result


def dependency_cycle(packages):
    def visit(current, active, done):
        if current in active:
            return True
        if current in done:
            return False
        active.add(current)
        cyclic = any(
            visit(key, active, done)
            for key in packages[current]["dependency_package_ids"]
        )
        active.remove(current)
        done.add(current)
        return cyclic
    done = set()
    return any(visit(key, set(), done) for key in packages)


def root_path(package_id: str, kind: str) -> str:
    name = "main.rs" if kind == "bin" else "lib.rs"
    return f"{package_member_path(package_id)}/src/{name}"


def block(blockers, code, kind, entity_id) -> None:
    blockers.add((code, kind, entity_id))


__all__ = [
    "block", "entry_module", "link_order_unproven", "public_namespaces",
    "root_path", "topology_blockers",
]

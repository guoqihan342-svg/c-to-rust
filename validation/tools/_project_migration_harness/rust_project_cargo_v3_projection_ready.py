from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import re

from .rust_project_cargo_v3_link_semantics import link_order_unproven


_CARGO_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{0,63}\Z")


def validate_ready_projection(
    packages: Mapping[str, Mapping], targets: Mapping[str, Mapping],
    modules: Mapping[str, Mapping],
) -> None:
    if any(len(item["target_ids"]) != 1 for item in packages.values()):
        _fail("Cargo v3 ready projection requires one target per package")
    if any(not _CARGO_NAME.fullmatch(str(item["name"])) for item in packages.values()):
        _fail("Cargo v3 ready projection package name is invalid")
    normalized = [
        str(item["name"]).replace("-", "_").casefold()
        for item in packages.values()
    ]
    if len(normalized) != len(set(normalized)):
        _fail("Cargo v3 ready projection package names collide")
    paths = [item["manifest_path"] for item in packages.values()]
    paths += [item["root_path"] for item in targets.values()]
    paths += [item["render_path"] for item in modules.values()]
    if len(paths) != len({str(item).casefold() for item in paths}):
        _fail("Cargo v3 ready projection paths collide")
    for target in targets.values():
        _validate_target(target, packages, modules)


def _validate_target(target, packages, modules) -> None:
    owned = [modules[key] for key in target["module_ids"]]
    counts = [item["binary_entry_count"] for item in owned]
    if target["kind"] == "bin":
        entries = [item for item in owned if item["binary_entry_count"] == 1]
        if len(entries) != 1 or any(item not in {0, 1} for item in counts):
            _fail("Cargo v3 ready binary entrypoint is invalid")
        if target["entry_module_id"] != entries[0]["module_id"]:
            _fail("Cargo v3 ready binary entry module drifted")
    elif any(counts) or target["entry_module_id"] is not None:
        _fail("Cargo v3 ready library entrypoint is invalid")
    names = [name for item in owned for name in item["top_level_names"]]
    identifiers = [item["identifier"] for item in owned]
    aliases = list(packages[target["package_id"]]["dependency_aliases"].values())
    if any(count > 1 for count in Counter(names).values()):
        _fail("Cargo v3 ready target names collide")
    if len(identifiers) != len(set(identifiers)) or set(identifiers) & set(names):
        _fail("Cargo v3 ready module identifiers collide")
    namespace = [*identifiers, *names]
    if len(aliases) != len({item.casefold() for item in aliases}) or {
        item.casefold() for item in aliases
    } & {item.casefold() for item in namespace}:
        _fail("Cargo v3 ready dependency aliases collide")
    if link_order_unproven(target):
        _fail("Cargo v3 ready link occurrence order is unproven")


def _fail(message: str) -> None:
    raise ValueError(message)


__all__ = ["validate_ready_projection"]

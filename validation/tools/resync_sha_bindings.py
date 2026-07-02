import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from validation.tools import validate_judge_entrypoints as judge_validator


DEFAULT_SCAN_ROOTS = [
    Path("config/competition-env"),
    Path("validation/evidence"),
    Path("validation/slice-specs"),
]

DEFAULT_JUDGE_CHAIN_SEEDS = [
    Path("config/competition-env/judge-entrypoints/flashdb-harness.json"),
    Path("config/competition-env/bundle-manifest.json"),
]

JUDGE_CHAIN_IGNORED_REF_PREFIXES = (
    "target/",
    "sources/",
    "src/",
    "inc/",
    "stdlib/",
    "validation/evidence/demo/",
    "validation/evidence/libuv/",
    "validation/evidence/zlib-ng/",
    "validation/slice-specs/demo-",
    "validation/slice-specs/libuv-",
    "validation/slice-specs/zlib-",
)


def resync_roots(*, repo_root: Path, scan_roots: list[Path], max_passes: int = 8, dry_run: bool = False) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    json_files = discover_json_files(repo_root=repo_root, scan_roots=scan_roots)
    return resync_json_files(
        repo_root=repo_root,
        json_files=json_files,
        max_passes=max_passes,
        dry_run=dry_run,
    )


def resync_judge_chain(
    *,
    repo_root: Path,
    seeds: list[Path] | None = None,
    max_passes: int = 8,
    dry_run: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    json_files = discover_judge_chain_json_files(
        repo_root=repo_root,
        seeds=seeds or DEFAULT_JUDGE_CHAIN_SEEDS,
        ignored_ref_prefixes=JUDGE_CHAIN_IGNORED_REF_PREFIXES,
    )
    result = resync_json_files(
        repo_root=repo_root,
        json_files=json_files,
        max_passes=max_passes,
        dry_run=dry_run,
        ignored_ref_prefixes=JUDGE_CHAIN_IGNORED_REF_PREFIXES,
        skip_self_refs=True,
        skip_cycle_refs=True,
    )
    result["scan_scope"] = "judge-chain"
    result["ignored_ref_prefixes"] = list(JUDGE_CHAIN_IGNORED_REF_PREFIXES)
    result["scanned_json_files"] = [judge_validator.repo_relative(path, repo_root) for path in json_files]
    return result


def resync_json_files(
    *,
    repo_root: Path,
    json_files: list[Path],
    max_passes: int = 8,
    dry_run: bool = False,
    ignored_ref_prefixes: tuple[str, ...] = (),
    skip_self_refs: bool = False,
    skip_cycle_refs: bool = False,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    json_files = sorted(path.resolve() for path in json_files)
    payload_cache = {json_file: load_json(json_file) for json_file in json_files} if dry_run else None
    simulated_changed_files: set[Path] = set()
    total_updates = 0
    changed_files: set[str] = set()
    missing_refs: set[str] = set()
    self_refs: set[str] = set()
    cycle_refs: set[str] = set()
    skipped_refs: set[str] = set()
    skipped_self_refs: set[str] = set()
    skipped_cycle_refs: set[str] = set()

    for pass_index in range(1, max_passes + 1):
        pass_updates = 0
        cycle_cache: dict[tuple[Path, Path], bool] = {}
        for json_file in json_files:
            payload = payload_cache[json_file] if payload_cache is not None else load_json(json_file)
            result = update_payload_refs(
                payload,
                source_file=json_file,
                repo_root=repo_root,
                cycle_cache=cycle_cache,
                simulated_payloads=payload_cache,
                simulated_changed_files=simulated_changed_files,
                ignored_ref_prefixes=ignored_ref_prefixes,
                skip_self_refs=skip_self_refs,
                skip_cycle_refs=skip_cycle_refs,
            )
            pass_updates += result["updated_ref_count"]
            missing_refs.update(result["missing_refs"])
            self_refs.update(result["self_refs"])
            cycle_refs.update(result["cycle_refs"])
            skipped_refs.update(result["skipped_refs"])
            skipped_self_refs.update(result["skipped_self_refs"])
            skipped_cycle_refs.update(result["skipped_cycle_refs"])
            if result["updated_ref_count"]:
                simulated_changed_files.add(json_file.resolve())
                changed_files.add(judge_validator.repo_relative(json_file, repo_root))
                if not dry_run:
                    write_json(json_file, payload)
        total_updates += pass_updates
        if pass_updates == 0:
            return {
                "status": ("would_update" if dry_run else "updated") if total_updates else "unchanged",
                "passes": pass_index,
                "updated_ref_count": total_updates,
                "changed_files": sorted(changed_files),
                "missing_refs": sorted(missing_refs),
                "self_refs": sorted(self_refs),
                "cycle_refs": sorted(cycle_refs),
                "skipped_refs": sorted(skipped_refs),
                "skipped_self_refs": sorted(skipped_self_refs),
                "skipped_cycle_refs": sorted(skipped_cycle_refs),
                "dry_run": dry_run,
            }

    return {
        "status": "needs_more_passes",
        "passes": max_passes,
        "updated_ref_count": total_updates,
        "changed_files": sorted(changed_files),
        "missing_refs": sorted(missing_refs),
        "self_refs": sorted(self_refs),
        "cycle_refs": sorted(cycle_refs),
        "skipped_refs": sorted(skipped_refs),
        "skipped_self_refs": sorted(skipped_self_refs),
        "skipped_cycle_refs": sorted(skipped_cycle_refs),
        "dry_run": dry_run,
    }


def discover_json_files(*, repo_root: Path, scan_roots: list[Path]) -> list[Path]:
    files: set[Path] = set()
    for root in scan_roots:
        absolute = root if root.is_absolute() else repo_root / root
        if absolute.is_file() and absolute.suffix.lower() == ".json":
            files.add(absolute.resolve())
        elif absolute.is_dir():
            files.update(path.resolve() for path in absolute.rglob("*.json") if path.is_file())
    return sorted(files)


def discover_judge_chain_json_files(
    *,
    repo_root: Path,
    seeds: list[Path],
    ignored_ref_prefixes: tuple[str, ...] = (),
) -> list[Path]:
    repo_root = repo_root.resolve()
    queued: list[Path] = []
    seen: set[Path] = set()

    for seed in seeds:
        absolute = seed if seed.is_absolute() else repo_root / seed
        absolute = absolute.resolve()
        if absolute.suffix.lower() != ".json":
            raise ValueError(f"judge-chain seed must be a JSON file: {seed}")
        if not absolute.is_file():
            raise FileNotFoundError(f"judge-chain seed is missing: {seed}")
        queued.append(absolute)
    terminal_json_files = judge_chain_terminal_json_files(repo_root=repo_root, seeds=queued)

    for json_file in queued:
        resolved = json_file.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            payload = load_json(resolved)
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if is_judge_entrypoint_config(payload):
            for target in iter_judge_config_json_roots(
                payload,
                repo_root=repo_root,
                ignored_ref_prefixes=ignored_ref_prefixes,
            ):
                if target not in seen and target not in queued:
                    queued.append(target)
        if resolved in terminal_json_files:
            continue
        for target in iter_hash_bound_json_refs(
            payload,
            repo_root=repo_root,
            ignored_ref_prefixes=ignored_ref_prefixes,
        ):
            if target not in seen and target not in queued:
                queued.append(target)

    return sorted(seen)


def judge_chain_terminal_json_files(*, repo_root: Path, seeds: list[Path]) -> set[Path]:
    terminal: set[Path] = set()
    for seed in seeds:
        try:
            rel_path = judge_validator.repo_relative(seed, repo_root)
        except ValueError:
            continue
        if rel_path == "config/competition-env/bundle-manifest.json":
            terminal.add(seed.resolve())
    return terminal


def is_judge_entrypoint_config(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("manifest_kind") == "judge-entrypoints"


def iter_judge_config_json_roots(
    payload: dict[str, Any],
    *,
    repo_root: Path,
    ignored_ref_prefixes: tuple[str, ...] = (),
) -> list[Path]:
    refs: set[Path] = set()

    def add_ref(value: Any) -> None:
        if not isinstance(value, dict):
            return
        path_text = value.get("path")
        if not isinstance(path_text, str) or ref_is_ignored(path_text, ignored_ref_prefixes):
            return
        try:
            target = judge_validator.repo_path(path_text, repo_root=repo_root).resolve()
        except (AssertionError, ValueError):
            return
        if target.suffix.lower() == ".json" and target.is_file():
            refs.add(target)

    add_ref(payload.get("environment_profile"))
    entrypoints = payload.get("entrypoints")
    if isinstance(entrypoints, list):
        for entry in entrypoints:
            if not isinstance(entry, dict):
                continue
            add_ref(entry.get("profile"))
            add_ref(entry.get("tracked_manifest"))
            add_ref(entry.get("review_checklist"))

    return sorted(refs)


def iter_hash_bound_json_refs(
    payload: Any,
    *,
    repo_root: Path,
    ignored_ref_prefixes: tuple[str, ...] = (),
) -> list[Path]:
    refs: set[Path] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            path_text = value.get("path")
            sha256 = value.get("sha256")
            if isinstance(path_text, str) and isinstance(sha256, str):
                if not ref_is_ignored(path_text, ignored_ref_prefixes):
                    try:
                        target = judge_validator.repo_path(path_text, repo_root=repo_root).resolve()
                    except (AssertionError, ValueError):
                        target = None
                    if target is not None and target.suffix.lower() == ".json" and target.is_file():
                        refs.add(target)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return sorted(refs)


def ref_is_ignored(path_text: str, ignored_ref_prefixes: tuple[str, ...]) -> bool:
    normalized = path_text.replace("\\", "/")
    return any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in ignored_ref_prefixes)


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.write_bytes(canonical_json_bytes(payload))


def canonical_json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")


def update_payload_refs(
    payload: Any,
    *,
    source_file: Path,
    repo_root: Path,
    cycle_cache: dict[tuple[Path, Path], bool] | None = None,
    simulated_payloads: dict[Path, Any] | None = None,
    simulated_changed_files: set[Path] | None = None,
    ignored_ref_prefixes: tuple[str, ...] = (),
    skip_self_refs: bool = False,
    skip_cycle_refs: bool = False,
) -> dict[str, Any]:
    updated_ref_count = 0
    missing_refs: list[str] = []
    self_refs: list[str] = []
    cycle_refs: list[str] = []
    skipped_refs: list[str] = []
    skipped_self_refs: list[str] = []
    skipped_cycle_refs: list[str] = []
    cycle_cache = cycle_cache if cycle_cache is not None else {}

    def visit(value: Any) -> None:
        nonlocal updated_ref_count
        if isinstance(value, dict):
            path_text = value.get("path")
            sha256 = value.get("sha256")
            if isinstance(path_text, str) and isinstance(sha256, str):
                if ref_is_ignored(path_text, ignored_ref_prefixes):
                    skipped_refs.append(path_text)
                else:
                    try:
                        target = judge_validator.repo_path(path_text, repo_root=repo_root)
                    except (AssertionError, ValueError):
                        target = None
                    if target is not None:
                        if target.resolve() == source_file.resolve():
                            if skip_self_refs:
                                skipped_self_refs.append(path_text)
                            else:
                                self_refs.append(path_text)
                        elif creates_json_hash_cycle(
                            source_file=source_file,
                            target_file=target,
                            repo_root=repo_root,
                            cache=cycle_cache,
                            ignored_ref_prefixes=ignored_ref_prefixes,
                        ):
                            if skip_cycle_refs:
                                skipped_cycle_refs.append(path_text)
                            else:
                                cycle_refs.append(path_text)
                        elif target.is_file():
                            actual_sha = sha256_for_target(
                                target,
                                simulated_payloads=simulated_payloads,
                                simulated_changed_files=simulated_changed_files,
                            )
                            if sha256 != actual_sha:
                                value["sha256"] = actual_sha
                                updated_ref_count += 1
                        else:
                            missing_refs.append(path_text)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return {
        "updated_ref_count": updated_ref_count,
        "missing_refs": missing_refs,
        "self_refs": self_refs,
        "cycle_refs": cycle_refs,
        "skipped_refs": skipped_refs,
        "skipped_self_refs": skipped_self_refs,
        "skipped_cycle_refs": skipped_cycle_refs,
    }


def sha256_for_target(
    target: Path,
    *,
    simulated_payloads: dict[Path, Any] | None,
    simulated_changed_files: set[Path] | None,
) -> str:
    resolved = target.resolve()
    if simulated_payloads is not None and simulated_changed_files is not None and resolved in simulated_changed_files:
        payload = simulated_payloads.get(resolved)
        if payload is not None:
            return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()
    return judge_validator.sha256_file(target)


def creates_json_hash_cycle(
    *,
    source_file: Path,
    target_file: Path,
    repo_root: Path,
    cache: dict[tuple[Path, Path], bool],
    ignored_ref_prefixes: tuple[str, ...] = (),
) -> bool:
    if target_file.suffix.lower() != ".json" or not target_file.is_file():
        return False
    key = (target_file.resolve(), source_file.resolve())
    if key not in cache:
        cache[key] = json_file_reaches_path(
            json_file=target_file.resolve(),
            target_path=source_file.resolve(),
            repo_root=repo_root,
            seen=set(),
            ignored_ref_prefixes=ignored_ref_prefixes,
        )
    return cache[key]


def json_file_reaches_path(
    *,
    json_file: Path,
    target_path: Path,
    repo_root: Path,
    seen: set[Path],
    ignored_ref_prefixes: tuple[str, ...] = (),
) -> bool:
    if json_file in seen:
        return False
    seen.add(json_file)
    try:
        payload = load_json(json_file)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return False

    found = False

    def visit(value: Any) -> None:
        nonlocal found
        if found:
            return
        if isinstance(value, dict):
            path_text = value.get("path")
            if isinstance(path_text, str):
                if ref_is_ignored(path_text, ignored_ref_prefixes):
                    return
                try:
                    resolved = judge_validator.repo_path(path_text, repo_root=repo_root).resolve()
                except (AssertionError, ValueError):
                    resolved = None
                if resolved == target_path:
                    found = True
                    return
                if resolved is not None and resolved.suffix.lower() == ".json" and resolved.is_file():
                    if json_file_reaches_path(
                        json_file=resolved,
                        target_path=target_path,
                        repo_root=repo_root,
                        seen=seen,
                        ignored_ref_prefixes=ignored_ref_prefixes,
                    ):
                        found = True
                        return
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    return found


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Resync repo-relative {path, sha256} bindings with LF-stable hashes.")
    parser.add_argument("--repo-root", default=".", help="Repository root. Defaults to current directory.")
    parser.add_argument(
        "--scan-root",
        action="append",
        dest="scan_roots",
        help="File or directory to scan. May be repeated. Defaults to competition config, validation evidence, and slice specs.",
    )
    parser.add_argument(
        "--scope",
        choices=("default", "judge-chain"),
        default="default",
        help=(
            "Scan scope. default scans --scan-root roots. judge-chain starts from judge entrypoint/config bundle seeds "
            "and follows hash-bound JSON refs, avoiding unrelated historical evidence."
        ),
    )
    parser.add_argument(
        "--seed",
        action="append",
        dest="seeds",
        help="Judge-chain seed JSON file. May be repeated. Only valid with --scope judge-chain.",
    )
    parser.add_argument("--max-passes", type=int, default=8)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Fail when the scan would update bindings, needs more passes, or finds missing/self/cycle refs. "
            "Intended for CI drift gates; usually combined with --dry-run."
        ),
    )
    return parser.parse_args()


def exit_code_for_result(result: dict[str, Any], *, check: bool = False) -> int:
    if not check:
        return 0 if result["status"] in {"updated", "unchanged", "would_update"} else 1
    if result["status"] != "unchanged":
        return 1
    for key in ("missing_refs", "self_refs", "cycle_refs"):
        if result.get(key):
            return 1
    return 0


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root)
    if args.scope == "judge-chain":
        if args.scan_roots:
            raise SystemExit("--scan-root cannot be combined with --scope judge-chain; use --seed instead")
        seeds = [Path(value) for value in args.seeds] if args.seeds else DEFAULT_JUDGE_CHAIN_SEEDS
        result = resync_judge_chain(repo_root=repo_root, seeds=seeds, max_passes=args.max_passes, dry_run=args.dry_run)
    else:
        if args.seeds:
            raise SystemExit("--seed requires --scope judge-chain")
        scan_roots = [Path(value) for value in args.scan_roots] if args.scan_roots else DEFAULT_SCAN_ROOTS
        result = resync_roots(repo_root=repo_root, scan_roots=scan_roots, max_passes=args.max_passes, dry_run=args.dry_run)
    result["check"] = args.check
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code_for_result(result, check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())

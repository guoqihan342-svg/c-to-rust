from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import ExitStack, contextmanager
import hashlib
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
from typing import Any

from .artifacts import content_sha256
from .ledger_security import contains_secret_text
from .project_agent_contract import AGENT_RELATIVE_PATH, verify_project_agent


REQUIRED_ROOTS = ("config", "data", "cache", "state", "tmp", "out")
ENVIRONMENT_VARIABLES = (
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "XDG_CACHE_HOME",
    "XDG_STATE_HOME",
    "TMPDIR",
    "TEMP",
    "TMP",
    "HOME",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "OPENCODE_LOG_PATH",
)
MAX_CREDENTIAL_BYTES = 1_048_576


@contextmanager
def isolated_opencode_environment(
    *, harness_root: Path, runtime_roots: Mapping[str, Any],
    attempt_id: str, fencing_token: int,
) -> Iterator[tuple[dict[str, str], Path, dict[str, Any]]]:
    if (
        not isinstance(attempt_id, str)
        or not attempt_id
        or len(attempt_id) > 512
        or any(ord(char) < 32 for char in attempt_id)
        or fencing_token < 1
    ):
        raise ValueError("OpenCode environment attempt identity is invalid")
    bases = validate_runtime_roots(harness_root, runtime_roots)
    tag = hashlib.sha256(
        f"{attempt_id}:{fencing_token}".encode("utf-8")
    ).hexdigest()[:16]
    source_environment = os.environ.copy()
    agent_contract = verify_project_agent(harness_root)
    with ExitStack() as stack:
        paths = {
            name: Path(stack.enter_context(tempfile.TemporaryDirectory(
                prefix=f"attempt-{tag}-", dir=bases[name]
            )))
            for name in REQUIRED_ROOTS
            if name != "out"
        }
        home = paths["state"] / "home"
        workspace = paths["state"] / "workspace"
        appdata = paths["config"] / "appdata"
        local_appdata = paths["data"] / "localappdata"
        for path in (home, workspace, appdata, local_appdata):
            path.mkdir(parents=True, exist_ok=False)
        auth_digest = _copy_first_regular(
            _credential_candidates(source_environment),
            paths["data"] / "opencode" / "auth.json",
        )
        config_digests = _copy_config_files(
            source_environment,
            paths["config"] / "opencode",
        )
        agent_destination = workspace / AGENT_RELATIVE_PATH
        copied_agent = _copy_first_regular(
            [harness_root / AGENT_RELATIVE_PATH], agent_destination
        )
        if copied_agent != agent_contract["sha256"]:
            raise ValueError("OpenCode agent snapshot drifted during isolation")
        agent_destination.chmod(0o400)
        log_path = paths["data"] / "opencode" / "log" / "opencode.log"
        environment = _base_environment(source_environment)
        environment.update({
            "XDG_CONFIG_HOME": str(paths["config"]),
            "XDG_DATA_HOME": str(paths["data"]),
            "XDG_CACHE_HOME": str(paths["cache"]),
            "XDG_STATE_HOME": str(paths["state"]),
            "TMPDIR": str(paths["tmp"]),
            "TEMP": str(paths["tmp"]),
            "TMP": str(paths["tmp"]),
            "HOME": str(home),
            "USERPROFILE": str(home),
            "APPDATA": str(appdata),
            "LOCALAPPDATA": str(local_appdata),
            "OPENCODE_LOG_PATH": str(log_path),
        })
        runtime_input_sha256 = content_sha256({
            "agent_sha256": copied_agent,
            "auth_sha256": auth_digest or "unavailable",
            "config_sha256": config_digests,
        })
        yield environment, workspace, {
            "schema_version": 1,
            "status": "isolated",
            "scope": "attempt",
            "attempt_tag": tag,
            "explicit_environment": True,
            "global_environment_mutated": False,
            "credential_copy": "bounded-ephemeral" if auth_digest else "unavailable",
            "config_file_count": len(config_digests),
            "agent_sha256": copied_agent,
            "runtime_input_sha256": runtime_input_sha256,
            "environment_variables": list(ENVIRONMENT_VARIABLES),
            "cleanup": "context-exit",
        }


def validate_runtime_roots(
    harness_root: Path, runtime_roots: Mapping[str, Any],
) -> dict[str, Path]:
    if set(runtime_roots) != set(REQUIRED_ROOTS):
        raise ValueError("OpenCode runtime roots must match the fixed isolation contract")
    root = harness_root.resolve(strict=True)
    resolved: dict[str, Path] = {}
    for name in REQUIRED_ROOTS:
        value = runtime_roots.get(name)
        if (
            not isinstance(value, str)
            or not value
            or "\\" in value
            or ":" in value
            or value.startswith("~")
        ):
            raise ValueError("OpenCode runtime root is not a canonical relative path")
        relative = PurePosixPath(value)
        if (
            relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
            or relative.as_posix() != value
        ):
            raise ValueError("OpenCode runtime root escapes the harness")
        unresolved = root
        for part in relative.parts:
            unresolved /= part
            if unresolved.exists() and _is_linklike(unresolved):
                raise ValueError("OpenCode runtime root contains a link")
        target = unresolved.resolve()
        try:
            target.relative_to(root)
        except ValueError as error:
            raise ValueError("OpenCode runtime root escapes the harness") from error
        target.mkdir(parents=True, exist_ok=True)
        resolved[name] = target
    values = list(resolved.values())
    if any(
        left == right or left in right.parents or right in left.parents
        for index, left in enumerate(values)
        for right in values[index + 1 :]
    ):
        raise ValueError("OpenCode runtime roots must be pairwise disjoint")
    return resolved


def preflight_runtime_roots(out_root_rel: str) -> dict[str, str]:
    base = PurePosixPath(out_root_rel)
    if (
        not out_root_rel
        or "\\" in out_root_rel
        or ":" in out_root_rel
        or out_root_rel.startswith("~")
        or base.is_absolute()
        or any(part in {"", ".", ".."} for part in base.parts)
        or base.as_posix() != out_root_rel
    ):
        raise ValueError("preflight out root must be a canonical relative path")
    prefix = (base / "preflight" / "runtime").as_posix()
    return {name: f"{prefix}/{name}" for name in REQUIRED_ROOTS}


def fixed_isolation_contract() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "status": "required",
        "scope": "attempt",
        "required_roots": list(REQUIRED_ROOTS),
        "environment_variables": list(ENVIRONMENT_VARIABLES),
        "credential_copy": "bounded-ephemeral",
        "parent_environment": "allowlist",
        "agent": "immutable-attempt-snapshot",
        "global_environment_mutation": "forbidden",
        "cleanup": "context-exit",
    }


def _credential_candidates(environment: Mapping[str, str]) -> list[Path]:
    home = Path(environment.get("HOME", str(Path.home())))
    candidates = [
        Path(environment.get("XDG_DATA_HOME", home / ".local" / "share"))
        / "opencode" / "auth.json",
    ]
    local = environment.get("LOCALAPPDATA")
    if local:
        candidates.append(Path(local) / "opencode" / "auth.json")
    return candidates


def _config_roots(environment: Mapping[str, str]) -> list[Path]:
    home = Path(environment.get("HOME", str(Path.home())))
    roots = [Path(environment.get("XDG_CONFIG_HOME", home / ".config")) / "opencode"]
    appdata = environment.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / "opencode")
    return roots


def _copy_config_files(environment: Mapping[str, str], destination: Path) -> list[str]:
    copied: list[str] = []
    seen: set[str] = set()
    for root in _config_roots(environment):
        for name in ("opencode.json", "opencode.jsonc"):
            if name in seen:
                continue
            digest = _copy_first_regular([root / name], destination / name)
            if digest is not None:
                seen.add(name)
                copied.append(digest)
    return sorted(copied)


def _copy_first_regular(candidates: list[Path], destination: Path) -> str | None:
    for source in candidates:
        try:
            if source.is_symlink():
                continue
            flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(source, flags)
            with os.fdopen(descriptor, "rb") as handle:
                metadata = os.fstat(handle.fileno())
                if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_CREDENTIAL_BYTES:
                    continue
                data = handle.read(MAX_CREDENTIAL_BYTES + 1)
            if len(data) > MAX_CREDENTIAL_BYTES:
                continue
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("xb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            destination.chmod(0o600)
            return hashlib.sha256(data).hexdigest()
        except OSError:
            continue
    return None


def _base_environment(source: Mapping[str, str]) -> dict[str, str]:
    allowed = (
        "PATH", "LANG", "LC_ALL", "TZ", "SYSTEMROOT", "WINDIR", "COMSPEC",
        "PATHEXT", "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
        "SSL_CERT_FILE", "SSL_CERT_DIR",
    )
    result = {key: source[key] for key in allowed if source.get(key)}
    result.setdefault("LANG", "C.UTF-8")
    result.setdefault("LC_ALL", "C.UTF-8")
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        value = source.get(key)
        if (
            value
            and "@" not in value
            and "\r" not in value
            and "\n" not in value
            and not contains_secret_text(value)
        ):
            result[key] = value
    return result


def _is_linklike(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", None)
    return path.is_symlink() or bool(is_junction and is_junction())


__all__ = [
    "ENVIRONMENT_VARIABLES",
    "REQUIRED_ROOTS",
    "fixed_isolation_contract",
    "isolated_opencode_environment",
    "preflight_runtime_roots",
    "validate_runtime_roots",
]

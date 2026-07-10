def ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        pragma journal_mode = wal;
        create table if not exists profiles(
          profile_id text primary key,
          profile_path text not null,
          profile_sha256 text not null,
          payload_json text not null,
          created_at text not null
        );
        create table if not exists runs(
          run_id text primary key,
          out_root text not null,
          proof_class text not null,
          profile_id text not null,
          profile_sha256 text not null,
          schema_version integer not null,
          status text not null,
          started_at text not null,
          ended_at text,
          final_gate_status text,
          summary_path text,
          summary_sha256 text,
          payload_json text not null
        );
        create table if not exists agents(
          agent_id text primary key,
          run_id text not null,
          runtime text not null,
          worker_name text not null,
          role text not null,
          isolated_out_root text not null,
          status text not null,
          created_at text not null
        );
        create table if not exists agent_tasks(
          task_id text primary key,
          run_id text not null,
          agent_id text not null,
          target_id text not null,
          slice_id text not null,
          phase text not null,
          status text not null,
          attempt integer not null,
          allowed_paths_json text not null,
          started_at text,
          ended_at text,
          error_key text
        );
        create table if not exists slices(
          target_id text not null,
          slice_id text not null,
          source_repo_root_rel text not null,
          source_file_rel text not null,
          function_name text not null,
          source_commit text not null,
          slice_spec_path text,
          slice_spec_sha256 text,
          fixture_path text,
          fixture_hash text,
          payload_json text not null,
          primary key(target_id, slice_id)
        );
        create table if not exists candidates(
          candidate_id text primary key,
          run_id text not null,
          target_id text,
          slice_id text,
          source_kind text not null,
          semantic_pass integer not null default 0,
          artifact_path text,
          artifact_sha256 text,
          payload_json text not null
        );
        create table if not exists gates(
          gate_id text primary key,
          run_id text not null,
          target_id text,
          slice_id text,
          gate_name text not null,
          status text not null,
          is_blocking integer not null,
          evidence_path text,
          evidence_sha256 text,
          payload_json text not null
        );
        create table if not exists artifacts(
          artifact_id integer primary key autoincrement,
          run_id text not null,
          agent_id text,
          target_id text,
          slice_id text,
          kind text not null,
          repo_rel_path text not null unique,
          sha256 text not null,
          status text not null,
          semantic_role text not null,
          schema_name text,
          payload_status text,
          payload_json text not null,
          created_at text not null
        );
        create table if not exists artifact_links(
          link_id integer primary key autoincrement,
          run_id text not null,
          from_artifact_path text not null,
          to_artifact_path text not null,
          relation text not null,
          payload_json text not null
        );
        create table if not exists events(
          event_id integer primary key autoincrement,
          run_id text not null,
          event_type text not null,
          payload_json text not null,
          created_at text not null
        );
        create table if not exists leases(
          resource_key text primary key,
          run_id text not null,
          lease_owner text not null,
          status text not null,
          expires_at text not null,
          heartbeat_at text not null,
          fencing_token integer not null
        );
        create table if not exists context_packs(
          context_pack_id text primary key,
          run_id text not null,
          target_id text,
          slice_id text,
          depth integer not null,
          max_tokens integer not null,
          artifact_path text not null,
          artifact_sha256 text not null,
          payload_json text not null
        );
        create table if not exists repair_hints(
          hint_id text primary key,
          run_id text not null,
          target_id text,
          slice_id text,
          root_cause_key text not null,
          status text not null,
          payload_json text not null,
          created_at text not null
        );
        create table if not exists metrics(
          metric_id integer primary key autoincrement,
          run_id text not null,
          metric_name text not null,
          metric_value real not null,
          payload_json text not null,
          created_at text not null
        );
        """
    )


def assignment_file_path(db_path: Path, worker_id: str) -> Path:
    out_root = db_path.parent.parent
    return out_root / "harness" / "assignments" / f"{worker_id}.json"


def run_proof_class(db_path: Path, run_id: str) -> str:
    connection = connect(db_path)
    try:
        row = connection.execute("select proof_class from runs where run_id=?", (run_id,)).fetchone()
    finally:
        connection.close()
    if row is None:
        raise SystemExit(f"unknown run_id: {run_id}")
    return str(row[0])


def assigned_worker_out_root_rel(connection: sqlite3.Connection, *, run_id: str, worker_id: str) -> str:
    row = connection.execute(
        "select isolated_out_root from agents where run_id=? and agent_id=?",
        (run_id, worker_id),
    ).fetchone()
    if row is None:
        raise SystemExit(f"worker is not assigned in run {run_id}: {worker_id}")
    return str(row[0])


def assigned_worker_summary_path(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    worker_id: str,
    repo_root: Path,
) -> Path:
    out_root_rel = assigned_worker_out_root_rel(connection, run_id=run_id, worker_id=worker_id)
    return repo_path(Path(out_root_rel), repo_root=repo_root) / "summary" / "competition-run-summary.json"


def discover_top_level_function_names(text: str) -> list[str]:
    masked = mask_comments_and_strings(text)
    names: list[str] = []
    seen: set[str] = set()
    index = 0
    while index < len(masked):
        if masked[index] != "{":
            index += 1
            continue
        prefix = masked[:index].rstrip()
        if not prefix.endswith(")"):
            match_end = find_matching(masked, index, "{", "}")
            index = match_end + 1 if match_end is not None else index + 1
            continue
        close_paren = len(prefix) - 1
        open_paren = find_matching_reverse(masked, close_paren, "(", ")")
        if open_paren is None:
            index += 1
            continue
        name_match = re.search(r"([A-Za-z_][A-Za-z0-9_]*)\s*$", masked[:open_paren].rstrip())
        if name_match is None:
            index += 1
            continue
        name = name_match.group(1)
        if name not in C_STATEMENT_KEYWORDS and name not in seen:
            names.append(name)
            seen.add(name)
        match_end = find_matching(masked, index, "{", "}")
        index = match_end + 1 if match_end is not None else index + 1
    return names


C_STATEMENT_KEYWORDS = {
    "do",
    "else",
    "for",
    "if",
    "switch",
    "while",
}


def find_matching_reverse(text: str, close_index: int, open_char: str, close_char: str) -> int | None:
    depth = 0
    for index in range(close_index, -1, -1):
        char = text[index]
        if char == close_char:
            depth += 1
        elif char == open_char:
            depth -= 1
            if depth == 0:
                return index
    return None


def connect(db_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=30)
    connection.execute("pragma foreign_keys = on")
    connection.execute("pragma busy_timeout = 30000")
    return connection


def record_event(connection: sqlite3.Connection, *, run_id: str, event_type: str, payload: dict[str, Any]) -> None:
    connection.execute(
        "insert into events(run_id, event_type, payload_json, created_at) values (?, ?, ?, ?)",
        (run_id, event_type, json.dumps(payload, sort_keys=True), now_text()),
    )


def repo_path(path: Path, *, repo_root: Path = REPO_ROOT) -> Path:
    if path.is_absolute():
        resolved = path.resolve()
    else:
        checked_relative_path(path_text(path))
        resolved = (repo_root / path).resolve()
    resolved = normalize_windows_extended_path(resolved)
    repo_resolved = normalize_windows_extended_path(repo_root.resolve())
    try:
        resolved.relative_to(repo_resolved)
    except ValueError as error:
        raise SystemExit(f"path must stay inside repository: {path}") from error
    return resolved


def normalize_windows_extended_path(path: Path) -> Path:
    text = str(path)
    if text.startswith("\\\\?\\"):
        return Path(text[4:])
    return path


def checked_relative_path(value: str) -> PurePosixPath:
    if not value or "\\" in value:
        raise SystemExit(f"path must be a non-empty POSIX relative path: {value}")
    if value.startswith("/") or value.startswith("~"):
        raise SystemExit(f"path must be relative to repository: {value}")
    if len(value) >= 2 and value[1] == ":":
        raise SystemExit(f"path must not contain a drive prefix: {value}")
    path = PurePosixPath(value)
    if ".." in path.parts:
        raise SystemExit(f"path must not escape repository: {value}")
    return path


def path_text(path: Path) -> str:
    return PurePosixPath(*path.parts).as_posix()


def slug_id(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    if not slug:
        raise SystemExit(f"cannot build id slug from empty value: {value!r}")
    return slug


def repo_relative(path: Path, *, repo_root: Path = REPO_ROOT) -> str:
    resolved = normalize_windows_extended_path(path.resolve())
    repo_resolved = normalize_windows_extended_path(repo_root.resolve())
    try:
        return resolved.relative_to(repo_resolved).as_posix()
    except ValueError as error:
        raise SystemExit(f"path must stay inside repository: {path}") from error


def sha256_file(path: Path) -> str:
    data = path.read_bytes()
    if path.suffix.lower() in LF_STABLE_TEXT_SUFFIXES:
        data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    tmp_path: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        tmp_path = Path(tmp_name)
        with os.fdopen(fd, "w", encoding=encoding, newline="") as handle:
            fd = None
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    tmp_path: Path | None = None
    try:
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
        tmp_path = Path(tmp_name)
        with os.fdopen(fd, "wb") as handle:
            fd = None
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        if fd is not None:
            os.close(fd)
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink()


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def now_text() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


if __name__ == "__main__":
    raise SystemExit(main())

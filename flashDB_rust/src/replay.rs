use crate::config::DEFAULT_FLASH_SIZE;
use crate::flash::{FileFlash, MemoryFlash};
use crate::format::image_hash;
use crate::kvdb::{KvDb, KvEntry};
use crate::tsdb::{TsDb, TsEntry};
use crate::types::{Error, Result, TsStatus};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone)]
struct Fixture {
    name: String,
    operations: Vec<Operation>,
    accepted_differences: Vec<AcceptedDifference>,
}

#[derive(Debug, Clone)]
struct Operation {
    id: String,
    op: String,
    fields: BTreeMap<String, String>,
}

#[derive(Debug, Clone)]
struct AcceptedDifference {
    id: String,
    reason: String,
    fields: String,
}

#[derive(Debug, Clone)]
struct StepReport {
    id: String,
    op: String,
    status: String,
    code: String,
    fields: Vec<(String, String)>,
}

pub fn run_replay(
    fixture_path: &Path,
    report_path: Option<&Path>,
    backend: &str,
    size: usize,
) -> Result<String> {
    if backend != "memory" && backend != "file" {
        return Err(Error::Cli(format!(
            "unsupported backend {backend}; expected memory or file"
        )));
    }

    let fixture_text = fs::read_to_string(fixture_path)?;
    let fixture = parse_fixture(&fixture_text)?;
    let fixture_hash = image_hash(fixture_text.as_bytes());
    let mut state = ReplayState::new(backend, size)?;
    let mut steps = Vec::new();

    for operation in &fixture.operations {
        steps.push(execute_step(&mut state, operation));
    }

    let json = replay_report_json(
        &fixture,
        fixture_path,
        &fixture_hash,
        backend,
        &steps,
        "NOT_APPLICABLE_RUST_REPLAY",
    );
    write_optional_report(report_path, &json)?;
    Ok(json)
}

pub fn run_diff(
    rust_report: &Path,
    oracle_report: &Path,
    report_path: Option<&Path>,
) -> Result<String> {
    let actual = fs::read_to_string(rust_report)?;
    let expected = fs::read_to_string(oracle_report)?;
    let actual_hash = image_hash(actual.as_bytes());
    let expected_hash = image_hash(expected.as_bytes());
    let passed = actual == expected;
    let mismatch = if passed {
        None
    } else {
        Some(first_mismatch(&expected, &actual))
    };
    let json = diff_report_json(
        rust_report,
        oracle_report,
        &actual_hash,
        &expected_hash,
        passed,
        mismatch.as_ref(),
        c_toolchain_status(),
    );
    write_optional_report(report_path, &json)?;
    if passed {
        Ok(json)
    } else {
        let detail = mismatch
            .map(|value| format!("{} at {}", value.step_id, value.field_path))
            .unwrap_or_else(|| "unknown mismatch".to_string());
        Err(Error::Cli(format!("diff mismatch: {detail}")))
    }
}

fn write_optional_report(path: Option<&Path>, json: &str) -> Result<()> {
    if let Some(path) = path {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(path, json)?;
    }
    Ok(())
}

struct ReplayState {
    kv: KvReplayDb,
    ts: TsReplayDb,
}

impl ReplayState {
    fn new(backend: &str, size: usize) -> Result<Self> {
        let size = if size == 0 { DEFAULT_FLASH_SIZE } else { size };
        let unique = unique_run_id();
        let base = std::env::temp_dir().join(format!("flashdb_rust_replay_{unique}"));
        let kv = if backend == "file" {
            fs::create_dir_all(&base)?;
            KvReplayDb::File {
                db: Some(KvDb::create(FileFlash::create(base.join("kv.img"), size)?)?),
                path: base.join("kv.img"),
                size,
            }
        } else {
            KvReplayDb::Memory(KvDb::create(MemoryFlash::new(size))?)
        };
        let ts = if backend == "file" {
            TsReplayDb::File {
                db: Some(TsDb::create(FileFlash::create(base.join("ts.img"), size)?)?),
                path: base.join("ts.img"),
                size,
            }
        } else {
            TsReplayDb::Memory(TsDb::create(MemoryFlash::new(size))?)
        };
        Ok(Self { kv, ts })
    }
}

enum KvReplayDb {
    Memory(KvDb<MemoryFlash>),
    File {
        db: Option<KvDb<FileFlash>>,
        path: PathBuf,
        size: usize,
    },
}

impl KvReplayDb {
    fn set(&mut self, key: &str, value: &[u8]) -> Result<()> {
        match self {
            KvReplayDb::Memory(db) => db.set(key, value),
            KvReplayDb::File { db, .. } => db_mut(db).set(key, value),
        }
    }

    fn get(&mut self, key: &str) -> Result<Option<Vec<u8>>> {
        match self {
            KvReplayDb::Memory(db) => db.get(key),
            KvReplayDb::File { db, .. } => db_mut(db).get(key),
        }
    }

    fn delete(&mut self, key: &str) -> Result<()> {
        match self {
            KvReplayDb::Memory(db) => db.delete(key),
            KvReplayDb::File { db, .. } => db_mut(db).delete(key),
        }
    }

    fn entries(&self) -> Vec<KvEntry> {
        match self {
            KvReplayDb::Memory(db) => db.entries(),
            KvReplayDb::File { db, .. } => db.as_ref().expect("file db present").entries(),
        }
    }

    fn compact(&mut self) -> Result<()> {
        match self {
            KvReplayDb::Memory(db) => db.compact(),
            KvReplayDb::File { db, .. } => db_mut(db).compact(),
        }
    }

    fn image_hash(&mut self) -> Result<String> {
        match self {
            KvReplayDb::Memory(db) => db.image_hash(),
            KvReplayDb::File { db, .. } => db_mut(db).image_hash(),
        }
    }

    fn reopen(&mut self) -> Result<()> {
        match self {
            KvReplayDb::Memory(db) => {
                let image = db.image()?;
                *self = KvReplayDb::Memory(KvDb::open(MemoryFlash::from_bytes(image))?);
                Ok(())
            }
            KvReplayDb::File { db, path, size } => {
                drop(db.take());
                *db = Some(KvDb::open(FileFlash::open(path, *size)?)?);
                Ok(())
            }
        }
    }
}

enum TsReplayDb {
    Memory(TsDb<MemoryFlash>),
    File {
        db: Option<TsDb<FileFlash>>,
        path: PathBuf,
        size: usize,
    },
}

impl TsReplayDb {
    fn append(&mut self, timestamp: i64, payload: &[u8]) -> Result<u64> {
        match self {
            TsReplayDb::Memory(db) => db.append(timestamp, payload),
            TsReplayDb::File { db, .. } => ts_db_mut(db).append(timestamp, payload),
        }
    }

    fn query(&self, from: i64, to: i64) -> Vec<TsEntry> {
        match self {
            TsReplayDb::Memory(db) => db.query(from, to),
            TsReplayDb::File { db, .. } => db.as_ref().expect("file db present").query(from, to),
        }
    }

    fn count_by_status(&self, from: i64, to: i64, status: TsStatus) -> usize {
        match self {
            TsReplayDb::Memory(db) => db.count_by_status(from, to, status),
            TsReplayDb::File { db, .. } => db
                .as_ref()
                .expect("file db present")
                .count_by_status(from, to, status),
        }
    }

    fn set_status(&mut self, id: u64, status: TsStatus) -> Result<()> {
        match self {
            TsReplayDb::Memory(db) => db.set_status(id, status),
            TsReplayDb::File { db, .. } => ts_db_mut(db).set_status(id, status),
        }
    }

    fn image_hash(&mut self) -> Result<String> {
        match self {
            TsReplayDb::Memory(db) => db.image_hash(),
            TsReplayDb::File { db, .. } => ts_db_mut(db).image_hash(),
        }
    }

    fn reopen(&mut self) -> Result<()> {
        match self {
            TsReplayDb::Memory(db) => {
                let image = db.image()?;
                *self = TsReplayDb::Memory(TsDb::open(MemoryFlash::from_bytes(image))?);
                Ok(())
            }
            TsReplayDb::File { db, path, size } => {
                drop(db.take());
                *db = Some(TsDb::open(FileFlash::open(path, *size)?)?);
                Ok(())
            }
        }
    }
}

fn db_mut(db: &mut Option<KvDb<FileFlash>>) -> &mut KvDb<FileFlash> {
    db.as_mut().expect("file db present")
}

fn ts_db_mut(db: &mut Option<TsDb<FileFlash>>) -> &mut TsDb<FileFlash> {
    db.as_mut().expect("file db present")
}

fn execute_step(state: &mut ReplayState, operation: &Operation) -> StepReport {
    match execute_operation(state, operation) {
        Ok(fields) => StepReport {
            id: operation.id.clone(),
            op: operation.op.clone(),
            status: "ok".to_string(),
            code: "OK".to_string(),
            fields,
        },
        Err(err) => StepReport {
            id: operation.id.clone(),
            op: operation.op.clone(),
            status: "error".to_string(),
            code: err.code().to_string(),
            fields: vec![("message".to_string(), json_string(&err.to_string()))],
        },
    }
}

fn execute_operation(
    state: &mut ReplayState,
    operation: &Operation,
) -> Result<Vec<(String, String)>> {
    match operation.op.as_str() {
        "kv.set" => {
            let key = operation.required("key")?;
            let value = operation.required("value")?;
            state.kv.set(&key, value.as_bytes())?;
            Ok(vec![
                ("key".to_string(), json_string(&key)),
                ("value".to_string(), json_string(&value)),
            ])
        }
        "kv.get" => {
            let key = operation.required("key")?;
            let value = state.kv.get(&key)?;
            Ok(vec![(
                "value".to_string(),
                optional_bytes_json(value.as_deref()),
            )])
        }
        "kv.delete" => {
            let key = operation.required("key")?;
            state.kv.delete(&key)?;
            Ok(vec![("key".to_string(), json_string(&key))])
        }
        "kv.entries" => Ok(vec![(
            "entries".to_string(),
            kv_entries_json(&state.kv.entries()),
        )]),
        "kv.compact" => {
            state.kv.compact()?;
            Ok(vec![(
                "image_hash".to_string(),
                json_string(&state.kv.image_hash()?),
            )])
        }
        "kv.reopen" => {
            state.kv.reopen()?;
            Ok(vec![(
                "image_hash".to_string(),
                json_string(&state.kv.image_hash()?),
            )])
        }
        "kv.image_hash" => Ok(vec![(
            "image_hash".to_string(),
            json_string(&state.kv.image_hash()?),
        )]),
        "ts.append" => {
            let timestamp = operation.required_i64("timestamp")?;
            let value = operation.required("value")?;
            let id = state.ts.append(timestamp, value.as_bytes())?;
            Ok(vec![
                ("entry_id".to_string(), id.to_string()),
                ("timestamp".to_string(), timestamp.to_string()),
                ("value".to_string(), json_string(&value)),
            ])
        }
        "ts.query" => {
            let from = operation.required_i64("from")?;
            let to = operation.required_i64("to")?;
            Ok(vec![(
                "entries".to_string(),
                ts_entries_json(&state.ts.query(from, to)),
            )])
        }
        "ts.count_status" => {
            let from = operation.required_i64("from")?;
            let to = operation.required_i64("to")?;
            let status = parse_status(&operation.required("status")?)?;
            let count = state.ts.count_by_status(from, to, status);
            Ok(vec![("count".to_string(), count.to_string())])
        }
        "ts.set_status" => {
            let id = operation.required_u64("entry_id")?;
            let status = parse_status(&operation.required("status")?)?;
            state.ts.set_status(id, status)?;
            Ok(vec![
                ("entry_id".to_string(), id.to_string()),
                ("status".to_string(), json_string(status_name(status))),
            ])
        }
        "ts.reopen" => {
            state.ts.reopen()?;
            Ok(vec![(
                "image_hash".to_string(),
                json_string(&state.ts.image_hash()?),
            )])
        }
        "ts.image_hash" => Ok(vec![(
            "image_hash".to_string(),
            json_string(&state.ts.image_hash()?),
        )]),
        other => Err(Error::Cli(format!("unknown fixture operation {other}"))),
    }
}

impl Operation {
    fn required(&self, name: &str) -> Result<String> {
        self.fields
            .get(name)
            .cloned()
            .ok_or_else(|| Error::Parse(format!("operation {} missing field {name}", self.id)))
    }

    fn required_i64(&self, name: &str) -> Result<i64> {
        self.required(name)?
            .parse()
            .map_err(|_| Error::Parse(format!("operation {} invalid i64 field {name}", self.id)))
    }

    fn required_u64(&self, name: &str) -> Result<u64> {
        self.required(name)?
            .parse()
            .map_err(|_| Error::Parse(format!("operation {} invalid u64 field {name}", self.id)))
    }
}

fn parse_fixture(input: &str) -> Result<Fixture> {
    let name = field_value(input, "name").unwrap_or_else(|| "fixture".to_string());
    let mut operations = Vec::new();
    let mut accepted_differences = Vec::new();
    let mut in_accepted = false;

    for line in input.lines() {
        let trimmed = line.trim().trim_end_matches(',');
        if trimmed.contains("\"accepted_differences\"") {
            in_accepted = true;
            continue;
        }
        if in_accepted && trimmed.starts_with(']') {
            in_accepted = false;
            continue;
        }
        if !trimmed.starts_with('{') {
            continue;
        }
        if trimmed.contains("\"op\"") {
            let id = field_value(trimmed, "id")
                .ok_or_else(|| Error::Parse("fixture operation missing id".to_string()))?;
            let op = field_value(trimmed, "op")
                .ok_or_else(|| Error::Parse(format!("fixture operation {id} missing op")))?;
            let mut fields = BTreeMap::new();
            for field in [
                "key",
                "value",
                "timestamp",
                "from",
                "to",
                "status",
                "entry_id",
            ] {
                if let Some(value) = field_value(trimmed, field) {
                    fields.insert(field.to_string(), value);
                }
            }
            operations.push(Operation { id, op, fields });
        } else if in_accepted {
            accepted_differences.push(AcceptedDifference {
                id: field_value(trimmed, "id").unwrap_or_else(|| "unknown".to_string()),
                reason: field_value(trimmed, "reason").unwrap_or_default(),
                fields: field_value(trimmed, "fields").unwrap_or_default(),
            });
        }
    }

    if operations.is_empty() {
        return Err(Error::Parse("fixture has no operations".to_string()));
    }
    Ok(Fixture {
        name,
        operations,
        accepted_differences,
    })
}

fn field_value(input: &str, name: &str) -> Option<String> {
    let pattern = format!("\"{name}\"");
    let start = input.find(&pattern)? + pattern.len();
    let after_name = &input[start..];
    let colon = after_name.find(':')?;
    let mut rest = after_name[colon + 1..].trim_start();
    if rest.starts_with('"') {
        rest = &rest[1..];
        let end = rest.find('"')?;
        Some(rest[..end].to_string())
    } else {
        let end = rest
            .find(|ch: char| ch == ',' || ch == '}' || ch == ']')
            .unwrap_or(rest.len());
        Some(rest[..end].trim().to_string())
    }
}

#[derive(Debug, Clone)]
struct Mismatch {
    byte_offset: usize,
    step_id: String,
    field_path: String,
    expected: String,
    actual: String,
}

fn first_mismatch(expected: &str, actual: &str) -> Mismatch {
    let max = expected.len().min(actual.len());
    let mut offset = max;
    for i in 0..max {
        if expected.as_bytes()[i] != actual.as_bytes()[i] {
            offset = i;
            break;
        }
    }
    Mismatch {
        byte_offset: offset,
        step_id: nearest_step_id(actual, offset)
            .or_else(|| nearest_step_id(expected, offset))
            .unwrap_or_else(|| "report".to_string()),
        field_path: format!("report.byte_{offset}"),
        expected: snippet(expected, offset),
        actual: snippet(actual, offset),
    }
}

fn nearest_step_id(text: &str, offset: usize) -> Option<String> {
    let end = offset.min(text.len());
    let prefix = &text[..end];
    let marker = "\"id\":\"";
    let start = prefix.rfind(marker)? + marker.len();
    let rest = &prefix[start..];
    let end = rest.find('"')?;
    Some(rest[..end].to_string())
}

fn snippet(text: &str, offset: usize) -> String {
    if text.is_empty() {
        return String::new();
    }
    let start = offset.saturating_sub(16).min(text.len());
    let end = (offset + 32).min(text.len());
    text[start..end].to_string()
}

fn replay_report_json(
    fixture: &Fixture,
    fixture_path: &Path,
    fixture_hash: &str,
    backend: &str,
    steps: &[StepReport],
    toolchain_status: &str,
) -> String {
    format!(
        concat!(
            "{{",
            "\"command\":\"replay\",",
            "\"schema_version\":1,",
            "\"fixture\":\"{}\",",
            "\"fixture_name\":\"{}\",",
            "\"fixture_hash\":\"{}\",",
            "\"backend\":\"{}\",",
            "\"toolchain_status\":\"{}\",",
            "\"result\":\"completed\",",
            "\"accepted_differences\":[{}],",
            "\"steps\":[{}]",
            "}}"
        ),
        json_escape(&fixture_path.display().to_string()),
        json_escape(&fixture.name),
        json_escape(fixture_hash),
        json_escape(backend),
        json_escape(toolchain_status),
        accepted_differences_json(&fixture.accepted_differences),
        steps_json(steps)
    )
}

fn diff_report_json(
    rust_report: &Path,
    oracle_report: &Path,
    rust_hash: &str,
    oracle_hash: &str,
    passed: bool,
    mismatch: Option<&Mismatch>,
    toolchain_status: &str,
) -> String {
    let status = if passed { "passed" } else { "failed" };
    let mismatch_json = mismatch
        .map(mismatch_json)
        .unwrap_or_else(|| "null".to_string());
    format!(
        concat!(
            "{{",
            "\"command\":\"diff\",",
            "\"schema_version\":1,",
            "\"status\":\"{}\",",
            "\"rust_report\":\"{}\",",
            "\"oracle_report\":\"{}\",",
            "\"rust_report_hash\":\"{}\",",
            "\"oracle_report_hash\":\"{}\",",
            "\"toolchain_status\":\"{}\",",
            "\"first_mismatch\":{}",
            "}}"
        ),
        status,
        json_escape(&rust_report.display().to_string()),
        json_escape(&oracle_report.display().to_string()),
        json_escape(rust_hash),
        json_escape(oracle_hash),
        json_escape(toolchain_status),
        mismatch_json
    )
}

fn steps_json(steps: &[StepReport]) -> String {
    steps
        .iter()
        .map(|step| {
            let fields = step
                .fields
                .iter()
                .map(|(name, value)| format!("\"{}\":{}", json_escape(name), value))
                .collect::<Vec<_>>()
                .join(",");
            if fields.is_empty() {
                format!(
                    "{{\"id\":\"{}\",\"op\":\"{}\",\"status\":\"{}\",\"code\":\"{}\"}}",
                    json_escape(&step.id),
                    json_escape(&step.op),
                    json_escape(&step.status),
                    json_escape(&step.code)
                )
            } else {
                format!(
                    "{{\"id\":\"{}\",\"op\":\"{}\",\"status\":\"{}\",\"code\":\"{}\",{}}}",
                    json_escape(&step.id),
                    json_escape(&step.op),
                    json_escape(&step.status),
                    json_escape(&step.code),
                    fields
                )
            }
        })
        .collect::<Vec<_>>()
        .join(",")
}

fn accepted_differences_json(values: &[AcceptedDifference]) -> String {
    values
        .iter()
        .map(|value| {
            format!(
                "{{\"id\":\"{}\",\"reason\":\"{}\",\"fields\":\"{}\"}}",
                json_escape(&value.id),
                json_escape(&value.reason),
                json_escape(&value.fields)
            )
        })
        .collect::<Vec<_>>()
        .join(",")
}

fn mismatch_json(value: &Mismatch) -> String {
    format!(
        concat!(
            "{{",
            "\"byte_offset\":{},",
            "\"step_id\":\"{}\",",
            "\"field_path\":\"{}\",",
            "\"expected\":\"{}\",",
            "\"actual\":\"{}\"",
            "}}"
        ),
        value.byte_offset,
        json_escape(&value.step_id),
        json_escape(&value.field_path),
        json_escape(&value.expected),
        json_escape(&value.actual)
    )
}

fn kv_entries_json(entries: &[KvEntry]) -> String {
    let body = entries
        .iter()
        .map(|entry| {
            format!(
                "{{\"key\":\"{}\",\"value\":\"{}\"}}",
                json_escape(&entry.key),
                json_escape(&String::from_utf8_lossy(&entry.value))
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    format!("[{body}]")
}

fn ts_entries_json(entries: &[TsEntry]) -> String {
    let body = entries
        .iter()
        .map(|entry| {
            format!(
                concat!(
                    "{{",
                    "\"entry_id\":{},",
                    "\"timestamp\":{},",
                    "\"status\":\"{}\",",
                    "\"value\":\"{}\"",
                    "}}"
                ),
                entry.id,
                entry.timestamp,
                json_escape(status_name(entry.status)),
                json_escape(&String::from_utf8_lossy(&entry.payload))
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    format!("[{body}]")
}

fn optional_bytes_json(value: Option<&[u8]>) -> String {
    value
        .map(|bytes| json_string(&String::from_utf8_lossy(bytes)))
        .unwrap_or_else(|| "null".to_string())
}

fn json_string(value: &str) -> String {
    format!("\"{}\"", json_escape(value))
}

fn json_escape(input: &str) -> String {
    input
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\r', "\\r")
        .replace('\n', "\\n")
}

fn parse_status(value: &str) -> Result<TsStatus> {
    match value {
        "written" | "Written" => Ok(TsStatus::Written),
        "user1" | "UserStatus1" => Ok(TsStatus::UserStatus1),
        "deleted" | "Deleted" => Ok(TsStatus::Deleted),
        "user2" | "UserStatus2" => Ok(TsStatus::UserStatus2),
        other => Err(Error::Parse(format!("unknown TS status {other}"))),
    }
}

fn status_name(status: TsStatus) -> &'static str {
    match status {
        TsStatus::Written => "written",
        TsStatus::UserStatus1 => "user1",
        TsStatus::Deleted => "deleted",
        TsStatus::UserStatus2 => "user2",
    }
}

fn c_toolchain_status() -> &'static str {
    if command_exists("gcc")
        || command_exists("clang")
        || command_exists("cl")
        || command_exists("cc")
    {
        "C_TOOLCHAIN_AVAILABLE"
    } else {
        "SKIPPED_LOCAL_NO_C_TOOLCHAIN"
    }
}

fn command_exists(command: &str) -> bool {
    let Some(paths) = std::env::var_os("PATH") else {
        return false;
    };
    for dir in std::env::split_paths(&paths) {
        if dir.join(command).is_file() {
            return true;
        }
        if cfg!(windows) {
            for ext in ["exe", "cmd", "bat"] {
                if dir.join(format!("{command}.{ext}")).is_file() {
                    return true;
                }
            }
        }
    }
    false
}

fn unique_run_id() -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_nanos())
        .unwrap_or(0);
    format!("{}_{}", std::process::id(), nanos)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fixture_parser_reads_operations_and_accepted_differences() {
        let fixture = parse_fixture(
            r#"{
  "name": "unit",
  "operations": [
    {"id":"kv-001","op":"kv.set","key":"a","value":"b"}
  ],
  "accepted_differences": [
    {"id":"layout","reason":"seed","fields":"image"}
  ]
}"#,
        )
        .unwrap();
        assert_eq!(fixture.name, "unit");
        assert_eq!(fixture.operations.len(), 1);
        assert_eq!(fixture.accepted_differences[0].id, "layout");
    }
}

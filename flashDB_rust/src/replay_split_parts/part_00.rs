use crate::config::DEFAULT_FLASH_SIZE;
use crate::flash::{FileFlash, MemoryFlash};
use crate::format::image_hash;
use crate::kvdb::{KvDb, KvEntry};
use crate::tsdb::{TsDb, TsEntry};
use crate::types::{Error, Result, TsStatus};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

const FLASHDB_SOURCE_COMMIT: &str = "93d175549da579b8abac07bd175ce4c3f9dde829";
static NEXT_REPLAY_RUN_ID: AtomicU64 = AtomicU64::new(0);

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
    let mismatch = match compare_reports(&expected, &actual) {
        Ok(value) => value,
        Err(err) => Some(Mismatch {
            byte_offset: 0,
            step_id: "report".to_string(),
            field_path: "report.parse".to_string(),
            expected: err.to_string(),
            actual: "parse failed".to_string(),
        }),
    };
    let passed = mismatch.is_none();
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
    temp_dir: Option<PathBuf>,
}

impl ReplayState {
    fn new(backend: &str, size: usize) -> Result<Self> {
        let size = if size == 0 { DEFAULT_FLASH_SIZE } else { size };
        let unique = unique_run_id();
        let base = std::env::temp_dir().join(format!("flashdb_rust_replay_{unique}"));
        let temp_dir = (backend == "file").then(|| base.clone());
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
        Ok(Self { kv, ts, temp_dir })
    }
}

impl Drop for ReplayState {
    fn drop(&mut self) {
        if let KvReplayDb::File { db, .. } = &mut self.kv {
            drop(db.take());
        }
        if let TsReplayDb::File { db, .. } = &mut self.ts {
            drop(db.take());
        }
        if let Some(temp_dir) = &self.temp_dir {
            let _ = fs::remove_dir_all(temp_dir);
        }
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
                ("ts_status".to_string(), json_string(status_name(status))),
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
        let end = rest.find([',', '}', ']']).unwrap_or(rest.len());
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

#[derive(Debug, Clone)]
struct ParsedStep {
    id: String,
    fields: BTreeMap<String, String>,
}

fn compare_reports(expected: &str, actual: &str) -> Result<Option<Mismatch>> {
    let ignored = ignored_fields(expected, actual);
    let expected_steps = parse_report_steps(expected)?;
    let actual_steps = parse_report_steps(actual)?;
    if expected_steps.len() != actual_steps.len() {
        return Ok(Some(Mismatch {
            byte_offset: 0,
            step_id: "steps".to_string(),
            field_path: "steps.len".to_string(),
            expected: expected_steps.len().to_string(),
            actual: actual_steps.len().to_string(),
        }));
    }

    let actual_by_id: BTreeMap<&str, &ParsedStep> = actual_steps
        .iter()
        .map(|step| (step.id.as_str(), step))
        .collect();
    for expected_step in &expected_steps {
        let Some(actual_step) = actual_by_id.get(expected_step.id.as_str()) else {
            return Ok(Some(Mismatch {
                byte_offset: 0,
                step_id: expected_step.id.clone(),
                field_path: "steps.id".to_string(),
                expected: expected_step.id.clone(),
                actual: "missing".to_string(),
            }));
        };

        let mut fields: Vec<String> = expected_step
            .fields
            .keys()
            .chain(actual_step.fields.keys())
            .filter(|name| !ignored.contains(name))
            .cloned()
            .collect();
        fields.sort();
        fields.dedup();
        for field in fields {
            let expected_value = expected_step.fields.get(&field);
            let actual_value = actual_step.fields.get(&field);
            if expected_value != actual_value {
                return Ok(Some(Mismatch {
                    byte_offset: 0,
                    step_id: expected_step.id.clone(),
                    field_path: format!("steps.{}.{}", expected_step.id, field),
                    expected: expected_value
                        .cloned()
                        .unwrap_or_else(|| "missing".to_string()),
                    actual: actual_value
                        .cloned()
                        .unwrap_or_else(|| "missing".to_string()),
                }));
            }
        }
    }

    Ok(None)
}

fn ignored_fields(left: &str, right: &str) -> Vec<String> {
    let mut out = ACCEPTED_DIFF_FIELD_ALLOWLIST
        .iter()
        .map(|value| (*value).to_string())
        .collect::<Vec<_>>();
    collect_accepted_fields(left, &mut out);
    collect_accepted_fields(right, &mut out);
    out.sort();
    out.dedup();
    out
}

const ACCEPTED_DIFF_FIELD_ALLOWLIST: &[&str] = &[
    "image_hash",
    "message",
    "backend",
    "toolchain_status",
    "source",
    "fixture",
    "fixture_hash",
    "report_path",
];

fn collect_accepted_fields(report: &str, out: &mut Vec<String>) {
    let mut rest = report;
    while let Some(index) = rest.find("\"fields\"") {
        rest = &rest[index + "\"fields\"".len()..];
        let Some(colon) = rest.find(':') else {
            break;
        };
        let value = rest[colon + 1..].trim_start();
        if !value.starts_with('"') {
            continue;
        }
        let value = &value[1..];
        let Some(end) = value.find('"') else {
            break;
        };
        for field in value[..end].split(',') {
            let field = field.trim();
            if ACCEPTED_DIFF_FIELD_ALLOWLIST.contains(&field) {
                out.push(field.to_string());
            }
        }
        rest = &value[end + 1..];
    }
}

fn parse_report_steps(report: &str) -> Result<Vec<ParsedStep>> {
    let array = json_array(report, "steps")
        .ok_or_else(|| Error::Parse("report missing steps array".to_string()))?;
    let objects = top_level_objects(array)?;
    let mut steps = Vec::new();
    for object in objects {
        let fields = top_level_fields(object)?;
        let id = fields
            .get("id")
            .and_then(|value| unquote_json_string(value))
            .ok_or_else(|| Error::Parse("step missing id".to_string()))?;
        steps.push(ParsedStep { id, fields });
    }
    Ok(steps)
}

fn json_array<'a>(input: &'a str, name: &str) -> Option<&'a str> {
    let marker = format!("\"{name}\"");
    let start = input.find(&marker)? + marker.len();
    let after_name = &input[start..];
    let colon = after_name.find(':')?;
    let after_colon = after_name[colon + 1..].trim_start();
    if !after_colon.starts_with('[') {
        return None;
    }
    let offset = input.len() - after_colon.len();
    let end = matching_delimiter(input, offset, '[', ']')?;
    Some(&input[offset + 1..end])
}

fn top_level_objects(input: &str) -> Result<Vec<&str>> {
    let mut out = Vec::new();
    let mut in_string = false;
    let mut escape = false;
    let mut depth = 0usize;
    let mut start = None;
    for (index, ch) in input.char_indices() {
        if in_string {
            if escape {
                escape = false;
            } else if ch == '\\' {
                escape = true;
            } else if ch == '"' {
                in_string = false;
            }
            continue;
        }
        match ch {
            '"' => in_string = true,
            '{' => {
                if depth == 0 {
                    start = Some(index);
                }
                depth += 1;
            }
            '}' => {
                depth = depth
                    .checked_sub(1)
                    .ok_or_else(|| Error::Parse("unbalanced report object".to_string()))?;
                if depth == 0 {
                    let start = start
                        .take()
                        .ok_or_else(|| Error::Parse("missing object start".to_string()))?;
                    out.push(&input[start..=index]);
                }
            }
            _ => {}
        }
    }
    if depth != 0 {
        return Err(Error::Parse("unclosed report object".to_string()));
    }
    Ok(out)
}


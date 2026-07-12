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

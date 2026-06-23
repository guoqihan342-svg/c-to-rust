use crate::config::DEFAULT_FLASH_SIZE;
use crate::flash::{FileFlash, FlashCounters, FlashDevice, MemoryFlash};
use crate::format::{decode_record, encode_record, image_hash, RecordKind};
use crate::kvdb::KvDb;
use crate::replay;
use crate::tsdb::TsDb;
use crate::types::{Error, Result, TsStatus};
use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

#[derive(Debug, Clone)]
struct Options {
    command: String,
    backend: String,
    loops: u64,
    seed: u64,
    scenario: String,
    report: Option<PathBuf>,
    image: Option<PathBuf>,
    fixture: Option<PathBuf>,
    rust_report: Option<PathBuf>,
    oracle_report: Option<PathBuf>,
    size: usize,
}

impl Default for Options {
    fn default() -> Self {
        Self {
            command: "help".to_string(),
            backend: "memory".to_string(),
            loops: 1,
            seed: 1,
            scenario: "all".to_string(),
            report: None,
            image: None,
            fixture: None,
            rust_report: None,
            oracle_report: None,
            size: DEFAULT_FLASH_SIZE,
        }
    }
}

#[derive(Debug, Default)]
struct Report {
    command: String,
    backend: String,
    loops: u64,
    seed: u64,
    scenario: String,
    scenario_counts: BTreeMap<String, u64>,
    duration_ms: u128,
    counters: FlashCounters,
    bytes_processed: u64,
    image_hashes: Vec<String>,
}

pub fn run_from_env() -> Result<String> {
    run(std::env::args().skip(1))
}

pub fn run<I, S>(args: I) -> Result<String>
where
    I: IntoIterator<Item = S>,
    S: Into<String>,
{
    let options = parse_args(args)?;
    match options.command.as_str() {
        "help" | "--help" | "-h" => Ok(help()),
        "smoke" => run_stress(Options {
            command: "smoke".to_string(),
            loops: 1,
            ..options
        }),
        "stress" => run_stress(options),
        "replay" | "fixture-replay" => replay::run_replay(
            options
                .fixture
                .as_deref()
                .ok_or_else(|| Error::Cli("replay requires --fixture".to_string()))?,
            options.report.as_deref(),
            &options.backend,
            options.size,
        ),
        "diff" | "diff-report" => replay::run_diff(
            options
                .rust_report
                .as_deref()
                .ok_or_else(|| Error::Cli("diff requires --rust-report or --actual".to_string()))?,
            options.oracle_report.as_deref().ok_or_else(|| {
                Error::Cli("diff requires --oracle-report or --expected".to_string())
            })?,
            options.report.as_deref(),
        ),
        "inspect-image" => inspect_image(options),
        "unsafe-scan" => unsafe_scan(Path::new("src")),
        other => Err(Error::Cli(format!("unknown command {other}"))),
    }
}

fn parse_args<I, S>(args: I) -> Result<Options>
where
    I: IntoIterator<Item = S>,
    S: Into<String>,
{
    let mut args: Vec<String> = args.into_iter().map(Into::into).collect();
    let mut options = Options::default();
    if args.is_empty() {
        return Ok(options);
    }
    options.command = args.remove(0);
    let mut i = 0;
    while i < args.len() {
        let key = &args[i];
        let value = |i: usize, args: &[String]| -> Result<String> {
            args.get(i + 1)
                .cloned()
                .ok_or_else(|| Error::Cli(format!("missing value for {}", args[i])))
        };
        match key.as_str() {
            "--backend" => {
                options.backend = value(i, &args)?;
                i += 2;
            }
            "--loops" => {
                options.loops = value(i, &args)?
                    .parse()
                    .map_err(|_| Error::Parse("invalid --loops".to_string()))?;
                i += 2;
            }
            "--seed" => {
                options.seed = value(i, &args)?
                    .parse()
                    .map_err(|_| Error::Parse("invalid --seed".to_string()))?;
                i += 2;
            }
            "--scenario" => {
                options.scenario = value(i, &args)?;
                i += 2;
            }
            "--report" => {
                options.report = Some(PathBuf::from(value(i, &args)?));
                i += 2;
            }
            "--path" => {
                options.image = Some(PathBuf::from(value(i, &args)?));
                i += 2;
            }
            "--fixture" => {
                options.fixture = Some(PathBuf::from(value(i, &args)?));
                i += 2;
            }
            "--rust-report" | "--actual" => {
                options.rust_report = Some(PathBuf::from(value(i, &args)?));
                i += 2;
            }
            "--oracle-report" | "--expected" => {
                options.oracle_report = Some(PathBuf::from(value(i, &args)?));
                i += 2;
            }
            "--size" => {
                options.size = value(i, &args)?
                    .parse()
                    .map_err(|_| Error::Parse("invalid --size".to_string()))?;
                i += 2;
            }
            other => return Err(Error::Cli(format!("unknown option {other}"))),
        }
    }
    Ok(options)
}

fn run_stress(options: Options) -> Result<String> {
    if options.loops == 0 {
        return Err(Error::InvalidRange(
            "loops must be greater than zero".to_string(),
        ));
    }
    if options.backend != "memory" && options.backend != "file" {
        return Err(Error::Cli(format!(
            "unsupported backend {}; expected memory or file",
            options.backend
        )));
    }
    let start = Instant::now();
    let mut report = Report {
        command: options.command.clone(),
        backend: options.backend.clone(),
        loops: options.loops,
        seed: options.seed,
        scenario: options.scenario.clone(),
        ..Report::default()
    };
    let mut rng = Lcg::new(options.seed);

    if scenario_enabled(&options, "production") {
        run_production(&options, &mut report, &mut rng)?;
    }
    if scenario_enabled(&options, "abnormal") {
        run_abnormal(&options, &mut report)?;
    }
    if scenario_enabled(&options, "reliability") {
        run_reliability(&options, &mut report)?;
    }

    report.duration_ms = start.elapsed().as_millis();
    let json = report.to_json();
    if let Some(path) = &options.report {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(path, &json)?;
    }
    Ok(json)
}

fn scenario_enabled(options: &Options, name: &str) -> bool {
    options.scenario == "all" || options.scenario == name
}

fn run_production(options: &Options, report: &mut Report, rng: &mut Lcg) -> Result<()> {
    if options.backend == "file" {
        let base = std::env::temp_dir().join(format!(
            "flashdb_rust_production_{}",
            unique_run_id(options.seed)
        ));
        fs::create_dir_all(&base)
            .map_err(|err| Error::Io(format!("create production dir {}: {err}", base.display())))?;
        let kv_path = base.join("kv.img");
        let ts_path = base.join("ts.img");
        let _ = fs::remove_file(&kv_path);
        let _ = fs::remove_file(&ts_path);
        let kv = KvDb::create(FileFlash::create(&kv_path, options.size).map_err(|err| {
            Error::Io(format!(
                "create production kv image {}: {err}",
                kv_path.display()
            ))
        })?)?;
        let ts = TsDb::create(FileFlash::create(&ts_path, options.size).map_err(|err| {
            Error::Io(format!(
                "create production ts image {}: {err}",
                ts_path.display()
            ))
        })?)?;
        run_production_loop(kv, ts, options, report, rng)?;
        let _ = fs::remove_dir_all(base);
        return Ok(());
    }

    let kv = KvDb::create(MemoryFlash::new(options.size))?;
    let ts = TsDb::create(MemoryFlash::new(options.size))?;
    run_production_loop(kv, ts, options, report, rng)
}

fn run_production_loop<KF, TF>(
    mut kv: KvDb<KF>,
    mut ts: TsDb<TF>,
    options: &Options,
    report: &mut Report,
    rng: &mut Lcg,
) -> Result<()>
where
    KF: FlashDevice,
    TF: FlashDevice,
{
    for i in 0..options.loops {
        let key = format!("key-{}", rng.next() % 97);
        let value = format!("value-{i}-{}", rng.next()).into_bytes();
        kv.set(&key, &value)?;
        assert_eq_or_error(kv.get(&key)?, Some(value.clone()), "kv get after set")?;
        if i % 5 == 0 {
            kv.delete(&key)?;
            assert_eq_or_error(kv.get(&key)?, None, "kv get after delete")?;
        }
        if i % 11 == 0 {
            kv.compact()?;
        }

        let ts_id = ts.append(i as i64, &value)?;
        if i % 7 == 0 {
            ts.set_status(ts_id, TsStatus::UserStatus1)?;
        }
        let from = (i as i64).saturating_sub(3);
        let rows = ts.query(from, i as i64);
        if rows.is_empty() {
            return Err(Error::CorruptRecord(
                "TS query unexpectedly empty".to_string(),
            ));
        }
        *report
            .scenario_counts
            .entry("production".to_string())
            .or_insert(0) += 1;
    }
    report.counters = report.counters.add(kv.counters()).add(ts.counters());
    report.bytes_processed += kv.bytes_used()? as u64 + ts.bytes_used()? as u64;
    report.image_hashes.push(kv.image_hash()?);
    report.image_hashes.push(ts.image_hash()?);
    Ok(())
}

fn run_abnormal(options: &Options, report: &mut Report) -> Result<()> {
    let mut kv = KvDb::create(MemoryFlash::new(options.size))?;
    assert!(matches!(kv.set("", b"value"), Err(Error::InvalidKey)));
    assert!(matches!(kv.get("missing")?, None));
    let long_key = "x".repeat(65);
    assert!(matches!(
        kv.set(&long_key, b"value"),
        Err(Error::KeyTooLong { .. })
    ));

    let mut tiny = KvDb::create(MemoryFlash::new(48))?;
    assert!(matches!(
        tiny.set("k", &[7; 96]),
        Err(Error::CapacityExceeded { .. })
    ));

    let encoded = encode_record(RecordKind::KvSet, 0, 0, b"k", b"v")?;
    let mut corrupted = encoded.clone();
    let last = corrupted.len() - 1;
    corrupted[last] ^= 1;
    assert!(matches!(
        decode_record(&corrupted),
        Err(Error::CrcMismatch { .. })
    ));
    assert!(matches!(
        decode_record(&encoded[..encoded.len() - 1]),
        Err(Error::CorruptRecord(_))
    ));

    report
        .scenario_counts
        .insert("abnormal".to_string(), options.loops);
    report.bytes_processed += encoded.len() as u64 + corrupted.len() as u64;
    Ok(())
}

fn run_reliability(options: &Options, report: &mut Report) -> Result<()> {
    let base = std::env::temp_dir().join(format!(
        "flashdb_rust_reliability_{}",
        unique_run_id(options.seed)
    ));
    fs::create_dir_all(&base)
        .map_err(|err| Error::Io(format!("create reliability dir {}: {err}", base.display())))?;
    let kv_path = base.join("kv.img");
    let ts_path = base.join("ts.img");
    let _ = fs::remove_file(&kv_path);
    let _ = fs::remove_file(&ts_path);

    let mut kv = KvDb::create(FileFlash::create(&kv_path, options.size).map_err(|err| {
        Error::Io(format!(
            "create reliability kv image {}: {err}",
            kv_path.display()
        ))
    })?)?;
    let mut ts = TsDb::create(FileFlash::create(&ts_path, options.size).map_err(|err| {
        Error::Io(format!(
            "create reliability ts image {}: {err}",
            ts_path.display()
        ))
    })?)?;
    for i in 0..options.loops {
        let key = format!("persist-{i}");
        kv.set(&key, format!("value-{i}").as_bytes())?;
        if i % 4 == 0 {
            kv.compact()?;
        }
        ts.append(i as i64, format!("payload-{i}").as_bytes())?;
        *report
            .scenario_counts
            .entry("reliability".to_string())
            .or_insert(0) += 1;
    }
    let kv_hash = kv.image_hash()?;
    let ts_hash = ts.image_hash()?;
    drop(kv);
    drop(ts);

    let kv_reopened = KvDb::open(FileFlash::open(&kv_path, options.size).map_err(|err| {
        Error::Io(format!(
            "open reliability kv image {}: {err}",
            kv_path.display()
        ))
    })?)?;
    let ts_reopened = TsDb::open(FileFlash::open(&ts_path, options.size).map_err(|err| {
        Error::Io(format!(
            "open reliability ts image {}: {err}",
            ts_path.display()
        ))
    })?)?;
    if options.loops > 0 {
        let last = options.loops - 1;
        let key = format!("persist-{last}");
        assert_eq_or_error(
            kv_reopened.get(&key)?,
            Some(format!("value-{last}").into_bytes()),
            "reopen kv",
        )?;
        if ts_reopened.query(last as i64, last as i64).is_empty() {
            return Err(Error::CorruptRecord("reopen ts query empty".to_string()));
        }
    }
    report.counters = report
        .counters
        .add(kv_reopened.counters())
        .add(ts_reopened.counters());
    report.image_hashes.push(kv_hash);
    report.image_hashes.push(ts_hash);
    drop(kv_reopened);
    drop(ts_reopened);
    let _ = fs::remove_dir_all(base);
    Ok(())
}

fn inspect_image(options: Options) -> Result<String> {
    let path = options
        .image
        .ok_or_else(|| Error::Cli("inspect-image requires --path".to_string()))?;
    let bytes = fs::read(&path)?;
    Ok(format!(
        "{{\"path\":\"{}\",\"bytes\":{},\"image_hash\":\"{}\"}}",
        escape_json(&path.display().to_string()),
        bytes.len(),
        image_hash(&bytes)
    ))
}

fn unsafe_scan(path: &Path) -> Result<String> {
    let mut findings = Vec::new();
    scan_dir_for_unsafe(path, &mut findings)?;
    if findings.is_empty() {
        Ok("{\"unsafe_blocks\":0,\"unsafe_fns\":0,\"findings\":[]}".to_string())
    } else {
        Err(Error::Cli(format!(
            "unsafe usage found: {}",
            findings.join(", ")
        )))
    }
}

fn scan_dir_for_unsafe(path: &Path, findings: &mut Vec<String>) -> Result<()> {
    if !path.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            scan_dir_for_unsafe(&path, findings)?;
        } else if path.extension().and_then(|v| v.to_str()) == Some("rs") {
            let text = fs::read_to_string(&path)?;
            for (idx, line) in text.lines().enumerate() {
                let trimmed = line.trim_start();
                if trimmed.starts_with("unsafe fn ") || trimmed.starts_with("unsafe {") {
                    findings.push(format!("{}:{}", path.display(), idx + 1));
                }
            }
        }
    }
    Ok(())
}

fn assert_eq_or_error<T>(actual: T, expected: T, context: &str) -> Result<()>
where
    T: std::fmt::Debug + PartialEq,
{
    if actual == expected {
        Ok(())
    } else {
        Err(Error::CorruptRecord(format!(
            "{context}: expected {expected:?}, got {actual:?}"
        )))
    }
}

fn unique_run_id(seed: u64) -> String {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_nanos())
        .unwrap_or(0);
    format!("{}_{}_{}", std::process::id(), seed, nanos)
}

#[derive(Debug, Clone)]
struct Lcg {
    state: u64,
}

impl Lcg {
    fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    fn next(&mut self) -> u64 {
        self.state = self
            .state
            .wrapping_mul(6364136223846793005)
            .wrapping_add(1442695040888963407);
        self.state
    }
}

impl Report {
    fn to_json(&self) -> String {
        let scenarios = self
            .scenario_counts
            .iter()
            .map(|(name, count)| format!("\"{}\":{}", escape_json(name), count))
            .collect::<Vec<_>>()
            .join(",");
        let hashes = self
            .image_hashes
            .iter()
            .map(|hash| format!("\"{}\"", escape_json(hash)))
            .collect::<Vec<_>>()
            .join(",");
        format!(
            concat!(
                "{{",
                "\"command\":\"{}\",",
                "\"backend\":\"{}\",",
                "\"loops\":{},",
                "\"seed\":{},",
                "\"scenario\":\"{}\",",
                "\"scenario_counts\":{{{}}},",
                "\"duration_ms\":{},",
                "\"counters\":{{",
                "\"read_ops\":{},\"write_ops\":{},\"erase_ops\":{},\"flush_ops\":{},",
                "\"bytes_read\":{},\"bytes_written\":{},\"bytes_erased\":{}",
                "}},",
                "\"bytes_processed\":{},",
                "\"image_hashes\":[{}]",
                "}}"
            ),
            escape_json(&self.command),
            escape_json(&self.backend),
            self.loops,
            self.seed,
            escape_json(&self.scenario),
            scenarios,
            self.duration_ms,
            self.counters.read_ops,
            self.counters.write_ops,
            self.counters.erase_ops,
            self.counters.flush_ops,
            self.counters.bytes_read,
            self.counters.bytes_written,
            self.counters.bytes_erased,
            self.bytes_processed,
            hashes
        )
    }
}

fn escape_json(input: &str) -> String {
    input
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
}

fn help() -> String {
    [
        "flashdb-rust commands:",
        "  smoke [--backend memory|file] [--report path]",
        "  stress --loops N [--seed N] [--backend memory|file] [--scenario all|production|abnormal|reliability] [--report path]",
        "  replay --fixture file [--backend memory|file] [--report path]",
        "  diff --rust-report file --oracle-report file [--report path]",
        "  fixture-replay --fixture file [--report path]  # CI-compatible alias",
        "  diff-report --actual file --expected file [--report path]  # CI-compatible alias",
        "  inspect-image --path file",
        "  unsafe-scan",
        "",
        "Long run example:",
        "  cargo run --release -- stress --loops 10000 --seed 1 --backend file --scenario all --report target/verification/stress-10000.json",
    ]
    .join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stress_report_contains_counts() {
        let out = run(["stress", "--loops", "3", "--seed", "9"]).unwrap();
        assert!(out.contains("\"loops\":3"));
        assert!(out.contains("\"production\":3"));
        assert!(out.contains("\"abnormal\":3"));
        assert!(out.contains("\"reliability\":3"));
    }

    #[test]
    fn inspect_image_reports_hash() {
        let path = std::env::temp_dir().join("flashdb_rust_cli_inspect.img");
        fs::write(&path, [1u8, 2, 3]).unwrap();
        let out = run([
            "inspect-image".to_string(),
            "--path".to_string(),
            path.display().to_string(),
        ])
        .unwrap();
        assert!(out.contains("\"bytes\":3"));
        assert!(out.contains("\"image_hash\""));
        let _ = fs::remove_file(path);
    }
}

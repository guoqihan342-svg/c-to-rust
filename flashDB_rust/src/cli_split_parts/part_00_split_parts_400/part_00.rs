use crate::config::DEFAULT_FLASH_SIZE;
use crate::flash::{FileFlash, FlashCounters, FlashDevice, MemoryFlash};
use crate::format::{decode_record, encode_record, image_hash, RecordKind};
use crate::kvdb::KvDb;
use crate::replay;
use crate::tsdb::TsDb;
use crate::types::{Error, Result, TsStatus};
use std::collections::BTreeMap;
use std::fs;
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::time::{Instant, SystemTime, UNIX_EPOCH};

const EVIDENCE_SEARCH_MAX_DEPTH: usize = 32;
const EVIDENCE_SEARCH_MAX_FILES: usize = 100_000;
const EVIDENCE_SEARCH_MAX_LIMIT: usize = 10_000;
const EVIDENCE_SNIPPET_MAX_CHARS: usize = 160;

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
    evidence_dir: Option<PathBuf>,
    query: Option<String>,
    limit: usize,
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
            evidence_dir: None,
            query: None,
            limit: 100,
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
        "unsafe-scan" => unsafe_scan(Path::new("src"), options.report.as_deref()),
        "version-manifest" => version_manifest(options.report.as_deref()),
        "evidence-search" => evidence_search(options),
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
            "--evidence-dir" => {
                options.evidence_dir = Some(PathBuf::from(value(i, &args)?));
                i += 2;
            }
            "--query" => {
                options.query = Some(value(i, &args)?);
                i += 2;
            }
            "--limit" => {
                options.limit = value(i, &args)?
                    .parse()
                    .map_err(|_| Error::Parse("invalid --limit".to_string()))?;
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

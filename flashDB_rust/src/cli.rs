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
        "unsafe-scan" => unsafe_scan(Path::new("src")),
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

fn version_manifest(report_path: Option<&Path>) -> Result<String> {
    let cargo_lock_hash = file_sha256(&manifest_path("Cargo.lock"))?;
    let cargo_toml_hash = file_sha256(&manifest_path("Cargo.toml"))?;
    let rustc_version = command_version("rustc", &["--version"]);
    let cargo_version = command_version("cargo", &["--version"]);
    let git_version = command_version("git", &["--version"]);
    let openspec_version = command_version_any(&["openspec", "openspec.cmd"], &["--version"]);
    let branch = command_version("git", &["branch", "--show-current"]);
    let repo_commit = command_version("git", &["rev-parse", "HEAD"]);
    let json = format!(
        concat!(
            "{{",
            "\"command\":\"version-manifest\",",
            "\"schema_version\":1,",
            "\"agent_contract_version\":\"0.1.0\",",
            "\"context_schema_version\":\"0.1.0\",",
            "\"patch_plan_schema_version\":\"0.1.0\",",
            "\"fixture_schema_version\":1,",
            "\"evidence_schema_version\":1,",
            "\"package_name\":\"{}\",",
            "\"package_version\":\"{}\",",
            "\"edition\":\"2021\",",
            "\"cargo_toml_sha256\":\"{}\",",
            "\"cargo_lock_sha256\":\"{}\",",
            "\"rustc_version\":\"{}\",",
            "\"cargo_version\":\"{}\",",
            "\"git_version\":\"{}\",",
            "\"openspec_version\":\"{}\",",
            "\"rust_toolchain_file\":null,",
            "\"host_os\":\"{}\",",
            "\"workspace_branch\":\"{}\",",
            "\"workspace_commit\":\"{}\",",
            "\"flashdb_source_clone_url\":\"https://gitcode.com/xwxf/FlashDB.git\",",
            "\"flashdb_source_commit\":\"93d175549da579b8abac07bd175ce4c3f9dde829\",",
            "\"flashdb_source_tag\":null,",
            "\"flashdb_feature_matrix\":{{",
            "\"FDB_USING_KVDB\":true,",
            "\"FDB_USING_TSDB\":true,",
            "\"FDB_USING_FILE_POSIX_MODE\":true,",
            "\"FDB_WRITE_GRAN\":1",
            "}},",
            "\"cache_key_inputs\":[",
            "\"agent_contract_version\",",
            "\"context_schema_version\",",
            "\"patch_plan_schema_version\",",
            "\"fixture_schema_version\",",
            "\"evidence_schema_version\",",
            "\"package_version\",",
            "\"cargo_toml_sha256\",",
            "\"cargo_lock_sha256\",",
            "\"rustc_version\",",
            "\"cargo_version\",",
            "\"openspec_version\",",
            "\"flashdb_source_commit\",",
            "\"flashdb_feature_matrix\",",
            "\"command_arguments\",",
            "\"fixture_sha256\",",
            "\"ai_metadata\"",
            "]",
            "}}"
        ),
        escape_json(env!("CARGO_PKG_NAME")),
        escape_json(env!("CARGO_PKG_VERSION")),
        cargo_toml_hash,
        cargo_lock_hash,
        escape_json(&rustc_version),
        escape_json(&cargo_version),
        escape_json(&git_version),
        escape_json(&openspec_version),
        escape_json(std::env::consts::OS),
        escape_json(&branch),
        escape_json(&repo_commit)
    );
    if let Some(path) = report_path {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(path, &json)?;
    }
    Ok(json)
}

fn evidence_search(options: Options) -> Result<String> {
    let evidence_dir = options
        .evidence_dir
        .ok_or_else(|| Error::Cli("evidence-search requires --evidence-dir".to_string()))?;
    let query = options
        .query
        .ok_or_else(|| Error::Cli("evidence-search requires --query".to_string()))?;
    if query.is_empty() {
        return Err(Error::Cli(
            "evidence-search requires non-empty --query".to_string(),
        ));
    }
    if options.limit == 0 || options.limit > EVIDENCE_SEARCH_MAX_LIMIT {
        return Err(Error::Cli(format!(
            "evidence-search --limit must be between 1 and {EVIDENCE_SEARCH_MAX_LIMIT}"
        )));
    }
    let mut files = Vec::new();
    collect_evidence_files(&evidence_dir, &mut files)?;
    files.sort();

    let mut matches = Vec::new();
    for file in files {
        if options
            .report
            .as_deref()
            .is_some_and(|report_path| same_path(&file, report_path))
        {
            continue;
        }
        if matches.len() >= options.limit {
            break;
        }
        let relative = evidence_relative_path(&evidence_dir, &file);
        let file_handle = fs::File::open(&file)?;
        let mut reader = BufReader::new(file_handle);
        let mut line = Vec::new();
        let mut line_number = 0usize;
        loop {
            line.clear();
            let bytes_read = reader.read_until(b'\n', &mut line)?;
            if bytes_read == 0 {
                break;
            }
            line_number += 1;
            let line_text = String::from_utf8_lossy(&line);
            if line_text.contains(&query) {
                matches.push(EvidenceMatch {
                    path: relative.clone(),
                    line: line_number,
                    snippet: evidence_snippet(&line_text),
                });
                if matches.len() >= options.limit {
                    break;
                }
            }
        }
    }

    let matches_json = matches
        .iter()
        .map(|item| {
            format!(
                "{{\"path\":\"{}\",\"line\":{},\"snippet\":\"{}\"}}",
                escape_json(&item.path),
                item.line,
                escape_json(&item.snippet)
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    let json = format!(
        concat!(
            "{{",
            "\"command\":\"evidence-search\",",
            "\"schema_version\":1,",
            "\"evidence_dir\":\"{}\",",
            "\"query\":\"{}\",",
            "\"limit\":{},",
            "\"match_count\":{},",
            "\"matches\":[{}]",
            "}}"
        ),
        escape_json(&evidence_dir.display().to_string()),
        escape_json(&query),
        options.limit,
        matches.len(),
        matches_json
    );
    if let Some(path) = &options.report {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(path, &json)?;
    }
    Ok(json)
}

#[derive(Debug)]
struct EvidenceMatch {
    path: String,
    line: usize,
    snippet: String,
}

fn collect_evidence_files(path: &Path, files: &mut Vec<PathBuf>) -> Result<()> {
    if !path.exists() {
        return Err(Error::Cli(format!(
            "evidence-search directory does not exist: {}",
            path.display()
        )));
    }
    collect_evidence_files_at(path, files, 0)
}

fn collect_evidence_files_at(path: &Path, files: &mut Vec<PathBuf>, depth: usize) -> Result<()> {
    if depth > EVIDENCE_SEARCH_MAX_DEPTH {
        return Err(Error::Cli(format!(
            "evidence-search directory depth exceeds {EVIDENCE_SEARCH_MAX_DEPTH}: {}",
            path.display()
        )));
    }
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        let entry_path = entry.path();
        let metadata = fs::symlink_metadata(&entry_path)?;
        if metadata.file_type().is_symlink() {
            continue;
        }
        if metadata.is_dir() {
            collect_evidence_files_at(&entry_path, files, depth + 1)?;
        } else if metadata.is_file() && is_supported_evidence_file(&entry_path) {
            if files.len() >= EVIDENCE_SEARCH_MAX_FILES {
                return Err(Error::Cli(format!(
                    "evidence-search file count exceeds {EVIDENCE_SEARCH_MAX_FILES}"
                )));
            }
            files.push(entry_path);
        }
    }
    Ok(())
}

fn is_supported_evidence_file(path: &Path) -> bool {
    matches!(
        path.extension()
            .and_then(|value| value.to_str())
            .map(|value| value.to_ascii_lowercase()),
        Some(ext) if ext == "json" || ext == "jsonl" || ext == "log" || ext == "md"
    )
}

fn evidence_relative_path(base: &Path, path: &Path) -> String {
    path.strip_prefix(base)
        .unwrap_or(path)
        .display()
        .to_string()
        .replace('\\', "/")
}

fn same_path(left: &Path, right: &Path) -> bool {
    if left == right {
        return true;
    }
    match (fs::canonicalize(left), fs::canonicalize(right)) {
        (Ok(left), Ok(right)) => left == right,
        _ => false,
    }
}

fn evidence_snippet(line: &str) -> String {
    let trimmed = line.trim();
    if trimmed.chars().count() <= EVIDENCE_SNIPPET_MAX_CHARS {
        return trimmed.to_string();
    }
    let mut snippet = trimmed
        .chars()
        .take(EVIDENCE_SNIPPET_MAX_CHARS)
        .collect::<String>();
    snippet.push_str("...");
    snippet
}

fn manifest_path(name: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR")).join(name)
}

fn command_version_any(commands: &[&str], args: &[&str]) -> String {
    commands
        .iter()
        .map(|command| command_version(command, args))
        .find(|version| version != "NOT_FOUND")
        .unwrap_or_else(|| "NOT_FOUND".to_string())
}

fn command_version(command: &str, args: &[&str]) -> String {
    std::process::Command::new(command)
        .args(args)
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "NOT_FOUND".to_string())
}

fn file_sha256(path: &Path) -> Result<String> {
    let path_text = path.to_str().unwrap_or_default();
    if let Some(hash) = std::process::Command::new("sha256sum")
        .arg(path_text)
        .output()
        .ok()
        .filter(|output| output.status.success())
        .map(|output| String::from_utf8_lossy(&output.stdout).into_owned())
        .and_then(|value| value.split_whitespace().next().map(str::to_string))
        .filter(|value| is_sha256_hex(value))
    {
        return Ok(hash.to_ascii_lowercase());
    }
    if let Some(hash) = std::process::Command::new("certutil")
        .args(["-hashfile", path_text, "SHA256"])
        .output()
        .ok()
        .filter(|output| output.status.success())
        .map(|output| String::from_utf8_lossy(&output.stdout).into_owned())
        .and_then(|value| {
            value
                .lines()
                .map(str::trim)
                .find(|line| is_sha256_hex(line))
                .map(str::to_string)
        })
    {
        return Ok(hash.to_ascii_lowercase());
    }
    Ok("NOT_FOUND".to_string())
}

fn is_sha256_hex(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|byte| byte.is_ascii_hexdigit())
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
    let mut escaped = String::with_capacity(input.len());
    for ch in input.chars() {
        match ch {
            '\\' => escaped.push_str("\\\\"),
            '"' => escaped.push_str("\\\""),
            '\u{08}' => escaped.push_str("\\b"),
            '\u{0c}' => escaped.push_str("\\f"),
            '\n' => escaped.push_str("\\n"),
            '\r' => escaped.push_str("\\r"),
            '\t' => escaped.push_str("\\t"),
            ch if ch <= '\u{1f}' => escaped.push_str(&format!("\\u{:04x}", ch as u32)),
            ch => escaped.push(ch),
        }
    }
    escaped
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
        "  version-manifest [--report path]",
        "  evidence-search --evidence-dir dir --query text [--limit 1..10000] [--report path]",
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

    #[test]
    fn evidence_search_finds_supported_text_matches() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_{}",
            unique_run_id(101)
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(
            dir.join("summary.json"),
            "{\"status\":\"passed\"}\n{\"slice_id\":\"tsdb-user2-status\"}\n",
        )
        .unwrap();
        fs::write(dir.join("trace.log"), "first line\nstatus passed\n").unwrap();
        fs::write(dir.join("ignored.bin"), "status passed\n").unwrap();

        let out = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
            "--query".to_string(),
            "passed".to_string(),
        ])
        .unwrap();

        assert!(out.contains("\"command\":\"evidence-search\""));
        assert!(out.contains("\"schema_version\":1"));
        assert!(out.contains("\"match_count\":2"));
        assert!(out.contains("\"path\":\"summary.json\""));
        assert!(out.contains("\"path\":\"trace.log\""));
        assert!(out.contains("\"line\":1"));
        assert!(out.contains("\"line\":2"));
        assert!(out.contains("\"snippet\":\"{\\\"status\\\":\\\"passed\\\"}\""));
        assert!(!out.contains("ignored.bin"));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn evidence_search_honors_limit_and_supported_extensions() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_limit_{}",
            unique_run_id(102)
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("a.jsonl"), "{\"status\":\"failed\"}\n").unwrap();
        fs::write(dir.join("b.md"), "status failed\n").unwrap();
        fs::write(dir.join("c.bin"), "status failed\n").unwrap();

        let out = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
            "--query".to_string(),
            "failed".to_string(),
            "--limit".to_string(),
            "1".to_string(),
        ])
        .unwrap();

        assert!(out.contains("\"limit\":1"));
        assert!(out.contains("\"match_count\":1"));
        assert!(out.contains("\"path\":\"a.jsonl\""));
        assert!(!out.contains("\"path\":\"b.md\""));
        assert!(!out.contains("c.bin"));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn evidence_search_requires_query() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_missing_query_{}",
            unique_run_id(103)
        ));
        fs::create_dir_all(&dir).unwrap();

        let err = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
        ])
        .unwrap_err();

        assert_eq!(
            err,
            Error::Cli("evidence-search requires --query".to_string())
        );

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn evidence_search_rejects_empty_query() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_empty_query_{}",
            unique_run_id(104)
        ));
        fs::create_dir_all(&dir).unwrap();

        let err = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
            "--query".to_string(),
            "".to_string(),
        ])
        .unwrap_err();

        assert_eq!(
            err,
            Error::Cli("evidence-search requires non-empty --query".to_string())
        );

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn evidence_search_rejects_invalid_limits() {
        for (seed, limit) in [(105, "0"), (106, "10001")] {
            let dir = std::env::temp_dir().join(format!(
                "flashdb_rust_evidence_search_limit_bounds_{}",
                unique_run_id(seed)
            ));
            fs::create_dir_all(&dir).unwrap();

            let err = run([
                "evidence-search".to_string(),
                "--evidence-dir".to_string(),
                dir.display().to_string(),
                "--query".to_string(),
                "passed".to_string(),
                "--limit".to_string(),
                limit.to_string(),
            ])
            .unwrap_err();

            assert_eq!(
                err,
                Error::Cli("evidence-search --limit must be between 1 and 10000".to_string())
            );

            let _ = fs::remove_dir_all(dir);
        }
    }

    #[test]
    fn evidence_search_tolerates_non_utf8_text_evidence() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_non_utf8_{}",
            unique_run_id(107)
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("a-bad.log"), [0xff, b'\n']).unwrap();
        fs::write(dir.join("z-good.json"), "{\"status\":\"passed\"}\n").unwrap();

        let out = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
            "--query".to_string(),
            "passed".to_string(),
        ])
        .unwrap();

        assert!(out.contains("\"match_count\":1"));
        assert!(out.contains("\"path\":\"z-good.json\""));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn evidence_search_bounds_long_snippets() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_long_snippet_{}",
            unique_run_id(108)
        ));
        fs::create_dir_all(&dir).unwrap();
        let long_value = "x".repeat(320);
        fs::write(
            dir.join("long.json"),
            format!("{{\"status\":\"passed\",\"payload\":\"{long_value}\"}}\n"),
        )
        .unwrap();

        let out = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
            "--query".to_string(),
            "passed".to_string(),
        ])
        .unwrap();

        assert!(out.contains("\"snippet\":\"{\\\"status\\\":\\\"passed\\\""));
        assert!(out.contains("..."));
        assert!(!out.contains(&long_value));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn evidence_search_excludes_report_path_from_matches() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_report_exclusion_{}",
            unique_run_id(109)
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("source.json"), "{\"status\":\"passed\"}\n").unwrap();
        let report = dir.join("evidence-search-report.json");
        fs::write(&report, "{\"old_query\":\"passed\"}\n").unwrap();

        let out = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
            "--query".to_string(),
            "passed".to_string(),
            "--report".to_string(),
            report.display().to_string(),
        ])
        .unwrap();

        assert!(out.contains("\"match_count\":1"));
        assert!(out.contains("\"path\":\"source.json\""));
        assert!(!out.contains("\"path\":\"evidence-search-report.json\""));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn evidence_search_escapes_json_control_characters() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_json_escape_{}",
            unique_run_id(110)
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("control.log"), "status\tpassed\u{1}\n").unwrap();

        let out = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
            "--query".to_string(),
            "\tpassed".to_string(),
        ])
        .unwrap();

        assert!(out.contains("\"query\":\"\\tpassed\""));
        assert!(out.contains("\"snippet\":\"status\\tpassed\\u0001\""));
        assert!(!out.contains('\t'));
        assert!(!out.contains('\u{1}'));

        let _ = fs::remove_dir_all(dir);
    }
}

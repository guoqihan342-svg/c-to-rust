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
    report.counters = report
        .counters
        .combined_with(kv.counters())
        .combined_with(ts.counters());
    report.bytes_processed += kv.bytes_used()? as u64 + ts.bytes_used()? as u64;
    report.image_hashes.push(kv.image_hash()?);
    report.image_hashes.push(ts.image_hash()?);
    Ok(())
}

fn run_abnormal(options: &Options, report: &mut Report) -> Result<()> {
    let mut kv = KvDb::create(MemoryFlash::new(options.size))?;
    assert!(matches!(kv.set("", b"value"), Err(Error::InvalidKey)));
    assert!(kv.get("missing")?.is_none());
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
        .combined_with(kv_reopened.counters())
        .combined_with(ts_reopened.counters());
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
            "\"command_arguments\":[\"version-manifest\"],",
            "\"fixture_sha256\":null,",
            "\"ai_metadata\":{{\"used\":false,\"provider\":\"not_configured\"}},",
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

#[derive(Debug, Clone)]
struct UnsafeFinding {
    path: String,
    line: usize,
    category: String,
    text: String,
}


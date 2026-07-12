fn version_manifest(report_path: Option<&Path>) -> Result<String> {
    let cargo_lock_hash = file_sha256(&manifest_path("Cargo.lock"))?;
    let cargo_toml_hash = file_sha256(&manifest_path("Cargo.toml"))?;
    let rustc_version = command_version("rustc", &["--version"]);
    let cargo_version = command_version("cargo", &["--version"]);
    let git_version = command_version("git", &["--version"]);
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

#[derive(Debug, Clone)]
struct UnsafeFinding {
    path: String,
    line: usize,
    category: String,
    text: String,
}

fn unsafe_scan(path: &Path, report_path: Option<&Path>) -> Result<String> {
    let mut findings = Vec::new();
    let mut scanned_files = 0usize;
    let mut scanned_lines = 0usize;
    scan_dir_for_unsafe(path, &mut findings, &mut scanned_files, &mut scanned_lines)?;
    let categories = unsafe_category_counts(&findings);
    let unsafe_count = findings.len();
    let unsafe_ratio = if scanned_lines == 0 {
        0.0
    } else {
        unsafe_count as f64 / scanned_lines as f64
    };
    let status = if findings.is_empty() {
        "passed"
    } else {
        "failed"
    };
    let findings_json = findings
        .iter()
        .map(|finding| {
            format!(
                concat!(
                    "{{",
                    "\"path\":\"{}\",",
                    "\"line\":{},",
                    "\"category\":\"{}\",",
                    "\"text\":\"{}\"",
                    "}}"
                ),
                escape_json(&finding.path),
                finding.line,
                escape_json(&finding.category),
                escape_json(&finding.text)
            )
        })
        .collect::<Vec<_>>()
        .join(",");
    let json = format!(
        concat!(
            "{{",
            "\"command\":\"unsafe-scan\",",
            "\"schema_version\":1,",
            "\"status\":\"{}\",",
            "\"scope\":\"first-party non-test Rust source under flashDB_rust/src\",",
            "\"scanned_files\":{},",
            "\"scanned_lines\":{},",
            "\"ignored_paths\":[],",
            "\"first_party_non_test_unsafe_count\":{},",
            "\"unsafe_ratio\":{},",
            "\"categories\":{{",
            "\"unsafe_function\":{},",
            "\"unsafe_block\":{},",
            "\"unsafe_impl\":{},",
            "\"extern_c\":{},",
            "\"repr_c\":{},",
            "\"transmute\":{},",
            "\"raw_pointer\":{}",
            "}},",
            "\"findings\":[{}]",
            "}}"
        ),
        status,
        scanned_files,
        scanned_lines,
        unsafe_count,
        format_ratio(unsafe_ratio),
        categories.get("unsafe_function").copied().unwrap_or(0),
        categories.get("unsafe_block").copied().unwrap_or(0),
        categories.get("unsafe_impl").copied().unwrap_or(0),
        categories.get("extern_c").copied().unwrap_or(0),
        categories.get("repr_c").copied().unwrap_or(0),
        categories.get("transmute").copied().unwrap_or(0),
        categories.get("raw_pointer").copied().unwrap_or(0),
        findings_json
    );
    if let Some(path) = report_path {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent)?;
        }
        fs::write(path, &json)?;
    }
    if findings.is_empty() {
        Ok(json)
    } else {
        Err(Error::Cli(format!(
            "unsafe usage found: {}",
            findings
                .iter()
                .map(|finding| format!("{}:{}:{}", finding.path, finding.line, finding.category))
                .collect::<Vec<_>>()
                .join(", ")
        )))
    }
}

fn scan_dir_for_unsafe(
    path: &Path,
    findings: &mut Vec<UnsafeFinding>,
    scanned_files: &mut usize,
    scanned_lines: &mut usize,
) -> Result<()> {
    if !path.exists() {
        return Ok(());
    }
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        let path = entry.path();
        if path.is_dir() {
            scan_dir_for_unsafe(&path, findings, scanned_files, scanned_lines)?;
        } else if path.extension().and_then(|v| v.to_str()) == Some("rs") {
            *scanned_files += 1;
            let text = fs::read_to_string(&path)?;
            for (idx, line) in text.lines().enumerate() {
                *scanned_lines += 1;
                findings.extend(unsafe_findings_in_line(&path, idx + 1, line));
            }
        }
    }
    Ok(())
}

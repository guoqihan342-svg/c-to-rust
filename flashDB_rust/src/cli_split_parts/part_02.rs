fn unsafe_findings_in_line(path: &Path, line_no: usize, line: &str) -> Vec<UnsafeFinding> {
    let code = strip_strings_and_line_comments(line);
    let raw_without_comment = strip_line_comment(line);
    let mut findings = Vec::new();
    let mut add = |category: &str| {
        findings.push(UnsafeFinding {
            path: path.display().to_string().replace('\\', "/"),
            line: line_no,
            category: category.to_string(),
            text: line.trim().to_string(),
        });
    };

    if has_ordered_tokens(&code, &["unsafe", "fn"]) {
        add("unsafe_function");
    }
    if has_ordered_tokens(&code, &["unsafe", "impl"]) {
        add("unsafe_impl");
    }
    if code.contains("unsafe {") || code.contains("unsafe{") {
        add("unsafe_block");
    }
    if has_token(&code, "extern")
        && (raw_without_comment.contains("\"C\"") || raw_without_comment.contains("\"cdecl\""))
    {
        add("extern_c");
    }
    if code.contains("repr(C)") || code.contains("repr( C )") || code.contains("repr(C,") {
        add("repr_c");
    }
    if has_token(&code, "transmute") {
        add("transmute");
    }
    if code.contains("*mut ")
        || code.contains("*const ")
        || code.contains("as *mut")
        || code.contains("as *const")
    {
        add("raw_pointer");
    }

    findings
}

fn has_ordered_tokens(code: &str, expected: &[&str]) -> bool {
    let mut index = 0usize;
    for token in code.split(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_')) {
        if token == expected[index] {
            index += 1;
            if index == expected.len() {
                return true;
            }
        }
    }
    false
}

fn has_token(code: &str, expected: &str) -> bool {
    code.split(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_'))
        .any(|token| token == expected)
}

fn strip_line_comment(line: &str) -> String {
    line.split_once("//")
        .map(|(left, _)| left)
        .unwrap_or(line)
        .to_string()
}

fn strip_strings_and_line_comments(line: &str) -> String {
    let mut out = String::with_capacity(line.len());
    let mut chars = line.chars().peekable();
    let mut in_string = false;
    let mut in_char = false;
    let mut escaped = false;

    while let Some(ch) = chars.next() {
        if !in_string && !in_char && ch == '/' && chars.peek() == Some(&'/') {
            break;
        }

        if in_string {
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == '"' {
                in_string = false;
            }
            out.push(' ');
            continue;
        }

        if in_char {
            if escaped {
                escaped = false;
            } else if ch == '\\' {
                escaped = true;
            } else if ch == '\'' {
                in_char = false;
            }
            out.push(' ');
            continue;
        }

        if ch == '"' {
            in_string = true;
            out.push(' ');
        } else if ch == '\'' {
            in_char = true;
            out.push(' ');
        } else {
            out.push(ch);
        }
    }

    out
}

fn unsafe_category_counts(findings: &[UnsafeFinding]) -> BTreeMap<&'static str, usize> {
    let mut counts = BTreeMap::from([
        ("unsafe_function", 0),
        ("unsafe_block", 0),
        ("unsafe_impl", 0),
        ("extern_c", 0),
        ("repr_c", 0),
        ("transmute", 0),
        ("raw_pointer", 0),
    ]);
    for finding in findings {
        if let Some(value) = counts.get_mut(finding.category.as_str()) {
            *value += 1;
        }
    }
    counts
}

fn format_ratio(value: f64) -> String {
    if value == 0.0 {
        "0".to_string()
    } else {
        format!("{value:.6}")
    }
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
    ]
    .join("\n")
}

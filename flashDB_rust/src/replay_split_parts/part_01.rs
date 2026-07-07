fn top_level_fields(object: &str) -> Result<BTreeMap<String, String>> {
    let inner = object
        .strip_prefix('{')
        .and_then(|value| value.strip_suffix('}'))
        .ok_or_else(|| Error::Parse("step object must be braced".to_string()))?;
    let mut fields = BTreeMap::new();
    let bytes = inner.as_bytes();
    let mut index = 0usize;
    while index < inner.len() {
        skip_ws_and_commas(inner, &mut index);
        if index >= inner.len() {
            break;
        }
        if bytes[index] != b'"' {
            return Err(Error::Parse("expected object field name".to_string()));
        }
        let (name, after_name) = read_json_string(inner, index)?;
        index = after_name;
        skip_ws(inner, &mut index);
        if index >= inner.len() || bytes[index] != b':' {
            return Err(Error::Parse(format!("field {name} missing colon")));
        }
        index += 1;
        skip_ws(inner, &mut index);
        let (raw, after_value) = read_json_value(inner, index)?;
        fields.insert(name, raw.trim().to_string());
        index = after_value;
    }
    Ok(fields)
}

fn read_json_value(input: &str, start: usize) -> Result<(&str, usize)> {
    let bytes = input.as_bytes();
    if start >= input.len() {
        return Err(Error::Parse("missing json value".to_string()));
    }
    match bytes[start] {
        b'"' => {
            let (_, end) = read_json_string(input, start)?;
            Ok((&input[start..end], end))
        }
        b'[' => {
            let end = matching_delimiter(input, start, '[', ']')
                .ok_or_else(|| Error::Parse("unclosed array value".to_string()))?;
            Ok((&input[start..=end], end + 1))
        }
        b'{' => {
            let end = matching_delimiter(input, start, '{', '}')
                .ok_or_else(|| Error::Parse("unclosed object value".to_string()))?;
            Ok((&input[start..=end], end + 1))
        }
        _ => {
            let end = input[start..]
                .find(',')
                .map(|value| start + value)
                .unwrap_or(input.len());
            Ok((&input[start..end], end))
        }
    }
}

fn matching_delimiter(input: &str, start: usize, open: char, close: char) -> Option<usize> {
    let mut in_string = false;
    let mut escape = false;
    let mut depth = 0usize;
    for (index, ch) in input[start..].char_indices() {
        let absolute = start + index;
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
        if ch == '"' {
            in_string = true;
        } else if ch == open {
            depth += 1;
        } else if ch == close {
            depth = depth.checked_sub(1)?;
            if depth == 0 {
                return Some(absolute);
            }
        }
    }
    None
}

fn read_json_string(input: &str, start: usize) -> Result<(String, usize)> {
    let bytes = input.as_bytes();
    if bytes.get(start) != Some(&b'"') {
        return Err(Error::Parse("expected string".to_string()));
    }
    let mut out = String::new();
    let mut index = start + 1;
    let mut escape = false;
    while index < input.len() {
        let ch = input[index..]
            .chars()
            .next()
            .ok_or_else(|| Error::Parse("invalid string".to_string()))?;
        index += ch.len_utf8();
        if escape {
            out.push(match ch {
                'n' => '\n',
                'r' => '\r',
                't' => '\t',
                '"' => '"',
                '\\' => '\\',
                other => other,
            });
            escape = false;
        } else if ch == '\\' {
            escape = true;
        } else if ch == '"' {
            return Ok((out, index));
        } else {
            out.push(ch);
        }
    }
    Err(Error::Parse("unterminated string".to_string()))
}

fn unquote_json_string(value: &str) -> Option<String> {
    if !value.starts_with('"') {
        return None;
    }
    read_json_string(value, 0).ok().map(|(value, _)| value)
}

fn skip_ws(input: &str, index: &mut usize) {
    while *index < input.len() && input.as_bytes()[*index].is_ascii_whitespace() {
        *index += 1;
    }
}

fn skip_ws_and_commas(input: &str, index: &mut usize) {
    while *index < input.len() {
        let ch = input.as_bytes()[*index];
        if ch.is_ascii_whitespace() || ch == b',' {
            *index += 1;
        } else {
            break;
        }
    }
}

fn replay_report_json(
    fixture: &Fixture,
    fixture_path: &Path,
    fixture_hash: &str,
    backend: &str,
    steps: &[StepReport],
    toolchain_status: &str,
) -> String {
    let l3_metadata = l3_report_metadata_json(&fixture.name);
    format!(
        concat!(
            "{{",
            "\"command\":\"replay\",",
            "\"schema_version\":1,",
            "{}",
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
        l3_metadata,
        json_escape(&fixture_path.display().to_string()),
        json_escape(&fixture.name),
        json_escape(fixture_hash),
        json_escape(backend),
        json_escape(toolchain_status),
        accepted_differences_json(&fixture.accepted_differences),
        steps_json(steps)
    )
}

fn l3_report_metadata_json(fixture_name: &str) -> String {
    let Some(slice_id) = fixture_name.strip_prefix("l3-") else {
        return String::new();
    };
    format!(
        concat!(
            "\"level\":\"L3\",",
            "\"target_id\":\"flashdb\",",
            "\"slice_id\":\"{}\",",
            "\"source\":{{",
            "\"clone_url\":\"https://gitcode.com/xwxf/FlashDB.git\",",
            "\"commit\":\"{}\"",
            "}},"
        ),
        json_escape(slice_id),
        FLASHDB_SOURCE_COMMIT
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
    let sequence = NEXT_REPLAY_RUN_ID.fetch_add(1, Ordering::Relaxed);
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|value| value.as_nanos())
        .unwrap_or(0);
    format!("{}_{}_{}", std::process::id(), sequence, nanos)
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

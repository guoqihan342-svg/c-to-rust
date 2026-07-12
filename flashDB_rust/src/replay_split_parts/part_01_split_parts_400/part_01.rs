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

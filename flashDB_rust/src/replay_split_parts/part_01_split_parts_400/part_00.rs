fn parse_fixture(input: &str) -> Result<Fixture> {
    let name = field_value(input, "name").unwrap_or_else(|| "fixture".to_string());
    let mut operations = Vec::new();
    let mut accepted_differences = Vec::new();
    let mut in_accepted = false;

    for line in input.lines() {
        let trimmed = line.trim().trim_end_matches(',');
        if trimmed.contains("\"accepted_differences\"") {
            in_accepted = true;
            continue;
        }
        if in_accepted && trimmed.starts_with(']') {
            in_accepted = false;
            continue;
        }
        if !trimmed.starts_with('{') {
            continue;
        }
        if trimmed.contains("\"op\"") {
            let id = field_value(trimmed, "id")
                .ok_or_else(|| Error::Parse("fixture operation missing id".to_string()))?;
            let op = field_value(trimmed, "op")
                .ok_or_else(|| Error::Parse(format!("fixture operation {id} missing op")))?;
            let mut fields = BTreeMap::new();
            for field in [
                "key",
                "value",
                "timestamp",
                "from",
                "to",
                "status",
                "entry_id",
            ] {
                if let Some(value) = field_value(trimmed, field) {
                    fields.insert(field.to_string(), value);
                }
            }
            operations.push(Operation { id, op, fields });
        } else if in_accepted {
            accepted_differences.push(AcceptedDifference {
                id: field_value(trimmed, "id").unwrap_or_else(|| "unknown".to_string()),
                reason: field_value(trimmed, "reason").unwrap_or_default(),
                fields: field_value(trimmed, "fields").unwrap_or_default(),
            });
        }
    }

    if operations.is_empty() {
        return Err(Error::Parse("fixture has no operations".to_string()));
    }
    Ok(Fixture {
        name,
        operations,
        accepted_differences,
    })
}

fn field_value(input: &str, name: &str) -> Option<String> {
    let pattern = format!("\"{name}\"");
    let start = input.find(&pattern)? + pattern.len();
    let after_name = &input[start..];
    let colon = after_name.find(':')?;
    let mut rest = after_name[colon + 1..].trim_start();
    if rest.starts_with('"') {
        rest = &rest[1..];
        let end = rest.find('"')?;
        Some(rest[..end].to_string())
    } else {
        let end = rest.find([',', '}', ']']).unwrap_or(rest.len());
        Some(rest[..end].trim().to_string())
    }
}

#[derive(Debug, Clone)]
struct Mismatch {
    byte_offset: usize,
    step_id: String,
    field_path: String,
    expected: String,
    actual: String,
}

#[derive(Debug, Clone)]
struct ParsedStep {
    id: String,
    fields: BTreeMap<String, String>,
}

fn compare_reports(expected: &str, actual: &str) -> Result<Option<Mismatch>> {
    let ignored = ignored_fields(expected, actual);
    let expected_steps = parse_report_steps(expected)?;
    let actual_steps = parse_report_steps(actual)?;
    if expected_steps.len() != actual_steps.len() {
        return Ok(Some(Mismatch {
            byte_offset: 0,
            step_id: "steps".to_string(),
            field_path: "steps.len".to_string(),
            expected: expected_steps.len().to_string(),
            actual: actual_steps.len().to_string(),
        }));
    }

    let actual_by_id: BTreeMap<&str, &ParsedStep> = actual_steps
        .iter()
        .map(|step| (step.id.as_str(), step))
        .collect();
    for expected_step in &expected_steps {
        let Some(actual_step) = actual_by_id.get(expected_step.id.as_str()) else {
            return Ok(Some(Mismatch {
                byte_offset: 0,
                step_id: expected_step.id.clone(),
                field_path: "steps.id".to_string(),
                expected: expected_step.id.clone(),
                actual: "missing".to_string(),
            }));
        };

        let mut fields: Vec<String> = expected_step
            .fields
            .keys()
            .chain(actual_step.fields.keys())
            .filter(|name| !ignored.contains(name))
            .cloned()
            .collect();
        fields.sort();
        fields.dedup();
        for field in fields {
            let expected_value = expected_step.fields.get(&field);
            let actual_value = actual_step.fields.get(&field);
            if expected_value != actual_value {
                return Ok(Some(Mismatch {
                    byte_offset: 0,
                    step_id: expected_step.id.clone(),
                    field_path: format!("steps.{}.{}", expected_step.id, field),
                    expected: expected_value
                        .cloned()
                        .unwrap_or_else(|| "missing".to_string()),
                    actual: actual_value
                        .cloned()
                        .unwrap_or_else(|| "missing".to_string()),
                }));
            }
        }
    }

    Ok(None)
}

fn ignored_fields(left: &str, right: &str) -> Vec<String> {
    let mut out = ACCEPTED_DIFF_FIELD_ALLOWLIST
        .iter()
        .map(|value| (*value).to_string())
        .collect::<Vec<_>>();
    collect_accepted_fields(left, &mut out);
    collect_accepted_fields(right, &mut out);
    out.sort();
    out.dedup();
    out
}

const ACCEPTED_DIFF_FIELD_ALLOWLIST: &[&str] = &[
    "image_hash",
    "message",
    "backend",
    "toolchain_status",
    "source",
    "fixture",
    "fixture_hash",
    "report_path",
];

fn collect_accepted_fields(report: &str, out: &mut Vec<String>) {
    let mut rest = report;
    while let Some(index) = rest.find("\"fields\"") {
        rest = &rest[index + "\"fields\"".len()..];
        let Some(colon) = rest.find(':') else {
            break;
        };
        let value = rest[colon + 1..].trim_start();
        if !value.starts_with('"') {
            continue;
        }
        let value = &value[1..];
        let Some(end) = value.find('"') else {
            break;
        };
        for field in value[..end].split(',') {
            let field = field.trim();
            if ACCEPTED_DIFF_FIELD_ALLOWLIST.contains(&field) {
                out.push(field.to_string());
            }
        }
        rest = &value[end + 1..];
    }
}

fn parse_report_steps(report: &str) -> Result<Vec<ParsedStep>> {
    let array = json_array(report, "steps")
        .ok_or_else(|| Error::Parse("report missing steps array".to_string()))?;
    let objects = top_level_objects(array)?;
    let mut steps = Vec::new();
    for object in objects {
        let fields = top_level_fields(object)?;
        let id = fields
            .get("id")
            .and_then(|value| unquote_json_string(value))
            .ok_or_else(|| Error::Parse("step missing id".to_string()))?;
        steps.push(ParsedStep { id, fields });
    }
    Ok(steps)
}

fn json_array<'a>(input: &'a str, name: &str) -> Option<&'a str> {
    let marker = format!("\"{name}\"");
    let start = input.find(&marker)? + marker.len();
    let after_name = &input[start..];
    let colon = after_name.find(':')?;
    let after_colon = after_name[colon + 1..].trim_start();
    if !after_colon.starts_with('[') {
        return None;
    }
    let offset = input.len() - after_colon.len();
    let end = matching_delimiter(input, offset, '[', ']')?;
    Some(&input[offset + 1..end])
}

fn top_level_objects(input: &str) -> Result<Vec<&str>> {
    let mut out = Vec::new();
    let mut in_string = false;
    let mut escape = false;
    let mut depth = 0usize;
    let mut start = None;
    for (index, ch) in input.char_indices() {
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
        match ch {
            '"' => in_string = true,
            '{' => {
                if depth == 0 {
                    start = Some(index);
                }
                depth += 1;
            }
            '}' => {
                depth = depth
                    .checked_sub(1)
                    .ok_or_else(|| Error::Parse("unbalanced report object".to_string()))?;
                if depth == 0 {
                    let start = start
                        .take()
                        .ok_or_else(|| Error::Parse("missing object start".to_string()))?;
                    out.push(&input[start..=index]);
                }
            }
            _ => {}
        }
    }
    if depth != 0 {
        return Err(Error::Parse("unclosed report object".to_string()));
    }
    Ok(out)
}

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

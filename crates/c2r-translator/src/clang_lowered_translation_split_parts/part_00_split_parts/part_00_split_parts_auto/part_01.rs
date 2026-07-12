
fn slice_source_struct_declarations(spec: &SliceSpec) -> String {
    let mut structs = collect_struct_names(&spec.c_source);
    for signature in &spec.c_boundary.signatures {
        collect_struct_names_from_type(&signature.return_type, &mut structs);
        for parameter in &signature.parameters {
            collect_struct_names_from_type(&parameter.c_type, &mut structs);
        }
    }
    let complete_source_structs = collect_complete_struct_names(&spec.c_source);
    let accepted_record_fields = collect_accepted_named_slice_record_fields(spec);
    let field_placeholders = collect_signature_record_pointer_field_placeholders(spec);

    structs
        .into_iter()
        .map(|name| {
            if complete_source_structs.contains(&name) {
                return format!("struct {name};\n");
            }
            if let Some(fields) = accepted_record_fields
                .get(&name)
                .filter(|fields| !fields.is_empty())
            {
                let mut declaration = format!("struct {name} {{\n");
                for field in fields {
                    declaration.push_str(&format!("    {} {};\n", field.c_type, field.name));
                }
                declaration.push_str("};\n");
                return declaration;
            }
            let Some(fields) = field_placeholders.get(&name).filter(|fields| !fields.is_empty())
            else {
                return format!("struct {name} {{ unsigned char _c2r_opaque; }};\n");
            };
            let mut declaration = format!("struct {name} {{\n");
            for field in fields {
                declaration.push_str(&format!("    int {field};\n"));
            }
            declaration.push_str("    unsigned char _c2r_opaque;\n};\n");
            declaration
        })
        .collect::<String>()
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct SliceSourceRecordField {
    name: String,
    c_type: String,
}

fn collect_accepted_named_slice_record_fields(
    spec: &SliceSpec,
) -> BTreeMap<String, Vec<SliceSourceRecordField>> {
    let mut result = BTreeMap::new();
    for callee in &spec.c_boundary.external_direct_callees {
        let Some(evidence) = &callee.accepted_named_slice_evidence else {
            continue;
        };
        let Some(report_path) = accepted_named_slice_clang_lowering_report_path(evidence) else {
            continue;
        };
        for (record_name, fields) in record_fields_from_clang_lowering_report(&report_path) {
            result.entry(record_name).or_insert(fields);
        }
    }
    result
}

fn accepted_named_slice_clang_lowering_report_path(
    evidence: &crate::AcceptedNamedSliceEvidence,
) -> Option<PathBuf> {
    let final_verification = evidence.final_verification.trim();
    if final_verification.is_empty() {
        return None;
    }
    let final_path = resolve_repo_path(final_verification);
    let final_value: serde_json::Value = serde_json::from_str(&fs::read_to_string(&final_path).ok()?).ok()?;
    if !final_verification_accepts_named_slice(&final_value) {
        return None;
    }

    if let Some(manifest_path) =
        sibling_path_with_replaced_file_name(&final_path, "final-verification", "evidence-manifest")
    {
        if let Some(report_path) = clang_lowering_report_path_from_manifest(&manifest_path) {
            return Some(report_path);
        }
    }

    sibling_path_with_replaced_file_name(&final_path, "final-verification", "clang-lowering-report")
        .filter(|path| path.exists())
}

fn final_verification_accepts_named_slice(value: &serde_json::Value) -> bool {
    let status_passed = value
        .get("status")
        .and_then(serde_json::Value::as_str)
        .is_some_and(|status| status == "passed");
    let semantic_pass = value
        .get("semantic_pass")
        .and_then(serde_json::Value::as_bool)
        .unwrap_or(false);
    status_passed && semantic_pass
}

fn clang_lowering_report_path_from_manifest(manifest_path: &Path) -> Option<PathBuf> {
    let value: serde_json::Value =
        serde_json::from_str(&fs::read_to_string(manifest_path).ok()?).ok()?;
    let report = value
        .pointer("/evidence/clang_lowering_report")
        .and_then(serde_json::Value::as_object)?;
    let status_recorded = report
        .get("status")
        .and_then(serde_json::Value::as_str)
        .is_some_and(|status| status == "recorded" || status == "passed");
    if !status_recorded {
        return None;
    }
    report
        .get("path")
        .and_then(serde_json::Value::as_str)
        .map(resolve_repo_path)
        .filter(|path| path.exists())
}

fn sibling_path_with_replaced_file_name(path: &Path, needle: &str, replacement: &str) -> Option<PathBuf> {
    let file_name = path.file_name()?.to_str()?;
    let replaced = file_name.replace(needle, replacement);
    (replaced != file_name).then(|| path.with_file_name(replaced))
}

fn record_fields_from_clang_lowering_report(
    report_path: &Path,
) -> BTreeMap<String, Vec<SliceSourceRecordField>> {
    let Ok(raw_json) = fs::read_to_string(report_path) else {
        return BTreeMap::new();
    };
    let Ok(report) = serde_json::from_str::<serde_json::Value>(&raw_json) else {
        return BTreeMap::new();
    };
    let root = report
        .pointer("/lowering_report/function_ir")
        .or_else(|| report.get("function_ir"))
        .unwrap_or(&report);
    let mut result = BTreeMap::new();
    collect_record_fields_from_json_value(root, &mut result);
    result
}

fn collect_record_fields_from_json_value(
    value: &serde_json::Value,
    records: &mut BTreeMap<String, Vec<SliceSourceRecordField>>,
) {
    match value {
        serde_json::Value::Object(object) => {
            if let Some(record) = object.get("kind").and_then(|kind| kind.get("Record")) {
                collect_record_fields_from_record_kind(record, records);
            }
            for child in object.values() {
                collect_record_fields_from_json_value(child, records);
            }
        }
        serde_json::Value::Array(items) => {
            for item in items {
                collect_record_fields_from_json_value(item, records);
            }
        }
        _ => {}
    }
}

fn collect_record_fields_from_record_kind(
    record: &serde_json::Value,
    records: &mut BTreeMap<String, Vec<SliceSourceRecordField>>,
) {
    let Some(name) = record
        .get("name")
        .and_then(serde_json::Value::as_str)
        .filter(|name| is_c_identifier(name))
    else {
        return;
    };
    let Some(fields) = record.get("fields").and_then(serde_json::Value::as_array) else {
        return;
    };
    if fields.is_empty() {
        return;
    }

    let mut declarations = Vec::new();
    for field in fields {
        let Some(field_name) = field
            .get("name")
            .and_then(serde_json::Value::as_str)
            .filter(|name| is_c_identifier(name))
        else {
            return;
        };
        let Some(c_type) = field
            .get("ty")
            .and_then(c_field_type_from_typed_ir_json)
        else {
            return;
        };
        declarations.push(SliceSourceRecordField {
            name: field_name.to_string(),
            c_type,
        });
    }
    records.entry(name.to_string()).or_insert(declarations);
}

fn c_field_type_from_typed_ir_json(ty: &serde_json::Value) -> Option<String> {
    ty.get("spelled")
        .and_then(serde_json::Value::as_str)
        .and_then(normalize_supported_c_field_type)
        .or_else(|| {
            ty.get("canonical")
                .and_then(serde_json::Value::as_str)
                .and_then(normalize_supported_c_field_type)
        })
}

fn normalize_supported_c_field_type(candidate: &str) -> Option<String> {
    let trimmed = candidate.trim();
    if trimmed.is_empty()
        || !trimmed
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'*' || byte.is_ascii_whitespace())
    {
        return None;
    }
    let tokens = c_identifier_tokens(trimmed);
    if tokens.is_empty() || tokens.iter().any(|token| !is_builtin_type_token(token)) {
        return None;
    }
    if tokens.len() == 1 && tokens[0] == "void" && !trimmed.contains('*') {
        return None;
    }
    Some(normalize_c_type_spacing(trimmed))
}

fn normalize_c_type_spacing(value: &str) -> String {
    let mut result = String::new();
    let mut previous_was_space = false;
    for ch in value.trim().chars() {
        if ch.is_whitespace() {
            if !previous_was_space {
                result.push(' ');
                previous_was_space = true;
            }
        } else {
            result.push(ch);
            previous_was_space = false;
        }
    }
    result
}

fn collect_signature_record_pointer_field_placeholders(
    spec: &SliceSpec,
) -> BTreeMap<String, BTreeSet<String>> {
    let mut record_pointer_params: BTreeMap<String, String> = BTreeMap::new();
    for signature in &spec.c_boundary.signatures {
        for parameter in &signature.parameters {
            if let Some(record_name) = record_pointer_type_name(&parameter.c_type) {
                record_pointer_params.insert(parameter.name.clone(), record_name);
            }
        }
    }
    collect_record_pointer_arrow_field_uses(&spec.c_source, &record_pointer_params)
}

fn collect_record_pointer_arrow_field_uses(
    source: &str,
    record_pointer_params: &BTreeMap<String, String>,
) -> BTreeMap<String, BTreeSet<String>> {
    let searchable_source = c_source_without_strings_and_comments(source);
    let bytes = searchable_source.as_bytes();
    let mut result: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    let mut index = 0usize;
    while index < bytes.len() {
        if !is_c_ident_start(bytes[index]) {
            index += 1;
            continue;
        }
        let base_start = index;
        index += 1;
        while index < bytes.len() && is_c_ident_continue(bytes[index]) {
            index += 1;
        }
        let base = &searchable_source[base_start..index];
        let mut lookahead = index;
        while lookahead < bytes.len() && bytes[lookahead].is_ascii_whitespace() {
            lookahead += 1;
        }
        if lookahead + 1 >= bytes.len() || bytes[lookahead] != b'-' || bytes[lookahead + 1] != b'>'
        {
            continue;
        }
        lookahead += 2;
        while lookahead < bytes.len() && bytes[lookahead].is_ascii_whitespace() {
            lookahead += 1;
        }
        if lookahead >= bytes.len() || !is_c_ident_start(bytes[lookahead]) {
            continue;
        }
        let field_start = lookahead;
        lookahead += 1;
        while lookahead < bytes.len() && is_c_ident_continue(bytes[lookahead]) {
            lookahead += 1;
        }
        let field = &searchable_source[field_start..lookahead];
        if let Some(record_name) = record_pointer_params.get(base) {
            result
                .entry(record_name.clone())
                .or_default()
                .insert(field.to_string());
        }
    }
    result
}

fn record_pointer_type_name(c_type: &str) -> Option<String> {
    if !c_type.contains('*') {
        return None;
    }
    let tokens = c_identifier_tokens(c_type);
    for window in tokens.windows(2) {
        if window[0] == "struct" && !is_builtin_type_token(&window[1]) {
            return Some(window[1].clone());
        }
    }
    None
}

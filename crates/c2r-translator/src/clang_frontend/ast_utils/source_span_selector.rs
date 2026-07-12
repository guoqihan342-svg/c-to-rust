use super::*;
use sha2::{Digest, Sha256};

pub(super) fn select_expanded_function_name_by_source_span(
    ast: &Value,
    source_file: &Path,
    function_source_span: &SourceSpanRef,
) -> Result<String, ClangFrontendError> {
    let source_file = normalized_source_evidence_path(&source_file.to_string_lossy());
    let span_file = normalized_source_evidence_path(&function_source_span.file);
    if !source_evidence_paths_match(&source_file, &span_file)
        || function_source_span.line_start == 0
        || function_source_span.line_end < function_source_span.line_start
        || function_source_span.byte_end <= function_source_span.byte_start
    {
        return Err(ClangFrontendError {
        kind: "invalid_function_source_span".to_string(),
        message: "function source span must match source_file and contain ordered line and byte evidence"
            .to_string(),
    });
    }

    let (raw_byte_start, raw_byte_end) =
        raw_byte_span_for_normalized_source(source_file.as_str(), function_source_span)?;

    let mut matches = Vec::new();
    collect_body_function_names_by_source_span(
        ast,
        &source_file,
        function_source_span,
        raw_byte_start,
        raw_byte_end,
        &mut matches,
    );

    match matches.as_slice() {
    [Some(name)] => Ok(name.clone()),
    [None] => Err(ClangFrontendError {
        kind: "invalid_function_decl_source_span_match".to_string(),
        message: "the uniquely matched body-bearing FunctionDecl has no valid expanded C identifier"
            .to_string(),
    }),
    [] => Err(ClangFrontendError {
        kind: "function_decl_source_span_mismatch".to_string(),
        message: format!(
            "clang AST JSON does not contain exactly one body-bearing FunctionDecl at {}:{}-{} bytes {}-{}",
            function_source_span.file,
            function_source_span.line_start,
            function_source_span.line_end,
            function_source_span.byte_start,
            function_source_span.byte_end,
        ),
    }),
    _ => Err(ClangFrontendError {
        kind: "ambiguous_function_decl_source_span".to_string(),
        message: format!(
            "clang AST JSON contains multiple body-bearing FunctionDecl nodes at {}:{}-{} bytes {}-{}",
            function_source_span.file,
            function_source_span.line_start,
            function_source_span.line_end,
            function_source_span.byte_start,
            function_source_span.byte_end,
        ),
    }),
}
}

#[cfg(feature = "typed-ir")]
#[derive(Clone, Default)]
struct AstLocationState {
    file: Option<String>,
    line: Option<u64>,
}

#[cfg(feature = "typed-ir")]
struct AstSourceLocation {
    file: Option<String>,
    line: Option<u64>,
    offset: Option<u64>,
    token_length: Option<u64>,
}

#[cfg(feature = "typed-ir")]
fn collect_body_function_names_by_source_span(
    node: &Value,
    source_file: &str,
    function_source_span: &SourceSpanRef,
    raw_byte_start: u64,
    raw_byte_end: u64,
    matches: &mut Vec<Option<String>>,
) {
    if string_field(node, "kind").as_deref() == Some("FunctionDecl")
        && inner(node)
            .iter()
            .any(|child| string_field(child, "kind").as_deref() == Some("CompoundStmt"))
    {
        let mut state = AstLocationState::default();
        let declaration_location = resolve_ast_source_location(node.get("loc"), &mut state);
        let range_begin = resolve_ast_source_location(node.pointer("/range/begin"), &mut state);
        let range_end = resolve_ast_source_location(node.pointer("/range/end"), &mut state);
        if function_decl_matches_source_span(
            declaration_location.as_ref(),
            range_begin.as_ref(),
            range_end.as_ref(),
            source_file,
            function_source_span,
            raw_byte_start,
            raw_byte_end,
        ) {
            matches.push(string_field(node, "name").filter(|name| is_simple_c_identifier(name)));
        }
    }

    for child in inner(node) {
        collect_body_function_names_by_source_span(
            child,
            source_file,
            function_source_span,
            raw_byte_start,
            raw_byte_end,
            matches,
        );
    }
}

#[cfg(feature = "typed-ir")]
fn resolve_ast_source_location(
    location: Option<&Value>,
    state: &mut AstLocationState,
) -> Option<AstSourceLocation> {
    let location = location?.as_object()?;
    if location.contains_key("spellingLoc") || location.contains_key("expansionLoc") {
        let mut spelling_state = state.clone();
        let spelling =
            resolve_ast_source_location(location.get("spellingLoc"), &mut spelling_state);
        let expansion = resolve_ast_source_location(location.get("expansionLoc"), state);
        if expansion.is_some() {
            return expansion;
        }
        *state = spelling_state;
        return spelling;
    }

    if let Some(file) = location.get("file").and_then(Value::as_str) {
        state.file = Some(normalized_source_evidence_path(file));
    }
    if let Some(line) = location.get("line").and_then(Value::as_u64) {
        state.line = Some(line);
    }

    Some(AstSourceLocation {
        file: state.file.clone(),
        line: state.line,
        offset: location.get("offset").and_then(Value::as_u64),
        token_length: location.get("tokLen").and_then(Value::as_u64),
    })
}

#[cfg(feature = "typed-ir")]
fn function_decl_matches_source_span(
    declaration_location: Option<&AstSourceLocation>,
    range_begin: Option<&AstSourceLocation>,
    range_end: Option<&AstSourceLocation>,
    source_file: &str,
    function_source_span: &SourceSpanRef,
    raw_byte_start: u64,
    raw_byte_end: u64,
) -> bool {
    let (Some(declaration_location), Some(range_begin), Some(range_end)) =
        (declaration_location, range_begin, range_end)
    else {
        return false;
    };
    let Some(range_end_exclusive) = range_end
        .offset
        .and_then(|offset| offset.checked_add(range_end.token_length?))
    else {
        return false;
    };

    [
        declaration_location.file.as_deref(),
        range_begin.file.as_deref(),
        range_end.file.as_deref(),
    ]
    .into_iter()
    .all(|file| file.is_some_and(|file| source_evidence_paths_match(file, source_file)))
        && declaration_location.line == Some(function_source_span.line_start)
        && range_begin.line == Some(function_source_span.line_start)
        && range_end.line == Some(function_source_span.line_end)
        && range_begin.offset == Some(raw_byte_start)
        && range_end_exclusive == raw_byte_end
}

#[cfg(feature = "typed-ir")]
fn raw_byte_span_for_normalized_source(
    source_file: &str,
    function_source_span: &SourceSpanRef,
) -> Result<(u64, u64), ClangFrontendError> {
    let Ok(raw) = std::fs::read(source_file) else {
        return Ok((
            function_source_span.byte_start,
            function_source_span.byte_end,
        ));
    };
    let mut normalized = Vec::with_capacity(raw.len());
    let mut raw_boundaries = Vec::with_capacity(raw.len() + 1);
    raw_boundaries.push(0usize);
    let mut raw_index = 0usize;
    while raw_index < raw.len() {
        if raw[raw_index] == b'\r' {
            normalized.push(b'\n');
            raw_index += usize::from(raw.get(raw_index + 1) == Some(&b'\n')) + 1;
        } else {
            normalized.push(raw[raw_index]);
            raw_index += 1;
        }
        raw_boundaries.push(raw_index);
    }

    let start = usize::try_from(function_source_span.byte_start).ok();
    let end = usize::try_from(function_source_span.byte_end).ok();
    let (Some(start), Some(end)) = (start, end) else {
        return Err(invalid_normalized_source_span(function_source_span));
    };
    let Some(source_slice) = normalized.get(start..end) else {
        return Err(invalid_normalized_source_span(function_source_span));
    };
    let source_sha256 = format!("{:x}", Sha256::digest(source_slice));
    if source_sha256 != function_source_span.sha256.to_ascii_lowercase() {
        return Err(ClangFrontendError {
            kind: "function_source_span_hash_mismatch".to_string(),
            message: format!(
                "normalized source span SHA-256 mismatch for {}:{}-{} bytes {}-{}",
                function_source_span.file,
                function_source_span.line_start,
                function_source_span.line_end,
                function_source_span.byte_start,
                function_source_span.byte_end,
            ),
        });
    }
    Ok((
        raw_boundaries[start] as u64,
        raw_boundaries[end] as u64,
    ))
}

#[cfg(feature = "typed-ir")]
fn invalid_normalized_source_span(
    function_source_span: &SourceSpanRef,
) -> ClangFrontendError {
    ClangFrontendError {
        kind: "invalid_function_source_span".to_string(),
        message: format!(
            "normalized source span is outside {} bytes {}-{}",
            function_source_span.file,
            function_source_span.byte_start,
            function_source_span.byte_end,
        ),
    }
}

#[cfg(feature = "typed-ir")]
fn normalized_source_evidence_path(path: &str) -> String {
    let path = path.trim().replace('\\', "/");
    if path.starts_with('<') && path.ends_with('>') {
        return path;
    }

    let has_root = path.starts_with('/');
    let mut components: Vec<&str> = Vec::new();
    for component in path.split('/') {
        match component {
            "" | "." => {}
            ".." if components.last().is_some_and(|last| *last != "..") => {
                components.pop();
            }
            _ => components.push(component),
        }
    }
    let normalized = components.join("/");
    if has_root {
        format!("/{normalized}")
    } else {
        normalized
    }
}

#[cfg(feature = "typed-ir")]
fn source_evidence_paths_match(left: &str, right: &str) -> bool {
    let left = normalized_source_evidence_path(left);
    let right = normalized_source_evidence_path(right);
    let left_absolute = is_absolute_source_evidence_path(&left);
    let right_absolute = is_absolute_source_evidence_path(&right);
    left == right
        || (left_absolute && !right_absolute && left.ends_with(&format!("/{right}")))
        || (right_absolute && !left_absolute && right.ends_with(&format!("/{left}")))
}

#[cfg(feature = "typed-ir")]
fn is_absolute_source_evidence_path(path: &str) -> bool {
    path.starts_with('/')
        || path
            .as_bytes()
            .get(1)
            .is_some_and(|separator| *separator == b':')
}

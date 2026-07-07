fn detect_unsupported_control_flow(body: &str) -> Vec<UnsupportedControlFlow> {
    let mut unsupported = Vec::new();
    for label in label_targets(body) {
        push_control_flow(&mut unsupported, "label", Some(label));
    }
    if contains_token(body, "goto") {
        push_control_flow(&mut unsupported, "goto", None);
        for target in goto_targets(body) {
            push_control_flow(&mut unsupported, "goto", Some(target));
        }
    }
    if contains_token(body, "switch") {
        push_control_flow(&mut unsupported, "switch", None);
        for case in case_targets(body) {
            push_control_flow(&mut unsupported, "case", Some(case));
        }
        if contains_token(body, "default") {
            push_control_flow(&mut unsupported, "default", None);
        }
    }
    for (needle, label) in [
        ("setjmp", "setjmp"),
        ("longjmp", "longjmp"),
        ("asm", "inline_assembly"),
    ] {
        if contains_token(body, needle) {
            push_control_flow(&mut unsupported, label, None);
        }
    }
    unsupported
}

fn push_control_flow(
    unsupported: &mut Vec<UnsupportedControlFlow>,
    kind: &'static str,
    detail: Option<String>,
) {
    let candidate = UnsupportedControlFlow { kind, detail };
    if !unsupported.iter().any(|item| item == &candidate) {
        unsupported.push(candidate);
    }
}

fn unsupported_control_flow_labels(items: &[UnsupportedControlFlow]) -> Vec<String> {
    let mut labels = items
        .iter()
        .map(UnsupportedControlFlow::label)
        .collect::<Vec<_>>();
    if items.iter().any(|item| item.kind == "goto") {
        push_unique(&mut labels, "relooper_refusal:goto");
    }
    if items.iter().any(|item| item.kind == "switch") {
        push_unique(&mut labels, "relooper_refusal:switch");
    }
    labels
}

fn structured_control_flow_evidence(
    statements: &[ParsedStatement],
    items: &[UnsupportedControlFlow],
) -> Option<StructuredControlFlowEvidence> {
    if items.is_empty() {
        return None;
    }
    let has_goto = items.iter().any(|item| item.kind == "goto");
    let has_switch = items.iter().any(|item| item.kind == "switch");
    let label_names = items
        .iter()
        .filter(|item| item.kind == "label")
        .filter_map(|item| item.detail.as_deref())
        .collect::<Vec<_>>();
    let mut preconditions = Vec::new();
    if has_goto
        && items
            .iter()
            .filter(|item| item.kind == "goto")
            .filter_map(|item| item.detail.as_deref())
            .all(|target| label_names.iter().any(|label| *label == target))
    {
        push_unique(&mut preconditions, "goto_target_resolved");
    }
    if has_switch
        && items
            .iter()
            .any(|item| matches!(item.kind, "case" | "default"))
    {
        push_unique(&mut preconditions, "switch_cases_enumerated");
    }

    let mut refusals = Vec::new();
    if has_goto {
        push_unique(&mut refusals, "goto_requires_structured_recovery");
    }
    if has_switch {
        push_unique(&mut refusals, "switch_requires_structured_recovery");
    }

    Some(StructuredControlFlowEvidence {
        if_count: statements
            .iter()
            .filter(|statement| statement.kind == StatementKind::If)
            .count(),
        loop_count: statements
            .iter()
            .filter(|statement| {
                matches!(statement.kind, StatementKind::While | StatementKind::For)
            })
            .count(),
        has_goto,
        has_switch,
        relooper_required: has_goto || has_switch,
        recovery_status: "refused".to_string(),
        relooper_preconditions: preconditions,
        relooper_refusals: refusals,
        scope_note: "minimal structured-recovery evidence only; no Rust candidate lowering or C/Rust semantic pass is claimed".to_string(),
    })
}

fn label_targets(body: &str) -> Vec<String> {
    let mut labels = Vec::new();
    for segment in body.split(';') {
        let trimmed = segment.trim();
        let Some(colon_index) = trimmed.find(':') else {
            continue;
        };
        let before_colon = trimmed[..colon_index].trim();
        if before_colon.starts_with("case ")
            || before_colon == "default"
            || before_colon.contains('?')
            || before_colon.contains(' ')
        {
            continue;
        }
        if is_identifier(before_colon) {
            push_unique(&mut labels, before_colon);
        }
    }
    labels
}

fn goto_targets(body: &str) -> Vec<String> {
    let mut targets = Vec::new();
    for segment in body.split(';') {
        let Some(index) = find_token(segment, "goto") else {
            continue;
        };
        let after_goto = segment[index + "goto".len()..].trim();
        let target = after_goto
            .split(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_'))
            .next()
            .unwrap_or("")
            .trim();
        if is_identifier(target) {
            push_unique(&mut targets, target);
        }
    }
    targets
}

fn case_targets(body: &str) -> Vec<String> {
    let mut cases = Vec::new();
    let mut rest = body;
    while let Some(index) = find_token(rest, "case") {
        let after_case = &rest[index + "case".len()..];
        if let Some(colon_index) = after_case.find(':') {
            let value = after_case[..colon_index].trim();
            if !value.is_empty() {
                push_unique(&mut cases, &sanitize_case_label(value));
            }
            rest = &after_case[colon_index + 1..];
        } else {
            break;
        }
    }
    cases
}

fn find_token(text: &str, token: &str) -> Option<usize> {
    let mut offset = 0usize;
    while let Some(index) = text[offset..].find(token) {
        let absolute = offset + index;
        let before = text[..absolute].chars().next_back();
        let after = text[absolute + token.len()..].chars().next();
        let before_boundary = before
            .map(|ch| !(ch.is_ascii_alphanumeric() || ch == '_'))
            .unwrap_or(true);
        let after_boundary = after
            .map(|ch| !(ch.is_ascii_alphanumeric() || ch == '_'))
            .unwrap_or(true);
        if before_boundary && after_boundary {
            return Some(absolute);
        }
        offset = absolute + token.len();
    }
    None
}

fn is_identifier(value: &str) -> bool {
    let mut chars = value.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    (first.is_ascii_alphabetic() || first == '_')
        && chars.all(|ch| ch.is_ascii_alphanumeric() || ch == '_')
}

fn sanitize_case_label(value: &str) -> String {
    value
        .trim()
        .trim_matches(|ch: char| ch == '(' || ch == ')')
        .to_string()
}

fn contains_token(text: &str, token: &str) -> bool {
    text.split(|ch: char| !(ch.is_ascii_alphanumeric() || ch == '_'))
        .any(|part| part == token)
}

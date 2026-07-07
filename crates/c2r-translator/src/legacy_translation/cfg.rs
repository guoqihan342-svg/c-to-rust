fn cfg_edges_for_statements(
    statements: &[ParsedStatement],
    unsupported_control_flow: &[UnsupportedControlFlow],
) -> Vec<String> {
    let mut edges = statements
        .iter()
        .enumerate()
        .filter_map(|(index, statement)| match statement.kind {
            StatementKind::If => Some(format!("entry->if-{index}")),
            StatementKind::While => Some(format!("entry->while-{index}")),
            StatementKind::For => Some(format!("entry->for-{index}")),
            StatementKind::Return => Some(format!("entry->return-{index}")),
            _ => None,
        })
        .collect::<Vec<_>>();
    for item in unsupported_control_flow {
        match item.kind {
            "label" => push_unique(&mut edges, &format!("entry->{}", item.block_id())),
            "goto" if item.detail.is_some() => {
                push_unique(&mut edges, &format!("entry->{}", item.block_id()));
            }
            "switch" => push_unique(&mut edges, "entry->switch-0"),
            _ => {}
        }
    }
    edges
}

fn unsupported_control_flow_blocks(items: &[UnsupportedControlFlow]) -> Vec<CfgBlock> {
    let mut blocks = Vec::new();
    let labels = items
        .iter()
        .filter(|item| item.kind == "label")
        .collect::<Vec<_>>();
    let cases = items
        .iter()
        .filter(|item| item.kind == "case")
        .collect::<Vec<_>>();
    let has_default = items.iter().any(|item| item.kind == "default");

    for item in items {
        match item.kind {
            "label" => blocks.push(CfgBlock {
                id: item.block_id(),
                statements: vec![item.label()],
                statement_kinds: vec!["label".to_string()],
                lvalue_kinds: Vec::new(),
                terminator: "unsupported_label".to_string(),
                edges: Vec::new(),
            }),
            "goto" if item.detail.is_some() => {
                let mut edges = Vec::new();
                if let Some(target) = &item.detail {
                    if labels
                        .iter()
                        .any(|label| label.detail.as_ref() == Some(target))
                    {
                        push_unique(
                            &mut edges,
                            &format!("{}->label-{}", item.block_id(), sanitize_cfg_id(target)),
                        );
                    }
                }
                blocks.push(CfgBlock {
                    id: item.block_id(),
                    statements: vec![item.label()],
                    statement_kinds: vec!["goto".to_string()],
                    lvalue_kinds: Vec::new(),
                    terminator: "unsupported_goto".to_string(),
                    edges,
                });
            }
            "switch" => {
                let mut edges = Vec::new();
                for case in &cases {
                    push_unique(&mut edges, &format!("switch-0->{}", case.block_id()));
                }
                if has_default {
                    push_unique(&mut edges, "switch-0->default");
                }
                blocks.push(CfgBlock {
                    id: "switch-0".to_string(),
                    statements: vec!["switch".to_string()],
                    statement_kinds: vec!["switch".to_string()],
                    lvalue_kinds: Vec::new(),
                    terminator: "unsupported_switch".to_string(),
                    edges,
                });
            }
            "case" | "default" => blocks.push(CfgBlock {
                id: item.block_id(),
                statements: vec![item.label()],
                statement_kinds: vec![item.kind.to_string()],
                lvalue_kinds: Vec::new(),
                terminator: format!("unsupported_{}", item.kind),
                edges: Vec::new(),
            }),
            _ => {}
        }
    }
    blocks
}

fn sanitize_cfg_id(value: &str) -> String {
    let sanitized = value
        .chars()
        .map(|ch| {
            if ch.is_ascii_alphanumeric() || ch == '_' {
                ch
            } else {
                '-'
            }
        })
        .collect::<String>()
        .trim_matches('-')
        .replace('_', "-");
    if sanitized.is_empty() {
        "unknown".to_string()
    } else {
        sanitized
    }
}

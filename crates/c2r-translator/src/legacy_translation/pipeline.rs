/// Runs the legacy string pipeline end to end for one slice.
///
/// The result is useful as a compatibility candidate only: parsing,
/// unsupported-node detection, evidence, and Rust emission all share the same
/// bounded string view of the C body. Any uncertainty is recorded on the result
/// and stops emission instead of being silently interpreted as real C semantics.
pub fn translate_slice(spec: &SliceSpec) -> TranslationResult {
    let parsed = parse_function(&spec.c_source, &spec.function_name);
    let mut result = TranslationResult {
        translation_source: TranslationSource::selected("legacy-string-translator"),
        plan: TranslationPlan {
            target_id: spec.target_id.clone(),
            slice_id: spec.slice_id.clone(),
            function_name: spec.function_name.clone(),
            ..TranslationPlan::default()
        },
        ..TranslationResult::default()
    };

    let function = match parsed {
        Ok(function) => function,
        Err(error) => {
            result.errors.push(error);
            return result;
        }
    };

    let statements = parse_statements(&function.body);
    let unsupported_control_flow = detect_unsupported_control_flow(&function.body);
    let unsupported_control_flow_labels =
        unsupported_control_flow_labels(&unsupported_control_flow);
    let mut blocks = vec![CfgBlock {
        id: "entry".to_string(),
        statements: statements
            .iter()
            .map(|statement| statement.text.clone())
            .collect(),
        statement_kinds: statement_kind_labels(&statements),
        lvalue_kinds: statement_lvalue_kinds(&statements),
        terminator: if statements
            .iter()
            .any(|statement| statement.kind == StatementKind::Return)
        {
            "return".to_string()
        } else {
            "fallthrough".to_string()
        },
        edges: cfg_edges_for_statements(&statements, &unsupported_control_flow),
    }];
    blocks.extend(unsupported_control_flow_blocks(&unsupported_control_flow));
    result.cfg.functions.push(CfgFunction {
        name: function.name.clone(),
        blocks,
        unsupported_control_flow: unsupported_control_flow_labels.clone(),
        structured_control_flow: structured_control_flow_evidence(
            &statements,
            &unsupported_control_flow,
        ),
    });

    if !unsupported_control_flow.is_empty() {
        result.plan.unsupported_node_count = unsupported_control_flow_labels.len();
        for node in unsupported_control_flow_labels {
            result.errors.push(TranslationError {
                kind: "unsupported_control_flow".to_string(),
                message: format!("{node} requires CFG/relooper support before automatic lowering"),
                source_span: Some(node),
            });
        }
        return result;
    }

    record_unsupported_statements(&statements, &mut result);
    record_unbounded_buffer_reads(&statements, &mut result);
    record_unbounded_pointer_arithmetic_output_writes(&function, &statements, &mut result);
    if result
        .errors
        .iter()
        .any(|error| error.kind == "unsupported_syntax")
    {
        result.plan.unsupported_node_count = result.errors.len();
        return result;
    }

    emit_type_map(&function, &statements, spec, &mut result);
    emit_pointer_graph(&function, &statements, &mut result);
    record_call_expression_evidence(&statements, &mut result);

    if !result.errors.is_empty() {
        result.plan.unsupported_node_count = result.errors.len();
        return result;
    }

    result.rust_code = emit_rust(&function, &statements, &mut result);
    result
}

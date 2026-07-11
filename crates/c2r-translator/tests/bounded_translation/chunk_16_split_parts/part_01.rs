
#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_rejects_do_while_tail_call_assignment_boundaries_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/do_while_tail_call_assignment_ast.json"
    ))
    .expect("fixture JSON");

    for (function_name, expected_reason) in [
        (
            "bad_do_while_tail_assign_deref_target",
            "direct non-volatile, non-atomic fixed-width integer DeclRef",
        ),
        ("bad_do_while_tail_assign_second_call", "second call"),
        (
            "bad_while_tail_assign_shape",
            "opcode = is outside the current skeleton",
        ),
    ] {
        let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
            .expect_err("out-of-bound tail assignment shape must fail closed");
        assert!(
            error.message.contains(expected_reason),
            "{function_name}: expected {expected_reason:?}, got {error:?}"
        );
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn nested_local_record_tail_ast(
    record_name: &str,
    local_name: &str,
    middle_field: &str,
    leaf_field: &str,
    function_name: &str,
    callee: &str,
) -> Value {
    let nested_record_name = format!("{record_name}_{middle_field}");
    let record_ty = format!("struct {record_name}");
    let nested_record_ty = format!("struct {nested_record_name}");
    let mut target = serde_json::json!({
        "kind": "DeclRefExpr",
        "type": { "qualType": record_ty },
        "referencedDecl": { "kind": "VarDecl", "name": local_name }
    });
    target = serde_json::json!({
        "kind": "MemberExpr",
        "name": middle_field,
        "isArrow": false,
        "type": { "qualType": nested_record_ty },
        "inner": [target]
    });
    target = serde_json::json!({
        "kind": "MemberExpr",
        "name": leaf_field,
        "isArrow": false,
        "type": { "qualType": "int" },
        "inner": [target]
    });
    let return_target = target.clone();

    let nested_record = serde_json::json!({
        "kind": "RecordDecl",
        "tagUsed": "struct",
        "completeDefinition": true,
        "inner": [{
            "kind": "FieldDecl",
            "name": leaf_field,
            "type": { "qualType": "int" }
        }]
    });
    let record = serde_json::json!({
        "kind": "RecordDecl",
        "tagUsed": "struct",
        "name": record_name,
        "completeDefinition": true,
        "inner": [
            nested_record,
            {
                "kind": "FieldDecl",
                "name": middle_field,
                "type": {
                    "qualType": "struct (unnamed struct at renamed_fixture.c:1:1)",
                    "desugaredQualType": nested_record_ty,
                    "canonicalQualType": nested_record_ty
                }
            }
        ]
    });
    let local_decl = serde_json::json!({
        "kind": "DeclStmt",
        "inner": [{
            "kind": "VarDecl",
            "name": local_name,
            "init": "c",
            "type": { "qualType": record_ty },
            "inner": [{
                "kind": "DeclRefExpr",
                "type": { "qualType": record_ty },
                "referencedDecl": { "kind": "ParmVarDecl", "name": "seed" }
            }]
        }]
    });
    let call = serde_json::json!({
        "kind": "CallExpr",
        "type": { "qualType": "int" },
        "inner": [{
            "kind": "ImplicitCastExpr",
            "castKind": "FunctionToPointerDecay",
            "type": { "qualType": "int (*)(void)" },
            "inner": [{
                "kind": "DeclRefExpr",
                "type": { "qualType": "int (void)" },
                "referencedDecl": { "kind": "FunctionDecl", "name": callee }
            }]
        }]
    });
    let assignment = serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": "=",
        "type": { "qualType": "int" },
        "inner": [target, call]
    });
    let condition = serde_json::json!({
        "kind": "BinaryOperator",
        "opcode": "!=",
        "type": { "qualType": "int" },
        "inner": [
            {
                "kind": "ParenExpr",
                "type": { "qualType": "int" },
                "inner": [assignment]
            },
            { "kind": "IntegerLiteral", "value": "0", "type": { "qualType": "int" } }
        ]
    });
    let do_stmt = serde_json::json!({
        "kind": "DoStmt",
        "inner": [{ "kind": "CompoundStmt", "inner": [] }, condition]
    });
    let return_stmt = serde_json::json!({
        "kind": "ReturnStmt",
        "inner": [{
            "kind": "ImplicitCastExpr",
            "castKind": "LValueToRValue",
            "type": { "qualType": "int" },
            "inner": [return_target]
        }]
    });
    let function = serde_json::json!({
        "kind": "FunctionDecl",
        "name": function_name,
        "type": { "qualType": format!("int ({record_ty})") },
        "inner": [
            {
                "kind": "ParmVarDecl",
                "name": "seed",
                "type": { "qualType": record_ty }
            },
            {
                "kind": "CompoundStmt",
                "inner": [local_decl, do_stmt, return_stmt]
            }
        ]
    });
    serde_json::json!({
        "kind": "TranslationUnitDecl",
        "inner": [record, function]
    })
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn chunk16_local_member_path(expr: &IrExpr) -> Option<(String, Vec<String>)> {
    match expr {
        IrExpr::Var { name, .. } => Some((name.clone(), Vec::new())),
        IrExpr::Member {
            base,
            field,
            is_arrow: false,
            ..
        } => {
            let (root, mut fields) = chunk16_local_member_path(base)?;
            fields.push(field.clone());
            Some((root, fields))
        }
        _ => None,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn renamed_nested_local_record_do_while_tail_runs_without_clang() {
    for (
        record_name,
        rust_record,
        local_name,
        middle_field,
        rust_nested_record,
        leaf_field,
        function_name,
        callee,
    ) in [
        (
            "packet_box",
            "PacketBox",
            "packet",
            "state",
            "PacketBoxState",
            "code",
            "walk_packet",
            "pull_code",
        ),
        (
            "cursor_frame",
            "CursorFrame",
            "cursor",
            "window",
            "CursorFrameWindow",
            "offset",
            "scan_cursor",
            "advance_offset",
        ),
    ] {
        let ast = nested_local_record_tail_ast(
            record_name,
            local_name,
            middle_field,
            leaf_field,
            function_name,
            callee,
        );
        let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
            .expect("lower renamed nested local record tail without clang");
        let [IrStmt::Decl { .. }, IrStmt::DoWhile {
            body, condition, ..
        }, IrStmt::Return { .. }] = lowered.function_ir.body.as_slice()
        else {
            panic!(
                "unexpected local record tail IR: {:?}",
                lowered.function_ir.body
            );
        };
        let Some(IrStmt::Assign { target, value, .. }) = body.last() else {
            panic!("do-while body must end with the normalized assignment");
        };
        let expected_path = (
            local_name.to_string(),
            vec![middle_field.to_string(), leaf_field.to_string()],
        );
        assert_eq!(
            chunk16_local_member_path(target),
            Some(expected_path.clone())
        );
        assert!(matches!(value, IrExpr::Call { callee: actual, .. } if actual == callee));
        assert!(matches!(
            condition,
            IrExpr::Binary { lhs, .. }
                if matches!(
                    lhs.as_ref(),
                    IrExpr::LValueToRValue { expr, .. }
                        if chunk16_local_member_path(expr) == Some(expected_path.clone())
                )
        ));

        let emitted = emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
            .expect("emit renamed nested local record tail");
        assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
        let rust = emitted.rust;
        let path = format!("{local_name}.{middle_field}.{leaf_field}");
        assert!(rust.contains(&format!("{path} = {callee}();")), "{rust}");
        assert!(rust.contains(&format!("{path} != 0i32")), "{rust}");
        assert!(rust.contains(&format!("return {path};")), "{rust}");

        let runtime_rust = format!("fn {callee}() -> i32 {{ 0i32 }}\n{rust}");
        let main_body = format!(
            "    let seed = {rust_record} {{ {middle_field}: {rust_nested_record} {{ {leaf_field}: 41i32 }} }};\n    assert_eq!({function_name}(seed), 0i32);"
        );
        assert_rust_snippet_runs(
            &format!("typed-ir-nested-local-record-tail-{function_name}"),
            &runtime_rust,
            &main_body,
        );
    }
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_rejects_incomplete_nested_local_record_member_path() {
    let i32_ty = ir_i32();
    let incomplete_inner = ir_record("inner_state");
    let outer = ir_record_with_fields("outer_state", vec![("inner", incomplete_inner.clone())]);
    let inner_member = IrExpr::Member {
        base: Box::new(ir_var("local", outer.clone())),
        field: "inner".to_string(),
        ty: incomplete_inner,
        is_arrow: false,
        source_span: None,
    };
    let leaf_target = IrExpr::Member {
        base: Box::new(inner_member),
        field: "value".to_string(),
        ty: i32_ty.clone(),
        is_arrow: false,
        source_span: None,
    };
    let ir = IrFunction {
        name: "reject_incomplete_local_path".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "seed".to_string(),
            ty: outer.clone(),
            source_span: None,
        }],
        body: vec![
            IrStmt::Decl {
                name: "local".to_string(),
                ty: outer.clone(),
                init: Some(ir_var("seed", outer)),
                source_span: None,
            },
            IrStmt::Assign {
                target: leaf_target,
                value: IrExpr::LitInt {
                    value: 1,
                    spelling: "1".to_string(),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Return {
                value: Some(IrExpr::LitInt {
                    value: 0,
                    spelling: "0".to_string(),
                    ty: i32_ty,
                    source_span: None,
                }),
                source_span: None,
            },
        ],
        source_span: None,
    };

    let error =
        emit_rust_from_ir(&ir).expect_err("incomplete nested local record path must fail closed");
    assert!(
        error
            .reason
            .contains("record outer_state field inner has record type inner_state is unsupported"),
        "{error:?}"
    );
}

#[cfg(feature = "typed-ir")]
#[test]
fn typed_ir_preserves_single_member_with_incomplete_record_inventory() {
    let i32_ty = ir_i32();
    let record_ty = ir_record("legacy_box");
    let ir = IrFunction {
        name: "read_legacy_value".to_string(),
        return_type: i32_ty.clone(),
        params: vec![IrParam {
            name: "item".to_string(),
            ty: record_ty.clone(),
            source_span: None,
        }],
        body: vec![IrStmt::Return {
            value: Some(IrExpr::Member {
                base: Box::new(ir_var("item", record_ty)),
                field: "value".to_string(),
                ty: i32_ty,
                is_arrow: false,
                source_span: None,
            }),
            source_span: None,
        }],
        source_span: None,
    };

    let emitted = emit_rust_from_ir(&ir)
        .expect("single dot member must retain the legacy incomplete-root emitter path");
    let rust = emitted.rust;
    assert!(rust.contains("pub struct LegacyBox"), "{rust}");
    assert!(rust.contains("pub value: i32"), "{rust}");
    assert!(rust.contains("return item.value;"), "{rust}");
    assert_rust_snippet_runs(
        "typed-ir-single-member-incomplete-record-inventory",
        &rust,
        "    assert_eq!(read_legacy_value(LegacyBox { value: 17i32 }), 17i32);",
    );
}

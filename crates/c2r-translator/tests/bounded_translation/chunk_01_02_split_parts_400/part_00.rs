#[cfg(feature = "typed-ir")]
fn ir_record(name: &str) -> IrType {
    IrType {
        spelled: format!("struct {name}"),
        canonical: format!("struct {name}"),
        kind: IrTypeKind::Record {
            name: name.to_string(),
            fields: None,
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_record_with_fields(name: &str, fields: Vec<(&str, IrType)>) -> IrType {
    IrType {
        spelled: format!("struct {name}"),
        canonical: format!("struct {name}"),
        kind: IrTypeKind::Record {
            name: name.to_string(),
            fields: Some(
                fields
                    .into_iter()
                    .map(|(name, ty)| IrRecordField {
                        name: name.to_string(),
                        ty,
                    })
                    .collect(),
            ),
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_var(name: &str, ty: IrType) -> IrExpr {
    IrExpr::Var {
        name: name.to_string(),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_null_ptr(ty: IrType) -> IrExpr {
    IrExpr::NullPtr {
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_lit(value: u64, spelling: &str, ty: IrType) -> IrExpr {
    IrExpr::LitInt {
        value,
        spelling: spelling.to_string(),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_array(element: IrType, len: usize) -> IrType {
    IrType {
        spelled: format!("{}[{len}]", element.spelled),
        canonical: format!("{}[{len}]", element.canonical),
        kind: IrTypeKind::Array {
            element: Box::new(element),
            len: Some(len),
        },
        is_const: false,
        width_bits: None,
        source_span: None,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
fn without_implicit_cast(expr: &IrExpr) -> &IrExpr {
    match expr {
        IrExpr::Cast {
            expr,
            implicit: true,
            ..
        } => without_implicit_cast(expr),
        _ => expr,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_binary(op: IrBinOp, lhs: IrExpr, rhs: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Binary {
        op,
        lhs: Box::new(lhs),
        rhs: Box::new(rhs),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_conditional(condition: IrExpr, then_expr: IrExpr, else_expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Conditional {
        condition: Box::new(condition),
        then_expr: Box::new(then_expr),
        else_expr: Box::new(else_expr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_deref(ptr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Deref {
        ptr: Box::new(ptr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_bitnot(expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Unary {
        op: IrUnOp::BitNot,
        operand: Box::new(expr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_neg(expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Unary {
        op: IrUnOp::Neg,
        operand: Box::new(expr),
        ty,
        source_span: None,
    }
}

#[cfg(feature = "typed-ir")]
fn ir_not(expr: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Unary {
        op: IrUnOp::Not,
        operand: Box::new(expr),
        ty,
        source_span: None,
    }
}

#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_control_flow_refusals_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../../fixtures/clang_ast/control_flow_refusals_ast.json"
    ))
    .expect("fixture JSON");

    for (function_name, expected_reason, expected_range) in [
        (
            "label_refusal",
            "unsupported control-flow LabelStmt",
            "source_range=2:3-2:15",
        ),
        (
            "goto_refusal",
            "unsupported control-flow GotoStmt",
            "source_range=5:3-5:12",
        ),
        (
            "switch_refusal",
            "unsupported control-flow SwitchStmt",
            "source_range=8:3-8:48",
        ),
        (
            "case_refusal",
            "unsupported control-flow CaseStmt",
            "source_range=11:3-11:18",
        ),
        (
            "default_refusal",
            "unsupported control-flow DefaultStmt",
            "source_range=14:3-14:18",
        ),
    ] {
        let error = lower_function_and_globals_from_clang_ast_json_value(&ast, function_name)
            .expect_err("control-flow fixture must fail closed during clang AST lowering");
        assert_eq!(error.kind, "unsupported_clang_stmt");
        assert!(
            error.message.contains(expected_reason),
            "expected {function_name} refusal to contain {expected_reason:?}, got {:?}",
            error.message
        );
        assert!(
            error
                .message
                .contains("requires structured CFG/relooper support"),
            "expected {function_name} refusal to mention CFG/relooper support, got {:?}",
            error.message
        );
        assert!(
            error.message.contains(expected_range),
            "expected {function_name} refusal to contain {expected_range:?}, got {:?}",
            error.message
        );
    }
}

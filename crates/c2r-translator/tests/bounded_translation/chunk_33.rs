#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn clang_ast_fixture_replays_mutable_record_pointer_u32_postfix_increment_without_clang() {
    let ast: Value = serde_json::from_str(include_str!(
        "../../fixtures/clang_ast/record_pointer_u32_postfix_inc_ast.json"
    ))
    .expect("fixture JSON");
    let lowered = lower_function_and_globals_from_clang_ast_json_value(&ast, "bump_counter")
        .expect("lower mutable record pointer u32 postfix increment fixture");

    let [IrStmt::Assign {
        target:
            IrExpr::Member {
                field: target_field,
                is_arrow: true,
                ..
            },
        value:
            IrExpr::Binary {
                op: IrBinOp::Add,
                lhs,
                rhs,
                ..
            },
        ..
    }] = lowered.function_ir.body.as_slice()
    else {
        panic!(
            "expected one normalized arrow-field increment assignment, got {:?}",
            lowered.function_ir.body
        );
    };
    assert_eq!(target_field, "value");
    assert!(
        matches!(lhs.as_ref(), IrExpr::Member { field, is_arrow: true, .. } if field == "value"),
        "expected the same arrow field on the increment lhs, got {lhs:?}"
    );
    assert!(
        matches!(
            rhs.as_ref(),
            IrExpr::LitInt {
                value: 1,
                ty: IrType {
                    kind: IrTypeKind::Integer {
                        signed: false,
                        width: 32
                    },
                    ..
                },
                ..
            }
        ),
        "expected an unsigned 32-bit increment literal, got {rhs:?}"
    );

    let emitted =
        emit_rust_from_ir_with_globals(&lowered.function_ir, &lowered.globals)
            .expect("emit mutable record pointer u32 postfix increment");
    let rust = &emitted.rust;

    assert_eq!(emitted.route.route, CandidateRoute::GenericTypedIr);
    assert!(rust.contains("pub struct Counter"), "{rust}");
    assert!(rust.contains("pub value: u32"), "{rust}");
    assert!(
        rust.contains("pub fn bump_counter(mut counter: &mut Counter)"),
        "{rust}"
    );
    assert!(
        rust.contains("counter.value = counter.value.wrapping_add(1u32);"),
        "{rust}"
    );
    assert_rust_snippet_runs(
        "typed-ir-clang-ast-fixture-record-pointer-u32-postfix-inc",
        rust,
        "let mut zero = Counter { value: 0u32 };\n\
bump_counter(&mut zero);\n\
assert_eq!(zero.value, 1u32);\n\
let mut ordinary = Counter { value: 41u32 };\n\
bump_counter(&mut ordinary);\n\
assert_eq!(ordinary.value, 42u32);\n\
let mut wrapped = Counter { value: u32::MAX };\n\
bump_counter(&mut wrapped);\n\
assert_eq!(wrapped.value, 0u32);",
    );
}

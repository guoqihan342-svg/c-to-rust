#[cfg(all(feature = "clang-frontend", feature = "typed-ir"))]
#[test]
fn typed_ir_emits_scalar_bit_or_and_left_shift_from_clang_lowered_ir() {
    let uint32_ty = ClangTypeSkeleton {
        spelled: "uint32_t".to_string(),
        canonical: "uint32_t".to_string(),
        kind: ClangTypeKind::Integer {
            signed: false,
            width: 32,
        },
    };
    let shifted = ClangExprSkeleton::Binary {
        op: ClangBinaryOperator::Shl,
        lhs: Box::new(ClangExprSkeleton::DeclRef {
            name: "value".to_string(),
            ty: uint32_ty.clone(),
        }),
        rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
            value: 4,
            spelling: "4U".to_string(),
            ty: uint32_ty.clone(),
        }),
        ty: uint32_ty.clone(),
    };
    let skeleton = ClangFunctionSkeleton {
        name: "pack_flags".to_string(),
        return_type: uint32_ty.clone(),
        params: vec![ClangParamSkeleton {
            name: "value".to_string(),
            ty: uint32_ty.clone(),
        }],
        body: vec![ClangStmtSkeleton::Return {
            value: Some(ClangExprSkeleton::Binary {
                op: ClangBinaryOperator::BitOr,
                lhs: Box::new(shifted),
                rhs: Box::new(ClangExprSkeleton::IntegerLiteral {
                    value: 3,
                    spelling: "3U".to_string(),
                    ty: uint32_ty.clone(),
                }),
                ty: uint32_ty,
            }),
        }],
    };
    let ir = lower_function_skeleton(&skeleton).expect("lower bit-or left-shift skeleton");

    let [IrStmt::Return {
        value:
            Some(IrExpr::Binary {
                op: IrBinOp::BitOr,
                lhs,
                rhs,
                ..
            }),
        ..
    }] = ir.body.as_slice()
    else {
        panic!("expected bit-or return, got {:?}", ir.body);
    };
    assert!(matches!(
        lhs.as_ref(),
        IrExpr::Binary {
            op: IrBinOp::Shl,
            ..
        }
    ));
    assert!(matches!(
        rhs.as_ref(),
        IrExpr::LitInt { value: 3, spelling, .. } if spelling == "3U"
    ));

    let rust = emit_rust_from_ir(&ir).expect("emit bit-or left-shift from lowered typed IR");

    assert!(rust.contains("pub fn pack_flags(value: u32) -> u32"));
    assert!(rust.contains("return (value.checked_shl(core::convert::TryFrom::try_from(4u32).expect(\"shift count must be nonnegative and fit u32\")).expect(\"shift count out of range\") | 3u32);"));
    assert_rust_snippet_compiles("typed-ir-clang-bit-or-left-shift", &rust);
}

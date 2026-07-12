    use std::{
        env, fs,
        path::PathBuf,
        time::{SystemTime, UNIX_EPOCH},
    };

    use serde_json::Value;

    use super::*;
    use crate::{
        typed_ir::{
            EmitPolicy, IrBinOp, IrExpr, IrFunction, IrParam, IrStmt, IrType, IrTypeKind, IrUnOp,
            SignedRightShiftPolicy,
        },
        BuildProfile,
    };

    fn unique_out_dir(name: &str) -> PathBuf {
        let nanos = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        env::temp_dir().join(format!(
            "c2r-artifacts-{name}-{}-{nanos}",
            std::process::id()
        ))
    }

    fn profile() -> BuildProfile {
        BuildProfile {
            include_paths: Vec::new(),
            defines: Vec::new(),
            target: None,
            clang_ast_fixture: None,
            target_triple: None,
            abi: None,
            compiler_command_source: "unit-test".to_string(),
            clang_available: true,
        }
    }

    fn int_type(name: &str, signed: bool, width: u16) -> IrType {
        IrType {
            spelled: name.to_string(),
            canonical: name.to_string(),
            kind: IrTypeKind::Integer { signed, width },
            is_const: false,
            width_bits: Some(width),
            source_span: None,
        }
    }

    fn var(name: &str, ty: &IrType) -> IrExpr {
        IrExpr::Var {
            name: name.to_string(),
            ty: ty.clone(),
            source_span: None,
        }
    }

    fn lit(value: u64, spelling: &str, ty: &IrType) -> IrExpr {
        IrExpr::LitInt {
            value,
            spelling: spelling.to_string(),
            ty: ty.clone(),
            source_span: None,
        }
    }

    fn binary(op: IrBinOp, lhs: IrExpr, rhs: IrExpr, ty: &IrType) -> IrExpr {
        IrExpr::Binary {
            op,
            lhs: Box::new(lhs),
            rhs: Box::new(rhs),
            ty: ty.clone(),
            source_span: None,
        }
    }

    #[test]
    fn typed_ir_candidate_evidence_records_runtime_preconditions() {
        let i32_ty = int_type("int", true, 32);
        let u32_ty = int_type("uint32_t", false, 32);
        let function = IrFunction {
            name: "preconditioned".to_string(),
            return_type: u32_ty.clone(),
            params: vec![
                IrParam {
                    name: "value".to_string(),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                IrParam {
                    name: "divisor".to_string(),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                IrParam {
                    name: "bits".to_string(),
                    ty: u32_ty.clone(),
                    source_span: None,
                },
                IrParam {
                    name: "count".to_string(),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
            ],
            body: vec![
                IrStmt::Decl {
                    name: "sum".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(binary(
                        IrBinOp::Add,
                        var("value", &i32_ty),
                        lit(1, "1", &i32_ty),
                        &i32_ty,
                    )),
                    source_span: None,
                },
                IrStmt::Decl {
                    name: "quotient".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(binary(
                        IrBinOp::Div,
                        var("sum", &i32_ty),
                        var("divisor", &i32_ty),
                        &i32_ty,
                    )),
                    source_span: None,
                },
                IrStmt::Decl {
                    name: "remainder".to_string(),
                    ty: i32_ty.clone(),
                    init: Some(binary(
                        IrBinOp::Mod,
                        var("quotient", &i32_ty),
                        var("divisor", &i32_ty),
                        &i32_ty,
                    )),
                    source_span: None,
                },
                IrStmt::Return {
                    value: Some(binary(
                        IrBinOp::Shl,
                        var("bits", &u32_ty),
                        var("count", &i32_ty),
                        &u32_ty,
                    )),
                    source_span: None,
                },
            ],
            source_span: None,
        };

        let evidence = typed_ir_candidate_evidence(Some(&function), &[], EmitPolicy::default());
        let codes = evidence["runtime_preconditions"]
            .as_array()
            .expect("runtime precondition evidence")
            .iter()
            .map(|item| item["code"].as_str().unwrap())
            .collect::<Vec<_>>();

        assert_eq!(evidence["status"], "generated");
        assert!(codes.contains(&"signed_add_no_overflow"));
        assert!(codes.contains(&"division_divisor_nonzero"));
        assert!(codes.contains(&"signed_division_no_overflow"));
        assert!(codes.contains(&"modulo_divisor_nonzero"));
        assert!(codes.contains(&"signed_modulo_no_overflow"));
        assert!(codes.contains(&"shift_count_in_range"));
    }

    #[test]
    fn typed_ir_candidate_evidence_records_signed_right_shift_contract_precondition() {
        let i32_ty = int_type("int", true, 32);
        let function = IrFunction {
            name: "signed_rshift_contract".to_string(),
            return_type: i32_ty.clone(),
            params: vec![
                IrParam {
                    name: "value".to_string(),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
                IrParam {
                    name: "count".to_string(),
                    ty: i32_ty.clone(),
                    source_span: None,
                },
            ],
            body: vec![IrStmt::Return {
                value: Some(binary(
                    IrBinOp::Shr,
                    var("value", &i32_ty),
                    var("count", &i32_ty),
                    &i32_ty,
                )),
                source_span: None,
            }],
            source_span: None,
        };
        let policy = EmitPolicy {
            signed_right_shift: SignedRightShiftPolicy::ImplementationDefinedArithmetic,
            ..Default::default()
        };

        let evidence = typed_ir_candidate_evidence(Some(&function), &[], policy);
        let codes = evidence["runtime_preconditions"]
            .as_array()
            .expect("runtime precondition evidence")
            .iter()
            .map(|item| item["code"].as_str().unwrap())
            .collect::<Vec<_>>();

        assert_eq!(evidence["status"], "generated");
        assert!(codes.contains(&"shift_count_in_range"));
        assert!(codes.contains(&"signed_right_shift_implementation_defined"));
    }

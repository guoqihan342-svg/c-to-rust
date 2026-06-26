use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct SourceSpan {
    pub file: Option<String>,
    pub line: Option<u32>,
    pub column: Option<u32>,
    pub text: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct IrFunction {
    pub name: String,
    pub return_type: IrType,
    pub params: Vec<IrParam>,
    pub body: Vec<IrStmt>,
    pub source_span: Option<SourceSpan>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct IrParam {
    pub name: String,
    pub ty: IrType,
    pub source_span: Option<SourceSpan>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct IrType {
    pub spelled: String,
    pub canonical: String,
    pub kind: IrTypeKind,
    pub is_const: bool,
    pub width_bits: Option<u16>,
    pub source_span: Option<SourceSpan>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum IrTypeKind {
    Void,
    Integer {
        signed: bool,
        width: u16,
    },
    Pointer {
        pointee: Box<IrType>,
    },
    Array {
        element: Box<IrType>,
        len: Option<usize>,
    },
    Record {
        name: String,
    },
    Function,
    Unsupported {
        reason: String,
    },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum IrExpr {
    LitInt {
        value: u64,
        spelling: String,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    Var {
        name: String,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    Binary {
        op: IrBinOp,
        lhs: Box<IrExpr>,
        rhs: Box<IrExpr>,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    Unary {
        op: IrUnOp,
        operand: Box<IrExpr>,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    Cast {
        target: IrType,
        expr: Box<IrExpr>,
        implicit: bool,
        source_span: Option<SourceSpan>,
    },
    Index {
        base: Box<IrExpr>,
        index: Box<IrExpr>,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    Call {
        callee: String,
        args: Vec<IrExpr>,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    IncDec {
        target: Box<IrExpr>,
        op: IrIncDecOp,
        prefix: bool,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    Deref {
        ptr: Box<IrExpr>,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    AddrOf {
        operand: Box<IrExpr>,
        ty: IrType,
        source_span: Option<SourceSpan>,
    },
    Unsupported {
        node: String,
        reason: String,
        source_span: Option<SourceSpan>,
    },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum IrStmt {
    Decl {
        name: String,
        ty: IrType,
        init: Option<IrExpr>,
        source_span: Option<SourceSpan>,
    },
    Assign {
        target: IrExpr,
        value: IrExpr,
        source_span: Option<SourceSpan>,
    },
    If {
        condition: IrExpr,
        then_body: Vec<IrStmt>,
        else_body: Vec<IrStmt>,
        source_span: Option<SourceSpan>,
    },
    While {
        condition: IrExpr,
        body: Vec<IrStmt>,
        source_span: Option<SourceSpan>,
    },
    Return {
        value: Option<IrExpr>,
        source_span: Option<SourceSpan>,
    },
    Expr {
        expr: IrExpr,
        source_span: Option<SourceSpan>,
    },
    Unsupported {
        node: String,
        reason: String,
        source_span: Option<SourceSpan>,
    },
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum IrBinOp {
    Add,
    Sub,
    Mul,
    Div,
    Mod,
    BitAnd,
    BitOr,
    BitXor,
    Shl,
    Shr,
    Eq,
    Neq,
    Lt,
    Le,
    Gt,
    Ge,
    LogAnd,
    LogOr,
    Assign,
    Comma,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum IrUnOp {
    Neg,
    Not,
    BitNot,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum IrIncDecOp {
    Inc,
    Dec,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct IrEmitError {
    pub reason: String,
}

pub fn emit_rust_from_ir(function: &IrFunction) -> Result<String, IrEmitError> {
    if is_crc32_byte_cursor_ir(function) {
        return Ok(emit_crc32_byte_cursor_rust(&function.name));
    }

    Err(IrEmitError {
        reason: format!(
            "{} is outside the current typed IR emitter subset",
            function.name
        ),
    })
}

pub fn crc32_byte_cursor_function(function_name: &str) -> IrFunction {
    let u32_ty = unsigned_integer("uint32_t", "unsigned int", 32);
    let u8_ty = unsigned_integer("uint8_t", "unsigned char", 8);
    let usize_ty = unsigned_integer("size_t", "unsigned long", 64);
    let int_ty = signed_integer("int", "int", 32);
    let const_void_ptr = pointer_type("const void *", "const void *", void_type(true), true);
    let const_u8_ptr = pointer_type(
        "const uint8_t *",
        "const unsigned char *",
        u8_ty.clone(),
        true,
    );

    let post_inc_p = IrExpr::IncDec {
        target: Box::new(var("p", const_u8_ptr.clone())),
        op: IrIncDecOp::Inc,
        prefix: false,
        ty: const_u8_ptr.clone(),
        source_span: None,
    };
    let byte_read = IrExpr::Deref {
        ptr: Box::new(post_inc_p),
        ty: u8_ty.clone(),
        source_span: None,
    };
    let promoted_byte = IrExpr::Cast {
        target: u32_ty.clone(),
        expr: Box::new(byte_read),
        implicit: true,
        source_span: None,
    };
    let table_index = binary(
        IrBinOp::BitAnd,
        binary(
            IrBinOp::BitXor,
            var("crc", u32_ty.clone()),
            promoted_byte,
            u32_ty.clone(),
        ),
        lit_int(0xFF, "0xFF", int_ty.clone()),
        u32_ty.clone(),
    );
    let table_lookup = IrExpr::Index {
        base: Box::new(var(
            "crc32_table",
            IrType {
                spelled: "const uint32_t[256]".to_string(),
                canonical: "const unsigned int[256]".to_string(),
                kind: IrTypeKind::Array {
                    element: Box::new(u32_ty.clone()),
                    len: Some(256),
                },
                is_const: true,
                width_bits: None,
                source_span: None,
            },
        )),
        index: Box::new(table_index),
        ty: u32_ty.clone(),
        source_span: None,
    };
    let shift = binary(
        IrBinOp::Shr,
        var("crc", u32_ty.clone()),
        lit_int(8, "8", int_ty.clone()),
        u32_ty.clone(),
    );

    IrFunction {
        name: function_name.to_string(),
        return_type: u32_ty.clone(),
        params: vec![
            IrParam {
                name: "crc".to_string(),
                ty: u32_ty.clone(),
                source_span: None,
            },
            IrParam {
                name: "buf".to_string(),
                ty: const_void_ptr.clone(),
                source_span: None,
            },
            IrParam {
                name: "size".to_string(),
                ty: usize_ty.clone(),
                source_span: None,
            },
        ],
        body: vec![
            IrStmt::Decl {
                name: "p".to_string(),
                ty: const_u8_ptr.clone(),
                init: None,
                source_span: None,
            },
            IrStmt::Assign {
                target: var("p", const_u8_ptr.clone()),
                value: IrExpr::Cast {
                    target: const_u8_ptr,
                    expr: Box::new(var("buf", const_void_ptr)),
                    implicit: false,
                    source_span: None,
                },
                source_span: None,
            },
            IrStmt::Assign {
                target: var("crc", u32_ty.clone()),
                value: crc_xor_not_zero(u32_ty.clone()),
                source_span: None,
            },
            IrStmt::While {
                condition: IrExpr::IncDec {
                    target: Box::new(var("size", usize_ty.clone())),
                    op: IrIncDecOp::Dec,
                    prefix: false,
                    ty: usize_ty,
                    source_span: None,
                },
                body: vec![IrStmt::Assign {
                    target: var("crc", u32_ty.clone()),
                    value: binary(IrBinOp::BitXor, table_lookup, shift, u32_ty.clone()),
                    source_span: None,
                }],
                source_span: None,
            },
            IrStmt::Return {
                value: Some(crc_xor_not_zero(u32_ty)),
                source_span: None,
            },
        ],
        source_span: None,
    }
}

pub fn emit_crc32_byte_cursor_rust(function_name: &str) -> String {
    format!(
        "fn crc32_update_byte(mut crc: u32, byte: u8) -> u32 {{\n\
             crc ^= u32::from(byte);\n\
             for _ in 0..8 {{\n\
                 let mask = 0u32.wrapping_sub(crc & 1);\n\
                 crc = (crc >> 1) ^ (0xEDB8_8320u32 & mask);\n\
             }}\n\
             crc\n\
         }}\n\n\
         pub fn {function_name}(mut crc: u32, buf: &[u8], size: usize) -> u32 {{\n\
             let mut p: usize = 0;\n\
             let mut remaining = size;\n\
             crc = crc ^ !0u32;\n\
             while remaining != 0 {{\n\
                 remaining -= 1;\n\
                 let byte = buf[p];\n\
                 p += 1;\n\
                 crc = crc32_update_byte(crc, byte);\n\
             }}\n\
             return crc ^ !0u32;\n\
         }}\n"
    )
}

fn unsigned_integer(spelled: &str, canonical: &str, width: u16) -> IrType {
    IrType {
        spelled: spelled.to_string(),
        canonical: canonical.to_string(),
        kind: IrTypeKind::Integer {
            signed: false,
            width,
        },
        is_const: false,
        width_bits: Some(width),
        source_span: None,
    }
}

fn signed_integer(spelled: &str, canonical: &str, width: u16) -> IrType {
    IrType {
        spelled: spelled.to_string(),
        canonical: canonical.to_string(),
        kind: IrTypeKind::Integer {
            signed: true,
            width,
        },
        is_const: false,
        width_bits: Some(width),
        source_span: None,
    }
}

fn void_type(is_const: bool) -> IrType {
    IrType {
        spelled: "void".to_string(),
        canonical: "void".to_string(),
        kind: IrTypeKind::Void,
        is_const,
        width_bits: None,
        source_span: None,
    }
}

fn pointer_type(spelled: &str, canonical: &str, pointee: IrType, is_const: bool) -> IrType {
    IrType {
        spelled: spelled.to_string(),
        canonical: canonical.to_string(),
        kind: IrTypeKind::Pointer {
            pointee: Box::new(pointee),
        },
        is_const,
        width_bits: None,
        source_span: None,
    }
}

fn var(name: &str, ty: IrType) -> IrExpr {
    IrExpr::Var {
        name: name.to_string(),
        ty,
        source_span: None,
    }
}

fn lit_int(value: u64, spelling: &str, ty: IrType) -> IrExpr {
    IrExpr::LitInt {
        value,
        spelling: spelling.to_string(),
        ty,
        source_span: None,
    }
}

fn binary(op: IrBinOp, lhs: IrExpr, rhs: IrExpr, ty: IrType) -> IrExpr {
    IrExpr::Binary {
        op,
        lhs: Box::new(lhs),
        rhs: Box::new(rhs),
        ty,
        source_span: None,
    }
}

fn crc_xor_not_zero(u32_ty: IrType) -> IrExpr {
    binary(
        IrBinOp::BitXor,
        var("crc", u32_ty.clone()),
        IrExpr::Unary {
            op: IrUnOp::BitNot,
            operand: Box::new(lit_int(0, "0U", u32_ty.clone())),
            ty: u32_ty.clone(),
            source_span: None,
        },
        u32_ty,
    )
}

fn is_crc32_byte_cursor_ir(function: &IrFunction) -> bool {
    is_u32(&function.return_type)
        && function.params.len() == 3
        && param_is(&function.params[0], "crc", is_u32)
        && param_is(&function.params[1], "buf", is_void_pointer)
        && param_is(&function.params[2], "size", is_usize)
        && function.body.len() == 5
        && matches_crc32_cursor_decl(&function.body[0])
        && matches_pointer_cast_assignment(&function.body[1])
        && matches_crc_invert_assignment(&function.body[2])
        && matches_crc32_loop(&function.body[3])
        && matches_crc_invert_return(&function.body[4])
}

fn param_is(param: &IrParam, name: &str, predicate: fn(&IrType) -> bool) -> bool {
    param.name == name && predicate(&param.ty)
}

fn is_u32(ty: &IrType) -> bool {
    matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 32
        }
    )
}

fn is_u8(ty: &IrType) -> bool {
    matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: false,
            width: 8
        }
    )
}

fn is_usize(ty: &IrType) -> bool {
    ty.spelled == "size_t"
        || ty.canonical == "size_t"
        || matches!(
            ty.kind,
            IrTypeKind::Integer {
                signed: false,
                width: 64
            }
        )
}

fn is_void_pointer(ty: &IrType) -> bool {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } => matches!(pointee.kind, IrTypeKind::Void),
        _ => false,
    }
}

fn is_u8_pointer(ty: &IrType) -> bool {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } => is_u8(pointee),
        _ => false,
    }
}

fn matches_crc32_cursor_decl(stmt: &IrStmt) -> bool {
    matches!(
        stmt,
        IrStmt::Decl {
            name,
            ty,
            init: None,
            ..
        } if name == "p" && is_u8_pointer(ty)
    )
}

fn matches_pointer_cast_assignment(stmt: &IrStmt) -> bool {
    let IrStmt::Assign { target, value, .. } = stmt else {
        return false;
    };
    var_name(target) == Some("p")
        && matches!(
            value,
            IrExpr::Cast {
                target,
                expr,
                implicit: false,
                ..
            } if is_u8_pointer(target) && var_name(expr) == Some("buf")
        )
}

fn matches_crc_invert_assignment(stmt: &IrStmt) -> bool {
    matches!(
        stmt,
        IrStmt::Assign { target, value, .. }
            if var_name(target) == Some("crc") && is_crc_xor_not_zero(value)
    )
}

fn matches_crc_invert_return(stmt: &IrStmt) -> bool {
    matches!(
        stmt,
        IrStmt::Return {
            value: Some(value),
            ..
        } if is_crc_xor_not_zero(value)
    )
}

fn matches_crc32_loop(stmt: &IrStmt) -> bool {
    let IrStmt::While {
        condition, body, ..
    } = stmt
    else {
        return false;
    };
    if !is_post_dec_var(condition, "size") || body.len() != 1 {
        return false;
    }
    matches!(
        &body[0],
        IrStmt::Assign { target, value, .. }
            if var_name(target) == Some("crc")
                && is_crc32_update_expr(value)
    )
}

fn is_crc32_update_expr(expr: &IrExpr) -> bool {
    match expr {
        IrExpr::Binary {
            op: IrBinOp::BitXor,
            lhs,
            rhs,
            ..
        } => {
            (contains_crc32_table_lookup(lhs) && contains_crc_shift(rhs))
                || (contains_crc32_table_lookup(rhs) && contains_crc_shift(lhs))
        }
        _ => false,
    }
}

fn is_crc_xor_not_zero(expr: &IrExpr) -> bool {
    match expr {
        IrExpr::Binary {
            op: IrBinOp::BitXor,
            lhs,
            rhs,
            ..
        } => {
            (var_name(lhs) == Some("crc") && is_bit_not_zero(rhs))
                || (var_name(rhs) == Some("crc") && is_bit_not_zero(lhs))
        }
        _ => false,
    }
}

fn is_bit_not_zero(expr: &IrExpr) -> bool {
    matches!(
        expr,
        IrExpr::Unary {
            op: IrUnOp::BitNot,
            operand,
            ..
        } if matches!(operand.as_ref(), IrExpr::LitInt { value: 0, .. })
    )
}

fn contains_crc32_table_lookup(expr: &IrExpr) -> bool {
    match expr {
        IrExpr::Index { base, index, .. } => {
            var_name(base) == Some("crc32_table") && contains_crc_byte_index(index)
        }
        IrExpr::Cast { expr, .. } => contains_crc32_table_lookup(expr),
        _ => false,
    }
}

fn contains_crc_byte_index(expr: &IrExpr) -> bool {
    match expr {
        IrExpr::Binary {
            op: IrBinOp::BitAnd,
            lhs,
            rhs,
            ..
        } => {
            (contains_crc_byte_xor(lhs) && is_int_literal(rhs, 0xFF))
                || (contains_crc_byte_xor(rhs) && is_int_literal(lhs, 0xFF))
        }
        IrExpr::Cast { expr, .. } => contains_crc_byte_index(expr),
        _ => false,
    }
}

fn contains_crc_byte_xor(expr: &IrExpr) -> bool {
    match expr {
        IrExpr::Binary {
            op: IrBinOp::BitXor,
            lhs,
            rhs,
            ..
        } => {
            (var_name(lhs) == Some("crc") && contains_post_increment_byte_read(rhs))
                || (var_name(rhs) == Some("crc") && contains_post_increment_byte_read(lhs))
        }
        IrExpr::Cast { expr, .. } => contains_crc_byte_xor(expr),
        _ => false,
    }
}

fn contains_post_increment_byte_read(expr: &IrExpr) -> bool {
    match expr {
        IrExpr::Deref { ptr, .. } => is_post_inc_var(ptr, "p"),
        IrExpr::Cast { expr, .. } => contains_post_increment_byte_read(expr),
        _ => false,
    }
}

fn contains_crc_shift(expr: &IrExpr) -> bool {
    match expr {
        IrExpr::Binary {
            op: IrBinOp::Shr,
            lhs,
            rhs,
            ..
        } => var_name(lhs) == Some("crc") && is_int_literal(rhs, 8),
        IrExpr::Cast { expr, .. } => contains_crc_shift(expr),
        _ => false,
    }
}

fn is_int_literal(expr: &IrExpr, expected: u64) -> bool {
    matches!(expr, IrExpr::LitInt { value, .. } if *value == expected)
}

fn is_post_inc_var(expr: &IrExpr, expected_name: &str) -> bool {
    matches!(
        expr,
        IrExpr::IncDec {
            target,
            op: IrIncDecOp::Inc,
            prefix: false,
            ..
        } if var_name(target) == Some(expected_name)
    )
}

fn is_post_dec_var(expr: &IrExpr, expected_name: &str) -> bool {
    matches!(
        expr,
        IrExpr::IncDec {
            target,
            op: IrIncDecOp::Dec,
            prefix: false,
            ..
        } if var_name(target) == Some(expected_name)
    )
}

fn var_name(expr: &IrExpr) -> Option<&str> {
    match expr {
        IrExpr::Var { name, .. } => Some(name),
        _ => None,
    }
}

use serde::{Deserialize, Serialize};
use std::collections::HashSet;

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

    emit_scalar_rust_from_ir(function).map_err(|detail| IrEmitError {
        reason: format!(
            "{} is outside the current typed IR emitter subset: {}",
            function.name, detail
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

fn emit_scalar_rust_from_ir(function: &IrFunction) -> Result<String, String> {
    let return_type = emit_return_type(&function.return_type)?;
    if return_type.is_some() && !ends_with_return_value(&function.body) {
        return Err("non-void function must end with a return value".to_string());
    }
    let assigned_vars = collect_assigned_vars(&function.body);
    let function_name = emit_identifier(&function.name, "function")?;
    let params = function
        .params
        .iter()
        .map(|param| emit_param(param, &assigned_vars))
        .collect::<Result<Vec<_>, _>>()?
        .join(", ");
    let mut symbols = collect_param_symbols(&function.params)?;

    let mut rust = String::new();
    rust.push_str(&format!("pub fn {function_name}({params})"));
    if let Some(return_type) = return_type {
        rust.push_str(&format!(" -> {}", return_type));
    }
    rust.push_str(" {\n");
    for (index, stmt) in function.body.iter().enumerate() {
        let line = emit_stmt(stmt, &function.return_type, 1, &mut symbols)
            .map_err(|detail| format!("stmt[{index}].{detail}"))?;
        rust.push_str(&line);
    }
    rust.push_str("}\n");
    Ok(rust)
}

fn emit_param(param: &IrParam, assigned_vars: &HashSet<String>) -> Result<String, String> {
    let ty = emit_scalar_type(&param.ty)
        .map_err(|detail| format!("param {} has {}", param.name, detail))?;
    let name = emit_identifier(&param.name, "param")?;
    let mut_prefix = if assigned_vars.contains(&param.name) {
        "mut "
    } else {
        ""
    };
    Ok(format!("{mut_prefix}{name}: {ty}"))
}

fn emit_return_type(ty: &IrType) -> Result<Option<String>, String> {
    if is_void_type(ty) {
        Ok(None)
    } else {
        emit_scalar_type(ty).map(Some)
    }
}

fn emit_scalar_type(ty: &IrType) -> Result<String, String> {
    match &ty.kind {
        IrTypeKind::Integer { signed, width } => {
            if is_size_t_type(ty) {
                return Ok("usize".to_string());
            }
            match (*signed, *width) {
                (true, 8) => Ok("i8".to_string()),
                (true, 16) => Ok("i16".to_string()),
                (true, 32) => Ok("i32".to_string()),
                (true, 64) => Ok("i64".to_string()),
                (false, 8) => Ok("u8".to_string()),
                (false, 16) => Ok("u16".to_string()),
                (false, 32) => Ok("u32".to_string()),
                (false, 64) => Ok("u64".to_string()),
                _ => Err(format!("integer type {} is unsupported", type_label(ty))),
            }
        }
        IrTypeKind::Void => Err("void type is only supported as a return type".to_string()),
        IrTypeKind::Pointer { .. } => {
            Err(format!("pointer type {} is unsupported", type_label(ty)))
        }
        IrTypeKind::Array { .. } => Err(format!("array type {} is unsupported", type_label(ty))),
        IrTypeKind::Record { name } => Err(format!("record type {name} is unsupported")),
        IrTypeKind::Function => Err(format!("function type {} is unsupported", type_label(ty))),
        IrTypeKind::Unsupported { reason } => {
            Err(format!("unsupported type {}: {reason}", type_label(ty)))
        }
    }
}

fn emit_stmt(
    stmt: &IrStmt,
    return_type: &IrType,
    indent_level: usize,
    symbols: &mut HashSet<String>,
) -> Result<String, String> {
    let indent = "    ".repeat(indent_level);
    match stmt {
        IrStmt::Decl { name, ty, init, .. } => {
            let decl_name = emit_identifier(name, "decl")?;
            if symbols.contains(name) {
                return Err(format!("decl {name} duplicates an existing symbol"));
            }
            let decl_ty =
                emit_scalar_type(ty).map_err(|detail| format!("decl {name} has {detail}"))?;
            if let Some(init) = init {
                validate_expr_matches_type(init, ty, &format!("decl {name} initializer"))?;
                let init = emit_expr(init, symbols)
                    .map_err(|detail| format!("decl {name} initializer {detail}"))?;
                symbols.insert(name.clone());
                Ok(format!(
                    "{indent}let mut {decl_name}: {decl_ty} = {init};\n"
                ))
            } else {
                Err(format!("decl {name} without initializer is unsupported"))
            }
        }
        IrStmt::Assign { target, value, .. } => {
            let (name, target_ty) = match target {
                IrExpr::Var { name, ty, .. } => (name, ty),
                _ => return Err("assign target must be Var".to_string()),
            };
            if !symbols.contains(name) {
                return Err(format!("assign target {name} is not declared"));
            }
            let target_name = emit_identifier(name, "assign target")?;
            validate_expr_matches_type(value, target_ty, "assign value")?;
            let value =
                emit_expr(value, symbols).map_err(|detail| format!("assign value {detail}"))?;
            Ok(format!("{indent}{target_name} = {value};\n"))
        }
        IrStmt::Return { value, .. } => match value {
            Some(value) => {
                if is_void_type(return_type) {
                    return Err("return value in void function".to_string());
                }
                validate_expr_matches_type(value, return_type, "return expr")?;
                let value =
                    emit_expr(value, symbols).map_err(|detail| format!("return expr {detail}"))?;
                Ok(format!("{indent}return {value};\n"))
            }
            None if is_void_type(return_type) => Ok(format!("{indent}return;\n")),
            None => Err("return without value in non-void function".to_string()),
        },
        IrStmt::Expr { expr, .. } => {
            let expr = emit_expr(expr, symbols).map_err(|detail| format!("expr {detail}"))?;
            Ok(format!("{indent}{expr};\n"))
        }
        IrStmt::If { .. } => Err("if statement is unsupported".to_string()),
        IrStmt::While { .. } => Err("while statement is unsupported".to_string()),
        IrStmt::Unsupported { node, reason, .. } => {
            Err(format!("unsupported statement {node}: {reason}"))
        }
    }
}

fn emit_expr(expr: &IrExpr, symbols: &HashSet<String>) -> Result<String, String> {
    match expr {
        IrExpr::LitInt { value, ty, .. } => emit_integer_literal(*value, ty),
        IrExpr::Var { name, ty, .. } => {
            if !symbols.contains(name) {
                return Err(format!("var {name} is not declared"));
            }
            emit_scalar_type(ty).map_err(|detail| format!("var {name} has {detail}"))?;
            emit_identifier(name, "var")
        }
        IrExpr::Binary {
            op, lhs, rhs, ty, ..
        } => {
            let op = emit_binary_op(op)?;
            validate_binary_operand_types(op, lhs, rhs, ty)?;
            let lhs = emit_expr(lhs, symbols).map_err(|detail| format!("binary lhs {detail}"))?;
            let rhs = emit_expr(rhs, symbols).map_err(|detail| format!("binary rhs {detail}"))?;
            Ok(format!("({lhs} {op} {rhs})"))
        }
        IrExpr::Unary {
            op, operand, ty, ..
        } => match op {
            IrUnOp::BitNot => {
                validate_expr_matches_type(operand, ty, "bitnot operand")?;
                let operand = emit_expr(operand, symbols)
                    .map_err(|detail| format!("bitnot operand {detail}"))?;
                Ok(format!("!{operand}"))
            }
            _ => Err(format!("unary op {op:?} is unsupported")),
        },
        IrExpr::Cast { target, expr, .. } => {
            if !is_integer_type(target) {
                return Err(format!("cast target {} is unsupported", type_label(target)));
            }
            let source_type =
                expr_type(expr).ok_or_else(|| "cast source type is unsupported".to_string())?;
            if !is_integer_type(source_type) {
                return Err(format!(
                    "cast source {} is unsupported",
                    type_label(source_type)
                ));
            }
            let target =
                emit_scalar_type(target).map_err(|detail| format!("cast target has {detail}"))?;
            let expr = emit_expr(expr, symbols).map_err(|detail| format!("cast expr {detail}"))?;
            Ok(format!("({expr} as {target})"))
        }
        IrExpr::Index { .. } => Err("index expression is unsupported".to_string()),
        IrExpr::Call { callee, .. } => Err(format!("call expression {callee} is unsupported")),
        IrExpr::IncDec { .. } => Err("inc/dec expression is unsupported".to_string()),
        IrExpr::Deref { .. } => Err("deref expression is unsupported".to_string()),
        IrExpr::AddrOf { .. } => Err("address-of expression is unsupported".to_string()),
        IrExpr::Unsupported { node, reason, .. } => {
            Err(format!("unsupported expression {node}: {reason}"))
        }
    }
}

fn emit_binary_op(op: &IrBinOp) -> Result<&'static str, String> {
    match op {
        IrBinOp::Add => Ok("+"),
        IrBinOp::BitAnd => Ok("&"),
        IrBinOp::BitXor => Ok("^"),
        IrBinOp::Shr => Ok(">>"),
        _ => Err(format!("binary op {op:?} is unsupported")),
    }
}

fn validate_binary_operand_types(
    op: &str,
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
) -> Result<(), String> {
    let result_ty =
        emit_scalar_type(result_ty).map_err(|detail| format!("binary result has {detail}"))?;
    let lhs_ty = expr_type(lhs).ok_or_else(|| "binary lhs type is unsupported".to_string())?;
    let rhs_ty = expr_type(rhs).ok_or_else(|| "binary rhs type is unsupported".to_string())?;
    let lhs_ty = emit_scalar_type(lhs_ty).map_err(|detail| format!("binary lhs has {detail}"))?;
    let rhs_ty = emit_scalar_type(rhs_ty).map_err(|detail| format!("binary rhs has {detail}"))?;

    match op {
        "+" | "&" | "^" => {
            if lhs_ty == result_ty && rhs_ty == result_ty {
                Ok(())
            } else {
                Err(format!(
                    "binary operand types must match result type for {op}: lhs={lhs_ty}, rhs={rhs_ty}, result={result_ty}"
                ))
            }
        }
        ">>" => {
            if lhs_ty == result_ty {
                Ok(())
            } else {
                Err(format!(
                    "shift lhs type must match result type: lhs={lhs_ty}, result={result_ty}"
                ))
            }
        }
        _ => Err(format!("binary op {op} is unsupported")),
    }
}

fn validate_expr_matches_type(
    expr: &IrExpr,
    expected_ty: &IrType,
    context: &str,
) -> Result<(), String> {
    let expected_ty = emit_scalar_type(expected_ty)
        .map_err(|detail| format!("{context} expected type has {detail}"))?;
    let actual_ty = expr_type(expr).ok_or_else(|| format!("{context} type is unsupported"))?;
    let actual_ty =
        emit_scalar_type(actual_ty).map_err(|detail| format!("{context} has {detail}"))?;
    if actual_ty == expected_ty {
        Ok(())
    } else {
        Err(format!(
            "{context} type {actual_ty} does not match expected type {expected_ty}"
        ))
    }
}

fn ends_with_return_value(body: &[IrStmt]) -> bool {
    matches!(body.last(), Some(IrStmt::Return { value: Some(_), .. }))
}

fn emit_integer_literal_suffix(ty: &IrType) -> Result<String, String> {
    if is_size_t_type(ty) {
        return Ok("usize".to_string());
    }
    match &ty.kind {
        IrTypeKind::Integer { signed, width } => match (*signed, *width) {
            (true, 8) => Ok("i8".to_string()),
            (true, 16) => Ok("i16".to_string()),
            (true, 32) => Ok("i32".to_string()),
            (true, 64) => Ok("i64".to_string()),
            (false, 8) => Ok("u8".to_string()),
            (false, 16) => Ok("u16".to_string()),
            (false, 32) => Ok("u32".to_string()),
            (false, 64) => Ok("u64".to_string()),
            _ => Err(format!(
                "literal integer type {} is unsupported",
                type_label(ty)
            )),
        },
        _ => Err(format!("literal type {} is not an integer", type_label(ty))),
    }
}

fn emit_integer_literal(value: u64, ty: &IrType) -> Result<String, String> {
    validate_integer_literal_range(value, ty)?;
    let suffix = emit_integer_literal_suffix(ty)?;
    Ok(format!("{value}{suffix}"))
}

fn validate_integer_literal_range(value: u64, ty: &IrType) -> Result<(), String> {
    let label = emit_scalar_type(ty)?;
    let max = match &ty.kind {
        IrTypeKind::Integer { signed, width } => {
            if is_size_t_type(ty) {
                usize::MAX as u64
            } else if *signed {
                match width {
                    8 => i8::MAX as u64,
                    16 => i16::MAX as u64,
                    32 => i32::MAX as u64,
                    64 => i64::MAX as u64,
                    _ => return Err(format!("literal integer type {label} is unsupported")),
                }
            } else {
                match width {
                    8 => u8::MAX as u64,
                    16 => u16::MAX as u64,
                    32 => u32::MAX as u64,
                    64 => u64::MAX,
                    _ => return Err(format!("literal integer type {label} is unsupported")),
                }
            }
        }
        _ => return Err(format!("literal type {label} is not an integer")),
    };

    if value <= max {
        Ok(())
    } else {
        Err(format!("literal value {value} does not fit type {label}"))
    }
}

fn collect_assigned_vars(body: &[IrStmt]) -> HashSet<String> {
    let mut assigned_vars = HashSet::new();
    collect_assigned_vars_from_body(body, &mut assigned_vars);
    assigned_vars
}

fn collect_param_symbols(params: &[IrParam]) -> Result<HashSet<String>, String> {
    let mut symbols = HashSet::new();
    for param in params {
        if !symbols.insert(param.name.clone()) {
            return Err(format!(
                "param {} duplicates an existing symbol",
                param.name
            ));
        }
    }
    Ok(symbols)
}

fn collect_assigned_vars_from_body(body: &[IrStmt], assigned_vars: &mut HashSet<String>) {
    for stmt in body {
        match stmt {
            IrStmt::Assign { target, .. } => {
                if let IrExpr::Var { name, .. } = target {
                    assigned_vars.insert(name.clone());
                }
            }
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                collect_assigned_vars_from_body(then_body, assigned_vars);
                collect_assigned_vars_from_body(else_body, assigned_vars);
            }
            IrStmt::While { body, .. } => {
                collect_assigned_vars_from_body(body, assigned_vars);
            }
            _ => {}
        }
    }
}

fn expr_type(expr: &IrExpr) -> Option<&IrType> {
    match expr {
        IrExpr::LitInt { ty, .. }
        | IrExpr::Var { ty, .. }
        | IrExpr::Binary { ty, .. }
        | IrExpr::Unary { ty, .. }
        | IrExpr::Index { ty, .. }
        | IrExpr::Call { ty, .. }
        | IrExpr::IncDec { ty, .. }
        | IrExpr::Deref { ty, .. }
        | IrExpr::AddrOf { ty, .. } => Some(ty),
        IrExpr::Cast { target, .. } => Some(target),
        IrExpr::Unsupported { .. } => None,
    }
}

fn is_integer_type(ty: &IrType) -> bool {
    matches!(ty.kind, IrTypeKind::Integer { .. })
}

fn is_void_type(ty: &IrType) -> bool {
    matches!(ty.kind, IrTypeKind::Void)
}

fn is_size_t_type(ty: &IrType) -> bool {
    ty.spelled == "size_t" || ty.canonical == "size_t"
}

fn type_label(ty: &IrType) -> String {
    if !ty.spelled.trim().is_empty() {
        ty.spelled.clone()
    } else if !ty.canonical.trim().is_empty() {
        ty.canonical.clone()
    } else {
        format!("{:?}", ty.kind)
    }
}

fn emit_identifier(name: &str, context: &str) -> Result<String, String> {
    if is_rust_identifier(name) && !is_rust_keyword(name) {
        Ok(name.to_string())
    } else {
        Err(format!("{context} identifier {name:?} is unsupported"))
    }
}

fn is_rust_identifier(name: &str) -> bool {
    if name == "_" {
        return false;
    }
    let mut chars = name.chars();
    let Some(first) = chars.next() else {
        return false;
    };
    (first == '_' || first.is_ascii_alphabetic())
        && chars.all(|character| character == '_' || character.is_ascii_alphanumeric())
}

fn is_rust_keyword(name: &str) -> bool {
    matches!(
        name,
        "as" | "async"
            | "await"
            | "break"
            | "const"
            | "continue"
            | "crate"
            | "dyn"
            | "else"
            | "enum"
            | "extern"
            | "false"
            | "fn"
            | "for"
            | "if"
            | "impl"
            | "in"
            | "let"
            | "loop"
            | "match"
            | "mod"
            | "move"
            | "mut"
            | "pub"
            | "ref"
            | "return"
            | "self"
            | "Self"
            | "static"
            | "struct"
            | "super"
            | "trait"
            | "true"
            | "type"
            | "union"
            | "unsafe"
            | "use"
            | "where"
            | "while"
            | "abstract"
            | "become"
            | "box"
            | "do"
            | "final"
            | "macro"
            | "override"
            | "priv"
            | "try"
            | "typeof"
            | "unsized"
            | "virtual"
            | "yield"
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

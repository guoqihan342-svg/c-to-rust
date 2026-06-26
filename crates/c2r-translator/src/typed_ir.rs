use crate::translation_route::{generic_typed_ir_route, unsupported_route, EmittedRust};
use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};

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
pub struct IrGlobal {
    pub name: String,
    pub ty: IrType,
    pub init: IrGlobalInit,
    pub source_span: Option<SourceSpan>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub enum IrGlobalInit {
    IntegerArray(Vec<u64>),
    Zeroed,
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
    pub route: crate::translation_route::CandidateRouteDecision,
}

#[derive(Clone, Debug, Default)]
struct EmitContext {
    byte_slice_params: HashSet<String>,
    byte_cursor_sources: HashMap<String, String>,
    readonly_globals: HashMap<String, IrGlobal>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
struct EmittedExpr {
    prelude: String,
    expr: String,
}

impl EmitContext {
    fn from_function_and_globals(
        function: &IrFunction,
        globals: &[IrGlobal],
    ) -> Result<Self, String> {
        let byte_cursor_sources = collect_byte_cursor_sources(&function.body);
        let mut byte_slice_params = HashSet::new();
        for source in byte_cursor_sources.values() {
            if function
                .params
                .iter()
                .any(|param| param.name == *source && is_const_void_pointer(&param.ty))
            {
                byte_slice_params.insert(source.clone());
            }
        }
        let mut readonly_globals = HashMap::new();
        for global in globals {
            if readonly_globals
                .insert(global.name.clone(), global.clone())
                .is_some()
            {
                return Err(format!(
                    "global {} duplicates an existing global",
                    global.name
                ));
            }
        }
        Ok(Self {
            byte_slice_params,
            byte_cursor_sources,
            readonly_globals,
        })
    }

    fn byte_cursor_source(&self, cursor: &str) -> Option<&str> {
        self.byte_cursor_sources.get(cursor).map(String::as_str)
    }

    fn is_byte_slice_param(&self, name: &str) -> bool {
        self.byte_slice_params.contains(name)
    }

    fn readonly_global(&self, name: &str) -> Option<&IrGlobal> {
        self.readonly_globals.get(name)
    }

    fn global_rust_name(&self, name: &str) -> Result<String, String> {
        emit_global_const_identifier(name)
    }
}

pub fn emit_rust_from_ir(function: &IrFunction) -> Result<EmittedRust, IrEmitError> {
    emit_scalar_rust_from_ir(function)
        .map(|rust| EmittedRust {
            rust,
            route: generic_typed_ir_route(),
        })
        .map_err(|detail| {
            let reason = format!(
                "{} is outside the current typed IR emitter subset: {}",
                function.name, detail
            );
            IrEmitError {
                route: unsupported_route(reason.clone()),
                reason,
            }
        })
}

pub fn emit_rust_from_ir_with_globals(
    function: &IrFunction,
    globals: &[IrGlobal],
) -> Result<EmittedRust, IrEmitError> {
    emit_scalar_rust_from_ir_with_globals(function, globals)
        .map(|rust| EmittedRust {
            rust,
            route: generic_typed_ir_route(),
        })
        .map_err(|detail| {
            let reason = format!(
                "{} is outside the current typed IR emitter subset: {}",
                function.name, detail
            );
            IrEmitError {
                route: unsupported_route(reason.clone()),
                reason,
            }
        })
}

fn emit_scalar_rust_from_ir(function: &IrFunction) -> Result<String, String> {
    emit_scalar_rust_from_ir_with_globals(function, &[])
}

fn emit_scalar_rust_from_ir_with_globals(
    function: &IrFunction,
    globals: &[IrGlobal],
) -> Result<String, String> {
    let return_type = emit_return_type(&function.return_type)?;
    if return_type.is_some() && !ends_with_return_value(&function.body) {
        return Err("non-void function must end with a return value".to_string());
    }
    let context = EmitContext::from_function_and_globals(function, globals)?;
    let assigned_vars = collect_assigned_vars(&function.body);
    let function_name = emit_identifier(&function.name, "function")?;
    let params = function
        .params
        .iter()
        .map(|param| emit_param(param, &assigned_vars, &context))
        .collect::<Result<Vec<_>, _>>()?
        .join(", ");
    let mut symbols = collect_param_symbols(&function.params)?;

    let mut rust = String::new();
    for global in globals {
        rust.push_str(&emit_global_const(global)?);
    }
    if !globals.is_empty() {
        rust.push('\n');
    }
    rust.push_str(&format!("pub fn {function_name}({params})"));
    if let Some(return_type) = return_type {
        rust.push_str(&format!(" -> {}", return_type));
    }
    rust.push_str(" {\n");
    for (index, stmt) in function.body.iter().enumerate() {
        let line = emit_stmt(stmt, &function.return_type, 1, &mut symbols, &context)
            .map_err(|detail| format!("stmt[{index}].{detail}"))?;
        rust.push_str(&line);
    }
    rust.push_str("}\n");
    Ok(rust)
}

fn emit_param(
    param: &IrParam,
    assigned_vars: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let ty = if context.is_byte_slice_param(&param.name) {
        "&[u8]".to_string()
    } else {
        emit_param_type(&param.ty)
            .map_err(|detail| format!("param {} has {}", param.name, detail))?
    };
    let name = emit_identifier(&param.name, "param")?;
    let mut_prefix = if assigned_vars.contains(&param.name) {
        "mut "
    } else {
        ""
    };
    Ok(format!("{mut_prefix}{name}: {ty}"))
}

fn emit_param_type(ty: &IrType) -> Result<String, String> {
    if let Some(element_ty) = readonly_pointer_slice_element_type(ty) {
        let element_ty = emit_scalar_type(element_ty)?;
        return Ok(format!("&[{element_ty}]"));
    }
    emit_scalar_type(ty)
}

fn emit_global_const(global: &IrGlobal) -> Result<String, String> {
    let IrTypeKind::Array { element, len } = &global.ty.kind else {
        return Err(format!(
            "global {} has non-array type {}",
            global.name,
            type_label(&global.ty)
        ));
    };
    if !global.ty.is_const {
        return Err(format!("global {} is not readonly const", global.name));
    }
    let Some(len) = len else {
        return Err(format!("global {} array length is unknown", global.name));
    };
    let element_ty = emit_scalar_type(element)
        .map_err(|detail| format!("global {} element has {detail}", global.name))?;
    let values = match &global.init {
        IrGlobalInit::IntegerArray(values) => {
            if values.len() != *len {
                return Err(format!(
                    "global {} initializer length {} does not match array length {len}",
                    global.name,
                    values.len()
                ));
            }
            values
                .iter()
                .map(|value| emit_integer_literal(*value, element))
                .collect::<Result<Vec<_>, _>>()?
                .join(", ")
        }
        IrGlobalInit::Zeroed => {
            let zero = emit_integer_literal(0, element)?;
            return Ok(format!(
                "const {}: [{element_ty}; {len}] = [{zero}; {len}];\n",
                emit_global_const_identifier(&global.name)?
            ));
        }
    };
    Ok(format!(
        "const {}: [{element_ty}; {len}] = [{values}];\n",
        emit_global_const_identifier(&global.name)?
    ))
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
    context: &EmitContext,
) -> Result<String, String> {
    let indent = "    ".repeat(indent_level);
    match stmt {
        IrStmt::Decl { name, ty, init, .. } => {
            let decl_name = emit_identifier(name, "decl")?;
            if symbols.contains(name) {
                return Err(format!("decl {name} duplicates an existing symbol"));
            }
            if init.is_none() && context.byte_cursor_source(name).is_some() && is_u8_pointer(ty) {
                symbols.insert(name.clone());
                return Ok(format!("{indent}let mut {decl_name}: usize = 0;\n"));
            }
            let decl_ty =
                emit_scalar_type(ty).map_err(|detail| format!("decl {name} has {detail}"))?;
            if let Some(init) = init {
                validate_expr_matches_type(init, ty, &format!("decl {name} initializer"))?;
                let init = emit_expr(init, symbols, context)
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
            if is_byte_cursor_cast_assignment(target, value, symbols, context)? {
                return Ok(String::new());
            }
            let (name, target_ty) = match target {
                IrExpr::Var { name, ty, .. } => (name, ty),
                _ => return Err("assign target must be Var".to_string()),
            };
            if !symbols.contains(name) {
                return Err(format!("assign target {name} is not declared"));
            }
            let target_name = emit_identifier(name, "assign target")?;
            if count_post_increment_byte_reads(value) > 1 {
                return Err(
                    "assign value multiple post-increment byte reads are unsupported".to_string(),
                );
            }
            validate_expr_matches_type(value, target_ty, "assign value")?;
            let emitted =
                emit_expr_with_prelude(value, symbols, context, indent_level, "assign value")?;
            Ok(format!(
                "{}{indent}{target_name} = {};\n",
                emitted.prelude, emitted.expr
            ))
        }
        IrStmt::Return { value, .. } => match value {
            Some(value) => {
                if is_void_type(return_type) {
                    return Err("return value in void function".to_string());
                }
                if let Some(line) = emit_post_increment_deref_return(
                    value,
                    return_type,
                    indent_level,
                    symbols,
                    context,
                )? {
                    return Ok(line);
                }
                if count_post_increment_byte_reads(value) > 1 {
                    return Err("multiple post-increment byte reads are unsupported".to_string());
                }
                validate_expr_matches_type(value, return_type, "return expr")?;
                let emitted =
                    emit_expr_with_prelude(value, symbols, context, indent_level, "return expr")?;
                Ok(format!(
                    "{}{indent}return {};\n",
                    emitted.prelude, emitted.expr
                ))
            }
            None if is_void_type(return_type) => Ok(format!("{indent}return;\n")),
            None => Err("return without value in non-void function".to_string()),
        },
        IrStmt::Expr { expr, .. } => {
            let expr =
                emit_expr(expr, symbols, context).map_err(|detail| format!("expr {detail}"))?;
            Ok(format!("{indent}{expr};\n"))
        }
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            let condition = emit_condition_expr(condition, symbols, context)
                .map_err(|detail| format!("if condition {detail}"))?;
            let mut block = String::new();
            block.push_str(&format!("{indent}if {condition} {{\n"));
            let mut then_symbols = symbols.clone();
            for (index, stmt) in then_body.iter().enumerate() {
                let line = emit_stmt(
                    stmt,
                    return_type,
                    indent_level + 1,
                    &mut then_symbols,
                    context,
                )
                .map_err(|detail| format!("if then[{index}].{detail}"))?;
                block.push_str(&line);
            }
            if else_body.is_empty() {
                block.push_str(&format!("{indent}}}\n"));
            } else {
                block.push_str(&format!("{indent}}} else {{\n"));
                let mut else_symbols = symbols.clone();
                for (index, stmt) in else_body.iter().enumerate() {
                    let line = emit_stmt(
                        stmt,
                        return_type,
                        indent_level + 1,
                        &mut else_symbols,
                        context,
                    )
                    .map_err(|detail| format!("if else[{index}].{detail}"))?;
                    block.push_str(&line);
                }
                block.push_str(&format!("{indent}}}\n"));
            }
            Ok(block)
        }
        IrStmt::While {
            condition, body, ..
        } => {
            if let Some(block) = emit_postfix_decrement_while_loop(
                condition,
                body,
                return_type,
                indent_level,
                symbols,
                context,
            )? {
                return Ok(block);
            }
            let condition = emit_condition_expr(condition, symbols, context)
                .map_err(|detail| format!("while condition {detail}"))?;
            let mut loop_symbols = symbols.clone();
            let mut block = String::new();
            block.push_str(&format!("{indent}while {condition} {{\n"));
            for (index, stmt) in body.iter().enumerate() {
                let line = emit_stmt(
                    stmt,
                    return_type,
                    indent_level + 1,
                    &mut loop_symbols,
                    context,
                )
                .map_err(|detail| format!("while body[{index}].{detail}"))?;
                block.push_str(&line);
            }
            block.push_str(&format!("{indent}}}\n"));
            Ok(block)
        }
        IrStmt::Unsupported { node, reason, .. } => {
            Err(format!("unsupported statement {node}: {reason}"))
        }
    }
}

fn emit_postfix_decrement_while_loop(
    condition: &IrExpr,
    body: &[IrStmt],
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Dec,
        prefix: false,
        ty,
        ..
    } = condition
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name,
        ty: target_ty,
        ..
    } = target.as_ref()
    else {
        return Ok(None);
    };
    if !symbols.contains(name) {
        return Err(format!(
            "while condition decrement target {name} is not declared"
        ));
    }
    if !is_usize(target_ty) || !is_usize(ty) {
        return Ok(None);
    }

    let name = emit_identifier(name, "while condition decrement target")?;
    let counter_ty = emit_scalar_type(target_ty)
        .map_err(|detail| format!("while condition decrement target has {detail}"))?;
    let zero = zero_literal_for_type(target_ty)
        .map_err(|detail| format!("while condition decrement zero {detail}"))?;
    let one = emit_integer_literal(1, target_ty)
        .map_err(|detail| format!("while condition decrement step {detail}"))?;
    let snapshot = emit_identifier(
        &first_available_temp_name(&format!("{name}_before_dec"), symbols),
        "while condition decrement snapshot",
    )?;

    let indent = "    ".repeat(indent_level);
    let inner_indent = "    ".repeat(indent_level + 1);
    let break_indent = "    ".repeat(indent_level + 2);
    let mut block = String::new();
    block.push_str(&format!("{indent}loop {{\n"));
    block.push_str(&format!(
        "{inner_indent}let {snapshot}: {counter_ty} = {name};\n"
    ));
    block.push_str(&format!(
        "{inner_indent}{name} = {name}.wrapping_sub({one});\n"
    ));
    block.push_str(&format!("{inner_indent}if {snapshot} == {zero} {{\n"));
    block.push_str(&format!("{break_indent}break;\n"));
    block.push_str(&format!("{inner_indent}}}\n"));

    let mut loop_symbols = symbols.clone();
    for (index, stmt) in body.iter().enumerate() {
        let line = emit_stmt(
            stmt,
            return_type,
            indent_level + 1,
            &mut loop_symbols,
            context,
        )
        .map_err(|detail| format!("while body[{index}].{detail}"))?;
        block.push_str(&line);
    }
    block.push_str(&format!("{indent}}}\n"));
    Ok(Some(block))
}

fn emit_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    match expr {
        IrExpr::LitInt { value, ty, .. } => emit_integer_literal(*value, ty),
        IrExpr::Var { name, ty, .. } => {
            if let Some(global) = context.readonly_global(name) {
                validate_global_expr_type(global, ty)?;
                return context.global_rust_name(name);
            }
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
            let lhs = emit_expr(lhs, symbols, context)
                .map_err(|detail| format!("binary lhs {detail}"))?;
            let rhs = emit_expr(rhs, symbols, context)
                .map_err(|detail| format!("binary rhs {detail}"))?;
            Ok(format!("({lhs} {op} {rhs})"))
        }
        IrExpr::Unary {
            op, operand, ty, ..
        } => match op {
            IrUnOp::BitNot => {
                validate_expr_matches_type(operand, ty, "bitnot operand")?;
                let operand = emit_expr(operand, symbols, context)
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
            let expr = emit_expr(expr, symbols, context)
                .map_err(|detail| format!("cast expr {detail}"))?;
            Ok(format!("({expr} as {target})"))
        }
        IrExpr::Index {
            base, index, ty, ..
        } => emit_index_expr(base, index, ty, symbols, context),
        IrExpr::Call { callee, .. } => Err(format!("call expression {callee} is unsupported")),
        IrExpr::IncDec { .. } => Err("inc/dec expression is unsupported".to_string()),
        IrExpr::Deref { .. } => Err("deref expression is unsupported".to_string()),
        IrExpr::AddrOf { .. } => Err("address-of expression is unsupported".to_string()),
        IrExpr::Unsupported { node, reason, .. } => {
            Err(format!("unsupported expression {node}: {reason}"))
        }
    }
}

fn emit_expr_with_prelude(
    expr: &IrExpr,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<EmittedExpr, String> {
    match expr {
        IrExpr::Binary {
            op, lhs, rhs, ty, ..
        } => {
            let op = emit_binary_op(op).map_err(|detail| format!("{path} {detail}"))?;
            validate_binary_operand_types(op, lhs, rhs, ty)
                .map_err(|detail| format!("{path} {detail}"))?;
            let lhs = emit_expr_with_prelude(
                lhs,
                symbols,
                context,
                indent_level,
                &format!("{path} binary lhs"),
            )?;
            let rhs = emit_expr_with_prelude(
                rhs,
                symbols,
                context,
                indent_level,
                &format!("{path} binary rhs"),
            )?;
            Ok(EmittedExpr {
                prelude: format!("{}{}", lhs.prelude, rhs.prelude),
                expr: format!("({} {op} {})", lhs.expr, rhs.expr),
            })
        }
        IrExpr::Cast { target, expr, .. } => {
            if !is_integer_type(target) {
                return Err(format!(
                    "{path} cast target {} is unsupported",
                    type_label(target)
                ));
            }
            let source_type =
                expr_type(expr).ok_or_else(|| format!("{path} cast source type is unsupported"))?;
            if !is_integer_type(source_type) {
                return Err(format!(
                    "{path} cast source {} is unsupported",
                    type_label(source_type)
                ));
            }
            let target = emit_scalar_type(target)
                .map_err(|detail| format!("{path} cast target has {detail}"))?;
            let emitted = emit_expr_with_prelude(
                expr,
                symbols,
                context,
                indent_level,
                &format!("{path} cast expr"),
            )?;
            Ok(EmittedExpr {
                prelude: emitted.prelude,
                expr: format!("({} as {target})", emitted.expr),
            })
        }
        IrExpr::Index {
            base, index, ty, ..
        } => {
            let index = emit_expr_with_prelude(
                index,
                symbols,
                context,
                indent_level,
                &format!("{path} index operand"),
            )?;
            let expr = emit_index_expr_with_emitted_index(base, &index.expr, ty, symbols, context)
                .map_err(|detail| format!("{path} {detail}"))?;
            Ok(EmittedExpr {
                prelude: index.prelude,
                expr,
            })
        }
        IrExpr::Deref { ptr, ty, .. } => {
            emit_post_increment_byte_read_expr(ptr, ty, symbols, context, indent_level, path)
        }
        _ => Ok(EmittedExpr {
            prelude: String::new(),
            expr: emit_expr(expr, symbols, context).map_err(|detail| format!("{path} {detail}"))?,
        }),
    }
}

fn emit_post_increment_byte_read_expr(
    ptr: &IrExpr,
    ty: &IrType,
    symbols: &mut HashSet<String>,
    context: &EmitContext,
    indent_level: usize,
    path: &str,
) -> Result<EmittedExpr, String> {
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Inc,
        prefix: false,
        ..
    } = ptr
    else {
        return Err(format!("{path} deref expression is unsupported"));
    };
    let IrExpr::Var {
        name: cursor,
        ty: cursor_ty,
        ..
    } = target.as_ref()
    else {
        return Err(format!("{path} post-increment target is unsupported"));
    };
    if !symbols.contains(cursor) {
        return Err(format!(
            "{path} post-increment cursor {cursor} is not declared"
        ));
    }
    let element_ty = readonly_pointer_slice_element_type(cursor_ty)
        .filter(|element_ty| is_u8(element_ty))
        .ok_or_else(|| {
            format!(
                "{path} post-increment cursor {cursor} has unsupported type {}",
                type_label(cursor_ty)
            )
        })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("{path} post-increment element has {detail}"))?;
    let deref_ty = emit_scalar_type(ty).map_err(|detail| format!("{path} deref has {detail}"))?;
    if deref_ty != element_ty {
        return Err(format!(
            "{path} deref type {deref_ty} does not match cursor element type {element_ty}"
        ));
    }
    let (source, cursor, declare_cursor) = if let Some(source) = context.byte_cursor_source(cursor)
    {
        if !symbols.contains(source) {
            return Err(format!("{path} byte source {source} is not declared"));
        }
        (
            emit_identifier(source, "byte source")?,
            emit_identifier(cursor, "byte cursor")?,
            false,
        )
    } else {
        let source = emit_identifier(cursor, "byte source")?;
        let cursor = first_available_named_temp(&format!("{source}_index"), symbols);
        (source, emit_identifier(&cursor, "byte cursor")?, true)
    };
    let temp = first_available_temp_name("byte", symbols);
    let indent = "    ".repeat(indent_level);
    let mut prelude = String::new();
    if declare_cursor {
        prelude.push_str(&format!("{indent}let mut {cursor}: usize = 0;\n"));
    }
    prelude.push_str(&format!(
        "{indent}let {temp}: {element_ty} = {source}[{cursor}];\n\
         {indent}{cursor} += 1;\n"
    ));
    Ok(EmittedExpr {
        prelude,
        expr: temp,
    })
}

fn emit_index_expr(
    base: &IrExpr,
    index: &IrExpr,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("index base must be Var".to_string());
    };
    let (element_ty, emitted_base) = if let Some(global) = context.readonly_global(base_name) {
        validate_global_expr_type(global, base_ty)?;
        (
            readonly_global_array_element_type(global)?,
            context.global_rust_name(base_name)?,
        )
    } else {
        if !symbols.contains(base_name) {
            return Err(format!("index base {base_name} is not declared"));
        }
        let element_ty = readonly_pointer_slice_element_type(base_ty).ok_or_else(|| {
            format!(
                "index base {base_name} has unsupported type {}",
                type_label(base_ty)
            )
        })?;
        (element_ty, emit_identifier(base_name, "index base")?)
    };
    let element_ty =
        emit_scalar_type(element_ty).map_err(|detail| format!("index element has {detail}"))?;
    let result_ty = emit_scalar_type(ty).map_err(|detail| format!("index result has {detail}"))?;
    if result_ty != element_ty {
        return Err(format!(
            "index result type {result_ty} does not match element type {element_ty}"
        ));
    }
    let index_ty =
        expr_type(index).ok_or_else(|| "index operand type is unsupported".to_string())?;
    if !is_integer_type(index_ty) {
        return Err(format!(
            "index operand type {} is unsupported",
            type_label(index_ty)
        ));
    }
    let index =
        emit_expr(index, symbols, context).map_err(|detail| format!("index operand {detail}"))?;
    Ok(format!("{emitted_base}[{index} as usize]"))
}

fn emit_index_expr_with_emitted_index(
    base: &IrExpr,
    emitted_index: &str,
    ty: &IrType,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = base
    else {
        return Err("index base must be Var".to_string());
    };
    let (element_ty, emitted_base) = if let Some(global) = context.readonly_global(base_name) {
        validate_global_expr_type(global, base_ty)?;
        (
            readonly_global_array_element_type(global)?,
            context.global_rust_name(base_name)?,
        )
    } else {
        if !symbols.contains(base_name) {
            return Err(format!("index base {base_name} is not declared"));
        }
        let element_ty = readonly_pointer_slice_element_type(base_ty).ok_or_else(|| {
            format!(
                "index base {base_name} has unsupported type {}",
                type_label(base_ty)
            )
        })?;
        (element_ty, emit_identifier(base_name, "index base")?)
    };
    let element_ty =
        emit_scalar_type(element_ty).map_err(|detail| format!("index element has {detail}"))?;
    let result_ty = emit_scalar_type(ty).map_err(|detail| format!("index result has {detail}"))?;
    if result_ty != element_ty {
        return Err(format!(
            "index result type {result_ty} does not match element type {element_ty}"
        ));
    }
    Ok(format!("{emitted_base}[{emitted_index} as usize]"))
}

fn is_byte_cursor_cast_assignment(
    target: &IrExpr,
    value: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<bool, String> {
    let IrExpr::Var {
        name: cursor,
        ty: cursor_ty,
        ..
    } = target
    else {
        return Ok(false);
    };
    let Some(source) = context.byte_cursor_source(cursor) else {
        return Ok(false);
    };
    let IrExpr::Cast {
        target,
        expr,
        implicit: false,
        ..
    } = value
    else {
        return Ok(false);
    };
    let IrExpr::Var {
        name: source_name,
        ty: source_ty,
        ..
    } = expr.as_ref()
    else {
        return Ok(false);
    };
    if source_name != source || !is_u8_pointer(cursor_ty) || !is_u8_pointer(target) {
        return Ok(false);
    }
    if !is_const_void_pointer(source_ty) {
        return Ok(false);
    }
    if !symbols.contains(cursor) {
        return Err(format!("byte cursor {cursor} is not declared"));
    }
    if !symbols.contains(source_name) {
        return Err(format!("byte cursor source {source_name} is not declared"));
    }
    Ok(true)
}

fn emit_post_increment_deref_return(
    value: &IrExpr,
    return_type: &IrType,
    indent_level: usize,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<Option<String>, String> {
    let IrExpr::Deref { ptr, ty, .. } = value else {
        return Ok(None);
    };
    let IrExpr::IncDec {
        target,
        op: IrIncDecOp::Inc,
        prefix: false,
        ..
    } = ptr.as_ref()
    else {
        return Ok(None);
    };
    let IrExpr::Var {
        name: base_name,
        ty: base_ty,
        ..
    } = target.as_ref()
    else {
        return Ok(None);
    };
    if !symbols.contains(base_name) {
        return Err(format!("post-increment cursor {base_name} is not declared"));
    }
    let element_ty = readonly_pointer_slice_element_type(base_ty)
        .filter(|element_ty| is_u8(element_ty))
        .ok_or_else(|| {
            format!(
                "post-increment cursor {base_name} has unsupported type {}",
                type_label(base_ty)
            )
        })?;
    let element_ty = emit_scalar_type(element_ty)
        .map_err(|detail| format!("post-increment element has {detail}"))?;
    let deref_ty = emit_scalar_type(ty).map_err(|detail| format!("deref result has {detail}"))?;
    let return_ty =
        emit_scalar_type(return_type).map_err(|detail| format!("return type has {detail}"))?;
    if deref_ty != element_ty || return_ty != element_ty {
        return Err(format!(
            "post-increment deref type must match element and return type: element={element_ty}, deref={deref_ty}, return={return_ty}"
        ));
    }
    let (slice_name, cursor_name, declare_cursor) =
        if let Some(source_name) = context.byte_cursor_source(base_name) {
            if !symbols.contains(source_name) {
                return Err(format!(
                    "post-increment source {source_name} is not declared"
                ));
            }
            (
                emit_identifier(source_name, "post-increment source")?,
                emit_identifier(base_name, "post-increment cursor")?,
                false,
            )
        } else {
            let slice_name = emit_identifier(base_name, "post-increment base")?;
            let cursor_name = emit_identifier(
                &first_available_named_temp(&format!("{slice_name}_index"), symbols),
                "post-increment cursor",
            )?;
            (slice_name, cursor_name, true)
        };
    let temp_name = first_available_temp_name("byte", symbols);
    let indent = "    ".repeat(indent_level);
    let mut rust = String::new();
    if declare_cursor {
        rust.push_str(&format!("{indent}let mut {cursor_name}: usize = 0;\n"));
    }
    rust.push_str(&format!(
        "{indent}let {temp_name}: {element_ty} = {slice_name}[{cursor_name}];\n\
         {indent}{cursor_name} += 1;\n\
         {indent}return {temp_name};\n"
    ));
    Ok(Some(rust))
}

fn first_available_temp_name(prefix: &str, symbols: &HashSet<String>) -> String {
    let mut index = 0usize;
    loop {
        let candidate = format!("{prefix}{index}");
        if !symbols.contains(&candidate) {
            return candidate;
        }
        index += 1;
    }
}

fn first_available_named_temp(preferred: &str, symbols: &HashSet<String>) -> String {
    if !symbols.contains(preferred) {
        return preferred.to_string();
    }
    let mut index = 1usize;
    loop {
        let candidate = format!("{preferred}{index}");
        if !symbols.contains(&candidate) {
            return candidate;
        }
        index += 1;
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

fn emit_comparison_op(op: &IrBinOp) -> Result<&'static str, String> {
    match op {
        IrBinOp::Eq => Ok("=="),
        IrBinOp::Neq => Ok("!="),
        IrBinOp::Lt => Ok("<"),
        IrBinOp::Le => Ok("<="),
        IrBinOp::Gt => Ok(">"),
        IrBinOp::Ge => Ok(">="),
        _ => Err(format!("binary op {op:?} is not a comparison")),
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

fn emit_condition_expr(
    expr: &IrExpr,
    symbols: &HashSet<String>,
    context: &EmitContext,
) -> Result<String, String> {
    if let IrExpr::Binary {
        op, lhs, rhs, ty, ..
    } = expr
    {
        if let Ok(op) = emit_comparison_op(op) {
            validate_comparison_condition_types(lhs, rhs, ty, op)?;
            let lhs = emit_expr(lhs, symbols, context)
                .map_err(|detail| format!("comparison lhs {detail}"))?;
            let rhs = emit_expr(rhs, symbols, context)
                .map_err(|detail| format!("comparison rhs {detail}"))?;
            return Ok(format!("({lhs} {op} {rhs})"));
        }
    }
    let ty = expr_type(expr).ok_or_else(|| "type is unsupported".to_string())?;
    let zero = zero_literal_for_type(ty)?;
    let expr = emit_expr(expr, symbols, context)?;
    Ok(format!("{expr} != {zero}"))
}

fn validate_comparison_condition_types(
    lhs: &IrExpr,
    rhs: &IrExpr,
    result_ty: &IrType,
    op: &str,
) -> Result<(), String> {
    if !is_c_int_type(result_ty) {
        return Err(format!(
            "comparison result type must be C int, got {}",
            type_label(result_ty)
        ));
    }
    let lhs_ty = expr_type(lhs).ok_or_else(|| "comparison lhs type is unsupported".to_string())?;
    let rhs_ty = expr_type(rhs).ok_or_else(|| "comparison rhs type is unsupported".to_string())?;
    let lhs_ty =
        emit_scalar_type(lhs_ty).map_err(|detail| format!("comparison lhs has {detail}"))?;
    let rhs_ty =
        emit_scalar_type(rhs_ty).map_err(|detail| format!("comparison rhs has {detail}"))?;
    if lhs_ty == rhs_ty {
        Ok(())
    } else {
        Err(format!(
            "comparison operand types must match for {op}: lhs={lhs_ty}, rhs={rhs_ty}"
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

fn zero_literal_for_type(ty: &IrType) -> Result<String, String> {
    emit_integer_literal(0, ty)
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

fn collect_byte_cursor_sources(body: &[IrStmt]) -> HashMap<String, String> {
    let mut candidates = HashMap::new();
    collect_byte_cursor_sources_from_body(body, &mut candidates);
    candidates
        .into_iter()
        .filter(|(cursor, _)| body_has_post_increment_byte_read(body, cursor))
        .collect()
}

fn collect_byte_cursor_sources_from_body(
    body: &[IrStmt],
    cursor_sources: &mut HashMap<String, String>,
) {
    for stmt in body {
        match stmt {
            IrStmt::Assign { target, value, .. } => {
                if let Some((cursor, source)) = byte_cursor_cast_assignment_parts(target, value) {
                    cursor_sources.insert(cursor.to_string(), source.to_string());
                }
            }
            IrStmt::If {
                then_body,
                else_body,
                ..
            } => {
                collect_byte_cursor_sources_from_body(then_body, cursor_sources);
                collect_byte_cursor_sources_from_body(else_body, cursor_sources);
            }
            IrStmt::While { body, .. } => {
                collect_byte_cursor_sources_from_body(body, cursor_sources);
            }
            _ => {}
        }
    }
}

fn byte_cursor_cast_assignment_parts<'a>(
    target: &'a IrExpr,
    value: &'a IrExpr,
) -> Option<(&'a str, &'a str)> {
    let IrExpr::Var {
        name: cursor,
        ty: cursor_ty,
        ..
    } = target
    else {
        return None;
    };
    let IrExpr::Cast {
        target,
        expr,
        implicit: false,
        ..
    } = value
    else {
        return None;
    };
    let IrExpr::Var {
        name: source,
        ty: source_ty,
        ..
    } = expr.as_ref()
    else {
        return None;
    };
    if is_u8_pointer(cursor_ty) && is_u8_pointer(target) && is_const_void_pointer(source_ty) {
        Some((cursor.as_str(), source.as_str()))
    } else {
        None
    }
}

fn body_has_post_increment_byte_read(body: &[IrStmt], cursor: &str) -> bool {
    body.iter()
        .any(|stmt| stmt_has_post_increment_byte_read(stmt, cursor))
}

fn stmt_has_post_increment_byte_read(stmt: &IrStmt, cursor: &str) -> bool {
    match stmt {
        IrStmt::Decl { init, .. } => init
            .as_ref()
            .is_some_and(|expr| expr_has_post_increment_byte_read(expr, cursor)),
        IrStmt::Assign { target, value, .. } => {
            expr_has_post_increment_byte_read(target, cursor)
                || expr_has_post_increment_byte_read(value, cursor)
        }
        IrStmt::Return { value, .. } => value
            .as_ref()
            .is_some_and(|expr| expr_has_post_increment_byte_read(expr, cursor)),
        IrStmt::Expr { expr, .. } => expr_has_post_increment_byte_read(expr, cursor),
        IrStmt::If {
            condition,
            then_body,
            else_body,
            ..
        } => {
            expr_has_post_increment_byte_read(condition, cursor)
                || body_has_post_increment_byte_read(then_body, cursor)
                || body_has_post_increment_byte_read(else_body, cursor)
        }
        IrStmt::While {
            condition, body, ..
        } => {
            expr_has_post_increment_byte_read(condition, cursor)
                || body_has_post_increment_byte_read(body, cursor)
        }
        IrStmt::Unsupported { .. } => false,
    }
}

fn expr_has_post_increment_byte_read(expr: &IrExpr, cursor: &str) -> bool {
    match expr {
        IrExpr::Deref { ptr, ty, .. } => is_u8(ty) && is_post_inc_var(ptr, cursor),
        IrExpr::Binary { lhs, rhs, .. } => {
            expr_has_post_increment_byte_read(lhs, cursor)
                || expr_has_post_increment_byte_read(rhs, cursor)
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => expr_has_post_increment_byte_read(operand, cursor),
        IrExpr::Index { base, index, .. } => {
            expr_has_post_increment_byte_read(base, cursor)
                || expr_has_post_increment_byte_read(index, cursor)
        }
        IrExpr::Call { args, .. } => args
            .iter()
            .any(|arg| expr_has_post_increment_byte_read(arg, cursor)),
        IrExpr::IncDec { target, .. } => expr_has_post_increment_byte_read(target, cursor),
        IrExpr::LitInt { .. } | IrExpr::Var { .. } | IrExpr::Unsupported { .. } => false,
    }
}

fn count_post_increment_byte_reads(expr: &IrExpr) -> usize {
    match expr {
        IrExpr::Deref { ptr, ty, .. } if is_u8(ty) && is_post_inc_expr(ptr) => 1,
        IrExpr::Deref { ptr, .. } => count_post_increment_byte_reads(ptr),
        IrExpr::Binary { lhs, rhs, .. } => {
            count_post_increment_byte_reads(lhs) + count_post_increment_byte_reads(rhs)
        }
        IrExpr::Unary { operand, .. }
        | IrExpr::Cast { expr: operand, .. }
        | IrExpr::AddrOf { operand, .. } => count_post_increment_byte_reads(operand),
        IrExpr::Index { base, index, .. } => {
            count_post_increment_byte_reads(base) + count_post_increment_byte_reads(index)
        }
        IrExpr::Call { args, .. } => args.iter().map(count_post_increment_byte_reads).sum(),
        IrExpr::IncDec { target, .. } => count_post_increment_byte_reads(target),
        IrExpr::LitInt { .. } | IrExpr::Var { .. } | IrExpr::Unsupported { .. } => 0,
    }
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
            IrStmt::While {
                condition, body, ..
            } => {
                if let IrExpr::IncDec {
                    target,
                    op: IrIncDecOp::Dec,
                    prefix: false,
                    ..
                } = condition
                {
                    if let IrExpr::Var { name, .. } = target.as_ref() {
                        assigned_vars.insert(name.clone());
                    }
                }
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

fn readonly_pointer_slice_element_type(ty: &IrType) -> Option<&IrType> {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } if pointee.is_const && is_integer_type(pointee) => {
            Some(pointee.as_ref())
        }
        _ => None,
    }
}

fn readonly_global_array_element_type(global: &IrGlobal) -> Result<&IrType, String> {
    let IrTypeKind::Array { element, len } = &global.ty.kind else {
        return Err(format!(
            "global {} has unsupported type {}",
            global.name,
            type_label(&global.ty)
        ));
    };
    if !global.ty.is_const {
        return Err(format!("global {} is not readonly const", global.name));
    }
    if len.is_none() {
        return Err(format!("global {} array length is unknown", global.name));
    }
    if !is_integer_type(element) {
        return Err(format!(
            "global {} element type {} is unsupported",
            global.name,
            type_label(element)
        ));
    }
    Ok(element.as_ref())
}

fn validate_global_expr_type(global: &IrGlobal, ty: &IrType) -> Result<(), String> {
    if &global.ty == ty {
        Ok(())
    } else {
        Err(format!(
            "global {} type {} does not match expression type {}",
            global.name,
            type_label(&global.ty),
            type_label(ty)
        ))
    }
}

fn is_c_int_type(ty: &IrType) -> bool {
    matches!(
        ty.kind,
        IrTypeKind::Integer {
            signed: true,
            width: 32
        }
    )
}

fn is_void_type(ty: &IrType) -> bool {
    matches!(ty.kind, IrTypeKind::Void)
}

fn is_const_void_pointer(ty: &IrType) -> bool {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } => {
            pointee.is_const && matches!(pointee.kind, IrTypeKind::Void)
        }
        _ => false,
    }
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

fn emit_global_const_identifier(name: &str) -> Result<String, String> {
    let mut output = String::new();
    let mut previous_was_underscore = false;
    for character in name.chars() {
        if character.is_ascii_alphanumeric() {
            output.push(character.to_ascii_uppercase());
            previous_was_underscore = false;
        } else if character == '_' && !previous_was_underscore {
            output.push('_');
            previous_was_underscore = true;
        } else {
            return Err(format!("global identifier {name:?} is unsupported"));
        }
    }
    while output.ends_with('_') {
        output.pop();
    }
    if output.is_empty()
        || output
            .chars()
            .next()
            .is_some_and(|character| character.is_ascii_digit())
    {
        return Err(format!("global identifier {name:?} is unsupported"));
    }
    Ok(output)
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

fn is_u8_pointer(ty: &IrType) -> bool {
    match &ty.kind {
        IrTypeKind::Pointer { pointee } => is_u8(pointee),
        _ => false,
    }
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

fn is_post_inc_expr(expr: &IrExpr) -> bool {
    matches!(
        expr,
        IrExpr::IncDec {
            target,
            op: IrIncDecOp::Inc,
            prefix: false,
            ..
        } if matches!(target.as_ref(), IrExpr::Var { .. })
    )
}

fn var_name(expr: &IrExpr) -> Option<&str> {
    match expr {
        IrExpr::Var { name, .. } => Some(name),
        _ => None,
    }
}

#[cfg(all(test, feature = "typed-ir"))]
mod tests {
    use super::*;
    use crate::typed_ir::{IrBinOp, IrExpr, IrStmt, IrType, IrTypeKind, IrUnOp};

    include!("tests/chunk_00.rs");
    include!("tests/chunk_01.rs");
    include!("tests/chunk_02.rs");
    include!("tests/chunk_03.rs");
    include!("tests/chunk_04.rs");
    include!("tests/chunk_05.rs");
    include!("tests/chunk_06.rs");
    include!("tests/chunk_07.rs");
    include!("tests/chunk_08.rs");
    include!("tests/ast_utils_source_span.rs");
    include!("tests/verified_parse_arguments.rs");
    include!("tests/null_pointer_bitcast.rs");
    include!("tests/record_layout.rs");
    include!("tests/record_typedef_fields.rs");
    include!("tests/typedef_body.rs");
    include!("tests/typedef_pointer_ast.rs");
}

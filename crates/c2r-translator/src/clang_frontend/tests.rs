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
}

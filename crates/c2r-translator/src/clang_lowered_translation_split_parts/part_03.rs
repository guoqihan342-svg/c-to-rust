#[cfg(all(test, feature = "clang-lowering-report"))]
mod clang_lowered_ir_evidence_tests {
    include!("part_03_split_parts/part_00.rs");
    include!("part_03_split_parts/part_01.rs");
}

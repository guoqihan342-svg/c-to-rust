mod artifact_io;
mod artifacts;
#[cfg(feature = "clang-frontend")]
pub mod clang_frontend;
#[cfg(feature = "clang-lowering-report")]
mod clang_lowered_translation;
mod legacy_translation;
mod model;
#[cfg(feature = "typed-ir")]
pub mod translation_route;
#[cfg(feature = "typed-ir")]
pub mod typed_ir;

pub use model::{
    AcceptedNamedSliceEvidence, ArtifactManifest, BuildProfile, CBoundary, CDirectDependency,
    CParameter, CSignature, CallExpressionEvidence, CfgBlock, CfgEvidence, CfgFunction,
    ExternalDirectCallee, PointerEdge, PointerGraphEvidence, PointerNode, ScalarArithmeticContract,
    SliceSpec, SourceFileRef, SourceSpanRef, StructuredControlFlowEvidence, TargetAbiProfile,
    TranslationError, TranslationPlan, TranslationResult, TranslationSource, TypeMapEvidence,
    TypeMapping, TypeUncertainty,
};

pub use artifacts::write_translation_artifacts;
// The legacy string translator is retired to a crate-internal compatibility
// candidate source; `translate_slice` is deliberately not re-exported as
// public API and stays visible to this crate only.
pub(crate) use legacy_translation::translate_slice;

#[cfg(all(test, feature = "clang-lowering-report"))]
mod clang_lowered_translation_module_tests {
    use super::*;

    #[test]
    fn clang_lowered_translation_module_exposes_fallback_candidate_entrypoint() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "missing-tu".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "add_one".to_string(),
            c_source: "int add_one(int value) { return value + 1; }".to_string(),
            ..SliceSpec::default()
        };

        let attempt =
            crate::clang_lowered_translation::try_clang_lowered_translation_attempt(&spec);
        assert!(attempt.is_none());
    }
}

#[cfg(test)]
mod legacy_translation_module_tests {
    use super::*;

    #[test]
    fn legacy_translation_module_exposes_translate_slice_entrypoint() {
        let spec = SliceSpec {
            target_id: "demo".to_string(),
            slice_id: "legacy-module-boundary".to_string(),
            source_commit: "1234567".to_string(),
            function_name: "identity".to_string(),
            c_source: "int identity(int value) { return value; }".to_string(),
            ..SliceSpec::default()
        };

        let result = crate::legacy_translation::translate_slice(&spec);

        assert!(result.errors.is_empty(), "{:?}", result.errors);
        assert!(result
            .rust_code
            .contains("pub fn identity(value: i32) -> i32"));
    }
}

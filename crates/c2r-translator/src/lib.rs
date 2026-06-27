use std::{error::Error, fs, path::Path};

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
    ArtifactManifest, BuildProfile, CallExpressionEvidence, CfgBlock, CfgEvidence, CfgFunction,
    PointerEdge, PointerGraphEvidence, PointerNode, SliceSpec, SourceFileRef, SourceSpanRef,
    TranslationError, TranslationPlan, TranslationResult, TypeMapEvidence, TypeMapping,
    TypeUncertainty,
};

#[cfg(feature = "clang-lowering-report")]
pub(crate) use legacy_translation::record_type_mapping;
pub use legacy_translation::translate_slice;

#[cfg(feature = "clang-frontend")]
use artifacts::write_clang_dry_run_artifact;
#[cfg(feature = "clang-lowering-report")]
use artifacts::write_clang_lowering_report_artifact;
use artifacts::write_core_translation_artifacts;

pub fn write_translation_artifacts(
    spec: &SliceSpec,
    out_dir: &Path,
) -> Result<ArtifactManifest, Box<dyn Error>> {
    fs::create_dir_all(out_dir)?;
    #[cfg(feature = "clang-lowering-report")]
    let result = translate_slice_with_optional_clang_lowered_ir(spec);
    #[cfg(not(feature = "clang-lowering-report"))]
    let result = translate_slice(spec);
    let prefix = format!("l3-{}", spec.slice_id);
    let status = if result.errors.is_empty() {
        "generated"
    } else {
        "blocked"
    };

    let artifacts = write_core_translation_artifacts(spec, &result, out_dir, &prefix, status)?;
    #[cfg(feature = "clang-frontend")]
    let artifacts = {
        let mut artifacts = artifacts;
        artifacts.push(write_clang_dry_run_artifact(spec, out_dir, &prefix)?);
        artifacts
    };
    #[cfg(feature = "clang-lowering-report")]
    let artifacts = {
        let mut artifacts = artifacts;
        artifacts.push(write_clang_lowering_report_artifact(
            spec, out_dir, &prefix,
        )?);
        artifacts
    };

    Ok(ArtifactManifest {
        target_id: spec.target_id.clone(),
        slice_id: spec.slice_id.clone(),
        status: status.to_string(),
        artifact_paths: artifacts
            .into_iter()
            .map(|path| path.to_string_lossy().replace('\\', "/"))
            .collect(),
    })
}

#[cfg(feature = "clang-lowering-report")]
fn translate_slice_with_optional_clang_lowered_ir(spec: &SliceSpec) -> TranslationResult {
    clang_lowered_translation::try_translate_slice_with_clang_lowered_ir(spec)
        .unwrap_or_else(|| translate_slice(spec))
}

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

        assert!(
            crate::clang_lowered_translation::try_translate_slice_with_clang_lowered_ir(&spec)
                .is_none()
        );
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

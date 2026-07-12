impl ClangParseSpec {
    pub fn from_slice_spec(spec: &SliceSpec) -> Result<Self, ClangFrontendError> {
        let source_root = required_path(spec.source_root.as_deref(), "source_root")?;
        let source_file = required_path(spec.source_file.as_deref(), "source_file")?;
        let source_file_key = normalized_path(&source_file);
        if spec.function_name.trim().is_empty() {
            return Err(ClangFrontendError {
                kind: "missing_function_name".to_string(),
                message: "clang frontend dry-run requires function_name".to_string(),
            });
        }
        if !spec.source_file_hashes.iter().any(|(path, sha256)| {
            normalized_metadata_path(path) == source_file_key && !sha256.trim().is_empty()
        }) {
            return Err(ClangFrontendError {
                kind: "missing_source_file_hash".to_string(),
                message: "clang frontend dry-run requires source_file_hashes entry for source_file"
                    .to_string(),
            });
        }
        let function_source_span = match spec.function_source_span.clone() {
            Some(function_source_span) => {
                if normalized_metadata_path(&function_source_span.file) != source_file_key {
                    return Err(ClangFrontendError {
                        kind: "function_span_source_file_mismatch".to_string(),
                        message: format!(
                            "function_source_span.file must match source_file: {} != {}",
                            function_source_span.file,
                            source_file.to_string_lossy()
                        ),
                    });
                }
                if function_source_span.sha256.trim().is_empty() {
                    return Err(ClangFrontendError {
                        kind: "missing_function_source_span_hash".to_string(),
                        message: "clang frontend dry-run requires function_source_span.sha256"
                            .to_string(),
                    });
                }
                Some(function_source_span)
            }
            None if !spec.c_source.trim().is_empty() => None,
            None => {
                return Err(ClangFrontendError {
                    kind: "missing_function_source_span".to_string(),
                    message: "clang frontend dry-run requires function_source_span".to_string(),
                });
            }
        };

        Ok(Self {
            source_root,
            source_file,
            function_name: spec.function_name.clone(),
            include_paths: spec.build_profile.include_paths.clone(),
            defines: spec.build_profile.defines.clone(),
            target_abi: spec.build_profile.resolved_target_abi(),
            compile_commands: spec.compile_commands.clone(),
            source_file_hashes: spec.source_file_hashes.clone(),
            function_source_span,
        })
    }

    pub fn dry_run(&self) -> ClangDryRun {
        self.dry_run_with_environment(&env::vars().collect())
    }

    pub fn dry_run_with_environment(&self, environment: &BTreeMap<String, String>) -> ClangDryRun {
        let mut diagnostics = vec![
            "LIBCLANG_PATH is observed only as ignored legacy metadata; active lowering uses clang AST dump JSON via CLANG_PATH"
                .to_string(),
        ];
        if self.compile_commands.is_some() {
            diagnostics.push(
                "compile_commands is present; dry-run arguments omit synthesized include/define flags"
                    .to_string(),
            );
        }

        ClangDryRun {
            status: "diagnostic_only".to_string(),
            active_frontend: clang_ast_dump_active_frontend(),
            claim_boundary: diagnostic_claim_boundary(),
            source_root: self.source_root.to_string_lossy().into_owned(),
            source_file: self.source_file.to_string_lossy().into_owned(),
            function_name: self.function_name.clone(),
            arguments: self.clang_arguments(),
            compile_commands: self
                .compile_commands
                .as_ref()
                .map(|reference| reference.path().to_string()),
            environment: ClangEnvironment::detect_from_env(environment),
            diagnostics,
        }
    }

    pub fn clang_arguments(&self) -> Vec<String> {
        if self.compile_commands.is_some() {
            return Vec::new();
        }

        self.resolved_include_paths()
            .iter()
            .map(|include_path| {
                format!("-I{}", include_path.to_string_lossy().replace('\\', "/"))
            })
            .chain(self.defines.iter().map(|define| format!("-D{define}")))
            .collect()
    }

    pub(crate) fn resolved_include_paths(&self) -> Vec<PathBuf> {
        self.include_paths
            .iter()
            .map(|include_path| {
                let include_path = Path::new(include_path);
                if include_path.is_absolute() {
                    include_path.to_path_buf()
                } else {
                    self.source_root.join(include_path)
                }
            })
            .collect()
    }
}

pub fn clang_ast_dump_active_frontend() -> ClangActiveFrontend {
    ClangActiveFrontend {
        kind: "clang_ast_dump_json".to_string(),
        command: "clang -Xclang -ast-dump=json -fsyntax-only".to_string(),
        required_env: vec!["CLANG_PATH".to_string()],
        uses_libclang: false,
    }
}

pub fn diagnostic_claim_boundary() -> ClangClaimBoundary {
    ClangClaimBoundary {
        role: "diagnostic_only".to_string(),
        affects_manifest_status: false,
        affects_semantic_pass: false,
        authoritative_evidence: false,
    }
}

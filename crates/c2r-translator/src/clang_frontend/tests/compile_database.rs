use std::fs;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use sha2::{Digest, Sha256};

use super::*;

static TEST_ID: AtomicU64 = AtomicU64::new(0);

struct TestDir(PathBuf);

impl TestDir {
    fn new() -> Self {
        let id = TEST_ID.fetch_add(1, Ordering::Relaxed);
        let path =
            std::env::temp_dir().join(format!("c2r-compile-database-{}-{id}", std::process::id()));
        fs::create_dir_all(&path).expect("create compile database test dir");
        Self(path)
    }

    fn path(&self) -> &Path {
        &self.0
    }
}

impl Drop for TestDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

fn write_database(root: &Path, value: serde_json::Value) -> CompileDatabaseRef {
    let bytes = serde_json::to_vec(&value).expect("serialize compile database");
    fs::write(root.join("compile_commands.json"), &bytes).expect("write compile database");
    CompileDatabaseRef::HashBound {
        path: "compile_commands.json".to_string(),
        sha256: format!("{:x}", Sha256::digest(&bytes)),
    }
}

fn create_source(root: &Path) -> PathBuf {
    let source = root.join("project").join("src").join("unit.c");
    fs::create_dir_all(source.parent().expect("source parent")).expect("create source parent");
    fs::write(&source, "int unit(void) { return 1; }\n").expect("write source");
    source
}

fn project_directory(source: &Path) -> &Path {
    source.parent().unwrap().parent().unwrap()
}

#[test]
fn slice_spec_accepts_hash_bound_and_legacy_compile_commands() {
    let common = serde_json::json!({
        "target_id": "fixture",
        "slice_id": "unit",
        "source_commit": "deadbeef",
        "function_name": "unit",
        "c_source": "int unit(void) { return 1; }",
        "fixture_hash": "fixture",
        "build_profile": {
            "include_paths": [],
            "defines": [],
            "compiler_command_source": "compile_commands.json",
            "clang_available": true
        }
    });
    let mut hash_bound = common.clone();
    hash_bound["compile_commands"] = serde_json::json!({
        "path": "build/compile_commands.json",
        "sha256": "a".repeat(64)
    });
    let spec: SliceSpec = serde_json::from_value(hash_bound).expect("hash-bound spec");
    let expected_sha256 = "a".repeat(64);
    assert_eq!(
        spec.compile_commands.as_ref().unwrap().sha256(),
        Some(expected_sha256.as_str())
    );

    let mut legacy = common;
    legacy["compile_commands"] = serde_json::json!("build/compile_commands.json");
    let spec: SliceSpec = serde_json::from_value(legacy).expect("legacy spec");
    assert_eq!(
        spec.compile_commands.as_deref(),
        Some("build/compile_commands.json")
    );
    assert_eq!(spec.compile_commands.unwrap().sha256(), None);
}

#[test]
fn arguments_are_hash_verified_matched_and_sanitized() {
    let root = TestDir::new();
    let source = create_source(root.path());
    let directory = project_directory(&source);
    let reference = write_database(
        root.path(),
        serde_json::json!([{
            "directory": directory,
            "file": "src/unit.c",
            "arguments": [
                "/usr/bin/clang", "-Iinclude dir", "-DVALUE=7", "-std=c11",
                "-c", "src/unit.c", "-o", "unit.o", "-MMD", "-MFdeps.d"
            ]
        }]),
    );

    let resolved = resolve_compile_database(&reference, root.path(), &source)
        .expect("resolve hash-bound compile command");

    assert_eq!(resolved.working_directory, directory);
    assert_eq!(
        resolved.arguments,
        ["-Iinclude dir", "-DVALUE=7", "-std=c11"]
    );
    assert_eq!(resolved.database_sha256, reference.sha256().unwrap());
}

#[test]
fn command_is_tokenized_without_a_shell() {
    let root = TestDir::new();
    let source = create_source(root.path());
    let directory = project_directory(&source);
    let reference = write_database(
        root.path(),
        serde_json::json!([{
            "directory": directory,
            "file": "src/unit.c",
            "command": "clang '-Iinclude dir' -DNAME=demo -std=c17 -c src/unit.c -ounit.o -MD"
        }]),
    );

    let resolved = resolve_compile_database(&reference, root.path(), &source)
        .expect("resolve command-form entry");

    assert_eq!(
        resolved.arguments,
        ["-Iinclude dir", "-DNAME=demo", "-std=c17"]
    );
}

#[test]
fn nested_database_resolves_dot_directory_from_reference_root() {
    let root = TestDir::new();
    let source = root.path().join("vendor/package/src/unit.c");
    fs::create_dir_all(source.parent().unwrap()).unwrap();
    fs::write(&source, "int unit(void) { return 1; }\n").unwrap();
    let database_path = root.path().join("closure/unit/compile_commands.json");
    fs::create_dir_all(database_path.parent().unwrap()).unwrap();
    let bytes = serde_json::to_vec(&serde_json::json!([{
        "directory": ".",
        "file": "vendor/package/src/unit.c",
        "arguments": ["clang", "-Ivendor/package/include", "-c", "vendor/package/src/unit.c"]
    }]))
    .unwrap();
    fs::write(&database_path, &bytes).unwrap();
    let reference = CompileDatabaseRef::HashBound {
        path: "closure/unit/compile_commands.json".to_string(),
        sha256: format!("{:x}", Sha256::digest(&bytes)),
    };

    let resolved = resolve_compile_database(&reference, root.path(), &source).unwrap();

    assert_eq!(resolved.working_directory, root.path().join("."));
    assert_eq!(resolved.arguments, ["-Ivendor/package/include"]);
}

#[test]
fn parse_spec_exposes_verified_command_result() {
    let root = TestDir::new();
    let source = create_source(root.path());
    let directory = project_directory(&source);
    let reference = write_database(
        root.path(),
        serde_json::json!([{
            "directory": directory,
            "file": "src/unit.c",
            "arguments": ["clang", "-DVERIFIED=1", "-c", "src/unit.c"]
        }]),
    );
    let parse_spec = ClangParseSpec {
        source_root: root.path().to_path_buf(),
        source_file: source.clone(),
        function_name: "unit".to_string(),
        include_paths: Vec::new(),
        defines: Vec::new(),
        target_abi: None,
        compile_commands: Some(reference),
        source_file_hashes: BTreeMap::new(),
        function_source_span: None,
    };

    let resolved = parse_spec
        .resolved_compile_command()
        .expect("resolve through ClangParseSpec")
        .expect("declared command");

    assert_eq!(resolved.arguments, ["-DVERIFIED=1"]);
    assert_eq!(resolved.working_directory, directory);
}

#[test]
fn rejects_hash_drift_and_legacy_paths() {
    let root = TestDir::new();
    let source = create_source(root.path());
    let directory = project_directory(&source);
    let reference = write_database(
        root.path(),
        serde_json::json!([{
            "directory": directory,
            "file": "src/unit.c",
            "arguments": ["clang", "-c", "src/unit.c"]
        }]),
    );
    fs::write(root.path().join("compile_commands.json"), b"[]").unwrap();
    let error = resolve_compile_database(&reference, root.path(), &source).unwrap_err();
    assert_eq!(error.kind, "compile_database_hash_mismatch");

    let legacy = CompileDatabaseRef::LegacyPath("compile_commands.json".to_string());
    let error = resolve_compile_database(&legacy, root.path(), &source).unwrap_err();
    assert_eq!(error.kind, "unhashed_compile_database");
}

#[test]
fn requires_exactly_one_matching_entry() {
    let root = TestDir::new();
    let source = create_source(root.path());
    let directory = project_directory(&source);
    let missing = write_database(
        root.path(),
        serde_json::json!([{
            "directory": directory,
            "file": "src/other.c",
            "arguments": ["clang", "-c", "src/other.c"]
        }]),
    );
    let error = resolve_compile_database(&missing, root.path(), &source).unwrap_err();
    assert_eq!(error.kind, "compile_database_source_missing");

    let entry = serde_json::json!({
        "directory": directory,
        "file": "src/unit.c",
        "arguments": ["clang", "-c", "src/unit.c"]
    });
    let ambiguous = write_database(root.path(), serde_json::json!([entry.clone(), entry]));
    let error = resolve_compile_database(&ambiguous, root.path(), &source).unwrap_err();
    assert_eq!(error.kind, "compile_database_source_ambiguous");
}

#[test]
fn rejects_response_files_and_unsafe_commands() {
    let root = TestDir::new();
    let source = create_source(root.path());
    let directory = project_directory(&source);
    let response_file = write_database(
        root.path(),
        serde_json::json!([{
            "directory": directory,
            "file": "src/unit.c",
            "arguments": ["clang", "@flags.rsp", "-c", "src/unit.c"]
        }]),
    );
    let error = resolve_compile_database(&response_file, root.path(), &source).unwrap_err();
    assert_eq!(error.kind, "compile_database_response_file_unsupported");

    let unsafe_command = write_database(
        root.path(),
        serde_json::json!([{
            "directory": directory,
            "file": "src/unit.c",
            "command": "clang -c src/unit.c | tee unit.log"
        }]),
    );
    let error = resolve_compile_database(&unsafe_command, root.path(), &source).unwrap_err();
    assert_eq!(error.kind, "invalid_compile_database_entry");
}

#[test]
fn rejects_malformed_entries_and_references() {
    let root = TestDir::new();
    let source = create_source(root.path());
    let directory = project_directory(&source);
    let malformed = write_database(
        root.path(),
        serde_json::json!([{
            "directory": directory,
            "file": "src/unit.c",
            "arguments": ["clang", "-c", "src/unit.c"],
            "command": "clang -c src/unit.c"
        }]),
    );
    let error = resolve_compile_database(&malformed, root.path(), &source).unwrap_err();
    assert_eq!(error.kind, "invalid_compile_database_entry");

    let invalid_reference = CompileDatabaseRef::HashBound {
        path: "../compile_commands.json".to_string(),
        sha256: "0".repeat(64),
    };
    let error = resolve_compile_database(&invalid_reference, root.path(), &source).unwrap_err();
    assert_eq!(error.kind, "invalid_compile_database_reference");
}

use std::fs;
use std::sync::atomic::{AtomicU64, Ordering};

use sha2::Sha256;

static VERIFIED_ARGUMENT_TEST_ID: AtomicU64 = AtomicU64::new(0);

struct VerifiedArgumentTestDir(PathBuf);

impl VerifiedArgumentTestDir {
    fn new() -> Self {
        let id = VERIFIED_ARGUMENT_TEST_ID.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "c2r-verified-arguments-{}-{id}",
            std::process::id()
        ));
        fs::create_dir_all(&path).expect("create verified argument test dir");
        Self(path)
    }
}

impl Drop for VerifiedArgumentTestDir {
    fn drop(&mut self) {
        let _ = fs::remove_dir_all(&self.0);
    }
}

#[test]
fn hash_bound_command_uses_declared_closure_includes_and_preserves_semantic_flags() {
    let root = VerifiedArgumentTestDir::new();
    let source = root.0.join("vendor/src/unit.c");
    let database = root.0.join("closure/compile_commands.json");
    fs::create_dir_all(source.parent().expect("source parent")).expect("create source parent");
    fs::create_dir_all(database.parent().expect("database parent"))
        .expect("create database parent");
    fs::create_dir_all(root.0.join("vendor/include")).expect("create source include");
    fs::create_dir_all(root.0.join("closure/include")).expect("create generated include");
    fs::write(&source, "int unit(void) { return DB_VALUE + BOUND_VALUE; }\n")
        .expect("write source");
    let bytes = serde_json::to_vec(&serde_json::json!([{
        "directory": ".",
        "file": "vendor/src/unit.c",
        "arguments": [
            "clang",
            "-Itarget/stale-generated-include",
            "-isystem", "target/stale-system-include",
            "-DDB_VALUE=3",
            "-std=c11",
            "-c", "vendor/src/unit.c",
            "-o", "unit.o"
        ]
    }]))
    .expect("serialize database");
    fs::write(&database, &bytes).expect("write database");

    let parse_spec = ClangParseSpec {
        source_root: root.0.clone(),
        source_file: PathBuf::from("vendor/src/unit.c"),
        function_name: "unit".to_string(),
        include_paths: vec![
            "vendor/include".to_string(),
            "closure/include".to_string(),
        ],
        defines: vec!["BOUND_VALUE=4".to_string()],
        target_abi: None,
        compile_commands: Some(CompileDatabaseRef::HashBound {
            path: "closure/compile_commands.json".to_string(),
            sha256: format!("{:x}", <Sha256 as sha2::Digest>::digest(&bytes)),
        }),
        source_file_hashes: BTreeMap::new(),
        function_source_span: None,
    };

    let (arguments, diagnostic) =
        verified_parse_arguments(&parse_spec).expect("resolve verified parse arguments");

    assert_eq!(
        arguments,
        [
            "-DDB_VALUE=3",
            "-std=c11",
            &format!("-I{}/vendor/include", root.0.to_string_lossy().replace('\\', "/")),
            &format!("-I{}/closure/include", root.0.to_string_lossy().replace('\\', "/")),
            "-DBOUND_VALUE=4",
        ]
    );
    assert!(diagnostic
        .as_deref()
        .is_some_and(|value| value.contains("hash-bound compile database replay selected")));
    assert!(arguments.iter().all(|value| !value.contains("target/stale")));
}

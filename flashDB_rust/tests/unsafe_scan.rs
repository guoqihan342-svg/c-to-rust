use std::fs;
use std::path::Path;

#[test]
fn first_party_non_test_sources_do_not_use_unsafe() {
    let src = Path::new(env!("CARGO_MANIFEST_DIR")).join("src");
    let mut findings = Vec::new();
    scan(&src, &mut findings);
    assert!(findings.is_empty(), "unsafe findings: {findings:?}");
}

fn scan(path: &Path, findings: &mut Vec<String>) {
    for entry in fs::read_dir(path).unwrap() {
        let entry = entry.unwrap();
        let path = entry.path();
        if path.is_dir() {
            scan(&path, findings);
        } else if path.extension().and_then(|value| value.to_str()) == Some("rs") {
            let text = fs::read_to_string(&path).unwrap();
            for (idx, line) in text.lines().enumerate() {
                let trimmed = line.trim_start();
                if trimmed.starts_with("unsafe fn ") || trimmed.starts_with("unsafe {") {
                    findings.push(format!("{}:{}", path.display(), idx + 1));
                }
            }
        }
    }
}

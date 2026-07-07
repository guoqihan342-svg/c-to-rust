#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stress_report_contains_counts() {
        let out = run(["stress", "--loops", "3", "--seed", "9"]).unwrap();
        assert!(out.contains("\"loops\":3"));
        assert!(out.contains("\"production\":3"));
        assert!(out.contains("\"abnormal\":3"));
        assert!(out.contains("\"reliability\":3"));
    }

    #[test]
    fn inspect_image_reports_hash() {
        let path = std::env::temp_dir().join("flashdb_rust_cli_inspect.img");
        fs::write(&path, [1u8, 2, 3]).unwrap();
        let out = run([
            "inspect-image".to_string(),
            "--path".to_string(),
            path.display().to_string(),
        ])
        .unwrap();
        assert!(out.contains("\"bytes\":3"));
        assert!(out.contains("\"image_hash\""));
        let _ = fs::remove_file(path);
    }

    #[test]
    fn evidence_search_finds_supported_text_matches() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_{}",
            unique_run_id(101)
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(
            dir.join("summary.json"),
            "{\"status\":\"passed\"}\n{\"slice_id\":\"tsdb-user2-status\"}\n",
        )
        .unwrap();
        fs::write(dir.join("trace.log"), "first line\nstatus passed\n").unwrap();
        fs::write(dir.join("ignored.bin"), "status passed\n").unwrap();

        let out = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
            "--query".to_string(),
            "passed".to_string(),
        ])
        .unwrap();

        assert!(out.contains("\"command\":\"evidence-search\""));
        assert!(out.contains("\"schema_version\":1"));
        assert!(out.contains("\"match_count\":2"));
        assert!(out.contains("\"path\":\"summary.json\""));
        assert!(out.contains("\"path\":\"trace.log\""));
        assert!(out.contains("\"line\":1"));
        assert!(out.contains("\"line\":2"));
        assert!(out.contains("\"snippet\":\"{\\\"status\\\":\\\"passed\\\"}\""));
        assert!(!out.contains("ignored.bin"));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn evidence_search_honors_limit_and_supported_extensions() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_limit_{}",
            unique_run_id(102)
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("a.jsonl"), "{\"status\":\"failed\"}\n").unwrap();
        fs::write(dir.join("b.md"), "status failed\n").unwrap();
        fs::write(dir.join("c.bin"), "status failed\n").unwrap();

        let out = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
            "--query".to_string(),
            "failed".to_string(),
            "--limit".to_string(),
            "1".to_string(),
        ])
        .unwrap();

        assert!(out.contains("\"limit\":1"));
        assert!(out.contains("\"match_count\":1"));
        assert!(out.contains("\"path\":\"a.jsonl\""));
        assert!(!out.contains("\"path\":\"b.md\""));
        assert!(!out.contains("c.bin"));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn evidence_search_requires_query() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_missing_query_{}",
            unique_run_id(103)
        ));
        fs::create_dir_all(&dir).unwrap();

        let err = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
        ])
        .unwrap_err();

        assert_eq!(
            err,
            Error::Cli("evidence-search requires --query".to_string())
        );

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn evidence_search_rejects_empty_query() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_empty_query_{}",
            unique_run_id(104)
        ));
        fs::create_dir_all(&dir).unwrap();

        let err = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
            "--query".to_string(),
            "".to_string(),
        ])
        .unwrap_err();

        assert_eq!(
            err,
            Error::Cli("evidence-search requires non-empty --query".to_string())
        );

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn evidence_search_rejects_invalid_limits() {
        for (seed, limit) in [(105, "0"), (106, "10001")] {
            let dir = std::env::temp_dir().join(format!(
                "flashdb_rust_evidence_search_limit_bounds_{}",
                unique_run_id(seed)
            ));
            fs::create_dir_all(&dir).unwrap();

            let err = run([
                "evidence-search".to_string(),
                "--evidence-dir".to_string(),
                dir.display().to_string(),
                "--query".to_string(),
                "passed".to_string(),
                "--limit".to_string(),
                limit.to_string(),
            ])
            .unwrap_err();

            assert_eq!(
                err,
                Error::Cli("evidence-search --limit must be between 1 and 10000".to_string())
            );

            let _ = fs::remove_dir_all(dir);
        }
    }

    #[test]
    fn evidence_search_tolerates_non_utf8_text_evidence() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_non_utf8_{}",
            unique_run_id(107)
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("a-bad.log"), [0xff, b'\n']).unwrap();
        fs::write(dir.join("z-good.json"), "{\"status\":\"passed\"}\n").unwrap();

        let out = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
            "--query".to_string(),
            "passed".to_string(),
        ])
        .unwrap();

        assert!(out.contains("\"match_count\":1"));
        assert!(out.contains("\"path\":\"z-good.json\""));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn evidence_search_bounds_long_snippets() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_long_snippet_{}",
            unique_run_id(108)
        ));
        fs::create_dir_all(&dir).unwrap();
        let long_value = "x".repeat(320);
        fs::write(
            dir.join("long.json"),
            format!("{{\"status\":\"passed\",\"payload\":\"{long_value}\"}}\n"),
        )
        .unwrap();

        let out = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
            "--query".to_string(),
            "passed".to_string(),
        ])
        .unwrap();

        assert!(out.contains("\"snippet\":\"{\\\"status\\\":\\\"passed\\\""));
        assert!(out.contains("..."));
        assert!(!out.contains(&long_value));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn evidence_search_excludes_report_path_from_matches() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_report_exclusion_{}",
            unique_run_id(109)
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("source.json"), "{\"status\":\"passed\"}\n").unwrap();
        let report = dir.join("evidence-search-report.json");
        fs::write(&report, "{\"old_query\":\"passed\"}\n").unwrap();

        let out = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
            "--query".to_string(),
            "passed".to_string(),
            "--report".to_string(),
            report.display().to_string(),
        ])
        .unwrap();

        assert!(out.contains("\"match_count\":1"));
        assert!(out.contains("\"path\":\"source.json\""));
        assert!(!out.contains("\"path\":\"evidence-search-report.json\""));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn evidence_search_escapes_json_control_characters() {
        let dir = std::env::temp_dir().join(format!(
            "flashdb_rust_evidence_search_json_escape_{}",
            unique_run_id(110)
        ));
        fs::create_dir_all(&dir).unwrap();
        fs::write(dir.join("control.log"), "status\tpassed\u{1}\n").unwrap();

        let out = run([
            "evidence-search".to_string(),
            "--evidence-dir".to_string(),
            dir.display().to_string(),
            "--query".to_string(),
            "\tpassed".to_string(),
        ])
        .unwrap();

        assert!(out.contains("\"query\":\"\\tpassed\""));
        assert!(out.contains("\"snippet\":\"status\\tpassed\\u0001\""));
        assert!(!out.contains('\t'));
        assert!(!out.contains('\u{1}'));

        let _ = fs::remove_dir_all(dir);
    }

    #[test]
    fn unsafe_scan_classifies_review_relevant_categories() {
        let path = Path::new("src/demo.rs");
        let samples = [
            ("pub unsafe fn call() {}", "unsafe_function"),
            ("unsafe { do_work(); }", "unsafe_block"),
            ("unsafe impl Send for Demo {}", "unsafe_impl"),
            ("extern \"C\" { fn c_call(); }", "extern_c"),
            ("#[repr(C)] struct Demo { value: u32 }", "repr_c"),
            ("#[repr(C, packed)] struct Demo { value: u32 }", "repr_c"),
            (
                "let value = std::mem::transmute::<u32, i32>(raw);",
                "transmute",
            ),
            ("let ptr: *mut u8 = buffer.as_mut_ptr();", "raw_pointer"),
        ];

        for (line, category) in samples {
            let findings = unsafe_findings_in_line(path, 7, line);
            assert!(
                findings.iter().any(|finding| finding.category == category),
                "missing category {category} for line {line}; findings={findings:?}"
            );
        }
    }
}

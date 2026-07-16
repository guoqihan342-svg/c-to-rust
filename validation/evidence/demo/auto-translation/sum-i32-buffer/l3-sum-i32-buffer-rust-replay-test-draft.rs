// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

// ReplayCallPlan-SHA256: f6c2e4a70e461e26a3a5d6bc37be233cef12727fa4986a017d9eda33be255219
#[test]
fn replay_sum_i32_buffer_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/sum-i32-buffer-c-oracle.json";
    let _api = "sum_i32_buffer";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    {
        let case_id = "empty";
        let mut actual_empty_0_out: [i32; 1] = [0i32; 1];
        let actual_return: i32 = sum_i32_buffer(&[], 0i32, &mut actual_empty_0_out);
        let observed_empty_0_0: i32 = actual_return;
        if observed_empty_0_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:479d618842d388d924f58a212682f7d5a3e405efd946210272095e24e3c5ef35"); }
        let observed_empty_0_1: i32 = actual_empty_0_out[0];
        if observed_empty_0_1 != 0i32 { panic!("C2R_REPLAY_ASSERT:a8718974e00093b91563b18fce643e3c0146f65ceed323e6b2ef1325dee7413a"); }
        assert_eq!("ok", "ok", "{} status metadata drifted", case_id);
        assert_eq!("values[i] under i < len", "values[i] under i < len", "{} source_reads metadata drifted", case_id);
        assert_eq!("out[0]", "out[0]", "{} source_write metadata drifted", case_id);
        assert_eq!(0i32, 0i32, "{} fixture relation equal drifted", case_id);
        assert_eq!(vec![0i32; 0usize].len(), 0usize, "{} fixture relation length_equals drifted", case_id);
    }
    {
        let case_id = "single-positive";
        let mut actual_single_positive_1_out: [i32; 1] = [0i32; 1];
        let actual_return: i32 = sum_i32_buffer(&[7i32], 1i32, &mut actual_single_positive_1_out);
        let observed_single_positive_1_0: i32 = actual_return;
        if observed_single_positive_1_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:87483558296d2a29107b6bfb229428a0ae9754842c18af4ac4f279236fbae3e2"); }
        let observed_single_positive_1_1: i32 = actual_single_positive_1_out[0];
        if observed_single_positive_1_1 != 7i32 { panic!("C2R_REPLAY_ASSERT:f00f1920146830d251e66216061bedcea6c582beb5dcecf9685c727fe9b2c066"); }
        assert_eq!("ok", "ok", "{} status metadata drifted", case_id);
        assert_eq!("values[i] under i < len", "values[i] under i < len", "{} source_reads metadata drifted", case_id);
        assert_eq!("out[0]", "out[0]", "{} source_write metadata drifted", case_id);
        assert_eq!(1i32, 1i32, "{} fixture relation equal drifted", case_id);
        assert_eq!(vec![7i32].len(), 1usize, "{} fixture relation length_equals drifted", case_id);
    }
    {
        let case_id = "mixed-negative";
        let mut actual_mixed_negative_2_out: [i32; 1] = [0i32; 1];
        let actual_return: i32 = sum_i32_buffer(&[-5i32, 2i32, -3i32, 6i32], 4i32, &mut actual_mixed_negative_2_out);
        let observed_mixed_negative_2_0: i32 = actual_return;
        if observed_mixed_negative_2_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:c380d299209c44566720ccf9287d1ec4528aa3f9c86ded0092e206d26c5fc81e"); }
        let observed_mixed_negative_2_1: i32 = actual_mixed_negative_2_out[0];
        if observed_mixed_negative_2_1 != 0i32 { panic!("C2R_REPLAY_ASSERT:20a5243c6b09269dd4a8dfdf98af632da1b116ae68825a64ade06a2168865fdc"); }
        assert_eq!("ok", "ok", "{} status metadata drifted", case_id);
        assert_eq!("values[i] under i < len", "values[i] under i < len", "{} source_reads metadata drifted", case_id);
        assert_eq!("out[0]", "out[0]", "{} source_write metadata drifted", case_id);
        assert_eq!(4i32, 4i32, "{} fixture relation equal drifted", case_id);
        assert_eq!(vec![-5i32, 2i32, -3i32, 6i32].len(), 4usize, "{} fixture relation length_equals drifted", case_id);
    }
    {
        let case_id = "boundary-safe";
        let mut actual_boundary_safe_3_out: [i32; 1] = [0i32; 1];
        let actual_return: i32 = sum_i32_buffer(&[1073741823i32, 1073741823i32, -1i32], 3i32, &mut actual_boundary_safe_3_out);
        let observed_boundary_safe_3_0: i32 = actual_return;
        if observed_boundary_safe_3_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:da3b1f2cfc5eeb06a51fe2c62d4b1d081fbffa161301c6109e448ad53c7ea77e"); }
        let observed_boundary_safe_3_1: i32 = actual_boundary_safe_3_out[0];
        if observed_boundary_safe_3_1 != 2147483645i32 { panic!("C2R_REPLAY_ASSERT:9fffcbe1418b4a27a140e44d1717047abb8a3532616075cd85c23126825c59f1"); }
        assert_eq!("ok", "ok", "{} status metadata drifted", case_id);
        assert_eq!("values[i] under i < len", "values[i] under i < len", "{} source_reads metadata drifted", case_id);
        assert_eq!("out[0]", "out[0]", "{} source_write metadata drifted", case_id);
        assert_eq!(3i32, 3i32, "{} fixture relation equal drifted", case_id);
        assert_eq!(vec![1073741823i32, 1073741823i32, -1i32].len(), 3usize, "{} fixture relation length_equals drifted", case_id);
    }
}

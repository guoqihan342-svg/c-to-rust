// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

// ReplayCallPlan-SHA256: 84f8638cd5b9a86e1d33203385000409f6f74d59b3f402f337698970c6e15759
#[test]
fn replay_copy_i32_ptr_arith_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/copy-i32-ptr-arith-c-oracle.json";
    let _api = "copy_i32_ptr_arith";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    {
        let case_id = "empty";
        let mut actual_empty_0_out: Vec<i32> = vec![0i32; 0usize];
        let actual_return: i32 = copy_i32_ptr_arith(&[], 0i32, &mut actual_empty_0_out);
        let observed_empty_0_0: i32 = actual_return;
        if observed_empty_0_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:7d48c7730e38a8750ca822b7bd2ff771ea7f052ab10612acc73195620adcb1f1"); }
        let observed_empty_0_1: Vec<i32> = actual_empty_0_out;
        if observed_empty_0_1 != vec![0i32; 0usize] { panic!("C2R_REPLAY_ASSERT:10485939883cc320ca7b22c1a66d2acb08b4a6538b1a82cf67a78db202f95013"); }
        assert_eq!("ok", "ok", "{} status metadata drifted", case_id);
        assert_eq!("*(values + i) under i < len", "*(values + i) under i < len", "{} source_reads metadata drifted", case_id);
        assert_eq!("values[i]", "values[i]", "{} canonical_reads metadata drifted", case_id);
        assert_eq!("*(out + i) under i < len", "*(out + i) under i < len", "{} source_writes metadata drifted", case_id);
        assert_eq!("out[i]", "out[i]", "{} canonical_writes metadata drifted", case_id);
        assert_eq!(vec![0i32; 0usize], vec![0i32; 0usize], "{} fixture relation equal drifted", case_id);
        assert_eq!(0i32, 0i32, "{} fixture relation equal drifted", case_id);
        assert_eq!(vec![0i32; 0usize].len(), 0usize, "{} fixture relation length_equals drifted", case_id);
        assert_eq!(vec![0i32; 0usize].len(), 0usize, "{} fixture relation length_equals drifted", case_id);
        assert_eq!(0usize, 0usize, "{} fixture relation numeric_equal drifted", case_id);
    }
    {
        let case_id = "single-positive";
        let mut actual_single_positive_1_out: Vec<i32> = vec![0i32; 1usize];
        let actual_return: i32 = copy_i32_ptr_arith(&[7i32], 1i32, &mut actual_single_positive_1_out);
        let observed_single_positive_1_0: i32 = actual_return;
        if observed_single_positive_1_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:439db86ceccc58294ca31b407ab0bea12824b95d0878ee470c5dd37e9af1e2b3"); }
        let observed_single_positive_1_1: Vec<i32> = actual_single_positive_1_out;
        if observed_single_positive_1_1 != vec![7i32] { panic!("C2R_REPLAY_ASSERT:e5874dd3bdffe1959ebd148d6d3170f46167cd22daa714c740a4da476b0548e6"); }
        assert_eq!("ok", "ok", "{} status metadata drifted", case_id);
        assert_eq!("*(values + i) under i < len", "*(values + i) under i < len", "{} source_reads metadata drifted", case_id);
        assert_eq!("values[i]", "values[i]", "{} canonical_reads metadata drifted", case_id);
        assert_eq!("*(out + i) under i < len", "*(out + i) under i < len", "{} source_writes metadata drifted", case_id);
        assert_eq!("out[i]", "out[i]", "{} canonical_writes metadata drifted", case_id);
        assert_eq!(vec![7i32], vec![7i32], "{} fixture relation equal drifted", case_id);
        assert_eq!(1i32, 1i32, "{} fixture relation equal drifted", case_id);
        assert_eq!(vec![7i32].len(), 1usize, "{} fixture relation length_equals drifted", case_id);
        assert_eq!(vec![7i32].len(), 1usize, "{} fixture relation length_equals drifted", case_id);
        assert_eq!(1usize, 1usize, "{} fixture relation numeric_equal drifted", case_id);
    }
    {
        let case_id = "mixed-negative";
        let mut actual_mixed_negative_2_out: Vec<i32> = vec![0i32; 4usize];
        let actual_return: i32 = copy_i32_ptr_arith(&[-5i32, 2i32, -3i32, 6i32], 4i32, &mut actual_mixed_negative_2_out);
        let observed_mixed_negative_2_0: i32 = actual_return;
        if observed_mixed_negative_2_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:47383a4a61dea989acb0acfd014a52a77b0ec15e55ba6d4fd0714acaa9d3efb7"); }
        let observed_mixed_negative_2_1: Vec<i32> = actual_mixed_negative_2_out;
        if observed_mixed_negative_2_1 != vec![-5i32, 2i32, -3i32, 6i32] { panic!("C2R_REPLAY_ASSERT:ee08f016d62714b071b8bccf63252e97dea8fad3bd5188bc5268801a5e9f6474"); }
        assert_eq!("ok", "ok", "{} status metadata drifted", case_id);
        assert_eq!("*(values + i) under i < len", "*(values + i) under i < len", "{} source_reads metadata drifted", case_id);
        assert_eq!("values[i]", "values[i]", "{} canonical_reads metadata drifted", case_id);
        assert_eq!("*(out + i) under i < len", "*(out + i) under i < len", "{} source_writes metadata drifted", case_id);
        assert_eq!("out[i]", "out[i]", "{} canonical_writes metadata drifted", case_id);
        assert_eq!(vec![-5i32, 2i32, -3i32, 6i32], vec![-5i32, 2i32, -3i32, 6i32], "{} fixture relation equal drifted", case_id);
        assert_eq!(4i32, 4i32, "{} fixture relation equal drifted", case_id);
        assert_eq!(vec![-5i32, 2i32, -3i32, 6i32].len(), 4usize, "{} fixture relation length_equals drifted", case_id);
        assert_eq!(vec![-5i32, 2i32, -3i32, 6i32].len(), 4usize, "{} fixture relation length_equals drifted", case_id);
        assert_eq!(4usize, 4usize, "{} fixture relation numeric_equal drifted", case_id);
    }
    {
        let case_id = "boundary-safe";
        let mut actual_boundary_safe_3_out: Vec<i32> = vec![0i32; 3usize];
        let actual_return: i32 = copy_i32_ptr_arith(&[1073741823i32, -1073741824i32, -1i32], 3i32, &mut actual_boundary_safe_3_out);
        let observed_boundary_safe_3_0: i32 = actual_return;
        if observed_boundary_safe_3_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:aa21a6136b45625115d4a15371a14ecae599f41513c677d4542d0904a28667bf"); }
        let observed_boundary_safe_3_1: Vec<i32> = actual_boundary_safe_3_out;
        if observed_boundary_safe_3_1 != vec![1073741823i32, -1073741824i32, -1i32] { panic!("C2R_REPLAY_ASSERT:09c34ea6921148cd3dee2b3f484297e96fef81541b9e67f9f0f09c00dc72b090"); }
        assert_eq!("ok", "ok", "{} status metadata drifted", case_id);
        assert_eq!("*(values + i) under i < len", "*(values + i) under i < len", "{} source_reads metadata drifted", case_id);
        assert_eq!("values[i]", "values[i]", "{} canonical_reads metadata drifted", case_id);
        assert_eq!("*(out + i) under i < len", "*(out + i) under i < len", "{} source_writes metadata drifted", case_id);
        assert_eq!("out[i]", "out[i]", "{} canonical_writes metadata drifted", case_id);
        assert_eq!(vec![1073741823i32, -1073741824i32, -1i32], vec![1073741823i32, -1073741824i32, -1i32], "{} fixture relation equal drifted", case_id);
        assert_eq!(3i32, 3i32, "{} fixture relation equal drifted", case_id);
        assert_eq!(vec![1073741823i32, -1073741824i32, -1i32].len(), 3usize, "{} fixture relation length_equals drifted", case_id);
        assert_eq!(vec![1073741823i32, -1073741824i32, -1i32].len(), 3usize, "{} fixture relation length_equals drifted", case_id);
        assert_eq!(3usize, 3usize, "{} fixture relation numeric_equal drifted", case_id);
    }
}

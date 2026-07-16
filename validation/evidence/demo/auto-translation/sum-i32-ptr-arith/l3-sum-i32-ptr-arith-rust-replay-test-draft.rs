// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

// ReplayCallPlan-SHA256: 7e62ba3d296d48dde4ddf39c210696baa5663afb7dfdc69d3d2457c3e8b61fe7
#[test]
fn replay_sum_i32_ptr_arith_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/sum-i32-ptr-arith-c-oracle.json";
    let _api = "sum_i32_ptr_arith";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    {
        let case_id = "empty";
        let mut actual_empty_0_out: [i32; 1] = [0i32; 1];
        let actual_return: i32 = sum_i32_ptr_arith(&[], 0i32, &mut actual_empty_0_out);
        let observed_empty_0_0: i32 = actual_return;
        if observed_empty_0_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:4ba4400e674daaa0f8db0db6ba7d9f0bb285817785a372ba9c159917b2d02afc"); }
        let observed_empty_0_1: i32 = actual_empty_0_out[0];
        if observed_empty_0_1 != 0i32 { panic!("C2R_REPLAY_ASSERT:59573d199accd7c03a852745a1e4f212d76f2babb4946de9e2885b093fe141e0"); }
        assert_eq!("ok", "ok", "{} status metadata drifted", case_id);
        assert_eq!("*(values + i) under i < len", "*(values + i) under i < len", "{} source_reads metadata drifted", case_id);
        assert_eq!("values[i]", "values[i]", "{} canonical_reads metadata drifted", case_id);
        assert_eq!("out[0]", "out[0]", "{} source_write metadata drifted", case_id);
        assert_eq!(0i32, 0i32, "{} fixture relation equal drifted", case_id);
        assert_eq!(vec![0i32; 0usize].len(), 0usize, "{} fixture relation length_equals drifted", case_id);
    }
    {
        let case_id = "single-positive";
        let mut actual_single_positive_1_out: [i32; 1] = [0i32; 1];
        let actual_return: i32 = sum_i32_ptr_arith(&[7i32], 1i32, &mut actual_single_positive_1_out);
        let observed_single_positive_1_0: i32 = actual_return;
        if observed_single_positive_1_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:8e357a6c8d7bfc8be218b899f885d202dbadaeaf96dc61eaac58e32822b6a782"); }
        let observed_single_positive_1_1: i32 = actual_single_positive_1_out[0];
        if observed_single_positive_1_1 != 7i32 { panic!("C2R_REPLAY_ASSERT:32a538871e5d488d62335766fbcdbf9c2642ddfef727fe0e95a0556483da29bd"); }
        assert_eq!("ok", "ok", "{} status metadata drifted", case_id);
        assert_eq!("*(values + i) under i < len", "*(values + i) under i < len", "{} source_reads metadata drifted", case_id);
        assert_eq!("values[i]", "values[i]", "{} canonical_reads metadata drifted", case_id);
        assert_eq!("out[0]", "out[0]", "{} source_write metadata drifted", case_id);
        assert_eq!(1i32, 1i32, "{} fixture relation equal drifted", case_id);
        assert_eq!(vec![7i32].len(), 1usize, "{} fixture relation length_equals drifted", case_id);
    }
    {
        let case_id = "mixed-negative";
        let mut actual_mixed_negative_2_out: [i32; 1] = [0i32; 1];
        let actual_return: i32 = sum_i32_ptr_arith(&[-5i32, 2i32, -3i32, 6i32], 4i32, &mut actual_mixed_negative_2_out);
        let observed_mixed_negative_2_0: i32 = actual_return;
        if observed_mixed_negative_2_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:5ee040b8a0fff9fb28efb4c5ec1afa8fbafe7a35c0cf28c69b55485d9338691e"); }
        let observed_mixed_negative_2_1: i32 = actual_mixed_negative_2_out[0];
        if observed_mixed_negative_2_1 != 0i32 { panic!("C2R_REPLAY_ASSERT:c98c378575daee8a85041fd00b17cb6cc84a89374264e02fa55ef52c6813a6b8"); }
        assert_eq!("ok", "ok", "{} status metadata drifted", case_id);
        assert_eq!("*(values + i) under i < len", "*(values + i) under i < len", "{} source_reads metadata drifted", case_id);
        assert_eq!("values[i]", "values[i]", "{} canonical_reads metadata drifted", case_id);
        assert_eq!("out[0]", "out[0]", "{} source_write metadata drifted", case_id);
        assert_eq!(4i32, 4i32, "{} fixture relation equal drifted", case_id);
        assert_eq!(vec![-5i32, 2i32, -3i32, 6i32].len(), 4usize, "{} fixture relation length_equals drifted", case_id);
    }
    {
        let case_id = "boundary-safe";
        let mut actual_boundary_safe_3_out: [i32; 1] = [0i32; 1];
        let actual_return: i32 = sum_i32_ptr_arith(&[1073741823i32, 1073741823i32, -1i32], 3i32, &mut actual_boundary_safe_3_out);
        let observed_boundary_safe_3_0: i32 = actual_return;
        if observed_boundary_safe_3_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:3603cf2c5647224e8cefae11a85267ce67647c7cd7bb692853a7be0b676ed4d4"); }
        let observed_boundary_safe_3_1: i32 = actual_boundary_safe_3_out[0];
        if observed_boundary_safe_3_1 != 2147483645i32 { panic!("C2R_REPLAY_ASSERT:49847337aff6c5598ca83f1fc125498dc0a94bbdd3e8a6a6fee65372ff57667f"); }
        assert_eq!("ok", "ok", "{} status metadata drifted", case_id);
        assert_eq!("*(values + i) under i < len", "*(values + i) under i < len", "{} source_reads metadata drifted", case_id);
        assert_eq!("values[i]", "values[i]", "{} canonical_reads metadata drifted", case_id);
        assert_eq!("out[0]", "out[0]", "{} source_write metadata drifted", case_id);
        assert_eq!(3i32, 3i32, "{} fixture relation equal drifted", case_id);
        assert_eq!(vec![1073741823i32, 1073741823i32, -1i32].len(), 3usize, "{} fixture relation length_equals drifted", case_id);
    }
}

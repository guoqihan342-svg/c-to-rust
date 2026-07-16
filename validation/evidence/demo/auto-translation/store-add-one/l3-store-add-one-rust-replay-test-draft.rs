// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

// ReplayCallPlan-SHA256: e1ecc115d4bf3d874625342ba46b4febaa0ad68d139ce6b301446d0f32d56c84
#[test]
fn replay_store_add_one_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/store-add-one-c-oracle.json";
    let _api = "store_add_one";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    {
        let case_id = "int-min";
        let mut actual_int_min_0_out: [i32; 1] = [0i32; 1];
        let actual_return: i32 = store_add_one(-2147483648i32, &mut actual_int_min_0_out);
        let observed_int_min_0_0: i32 = actual_return;
        if observed_int_min_0_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:54c1576d2d10aeaf5613f19433db42b2dbd8f845abc57f0e7a7af2ba52e69311"); }
        let observed_int_min_0_1: i32 = actual_int_min_0_out[0];
        if observed_int_min_0_1 != -2147483647i32 { panic!("C2R_REPLAY_ASSERT:8bff86331f71a5bb7e2eee6c557b1935ecbfd58b5e6e1b448152d226b4832673"); }
        assert_eq!("ok", "ok", "{} status metadata drifted", case_id);
    }
    {
        let case_id = "zero";
        let mut actual_zero_1_out: [i32; 1] = [0i32; 1];
        let actual_return: i32 = store_add_one(0i32, &mut actual_zero_1_out);
        let observed_zero_1_0: i32 = actual_return;
        if observed_zero_1_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:2845ffe6f7b85bcf681ae3ac2534b10f738b6b8b7cbf657d803114cf668baa3a"); }
        let observed_zero_1_1: i32 = actual_zero_1_out[0];
        if observed_zero_1_1 != 1i32 { panic!("C2R_REPLAY_ASSERT:5c01c52659b739ac6982111a468a8629b11c16f6cef0fed00d994299aa42d827"); }
        assert_eq!("ok", "ok", "{} status metadata drifted", case_id);
    }
    {
        let case_id = "int-max-minus-one";
        let mut actual_int_max_minus_one_2_out: [i32; 1] = [0i32; 1];
        let actual_return: i32 = store_add_one(2147483646i32, &mut actual_int_max_minus_one_2_out);
        let observed_int_max_minus_one_2_0: i32 = actual_return;
        if observed_int_max_minus_one_2_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:57789472e47b6e723320a9a24added26cca5f31339f06470e646cb7e0a817361"); }
        let observed_int_max_minus_one_2_1: i32 = actual_int_max_minus_one_2_out[0];
        if observed_int_max_minus_one_2_1 != 2147483647i32 { panic!("C2R_REPLAY_ASSERT:e052a8b0c2e7d5f7ee7c48dc80bdbbac805f12395aa029b273711e0e7ed83527"); }
        assert_eq!("ok", "ok", "{} status metadata drifted", case_id);
    }
}

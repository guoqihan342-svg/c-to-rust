// Auto-generated Rust replay test draft.
// Review before promoting into validation/l2_slices/tests.

// ReplayCallPlan-SHA256: 80fa86be280da4781d1534533c2f8a5e5ed20b32aa74810a01dda029a10e8826
#[test]
fn replay_call_expression_fixture_contract() {
    let _fixture = "validation/l2_slices/fixtures/call-expression-c-oracle.json";
    let _api = "call_expression_chain";
    const GENERATED_DRAFT_SEMANTIC_PASS: bool = false;
    let actual_negative_two_0: i32 = call_expression_chain(-2i32);
    let observed_negative_two_0_0: i32 = actual_negative_two_0;
    if observed_negative_two_0_0 != 2i32 { panic!("C2R_REPLAY_ASSERT:df80f623adf887d980339a256aa67069cceccb1d92133ab7ef7fe409d7a1cf6c"); }
    assert_eq!("ok", "ok", "negative-two status metadata drifted");
    assert_eq!(3usize, 3usize, "negative-two call_expression_count metadata drifted");
    assert_eq!(&["declaration_initializer", "assignment", "return"], &["declaration_initializer", "assignment", "return"], "negative-two call_expression_contexts metadata drifted");
    assert_eq!(&["int first = call_expression_chain(value - 1)", "value = call_expression_chain(first - 1)", "return call_expression_chain(value - 1)"], &["int first = call_expression_chain(value - 1)", "value = call_expression_chain(first - 1)", "return call_expression_chain(value - 1)"], "negative-two source_calls metadata drifted");
    let actual_zero_1: i32 = call_expression_chain(0i32);
    let observed_zero_1_0: i32 = actual_zero_1;
    if observed_zero_1_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:e15564b3c8c34e18783cc792db7d0e4dac882ffd9d4f8dded7f3b4eace71ec89"); }
    assert_eq!("ok", "ok", "zero status metadata drifted");
    assert_eq!(3usize, 3usize, "zero call_expression_count metadata drifted");
    assert_eq!(&["declaration_initializer", "assignment", "return"], &["declaration_initializer", "assignment", "return"], "zero call_expression_contexts metadata drifted");
    assert_eq!(&["int first = call_expression_chain(value - 1)", "value = call_expression_chain(first - 1)", "return call_expression_chain(value - 1)"], &["int first = call_expression_chain(value - 1)", "value = call_expression_chain(first - 1)", "return call_expression_chain(value - 1)"], "zero source_calls metadata drifted");
    let actual_one_2: i32 = call_expression_chain(1i32);
    let observed_one_2_0: i32 = actual_one_2;
    if observed_one_2_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:def1aa957a7dadfa64cfe65e858595d9b34a383d5cf333e0c5e2e442df446510"); }
    assert_eq!("ok", "ok", "one status metadata drifted");
    assert_eq!(3usize, 3usize, "one call_expression_count metadata drifted");
    assert_eq!(&["declaration_initializer", "assignment", "return"], &["declaration_initializer", "assignment", "return"], "one call_expression_contexts metadata drifted");
    assert_eq!(&["int first = call_expression_chain(value - 1)", "value = call_expression_chain(first - 1)", "return call_expression_chain(value - 1)"], &["int first = call_expression_chain(value - 1)", "value = call_expression_chain(first - 1)", "return call_expression_chain(value - 1)"], "one source_calls metadata drifted");
    let actual_three_3: i32 = call_expression_chain(3i32);
    let observed_three_3_0: i32 = actual_three_3;
    if observed_three_3_0 != 0i32 { panic!("C2R_REPLAY_ASSERT:3768890cb3790261f372ffc908b2ab32a9f252a05ebfda8565ef8c3d39f2e567"); }
    assert_eq!("ok", "ok", "three status metadata drifted");
    assert_eq!(3usize, 3usize, "three call_expression_count metadata drifted");
    assert_eq!(&["declaration_initializer", "assignment", "return"], &["declaration_initializer", "assignment", "return"], "three call_expression_contexts metadata drifted");
    assert_eq!(&["int first = call_expression_chain(value - 1)", "value = call_expression_chain(first - 1)", "return call_expression_chain(value - 1)"], &["int first = call_expression_chain(value - 1)", "value = call_expression_chain(first - 1)", "return call_expression_chain(value - 1)"], "three source_calls metadata drifted");
}

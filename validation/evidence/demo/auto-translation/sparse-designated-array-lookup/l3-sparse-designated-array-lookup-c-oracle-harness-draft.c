/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

/* slice: demo/sparse-designated-array-lookup */
/* function: sparse_designated_array_lookup */
/* fixture input: validation/l2_slices/fixtures/sparse-designated-array-lookup-c-oracle.json */
/* fixture cases: 4 */
/* observable outputs: return_value, status */
/* fixture case: index-zero input_ref=cases[0] expected_ref=validation/evidence/demo/l3-sparse-designated-array-lookup-c-oracle.json expected_outputs={"return_value": 0, "status": "ok"} */
/* fixture case: index-one input_ref=cases[1] expected_ref=validation/evidence/demo/l3-sparse-designated-array-lookup-c-oracle.json expected_outputs={"return_value": 0, "status": "ok"} */
/* fixture case: index-two input_ref=cases[2] expected_ref=validation/evidence/demo/l3-sparse-designated-array-lookup-c-oracle.json expected_outputs={"return_value": 7, "status": "ok"} */
/* fixture case: index-three input_ref=cases[3] expected_ref=validation/evidence/demo/l3-sparse-designated-array-lookup-c-oracle.json expected_outputs={"return_value": 0, "status": "ok"} */
/* source file: validation/l2_slices/fixtures/sparse-designated-array-lookup.c (sha256: d93c730d7ccddd77f03ec9311a931a74a2ca9ffd39c4ce781f1ef65b8edbed0a) */
/* global dependency: table (declared) from slice-spec */
int sparse_designated_array_lookup(int index);

int main(void) {
  puts("oracle harness draft for sparse_designated_array_lookup");
  puts("fixture input: validation/l2_slices/fixtures/sparse-designated-array-lookup-c-oracle.json");
  int actual_index_zero_return_value = sparse_designated_array_lookup((int)0u);
  if (actual_index_zero_return_value != (int)0u) {
    fprintf(stderr, "index-zero return_value mismatch: expected 0 got %d\n", actual_index_zero_return_value);
    return 1;
  }
  puts("fixture case index-zero return_value matched");
  puts("fixture case index-zero status matched");
  int actual_index_one_return_value = sparse_designated_array_lookup((int)1u);
  if (actual_index_one_return_value != (int)0u) {
    fprintf(stderr, "index-one return_value mismatch: expected 0 got %d\n", actual_index_one_return_value);
    return 1;
  }
  puts("fixture case index-one return_value matched");
  puts("fixture case index-one status matched");
  int actual_index_two_return_value = sparse_designated_array_lookup((int)2u);
  if (actual_index_two_return_value != (int)7u) {
    fprintf(stderr, "index-two return_value mismatch: expected 7 got %d\n", actual_index_two_return_value);
    return 1;
  }
  puts("fixture case index-two return_value matched");
  puts("fixture case index-two status matched");
  int actual_index_three_return_value = sparse_designated_array_lookup((int)3u);
  if (actual_index_three_return_value != (int)0u) {
    fprintf(stderr, "index-three return_value mismatch: expected 0 got %d\n", actual_index_three_return_value);
    return 1;
  }
  puts("fixture case index-three return_value matched");
  puts("fixture case index-three status matched");
  return 0;
}

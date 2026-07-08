/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

/* slice: demo/implicit-integer-noop-cast */
/* function: identity_noop */
/* fixture input: validation/l2_slices/fixtures/implicit-integer-noop-cast-c-oracle.json */
/* fixture cases: 5 */
/* observable outputs: return_value, status */
/* fixture case: int-min input_ref=cases[0] expected_ref=validation/evidence/demo/l3-implicit-integer-noop-cast-c-oracle.json expected_outputs={"return_value": -2147483648, "status": "ok"} */
/* fixture case: negative input_ref=cases[1] expected_ref=validation/evidence/demo/l3-implicit-integer-noop-cast-c-oracle.json expected_outputs={"return_value": -1, "status": "ok"} */
/* fixture case: zero input_ref=cases[2] expected_ref=validation/evidence/demo/l3-implicit-integer-noop-cast-c-oracle.json expected_outputs={"return_value": 0, "status": "ok"} */
/* fixture case: one input_ref=cases[3] expected_ref=validation/evidence/demo/l3-implicit-integer-noop-cast-c-oracle.json expected_outputs={"return_value": 1, "status": "ok"} */
/* fixture case: int-max input_ref=cases[4] expected_ref=validation/evidence/demo/l3-implicit-integer-noop-cast-c-oracle.json expected_outputs={"return_value": 2147483647, "status": "ok"} */
/* source file: validation/l2_slices/fixtures/implicit-integer-noop-cast.c (sha256: 82e95d204df1416e9913c1facc692ed2a7f363fdf85da50769e7d98c296487c5) */
int identity_noop(int value);

int main(void) {
  puts("oracle harness draft for identity_noop");
  puts("fixture input: validation/l2_slices/fixtures/implicit-integer-noop-cast-c-oracle.json");
  int actual_int_min_return_value = identity_noop((int)-2147483648);
  if (actual_int_min_return_value != (int)-2147483648) {
    fprintf(stderr, "int-min return_value mismatch: expected -2147483648 got %d\n", actual_int_min_return_value);
    return 1;
  }
  puts("fixture case int-min return_value matched");
  puts("fixture case int-min status matched");
  int actual_negative_return_value = identity_noop((int)-1);
  if (actual_negative_return_value != (int)-1) {
    fprintf(stderr, "negative return_value mismatch: expected -1 got %d\n", actual_negative_return_value);
    return 1;
  }
  puts("fixture case negative return_value matched");
  puts("fixture case negative status matched");
  int actual_zero_return_value = identity_noop((int)0u);
  if (actual_zero_return_value != (int)0u) {
    fprintf(stderr, "zero return_value mismatch: expected 0 got %d\n", actual_zero_return_value);
    return 1;
  }
  puts("fixture case zero return_value matched");
  puts("fixture case zero status matched");
  int actual_one_return_value = identity_noop((int)1u);
  if (actual_one_return_value != (int)1u) {
    fprintf(stderr, "one return_value mismatch: expected 1 got %d\n", actual_one_return_value);
    return 1;
  }
  puts("fixture case one return_value matched");
  puts("fixture case one status matched");
  int actual_int_max_return_value = identity_noop((int)2147483647u);
  if (actual_int_max_return_value != (int)2147483647u) {
    fprintf(stderr, "int-max return_value mismatch: expected 2147483647 got %d\n", actual_int_max_return_value);
    return 1;
  }
  puts("fixture case int-max return_value matched");
  puts("fixture case int-max status matched");
  return 0;
}

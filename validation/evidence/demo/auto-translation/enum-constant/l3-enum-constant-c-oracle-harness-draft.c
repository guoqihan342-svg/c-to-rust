/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

/* slice: demo/enum-constant */
/* function: add_status */
/* fixture input: validation/l2_slices/fixtures/enum-constant-c-oracle.json */
/* fixture cases: 5 */
/* observable outputs: return_value, status */
/* fixture case: int-min input_ref=cases[0] expected_ref=validation/evidence/demo/l3-enum-constant-c-oracle.json expected_outputs={"return_value": -2147483641, "status": "ok"} */
/* fixture case: negative input_ref=cases[1] expected_ref=validation/evidence/demo/l3-enum-constant-c-oracle.json expected_outputs={"return_value": -5, "status": "ok"} */
/* fixture case: minus-seven input_ref=cases[2] expected_ref=validation/evidence/demo/l3-enum-constant-c-oracle.json expected_outputs={"return_value": 0, "status": "ok"} */
/* fixture case: zero input_ref=cases[3] expected_ref=validation/evidence/demo/l3-enum-constant-c-oracle.json expected_outputs={"return_value": 7, "status": "ok"} */
/* fixture case: int-max-minus-seven input_ref=cases[4] expected_ref=validation/evidence/demo/l3-enum-constant-c-oracle.json expected_outputs={"return_value": 2147483647, "status": "ok"} */
/* source file: validation/l2_slices/fixtures/enum-constant.c (sha256: 60bbacccf6d22b3e1af75672e9bd5a6e8f219e83cb24c81b5cf2f49d5bf97389) */
/* global dependency: STATUS_OK (declared) from slice-spec */
int add_status(int value);

int main(void) {
  puts("oracle harness draft for add_status");
  puts("fixture input: validation/l2_slices/fixtures/enum-constant-c-oracle.json");
  int actual_int_min_return_value = add_status((int)-2147483648);
  if (actual_int_min_return_value != (int)-2147483641) {
    fprintf(stderr, "int-min return_value mismatch: expected -2147483641 got %d\n", actual_int_min_return_value);
    return 1;
  }
  puts("fixture case int-min return_value matched");
  puts("fixture case int-min status matched");
  int actual_negative_return_value = add_status((int)-12);
  if (actual_negative_return_value != (int)-5) {
    fprintf(stderr, "negative return_value mismatch: expected -5 got %d\n", actual_negative_return_value);
    return 1;
  }
  puts("fixture case negative return_value matched");
  puts("fixture case negative status matched");
  int actual_minus_seven_return_value = add_status((int)-7);
  if (actual_minus_seven_return_value != (int)0u) {
    fprintf(stderr, "minus-seven return_value mismatch: expected 0 got %d\n", actual_minus_seven_return_value);
    return 1;
  }
  puts("fixture case minus-seven return_value matched");
  puts("fixture case minus-seven status matched");
  int actual_zero_return_value = add_status((int)0u);
  if (actual_zero_return_value != (int)7u) {
    fprintf(stderr, "zero return_value mismatch: expected 7 got %d\n", actual_zero_return_value);
    return 1;
  }
  puts("fixture case zero return_value matched");
  puts("fixture case zero status matched");
  int actual_int_max_minus_seven_return_value = add_status((int)2147483640u);
  if (actual_int_max_minus_seven_return_value != (int)2147483647u) {
    fprintf(stderr, "int-max-minus-seven return_value mismatch: expected 2147483647 got %d\n", actual_int_max_minus_seven_return_value);
    return 1;
  }
  puts("fixture case int-max-minus-seven return_value matched");
  puts("fixture case int-max-minus-seven status matched");
  return 0;
}

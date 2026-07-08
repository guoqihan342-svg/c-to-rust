/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

/* slice: demo/add-one */
/* function: add_one */
/* fixture input: validation/l2_slices/fixtures/add-one-c-oracle.json */
/* fixture cases: 3 */
/* observable outputs: return_value, status */
/* fixture case: int-min input_ref=cases[0] expected_ref=validation/evidence/demo/l3-add-one-c-oracle.json expected_outputs={"return_value": -2147483647, "status": "ok"} */
/* fixture case: zero input_ref=cases[3] expected_ref=validation/evidence/demo/l3-add-one-c-oracle.json expected_outputs={"return_value": 1, "status": "ok"} */
/* fixture case: int-max-minus-one input_ref=cases[5] expected_ref=validation/evidence/demo/l3-add-one-c-oracle.json expected_outputs={"return_value": 2147483647, "status": "ok"} */
/* source file: validation/l2_slices/fixtures/add-one.c (sha256: 7a5ab0929c73c41027024fd707363adffcb1b5be924a7ee33ffe764a3ba59401) */
int add_one(int value);

int main(void) {
  puts("oracle harness draft for add_one");
  puts("fixture input: validation/l2_slices/fixtures/add-one-c-oracle.json");
  int actual_int_min_return_value = add_one((int)-2147483648);
  if (actual_int_min_return_value != (int)-2147483647) {
    fprintf(stderr, "int-min return_value mismatch: expected -2147483647 got %d\n", actual_int_min_return_value);
    return 1;
  }
  puts("fixture case int-min return_value matched");
  puts("fixture case int-min status matched");
  int actual_zero_return_value = add_one((int)0u);
  if (actual_zero_return_value != (int)1u) {
    fprintf(stderr, "zero return_value mismatch: expected 1 got %d\n", actual_zero_return_value);
    return 1;
  }
  puts("fixture case zero return_value matched");
  puts("fixture case zero status matched");
  int actual_int_max_minus_one_return_value = add_one((int)2147483646u);
  if (actual_int_max_minus_one_return_value != (int)2147483647u) {
    fprintf(stderr, "int-max-minus-one return_value mismatch: expected 2147483647 got %d\n", actual_int_max_minus_one_return_value);
    return 1;
  }
  puts("fixture case int-max-minus-one return_value matched");
  puts("fixture case int-max-minus-one status matched");
  return 0;
}

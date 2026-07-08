/* Auto-generated C oracle harness draft. */
/* Review and compile against the pinned L1 source tree before using as oracle evidence. */
/* Draft only: fixture values and oracle assertions must be reviewed before acceptance. */
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>

/* slice: demo/while-countdown-positive */
/* function: while_countdown_positive */
/* fixture input: validation/l2_slices/fixtures/while-countdown-positive-c-oracle.json */
/* fixture cases: 5 */
/* observable outputs: return_value, status */
/* fixture case: negative input_ref=cases[0] expected_ref=validation/evidence/demo/l3-while-countdown-positive-c-oracle.json expected_outputs={"return_value": -3, "status": "ok"} */
/* fixture case: zero input_ref=cases[1] expected_ref=validation/evidence/demo/l3-while-countdown-positive-c-oracle.json expected_outputs={"return_value": 0, "status": "ok"} */
/* fixture case: one input_ref=cases[2] expected_ref=validation/evidence/demo/l3-while-countdown-positive-c-oracle.json expected_outputs={"return_value": 0, "status": "ok"} */
/* fixture case: three input_ref=cases[3] expected_ref=validation/evidence/demo/l3-while-countdown-positive-c-oracle.json expected_outputs={"return_value": 0, "status": "ok"} */
/* fixture case: seven input_ref=cases[4] expected_ref=validation/evidence/demo/l3-while-countdown-positive-c-oracle.json expected_outputs={"return_value": 0, "status": "ok"} */
/* source file: validation/l2_slices/fixtures/while-countdown-positive.c (sha256: c271e9b108c1eb537cad18196977dc34b8202de76827a725efb118cccb119ced) */
int while_countdown_positive(int value);

int main(void) {
  puts("oracle harness draft for while_countdown_positive");
  puts("fixture input: validation/l2_slices/fixtures/while-countdown-positive-c-oracle.json");
  int actual_negative_return_value = while_countdown_positive((int)-3);
  if (actual_negative_return_value != (int)-3) {
    fprintf(stderr, "negative return_value mismatch: expected -3 got %d\n", actual_negative_return_value);
    return 1;
  }
  puts("fixture case negative return_value matched");
  puts("fixture case negative status matched");
  int actual_zero_return_value = while_countdown_positive((int)0u);
  if (actual_zero_return_value != (int)0u) {
    fprintf(stderr, "zero return_value mismatch: expected 0 got %d\n", actual_zero_return_value);
    return 1;
  }
  puts("fixture case zero return_value matched");
  puts("fixture case zero status matched");
  int actual_one_return_value = while_countdown_positive((int)1u);
  if (actual_one_return_value != (int)0u) {
    fprintf(stderr, "one return_value mismatch: expected 0 got %d\n", actual_one_return_value);
    return 1;
  }
  puts("fixture case one return_value matched");
  puts("fixture case one status matched");
  int actual_three_return_value = while_countdown_positive((int)3u);
  if (actual_three_return_value != (int)0u) {
    fprintf(stderr, "three return_value mismatch: expected 0 got %d\n", actual_three_return_value);
    return 1;
  }
  puts("fixture case three return_value matched");
  puts("fixture case three status matched");
  int actual_seven_return_value = while_countdown_positive((int)7u);
  if (actual_seven_return_value != (int)0u) {
    fprintf(stderr, "seven return_value mismatch: expected 0 got %d\n", actual_seven_return_value);
    return 1;
  }
  puts("fixture case seven return_value matched");
  puts("fixture case seven status matched");
  return 0;
}

enum status { STATUS_OK = 7, STATUS_PENDING };

static const int table[4] = { [2] = 7 };

int add_one(int value) { return value + 1; }

int while_countdown_positive(int value) {
  while (value > 0) {
    value = value - 1;
  }
  return value;
}

int copy_i32_ptr_arith(const int *values, int len, int *out) {
  for (int i = 0; i < len; i++) {
    *(out + i) = *(values + i);
  }
  return 0;
}

int call_expression_chain(int value) {
  if (value <= 0) {
    return -value;
  }
  int first = call_expression_chain(value - 1);
  value = call_expression_chain(first - 1);
  return call_expression_chain(value - 1);
}

int add_status(int value) { return value + STATUS_OK; }

int sparse_designated_array_lookup(int index) { return table[index]; }

int scalar_div_rem_contract(int value) { return (value / 3) + (value % 5); }

int signed_rshift_contract(int value, int count) { return value >> count; }

int call_fn(int (*fp)(int), int value) { return fp(value); }

int bad_do_while_same_variable_sibling(int value) {
  do {
  } while (value++ == value);
  return value;
}

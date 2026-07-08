int call_expression_chain(int value) {
    if (value <= 0) {
        return -value;
    }
    int first = call_expression_chain(value - 1);
    value = call_expression_chain(first - 1);
    return call_expression_chain(value - 1);
}

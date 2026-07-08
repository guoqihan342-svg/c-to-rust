const STATUS_TABLE: [i32; 2] = [7i32, 0i32];

pub fn add_status(value: i32) -> i32 {
    return value.checked_add(7i32).expect("signed addition overflow");
}

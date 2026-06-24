const BASE: u32 = 65_521;
const NMAX: usize = 5_552;

pub fn adler32(input: &[u8]) -> u32 {
    let mut s1 = 1_u32;
    let mut s2 = 0_u32;

    for chunk in input.chunks(NMAX) {
        for byte in chunk {
            s1 += u32::from(*byte);
            s2 += s1;
        }
        s1 %= BASE;
        s2 %= BASE;
    }

    (s2 << 16) | s1
}

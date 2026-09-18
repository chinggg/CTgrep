#include <stdlib.h>
#include <string.h>
#include <stdint.h>

typedef uint64_t crypto_word_t;

static inline crypto_word_t constant_time_msb_w(crypto_word_t a) {
  return 0u - (a >> (sizeof(a) * 8 - 1));
}

static inline uint8_t constant_time_lt_args_8(uint8_t a, uint8_t b) {
  crypto_word_t aw = a;
  crypto_word_t bw = b;
  // |crypto_word_t| is larger than |uint8_t|, so |aw| and |bw| have the same
  // MSB. |aw| < |bw| iff MSB(|aw| - |bw|) is 1.
  return constant_time_msb_w(aw - bw);
}

static inline uint8_t constant_time_in_range_8(uint8_t a, uint8_t min,
                                               uint8_t max) {
  a -= min;
  return constant_time_lt_args_8(a, max - min + 1);
}

static inline crypto_word_t constant_time_is_zero_w(crypto_word_t a) {
  return constant_time_msb_w(~a & (a - 1));
}

// constant_time_eq_w returns 0xff..f if a == b and 0 otherwise.
static inline crypto_word_t constant_time_eq_w(crypto_word_t a,
                                               crypto_word_t b) {
  return constant_time_is_zero_w(a ^ b);
}

static inline uint8_t constant_time_eq_8(crypto_word_t a, crypto_word_t b) {
  return (uint8_t)(constant_time_eq_w(a, b));
}


uint8_t base64_ascii_to_bin(uint8_t a) {
  // Since PEM is sometimes used to carry private keys, we decode base64 data
  // itself in constant-time.
  const uint8_t is_upper = constant_time_in_range_8(a, 'A', 'Z');
  const uint8_t is_lower = constant_time_in_range_8(a, 'a', 'z');
  const uint8_t is_digit = constant_time_in_range_8(a, '0', '9');
  const uint8_t is_plus = constant_time_eq_8(a, '+');
  const uint8_t is_slash = constant_time_eq_8(a, '/');
  const uint8_t is_equals = constant_time_eq_8(a, '=');

  uint8_t ret = 0;
  ret |= is_upper & (a - 'A');       // [0,26)
  ret |= is_lower & (a - 'a' + 26);  // [26,52)
  ret |= is_digit & (a - '0' + 52);  // [52,62)
  ret |= is_plus & 62;
  ret |= is_slash & 63;
  // Invalid inputs, 'A', and '=' have all been mapped to zero. Map invalid
  // inputs to 0xff. Note '=' is padding and handled separately by the caller.
  const uint8_t is_valid =
      is_upper | is_lower | is_digit | is_plus | is_slash | is_equals;
  ret |= ~is_valid;
  return ret;
}
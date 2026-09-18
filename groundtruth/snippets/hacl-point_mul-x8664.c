#include <stdint.h>
#include <string.h>
#include <stdbool.h>
typedef unsigned __int128 FStar_UInt128_uint128;

/* Macros for prettier unrolling of loops */
#define KRML_LOOP1(i, n, x) { \
  x \
  i += n; \
}

#define KRML_LOOP2(i, n, x) \
  KRML_LOOP1(i, n, x) \
  KRML_LOOP1(i, n, x)

#define KRML_LOOP3(i, n, x) \
  KRML_LOOP2(i, n, x) \
  KRML_LOOP1(i, n, x)

#define KRML_LOOP4(i, n, x) \
  KRML_LOOP2(i, n, x) \
  KRML_LOOP2(i, n, x)

#define KRML_LOOP5(i, n, x) \
  KRML_LOOP4(i, n, x) \
  KRML_LOOP1(i, n, x)

#define KRML_LOOP6(i, n, x) \
  KRML_LOOP4(i, n, x) \
  KRML_LOOP2(i, n, x)

#define KRML_LOOP7(i, n, x) \
  KRML_LOOP4(i, n, x) \
  KRML_LOOP3(i, n, x)

#define KRML_LOOP8(i, n, x) \
  KRML_LOOP4(i, n, x) \
  KRML_LOOP4(i, n, x)

#define KRML_LOOP9(i, n, x) \
  KRML_LOOP8(i, n, x) \
  KRML_LOOP1(i, n, x)

#define KRML_LOOP10(i, n, x) \
  KRML_LOOP8(i, n, x) \
  KRML_LOOP2(i, n, x)

#define KRML_LOOP11(i, n, x) \
  KRML_LOOP8(i, n, x) \
  KRML_LOOP3(i, n, x)

#define KRML_LOOP12(i, n, x) \
  KRML_LOOP8(i, n, x) \
  KRML_LOOP4(i, n, x)

#define KRML_LOOP13(i, n, x) \
  KRML_LOOP8(i, n, x) \
  KRML_LOOP5(i, n, x)

#define KRML_LOOP14(i, n, x) \
  KRML_LOOP8(i, n, x) \
  KRML_LOOP6(i, n, x)

#define KRML_LOOP15(i, n, x) \
  KRML_LOOP8(i, n, x) \
  KRML_LOOP7(i, n, x)

#define KRML_LOOP16(i, n, x) \
  KRML_LOOP8(i, n, x) \
  KRML_LOOP8(i, n, x)

#define KRML_UNROLL_FOR(i, z, n, k, x) do { \
  uint32_t i = z; \
  KRML_LOOP##n(i, k, x) \
} while (0)

#define KRML_MAYBE_FOR4(i, z, n, k, x) KRML_UNROLL_FOR(i, z, 4, k, x)
#define KRML_MAYBE_FOR7(i, z, n, k, x) KRML_UNROLL_FOR(i, z, 7, k, x)
#define KRML_MAYBE_FOR12(i, z, n, k, x) KRML_UNROLL_FOR(i, z, 12, k, x)
#define KRML_MAYBE_FOR15(i, z, n, k, x) KRML_UNROLL_FOR(i, z, 15, k, x)

static inline uint64_t FStar_UInt64_eq_mask(uint64_t a, uint64_t b)
{
  uint64_t x = a ^ b;
  uint64_t minus_x = ~x + (uint64_t)1U;
  uint64_t x_or_minus_x = x | minus_x;
  uint64_t xnx = x_or_minus_x >> (uint32_t)63U;
  return xnx - (uint64_t)1U;
}

extern void make_fzero(uint64_t *n);
extern void make_fone(uint64_t *n);
extern void make_point_at_inf(uint64_t *p);
extern uint64_t Hacl_Bignum_Lib_bn_get_bits_u64(uint32_t len, uint64_t *b, uint32_t i, uint32_t l);
extern void point_double(uint64_t *res, uint64_t *p);
extern void point_add(uint64_t *res, uint64_t *p, uint64_t *q);


// extern void point_mul(uint64_t *res, uint64_t *scalar, uint64_t *p);
void point_mul(uint64_t *res, uint64_t *scalar, uint64_t *p)
{
  uint64_t table[192U] = { 0U };
  uint64_t tmp[12U] = { 0U };
  uint64_t *t0 = table;
  uint64_t *t1 = table + (uint32_t)12U;
  make_point_at_inf(t0);
  memcpy(t1, p, (uint32_t)12U * sizeof (uint64_t));
  KRML_MAYBE_FOR7(i,
    (uint32_t)0U,
    (uint32_t)7U,
    (uint32_t)1U,
    uint64_t *t11 = table + (i + (uint32_t)1U) * (uint32_t)12U;
    point_double(tmp, t11);
    memcpy(table + ((uint32_t)2U * i + (uint32_t)2U) * (uint32_t)12U,
      tmp,
      (uint32_t)12U * sizeof (uint64_t));
    uint64_t *t2 = table + ((uint32_t)2U * i + (uint32_t)2U) * (uint32_t)12U;
    point_add(tmp, p, t2);
    memcpy(table + ((uint32_t)2U * i + (uint32_t)3U) * (uint32_t)12U,
      tmp,
      (uint32_t)12U * sizeof (uint64_t)););
  make_point_at_inf(res);
  uint64_t tmp0[12U] = { 0U };
  for (uint32_t i0 = (uint32_t)0U; i0 < (uint32_t)64U; i0++)
  {
    KRML_MAYBE_FOR4(i, (uint32_t)0U, (uint32_t)4U, (uint32_t)1U, point_double(res, res););
    uint32_t k = (uint32_t)256U - (uint32_t)4U * i0 - (uint32_t)4U;
    uint64_t bits_l = Hacl_Bignum_Lib_bn_get_bits_u64((uint32_t)4U, scalar, k, (uint32_t)4U);
    memcpy(tmp0, (uint64_t *)table, (uint32_t)12U * sizeof (uint64_t));
    KRML_MAYBE_FOR15(i1,
      (uint32_t)0U,
      (uint32_t)15U,
      (uint32_t)1U,
      uint64_t c = FStar_UInt64_eq_mask(bits_l, (uint64_t)(i1 + (uint32_t)1U));
      const uint64_t *res_j = table + (i1 + (uint32_t)1U) * (uint32_t)12U;
      KRML_MAYBE_FOR12(i,
        (uint32_t)0U,
        (uint32_t)12U,
        (uint32_t)1U,
        uint64_t *os = tmp0;
        uint64_t x = (c & res_j[i]) | (~c & tmp0[i]);
        os[i] = x;););
    point_add(res, res, tmp0);
  }
}

extern bool load_point_vartime(uint64_t *p, uint8_t *b);
extern void bn_from_bytes_be4(uint64_t *res, uint8_t *b);
extern uint64_t bn_is_lt_order_and_gt_zero_mask4(uint64_t *f);
extern void point_store(uint8_t *res, uint64_t *p);
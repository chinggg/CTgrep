#include <stdint.h>
#include <stddef.h>
#include <string.h>

static inline uint32_t NOT(uint32_t ctl)
{
	return ctl ^ 1;
}

static inline uint32_t EQ(uint32_t x, uint32_t y)
{
	uint32_t q;

	q = x ^ y;
	return NOT((q | -q) >> 31);
}

static inline uint32_t MUX(uint32_t ctl, uint32_t x, uint32_t y)
{
	return y ^ (-ctl & (x ^ y));
}

static inline uint32_t GT(uint32_t x, uint32_t y)
{
	uint32_t z;

	z = y - x;
	return (z ^ ((x ^ y) & (x ^ z))) >> 31;
}

#define MUL31(x, y)     ((uint64_t)(x) * (uint64_t)(y))

/* see inner.h */
void br_i31_muladd_small(uint32_t *x, uint32_t z, const uint32_t *m, uint32_t q, size_t mlen)
{
	uint32_t cc, tb, over, under;
    size_t u;
    // size_t mlen = 8;

    uint32_t hi = x[mlen];

    /*
	 * We subtract q*m from x (with the extra high word of value 'hi').
	 * Since q may be off by 1 (in either direction), we may have to
	 * add or subtract m afterwards.
	 *
	 * The 'tb' flag will be true (1) at the end of the loop if the
	 * result is greater than or equal to the modulus (not counting
	 * 'hi' or the carry).
	 */
	cc = 0;
	tb = 1;
	for (u = 1; u <= mlen; u ++) {
		uint32_t mw, zw, xw, nxw;
		uint64_t zl;

		mw = m[u];
		zl = MUL31(mw, q) + cc;
		cc = (uint32_t)(zl >> 31);
		zw = (uint32_t)zl & (uint32_t)0x7FFFFFFF;
		xw = x[u];
		nxw = xw - zw;
		cc += nxw >> 31;
		nxw &= 0x7FFFFFFF;
		x[u] = nxw;
		tb = MUX(EQ(nxw, mw), tb, GT(nxw, mw));
	}

    over = GT(cc, hi);
	under = ~over & (tb | LT(cc, hi));
	br_i31_add(x, m, over);
	br_i31_sub(x, m, under);
    return;
}
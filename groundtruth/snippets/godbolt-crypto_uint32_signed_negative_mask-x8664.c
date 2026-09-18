#include <stdint.h>
#include <string.h>
#define SYS_T 128
#define SYS_N 8192


int randombytes(uint8_t *output, size_t n);

static inline unsigned char same_mask(uint16_t x, uint16_t y) {
    uint32_t mask;

    mask = x ^ y;
    mask -= 1;
    mask >>= 31;
    mask = -mask;

    return mask & 0xFF;
}

#define GFBITS 13
#define GFMASK ((1 << GFBITS) - 1)
uint16_t load_gf(const unsigned char *src) {
    uint16_t a;

    a = src[1];
    a <<= 8;
    a |= src[0];

    return a & GFMASK;
}

#define crypto_declassify(x, y)
typedef uint32_t crypto_uint32;
typedef int32_t crypto_uint32_signed;

crypto_uint32_signed crypto_uint32_signed_negative_mask(crypto_uint32_signed crypto_uint32_signed_x) {
    return crypto_uint32_signed_x >> 31;
}

crypto_uint32 crypto_uint32_nonzero_mask(crypto_uint32 crypto_uint32_x) {
    return crypto_uint32_signed_negative_mask(crypto_uint32_x) | crypto_uint32_signed_negative_mask(-crypto_uint32_x);
}

crypto_uint32 crypto_uint32_unequal_mask(crypto_uint32 crypto_uint32_x, crypto_uint32 crypto_uint32_y) {
    crypto_uint32 crypto_uint32_xy = crypto_uint32_x ^ crypto_uint32_y;
    return crypto_uint32_nonzero_mask(crypto_uint32_xy);
}

crypto_uint32 crypto_uint32_equal_mask(crypto_uint32 crypto_uint32_x, crypto_uint32 crypto_uint32_y) {
    return ~crypto_uint32_unequal_mask(crypto_uint32_x, crypto_uint32_y);
}

static inline crypto_uint32 uint32_is_equal_declassify(uint32_t t, uint32_t u) {
    crypto_uint32 mask = crypto_uint32_equal_mask(t, u);
    crypto_declassify(&mask, sizeof mask);
    return mask;
}

void gen_e(unsigned char *e) {
    int i, j, eq;

    uint16_t ind[ SYS_T ];
    unsigned char bytes[ sizeof(ind) ];
    unsigned char mask;
    unsigned char val[ SYS_T ];

    while (1) {
        randombytes(bytes, sizeof(bytes));

        for (i = 0; i < SYS_T; i++) {
            ind[i] = load_gf(bytes + i * 2);
        }

        // check for repetition

        eq = 0;

        for (i = 1; i < SYS_T; i++) {
            for (j = 0; j < i; j++) {
                if (uint32_is_equal_declassify(ind[i], ind[j])) {
                    eq = 1;
                }
            }
        }

        if (eq == 0) {
            break;
        }
    }

    for (j = 0; j < SYS_T; j++) {
        val[j] = 1 << (ind[j] & 7);
    }

    for (i = 0; i < SYS_N / 8; i++) {
        e[i] = 0;

        for (j = 0; j < SYS_T; j++) {
            mask = same_mask((uint16_t)i, ind[j] >> 3);

            e[i] |= val[j] & mask;
        }
    }
}

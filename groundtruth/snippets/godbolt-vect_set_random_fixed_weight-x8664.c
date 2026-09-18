#include <stdint.h>
#include <string.h>
#define PARAM_DELTA 15
#define PARAM_OMEGA_R 75
#define VEC_N_SIZE_64 277

typedef struct {
    uint64_t *ctx;
} shake256incctx;

typedef shake256incctx seedexpander_state;

extern uint16_t PQCLEAN_HQC128_CLEAN_gf_inverse(uint16_t a);
uint16_t PQCLEAN_HQC128_CLEAN_gf_mul(uint16_t a, uint16_t b);
static inline uint32_t reduce(uint32_t a, size_t i);
static inline uint32_t compare_u32(uint32_t v1, uint32_t v2);
static uint64_t single_bit_mask(uint32_t pos);
void PQCLEAN_HQC128_CLEAN_seedexpander(seedexpander_state *state, uint8_t *output, size_t outlen);



void PQCLEAN_HQC128_CLEAN_vect_set_random_fixed_weight(seedexpander_state *ctx, uint64_t *v, uint16_t weight) {
    uint8_t rand_bytes[4 * PARAM_OMEGA_R] = {0}; // to be interpreted as PARAM_OMEGA_R 32-bit unsigned ints
    uint32_t support[PARAM_OMEGA_R] = {0};
    uint32_t index_tab [PARAM_OMEGA_R] = {0};
    uint64_t bit_tab [PARAM_OMEGA_R] = {0};
    uint32_t pos, found, mask32, tmp;
    uint64_t mask64, val;

    PQCLEAN_HQC128_CLEAN_seedexpander(ctx, rand_bytes, 4 * weight);

    for (size_t i = 0; i < weight; ++i) {
        support[i] = rand_bytes[4 * i];
        support[i] |= rand_bytes[4 * i + 1] << 8;
        support[i] |= (uint32_t)rand_bytes[4 * i + 2] << 16;
        support[i] |= (uint32_t)rand_bytes[4 * i + 3] << 24;
        support[i] = (uint32_t)(i + reduce(support[i], i)); // use constant-tme reduction
    }

    for (size_t i = (weight - 1); i-- > 0;) {
        found = 0;

        for (size_t j = i + 1; j < weight; ++j) {
            found |= compare_u32(support[j], support[i]);
        }

        mask32 = 0 - found;
        support[i] = (mask32 & i) ^ (~mask32 & support[i]);
    }

    for (size_t i = 0; i < weight; ++i) {
        index_tab[i] = support[i] >> 6;
        pos = support[i] & 0x3f;
        bit_tab[i] = single_bit_mask(pos); // avoid secret shift
    }

    for (size_t i = 0; i < VEC_N_SIZE_64; ++i) {
        val = 0;
        for (size_t j = 0; j < weight; ++j) {
            tmp = (uint32_t)(i - index_tab[j]);
            tmp = 1 ^ ((uint32_t)(tmp | (0 - tmp)) >> 31);
            mask64 = 0 - (uint64_t)tmp;
            val |= (bit_tab[j] & mask64);
        }
        v[i] |= val;
    }
}

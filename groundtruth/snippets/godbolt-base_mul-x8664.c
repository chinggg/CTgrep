#include <stdint.h>
#include <string.h>
#include <stdlib.h>
#define PARAM_DELTA 15
#define PARAM_OMEGA_R 75
#define VEC_N_SIZE_64 277

void base_mul(uint64_t *c, uint64_t a, uint64_t b) {
    uint64_t h = 0;
    uint64_t l = 0;
    uint64_t g;
    uint64_t u[16] = {0};
    uint64_t mask_tab[4] = {0};
    uint64_t tmp1, tmp2;

    // Step 1
    u[0] = 0;
    u[1] = b & (((uint64_t)1 << (64 - 4)) - 1);
    u[2] = u[1] << 1;
    u[3] = u[2] ^ u[1];
    u[4] = u[2] << 1;
    u[5] = u[4] ^ u[1];
    u[6] = u[3] << 1;
    u[7] = u[6] ^ u[1];
    u[8] = u[4] << 1;
    u[9] = u[8] ^ u[1];
    u[10] = u[5] << 1;
    u[11] = u[10] ^ u[1];
    u[12] = u[6] << 1;
    u[13] = u[12] ^ u[1];
    u[14] = u[7] << 1;
    u[15] = u[14] ^ u[1];

    g = 0;
    tmp1 = a & 0x0f;


    for (size_t i = 0; i < 16; ++i) {
        tmp2 = tmp1 - i;
        g ^= (u[i] & (uint64_t)(0 - (1 - ((uint64_t)(tmp2 | (0 - tmp2)) >> 63))));
    }

    l = g;
    h = 0;

    // Step 2
    for (size_t i = 4; i < 64; i += 4) {
        g = 0;
        tmp1 = (a >> i) & 0x0f;
        
        for (size_t j = 0; j < 16; ++j) {
            tmp2 = tmp1 - j;
            g ^= (u[j] & (uint64_t)(0 - (1 - ((uint64_t)(tmp2 | (0 - tmp2)) >> 63))));  // TIME LEAK
        }

        l ^= g << i;
        h ^= g >> (64 - i);
    }

    // Step 3
    mask_tab [0] = 0 - ((b >> 60) & 1);
    mask_tab [1] = 0 - ((b >> 61) & 1);
    mask_tab [2] = 0 - ((b >> 62) & 1);
    mask_tab [3] = 0 - ((b >> 63) & 1);

    l ^= ((a << 60) & mask_tab[0]);
    h ^= ((a >> 4) & mask_tab[0]);

    l ^= ((a << 61) & mask_tab[1]);
    h ^= ((a >> 3) & mask_tab[1]);

    l ^= ((a << 62) & mask_tab[2]);
    h ^= ((a >> 2) & mask_tab[2]);

    l ^= ((a << 63) & mask_tab[3]);
    h ^= ((a >> 1) & mask_tab[3]);

    c[0] = l;
    c[1] = h;
}

CC ?= clang
CXX ?= clang++
# BASE_CFLAGS = -g -O1 -mllvm -enable-mf-count-instr
CFLAGS += -S -Wno-implicit-function-declaration -Wno-incompatible-pointer-types -fno-verbose-asm
CXXFLAGS = -std=c++20 $(CFLAGS)

# Suppress the per-rule -target if CFLAGS/CXXFLAGS already provide one
maybe_target = $(if $(filter -target,$(CFLAGS) $(CXXFLAGS)),,$(1))

TARGETS = \
	bearssl-br_i31_muladd_small-x86i386 \
	bearssl-check_scalar-riscv64 \
	bearssl-modpow_opt-x8664 \
	bearssl-modpow_opt-x86i386 \
	binsec-ct_select_u32_v1-x8664 \
	binsec-ct_select_u32_v2-x8664 \
	binsec-ct_select_u32_v3-x8664 \
	binsec-ct_select_u32_v4-x8664 \
	binsec-sort2_multiplex-x8664 \
	botan-hex_decode-riscv64 \
	botan-key_schedule-riscv64 \
	godbolt-base_mul-x8664 \
	godbolt-constant_time_msb_w-x8632 \
	godbolt-crypto_uint32_signed_negative_mask-x8664 \
	godbolt-vect_set_random_fixed_weight-x8664 \
	hacl-cmovznz4-riscv64 \
	hacl-point_mul-x8664 \
	wolfssl-Base64_Char2Val-x8664 \
	wolfssl-sp_clamp_ct-x8664

all: $(TARGETS)

bearssl-br_i31_muladd_small-x86i386: bearssl-br_i31_muladd_small-x86i386.c
	$(CC) $(CFLAGS) $(call maybe_target,-target i386-linux-gnu) $< -o $@

bearssl-check_scalar-riscv64: bearssl-check_scalar-riscv64.c
	$(CC) $(CFLAGS) $(call maybe_target,-target riscv64-linux-gnu) $< -o $@

bearssl-modpow_opt-x8664: bearssl-modpow_opt-x8664.c
	$(CC) $(CFLAGS) $(call maybe_target,-target x86_64-linux-gnu) $< -o $@

bearssl-modpow_opt-x86i386: bearssl-modpow_opt-x86i386.c
	$(CC) $(CFLAGS) $(call maybe_target,-target i386-linux-gnu) $< -o $@


binsec-ct_select_u32_v1-x8664: binsec-ct_select_u32_v1-x8664.c
	$(CC) $(CFLAGS) -mllvm --x86-cmov-converter-force-all -target x86_64-linux-gnu $< -o $@

binsec-ct_select_u32_v2-x8664: binsec-ct_select_u32_v2-x8664.c
	$(CC) $(CFLAGS) -mllvm --x86-cmov-converter-force-all -target x86_64-linux-gnu $< -o $@

binsec-ct_select_u32_v3-x8664: binsec-ct_select_u32_v3-x8664.c
	$(CC) $(CFLAGS) -mllvm --x86-cmov-converter-force-all -target x86_64-linux-gnu $< -o $@

binsec-ct_select_u32_v4-x8664: binsec-ct_select_u32_v4-x8664.c
	$(CC) $(CFLAGS) -mllvm --x86-cmov-converter-force-all -target x86_64-linux-gnu $< -o $@


binsec-sort2_multiplex-x8664: binsec-sort2_multiplex-x8664.c
	$(CC) $(CFLAGS) -mllvm --x86-cmov-converter-force-all -target x86_64-linux-gnu $< -o $@






botan-hex_decode-riscv64: botan-hex_decode-riscv64.cpp
	$(CXX) $(CXXFLAGS) $(call maybe_target,-target riscv64-linux-gnu) $< -o $@

botan-key_schedule-riscv64: botan-key_schedule-riscv64.cpp
	$(CXX) $(CXXFLAGS) $(call maybe_target,-target riscv64-linux-gnu) $< -o $@

godbolt-base_mul-x8664: godbolt-base_mul-x8664.c
	$(CC) $(CFLAGS) $(call maybe_target,-target x86_64-linux-gnu) $< -o $@

godbolt-constant_time_msb_w-x8632: godbolt-constant_time_msb_w-x8632.c
	$(CC) $(CFLAGS) $(call maybe_target,-target i386-linux-gnu) $< -o $@

godbolt-crypto_uint32_signed_negative_mask-x8664: godbolt-crypto_uint32_signed_negative_mask-x8664.c
	$(CC) $(CFLAGS) $(call maybe_target,-target x86_64-linux-gnu) $< -o $@

godbolt-vect_set_random_fixed_weight-x8664: godbolt-vect_set_random_fixed_weight-x8664.c
	$(CC) $(CFLAGS) $(call maybe_target,-target x86_64-linux-gnu) $< -o $@

hacl-cmovznz4-riscv64: hacl-cmovznz4-riscv64.c
	$(CC) $(CFLAGS) $(call maybe_target,-target riscv64-linux-gnu) $< -o $@

hacl-point_mul-x8664: hacl-point_mul-x8664.c
	$(CC) $(CFLAGS) $(call maybe_target,-target x86_64-linux-gnu) $< -o $@

wolfssl-Base64_Char2Val-x8664: wolfssl-Base64_Char2Val-x8664.c
	$(CC) $(CFLAGS) $(call maybe_target,-target x86_64-linux-gnu) $< -o $@

wolfssl-sp_clamp_ct-x8664: wolfssl-sp_clamp_ct-x8664.c
	$(CC) $(CFLAGS) $(call maybe_target,-target x86_64-linux-gnu) $< -o $@

clean:
	rm -f $(TARGETS)

.PHONY: all clean


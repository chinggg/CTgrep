# CTgrep artifact image.
#
# Stage 1 builds the patched Clang/LLVM (one major version per image, chosen
# with --build-arg LLVM_VERSION=14|18|20). Stage 2 is the runtime image with
# the cross toolchains, Python, the artifact sources and the compiled
# instrumentation plugins.
#
#   docker build --build-arg LLVM_VERSION=18 -t ctgrep:clang18 .
#   docker run --rm -it -v "$PWD/results:/ctgrep/results" ctgrep:clang18
#
# Stage 1 is the expensive part (see AE.md for time and disk figures).

ARG LLVM_VERSION=18

# --------------------------------------------------------------------------
# Stage 1: patched LLVM
# --------------------------------------------------------------------------
FROM ubuntu:22.04 AS llvm-builder
ARG LLVM_VERSION=18
ARG LLVM_REPO=https://github.com/llvm/llvm-project.git
ARG LLVM_BRANCH=release/${LLVM_VERSION}.x
ARG LLVM_BUILD_JOBS=""
ARG LLVM_LINK_JOBS=2

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git cmake ninja-build build-essential python3 \
    && rm -rf /var/lib/apt/lists/*

COPY patches/ /tmp/patches/
RUN git clone --depth 1 --branch ${LLVM_BRANCH} ${LLVM_REPO} /llvm-project \
    && cd /llvm-project \
    && if [ -f llvm/lib/CodeGen/MachineFunctionCountInstr.cpp ]; then \
           echo "Using pre-patched LLVM repository"; \
       elif [ -f /tmp/patches/ct-backend-${LLVM_VERSION}.patch ]; then \
           git apply /tmp/patches/ct-backend-${LLVM_VERSION}.patch; \
       else \
           echo "ERROR: No patch found at patches/ct-backend-${LLVM_VERSION}.patch and repository is not pre-patched" >&2 && exit 1; \
       fi

# The patch adds `-mllvm --enable-mf-count-instr` (MachineFunctionCountInstr)
# and `-mllvm --mfpass-dump`; everything else is upstream LLVM. Only the five
# back-ends used in the paper are built. LLVM is linked as a shared library
# so that the pass plugins in llvm_tool/ resolve their symbols at load time.
RUN cmake -G Ninja -S /llvm-project/llvm -B /llvm-build \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_INSTALL_PREFIX=/opt/llvm \
        -DLLVM_ENABLE_PROJECTS=clang \
        -DLLVM_TARGETS_TO_BUILD="X86;AArch64;ARM;Mips;RISCV" \
        -DLLVM_BUILD_LLVM_DYLIB=ON -DLLVM_LINK_LLVM_DYLIB=ON \
        -DCLANG_LINK_CLANG_DYLIB=ON \
        -DLLVM_ENABLE_DUMP=ON \
        -DLLVM_ENABLE_ASSERTIONS=OFF \
        -DLLVM_INCLUDE_TESTS=OFF -DLLVM_INCLUDE_BENCHMARKS=OFF \
        -DLLVM_INCLUDE_EXAMPLES=OFF -DLLVM_INCLUDE_DOCS=OFF \
        -DCLANG_INCLUDE_TESTS=OFF -DCLANG_ENABLE_ARCMT=OFF \
        -DCLANG_ENABLE_STATIC_ANALYZER=OFF \
        -DLLVM_ENABLE_ZLIB=OFF -DLLVM_ENABLE_ZSTD=OFF \
        -DLLVM_ENABLE_LIBXML2=OFF -DLLVM_ENABLE_TERMINFO=OFF \
        -DLLVM_ENABLE_LIBEDIT=OFF \
        -DLLVM_PARALLEL_LINK_JOBS=${LLVM_LINK_JOBS} \
    && ninja -C /llvm-build ${LLVM_BUILD_JOBS:+-j${LLVM_BUILD_JOBS}} install \
    && rm -rf /llvm-build /llvm-project

# --------------------------------------------------------------------------
# Stage 2: runtime
# --------------------------------------------------------------------------
FROM ubuntu:22.04
ARG LLVM_VERSION
ENV DEBIAN_FRONTEND=noninteractive

# Build tools, cross toolchains for the target platforms (headers, libc and
# linkers; the compiler itself is always our patched clang), Python.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git wget curl make cmake ninja-build libtool \
        libarchive-tools rsync jq python3 python3-pip \
        build-essential \
        crossbuild-essential-i386 \
        crossbuild-essential-armhf crossbuild-essential-riscv64 \
        crossbuild-essential-mips crossbuild-essential-mipsel \
        crossbuild-essential-mips64 \
        python3-jsonschema python3-jinja2 \
    && case "$(dpkg --print-architecture)" in \
         amd64) apt-get install -y --no-install-recommends crossbuild-essential-arm64 ;; \
         arm64) apt-get install -y --no-install-recommends crossbuild-essential-amd64 ;; \
         *)     apt-get install -y --no-install-recommends crossbuild-essential-amd64 crossbuild-essential-arm64 ;; \
       esac \
    && rm -rf /var/lib/apt/lists/*

# Libgcrypt needs libgpg-error; the Ubuntu package is too old.
RUN mkdir -p /root/.local && cd /root/.local && \
    wget -q https://gnupg.org/ftp/gcrypt/libgpg-error/libgpg-error-1.55.tar.gz && \
    tar -xzf libgpg-error-1.55.tar.gz && cd libgpg-error-1.55 && \
    ./configure --prefix=/root/.local >/dev/null && make -j"$(nproc)" install >/dev/null && \
    cd .. && rm -rf libgpg-error-1.55 libgpg-error-1.55.tar.gz

COPY --from=llvm-builder /opt/llvm /opt/llvm
ENV PATH=/opt/llvm/bin:/root/.local/bin:$PATH \
    CC=/opt/llvm/bin/clang \
    CXX=/opt/llvm/bin/clang++ \
    LLVM_CONFIG=/opt/llvm/bin/llvm-config \
    CTGREP_LLVM_VERSION=${LLVM_VERSION}

WORKDIR /ctgrep
COPY . /ctgrep
RUN pip3 install --no-cache-dir -r reproduce/requirements.txt \
    && make plugins \
    && clang --version

CMD ["/bin/bash"]

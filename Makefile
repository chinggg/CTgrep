# Entry points for the CTgrep artifact. See AE.md for what each target
# checks and how long it takes; README.md for how the pieces fit together.

LLVM_VERSION ?= 18
LLVM_REPO    ?= https://github.com/llvm/llvm-project.git
LLVM_BRANCH  ?= release/$(LLVM_VERSION).x
IMAGE        ?= ctgrep:clang$(LLVM_VERSION)
GHCR_IMAGE   ?= ghcr.io/chinggg/ctgrep:clang$(LLVM_VERSION)

.PHONY: help image pull-image plugins kick-tires bearssl-levels bearssl-flags reproduce phase1 phase2 shell rootcause clean

help:
	@echo "make pull-image      pull the published GHCR image (LLVM_VERSION=14|18|20)"
	@echo "make image           build the Docker image with patched LLVM $(LLVM_VERSION) (LLVM_VERSION=14|18|20)"
	@echo "make plugins         compile llvm_tool/*.so against the clang on PATH"
	@echo "make kick-tires      the 19 test cases of the appendix 'Ground Truth Validation Test Cases'"
	@echo "make bearssl-levels  BearSSL, optimization levels only, all paper platforms"
	@echo "make bearssl-flags   BearSSL, paper's problematic flags for this Clang version"
	@echo "make reproduce       regenerate paper figures/tables from recorded data"
	@echo "make phase1          full candidate sweep on BearSSL, MbedTLS and PQClean"
	@echo "make phase2          supplied problematic flags on the other four libraries"
	@echo "make shell           enter the image; persist results and work directories"
	@echo "make rootcause       attribute the kick-tires violations to compiler passes"

shell:
	mkdir -p results work
	docker run --rm -it -v "$(CURDIR)/results:/ctgrep/results" -v "$(CURDIR)/work:/ctgrep/work" $(IMAGE)

rootcause: plugins
	bash experiments/rootcause.sh

phase1 phase2: plugins
	bash experiments/paper_campaign.sh $@

pull-image:
	docker pull "$(GHCR_IMAGE)"
	docker tag "$(GHCR_IMAGE)" "$(IMAGE)"

image:
	docker build --build-arg LLVM_VERSION=$(LLVM_VERSION) --build-arg LLVM_REPO=$(LLVM_REPO) --build-arg LLVM_BRANCH=$(LLVM_BRANCH) -t $(IMAGE) .

plugins: llvm_tool/IRCountInstr.so llvm_tool/PassViolateCT.so

llvm_tool/IRCountInstr.so llvm_tool/PassViolateCT.so: llvm_tool/IRCountInstr.cpp llvm_tool/PassViolateCT.cpp
	bash llvm_tool/build.sh

kick-tires: plugins
	bash experiments/kick_tires.sh

bearssl-levels: plugins
	bash experiments/bearssl_levels.sh

bearssl-flags: plugins
	bash experiments/bearssl_flags.sh

reproduce:
	cd reproduce && python3 reproduce.py

clean:
	rm -rf work badsnippets llvm_tool/*.so

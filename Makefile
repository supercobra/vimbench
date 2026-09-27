# vimbench developer and benchmark shortcuts.
# Override any variable at invocation time, for example:
#   make llm-single PROVIDER=openai MODEL=gpt-5 MAX_TASKS=30
#   make site-open PORT=9000

.DEFAULT_GOAL := help

PYTHON ?= python3
VIM ?= $(if $(VIMBENCH_VIM),$(VIMBENCH_VIM),vi)
HOST ?= 127.0.0.1
PORT ?= 8000
PAGES_URL ?= https://supercobra.github.io/vimbench/
REPO ?= supercobra/vimbench

TASK_SET ?= seed
SYNTH_TASKS ?= tasks_synth.json
SYNTH_OUT ?= /tmp/vimbench_tasks_synth.json
COUNT ?= 4
SEED ?= 42
MAX_TASKS ?= 10
MAX_TURNS ?= 8
TIMEOUT ?= 120
TRACK ?= single

PROVIDER ?= mock
MODEL ?=
BASE_URL ?=
INPUT_PRICE ?=
OUTPUT_PRICE ?=
LLM_OUT ?= llm_results.json
LEADERBOARD_OUT ?= leaderboard.json
MODELS_FILE ?=
SOLUTIONS ?=
RESULTS_OUT ?= results.json
SOURCE_RESULTS ?= openai_leaderboard.json

MODEL_FLAG = $(if $(strip $(MODEL)),--model "$(MODEL)")
BASE_URL_FLAG = $(if $(strip $(BASE_URL)),--base-url "$(BASE_URL)")
INPUT_PRICE_FLAG = $(if $(strip $(INPUT_PRICE)),--input-price "$(INPUT_PRICE)")
OUTPUT_PRICE_FLAG = $(if $(strip $(OUTPUT_PRICE)),--output-price "$(OUTPUT_PRICE)")
SYNTH_TASKS_FLAG = $(if $(strip $(SYNTH_TASKS)),--synth-tasks "$(SYNTH_TASKS)")

.PHONY: help prerequisites all check compile test verify demo synth demo-synth \
	multiturn score llm llm-single llm-multi leaderboard leaderboard-mock \
	site-data site-check site-serve site-open site-view pages pages-open \
	pages-check pages-status pages-deploy pages-watch actions

help: ## Show available targets and common overrides.
	@printf 'vimbench\n\nUsage: make <target> [VARIABLE=value ...]\n\nTargets:\n'
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_.-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
	@printf '\nCommon variables:\n'
	@printf '  TASK_SET=%s  MAX_TASKS=%s  PROVIDER=%s  MODEL=<id>\n' "$(TASK_SET)" "$(MAX_TASKS)" "$(PROVIDER)"
	@printf '  PORT=%s  PAGES_URL=%s\n' "$(PORT)" "$(PAGES_URL)"

prerequisites: ## Confirm Python and Vim are available.
	@command -v "$(PYTHON)" >/dev/null || { echo "missing Python: $(PYTHON)"; exit 1; }
	@command -v "$(VIM)" >/dev/null || { echo "missing Vim: $(VIM)"; exit 1; }
	@"$(PYTHON)" --version
	@"$(VIM)" --version | head -n 1

all: check ## Run the standard local validation suite.

check: compile test verify site-check ## Compile, test, verify tasks, and validate the site.

compile: ## Compile all Python source and test files.
	@files="$$(find . -maxdepth 2 -name '*.py' -not -path './.git/*')"; \
		"$(PYTHON)" -m py_compile $$files

test: ## Run the complete unittest regression suite.
	"$(PYTHON)" -m unittest discover -s tests -v

verify: ## Replay all seed reference solutions through real Vim.
	VIMBENCH_VIM="$(VIM)" "$(PYTHON)" run.py --verify

demo: ## Run the built-in synthetic-model demo (TASK_SET=seed|synth|all).
	VIMBENCH_VIM="$(VIM)" "$(PYTHON)" run.py --demo \
		--task-set "$(TASK_SET)" $(SYNTH_TASKS_FLAG)

synth: ## Generate verified tasks safely outside the tracked task file.
	VIMBENCH_VIM="$(VIM)" "$(PYTHON)" synthesize.py \
		--count "$(COUNT)" --seed "$(SEED)" --out "$(SYNTH_OUT)"
	@echo "generated $(SYNTH_OUT)"

demo-synth: synth ## Generate fresh tasks, then run the demo against them.
	VIMBENCH_VIM="$(VIM)" "$(PYTHON)" run.py --demo --task-set synth \
		--synth-tasks "$(SYNTH_OUT)" --out /tmp/vimbench_demo_results.json

multiturn: ## Run the built-in multi-turn agent demonstrations.
	VIMBENCH_VIM="$(VIM)" "$(PYTHON)" multiturn.py

score: ## Score SOLUTIONS=<file.json> and write RESULTS_OUT=<file.json>.
	@test -n "$(SOLUTIONS)" || { echo "usage: make score SOLUTIONS=solutions.json"; exit 2; }
	VIMBENCH_VIM="$(VIM)" "$(PYTHON)" run.py --solutions "$(SOLUTIONS)" \
		--task-set "$(TASK_SET)" $(SYNTH_TASKS_FLAG) --out "$(RESULTS_OUT)"

llm: ## Run an LLM with configurable TRACK, PROVIDER, MODEL, and pricing.
	VIMBENCH_VIM="$(VIM)" "$(PYTHON)" llm_runner.py \
		--provider "$(PROVIDER)" --track "$(TRACK)" --task-set "$(TASK_SET)" \
		--max-tasks "$(MAX_TASKS)" --max-turns "$(MAX_TURNS)" \
		--timeout "$(TIMEOUT)" --out "$(LLM_OUT)" $(SYNTH_TASKS_FLAG) \
		$(MODEL_FLAG) $(BASE_URL_FLAG) $(INPUT_PRICE_FLAG) $(OUTPUT_PRICE_FLAG)

llm-single: ## Run the single-turn LLM track.
	@$(MAKE) llm TRACK=single

llm-multi: ## Run the multi-turn LLM track.
	@$(MAKE) llm TRACK=multi

leaderboard: ## Run MODELS_FILE=<models.json> on the selected track and tasks.
	@test -n "$(MODELS_FILE)" || { echo "usage: make leaderboard MODELS_FILE=models.json"; exit 2; }
	VIMBENCH_VIM="$(VIM)" "$(PYTHON)" leaderboard.py \
		--models-file "$(MODELS_FILE)" --track "$(TRACK)" \
		--task-set "$(TASK_SET)" --max-tasks "$(MAX_TASKS)" \
		--max-turns "$(MAX_TURNS)" --timeout "$(TIMEOUT)" \
		--out "$(LEADERBOARD_OUT)" $(SYNTH_TASKS_FLAG)

leaderboard-mock: ## Smoke-test leaderboard and telemetry without API keys.
	VIMBENCH_VIM="$(VIM)" "$(PYTHON)" leaderboard.py \
		--model 'reference,mock:,reference' --track "$(TRACK)" \
		--task-set "$(TASK_SET)" --max-tasks "$(MAX_TASKS)" \
		--max-turns "$(MAX_TURNS)" --out /tmp/vimbench_leaderboard.json \
		$(SYNTH_TASKS_FLAG)

site-data: ## Rebuild public site data from SOURCE_RESULTS=<leaderboard.json>.
	@test -f "$(SOURCE_RESULTS)" || { echo "missing source results: $(SOURCE_RESULTS)"; exit 2; }
	"$(PYTHON)" site/build_data.py "$(SOURCE_RESULTS)" site/data/leaderboard.json
	"$(PYTHON)" -m json.tool site/data/leaderboard.json >/dev/null
	@echo "updated site/data/leaderboard.json"

site-check: ## Validate static Pages files and leaderboard JSON.
	"$(PYTHON)" -m py_compile site/build_data.py
	"$(PYTHON)" -m json.tool site/data/leaderboard.json >/dev/null
	@"$(PYTHON)" -c 'from html.parser import HTMLParser; from pathlib import Path; [HTMLParser().feed(p.read_text()) for p in Path("site").glob("*.html")]; print("site HTML and JSON valid")'

site-serve: site-check ## Serve the local Pages site (HOST=127.0.0.1 PORT=8000).
	@echo "serving http://$(HOST):$(PORT)/ — press Ctrl-C to stop"
	"$(PYTHON)" -m http.server "$(PORT)" --bind "$(HOST)" --directory site

site-open: ## Open the local site in a browser and keep serving it.
	@("$(PYTHON)" -c 'import time, webbrowser; time.sleep(1); webbrowser.open("http://$(HOST):$(PORT)/")' >/dev/null 2>&1 &)
	@$(MAKE) site-serve HOST="$(HOST)" PORT="$(PORT)"

site-view: site-open ## Alias for site-open.

pages: pages-check pages-open ## Verify and open the deployed GitHub Pages site.

pages-open: ## Open the deployed GitHub Pages site in the default browser.
	@"$(PYTHON)" -m webbrowser "$(PAGES_URL)"
	@echo "opened $(PAGES_URL)"

pages-check: ## Verify the live Pages homepage and leaderboard data.
	@PAGES_URL="$(PAGES_URL)" "$(PYTHON)" -c 'import json, os, urllib.request; base=os.environ["PAGES_URL"].rstrip("/") + "/"; html=urllib.request.urlopen(base, timeout=20).read().decode(); assert "vimbench" in html and "leaderboard" in html.lower(); data=json.load(urllib.request.urlopen(base + "data/leaderboard.json", timeout=20)); assert data.get("rows"); print("live Pages OK: {} ({} models)".format(base, len(data["rows"])))'

pages-status: ## Show GitHub's Pages configuration and recent deploy runs (requires gh).
	@command -v gh >/dev/null || { echo "missing GitHub CLI: gh"; exit 1; }
	@gh api "repos/$(REPO)/pages" --jq '{url: .html_url, build_type, https_enforced, public}'
	@gh run list --repo "$(REPO)" --workflow pages.yml --limit 5

pages-deploy: ## Trigger the Pages workflow on master (requires gh authentication).
	@command -v gh >/dev/null || { echo "missing GitHub CLI: gh"; exit 1; }
	gh workflow run pages.yml --repo "$(REPO)" --ref master
	@echo "triggered Pages deploy; run 'make pages-watch' to follow it"

pages-watch: ## Watch the most recent Pages workflow run (requires gh).
	@command -v gh >/dev/null || { echo "missing GitHub CLI: gh"; exit 1; }
	@run_id="$$(gh run list --repo "$(REPO)" --workflow pages.yml --limit 1 --json databaseId --jq '.[0].databaseId')"; \
		test -n "$$run_id" || { echo "no Pages workflow run found"; exit 1; }; \
		gh run watch "$$run_id" --repo "$(REPO)" --exit-status

actions: ## List recent GitHub Actions runs (requires gh).
	@command -v gh >/dev/null || { echo "missing GitHub CLI: gh"; exit 1; }
	@gh run list --repo "$(REPO)" --limit 10

.PHONY: \
	help \
	clean \
	lint \
	format \
	test \
	resolve-line-endings \

#################################################################################
# GLOBALS                                                                       #
#################################################################################

PROJECT_DIR := $(shell dirname $(realpath $(lastword $(MAKEFILE_LIST))))
PROJECT_NAME := ACubed
PYTHON_INTERPRETER := python3

#################################################################################
# COMMANDS                                                                      #
#################################################################################

clean-pycache:
	find . -type d -name "__pycache__" -exec rm -rf {} +

clean-pyc:
	find . -type f -name "*.pyc" -delete

clean-pytest:
	find . -type d -name "*.pytest_cache" -exec rm -rf {} +

clean-ruff:
	find . -type d -name "*.ruff_cache" -exec rm -rf {} +

## Clean generated artifacts
clean: \
	clean-pycache \
	clean-pyc \
	clean-pytest \
	clean-ruff \

remove-venv:
	find . -type d -name "*.venv" -exec rm -rf {} +

remove-cache:
	find . \
		-type d \
		-name "*cache" \
		-not -path "./acubed/cache" \
		-exec rm -rf {} +

remove-data:
	find . \
		-type d \
		-name "*data" \
		-not -path "./acubed/data" \
		-exec rm -rf {} +

remove-models:
	find . \
		-type d \
		-name "*models" \
		-not -path "./acubed/models" \
		-exec rm -rf {} +

## Factory reset project to clean state
factory-reset: \
	clean \
	remove-venv \
	remove-cache \
	remove-data \
	remove-models

## Format code
format:
	uv run ruff format .

## Run lint checks
lint:
	uv run ruff check .

## Auto-fix lint issues
force-lint:
	uv run ruff check . --fix

## Normalize line endings
resolve-line-endings:
	uv run python scripts/resolve_line_endings.py

## Run tests
test:
	uv run pytest

#################################################################################
# PROJECT RULES                                                                 #
#################################################################################

.DEFAULT_GOAL := help

#################################################################################
# SELF-DOCUMENTING HELP                                                         #
#################################################################################

# Inspired by:
# http://marmelab.com/blog/2016/02/29/auto-documented-makefile.html

.PHONY: help

help:
	@echo "$$(tput bold)Available rules:$$(tput sgr0)"
	@echo
	@sed -n -e "/^## / { \
		h; \
		s/.*//; \
		:doc" \
		-e "H; \
		n; \
		s/^## //; \
		t doc" \
		-e "s/:.*//; \
		G; \
		s/\\n## /---/; \
		s/\\n/ /g; \
		p; \
	}" ${MAKEFILE_LIST} \
	| LC_ALL='C' sort --ignore-case \
	| awk -F '---' \
		-v ncol=$$(tput cols) \
		-v indent=30 \
		-v col_on="$$(tput setaf 6)" \
		-v col_off="$$(tput sgr0)" \
	'{ \
		printf "%s%*s%s ", col_on, -indent, $$1, col_off; \
		n = split($$2, words, " "); \
		line_length = ncol - indent; \
		for (i = 1; i <= n; i++) { \
			line_length -= length(words[i]) + 1; \
			if (line_length <= 0) { \
				line_length = ncol - indent - length(words[i]) - 1; \
				printf "\n%*s ", -indent, " "; \
			} \
			printf "%s ", words[i]; \
		} \
		printf "\n"; \
	}' \
	| more $(shell test $(shell uname) = Darwin && echo '--no-init --raw-control-chars')


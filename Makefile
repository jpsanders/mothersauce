SRC := src
TESTS := tests
SCRIPTS := scripts
ROOT_EC_FILES := $(wildcard *.yaml *.yml *.md *.toml *.json) .github docs
PACKAGE := mothersauce
DOCKER_IMAGE := mothersauce:latest

.PHONY: help
help:
	@echo "Available targets:"
	@grep -E "^([a-zA-Z_-]+):.*" $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":"}; {printf "    \033[36m%s\n\033[0m", $$1}'
	@echo ""
	@echo "Hints:"
	@echo "    Use '-n' to do a dry run"
	@echo "    Use '-k' to ignore failed targets and keep going"

.PHONY: init
init:
	@echo
	pip install -e .

.PHONY: init-dev
init-dev:
	@echo
	pip install -e .[dev]

.PHONY: format
format: black isort

.PHONY: isort-check
isort-check:
	@echo
	@echo --- Isort check ---
	isort --check --diff ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: isort
isort:
	@echo
	@echo --- Isort auto format ---
	isort ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: black-check
black-check:
	@echo
	@echo --- Black check ---
	black --check --diff ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: black
black:
	@echo
	@echo --- Black auto format ---
	black ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: ec
ec:
	@echo
	@echo --- Editorconfig linting checks ---
	ec ${SRC} ${TESTS} ${SCRIPTS} ${ROOT_EC_FILES}

.PHONY: docstyle
docstyle:
	@echo
	@echo --- Darglint docstring checks ---
	darglint -v 2 ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: lint
lint:
	@echo
	@echo --- Flake8 linting checks ---
	flake8 ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: mypy
mypy:
	@echo
	@echo --- Mypy type checks ---
	mypy ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: pytest
pytest:
	@echo
	@echo --- Pytest regression and unit tests ---
	pytest --cov ${SRC}/${PACKAGE} ${SRC} ${TESTS}

.PHONY: bandit
bandit:
	@echo
	@echo --- Bandit security checks ---
	bandit -c pyproject.toml -f custom -r ${SRC} ${TESTS} ${SCRIPTS}

.PHONY: docs-check
docs-check:
	@echo
	@echo --- Recipe menu, skill copy and llms.txt up to date ---
	python scripts/build_docs.py --check

# Build docs/RECIPES.md, the manual's recipe list, the skill copy and llms.txt from data/recipes.toml
.PHONY: docs
docs:
	@echo
	@echo --- Build the recipe docs ---
	python scripts/build_docs.py

.PHONY: man-check
man-check:
	@echo
	@echo --- Man page and packaged manual up to date ---
	python scripts/build_man.py --check

# Build the man page and the packaged manual from docs/MANUAL.md
.PHONY: man
man: docs
	@echo
	@echo --- Build the man page ---
	python scripts/build_man.py

# How fast the command starts: lazy imports keep it light
.PHONY: bench
bench:
	@echo
	@echo --- Start up time, best of 20 runs ---
	python scripts/bench_startup.py

# Run every recipe's demo, the way a reader would taste them
.PHONY: demo
demo:
	@echo
	@for r in $$(mothersauce list --kind code --ids); do echo "=== $$r"; mothersauce run $$r || exit 1; done

.PHONY: build
build: clean
	@echo
	@echo --- Build package wheel ---
	python -m build -o build/dist

.PHONY: build-docker
build-docker:
	@echo
	@echo --- Docker build image ---
	docker build -t ${DOCKER_IMAGE} --no-cache --build-arg VERSION=$$(python -m setuptools_scm) .

.PHONY: clean
clean:
	@echo
	rm -rf build/
	find ${SRC} ${TESTS} | grep -E "(\.egg-info|__pycache__|\.pyc|\.pyo$$)" | xargs rm -rf

# Run all checking tools
.PHONY: checks
checks: ec black-check isort-check bandit lint docstyle mypy docs-check man-check pytest

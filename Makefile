# MicroClaw Streams - Build & Publish
#
# Prerequisites:
#   pip install build twine
#
# Publishing workflow:
#   1. Create an account at https://pypi.org
#   2. Generate an API token in your account settings
#   3. Run `make publish` (or `make test-publish` to test first)
#   4. Twine will prompt for your API token
#
# After publishing, anyone can install with:
#   pip install microclaw-streams

.PHONY: install dev clean build test-publish publish run help bump-patch bump-minor bump-major release

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

install: ## Install the package locally
	pip install -e .

dev: ## Install with build and publish tools
	pip install -e .
	pip install build twine

clean: ## Remove build artifacts
	rm -rf dist/ build/ *.egg-info microclaw_streams.egg-info/

build: clean ## Build the package
	python -m build

test-publish: build ## Upload to TestPyPI (test run)
	twine upload --repository testpypi dist/*

publish: build ## Upload to PyPI (for real)
	twine upload dist/*

run: ## Run microclaw-streams
	microclaw-streams

version: ## Show current version
	@python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"

bump-patch: ## Bump patch version (0.1.0 -> 0.1.1) and create git tag
	@python3 -c "\
	import re, tomllib; \
	v = tomllib.load(open('pyproject.toml','rb'))['project']['version']; \
	parts = v.split('.'); \
	parts[2] = str(int(parts[2]) + 1); \
	nv = '.'.join(parts); \
	content = open('pyproject.toml').read(); \
	open('pyproject.toml','w').write(content.replace(f'version = \"{v}\"', f'version = \"{nv}\"')); \
	print(f'{v} -> {nv}')"
	@git add pyproject.toml
	@git commit -m "Bump version to $$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
	@git tag v$$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
	@echo "Tagged v$$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"

bump-minor: ## Bump minor version (0.1.0 -> 0.2.0) and create git tag
	@python3 -c "\
	import re, tomllib; \
	v = tomllib.load(open('pyproject.toml','rb'))['project']['version']; \
	parts = v.split('.'); \
	parts[1] = str(int(parts[1]) + 1); \
	parts[2] = '0'; \
	nv = '.'.join(parts); \
	content = open('pyproject.toml').read(); \
	open('pyproject.toml','w').write(content.replace(f'version = \"{v}\"', f'version = \"{nv}\"')); \
	print(f'{v} -> {nv}')"
	@git add pyproject.toml
	@git commit -m "Bump version to $$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
	@git tag v$$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
	@echo "Tagged v$$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"

bump-major: ## Bump major version (0.1.0 -> 1.0.0) and create git tag
	@python3 -c "\
	import re, tomllib; \
	v = tomllib.load(open('pyproject.toml','rb'))['project']['version']; \
	parts = v.split('.'); \
	parts[0] = str(int(parts[0]) + 1); \
	parts[1] = '0'; \
	parts[2] = '0'; \
	nv = '.'.join(parts); \
	content = open('pyproject.toml').read(); \
	open('pyproject.toml','w').write(content.replace(f'version = \"{v}\"', f'version = \"{nv}\"')); \
	print(f'{v} -> {nv}')"
	@git add pyproject.toml
	@git commit -m "Bump version to $$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"
	@git tag v$$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
	@echo "Tagged v$$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")"

release: bump-patch publish ## Bump patch version, tag, and publish to PyPI

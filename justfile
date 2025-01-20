alias b := build
alias t := test
pre-push: lint test
  @echo "All checks passed"
build:
  uv build --package zero-3rdparty
  uv build --package model-lib
fix:
  uv run ruff check --fix .
fmt:
  uv run ruff format .
lint:
  uv run ruff check .
type:
  uv run pyright
test version='3.10':
  uv run --python {{version}} pytest
test-all:
  just test 3.10
  just test 3.11
  just test 3.12
  just test 3.13
cov:
  export RUN_SLOW=false && uv run pytest --cov --cov-report=html
cov-full format='html':
  export RUN_SLOW=true && uv run pytest --cov --cov-report={{format}}
open-cov: cov
  open htmlcov/index.html
open-cov-full: cov-full
  open htmlcov/index.html
pre-release: build
  uv venv -p python3.10 .venv-ci
  echo "dist/model_lib-1.0.0+rc1-py3-none-any.whl[toml]" > .venv-ci/requirements.txt
  uv pip sync --python .venv-ci/bin/python .venv-ci/requirements.txt
  uv pip install --python .venv-ci/bin/python -r .venv-ci/requirements.txt
  .venv-ci/bin/python scripts/model_lib_pre_release.py
docs command='serve':
  uv run scripts/pre_docs.py
  mkdocs {{command}}

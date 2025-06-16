alias b := build
alias t := test
mversion := "1.0.0b4"
zversion := "1.0.0b2"
quick: fmt fix lint
  @echo "Quick checks passed"
pre-push: lint fmt-check test
  @echo "All checks passed"
build-only pkg_name:
  uv build --package {{pkg_name}}
build:
  uv build --package zero-3rdparty
  uv build --package model-lib
fix:
  uv run ruff check --fix .
fmt-check:
  uv run ruff format --check .
fmt:
  uv run ruff format .
lint:
  uv run ruff check .
type:
  uv run pyright
test version='3.11' test-path='':
  uv run --python {{version}} pytest {{test-path}}
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
pre-release mversion=mversion zversion=zversion: build
  uv venv -p python3.11 .venv-ci
  echo "dist/model_lib-{{mversion}}-py3-none-any.whl[toml]\ndist/zero_3rdparty-{{zversion}}-py3-none-any.whl" > .venv-ci/requirements.txt
  uv pip sync --python .venv-ci/bin/python .venv-ci/requirements.txt
  uv pip install --python .venv-ci/bin/python -r .venv-ci/requirements.txt
  .venv-ci/bin/python scripts/model_lib_pre_release.py
docs command='serve':
  uv run scripts/pre_docs.py
  uv run mkdocs {{command}}
pkg-version pkg_name command='read': # use m for model-lib and z for zero-3rdparty, bump-{patch,minor,major,alpha,beta,rc} or tag to read the git tag
  @uv run scripts/pkg_version.py {{pkg_name}} {{command}}
pkg-find tag_name:
  @uv run scripts/pkg_version.py {{tag_name}} decode-tag


[positional-arguments]
gh-ext *args:
  @uv run scripts/gh_ext.py {{args}}

[positional-arguments]
pkg-ext *args:
  @uv run scripts/pkg_ext.py {{args}}
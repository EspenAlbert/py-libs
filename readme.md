<p align="center">
    <a href="https://github.com/EspenAlbert/py-libs/actions/workflows/ci.yaml" target="_blank">
        <img src="https://github.com/EspenAlbert/py-libs/actions/workflows/ci.yaml/badge.svg">
    </a>
    <a href="https://pypi.org/project/model-lib/" target="_blank">
        <img src="https://img.shields.io/pypi/v/model-lib.svg">
    </a>
    <a href="https://pypi.org/project/model-lib/" target="_blank">
        <img src="https://img.shields.io/pypi/pyversions/model-lib.svg">
    </a>
    <a href="https://codecov.io/gh/EspenAlbert/py-libs" target="_blank">
        <img src="https://img.shields.io/codecov/c/github/EspenAlbert/py-libs?color=%2334D058" alt="Coverage">
    </a>
    <a href="https://github.com/psf/black" target="_blank">
            <img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black">
    </a>
    <a href="https://github.com/EspenAlbert/py-libs/blob/main/LICENSE" target="_blank">
            <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License">
    </a>
    <a href="https://github.com/pre-commit/pre-commit"><img src="https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit" alt="pre-commit" style="max-width:100%;"></a>

</p>

# py-libs (drastic changes coming for v1.0.0)

- An experiment for sharing python packages
- ~~[compose_chart_export](./compose_chart_export/readme.md)~~
	- `pip install compose-chart-export`
- ~~[docker_compose_parser](./docker_compose_parser/readme.md)~~
	- `pip install docker-compose-parser`
- [model_lib-pydantic base models with convenient dump methods](./model-lib/readme.md)
	- `pip install model-lib`
- [zero_lib-handy standalone scripts without 3rdparty dependencies](./zero-3rdparty/readme.md)
	- `pip install zero-3rdparty`

## Hierarchy

```mermaid
flowchart TD
    model_lib --> zero_3rdparty
    compose_chart_export --> model_lib
    docker_compose_parser --> model_lib
    compose_chart_export --> docker_compose_parser
    pants_py_deploy --> compose_chart_export
    pants_py_deploy --> docker_compose_parser

    click zero_3rdparty href "/py-libs/zero-3rdparty" "zero_3rdparty docs"
    click model_lib href "/py-libs/model-lib" "model_lib docs"
    click docker_compose_parser href "/py-libs/docker_compose_parser" "docker_compose_parser docs"
    click compose_chart_export href "/py-libs/compose_chart_export" "compose_chart_export docs"
    click pants_py_deploy href "/py-libs/_pants/pants_py_deploy" "pants_py_deploy docs"
```

- (Click) on a library to see the documentation
- The higher up in the hierarchy the more dependencies needs to be installed
	- e.g., `zero_3rdparty` has no dependencies and `pants_py_deploy` depends on all the others

## Local Installation

- [Install `just`](https://just.systems/man/en/introduction.html)
- [Install `uv`](https://docs.astral.sh/uv/getting-started/installation/)

```sh
pre-commit install --hook-type pre-push
uv sync
code .
```

## Release process
1. Do changes on your branch
2. Bump the versions you want to deploy
```sh
just pkg-version z beta # alpha/patch,etc.
just pkg-version m beta
```
3. Merge and wait for release to complete


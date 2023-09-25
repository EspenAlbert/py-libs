from __future__ import annotations

from compose_chart_export.ports import PrefixPort
from pants.engine.collection import Collection
from pants.engine.fs import FileContent
from pants.util.frozendict import FrozenDict
from pants.util.ordered_set import FrozenOrderedSet
from pants_py_deploy.compose_file import create_compose_files, modify_existing_compose
from pants_py_deploy.models import ComposeFiles, ComposeService

path1 = "docker_example/src/docker_example"
path_settings = "docker_example/src/docker_example/settings"
path_new_settings = "docker_example/src/docker_example/settings2"


def _create_compose_service(
    dependencies: list[str], extra_env_vars: dict[str, str] | None = None
) -> ComposeService:
    extra_env_vars = extra_env_vars or {}
    return ComposeService(
        path=path1,
        name="docker-example-arm",
        dependency_paths=FrozenOrderedSet(dependencies),
        image_tag="latest-arm",
        env_vars=FrozenDict(
            {"name": "__REQUIRED__", "env": "default", **extra_env_vars}
        ),
        ports=Collection[PrefixPort](
            [PrefixPort(prefix="/", port=8000, protocol="http")]
        ),
        healthcheck=FrozenDict(),
    )


def test_create_compose_files(file_regression):
    compose_service = _create_compose_service([path_settings])
    compose_files = ComposeFiles([compose_service])
    files = create_compose_files(new_paths={path1}, compose_files=compose_files)
    filename = "docker-compose-new"
    check_updated_compose(file_regression, filename, files)


def check_updated_compose(file_regression, filename, files):
    assert files
    compose_content = files[0]
    assert compose_content.path == f"{path1}/docker-compose.yaml"
    file_regression.check(
        compose_content.content.decode("utf-8"),
        extension=".yaml",
        basename=filename,
    )


_old_content = """\
version: '3'
services:
  docker-example-arm:
    image: docker-example-arm:latest-arm
    environment:
      name: __REQUIRED__
      env: default
    ports:
    - 8000:8000
    networks:
    - pants-default
networks:
  pants-default:
    external: true
"""


def test_modify_existing_compose(file_regression):
    service = _create_compose_service(
        [path_settings, path_new_settings], extra_env_vars={"new": "new_value"}
    )
    compose_files = ComposeFiles([service])
    old_content = FileContent(path=path1, content=_old_content.encode("utf-8"))
    updated = modify_existing_compose(
        compose_files=compose_files,
        digest_contents=[old_content],
    )
    check_updated_compose(file_regression, "docker-compose-modified", updated)

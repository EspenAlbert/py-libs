from docker_compose.compose_file import create_compose_files, modify_existing_compose
from docker_compose.models import ComposeFiles, ComposeService, EnvVar, FileEnvVars
from docker_compose.ports import PrefixPort
from pants.engine.fs import FileContent
from pants.util.ordered_set import FrozenOrderedSet

path1 = "docker_example/src/docker_example"
path_settings = "docker_example/src/docker_example/settings"
path_new_settings = "docker_example/src/docker_example/settings2"
env_vars = FileEnvVars(
    file_env_vars={
        path_settings: [
            EnvVar(name="name", default="__REQUIRED__"),
            EnvVar(name="env", default="default"),
        ]
    },
    file_port_info={
        path_settings: [PrefixPort(prefix="/", port=8000, protocol="http")]
    },
)


def _create_compose_service(dependencies: list[str]) -> ComposeService:
    return ComposeService(
        path=path1,
        name="docker-example-arm",
        dependency_paths=FrozenOrderedSet(dependencies),
        image_tag="latest-arm",
    )


def test_create_compose_files(file_regression):
    compose_service = _create_compose_service([path_settings])
    compose_files = ComposeFiles([compose_service])
    files = create_compose_files(
        new_paths={path1}, env_vars=env_vars, compose_files=compose_files
    )
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
    service = _create_compose_service([path_settings, path_new_settings])
    extra_env_vars = FileEnvVars(
        {
            **env_vars.file_env_vars,
            **{path_new_settings: [EnvVar(name="new", default="new_value")]},
        },
        {**env_vars.file_port_info},
    )
    compose_files = ComposeFiles([service])
    old_content = FileContent(path=path1, content=_old_content.encode("utf-8"))
    updated = modify_existing_compose(
        compose_files=compose_files,
        digest_contents=[old_content],
        env_vars=extra_env_vars,
    )
    check_updated_compose(file_regression, "docker-compose-modified", updated)

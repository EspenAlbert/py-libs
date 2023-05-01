from docker_compose import plugin
from docker_compose.fields import ComposeEnabledField
from pants.backend.docker.target_types import DockerImageTarget


def rules():
    return [
        *plugin.rules(),
        DockerImageTarget.register_plugin_field(ComposeEnabledField),
    ]

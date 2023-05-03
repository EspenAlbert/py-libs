from pants.backend.docker.target_types import DockerImageTarget
from pants_py_deploy import plugin
from pants_py_deploy.fields import (
    ComposeChartField,
    ComposeChartNameField,
    ComposeEnabledField,
)


def rules():
    return [
        *plugin.rules(),
        DockerImageTarget.register_plugin_field(ComposeEnabledField),
        DockerImageTarget.register_plugin_field(ComposeChartField),
        DockerImageTarget.register_plugin_field(ComposeChartNameField),
    ]

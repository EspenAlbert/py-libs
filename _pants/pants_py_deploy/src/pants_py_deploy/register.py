from pants_py_deploy import plugin
from pants_py_deploy.fields import ComposeEnabledField
from pants.backend.docker.target_types import DockerImageTarget


def rules():
    return [
        *plugin.rules(),
        DockerImageTarget.register_plugin_field(ComposeEnabledField),
    ]

from pants.backend.docker.target_types import DockerImageTarget
from pants_py_deploy import plugin
from pants_py_deploy.fields import (
    ComposeChartField,
    ComposeChartNameField,
    ComposeEnabledField,
    ComposeEnvExportField,
    HealthcheckField,
    TargetPortField,
    SecretEnvVarsField,
)


def rules():
    return [
        *plugin.rules(),
        DockerImageTarget.register_plugin_field(ComposeEnabledField),
        DockerImageTarget.register_plugin_field(ComposeChartField),
        DockerImageTarget.register_plugin_field(ComposeChartNameField),
        DockerImageTarget.register_plugin_field(ComposeEnvExportField),
        DockerImageTarget.register_plugin_field(HealthcheckField),
        DockerImageTarget.register_plugin_field(SecretEnvVarsField),
        DockerImageTarget.register_plugin_field(TargetPortField),
    ]

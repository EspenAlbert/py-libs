from typing import ClassVar

from pants.engine.target import (
    BoolField,
    DictStringToStringSequenceField,
    StringField,
    DictStringToStringField,
)
from pants.option.option_types import StrListOption
from pants.option.subsystem import Subsystem
from pants.util.frozendict import FrozenDict


class ComposeEnabledField(BoolField):
    alias = "compose_enabled"
    default = False
    help = "If set to true, it will create a docker-compose file in the same directory"


class ComposeChartField(StringField):
    alias = "compose_chart"
    default = ""
    help = "If set to a path, it will use the docker-compose file to export a chart"


class ComposeChartNameField(StringField):
    alias = "compose_chart_name"
    default = ""
    help = "Will not use the name of the docker-image if it is set"


class ComposeEnvExportField(DictStringToStringSequenceField):
    alias = "compose_env_export"
    default: ClassVar[FrozenDict[str, tuple[str]]] = FrozenDict()
    help = "dict(exclude_globs=['some_ignored_prefix*'], include_globs=['*port']), include_globs takes preference over exclude_globs"


class HealthcheckField(DictStringToStringField):
    alias = "app_healthcheck"
    default: ClassVar[FrozenDict[str, str]] = FrozenDict()
    help = "dict(port='8000', path='/health', interval='30s') see more options here: https://docs.docker.com/engine/reference/builder/#healthcheck"


COMPOSE_NETWORK_NAME = "pants-default"


class PyDeploySubsystem(Subsystem):
    options_scope = "py-deploy"
    name = "PyDeploy"
    help = "Control env-vars resolving for docker-compose files"

    env_vars_file_globs = StrListOption(
        flag_name="--env-vars-globs",
        default=lambda cls: ["**/settings.py"],
        help="patterns of files for finding env-vars",
    )

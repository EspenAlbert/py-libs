from typing import ClassVar, Optional, Iterable

from pants.engine.addresses import Address
from pants.engine.target import (
    BoolField,
    DictStringToStringSequenceField,
    StringField,
    DictStringToStringField,
    Field,
)
from pants.option.option_types import StrListOption
from pants.option.subsystem import Subsystem
from pants.util.frozendict import FrozenDict

from compose_chart_export.ports import PrefixPort


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


class TargetPortField(Field):
    alias = "app_ports"
    value: tuple[str, str, str]
    default = None
    help = "a sequence of (number, prefix, port_protocol{http|grpc|grpc-web|tcp|tls|udp|http2})"

    @classmethod
    def compute_value(
        cls, raw_value: Optional[Iterable[tuple[str, str, str]]], address: Address
    ) -> tuple[PrefixPort, ...]:
        if not raw_value:
            return tuple()
        return tuple(
            PrefixPort(prefix=prefix, port=int(port), protocol=protocol)
            for port, prefix, protocol in raw_value
        )


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

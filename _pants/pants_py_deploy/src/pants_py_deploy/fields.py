from typing import ClassVar

from pants.engine.target import BoolField, DictStringToStringSequenceField, StringField
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


COMPOSE_NETWORK_NAME = "pants-default"

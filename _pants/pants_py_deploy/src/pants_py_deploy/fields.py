from pants.engine.target import BoolField, StringField


class ComposeEnabledField(BoolField):
    alias = "compose_enabled"
    default = False
    help = "If set to true, it will create a docker-compose file in the same directory"


class ComposeChartField(StringField):
    alias = "compose_chart"
    default = ""
    help = "If set to a path, it will use the docker-compose file to export a chart"


COMPOSE_NETWORK_NAME = "pants-default"

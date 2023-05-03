from pants.engine.target import BoolField, StringField


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


COMPOSE_NETWORK_NAME = "pants-default"

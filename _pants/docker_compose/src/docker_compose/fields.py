from pants.engine.target import BoolField


class ComposeEnabledField(BoolField):
    alias = "compose_enabled"
    default = False
    help = "If set to true, it will create a docker-compose file in the same directory"


COMPOSE_NETWORK_NAME = "pants-default"

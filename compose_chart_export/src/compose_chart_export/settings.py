from zero_3rdparty.enum_utils import StrEnum


class ChartTemplate(StrEnum):
    DAEMONSET = "daemonset"
    DEPLOYMENT_ONLY = "deployment_only"
    SERVICE_DEPLOYMENT = "service_deployment"

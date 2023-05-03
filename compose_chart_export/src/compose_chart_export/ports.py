from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class StrEnumNoRepr(str, Enum):
    def __repr__(self) -> str:
        return str.__repr__(self)

    def __str__(self) -> str:
        return str.__str__(self)


class PortProtocol(StrEnumNoRepr):
    """See https://istio.io/latest/docs/ops/configuration/traffic-management.

    /protocol-selection/
    """

    grpc = "grpc"
    grpc_web = "grpc-web"
    http = "http"
    http2 = "http2"
    mongo = "mongo"
    tcp = "tcp"
    tls = "tls"
    udp = "udp"


@dataclass(frozen=True)
class PrefixPort:
    """Used for creating virtual services with ports that maps to paths.

    Example:
        warehouse1.dev.example.com/robot
        warehouse1.dev.example.com/frontend_grpc
        >>> prefix_port = PrefixPort(prefix='frontend_grpc_web', port=50051, protocol=PortProtocol.grpc_web)
        >>> prefix_port.as_kub_port_name(prefix_port)
        'grpc-web-fronte'
        >>> prefix_port = PrefixPort(prefix='/frontend_grpc', port=50051, protocol=PortProtocol.grpc)
        >>> prefix_port.as_kub_port_name(prefix_port)
        'grpc-frontend'


    Args:
        prefix: robot, frontend_grpc
        port: 8050, 50051
        protocol: http, grpc
    """

    prefix: str
    port: int
    protocol: PortProtocol | str

    def __post_init__(self):
        options = list(PortProtocol)
        assert (
            self.protocol in options
        ), f"unknown protocol: {self.protocol}, possibilities: {options}"

    @classmethod
    def as_kub_port_name(cls, value: PrefixPort):
        protocol = value.protocol
        prefix = value.prefix
        return cls.as_kub_port_name_raw(protocol, prefix)

    @classmethod
    def as_kub_port_name_raw(cls, protocol: PortProtocol, prefix: str):
        protocol_with_underscore = protocol.replace("-", "_")
        prefix = prefix.replace(protocol_with_underscore, "")
        if prefix == "/":
            prefix = "root"
        elif prefix.startswith("/"):
            prefix = prefix.lstrip("/")
        parts = [part for part in prefix.split("_") if part]
        maxlen = 15
        max_letters_from_each_part = (maxlen - len(protocol)) // len(parts)
        return (
            f"{protocol}-"
            + "-".join(part[:max_letters_from_each_part] for part in parts)
        )[:maxlen].rstrip("-")

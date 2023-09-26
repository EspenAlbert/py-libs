from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar


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
        >>> prefix_port2 = PrefixPort(prefix='/frontend_grpc', port=50052, protocol=PortProtocol.grpc)
        >>> prefix_port2.as_kub_port_name(prefix_port2)
        'grpc-frontend'
        >>> prefix_port2.find_alternative_name({"grpc-frontend"})
        'grpc-frontend2'
        >>> prefix_port3 = PrefixPort(prefix="/", port=8000, protocol=PortProtocol.http)
        >>> prefix_port3.as_kub_port_name(prefix_port3)
        'http-8000'


    Args:
        prefix: robot, frontend_grpc
        port: 8050, 50051
        protocol: http, grpc
    """

    prefix: str
    port: int
    protocol: PortProtocol | str

    KUB_PORT_MAX_LEN: ClassVar[int] = 15

    def __post_init__(self):
        options = list(PortProtocol)
        assert (
            self.protocol in options
        ), f"unknown protocol: {self.protocol}, possibilities: {options}"

    @classmethod
    def as_kub_port_name(cls, value: PrefixPort):
        protocol = value.protocol
        prefix = value.prefix
        return cls.as_kub_port_name_raw(protocol, prefix, str(value.port))

    @classmethod
    def as_kub_port_name_raw(
        cls, protocol: PortProtocol | str, prefix: str, no_prefix_name: str
    ):
        protocol_with_underscore = protocol.replace("-", "_")
        prefix = prefix.replace(protocol_with_underscore, "")
        if prefix == "/":
            prefix = no_prefix_name
        if prefix.startswith("/"):
            prefix = prefix.lstrip("/")
        parts = [part for part in prefix.split("_") if part]
        maxlen = 15
        max_letters_from_each_part = (maxlen - len(protocol)) // len(parts)
        return (
            f"{protocol}-"
            + "-".join(part[:max_letters_from_each_part] for part in parts)
        )[:maxlen].rstrip("-")

    def find_alternative_name(self, existing_names: set[str]) -> str:
        default_name: str = self.as_kub_port_name(self)
        if default_name not in existing_names:
            return default_name
        name_length = len(default_name)
        if name_length == self.KUB_PORT_MAX_LEN:
            default_name = default_name[:-1]
        for i in range(2, 10):
            name = f"{default_name}{i}"
            if name not in existing_names:
                return name
        raise ValueError(f"couldn't find alternative name for {self}")

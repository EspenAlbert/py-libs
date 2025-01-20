from pathlib import Path

import pytest

from compose_chart_export.chart_read import (
    read_app_version,
    read_chart_version,
    read_container_name,
    read_values,
)
from compose_chart_export.compose_export import (
    export_from_compose,
    parse_container_ports,
)
from compose_chart_export.ports import PrefixPort
from zero_3rdparty.file_utils import copy
from zero_3rdparty.future import ConcFuture

REG_DIR = Path(__file__).parent / "charts"
COMPOSE_DIR = Path(__file__).parent / "compose_files"


@pytest.mark.parametrize(
    "compose_file", COMPOSE_DIR.glob("*.yaml"), ids=lambda p: p.stem
)
def test_export_from_compose(compose_file, tmp_path):
    dest_path_future = ConcFuture()

    def copy_to_chart_path(chart_path: Path):
        dest_path = REG_DIR / chart_path.name
        copy(chart_path, dest_path, clean_dest=True)
        dest_path_future.set_result(dest_path)

    export_from_compose(
        compose_file,
        chart_version="0.0.1",
        chart_name=compose_file.stem,
        on_exported=copy_to_chart_path,
    )
    chart_export_path = dest_path_future.result(timeout=1)
    assert read_chart_version(chart_export_path) == "0.0.1"
    assert read_app_version(chart_export_path) == "0.0.1"
    assert read_values(chart_export_path)
    assert read_container_name(chart_export_path)


def test_parse_container_ports():
    compose_labels = {"chart_name": "app", "PORTS_EXTRA": "80"}
    assert parse_container_ports(compose_labels, []) == [
        PrefixPort(prefix="/", port=80, protocol="http")
    ]


def test_parse_container_ports_add_to_existing():
    compose_labels = {"chart_name": "app", "PORTS_EXTRA": "80"}
    assert parse_container_ports(compose_labels, [(80, 80), (8080, 8081)]) == [
        PrefixPort(prefix="/", port=80, protocol="http"),
        PrefixPort(prefix="/", port=8081, protocol="http"),
    ]

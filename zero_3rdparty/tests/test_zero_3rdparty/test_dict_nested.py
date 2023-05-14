from copy import deepcopy

import pytest
import xdoctest
from zero_3rdparty.dict_nested import read_nested, update


def test_doctests():
    xdoctest.doctest_module(read_nested.__module__)

d = {
    "apiVersion": "v1",
    "kind": "Service",
    "metadata": {
        "name": "kibana",
    },
    "spec": {
        "ports": [{"port": 443, "targetPort": 5601, "protocol": "TCP"}],
    },
}


@pytest.mark.parametrize(
    "path,new_value",
    [
        ("metadata.namespace", "kibana"),  # does not exist
        ("metadata.name", "kibana2"),  # existing value
    ],
)
def test_dict_updates(path, new_value):
    active_d = update(deepcopy(d), path, new_value)
    final_value = read_nested(active_d, path)
    assert final_value == new_value


@pytest.mark.parametrize(
    "path,new_value",
    [
        ("spec.ports.[1]", "port"),  # does not exist
        ("spec.ports.[0]", "port"),  # existing value
    ],
)
def test_list_updates(path, new_value):
    active_d = update(deepcopy(d), path, new_value)
    final_value = read_nested(active_d, path)
    assert final_value == new_value


def test_update_dict_inside_list():
    path = "spec.ports.[0].port"
    new_value = 5601
    active_d = update(deepcopy(d), path, new_value)
    assert active_d["spec"]["ports"][0]["port"] == 5601
    assert read_nested(active_d, path) == 5601


def test_update_ensure_parents():
    active_d = update(deepcopy(d), "metadata.labels.name", "kibana")
    assert active_d["metadata"]["labels"]["name"] == "kibana"


def test_update_ensure_parents_dict_and_list_path():
    active_d = update(deepcopy(d), "spec.containers.[0].name", "kibana")
    assert active_d["spec"]["containers"][0]["name"] == "kibana"


def test_update_list_type_hints():
    a_list = update([], simple_path="[0]", new_value="ok")
    a_list.append("ok2")
    assert a_list == ["ok", "ok2"]

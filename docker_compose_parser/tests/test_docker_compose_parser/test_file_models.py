from pathlib import Path

from docker_compose_parser.file_models import ComposeHealthCheck, iter_compose_info


def test_parse_es_file():
    path = Path(__file__).with_name("es.yaml")
    services = dict(iter_compose_info(path))
    expected_healthchecks = {
        "elasticsearch": ComposeHealthCheck(
            test='curl -s http://localhost:9200/_cluster/health | grep -vq \'"status":"red"\'',
            interval="30s",
            timeout="30s",
            start_period="0s",
            start_interval="5s",
            retries=10,
        ),
        "kibana": ComposeHealthCheck(
            test="curl --write-out 'HTTP %{http_code}' --fail --silent --output /dev/null http://localhost:5601/api/status",
            interval="30s",
            timeout="30s",
            start_period="0s",
            start_interval="5s",
            retries=20,
        ),
    }
    for service, healthcheck in expected_healthchecks.items():
        assert services[service].healthcheck == healthcheck


def test_parse_healthcheck_from_port_path():
    check = ComposeHealthCheck.parse_healthcheck({"port": "8000", "retries": "2"})
    assert check == ComposeHealthCheck(
        test="curl -f http://localhost:8000/ || exit 1",
        interval="30s",
        timeout="30s",
        start_period="0s",
        start_interval="5s",
        retries=2,
    )

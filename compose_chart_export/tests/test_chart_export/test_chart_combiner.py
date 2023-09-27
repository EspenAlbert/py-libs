from compose_chart_export.chart_combiner import combine
from zero_3rdparty.file_utils import ensure_parents_write_text, iter_paths_and_relative

_frozen_file = """\
# FROZEN
line1
line2"""

_no_update_file = """\
lineextra # noupdate
line1
line2
lineendextra # noupdate
lineendextra2 # noupdate
"""

_no_update_file_updated = """\
lineextra # noupdate
newline1
newline2
lineendextra # noupdate
lineendextra2 # noupdate
"""
_chart_yaml = """\
apiVersion: v2
name: combine-chart-example
type: application
version: 0.0.1
appVersion: 0.0.1
"""
_values_yaml_old = """\
replicas: 3 # should be kept
docker_example:
  PORT: '8000'
  env: default
  name: __REQUIRED__
  secret1_env_var1: KEEP_OLD # should be kept
  image: docker-example-amd-docker:latest-amd
  startupProbe:
    exec:
      command:
      - sh
      - -c
      - curl -f http://localhost:8000/health || exit 1
    initialDelaySeconds: 0
    periodSeconds: 3 # should be kept
    timeoutSeconds: 1 # should be kept
    failureThreshold: 10 # should be kept
existing_secret_secret1: ''
existing_secret_secret2: ''
some_extra_value: "my-extra-value" # should be kept
"""
_values_yaml_new = """\
replicas: 1
docker_example:
  PORT: '8000'
  env: default
  name: __REQUIRED__
  secret1_env_var1: DEFAULT1
  secret1_env_var2: DEFAULT2 # should be added
  secret2_env_var3: DEFAULT3 # should be added
  image: docker-example-amd-docker:latest-amd
  startupProbe:
    exec:
      command:
      - sh
      - -c
      - curl -f http://localhost:8000/health || exit 1
    initialDelaySeconds: 0
    periodSeconds: 30
    timeoutSeconds: 30
    failureThreshold: 3
existing_secret_secret1: ''
existing_secret_secret2: ''
"""

_combined_values_yaml = """\
replicas: 3
docker_example:
  PORT: '8000'
  env: default
  name: __REQUIRED__
  secret1_env_var1: KEEP_OLD
  secret1_env_var2: DEFAULT2
  secret2_env_var3: DEFAULT3
  image: docker-example-amd-docker:latest-amd
  startupProbe:
    exec:
      command:
      - sh
      - -c
      - curl -f http://localhost:8000/health || exit 1
    initialDelaySeconds: 0
    periodSeconds: 3
    timeoutSeconds: 1
    failureThreshold: 10
existing_secret_secret1: ''
existing_secret_secret2: ''
some_extra_value: my-extra-value
"""


def test_combine(tmp_path):
    old_paths = {
        "chart.yaml": _chart_yaml,
        "frozen.yaml": _frozen_file,
        "no_update.yaml": _no_update_file,
        "not_in_new.yaml": "old_content_unchanged\n",
        "templates/fully_replace.yaml": "override_me",
        "values.yaml": _values_yaml_old,
    }
    new_paths = {
        "chart.yaml": _chart_yaml,
        "frozen.yaml": "I WILL HAVE OLD CONTENT",
        "no_update.yaml": "newline1\nnewline2\n",
        "templates/fully_replace.yaml": "new_content_only\n",
        "values.yaml": _values_yaml_new,
    }
    expected_content = {
        "chart.yaml": _chart_yaml,
        "frozen.yaml": _frozen_file,
        "no_update.yaml": _no_update_file_updated,
        "not_in_new.yaml": "old_content_unchanged\n",
        "templates/fully_replace.yaml": "new_content_only\n",
        "values.yaml": _combined_values_yaml,
    }
    for rel_path, content in old_paths.items():
        ensure_parents_write_text(tmp_path / f"old/{rel_path}", content)

    for rel_path, content in new_paths.items():
        ensure_parents_write_text(tmp_path / f"new/{rel_path}", content)
    combine(tmp_path / "old", tmp_path / "new")

    for path, rel_path in iter_paths_and_relative(
        tmp_path / "new", "*", only_files=True
    ):
        expected = expected_content[rel_path]
        assert path.read_text() == expected

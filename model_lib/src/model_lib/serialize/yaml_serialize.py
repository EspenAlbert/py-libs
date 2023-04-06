from __future__ import annotations

import logging
import re
from io import StringIO
from os import getenv
from pathlib import Path
from typing import Callable, List, Mapping, Match

from model_lib.dump_functions import base_model_dumper
from model_lib.model_dump import PrimitiveT, register_dumper
from pydantic import BaseModel
from zero_lib.dict_nested import read_nested
from zero_lib.file_utils import PathLike

from model_lib import DumperExist

logger = logging.getLogger(__name__)


try:
    import yaml
except ModuleNotFoundError:
    allow_ignore = "yes,true,1"
    ignore_name = "IGNORE_YAML_MISSING"
    yaml_missing = Exception(f"pip install PyYAML or export {ignore_name}=yes")
    if getenv(ignore_name, "no").lower() in allow_ignore:
        logger.warning("PyYAML not installed, but ignored!")
    else:
        raise yaml_missing

    class yaml_dummy:
        def safe_dump(self, *_, **__):
            raise yaml_missing

        def safe_load(self, *_, **__):
            raise yaml_missing

        @property
        def Dumper(self):
            raise yaml_missing

        @property
        def SafeDumper(self):
            raise yaml_missing

    yaml = yaml_dummy()


def dump_yaml_str(
    data: object,
    width=1000,
    default_flow_style=False,
    allow_unicode: bool = True,
    sort_keys: bool = False,
) -> str:
    s = StringIO()
    try:
        yaml.safe_dump(
            data,
            s,
            default_flow_style=default_flow_style,
            width=width,
            allow_unicode=allow_unicode,
            sort_keys=sort_keys,
        )
    except yaml.representer.RepresenterError as e:
        _, maybe_base_model = e.args
        logger.warning(
            f"not yaml serializable, trying re-register: {type(maybe_base_model)}"
        )
        if isinstance(maybe_base_model, BaseModel):
            try:
                register_dumper(
                    type(maybe_base_model), base_model_dumper, allow_override="never"
                )
            except DumperExist:
                raise e from None
            return dump_yaml_str(
                data, width, default_flow_style, allow_unicode, sort_keys
            )
        raise e
    return s.getvalue()


def dump_yaml_file(path: PathLike, data: Mapping, width=1000):
    with open(path, "w") as f:
        yaml.safe_dump(data, stream=f, default_flow_style=False, width=width)
    return path


def parse_yaml_file(path: PathLike) -> dict:
    with open(str(path), "rt") as f:
        return yaml.safe_load(f)


def parse_yaml_str(payload: str) -> PrimitiveT:
    return yaml.safe_load(StringIO(payload))


class edit_yaml:
    def __init__(
        self,
        path: PathLike,
        yaml_path: str = None,
        out_file="",
        width=1000,
        read_only=False,
    ):
        """
        Args:
            yaml_path: either separated by spaces or .
        """
        self.path = path
        self.yaml_path = yaml_path
        if not out_file:
            out_file = path
        self.out_file = out_file
        self.width = width
        self.read_only = read_only

    def __enter__(self):
        with open(self.path) as f:
            self.loaded = yaml.safe_load(f)
            if self.yaml_path:
                self.to_update = read_nested(
                    self.loaded, self.yaml_path.replace(" ", ".")
                )
                return self.to_update
            return self.loaded

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            return False
        if self.read_only:
            return
        dump_yaml_file(self.out_file, self.loaded, self.width)


class edit_helm_template:
    yaml_path = "spec template spec containers"
    QUOTE_REPLACEMENT = "QUOTE"
    START_BRACKETS_REPLACEMENT = "'START_BRACKETS"
    END_BRACKETS_REPLACEMENT = "END_BRACKETS'"

    def make_template_loadable(self) -> None:
        """template -> yaml."""
        old_text = Path(self.path).read_text()
        self.template_lines = standalone_template_lines = []
        yaml_parts: List[str] = []
        for line in old_text.split("\n"):
            if line.startswith("{{"):
                standalone_template_lines.append(line)
            else:
                yaml_parts.append(line)

        converters: List[Callable[[str], str]] = [
            _replace_brackets,
            _indent_standalone_templates,
        ]
        new_text = "\n".join(yaml_parts)
        for converter in converters:
            new_text = converter(new_text)
        self.out_path.write_text(new_text)

    def dump_template_from_yaml(self) -> None:
        """yaml -> template."""
        template_yaml: str = self.out_path.read_text()
        converters: List[Callable[[str], str]] = [
            _dedent_standalone_brackets,
            _add_brackets,
            remove_quoted_values,
        ]
        for converter in converters:
            template_yaml = converter(template_yaml)
        template_lines = "\n".join(self.template_lines)
        final_template = "\n".join([template_lines, template_yaml]).lstrip("\n") + "\n"
        self.out_path.write_text(final_template)

    def __init__(
        self,
        path: PathLike,
        out_path: PathLike = None,
        yaml_path=None,
    ):
        self.path = Path(path)
        self.template_lines: List[str] = []
        self.out_path = out_path or path
        self.out_path = Path(self.out_path)

        self.edit_yaml = edit_yaml(self.out_path, yaml_path, width=1000)
        # TRANSFORM FILE
        self.make_template_loadable()

    def __enter__(self):
        return self.edit_yaml.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_val:
            self.edit_yaml.__exit__(exc_type, exc_val, exc_tb)
            return False
        self.edit_yaml.__exit__(exc_type, exc_val, exc_tb)
        # TRANSFORM FILE
        self.dump_template_from_yaml()


_start_bracket_re = re.compile(
    rf"'?{edit_helm_template.START_BRACKETS_REPLACEMENT[1:]}"
)
_end_bracket_re = re.compile(rf"{edit_helm_template.END_BRACKETS_REPLACEMENT[:-1]}'?")


#  yaml -> template


def _str_presenter(dumper, data: str):
    if "\n" in data:  # check for multiline string
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


class multiline_pipe_style:
    def __enter__(self):
        self.old_representer_dumper = yaml.Dumper.yaml_representers[str]
        self.old_representer_safe_dumper = yaml.SafeDumper.yaml_representers[str]
        yaml.add_representer(str, _str_presenter, yaml.Dumper)
        yaml.add_representer(str, _str_presenter, yaml.SafeDumper)

    def __exit__(self, exc_type, exc_val, exc_tb):
        yaml.add_representer(str, self.old_representer_dumper, yaml.Dumper)
        yaml.add_representer(str, self.old_representer_safe_dumper, yaml.SafeDumper)


def _add_brackets(raw_yaml: str) -> str:
    template = []
    start_bracket = edit_helm_template.START_BRACKETS_REPLACEMENT[1:]
    quote_replacement = edit_helm_template.QUOTE_REPLACEMENT
    for line in raw_yaml.split("\n"):
        if start_bracket in line:
            no_quotes = line.replace(quote_replacement, '"')
            with_start = _start_bracket_re.sub("{{", no_quotes)
            line = _end_bracket_re.sub("}}", with_start)
        if line:
            template.append(line)
    return "\n".join(template)


def _dedent_standalone_brackets(raw: str) -> str:
    return key_regex.sub(_remove_indent, raw)


_key_example = "'16': START_BRACKETS- include QUOTEcommon.labels.standardQUOTE . | nindent 8 END_BRACKETS"
key_regex = re.compile(r"^(\s+)'\d+': ('?START_BRACKETS.*)$", flags=re.M)


def _remove_indent(m: Match) -> str:
    template_content = m.group(2)
    if not template_content.startswith("'"):
        template_content = f"'{template_content}'"
    return m.group(1)[:-2] + template_content


#  template -> yaml


def _replace_brackets(raw_yaml: str) -> str:
    loadable = []
    for line in raw_yaml.split("\n"):
        if "{{" in line:
            line = _make_yaml_line(line)
        loadable.append(line)
    return "\n".join(loadable)


def _make_yaml_line(line):
    quote_replacement = edit_helm_template.QUOTE_REPLACEMENT
    start_replacement = edit_helm_template.START_BRACKETS_REPLACEMENT
    end_replacement = edit_helm_template.END_BRACKETS_REPLACEMENT
    return (
        line.replace('"', quote_replacement)
        .replace("{{", start_replacement)
        .replace("}}", end_replacement)
    )


def _indent_standalone_templates(raw: str) -> str:
    modified = []
    ended_with_colon = False
    indentation_level = -1
    for i, line in enumerate(raw.splitlines(keepends=False)):
        line_indentation_level = len(line) - len(line.lstrip(" "))
        if line.endswith(":"):
            indentation_level = line_indentation_level
            ended_with_colon = True
        elif (
            "START_BRACKETS" in line
            and ended_with_colon
            and line_indentation_level == indentation_level
        ):
            safe_str = line.lstrip(" ")
            line = (indentation_level + 2) * " " + f"'{i}': {safe_str}"
        else:
            ended_with_colon = False
            indentation_level = -1
        modified.append(line)
    return "\n".join(modified)


sub_quoted = re.compile(r"'\{\{.*?\}\}'$", flags=re.M)


def remove_quotes(m: Match) -> str:
    return m.group(0)[1:-1]


def remove_quoted_values(raw: str):
    """After the dump the deployment.yaml will look like:

            - name: grpc_max_message_size
              value: '{{ .Values.grpc_max_message_size | quote }}'
    Notice      -----^-------------------------------------------^
    These extra quotes needs to be removed
    """
    return sub_quoted.sub(remove_quotes, raw)

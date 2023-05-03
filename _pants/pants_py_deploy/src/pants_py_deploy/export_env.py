from __future__ import annotations

import ast
import dataclasses
import logging
import typing
from pydoc import locate

from compose_chart_export.ports import PrefixPort

logger = logging.getLogger(__name__)
NodeType = typing.TypeVar("NodeType", bound=ast.AST)
REQUIRED = "__REQUIRED__"


@dataclasses.dataclass
class ClsModifier(typing.Generic[NodeType], ast.NodeTransformer):
    skip_settings: set[str] = dataclasses.field(default_factory=set)

    @property
    def node_type(self) -> typing.Type[NodeType]:
        generic_base = type(self).__orig_bases__[0]
        return typing.get_args(generic_base)[0]

    def __call__(self, node: NodeType) -> typing.Optional[NodeType]:
        raise NotImplementedError()

    def visit_ClassDef(self, node: ast.ClassDef) -> typing.Optional[ast.ClassDef]:
        if node.name in self.skip_settings:
            print(f"skipping: {node.name}")
            return None
        bases = {base.id for base in node.bases}
        if "BaseSettings" not in bases and "BaseEnvVars" not in bases:
            return None
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (self.node_type,)):
                child = typing.cast(NodeType, child)
                if self(child) is None:
                    node.body.remove(child)
        return node


def assign_as_name_value(
    assign: typing.Union[ast.Assign, ast.AnnAssign]
) -> typing.Optional[typing.Tuple[str, ast.AST]]:
    targets = assign.targets if isinstance(assign, ast.Assign) else [assign.target]
    if (name := targets[0]) and isinstance(name, ast.Name):
        return name.id, assign.value


def constant_value(constant: ast.Constant) -> str:
    assert isinstance(constant, ast.Constant), f"not ast.Constant: {constant}"
    return constant.value


def as_kwargs(call: ast.Call):
    kwargs = {}
    for keyword in call.keywords:
        assert isinstance(keyword, ast.keyword)
        value = keyword.value
        keyword_name = keyword.arg
        if keyword_name == "default_factory":
            if isinstance(value, ast.Lambda):
                kwargs[keyword_name] = "__FACTORY__lambda"
            else:
                kwargs[keyword_name] = f"__FACTORY__{value.id}"
        elif isinstance(value, ast.Name):
            assert value.id in [
                "RANDOM_STRING",
                "UNKNOWN",
            ], f"don't know how to decode: {value.id}"

            kwargs[keyword_name] = REQUIRED
        else:
            kwargs[keyword_name] = constant_value(value)
    return kwargs


def find_arg(call: ast.Call) -> str:
    assert len(call.args) == 1
    arg_0 = call.args[0]
    assert isinstance(arg_0, ast.Constant)
    return constant_value(arg_0)


@dataclasses.dataclass
class FindPrefix(ClsModifier[ast.ClassDef]):
    env_var_prefix: str = dataclasses.field(init=False, default="")

    def __call__(self, node: ast.ClassDef) -> ast.ClassDef | None:
        if node.name == "Config":
            for child in ast.iter_child_nodes(node):
                if isinstance(child, ast.Assign):
                    if name_value := assign_as_name_value(child):
                        var_name, value = name_value
                        if var_name == "env_prefix":
                            constant = child.value
                            assert isinstance(constant, ast.Constant)
                            self.env_var_prefix = constant.value
        return node


@dataclasses.dataclass
class EnvReader(ClsModifier[ast.AnnAssign]):
    prefix: str = ""
    env_vars: typing.Dict[str, object] = dataclasses.field(default_factory=dict)
    ports: typing.List[PrefixPort] = dataclasses.field(default_factory=list)

    @property
    def env_vars_str(self):
        return {key: str(v) for key, v in self.env_vars.items()}

    def __call__(self, node: ast.AnnAssign) -> typing.Optional[ast.AnnAssign]:
        if name_value := assign_as_name_value(node):
            name, value = name_value
            name_with_prefix = f"{self.prefix}{name}"
            node_annotation = node.annotation
            if (
                isinstance(node_annotation, ast.Subscript)
                and node_annotation.value.id == "ClassVar"
            ):
                return node
            if isinstance(value, ast.Constant):
                self.env_vars[name_with_prefix] = value.value
            elif value is None:
                self.env_vars[name_with_prefix] = REQUIRED
            elif isinstance(value, ast.Call):
                kwargs = as_kwargs(value)
                if value.func.id == "port_info":
                    port = (
                        kwargs.get("default") or kwargs.get("number") or find_arg(value)
                    )
                    prefix_port = PrefixPort(
                        prefix=kwargs["url_prefix"],
                        port=port,
                        protocol=kwargs["protocol"],
                    )
                    self.ports.append(prefix_port)
                    self.env_vars[name_with_prefix] = port
                if docker_default := kwargs.get("docker_default"):
                    self.env_vars[name_with_prefix] = docker_default
                elif factory := kwargs.get("default_factory"):
                    self.env_vars[name_with_prefix] = factory
                else:
                    if override_env := kwargs.get("env"):
                        name_with_prefix = override_env
                    try:
                        default = kwargs["default"]
                    except KeyError:
                        try:
                            default = find_arg(value)
                        except AssertionError:
                            default = "__REQUIRED__"
                    if name_with_prefix not in self.env_vars:
                        self.env_vars[name_with_prefix] = default
            elif isinstance(value, ast.Attribute):
                module = value.value
                assert isinstance(module, ast.Name)
                self.env_vars[name_with_prefix] = locate(f"{module.id}.{value.attr}")
            elif isinstance(value, ast.List):
                self.env_vars[name_with_prefix] = "[]"
            elif isinstance(value, ast.Name) and value.id == "UNKNOWN":
                self.env_vars[name_with_prefix] = REQUIRED
            else:
                logger.info(f"unknown field {value!r} for {name_with_prefix}")
                self.env_vars[name_with_prefix] = REQUIRED
        return node


class EnvAndPorts(typing.NamedTuple):
    env: typing.Dict[str, str]
    ports: typing.List[PrefixPort]


def read_env_and_ports(
    py_script: str, skip_settings: set[str] | None = None
) -> EnvAndPorts:
    skip_settings = skip_settings or set()
    tree = ast.parse(py_script, type_comments=True)
    prefix_finder = FindPrefix(skip_settings=skip_settings)
    prefix_finder.visit(tree)
    env_reader = EnvReader(
        skip_settings=skip_settings, prefix=prefix_finder.env_var_prefix
    )
    env_reader.visit(tree)
    return EnvAndPorts(env_reader.env_vars_str, env_reader.ports)

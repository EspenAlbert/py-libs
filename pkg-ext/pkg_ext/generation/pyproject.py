from model_lib.serialize import dump
from model_lib.serialize.parse import parse_dict

from pkg_ext.models import pkg_ctx


def update_pyproject_toml(ctx: pkg_ctx, new_version: str):
    path = ctx.settings.pyproject_toml
    if not path.exists():
        return
    pyproject = parse_dict(path)
    pyproject["project"]["version"] = new_version
    pyproject_toml = dump(pyproject, "toml_compact")
    path.write_text(pyproject_toml)

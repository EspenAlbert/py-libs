from typing import Any, cast

import tomlkit

from pkg_ext.context import pkg_ctx


def update_pyproject_toml(ctx: pkg_ctx, new_version: str):
    path = ctx.settings.pyproject_toml
    if not path.exists():
        return
    doc = tomlkit.loads(path.read_text())
    project = cast(dict[str, Any], doc["project"])
    project["version"] = new_version
    path.write_text(tomlkit.dumps(doc))

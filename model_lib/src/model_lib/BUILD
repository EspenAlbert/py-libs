py_package(
    description="base models, metadata, and how to dump them to json|yaml",
    extra_dependencies=[
        "!!//3rdparty#orjson@resolve=python-default",
        "!!//3rdparty#tomlkit@resolve=python-default",
        "!!//3rdparty:pydantic_v2_settings",  # settings are optional
    ],
    extras_require={
        "json": ["orjson>=3.6.5"],
        "toml": ["tomlkit>=0.12.1"],
        "full": [
            "orjson>=3.6.5",
            "tomlkit>=0.12.1",
            "pydantic-settings>=2.0.3",
            "pydantic>=2.2",
        ],
    },
)

python_requirements(
    module_mapping={
        "GitPython": ["git"],
        "PyYaml": ["yaml"],
        "pytest-freezegun": ["freezegun"],
    },
    resolve=parametrize("python-default", "pydantic-v1"),
)

python_requirement(
    name="pydantic_v1",
    requirements=["pydantic==1.10.2"],
    resolve="pydantic-v1",
    # hack to avoid "Pants cannot infer owners"
    modules=["pydantic", "pydantic_core", "pydantic_settings"],
)
python_requirement(
    name="pydantic_v2_settings",
    requirements=["pydantic-settings>=2.0.3"],
    resolve="python-default",
    modules=["pydantic_settings"],
)

python_requirement(
    name="pydantic_v1_or_later",
    requirements=["pydantic>=1.10.2,<3"],
    resolve="python-default",
    modules=["pydantic", "pydantic_core"],
)

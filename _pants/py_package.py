VERSION = "0.0.25b1"
def py_package(
    *,
    description: str,
    extra_dependencies: list[str] = None,
    resolve: str = "python-default",
    distribution_name: str = "",
    extras_require: dict = None,
):
    parent = build_file_dir()
    folder_name = parent.name
    extra_dependencies = extra_dependencies or []
    all_dependencies = [
        f":{folder_name}@resolve={resolve}",
        f"!!//3rdparty:pydantic_v2",
        f"//3rdparty:pydantic_v1_or_later",
    ] + extra_dependencies
    resources(name="py-typed", sources=["py.typed"])
    python_sources(sources=["*.py"], dependencies=[":py-typed"])
    distribution_name = distribution_name or folder_name.replace("_", "-")
    assert (
        distribution_name != folder_name
    ), f"cannot use the same name for python_distribution as the folder @ {parent}"
    extras_require = extras_require or {}
    extras_require.update({
        "pydantic_v1": ["pydantic>=1.10.2,<=2"],
        "pydantic_v2": ["pydantic>=2.1.1,<=3", "pydantic-settings>=2.0.3"],
    })
    python_distribution(
        name=distribution_name,
        # orjson is not a hard requirement
        dependencies=all_dependencies,
        long_description_path=f"{folder_name}/readme.md",
        provides=setup_py(
            name=distribution_name,
            version=VERSION,
            description=description,
            author="Espen Albert",
            classifiers=[
                "Programming Language :: Python :: 3.9",
                "Programming Language :: Python :: 3.10",
            ],
            extras_require=extras_require or {},
            long_description_content_type="text/markdown",
            license="MIT",
            url="https://github.com/EspenAlbert/py-libs",
        ),
        wheel=True,
        sdist=False,
        repositories=["@pypi"],
    )

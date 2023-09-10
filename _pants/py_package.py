VERSION = "0.0.28a2"
CLASSIFIERS = (
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Development Status :: 3 - Alpha",
)
PROJECT_URLS = (
    ("Source", "https://github.com/EspenAlbert/py-libs/tree/main/"),
    ("Documentation", "https://espenalbert.github.io/py-libs/"),
)


def py_package(
    *,
    description: str,
    extra_dependencies: list[str] = None,
    resolve: str = "python-default",
    distribution_name: str = "",
    extras_require: dict = None,
    explicit_dependencies: list[str] = None,
    is_root_package: bool = False,
):
    version = env("VERSION", VERSION)
    parent = build_file_dir()
    folder_name = parent.name
    extra_dependencies = extra_dependencies or []
    resolve_ref = f"@resolve={resolve}" if resolve else ""
    all_dependencies = [f":{folder_name}{resolve_ref}"] + extra_dependencies
    resources(name="py-typed", sources=["py.typed"])
    python_sources(sources=["*.py"], dependencies=[":py-typed"])
    distribution_name = distribution_name or folder_name.replace("_", "-")
    assert (
        distribution_name != folder_name
    ), f"cannot use the same name for python_distribution as the folder @ {parent}"
    extras_require = extras_require or {}
    project_urls = dict(PROJECT_URLS)
    if not is_root_package:
        project_urls = {k: f"{v}{folder_name}" for k, v in PROJECT_URLS}
    description_path = "readme.md" if is_root_package else f"{folder_name}/readme.md"
    python_distribution(
        name=distribution_name,
        dependencies=explicit_dependencies or all_dependencies,
        long_description_path=description_path,
        provides=setup_py(
            name=distribution_name,
            version=version,
            description=description,
            author="Espen Albert",
            classifiers=CLASSIFIERS,
            extras_require=extras_require or {},
            long_description_content_type="text/markdown",
            license="MIT",
            project_urls=project_urls,
        ),
        wheel=True,
        sdist=False,
        repositories=["@pypi"],
    )

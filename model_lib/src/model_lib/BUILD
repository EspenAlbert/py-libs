resources(name="py-typed", sources=["py.typed"])
python_sources(sources=["*.py"], dependencies=[":py-typed"])
python_distribution(
    name="model-lib",
    # orjson is not a hard requirement
    dependencies=[":model_lib", "!!//3rdparty#orjson"],
    long_description_path="model_lib/readme.md",
    provides=setup_py(
        name="model-lib",
        version="0.0.23",
        description="base models, metadata, and how to dump them to json|yaml",
        author="Espen Albert",
        classifiers=[
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
        ],
        extras_require={"json": ["orjson>=3.6.5"]},
        long_description_content_type="text/markdown",
        license="MIT",
        url="https://github.com/EspenAlbert/py-libs",
    ),
    wheel=True,
    sdist=False,
    repositories=["@pypi"],
)

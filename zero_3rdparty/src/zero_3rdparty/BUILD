resources(name="py-typed", sources=["py.typed"])
python_sources(sources=["*.py"], dependencies=[":py-typed"])
python_distribution(
    name="zero-3rdparty",
    dependencies=[":zero_3rdparty"],
    provides=setup_py(
        name="zero-3rdparty",
        version="0.0.21",
        description="zero_lib modules without 3rd-party dependencies",
        author="Espen Albert",
        classifiers=[
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
        ],
        license="MIT",
        url="https://github.com/EspenAlbert/py-libs",
    ),
    wheel=True,
    sdist=False,
    repositories=["@pypi"],
)

python_sources(resolve=parametrize("pants-plugins", "python-default"))
python_distribution(
    name="zero-3rdparty",
    dependencies=[":zero_3rdparty@resolve=python-default"],
    provides=setup_py(
        name="zero-3rdparty",
        version="0.0.9",
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

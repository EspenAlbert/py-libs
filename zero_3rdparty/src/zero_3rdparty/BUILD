python_sources()
python_distribution(
    name="zero-3rdparty",
    dependencies=[":zero_3rdparty"],
    provides=setup_py(
        name="zero-3rdparty",
        version="0.0.7",
        description="zero_lib modules without 3rd-party dependencies",
        author="Espen Albert",
        classifiers=[
            "Programming Language :: Python :: 3.10",
        ],
        license="MIT"
    ),
    wheel=True,
    sdist=False,
    repositories=["@pypi"],
)

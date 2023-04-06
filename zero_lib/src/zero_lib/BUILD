python_sources()
python_distribution(
    name="zero-lib",
    dependencies=[":zero_lib"],
    provides=setup_py(
        name="zero-lib",
        version="0.0.1",
        description="zero_lib modules without 3rd-party dependencies",
        author="Espen Albert",
        classifiers=[
            "Programming Language :: Python :: 3.10",
        ],
    ),
    wheel=True,
    sdist=False,
)

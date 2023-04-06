python_sources(name="model_lib")
python_distribution(
    name="model-lib",
    dependencies=[":model_lib"],
    provides=setup_py(
        name="model-lib",
        version="0.0.1",
        description="base models, metadata, and how to dump them to json|yaml",
        author="Espen Albert",
        classifiers=[
            "Programming Language :: Python :: 3.10",
        ],
    ),
    wheel=True,
    sdist=False,
    repositories=["@pypi"],
)

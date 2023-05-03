python_sources()
python_distribution(
    name="docker-compose-parser",
    dependencies=[":docker_compose_parser"],
    provides=setup_py(
        name="docker-compose-parser",
        version="0.0.14",
        description="Small package for modifying/reading docker-compose files",
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

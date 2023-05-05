python_sources()
python_distribution(
    name="pants-py-deploy",
    dependencies=[":pants_py_deploy"],
    long_description_path="_pants/pants_py_deploy/readme.md",
    provides=setup_py(
        name="pants-py-deploy",
        version="0.0.15.rc4",
        description="Make it easy to maintain docker-compose files and helm-charts across projects with pants-py-deploy",
        author="Espen Albert",
        classifiers=[
            "Programming Language :: Python :: 3.9",
        ],
        long_description_content_type="text/markdown",
        license="MIT",
        url="https://github.com/EspenAlbert/py-libs",
    ),
    wheel=True,
    sdist=False,
    repositories=["@pypi"],
)

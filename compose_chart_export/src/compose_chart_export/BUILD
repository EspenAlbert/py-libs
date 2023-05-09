python_sources()
python_distribution(
    name="compose-chart-export",
    dependencies=[":compose_chart_export"],
    long_description_path="compose_chart_export/readme.md",
    provides=setup_py(
        name="compose_chart_export",
        version="0.0.16rc1",
        description="compose_agent_export for docker-compose -> helm chart",
        author="Espen",
        classifiers=[
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
        ],
    ),
    wheel=True,
    sdist=False,
    repositories=["@pypi"],
)

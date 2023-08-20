resources(name="json", sources=["test_dump_functions/*.json"])
python_test_utils(name="conftest", resolve=parametrize("python-default", "pydantic-v1"))
python_tests(
    dependencies=[":json"],
    interpreter_constraints=test_versions,
    # resolve=parametrize("python-default", "pydantic-v1")
)

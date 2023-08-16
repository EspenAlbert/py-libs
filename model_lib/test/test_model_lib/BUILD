resources(name="json", sources=["test_dump_functions/*.json"])
python_test_utils(name="conftest", resolve=parametrize("python-default", "pydantic-v1"))
python_tests(
    dependencies=[":json"],
    interpreter_constraints=parametrize(py39=["==3.9.*"], py310=["==3.10.*"]),
    # resolve=parametrize("python-default", "pydantic-v1")
)

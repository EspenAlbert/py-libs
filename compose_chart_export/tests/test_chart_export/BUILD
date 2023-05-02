resources(name="reg", sources=["charts/*", "compose_files/*"])
python_tests(
    dependencies=[":reg"],
    interpreter_constraints=parametrize(py39=["==3.9.*"], py310=["==3.10.*"]),
)

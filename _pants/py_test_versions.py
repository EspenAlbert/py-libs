def test_params() -> dict:
    return dict(
        interpreter_constraints=parametrize(
            py39=["==3.9.*"], py310=["==3.10.*"], py311=["==3.11.*"]
        ),
        skip_mypy=True,
    )
